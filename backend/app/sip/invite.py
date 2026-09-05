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
from app.models.asset_stream_policy import AssetStreamPolicy
from app.models.asset_stream_health import AssetStreamHealth
from app.models.asset import Asset
from app.models.resource import Resource
from app.db.session import AsyncSessionLocal
from app.services.stream_strategy import normalize_stream_mode, recommend_stream_mode
from app.services.audit_center_service import audit_center_service
from sqlalchemy import select, delete
import asyncio
import contextlib
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
# FIX [2026-07-17 P1]: 统一使用进程级 CSeq 计数器（RFC 3261 §22.2 单调递增）
from app.sip.commander import _next_cseq
from app.core.plugin_manager import plugin_manager
from app.sip.ssrc_manager import ssrc_manager
from app.sip.dialog_manager import dialog_manager
# P1-fix [2026-07-17]: SIP Session Timer (RFC 4028) — 长会话保活机制
from app.sip.invite_server_state import (
    apply_session_expires_to_request,
    parse_session_expires,
)


def _gb28181_playback_time(epoch: int) -> str:
    if not epoch or epoch <= 0:
        return "19700101T000000Z"
    try:
        dt = datetime.datetime.fromtimestamp(int(epoch), tz=datetime.timezone.utc)
        return dt.strftime("%Y%m%dT%H%M%SZ")
    except Exception:
        return "19700101T000000Z"


def _attach_trace_header(req: SipMessage) -> str:
    """返回 Call-ID 作为 trace_id 用于日志关联。

    FIX: [2026-07-21 P0] 不再向 SIP 请求添加 X-Trace-ID 头域。
    实测发现 EasyGBS 等非标准 SIP 客户端对非标准头域（X- 开头）敏感，会返回 400 Bad Request。
    """
    return (req.get_header("Call-ID") or "").strip()
from app.core.config import settings, sip_host_for_contact, sip_via_host, sip_from_to_host
from app.core.async_utils import fire_and_forget  # P0-16: 安全的火-忘任务
from fastapi import HTTPException
from app.sip.state_backend import get_sip_state_backend

class InviteState:
    """Encapsulates all INVITE-related global state with bounded cleanup."""

    def __init__(self):
        self.stream_switch_lock = asyncio.Lock()
        self.stream_switch_pending: dict[str, str] = {}
        self.stream_switch_pending_timestamps: dict[str, float] = {}
        self.stream_switch_rollback_depth: dict[str, int] = {}
        self.stream_switch_rollback_depth_max = 500
        self.stream_switch_rollback_depth_ttl = 120
        self.stream_switch_rollback_depth_timestamps: dict[str, float] = {}
        self.stream_switch_pending_max = 1000
        self.stream_switch_pending_ttl = 60
        # Note: invite_rate_stats modifications are safe in asyncio single-thread model.
        # No lock needed as long as no await between read and write.
        self.invite_rate_stats: dict[str, int] = {
            "allowed": 0,
            "blocked_device": 0,
            "blocked_tenant": 0,
            "backend_redis": 0,
            "backend_local": 0,
            "backend_fallback": 0,
        }
        self.invite_pending: dict[str, tuple[asyncio.Event, dict]] = {}
        self.invite_pending_max_size = 10000
        self.invite_provisional: dict[str, dict] = {}
        # FIX [2026-07-17 P1-B3]: cascade_call_ids 从 set 改为 dict[str, float]（call_id -> timestamp），
        # 支持按 TTL 清理过期条目，避免超限时整体清空丢失活跃级联 INVITE 跟踪。
        self.cascade_call_ids: dict[str, float] = {}
        self.cascade_call_ids_max = 2000
        self.cascade_call_ids_ttl = 300  # 5 分钟 TTL，超过的视为已完成级联事务
        self.channel_invite_locks: dict[str, asyncio.Lock] = {}
        self.ssrc_gen_lock = asyncio.Lock()
        # FIX: [2026-07-03] 全局并发 INVITE 信号量，防止大流量时打爆设备 [全栈工程师]
        _max_concurrent = int(getattr(__import__('app.core.config', fromlist=['settings']).settings, 'SIP_INVITE_MAX_CONCURRENT', 200) or 200)
        self.global_invite_semaphore = asyncio.Semaphore(_max_concurrent)

    def cleanup(self) -> None:
        """Periodic cleanup of stale entries."""
        now = time.time()
        # 清理 stream_switch_rollback_depth：超过 TTL 的条目
        if self.stream_switch_rollback_depth_timestamps:
            stale_keys = [k for k, t in self.stream_switch_rollback_depth_timestamps.items() if now - t > self.stream_switch_rollback_depth_ttl]
            for k in stale_keys:
                self.stream_switch_rollback_depth.pop(k, None)
                self.stream_switch_rollback_depth_timestamps.pop(k, None)
        # 溢出清理：超过 max_size 时移除最旧的条目
        if len(self.stream_switch_rollback_depth) > self.stream_switch_rollback_depth_max:
            sorted_keys = sorted(self.stream_switch_rollback_depth_timestamps.keys(), key=lambda k: self.stream_switch_rollback_depth_timestamps.get(k, 0))
            excess = len(self.stream_switch_rollback_depth) - self.stream_switch_rollback_depth_max + 100
            for k in sorted_keys[:excess]:
                self.stream_switch_rollback_depth.pop(k, None)
                self.stream_switch_rollback_depth_timestamps.pop(k, None)
        # FIX [2026-07-17 P1-B3]: cascade_call_ids 按 TTL 清理过期条目，而非整体清空。
        # 原实现 .clear() 会丢失所有活跃级联 INVITE 的 Call-ID 跟踪，
        # 导致进行中的级联流无法匹配响应，引发资源泄漏和流异常中断。
        if self.cascade_call_ids:
            _stale_cascade = [k for k, t in self.cascade_call_ids.items() if now - t > self.cascade_call_ids_ttl]
            for k in _stale_cascade:
                self.cascade_call_ids.pop(k, None)
            # 溢出兜底：仍超限时移除最旧的条目（按 timestamp 排序）
            if len(self.cascade_call_ids) > self.cascade_call_ids_max:
                _sorted_keys = sorted(self.cascade_call_ids.keys(), key=lambda k: self.cascade_call_ids.get(k, 0))
                _excess = len(self.cascade_call_ids) - self.cascade_call_ids_max + 100
                for k in _sorted_keys[:_excess]:
                    self.cascade_call_ids.pop(k, None)
        # 清理 stream_switch_pending + stream_switch_pending_timestamps：超过 TTL 的条目
        if self.stream_switch_pending_timestamps:
            _stale_switch_keys = [k for k, t in self.stream_switch_pending_timestamps.items() if now - t > self.stream_switch_pending_ttl]
            for k in _stale_switch_keys:
                self.stream_switch_pending.pop(k, None)
                self.stream_switch_pending_timestamps.pop(k, None)
        # 溢出清理：stream_switch_pending 超过 max_size 时移除最旧的条目
        if len(self.stream_switch_pending) > self.stream_switch_pending_max:
            _sorted_keys = sorted(self.stream_switch_pending_timestamps.keys(), key=lambda k: self.stream_switch_pending_timestamps.get(k, 0))
            _excess = len(self.stream_switch_pending) - self.stream_switch_pending_max + 100
            for k in _sorted_keys[:_excess]:
                self.stream_switch_pending.pop(k, None)
                self.stream_switch_pending_timestamps.pop(k, None)
        # 清理 invite_pending：超过 300 秒的条目
        _invite_pending_ttl = 300
        stale_pending = []
        for k, (ev, res) in self.invite_pending.items():
            _created = res.get("created_at", 0) if isinstance(res, dict) else 0
            if _created and now - _created > _invite_pending_ttl:
                stale_pending.append(k)
        for k in stale_pending:
            removed = self.invite_pending.pop(k, None)
            if removed:
                ev, res = removed
                res["ok"] = False
                res["reason"] = "cleanup_ttl_expired"
                ev.set()
        # 溢出清理：invite_pending 超过 max_size 时移除最旧的条目
        if len(self.invite_pending) > self.invite_pending_max_size:
            _cutoff = len(self.invite_pending) - self.invite_pending_max_size + 100
            for k in list(self.invite_pending.keys())[:_cutoff]:
                removed = self.invite_pending.pop(k, None)
                if removed:
                    ev, res = removed
                    res["ok"] = False
                    res["reason"] = "cleanup_overflow"
                    ev.set()
        # 清理 invite_provisional：超过 300 秒的条目
        _provisional_ttl = 300
        stale_provisional = [k for k, v in self.invite_provisional.items() if now - v.get("timestamp", 0) > _provisional_ttl]
        for k in stale_provisional:
            self.invite_provisional.pop(k, None)
        # 溢出清理：invite_provisional 超过 5000 时移除最旧的条目
        if len(self.invite_provisional) > 5000:
            _sorted_prov = sorted(self.invite_provisional.items(), key=lambda x: x[1].get("timestamp", 0))
            _excess_prov = len(self.invite_provisional) - 5000 + 100
            for k, _ in _sorted_prov[:_excess_prov]:
                self.invite_provisional.pop(k, None)
        # 清理 channel_invite_locks：未被锁定的条目
        if len(self.channel_invite_locks) > 1000:
            _unlocked = [k for k, lock in self.channel_invite_locks.items() if not lock.locked()]
            for k in _unlocked:
                self.channel_invite_locks.pop(k, None)

    def get_channel_lock(self, channel_id: str) -> asyncio.Lock:
        lock = self.channel_invite_locks.get(channel_id)
        if lock is None:
            lock = asyncio.Lock()
            self.channel_invite_locks[channel_id] = lock
        # 清理过多的通道锁，防止长期运行内存泄漏（保留最近1000个）
        if len(self.channel_invite_locks) > 1000:
            _evict_keys = list(self.channel_invite_locks.keys())[:len(self.channel_invite_locks) - 800]
            for k in _evict_keys:
                if k != channel_id and not self.channel_invite_locks[k].locked():
                    self.channel_invite_locks.pop(k, None)
        return lock


invite_state = InviteState()


def cancel_invite_watchdog(call_id: str) -> None:
    cancel_watchdog(f"invite:{call_id}")


