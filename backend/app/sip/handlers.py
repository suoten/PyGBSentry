# -------------------------------------------------------------------------
# 🚀 Project: PyGBSentry
# ✍️ Author: suoten
# 📧 Email: suoten@163.com
# 📄 License: MIT
# -------------------------------------------------------------------------

import uuid
from xml.sax.saxutils import escape as _xml_escape

from app.sip.message import SipMessage
from app.sip.auth import DigestAuth
from app.sip.send import send_sip_bytes, send_sip_message
from app.core.config import settings, sip_host_for_contact
from app.sip.state_backend import get_sip_state_backend
from app.db.session import AsyncSessionLocal
from app.models.asset import Asset
from app.models.platform import ParentPlatform
from app.models.resource import Resource
from app.models.alarm import Alarm
from app.models.alarm_escalation import AlarmEscalation
from app.models.alarm_link_rule import AlarmLinkRule
import app.sip.commander as sip_commander_module
from app.sip.catalog import handle_catalog_response
from app.sip.response_handler import handle_invite_response
from app.sip.record_handler import handle_record_info_response
from app.api.v1.endpoints.alarms import alarm_manager
from app.services.notification_service import notification_service
from app.core.plugin_manager import plugin_manager, HOOK_ON_DEVICE_REGISTER, HOOK_ON_ALARM, HOOK_ON_SIP_RECEIVE, HOOK_ON_SIP_SEND, HOOK_ALARM_RECORD_LINK, HOOK_ON_MOBILE_POSITION
from app.models.stream_session import StreamSession
from app.models.device_position import DevicePosition
from app.services.commercial_guard import check_device_quota
from app.core.xml_utils import parse_xml, get_xml_text, local_name
from app.sip.catalog_runtime import patch_device_catalog_runtime, utc_now_iso
from app.models.platform_catalog_resource import PlatformCatalogResource
from app.models.platform_runtime import PlatformRuntime
from app.sip.trace_events import should_warn_unknown_event_once
from app.services.sip_trace_store import schedule_store_sip_trace
from sqlalchemy import select, update, delete, func
from loguru import logger  # 统一使用 loguru 替代 logging
import datetime
import asyncio
import json
from email.utils import format_datetime
import re
import random
import string
import hashlib
import hmac
import time
import secrets

# P4 魔法数字→命名常量
_SIP_DEFAULT_PORT = 5060
_SIP_DEFAULT_EXPIRES = 3600
_SIP_MAX_FORWARDS_DEFAULT = 70
_SIP_REGISTER_GRACE_FACTOR = 1.2
_SIP_MAX_GRACE_SECONDS = 300
_SIP_T1_SECONDS = 1.0
_SIP_SUBSCRIBE_DEFAULT_EXPIRES = 3600
_SIP_CATALOG_SN_MAX = 9999

_DIGEST_NONCE_TTL_SECONDS = int(getattr(settings, "SIP_DIGEST_NONCE_TTL_SECONDS", 300) or 300)

_background_tasks: set[asyncio.Task] = set()

# 信令路由循环防护 — 重复请求检测缓存
_SEEN_REQUESTS: dict[str, float] = {}  # key: "Call-ID~CSeq" -> timestamp
_SEEN_REQUESTS_MAX = 5000
_SEEN_REQUESTS_TTL = 300  # 5 minutes


def _bg_create_task(coro):
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


async def _cleanup_device_resources(gb_id: str) -> None:
    # REGISTER expires=0 should clean up subscriptions, stream sessions, and SSRC
    try:
        from app.sip.subscribe_manager import subscribe_manager
        await subscribe_manager.remove_all_for_device(gb_id)
    except Exception as e:
        logger.warning(f"Failed to remove subscriptions for deregistered device {gb_id}: {e}")
    # S-09 防止double-free — release_stream_session已删除DB记录，
    # 第二段只处理release_stream_session未能成功清理的会话
    _released_session_ids: set = set()
    try:
        async with AsyncSessionLocal() as session:
            from app.models.stream_session import StreamSession
            from app.models.asset import Asset
            from app.services.stream_session_service import release_stream_session
            # S-01 每个session使用独立DB会话，避免commit后ORM对象detached导致后续会话跳过清理
            result = await session.execute(
                select(StreamSession).join(Asset, StreamSession.asset_id == Asset.id).where(Asset.gb_id == gb_id)
            )
            sessions = result.scalars().all()
            session_ids = [str(ss.id) for ss in sessions]
        for sid in session_ids:
            try:
                async with AsyncSessionLocal() as inner_session:
                    ss_result = await inner_session.execute(select(StreamSession).where(StreamSession.id == sid))
                    ss = ss_result.scalars().first()
                    if ss:
                        await release_stream_session(inner_session, ss, wait_bye_response=False, reason="device_deregistered")
                        await inner_session.commit()
                        _released_session_ids.add(sid)
            except Exception as e:
                logger.warning(f"Failed to release stream session {sid} for deregistered device {gb_id}: {e}")
    except Exception as e:
        logger.warning(f"Failed to cleanup stream sessions for deregistered device {gb_id}: {e}")
    # GB28181协议 — 设备离线后清理活跃StreamSession
    # S-09 只删除release_stream_session未能成功清理的会话，避免double-free
    # W-05 使用同一个session上下文避免两段清理间竞态窗口
    try:
        async with AsyncSessionLocal() as session:
            from app.models.stream_session import StreamSession
            from app.models.asset import Asset
            asset_result = await session.execute(select(Asset).where(Asset.gb_id == gb_id))
            asset = asset_result.scalars().first()
            if asset:
                sessions_result = await session.execute(
                    select(StreamSession).where(StreamSession.asset_id == asset.id)
                )
                for ss in sessions_result.scalars().all():
                    if str(ss.id) not in _released_session_ids:
                        await session.delete(ss)
                await session.commit()
    except Exception as e:
        logger.warning(f"Failed to cleanup StreamSession for offline device {gb_id}: {e}")
    # W-04 设备注销时清理DialogManager中关联的Dialog条目
    try:
        from app.sip.dialog_manager import dialog_manager
        await dialog_manager.terminate_dialogs_by_device(gb_id)
    except Exception as e:
        logger.warning(f"Failed to cleanup dialogs for device {gb_id}: {e}")


def _issue_digest_nonce() -> str:
    return DigestAuth.generate_nonce()


