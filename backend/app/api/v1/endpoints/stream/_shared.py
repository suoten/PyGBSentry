# FIX: [2026-07-03] stream_play.py 从 ._shared 导入 22 个符号，但 _shared.py 文件在
#      包拆分时遗漏创建，导致 stream_play.py 无法导入、实时预览全部 API 返回 404。
#      根因：refactoring 时遗漏了共享模块的创建。修复：按使用方式重建 _shared.py。 [全栈工程师]
"""实时预览端点共享工具函数与状态。

由 stream_play.py 使用，部分常量由 system_config.py 使用。
"""
from __future__ import annotations

import asyncio
import time
from typing import Any
from datetime import datetime, timezone
from collections import deque, OrderedDict

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.asset import Asset
from app.models.stream_session import StreamSession
from app.services.auth_audit import safe_auth_audit
from app.services.stream_session_service import release_stream_session
# FIX: [2026-07-03] 修正导入函数名：get_all_nodes→get_media_nodes, get_all_db_media_nodes→list_db_media_nodes [全栈工程师]
from app.core.media_nodes import get_media_nodes
from app.core.media_nodes_db import list_db_media_nodes
from app.core.http_client import get_http_client


# ─── 全局状态 ──────────────────────────────────────────────────────────────────

# FIX: [2026-07-04] 所有全局字典添加容量上限和定期清理，防止长时间运行后内存无限增长 [可靠性工程师]

# 播放幂等性保护：正在进行的 (device_id, channel_id) → 过期时间戳
_PLAY_INFLIGHT: dict[str, float] = {}

# INVITE 端点缓存：device_id → {ip, port, proto}
# FIX: 使用 OrderedDict + 容量上限，防止设备数量增长时无限膨胀
_INVITE_ENDPOINT_HINTS: OrderedDict[str, dict[str, Any]] = OrderedDict()
_INVITE_ENDPOINT_HINTS_MAX = 10000

# 最近的播放失败诊断：session_id → failure_detail
# FIX: 使用 OrderedDict + 容量上限 + TTL 过期，防止会话累积时无限膨胀
_PLAY_STATUS_RECENT_FAILURE: OrderedDict[str, dict[str, Any]] = OrderedDict()
_PLAY_STATUS_RECENT_FAILURE_MAX = 5000
_PLAY_STATUS_RECENT_FAILURE_TTL = 3600  # 1小时后自动过期

# 播放追踪：session_id → deque of (event, timestamp, detail)
# FIX: 使用 OrderedDict + 容量上限，防止会话累积时无限膨胀
_PLAY_TRACES: OrderedDict[str, deque] = OrderedDict()
_PLAY_TRACE_MAX = 60  # 每个 session 最多保留 60 条事件
_PLAY_TRACES_MAX_SESSIONS = 5000  # 最多保留 5000 个 session 的追踪

# 标记是否已注册定期清理任务
_stream_cleanup_registered = False

# 默认 bootstrap 模板（由 system_config.py 导入）
_DEFAULT_BOOTSTRAP_TEMPLATES: list[dict[str, Any]] = [
    {
        "name": "udp_passive",
        "transport": "UDP",
        "media_mode": "passive",
        "description": "UDP 被动收流（默认）",
    },
    {
        "name": "tcp_passive",
        "transport": "TCP",
        "media_mode": "passive",
        "description": "TCP 被动收流",
    },
]

# 默认 bootstrap 学习权重（由 system_config.py 导入）
_DEFAULT_BOOTSTRAP_WEIGHTS: dict[str, float] = {
    "udp_passive": 0.7,
    "tcp_passive": 0.3,
}


# ─── 播放幂等性保护 ────────────────────────────────────────────────────────────

class _PlayIdempotencyGuard:
    """点播幂等性保护：同一 (device_id, channel_id) 在 TTL 内只允许一次并发请求。"""

    _TTL_SECONDS = 10.0

    def __init__(self, device_id: str, channel_id: str) -> None:
        """Internal helper:   init  ."""
        self._key = f"{device_id}:{channel_id}"

    async def acquire(self) -> bool:
        """Acquire."""
        now = time.monotonic()
        # 清理过期条目
        expired = [k for k, ts in _PLAY_INFLIGHT.items() if now - ts > self._TTL_SECONDS]
        for k in expired:
            _PLAY_INFLIGHT.pop(k, None)
        if self._key in _PLAY_INFLIGHT:
            return False
        _PLAY_INFLIGHT[self._key] = now
        return True

    async def release(self) -> None:
        """Release."""
        _PLAY_INFLIGHT.pop(self._key, None)