async def _send_cancel(addr: tuple, proto: str, transport, call_id: str, from_tag: str, invite_branch: str, channel_id: str, cseq_num: int = 1) -> None:
    cancel_req = SipMessage()
    cancel_req.method = "CANCEL"
    cancel_req.uri = f"sip:{channel_id}@{addr[0]}:{addr[1]}"
    cancel_req.version = "SIP/2.0"
    cancel_req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={invite_branch}"
    cancel_req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={from_tag}"
    cancel_req.headers["To"] = f"<sip:{channel_id}@{sip_from_to_host()}>"
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
    branch = f"z9hG4bK{secrets.token_hex(8)}"  # FIX [2026-07-21 P0]: 无前缀，兼容 EasyGBS 等非标准客户端
    bye_req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={branch}"
    bye_req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={from_tag}"
    to_header = f"<sip:{channel_id}@{sip_from_to_host()}>"
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
        "original_sdp": "",  # C-04 存储原始INVITE的SDP，供3xx重定向使用
        "watchdog_on_timeout": None,  # S-07 存储watchdog回调，供3xx重定向后重置watchdog
    }
    if len(invite_state.invite_pending) > invite_state.invite_pending_max_size:
        cutoff_count = len(invite_state.invite_pending) - invite_state.invite_pending_max_size + 100
        for k in list(invite_state.invite_pending.keys())[:cutoff_count]:
            removed = invite_state.invite_pending.pop(k, None)
            if removed:
                ev, res = removed
                # 驱逐时取消看门狗定时器，避免超时回调浪费事件循环资源
                try:
                    cancel_invite_watchdog(k)
                except Exception as _wd_err:
                    logger.warning(f"Failed to cancel watchdog for evicted INVITE {k}: {_wd_err}")
                # release SSRC/port/ZLM resources when evicting pending INVITE entries
                _evicted_ssrc = res.get("ssrc", "")
                _evicted_stream_id = res.get("stream_id", "")
                _evicted_app = res.get("app", "")
                _evicted_node_id = res.get("node_id", "")
                _evicted_lease_id = res.get("lease_id", "")
                if _evicted_ssrc:
                    try:
                        from app.sip.ssrc_manager import ssrc_manager as _sm
                        fire_and_forget(_sm.release(_evicted_ssrc))
                    except Exception as e:
                        # evicted SSRC release should log, not silently pass
                        logger.warning(f"Failed to release evicted SSRC {_evicted_ssrc}: {e}")
                    try:
                        fire_and_forget(unregister_ssrc_waiter(_evicted_ssrc))
                    except Exception as e:
                        # evicted SSRC waiter unregister should log, not silently pass
                        logger.warning(f"Failed to unregister evicted SSRC waiter {_evicted_ssrc}: {e}")
                if _evicted_stream_id and _evicted_app:
                    try:
                        from app.services.zlm_stream_control import close_zlm_stream as _close_stream
                        fire_and_forget(_close_stream(app=_evicted_app, stream=_evicted_stream_id, node_id=_evicted_node_id or None))
                    except Exception as e:
                        # evicted ZLM stream close should log, not silently pass
                        logger.warning(f"Failed to close evicted ZLM stream {_evicted_stream_id}: {e}")
                if _evicted_lease_id:
                    try:
                        async def _release_evicted_lease(lid=_evicted_lease_id):
                            async with AsyncSessionLocal() as s:
                                await release_lease(s, lid)
                                await s.commit()
                        fire_and_forget(_release_evicted_lease())
                    except Exception as e:
                        # evicted lease release should log, not silently pass
                        logger.warning(f"Failed to release evicted lease {_evicted_lease_id}: {e}")
                res["ok"] = False
                res["status_code"] = 0
                res["reason"] = "evicted_from_overflow"
                ev.set()
    invite_state.invite_pending[call_id] = (event, result)
    return event, result


def on_invite_response(call_id: str, status_code: int, reason: str, sdp_body: str, to_tag: str | None = None, record_route: str | None = None, session_expires_header: str | None = None) -> None:
    entry = invite_state.invite_pending.pop(call_id, None)
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
                # P1-fix [2026-07-17]: 捕获当前 dialog_manager 引用到局部变量，
                # 避免 fire_and_forget 闭包在 patch 退出后访问到已被还原的模块级变量
                _dm = dialog_manager
                # GB28181协议 — 级联场景传递Record-Route头到dialog
                route_header = result.get("record_route", "")
                route_set = [route_header] if route_header else None
                fire_and_forget(_dm.confirm_dialog(
                    call_id, from_tag, to_tag, route_set=route_set,
                ))
                # P1-fix [2026-07-17]: SIP Session Timer (RFC 4028) — 协商 200 OK 中的 Session-Expires
                # GB28181-2016 兼容：无该头域时降级为现有行为，仅记录 debug 日志
                if session_expires_header:
                    try:
                        se_seconds, se_refresher = parse_session_expires(session_expires_header)
                    except Exception as _se_parse_err:
                        # FIX [2026-07-17 P3-9]: 描述性日志替代 "silently_swallowed_exception"
                        logger.warning(f"on_invite_response: failed to parse Session-Expires header call_id={call_id}: {_se_parse_err}")
                        se_seconds, se_refresher = 0, ""
                else:
                    # GB28181-2016 兼容降级：无 Session-Expires 头域
                    logger.debug(f"on_invite_response: 200 OK without Session-Expires (GB28181 degrade) call_id={call_id}")
                    se_seconds, se_refresher = 0, ""
                # UAC 侧 local_role=uac；refresher 未指定时按 RFC 4028 默认 uac 刷新
                refresher_role = (se_refresher or "uac") if se_seconds > 0 else ""

                async def _setup_session_timer(_cid: str, _ft: str, _exp: int, _ref: str) -> None:
                    """fire_and_forget 包装：写 Session Timer 状态并按需启动定时器。"""
                    try:
                        ok_set = await _dm.set_session_timer(
                            _cid, _ft,
                            expires=_exp,
                            refresher=_ref,
                            local_role="uac",
                        )
                        if ok_set:
                            # start_session_timer 内部已使用 fire_and_forget 调度任务
                            _dm.start_session_timer(_cid, _ft)
                            logger.debug(f"on_invite_response: session timer started call_id={_cid} expires={_exp} refresher={_ref}")
                    except Exception as _se_set_err:
                        # FIX [2026-07-17 P3-9]: 描述性日志替代 "silently_swallowed_exception"
                        logger.warning(f"on_invite_response: failed to set session timer call_id={_cid}: {_se_set_err}")

                fire_and_forget(
                    _setup_session_timer(call_id, from_tag, se_seconds, refresher_role),
                    name=f"session_timer_setup:{call_id}",
                )
        except Exception as e:
            logger.warning(f"Failed to confirm dialog for INVITE 2xx call_id={call_id}: {e}")  # 资源清理失败仅debug日志，提升为warning
    if status_code >= 300:
        try:
            from_tag = result.get("from_tag", "")
            if from_tag:
                fire_and_forget(dialog_manager.terminate_dialog(call_id, from_tag))
        except Exception as e:
            logger.warning(f"Failed to terminate dialog for INVITE error call_id={call_id}: {e}")  # 资源清理失败仅debug日志，提升为warning
        ssrc_val = result.get("ssrc", "")
        if ssrc_val:
            try:
                from app.sip.ssrc_manager import ssrc_manager as _sm
                fire_and_forget(_sm.release(ssrc_val))
            except Exception as e:
                logger.warning(f"Failed to release SSRC for INVITE error call_id={call_id}: {e}")  # 资源清理失败仅debug日志，提升为warning
            try:
                fire_and_forget(unregister_ssrc_waiter(ssrc_val))
            except Exception as e:
                logger.warning(f"Failed to unregister SSRC waiter for INVITE error call_id={call_id}: {e}")  # 资源清理失败仅debug日志，提升为warning
        stream_id_val = result.get("stream_id", "")
        app_val = result.get("app", "")
        node_id_val = result.get("node_id", "")
        if stream_id_val:
            try:
                from app.services.zlm_stream_control import close_zlm_stream as _close_stream
                fire_and_forget(_close_stream(app=app_val, stream=stream_id_val, node_id=node_id_val or None))
            except Exception as e:
                logger.warning(f"Failed to close ZLM stream for INVITE error call_id={call_id}: {e}")  # 资源清理失败仅debug日志，提升为warning
        lease_id_val = result.get("lease_id", "")
        if lease_id_val:
            try:
                async def _release_lease():
                    async with AsyncSessionLocal() as s:
                        await release_lease(s, lease_id_val)
                        await s.commit()
                fire_and_forget(_release_lease())
            except Exception as e:
                logger.warning(f"Failed to release lease for INVITE error call_id={call_id}: {e}")
        # INVITE非成功响应后清理StreamSession记录，防止DB残留僵尸会话
        session_id_val = result.get("session_id", "")
        if session_id_val:
            try:
                async def _delete_stale_session():
                    async with AsyncSessionLocal() as s:
                        from app.models.stream_session import StreamSession
                        from sqlalchemy import delete as sql_delete
                        await s.execute(sql_delete(StreamSession).where(StreamSession.id == session_id_val))
                        await s.commit()
                fire_and_forget(_delete_stale_session())
            except Exception as e:
                logger.warning(f"Failed to delete stale StreamSession for INVITE error call_id={call_id}: {e}")
    event.set()


def on_invite_provisional(call_id: str, status_code: int, reason: str) -> None:
    invite_state.invite_provisional[call_id] = {
        "status_code": status_code,
        "reason": reason,
        "timestamp": time.time(),
    }
    if len(invite_state.invite_provisional) > 5000:
        cutoff = time.time() - 60
        stale = [k for k, v in invite_state.invite_provisional.items() if v.get("timestamp", 0) < cutoff]
        for k in stale:
            invite_state.invite_provisional.pop(k, None)


