import uuid
import re
import secrets
from loguru import logger

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def _uuid7_hex(n: int = 16) -> str:
    return _uuid7_impl().hex[:n]
from app.core.media_nodes import select_best_node
from app.core.media_nodes_db import (
    allocate_rtp_port,
    allocate_rtp_port_with_lease,
    attach_lease_to_session,
    cleanup_invalid_bound_leases,
    cleanup_stale_leases,
    ensure_embedded_media_node,
    get_active_media_node_id,
    get_db_media_node_by_id,
    list_db_media_nodes,
    release_lease,
    select_best_db_node,
)
from app.models.stream_session import StreamSession
from app.models.media_port_lease import MediaPortLease
from app.models.asset_stream_policy import AssetStreamPolicy
from app.models.asset_stream_health import AssetStreamHealth
from app.models.asset import Asset
from app.models.resource import Resource
from app.db.session import AsyncSessionLocal
from app.services.stream_strategy import normalize_stream_mode, recommend_stream_mode
from app.services.audit_center_service import audit_center_service
from sqlalchemy import select, func, delete
from loguru import logger  # FIXED: 统一使用 loguru 替代 logging
import asyncio
import contextlib
import random
import string
import time
import socket
import datetime
from types import SimpleNamespace
from app.services.zlm_rtp_server_service import open_rtp_server, ZlmApiError
from app.services.stream_session_service import finalize_stream_session
from app.services.zlm_stream_control import close_zlm_stream
from app.sip.watchdog import start_watchdog, cancel_watchdog
from app.sip.message import SipMessage
from app.sip.send import send_sip_bytes
from app.core.plugin_manager import plugin_manager
from app.sip.ssrc_manager import ssrc_manager
from app.sip.dialog_manager import dialog_manager, DialogState


def _gb28181_playback_time(epoch: int) -> str:
    if not epoch or epoch <= 0:
        return "19700101T000000Z"
    try:
        dt = datetime.datetime.fromtimestamp(int(epoch), tz=datetime.timezone.utc)
        return dt.strftime("%Y%m%dT%H%M%SZ")
    except Exception:
        return "19700101T000000Z"


def _attach_trace_header(req: SipMessage) -> None:
    call_id = (req.get_header("Call-ID") or "").strip()
    if call_id:
        req.headers["X-Trace-ID"] = call_id
from app.core.config import settings, sip_host_for_contact
from fastapi import HTTPException
from app.sip.state_backend import get_sip_state_backend

_SSRC_GEN_LOCK: asyncio.Lock | None = None
_STREAM_SWITCH_LOCK = asyncio.Lock()
_STREAM_SWITCH_PENDING: dict[str, str] = {}
_STREAM_SWITCH_PENDING_TIMESTAMPS: dict[str, float] = {}
_STREAM_SWITCH_ROLLBACK_DEPTH: dict[str, int] = {}  # FIXED: I10 需定期清理，见 _cleanup_global_dicts
_STREAM_SWITCH_ROLLBACK_DEPTH_MAX = 500
_STREAM_SWITCH_ROLLBACK_DEPTH_TTL = 120  # FIXED: I10 回退深度记录TTL(秒)，超过此时间未更新则清理
_STREAM_SWITCH_ROLLBACK_DEPTH_TIMESTAMPS: dict[str, float] = {}  # FIXED: I10 记录每个call_id的更新时间
_STREAM_SWITCH_PENDING_MAX = 1000
_STREAM_SWITCH_PENDING_TTL = 60
_INVITE_RATE_STATS: dict[str, int] = {
    "allowed": 0,
    "blocked_device": 0,
    "blocked_tenant": 0,
    "backend_redis": 0,
    "backend_local": 0,
    "backend_fallback": 0,
}
# INVITE 200 OK 待办：call_id -> (event, result_dict)
_INVITE_PENDING: dict[str, tuple[asyncio.Event, dict]] = {}  # FIXED: I10 有 max_size 溢出清理 + watchdog 超时清理
_INVITE_PENDING_MAX_SIZE = 10000
_INVITE_PROVISIONAL: dict[str, dict] = {}  # FIXED: I10 有 max_size 5000 + TTL 60s 清理
_CASCADE_CALL_IDS: set[str] = set()  # FIXED: I10 需定期清理，见 _cleanup_global_dicts
_CASCADE_CALL_IDS_MAX = 2000
# FIXED: per-channel INVITE mutex to prevent concurrent INVITE for the same channel
_CHANNEL_INVITE_LOCKS: dict[str, asyncio.Lock] = {}


def _cleanup_global_dicts() -> None:
    """FIXED: I10 定期清理全局字典，防止长期运行内存泄漏。
    清理策略：
    - _INVITE_PENDING: max_size 溢出清理（在 _register_invite_pending 中）+ watchdog 超时清理
    - _INVITE_PROVISIONAL: max_size 5000 + TTL 60s（在 on_invite_provisional 中）
    - _STREAM_SWITCH_PENDING: max_size 1000 + TTL 60s（在 send_stream_switch_reinvite 中）
    - _STREAM_SWITCH_ROLLBACK_DEPTH: max_size 500 + TTL 120s（在此函数中）
    - _CASCADE_CALL_IDS: max_size 2000（在此函数中）
    - _CHANNEL_INVITE_LOCKS: max_size 1000（在 _get_channel_invite_lock 中）
    """
    now = time.time()
    # 清理 _STREAM_SWITCH_ROLLBACK_DEPTH：超过 TTL 的条目
    if _STREAM_SWITCH_ROLLBACK_DEPTH_TIMESTAMPS:
        stale_keys = [k for k, t in _STREAM_SWITCH_ROLLBACK_DEPTH_TIMESTAMPS.items() if now - t > _STREAM_SWITCH_ROLLBACK_DEPTH_TTL]
        for k in stale_keys:
            _STREAM_SWITCH_ROLLBACK_DEPTH.pop(k, None)
            _STREAM_SWITCH_ROLLBACK_DEPTH_TIMESTAMPS.pop(k, None)
    # 溢出清理：超过 max_size 时移除最旧的条目
    if len(_STREAM_SWITCH_ROLLBACK_DEPTH) > _STREAM_SWITCH_ROLLBACK_DEPTH_MAX:
        sorted_keys = sorted(_STREAM_SWITCH_ROLLBACK_DEPTH_TIMESTAMPS.keys(), key=lambda k: _STREAM_SWITCH_ROLLBACK_DEPTH_TIMESTAMPS.get(k, 0))
        excess = len(_STREAM_SWITCH_ROLLBACK_DEPTH) - _STREAM_SWITCH_ROLLBACK_DEPTH_MAX + 100
        for k in sorted_keys[:excess]:
            _STREAM_SWITCH_ROLLBACK_DEPTH.pop(k, None)
            _STREAM_SWITCH_ROLLBACK_DEPTH_TIMESTAMPS.pop(k, None)
    # 清理 _CASCADE_CALL_IDS：超过 max_size 时整体清空（set 无法按时间排序，安全清空）
    if len(_CASCADE_CALL_IDS) > _CASCADE_CALL_IDS_MAX:
        _CASCADE_CALL_IDS.clear()


def _get_channel_invite_lock(channel_id: str) -> asyncio.Lock:
    lock = _CHANNEL_INVITE_LOCKS.get(channel_id)
    if lock is None:
        lock = asyncio.Lock()
        _CHANNEL_INVITE_LOCKS[channel_id] = lock
    # FIXED: 清理过多的通道锁，防止长期运行内存泄漏（保留最近1000个）
    if len(_CHANNEL_INVITE_LOCKS) > 1000:
        _evict_keys = list(_CHANNEL_INVITE_LOCKS.keys())[:len(_CHANNEL_INVITE_LOCKS) - 800]
        for k in _evict_keys:
            if k != channel_id and not _CHANNEL_INVITE_LOCKS[k].locked():
                _CHANNEL_INVITE_LOCKS.pop(k, None)
    return lock


def _get_ssrc_gen_lock() -> asyncio.Lock:
    global _SSRC_GEN_LOCK
    if _SSRC_GEN_LOCK is None:
        _SSRC_GEN_LOCK = asyncio.Lock()
    return _SSRC_GEN_LOCK


def cancel_invite_watchdog(call_id: str) -> None:
    cancel_watchdog(f"invite:{call_id}")


async def _send_cancel(addr: tuple, proto: str, transport, call_id: str, from_tag: str, invite_branch: str, channel_id: str, cseq_num: int = 1) -> None:
    cancel_req = SipMessage()
    cancel_req.method = "CANCEL"
    cancel_req.uri = f"sip:{channel_id}@{addr[0]}:{addr[1]}"
    cancel_req.version = "SIP/2.0"
    cancel_req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={invite_branch}"
    cancel_req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={from_tag}"
    cancel_req.headers["To"] = f"<sip:{channel_id}@{settings.SIP_DOMAIN}>"
    cancel_req.headers["Call-ID"] = call_id
    cancel_req.headers["CSeq"] = f"{cseq_num} CANCEL"
    cancel_req.headers["Max-Forwards"] = "70"
    cancel_req.headers["User-Agent"] = settings.PROJECT_NAME
    try:
        await send_sip_bytes(proto, transport, addr, cancel_req.to_bytes())
        logger.info(f"Sent CANCEL for INVITE call_id={call_id} to {addr}")
    except Exception as e:
        logger.warning(f"Failed to send CANCEL for INVITE call_id={call_id}: {e}")


async def _send_bye_for_timeout(addr: tuple, proto: str, transport, call_id: str, from_tag: str, invite_branch: str, channel_id: str, stream_session) -> None:
    to_tag = getattr(stream_session, "to_tag", "") or ""
    bye_req = SipMessage()
    bye_req.method = "BYE"
    bye_req.uri = f"sip:{channel_id}@{addr[0]}:{addr[1]}"
    bye_req.version = "SIP/2.0"
    branch = f"z9hG4bKbye{secrets.token_hex(4)}"
    bye_req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
    bye_req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={from_tag}"
    to_header = f"<sip:{channel_id}@{settings.SIP_DOMAIN}>"
    if to_tag:
        to_header += f";tag={to_tag}"
    bye_req.headers["To"] = to_header
    bye_req.headers["Call-ID"] = call_id
    bye_cseq = (getattr(stream_session, "cseq", None) or 1) + 1
    bye_req.headers["CSeq"] = f"{bye_cseq} BYE"
    bye_req.headers["Max-Forwards"] = "70"
    bye_req.headers["User-Agent"] = settings.PROJECT_NAME
    try:
        await send_sip_bytes(proto, transport, addr, bye_req.to_bytes())
        logger.info(f"Sent BYE for timed-out INVITE call_id={call_id} (device had already accepted) to {addr}")
    except Exception as e:
        logger.warning(f"Failed to send BYE for timed-out INVITE call_id={call_id}: {e}")


def _register_invite_pending(call_id: str) -> tuple[asyncio.Event, dict]:
    """注册一个 INVITE 等待项，返回 (event, result_dict)。"""
    event = asyncio.Event()
    result: dict = {
        "ok": False,
        "sdp_response": "",
        "to_tag": "",
        "status_code": 0,
        "reason": "",
        "from_tag": "",
        "ssrc": "",
        "stream_id": "",
        "app": "",
        "node_id": "",
        "lease_id": "",
        "original_sdp": "",  # FIXED-P1: C-04 存储原始INVITE的SDP，供3xx重定向使用
        "watchdog_on_timeout": None,  # FIXED-P2: S-07 存储watchdog回调，供3xx重定向后重置watchdog
    }
    if len(_INVITE_PENDING) > _INVITE_PENDING_MAX_SIZE:
        cutoff_count = len(_INVITE_PENDING) - _INVITE_PENDING_MAX_SIZE + 100
        for k in list(_INVITE_PENDING.keys())[:cutoff_count]:
            removed = _INVITE_PENDING.pop(k, None)
            if removed:
                ev, res = removed
                # FIXED-P2: 驱逐时取消看门狗定时器，避免超时回调浪费事件循环资源
                try:
                    cancel_invite_watchdog(k)
                except Exception:
                    pass
                # FIXED: release SSRC/port/ZLM resources when evicting pending INVITE entries
                _evicted_ssrc = res.get("ssrc", "")
                _evicted_stream_id = res.get("stream_id", "")
                _evicted_app = res.get("app", "")
                _evicted_node_id = res.get("node_id", "")
                _evicted_lease_id = res.get("lease_id", "")
                if _evicted_ssrc:
                    try:
                        from app.sip.ssrc_manager import ssrc_manager as _sm
                        asyncio.ensure_future(_sm.release(_evicted_ssrc))
                    except Exception as e:
                        # FIXED: evicted SSRC release should log, not silently pass
                        logger.warning(f"Failed to release evicted SSRC {_evicted_ssrc}: {e}")
                    try:
                        asyncio.ensure_future(unregister_ssrc_waiter(_evicted_ssrc))
                    except Exception as e:
                        # FIXED: evicted SSRC waiter unregister should log, not silently pass
                        logger.warning(f"Failed to unregister evicted SSRC waiter {_evicted_ssrc}: {e}")
                if _evicted_stream_id and _evicted_app:
                    try:
                        from app.services.zlm_stream_control import close_zlm_stream as _close_stream
                        asyncio.ensure_future(_close_stream(app=_evicted_app, stream=_evicted_stream_id, node_id=_evicted_node_id or None))
                    except Exception as e:
                        # FIXED: evicted ZLM stream close should log, not silently pass
                        logger.warning(f"Failed to close evicted ZLM stream {_evicted_stream_id}: {e}")
                if _evicted_lease_id:
                    try:
                        async def _release_evicted_lease(lid=_evicted_lease_id):
                            async with AsyncSessionLocal() as s:
                                await release_lease(s, lid)
                                await s.commit()
                        asyncio.ensure_future(_release_evicted_lease())
                    except Exception as e:
                        # FIXED: evicted lease release should log, not silently pass
                        logger.warning(f"Failed to release evicted lease {_evicted_lease_id}: {e}")
                res["ok"] = False
                res["status_code"] = 0
                res["reason"] = "evicted_from_overflow"
                ev.set()
    _INVITE_PENDING[call_id] = (event, result)
    return event, result