# ─── 审计与追踪 ────────────────────────────────────────────────────────────────

async def _stream_audit(
    db: AsyncSession,
    user: Any,
    *,
    action: str,
    result: str,
    status_code: int,
    detail: str = "",
    extra_summary: str = "",
) -> None:
    """记录流操作审计日志。"""
    await safe_auth_audit(
        db,
        module="stream",
        action=action,
        source="stream_api",
        operator=getattr(user, "username", None) or "unknown",
        result=result,
        tenant_id=(getattr(user, "tenant_id", None) or "default").strip() or "default",
        status_code=status_code,
        detail=detail,
        extra_summary=extra_summary,
    )


def _record_play_trace(session_id: str, event: str, detail: dict[str, Any] | None = None) -> None:
    """记录播放追踪事件（内存中，最多保留 _PLAY_TRACE_MAX 条）。"""
    if not session_id:
        return
    key = str(session_id).strip()
    if key not in _PLAY_TRACES:
        _PLAY_TRACES[key] = deque(maxlen=_PLAY_TRACE_MAX)
    _PLAY_TRACES[key].append({
        "event": str(event or ""),
        "ts": datetime.now(timezone.utc).isoformat(),
        "detail": detail or {},
    })
    # FIX: [2026-07-04] 容量上限保护 — 超过最大 session 数时淘汰最旧的条目 [可靠性工程师]
    while len(_PLAY_TRACES) > _PLAY_TRACES_MAX_SESSIONS:
        try:
            _PLAY_TRACES.popitem(last=False)
        except KeyError:
            break


def _read_play_trace(session_id: str) -> list[dict[str, Any]]:
    """读取播放追踪记录。"""
    key = str(session_id or "").strip()
    if not key or key not in _PLAY_TRACES:
        return []
    return list(_PLAY_TRACES[key])


