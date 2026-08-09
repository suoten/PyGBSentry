"""stream 子模块共享的工具函数、全局变量和常量。"""

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db, AsyncSessionLocal
from app.core.config import settings
from app.core.media_nodes import get_node_by_id, get_media_nodes, get_all_media_from_nodes
from app.core.media_nodes_db import get_all_media_from_nodes as get_all_media_from_db_nodes, get_db_media_node_by_id, list_db_media_nodes, release_lease
from app.models.asset import Asset
from app.models.resource import Resource
from app.models.stream_session import StreamSession
from app.models.asset_stream_health import AssetStreamHealth
from app.models.asset_stream_policy import AssetStreamPolicy
from app.models.platform import ParentPlatform
from app.models.user import User
from app.models.system_setting import SystemSetting
from app.api import deps
import app.sip.invite as sip_invite_module
from app.sip.server import sip_server
from app.core.plugin_manager import plugin_manager
from app.services.audit_center_service import audit_center_service
from app.services.auth_audit import safe_auth_audit
from app.services.stream_session_service import close_stream, release_stream_session, finalize_stream_session
from app.services.zlm_rtp_server_service import ZlmApiError
from app.services.zlm_stream_control import close_zlm_stream, _get_zlm_client
import contextlib
import copy
from loguru import logger
from datetime import datetime, timezone
import hmac
import hashlib
import base64
import time
import asyncio
import json
from typing import Any, Optional
from types import SimpleNamespace

# Bootstrap 运行时配置的 TTL 缓存，避免每次播放都查数据库
_BOOTSTRAP_RUNTIME_CONFIG_CACHE_TTL_SECONDS = 60
_bootstrap_runtime_config_cache: dict[str, Any] = {}
_bootstrap_runtime_config_cache_timestamp: float = 0.0
_bootstrap_runtime_config_cache_lock = asyncio.Lock()

# 点播幂等性保护：防止同一通道并发多次 INVITE
# 使用 dict 记录 {key: timestamp}，5秒后自动过期，无需手动清理
_PLAY_INFLIGHT: dict[str, float] = {}
_PLAY_INFLIGHT_LOCK = asyncio.Lock()


class _PlayIdempotencyGuard:

    _TTL = 5.0

    def __init__(self, device_id: str, channel_id: str):
        self.key = f"{device_id}:{channel_id}"
        self._acquired = False
        self._registered_ts: float = 0.0

    async def __aenter__(self):
        ok = await self.acquire()
        if not ok:
            raise HTTPException(status_code=409, detail="VOD request for this channel is in progress, please retry later")
        self._acquired = True
        return self

    async def __aexit__(self, *args):
        if self._acquired:
            await self.release()
        return False

    async def acquire(self) -> bool:
        import time as _time
        async with _PLAY_INFLIGHT_LOCK:
            ts = _PLAY_INFLIGHT.get(self.key)
            if ts is not None and (_time.time() - ts) < self._TTL:
                return False
            now = _time.time()
            _PLAY_INFLIGHT[self.key] = now
            self._registered_ts = now
            return True

    async def release(self):
        import time as _time
        async with _PLAY_INFLIGHT_LOCK:
            current_ts = _PLAY_INFLIGHT.get(self.key)
            if current_ts is not None and abs(current_ts - self._registered_ts) < 0.001:
                _PLAY_INFLIGHT.pop(self.key, None)


def _stream_audit_tid(user: User) -> str:
    return (user.tenant_id or "default").strip() or "default"


async def _stream_audit(
    db: AsyncSession,
    user: User,
    *,
    action: str,
    result: str,
    status_code: int,
    detail: str,
    extra_summary: str = "",
) -> None:
    await safe_auth_audit(
        db,
        module="stream",
        action=action,
        source="stream_console",
        operator=user.username or "unknown",
        result=result,
        tenant_id=_stream_audit_tid(user),
        status_code=status_code,
        detail=detail,
        extra_summary=extra_summary,
    )