def on_invite_response(call_id: str, status_code: int, reason: str, sdp_body: str, to_tag: str | None = None, record_route: str | None = None) -> None:
    entry = _INVITE_PENDING.pop(call_id, None)
    if not entry:
        return
    event, result = entry
    cancel_invite_watchdog(call_id)
    result["ok"] = (200 <= status_code < 300)
    result["status_code"] = status_code
    result["reason"] = reason
    result["sdp_response"] = sdp_body or ""
    if to_tag:
        result["to_tag"] = to_tag
    if record_route:
        result["record_route"] = record_route
    if 200 <= status_code < 300 and to_tag:
        try:
            from_tag = result.get("from_tag", "")
            if from_tag:
                # FIXED: GB28181协议 — 级联场景传递Record-Route头到dialog
                route_header = result.get("record_route", "")
                route_set = [route_header] if route_header else None
                asyncio.ensure_future(dialog_manager.confirm_dialog(
                    call_id, from_tag, to_tag, route_set=route_set,
                ))
        except Exception as e:
            logger.warning(f"Failed to confirm dialog for INVITE 2xx call_id={call_id}: {e}")  # FIXED: 资源清理失败仅debug日志，提升为warning
    if status_code >= 300:
        try:
            from_tag = result.get("from_tag", "")
            if from_tag:
                asyncio.ensure_future(dialog_manager.terminate_dialog(call_id, from_tag))
        except Exception as e:
            logger.warning(f"Failed to terminate dialog for INVITE error call_id={call_id}: {e}")  # FIXED: 资源清理失败仅debug日志，提升为warning
        ssrc_val = result.get("ssrc", "")
        if ssrc_val:
            try:
                from app.sip.ssrc_manager import ssrc_manager as _sm
                asyncio.ensure_future(_sm.release(ssrc_val))
            except Exception as e:
                logger.warning(f"Failed to release SSRC for INVITE error call_id={call_id}: {e}")  # FIXED: 资源清理失败仅debug日志，提升为warning
            try:
                asyncio.ensure_future(unregister_ssrc_waiter(ssrc_val))
            except Exception as e:
                logger.warning(f"Failed to unregister SSRC waiter for INVITE error call_id={call_id}: {e}")  # FIXED: 资源清理失败仅debug日志，提升为warning
        stream_id_val = result.get("stream_id", "")
        app_val = result.get("app", "")
        node_id_val = result.get("node_id", "")
        if stream_id_val:
            try:
                from app.services.zlm_stream_control import close_zlm_stream as _close_stream
                asyncio.ensure_future(_close_stream(app=app_val, stream=stream_id_val, node_id=node_id_val or None))
            except Exception as e:
                logger.warning(f"Failed to close ZLM stream for INVITE error call_id={call_id}: {e}")  # FIXED: 资源清理失败仅debug日志，提升为warning
        lease_id_val = result.get("lease_id", "")
        if lease_id_val:
            try:
                async def _release_lease():
                    async with AsyncSessionLocal() as s:
                        await release_lease(s, lease_id_val)
                        await s.commit()
                asyncio.ensure_future(_release_lease())
            except Exception as e:
                logger.warning(f"Failed to release lease for INVITE error call_id={call_id}: {e}")
        # FIXED: INVITE非成功响应后清理StreamSession记录，防止DB残留僵尸会话
        session_id_val = result.get("session_id", "")
        if session_id_val:
            try:
                async def _delete_stale_session():
                    async with AsyncSessionLocal() as s:
                        from app.models.stream_session import StreamSession
                        from sqlalchemy import delete as sql_delete
                        await s.execute(sql_delete(StreamSession).where(StreamSession.id == session_id_val))
                        await s.commit()
                asyncio.ensure_future(_delete_stale_session())
            except Exception as e:
                logger.warning(f"Failed to delete stale StreamSession for INVITE error call_id={call_id}: {e}")
    event.set()


def on_invite_provisional(call_id: str, status_code: int, reason: str) -> None:
    _INVITE_PROVISIONAL[call_id] = {
        "status_code": status_code,
        "reason": reason,
        "timestamp": time.time(),
    }
    if len(_INVITE_PROVISIONAL) > 5000:
        cutoff = time.time() - 60
        stale = [k for k, v in _INVITE_PROVISIONAL.items() if v.get("timestamp", 0) < cutoff]
        for k in stale:
            _INVITE_PROVISIONAL.pop(k, None)


async def wait_invite_response(call_id: str, timeout: float = 20.0) -> dict:
    # FIXED: INVITE dual-timeout race - wait for event with slightly longer timeout than watchdog
    # so watchdog fires first and cleans up resources, then this returns the result
    entry = _INVITE_PENDING.get(call_id)
    if not entry:
        return {}
    event, result = entry
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout + 2.0)
        return result
    except asyncio.TimeoutError:
        # FIXED: if timeout reached, try to pop and clean up (watchdog may not have fired yet)
        pending = _INVITE_PENDING.pop(call_id, None)
        if pending:
            _, pending_result = pending
            cancel_invite_watchdog(call_id)
            pending_result["ok"] = False
            pending_result["reason"] = "wait_timeout"
            # FIXED: P2 资源泄漏 — 超时后释放SSRC/lease
            _timeout_ssrc = pending_result.get("ssrc", "")
            if _timeout_ssrc:
                try:
                    from app.sip.ssrc_manager import ssrc_manager as _sm
                    asyncio.ensure_future(_sm.release(_timeout_ssrc))
                except Exception as e:
                    logger.warning(f"Failed to release SSRC for INVITE timeout call_id={call_id}: {e}")
                try:
                    asyncio.ensure_future(unregister_ssrc_waiter(_timeout_ssrc))
                except Exception as e:
                    logger.warning(f"Failed to unregister SSRC waiter for INVITE timeout call_id={call_id}: {e}")
            _timeout_lease_id = pending_result.get("lease_id", "")
            if _timeout_lease_id:
                try:
                    async def _release_timeout_lease():
                        async with AsyncSessionLocal() as s:
                            await release_lease(s, _timeout_lease_id)
                            await s.commit()
                    asyncio.ensure_future(_release_timeout_lease())
                except Exception as e:
                    logger.warning(f"Failed to release lease for INVITE timeout call_id={call_id}: {e}")
            _timeout_stream_id = pending_result.get("stream_id", "")
            _timeout_app = pending_result.get("app", "")
            _timeout_node_id = pending_result.get("node_id", "")
            if _timeout_stream_id:
                try:
                    from app.services.zlm_stream_control import close_zlm_stream as _close_stream
                    asyncio.ensure_future(_close_stream(app=_timeout_app, stream=_timeout_stream_id, node_id=_timeout_node_id or None))
                except Exception as e:
                    logger.warning(f"Failed to close ZLM stream for INVITE timeout call_id={call_id}: {e}")
        return result


async def wait_ssrc_stream_registered(ssrc: str, timeout: float = 8.0) -> bool:
    key = str(ssrc or "").strip()
    if not key:
        return False
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    try:
        backend = get_sip_state_backend()
        result = await backend.wait_ssrc_stream(ssrc, timeout=timeout)
        return result
    except Exception:
        return False
    finally:
        try:
            backend = get_sip_state_backend()
            await backend.unregister_ssrc_waiter(ssrc)
        except Exception as e:
            logger.warning(f"SIP Invite SSRC unregister failed: {e}")  # FIXED: 国际化


async def register_ssrc_waiter(ssrc: str) -> None:
    key = str(ssrc or "").strip()
    if not key:
        return
    try:
        backend = get_sip_state_backend()
        await backend.register_ssrc_waiter(ssrc)
    except Exception as e:
        logger.warning(f"SIP Invite SSRC register failed: {e}")  # FIXED: 国际化


async def unregister_ssrc_waiter(ssrc: str) -> None:
    key = str(ssrc or "").strip()
    if not key:
        return
    try:
        backend = get_sip_state_backend()
        await backend.unregister_ssrc_waiter(ssrc)
    except Exception as e:
        logger.warning(f"SIP Invite operation failed: {e}")


def get_ssrc_waiter_count() -> int:
    """获取当前等待者数量（用于监控）"""
    try:
        backend = get_sip_state_backend()
        if hasattr(backend, '_ssrc_waiters'):
            return len(backend._ssrc_waiters)
    except Exception as e:
        logger.warning(f"SIP Invite operation failed: {e}")
    return -1


async def notify_ssrc_waiters(ssrc: str) -> None:
    """由 hook.py on_stream_changed 调用，唤醒等待该 SSRC 的进程。"""
    key = str(ssrc or "").strip()
    if not key:
        return
    try:
        backend = get_sip_state_backend()
        await backend.notify_ssrc_registered(ssrc)
    except Exception as e:
        logger.warning(f"SIP Invite operation failed: {e}")


def _is_local_host(v: str | None) -> bool:
    s = (v or "").strip().lower()
    return s in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}

def _is_ipv4(v: str | None) -> bool:
    s = (v or "").strip()
    parts = s.split(".")
    if len(parts) != 4:
        return False
    try:
        nums = [int(p) for p in parts]
    except Exception:
        return False
    return all(0 <= n <= 255 for n in nums)

def _resolve_sdp_ip(host: str) -> str:
    h = (host or "").strip()
    if not h:
        return ""
    if _is_ipv4(h):
        return h
    try:
        ip = socket.gethostbyname(h)
        return ip or h
    except Exception:
        return h


def _parse_port_range(raw: str | None) -> tuple[int, int]:
    text = str(raw or "").strip()
    if "-" not in text:
        return 0, 0
    try:
        left, right = text.split("-", 1)
        start = int(left.strip() or 0)
        end = int(right.strip() or 0)
        if start > 0 and end >= start:
            return start, end
    except Exception as e:
        logger.warning(f"SIP Invite operation failed: {e}")
    return 0, 0


def _get_client_tx_manager():
    try:
        from app.sip import transactions as sip_transactions
    except Exception:
        return None
    return getattr(sip_transactions, "client_tx_manager", None) or getattr(sip_transactions, "tx_manager", None)


async def _check_and_consume_invite_rate(tenant_id: str, device_id: str) -> tuple[bool, str]:
    window = float(getattr(settings, "SIP_INVITE_RATE_LIMIT_WINDOW_SECONDS", 5.0) or 5.0)
    per_device = int(getattr(settings, "SIP_INVITE_RATE_LIMIT_PER_DEVICE", 8) or 8)
    per_tenant = int(getattr(settings, "SIP_INVITE_RATE_LIMIT_PER_TENANT", 40) or 40)
    if window <= 0:
        _INVITE_RATE_STATS["allowed"] = int(_INVITE_RATE_STATS.get("allowed", 0) or 0) + 1
        return True, ""
    try:
        backend = get_sip_state_backend()
        allowed, reason = await backend.consume_invite_rate(
            tenant_id, device_id, window=window, per_device=per_device, per_tenant=per_tenant
        )
    except Exception as rate_err:
        # FIXED: 限流后端异常时默认拒绝（fail-closed），防止高并发下限流失效
        logger.error(f"INVITE rate limit backend error, denying request (fail-closed): {rate_err}")
        _INVITE_RATE_STATS.setdefault("backend_error", 0)
        _INVITE_RATE_STATS["backend_error"] = int(_INVITE_RATE_STATS.get("backend_error", 0) or 0) + 1
        return False, "rate_limit_backend_error"
    if allowed:
        _INVITE_RATE_STATS.setdefault("allowed", 0)
        _INVITE_RATE_STATS["allowed"] = int(_INVITE_RATE_STATS.get("allowed", 0) or 0) + 1
    else:
        if "device" in reason:
            _INVITE_RATE_STATS.setdefault("blocked_device", 0)
            _INVITE_RATE_STATS["blocked_device"] = int(_INVITE_RATE_STATS.get("blocked_device", 0) or 0) + 1
        elif "tenant" in reason:
            _INVITE_RATE_STATS.setdefault("blocked_tenant", 0)
            _INVITE_RATE_STATS["blocked_tenant"] = int(_INVITE_RATE_STATS.get("blocked_tenant", 0) or 0) + 1
    return allowed, reason