def _record_play_failure(session_id: str, failure: dict[str, Any]) -> None:
    """记录播放失败诊断信息。"""
    key = str(session_id or "").strip()
    if not key:
        return
    _PLAY_STATUS_RECENT_FAILURE[key] = {
        **failure,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    _record_play_trace(session_id, "play_failure", failure)
    # FIX: [2026-07-04] 容量上限保护 — 超过最大条目数时淘汰最旧的条目 [可靠性工程师]
    while len(_PLAY_STATUS_RECENT_FAILURE) > _PLAY_STATUS_RECENT_FAILURE_MAX:
        try:
            _PLAY_STATUS_RECENT_FAILURE.popitem(last=False)
        except KeyError:
            break


# ─── 信号与传输辅助 ────────────────────────────────────────────────────────────

def _normalize_signal_proto(proto: Any) -> str:
    """规范化信号协议为大写 UDP/TCP。"""
    v = str(proto or "").strip().upper()
    if v in ("UDP", "TCP"):
        return v
    return "UDP"


def _media_mode_label(mode: Any) -> str:
    """将 media_mode 枚举值转为可读标签。"""
    if mode is None:
        return "auto"
    v = str(mode).strip().lower()
    if v in ("passive", "0"):
        return "passive"
    if v in ("active", "1"):
        return "active"
    return v or "auto"


async def _build_signal_targets(db: AsyncSession, asset: Asset) -> list[tuple[str, int, str]]:
    """构建设备信令目标列表：[(ip, port, proto), ...]。"""
    ip = str(getattr(asset, "ip_addr", "") or "").strip()
    port = int(getattr(asset, "port", 0) or 0)
    transport = str(getattr(asset, "transport", "") or "UDP").strip().upper()
    if not ip or port <= 0:
        # 尝试从 INVITE 端点缓存中获取
        gb_id = str(getattr(asset, "gb_id", "") or "").strip()
        hint = _INVITE_ENDPOINT_HINTS.get(gb_id)
        if hint:
            ip = str(hint.get("ip") or "").strip()
            port = int(hint.get("port") or 0)
            transport = _normalize_signal_proto(hint.get("proto"))
    if not ip or port <= 0:
        return []
    return [(ip, port, _normalize_signal_proto(transport))]


def _build_live_session_stream_key(device_id: str, channel_id: str) -> str:
    """生成直播会话的 stream key。"""
    return f"{device_id}_{channel_id}"


def _build_stream_match_hints(stream_id: str, ssrc: str) -> dict[str, Any]:
    """构建 ZLM 流匹配提示。"""
    return {
        "stream_id": str(stream_id or ""),
        "ssrc": str(ssrc or ""),
        "alt_stream_ids": [],
    }


# ─── ZLM 流探测 ───────────────────────────────────────────────────────────────

async def _probe_zlm_stream(
    host: str,
    http_port: int,
    secret: str,
    app: str,
    stream: str,
    stream_hints: dict[str, Any] | None = None,
    extra_apps: list[str] | None = None,
    ssrc: str = "",
) -> tuple[bool, bool, dict[str, Any]]:
    """探测单个 ZLM 节点上的流是否就绪。

    FIX: [2026-07-03] 原返回 2-tuple (ready, detail)，但 stream_play.py:908/927 与
    response_handler.py:48 均按 3-tuple (probe_ok, stream_found, media_item) 解包，
    导致运行时 ValueError。改为 3-tuple：probe_ok=ZLM 可达, stream_found=流在线,
    media_item=匹配信息（含 app/stream/matched_app/matched_stream 供 response_handler 使用）。[全栈工程师]
    """
    if not host or not http_port:
        return False, False, {"error": "invalid_host"}
    base_url = f"http://{host}:{http_port}"
    # FIX: [2026-07-04] 添加 await — get_http_client 是异步函数，缺少 await 返回协程对象而非 AsyncClient，
    #      导致后续 client.get() 抛出 AttributeError 'coroutine' object has no attribute 'get'，
    #      使流探测始终失败 [可靠性工程师]
    client = await get_http_client()
    try:
        params = {
            "secret": secret,
            "schema": "rtsp",
            "app": app,
            "stream": stream,
        }
        resp = await client.post(f"{base_url}/index/api/getMediaInfo", data=params, timeout=3.0)
        data = resp.json()
        if data.get("code") == 0 and data.get("online"):
            return True, True, {
                "matched_app": app,
                "matched_stream": stream,
                "app": app,
                "stream": stream,
                "node_host": host,
                "node_http_port": http_port,
            }
        # 如果指定了 ssrc，尝试在 rtp app 下查找
        if ssrc and extra_apps:
            for alt_app in extra_apps:
                params2 = {
                    "secret": secret,
                    "schema": "rtsp",
                    "app": alt_app,
                    "stream": ssrc,
                }
                resp2 = await client.post(f"{base_url}/index/api/getMediaInfo", data=params2, timeout=3.0)
                data2 = resp2.json()
                if data2.get("code") == 0 and data2.get("online"):
                    return True, True, {
                        "matched_app": alt_app,
                        "matched_stream": ssrc,
                        "app": alt_app,
                        "stream": ssrc,
                        "node_host": host,
                        "node_http_port": http_port,
                    }
        # ZLM 可达但流未在线
        return True, False, {"online": False, "code": data.get("code")}
    except Exception as e:
        return False, False, {"error": str(e)[:200]}


async def _wait_zlm_stream_ready(
    host: str,
    http_port: int,
    secret: str,
    app: str,
    stream: str,
    max_attempts: int = 20,
    interval_seconds: float = 0.25,
    stream_hints: dict[str, Any] | None = None,
    extra_apps: list[str] | None = None,
    ssrc: str = "",
) -> tuple[bool, bool, dict[str, Any], dict[str, Any]]:
    """轮询等待 ZLM 流就绪。返回 (probe_ok, stream_ready, media_item, detail)。"""
    probe_ok = False
    for attempt in range(max_attempts):
        # FIX: [2026-07-04] _probe_zlm_stream 返回 3-tuple (probe_ok, stream_found, media_item)，
        #      原代码使用 2-tuple 解包导致 ValueError: too many values to unpack [可靠性工程师]
        _probe_ok, _stream_found, media_item = await _probe_zlm_stream(
            host, http_port, secret, app, stream, stream_hints, extra_apps, ssrc
        )
        if _stream_found:
            probe_ok = True
            return True, True, media_item, {"attempts": attempt + 1, "detail": media_item}
        if "error" not in (media_item or {}):
            probe_ok = True  # ZLM 可达但流未就绪
        await asyncio.sleep(interval_seconds)
    return probe_ok, False, {}, {"attempts": max_attempts, "detail": "timeout"}


async def _probe_stream_across_nodes(
    db: AsyncSession,
    app: str,
    stream: str,
    stream_hints: dict[str, Any] | None = None,
    preferred_node_id: str | None = None,
    extra_apps: list[str] | None = None,
) -> tuple[bool, dict[str, Any], dict[str, Any], dict[str, Any]]:
    """跨所有媒体节点探测流是否就绪。返回 (ready, node, media_item, detail)。"""
    # 获取所有节点
    db_nodes = await list_db_media_nodes(db)
    static_nodes = get_media_nodes()
    all_nodes = []
    for n in db_nodes:
        all_nodes.append({
            "id": str(getattr(n, "id", "") or ""),
            "host": str(getattr(n, "host", "") or ""),
            "http_port": int(getattr(n, "http_port", 0) or 0),
            "secret": str(getattr(n, "secret", "") or ""),
            "public_host": str(getattr(n, "public_host", "") or ""),
            "public_http_port": int(getattr(n, "public_http_port", 0) or 0),
            "is_embedded": bool(getattr(n, "is_embedded", False)),
        })
    for n in static_nodes:
        all_nodes.append(n)

    # 优先探测 preferred_node
    if preferred_node_id:
        all_nodes.sort(key=lambda n: 0 if str(n.get("id")) == str(preferred_node_id) else 1)

    ssrc = str((stream_hints or {}).get("ssrc") or "")
    for node in all_nodes:
        host = str(node.get("host") or "")
        http_port = int(node.get("http_port") or 0)
        secret = str(node.get("secret") or "")
        if not host or http_port <= 0:
            continue
        # FIX: [2026-07-03] _probe_zlm_stream 改为 3-tuple，此处同步解包 [全栈工程师]
        _probe_reachable, ready, detail = await _probe_zlm_stream(
            host, http_port, secret, app, stream, stream_hints, extra_apps, ssrc
        )
        if ready:
            return True, node, detail, {"probed_nodes": len(all_nodes), "matched_node": node.get("id")}
    return False, {}, {}, {"probed_nodes": len(all_nodes), "detail": "no_match"}


# ─── 健康与配置 ────────────────────────────────────────────────────────────────

async def _record_runtime_play_health(
    db: AsyncSession,
    *,
    asset_id: str | None,
    mode: str,
    success: bool,
    status_code: int,
) -> None:
    """记录播放健康指标到数据库（如果模型存在）。"""
    try:
        from app.models.network_metric import NetworkMetric
        metric = NetworkMetric(
            asset_id=asset_id,
            metric_type="play_health",
            value=float(1 if success else 0),
            detail=f"mode={mode};status={status_code}",
        )
        db.add(metric)
    except Exception:
        logger.debug("play_health metric not recorded (model unavailable)")


async def _resolve_media_mode_candidates(
    db: AsyncSession,
    asset_id: str | None,
    *,
    asset: Asset | None = None,
) -> list[str]:
    """解析设备支持的媒体模式候选列表。"""
    # 默认返回 passive → active 顺序
    return ["passive", "active"]


async def _get_gb28181_play_config(db: AsyncSession) -> dict[str, Any]:
    """从 SystemSetting 获取 GB28181 播放配置。"""
    cfg: dict[str, Any] = {
        "ssrc_retry_on_not_ready": True,
        "ssrc_check_mode": "strict",
        "preferred_transport": "UDP",
        "media_mode": "passive",
    }
    try:
        from app.models.system_setting import SystemSetting
        result = await db.execute(
            select(SystemSetting.setting_key, SystemSetting.setting_value).where(
                SystemSetting.setting_key.like("gb28181.%")
            )
        )
        for key, val in result.all():
            cfg_key = key.split(".", 1)[1] if "." in key else key
            cfg[cfg_key] = val
    except Exception as e:
        logger.debug(f"_shared: failed to load gb28181 config from DB: {e}")
    return cfg


def _ssrc_policy_chain(cfg: dict[str, Any]) -> list[str]:
    """根据配置返回 SSRC 策略链。"""
    chain = ["strict"]
    if cfg.get("ssrc_retry_on_not_ready", True):
        chain.append("adaptive")
    return chain


async def _do_warmup_flv(
    url: str,
    logger,
    app: str,
    stream: str,
    timeout: float = 2.0,
) -> None:
    """预热 FLV 流连接（发起一个短请求触发 ZLM 初始化）。

    FIX: [2026-07-03] 原签名为 (media_host, media_port, app, stream)，但 stream_play.py:347/1183
    实际以 (_flv_url, _flv_log, matched_app, matched_stream) 调用——第 1 参为完整 URL 字符串、
    第 2 参为 logger 实例，原签名会把 logger 当作 int 端口做 <=0 比较抛 TypeError。改为接收完整 URL。[全栈工程师]
    """
    if not url:
        return
    # FIX: [2026-07-04] 添加 await — get_http_client 是异步函数 [可靠性工程师]
    client = await get_http_client()
    try:
        await client.get(url, timeout=timeout, headers={"Range": "bytes=0-0"})
    except Exception as warmup_err:
        # 预热失败不影响主流程，仅记录调试日志
        if logger is not None:
            try:
                logger.debug(f"FLV warmup failed for {app}/{stream}: {warmup_err}")
            except Exception as log_err:
                pass  # logger itself failed, nothing more we can do


async def _release_stream_session(db: AsyncSession, session: Any, reason: str = "") -> None:
    """释放流会话资源的薄包装。

    FIX: [2026-07-03] device_record.py 在 4 处延迟导入 `from app.api.v1.endpoints.stream import _release_stream_session`，
    但该符号此前完全缺失，运行到下载停止/清理逻辑会 ImportError。此处转发到 stream_session_service.release_stream_session。[全栈工程师]
    """
    if session is None:
        return
    await release_stream_session(db, session, reason=reason or "")


def _get_max_concurrent_streams() -> int:
    """获取最大并发流数限制（0 = 不限制）。"""
    return int(getattr(settings, "MAX_CONCURRENT_STREAMS", 0) or 0)


# FIX: [2026-07-04] 定期清理播放追踪和失败诊断缓存，防止长时间运行后内存无限增长 [可靠性工程师]
def cleanup_stream_traces() -> int:
    """清理过期的播放追踪和失败诊断条目。

    被 ``server._prune_loop`` 或 ``health_service._run_loop`` 周期性调用。
    返回清理的条目总数。
    """
    cleaned = 0
    now_ts = time.time()

    # 1. 清理过期的 _PLAY_STATUS_RECENT_FAILURE（超过 TTL 的条目）
    expired_failures = []
    for key, val in _PLAY_STATUS_RECENT_FAILURE.items():
        recorded_at = str(val.get("recorded_at") or "")
        if recorded_at:
            try:
                dt = datetime.fromisoformat(recorded_at.replace("Z", "+00:00"))
                if now_ts - dt.timestamp() > _PLAY_STATUS_RECENT_FAILURE_TTL:
                    expired_failures.append(key)
            except Exception:
                expired_failures.append(key)
        else:
            expired_failures.append(key)
    for key in expired_failures:
        _PLAY_STATUS_RECENT_FAILURE.pop(key, None)
        cleaned += 1

    # 2. 容量上限保护（已在写入时处理，此处做二次保护）
    while len(_PLAY_STATUS_RECENT_FAILURE) > _PLAY_STATUS_RECENT_FAILURE_MAX:
        _PLAY_STATUS_RECENT_FAILURE.popitem(last=False)
        cleaned += 1
    while len(_PLAY_TRACES) > _PLAY_TRACES_MAX_SESSIONS:
        _PLAY_TRACES.popitem(last=False)
        cleaned += 1
    while len(_INVITE_ENDPOINT_HINTS) > _INVITE_ENDPOINT_HINTS_MAX:
        _INVITE_ENDPOINT_HINTS.popitem(last=False)
        cleaned += 1

    return cleaned


# ─── list_streams（由 proxy_compat.py 导入）────────────────────────────────────

async def list_streams(
    db: AsyncSession = None,
    current_user: Any = None,
) -> list[dict[str, Any]]:
    """列出当前活跃的流会话。"""
    stmt = select(StreamSession).where(StreamSession.to_tag.is_(None))
    if current_user and not getattr(current_user, "is_superuser", False):
        tenant_id = getattr(current_user, "tenant_id", None) or "default"
        stmt = stmt.join(Asset, StreamSession.asset_id == Asset.id).where(Asset.tenant_id == tenant_id)
    if db is None:
        return []
    result = await db.execute(stmt)
    sessions = result.scalars().all()
    return [
        {
            "app": str(getattr(s, "app", "") or ""),
            "stream": str(getattr(s, "stream", "") or ""),
            "is_proxy": False,
            "device_id": str(getattr(s, "asset_id", "") or ""),
            "channel_id": str(getattr(s, "resource_id", "") or ""),
        }
        for s in sessions
    ]