async def _get_asset_resource(
    db: AsyncSession,
    device_id: str,
    channel_id: str,
    current_user: User,
) -> tuple[Asset | None, Resource | None]:
    device_id = (device_id or "").strip()
    channel_id = (channel_id or "").strip()

    stmt = select(Asset).where(Asset.gb_id == device_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
    asset = (await db.execute(stmt)).scalars().first()

    stmt = select(Resource).where(Resource.gb_id == channel_id)
    if not current_user.is_superuser:
        stmt = stmt.join(Asset, Asset.id == Resource.asset_id).where(
            Asset.tenant_id == (current_user.tenant_id or "default")
        )
    resource = (await db.execute(stmt)).scalars().first()
    return asset, resource


_INVITE_ENDPOINT_HINTS: dict[str, dict[str, Any]] = {}
_PLAY_STATUS_RECENT_FAILURE: dict[str, dict[str, Any]] = {}
_PLAY_SESSION_TRACE: dict[str, dict[str, Any]] = {}
_PLAY_DIAGNOSTIC_BUILD = "20260329-stream-fix-6"

# 诊断数据持久化到日志的阈值与锁
_PLAY_TRACE_PERSIST_LOCK = asyncio.Lock()
_PLAY_TRACE_PERSIST_INTERVAL = 300  # 每 5 分钟最多写一次日志
_LAST_TRACE_PERSIST_TIME: float = 0.0
_BOOTSTRAP_TEMPLATE_SETTING_KEY = "gb28181.bootstrap_templates"
_BOOTSTRAP_LEARNING_WEIGHT_SETTING_KEY = "gb28181.bootstrap_learning_weights"
_BOOTSTRAP_LEARNING_STATE_SETTING_KEY = "gb28181.bootstrap_learning_state"
_PLAY_TRACE_MAX_EVENTS = 80
_PLAY_TRACE_KEEP_SESSIONS = 800
_DEFAULT_BOOTSTRAP_TEMPLATES: list[dict[str, Any]] = [
    {"reason": "wireless_profile", "mode": "TCP_PASSIVE", "keywords": ["4g", "5g", "lte", "wifi", "wireless", "无线"]},
    {"reason": "vendor_hikvision", "mode": "TCP_PASSIVE", "keywords": ["hikvision", "海康"]},
    {"reason": "vendor_dahua", "mode": "TCP_PASSIVE", "keywords": ["dahua", "大华"]},
    {"reason": "vendor_uniview", "mode": "TCP_PASSIVE", "keywords": ["uniview", "宇视"]},
    {"reason": "vendor_tiandy", "mode": "TCP_PASSIVE", "keywords": ["tiandy", "天地伟业"]},
]
_DEFAULT_BOOTSTRAP_WEIGHTS = {"policy": 2.2, "health": 1.0, "template": 0.9, "learning": 1.3}


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _clamp_float(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _normalize_mode_for_candidate(mode: str | None) -> str | None:
    text = str(mode or "").strip().upper().replace("-", "_")
    if text in {"", "AUTO", "UDP", "GLOBAL"}:
        return None
    if text in {"TCP_PASSIVE", "TCP_ACTIVE"}:
        return text
    return None


def _mode_score_key(mode: str | None) -> str:
    normalized = _normalize_mode_for_candidate(mode)
    if normalized == "TCP_PASSIVE":
        return "TCP_PASSIVE"
    if normalized == "TCP_ACTIVE":
        return "TCP_ACTIVE"
    return "UDP"


def _mode_from_score_key(key: str | None) -> str | None:
    text = str(key or "").strip().upper()
    if text == "TCP_PASSIVE":
        return "TCP_PASSIVE"
    if text == "TCP_ACTIVE":
        return "TCP_ACTIVE"
    if text == "UDP":
        return "UDP"
    return None


def _parse_bootstrap_templates(raw_value: str | None) -> list[dict[str, Any]]:
    raw = str(raw_value or "").strip()
    if not raw:
        return [dict(item) for item in _DEFAULT_BOOTSTRAP_TEMPLATES]
    try:
        parsed = json.loads(raw)
    except Exception:
        return [dict(item) for item in _DEFAULT_BOOTSTRAP_TEMPLATES]
    if not isinstance(parsed, list):
        return [dict(item) for item in _DEFAULT_BOOTSTRAP_TEMPLATES]
    templates: list[dict[str, Any]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        reason = str(item.get("reason") or "").strip()
        mode = str(item.get("mode") or "").strip().upper().replace("-", "_")
        keywords = item.get("keywords")
        if not reason or mode not in {"AUTO", "TCP_PASSIVE", "TCP_ACTIVE"} or not isinstance(keywords, list):
            continue
        kws = [str(seg or "").strip().lower() for seg in keywords if str(seg or "").strip()]
        if not kws:
            continue
        templates.append({"reason": reason[:64], "mode": mode, "keywords": kws[:24]})
    if not templates:
        return [dict(item) for item in _DEFAULT_BOOTSTRAP_TEMPLATES]
    return templates[:32]


def _parse_bootstrap_weights(raw_value: str | None) -> dict[str, float]:
    raw = str(raw_value or "").strip()
    if not raw:
        return dict(_DEFAULT_BOOTSTRAP_WEIGHTS)
    try:
        parsed = json.loads(raw)
    except Exception:
        return dict(_DEFAULT_BOOTSTRAP_WEIGHTS)
    if not isinstance(parsed, dict):
        return dict(_DEFAULT_BOOTSTRAP_WEIGHTS)
    merged = dict(_DEFAULT_BOOTSTRAP_WEIGHTS)
    for key in ("policy", "health", "template", "learning"):
        merged[key] = _clamp_float(_safe_float(parsed.get(key), merged[key]), 0.0, 5.0)
    return merged


def _parse_bootstrap_learning_state(raw_value: str | None) -> dict[str, Any]:
    raw = str(raw_value or "").strip()
    if not raw:
        return {"profiles": {}}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {"profiles": {}}
    if not isinstance(parsed, dict):
        return {"profiles": {}}
    profiles = parsed.get("profiles")
    if not isinstance(profiles, dict):
        return {"profiles": {}}
    clean_profiles: dict[str, Any] = {}
    for key, item in profiles.items():
        profile_key = str(key or "").strip()[:80]
        if not profile_key or not isinstance(item, dict):
            continue
        clean_item: dict[str, Any] = {"updated_at": int(_safe_float(item.get("updated_at"), 0.0))}
        for mode_key in ("UDP", "TCP_PASSIVE", "TCP_ACTIVE"):
            mv = item.get(mode_key)
            if not isinstance(mv, dict):
                continue
            s = max(0, int(_safe_float(mv.get("s"), 0.0)))
            f = max(0, int(_safe_float(mv.get("f"), 0.0)))
            clean_item[mode_key] = {"s": min(9999, s), "f": min(9999, f)}  # 9999为SIP SN上限，与device_control保持一致
        clean_profiles[profile_key] = clean_item
        if len(clean_profiles) >= 24:
            break
    return {"profiles": clean_profiles}


async def _set_system_setting(db: AsyncSession, key: str, value: str) -> None:
    item = (
        await db.execute(select(SystemSetting).where(SystemSetting.setting_key == key))
    ).scalars().first()
    if item:
        item.setting_value = value
    else:
        db.add(SystemSetting(setting_key=key, setting_value=value))


async def _load_bootstrap_runtime_config(db: AsyncSession) -> dict[str, Any]:
    global _bootstrap_runtime_config_cache, _bootstrap_runtime_config_cache_timestamp
    current_time = time.time()
    if (
        _bootstrap_runtime_config_cache
        and current_time - _bootstrap_runtime_config_cache_timestamp < _BOOTSTRAP_RUNTIME_CONFIG_CACHE_TTL_SECONDS
    ):
        return _bootstrap_runtime_config_cache
    async with _bootstrap_runtime_config_cache_lock:
        if (
            _bootstrap_runtime_config_cache
            and time.time() - _bootstrap_runtime_config_cache_timestamp < _BOOTSTRAP_RUNTIME_CONFIG_CACHE_TTL_SECONDS
        ):
            return _bootstrap_runtime_config_cache
        keys = [
            _BOOTSTRAP_TEMPLATE_SETTING_KEY,
            _BOOTSTRAP_LEARNING_WEIGHT_SETTING_KEY,
            _BOOTSTRAP_LEARNING_STATE_SETTING_KEY,
        ]
        result = await db.execute(select(SystemSetting).where(SystemSetting.setting_key.in_(keys)))
        values = {item.setting_key: item.setting_value for item in result.scalars().all()}
        _bootstrap_runtime_config_cache = {
            "templates": _parse_bootstrap_templates(values.get(_BOOTSTRAP_TEMPLATE_SETTING_KEY)),
            "weights": _parse_bootstrap_weights(values.get(_BOOTSTRAP_LEARNING_WEIGHT_SETTING_KEY)),
            "learning_state": _parse_bootstrap_learning_state(values.get(_BOOTSTRAP_LEARNING_STATE_SETTING_KEY)),
        }
        _bootstrap_runtime_config_cache_timestamp = time.time()
        return _bootstrap_runtime_config_cache


def _resolve_learning_rate_map(learning_state: dict[str, Any], profile_key: str) -> dict[str, float]:
    profiles = (learning_state or {}).get("profiles") if isinstance(learning_state, dict) else {}
    profile = (profiles or {}).get(profile_key) if isinstance(profiles, dict) else {}
    out = {"UDP": 0.5, "TCP_PASSIVE": 0.5, "TCP_ACTIVE": 0.5}
    if not isinstance(profile, dict):
        return out
    for mode_key in ("UDP", "TCP_PASSIVE", "TCP_ACTIVE"):
        stat = profile.get(mode_key)
        if not isinstance(stat, dict):
            continue
        s = max(0, int(_safe_float(stat.get("s"), 0.0)))
        f = max(0, int(_safe_float(stat.get("f"), 0.0)))
        out[mode_key] = (float(s) + 1.0) / (float(s + f) + 2.0)
    return out


def _normalize_signal_proto(v: str | None) -> str:
    p = str(v or "UDP").strip().upper()
    return p if p in {"UDP", "TCP"} else "UDP"


def _media_mode_label(mode: str | None) -> str:
    return "AUTO" if not mode else str(mode)


async def _do_warmup_flv(flv_url: str, logger, app: str, stream: str) -> bool:
    """发送 HEAD 请求触发 ZLM 创建 FLV 端点，增加重试和稳定性验证"""
    max_retries = 3
    retry_delay = 0.5  # 秒
    
    for attempt in range(max_retries):
        try:
            client = await _get_zlm_client()
            response = await client.head(flv_url, timeout=3.0)
            if response.status_code == 200:
                logger.debug(f"[Warmup] FLV endpoint ready for {app}/{stream} on attempt {attempt + 1}")
                return True
            elif response.status_code == 404:
                logger.warning(f"[Warmup] FLV endpoint not found for {app}/{stream} on attempt {attempt + 1}")
        except Exception as exc:
            logger.warning(f"[Warmup] FLV warmup failed for {app}/{stream} on attempt {attempt + 1}: {exc}")
        
        if attempt < max_retries - 1:
            await asyncio.sleep(retry_delay * (attempt + 1))  # 指数退避
    
    logger.error(f"[Warmup] FLV warmup exhausted for {app}/{stream} after {max_retries} attempts")
    return False


async def _validate_play_urls(
    urls: dict,
    node_host: str,
    node_http_port: int,
    secret: str,
    app: str,
    stream: str,
    *,
    timeout: float = 2.0,
) -> dict[str, Optional[bool]]:
    """
    逐一验证每个播放 URL 的 HTTP HEAD 请求是否返回 2xx/3xx。
    只验证 HTTP/HTTPS/WSS/WSS 协议的可访问流端点，
    rtmp/rtsp/rtc 等非 HTTP 协议返回 None（表示不适用）。
    返回 {url_key: True/False/None}，True=可用，False=不可用，None=不适用。
    """
    validated: dict[str, bool] = {}
    http_keys = {
        "flv", "https_flv", "ws_flv", "wss_flv",
        "fmp4", "https_fmp4", "ws_fmp4", "wss_fmp4",
        "hls", "https_hls", "ws_hls", "wss_hls",
        "ts", "https_ts", "ws_ts", "wss_ts",
        "rtc", "rtcs",
    }
    # RTC/WHEP 端点需要用 POST 探测，不能用 HEAD
    rtc_keys = {"rtc", "rtcs"}

    for key, url in urls.items():
        if not url:
            validated[key] = False
            continue
        if key in rtc_keys:
            # RTC 端点：POST 探测，返回非 404/401 即认为可用
            # P1-fix [2026-07-17]: 1) 添加 secret 参数 2) 区分 401（鉴权失败）与 404（接口缺失）
            #   3) 移除重复 app/stream 参数（URL 已含）和 WHEP 不支持的 type 参数
            try:
                client = await _get_zlm_client()
                # SDP o= line hardcoded 127.0.0.1 → use MEDIA_SERVER_HOST from settings
                _sdp_ip = str(settings.MEDIA_SERVER_HOST or "")  # I3 回退值不再硬编码127.0.0.1
                placeholder_sdp = (
                    "v=0\r\n"
                    f"o=- 0 0 IN IP4 {_sdp_ip}\r\n"
                    "s=-\r\n"
                    "t=0 0\r\n"
                )
                _probe_params = {}
                if secret:
                    _probe_params["secret"] = secret
                r = await client.post(
                    url,
                    params=_probe_params,
                    content=placeholder_sdp.encode("utf-8"),
                    headers={"Content-Type": "text/plain;charset=utf-8"},
                    timeout=timeout,
                )
                # 401 = ZLM 启用鉴权但探测未正确传 secret；404 = 接口缺失
                if r.status_code == 401:
                    logger.warning(f"[Validate] {key} returned 401 for {url}: ZLM auth enabled but probe secret invalid")
                    validated[key] = False
                elif r.status_code == 404:
                    validated[key] = False
                else:
                    validated[key] = True
            except Exception:
                validated[key] = False
            continue
        if key not in http_keys:
            # 非 HTTP 协议（rtmp/rtsp/rtsps 等）不做主动探测
            validated[key] = None
            continue
        # HTTP/HTTPS/WS/WSS 端点：HEAD 探测
        try:
            client = await _get_zlm_client()
            r = await client.head(url, timeout=timeout, follow_redirects=True)
            # 2xx 或 3xx 重定向都认为端点存在
            validated[key] = 200 <= r.status_code < 400
        except Exception as exc:
            logger.debug(f"[Validate] {key} HEAD failed for {url}: {exc}")
            validated[key] = False

    return validated


async def _persist_diagnostics_to_log() -> None:
    """将内存中的诊断数据定期写入日志，便于进程重启后排查问题。"""
    global _LAST_TRACE_PERSIST_TIME
    now = time.time()
    if (now - _LAST_TRACE_PERSIST_TIME) < _PLAY_TRACE_PERSIST_INTERVAL:
        return
    async with _PLAY_TRACE_PERSIST_LOCK:
        if (time.time() - _LAST_TRACE_PERSIST_TIME) < _PLAY_TRACE_PERSIST_INTERVAL:
            return
        _LAST_TRACE_PERSIST_TIME = time.time()
        failure_count = len(_PLAY_STATUS_RECENT_FAILURE)
        trace_count = len(_PLAY_SESSION_TRACE)
        if failure_count > 0 or trace_count > 0:
            logger.info(
                f"[DiagnosticsSnapshot] failures={failure_count} traces={trace_count} "
                f"build={_PLAY_DIAGNOSTIC_BUILD}"
            )


def _record_play_trace(session_id: str, stage: str, detail: dict[str, Any] | None = None) -> None:
    key = str(session_id or "").strip()
    if not key:
        return
    ts_ms = int(time.time() * 1000)
    record = _PLAY_SESSION_TRACE.get(key)
    if not isinstance(record, dict):
        record = {"created_at_ms": ts_ms, "events": [], "build": _PLAY_DIAGNOSTIC_BUILD}
        _PLAY_SESSION_TRACE[key] = record
    events = record.get("events")
    if not isinstance(events, list):
        events = []
        record["events"] = events
    payload = {
        "ts_ms": ts_ms,
        "stage": str(stage or "").strip() or "unknown",
        "detail": dict(detail or {}),
    }
    events.append(payload)
    if len(events) > _PLAY_TRACE_MAX_EVENTS:
        record["events"] = events[-_PLAY_TRACE_MAX_EVENTS:]
    record["updated_at_ms"] = ts_ms
    if len(_PLAY_SESSION_TRACE) > _PLAY_TRACE_KEEP_SESSIONS:
        oldest = sorted(
            _PLAY_SESSION_TRACE.items(),
            key=lambda kv: int(((kv[1] or {}).get("updated_at_ms") or 0)),
        )[: max(1, _PLAY_TRACE_KEEP_SESSIONS // 6)]
        for sid, _ in oldest:
            _PLAY_SESSION_TRACE.pop(sid, None)
    # 异步触发诊断数据持久化（不阻塞主流程）
    try:
        loop = asyncio.get_running_loop()
        _diag_task = loop.create_task(_persist_diagnostics_to_log())
        _diag_task.add_done_callback(lambda t: logger.debug(f"Diagnostic persist error: {t.exception()}") if not t.cancelled() and t.exception() else None)
    except RuntimeError:
        logger.warning("RuntimeError occurred")


def _read_play_trace(session_id: str) -> dict[str, Any]:
    record = _PLAY_SESSION_TRACE.get(str(session_id or "").strip())
    if not isinstance(record, dict):
        return {}
    events = record.get("events")
    if not isinstance(events, list):
        events = []
    return {
        "build": str(record.get("build") or _PLAY_DIAGNOSTIC_BUILD),
        "created_at_ms": int(record.get("created_at_ms") or 0),
        "updated_at_ms": int(record.get("updated_at_ms") or 0),
        "events": [dict(item) for item in events if isinstance(item, dict)],
    }


def _record_play_failure(session_id: str, detail: dict[str, Any]) -> None:
    key = str(session_id or "").strip()
    if not key:
        return
    payload = dict(detail or {})
    payload["ts"] = int(time.time())
    trace = _read_play_trace(key)
    if trace:
        payload["trace"] = trace
    _PLAY_STATUS_RECENT_FAILURE[key] = payload
    if len(_PLAY_STATUS_RECENT_FAILURE) > 500:
        oldest = sorted(_PLAY_STATUS_RECENT_FAILURE.items(), key=lambda kv: int((kv[1] or {}).get("ts") or 0))[:100]
        for k, _ in oldest:
            _PLAY_STATUS_RECENT_FAILURE.pop(k, None)
    # 异步触发诊断数据持久化（不阻塞主流程）
    try:
        loop = asyncio.get_running_loop()
        _diag_task2 = loop.create_task(_persist_diagnostics_to_log())
        _diag_task2.add_done_callback(lambda t: logger.debug(f"Diagnostic persist error: {t.exception()}") if not t.cancelled() and t.exception() else None)
    except RuntimeError:
        logger.warning("RuntimeError occurred")


def _normalize_health_mode(mode: str | None) -> str:
    text = str(mode or "UDP").strip().upper().replace("-", "_")
    if text not in {"UDP", "TCP_PASSIVE", "TCP_ACTIVE"}:
        return "UDP"
    return text


def _should_promote_policy_to_auto(
    *,
    success_total: int,
    fail_total: int,
    consecutive_failures: int,
    auto_switch_count: int,
) -> bool:
    if auto_switch_count <= 0:
        return False
    if consecutive_failures > 0:
        return False
    total = int(success_total or 0) + int(fail_total or 0)
    if total < 12:
        return False
    if int(success_total or 0) - int(fail_total or 0) < 10:
        return False
    failure_rate = (float(fail_total) / float(total)) if total > 0 else 0.0
    return failure_rate <= 0.15


async def _record_runtime_play_health(
    db: AsyncSession,
    *,
    asset_id: str | None,
    mode: str | None,
    success: bool,
    status_code: int,
) -> None:
    aid = str(asset_id or "").strip()
    if not aid:
        return
    result = await db.execute(select(AssetStreamHealth).where(AssetStreamHealth.asset_id == aid))
    health = result.scalars().first()
    if not health:
        health = AssetStreamHealth(asset_id=aid)
        db.add(health)
    runtime_cfg = await _load_bootstrap_runtime_config(db)
    asset = (await db.execute(select(Asset).where(Asset.id == aid))).scalars().first()
    _, bootstrap_reason = _infer_bootstrap_transport_mode(asset, runtime_cfg.get("templates"))
    learning_state = copy.deepcopy(runtime_cfg.get("learning_state") if isinstance(runtime_cfg, dict) else {"profiles": {}})
    profiles = learning_state.setdefault("profiles", {})
    if not isinstance(profiles, dict):
        profiles = {}
        learning_state["profiles"] = profiles
    mode_score_key = _mode_score_key(mode)
    profile_entry = profiles.get(bootstrap_reason)
    if not isinstance(profile_entry, dict):
        profile_entry = {"updated_at": int(time.time())}
        profiles[bootstrap_reason] = profile_entry
    mode_stat = profile_entry.get(mode_score_key)
    if not isinstance(mode_stat, dict):
        mode_stat = {"s": 0, "f": 0}
        profile_entry[mode_score_key] = mode_stat
    if success:
        mode_stat["s"] = min(9999, int(_safe_float(mode_stat.get("s"), 0.0)) + 1)
    else:
        mode_stat["f"] = min(9999, int(_safe_float(mode_stat.get("f"), 0.0)) + 1)
    profile_entry["updated_at"] = int(time.time())
    if len(profiles) > 24:
        ranked = sorted(
            [(k, int(_safe_float((v or {}).get("updated_at"), 0.0))) for k, v in profiles.items()],
            key=lambda kv: kv[1],
            reverse=True,
        )[:24]
        keep = {k for k, _ in ranked}
        profiles = {k: v for k, v in profiles.items() if k in keep}
        learning_state["profiles"] = profiles
    serialized_learning = json.dumps(learning_state, ensure_ascii=False, separators=(",", ":"))
    if len(serialized_learning) <= 1900:
        await _set_system_setting(db, _BOOTSTRAP_LEARNING_STATE_SETTING_KEY, serialized_learning)
        async with _bootstrap_runtime_config_cache_lock:
            global _bootstrap_runtime_config_cache, _bootstrap_runtime_config_cache_timestamp
            _bootstrap_runtime_config_cache = {}
            _bootstrap_runtime_config_cache_timestamp = 0.0
    health.last_status_code = int(status_code or 0)
    health.last_mode = _normalize_health_mode(mode)
    health.success_total = int(getattr(health, "success_total", 0) or 0)
    health.fail_total = int(getattr(health, "fail_total", 0) or 0)
    health.consecutive_failures = int(getattr(health, "consecutive_failures", 0) or 0)
    health.auto_switch_count = int(getattr(health, "auto_switch_count", 0) or 0)
    if success:
        health.success_total += 1
        health.consecutive_failures = 0
        policy_result = await db.execute(select(AssetStreamPolicy).where(AssetStreamPolicy.asset_id == aid))
        policy = policy_result.scalars().first()
        current_mode = str(getattr(policy, "stream_mode", "") or "").strip().upper() if policy else ""
        if current_mode == "TCP_PASSIVE" and _should_promote_policy_to_auto(
            success_total=health.success_total,
            fail_total=health.fail_total,
            consecutive_failures=health.consecutive_failures,
            auto_switch_count=health.auto_switch_count,
        ):
            policy.stream_mode = "AUTO"
        return
    health.fail_total += 1
    health.consecutive_failures += 1
    if health.consecutive_failures < 2:
        return

    # 模式特定的失败追踪：从 learning_state 中获取各模式失败次数
    runtime_cfg = await _load_bootstrap_runtime_config(db)
    learning_state = runtime_cfg.get("learning_state") if isinstance(runtime_cfg, dict) else {}
    profiles = learning_state.get("profiles") if isinstance(learning_state, dict) else {}
    bootstrap_mode, bootstrap_reason = _infer_bootstrap_transport_mode(asset, runtime_cfg.get("templates"))
    profile_entry = profiles.get(bootstrap_reason) if isinstance(profiles, dict) else {}

    def _get_mode_failures(mode_key: str) -> int:
        m = profile_entry.get(mode_key) if isinstance(profile_entry, dict) else {}
        return int(_safe_float((m or {}).get("f"), 0.0)) if isinstance(m, dict) else 0

    policy_result = await db.execute(select(AssetStreamPolicy).where(AssetStreamPolicy.asset_id == aid))
    policy = policy_result.scalars().first()
    if not policy:
        # 新建设备策略：优先尝试 UDP（最通用）
        policy = AssetStreamPolicy(asset_id=aid, stream_mode="UDP")
        db.add(policy)
        health.auto_switch_count += 1
        health.consecutive_failures = 0
        return

    current_mode = str(getattr(policy, "stream_mode", "") or "").strip().upper()
    # 同一模式连续失败 >= 2 才切换
    if current_mode == "UDP" and _get_mode_failures("UDP") >= 2:
        policy.stream_mode = "TCP_PASSIVE"
        health.auto_switch_count += 1
        health.consecutive_failures = 0
    elif current_mode == "TCP_PASSIVE" and _get_mode_failures("TCP_PASSIVE") >= 2:
        policy.stream_mode = "TCP_ACTIVE"
        health.auto_switch_count += 1
        health.consecutive_failures = 0
    elif current_mode == "TCP_ACTIVE" and _get_mode_failures("TCP_ACTIVE") >= 2:
        policy.stream_mode = "UDP"
        health.auto_switch_count += 1
        health.consecutive_failures = 0
    elif current_mode in {"AUTO", "GLOBAL"}:
        # AUTO/GLOBAL 模式：按 UDP -> TCP_PASSIVE -> TCP_ACTIVE 顺序降级
        if _get_mode_failures("UDP") >= 2:
            policy.stream_mode = "TCP_PASSIVE"
        elif _get_mode_failures("TCP_PASSIVE") >= 2:
            policy.stream_mode = "TCP_ACTIVE"
        elif _get_mode_failures("TCP_ACTIVE") >= 2:
            policy.stream_mode = "UDP"
        if policy.stream_mode != current_mode:
            health.auto_switch_count += 1
            health.consecutive_failures = 0


def _infer_bootstrap_transport_mode(asset: Asset | None, templates: list[dict[str, Any]] | None = None) -> tuple[str, str]:
    if not asset:
        return "AUTO", "no_asset_profile"
    manufacturer = str(getattr(asset, "manufacturer", "") or "").strip().lower()
    model = str(getattr(asset, "model", "") or "").strip().lower()
    transport = str(getattr(asset, "transport", "") or "").strip().upper()
    text = f"{manufacturer} {model}"
    for tpl in (templates or _DEFAULT_BOOTSTRAP_TEMPLATES):
        if not isinstance(tpl, dict):
            continue
        keywords = tpl.get("keywords")
        if not isinstance(keywords, list) or not keywords:
            continue
        if any(str(k or "").strip().lower() in text for k in keywords if str(k or "").strip()):
            mode = str(tpl.get("mode") or "AUTO").strip().upper().replace("-", "_")
            if mode not in {"AUTO", "TCP_PASSIVE", "TCP_ACTIVE"}:
                mode = "AUTO"
            reason = str(tpl.get("reason") or "template_profile").strip() or "template_profile"
            return mode, reason
    if transport == "TCP":
        return "TCP_PASSIVE", "transport_profile"
    return "AUTO", "default_profile"


async def _resolve_media_mode_candidates(db: AsyncSession, asset_id: str | None, asset: Asset | None = None) -> list[str | None]:
    # 基础候选列表：UDP 优先（设备最通用的传输模式），TCP 模式作为备选
    # 注意：这里的顺序会影响 fallback 行为，但排序逻辑会确保 UDP 排在最前
    base = ["UDP", None, "TCP_PASSIVE", "TCP_ACTIVE"]
    aid = str(asset_id or "").strip()
    policy = None
    health = None
    runtime_cfg = await _load_bootstrap_runtime_config(db)
    weights = runtime_cfg.get("weights") if isinstance(runtime_cfg, dict) else dict(_DEFAULT_BOOTSTRAP_WEIGHTS)
    learning_state = runtime_cfg.get("learning_state") if isinstance(runtime_cfg, dict) else {"profiles": {}}
    if aid:
        policy = (
            await db.execute(select(AssetStreamPolicy).where(AssetStreamPolicy.asset_id == aid))
        ).scalars().first()
        health = (
            await db.execute(select(AssetStreamHealth).where(AssetStreamHealth.asset_id == aid))
        ).scalars().first()
    mode = str(getattr(policy, "stream_mode", "") or "").strip().upper()
    success_total = int(getattr(health, "success_total", 0) or 0)
    fail_total = int(getattr(health, "fail_total", 0) or 0)
    total = success_total + fail_total
    failure_rate = (float(fail_total) / float(total)) if total > 0 else 0.0
    consecutive_failures = int(getattr(health, "consecutive_failures", 0) or 0)
    prefer_stable = bool(consecutive_failures >= 1 or failure_rate >= 0.25)
    bootstrap_mode, bootstrap_reason = _infer_bootstrap_transport_mode(asset, runtime_cfg.get("templates"))
    learning_map = _resolve_learning_rate_map(learning_state, bootstrap_reason)
    mode_scores: dict[str, float] = {"UDP": 0.0, "TCP_PASSIVE": 0.0, "TCP_ACTIVE": 0.0}
    normalized_policy_mode = str(mode or "").strip().upper()
    if normalized_policy_mode in {"UDP", "TCP_PASSIVE", "TCP_ACTIVE"}:
        policy_pref = _mode_score_key(normalized_policy_mode)
        for key in mode_scores.keys():
            mode_scores[key] += float(weights.get("policy", 1.0)) * (1.0 if key == policy_pref else 0.0)

    # 失败感知的模式降级策略：
    # - 当前模式(last_mode)连续失败过 → 大幅降级该模式
    # - TCP 模式整体失败 → 提升 UDP 权重（因为 UDP 通常最通用）
    # - prefer_stable 只影响"还没失败过的模式"之间的优先顺序
    last_mode_normalized = _normalize_health_mode(
        getattr(health, "last_mode", None) if health else None
    )
    last_mode_failures: int = 0
    if health and last_mode_normalized and last_mode_normalized != "UDP":
        # 查询该模式的历史失败情况（通过 learning_state 反推）
        learning_state = runtime_cfg.get("learning_state") if isinstance(runtime_cfg, dict) else {}
        profiles = learning_state.get("profiles") if isinstance(learning_state, dict) else {}
        bootstrap_mode, bootstrap_reason = _infer_bootstrap_transport_mode(asset, runtime_cfg.get("templates"))
        profile_entry = profiles.get(bootstrap_reason) if isinstance(profiles, dict) else {}
        mode_stat = profile_entry.get(last_mode_normalized) if isinstance(profile_entry, dict) else {}
        last_mode_failures = int(_safe_float(mode_stat.get("f"), 0.0)) if isinstance(mode_stat, dict) else 0

    if prefer_stable:
        # 失败感知降级：如果当前模式已经失败了多次（>= 2），大幅降级它
        if last_mode_failures >= 2:
            mode_scores[last_mode_normalized] -= float(weights.get("health", 1.0)) * 3.0
            # 补偿给 UDP：TCP 模式多次失败说明设备对 TCP 支持差，应该优先尝试 UDP
            mode_scores["UDP"] += float(weights.get("health", 1.0)) * 0.8
        # TCP_PASSIVE 和 TCP_ACTIVE 的基础权重（稳定模式下优先被动模式）
        mode_scores["TCP_PASSIVE"] += float(weights.get("health", 1.0)) * 1.0
        mode_scores["TCP_ACTIVE"] += float(weights.get("health", 1.0)) * 0.6
    else:
        mode_scores["UDP"] += float(weights.get("health", 1.0)) * 1.0
        mode_scores["TCP_PASSIVE"] += float(weights.get("health", 1.0)) * 0.45
        mode_scores["TCP_ACTIVE"] += float(weights.get("health", 1.0)) * 0.2
    if total == 0:
        template_pref = _mode_score_key(bootstrap_mode)
        mode_scores[template_pref] += float(weights.get("template", 1.0))
    for key in ("UDP", "TCP_PASSIVE", "TCP_ACTIVE"):
        mode_scores[key] += float(weights.get("learning", 1.0)) * (float(learning_map.get(key, 0.5)) - 0.5)
    # UDP 始终优先（最通用的传输模式，设备支持度最高）
    # 排序规则：UDP 固定排第一，其余按分数排序
    ordered_keys = sorted(
        mode_scores.keys(),
        key=lambda k: (0 if k == "UDP" else 1, -mode_scores[k]),
        reverse=False,
    )
    final: list[str | None] = [_mode_from_score_key(item) for item in ordered_keys]
    # 确保 base 中的 None 和其他模式也加入（避免遗漏）
    for item in base:
        if item not in final:
            final.append(item)
    return final


async def _build_signal_targets(db: AsyncSession, asset: Asset) -> list[tuple[str, int, str]]:
    targets: list[tuple[str, int, str]] = []
    if not asset or not asset.ip_addr:
        return targets
    base_ip = str(asset.ip_addr or "").strip()
    base_port = int(asset.port or 0)
    base_proto = _normalize_signal_proto(asset.transport)

    hint = _INVITE_ENDPOINT_HINTS.get(str(asset.gb_id or "").strip()) or {}
    hint_ip = str(hint.get("ip") or "").strip()
    hint_port = int(hint.get("port") or 0)
    hint_proto = _normalize_signal_proto(str(hint.get("proto") or base_proto))
    if hint_ip and hint_port > 0:
        targets.append((hint_ip, hint_port, hint_proto))

    pf = (
        await db.execute(
            select(ParentPlatform).where(
                ParentPlatform.server_gb_id == asset.gb_id
            )
        )
    ).scalars().first()
    if pf:
        pf_ip = str(getattr(pf, "server_ip", "") or "").strip() or base_ip
        pf_port = int(getattr(pf, "server_port", 0) or 0)
        pf_proto = _normalize_signal_proto(getattr(pf, "transport", None) or base_proto)
        if pf_ip and pf_port > 0:
            targets.append((pf_ip, pf_port, pf_proto))
    if base_ip and base_port > 0:
        targets.append((base_ip, base_port, base_proto))

    dedup: list[tuple[str, int, str]] = []
    seen = set()
    for ip, port, proto in targets:
        key = (str(ip).strip(), int(port), _normalize_signal_proto(proto))
        if key in seen:
            continue
        seen.add(key)
        dedup.append((key[0], key[1], key[2]))
    return dedup

# ---- compatibility aliases (older modules import these private names) ----
async def _release_stream_session(db: AsyncSession, stream_session: StreamSession, reason: str = "compat") -> None:
    await release_stream_session(db, stream_session, reason=reason)

async def _close_zlm_stream(app: str, stream: str, node_id: str | None = None) -> None:
    await close_zlm_stream(app, stream, node_id)

async def _probe_zlm_stream(
    node_host: str,
    node_http_port: int,
    secret: str,
    app: str,
    stream: str,
    *,
    stream_hints: list[str] | None = None,
    extra_apps: list[str] | None = None,
) -> tuple[bool, bool, dict]:
    try:
        logger_probe = logging.getLogger("stream.probe")

        def _normalize_stream_key(v: str) -> str:
            raw = str(v or "").strip().lower()
            return "".join(ch for ch in raw if ch.isalnum())

        def _stream_match(target: str, target_norm: str, candidate: str, candidate_norm: str) -> bool:
            if candidate == target:
                return True
            if target and candidate.endswith(f"_{target}"):
                return True
            if candidate and target.endswith(f"_{candidate}"):
                return True
            if target and candidate.endswith(f"-{target}"):
                return True
            if candidate and target.endswith(f"-{candidate}"):
                return True
            if target_norm and candidate_norm:
                if candidate_norm == target_norm:
                    return True
                if len(target_norm) >= 4 and candidate_norm.endswith(target_norm):
                    return True
                if len(candidate_norm) >= 4 and target_norm.endswith(candidate_norm):
                    return True
            return False

        def _snapshot_candidates(items: list[dict], limit: int = 8) -> list[dict]:
            out: list[dict] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                tracks = item.get("tracks")
                if isinstance(tracks, list):
                    track_count = len(tracks)
                else:
                    track_count = 0
                out.append(
                    {
                        "app": str(item.get("app") or ""),
                        "stream": str(item.get("stream") or ""),
                        "schema": str(item.get("schema") or ""),
                        "bytes_speed": int(item.get("bytesSpeed") or 0),
                        "reader_count": int(item.get("readerCount") or 0),
                        "track_count": track_count,
                    }
                )
                if len(out) >= max(1, int(limit or 8)):
                    break
            return out

        target_app = str(app or "")
        target_stream = str(stream or "")
        target_stream_norm = _normalize_stream_key(target_stream)
        expected_streams = [target_stream] + [str(v or "").strip() for v in (stream_hints or [])]
        expected_streams = [v for v in expected_streams if v]
        if not expected_streams:
            expected_streams = [target_stream]

        # 扩展 app 列表：优先匹配目标 app，兜底 rtp 等中间层 app
        apps_to_probe = [target_app]
        if extra_apps:
            for a in extra_apps:
                if a and a not in apps_to_probe:
                    apps_to_probe.append(a)
        # 永远兜底探测 rtp（ZLM RTP 收流后流挂在 rtp app 下）
        if "rtp" not in apps_to_probe:
            apps_to_probe.append("rtp")
        # 兜底探测 live（某些老版本 ZLM 推流挂在 live 下）
        if "live" not in apps_to_probe:
            apps_to_probe.append("live")
        # 兜底探测 playback
        if "playback" not in apps_to_probe:
            apps_to_probe.append("playback")

        sec = (str(secret or "").strip() or str(settings.MEDIA_SERVER_SECRET or "").strip())
        url = f"http://{node_host}:{int(node_http_port)}/index/api/getMediaList"
        client = await _get_zlm_client()
        # FIX [2026-07-17 P1-D1]: secret 通过 POST body 传递
        r = await client.post(url, data={"secret": sec}, timeout=3.0)
        if r.status_code >= 400:
            return False, False, {}
        data = r.json()
        if data.get("code") not in (0, "0"):
            return False, False, {}
        lst = data.get("data")
        if not isinstance(lst, list):
            return True, False, {}

        logger_probe.info(
            f"[Probe] Checking node={node_host}:{node_http_port} "
            f"target_app={target_app} target_stream={target_stream} "
            f"apps_to_probe={apps_to_probe} "
            f"expected_streams={expected_streams} "
            f"ZLM_returned_count={len(lst)}"
        )
        # 重要：始终记录 ZLM 返回的所有 app/stream（即使为空），用于诊断
        if not lst:
            logger_probe.warning(
                f"[Probe] ZLM getMediaList returned EMPTY list! "
                f"node={node_host}:{node_http_port} secret_match={bool(sec)}, "
                f"url={url}, stream={stream}, app={app}"
            )

        candidates_snapshot = _snapshot_candidates(lst)
        app_mismatch_candidates: list[dict] = []

        for item in lst:
            if not isinstance(item, dict):
                continue
            item_app = str(item.get("app") or "")
            item_stream = str(item.get("stream") or "")
            item_stream_norm = _normalize_stream_key(item_stream)

            # 按 app 优先级匹配
            for probe_app in apps_to_probe:
                if item_app != probe_app:
                    continue
                for expected in expected_streams:
                    if _stream_match(expected, _normalize_stream_key(expected), item_stream, item_stream_norm):
                        # 找到了！无论实际注册在哪个 app，都记录目标 app/stream 用于后续探测
                        item["_matched_app"] = item_app
                        item["_matched_stream"] = item_stream
                        logger_probe.debug(
                            f"[Probe] FOUND stream={item_stream} app={item_app} "
                            f"(target_app={target_app} target_stream={target_stream})"
                        )
                        return True, True, item

        # 没有精确匹配，但可能有流（app mismatch 但 stream 部分匹配）
        for item in lst:
            if not isinstance(item, dict):
                continue
            item_app = str(item.get("app") or "")
            item_stream = str(item.get("stream") or "")
            item_stream_norm = _normalize_stream_key(item_stream)
            # 跳过已匹配的 app
            if item_app in apps_to_probe:
                continue
            for expected in expected_streams:
                if _stream_match(expected, _normalize_stream_key(expected), item_stream, item_stream_norm):
                    item["_matched_app"] = item_app
                    item["_matched_stream"] = item_stream
                    logger_probe.debug(
                        f"[Probe] FOUND (app_mismatch) stream={item_stream} app={item_app} "
                        f"(target_app={target_app} target_stream={target_stream})"
                    )
                    return True, True, item

        logger_probe.debug(
            f"[Probe] NOT FOUND target_app={target_app} target_stream={target_stream} "
            f"expected_streams={expected_streams}, candidates={candidates_snapshot}"
        )
        return True, False, {"_candidates": candidates_snapshot}
    except Exception as e:
        logger.debug(f"[Probe] _probe_zlm_stream error for {node_host}:{node_http_port} app={app} stream={stream}: {e}")
        return False, False, {}

def _probe_zlm_playable(node_host: str, node_http_port: int, app: str, stream: str) -> bool:
    # 既然我们已经用 HTTP 接口 getMediaList 查到了这个流存在
    # 而且我们刚才去掉了强制 bytesSpeed > 0 的限制（为了包容出流慢的 4G 摄像头）
    # 如果再用 /live.flv 去同步下载，可能会因为没有 I 帧而阻塞或超时报错
    # 这会抹杀掉我们刚才放宽的限制。
    # 现在的商业逻辑：只要流在 ZLM 里存在（有 tracks 且 bytesSpeed 逐渐上来），前端就有播放器负责重试
    return True


async def _probe_zlm_hls_ready(
    node_host: str,
    node_http_port: int,
    app: str,
    stream: str,
    *,
    max_attempts: int = 5,
    interval_seconds: float = 0.5,
) -> tuple[bool, str, dict]:
    """
    探测 ZLM HLS 端点是否就绪。
    返回 (is_ready, hls_url, probe_detail)

    1. 先尝试发送 HEAD 请求探测现有的 .m3u8 是否可访问
    2. 如果 ZLM 返回 200，说明 HLS 端点已生成 → 返回就绪
    3. 如果返回 404 或异常，说明 HLS 切片尚未生成 → 轮询等待
    4. 最多等待 max_attempts * interval_seconds 秒后返回未就绪状态

    第三个返回值 probe_detail 包含详细诊断信息用于调试。
    """
    _stream_suffix = "" if app == "rtp" else ".live"
    _base_stream = stream
    for _suf in (".live", ".mp4", ".ts"):
        if _base_stream.endswith(_suf):
            _base_stream = _base_stream[:-len(_suf)]
            break

    hls_url = f"http://{node_host}:{int(node_http_port)}/{app}/{_base_stream}{_stream_suffix}/hls.m3u8"
    probe_detail: dict = {
        "hls_url": hls_url,
        "attempts": 0,
        "last_status_code": None,
        "last_error": None,
    }

    for attempt in range(max_attempts):
        probe_detail["attempts"] = attempt + 1
        try:
            client = await _get_zlm_client()
            response = await client.head(hls_url, timeout=3.0, follow_redirects=True)
            probe_detail["last_status_code"] = response.status_code
            if response.status_code == 200:
                logger.info(
                    f"[HLS] Ready for {app}/{stream} after {attempt + 1} attempt(s), "
                    f"URL: {hls_url}"
                )
                return True, hls_url, probe_detail
            elif response.status_code == 404:
                logger.debug(
                    f"[HLS] Not ready (404) for {app}/{stream} on attempt {attempt + 1}/{max_attempts}"
                )
            else:
                logger.debug(
                    f"[HLS] Unexpected status {response.status_code} for {app}/{stream} "
                    f"on attempt {attempt + 1}/{max_attempts}"
                )
        except Exception as exc:
            probe_detail["last_error"] = str(exc)[:120]
            logger.debug(
                f"[HLS] Probe failed for {app}/{stream} on attempt {attempt + 1}/{max_attempts}: {exc}"
            )

        if attempt < max_attempts - 1:
            await asyncio.sleep(interval_seconds * (attempt + 1))  # 指数退避

    logger.warning(
        f"[HLS] Exhausted {max_attempts} probes for {app}/{stream}, "
        f"URL={hls_url}, last_status={probe_detail['last_status_code']}, "
        f"last_error={probe_detail['last_error']}"
    )
    return False, "", probe_detail

def _build_stream_match_hints(stream: str | None, ssrc: str | None) -> list[str]:
    hints: list[str] = []

    def _push(v: str | None) -> None:
        text = str(v or "").strip()
        if text and text not in hints:
            hints.append(text)

    stream_text = str(stream or "").strip()
    ssrc_text = str(ssrc or "").strip()
    _push(stream_text)
    _push(ssrc_text)
    if ssrc_text:
        _push(ssrc_text.lstrip("0"))
        with contextlib.suppress(Exception):
            ssrc_num = int(ssrc_text, 10)
            _push(str(ssrc_num))
            _push(format(ssrc_num, "X").upper().zfill(8))
            _push(format(ssrc_num, "x").lower().zfill(8))
            # Also push 8-digit versions without leading zeros
            _push(format(ssrc_num, "X").upper())
            _push(format(ssrc_num, "x").lower())
    
    # Try to split stream to get channel_id if it's formatted like {channel}_{ssrc}
    if stream_text and "_" in stream_text:
        parts = stream_text.split("_")
        _push(parts[0]) # usually channel id
        _push(parts[-1]) # usually ssrc
    
    return hints


def _build_live_session_stream_key(device_id: str | None, channel_id: str | None) -> str:
    did = str(device_id or "").strip()
    cid = str(channel_id or "").strip()
    if did and cid:
        return f"{did}_{cid}"
    return cid or did


async def _wait_zlm_stream_ready(
    node_host: str,
    node_http_port: int,
    secret: str,
    app: str,
    stream: str,
    *,
    max_attempts: int = 80,
    interval_seconds: float = 0.25,
    stream_hints: list[str] | None = None,
    extra_apps: list[str] | None = None,
    ssrc: str | None = None,
) -> tuple[bool, bool, dict, dict]:
    attempts = max(1, int(max_attempts or 1))
    interval = max(0.05, float(interval_seconds or 0.25))
    probe_ok = False
    stream_ready = False
    stream_found = False
    playable = False
    media_item: dict = {}

    # 稳定性检测：对于 RTP 流，需要多次确认流稳定后再返回 ready
    # FIX: [2026-07-16] GB28181 实时流使用 app="live"（非 "rtp"），但本质也是 RTP 拉流。
    # 当 ssrc 参数非空时（GB28181 INVITE 场景），也启用稳定性检查，避免流仅出现 1 个 RTP 包
    # 即判定 ready 导致首帧黑屏。
    _is_rtp_stream = (str(app or "").lower() == "rtp") or (bool(ssrc) and str(app or "").lower() in ("rtp", "live"))
    _stability_window = 3  # 需要连续3次检测到流存在才认为稳定
    _stability_count = 0
    _last_bytes_speed = 0
    _bytes_speed_samples: list[int] = []

    # 优化（P0）：优先等待 ZLM on_stream_changed webhook 事件，延迟从秒级降到毫秒级。
    # 只有事件超时后才走轮询兜底。
    # 如果 webhook 事件触发，立即执行一次探测获取流信息
    _ssrc_wait_timeout = 6.0  # 等待 webhook 事件的最大时间
    _event_fired = False
    _initial_probe_done = False
    if ssrc:
        try:
            from app.sip.invite import wait_ssrc_stream_registered
            _event_fired = await wait_ssrc_stream_registered(ssrc, timeout=_ssrc_wait_timeout)
            if _event_fired:
                logger.info(f"[StreamReady] ZLM webhook event fired for ssrc={ssrc}, probing immediately")
                # Webhook 触发后立即探测，不等待 sleep
                probe_ok, stream_found, media_item = await _probe_zlm_stream(
                    node_host,
                    node_http_port,
                    secret,
                    app,
                    stream,
                    stream_hints=stream_hints,
                    extra_apps=extra_apps,
                )
                _initial_probe_done = True
                if stream_found:
                    playable_app = str(media_item.get("app") or app)
                    playable_stream = str(media_item.get("stream") or stream)
                    playable = _probe_zlm_playable(node_host, node_http_port, playable_app, playable_stream)
                    current_bytes_speed = int(media_item.get("bytesSpeed") or 0)
                    _bytes_speed_samples.append(current_bytes_speed)

                    if _is_rtp_stream and current_bytes_speed > 0:
                        _stability_count += 1
                    elif not _is_rtp_stream:
                        _stability_count += 1
                    else:
                        _stability_count = 0
                        _bytes_speed_samples = []

                    _needs_stability_check = _is_rtp_stream
                    _stability_threshold = 1  # Webhook 触发后，1次探测即可返回
                    if playable and _stability_count >= _stability_threshold:
                        return (
                            probe_ok,
                            True,
                            media_item,
                            {
                                "attempts": 1,
                                "max_attempts": attempts,
                                "interval_seconds": 0,
                                "stream_found": True,
                                "playable": True,
                                "requested_app": str(app or ""),
                                "requested_stream": str(stream or ""),
                                "requested_stream_hints": list(stream_hints or []),
                                "matched_app": playable_app,
                                "matched_stream": playable_stream,
                                "stability_verified": _needs_stability_check,
                                "stability_count": _stability_count,
                                "avg_bytes_speed": sum(_bytes_speed_samples) / len(_bytes_speed_samples) if _bytes_speed_samples else 0,
                                "early_return": True,
                                "trigger": "webhook_event",
                            },
                        )
        except Exception as e:
            logger.warning(f"Error: {e}")

    for idx in range(attempts):
        # 跳过 webhook 已探测过的第一次循环
        if _initial_probe_done and idx == 0:
            continue
        # 无论 webhook 事件是否触发，我们都必须探测一次 ZLM 以获取实际的 app/stream 映射
        probe_ok, stream_found, media_item = await _probe_zlm_stream(
            node_host,
            node_http_port,
            secret,
            app,
            stream,
            stream_hints=stream_hints,
            extra_apps=extra_apps,
        )
        if stream_found:
            # Smart ready check: bytesSpeed == 0 doesn't mean stream is dead, could be waiting for I-Frame.
            # If schema is rtp or ts, we wait longer but still consider it found.
            # We rely on _probe_zlm_playable for actual playable status.
            playable_app = str(media_item.get("app") or app)
            playable_stream = str(media_item.get("stream") or stream)
            playable = _probe_zlm_playable(node_host, node_http_port, playable_app, playable_stream)
            
            # 增强稳定性检测
            current_bytes_speed = int(media_item.get("bytesSpeed") or 0)
            _bytes_speed_samples.append(current_bytes_speed)
            
            # 对于 RTP 流，检查流是否在持续产生数据
            if _is_rtp_stream and current_bytes_speed > 0:
                _stability_count += 1
            elif not _is_rtp_stream:
                _stability_count += 1
            else:
                # bytesSpeed 为 0 或流不稳定，重置计数
                _stability_count = 0
                _bytes_speed_samples = []
            
            # 对于 RTP 流，需要稳定性窗口确认；对于其他流，直接可播放即可
            _needs_stability_check = _is_rtp_stream
            _stability_threshold = _stability_window if _needs_stability_check else 1
            
            if playable and _stability_count >= _stability_threshold:
                return (
                    probe_ok,
                    True,
                    media_item,
                    {
                        "attempts": idx + 1,
                        "max_attempts": attempts,
                        "interval_seconds": interval,
                        "stream_found": True,
                        "playable": True,
                        "requested_app": str(app or ""),
                        "requested_stream": str(stream or ""),
                        "requested_stream_hints": list(stream_hints or []),
                        "matched_app": playable_app,
                        "matched_stream": playable_stream,
                        "stability_verified": _needs_stability_check,
                        "stability_count": _stability_count,
                        "avg_bytes_speed": sum(_bytes_speed_samples) / len(_bytes_speed_samples) if _bytes_speed_samples else 0,
                    },
                )
            stream_ready = False
        if idx < attempts - 1:
            await asyncio.sleep(interval)
    return (
        probe_ok,
        stream_ready,
        media_item,
        {
            "attempts": attempts,
            "max_attempts": attempts,
            "interval_seconds": interval,
            "stream_found": bool(stream_found),
            "playable": bool(playable),
            "requested_app": str(app or ""),
            "requested_stream": str(stream or ""),
            "requested_stream_hints": list(stream_hints or []),
            "matched_app": str(media_item.get("app") or ""),
            "matched_stream": str(media_item.get("stream") or ""),
            "zlm_candidates": list((media_item or {}).get("_candidates") or []),
            "stability_verified": False,
            "stability_count": _stability_count,
            "avg_bytes_speed": sum(_bytes_speed_samples) / len(_bytes_speed_samples) if _bytes_speed_samples else 0,
        },
    )


async def _collect_probe_nodes(db: AsyncSession, preferred_node_id: str | None = None) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    db_nodes = await list_db_media_nodes(db)
    if db_nodes:
        for item in db_nodes:
            nodes.append(
                {
                    "id": str(getattr(item, "id", "") or ""),
                    "host": str(getattr(item, "host", "") or ""),
                    "http_port": int(getattr(item, "http_port", 0) or 0),
                    "secret": str(getattr(item, "secret", "") or ""),
                    "public_host": str(getattr(item, "public_host", "") or ""),
                    "public_http_port": int(getattr(item, "public_http_port", 0) or 0),
                    "is_embedded": bool(getattr(item, "is_embedded", False)),
                }
            )
    else:
        for item in get_media_nodes():
            if not isinstance(item, dict):
                continue
            nodes.append(
                {
                    "id": str(item.get("id") or ""),
                    "host": str(item.get("host") or ""),
                    "http_port": int(item.get("http_port") or 0),
                    "secret": str(item.get("secret") or ""),
                    "public_host": str(item.get("public_host") or ""),
                    "public_http_port": int(item.get("public_http_port") or 0),
                    "is_embedded": bool(item.get("is_embedded", False)),
                }
            )
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int]] = set()
    for node in nodes:
        host = str(node.get("host") or "").strip()
        http_port = int(node.get("http_port") or 0)
        if not host or http_port <= 0:
            continue
        node_id = str(node.get("id") or "").strip()
        key = (node_id, host, http_port)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(node)
    preferred = str(preferred_node_id or "").strip()
    if preferred:
        deduped.sort(key=lambda item: 0 if str(item.get("id") or "").strip() == preferred else 1)
    return deduped


async def _probe_stream_across_nodes(
    db: AsyncSession,
    *,
    app: str,
    stream: str,
    stream_hints: list[str] | None,
    preferred_node_id: str | None = None,
    limit_nodes: int = 6,
    extra_apps: list[str] | None = None,
) -> tuple[bool, dict[str, Any], dict[str, Any], dict[str, Any]]:
    nodes = await _collect_probe_nodes(db, preferred_node_id=preferred_node_id)
    max_nodes = max(1, int(limit_nodes or 1))
    attempts: list[dict[str, Any]] = []
    for node in nodes[:max_nodes]:
        host = str(node.get("host") or "")
        http_port = int(node.get("http_port") or 0)
        probe_ok, stream_found, media_item = await _probe_zlm_stream(
            host,
            http_port,
            str(node.get("secret") or ""),
            app,
            stream,
            stream_hints=stream_hints,
            extra_apps=extra_apps,
        )
        attempts.append(
            {
                "node_id": str(node.get("id") or ""),
                "node_host": host,
                "node_http_port": http_port,
                "probe_ok": bool(probe_ok),
                "stream_found": bool(stream_found),
            }
        )
        if probe_ok and stream_found:
            return True, node, media_item, {"cluster_probe_attempts": attempts}
    return False, {}, {}, {"cluster_probe_attempts": attempts}


async def _probe_webrtc_capability(node_host: str, node_http_port: int, app: str, stream: str, secret: str = "") -> tuple[bool, str]:
    """
    探测节点 WebRTC 播放能力：
    - True: 节点支持且当前流可返回 SDP
    - False: 返回原因提示

    P1-fix [2026-07-17]:
    1) 添加 secret 参数，ZLM 启用鉴权时不传 secret 会返回 401 而非 404，导致误判
    2) 区分 401（鉴权失败）与 404（接口缺失）
    """
    # 注意：ZLMediaKit 的 /index/api/webrtc 通常以 POST SDP 的方式交互，
    # GET 可能直接 404。这里改为 POST（即使 SDP 不完整也够判断"接口是否存在/可用"）。
    # SDP o= line hardcoded 127.0.0.1 → use MEDIA_SERVER_HOST from settings
    _sdp_ip = str(settings.MEDIA_SERVER_HOST or "")  # I3 回退值不再硬编码127.0.0.1
    placeholder_sdp = (
        "v=0\r\n"
        f"o=- 0 0 IN IP4 {_sdp_ip}\r\n"
        "s=-\r\n"
        "t=0 0\r\n"
    )
    try:
        url = f"http://{node_host}:{int(node_http_port)}/index/api/webrtc"
        client = await _get_zlm_client()
        # P0-fix [2026-07-17]: 禁止通过 URL 查询参数传递 ZLM secret（项目硬约束）
        # ZLM /index/api/webrtc 接口要求 body 为 raw SDP，无法用 form 字段同时传 secret。
        # 探测的本质是判断接口是否可用，因此不传 secret：
        #   - 404 → WebRTC 模块未启用
        #   - 401 → 接口存在，ZLM 启用 secret 鉴权（视为可用，secret 正确性由真实播放链路验证）
        #   - 其他 → 接口存在
        # 原 `params=_probe_params`（含 secret）会让 secret 出现在反向代理日志、浏览器历史中。
        _probe_params = {"app": app, "stream": stream, "type": "play"}
        r = await client.post(
            url,
            params=_probe_params,
            content=placeholder_sdp.encode("utf-8"),
            headers={"Content-Type": "text/plain;charset=utf-8"},
            timeout=2.0,
        )
        if r.status_code == 404:
            return (
                False,
                "WebRTC 不可用：媒体服务未提供 /index/api/webrtc（HTTP 404）。"
                "通常是 ZLMediaKit 版本过旧或编译未包含 WebRTC/RTC 模块，需要升级内置 ZLM 或更换为支持 WebRTC 的构建。",
            )
        # P1-fix: 401 = ZLM 启用 secret 鉴权但探测未传/传错 secret
        if r.status_code == 401:
            return (
                False,
                "WebRTC 探测返回 401：ZLM 启用 secret 鉴权但探测请求未携带有效 secret。"
                "请检查媒体节点 secret 配置与 MEDIA_SERVER_SECRET 是否一致。",
            )
        # 只要不是 404/401，就认为 WebRTC 接口存在（可能因 SDP 不完整返回 400/其它错误）
        if r.status_code >= 500:
            return False, f"WebRTC probe failed: server error (HTTP {r.status_code})"  # i18n
        return True, ""
    except Exception as e:
        return False, f"WebRTC 探测异常: {e}"


from app.core.play_token import generate_play_token
from loguru import logger


def _stream_play_token(app: str, stream: str, expire_seconds: int = 300) -> str:
    """生成播放鉴权 token（委托给 play_token 模块）。"""
    return generate_play_token(app, stream, expire_seconds)


def _append_token(url: str, token: str) -> str:
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}token={token}"


def _get_play_token_ttl() -> int:
    """从 mobile_app_suite / mini_program_suite 插件配置读取 token 有效期，默认 300 秒。"""
    default = 300
    for pid in ("mobile_app_suite", "mini_program_suite"):
        meta = getattr(plugin_manager, "metadata", {}).get(pid) or {}
        cfg = meta.get("config_template") or {}
        if cfg.get("enabled") and isinstance(cfg.get("token_ttl_seconds"), (int, float)):
            return max(60, int(cfg["token_ttl_seconds"]))
    return default


def _get_max_concurrent_streams() -> int:
    """从 mobile_app_suite / mini_program_suite 插件配置读取单用户（按租户）最大并发流数，0 表示不限制。"""
    for pid in ("mobile_app_suite", "mini_program_suite"):
        meta = getattr(plugin_manager, "metadata", {}).get(pid) or {}
        cfg = meta.get("config_template") or {}
        if cfg.get("enabled") and isinstance(cfg.get("max_concurrent_streams_per_user"), (int, float)):
            return max(0, int(cfg["max_concurrent_streams_per_user"]))
    return 0


def _normalize_ssrc_policy(value: str | None) -> str:
    text = str(value or "").strip().lower()
    if text in {"strict", "check", "on", "1", "true", "yes"}:
        return "strict"
    if text in {"off", "nocheck", "no_check", "0", "false", "no"}:
        return "off"
    if text in {"adaptive", "auto"}:
        return "adaptive"
    return "adaptive"


def _parse_ssrc_retry_order(value: str | None) -> list[str]:
    raw = str(value or "").strip()
    if not raw:
        raw = "strict,off"
    parts = []
    for seg in raw.replace(";", ",").split(","):
        p = _normalize_ssrc_policy(seg)
        if p == "adaptive":
            continue
        if p not in parts:
            parts.append(p)
    if not parts:
        parts = ["strict", "off"]
    return parts


async def _get_gb28181_play_config(db: AsyncSession) -> dict:
    keys = [
        "gb28181.ssrc_policy",
        "gb28181.ssrc_retry_on_not_ready",
        "gb28181.ssrc_retry_order",
        "gb28181.auto_ensure_embedded_media_node",
    ]
    result = await db.execute(select(SystemSetting).where(SystemSetting.setting_key.in_(keys)))
    values = {item.setting_key: item.setting_value for item in result.scalars().all()}
    return {
        "ssrc_policy": _normalize_ssrc_policy(values.get("gb28181.ssrc_policy") or settings.GB28181_SSRC_POLICY),
        "ssrc_retry_on_not_ready": (
            (values.get("gb28181.ssrc_retry_on_not_ready") or "").strip().lower() in {"1", "true", "yes", "on"}
            if "gb28181.ssrc_retry_on_not_ready" in values
            else settings.GB28181_SSRC_RETRY_ON_NOT_READY
        ),
        "ssrc_retry_order": _parse_ssrc_retry_order(values.get("gb28181.ssrc_retry_order") or settings.GB28181_SSRC_RETRY_ORDER),
        "auto_ensure_embedded_media_node": (
            (values.get("gb28181.auto_ensure_embedded_media_node") or "").strip().lower() in {"1", "true", "yes", "on"}
            if "gb28181.auto_ensure_embedded_media_node" in values
            else settings.GB28181_AUTO_ENSURE_EMBEDDED_MEDIA_NODE
        ),
    }


def _ssrc_policy_chain(cfg: dict) -> list[str]:
    policy = _normalize_ssrc_policy(cfg.get("ssrc_policy"))
    if policy == "adaptive":
        order = cfg.get("ssrc_retry_order") or ["strict", "off"]
        chain = ["strict"]
        for item in order:
            if item not in chain:
                chain.append(item)
        return chain
    return [policy]


def _public_stream_scheme() -> str:
    scheme = str(settings.STREAM_PUBLIC_SCHEME or "").strip().lower()
    if scheme in {"http", "https"}:
        return scheme
    return "http"


def _safe_int(value, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def _node_value(node, key: str, default=None):
    if node is None:
        return default
    if isinstance(node, dict):
        return node.get(key, default)
    return getattr(node, key, default)


def _first_non_empty(*values):
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _build_media_url(scheme: str, host: str | None, port: int | None, path: str) -> str | None:
    host_text = str(host or "").strip()
    port_num = _safe_int(port, 0)
    if not host_text or port_num <= 0:
        return None
    hide_default_port = (
        (scheme in {"http", "ws", "rtmp", "rtsp"} and port_num == 80)
        or (scheme in {"https", "wss", "rtmps", "rtsps"} and port_num == 443)
    )
    if hide_default_port:
        return f"{scheme}://{host_text}{path}"
    return f"{scheme}://{host_text}:{port_num}{path}"


def cleanup_stream_traces(max_age_seconds: float = 3600) -> int:
    """清理过期的播放追踪、失败诊断和端点缓存，防止内存泄漏。

    由 sip.server._prune_loop 每 5 分钟调用一次。
    返回被清理的条目总数。
    """
    now = time.time()
    now_ms = int(now * 1000)
    max_age_ms = int(max_age_seconds * 1000)
    removed = 0

    # 清理 _PLAY_SESSION_TRACE：移除超过 max_age 未更新的条目
    stale_trace_keys = [
        sid for sid, rec in _PLAY_SESSION_TRACE.items()
        if not isinstance(rec, dict) or (now_ms - int(rec.get("updated_at_ms") or 0)) > max_age_ms
    ]
    for key in stale_trace_keys:
        _PLAY_SESSION_TRACE.pop(key, None)
    removed += len(stale_trace_keys)

    # 清理 _PLAY_STATUS_RECENT_FAILURE：移除超过 max_age 的条目
    stale_failure_keys = [
        key for key, val in _PLAY_STATUS_RECENT_FAILURE.items()
        if not isinstance(val, dict) or (now - float(val.get("ts") or 0)) > max_age_seconds
    ]
    for key in stale_failure_keys:
        _PLAY_STATUS_RECENT_FAILURE.pop(key, None)
    removed += len(stale_failure_keys)

    # 清理 _INVITE_ENDPOINT_HINTS：限制为最近 200 条（按插入顺序，dict 保序）
    if len(_INVITE_ENDPOINT_HINTS) > 200:
        excess = len(_INVITE_ENDPOINT_HINTS) - 200
        for key in list(_INVITE_ENDPOINT_HINTS.keys())[:excess]:
            _INVITE_ENDPOINT_HINTS.pop(key, None)
        removed += excess

    return removed


async def _find_zlm_media_item(node_host: str, node_http_port: int, secret: str, app: str, stream: str) -> dict | None:
    try:
        sec = (str(secret or "").strip() or str(settings.MEDIA_SERVER_SECRET or "").strip())
        url = f"http://{node_host}:{int(node_http_port)}/index/api/getMediaList"
        client = await _get_zlm_client()
        # FIX [2026-07-17 P1-D1]: secret 通过 POST body 传递
        r = await client.post(url, data={"secret": sec}, timeout=2.0)
        if r.status_code >= 400:
            return None
        data = r.json()
        if data.get("code") not in (0, "0"):
            return None
        lst = data.get("data")
        if not isinstance(lst, list):
            return None
        for item in lst:
            if not isinstance(item, dict):
                continue
            if str(item.get("app") or "") == str(app) and str(item.get("stream") or "") == str(stream):
                return item
        return None
    except Exception:
        return None