def get_invite_rate_limit_metrics() -> dict:
    _backend_type = (getattr(settings, "SIP_STATE_BACKEND", "local") or "local").strip().lower()
    return {
        "window_seconds": float(getattr(settings, "SIP_INVITE_RATE_LIMIT_WINDOW_SECONDS", 5.0) or 5.0),
        "per_device_limit": int(getattr(settings, "SIP_INVITE_RATE_LIMIT_PER_DEVICE", 8) or 8),
        "per_tenant_limit": int(getattr(settings, "SIP_INVITE_RATE_LIMIT_PER_TENANT", 40) or 40),
        "backend_type": _backend_type,
        "stats": {
            "allowed": int(_INVITE_RATE_STATS.get("allowed", 0) or 0),
            "blocked_device": int(_INVITE_RATE_STATS.get("blocked_device", 0) or 0),
            "blocked_tenant": int(_INVITE_RATE_STATS.get("blocked_tenant", 0) or 0),
        },
    }

class SipInvite:
    def __init__(self, sip_server):
        self.sip_server = sip_server

    @staticmethod
    def _normalize_media_mode(mode: str | None) -> str:
        return normalize_stream_mode(mode)

    async def _resolve_media_mode(self, asset_id: str) -> str:
        configured_mode = self._normalize_media_mode(settings.MEDIA_SERVER_RTP_STREAM_MODE)
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(AssetStreamPolicy).where(AssetStreamPolicy.asset_id == asset_id))
                policy = result.scalars().first()
                health_result = await session.execute(select(AssetStreamHealth).where(AssetStreamHealth.asset_id == asset_id))
                health = health_result.scalars().first()
        except Exception as e:
            logger.error(f"_resolve_media_mode DB error: {e}")
            return configured_mode
        if not policy or not policy.stream_mode:
            return configured_mode
        policy_mode = normalize_stream_mode(policy.stream_mode, default_mode="GLOBAL", allow_auto=True)
        if policy_mode == "GLOBAL":
            return configured_mode
        if policy_mode in {"UDP", "TCP_PASSIVE", "TCP_ACTIVE"}:
            return policy_mode
        if policy_mode == "AUTO" and health:
            recommended_mode, _, _ = recommend_stream_mode(
                last_mode=health.last_mode,
                current_mode=configured_mode,
                success_total=health.success_total,
                fail_total=health.fail_total,
                consecutive_failures=health.consecutive_failures,
                auto_switch_count=health.auto_switch_count,
            )
            return recommended_mode
        return configured_mode

    async def retry_invite_with_fallback(self, call_id: str) -> bool:
        asset = None
        resource = None
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(StreamSession).where(StreamSession.call_id == call_id))
                failed_session = result.scalars().first()
                if not failed_session or failed_session.app != "live":
                    return False
                current_mode = self._normalize_media_mode((failed_session.protocol or "UDP").replace("-", "_"))
                fallback_mode = "UDP" if current_mode != "UDP" else ""
                if not fallback_mode:
                    return False
                asset_result = await session.execute(select(Asset).where(Asset.id == failed_session.asset_id))
                asset = asset_result.scalars().first()
                resource_result = await session.execute(select(Resource).where(Resource.id == failed_session.resource_id))
                resource = resource_result.scalars().first()
                if not asset or not resource or not asset.ip_addr:
                    return False
                old_lease_id = getattr(failed_session, "media_port_lease_id", None)
                old_node_id = getattr(failed_session, "media_server_id", None)
                old_app = str(getattr(failed_session, "app", "") or "")
                old_stream = str(getattr(failed_session, "stream", "") or "")
                await session.delete(failed_session)
                await session.commit()
                if old_lease_id:
                    with contextlib.suppress(Exception):
                        await release_lease(session, old_lease_id)
                        await session.commit()
                if old_app and old_stream:
                    with contextlib.suppress(Exception):
                        await close_zlm_stream(app=old_app, stream=old_stream, node_id=old_node_id)
        except Exception as e:
            logger.error(f"retry_invite_with_fallback DB error: {e}")
            return False
        transport = self.sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
        if transport is None:
            return False
        await self._send_invite_common(asset, resource, ((asset.ip_addr, asset.port), asset.transport, transport), is_playback=False, media_mode_override=fallback_mode)
        logger.warning(f"Retried INVITE with fallback mode {fallback_mode} for device {asset.gb_id}")
        return True

    async def _cleanup_ssrc_reserves(self, max_age_seconds: int = 300) -> int:
        try:
            async with AsyncSessionLocal() as session:
                cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=max_age_seconds)
                stmt = delete(StreamSession).where(
                    StreamSession.app == "_ssrc_reserve",
                    StreamSession.created_at < cutoff,
                )
                result = await session.execute(stmt)
                await session.commit()
                return result.rowcount
        except Exception:
            return 0

    async def _migrate_ssrc_reserves(self) -> int:
        try:
            async with AsyncSessionLocal() as session:
                stmt = delete(StreamSession).where(
                    StreamSession.app == "_ssrc_reserve",
                )
                result = await session.execute(stmt)
                await session.commit()
                if result.rowcount > 0:
                    logger.info(f"Migrated {result.rowcount} legacy SSRC reserves to in-memory manager")
                return result.rowcount
        except Exception:
            return 0

    async def _generate_ssrc(self, domain_code: str, is_playback: bool = False) -> str:
        return await ssrc_manager.allocate(is_playback=is_playback)

    async def send_invite(
        self,
        asset,
        resource,
        transport_info: tuple,
        stream_type: str = "main",
        *,
        zlm_ssrc_check: bool | None = None,
        media_mode_override: str | None = None,
        reuse_stream_session_id: str | None = None,
    ):
        """
        Send INVITE to device for live streaming.
        stream_type: main | sub，对应国标 Subject 末尾 0=主码流 1=子码流。
        """
        return await self._send_invite_common(
            asset,
            resource,
            transport_info,
            is_playback=False,
            media_mode_override=media_mode_override,
            stream_type=stream_type,
            zlm_ssrc_check=zlm_ssrc_check,
            reuse_stream_session_id=reuse_stream_session_id,
        )

    async def send_playback_invite(
        self,
        asset,
        resource,
        transport_info: tuple,
        start_time: int,
        end_time: int,
        *,
        zlm_ssrc_check: bool | None = None,
        media_mode_override: str | None = None,
        reuse_stream_session_id: str | None = None,
        download_speed: int | None = None,
    ):
        """
        Send INVITE to device for playback
        """
        return await self._send_invite_common(
            asset,
            resource,
            transport_info,
            is_playback=True,
            start_time=start_time,
            end_time=end_time,
            media_mode_override=media_mode_override,
            zlm_ssrc_check=zlm_ssrc_check,
            reuse_stream_session_id=reuse_stream_session_id,
            download_speed=download_speed,
        )

    async def send_stream_switch_reinvite(
        self,
        stream_session: StreamSession,
        target_stream_type: str,
        *,
        is_rollback: bool = False,
    ) -> bool:
        """
        发送 Re-INVITE 进行主辅码流动态切换
        target_stream_type: 'main' 或 'sub'
        """
        if not stream_session.call_id or not stream_session.from_tag or not stream_session.to_tag:
            logger.error(f"[Stream Switch] StreamSession missing dialog info for Re-INVITE: {stream_session.id}")
            return False

        try:
            async with AsyncSessionLocal() as session:
                asset_result = await session.execute(select(Asset).where(Asset.id == stream_session.asset_id))
                asset = asset_result.scalars().first()
                if not asset or not asset.ip_addr:
                    return False
                resource_result = await session.execute(select(Resource).where(Resource.id == stream_session.resource_id))
                resource = resource_result.scalars().first()
                if not resource:
                    return False
                channel_gb_id = resource.gb_id or ""
        except Exception as e:
            logger.error(f"send_stream_switch_reinvite DB query error: {e}")
            return False

        transport = self.sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
        if transport is None:
            return False

        proto = (asset.transport or "UDP").upper()
        branch = f"z9hG4bK{secrets.token_hex(10)}"
        cseq_num = (stream_session.cseq or 1) + 1

        req = SipMessage()
        req.method = "INVITE"
        req.uri = f"sip:{channel_gb_id}@{asset.ip_addr}:{asset.port}"
        req.version = "SIP/2.0"
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={stream_session.from_tag}"
        req.headers["To"] = f"<sip:{channel_gb_id}@{settings.SIP_DOMAIN}>;tag={stream_session.to_tag}"
        req.headers["Call-ID"] = stream_session.call_id
        req.headers["CSeq"] = f"{cseq_num} INVITE"
        req.headers["Contact"] = f"<sip:{settings.SIP_ID}@{sip_host_for_contact()}:{settings.SIP_PORT}>"
        req.headers["Content-Type"] = "application/sdp"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME

        stream_type_code = "1" if target_stream_type == "sub" else "0"
        subject_base = f"{channel_gb_id}:{stream_session.ssrc},{settings.SIP_ID}:{stream_type_code}"

        enable_track_in_subject = bool(getattr(settings, "GB28181_STREAM_SWITCH_USE_TRACK_SUBJECT", False))
        if enable_track_in_subject:
            track_suffix = "track:Video" if target_stream_type == "sub" else "track:All"
            subject_header = f"{subject_base},{track_suffix}"
        else:
            subject_header = subject_base

        req.headers["Subject"] = subject_header
        
        ssrc_str = str(stream_session.ssrc).zfill(10)
        sdp_ip = stream_session.media_ip
        rtp_port = stream_session.media_port
        session_protocol = str(getattr(stream_session, "protocol", "") or "UDP").upper()
        is_tcp = "TCP" in session_protocol
        media_profile = "TCP/RTP/AVP" if is_tcp else "RTP/AVP"
        setup_val = None
        if is_tcp:
            if "ACTIVE" in session_protocol:
                setup_val = "active"
            else:
                setup_val = "passive"
        
        from app.sip.sdp import build_sdp as _build_sdp
        sdp_str = _build_sdp(
            origin_id=channel_gb_id,
            session_name="Play",
            connection_ip=sdp_ip,
            media_type="video",
            media_port=rtp_port,
            media_profile=media_profile,
            direction="recvonly",
            ssrc=ssrc_str,
            f_line="f=v/0",
            extended_rtpmap=False,
            setup=setup_val,
        )
        
        req.body = sdp_str.encode("utf-8")
        req.headers["Content-Length"] = str(len(req.body))
        
        try:
            async with AsyncSessionLocal() as session:
                ss = (await session.execute(
                    select(StreamSession).where(StreamSession.id == stream_session.id)
                )).scalars().first()
                if ss:
                    ss.cseq = cseq_num
                    await session.commit()
                else:
                    return False
        except Exception as e:
            logger.error(f"send_stream_switch_reinvite CSeq update DB error: {e}")
            return False

        tx_manager = _get_client_tx_manager()
        try:
            if tx_manager is None:
                raise RuntimeError("sip_client_tx_manager_unavailable")
            await tx_manager.send_request(req, (asset.ip_addr, asset.port), proto, transport)
        except Exception as e:
            logger.warning(f"[Stream Switch] Error sending Re-INVITE: {e}")
            try:
                await send_sip_bytes(proto, transport, (asset.ip_addr, asset.port), req.to_bytes())
            except Exception as fallback_err:
                logger.warning(f"[Stream Switch] Fallback send_sip_bytes also failed: {fallback_err}")

        # 记录切换中状态（用于超时回退时判断原始码流类型）
        async with _STREAM_SWITCH_LOCK:
            if len(_STREAM_SWITCH_PENDING) > _STREAM_SWITCH_PENDING_MAX:
                oldest_keys = list(_STREAM_SWITCH_PENDING.keys())[:100]
                for k in oldest_keys:
                    _STREAM_SWITCH_PENDING.pop(k, None)
                    _STREAM_SWITCH_PENDING_TIMESTAMPS.pop(k, None)
            _now = time.time()
            _stale_keys = [k for k, t in _STREAM_SWITCH_PENDING_TIMESTAMPS.items() if _now - t > _STREAM_SWITCH_PENDING_TTL]
            for _k in _stale_keys:
                _STREAM_SWITCH_PENDING.pop(_k, None)
                _STREAM_SWITCH_PENDING_TIMESTAMPS.pop(_k, None)
            _STREAM_SWITCH_PENDING[stream_session.call_id or ""] = target_stream_type
            _STREAM_SWITCH_PENDING_TIMESTAMPS[stream_session.call_id or ""] = time.time()
        if not is_rollback:
            _STREAM_SWITCH_ROLLBACK_DEPTH.pop(stream_session.call_id or "", None)

        # 启动超时看门狗：设备 5s 不响应则回退原码流
        _STREAM_SWITCH_TIMEOUT = 5
        from app.sip.watchdog import start_stream_switch_watchdog
        _cid = stream_session.call_id or ""
        start_stream_switch_watchdog(
            call_id=_cid,
            timeout_seconds=_STREAM_SWITCH_TIMEOUT,
            on_timeout=lambda: self._do_stream_switch_rollback(_cid),
        )
        logger.info(
            f"[Stream Switch] Re-INVITE sent for {stream_session.call_id}, "
            f"target={target_stream_type}, timeout={_STREAM_SWITCH_TIMEOUT}s"
        )
        return True


    async def _do_stream_switch_rollback(self, call_id: str, saved_target_type: str | None = None) -> None:
        logger.warning(f"[Stream Switch] Timeout for {call_id}, rolling back to original stream")
        depth = _STREAM_SWITCH_ROLLBACK_DEPTH.get(call_id, 0)
        _STREAM_SWITCH_ROLLBACK_DEPTH_MAX_RETRIES = 3  # FIXED: GB28181协议 — 码流切换回退深度从1增加到3
        if depth >= _STREAM_SWITCH_ROLLBACK_DEPTH_MAX_RETRIES:
            logger.error(f"[Stream Switch] Rollback depth limit reached for {call_id}, stopping to prevent infinite loop")
            async with _STREAM_SWITCH_LOCK:
                _STREAM_SWITCH_PENDING.pop(call_id, None)
                _STREAM_SWITCH_PENDING_TIMESTAMPS.pop(call_id, None)
            _STREAM_SWITCH_ROLLBACK_DEPTH.pop(call_id, None)
            return

        async with _STREAM_SWITCH_LOCK:
            target_type = saved_target_type or _STREAM_SWITCH_PENDING.pop(call_id, None)
            _STREAM_SWITCH_PENDING_TIMESTAMPS.pop(call_id, None)

        try:
            from app.sip.watchdog import cancel_stream_switch_watchdog
            cancel_stream_switch_watchdog(call_id)
        except Exception as e:
            logger.warning(f"SIP Invite operation failed: {e}")

        try:
            async with AsyncSessionLocal() as session:
                stmt = select(StreamSession).where(StreamSession.call_id == call_id)
                result = await session.execute(stmt)
                ss = result.scalars().first()
                if not ss or not ss.asset_id:
                    return

                asset_result = await session.execute(select(Asset).where(Asset.id == ss.asset_id))
                asset = asset_result.scalars().first()
                if not asset or not asset.ip_addr:
                    return

                from app.sip.server import sip_server
                transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
                if not transport:
                    return

                if not target_type:
                    logger.warning(f"[Stream Switch] No target_type found for {call_id}, skipping rollback")
                    return
                original_type = "sub" if target_type == "main" else "main"
                logger.info(f"[Stream Switch] Sending rollback to {original_type} for {call_id}")
                _STREAM_SWITCH_ROLLBACK_DEPTH[call_id] = depth + 1
                _STREAM_SWITCH_ROLLBACK_DEPTH_TIMESTAMPS[call_id] = time.time()  # FIXED: I10 记录更新时间用于TTL清理
                await self.send_stream_switch_reinvite(ss, original_type, is_rollback=True)
        except Exception as e:
            logger.error(f"[Stream Switch] Rollback failed for {call_id}: {e}")
            _STREAM_SWITCH_ROLLBACK_DEPTH.pop(call_id, None)

    async def send_reinvite(
        self,
        stream_session: StreamSession,
        target_node,
    ) -> bool:
        """
        发送 Re-INVITE 进行流媒体节点容灾漂移
        """
        if not stream_session.call_id or not stream_session.from_tag or not stream_session.to_tag:
            logger.error(f"[HA Failover] StreamSession missing dialog info for Re-INVITE: {stream_session.id}")
            return False

        try:
            async with AsyncSessionLocal() as session:
                asset_result = await session.execute(select(Asset).where(Asset.id == stream_session.asset_id))
                asset = asset_result.scalars().first()
                if not asset or not asset.ip_addr:
                    return False

                resource_result = await session.execute(select(Resource).where(Resource.id == stream_session.resource_id))
                resource = resource_result.scalars().first()
                channel_gb_id = resource.gb_id if resource else ""

                rtp_port, lease_id = await allocate_rtp_port_with_lease(session, target_node)
                if not rtp_port:
                    logger.error("[HA Failover] Failed to allocate port on new node")
                    return False

                try:
                    await open_rtp_server(
                        host=target_node.host,
                        http_port=target_node.http_port,
                        secret=target_node.secret,
                        port=rtp_port,
                        tcp_mode=1 if str(getattr(stream_session, 'transport_mode', '') or '').upper().startswith("TCP") else 0,  # FIXED: SDP 传输模式硬编码 UDP
                        app=stream_session.app,
                        stream_id=stream_session.stream,
                        ssrc="0",
                        re_use_port="0",
                        enable_hls=1,
                    )
                except Exception as e:
                    logger.error(f"[HA Failover] Failed to open RTP server on new node: {e}")
                    await release_lease(session, lease_id)
                    return False

                transport = self.sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
                if transport is None:
                    await release_lease(session, lease_id)
                    return False
            
                proto = (asset.transport or "UDP").upper()
                branch = f"z9hG4bK{secrets.token_hex(10)}"
                cseq_num = (stream_session.cseq or 1) + 1
                
                req = SipMessage()
                req.method = "INVITE"
                req.uri = f"sip:{channel_gb_id}@{asset.ip_addr}:{asset.port}"
                req.version = "SIP/2.0"
                req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
                req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={stream_session.from_tag}"
                req.headers["To"] = f"<sip:{channel_gb_id}@{settings.SIP_DOMAIN}>;tag={stream_session.to_tag}"
                req.headers["Call-ID"] = stream_session.call_id
                req.headers["CSeq"] = f"{cseq_num} INVITE"
                req.headers["Contact"] = f"<sip:{settings.SIP_ID}@{sip_host_for_contact()}:{settings.SIP_PORT}>"
                req.headers["Content-Type"] = "application/sdp"
                req.headers["Max-Forwards"] = "70"
                req.headers["User-Agent"] = settings.PROJECT_NAME
                
                ssrc_str = str(stream_session.ssrc).zfill(10)
                sdp_ip = target_node.sdp_ip or target_node.host
                session_protocol = str(getattr(stream_session, "protocol", "") or "UDP").upper()
                is_tcp = "TCP" in session_protocol
                media_profile = "TCP/RTP/AVP" if is_tcp else "RTP/AVP"
                setup_val = None
                if is_tcp:
                    if "ACTIVE" in session_protocol:
                        setup_val = "active"
                    else:
                        setup_val = "passive"
                
                from app.sip.sdp import build_sdp as _build_sdp
                sdp_str = _build_sdp(
                    origin_id=channel_gb_id,
                    session_name="Play",
                    connection_ip=sdp_ip,
                    media_type="video",
                    media_port=rtp_port,
                    media_profile=media_profile,
                    direction="recvonly",
                    ssrc=ssrc_str,
                    f_line="f=v/0",
                    extended_rtpmap=False,
                    setup=setup_val,
                )
                req.body = sdp_str.encode("utf-8")
                req.headers["Content-Length"] = str(len(req.body))
                
                tx_manager = _get_client_tx_manager()
                try:
                    if tx_manager is None:
                        raise RuntimeError("sip_client_tx_manager_unavailable")
                    await tx_manager.send_request(req, (asset.ip_addr, asset.port), proto, transport)
                except Exception as e:
                    logger.warning(f"[HA Failover] Error sending Re-INVITE: {e}")
                    try:
                        await send_sip_bytes(proto, transport, (asset.ip_addr, asset.port), req.to_bytes())
                    except Exception as fallback_err:
                        logger.warning(f"[HA Failover] Fallback send_sip_bytes also failed: {fallback_err}")

                old_lease_id = stream_session.media_port_lease_id
                stream_session.media_server_id = target_node.id
                stream_session.media_ip = sdp_ip
                stream_session.media_port = rtp_port
                stream_session.cseq = cseq_num
                stream_session.media_port_lease_id = lease_id
                session.add(stream_session)
                    
                await session.commit()
                if old_lease_id:
                    with contextlib.suppress(Exception):
                        await release_lease(session, old_lease_id)
                        await session.commit()
                return True
        except Exception as e:
            logger.error(f"send_reinvite DB error: {e}")
            return False

    async def send_bye(self, asset, stream_session, channel_id: str, wait_response: bool = True, timeout_seconds: float = 5.0) -> bool:
        """
        发送 INVITE 会话的 BYE 请求（用于复用会话前先关闭旧会话）。

        Args:
            asset: 设备对象（有 ip_addr, port, transport 属性）
            stream_session: 会话对象（有 call_id, from_tag, to_tag, cseq 属性）
            channel_id: 通道 ID
            wait_response: 是否等待设备响应（默认 True，避免 Session 提前删除）
            timeout_seconds: 等待响应超时时间（秒）
        Returns:
            True: BYE 发送成功（收到响应或超时）
            False: BYE 发送失败
        """
        try:
            addr = (str(getattr(asset, "ip_addr", "") or "").strip(), int(getattr(asset, "port", 0) or 0))
            proto = str(getattr(asset, "transport", "") or "UDP").upper()
            transport = self.sip_server.get_transport(addr[0], addr[1], proto)
        except Exception:
            logger.warning(f"[SipInvite BYE] Failed to get transport for asset")
            return False

        if not transport:
            logger.warning(f"[SipInvite BYE] No transport available for {addr[0]}:{addr[1]}/{proto}")
            return False

        device_id = str(getattr(asset, "gb_id", channel_id) or channel_id)
        call_id = str(getattr(stream_session, "call_id", "") or "").strip()
        if not call_id:
            logger.warning(f"[SipInvite BYE] No call_id for session")
            return False

        from_tag = str(getattr(stream_session, "from_tag", "") or "").strip()
        if not from_tag:
            logger.warning(f"[SipInvite BYE] No from_tag for session {call_id}")
            from_tag = "untagged"

        to_tag = str(getattr(stream_session, "to_tag", "") or "").strip()
        to_header = f"<sip:{channel_id or device_id}@{settings.SIP_DOMAIN}>"
        if to_tag:
            to_header = f"{to_header};tag={to_tag}"

        branch = f"z9hG4bK{secrets.token_hex(10)}"
        cseq = int(getattr(stream_session, "cseq", 1) or 1) + 1

        req = SipMessage()
        req.method = "BYE"
        req.uri = f"sip:{device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={from_tag}"
        req.headers["To"] = to_header
        req.headers["Call-ID"] = call_id
        req.headers["CSeq"] = f"{cseq} BYE"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)

        data = req.to_bytes()

        # 通过事务管理器发送 BYE，支持重传和响应等待
        tx_manager = _get_client_tx_manager()
        if tx_manager and wait_response and proto.upper() == "UDP":
            try:
                event = asyncio.Event()
                result_container = {"received": False, "status_code": 0}

                def _bye_response_handler(msg: SipMessage, addr_t: tuple, proto_t: str, transport_t):
                    if msg.get_header("Call-ID") != call_id:
                        return False
                    # FIXED-P2: W-03 BYE response handler must also check CSeq method is BYE to avoid mismatch
                    cseq_val = str(msg.get_header("CSeq") or "").strip()
                    cseq_method = cseq_val.split(" ", 1)[1].strip().upper() if " " in cseq_val else ""
                    if cseq_method != "BYE":
                        return False
                    if msg.status_code in (200, 481, 486, 603):
                        result_container["received"] = True
                        result_container["status_code"] = msg.status_code
                        event.set()
                        return True
                    return False

                self.sip_server.register_response_handler(_bye_response_handler)
                try:
                    await tx_manager.send_request(req, addr, proto, transport)
                    await asyncio.wait_for(event.wait(), timeout=timeout_seconds)
                    logger.info(f"[SipInvite BYE] Received response {result_container['status_code']} for {device_id} call_id={call_id}")
                except asyncio.TimeoutError:
                    logger.warning(f"[SipInvite BYE] Timeout waiting for BYE response from {device_id} call_id={call_id}")
                    # FIXED: BYE超时返回False而非True，让调用方知道设备未确认BYE
                    return False
                finally:
                    self.sip_server.unregister_response_handler(_bye_response_handler)
            except Exception as e:
                logger.warning(f"[SipInvite BYE] Error sending BYE via tx_manager: {e}, falling back to direct send")
                try:
                    await send_sip_bytes(proto, transport, addr, data)
                except Exception as e2:
                    logger.error(f"[SipInvite BYE] Direct send also failed: {e2}")
                    return False  # FIXED: send_bye 发送失败时应返回 False
        else:
            try:
                await send_sip_bytes(proto, transport, addr, data)
            except Exception as e:
                logger.error(f"[SipInvite BYE] Direct send failed: {e}")
                return False  # FIXED: 非UDP直接发送失败时返回False

        logger.info(f"[SipInvite BYE] Sent BYE to {device_id} call_id={call_id}")
        return True

    async def send_cascade_invite(
        self, asset, resource, transport_info: tuple, sdp_body: str, *, session_name: str = "Play"
    ) -> dict:
        (addr, proto, transport) = transport_info
        device_id = asset.gb_id
        channel_id = resource.gb_id
        call_id = f"cascade_{uuid.uuid4().hex[:16]}"
        from_tag = uuid.uuid4().hex[:8]
        branch = f"z9hG4bK{uuid.uuid4().hex[:12]}"
        _CASCADE_CALL_IDS.add(call_id)

        upstream_sdp = sdp_body
        from app.sip.sdp import parse_sdp as _parse_sdp, pick_media as _pick_media, is_tcp_profile as _is_tcp_profile, build_sdp as _build_sdp
        parsed = _parse_sdp(upstream_sdp, fallback_ip=addr[0])
        media_info = _pick_media(parsed, "video")
        if media_info:
            recv_ip = str((media_info.get("connection_ip") or "").strip()) or addr[0]
            recv_port = media_info.get("port", 0)
            is_tcp = _is_tcp_profile(media_info.get("proto", "RTP/AVP"))
            setup_attr = media_info.get("setup")
        else:
            recv_ip = addr[0]
            recv_port = 0
            is_tcp = False
            setup_attr = None

        req = SipMessage()
        req.method = "INVITE"
        req.uri = f"sip:{channel_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={from_tag}"
        req.headers["To"] = f"<sip:{channel_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = call_id
        req.headers["CSeq"] = "1 INVITE"
        req.headers["Content-Type"] = "application/sdp"
        req.headers["Contact"] = f"<sip:{settings.SIP_ID}@{sip_host_for_contact()}:{settings.SIP_PORT}>"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        req.headers["Max-Forwards"] = "70"

        ssrc = await self._generate_ssrc(getattr(settings, "SIP_DOMAIN", "1"), is_playback=(session_name == "Playback"))
        # FIXED: SSRC allocation may return empty string when exhausted — fail fast instead of sending invalid INVITE
        if not ssrc:
            raise HTTPException(status_code=503, detail="SSRC allocation exhausted, cannot start cascade stream")
        stream_type_code = "0"
        req.headers["Subject"] = f"{channel_id}:{ssrc},{settings.SIP_ID}:{stream_type_code}"
        setup_val = None
        if is_tcp:
            if setup_attr == "active":
                setup_val = "passive"
            elif setup_attr == "passive":
                setup_val = "active"
            else:
                setup_val = "passive"
        req.body = _build_sdp(
            origin_id=channel_id,
            session_name=session_name,
            connection_ip=recv_ip,
            media_type="video",
            media_port=recv_port or 0,
            media_profile="TCP/RTP/AVP" if is_tcp else "RTP/AVP",
            direction="recvonly",
            ssrc=ssrc,
            setup=setup_val,
            extended_rtpmap=False,
        ).encode("utf-8")

        event = asyncio.Event()
        result_container = {"sdp_response": None, "status_code": None, "invite_ok": False, "to_tag": "", "from_tag": from_tag, "call_id": call_id, "ssrc": ssrc, "branch": branch}

        async def _cascade_response_handler(msg: SipMessage, a: tuple, p: str, t):
            if msg.get_header("Call-ID") != call_id:
                return False
            if msg.status_code == 200:
                result_container["sdp_response"] = msg.body if msg.body else ""  # FIXED-P0: C-17 msg.body已是str，无需decode
                result_container["status_code"] = 200
                result_container["invite_ok"] = True
                to_hdr = msg.get_header("To") or ""
                m = re.search(r";\s*tag=([^;>\s]+)", to_hdr, re.IGNORECASE)
                if m:
                    result_container["to_tag"] = m.group(1).strip()
                try:
                    from app.sip.dialog_manager import dialog_manager
                    from_hdr = req.headers.get("From", "")
                    ft_match = re.search(r";\s*tag=([^;>\s]+)", from_hdr, re.IGNORECASE)
                    from_tag_val = ft_match.group(1).strip() if ft_match else ""
                    to_tag_val = result_container.get("to_tag", "")
                    if from_tag_val:
                        asyncio.ensure_future(dialog_manager.create_dialog(call_id, from_tag_val, session_data={"cascade": True}))
                        if to_tag_val:
                            # FIXED: GB28181协议 — 级联场景传递Record-Route头到dialog
                            _cascade_rr = msg.get_header("Record-Route") if hasattr(msg, 'get_header') else None
                            _cascade_route_set = [_cascade_rr] if _cascade_rr else None
                            asyncio.ensure_future(dialog_manager.confirm_dialog(call_id, from_tag_val, to_tag_val, route_set=_cascade_route_set))
                except Exception as dlg_err:
                    logger.debug(f"Cascade INVITE dialog registration failed: {dlg_err}")
                event.set()
                return True
            elif msg.status_code >= 300:
                result_container["status_code"] = msg.status_code
                result_container["invite_ok"] = False
                try:
                    from_tag_val = ""
                    from_hdr = req.headers.get("From", "")
                    ft_match = re.search(r";\s*tag=([^;>\s]+)", from_hdr, re.IGNORECASE)
                    from_tag_val = ft_match.group(1).strip() if ft_match else ""
                    if from_tag_val:
                        asyncio.ensure_future(dialog_manager.terminate_dialog(call_id, from_tag_val))
                except Exception as e:
                    logger.debug(f"Exception: {e}")
                try:
                    ack = SipMessage()
                    ack.method = "ACK"
                    ack.uri = req.uri
                    ack.version = "SIP/2.0"
                    ack.headers["Via"] = req.headers.get("Via", "")
                    ack.headers["From"] = req.headers.get("From", "")
                    ack.headers["To"] = msg.get_header("To") or req.headers.get("To", "")
                    ack.headers["Call-ID"] = call_id
                    cseq_hdr = req.headers.get("CSeq") or "1 INVITE"
                    cseq_num = cseq_hdr.split()[0] if cseq_hdr else "1"
                    ack.headers["CSeq"] = f"{cseq_num} ACK"
                    ack.headers["Max-Forwards"] = "70"
                    await send_sip_bytes(proto, transport, addr, ack.to_bytes())
                    logger.info(f"[Cascade INVITE] Sent ACK for non-2xx {msg.status_code} call_id={call_id}")
                except Exception as ack_err:
                    logger.warning(f"[Cascade INVITE] Failed to send ACK for non-2xx: {ack_err}")
                event.set()
                return True
            return False

        self.sip_server.register_response_handler(_cascade_response_handler)
        try:
            from app.sip import transactions as sip_transactions
            tx_manager = getattr(sip_transactions, "client_tx_manager", None) or getattr(sip_transactions, "tx_manager", None)
            if tx_manager:
                await tx_manager.send_request(req, addr, proto, transport)
            else:
                await send_sip_bytes(proto, transport, addr, req.to_bytes())
            logger.info(f"[Cascade INVITE] Sent to {channel_id}@{addr[0]}:{addr[1]} call_id={call_id}")
            await asyncio.wait_for(event.wait(), timeout=int(getattr(settings, "SIP_INVITE_RESPONSE_TIMEOUT_SECONDS", 20) or 20))
        except asyncio.TimeoutError:
            logger.warning(f"[Cascade INVITE] Timeout for {channel_id} call_id={call_id}")
            await _send_cancel(addr, proto, transport, call_id, from_tag, branch, channel_id)
            try:
                from_hdr = req.headers.get("From", "")
                ft_match = re.search(r";\s*tag=([^;>\s]+)", from_hdr, re.IGNORECASE)
                from_tag_val = ft_match.group(1).strip() if ft_match else ""
                if from_tag_val:
                    asyncio.ensure_future(dialog_manager.terminate_dialog(call_id, from_tag_val))
            except Exception as e:
                logger.debug(f"Exception: {e}")
        except asyncio.CancelledError:
            # FIXED-P0: CancelledError下释放SSRC，防止泄漏
            logger.warning(f"[Cascade INVITE] Cancelled for {channel_id} call_id={call_id}")
            if ssrc:
                try:
                    await ssrc_manager.release(ssrc)
                except Exception:
                    pass
            ssrc = None  # 标记已释放
            raise
        except Exception as e:
            logger.error(f"[Cascade INVITE] Error: {e}")
        finally:
            self.sip_server.unregister_response_handler(_cascade_response_handler)

        if result_container["invite_ok"]:
            ack = SipMessage()
            ack.method = "ACK"
            ack.uri = req.uri
            ack.version = "SIP/2.0"
            ack.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch=z9hG4bK{secrets.token_hex(6)}ack"
            ack.headers["From"] = req.headers["From"]
            ack.headers["To"] = f"<sip:{channel_id}@{settings.SIP_DOMAIN}>;tag={result_container['to_tag']}" if result_container["to_tag"] else req.headers["To"]
            ack.headers["Call-ID"] = call_id
            ack.headers["CSeq"] = "1 ACK"
            ack.headers["Max-Forwards"] = "70"
            ack.headers["User-Agent"] = settings.PROJECT_NAME
            try:
                await send_sip_bytes(proto, transport, addr, ack.to_bytes())
                logger.info(f"[Cascade INVITE] Sent ACK for call_id={call_id}")
            except Exception as e:
                logger.warning(f"[Cascade INVITE] Failed to send ACK: {e}")

        if not result_container["invite_ok"] and ssrc:
            try:
                await ssrc_manager.release(ssrc)
            except Exception as e:
                logger.warning(f"Cascade INVITE SSRC release failed: {e}")

        _CASCADE_CALL_IDS.discard(call_id)
        return result_container

    async def send_talk_invite(
        self, asset, resource, transport_info: tuple, sdp_body: str
    ) -> dict:
        """
        发送双向语音对讲请求 (INVITE s=Talk)
        这里直接使用前端或者 ZLM 回传的 SDP 建立连接
        """
        addr, proto, transport = transport_info
        asset_id = str(getattr(asset, "id", "") or "")
        asset_gb_id = str(getattr(asset, "gb_id", "") or "")
        resource_id = str(getattr(resource, "id", "") or "")
        channel_id = str(getattr(resource, "gb_id", "") or "")
        device_id = asset_gb_id
        
        # SSRC 分配
        ssrc = await self._generate_ssrc(settings.SIP_DOMAIN, is_playback=False)
        # FIXED: SSRC allocation may return empty string when exhausted — fail fast instead of sending invalid INVITE
        if not ssrc:
            raise HTTPException(status_code=503, detail="SSRC allocation exhausted, cannot start talk stream")
        stream_id = f"{channel_id}_talk_{ssrc}"
        app_name = "talk"
        
        subject_header = f"{channel_id}:{ssrc},{settings.SIP_ID}:0"

        call_id = f"{secrets.token_hex(10)}@{sip_host_for_contact()}"
        tag = secrets.token_hex(8)
        branch = f"z9hG4bK{secrets.token_hex(8)}"

        if "y=" not in sdp_body:
            sdp_body += f"y={str(ssrc).zfill(10)}\n"

        req = SipMessage()
        req.method = "INVITE"
        req.uri = f"sip:{channel_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"
        
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={tag}"
        req.headers["To"] = f"<sip:{channel_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = call_id
        req.headers["CSeq"] = f"1 INVITE"
        req.headers["Contact"] = f"<sip:{settings.SIP_ID}@{sip_host_for_contact()}:{settings.SIP_PORT}>"
        req.headers["Subject"] = subject_header
        req.headers["Content-Type"] = "application/sdp"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)

        req.body = sdp_body.encode("utf-8") if isinstance(sdp_body, str) else sdp_body

        try:
            stream_session = StreamSession(
                app=app_name,
                stream=stream_id,
                resource_id=resource_id,
                asset_id=asset_id,
                call_id=call_id,
                from_tag=tag,
                ssrc=ssrc,
                protocol="UDP",
            )
            async with AsyncSessionLocal() as session:
                session.add(stream_session)
                await session.commit()
                stream_session_id = str(stream_session.id)
        except Exception as e:
            logger.error(f"Talk invite session save failed: {e}")
            # FIXED-P0: StreamSession保存失败时释放SSRC，防止泄漏
            if ssrc:
                try:
                    await ssrc_manager.release(ssrc)
                except Exception:
                    pass
            raise HTTPException(status_code=500, detail="Failed to save session")

        tx_manager = _get_client_tx_manager()
        if tx_manager is None:
            # FIXED-P0: tx_manager不可用时释放SSRC，防止泄漏
            if ssrc:
                try:
                    await ssrc_manager.release(ssrc)
                except Exception:
                    pass
            raise RuntimeError("sip_client_tx_manager_unavailable")

        await dialog_manager.create_dialog(
            call_id, tag,
            cseq=1,
            session_data={
                "asset_id": asset_id,
                "resource_id": resource_id,
                "ssrc": ssrc,
                "stream_id": stream_id,
                "app": app_name,
            },
        )

        try:
            resp, meta = await tx_manager.send_and_wait(
                request=req,
                send_once=lambda: send_sip_bytes(proto, transport, addr, req.to_bytes()),
                timeout_seconds=float(getattr(settings, "SIP_INVITE_TIMEOUT_SECONDS", 10.0)),
                retries=0,
            )
            if resp.status_code >= 300:
                try:
                    nack = SipMessage()
                    nack.method = "ACK"
                    nack.uri = req.uri
                    nack.version = "SIP/2.0"
                    nack.headers["Via"] = req.headers.get("Via", "")
                    nack.headers["From"] = req.headers.get("From", "")
                    nack.headers["To"] = resp.get_header("To") or req.headers.get("To", "")
                    nack.headers["Call-ID"] = req.headers.get("Call-ID", "")
                    cseq_hdr = req.headers.get("CSeq") or "1 INVITE"
                    cseq_num = cseq_hdr.split()[0] if cseq_hdr else "1"
                    nack.headers["CSeq"] = f"{cseq_num} ACK"
                    nack.headers["Max-Forwards"] = "70"
                    await send_sip_bytes(proto, transport, addr, nack.to_bytes())
                except Exception as e:
                    logger.debug(f"Exception: {e}")
                raise Exception(f"Talk INVITE rejected with {resp.status_code}")
                
            # Send ACK
            ack = SipMessage()
            ack.method = "ACK"
            ack.uri = req.uri
            ack.version = "SIP/2.0"
            ack.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch=z9hG4bK{secrets.token_hex(6)}ack"
            ack.headers["From"] = req.headers["From"]
            ack.headers["To"] = resp.get_header("To") or req.headers["To"]
            ack.headers["Call-ID"] = req.headers["Call-ID"]
            ack.headers["CSeq"] = "1 ACK"
            ack.headers["Max-Forwards"] = "70"
            ack.headers["User-Agent"] = settings.PROJECT_NAME
            await send_sip_bytes(proto, transport, addr, ack.to_bytes())

            to_tag = ""
            to_h = str(resp.get_header("To") or "")
            if "tag=" in to_h:
                to_tag = to_h.split("tag=")[1].split(";")[0]

            async with AsyncSessionLocal() as session:
                ss = (await session.execute(select(StreamSession).where(StreamSession.id == stream_session_id))).scalars().first()
                if ss:
                    ss.to_tag = to_tag
                    ss.via_branch = branch
                    await session.commit()

            if to_tag:
                try:
                    await dialog_manager.confirm_dialog(call_id, tag, to_tag)
                except Exception as e:
                    logger.debug(f"Exception: {e}")

            return {
                "app": app_name,
                "stream": stream_id,
                "call_id": call_id,
                "sdp_response": resp.body,
                "session_id": stream_session_id
            }
        except Exception as e:
            logger.error(f"Talk INVITE failed: {e}")
            try:
                await ssrc_manager.release(ssrc)
            except Exception as e:
                logger.debug(f"Exception: {e}")
            try:
                async with AsyncSessionLocal() as session:
                    ss = (await session.execute(select(StreamSession).where(StreamSession.id == stream_session_id))).scalars().first()
                    if ss:
                        await session.delete(ss)
                        await session.commit()
            except Exception as cleanup_err:
                logger.error(f"Talk INVITE cleanup DB error: {cleanup_err}")
            # FIXED-P1: W-03 对讲INVITE失败时终止Dialog，防止僵尸Dialog
            try:
                from app.sip.dialog_manager import dialog_manager
                await dialog_manager.terminate_dialog(call_id, tag)
            except Exception as _dlg_err:
                logger.debug(f"Talk INVITE cleanup dialog error: {_dlg_err}")
            raise HTTPException(status_code=503, detail=f"Talk request failed: {e}")  # FIXED: 中文错误消息→英文

    async def _select_media_node(self, session) -> tuple:
        node_id = None
        media_ip = None
        media_port = None
        db_node = None
        selection_reason = "unknown"
        try:
            db_nodes = await list_db_media_nodes(session)
            if (
                bool(getattr(settings, "GB28181_AUTO_ENSURE_EMBEDDED_MEDIA_NODE", True))
                and bool(getattr(settings, "EMBEDDED_ZLM_ENABLED", True))
            ):
                ensured_id = await ensure_embedded_media_node(session)
                if ensured_id:
                    db_nodes = await list_db_media_nodes(session)
            active_id = await get_active_media_node_id(session)
            active_node = await get_db_media_node_by_id(session, active_id) if active_id else None
            best_node = await select_best_db_node(session)
            if active_node and best_node and active_node.id != best_node.id:
                db_node = best_node
                selection_reason = "auto_active_unhealthy"
            elif active_node and best_node and active_node.id == best_node.id:
                db_node = active_node
                selection_reason = "active"
            elif best_node:
                db_node = best_node
                selection_reason = "auto"
            if db_node:
                node_id = db_node.id
                media_ip = db_node.host
                mode_hint = str(getattr(db_node, "rtp_port_mode", "single") or "single").lower()
                if mode_hint != "range":
                    range_start = int(getattr(db_node, "rtp_port_range_start", 0) or 0)
                    range_end = int(getattr(db_node, "rtp_port_range_end", 0) or 0)
                    if range_start > 0 and range_end >= range_start:
                        mode_hint = "range"
                if mode_hint == "single":
                    media_port = db_node.rtp_port
                else:
                    media_port = 0
                if selection_reason != "auto_active_unhealthy":
                    selection_reason = "active" if (active_id and db_node.id == active_id) else "auto"
            elif db_nodes:
                raise RuntimeError("No media node is ready to receive stream.")
        except RuntimeError:
            raise
        except Exception as e:
            logger.error(f"_select_media_node DB error: {e}")
        if not node_id:
            node = await select_best_node()
            if not node:
                raise RuntimeError("No media node available (env fallback returned None)")
            node_id = node["id"]
            media_ip = node["host"]
            media_port = node["rtp_port"]
            selection_reason = "env_fallback"
        return node_id, media_ip, media_port, db_node, selection_reason

    async def _open_zlm_rtp_server(
        self,
        session,
        db_node,
        app_name: str,
        stream_id: str,
        ssrc: str,
        tcp_mode: int,
        ssrc_check_enabled: bool,
        media_port: int,
        media_ip: str,
        node_id: str,
        sdp_ip: str,
        selection_reason: str,
    ) -> tuple:
        lease_id = None
        zlm_res = None
        last_err_msg = ""
        excluded_nodes = []
        base_ssrc_check = ssrc_check_enabled

        max_node_retries = int(getattr(settings, "SIP_INVITE_ZLM_MAX_NODE_RETRIES", 3) or 3)
        max_node_retries = max(1, min(max_node_retries, 10))

        for attempt in range(max_node_retries):
            attempt_lease_id = None
            mode = str(getattr(db_node, "rtp_port_mode", "single") or "single").lower()

            if bool(getattr(settings, "FORCE_SINGLE_PORT_MULTIPLEXING", True)):
                mode = "single"
            else:
                range_start = int(getattr(db_node, "rtp_port_range_start", 0) or 0)
                range_end = int(getattr(db_node, "rtp_port_range_end", 0) or 0)
                if mode != "range" and range_start > 0 and range_end >= range_start:
                    mode = "range"
                if mode != "range":
                    env_start, env_end = _parse_port_range(getattr(settings, "MEDIA_SERVER_RTP_PROXY_PORT_RANGE", ""))
                    if env_start > 0 and env_end >= env_start:
                        mode = "range"
                        range_start, range_end = env_start, env_end
                if mode == "range" and (range_start <= 0 or range_end < range_start):
                    mode = "single"
                if mode == "range":
                    db_node.rtp_port_mode = "range"
                    db_node.rtp_port_range_start = int(range_start)
                    db_node.rtp_port_range_end = int(range_end)

            effective_ssrc_check = base_ssrc_check if mode == "range" else True
            zlm_expect_ssrc = str(int(ssrc)) if effective_ssrc_check else "0"

            if mode == "range":
                max_port_retries = int(getattr(settings, "SIP_INVITE_ZLM_MAX_PORT_RETRIES", 10) or 10)
                max_port_retries = max(1, min(max_port_retries, 100))
                tried_ports: set[int] = set()
                start_from: int | None = None
                for _ in range(max_port_retries):
                    allocated_port, attempt_lease_id = await allocate_rtp_port_with_lease(
                        session, db_node, start_from=start_from, exclude_ports=tried_ports,
                    )
                    if not attempt_lease_id or int(allocated_port or 0) <= 0:
                        last_err_msg = f"node={db_node.id}, error=media_port_exhausted"
                        logger.warning(f"RTP port lease exhausted on node {db_node.id}")
                        zlm_res = None
                        break
                    media_port = int(allocated_port or 0)
                    secret = (db_node.secret or settings.MEDIA_SERVER_SECRET or "")
                    if not secret:
                        last_err_msg = f"node={db_node.id}, reason=empty_secret"
                        logger.error(f"ZLM openRtpServer skipped: secret is empty for node {db_node.id}")
                        zlm_res = None
                        if attempt_lease_id:
                            await release_lease(session, attempt_lease_id)
                        break
                    try:
                        zlm_res = await open_rtp_server(
                            host=str(db_node.host), http_port=int(db_node.http_port or 0),
                            secret=str(secret), port=int(media_port or 0), tcp_mode=int(tcp_mode),
                            app=app_name, stream_id=stream_id, ssrc=zlm_expect_ssrc,
                            re_use_port="0", enable_hls=1,
                        )
                        ssrc_check_enabled = effective_ssrc_check
                        media_port = zlm_res.get("port", media_port)
                        node_id = db_node.id
                        media_ip = db_node.host
                        lease_id = attempt_lease_id
                        if attempt > 0:
                            sdp_ip = media_ip
                            if getattr(db_node, "sdp_ip", None):
                                sdp_ip = _resolve_sdp_ip(str(db_node.sdp_ip).strip()) or sdp_ip
                            selection_reason = "failover_retry"
                        break
                    except Exception as e:
                        last_err_msg = f"node={db_node.id}, error={e}"
                        logger.warning(f"Call ZLM openRtpServer failed on node {db_node.id} (attempt {attempt + 1}/{max_node_retries}): {e}")
                        if attempt_lease_id:
                            await release_lease(session, attempt_lease_id)
                        retry_another_port = False
                        if isinstance(e, ZlmApiError):
                            if getattr(e, "category", "") == "media_port_exhausted" and bool(getattr(e, "retryable", False)):
                                retry_another_port = True
                            elif getattr(e, "category", "") == "media_stream_already_exists":
                                logger.info(f"Stream {stream_id} already exists on node {db_node.id} port {media_port}, reusing it.")
                                zlm_res = {"port": media_port, "code": 0}
                                break
                            else:
                                err_text = str(e)
                                if "Assertion failed" in err_text or "api secret" in err_text.lower():
                                    logger.error(f"ZLM openRtpServer fatal error on node {db_node.id}, skip retries: {e}")
                                    zlm_res = None
                                    if attempt_lease_id:
                                        await release_lease(session, attempt_lease_id)
                                    break
                        if retry_another_port:
                            tried_ports.add(int(media_port))
                            start_from = int(media_port) + 1
                            zlm_res = None
                            if len(tried_ports) > max_port_retries:
                                break
                            continue
                        zlm_res = None
                        break
                if zlm_res:
                    break
            else:
                media_port = int(getattr(db_node, "rtp_port", None) if getattr(db_node, "rtp_port", None) is not None else media_port)  # FIXED: GB28181协议 — 0是合法端口值，不应被falsy跳过
                secret = (db_node.secret or settings.MEDIA_SERVER_SECRET or "")
                if not secret:
                    last_err_msg = f"node={db_node.id}, reason=empty_secret"
                    logger.error(f"ZLM openRtpServer skipped: secret is empty for node {db_node.id}")
                    zlm_res = None
                else:
                    try:
                        zlm_res = await open_rtp_server(
                            host=str(db_node.host), http_port=int(db_node.http_port or 0),
                            secret=str(secret), port=int(media_port or 0), tcp_mode=int(tcp_mode),
                            app=app_name, stream_id=stream_id, ssrc=zlm_expect_ssrc,
                            re_use_port="1" if mode != "range" else "0",
                            enable_hls=1, enable_mp4=0, enable_rtsp=1, enable_rtmp=1, enable_flv=1,
                        )
                        ssrc_check_enabled = effective_ssrc_check
                        media_port = zlm_res.get("port", media_port)
                        node_id = db_node.id
                        media_ip = db_node.host
                        lease_id = attempt_lease_id
                        if attempt > 0:
                            sdp_ip = media_ip
                            if getattr(db_node, "sdp_ip", None):
                                sdp_ip = _resolve_sdp_ip(str(db_node.sdp_ip).strip()) or sdp_ip
                            selection_reason = "failover_retry"
                        break
                    except Exception as e:
                        last_err_msg = f"node={db_node.id}, error={e}"
                        logger.warning(f"Call ZLM openRtpServer failed on node {db_node.id} (attempt {attempt + 1}/{max_node_retries}): {e}")
                        if isinstance(e, ZlmApiError):
                            if getattr(e, "category", "") == "media_stream_already_exists":
                                logger.info(f"Stream {stream_id} already exists on node {db_node.id} port {media_port}, reusing it.")
                                zlm_res = {"port": media_port, "code": 0}
                                node_id = db_node.id
                                media_ip = db_node.host
                                lease_id = attempt_lease_id
                                break
                            elif getattr(e, "category", "") == "media_port_exhausted" and bool(getattr(e, "retryable", False)):
                                logger.debug("Port exhausted but retryable, continuing...")  # FIXED: 端口耗尽且可重试时不应空 pass
                            else:
                                err_text = str(e)
                                if "Assertion failed" in err_text or "api secret" in err_text.lower():
                                    logger.error(f"ZLM openRtpServer fatal error on node {db_node.id}, skip retries: {e}")
                                    zlm_res = None
                                    if attempt_lease_id:
                                        await release_lease(session, attempt_lease_id)
                                    break
                        zlm_res = None
                        if attempt_lease_id:
                            await release_lease(session, attempt_lease_id)
                if zlm_res:
                    break

            if attempt < max_node_retries - 1:
                logger.info(f"Trying to find another available media node for failover...")
                excluded_nodes.append(db_node.id)
                db_node = await select_best_db_node(session, exclude_node_ids=excluded_nodes)
                if not db_node:
                    logger.warning("No other media nodes available for failover.")
                    break

        return zlm_res, media_port, media_ip, node_id, lease_id, ssrc_check_enabled, sdp_ip, selection_reason, last_err_msg

    async def _send_invite_common(
        self,
        asset,
        resource,
        transport_info: tuple,
        is_playback: bool,
        start_time: int = 0,
        end_time: int = 0,
        media_mode_override: str | None = None,
        stream_type: str = "main",
        zlm_ssrc_check: bool | None = None,
        reuse_stream_session_id: str | None = None,
        download_speed: int | None = None,
    ):
        addr, proto, transport = transport_info
        asset_id = str(getattr(asset, "id", "") or "")
        asset_gb_id = str(getattr(asset, "gb_id", "") or "")
        asset_ip_addr = str(getattr(asset, "ip_addr", "") or "")
        asset_port = int(getattr(asset, "port", 0) or 0)
        asset_transport = str(getattr(asset, "transport", "") or "UDP")
        tenant_id = str(getattr(asset, "tenant_id", "") or "default").strip() or "default"
        resource_id = str(getattr(resource, "id", "") or "")
        channel_id = str(getattr(resource, "gb_id", "") or "")
        device_id = asset_gb_id
        # FIXED: per-channel INVITE mutex to prevent concurrent INVITE for the same channel
        _ch_lock = _get_channel_invite_lock(channel_id)
        # FIXED: GB28181协议 — INVITE并发改409为排队等待
        await _ch_lock.acquire()
        try:
            return await self._send_invite_common_inner(
                asset, resource, transport_info, is_playback,
                start_time, end_time, media_mode_override, stream_type,
                zlm_ssrc_check, reuse_stream_session_id, download_speed,
                asset_id, asset_gb_id, tenant_id, channel_id, device_id,
            )
        finally:
            _ch_lock.release()

    async def _send_invite_common_inner(
        self, asset, resource, transport_info, is_playback,
        start_time, end_time, media_mode_override, stream_type,
        zlm_ssrc_check, reuse_stream_session_id, download_speed,
        asset_id, asset_gb_id, tenant_id, channel_id, device_id,
    ):
        allowed, limit_detail = await _check_and_consume_invite_rate(tenant_id=tenant_id, device_id=device_id or asset_id or "unknown")
        if not allowed:
            logger.warning(
                "sip_invite_rate_limited tenant=%s device=%s detail=%s channel=%s",
                tenant_id,
                device_id,
                limit_detail,
                channel_id,
            )
            raise HTTPException(status_code=429, detail="SIP INVITE too frequent, please retry later")  # FIXED: 中文错误消息→英文
        
        ssrc = await self._generate_ssrc(settings.SIP_DOMAIN, is_playback)
        if not ssrc:  # FIXED: SSRC分配失败空值检查，防止后续SDP/ZLM配置出错
            raise HTTPException(status_code=503, detail="SSRC allocation failed, please retry later")
        await register_ssrc_waiter(ssrc)
        ssrc_check_enabled = True if zlm_ssrc_check is None else bool(zlm_ssrc_check)
        
        # FIX: Ensure ZLM stream_id is ALWAYS globally unique per SIP INVITE session 
        # to prevent stream overwriting in port-multiplexing mode.
        # Format: {channel_id}_{ssrc} for BOTH live and playback
        stream_id = f"{channel_id}_{ssrc}"
        
        stream_type_code = "0"
        subject_header = f"{channel_id}:{ssrc},{settings.SIP_ID}:{stream_type_code}"
        normalized_stream_type = "main"
        
        app_name = "playback" if is_playback else "live"
        if download_speed is not None:
            app_name = "download"
        
        if stream_type:
            st_lower = stream_type.lower()
            if st_lower == "sub" or st_lower == "1":
                stream_type_code = "1"
                subject_header = f"{channel_id}:{ssrc},{settings.SIP_ID}:{stream_type_code}"
                normalized_stream_type = "sub"
            elif ":" in stream_type:
                subject_header = f"{channel_id}:{ssrc},{settings.SIP_ID}:{stream_type}"
            else:
                stream_type_code = "0"
                subject_header = f"{channel_id}:{ssrc},{settings.SIP_ID}:{stream_type_code}"
                normalized_stream_type = "main"

        # 缓存：让 ZLM on_stream_changed 回调能通过 ssrc 反推主/辅码流，并补齐 channel/asset 上下文
        try:
            plugin_manager.set_stream_ctx_by_ssrc(
                ssrc,
                stream_type=normalized_stream_type,
                channel_gb_id=channel_id,
                asset_gb_id=asset_gb_id,
            )
        except Exception as e:
            logger.warning(f"SIP Invite operation failed: {e}")

        node_id = None
        media_ip = None
        media_port = None
        lease_id = None
        db_node = None
        selection_reason = "unknown"
        try:
            async with AsyncSessionLocal() as _db:
                node_id, media_ip, media_port, db_node, selection_reason = await self._select_media_node(_db)
        except RuntimeError:
            await unregister_ssrc_waiter(ssrc)
            await ssrc_manager.release(ssrc)
            raise

        media_mode = self._normalize_media_mode(media_mode_override) if media_mode_override else await self._resolve_media_mode(asset_id)
        media_protocol = "UDP"
        media_profile = "RTP/AVP"
        if media_mode == "TCP_PASSIVE":
            media_protocol = "TCP-PASSIVE"
            media_profile = "TCP/RTP/AVP"
        elif media_mode == "TCP_ACTIVE":
            media_protocol = "TCP-ACTIVE"
            media_profile = "TCP/RTP/AVP"
        
        session_name = "Play"
        if is_playback:
            session_name = "Playback" if download_speed is None else "Download"
        
        time_range = "0 0"
        if is_playback:
            fmt = str(getattr(settings, "GB28181_PLAYBACK_SDP_TIME_FORMAT", "iso") or "iso").strip().lower()
            if fmt == "epoch":
                time_range = f"{start_time} {end_time}"
            else:
                st = _gb28181_playback_time(start_time)
                et = _gb28181_playback_time(end_time)
                time_range = f"{st} {et}".strip()

        sdp_ip = media_ip
        try:
            if db_node and getattr(db_node, "sdp_ip", None):
                sdp_ip = _resolve_sdp_ip(str(db_node.sdp_ip).strip()) or sdp_ip
            elif db_node and getattr(db_node, "public_host", None):
                public_hint = str(getattr(db_node, "public_host", "") or "").strip()
                if public_hint and not _is_local_host(public_hint):
                    sdp_ip = _resolve_sdp_ip(public_hint) or sdp_ip
            else:
                public_hint = str(getattr(settings, "STREAM_PUBLIC_HOST", "") or "").strip()
                if public_hint and not _is_local_host(public_hint):
                    sdp_ip = _resolve_sdp_ip(public_hint) or sdp_ip
        except Exception as e:
            logger.warning(f"SIP Invite operation failed: {e}")

        def build_sdp(port: int) -> str:
            from app.sip.sdp import build_sdp as _build_sdp
            f_line_val = f"f=v/2/4/{getattr(settings, 'GB28181_VIDEO_QUALITY', 96)}/1/0a/0/0/0" if not is_playback else ""
            u_line_val = f"u={channel_id}:0" if is_playback else ""
            setup_val = None
            if media_mode == "TCP_PASSIVE":
                setup_val = "passive"
            elif media_mode == "TCP_ACTIVE":
                setup_val = "active"
            # FIXED: GB28181-2022 SDP 添加 a=track 行标识媒体轨道类型
            track_val = None
            gb_version = getattr(settings, "GB28181_VERSION", "2016")
            if gb_version == "2022":
                if stream_type == "sub":
                    track_val = "Video"
                else:
                    track_val = "All"
            return _build_sdp(
                origin_id=channel_id,
                session_name=session_name,
                connection_ip=sdp_ip,
                media_type="video",
                media_port=int(port or 0),
                media_profile=media_profile,
                direction="recvonly",
                ssrc=ssrc,
                setup=setup_val,
                time_range=time_range,
                u_line=u_line_val,
                download_speed=download_speed,
                f_line=f_line_val,
                extended_rtpmap=True,
                track=track_val,
            )
        
        branch = f"z9hG4bK{secrets.token_hex(10)}"
        tag = secrets.token_hex(8)
        call_id = f"{secrets.token_hex(10)}@{sip_host_for_contact()}"
        
        req = SipMessage()
        req.method = "INVITE"
        req.uri = f"sip:{channel_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={tag}"
        req.headers["To"] = f"<sip:{channel_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = call_id
        req.headers["CSeq"] = "1 INVITE"
        req.headers["Contact"] = f"<sip:{settings.SIP_ID}@{sip_host_for_contact()}:{settings.SIP_PORT}>"
        req.headers["Content-Type"] = "application/sdp"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        req.headers["Subject"] = subject_header if subject_header else f"{channel_id}:{ssrc},{settings.SIP_ID}:{stream_type_code}"
        
        async with AsyncSessionLocal() as session:
            # Add robust failover for ZLM openRtpServer
            reuse_session_snapshot = None
            if reuse_stream_session_id:
                reuse_session = (
                    await session.execute(select(StreamSession).where(StreamSession.id == reuse_stream_session_id))
                ).scalars().first()
                if reuse_session:
                    reuse_session_snapshot = {
                        "id": str(getattr(reuse_session, "id", "") or ""),
                        "call_id": str(getattr(reuse_session, "call_id", "") or "").strip(),
                        "to_tag": str(getattr(reuse_session, "to_tag", "") or "").strip(),
                        "from_tag": str(getattr(reuse_session, "from_tag", "") or "").strip(),
                        "cseq": int(getattr(reuse_session, "cseq", 1) or 1),
                        "app": str(getattr(reuse_session, "app", "") or ""),
                        "stream": str(getattr(reuse_session, "stream", "") or ""),
                        "media_server_id": str(getattr(reuse_session, "media_server_id", "") or ""),
                        "media_port_lease_id": str(getattr(reuse_session, "media_port_lease_id", "") or ""),
                    }
                    old_call_id = str((reuse_session_snapshot or {}).get("call_id") or "").strip()
                    if old_call_id:
                        with contextlib.suppress(Exception):
                            cancel_watchdog(f"invite:{old_call_id}")
                    if str((reuse_session_snapshot or {}).get("to_tag") or "").strip():
                        with contextlib.suppress(Exception):
                            await self.send_bye(
                                SimpleNamespace(ip_addr=asset_ip_addr, port=asset_port, transport=asset_transport),
                                SimpleNamespace(
                                    call_id=str((reuse_session_snapshot or {}).get("call_id") or ""),
                                    from_tag=str((reuse_session_snapshot or {}).get("from_tag") or ""),
                                    to_tag=str((reuse_session_snapshot or {}).get("to_tag") or ""),
                                    cseq=int((reuse_session_snapshot or {}).get("cseq") or 1),
                                ),
                                channel_id,
                            )
                    with contextlib.suppress(Exception):
                        await close_zlm_stream(
                            app=str((reuse_session_snapshot or {}).get("app") or ""),
                            stream=str((reuse_session_snapshot or {}).get("stream") or ""),
                            node_id=str((reuse_session_snapshot or {}).get("media_server_id") or "") or None,
                        )
                    old_lease_id = str((reuse_session_snapshot or {}).get("media_port_lease_id") or "").strip()
                    if old_lease_id:
                        with contextlib.suppress(Exception):
                            await release_lease(session, old_lease_id)
                    reuse_session = None
            db_node = await get_db_media_node_by_id(session, node_id)
            if db_node:
                with contextlib.suppress(Exception):
                    for _ in range(3):
                        cleaned_orphan = int(await cleanup_stale_leases(session, max_age_seconds=300, limit=5000) or 0)
                        cleaned_invalid = int(await cleanup_invalid_bound_leases(session, limit=5000) or 0)
                        if (cleaned_orphan + cleaned_invalid) <= 0:
                            break
                tcp_mode = 0
                if media_protocol == "TCP-PASSIVE":
                    tcp_mode = 1
                elif media_protocol == "TCP-ACTIVE":
                    tcp_mode = 2

                base_ssrc_check = True if zlm_ssrc_check is None else bool(zlm_ssrc_check)
                zlm_res, media_port, media_ip, node_id, lease_id, ssrc_check_enabled, sdp_ip, selection_reason, last_err_msg = await self._open_zlm_rtp_server(
                    session=session,
                    db_node=db_node,
                    app_name=app_name,
                    stream_id=stream_id,
                    ssrc=ssrc,
                    tcp_mode=tcp_mode,
                    ssrc_check_enabled=base_ssrc_check,
                    media_port=media_port,
                    media_ip=media_ip,
                    node_id=node_id,
                    sdp_ip=sdp_ip,
                    selection_reason=selection_reason,
                )

                if not zlm_res:
                    await unregister_ssrc_waiter(ssrc)
                    await ssrc_manager.release(ssrc)
                    raise RuntimeError(
                        f"Call ZLM openRtpServer failed. No media node is ready to receive stream. last_error=({last_err_msg})"
                    )

            try:
                sdp = build_sdp(int(media_port or 0))
                req.body = sdp.encode("utf-8") if isinstance(sdp, str) else sdp

                session_app = app_name
                session_stream = stream_id
                if not session_app:
                    session_app = app_name
                if not session_stream:
                    session_stream = stream_id
                if not session_stream:
                    session_stream = call_id
                if not resource_id or not asset_id:
                    await unregister_ssrc_waiter(ssrc)
                    await ssrc_manager.release(ssrc)  # FIXED: P2 SSRC泄漏 — 异常路径释放SSRC
                    raise RuntimeError("invalid_stream_session_refs")
                stream_session = None
                if reuse_stream_session_id:
                    stream_session = (
                        await session.execute(select(StreamSession).where(StreamSession.id == reuse_stream_session_id))
                    ).scalars().first()
                if not stream_session:
                    stream_session = StreamSession(
                        app=session_app,
                        stream=session_stream,
                        resource_id=resource_id,
                        asset_id=asset_id,
                        call_id=call_id,
                        from_tag=tag,
                        via_branch=branch,
                        cseq=1,
                        ssrc=ssrc,
                        media_server_id=node_id,
                        media_ip=media_ip,
                        media_port=media_port,
                        media_port_lease_id=lease_id,
                        start_time=datetime.datetime.now(),
                        protocol=media_protocol,
                    )
                    session.add(stream_session)
                    await session.flush()
                else:
                    stream_session.app = session_app
                    stream_session.stream = session_stream
                    stream_session.resource_id = resource_id
                    stream_session.asset_id = asset_id
                    stream_session.call_id = call_id
                    stream_session.from_tag = tag
                    stream_session.via_branch = branch
                    stream_session.cseq = 1
                    stream_session.ssrc = ssrc
                    stream_session.protocol = media_protocol
                    stream_session.media_server_id = node_id
                    stream_session.media_ip = media_ip
                    stream_session.media_port = media_port
                    stream_session.media_port_lease_id = lease_id
                    stream_session.start_time = datetime.datetime.now()
                if lease_id:
                    bound_lease_id = await attach_lease_to_session(
                        session,
                        node_id=node_id,
                        port=int(media_port or 0),
                        stream_session_id=stream_session.id,
                        lease_id_hint=lease_id,
                    )
                    stream_session.media_port_lease_id = bound_lease_id or lease_id
                stream_session_id_value = str(getattr(stream_session, "id", "") or "")
                await session.commit()
            except Exception as e:
                await unregister_ssrc_waiter(ssrc)
                with contextlib.suppress(Exception):
                    await ssrc_manager.release(ssrc)
                with contextlib.suppress(Exception):
                    await session.rollback()
                if lease_id:
                    with contextlib.suppress(Exception):
                        async with AsyncSessionLocal() as cleanup_session:
                            await release_lease(cleanup_session, lease_id)
                            await cleanup_session.commit()
                with contextlib.suppress(Exception):
                    await close_zlm_stream(app=app_name, stream=stream_id, node_id=node_id)
                raise
            
            try:
                await audit_center_service.log(
                    db=session,
                    module="media_nodes",
                    action="select_node_for_invite",
                    operator="system",
                    result="success",
                    summary=(
                        f"reason={selection_reason}; node_id={node_id}; "
                        f"media_ip={media_ip}; media_port={media_port}; lease_id={lease_id or ''}; "
                        f"sdp_ip={sdp_ip}; is_playback={bool(is_playback)}; stream_type={stream_type or 'main'}"
                    ),
                )
            except Exception as e:
                logger.warning(f"SIP Invite operation failed: {e}")

        data = req.to_bytes()
        
        await dialog_manager.create_dialog(
            call_id, tag,
            cseq=1,
            session_data={
                "asset_id": asset_id,
                "resource_id": resource_id,
                "ssrc": ssrc,
                "stream_id": stream_id,
                "app": app_name,
            },
        )
        await ssrc_manager.bind_stream(ssrc, stream_id)

        # Use transaction manager to handle UDP retransmissions, fallback to direct send
        tx_manager = _get_client_tx_manager()
        event, result = _register_invite_pending(call_id)
        result["from_tag"] = tag
        result["ssrc"] = ssrc
        result["stream_id"] = stream_id
        result["app"] = app_name
        result["node_id"] = node_id
        result["lease_id"] = lease_id
        result["original_sdp"] = sdp if isinstance(sdp, str) else (sdp.decode("utf-8") if isinstance(sdp, bytes) else "")  # FIXED-P1: C-04 存储原始SDP
        try:
            if tx_manager is None:
                raise RuntimeError("sip_client_tx_manager_unavailable")
            await tx_manager.send_request(req, addr, proto, transport)
        except Exception as e:
            logger.warning(f"Error sending INVITE via tx_manager: {e}, falling back to direct send")
            try:
                await send_sip_bytes(proto, transport, addr, data)
            except Exception as fallback_err:
                logger.warning(f"Fallback send_sip_bytes also failed: {fallback_err}")
            
        timeout = int(getattr(settings, "SIP_INVITE_RESPONSE_TIMEOUT_SECONDS", 20) or 20)
        async def _on_timeout():
            # FIXED: INVITE超时处理幂等性保护 — 防止watchdog与wait_invite_response双重超时竞态
            try:
                dialog_lock = await dialog_manager.acquire_dialog_lock(call_id, tag)
                if dialog_lock:
                    await dialog_lock.acquire()
                try:
                    if call_id not in _INVITE_PENDING:
                        logger.info(f"[InviteTimeout] {call_id} already responded, skipping timeout handler")
                        return
                    # FIXED: 原子性移除pending条目，防止wait_invite_response与on_timeout竞态
                    _pending_entry = _INVITE_PENDING.pop(call_id, None)
                    if not _pending_entry:
                        logger.info(f"[InviteTimeout] {call_id} pending entry already consumed, skipping")
                        return
                    # FIXED: GB28181协议 — INVITE超时直接清理StreamSession，通知wait_invite_response返回
                    _pending_event, _pending_result = _pending_entry
                    _pending_result["ok"] = False
                    _pending_result["status_code"] = 408
                    _pending_result["reason"] = "Request Timeout"
                    _pending_event.set()
                    await unregister_ssrc_waiter(ssrc)
                    await ssrc_manager.release(ssrc)
                    await dialog_manager.terminate_dialog(call_id, tag)
                    async with AsyncSessionLocal() as session:
                        stream_session = (
                            await session.execute(select(StreamSession).where(StreamSession.call_id == call_id))
                        ).scalars().first()
                        if not stream_session:
                            return
                        _app = str(getattr(stream_session, "app", "") or app_name)
                        _stream = str(getattr(stream_session, "stream", "") or stream_id)
                        _node_id = str(getattr(stream_session, "media_server_id", "") or "")
                        _lease_id = str(getattr(stream_session, "media_port_lease_id", "") or "")
                        if getattr(stream_session, "to_tag", None):
                            logger.info(f"[InviteTimeout] Session {call_id} already has to_tag, device accepted INVITE, sending BYE instead of CANCEL")
                            await _send_bye_for_timeout(addr, proto, transport, call_id, tag, branch, channel_id, stream_session)
                        else:
                            await _send_cancel(addr, proto, transport, call_id, tag, branch, channel_id)
                        with contextlib.suppress(Exception):
                            await close_zlm_stream(app=_app, stream=_stream, node_id=_node_id or None)
                        if _lease_id:
                            with contextlib.suppress(Exception):
                                await release_lease(session, _lease_id)
                        await finalize_stream_session(session, stream_session, reason="invite_timeout")
                        await session.commit()
                    # FIXED: GB28181协议 — 已通过_pending_event.set()通知wait_invite_response，无需再调用on_invite_response
                    try:
                        from app.sip.transactions import tx_key_from_request as _tx_key_fn
                        _client_txm = _get_client_tx_manager()
                        if _client_txm:
                            _tx_key = _tx_key_fn(req)
                            async with _client_txm._lock:
                                _old_tx = _client_txm._tx.pop(_tx_key, None)
                                if _old_tx:
                                    if _old_tx.timers:
                                        for _h in _old_tx.timers:
                                            _h.cancel()
                                    if not _old_tx.future.done():
                                        _old_tx.future.cancel()
                    except Exception as e:
                        logger.debug(f"Exception: {e}")
                finally:
                    if dialog_lock:
                        dialog_lock.release()
            except Exception as e:
                logger.error(f"Error in invite timeout handler for {call_id}: {e}")
        # FIXED-P2: S-07 存储watchdog回调到pending条目，供3xx重定向后重置watchdog
        _pending_for_wd = _INVITE_PENDING.get(call_id)
        if _pending_for_wd:
            _pending_for_wd[1]["watchdog_on_timeout"] = _on_timeout
        start_watchdog(key=f"invite:{call_id}", timeout_seconds=timeout, on_timeout=_on_timeout)

        logger.info(f"Sent {session_name} INVITE to {channel_id} (SSRC: {ssrc}, zlm_ssrc_check={bool(ssrc_check_enabled)})")

        # 等待 INVITE 200 OK，再返回给调用方（前端需要确认点播结果）
        resp_result = await wait_invite_response(call_id, timeout=float(timeout))

        return {
            "app": app_name,
            "stream": stream_id,
            "ssrc": ssrc,
            "zlm_ssrc_check": bool(ssrc_check_enabled),
            "node_id": node_id,
            "call_id": call_id,
            "stream_session_id": stream_session_id_value,
            "sdp_ip": sdp_ip,
            "media_port": media_port,
            "media_protocol": media_protocol,
            "selection_reason": selection_reason,
            "invite_ok": resp_result.get("ok", False),
            "invite_status_code": resp_result.get("status_code", 0),
            "invite_sdp": resp_result.get("sdp_response", ""),
            "invite_to_tag": resp_result.get("to_tag", ""),
        }

# Singleton
sip_invite = None