async def _validate_digest_replay(auth_params: dict, fallback_user: str) -> tuple[bool, str]:
    """
    校验 Digest Auth 的 replay protection。
    在生产环境（APP_ENV=prod/production）默认启用严格模式：
    1. nonce 格式校验：必须是 "timestamp:random:hmac_sig" 三段式
    2. nonce 过期检查：超过 _DIGEST_NONCE_TTL_SECONDS 则拒绝（stale nonce）
    3. nc 重放检查：同一 (user, nonce) 的 nc 值不能比记录的更小
    4. nonce 签名校验：hmac(secret, timestamp:random) == sig
    非生产环境默认宽松，仅警告，不阻断。
    """
    # default to strict mode for all environments, not just production
    # 消除_strict=None后立即if _strict is None的冗余逻辑
    _relaxed = str(getattr(settings, "SIP_AUTH_RELAXED", "") or "").lower() in {"true", "1", "yes"}
    _strict = not _relaxed

    # W-10 SIP_AUTH_RELAXED模式下保留nonce过期和HMAC签名校验，仅放宽nc重放检查
    nonce: str = str(auth_params.get("nonce") or "")
    nc: str = str(auth_params.get("nc") or "00000001")
    user: str = str(auth_params.get("username") or fallback_user or "")

    # 1. 格式检查：三段式 timestamp:random:signature
    parts = nonce.split(":")
    if len(parts) != 3:
        if _strict:
            return False, "invalid nonce format"
        logger.warning(f"[DigestAuth] nonce format invalid (not 3 parts), allowing in non-strict mode: {nonce[:32]}...")
        return True, ""

    ts_str, rnd, sig = parts
    try:
        ts = int(ts_str)
    except ValueError:
        if _strict:
            return False, "invalid nonce timestamp"
        logger.warning(f"[DigestAuth] nonce timestamp not integer, allowing in non-strict mode")
        return True, ""

    # 2. 时间戳过期检查（relaxed模式下也保留）
    current_ts = int(time.time())
    if current_ts - ts > _DIGEST_NONCE_TTL_SECONDS:
        reason = "stale nonce"
        logger.warning(f"[DigestAuth] stale nonce (age={current_ts - ts}s > {_DIGEST_NONCE_TTL_SECONDS}s)")
        return False, reason

    # 3. HMAC 签名校验：确保 nonce 是我们签发的（relaxed模式下也保留）
    # FIXED-P0: 优先使用 SIP_NONCE_SECRET，与 auth.py generate_nonce() 保持一致
    secret = (getattr(settings, "SIP_NONCE_SECRET", "") or "").encode("utf-8", errors="ignore")
    if not secret:
        secret = (getattr(settings, "SECRET_KEY", "") or "").encode("utf-8", errors="ignore")
    if not secret or secret == b"":
        logger.warning("[DigestAuth] SECRET_KEY is empty, cannot verify nonce HMAC signature reliably")
        return False, "SECRET_KEY not configured, cannot verify nonce signature"
    msg = f"{ts}:{rnd}".encode("utf-8")
    expected_sig = hmac.new(secret, msg, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        logger.warning("[DigestAuth] nonce HMAC mismatch (possible replay attack)")
        return False, "nonce signature mismatch (possible replay attack)"

    # 4. nc（nonce count）重放检查（relaxed模式下放宽）
    try:
        nc_val = int(nc, 16)
    except ValueError:
        if _strict:
            return False, "invalid nc format"
        logger.warning(f"[DigestAuth] nc not hex integer: {nc}, allowing in non-strict mode")
        return True, ""

    try:
        backend = get_sip_state_backend()
        nc_valid = await backend.check_nonce_nc(str(user), str(nonce), int(nc_val))
        if not nc_valid:
            reason = f"nc replay: received {nc_val}"
            if _strict:
                return False, "replay_detected"
            logger.warning(f"[DigestAuth] {reason}, allowing in non-strict mode")
            return True, ""
    except Exception as e:
        if _strict:
            logger.error(f"[DigestAuth] replay check backend failure (fail-close): {e}")
            return False, "replay_check_backend_unavailable"
        logger.warning(f"Digest replay check failed (non-strict, allowing): {e}")

    return True, ""


async def send_response(transport, proto: str, addr: tuple, response: SipMessage):
    if transport is None or getattr(transport, 'is_closing', lambda: False)():
        return
    _bg_create_task(plugin_manager.emit(HOOK_ON_SIP_SEND, response, addr, proto))
    try:
        from app.sip.server import sip_server
        from app.sip.transactions import tx_key_from_response, server_tx_manager
        await sip_server.cache_response(response)
        key = tx_key_from_response(response)
        await server_tx_manager.update_state(key, response)
    except Exception as e:
        logger.warning(f"Failed to cache SIP response or update transaction state: {e}")
    data = response.to_bytes()
    # for critical 2xx responses over TCP, use await_drain to ensure delivery
    _is_critical = bool(response.status_code and 200 <= response.status_code < 300)
    if proto == "UDP":
        dest_addr = addr
        via = response.get_header("Via")
        if via:
            via_parts = via.split(";")
            has_rport = False
            rport_val = None
            for p in via_parts:
                p = p.strip().lower()
                if p.startswith("rport="):
                    has_rport = True
                    rport_val = p.split("=")[1]
            
            if has_rport and rport_val:
                try:
                    dest_addr = (addr[0], int(rport_val))
                except ValueError:
                    logger.warning("ValueError occurred")
            elif not has_rport:
                # No rport, RFC 3261 Section 18.2.2: send to Via sent-by port
                sent_by = via_parts[0].split()[1] if len(via_parts[0].split()) > 1 else ""
                if ":" in sent_by:
                    try:
                        dest_port = int(sent_by.split(":")[1])
                        dest_addr = (addr[0], dest_port)
                    except ValueError:
                        logger.warning("ValueError occurred")
                else:
                    dest_addr = (addr[0], 5060)
        await send_sip_bytes(proto, transport, dest_addr, data)
    elif proto == "TCP":
        await send_sip_bytes(proto, transport, addr, data, await_drain=_is_critical)


async def _schedule_device_catalog_retry(device_id: str, transport_info: tuple) -> None:
    commander = getattr(sip_commander_module, "sip_commander", None)
    if not commander:
        return
    retry_delays = [1, 5, 15]
    await patch_device_catalog_runtime(
        device_id,
        {
            "catalog.last_query_at": utc_now_iso(),
            "catalog.retry_attempts": 1,
            "catalog.retry_plan_seconds": ",".join(str(x) for x in retry_delays),
            "catalog.last_error": "",
            "catalog.sync_state": "query_sent",
            "catalog.progress": 10,
        },
    )
    _sip_debug_log("device_catalog_retry_initial", None, {"device_id": device_id, "attempt": 1, "delay_seconds": 0})
    try:
        await commander.send_catalog_query(device_id, transport_info)
    except Exception as e:
        await patch_device_catalog_runtime(
            device_id,
            {"catalog.last_error": f"initial_query_failed: {e}", "catalog.sync_state": "query_failed"},
        )
        _sip_debug_log("device_catalog_retry_failed", None, {"device_id": device_id, "attempt": 1, "error": str(e)})
        return

    for idx, delay in enumerate(retry_delays, start=2):
        await asyncio.sleep(delay)
        runtime = await patch_device_catalog_runtime(device_id, {"catalog.retry_last_check_at": utc_now_iso()})
        # 已收到目录响应则终止重试
        if runtime.get("catalog.last_response_at"):
            await patch_device_catalog_runtime(device_id, {"catalog.sync_state": "synced"})
            _sip_debug_log("device_catalog_retry_stopped", None, {"device_id": device_id, "attempt": idx, "reason": "response_received"})
            return
        progress = 20 + idx * 15  # idx=2..4 => 50/80/110 -> will clamp in UI
        progress = max(0, min(90, int(progress)))
        await patch_device_catalog_runtime(
            device_id,
            {
                "catalog.retry_attempts": idx,
                "catalog.last_query_at": utc_now_iso(),
                "catalog.progress": progress,
            },
        )
        _sip_debug_log("device_catalog_retry_attempt", None, {"device_id": device_id, "attempt": idx, "delay_seconds": delay})
        try:
            await commander.send_catalog_query(device_id, transport_info)
        except Exception as e:
            await patch_device_catalog_runtime(
                device_id,
                {
                    "catalog.last_error": f"retry_{idx}_failed: {e}",
                    "catalog.sync_state": "query_failed",
                    "catalog.progress": 100,
                },
            )
            _sip_debug_log("device_catalog_retry_failed", None, {"device_id": device_id, "attempt": idx, "error": str(e)})
            return

    runtime = await patch_device_catalog_runtime(device_id, {"catalog.retry_finished_at": utc_now_iso()})
    if runtime.get("catalog.last_response_at"):
        await patch_device_catalog_runtime(device_id, {"catalog.sync_state": "synced"})
        _sip_debug_log("device_catalog_retry_success", None, {"device_id": device_id, "attempts": runtime.get("catalog.retry_attempts", 0)})
    else:
        await patch_device_catalog_runtime(
            device_id,
            {"catalog.last_error": "catalog_response_timeout", "catalog.sync_state": "query_timeout", "catalog.progress": 100},
        )
        _sip_debug_log("device_catalog_retry_timeout", None, {"device_id": device_id, "attempts": runtime.get("catalog.retry_attempts", 0)})

def create_response(request: SipMessage, status_code: int, reason: str = None, received_addr: tuple = None) -> SipMessage:
    resp = SipMessage()
    resp.version = "SIP/2.0"
    resp.status_code = status_code
    
    if reason:
        resp.reason_phrase = reason
    else:
        reasons = {200: "OK", 401: "Unauthorized", 400: "Bad Request"}
        resp.reason_phrase = reasons.get(status_code, "Unknown")
        
    via_list = request.get_headers("Via")
    for i, via_val in enumerate(via_list):
        if i == 0 and received_addr:
            via_parts = via_val.split(";")
            new_via = []
            rport_added = False
            for part in via_parts:
                p_strip = part.strip().lower()
                if p_strip == "rport" or p_strip.startswith("rport="):
                    new_via.append(f"rport={received_addr[1]}")
                    rport_added = True
                elif p_strip.startswith("received="):
                    pass
                else:
                    new_via.append(part)
            new_via.append(f"received={received_addr[0]}")
            if not rport_added and "rport" in via_val.lower():
                new_via.append(f"rport={received_addr[1]}")
            resp.headers.add("Via", ";".join(new_via))
        else:
            resp.headers.add("Via", via_val)
    if not via_list:
        val = request.get_header("Via")
        if val:
            resp.headers["Via"] = val

    for h in ["From", "To", "Call-ID", "CSeq"]:
        val = request.get_header(h)
        if val:
            resp.headers[h] = val

    to_val = resp.headers.get("To") or resp.headers.get("t")
    if to_val and not re.search(r";\s*tag=", to_val, re.IGNORECASE):
        src = f"{request.get_header('Call-ID') or ''}|{request.get_header('CSeq') or ''}|{request.method or ''}"
        tag = hashlib.sha256(src.encode("utf-8", errors="ignore")).hexdigest()[:8]
        resp.headers["To"] = f"{to_val};tag={tag}"
            
    resp.headers["User-Agent"] = settings.PROJECT_NAME
    resp.headers["Server"] = settings.PROJECT_NAME
    resp.headers["Date"] = format_datetime(datetime.datetime.now(datetime.timezone.utc), usegmt=True)
    _attach_trace_header(resp, request.get_header("Call-ID") or "")
    return resp


def _rewrite_register_contact(contact_value: str, received_addr: tuple, fallback_user: str, expires: int | None = None) -> str:
    if not received_addr:
        return contact_value
    raw = (contact_value or "").strip()
    if not raw:
        user = (fallback_user or "").strip() or "unknown"
        base = f"<sip:{user}@{received_addr[0]}:{received_addr[1]}>"
        # W-13 RFC 3261 §10.2.8 REGISTER 200 OK的Contact头应包含expires参数
        if expires is not None:
            base = base.rstrip(">") + f";expires={expires}>"
        return base
    
    # 兼容下级平台Contact头不带尖括号的情况
    if raw.startswith("sip:"):
        raw = f"<{raw}>"
    m = re.search(r"(<\s*sip:[^@>]+@)([^:;>\s]+)(?::(\d+))?", raw, re.IGNORECASE)
    if not m:
        return raw
    prefix = m.group(1) or ""
    suffix_start = m.end(0)
    suffix = raw[suffix_start:]
    result = f"{prefix}{received_addr[0]}:{received_addr[1]}{suffix}"
    # W-13 RFC 3261 §10.2.8 REGISTER 200 OK的Contact头应包含expires参数
    if expires is not None and ";expires=" not in result.lower():
        result = result.rstrip(">") + f";expires={expires}>"
    return result


def _sip_date_gmt(dt: datetime.datetime | None = None) -> str:
    now = dt or datetime.datetime.now(datetime.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=datetime.timezone.utc)
    else:
        now = now.astimezone(datetime.timezone.utc)
    return format_datetime(now, usegmt=True)


def _sip_debug_enabled() -> bool:
    return bool(getattr(settings, "SIP_DEBUG_TRACE_ENABLED", False))


from app.sip.sip_trace import sip_trace_should_log as _sip_trace_should_log


def _mask_sensitive_value(value: str) -> str:
    if not value:
        return value
    if len(value) <= 6:
        return "*" * len(value)
    return f"{value[:3]}***{value[-3:]}"


def _sanitize_sip_header_value(name: str, value: str) -> str:
    key = (name or "").lower()
    if key in {"authorization", "www-authenticate"}:
        masked = value
        # Mask common digest sensitive fields.
        for field in ["nonce", "response", "cnonce", "opaque"]:
            masked = re.sub(
                rf'({field}=")([^"]*)(")',
                lambda m: f'{m.group(1)}{_mask_sensitive_value(m.group(2))}{m.group(3)}',
                masked,
                flags=re.IGNORECASE,
            )
        return masked
    return value


def _sanitize_preview_text(text: str) -> str:
    preview = (text or "")[:200].replace("\r", " ").replace("\n", " ")
    # Best-effort mask for password-like XML fields in body preview.
    preview = re.sub(
        r"(<Password>)(.*?)(</Password>)",
        lambda m: f"{m.group(1)}{_mask_sensitive_value(m.group(2))}{m.group(3)}",
        preview,
        flags=re.IGNORECASE,
    )
    return preview


def _sip_trace_id(message: SipMessage | None) -> str:
    if message is None:
        return ""
    call_id = (message.get_header("Call-ID") or "").strip()
    if call_id:
        return call_id
    cseq = (message.get_header("CSeq") or "").strip()
    frm = (message.get_header("From") or "").strip()
    method = (message.method or "").strip()
    return f"{method}|{cseq}|{frm}"[:128]


def _log_with_trace(level: str, msg: str, message: SipMessage | None = None) -> None:
    trace_id = _sip_trace_id(message)
    final = f"[trace_id={trace_id}] {msg}" if trace_id else msg
    if level == "warning":
        logger.warning(final)
    elif level == "error":
        logger.error(final)
    else:
        logger.info(final)


def _attach_trace_header(message: SipMessage, trace_id: str | None) -> None:
    tid = (trace_id or "").strip()
    if tid:
        message.headers["X-Trace-ID"] = tid


async def _patch_platform_runtime(platform: ParentPlatform, patch: dict) -> None:
    if not platform or not patch:
        return
    tenant_id = platform.tenant_id or "default"
    async with AsyncSessionLocal() as session:
        stmt = select(PlatformRuntime).where(
            PlatformRuntime.platform_id == platform.id,
            PlatformRuntime.tenant_id == tenant_id,
        )
        runtime = (await session.execute(stmt)).scalars().first()
        data: dict = {}
        if runtime and runtime.data:
            try:
                loaded = json.loads(runtime.data)
                if isinstance(loaded, dict):
                    data = loaded
            except Exception as _json_err:
                logger.debug(f"Failed to parse catalog runtime JSON: {_json_err}")  # W-10 吞异常改为日志
                data = {}
        for k, v in patch.items():
            key = str(k or "").strip()
            if key:
                data[key] = v
        if runtime:
            runtime.data = json.dumps(data, ensure_ascii=False)
        else:
            session.add(
                PlatformRuntime(
                    tenant_id=tenant_id,
                    platform_id=platform.id,
                    data=json.dumps(data, ensure_ascii=False),
                )
            )
        try:
            await session.commit()
        except Exception as _commit_err:
            logger.warning(f"Failed to commit catalog runtime: {_commit_err}")  # W-10 吞异常改为日志
            await session.rollback()


def _sip_debug_log(event: str, message: SipMessage | None = None, extra: dict | None = None) -> None:
    if not _sip_trace_should_log():
        return
    if should_warn_unknown_event_once(event):
        logger.warning(f"SIP_TRACE event not registered in trace_events.py: {event}")
    payload: dict = {"event": event, "trace_id": _sip_trace_id(message)}
    if message is not None:
        auth = _sanitize_sip_header_value("Authorization", message.get_header("Authorization") or "")
        www_auth = _sanitize_sip_header_value("WWW-Authenticate", message.get_header("WWW-Authenticate") or "")
        payload.update(
            {
                "method": message.method or "",
                "status_code": message.status_code or 0,
                "call_id": message.get_header("Call-ID") or "",
                "cseq": message.get_header("CSeq") or "",
                "from": message.get_header("From") or "",
                "to": message.get_header("To") or "",
                "via": message.get_header("Via") or "",
                "content_type": message.get_header("Content-Type") or "",
                "authorization": auth,
                "www_authenticate": www_auth,
                "body_preview": _sanitize_preview_text(message.body or ""),
            }
        )
    if extra:
        payload.update(extra)
    logger.info(f"SIP_TRACE {payload}")
    schedule_store_sip_trace(payload)


async def _send_register_401(message: SipMessage, transport, proto: str, addr: tuple, stale: bool = False):
    resp = create_response(message, 401, received_addr=addr)
    nonce = _issue_digest_nonce()
    stale_str = "true" if stale else "false"
    # GB12 SIP认证SHA-256支持 — RFC 8760 同时提供SHA-256和MD5算法
    realm = settings.SIP_DOMAIN
    auth_header_sha256 = (
        f'Digest realm="{realm}", nonce="{nonce}", '
        f'algorithm=SHA-256, qop="auth", '
        f'stale={stale_str}'
    )
    auth_header_md5 = (
        f'Digest realm="{realm}", nonce="{nonce}", '
        f'algorithm=MD5, qop="auth", '
        f'stale={stale_str}'
    )
    # S-04 RFC 8760要求多个认证方案使用同名WWW-Authenticate头，非标准WWW-Authenticate-2
    resp.headers["WWW-Authenticate"] = auth_header_sha256
    resp.headers.add("WWW-Authenticate", auth_header_md5)
    resp.headers["Date"] = _sip_date_gmt()
    resp.headers["Server"] = settings.PROJECT_NAME
    _sip_debug_log("register_401_challenge", message, {"proto": proto, "addr": str(addr), "stale": stale})
    await send_response(transport, proto, addr, resp)

async def _push_catalog_to_platform(
    *,
    platform_id: str,
    client_gb_id: str,
    server_gb_id: str,
    server_ip: str,
    server_port: int,
    proto: str,
    transport,
    addr: tuple,
    catalog_batch_size: int = 0,
    sn_override: int | None = None,
    response_device_id: str | None = None,
    tenant_id: str = "default",
) -> None:
    """
    向“注册到我这里”的级联系统发送 Catalog 响应（包含分组/设备树）。
    支持虚拟目录与 ID 重映射。
    """
    async with AsyncSessionLocal() as session:
        scope_stmt = select(PlatformCatalogResource).where(
            PlatformCatalogResource.platform_id == platform_id
        )
        scope_result = await session.execute(scope_stmt)
        scope_mappings = {m.resource_id: m for m in scope_result.scalars().all()}
        
        scope_ids = list(scope_mappings.keys())

        stmt = select(Resource).where(Resource.tenant_id == (tenant_id or "default"))
        if scope_ids:
            stmt = stmt.where(Resource.id.in_(scope_ids))

        result = await session.execute(stmt)
        resources = result.scalars().all()

    if not resources:
        return
    logger.info(
        f"Platform REGISTER matched, pushing Catalog to platform_id={platform_id}, resources={len(resources)}, proto={proto}"
    )
    _sip_debug_log(
        "catalog_push_start",
        None,
        {
            "platform_id": platform_id,
            "tenant_id": tenant_id,
            "resources": len(resources),
            "proto": proto,
            "addr": str(addr),
        },
    )

    batch_size = catalog_batch_size or 0
    if batch_size <= 0:
        # 级联目录推送默认分批（100条/批），避免大目录产生巨型XML报文
        batch_size = min(len(resources), 100)
    batches = [resources[i:i + batch_size] for i in range(0, len(resources), batch_size)]

    # 注册方的 REGISTER 协议栈（TCP/UDP）由外层 handle_register 决定
    via_transport = "TCP" if proto == "TCP" else "UDP"

    for batch_idx, batch in enumerate(batches):
        sn = sn_override if sn_override is not None else (int(datetime.datetime.now(datetime.timezone.utc).timestamp()) + batch_idx) % 100000
        items_xml = ""
        for res in batch:
            mapping = scope_mappings.get(res.id)
            
            # 应用虚拟目录重映射规则
            output_gb_id = res.gb_id
            output_name = res.name or res.gb_id
            output_parent_id = res.parent_gb_id or client_gb_id
            
            if mapping:
                if mapping.virtual_gb_id:
                    output_gb_id = mapping.virtual_gb_id
                if mapping.virtual_name:
                    output_name = mapping.virtual_name
                if mapping.virtual_parent_id:
                    output_parent_id = mapping.virtual_parent_id
                    
            civil = (res.civil_code or "340200")[:6]
            is_dir = getattr(res, "node_type", "channel") == "directory"
            parental = "1" if is_dir else "0"
            items_xml += f"""<Item>
<DeviceID>{_xml_escape(output_gb_id)}</DeviceID>
<Name>{_xml_escape(output_name)}</Name>
<Manufacturer>PyGBSentry</Manufacturer>
<Model>AI-Sentry</Model>
<Owner>Owner</Owner>
<CivilCode>{_xml_escape(civil)}</CivilCode>
<Address>Address</Address>
<Parental>{parental}</Parental>
<ParentID>{_xml_escape(output_parent_id)}</ParentID>
<SafetyWay>0</SafetyWay>
<RegisterWay>1</RegisterWay>
<Secrecy>0</Secrecy>
<Status>{"ON" if res.status else "OFF"}</Status>
</Item>
"""

        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Notify>
<CmdType>Catalog</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(response_device_id or client_gb_id)}</DeviceID>
<SumNum>{len(resources)}</SumNum>
<DeviceList Num="{len(batch)}">
{items_xml}
</DeviceList>
</Notify>
"""

        req = SipMessage()
        # FIXED-P0: Catalog Query 响应使用 MESSAGE 方法（GB28181 标准），而非 NOTIFY
        # NOTIFY 仅用于已建立的 SUBSCRIBE 对话内（RFC 3265），此处无订阅对话，使用 NOTIFY 违反协议
        req.method = "MESSAGE"
        req.uri = f"sip:{server_gb_id}@{addr[0]}:{addr[1]}"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Via"] = f"SIP/2.0/{via_transport} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch=z9hG4bKcat{sn}"
        req.headers["From"] = f"<sip:{client_gb_id}@{settings.SIP_DOMAIN}>;tag=cat{sn}"
        req.headers["To"] = f"<sip:{server_gb_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = f"cat_{server_gb_id}_{batch_idx}@{sip_host_for_contact()}"
        req.headers["CSeq"] = f"{sn} MESSAGE"
        req.headers["Max-Forwards"] = str(_SIP_MAX_FORWARDS_DEFAULT)
        req.headers["User-Agent"] = settings.PROJECT_NAME
        req.headers["Date"] = _sip_date_gmt()
        _attach_trace_header(req, req.headers.get("Call-ID") or "")
        req.body = xml_body

        # 使用 REGISTER 的来源地址/连接通道来下发（TCP 走现有连接，UDP 走 sendto 到来源地址）
        _sip_debug_log(
            "catalog_push_message",
            req,
            {"platform_id": platform_id, "batch_idx": batch_idx, "batch_size": len(batch)},
        )
        await send_sip_message(proto, transport, addr, req)

        if len(batches) > 1:
            await asyncio.sleep(0.2)

async def handle_alarm_notify(xml_body: str, device_id: str):
    """
    Parse Alarm XML and broadcast
    """
    try:
        root = parse_xml(xml_body)
        if root is None:
            return
            
        cmd_type = get_xml_text(root, "CmdType")
        if cmd_type != "Alarm":
            return

        alarm_priority = get_xml_text(root, "AlarmPriority", "4")
        alarm_method = get_xml_text(root, "AlarmMethod", "0")
        alarm_time_str = get_xml_text(root, "AlarmTime")
        alarm_desc = get_xml_text(root, "AlarmDescription")
            
        try:
            alarm_time = datetime.datetime.strptime(alarm_time_str, "%Y-%m-%dT%H:%M:%S")
        except Exception:
            try:
                alarm_time = datetime.datetime.strptime(alarm_time_str, "%Y-%m-%d %H:%M:%S")
            except Exception as _alarm_time_err:
                logger.debug(f"Failed to parse alarm time '{alarm_time_str}': {_alarm_time_err}")  # W-10 吞异常改为日志
                alarm_time = datetime.datetime.now(datetime.timezone.utc)

        async with AsyncSessionLocal() as session:
            _alarm_tenant_id = "default"
            try:
                _asset_stmt = select(Asset.tenant_id).where(Asset.gb_id == device_id).limit(1)
                _asset_row = (await session.execute(_asset_stmt)).first()
                if _asset_row and _asset_row[0]:
                    _alarm_tenant_id = _asset_row[0]
            except Exception as _tid_err:
                logger.debug(f"Failed to lookup tenant_id for alarm device {device_id}: {_tid_err}")
            alarm = Alarm(
                tenant_id=_alarm_tenant_id,
                device_id=device_id,
                channel_id=device_id, 
                priority=alarm_priority,
                method=alarm_method,
                time=alarm_time,
                description=alarm_desc,
                alarm_type="Alarm", 
                status=0
            )
            session.add(alarm)
            await session.flush()
            escalation = AlarmEscalation(alarm_id=alarm.id, state="open", escalation_level=0, escalation_count=0)
            session.add(escalation)
            await session.commit()
            
            alarm_data = {
                "id": alarm.id,
                "device_id": alarm.device_id,
                "time": alarm_time.isoformat(),
                "description": alarm_desc,
                "priority": alarm_priority,
                "escalation_level": 0,
                "escalation_state": "open"
            }
            _bg_create_task(alarm_manager.broadcast_alarm(alarm_data))
            _bg_create_task(plugin_manager.emit(HOOK_ON_ALARM, alarm))
            # 统一通知服务：按告警联动规则中 link_notify == True 的配置决定是否发送第三方通知
            _bg_create_task(notification_service.notify_alarm(alarm.id))

            # 轨迹闭环：若该通道在 Resource 中有经纬度，写入一条 DevicePosition，供可视化指挥 GET /map/trajectory 展示
            try:
                ch_id = alarm.channel_id or device_id
                res_stmt = select(Resource).join(Asset, Resource.asset_id == Asset.id).where(
                    Asset.gb_id == device_id,
                    Resource.gb_id.in_([ch_id, device_id]),
                    Resource.longitude.isnot(None),
                    Resource.latitude.isnot(None),
                ).limit(1)
                res_row = (await session.execute(res_stmt)).scalars().first()
                if res_row and res_row.longitude is not None and res_row.latitude is not None:
                    pos = DevicePosition(
                        device_id=device_id,
                        channel_id=ch_id,
                        latitude=float(res_row.latitude),
                        longitude=float(res_row.longitude),
                        time=alarm_time,
                    )
                    session.add(pos)
                    await session.commit()
            except Exception as e:
                logger.warning(f"Failed to store mobile position: {e}")

            # 报警录像联动：根据全局开关 + 联动规则决定是否触发 HOOK_ALARM_RECORD_LINK
            try:
                from app.core.settings_cache import get_system_setting

                # 全局开关
                val = await get_system_setting(session, "alarm_record_link_enabled")
                global_enabled = bool(val and val.strip().lower() in ("1", "true", "yes"))

                if global_enabled:
                    # 解析优先级
                    try:
                        p = int(alarm.priority or "4")
                    except Exception as _prio_err:
                        logger.debug(f"Failed to parse alarm priority: {_prio_err}")  # W-10 吞异常改为日志
                        p = 4

                    # 拉取当前租户的启用规则
                    tenant_id = alarm.tenant_id or "default"
                    rule_stmt = select(AlarmLinkRule).where(
                        AlarmLinkRule.tenant_id == tenant_id,
                        AlarmLinkRule.enabled.is_(True),
                    )
                    rule_result = await session.execute(rule_stmt)
                    rules = rule_result.scalars().all()

                    def _match(rule: AlarmLinkRule) -> bool:
                        if rule.min_priority is not None and p < rule.min_priority:
                            return False
                        if rule.max_priority is not None and p > rule.max_priority:
                            return False
                        # 星期匹配
                        if rule.days:
                            try:
                                day = alarm_time.weekday()  # 0=周一
                                allowed_days = {
                                    int(x) for x in str(rule.days).split(",") if x.strip()
                                }
                                if allowed_days and day not in allowed_days:
                                    return False
                            except Exception as e:
                                logger.warning(f"Failed to parse alarm rule days: {e}")
                        try:
                            if rule.start_time and rule.end_time:
                                t_str = alarm_time.strftime("%H:%M")
                                if not (rule.start_time <= t_str <= rule.end_time):
                                    return False
                        except Exception as e:
                            logger.warning(f"Failed to parse alarm rule time: {e}")
                        return True

                    any_record = False
                    for r_rule in rules:
                        if not r_rule.link_record:
                            continue
                        if _match(r_rule):
                            any_record = True
                            break

                    if any_record:
                        channel_id = alarm.channel_id or device_id
                        _bg_create_task(
                            plugin_manager.emit(HOOK_ALARM_RECORD_LINK, device_id, channel_id)
                        )
            except Exception as e:
                logger.warning(f"Failed to process alarm record link: {e}")
            logger.warning(f"Received Alarm from {device_id}: {alarm_desc}")

    except Exception as e:
        logger.error(f"Error parsing Alarm XML: {e}")

async def handle_register(message: SipMessage, addr: tuple, proto: str, transport):
    # Emit SIP Receive Hook
    _bg_create_task(plugin_manager.emit(HOOK_ON_SIP_RECEIVE, message, addr, proto))
    _sip_debug_log("register_received", message, {"proto": proto, "addr": str(addr)})
    
    auth_header = message.get_header("Authorization")
    from_uri = message.from_header
    gb_id_from_from = ""
    if from_uri and "sip:" in from_uri:
        gb_id_from_from = from_uri.split("sip:")[1].split("@")[0]

    contact_in = (message.get_header("Contact") or message.get_header("m") or "").strip()
    real_ip = addr[0]
    real_port = addr[1]
    if contact_in:
        # 兼容不带尖括号的 contact
        search_target = contact_in
        if search_target.startswith("sip:"):
            search_target = f"<{search_target}>"
        m_contact = re.search(r"sip:[^@>]+@([^:;>\s]+)(?::(\d+))?", search_target, re.IGNORECASE)
        if m_contact:
            contact_ip = m_contact.group(1)
            contact_port = int(m_contact.group(2)) if m_contact.group(2) else 5060
            
            # 由于下级平台往往在 Contact 中直接填写真实的服务端口 (例如 15063)
            # 而通过 NAT 注册上来的来源端口往往是个随机高端口 (例如 15061)
            # 所以这里优先信任 Contact 中的端口
            if contact_port > 0:
                real_port = contact_port
                
            # IP 保持来源 IP 不变，因为通常 Contact 里的 IP 是个内网 IP
            # 但如果它配置了公网 IP 并且和来源 IP 相同，那更没问题

    async with AsyncSessionLocal() as session:
        # 解析 Authorization 后，优先用 Digest username 作为鉴权标识：
        # 不同级联系统 REGISTER 的 From/username 可能不一致（username 通常是“平台国标ID”）。
        auth_params = DigestAuth.parse_auth_header(auth_header or "")
        username = (auth_params.get("username") or "").strip()
        gb_id = username or gb_id_from_from

        if not gb_id:
            # 没有 From/username 就无法定位凭据
            resp = create_response(message, 400, "Bad Request", received_addr=addr)
            await send_response(transport, proto, addr, resp)
            return

        # 优先查找 client_gb_id（下级平台注册时使用的ID）
        # 再查找 server_gb_id（作为上级时配置的ID）
        platform_stmt = select(ParentPlatform).where(ParentPlatform.client_gb_id == gb_id)
        platform_result = await session.execute(platform_stmt)
        platform = platform_result.scalars().first()
        if not platform:
            platform_stmt = select(ParentPlatform).where(ParentPlatform.server_gb_id == gb_id)
            platform_result = await session.execute(platform_stmt)
            platform = platform_result.scalars().first()
        if not platform:
            # 尝试用 From header 中的完整 URI 来匹配
            from_header = message.get_header("From") or ""
            if from_header:
                uri_gb_match = re.search(r':([0-9]{20})@', from_header)
                if uri_gb_match:
                    uri_gb_id = uri_gb_match.group(1)
                    if uri_gb_id != gb_id:
                        platform_stmt = select(ParentPlatform).where(ParentPlatform.client_gb_id == uri_gb_id)
                        platform_result = await session.execute(platform_stmt)
                        platform = platform_result.scalars().first()
                        if not platform:
                            platform_stmt = select(ParentPlatform).where(ParentPlatform.server_gb_id == uri_gb_id)
                            platform_result = await session.execute(platform_stmt)
                            platform = platform_result.scalars().first()

        # 先准备候选密码，然后用 Digest response 去“验证匹配”，避免字段语义(client/server)不一致导致失败。
        sip_default_password = getattr(settings, "SIP_DEFAULT_PASSWORD", None) or ""
        skip_auth = False
        if not sip_default_password:
            _app_env = (getattr(settings, "APP_ENV", "dev") or "dev").lower()
            if _app_env in {"prod", "production"}:
                _log_with_trace("error", f"SIP register rejected for {gb_id}: SIP_DEFAULT_PASSWORD is empty in production", message)
                await _send_register_401(message, transport, proto, addr)
                return
            else:
                # dev environment skipping SIP auth entirely - now only allow loopback
                # 增加醒目启动告警，防止开发环境误暴露到公网
                src_ip = addr[0] if addr else ""
                if src_ip in ("127.0.0.1", "::1", "localhost"):
                    logger.warning(
                        "SECURITY WARNING: SIP_DEFAULT_PASSWORD is empty, auth SKIPPED for loopback device %s. "
                        "NEVER expose this to public networks! Set SIP_DEFAULT_PASSWORD in .env.",
                        gb_id
                    )
                    sip_default_password = None
                    skip_auth = True
                else:
                    _log_with_trace("error", f"SIP register rejected for {gb_id}: SIP_DEFAULT_PASSWORD is empty and source is not loopback ({src_ip})", message)
                    await _send_register_401(message, transport, proto, addr)
                    return
        candidate_passwords: list[str] = []

        # 1) parent_platforms：client_gb_id
        pf_stmt = select(ParentPlatform).where(ParentPlatform.client_gb_id == gb_id)
        pf_result = await session.execute(pf_stmt)
        pf = pf_result.scalars().first()
        if pf and pf.password:
            _pf_pw = getattr(pf, 'decrypted_password', None)
            if _pf_pw is None:
                from app.core.field_crypto import decrypt_field
                _pf_pw = decrypt_field(pf.password, purpose="sip_password")
            candidate_passwords.append(_pf_pw or pf.password)

        # 2) parent_platforms：server_gb_id（字段语义可能反了）
        if not candidate_passwords:
            pf_stmt2 = select(ParentPlatform).where(ParentPlatform.server_gb_id == gb_id)
            pf_result2 = await session.execute(pf_stmt2)
            pf2 = pf_result2.scalars().first()
            if pf2 and pf2.password:
                _pf2_pw = getattr(pf2, 'decrypted_password', None)
                if _pf2_pw is None:
                    from app.core.field_crypto import decrypt_field
                    _pf2_pw = decrypt_field(pf2.password, purpose="sip_password")
                candidate_passwords.append(_pf2_pw or pf2.password)

        # 3) assets：设备密码（兜底候选之一）
        asset = None
        stmt = select(Asset).where(Asset.gb_id == gb_id)
        result = await session.execute(stmt)
        asset = result.scalars().first()
        if asset and asset.password:
            _asset_pw = asset.decrypted_password
            candidate_passwords.append(_asset_pw if _asset_pw else "")
            
        # 未知设备发现逻辑：如果设备不在 Asset 且不在 Platform 中，将其记录到自动发现列表
        # （可选，这里我们可以先允许它使用默认密码注册，注册成功后自动创建 Asset，
        # 原代码已经在后面 `if not asset:` 逻辑中实现了自动创建，这其实就是一种“自动接管”。
        # 我们只需记录一下日志并给它打个“auto_discovered”标签。）

        # 兜底默认密码
        candidate_passwords.append(sip_default_password)

        candidate_passwords = [pw for pw in candidate_passwords if pw is not None]
        candidate_passwords = list(dict.fromkeys(candidate_passwords))

        if not auth_header:
            # 无认证头时，要求必须有认证才能注册（安全策略）
            await _send_register_401(message, transport, proto, addr)
            return

        # Digest Auth Validation：找到一个密码能匹配 response 即通过
        valid_replay, replay_reason = await _validate_digest_replay(auth_params, gb_id)
        if not valid_replay:
            _log_with_trace("warning", f"Auth rejected for {gb_id}: {replay_reason}", message)
            await _send_register_401(message, transport, proto, addr, stale=(replay_reason == "stale nonce"))
            return

        password_used: str | None = None
        auth_response = auth_params.get("response")
        auth_algorithm = DigestAuth.select_preferred_algorithm(auth_params)
        for pw in candidate_passwords:
            expected_resp = DigestAuth.calculate_response(
                username=auth_params.get("username"),
                password=pw,
                realm=auth_params.get("realm"),
                method="REGISTER",
                uri=auth_params.get("uri"),
                nonce=auth_params.get("nonce"),
                nc=auth_params.get("nc"),
                cnonce=auth_params.get("cnonce"),
                qop=auth_params.get("qop"),
                algorithm=auth_algorithm,
            )
            if auth_response and hmac.compare_digest(str(auth_response), str(expected_resp)):
                password_used = pw
                break

        if not password_used:
            if skip_auth:
                logger.warning(f"DEV MODE: Skipping auth for {gb_id}")
                password_used = "dev_skip"
            else:
                _log_with_trace("warning", f"Auth failed for {gb_id}: Response mismatch", message)
                resp = create_response(message, 403, "Forbidden - Auth Failed", received_addr=addr)
                _sip_debug_log(
                    "register_auth_failed",
                    message,
                    {
                        "gb_id": gb_id,
                        "auth.username": str(auth_params.get("username") or ""),
                        "auth.realm": str(auth_params.get("realm") or ""),
                        "auth.qop": str(auth_params.get("qop") or ""),
                        "auth.nc": str(auth_params.get("nc") or ""),
                        "auth.cnonce": _mask_sensitive_value(str(auth_params.get("cnonce") or "")),  # cnonce脱敏
                        "auth.uri": str(auth_params.get("uri") or ""),
                    },
                )
                await send_response(transport, proto, addr, resp)

                try:
                    backend = get_sip_state_backend()
                    fail_count = await backend.record_auth_failure(real_ip)
                except Exception as auth_err:
                    # 鉴权失败计数后端异常时使用高值触发拉黑保护（fail-safe）
                    logger.warning(f"Auth failure count backend error for IP {real_ip}, assuming high count for safety: {auth_err}")
                    fail_count = 999

                if fail_count >= 5:
                    _log_with_trace("warning", f"IP {real_ip} auth failed {fail_count} times in 5 minutes, auto-blacklisting.", message)
                    from app.models.ip_blacklist import IpBlacklist
                    exist_bl = await session.scalar(select(IpBlacklist).where(IpBlacklist.ip == real_ip))
                    if not exist_bl:
                        session.add(IpBlacklist(ip=real_ip, reason="Auto-blocked: 5+ auth failures within 5 minutes"))  # 国际化
                        await session.commit()
                        from app.sip.server import sip_server
                        if hasattr(sip_server, "reload_ip_blacklist"):
                            _bg_create_task(sip_server.reload_ip_blacklist())
                    try:
                        await get_sip_state_backend().clear_auth_failure(real_ip)
                    except Exception as e:
                        logger.warning(f"Failed to clear auth failure count: {e}")

                return

        password = password_used

        now = datetime.datetime.now(datetime.timezone.utc)
        expires = message.get_header("Expires")
        contact_expires = None
        if contact_in:
            m_exp = re.search(r"expires=(\d+)", contact_in, re.IGNORECASE)
            if m_exp:
                try:
                    contact_expires = int(m_exp.group(1))
                except ValueError as e:
                    logger.debug(f"ValueError: {e}")
        try:
            expires_int = contact_expires if contact_expires is not None else (int(expires) if expires else 3600)
        except (ValueError, TypeError) as _expires_err:
            logger.debug(f"Invalid expires value: {_expires_err}")  # W-10 吞异常改为日志
            expires_int = 3600

        register_call_id = (message.get_header("Call-ID") or "").strip()
        if register_call_id and expires_int > 0:
            try:
                backend = get_sip_state_backend()
                if hasattr(backend, "check_register_renewal"):
                    is_renewal = await backend.check_register_renewal(gb_id, register_call_id)
                    if is_renewal:
                        if platform and platform.enable:
                            try:
                                async with AsyncSessionLocal() as renew_session:
                                    pf = (await renew_session.execute(select(ParentPlatform).where(ParentPlatform.id == platform.id))).scalars().first()
                                    if pf and expires_int > 0:
                                        pf.last_keepalive = now
                                        await renew_session.commit()
                            except Exception as renew_err:
                                logger.warning(f"Renewal expires update failed: {renew_err}")  # 续注册时keepalive/IP更新失败仅debug日志，提升为warning
                            resp = create_response(message, 200, received_addr=addr)
                            resp.headers["Date"] = _sip_date_gmt(now)
                            resp.headers["Expires"] = str(expires_int)
                            contact_in = (message.get_header("Contact") or message.get_header("m") or "").strip()
                            resp.headers["Contact"] = _rewrite_register_contact(contact_in, (real_ip, real_port), gb_id, expires_int)
                            resp.headers["Server"] = settings.PROJECT_NAME
                            await send_response(transport, proto, addr, resp)
                            _sip_debug_log("register_renewal_platform", message, {"gb_id": gb_id, "call_id": register_call_id})
                            return
                        if asset:
                            from app.sip.storm_handler import enqueue_keepalive_update
                            enqueue_keepalive_update(gb_id, real_ip, real_port, proto)
                            if expires_int > 0:
                                try:
                                    async with AsyncSessionLocal() as renew_session:
                                        a = (await renew_session.execute(select(Asset).where(Asset.gb_id == gb_id))).scalars().first()
                                        if a:
                                            a.last_keepalive = now
                                            a.expires = expires_int
                                            # registration renewal should update IP/port for NAT traversal
                                            if real_ip and a.ip_addr != real_ip:
                                                a.ip_addr = real_ip
                                            if real_port and a.port != real_port:
                                                a.port = real_port
                                            await renew_session.commit()
                                except Exception as renew_err:
                                    logger.warning(f"Device renewal expires update failed: {renew_err}")  # 续注册时keepalive/IP更新失败仅debug日志，提升为warning
                            resp = create_response(message, 200, received_addr=addr)
                            resp.headers["Date"] = _sip_date_gmt(now)
                            resp.headers["Expires"] = str(expires_int)
                            contact_in = (message.get_header("Contact") or message.get_header("m") or "").strip()
                            resp.headers["Contact"] = _rewrite_register_contact(contact_in, (real_ip, real_port), gb_id, expires_int)
                            resp.headers["Server"] = settings.PROJECT_NAME
                            await send_response(transport, proto, addr, resp)
                            _sip_debug_log("register_renewal_device", message, {"gb_id": gb_id, "call_id": register_call_id})
                            return
            except Exception as e:
                logger.debug(f"Register renewal check failed (non-critical): {e}")

        if register_call_id:
            try:
                backend = get_sip_state_backend()
                if hasattr(backend, "record_register_call_id"):
                    await backend.record_register_call_id(gb_id, register_call_id, ttl=expires_int + 60)
            except Exception as e:
                logger.debug(f"Exception: {e}")
        
        if platform and platform.enable:
            resp = create_response(message, 200, received_addr=addr)
            resp.headers["Date"] = _sip_date_gmt(now)
            resp.headers["Expires"] = str(expires_int)
            contact_in = (message.get_header("Contact") or message.get_header("m") or "").strip()
            contact_out = _rewrite_register_contact(contact_in, (real_ip, real_port), gb_id, expires_int)  # R-04 平台首次注册Contact头需包含expires参数
            resp.headers["Contact"] = contact_out
            resp.headers["Server"] = settings.PROJECT_NAME
            _sip_debug_log("register_ok_platform", message, {"gb_id": gb_id, "platform_id": platform.id, "expires": expires_int})
            await send_response(transport, proto, addr, resp)
            platform_id = platform.id

            async def _after_register_digest() -> None:
                try:
                    async with AsyncSessionLocal() as session2:
                        p = (
                            await session2.execute(select(ParentPlatform).where(ParentPlatform.id == platform_id))
                        ).scalars().first()
                        if not p:
                            return
                        if expires_int == 0:
                            p.is_online = False
                            await session2.commit()
                            _log_with_trace("info", f"Platform unregister: gb_id={gb_id}, platform_id={p.id}", message)
                            # 平台注销时清理出站订阅，防止续期任务空转
                            try:
                                from app.sip.subscribe_manager import subscribe_manager
                                await subscribe_manager.remove_all_for_device(gb_id)
                            except Exception as _sub_err:
                                logger.warning(f"Failed to cleanup subscriptions for unregistered platform {gb_id}: {_sub_err}")
                            await _patch_platform_runtime(
                                p,
                                {
                                    "inbound.register.last_unreg_at": now.isoformat(),
                                    "inbound.register.last_expires": expires_int,
                                    "inbound.register.last_gb_id": gb_id,
                                    "inbound.register.last_addr": str(addr),
                                    "inbound.register.last_transport": str(proto or ""),
                                    "inbound.register.auth": "digest",
                                },
                            )
                            import app.services.platform_service as platform_service_mod
                            svc = getattr(platform_service_mod, "platform_service", None)
                            if svc and getattr(svc, "running", False):
                                _bg_create_task(svc.handle_platform_offline(p.id, reason="unregister"))
                            return
                        p.is_online = True
                        p.last_keepalive = now
                        p.server_ip = real_ip
                        p.server_port = real_port
                        await session2.commit()
                        _log_with_trace("info", f"Platform register: gb_id={gb_id}, platform_id={p.id}", message)
                        _sip_debug_log(
                            "register_platform_online",
                            message,
                            {
                                "gb_id": gb_id,
                                "platform_id": p.id,
                                "transport": proto,
                                "addr": str(addr),
                                "expires": expires_int,
                                "auth": "digest",
                            },
                        )
                        await _patch_platform_runtime(
                            p,
                            {
                                "inbound.register.last_ok_at": now.isoformat(),
                                "inbound.register.last_expires": expires_int,
                                "inbound.register.last_gb_id": gb_id,
                                "inbound.register.last_addr": str(addr),
                                "inbound.register.last_transport": str(proto or ""),
                                "inbound.register.auth": "digest",
                                "inbound.register.last_contact": contact_in,
                                "inbound.register.last_resp_contact": contact_out,
                            },
                        )
                        if getattr(sip_commander_module, "sip_commander", None):
                            target_platform_gb_id = gb_id or p.server_gb_id or p.client_gb_id
                            await _patch_platform_runtime(
                                p,
                                {
                                    "inbound.catalog.query_sent_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                    "inbound.catalog.query_target_gb_id": target_platform_gb_id,
                                },
                            )
                            _bg_create_task(
                                sip_commander_module.sip_commander.send_platform_catalog_query(
                                    target_platform_gb_id,
                                    ((real_ip, real_port), proto, transport),
                                )
                            )
                except Exception as e:
                    _log_with_trace("warning", f"Platform register(digest) post-process failed: {e}", message)

            _bg_create_task(_after_register_digest())
            return

        if expires_int == 0:
            _log_with_trace("info", f"Device {gb_id} unregistering", message)
            if asset:
                from app.sip.storm_handler import enqueue_register_update
                enqueue_register_update(gb_id, real_ip, real_port, proto, 0)
                try:
                    from app.core.redis import ha_cluster
                    await ha_cluster.unregister_device_owner(gb_id)
                    await ha_cluster.broadcast_device_change(gb_id, "status_changed", {"status": "offline"})
                except Exception as e:
                    logger.warning(f"HA cluster unregister_device_owner failed for {gb_id}: {e}")
                _bg_create_task(_cleanup_device_resources(gb_id))
        else:
            _log_with_trace("info", f"Device {gb_id} registered successfully", message)
            
            is_new_asset = False
            if not asset:
                allowed, limit, current = await check_device_quota(session, "default")
                if not allowed:
                    _log_with_trace(
                        "warning",
                        f"Device quota exceeded for tenant=default: current={current}, limit={limit}",
                        message,
                    )
                    resp = create_response(message, 403, "Forbidden - Device Quota Exceeded", received_addr=addr)
                    await send_response(transport, proto, addr, resp)
                    return

                # --- IP Spam Check & Auto Discovery ---
                real_ip = addr[0]
                # Check Auto Discovery setting
                if not getattr(settings, "ENABLE_AUTO_DISCOVERY", True):
                    _log_with_trace("warning", f"Auto-discovery disabled, rejecting unknown device: {gb_id}", message)
                    resp = create_response(message, 403, "Forbidden - Auto Discovery Disabled", received_addr=addr)
                    await send_response(transport, proto, addr, resp)
                    return
                    
                one_hour_ago = now - datetime.timedelta(hours=1)
                recent_devices_count = await session.scalar(
                    select(func.count(Asset.id)).where(
                        Asset.ip_addr == real_ip,
                        Asset.created_at >= one_hour_ago
                    )
                )
                # 先阻断再创建：>= 10 时直接拒绝，不创建任何资产
                if recent_devices_count >= 10:
                    _log_with_trace("warning", f"IP {real_ip} registered {recent_devices_count} devices in past hour, blocking new registration of {gb_id}.", message)

                    from app.models.ip_blacklist import IpBlacklist
                    exist_bl = await session.scalar(select(IpBlacklist).where(IpBlacklist.ip == real_ip))
                    if not exist_bl:
                        session.add(IpBlacklist(ip=real_ip, reason="Auto-blocked: 10+ device registrations from same IP within 1 hour"))  # 国际化
                        await session.commit()

                        from app.sip.server import sip_server
                        if hasattr(sip_server, "reload_ip_blacklist"):
                            _bg_create_task(sip_server.reload_ip_blacklist())

                    resp = create_response(message, 403, "Forbidden - Too Many Devices From This IP", received_addr=addr)
                    await send_response(transport, proto, addr, resp)
                    return
                # --- End IP Spam Check ---

                # 未知设备接管：自动创建设备
                _log_with_trace("info", f"Auto-discovered and taking over unknown device: {gb_id}", message)
                asset = Asset(gb_id=gb_id, name=f"Auto_Discovered_{gb_id}", password=getattr(settings, "SIP_DEFAULT_PASSWORD", "") or "", tenant_id="default")  # GB28181协议 — 自动发现设备使用SIP默认密码
                session.add(asset)
                is_new_asset = True
            
            if is_new_asset:
                asset.status = 1
                # 兼容下级平台指定的非标端口（如15063）或NAT穿透的真实地址
                asset.ip_addr = real_ip
                asset.port = real_port
                asset.transport = proto
                asset.register_time = now
                asset.last_keepalive = now
                asset.expires = expires_int
                
                await session.commit()
            else:
                from app.sip.storm_handler import enqueue_register_update
                enqueue_register_update(gb_id, real_ip, real_port, proto, expires_int)
            
            if getattr(sip_commander_module, "sip_commander", None):
                _bg_create_task(_schedule_device_catalog_retry(gb_id, ((real_ip, real_port), proto, transport)))
                _bg_create_task(
                    sip_commander_module.sip_commander.send_mobile_position_subscribe(
                        gb_id, ((real_ip, real_port), proto, transport)
                    )
                )
                _bg_create_task(
                    sip_commander_module.sip_commander.send_time_sync(
                        gb_id, ((real_ip, real_port), proto, transport)
                    )
                )
                # 设备注册后自动发起报警订阅
                try:
                    await sip_commander_module.sip_commander.send_alarm_subscribe(
                        device_id=gb_id,
                        gb_domain=settings.SIP_DOMAIN,
                        sip_id=settings.SIP_ID,
                        sip_domain=settings.SIP_DOMAIN,
                        device_host=real_ip,
                        device_port=real_port,
                        expires=3600,
                        transport=proto,
                    )
                    logger.info(f"Auto-subscribed alarm events for device {gb_id}")
                except Exception as e:
                    logger.warning(f"Failed to auto-subscribe alarm for {gb_id}: {e}")

            _bg_create_task(plugin_manager.emit(HOOK_ON_DEVICE_REGISTER, gb_id))

            try:
                from app.core.redis import ha_cluster
                await ha_cluster.register_device_owner(gb_id)
                await ha_cluster.broadcast_device_change(gb_id, "status_changed", {"status": "online"})
            except Exception as e:
                logger.warning(f"HA cluster register_device_owner failed for {gb_id}: {e}")

        resp = create_response(message, 200, received_addr=addr)
        resp.headers["Date"] = _sip_date_gmt(now)
        resp.headers["Expires"] = str(expires_int)
        contact_in = (message.get_header("Contact") or message.get_header("m") or "").strip()
        resp.headers["Contact"] = _rewrite_register_contact(contact_in, (real_ip, real_port), gb_id, expires_int)
        resp.headers["Server"] = settings.PROJECT_NAME
        _sip_debug_log("register_ok_device", message, {"gb_id": gb_id, "expires": expires_int})
        await send_response(transport, proto, addr, resp)

async def handle_message_request(message: SipMessage, addr: tuple, proto: str, transport):
    # Emit SIP Receive Hook
    _bg_create_task(plugin_manager.emit(HOOK_ON_SIP_RECEIVE, message, addr, proto))
    _sip_debug_log("message_received", message, {"proto": proto, "addr": str(addr)})

    content_type = message.get_header("Content-Type")
    from_uri = message.from_header
    gb_id = ""
    if "sip:" in from_uri:
        gb_id = from_uri.split("sip:")[1].split("@")[0]

    body = message.body
    looks_like_xml = bool(
        body and body.strip() and (  # C-30 增加body.strip()检查，防止空字符串误判为XML
            (content_type and "xml" in str(content_type).lower())
            or "<?xml" in body
            or "<Notify" in body
            or "<Query" in body
            or "<Response" in body
        )
    )
    root = parse_xml(body) if looks_like_xml else None
    cmd_type = get_xml_text(root, "CmdType") if root is not None else ""
    root_name = local_name(root.tag).lower() if root is not None else ""

    # 优先按 XML 结构识别，避免部分平台 Content-Type 不规范导致漏处理
    if root is not None:

        if cmd_type == "Keepalive":
            keepalive_gb_id = get_xml_text(root, "DeviceID") or gb_id
            
            from app.sip.storm_handler import should_skip_keepalive_db_update, enqueue_keepalive_update
            
            # Smooth out keepalive storms
            skip_db = await should_skip_keepalive_db_update(keepalive_gb_id, addr[0], addr[1])
            
            if not skip_db:
                # Instead of hitting DB directly, enqueue it
                enqueue_keepalive_update(keepalive_gb_id, addr[0], addr[1], proto)
                
                # We still need to update the runtime cache so UI is aware immediately if needed
                async with AsyncSessionLocal() as session:
                    matched_platforms = (
                        await session.execute(
                            select(ParentPlatform).where(
                                (ParentPlatform.server_gb_id == keepalive_gb_id) | (ParentPlatform.client_gb_id == keepalive_gb_id)
                            )
                        )
                    ).scalars().all()
                    for p in matched_platforms:
                        await _patch_platform_runtime(
                            p,
                            {
                                "inbound.keepalive.last_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                "inbound.keepalive.last_gb_id": keepalive_gb_id,
                                "inbound.keepalive.last_addr": str(addr),
                                "inbound.keepalive.last_transport": str(proto or ""),
                            },
                        )

            resp = create_response(message, 200, received_addr=addr)
            await send_response(transport, proto, addr, resp)
            return
            
        elif cmd_type == "Catalog":
            # GB28181：Catalog 同时可能是 Query（需要回复 Catalog Response）或 Response（需要解析更新本地资源）
            is_query = (root_name == "query")
            if is_query:
                resp = create_response(message, 200)
                await send_response(transport, proto, addr, resp)
                _sip_debug_log(
                    "message_catalog_query_ack",
                    message,
                    {
                        "gb_id": gb_id,
                        "sn": get_xml_text(root, "SN"),
                        "query_device_id": get_xml_text(root, "DeviceID"),
                    },
                )

                sn_text = get_xml_text(root, "SN") if root is not None else ""
                device_id_query = get_xml_text(root, "DeviceID") if root is not None else ""
                sn_override: int | None = None
                try:
                    sn_override = int(sn_text) if sn_text else None
                except Exception as _sn_err:
                    logger.debug(f"Failed to parse SN value: {_sn_err}")  # W-10 吞异常改为日志
                    sn_override = None

                async with AsyncSessionLocal() as session:
                    platform_stmt = select(ParentPlatform).where(ParentPlatform.server_gb_id == gb_id)
                    platform_result = await session.execute(platform_stmt)
                    platform = platform_result.scalars().first()
                    if not platform:
                        platform_stmt = select(ParentPlatform).where(ParentPlatform.client_gb_id == gb_id)
                        platform_result = await session.execute(platform_stmt)
                        platform = platform_result.scalars().first()

                    if platform and platform.enable:
                        await _patch_platform_runtime(
                            platform,
                            {
                                "inbound.catalog.query_received_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                "inbound.catalog.query_sn": str(sn_text or ""),
                                "inbound.catalog.query_device_id": str(device_id_query or ""),
                                "inbound.catalog.query_from_gb_id": gb_id,
                            },
                        )
                        _sip_debug_log("message_catalog_query_push", message, {"gb_id": gb_id, "platform_id": platform.id})
                        _bg_create_task(
                            _push_catalog_to_platform(
                                platform_id=platform.id,
                                client_gb_id=platform.client_gb_id,
                                server_gb_id=platform.server_gb_id,
                                server_ip=platform.server_ip,
                                server_port=platform.server_port,
                                proto=proto,
                                transport=transport,
                                addr=addr,
                                sn_override=sn_override,
                                response_device_id=device_id_query or None,
                                tenant_id=platform.tenant_id or "default",
                            )
                        )
                return

            # 否则按 Catalog Response 解析
            resp = create_response(message, 200)
            await send_response(transport, proto, addr, resp)
            response_device_id = (get_xml_text(root, "DeviceID") or "").strip() or gb_id
            _sip_debug_log(
                "message_catalog_response",
                message,
                {
                    "gb_id": gb_id,
                    "response_device_id": response_device_id,
                    "sn": get_xml_text(root, "SN"),
                    "sum_num": get_xml_text(root, "SumNum"),
                },
            )
            async with AsyncSessionLocal() as session:
                platform = (
                    await session.execute(
                        select(ParentPlatform).where(
                            (ParentPlatform.server_gb_id == gb_id) | (ParentPlatform.client_gb_id == gb_id)
                        )
                    )
                ).scalars().first()
            if platform:
                await _patch_platform_runtime(
                    platform,
                    {
                        "inbound.catalog.response_received_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        "inbound.catalog.response_sn": str(get_xml_text(root, "SN") or ""),
                        "inbound.catalog.response_sum_num": str(get_xml_text(root, "SumNum") or ""),
                        "inbound.catalog.response_from_gb_id": gb_id,
                    },
                )
            await patch_device_catalog_runtime(
                response_device_id,
                {
                    "catalog.last_response_at": utc_now_iso(),
                    "catalog.sync_state": "response_received",
                    "catalog.last_error": "",
                },
            )
            _bg_create_task(handle_catalog_response(body, response_device_id))
            return
        
        elif cmd_type == "RecordInfo":
            resp = create_response(message, 200)
            await send_response(transport, proto, addr, resp)
            _sip_debug_log("message_record_info", message, {"gb_id": gb_id})

            if root_name == "query":
                is_cascade = False
                try:
                    async with get_db() as session:
                        platform = (await session.execute(
                            select(ParentPlatform).where(ParentPlatform.server_gb_id == gb_id)
                        )).scalars().first()
                        if platform:
                            is_cascade = True
                except Exception as e:
                    # 级联目录查询异常不再静默吞没，记录warning日志
                    logger.warning(f"Cascade record query check failed for {gb_id}: {e}")
                if is_cascade:
                    channel_id = get_xml_text(root, "DeviceID") or gb_id
                    start_time = get_xml_text(root, "StartTime") or ""
                    end_time = get_xml_text(root, "EndTime") or ""
                    query_type = get_xml_text(root, "Type") or "all"
                    sn = get_xml_text(root, "SN") or "0"
                    import app.services.platform_service as _ps_mod
                    svc = getattr(_ps_mod, "platform_service", None)
                    if svc:
                        ok = await svc.forward_cascade_record_query(platform, channel_id, start_time, end_time, query_type, sn)
                        if ok:
                            logger.info(f"[MESSAGE] Forwarded cascade RecordInfo query from {gb_id} for channel {channel_id}")
                        else:
                            logger.warning(f"[MESSAGE] Failed to forward cascade RecordInfo query from {gb_id} for channel {channel_id}")
                    else:
                        logger.warning("[MESSAGE] PlatformService not available for cascade RecordInfo forwarding")
                else:
                    _bg_create_task(handle_record_info_response(body, gb_id))
            else:
                _bg_create_task(handle_record_info_response(body, gb_id))
            return
            
        elif cmd_type == "DirectoryInfo":
            # GB28181-2022 文件目录检索响应
            resp = create_response(message, 200)
            await send_response(transport, proto, addr, resp)
            _sip_debug_log("message_directory_info", message, {"gb_id": gb_id})
            try:
                from app.sip.catalog import catalog_data_manager
                await catalog_data_manager.put(gb_id, cmd_type, body)
            except Exception as e:
                logger.debug(f"Failed to route DirectoryInfo response to catalog_data_manager: {e}")
            return

        elif cmd_type == "AlarmCodeResponse":
            # GB28181-2022 布防报警分类响应
            resp = create_response(message, 200)
            await send_response(transport, proto, addr, resp)
            _sip_debug_log("message_alarm_code_response", message, {"gb_id": gb_id})
            try:
                from app.sip.catalog import catalog_data_manager
                await catalog_data_manager.put(gb_id, cmd_type, body)
            except Exception as e:
                logger.debug(f"Failed to route AlarmCodeResponse response to catalog_data_manager: {e}")
            return

        elif cmd_type == "Alarm":
            resp = create_response(message, 200)
            await send_response(transport, proto, addr, resp)
            _sip_debug_log("message_alarm", message, {"gb_id": gb_id})
            _bg_create_task(handle_alarm_notify(body, gb_id))
            return

        elif cmd_type == "MobilePosition":
            resp = create_response(message, 200)
            await send_response(transport, proto, addr, resp)
            _sip_debug_log("message_mobile_position", message, {"gb_id": gb_id})
            _bg_create_task(handle_mobile_position_notify(body, gb_id))
            return

        elif cmd_type == "MediaStatus":
            resp = create_response(message, 200)
            await send_response(transport, proto, addr, resp)
            _sip_debug_log("message_media_status", message, {"gb_id": gb_id})
            _bg_create_task(handle_media_status_notify(body, gb_id))
            return

        elif cmd_type == "DeviceControl":
            device_id_xml = get_xml_text(root, "DeviceID") or gb_id
            sn = get_xml_text(root, "SN") or "0"
            ptz_cmd_elem = None
            for tag_name in ("PTZCmd", "TeleBoot", "RecordCmd", "GuardCmd", "AlarmCmd", "DragZoomIn", "DragZoomOut", "HomePosition"):
                child = root.find(f".//{tag_name}")
                if child is not None and (child.text or "").strip():
                    ptz_cmd_elem = child
                    break
            if ptz_cmd_elem is not None:
                tag = local_name(ptz_cmd_elem.tag)
                inner_xml = f"<{tag}>{ptz_cmd_elem.text.strip()}</{tag}>"
                is_cascade = False
                try:
                    async with get_db() as session:
                        platform = (await session.execute(
                            select(ParentPlatform).where(ParentPlatform.server_gb_id == gb_id)
                        )).scalars().first()
                        if platform:
                            is_cascade = True
                except Exception as e:
                    # 级联设备控制查询异常不再静默吞没，记录warning日志
                    logger.warning(f"Cascade device control check failed for {gb_id}: {e}")
                if is_cascade:
                    import app.services.platform_service as _ps_mod
                    svc = getattr(_ps_mod, "platform_service", None)
                    if svc:
                        ok = await svc.forward_cascade_device_control(device_id_xml, inner_xml, sn)
                        if ok:
                            logger.info(f"[MESSAGE] Forwarded cascade DeviceControl from {gb_id} for channel {device_id_xml}")
                        else:
                            logger.warning(f"[MESSAGE] Failed to forward cascade DeviceControl from {gb_id} for channel {device_id_xml}")
                    else:
                        logger.warning("[MESSAGE] PlatformService not available for cascade DeviceControl forwarding")
                else:
                    try:
                        from app.sip.catalog import catalog_data_manager
                        await catalog_data_manager.put(device_id_xml, "DeviceControl", body)
                    except Exception as e:
                        logger.debug(f"Failed to route DeviceControl to catalog_data_manager: {e}")
            resp = create_response(message, 200)
            await send_response(transport, proto, addr, resp)
            _sip_debug_log("message_device_control", message, {"gb_id": gb_id, "channel": device_id_xml})
            return

        elif cmd_type in ("DeviceInfo", "DeviceStatus", "ConfigDownload", "PresetQuery", "DragZoomIn", "DragZoomOut", "HomePosition"):
            resp = create_response(message, 200)
            await send_response(transport, proto, addr, resp)
            _sip_debug_log(f"message_{cmd_type.lower()}", message, {"gb_id": gb_id, "cmd_type": cmd_type})
            # 处理 ConfigDownload 响应，记录配置内容
            if cmd_type == "ConfigDownload":
                inner_xml = body[:200] if body else ""
                logger.info(f"ConfigDownload response from {gb_id}: {inner_xml}")
            # Check if this is a cascade query from upstream platform
            is_cascade_query = False
            try:
                async with get_db() as session:
                    platform = (await session.execute(
                        select(ParentPlatform).where(ParentPlatform.server_gb_id == gb_id)
                    )).scalars().first()
                    if platform:
                        is_cascade_query = True
            except Exception as e:
                logger.warning(f"Cascade query check failed for {gb_id}: {e}")
            if is_cascade_query and cmd_type == "ConfigDownload":
                device_id_xml = get_xml_text(root, "DeviceID") or gb_id
                config_type = get_xml_text(root, "ConfigType") or "BasicParam"
                sn = get_xml_text(root, "SN") or "0"
                import app.services.platform_service as _ps_mod
                svc = getattr(_ps_mod, "platform_service", None)
                if svc:
                    ok = await svc.forward_cascade_config_download(device_id_xml, config_type, sn)
                    if ok:
                        logger.info(f"[MESSAGE] Forwarded cascade ConfigDownload from {gb_id} for channel {device_id_xml}")
                    else:
                        logger.warning(f"[MESSAGE] Failed to forward cascade ConfigDownload from {gb_id} for channel {device_id_xml}")
            try:
                from app.sip.catalog import catalog_data_manager
                await catalog_data_manager.put(gb_id, cmd_type, body)
            except Exception as e:
                logger.debug(f"Failed to route {cmd_type} response to catalog_data_manager: {e}")
            return

        elif cmd_type == "ConfigSet":
            # 处理 ConfigSet 响应
            resp = create_response(message, 200)
            await send_response(transport, proto, addr, resp)
            result = get_xml_text(root, "Result")
            logger.info(f"ConfigSet response from {gb_id}: Result={result}")
            _sip_debug_log("message_configset", message, {"gb_id": gb_id, "result": result})
            try:
                from app.sip.catalog import catalog_data_manager
                await catalog_data_manager.put(gb_id, cmd_type, body)
            except Exception as e:
                logger.debug(f"Failed to route ConfigSet response to catalog_data_manager: {e}")
            return

        elif cmd_type == "TimeSync":
            # GB28181协议 — 处理时间同步响应
            resp = create_response(message, 200)
            await send_response(transport, proto, addr, resp)
            inner_xml = body[:200] if body else ""
            logger.info(f"TimeSync response from {gb_id}: {inner_xml}")
            _sip_debug_log("message_timesync", message, {"gb_id": gb_id, "cmd_type": cmd_type})
            return

        elif cmd_type == "ConfigUpload":
            # 实现ConfigUpload设备配置设置/下发
            resp = create_response(message, 200)
            await send_response(transport, proto, addr, resp)
            result = get_xml_text(root, "Result")
            logger.info(f"ConfigUpload response from {gb_id}: Result={result}")
            _sip_debug_log("message_configupload", message, {"gb_id": gb_id, "result": result})
            try:
                from app.sip.catalog import catalog_data_manager
                await catalog_data_manager.put(gb_id, cmd_type, body)
            except Exception as e:
                logger.debug(f"Failed to route ConfigUpload response to catalog_data_manager: {e}")
            return

    resp = create_response(message, 200)
    if cmd_type:
        logger.warning(f"[MESSAGE] Unhandled CmdType={cmd_type} from {gb_id}, replying 200 OK")
    elif body and looks_like_xml:
        logger.warning(f"[MESSAGE] Unrecognized XML MESSAGE from {gb_id} (no CmdType), replying 200 OK")
    else:
        logger.warning(f"[MESSAGE] Unrecognized MESSAGE from {gb_id}, replying 200 OK")
    _sip_debug_log("message_fallback_200", message, {"gb_id": gb_id, "cmd_type": cmd_type or ""})
    await send_response(transport, proto, addr, resp)


async def handle_mobile_position_notify(xml_body: str, device_id: str):
    """
    Parse MobilePosition NOTIFY and update coordinates
    """
    root = parse_xml(xml_body)
    if root is None:
        return
        
    longitude = get_xml_text(root, "Longitude")
    latitude = get_xml_text(root, "Latitude")
    time_str = get_xml_text(root, "Time")
    speed = get_xml_text(root, "Speed")
    direction = get_xml_text(root, "Direction")
    altitude = get_xml_text(root, "Altitude")
    
    if longitude and latitude:
        try:
            # Parse time
            try:
                if time_str:
                    pos_time = datetime.datetime.strptime(time_str, "%Y-%m-%dT%H:%M:%S")
                else:
                    pos_time = datetime.datetime.now(datetime.timezone.utc)
            except Exception as _pos_time_err:
                logger.debug(f"Failed to parse position time: {_pos_time_err}")  # W-10 吞异常改为日志
                pos_time = datetime.datetime.now(datetime.timezone.utc)

            async with AsyncSessionLocal() as session:
                # 1. Update Resource (latest position)
                stmt = update(Resource).where(
                    Resource.asset_id == (
                        select(Asset.id).where(Asset.gb_id == device_id).scalar_subquery()
                    )
                ).values(
                    longitude=float(longitude),
                    latitude=float(latitude)
                )
                await session.execute(stmt)

                # 2. Insert History Record
                pos = DevicePosition(
                    device_id=device_id,
                    latitude=float(latitude),
                    longitude=float(longitude),
                    speed=float(speed) if speed else None,
                    direction=float(direction) if direction else None,
                    altitude=float(altitude) if altitude else None,
                    time=pos_time
                )
                session.add(pos)
                
                await session.commit()
                logger.info(f"Updated position and saved trajectory for {device_id}: {longitude}, {latitude}")
                _bg_create_task(plugin_manager.emit(HOOK_ON_MOBILE_POSITION, device_id, float(longitude), float(latitude), speed, direction, altitude, pos_time))
        except Exception as e:
            logger.error(f"Error parsing MobilePosition XML: {e}")

async def handle_media_status_notify(xml_body: str, device_id: str):
    """
    Parse MediaStatus NOTIFY and handle playback end/error
    """
    from app.core.xml_utils import parse_xml, get_xml_text
    from app.services.stream_session_service import finalize_stream_session
    from app.models.stream_session import StreamSession
    root = parse_xml(xml_body)
    if root is None:
        return
        
    channel_id = get_xml_text(root, "DeviceID") or device_id
    notify_type = get_xml_text(root, "NotifyType")
    
    if notify_type in ["121", "122"]:
        logger.info(f"Received MediaStatus {notify_type} from {device_id}/{channel_id}, stopping playback.")
        try:
            async with AsyncSessionLocal() as session:
                sn_val = get_xml_text(root, "SN") or ""
                stmt = select(StreamSession).where(
                    (StreamSession.app == 'playback') | (StreamSession.app == 'download')
                ).join(Resource, StreamSession.resource_id == Resource.id).where(
                    Resource.gb_id == channel_id
                ).order_by(StreamSession.start_time.desc()).limit(1)
                result = await session.execute(stmt)
                stream_session = result.scalars().first()
                
                if stream_session:
                    ss_id = stream_session.id
                    _bg_create_task(plugin_manager.emit("ON_MEDIA_STATUS", {
                        "device_id": device_id,
                        "channel_id": channel_id,
                        "notify_type": notify_type,
                        "stream": str(getattr(stream_session, "stream", "") or ""),
                        "app": str(getattr(stream_session, "app", "") or "")
                    }))
                    
                    async def _finalize_in_own_session():
                        try:
                            async with AsyncSessionLocal() as own_db:
                                ss = (await own_db.execute(
                                    select(StreamSession).where(StreamSession.id == ss_id)
                                )).scalars().first()
                                if ss:
                                    await finalize_stream_session(own_db, ss, reason=f"media_status_{notify_type}")
                        except Exception as e:
                            logger.error(f"Failed to finalize playback session {ss_id}: {e}")
                    _bg_create_task(_finalize_in_own_session())
                
                await session.commit()
        except Exception as e:
            logger.error(f"Error handling MediaStatus {notify_type}: {e}")

async def handle_invite_request(message: SipMessage, addr: tuple, proto: str, transport):
    """
    处理上级平台下发的 INVITE 请求（级联视频点播）。
    1. 解析请求的资源 ID (虚拟或真实)。
    2. 判断本地是否有该设备的流，若无则触发拉流。
    3. 调用 ZLM startSendRtp 向请求方推流。
    4. 回复 200 OK。
    """
    from app.core.media_nodes_db import select_best_db_node
    from app.sip.invite import sip_invite
    from app.sip.server import sip_server
    from app.services.zlm_stream_control import _get_zlm_client
    
    _sip_debug_log("invite_request_received", message, {"addr": str(addr)})
    
    # 解析来源和目标
    from_uri = message.from_header
    to_uri = message.to_header
    call_id = message.call_id
    from app.sip.invite_server_state import invite_server_state
    await invite_server_state.put(call_id, message, addr, proto, transport)
    trying = create_response(message, 100, "Trying", received_addr=addr)
    await send_response(transport, proto, addr, trying)
    
    requester_id = from_uri.split("sip:")[1].split("@")[0] if "sip:" in from_uri else ""
    target_id = to_uri.split("sip:")[1].split("@")[0] if "sip:" in to_uri else ""
    
    upstream_from_tag = ""
    from_hdr = message.get_header("From") or ""
    m_ftag = re.search(r";\s*tag=([^;>\s]+)", from_hdr, re.IGNORECASE)
    if m_ftag:
        upstream_from_tag = m_ftag.group(1).strip()
    
    sdp_body = message.body
    if not sdp_body:
        resp = create_response(message, 488, "Not Acceptable Here - Missing SDP")
        await send_response(transport, proto, addr, resp)
        await invite_server_state.pop(call_id)
        return

    from app.sip.sdp import parse_sdp, pick_media, is_tcp_profile, opposite_setup, build_sdp

    parsed = parse_sdp(sdp_body, fallback_ip=addr[0])
    media = pick_media(parsed, "video") or pick_media(parsed, "audio")
    recv_ip = str((media or {}).get("connection_ip") or parsed.get("connection_ip") or "").strip()
    # FIXED-P2: SDP port 转换添加异常保护，畸形 SDP 中 port 为非数字时不崩溃
    try:
        recv_port = int((media or {}).get("port") or 0)
    except (ValueError, TypeError):
        recv_port = 0
    recv_proto = str((media or {}).get("proto") or "")
    recv_setup = (media or {}).get("setup")
    recv_ssrc = str(parsed.get("ssrc") or "").strip()
    is_tcp = is_tcp_profile(recv_proto)
    session_name = str(parsed.get("session_name") or "Play").strip()

    if not recv_ip or recv_port <= 0:
        resp = create_response(message, 400)
        await send_response(transport, proto, addr, resp)
        await invite_server_state.pop(call_id)
        return
    if await invite_server_state.is_cancelled(call_id):
        resp = create_response(message, 487, "Request Terminated", received_addr=addr)
        await send_response(transport, proto, addr, resp)
        await invite_server_state.pop(call_id)
        return
        
    async with AsyncSessionLocal() as session:
        # 验证来源平台
        platform = (await session.execute(select(ParentPlatform).where(ParentPlatform.server_gb_id == requester_id))).scalars().first()
        if not platform:
            # Fallback to check if it's matching client_gb_id
            platform = (await session.execute(select(ParentPlatform).where(ParentPlatform.client_gb_id == requester_id))).scalars().first()
            
        # 如果设置了允许自动通过级联点播 (类似 auto-register) 或者是已知平台，放行
        if not platform and not bool(getattr(settings, "ALLOW_UNKNOWN_CASCADE_INVITE", True)):
            logger.warning(f"INVITE from unknown platform: {requester_id}")
            resp = create_response(message, 403)
            await send_response(transport, proto, addr, resp)
            await invite_server_state.pop(call_id)
            return
            
        # 查找目标通道 (先按 virtual_gb_id 找，找不到再按真实 gb_id)
        # 注意: 理论上应该通过映射反查真实 resource，这里简化处理
        real_gb_id = target_id
        resource_id = None
        if platform:
            mapping = (await session.execute(select(PlatformCatalogResource).where(
                PlatformCatalogResource.platform_id == platform.id,
                PlatformCatalogResource.virtual_gb_id == target_id
            ))).scalars().first()
            
            if mapping:
                mapped_resource = (await session.execute(select(Resource).where(Resource.id == mapping.resource_id))).scalars().first()
                if not mapped_resource:
                    resp = create_response(message, 404, "Resource Not Found", received_addr=addr)
                    await send_response(transport, proto, addr, resp)
                    await invite_server_state.pop(call_id)
                    return
                real_gb_id = mapped_resource.gb_id
                resource_id = mapping.resource_id
                
        if not resource_id:
            res = (await session.execute(select(Resource).where(Resource.gb_id == target_id))).scalars().first()
            if res:
                resource_id = res.id
                
        if not resource_id:
            logger.warning(f"INVITE target not found: {target_id}")
            resp = create_response(message, 404)
            await send_response(transport, proto, addr, resp)
            await invite_server_state.pop(call_id)
            return

        # 级联防雪崩与路由环路检测 (Cascade Loop Detection & Anti-Avalanche)
        # Check if the target is actually another cascade platform pushing to us (loop)
        # Or if the target is our own SIP_ID
        if target_id == settings.SIP_ID:
            logger.error(f"[Anti-Avalanche] Loop detected: Cascade INVITE target is our own SIP ID {settings.SIP_ID}")
            resp = create_response(message, 482, "Loop Detected")
            await send_response(transport, proto, addr, resp)
            await invite_server_state.pop(call_id)
            return
            
        # Check if the target resource belongs to another platform (meaning we learned it via cascade)
        # If the requester is also a platform, this is a platform-to-platform relay which is prone to loops.
        # We should only allow it if explicitly enabled.
        if resource_id:
            res_obj = (await session.execute(select(Resource).where(Resource.id == resource_id))).scalars().first()
            if res_obj and getattr(res_obj, "asset_id", None):
                asset = (await session.execute(select(Asset).where(Asset.id == res_obj.asset_id))).scalars().first()
                # If asset is a platform (has cascade info)
                if asset and str(getattr(asset, "manufacturer", "")).startswith("Cascade_"):
                    if not bool(getattr(settings, "ALLOW_CASCADE_RELAY", False)):
                        logger.error(f"[Anti-Avalanche] Cascade relay blocked: {requester_id} -> {target_id} (learned from another cascade)")
                        resp = create_response(message, 403, "Cascade Relay Forbidden")
                        await send_response(transport, proto, addr, resp)
                        await invite_server_state.pop(call_id)
                        return

        if not await invite_server_state.is_cancelled(call_id):
            ringing = create_response(message, 180, "Ringing", received_addr=addr)
            await send_response(transport, proto, addr, ringing)
            
        res_obj = (await session.execute(select(Resource).where(Resource.id == resource_id))).scalars().first()
        asset = None
        if res_obj and getattr(res_obj, "asset_id", None):
            asset = (await session.execute(select(Asset).where(Asset.id == res_obj.asset_id))).scalars().first()

        stream_to_send = real_gb_id
        local_stream = None
        if not asset:
            from app.models.push_channel import PushChannel
            from app.models.access_source import AccessSource

            pc = (
                await session.execute(
                    select(PushChannel).where(
                        PushChannel.gb_resource_id == resource_id,
                        PushChannel.gb_enabled == True,
                    )
                )
            ).scalars().first()
            if not pc:
                resp = create_response(message, 404)
                await send_response(transport, proto, addr, resp)
                await invite_server_state.pop(call_id)
                return
            src = (await session.execute(select(AccessSource).where(AccessSource.gb_resource_id == pc.gb_resource_id))).scalars().first()
            if not src or src.protocol != "RTMP":
                resp = create_response(message, 404)
                await send_response(transport, proto, addr, resp)
                await invite_server_state.pop(call_id)
                return
            stream_to_send = str(getattr(pc, "stream_name", None) or "") or str(src.stream_name or src.name or src.id)
            extra = src.extra if isinstance(getattr(src, "extra", None), dict) else {}
            running_val = extra.get("runtime.rtmp.is_running")
            is_running = bool(running_val) if isinstance(running_val, bool) else str(running_val or "").lower() == "true"
            if not is_running:
                resp = create_response(message, 480)
                await send_response(transport, proto, addr, resp)
                await invite_server_state.pop(call_id)
                return
        else:
            stmt_session = select(StreamSession).where(StreamSession.resource_id == resource_id)
            local_stream = (await session.execute(stmt_session)).scalars().first()
            
            # SDP Passthrough (RTP Media Bypass)
            if bool(getattr(settings, "CASCADE_RTP_MEDIA_BYPASS", True)):
                logger.info(f"[Cascade] Applying RTP Media Bypass for {real_gb_id}, sending INVITE directly to device with upstream SDP.")
                transport_info = (
                    (asset.ip_addr, asset.port),
                    asset.transport,
                    sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
                )
                try:
                    from app.sip.invite import sip_invite
                    bypass_res = await sip_invite.send_cascade_invite(
                        asset, res_obj, transport_info, sdp_body, session_name=session_name
                    )
                    
                    device_sdp = bypass_res.get("sdp_response", "")
                    if device_sdp:
                        resp = create_response(message, 200)
                        resp.headers["Content-Type"] = "application/sdp"
                        resp.headers["Contact"] = f"<sip:{settings.SIP_ID}@{sip_host_for_contact()}:{settings.SIP_PORT}>"
                        resp.body = device_sdp
                        
                        to_hdr = resp.get_header("To") or ""
                        to_tag = ""
                        m = re.search(r";\s*tag=([^;>\s]+)", to_hdr, re.IGNORECASE)
                        if m:
                            to_tag = (m.group(1) or "").strip()
                        if not to_tag:
                            to_tag = secrets.token_hex(8)
                            resp.headers["To"] = f"{to_hdr};tag={to_tag}"
                            
                        cascade_from_tag = str(bypass_res.get("from_tag") or "")
                        cascade_to_tag = str(bypass_res.get("to_tag") or to_tag)
                        cascade_call_id = str(bypass_res.get("call_id") or "")
                        cascade_ssrc = str(bypass_res.get("ssrc") or "0100000001")

                        cascade_session = StreamSession(
                            app="cascade_bypass",
                            stream=f"{real_gb_id}_bypass",
                            resource_id=resource_id,
                            asset_id=asset.id,
                            cascade_platform_id=platform.id if platform else None,
                            call_id=call_id,
                            from_tag=upstream_from_tag or "",
                            to_tag=to_tag,
                            cseq=1,
                            ssrc=cascade_ssrc,
                            protocol="UDP",
                            media_server_id="",
                            media_ip="",
                            media_port=0,
                            cascade_call_id=cascade_call_id,
                            cascade_from_tag=cascade_from_tag,
                            cascade_to_tag=cascade_to_tag,
                        )
                        session.add(cascade_session)
                        await session.commit()
                        
                        await send_response(transport, proto, addr, resp)
                        await invite_server_state.start_2xx_retransmit(call_id, resp)
                        return
                        
                except Exception as e:
                    logger.error(f"[Cascade] RTP Media Bypass failed: {e}, falling back to local ZLM pull.")
                    # check invite_ok before using sdp_response - if bypass failed, reply error to upstream
                    bypass_ok = bypass_res.get("invite_ok") if isinstance(bypass_res, dict) else False
                    if not bypass_ok:
                        logger.warning("[Cascade] Bypass invite_ok=False, replying 503 to upstream instead of fallback")
                        resp = create_response(message, 503)
                        await send_response(transport, proto, addr, resp)
                        await invite_server_state.pop(call_id)
                        return
            
            if not local_stream:
                logger.info(f"Stream for {real_gb_id} not found locally, pulling from device...")
                transport_info = (
                    (asset.ip_addr, asset.port),
                    asset.transport,
                    sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
                )
                try:
                    cascade_timeout = int(getattr(settings, "CASCADE_INVITE_TIMEOUT_SECONDS", 30) or 30)
                    invite_result = await asyncio.wait_for(
                        sip_invite.send_invite(asset, res_obj, transport_info),
                        timeout=cascade_timeout,
                    )
                    if invite_result and invite_result.get("invite_ok"):
                        stream_to_send = invite_result.get("stream", stream_to_send)
                except asyncio.TimeoutError:
                    logger.error(f"Cascade INVITE to device timed out after {cascade_timeout}s for {real_gb_id}")
                    resp = create_response(message, 504, "Gateway Timeout")
                    await send_response(transport, proto, addr, resp)
                    await invite_server_state.pop(call_id)
                    return
                except Exception as e:
                    logger.error(f"Failed to pull stream from device: {e}")
                    resp = create_response(message, 500)
                    await send_response(transport, proto, addr, resp)
                    await invite_server_state.pop(call_id)
                    return

        node = await select_best_db_node(session)
        if not node:
            resp = create_response(message, 500)
            await send_response(transport, proto, addr, resp)
            await invite_server_state.pop(call_id)
            return
        _cascade_app = getattr(local_stream, "app", "live") if local_stream else "live"
        if await invite_server_state.is_cancelled(call_id):
            resp = create_response(message, 487, "Request Terminated", received_addr=addr)
            await send_response(transport, proto, addr, resp)
            if not local_stream and asset:
                try:
                    ss = (await session.execute(
                        select(StreamSession).where(
                            StreamSession.resource_id == resource_id,
                            StreamSession.asset_id == asset.id,
                        )
                    )).scalars().first()
                    if ss:
                        from app.services.stream_session_service import finalize_stream_session
                        await finalize_stream_session(session, ss, reason="invite_cancelled_before_sendRtp")
                except Exception as cleanup_err:
                    logger.warning(f"Failed to cleanup after CANCEL (pre-startSendRtp): {cleanup_err}")
            await invite_server_state.pop(call_id)
            return
        if not local_stream and asset:
            stream_ready = False
            for _ in range(30):
                try:
                    check_url = f"http://{node.host}:{node.http_port}/index/api/getMediaList"
                    check_params = {"secret": node.secret, "vhost": "__defaultVhost__", "app": _cascade_app, "stream": stream_to_send}
                    client = await _get_zlm_client()
                    check_resp = await client.get(check_url, params=check_params, timeout=2.0)
                    check_data = check_resp.json()
                    if check_data.get("code") == 0 and check_data.get("data"):
                        stream_ready = True
                        break
                except Exception as e:
                    logger.warning(f"[Cascade] Stream readiness check failed: {e}")
                await asyncio.sleep(0.2)
            if not stream_ready:
                logger.warning(f"[Cascade] Stream {stream_to_send} not ready after 6s, proceeding anyway")
            
        requester_setup = str(recv_setup or "").strip().lower()
        if is_tcp and not requester_setup:
            requester_setup = "active"
        tcp_active = bool(is_tcp and requester_setup == "active")
        api_url = f"http://{node.host}:{node.http_port}/index/api/{'startSendRtpPassive' if tcp_active else 'startSendRtp'}"
        params = {
            "secret": node.secret,
            "vhost": "__defaultVhost__",
            "app": _cascade_app,
            "stream": stream_to_send,
            "ssrc": recv_ssrc or "0100000001",
            "pt": 96,
            "use_ps": "1",
            "only_audio": "0",
        }
        if not tcp_active:
            params.update(
                {
                    "dst_url": recv_ip,
                    "dst_port": recv_port,
                    "is_udp": 0 if is_tcp else 1,
                }
            )
        
        zlm_ret = None
        try:
            client = await _get_zlm_client()
            res = await client.post(api_url, data=params, timeout=5.0)
            zlm_ret = res.json()
            if zlm_ret.get("code") != 0:
                if tcp_active:
                    api_url2 = f"http://{node.host}:{node.http_port}/index/api/startSendRtp"
                    params2 = dict(params)
                    params2.update(
                        {
                            "dst_url": recv_ip,
                            "dst_port": recv_port,
                            "is_udp": 0,
                        }
                    )
                    res2 = await client.post(api_url2, data=params2, timeout=5.0)
                    zlm_ret2 = res2.json()
                    if zlm_ret2.get("code") == 0:
                        zlm_ret = zlm_ret2
                    else:
                        logger.warning(f"ZLM startSendRtp failed: {zlm_ret}; passive fallback failed: {zlm_ret2}")
                else:
                    logger.warning(f"ZLM startSendRtp failed: {zlm_ret}")
        except Exception as e:
            logger.error(f"Call ZLM API failed: {e}")
        if not zlm_ret or zlm_ret.get("code") != 0:
            resp = create_response(message, 500)
            await send_response(transport, proto, addr, resp)
            if not local_stream and asset:
                try:
                    ss = (await session.execute(
                        select(StreamSession).where(
                            StreamSession.resource_id == resource_id,
                            StreamSession.asset_id == asset.id,
                        )
                    )).scalars().first()
                    if ss:
                        from app.services.stream_session_service import finalize_stream_session
                        await finalize_stream_session(session, ss, reason="cascade_startSendRtp_failed")
                except Exception as cleanup_err:
                    logger.warning(f"Failed to cleanup device stream after startSendRtp failure: {cleanup_err}")
            await invite_server_state.pop(call_id)
            return
        if await invite_server_state.is_cancelled(call_id):
            resp = create_response(message, 487, "Request Terminated", received_addr=addr)
            await send_response(transport, proto, addr, resp)
            try:
                from app.services.zlm_stream_control import stop_rtp_pusher
                from app.core.media_nodes_db import get_db_node_by_id
                async with AsyncSessionLocal() as cancel_session:
                    db_node = await get_db_node_by_id(cancel_session, str(node.id if node else ""))
                    if db_node:
                        await stop_rtp_pusher(db_node.ip, db_node.http_port, db_node.secret, _cascade_app, stream_to_send)
            except Exception as stop_err:
                logger.warning(f"Failed to stop RTP pusher after CANCEL (post-startSendRtp): {stop_err}")
            await invite_server_state.pop(call_id)
            return
            
        # 组装响应 200 OK
        resp = create_response(message, 200)
        local_ip = sip_host_for_contact()
        local_port = zlm_ret.get("local_port", recv_port) if zlm_ret and zlm_ret.get("code") == 0 else recv_port  # S-03 ZLM失败时回退到recv_port而非硬编码10000

        resp_profile = "TCP/RTP/AVP" if is_tcp else "RTP/AVP"
        resp_setup = opposite_setup(str(recv_setup or "")) if is_tcp else None
        resp_sdp = build_sdp(
            origin_id=str(settings.SIP_ID),
            session_name="Play",
            connection_ip=str(local_ip),
            media_type="video",
            media_port=int(local_port),
            media_profile=resp_profile,
            direction="sendonly",
            ssrc=(recv_ssrc or "0100000001"),
            setup=resp_setup,
            extended_rtpmap=False,
        )
        resp.headers["Content-Type"] = "application/sdp"
        resp.headers["Contact"] = f"<sip:{settings.SIP_ID}@{local_ip}:{settings.SIP_PORT}>"
        resp.body = resp_sdp

        to_hdr = resp.get_header("To") or ""
        to_tag = ""
        m = re.search(r";\s*tag=([^;>\s]+)", to_hdr, re.IGNORECASE)
        if m:
            to_tag = (m.group(1) or "").strip()

        session_protocol = "UDP"
        if is_tcp:
            session_protocol = "TCP-PASSIVE" if str(recv_setup or "").strip().lower() == "active" else "TCP-ACTIVE"

        old_cascade_sessions = (await session.execute(
            select(StreamSession).where(
                StreamSession.resource_id == resource_id,
                StreamSession.cascade_platform_id.isnot(None),
            )
        )).scalars().all()
        for old_ss in old_cascade_sessions:
            try:
                from app.services.stream_session_service import finalize_stream_session
                await finalize_stream_session(session, old_ss, reason="cascade_replaced_by_new_invite")
            except Exception as old_cleanup_err:
                logger.warning(f"Failed to cleanup old cascade session: {old_cleanup_err}")

        cascade_session = StreamSession(
            app="live",
            stream=stream_to_send,
            resource_id=resource_id,
            asset_id=(asset.id if asset else None),
            cascade_platform_id=(platform.id if platform else None),
            call_id=call_id,
            from_tag=upstream_from_tag or uuid.uuid4().hex[:8],
            to_tag=to_tag,
            cseq=1,
            ssrc=recv_ssrc or "0100000001",
            media_server_id=node.id,
            media_ip=str(getattr(node, "host", "") or ""),
            media_port=int(local_port or 0),
            protocol=session_protocol,
        )
        session.add(cascade_session)
        await session.commit()

        # R-02 ctx_check为None时也改发487，防止对已丢失上下文的INVITE发送200OK
        async with invite_server_state._lock:
            ctx_check = invite_server_state._items.get(call_id)
            if ctx_check is None or ctx_check.cancelled:
                # CANCEL在异步操作期间到达或上下文已丢失，改发487而非200 OK
                resp = create_response(message, 487, "Request Terminated", received_addr=addr)

        await send_response(transport, proto, addr, resp)
        if int(getattr(resp, "status_code", 0) or 0) == 200:
            await invite_server_state.start_2xx_retransmit(call_id, resp)
        elif int(getattr(resp, "status_code", 0) or 0) == 487:
            await invite_server_state.start_2xx_retransmit(call_id, resp)
        else:
            await invite_server_state.pop(call_id)

async def handle_response(message: SipMessage, addr: tuple, proto: str, transport):
    _bg_create_task(plugin_manager.emit(HOOK_ON_SIP_RECEIVE, message, addr, proto))


    cseq = message.get_header("CSeq")
    _cseq_parts = (cseq or "").split(" ", 1)
    method = _cseq_parts[1].strip() if len(_cseq_parts) > 1 else ""
    if method == "INVITE":
        await handle_invite_response(message, addr, proto, transport)


async def handle_options(message: SipMessage, addr: tuple, proto: str, transport):
    """Handle SIP OPTIONS request for reachability detection (RFC 3261 Section 11)"""
    # GB1 SIP OPTIONS handler — RFC 3261 Section 11 可达性检测
    _bg_create_task(plugin_manager.emit(HOOK_ON_SIP_RECEIVE, message, addr, proto))
    resp = create_response(message, 200, received_addr=addr)
    resp.headers["Allow"] = "INVITE, ACK, CANCEL, BYE, OPTIONS, INFO, SUBSCRIBE, NOTIFY, MESSAGE, UPDATE"
    resp.headers["Accept"] = "application/sdp, Application/MANSCDP+xml"
    await send_response(transport, proto, addr, resp)


async def handle_update(message: SipMessage, addr: tuple, proto: str, transport):
    """Handle SIP UPDATE request for session parameter modification (RFC 3311)"""
    # GB1 SIP UPDATE handler — RFC 3311 会话参数更新
    call_id = message.call_id
    if not call_id:
        resp = create_response(message, 481, "Call/Transaction Does Not Exist", received_addr=addr)
        await send_response(transport, proto, addr, resp)
        return
    # For now, return 200 OK. Full UPDATE with SDP re-negotiation can be added later.
    resp = create_response(message, 200, received_addr=addr)
    await send_response(transport, proto, addr, resp)


async def handle_subscribe(message: SipMessage, addr: tuple, proto: str, transport):
    _bg_create_task(plugin_manager.emit(HOOK_ON_SIP_RECEIVE, message, addr, proto))
    expires = (message.get_header("Expires") or "").strip()
    from_uri = message.from_header or message.get_header("From") or ""
    subscribe_gb_id = ""
    if "sip:" in from_uri:
        subscribe_gb_id = from_uri.split("sip:")[1].split("@")[0].split(">")[0].split(";")[0]
    try:
        expires_int = int(expires) if expires else 0
    except Exception as _sub_exp_err:
        logger.debug(f"Invalid subscribe expires value: {_sub_exp_err}")  # W-10 吞异常改为日志
        expires_int = 0

    min_expires = int(getattr(settings, "SIP_SUBSCRIBE_MIN_EXPIRES", 60) or 60)
    if 0 < expires_int < min_expires:
        resp = create_response(message, 423, "Interval Too Brief", received_addr=addr)
        resp.headers["Min-Expires"] = str(min_expires)
        await send_response(transport, proto, addr, resp)
        return

    # FIXED-P2: 身份验证移到发送 200 OK 之前，避免同一 SUBSCRIBE 收到 200 OK + 403 两个最终响应
    _subscriber_known = True
    _sub_gb_id = ""
    _sub_event = ""
    try:
        _sub_event = (message.get_header("Event") or "").strip().split(";", 1)[0].strip()
        _sub_from_uri = message.from_header or ""
        if "sip:" in _sub_from_uri:
            _sub_gb_id = _sub_from_uri.split("sip:")[1].split("@")[0]
        if _sub_gb_id and _sub_event:
            _subscriber_known = False
            try:
                async with AsyncSessionLocal() as _sub_id_session:
                    _plat = (
                        await _sub_id_session.execute(
                            select(ParentPlatform).where(
                                (ParentPlatform.server_gb_id == _sub_gb_id) | (ParentPlatform.client_gb_id == _sub_gb_id)
                            )
                        )
                    ).scalars().first()
                    if _plat:
                        _subscriber_known = True
                    else:
                        _dev = (
                            await _sub_id_session.execute(select(Asset).where(Asset.gb_id == _sub_gb_id))
                        ).scalars().first()
                        if _dev:
                            _subscriber_known = True
            except Exception as _sub_id_err:
                logger.warning(f"[SUBSCRIBE] Identity lookup failed for {_sub_gb_id}: {_sub_id_err}")
            if not _subscriber_known:
                logger.warning(f"[SUBSCRIBE] Rejected: unknown subscriber gb_id={_sub_gb_id} from {addr}")
                _forbid_resp = create_response(message, 403, "Forbidden", received_addr=addr)
                await send_response(transport, proto, addr, _forbid_resp)
                return
    except Exception as _sub_precheck_err:
        logger.warning(f"[SUBSCRIBE] Pre-check error: {_sub_precheck_err}")

    resp = create_response(message, 200, received_addr=addr)
    expires = (message.get_header("Expires") or "").strip()
    if expires:
        resp.headers["Expires"] = expires
    resp.headers["Contact"] = f"<sip:{settings.SIP_ID}@{sip_host_for_contact()}:{settings.SIP_PORT}>"
    try:
        ev0 = ((message.get_header("Event") or "").strip()).split(";", 1)[0].strip()
        # GB5 SUBSCRIBE Event头验证 — 仅允许GB28181支持的事件类型
        _GB28181_ALLOWED_EVENTS = {"Catalog", "Alarm", "MobilePosition", "Presence"}
        if ev0 and ev0 not in _GB28181_ALLOWED_EVENTS:
            logger.warning(f"SUBSCRIBE rejected: unsupported Event type '{ev0}' from {addr}")
            resp = create_response(message, 489, "Bad Event", received_addr=addr)
            await send_response(transport, proto, addr, resp)
            return
        call_id0 = str(message.call_id or "")
        if ev0 and call_id0:
            tag_src = f"{call_id0}|{ev0}|{settings.SIP_ID}"
            local_tag = hashlib.sha256(tag_src.encode("utf-8", errors="ignore")).hexdigest()[:10]
            to_val = resp.headers.get("To") or ""
            to_val = re.sub(r";\s*tag=[^;>]+", "", to_val, flags=re.IGNORECASE).strip()
            if to_val:
                resp.headers["To"] = f"{to_val};tag={local_tag}"
    except Exception as e:
        logger.warning(f"Failed to set subscribe To tag: {e}")

    try:
        ev_lower = ((message.get_header("Event") or "").strip()).split(";", 1)[0].strip().lower()
        expires_int = int(expires) if expires and expires.isdigit() else _SIP_SUBSCRIBE_DEFAULT_EXPIRES
        if ev_lower == "catalog" and expires_int > 0:
            resp.headers["Content-Type"] = "Application/MANSCDP+xml"
            from_xml = _xml_escape(subscribe_gb_id or "")
            sn_val = secrets.randbelow(900000) + 100000
            resp.body = f'<?xml version="1.0" encoding="GB2312"?>\n<Response>\n<CmdType>Catalog</CmdType>\n<SN>{sn_val}</SN>\n<DeviceID>{from_xml}</DeviceID>\n<Result>OK</Result>\n</Response>'
        # handle_subscribe 支持 Alarm 事件
        elif ev_lower == "alarm" and expires_int > 0:
            resp.headers["Content-Type"] = "Application/MANSCDP+xml"
            from_xml = _xml_escape(subscribe_gb_id or "")
            sn_val = secrets.randbelow(900000) + 100000
            resp.body = (
                '<?xml version="1.0" encoding="GB2312"?>\n'
                '<Response>\n'
                '<CmdType>Alarm</CmdType>\n'
                f'<SN>{sn_val}</SN>\n'
                f'<DeviceID>{from_xml}</DeviceID>\n'
                '<Result>OK</Result>\n'
                '</Response>'
            )
    except Exception as e:
        logger.debug(f"Exception: {e}")

    await send_response(transport, proto, addr, resp)
    # FIXED-P2: 身份验证已在发送 200 OK 之前完成，_after_subscribe 不再重复验证
    async def _after_subscribe() -> None:
        try:
            event = (message.get_header("Event") or "").strip()
            from_uri = message.from_header or ""
            gb_id = ""
            if "sip:" in from_uri:
                gb_id = from_uri.split("sip:")[1].split("@")[0]
            if not gb_id:
                return
            try:
                expires_int = int(expires) if expires else 0
            except Exception as _plat_exp_err:
                logger.debug(f"Invalid platform subscribe expires value: {_plat_exp_err}")  # W-10 吞异常改为日志
                expires_int = 0

            async with AsyncSessionLocal() as session:
                platform = (
                    await session.execute(select(ParentPlatform).where(ParentPlatform.server_gb_id == gb_id))
                ).scalars().first()
                if not platform:
                    platform = (
                        await session.execute(select(ParentPlatform).where(ParentPlatform.client_gb_id == gb_id))
                    ).scalars().first()
            if not platform:
                return

            from app.services.platform_subscription_service import platform_subscription_service
            from_hdr = message.get_header("From") or ""
            m = re.search(r";\s*tag=([^;>\s]+)", from_hdr, re.IGNORECASE)
            remote_from_tag = m.group(1) if m else ""
            to_hdr = resp.headers.get("To") or ""
            m2 = re.search(r";\s*tag=([^;>\s]+)", to_hdr, re.IGNORECASE)
            local_to_tag = m2.group(1) if m2 else ""
            remote_contact = (message.get_header("Contact") or "").strip()
            record_route = ", ".join([h.strip() for h in message.get_headers("Record-Route") if (h or "").strip()])
            await platform_subscription_service.upsert_subscription(
                tenant_id=platform.tenant_id or "default",
                platform_id=platform.id,
                event=event,
                expires_seconds=expires_int,
                addr=f"{addr[0]}:{addr[1]}",
                transport=str(proto or ""),
                call_id=str(message.call_id or ""),
                remote_from_tag=remote_from_tag,
                local_to_tag=local_to_tag,
                remote_contact=remote_contact,
                record_route=record_route,
            )

            if ev0.lower() == "catalog" and expires_int > 0:
                import app.services.platform_service as platform_service_mod
                svc = getattr(platform_service_mod, "platform_service", None)
                if svc and getattr(svc, "running", False):
                    _bg_create_task(svc.trigger_push_catalog(platform.id))

            if expires_int == 0:
                try:
                    cseq_hdr = message.get_header("CSeq") or "1 SUBSCRIBE"
                    try:
                        notify_cseq = int(cseq_hdr.split()[0]) + 1
                    except (ValueError, IndexError):
                        notify_cseq = 2
                    from app.sip.send import send_sip_bytes
                    from app.sip.message import SipMessage
                    from app.sip.utils import sip_host_for_contact
                    notify_req = SipMessage()
                    notify_req.method = "NOTIFY"
                    notify_req.uri = message.get_header("Contact") or f"sip:{gb_id}@{addr[0]}:{addr[1]}"
                    notify_req.version = "SIP/2.0"
                    branch = f"z9hG4bK{secrets.token_hex(6)}" # __import__ 反模式改为标准 import
                    notify_req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
                    notify_req.headers["From"] = resp.headers.get("To", "")
                    notify_req.headers["To"] = message.get_header("From")
                    notify_req.headers["Call-ID"] = str(message.call_id or "")
                    notify_req.headers["CSeq"] = f"{notify_cseq} NOTIFY"
                    notify_req.headers["Contact"] = f"<sip:{settings.SIP_ID}@{sip_host_for_contact()}:{settings.SIP_PORT}>"
                    notify_req.headers["Event"] = event
                    notify_req.headers["Subscription-State"] = "terminated"
                    notify_req.headers["Max-Forwards"] = str(_SIP_MAX_FORWARDS_DEFAULT)
                    notify_req.headers["User-Agent"] = settings.PROJECT_NAME
                    await send_sip_bytes(proto, transport, addr, notify_req.to_bytes())
                    logger.info(f"[SUBSCRIBE] Sent terminated NOTIFY for {gb_id} event={event}")
                except Exception as notify_err:
                    logger.warning(f"[SUBSCRIBE] Failed to send terminated NOTIFY: {notify_err}")
        except Exception as e:
            logger.error(f"[SUBSCRIBE] _after_subscribe error: {e}", exc_info=True)

    _bg_create_task(_after_subscribe())
    # FIXED-P2: 身份验证已移到发送 200 OK 之前，此处仅保留订阅管理逻辑
    try:
        event = (message.get_header("Event") or "").strip().split(";", 1)[0].strip()
        from_uri = message.from_header or ""
        gb_id = ""
        if "sip:" in from_uri:
            gb_id = from_uri.split("sip:")[1].split("@")[0]
        if gb_id and event:
            try:
                expires_int = int(expires) if expires else 0
            except Exception as _notify_exp_err:
                logger.debug(f"Invalid NOTIFY subscribe expires value: {_notify_exp_err}")
                expires_int = 0
            from app.sip.subscribe_manager import subscribe_manager, SubscribeInfo
            from_hdr = message.get_header("From") or ""
            m = re.search(r";\s*tag=([^;>\s]+)", from_hdr, re.IGNORECASE)
            remote_from_tag = m.group(1) if m else ""
            to_hdr = resp.headers.get("To") or ""
            m2 = re.search(r";\s*tag=([^;>\s]+)", to_hdr, re.IGNORECASE)
            local_to_tag = m2.group(1) if m2 else ""
            cseq_val = message.get_header("CSeq") or "1 SUBSCRIBE"
            try:
                cseq_num = int(cseq_val.split()[0])
            except (ValueError, IndexError):
                cseq_num = 1
            sub_info = SubscribeInfo(
                device_id=gb_id,
                event=event,
                call_id=str(message.call_id or ""),
                from_tag=remote_from_tag,
                to_tag=local_to_tag,
                cseq=cseq_num,
                expires=expires_int,
                sn=cseq_num,
                remote_addr=addr,
                remote_proto=proto,
            )
            await subscribe_manager.put_inbound(sub_info)
    except Exception as e:
        logger.error(f"[SUBSCRIBE] _after_subscribe error: {e}", exc_info=True)


async def handle_notify(message: SipMessage, addr: tuple, proto: str, transport):
    _bg_create_task(plugin_manager.emit(HOOK_ON_SIP_RECEIVE, message, addr, proto))
    event_hdr = (message.get_header("Event") or "").strip()
    call_id_hdr = (message.get_header("Call-ID") or "").strip()
    from_hdr = message.get_header("From") or ""
    to_hdr = message.get_header("To") or ""
    notify_from_tag = ""
    notify_to_tag = ""
    m_from = re.search(r";\s*tag=([^;>\s]+)", from_hdr, re.IGNORECASE)
    m_to = re.search(r";\s*tag=([^;>\s]+)", to_hdr, re.IGNORECASE)
    if m_from:
        notify_from_tag = m_from.group(1).strip()
    if m_to:
        notify_to_tag = m_to.group(1).strip()
    subscription_found = False
    if event_hdr and call_id_hdr:
        try:
            from app.services.platform_subscription_service import platform_subscription_service
            subs = await platform_subscription_service.list_active_subscriptions(
                tenant_id="default", event=event_hdr
            )
            for sub in subs:
                if getattr(sub, "call_id", None) == call_id_hdr:
                    sub_from_tag = str(getattr(sub, "from_tag", "") or "").strip()
                    sub_to_tag = str(getattr(sub, "to_tag", "") or "").strip()
                    if sub_from_tag and sub_to_tag:
                        if notify_from_tag == sub_from_tag and notify_to_tag == sub_to_tag:
                            subscription_found = True
                            break
                    else:
                        subscription_found = True
                        break
        except Exception as _sub_find_err:
            logger.debug(f"Failed to check subscription existence: {_sub_find_err}")  # W-10 吞异常改为日志
            subscription_found = False
    else:
        subscription_found = False
    if not subscription_found:
        logger.warning(f"[NOTIFY] No matching subscription for event={event_hdr} call_id={call_id_hdr}, replying 481")
        resp = create_response(message, 481, "Call/Transaction Does Not Exist", received_addr=addr)
        await send_response(transport, proto, addr, resp)
        return
    resp = create_response(message, 200, received_addr=addr)
    await send_response(transport, proto, addr, resp)
    async def _after_notify() -> None:
        try:
            event = (message.get_header("Event") or "").strip()
            from_uri = message.from_header or ""
            gb_id = ""
            if "sip:" in from_uri:
                gb_id = from_uri.split("sip:")[1].split("@")[0]
            if not gb_id:
                return
            async with AsyncSessionLocal() as session:
                platform = (
                    await session.execute(select(ParentPlatform).where(ParentPlatform.server_gb_id == gb_id))
                ).scalars().first()
                if not platform:
                    platform = (
                        await session.execute(select(ParentPlatform).where(ParentPlatform.client_gb_id == gb_id))
                    ).scalars().first()
            if not platform:
                return
            from app.services.platform_subscription_service import platform_subscription_service
            await platform_subscription_service.mark_notify(
                tenant_id=platform.tenant_id or "default",
                platform_id=platform.id,
                event=event,
            )

            sub_state = (message.get_header("Subscription-State") or "").strip()
            if sub_state.lower().startswith("terminated"):
                logger.info(f"[NOTIFY] Subscription terminated for {gb_id} event={event}")
                try:
                    from app.sip.subscribe_manager import subscribe_manager
                    await subscribe_manager.remove_inbound(gb_id, event)
                except Exception as e:
                    logger.debug(f"[NOTIFY] Failed to remove inbound subscription: {e}")

            body = getattr(message, "body", "") or ""
            if body and event.lower() == "catalog":
                try:
                    from app.core.xml_utils import parse_xml
                    root = parse_xml(body)
                    sn_el = root.findtext("SN", "")
                    device_id_el = root.findtext("DeviceID", "")
                    cmd_el = root.findtext("CmdType", "")
                    item_list = root.findall(".//Item")
                    if item_list:
                        from app.sip.catalog_runtime import catalog_runtime
                        await catalog_runtime.handle_catalog_notify_items(gb_id, item_list)
                        logger.info(f"[NOTIFY] Parsed catalog notify from {gb_id}: {len(item_list)} items, SN={sn_el}")
                except Exception as catalog_err:
                    logger.debug(f"[NOTIFY] Failed to parse catalog notify body: {catalog_err}")
            # MobilePosition NOTIFY处理 — 解析设备上报的移动位置通知并更新数据库
            elif body and event.lower() == "mobileposition":
                try:
                    _bg_create_task(handle_mobile_position_notify(body, gb_id))
                    # Also dispatch to subscribe_manager callbacks
                    from app.sip.subscribe_manager import subscribe_manager
                    from app.core.xml_utils import parse_xml as _parse_xml, get_xml_text as _get_xml_text
                    pos_root = _parse_xml(body)
                    if pos_root is not None:
                        position = {
                            "longitude": _get_xml_text(pos_root, "Longitude"),
                            "latitude": _get_xml_text(pos_root, "Latitude"),
                            "time": _get_xml_text(pos_root, "Time"),
                            "speed": _get_xml_text(pos_root, "Speed"),
                            "direction": _get_xml_text(pos_root, "Direction"),
                            "altitude": _get_xml_text(pos_root, "Altitude"),
                        }
                        await subscribe_manager.notify_mobile_position(gb_id, position)
                    logger.info(f"[NOTIFY] Parsed MobilePosition notify from {gb_id}")
                except Exception as mp_err:
                    logger.warning(f"[NOTIFY] Failed to process MobilePosition notify: {mp_err}")
        except Exception as e:
            logger.error(f"[NOTIFY] _after_notify error: {e}", exc_info=True)
            return

    _bg_create_task(_after_notify())


async def handle_cancel(message: SipMessage, addr: tuple, proto: str, transport):
    _bg_create_task(plugin_manager.emit(HOOK_ON_SIP_RECEIVE, message, addr, proto))
    call_id = message.call_id
    # S-05 CANCEL 未验证 Via branch 是否与原始 INVITE 匹配（RFC 3261 Section 9.1）
    cancel_via = message.get_header("Via") or ""
    cancel_branch = ""
    via_match = re.search(r";branch=([^;]+)", cancel_via, re.IGNORECASE)
    if via_match:
        cancel_branch = via_match.group(1).strip()
    if call_id:
        from app.sip.invite_server_state import invite_server_state
        # Verify Via branch matches the original INVITE's branch
        async with invite_server_state._lock:
            ctx = invite_server_state._items.get(call_id)
        if ctx and ctx.message:
            inv_via = ctx.message.get_header("Via") or ""
            inv_branch = ""
            inv_match = re.search(r";branch=([^;]+)", inv_via, re.IGNORECASE)
            if inv_match:
                inv_branch = inv_match.group(1).strip()
            if cancel_branch and inv_branch and cancel_branch != inv_branch:
                logger.warning(f"CANCEL Via branch mismatch: cancel={cancel_branch} invite={inv_branch} call_id={call_id}")
                resp = create_response(message, 481, "Call/Transaction Does Not Exist", received_addr=addr)
                await send_response(transport, proto, addr, resp)
                return
        stats = await invite_server_state.get_stats(call_id)
        if stats and stats.get("acked"):
            resp = create_response(message, 200, received_addr=addr)
            await send_response(transport, proto, addr, resp)
            return
        if stats and stats.get("final_response_sent"):
            resp = create_response(message, 200, received_addr=addr)
            await send_response(transport, proto, addr, resp)
            logger.info(f"CANCEL received after 200 OK sent for {call_id}, caller should send BYE")
            return
        if not stats:
            resp = create_response(message, 481, "Call/Transaction Does Not Exist", received_addr=addr)
            await send_response(transport, proto, addr, resp)
            return
    resp = create_response(message, 200, received_addr=addr)
    await send_response(transport, proto, addr, resp)
    if call_id:
        from app.sip.invite_server_state import invite_server_state
        ctx = await invite_server_state.mark_cancelled(call_id)
        if ctx:
            try:
                resp2 = create_response(ctx.message, 487, "Request Terminated", received_addr=ctx.addr)
                await send_response(ctx.transport, ctx.proto, ctx.addr, resp2)
                # S-01 CANCEL后487响应启动重传机制(RFC 3261 §17.2.1)，而非立即pop导致487无法重传
                await invite_server_state.start_2xx_retransmit(call_id, resp2)
            except Exception as e:
                logger.warning(f"Failed to send 487 response: {e}")
                await invite_server_state.pop(call_id)


async def handle_ack(message: SipMessage, addr: tuple, proto: str, transport):
    _bg_create_task(plugin_manager.emit(HOOK_ON_SIP_RECEIVE, message, addr, proto))
    call_id = message.call_id
    if call_id:
        from app.sip.invite_server_state import invite_server_state
        # GB28181协议 — 验证ACK的From/To tag是否与原始INVITE匹配
        async with invite_server_state._lock:
            ctx = invite_server_state._items.get(call_id)
        if ctx and ctx.message:
            ack_from_tag = ""
            ack_to_tag = ""
            from_hdr = message.get_header("From") or ""
            to_hdr = message.get_header("To") or ""
            m_ftag = re.search(r";\s*tag=([^;>\s]+)", from_hdr, re.IGNORECASE)
            m_ttag = re.search(r";\s*tag=([^;>\s]+)", to_hdr, re.IGNORECASE)
            if m_ftag:
                ack_from_tag = m_ftag.group(1).strip()
            if m_ttag:
                ack_to_tag = m_ttag.group(1).strip()
            inv_from_tag = ""
            inv_to_tag = ""
            inv_from_hdr = ctx.message.get_header("From") or ""
            inv_to_hdr = ctx.message.get_header("To") or ""
            m_inv_ftag = re.search(r";\s*tag=([^;>\s]+)", inv_from_hdr, re.IGNORECASE)
            m_inv_ttag = re.search(r";\s*tag=([^;>\s]+)", inv_to_hdr, re.IGNORECASE)
            if m_inv_ftag:
                inv_from_tag = m_inv_ftag.group(1).strip()
            if m_inv_ttag:
                inv_to_tag = m_inv_ttag.group(1).strip()
            if ack_from_tag and inv_from_tag and ack_from_tag != inv_from_tag:
                logger.warning(f"[GB28181] ACK From tag mismatch for call_id={call_id}: ack_from_tag={ack_from_tag} inv_from_tag={inv_from_tag}")
                resp = create_response(message, 481, "Call/Transaction Does Not Exist", received_addr=addr)
                await send_response(transport, proto, addr, resp)
                return
            if ack_to_tag and inv_to_tag and ack_to_tag != inv_to_tag:
                logger.warning(f"[GB28181] ACK To tag mismatch for call_id={call_id}: ack_to_tag={ack_to_tag} inv_to_tag={inv_to_tag}")
                resp = create_response(message, 481, "Call/Transaction Does Not Exist", received_addr=addr)
                await send_response(transport, proto, addr, resp)
                return
        ok = await invite_server_state.mark_acked(call_id)
        if ok:
            stats = await invite_server_state.get_stats(call_id)
            if stats:
                _sip_debug_log("invite_ack_received", message, stats)
            # W-01 confirm_transaction 未被调用 — 收到ACK后需将事务状态从 Accepted 推进到 Confirmed
            try:
                from app.sip.transactions import server_tx_manager
                from app.sip.server import sip_server
                tx_key = sip_server._tx_key_from_request(message)
                await server_tx_manager.confirm_transaction(tx_key)
            except Exception as _tx_err:
                logger.debug(f"confirm_transaction failed in handle_ack: {_tx_err}")
            await invite_server_state.pop(call_id)
    return


async def handle_info(message: SipMessage, addr: tuple, proto: str, transport):
    _bg_create_task(plugin_manager.emit(HOOK_ON_SIP_RECEIVE, message, addr, proto))
    # 解析 MANSRTSP 内容，提取 NPT 播放进度
    body = message.body or ""
    if body and "MANSRTSP" in body:
        npt_match = re.search(r'Range:\s*npt=([\d.]+)-([\d.]*)', body)
        if npt_match:
            npt_start = float(npt_match.group(1))
            npt_end = float(npt_match.group(2)) if npt_match.group(2) else None
            logger.debug(f"GET_PARAMETER NPT response: start={npt_start}, end={npt_end}")
            # 存储到 playback_control 的 NPT 结果字典
            call_id = message.call_id or ""
            if call_id:
                from app.sip.playback_control import _npt_results_put  # W-30 使用带大小限制的写入方法
                _npt_results_put(call_id, {"npt_start": npt_start, "npt_end": npt_end})
    resp = create_response(message, 200, received_addr=addr)
    await send_response(transport, proto, addr, resp)

async def handle_bye(message: SipMessage, addr: tuple, proto: str, transport):
    """
    Handle BYE request (stop stream)

    安全加固（P0）：
    - 必须验证 Call-ID + From tag + To tag 三元组，防止攻击者仅凭 Call-ID 伪造 BYE
    - 若 session 存在但三元组不匹配，返回 481 Call/Transaction Does Not Exist
    - 若 session 不存在，直接返回 200 OK（防探测）
    - IP 来自非预期地址时记录告警
    """
    call_id = message.call_id or ""
    from_tag = message.get_header("From") or ""
    to_tag = message.get_header("To") or ""
    client_ip = addr[0] if addr else ""
    logger.info(f"Received BYE for Call-ID: {call_id}, from {client_ip}")

    async with AsyncSessionLocal() as session:
        stmt = select(StreamSession).where(StreamSession.call_id == call_id)
        result = await session.execute(stmt)
        stream_session = result.scalars().first()

        if not stream_session:
            stmt2 = select(StreamSession).where(StreamSession.cascade_call_id == call_id)
            result2 = await session.execute(stmt2)
            stream_session = result2.scalars().first()

        if stream_session:
            # 三元组校验：Call-ID + From tag + To tag
            # StreamSession 存储的是 INVITE 响应中的本地 to_tag（下级设备的 from_tag）
            # 和本端发出的 from_tag。BYE 请求中的 From/To header 方向与 INVITE 相反。
            ss_from_tag: str = stream_session.from_tag or ""
            ss_to_tag: str = stream_session.to_tag or ""

            # GB28181 中 BYE 的 From/To 标签与 INVITE 相反：
            # INVITE:   本端 From-tag=X  →  下级 To-tag=Y
            # BYE:     下级 From-tag=Y  →  本端 To-tag=X
            # 因此 BYE 请求的 from_tag 应匹配 ss_to_tag，to_tag 应匹配 ss_from_tag
            # 精确匹配：从 header 中提取 tag 值，避免 endswith 误判
            def _extract_tag_from_header(header_val: str) -> str:
                if not header_val:
                    return ""
                m = re.search(r";\s*tag=([^;>\s]+)", header_val, re.IGNORECASE)
                return m.group(1).strip() if m else ""

            bye_from_tag = _extract_tag_from_header(from_tag)
            bye_to_tag = _extract_tag_from_header(to_tag)

            # RFC 3261 §15.1.2: BYE 的 From/To tag 必须与 INVITE 对话一致。
            # GB28181 场景下有两种方向：
            #   方向A（设备挂断）: BYE From-tag=设备tag(Y), To-tag=本端tag(X)
            #     → bye_from==ss_to_tag, bye_to==ss_from_tag
            #   方向B（本端挂断）: BYE From-tag=本端tag(X), To-tag=设备tag(Y)
            #     → bye_from==ss_from_tag, bye_to==ss_to_tag
            # 两种方向都是合法的，但必须严格匹配，不允许交叉匹配。
            tag_matched = (
                (ss_to_tag and bye_from_tag == ss_to_tag and ss_from_tag and bye_to_tag == ss_from_tag)
                or (ss_from_tag and bye_from_tag == ss_from_tag and ss_to_tag and bye_to_tag == ss_to_tag)
            )

            # S-06 BYE tag为空时降级为Call-ID-only匹配存在伪造风险，增加源IP+端口校验
            if not tag_matched and (not ss_from_tag or not ss_to_tag):
                # 生产环境可禁用降级匹配（SIP_STRICT_BYE_TAG_MATCH=True）
                if getattr(settings, "SIP_STRICT_BYE_TAG_MATCH", False):
                    logger.error(
                        "BYE rejected: strict tag matching enabled, tag fallback disabled for %s",
                        call_id
                    )
                    resp = create_response(message, 481, "Call/Transaction Does Not Exist", received_addr=addr)
                    await send_response(transport, proto, addr, resp)
                    return
                # 查找该session关联的设备注册IP和端口，校验源地址
                _registered_ip = ""
                _registered_port = 0
                try:
                    # M-04 消除BYE处理嵌套DB会话，使用外层session查询
                    _asset_stmt = select(Asset).where(Asset.id == stream_session.asset_id) if stream_session.asset_id else None
                    if _asset_stmt is not None:
                        _asset_row = (await session.execute(_asset_stmt)).scalars().first()
                        if _asset_row and _asset_row.ip_addr:
                            _addr_str = str(_asset_row.ip_addr).strip()
                            if ":" in _addr_str:
                                _registered_ip = _addr_str.rsplit(":", 1)[0]
                                try:
                                    _registered_port = int(_addr_str.rsplit(":", 1)[1])
                                except (ValueError, IndexError):
                                    pass
                            else:
                                _registered_ip = _addr_str
                except Exception:
                    logger.debug("BYE handler: failed to query registered IP, skipping IP validation")
                if _registered_ip and client_ip != _registered_ip:
                    logger.warning(
                        "BYE rejected: Call-ID-only match with IP mismatch for %s (registered=%s, bye_from=%s)",
                        call_id, _registered_ip, client_ip
                    )
                    resp = create_response(message, 481, "Call/Transaction Does Not Exist", received_addr=addr)
                    await send_response(transport, proto, addr, resp)
                    return
                # S-06 增加源端口校验 — 同NAT下不同设备端口不同
                if _registered_port and len(addr) >= 2:
                    bye_src_port = addr[1]
                    if isinstance(bye_src_port, int) and bye_src_port != _registered_port:
                        logger.warning(
                            "BYE rejected: Call-ID-only match with port mismatch for %s (registered_port=%s, bye_port=%s)",
                            call_id, _registered_port, bye_src_port
                        )
                        resp = create_response(message, 481, "Call/Transaction Does Not Exist", received_addr=addr)
                        await send_response(transport, proto, addr, resp)
                        return
                tag_matched = True
                logger.warning(
                    "BYE tag fallback to Call-ID+IP+port match for %s (ss_from=%s, ss_to=%s, bye_ip=%s) - legacy device compatibility",
                    call_id, ss_from_tag, ss_to_tag, client_ip
                )

            # 额外安全：如果 session 有 cascade_call_id 且 BYE 的 Call-ID 匹配 cascade_call_id，
            # 则标签校验需要匹配 cascade_from_tag / cascade_to_tag
            if not tag_matched and stream_session.cascade_call_id and call_id == stream_session.cascade_call_id:
                cascade_from = str(getattr(stream_session, "cascade_from_tag", "") or "")
                cascade_to = str(getattr(stream_session, "cascade_to_tag", "") or "")
                if cascade_from and cascade_to:
                    tag_matched = (
                        (bye_from_tag == cascade_to and bye_to_tag == cascade_from)
                        or (bye_from_tag == cascade_from and bye_to_tag == cascade_to)
                    )

            if not tag_matched:
                logger.warning(
                    f"BYE auth failed for {call_id}: tag mismatch "
                    f"(ss_from={ss_from_tag}, ss_to={ss_to_tag}, "
                    f"bye_from={bye_from_tag}, bye_to={bye_to_tag}). "
                    f"Possible forged BYE from {client_ip}"
                )
                # 返回 481 不暴露 session 存在性
                resp = create_response(message, 481, "Call/Transaction Does Not Exist", received_addr=addr)
                await send_response(transport, proto, addr, resp)
                return

            # 三元组校验通过，先回复 200 OK 再关闭会话，避免 DB 异常导致设备重发 BYE
            resp = create_response(message, 200, received_addr=addr)
            await send_response(transport, proto, addr, resp)

            from app.services.stream_session_service import finalize_stream_session
            # W-06 handle_bye与release_stream_session并发时session可能已被删除，加try保护
            try:
                cascade_call_id_val = str(getattr(stream_session, "cascade_call_id", "") or "")
                if cascade_call_id_val:
                    from app.services.zlm_stream_control import stop_rtp_pusher
                    from app.core.media_nodes_db import get_db_node_by_id
                    try:
                        db_node = await get_db_node_by_id(session, str(getattr(stream_session, "media_server_id", "") or ""))
                        if db_node:
                            await stop_rtp_pusher(
                                db_node.ip, db_node.http_port, db_node.secret,
                                str(getattr(stream_session, "app", "") or ""),
                                str(getattr(stream_session, "stream", "") or ""),
                            )
                        else:
                            logger.warning(f"[BYE] media_server_id={getattr(stream_session, 'media_server_id', '')} not found in DB, call_id={call_id}")
                    except Exception as stop_err:
                        logger.warning(f"Failed to stop ZLM RTP pusher for cascade BYE {call_id}: {stop_err}")

                inner_call_id = str(getattr(stream_session, "call_id", "") or "")
                inner_asset_id = str(getattr(stream_session, "asset_id", "") or "")
                inner_resource_id = str(getattr(stream_session, "resource_id", "") or "")
                if inner_asset_id and inner_resource_id:
                    try:
                        # M-04 消除BYE处理嵌套DB会话，使用外层session查询
                        inner_stmt = select(StreamSession).where(
                            StreamSession.asset_id == inner_asset_id,
                            StreamSession.resource_id == inner_resource_id,
                            StreamSession.call_id != inner_call_id,
                        )
                        inner_ss = (await session.execute(inner_stmt)).scalars().first()
                        if inner_ss:
                            inner_ci = str(getattr(inner_ss, "call_id", "") or "")
                            logger.info(f"[BYE] Propagating cascade BYE to inner device session: {inner_ci}")
                            try:
                                from app.services.stream_session_service import release_stream_session
                                await release_stream_session(session, inner_ss, reason="cascade_bye_propagated")
                            except Exception as inner_rel_err:
                                logger.warning(f"[BYE] Failed to release inner device session {inner_ci}: {inner_rel_err}")
                    except Exception as inner_lookup_err:
                        logger.debug(f"[BYE] Inner device session lookup failed: {inner_lookup_err}")
                await finalize_stream_session(session, stream_session, reason="sip_bye")
                logger.info(f"Stream session {call_id} closed via authenticated BYE")
                # S-04 移除重复SSRC释放，finalize_stream_session内部已释放
                try:
                    ft = str(getattr(stream_session, "from_tag", "") or "")
                    if ft:
                        from app.sip.dialog_manager import dialog_manager
                        await dialog_manager.terminate_dialog(call_id, ft)
                except Exception as dlg_err:
                    logger.debug(f"Dialog terminate on BYE failed: {dlg_err}")
            except Exception as e:
                logger.error(f"Failed to finalize stream session for BYE {call_id}: {e}")

            from app.sip.invite_server_state import invite_server_state
            await invite_server_state.pop(call_id)
            cascade_call_id_val2 = str(getattr(stream_session, "cascade_call_id", "") or "")
            if cascade_call_id_val2 and cascade_call_id_val2 != call_id:
                await invite_server_state.pop(cascade_call_id_val2)
            # BYE处理后取消流切换看门狗，防止超时后对已终止会话发送Re-INVITE
            try:
                from app.sip.watchdog import cancel_stream_switch_watchdog
                cancel_stream_switch_watchdog(call_id)
            except Exception as _wd_err:
                logger.debug(f"Failed to cancel stream switch watchdog on BYE: {_wd_err}")
            # GB28181协议 — BYE处理后清理流切换全局字典
            try:
                from app.sip.invite import invite_state
                async with invite_state.stream_switch_lock:
                    invite_state.stream_switch_pending.pop(call_id, None)
                    invite_state.stream_switch_pending_timestamps.pop(call_id, None)
                    invite_state.stream_switch_rollback_depth.pop(call_id, None)
                    invite_state.stream_switch_rollback_depth_timestamps.pop(call_id, None)
            except Exception as _switch_err:
                logger.debug(f"Failed to cleanup stream switch state: {_switch_err}")  # W-10 吞异常改为日志
            # R4-01 BYE处理清理playback状态，防止内存泄漏
            try:
                from app.sip.playback_control import playback_control as _pb_ctrl
                if _pb_ctrl:
                    _pb_ctrl._playback_states.pop(call_id, None)
            except Exception:
                pass
            return
        # else: session 不存在时直接返回 200 OK，防探测

    # Respond 200 OK
    resp = create_response(message, 200, received_addr=addr)
    await send_response(transport, proto, addr, resp)

def init_handlers():
    from app.sip.server import sip_server
    from app.sip.invite_server_state import invite_server_state
    from app.sip.storm_handler import start_storm_handler
    from loguru import logger
    start_storm_handler()
    invite_server_state.start()
    invite_server_state.set_sender(lambda transport, proto, addr, msg: send_response(transport, proto, addr, msg))
    # 启动时从DB恢复活跃SSRC，防止进程重启后SSRC冲突
    from app.sip.ssrc_manager import ssrc_manager
    _bg_create_task(ssrc_manager.restore_from_db())
    try:
        from app.sip.subscribe_manager import subscribe_manager
        _bg_create_task(subscribe_manager.start())
    except Exception as e:
        logger.warning(f"Failed to start subscribe_manager: {e}")
    sip_server.register_handler("REGISTER", handle_register)
    sip_server.register_handler("MESSAGE", handle_message_request)
    sip_server.register_handler("BYE", handle_bye)
    sip_server.register_handler("INVITE", handle_invite_request)
    sip_server.register_handler("OPTIONS", handle_options)
    sip_server.register_handler("SUBSCRIBE", handle_subscribe)
    sip_server.register_handler("NOTIFY", handle_notify)
    sip_server.register_handler("CANCEL", handle_cancel)
    sip_server.register_handler("ACK", handle_ack)
    sip_server.register_handler("INFO", handle_info)
    sip_server.register_handler("UPDATE", handle_update)  # GB1 SIP UPDATE handler注册
    sip_server.register_response_handler(handle_response)