async def wait_invite_response(call_id: str, timeout: float = 20.0) -> dict:
    # INVITE dual-timeout race - wait for event with slightly longer timeout than watchdog
    # so watchdog fires first and cleans up resources, then this returns the result
    entry = invite_state.invite_pending.get(call_id)
    if not entry:
        return {}
    event, result = entry
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout + 2.0)
        return result
    except asyncio.TimeoutError:
        # if timeout reached, try to pop and clean up (watchdog may not have fired yet)
        pending = invite_state.invite_pending.pop(call_id, None)
        if pending:
            _, pending_result = pending
            cancel_invite_watchdog(call_id)
            pending_result["ok"] = False
            pending_result["reason"] = "wait_timeout"
            # P2 资源泄漏 — 超时后释放SSRC/lease
            _timeout_ssrc = pending_result.get("ssrc", "")
            if _timeout_ssrc:
                try:
                    from app.sip.ssrc_manager import ssrc_manager as _sm
                    fire_and_forget(_sm.release(_timeout_ssrc))
                except Exception as e:
                    logger.warning(f"Failed to release SSRC for INVITE timeout call_id={call_id}: {e}")
                try:
                    fire_and_forget(unregister_ssrc_waiter(_timeout_ssrc))
                except Exception as e:
                    logger.warning(f"Failed to unregister SSRC waiter for INVITE timeout call_id={call_id}: {e}")
            _timeout_lease_id = pending_result.get("lease_id", "")
            if _timeout_lease_id:
                try:
                    async def _release_timeout_lease():
                        async with AsyncSessionLocal() as s:
                            await release_lease(s, _timeout_lease_id)
                            await s.commit()
                    fire_and_forget(_release_timeout_lease())
                except Exception as e:
                    logger.warning(f"Failed to release lease for INVITE timeout call_id={call_id}: {e}")
            _timeout_stream_id = pending_result.get("stream_id", "")
            _timeout_app = pending_result.get("app", "")
            _timeout_node_id = pending_result.get("node_id", "")
            if _timeout_stream_id:
                try:
                    from app.services.zlm_stream_control import close_zlm_stream as _close_stream
                    fire_and_forget(_close_stream(app=_timeout_app, stream=_timeout_stream_id, node_id=_timeout_node_id or None))
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
    except Exception as e:
        # FIX [2026-07-19 P1]: 原 except 静默 return False，SSRC 等待失败无法诊断。
        # 区分超时与异常：超时由 wait_ssrc_stream 返回 False，此处仅为后端调用异常。
        logger.warning(f"wait_ssrc_stream backend call failed ssrc={ssrc}: {e}")
        return False
    finally:
        try:
            backend = get_sip_state_backend()
            await backend.unregister_ssrc_waiter(ssrc)
        except Exception as e:
            logger.warning(f"SIP Invite SSRC unregister failed: {e}")  # 国际化


async def register_ssrc_waiter(ssrc: str) -> None:
    key = str(ssrc or "").strip()
    if not key:
        return
    try:
        backend = get_sip_state_backend()
        await backend.register_ssrc_waiter(ssrc)
    except Exception as e:
        logger.warning(f"SIP Invite SSRC register failed: {e}")  # 国际化


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
    except ValueError:
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
    except ImportError:
        return None
    return getattr(sip_transactions, "client_tx_manager", None) or getattr(sip_transactions, "tx_manager", None)


async def _check_and_consume_invite_rate(tenant_id: str, device_id: str) -> tuple[bool, str]:
    # FIX [2026-07-19 P1]: 移除 getattr 动态兜底——SIP_INVITE_RATE_LIMIT_* 已在
    # Settings 类明确定义（config.py:449-451），违反硬约束 #41。
    # 测试桩通过 conftest.py 预加载真实 settings + 仅注入缺失字段模式，不会移除这些属性。
    try:
        window = float(settings.SIP_INVITE_RATE_LIMIT_WINDOW_SECONDS)
        per_device = int(settings.SIP_INVITE_RATE_LIMIT_PER_DEVICE)
        per_tenant = int(settings.SIP_INVITE_RATE_LIMIT_PER_TENANT)
    except (TypeError, ValueError) as cfg_err:
        logger.error(f"INVITE rate limit config invalid, denying request (fail-closed): {cfg_err}")
        return False, "rate_limit_config_error"
    if window <= 0:
        invite_state.invite_rate_stats["allowed"] = int(invite_state.invite_rate_stats.get("allowed", 0) or 0) + 1
        return True, ""
    try:
        backend = get_sip_state_backend()
        allowed, reason = await backend.consume_invite_rate(
            tenant_id, device_id, window=window, per_device=per_device, per_tenant=per_tenant
        )
    except Exception as rate_err:
        # 限流后端异常时默认拒绝（fail-closed），防止高并发下限流失效
        logger.error(f"INVITE rate limit backend error, denying request (fail-closed): {rate_err}")
        invite_state.invite_rate_stats.setdefault("backend_error", 0)
        invite_state.invite_rate_stats["backend_error"] = int(invite_state.invite_rate_stats.get("backend_error", 0) or 0) + 1
        return False, "rate_limit_backend_error"
    if allowed:
        invite_state.invite_rate_stats.setdefault("allowed", 0)
        invite_state.invite_rate_stats["allowed"] = int(invite_state.invite_rate_stats.get("allowed", 0) or 0) + 1
    else:
        if "device" in reason:
            invite_state.invite_rate_stats.setdefault("blocked_device", 0)
            invite_state.invite_rate_stats["blocked_device"] = int(invite_state.invite_rate_stats.get("blocked_device", 0) or 0) + 1
        elif "tenant" in reason:
            invite_state.invite_rate_stats.setdefault("blocked_tenant", 0)
            invite_state.invite_rate_stats["blocked_tenant"] = int(invite_state.invite_rate_stats.get("blocked_tenant", 0) or 0) + 1
    return allowed, reason


def get_invite_rate_limit_metrics() -> dict:
    _backend_type = (settings.SIP_STATE_BACKEND or "local").strip().lower()
    return {
        "window_seconds": settings.SIP_INVITE_RATE_LIMIT_WINDOW_SECONDS,
        "per_device_limit": settings.SIP_INVITE_RATE_LIMIT_PER_DEVICE,
        "per_tenant_limit": settings.SIP_INVITE_RATE_LIMIT_PER_TENANT,
        "backend_type": _backend_type,
        "stats": {
            "allowed": int(invite_state.invite_rate_stats.get("allowed", 0) or 0),
            "blocked_device": int(invite_state.invite_rate_stats.get("blocked_device", 0) or 0),
            "blocked_tenant": int(invite_state.invite_rate_stats.get("blocked_tenant", 0) or 0),
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
                # P1-fix [2026-07-17]: 渐进式回退策略，避免 TCP-ACTIVE 直接跳到 UDP
                # 原代码：任何非 UDP 模式失败都直接回退到 UDP，跳过 TCP-PASSIVE 中间过渡。
                # 某些设备 TCP-ACTIVE 不支持但 TCP-PASSIVE 可用，直接跳 UDP 降低传输可靠性。
                # 新策略：TCP-ACTIVE → TCP-PASSIVE → UDP 三级回退
                if current_mode == "TCP_ACTIVE":
                    fallback_mode = "TCP-PASSIVE"
                elif current_mode == "TCP_PASSIVE":
                    fallback_mode = "UDP"
                elif current_mode != "UDP":
                    fallback_mode = "UDP"
                else:
                    fallback_mode = ""
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
        logger.warning(f"Retried INVITE with fallback mode {fallback_mode} (from {current_mode}) for device {asset.gb_id}")
        return True

    async def _cleanup_ssrc_reserves(self, max_age_seconds: int = 300) -> int:
        try:
            async with AsyncSessionLocal() as session:
                cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=max_age_seconds)
                # FIX [2026-07-17 P0]: StreamSession 模型只有 start_time 列，不存在 created_at
                # （已确认 stream_session.py 模型定义）。原代码引用 StreamSession.created_at 会抛
                # AttributeError，被外层 `except Exception: return 0` 静默吞掉，
                # 导致 _ssrc_reserve 清理永远不执行——过期预留条目无限累积，DB 膨胀，
                # 且 _migrate_ssrc_reserves（无时间过滤的全量删除）虽能清理但无法区分新旧。
                # session.py 的 _before_cursor_execute_strip_tzinfo 事件会自动将 cutoff 的
                # tzinfo 去除，确保与 naive start_time 列的比较在 SQLite/PostgreSQL 上均正确。
                stmt = delete(StreamSession).where(
                    StreamSession.app == "_ssrc_reserve",
                    StreamSession.start_time < cutoff,
                )
                result = await session.execute(stmt)
                await session.commit()
                return result.rowcount
        except Exception as e:
            # FIX [2026-07-19 P1]: 原 except 静默 return 0，DB 清理失败无法诊断。
            logger.warning(f"_cleanup_ssrc_reserves failed: {e}")
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
        except Exception as e:
            # FIX [2026-07-19 P1]: 原 except 静默 return 0，迁移失败无法诊断。
            logger.warning(f"_migrate_ssrc_reserves failed: {e}")
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
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={stream_session.from_tag}"
        req.headers["To"] = f"<sip:{channel_gb_id}@{sip_from_to_host()}>;tag={stream_session.to_tag}"
        req.headers["Call-ID"] = stream_session.call_id
        req.headers["CSeq"] = f"{cseq_num} INVITE"
        req.headers["Contact"] = f"<sip:{settings.SIP_ID}@{sip_host_for_contact()}:{settings.SIP_PORT}>"
        req.headers["Content-Type"] = "application/sdp"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME

        stream_type_code = "1" if target_stream_type == "sub" else "0"
        subject_base = f"{channel_gb_id}:{stream_session.ssrc},{settings.SIP_ID}:{stream_type_code}"

        enable_track_in_subject = settings.GB28181_STREAM_SWITCH_USE_TRACK_SUBJECT
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
        # P1-fix: Re-INVITE 的 f= 行应与初始 INVITE 保持一致，原 f=v/0 表示媒体参数全 0，
        # 部分设备（海康/大华）会因 f= 行参数缺失而拒绝 Re-INVITE 或切换到不兼容的编码
        _reinvite_f_line = f"f=v/2/4/{settings.GB28181_VIDEO_QUALITY}/1/0a/0/0/0"
        sdp_str = _build_sdp(
            origin_id=channel_gb_id,
            session_name="Play",
            connection_ip=sdp_ip,
            media_type="video",
            media_port=rtp_port,
            media_profile=media_profile,
            direction="recvonly",
            ssrc=ssrc_str,
            f_line=_reinvite_f_line,
            # FIX [2026-07-17 P1-C1]: Re-INVITE 必须包含 a=rtpmap:96 PS/90000 等媒体格式映射，
            # 否则部分设备（海康/大华）因缺少 rtpmap 而拒绝 Re-INVITE 或发送不兼容的码流。
            extended_rtpmap=True,
            setup=setup_val,
            # FIX [2026-07-17 P1-C2]: Re-INVITE 的 sess-version 必须递增（RFC 4566 §5.2），
            # 使用 cseq_num 作为 sess-version，与 SIP CSeq 递增保持一致。
            sess_version=cseq_num,
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
        async with invite_state.stream_switch_lock:
            if len(invite_state.stream_switch_pending) > invite_state.stream_switch_pending_max:
                oldest_keys = list(invite_state.stream_switch_pending.keys())[:100]
                for k in oldest_keys:
                    invite_state.stream_switch_pending.pop(k, None)
                    invite_state.stream_switch_pending_timestamps.pop(k, None)
            _now = time.time()
            _stale_keys = [k for k, t in invite_state.stream_switch_pending_timestamps.items() if _now - t > invite_state.stream_switch_pending_ttl]
            for _k in _stale_keys:
                invite_state.stream_switch_pending.pop(_k, None)
                invite_state.stream_switch_pending_timestamps.pop(_k, None)
            invite_state.stream_switch_pending[stream_session.call_id or ""] = target_stream_type
            invite_state.stream_switch_pending_timestamps[stream_session.call_id or ""] = time.time()
            if not is_rollback:
                invite_state.stream_switch_rollback_depth.pop(stream_session.call_id or "", None)

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
        _STREAM_SWITCH_ROLLBACK_DEPTH_MAX_RETRIES = 3  # GB28181协议 — 码流切换回退深度从1增加到3
        async with invite_state.stream_switch_lock:  # W-06-02 回退深度读取和修改移入锁内，防止并发回退突破重试限制
            depth = invite_state.stream_switch_rollback_depth.get(call_id, 0)
            if depth >= _STREAM_SWITCH_ROLLBACK_DEPTH_MAX_RETRIES:
                logger.error(f"[Stream Switch] Rollback depth limit reached for {call_id}, stopping to prevent infinite loop")
                invite_state.stream_switch_pending.pop(call_id, None)
                invite_state.stream_switch_pending_timestamps.pop(call_id, None)
                invite_state.stream_switch_rollback_depth.pop(call_id, None)
                return
            target_type = saved_target_type or invite_state.stream_switch_pending.pop(call_id, None)
            invite_state.stream_switch_pending_timestamps.pop(call_id, None)
            invite_state.stream_switch_rollback_depth[call_id] = depth + 1
            invite_state.stream_switch_rollback_depth_timestamps[call_id] = time.time()

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
                await self.send_stream_switch_reinvite(ss, original_type, is_rollback=True)
        except Exception as e:
            logger.error(f"[Stream Switch] Rollback failed for {call_id}: {e}")
            invite_state.stream_switch_rollback_depth.pop(call_id, None)

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

                # FIX: [2026-07-03] 传入 stream_id/app_name 用于孤儿租约清理 [全栈工程师]
                rtp_port, lease_id = await allocate_rtp_port_with_lease(
                    session, target_node,
                    stream_id=stream_session.stream, app_name=stream_session.app,
                )
                if not rtp_port:
                    logger.error("[HA Failover] Failed to allocate port on new node")
                    return False

                try:
                    # P0-02: target_node 可能是 ORM MediaNode(密文) 或 RuntimeMediaNode(明文)，
                    # 优先用 decrypted_secret；RuntimeMediaNode 无此属性则回退到 .secret（已是明文）
                    _target_secret = getattr(target_node, 'decrypted_secret', None) or target_node.secret
                    # P0-fix [2026-07-17]: HA Failover Re-INVITE 必须正确映射 tcp_mode 三态
                    # 原代码对所有 TCP* 协议都传 tcp_mode=1（TCP-PASSIVE），TCP-ACTIVE 被降级，
                    # SDP 中 setup=active 与 ZLM RTP server passive 模式不一致，TCP-ACTIVE 流无法建立。
                    # 对照 _send_invite_common_inner line 2301-2305 的三态映射：
                    #   UDP           → tcp_mode=0
                    #   TCP-PASSIVE   → tcp_mode=1
                    #   TCP-ACTIVE    → tcp_mode=2
                    _proto_str = str(getattr(stream_session, 'protocol', '') or '').upper().replace("-", "_")
                    if _proto_str.startswith("TCP_ACTIVE") or _proto_str == "TCP_ACTIVE":
                        _ha_tcp_mode = 2
                    elif _proto_str.startswith("TCP"):
                        _ha_tcp_mode = 1
                    else:
                        _ha_tcp_mode = 0
                    await open_rtp_server(
                        host=target_node.host,
                        http_port=target_node.http_port,
                        secret=_target_secret,
                        port=rtp_port,
                        tcp_mode=_ha_tcp_mode,
                        app=stream_session.app,
                        stream_id=stream_session.stream,
                        ssrc="0",
                        re_use_port=False,  # P0-fix: 使用布尔值而非字符串 "0"，避免 truthy 误判
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
                req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={branch}"
                req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={stream_session.from_tag}"
                req.headers["To"] = f"<sip:{channel_gb_id}@{sip_from_to_host()}>;tag={stream_session.to_tag}"
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
                # P1-fix: HA 故障转移 Re-INVITE 的 f= 行应与初始 INVITE 保持一致
                _ha_reinvite_f_line = f"f=v/2/4/{settings.GB28181_VIDEO_QUALITY}/1/0a/0/0/0"
                sdp_str = _build_sdp(
                    origin_id=channel_gb_id,
                    session_name="Play",
                    connection_ip=sdp_ip,
                    media_type="video",
                    media_port=rtp_port,
                    media_profile=media_profile,
                    direction="recvonly",
                    ssrc=ssrc_str,
                    f_line=_ha_reinvite_f_line,
                    # FIX [2026-07-17 P2-2]: HA 故障转移 Re-INVITE 也必须包含 a=rtpmap（P1-C1 同类），
                    # 且 sess-version 必须递增（P1-C2 同类），否则设备忽略 Re-INVITE 导致故障转移失败。
                    extended_rtpmap=True,
                    setup=setup_val,
                    sess_version=cseq_num,
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
            logger.warning("[SipInvite BYE] Failed to get transport for asset")
            return False

        if not transport:
            logger.warning(f"[SipInvite BYE] No transport available for {addr[0]}:{addr[1]}/{proto}")
            return False

        device_id = str(getattr(asset, "gb_id", channel_id) or channel_id)
        call_id = str(getattr(stream_session, "call_id", "") or "").strip()
        if not call_id:
            logger.warning("[SipInvite BYE] No call_id for session")
            return False

        from_tag = str(getattr(stream_session, "from_tag", "") or "").strip()
        if not from_tag:
            logger.warning(f"[SipInvite BYE] No from_tag for session {call_id}")
            from_tag = "untagged"

        to_tag = str(getattr(stream_session, "to_tag", "") or "").strip()
        to_header = f"<sip:{channel_id or device_id}@{sip_from_to_host()}>"
        if to_tag:
            to_header = f"{to_header};tag={to_tag}"

        branch = f"z9hG4bK{secrets.token_hex(10)}"
        cseq = int(getattr(stream_session, "cseq", 1) or 1) + 1

        req = SipMessage()
        req.method = "BYE"
        req.uri = f"sip:{device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={from_tag}"
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

                # FIX [2026-09-01 P1]: 必须为 async — server.process_message 对所有
                # response handler 统一 await，同步函数返回 bool 会触发
                # "object bool can't be used in 'await' expression"。
                async def _bye_response_handler(msg: SipMessage, addr_t: tuple, proto_t: str, transport_t):
                    if msg.get_header("Call-ID") != call_id:
                        return False
                    # W-03 BYE response handler must also check CSeq method is BYE to avoid mismatch
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
                    # BYE超时返回False而非True，让调用方知道设备未确认BYE
                    return False
                finally:
                    self.sip_server.unregister_response_handler(_bye_response_handler)
            except Exception as e:
                logger.warning(f"[SipInvite BYE] Error sending BYE via tx_manager: {e}, falling back to direct send")
                try:
                    await send_sip_bytes(proto, transport, addr, data)
                except Exception as e2:
                    logger.error(f"[SipInvite BYE] Direct send also failed: {e2}")
                    return False  # send_bye 发送失败时应返回 False
        else:
            try:
                await send_sip_bytes(proto, transport, addr, data)
            except Exception as e:
                logger.error(f"[SipInvite BYE] Direct send failed: {e}")
                return False  # 非UDP直接发送失败时返回False

        logger.info(f"[SipInvite BYE] Sent BYE to {device_id} call_id={call_id}")
        return True

    async def send_cascade_invite(
        self, asset, resource, transport_info: tuple, sdp_body: str, *, session_name: str = "Play"
    ) -> dict:
        (addr, proto, transport) = transport_info
        channel_id = resource.gb_id
        call_id = f"cascade_{uuid.uuid4().hex[:16]}"
        from_tag = uuid.uuid4().hex[:8]
        branch = f"z9hG4bK{uuid.uuid4().hex[:12]}"
        invite_state.cascade_call_ids[call_id] = time.time()  # FIX [2026-07-17 P1-B3]: dict 替代 set，记录时间戳

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
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={from_tag}"
        req.headers["To"] = f"<sip:{channel_id}@{sip_from_to_host()}>"
        req.headers["Call-ID"] = call_id
        # FIX [2026-07-17 P1]: CSeq 单调递增（RFC 3261 §22.2），原硬编码 "1 INVITE"
        # 在进程重启后 CSeq 归零，可能与同对话内历史请求冲突。
        _invite_cseq = _next_cseq()
        req.headers["CSeq"] = f"{_invite_cseq} INVITE"
        req.headers["Content-Type"] = "application/sdp"
        req.headers["Contact"] = f"<sip:{settings.SIP_ID}@{sip_host_for_contact()}:{settings.SIP_PORT}>"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        req.headers["Max-Forwards"] = "70"

        ssrc = await self._generate_ssrc(settings.SIP_DOMAIN, is_playback=(session_name == "Playback"))
        # SSRC allocation may return empty string when exhausted — fail fast instead of sending invalid INVITE
        if not ssrc:
            raise HTTPException(status_code=503, detail="SSRC allocation exhausted, cannot start cascade stream")
        stream_type_code = "0"
        req.headers["Subject"] = f"{channel_id}:{ssrc},{settings.SIP_ID}:{stream_type_code}"

        # 级联INVITE需创建RTP服务端接收上级平台推流
        _cascade_rtp_port = None
        _cascade_lease_id = None
        _cascade_node = None
        try:
            _cascade_node = await select_best_node()
            if _cascade_node:
                async with AsyncSessionLocal() as _c_session:
                    # FIX: [2026-07-03] 传入 stream_id/app_name 用于孤儿租约清理 [全栈工程师]
                    _cascade_stream_id = f"{channel_id}_{ssrc}"
                    _cascade_rtp_port, _cascade_lease_id = await allocate_rtp_port_with_lease(
                        _c_session, _cascade_node,
                        stream_id=_cascade_stream_id, app_name="cascade",
                    )
                if _cascade_rtp_port:
                    # P1-fix [2026-07-17]: 级联 INVITE 必须支持 TCP-ACTIVE 模式
                    # 原代码 _tcp_mode = 1 if is_tcp else 0 仅支持 TCP-PASSIVE，
                    # 若上级平台 SDP setup=passive 要求本端主动连接，则 TCP-ACTIVE 流无法建立。
                    # 根据 RFC 4145 §5 协商规则：
                    #   对端 setup=active   → 本端 passive → tcp_mode=1
                    #   对端 setup=passive  → 本端 active  → tcp_mode=2
                    #   对端 setup=actpass  → 本端默认 passive → tcp_mode=1（更安全）
                    if not is_tcp:
                        _tcp_mode = 0
                    elif setup_attr and str(setup_attr).strip().lower() == "passive":
                        _tcp_mode = 2  # 对端被动，本端主动连接
                    else:
                        _tcp_mode = 1  # 默认本端被动监听
                    await open_rtp_server(
                        host=_cascade_node.host,
                        http_port=_cascade_node.http_port,
                        secret=_cascade_node.secret,
                        port=_cascade_rtp_port,
                        tcp_mode=_tcp_mode,
                        app="cascade",
                        stream_id=f"{channel_id}_{ssrc}",
                        ssrc="0",
                    )
                    logger.info(f"[Cascade INVITE] Opened RTP server on node={_cascade_node.host}:{_cascade_rtp_port} tcp={_tcp_mode} (peer_setup={setup_attr})")
        except Exception as _rtp_err:
            logger.warning(f"[Cascade INVITE] Failed to create RTP server for cascade: {_rtp_err}")
            if _cascade_lease_id:
                try:
                    async with AsyncSessionLocal() as _rl_session:
                        await release_lease(_rl_session, _cascade_lease_id)
                except Exception as _lease_err:
                    logger.warning(f"[Cascade INVITE] Failed to release lease {_cascade_lease_id}: {_lease_err}")
            _cascade_rtp_port = None
            _cascade_lease_id = None
            # FIX: [2026-07-16] RTP server 创建失败时必须中止 INVITE。
            # 原问题：失败后继续用 recv_port or 0 作为 SDP 端口，上级平台收到端口 0
            # 的 SDP 无法推流，播放黑屏。应直接返回错误。
            # FIX: [2026-07-16] 变量名修正：_ssrc → ssrc（原代码变量名错误导致 NameError，
            # SSRC 无法释放，且 HTTPException 不会抛出）。
            if ssrc:
                try:
                    await ssrc_manager.release(ssrc)
                except Exception as _ssrc_release_err:
                    # FIX: [2026-07-16 P0] 原异常被 pass 静默吞掉，SSRC 资源泄漏
                    # 会导致后续 INVITE 全部失败（资源耗尽）。必须记录日志便于排查。
                    logger.error(f"[Cascade INVITE] SSRC release failed after RTP server creation failure: ssrc={ssrc} error={_ssrc_release_err}")
            from fastapi import HTTPException as _FastApiHTTPException
            raise _FastApiHTTPException(status_code=503, detail="Failed to allocate RTP port for cascade stream")

        setup_val = None
        if is_tcp:
            if setup_attr == "active":
                setup_val = "passive"
            elif setup_attr == "passive":
                setup_val = "active"
            else:
                setup_val = "passive"

        _sdp_port = _cascade_rtp_port if _cascade_rtp_port else (recv_port or 0)
        _sdp_ip = (_cascade_node.sdp_ip or _cascade_node.host) if _cascade_node and _cascade_rtp_port else recv_ip
        req.body = _build_sdp(
            origin_id=channel_id,
            session_name=session_name,
            connection_ip=_sdp_ip,
            media_type="video",
            media_port=_sdp_port,
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
                result_container["sdp_response"] = msg.body if msg.body else ""  # C-17 msg.body已是str，无需decode
                result_container["status_code"] = 200
                result_container["invite_ok"] = True
                to_hdr = msg.get_header("To") or ""
                m = re.search(r";\s*tag=([^;>\s]+)", to_hdr, re.IGNORECASE)
                if m:
                    result_container["to_tag"] = m.group(1).strip()
                try:
                    from_hdr = req.headers.get("From", "")
                    ft_match = re.search(r";\s*tag=([^;>\s]+)", from_hdr, re.IGNORECASE)
                    from_tag_val = ft_match.group(1).strip() if ft_match else ""
                    to_tag_val = result_container.get("to_tag", "")
                    if from_tag_val:
                        fire_and_forget(dialog_manager.create_dialog(call_id, from_tag_val, session_data={"cascade": True}))
                        if to_tag_val:
                            # GB28181协议 — 级联场景传递Record-Route头到dialog
                            _cascade_rr = msg.get_header("Record-Route") if hasattr(msg, 'get_header') else None
                            _cascade_route_set = [_cascade_rr] if _cascade_rr else None
                            fire_and_forget(dialog_manager.confirm_dialog(call_id, from_tag_val, to_tag_val, route_set=_cascade_route_set))
                except Exception as dlg_err:
                    logger.warning(f"Cascade INVITE dialog registration failed: {dlg_err}")
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
                        fire_and_forget(dialog_manager.terminate_dialog(call_id, from_tag_val))
                except Exception as e:
                    logger.warning(f"Exception: {e}")
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
            # FIX: [2026-07-16] 级联 INVITE 场景下，下级平台需再向设备发 INVITE，
            # 整个链路可能需要 15-30 秒，原 20 秒超时可能导致级联点播失败。
            await asyncio.wait_for(event.wait(), timeout=settings.SIP_CASCADE_INVITE_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            logger.warning(f"[Cascade INVITE] Timeout for {channel_id} call_id={call_id}")
            await _send_cancel(addr, proto, transport, call_id, from_tag, branch, channel_id)
            try:
                from_hdr = req.headers.get("From", "")
                ft_match = re.search(r";\s*tag=([^;>\s]+)", from_hdr, re.IGNORECASE)
                from_tag_val = ft_match.group(1).strip() if ft_match else ""
                if from_tag_val:
                    fire_and_forget(dialog_manager.terminate_dialog(call_id, from_tag_val))
            except Exception as e:
                logger.warning(f"Exception: {e}")
            # 级联INVITE超时释放RTP端口租约和SSRC
            if _cascade_lease_id:
                try:
                    async with AsyncSessionLocal() as _rl_session:
                        await release_lease(_rl_session, _cascade_lease_id)
                except Exception as _lease_err:
                    logger.warning(f"[Cascade INVITE] Failed to release lease {_cascade_lease_id}: {_lease_err}")
        except asyncio.CancelledError:
            # CancelledError下释放SSRC，防止泄漏
            logger.warning(f"[Cascade INVITE] Cancelled for {channel_id} call_id={call_id}")
            if ssrc:
                try:
                    await ssrc_manager.release(ssrc)
                except Exception as _ssrc_err:
                    logger.warning(f"[Cascade INVITE] Failed to release SSRC {ssrc}: {_ssrc_err}")
            ssrc = None  # 标记已释放
            # CancelledError下释放端口租约
            if _cascade_lease_id:
                try:
                    async with AsyncSessionLocal() as _rl_session:
                        await release_lease(_rl_session, _cascade_lease_id)
                except Exception as _lease_err:
                    logger.warning(f"[Cascade INVITE] Failed to release lease {_cascade_lease_id}: {_lease_err}")
            # P1-fix [2026-07-17]: CancelledError 路径必须清理 cascade_call_ids
            # 原代码仅在正常路径（line 1584）清理，CancelledError raise 后该清理不会执行，
            # 活跃级联 INVITE 在 300 秒 TTL 窗口内无法匹配响应，导致资源泄漏和流异常中断。
            try:
                invite_state.cascade_call_ids.pop(call_id, None)
            except Exception as _cascade_pop_err:
                logger.warning(f"[Cascade INVITE] Failed to pop cascade_call_ids for {call_id}: {_cascade_pop_err}")
            raise
        except Exception as e:
            logger.error(f"[Cascade INVITE] Error: {e}")
        finally:
            self.sip_server.unregister_response_handler(_cascade_response_handler)

        # 级联INVITE失败时统一释放端口租约（超时/取消路径已在各自分支释放）
        if not result_container["invite_ok"] and _cascade_lease_id:
            try:
                async with AsyncSessionLocal() as _rl_session:
                    await release_lease(_rl_session, _cascade_lease_id)
            except Exception as _lease_err:
                logger.warning(f"[Cascade INVITE] Failed to release lease on failure path: {_lease_err}")

        if result_container["invite_ok"]:
            ack = SipMessage()
            ack.method = "ACK"
            ack.uri = req.uri
            ack.version = "SIP/2.0"
            ack.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch=z9hG4bK{secrets.token_hex(8)}"  # FIX [2026-07-21 P0]: 无后缀，兼容 EasyGBS 等非标准客户端
            ack.headers["From"] = req.headers["From"]
            ack.headers["To"] = f"<sip:{channel_id}@{sip_from_to_host()}>;tag={result_container['to_tag']}" if result_container["to_tag"] else req.headers["To"]
            ack.headers["Call-ID"] = call_id
            # FIX [2026-07-17 P1]: ACK 的 CSeq 必须与对应 INVITE 的 CSeq 一致（RFC 3261 §22.2）
            ack.headers["CSeq"] = f"{_invite_cseq} ACK"
            ack.headers["Max-Forwards"] = "70"
            ack.headers["User-Agent"] = settings.PROJECT_NAME
            ack_sent_ok = False
            try:
                ack_sent_ok = await send_sip_bytes(proto, transport, addr, ack.to_bytes())
                if ack_sent_ok:
                    logger.info(f"[Cascade INVITE] Sent ACK for call_id={call_id}")
            except Exception as e:
                logger.warning(f"[Cascade INVITE] Failed to send ACK: {e}")
            # R24-07: ACK 失败时发送 BYE 清理半开 dialog（RFC 3261 §13.2.2.4），
            # 否则对端认为会话已建立而本地无对应状态，导致资源泄漏
            if not ack_sent_ok:
                try:
                    bye_req = SipMessage()
                    bye_req.method = "BYE"
                    bye_req.uri = req.uri
                    bye_req.version = "SIP/2.0"
                    bye_req.headers["Via"] = ack.headers["Via"]
                    bye_req.headers["From"] = ack.headers["From"]
                    bye_req.headers["To"] = ack.headers["To"]
                    bye_req.headers["Call-ID"] = call_id
                    bye_req.headers["CSeq"] = f"{_invite_cseq + 1} BYE"  # FIX [2026-07-21 P0]: CSeq 应为 INVITE CSeq+1，而非硬编码 2
                    bye_req.headers["Max-Forwards"] = "70"
                    await send_sip_bytes(proto, transport, addr, bye_req.to_bytes())
                    logger.info(f"[Cascade INVITE] Sent BYE cleanup after ACK failure, call_id={call_id}")
                except Exception as bye_err:
                    logger.warning(f"[Cascade INVITE] BYE cleanup after ACK failure also failed: {bye_err}")
                # ACK 失败视为会话未建立，释放 SSRC
                if ssrc:
                    try:
                        await ssrc_manager.release(ssrc)
                    except Exception as e:
                        logger.warning(f"Cascade INVITE SSRC release after ACK failure: {e}")

        if not result_container["invite_ok"] and ssrc:
            try:
                await ssrc_manager.release(ssrc)
            except Exception as e:
                logger.warning(f"Cascade INVITE SSRC release failed: {e}")

        invite_state.cascade_call_ids.pop(call_id, None)  # FIX [2026-07-17 P1-B3]: dict.pop 替代 set.discard
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
        # SSRC allocation may return empty string when exhausted — fail fast instead of sending invalid INVITE
        if not ssrc:
            raise HTTPException(status_code=503, detail="SSRC allocation exhausted, cannot start talk stream")
        stream_id = f"{channel_id}_talk_{ssrc}"
        app_name = "talk"

        subject_header = f"{channel_id}:{ssrc},{settings.SIP_ID}:0"

        call_id = f"{secrets.token_hex(8)}@{sip_via_host()}"  # FIX [2026-07-29 P1]: token_hex(10)→token_hex(8) 统一 64 位随机性
        tag = secrets.token_hex(8)
        branch = f"z9hG4bK{secrets.token_hex(8)}"

        if "y=" not in sdp_body:
            # FIX: [2026-07-17 P1] SDP 行结束符使用 CRLF（RFC 4566 §5 要求）
            sdp_body += f"y={str(ssrc).zfill(10)}\r\n"

        req = SipMessage()
        req.method = "INVITE"
        req.uri = f"sip:{channel_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"

        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={tag}"
        req.headers["To"] = f"<sip:{channel_id}@{sip_from_to_host()}>"
        req.headers["Call-ID"] = call_id
        # FIX [2026-07-17 P1]: CSeq 单调递增（RFC 3261 §22.2）
        _invite_cseq2 = _next_cseq()
        req.headers["CSeq"] = f"{_invite_cseq2} INVITE"
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
            # StreamSession保存失败时释放SSRC，防止泄漏
            if ssrc:
                try:
                    await ssrc_manager.release(ssrc)
                except Exception as _ssrc_err:
                    logger.warning(f"[Cascade INVITE] Failed to release SSRC {ssrc}: {_ssrc_err}")
            raise HTTPException(status_code=500, detail="Failed to save session")

        tx_manager = _get_client_tx_manager()
        if tx_manager is None:
            # tx_manager不可用时释放SSRC，防止泄漏
            if ssrc:
                try:
                    await ssrc_manager.release(ssrc)
                except Exception as _ssrc_err:
                    logger.warning(f"[Cascade INVITE] Failed to release SSRC {ssrc}: {_ssrc_err}")
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
                "device_id": device_id,  # FIXED-P0: 添加 device_id，使 terminate_dialogs_by_device 能匹配到 Dialog
            },
        )

        try:
            resp, meta = await tx_manager.send_and_wait(
                request=req,
                send_once=lambda: send_sip_bytes(proto, transport, addr, req.to_bytes()),
                timeout_seconds=settings.SIP_INVITE_TIMEOUT_SECONDS,
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
                    logger.warning(f"Exception: {e}")
                raise Exception(f"Talk INVITE rejected with {resp.status_code}")

            # Send ACK
            ack = SipMessage()
            ack.method = "ACK"
            ack.uri = req.uri
            ack.version = "SIP/2.0"
            ack.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch=z9hG4bK{secrets.token_hex(8)}"  # FIX [2026-07-21 P0]: 无后缀，兼容 EasyGBS 等非标准客户端
            ack.headers["From"] = req.headers["From"]
            ack.headers["To"] = resp.get_header("To") or req.headers["To"]
            ack.headers["Call-ID"] = req.headers["Call-ID"]
            # FIX [2026-07-17 P1]: ACK 的 CSeq 必须与对应 INVITE 的 CSeq 一致（RFC 3261 §22.2）
            ack.headers["CSeq"] = f"{_invite_cseq2} ACK"
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
                    logger.warning(f"Exception: {e}")

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
                logger.warning(f"Exception: {e}")
            try:
                async with AsyncSessionLocal() as session:
                    ss = (await session.execute(select(StreamSession).where(StreamSession.id == stream_session_id))).scalars().first()
                    if ss:
                        await session.delete(ss)
                        await session.commit()
            except Exception as cleanup_err:
                logger.error(f"Talk INVITE cleanup DB error: {cleanup_err}")
            # W-03 对讲INVITE失败时终止Dialog，防止僵尸Dialog
            try:
                await dialog_manager.terminate_dialog(call_id, tag)
            except Exception as _dlg_err:
                logger.warning(f"Talk INVITE cleanup dialog error: {_dlg_err}")
            raise HTTPException(status_code=503, detail=f"Talk request failed: {e}")  # i18n

    async def _select_media_node(self, session) -> tuple:
        node_id = None
        media_ip = None
        media_port = None
        db_node = None
        selection_reason = "unknown"
        try:
            db_nodes = await list_db_media_nodes(session)
            if (
                settings.GB28181_AUTO_ENSURE_EMBEDDED_MEDIA_NODE
                and settings.EMBEDDED_ZLM_ENABLED
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
        # R25 Stream-3: 移除 session 参数，DB 操作使用短生命周期 AsyncSessionLocal，
        # ZLM HTTP 慢 I/O 期间不持有任何 DB 连接，避免多路并发播放时连接池耗尽报错。
        lease_id = None
        zlm_res = None
        last_err_msg = ""
        excluded_nodes = []
        base_ssrc_check = ssrc_check_enabled

        max_node_retries = settings.SIP_INVITE_ZLM_MAX_NODE_RETRIES
        max_node_retries = max(1, min(max_node_retries, 10))

        for attempt in range(max_node_retries):
            attempt_lease_id = None
            mode = str(getattr(db_node, "rtp_port_mode", "single") or "single").lower()

            if settings.FORCE_SINGLE_PORT_MULTIPLEXING:
                mode = "single"
            else:
                range_start = int(getattr(db_node, "rtp_port_range_start", 0) or 0)
                range_end = int(getattr(db_node, "rtp_port_range_end", 0) or 0)
                if mode != "range" and range_start > 0 and range_end >= range_start:
                    mode = "range"
                if mode != "range":
                    env_start, env_end = _parse_port_range(settings.MEDIA_SERVER_RTP_PROXY_PORT_RANGE)
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
                max_port_retries = settings.SIP_INVITE_ZLM_MAX_PORT_RETRIES
                max_port_retries = max(1, min(max_port_retries, 100))
                tried_ports: set[int] = set()
                start_from: int | None = None
                for _ in range(max_port_retries):
                    # R25 Stream-3: 短 session 分配租约并立即 commit，session 关闭后再调用 ZLM HTTP
                    allocated_port = 0
                    attempt_lease_id = None
                    async with AsyncSessionLocal() as lease_session:
                        # FIX: [2026-07-03] 传入 stream_id/app_name 用于孤儿租约清理 [全栈工程师]
                        allocated_port, attempt_lease_id = await allocate_rtp_port_with_lease(
                            lease_session, db_node, start_from=start_from, exclude_ports=tried_ports,
                            stream_id=stream_id, app_name=app_name,
                        )
                        if attempt_lease_id:
                            await lease_session.commit()
                        else:
                            await lease_session.rollback()
                    if not attempt_lease_id or int(allocated_port or 0) <= 0:
                        # FIX: [2026-07-04] 端口池耗尽时主动清理孤儿租约后重试 [全栈工程师]
                        # 根因：allocate_rtp_port_with_lease 返回 0 时直接 break，不尝试
                        # 清理孤儿租约。多路并发预览时，刚释放但租约未清理的端口无法复用。
                        # 修复：首次耗尽时触发 cleanup_stale_leases(30s)，回收后重试一次。
                        if _ == 0:  # 仅在第一次耗尽时清理，避免每次重试都清理
                            try:
                                async with AsyncSessionLocal() as _cleanup_db:
                                    from app.core.media_nodes_db import cleanup_stale_leases as _cleanup_fn
                                    _cleaned = await _cleanup_fn(_cleanup_db, max_age_seconds=30, limit=200)
                                    if _cleaned > 0:
                                        logger.info(f"Port exhaustion: cleaned {_cleaned} stale leases on node {db_node.id}, retrying allocation")
                                        await _cleanup_db.commit()
                                        continue  # 清理后重试端口分配
                            except Exception as _cleanup_err:
                                logger.warning(f"Port exhaustion cleanup failed: {_cleanup_err}")
                        last_err_msg = f"node={db_node.id}, error=media_port_exhausted"
                        logger.warning(f"RTP port lease exhausted on node {db_node.id}")
                        zlm_res = None
                        break
                    media_port = int(allocated_port or 0)
                    # db_node 为 RuntimeMediaNode（由 _select_media_node 经 _to_runtime 解密），
                    # .secret 已是明文，可直接用于 ZLM API 鉴权。
                    secret = (db_node.secret or settings.MEDIA_SERVER_SECRET or "")
                    if not secret:
                        last_err_msg = f"node={db_node.id}, reason=empty_secret"
                        logger.error(f"ZLM openRtpServer skipped: secret is empty for node {db_node.id}")
                        zlm_res = None
                        if attempt_lease_id:
                            async with AsyncSessionLocal() as cleanup_session:
                                await release_lease(cleanup_session, attempt_lease_id)
                                await cleanup_session.commit()
                        break
                    # R25 Stream-3: ZLM HTTP 在无 DB session 持有期间执行
                    try:
                        zlm_res = await open_rtp_server(
                            host=str(db_node.host), http_port=int(db_node.http_port or 0),
                            secret=str(secret), port=int(media_port or 0), tcp_mode=int(tcp_mode),
                            app=app_name, stream_id=stream_id, ssrc=zlm_expect_ssrc,
                            re_use_port=False, enable_hls=1,  # P0-fix: 使用布尔值而非字符串 "0"
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
                            async with AsyncSessionLocal() as cleanup_session:
                                await release_lease(cleanup_session, attempt_lease_id)
                                await cleanup_session.commit()
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
                media_port = int(getattr(db_node, "rtp_port", None) if getattr(db_node, "rtp_port", None) is not None else media_port)  # GB28181协议 — 0是合法端口值，不应被falsy跳过
                # db_node 为 RuntimeMediaNode，.secret 已是明文（同 range 模式）
                secret = (db_node.secret or settings.MEDIA_SERVER_SECRET or "")
                if not secret:
                    last_err_msg = f"node={db_node.id}, reason=empty_secret"
                    logger.error(f"ZLM openRtpServer skipped: secret is empty for node {db_node.id}")
                    zlm_res = None
                else:
                    # R25 Stream-3: single 模式无租约，ZLM HTTP 在无 DB session 期间执行
                    try:
                        zlm_res = await open_rtp_server(
                            host=str(db_node.host), http_port=int(db_node.http_port or 0),
                            secret=str(secret), port=int(media_port or 0), tcp_mode=int(tcp_mode),
                            app=app_name, stream_id=stream_id, ssrc=zlm_expect_ssrc,
                            re_use_port=(mode != "range"),  # P0-fix: 布尔值，避免字符串 "0"/"1" 误判
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
                                logger.debug("Port exhausted but retryable, continuing...")  # 端口耗尽且可重试时不应空 pass
                            else:
                                err_text = str(e)
                                if "Assertion failed" in err_text or "api secret" in err_text.lower():
                                    logger.error(f"ZLM openRtpServer fatal error on node {db_node.id}, skip retries: {e}")
                                    zlm_res = None
                                    break
                        zlm_res = None
                        if attempt_lease_id:
                            async with AsyncSessionLocal() as cleanup_session:
                                await release_lease(cleanup_session, attempt_lease_id)
                                await cleanup_session.commit()
                if zlm_res:
                    break

            if attempt < max_node_retries - 1:
                logger.info("Trying to find another available media node for failover...")
                excluded_nodes.append(db_node.id)
                # R25 Stream-3: failover 节点选择使用短 session
                async with AsyncSessionLocal() as failover_session:
                    db_node = await select_best_db_node(failover_session, exclude_node_ids=excluded_nodes)
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
        tenant_id = str(getattr(asset, "tenant_id", "") or "default").strip() or "default"
        channel_id = str(getattr(resource, "gb_id", "") or "")
        device_id = asset_gb_id
        # per-channel INVITE mutex to prevent concurrent INVITE for the same channel
        _ch_lock = invite_state.get_channel_lock(channel_id)
        # FIX: [2026-07-03] 全局并发 INVITE 信号量，防止大流量时打爆设备 [全栈工程师]
        async with invite_state.global_invite_semaphore:
            # W-20 使用async with替代手动acquire/release，避免CancelledError时release未获取的锁
            async with _ch_lock:
                return await self._send_invite_common_inner(
                    asset, resource, transport_info, is_playback,
                    start_time, end_time, media_mode_override, stream_type,
                    zlm_ssrc_check, reuse_stream_session_id, download_speed,
                    asset_id, asset_gb_id, tenant_id, channel_id, device_id,
                )

    async def _send_invite_common_inner(
        self, asset, resource, transport_info, is_playback,
        start_time, end_time, media_mode_override, stream_type,
        zlm_ssrc_check, reuse_stream_session_id, download_speed,
        asset_id, asset_gb_id, tenant_id, channel_id, device_id,
    ):
        addr, proto, transport = transport_info
        resource_id = str(getattr(resource, "id", "") or "")
        asset_ip_addr = str(getattr(asset, "ip_addr", "") or "")
        asset_port = int(getattr(asset, "port", 0) or 0)
        asset_transport = str(getattr(asset, "transport", "") or "UDP")
        allowed, limit_detail = await _check_and_consume_invite_rate(tenant_id=tenant_id, device_id=device_id or asset_id or "unknown")
        if not allowed:
            logger.warning(
                "sip_invite_rate_limited tenant=%s device=%s detail=%s channel=%s",
                tenant_id,
                device_id,
                limit_detail,
                channel_id,
            )
            raise HTTPException(status_code=429, detail="SIP INVITE too frequent, please retry later")  # i18n

        ssrc = await self._generate_ssrc(settings.SIP_DOMAIN, is_playback)
        if not ssrc:  # SSRC分配失败空值检查，防止后续SDP/ZLM配置出错
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
            fmt = str(settings.GB28181_PLAYBACK_SDP_TIME_FORMAT or "iso").strip().lower()
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
                public_hint = str(settings.STREAM_PUBLIC_HOST or "").strip()
                if public_hint and not _is_local_host(public_hint):
                    sdp_ip = _resolve_sdp_ip(public_hint) or sdp_ip
        except Exception as e:
            logger.warning(f"SIP Invite operation failed: {e}")

        def build_sdp(port: int) -> str:
            from app.sip.sdp import build_sdp as _build_sdp
            f_line_val = f"f=v/2/4/{settings.GB28181_VIDEO_QUALITY}/1/0a/0/0/0" if not is_playback else ""
            u_line_val = f"u={channel_id}:0" if is_playback else ""
            setup_val = None
            if media_mode == "TCP_PASSIVE":
                setup_val = "passive"
            elif media_mode == "TCP_ACTIVE":
                setup_val = "active"
            # GB28181-2022 SDP 添加 a=track 行标识媒体轨道类型
            track_val = None
            gb_version = settings.GB28181_VERSION
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

        branch = f"z9hG4bK{secrets.token_hex(8)}"  # FIX [2026-07-29 P1]: token_hex(10)→token_hex(8) 统一 64 位随机性
        tag = secrets.token_hex(8)
        call_id = f"{secrets.token_hex(8)}@{sip_via_host()}"  # FIX [2026-07-29 P1]: token_hex(10)→token_hex(8) 统一 64 位随机性

        req = SipMessage()
        req.method = "INVITE"
        req.uri = f"sip:{channel_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={tag}"
        req.headers["To"] = f"<sip:{channel_id}@{sip_from_to_host()}>"
        req.headers["Call-ID"] = call_id
        # FIX [2026-07-17 P1]: CSeq 单调递增（RFC 3261 §22.2）
        req.headers["CSeq"] = f"{_next_cseq()} INVITE"
        req.headers["Contact"] = f"<sip:{settings.SIP_ID}@{sip_host_for_contact()}:{settings.SIP_PORT}>"
        req.headers["Content-Type"] = "application/sdp"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        req.headers["Subject"] = subject_header if subject_header else f"{channel_id}:{ssrc},{settings.SIP_ID}:{stream_type_code}"
        # P1-fix [2026-07-17]: SIP Session Timer (RFC 4028) — UAC 在 INVITE 中添加 Session-Expires 和 Min-SE
        # 默认值取自 Settings 类（禁止 getattr 动态获取）
        try:
            apply_session_expires_to_request(
                req,
                expires=settings.SIP_SESSION_EXPIRES_SECONDS,
                min_se=settings.SIP_SESSION_MIN_SE_SECONDS,
            )
        except Exception as _se_apply_err:
            # FIX [2026-07-17 P3-9]: 描述性日志替代 "silently_swallowed_exception"
            logger.warning(f"_send_invite_common_inner: failed to apply Session-Expires header call_id={call_id}: {_se_apply_err}")

        # R25 Stream-3: 将原长 async with AsyncSessionLocal() 拆分为多阶段短 session，
        # ZLM HTTP 慢 I/O（_open_zlm_rtp_server / send_bye / close_zlm_stream）期间不持有 DB 连接，
        # 避免多路并发播放时连接池耗尽报错。
        # Phase 1: DB 读 — 复用 session 快照、db_node、清理过期租约
        reuse_session_snapshot = None
        db_node = None
        async with AsyncSessionLocal() as session:
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
                    reuse_session = None
            db_node = await get_db_media_node_by_id(session, node_id)
            if db_node:
                with contextlib.suppress(Exception):
                    for _ in range(3):
                        # FIX: [2026-07-03] 孤儿租约清理延迟从 300s 降至 120s，避免端口假性耗尽 [全栈工程师]
                        cleaned_orphan = int(await cleanup_stale_leases(session, max_age_seconds=120, limit=5000) or 0)
                        cleaned_invalid = int(await cleanup_invalid_bound_leases(session, limit=5000) or 0)
                        if (cleaned_orphan + cleaned_invalid) <= 0:
                            break
            # R25 Stream-3: 持久化清理结果后立即关闭 session
            with contextlib.suppress(Exception):
                await session.commit()

        # Phase 1.5: 复用 session 的慢 I/O 清理（SIP BYE / ZLM close / lease 释放）— 无 DB session 持有
        if reuse_session_snapshot:
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
                    async with AsyncSessionLocal() as cleanup_session:
                        await release_lease(cleanup_session, old_lease_id)
                        await cleanup_session.commit()

        # Phase 2: ZLM HTTP 慢 I/O — _open_zlm_rtp_server 内部使用短 session 做 lease 分配/释放
        if db_node:
            tcp_mode = 0
            if media_protocol == "TCP-PASSIVE":
                tcp_mode = 1
            elif media_protocol == "TCP-ACTIVE":
                tcp_mode = 2

            base_ssrc_check = True if zlm_ssrc_check is None else bool(zlm_ssrc_check)
            zlm_res, media_port, media_ip, node_id, lease_id, ssrc_check_enabled, sdp_ip, selection_reason, last_err_msg = await self._open_zlm_rtp_server(
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

        # Phase 3: DB 写 — 创建/更新 StreamSession、绑定租约、commit
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
                await ssrc_manager.release(ssrc)  # P2 SSRC泄漏 — 异常路径释放SSRC
                raise RuntimeError("invalid_stream_session_refs")
            stream_session_id_value = ""
            async with AsyncSessionLocal() as session:
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
                        start_time=datetime.datetime.now(datetime.timezone.utc),
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
                    stream_session.start_time = datetime.datetime.now(datetime.timezone.utc)
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
        except Exception:
            await unregister_ssrc_waiter(ssrc)
            with contextlib.suppress(Exception):
                await ssrc_manager.release(ssrc)
            if lease_id:
                with contextlib.suppress(Exception):
                    async with AsyncSessionLocal() as cleanup_session:
                        await release_lease(cleanup_session, lease_id)
                        await cleanup_session.commit()
            with contextlib.suppress(Exception):
                await close_zlm_stream(app=app_name, stream=stream_id, node_id=node_id)
            raise

        # Phase 4: 审计日志 — 独立短 session
        try:
            async with AsyncSessionLocal() as audit_session:
                await audit_center_service.log(
                    db=audit_session,
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

        # FIXED-P2: Dialog 创建和 SSRC 绑定添加异常保护，INVITE 已发出但追踪丢失时记录错误而非崩溃
        try:
            await dialog_manager.create_dialog(
                call_id, tag,
                cseq=1,
                session_data={
                    "asset_id": asset_id,
                    "resource_id": resource_id,
                    "ssrc": ssrc,
                    "stream_id": stream_id,
                    "app": app_name,
                    "device_id": device_id,  # FIXED-P0: 添加 device_id，使 terminate_dialogs_by_device 能匹配到 Dialog
                },
            )
        except Exception as _dialog_err:
            logger.error(f"[INVITE] create_dialog failed after INVITE sent: {_dialog_err}")
        try:
            await ssrc_manager.bind_stream(ssrc, stream_id)
        except Exception as _bind_err:
            logger.error(f"[INVITE] bind_stream failed after INVITE sent: {_bind_err}")

        # Use transaction manager to handle UDP retransmissions, fallback to direct send
        tx_manager = _get_client_tx_manager()
        event, result = _register_invite_pending(call_id)
        result["from_tag"] = tag
        result["ssrc"] = ssrc
        result["stream_id"] = stream_id
        result["app"] = app_name
        result["node_id"] = node_id
        result["lease_id"] = lease_id
        result["original_sdp"] = sdp if isinstance(sdp, str) else (sdp.decode("utf-8") if isinstance(sdp, bytes) else "")  # C-04 存储原始SDP
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

        # FIX: [2026-07-16] 级联 INVITE 场景下，下级平台需再向设备发 INVITE，
        # 整个链路可能需要 15-30 秒，原 20 秒超时可能导致级联点播失败。
        # 级联 call_id 以 "cascade_" 开头（见 send_cascade_invite line 1242）。
        if str(call_id).startswith("cascade_"):
            timeout = settings.SIP_CASCADE_INVITE_TIMEOUT_SECONDS
        else:
            timeout = settings.SIP_INVITE_RESPONSE_TIMEOUT_SECONDS
        async def _on_timeout():
            # INVITE超时处理幂等性保护 — 防止watchdog与wait_invite_response双重超时竞态
            try:
                dialog_lock = await dialog_manager.acquire_dialog_lock(call_id, tag)
                if dialog_lock:
                    await dialog_lock.acquire()
                try:
                    if call_id not in invite_state.invite_pending:
                        logger.info(f"[InviteTimeout] {call_id} already responded, skipping timeout handler")
                        return
                    # 原子性移除pending条目，防止wait_invite_response与on_timeout竞态
                    _pending_entry = invite_state.invite_pending.pop(call_id, None)
                    if not _pending_entry:
                        logger.info(f"[InviteTimeout] {call_id} pending entry already consumed, skipping")
                        return
                    # GB28181协议 — INVITE超时直接清理StreamSession，通知wait_invite_response返回
                    _pending_event, _pending_result = _pending_entry
                    _pending_result["ok"] = False
                    _pending_result["status_code"] = 408
                    _pending_result["reason"] = "Request Timeout"
                    _pending_event.set()
                    await unregister_ssrc_waiter(ssrc)
                    await ssrc_manager.release(ssrc)
                    await dialog_manager.terminate_dialog(call_id, tag)
                    # W-06-03 INVITE超时清理_REDIRECT_COUNTS，防止3xx重定向后超时条目残留
                    try:
                        from app.sip.response_handler import _REDIRECT_COUNTS
                        _REDIRECT_COUNTS.pop(call_id, None)
                    except Exception as _redirect_cleanup_err:
                        # FIX [2026-07-17 P2-8]: 描述性日志替代 "silently_swallowed_exception"
                        logger.warning(f"INVITE timeout: failed to cleanup _REDIRECT_COUNTS for call_id={call_id}: {_redirect_cleanup_err}")
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
                    # GB28181协议 — 已通过_pending_event.set()通知wait_invite_response，无需再调用on_invite_response
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
                        logger.warning(f"Exception: {e}")
                finally:
                    if dialog_lock:
                        dialog_lock.release()
            except Exception as e:
                logger.error(f"Error in invite timeout handler for {call_id}: {e}")
        # S-07 存储watchdog回调到pending条目，供3xx重定向后重置watchdog
        _pending_for_wd = invite_state.invite_pending.get(call_id)
        if _pending_for_wd:
            _pending_for_wd[1]["watchdog_on_timeout"] = _on_timeout
        start_watchdog(key=f"invite:{call_id}", timeout_seconds=timeout, on_timeout=_on_timeout)
        # NOTE: ACK 超时检测由 invite_server_state.py 的 Timer H (RFC 3261 §17.2.1) 处理。
        # UAC 侧（本模块）在收到 200 OK 后主动发送 ACK，无需等待设备 ACK。
        # UAS 侧在 invite_server_state 中已有完整的 Timer H 超时 + BYE 清理机制。

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

    async def send_session_refresh_reinvite(self, dialog) -> bool:
        """发送会话内 re-INVITE 进行 Session Timer 保活（RFC 4028）。

        在已确认的 dialog 内发送 re-INVITE，复用原 Call-ID、From tag、To tag，
        CSeq 通过 ``_next_cseq()`` 单调递增，Via branch 使用 ``secrets.token_hex(8)`` 生成。
        携带与原 INVITE 相同的 Session-Expires 头域。

        Args:
            dialog: :class:`app.sip.dialog_manager.Dialog` 对象，必须包含
                ``call_id``、``from_tag``、``to_tag``、``remote_target``、
                ``session_data``（含 ``session_expires``、``session_refresher``）。

        Returns:
            True — 收到 200 OK；False — 发送失败或超时。
        """
        call_id = str(getattr(dialog, "call_id", "") or "").strip()
        from_tag = str(getattr(dialog, "from_tag", "") or "").strip()
        to_tag = str(getattr(dialog, "to_tag", "") or "").strip()
        if not call_id or not from_tag:
            logger.warning("send_session_refresh_reinvite: missing call_id/from_tag for dialog")
            return False

        remote_target = str(getattr(dialog, "remote_target", "") or "").strip()
        session_data = getattr(dialog, "session_data", {}) or {}
        expires = int(session_data.get("session_expires", settings.SIP_SESSION_EXPIRES_SECONDS) or settings.SIP_SESSION_EXPIRES_SECONDS)
        refresher = str(session_data.get("session_refresher", "uac") or "uac").lower()

        # 解析 remote_target 获取设备地址（格式：sip:device_id@host:port）
        device_addr = remote_target or ""
        device_id = session_data.get("device_id", "") or session_data.get("channel_id", "")
        try:
            # remote_target 格式: sip:xxx@host:port
            if "@" in device_addr:
                _uri_part = device_addr.split(":", 1)[1] if ":" in device_addr else device_addr
                _id_part, _, _host_port = _uri_part.rpartition("@")
                if _id_part:
                    device_id = device_id or _id_part
                if _host_port:
                    _host, _, _port_str = _host_port.partition(":")
                    addr = (_host, int(_port_str) if _port_str.isdigit() else 5060)
                else:
                    addr = (settings.SIP_IP or "127.0.0.1", settings.SIP_PORT)
            else:
                addr = (settings.SIP_IP or "127.0.0.1", settings.SIP_PORT)
        except Exception as _addr_err:
            # FIX [2026-07-17 P3-9]: 描述性日志替代 "silently_swallowed_exception"
            logger.warning(f"send_session_refresh_reinvite: failed to parse remote_target={remote_target}: {_addr_err}")
            addr = (settings.SIP_IP or "127.0.0.1", settings.SIP_PORT)

        proto = "UDP"
        transport = None
        try:
            transport = self.sip_server.get_transport(addr[0], addr[1], proto)
        except Exception as _transport_err:
            # FIX [2026-07-19]: 禁止静默吞异常（项目硬约束：异常必须记录日志）。
            # 记录 warning 便于排查传输层问题；后续 if not transport 兜底返回 False。
            logger.warning(
                f"send_session_refresh_reinvite: get_transport({addr[0]}:{addr[1]}/{proto}) raised: {_transport_err}"
            )
        if not transport:
            logger.warning(f"send_session_refresh_reinvite: no transport for {addr[0]}:{addr[1]}/{proto}")
            return False

        # FIX [2026-07-17 P1]: CSeq 单调递增（RFC 3261 §22.2）
        cseq = _next_cseq()
        # FIX [memory-constraint]: branch/tag 使用 64 位密码学随机值
        branch = f"z9hG4bK{secrets.token_hex(8)}"

        to_header = f"<sip:{device_id or settings.SIP_ID}@{sip_from_to_host()}>"
        if to_tag:
            to_header = f"{to_header};tag={to_tag}"

        req = SipMessage()
        req.method = "INVITE"
        req.uri = remote_target or f"sip:{device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={from_tag}"
        req.headers["To"] = to_header
        req.headers["Call-ID"] = call_id
        req.headers["CSeq"] = f"{cseq} INVITE"
        req.headers["Contact"] = f"<sip:{settings.SIP_ID}@{sip_host_for_contact()}:{settings.SIP_PORT}>"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        # P1-fix [2026-07-17]: 携带 Session-Expires 头域进行保活协商
        try:
            from app.sip.invite_server_state import build_session_expires_header
            req.headers["Session-Expires"] = build_session_expires_header(expires, refresher)
            req.headers["Min-SE"] = str(settings.SIP_SESSION_MIN_SE_SECONDS)
        except Exception as _se_hdr_err:
            # FIX [2026-07-17 P3-9]: 描述性日志替代 "silently_swallowed_exception"
            logger.warning(f"send_session_refresh_reinvite: failed to set Session-Expires header: {_se_hdr_err}")
        _attach_trace_header(req)

        # 通过事务管理器发送 re-INVITE
        tx_manager = _get_client_tx_manager()
        try:
            if tx_manager:
                await tx_manager.send_request(req, addr, proto, transport)
            else:
                data = req.to_bytes()
                # FIX: [2026-08-22 PN] 原调用 send_sip_bytes(transport, data, addr, proto)
                # 参数顺序与签名 send_sip_bytes(proto, transport, addr, data) 颠倒，
                # 导致 tx_manager=None 回退分支发送必然失败。
                await send_sip_bytes(proto, transport, addr, data)
            logger.debug(f"send_session_refresh_reinvite: sent re-INVITE call_id={call_id} cseq={cseq}")
            return True
        except Exception as e:
            logger.warning(f"send_session_refresh_reinvite: failed to send re-INVITE call_id={call_id}: {e}")
            return False

# Singleton
sip_invite = None
