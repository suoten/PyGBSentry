"""GB28181 历史媒体回放/下载控制（MANSRTSP over SIP INFO）。

封装对已建立的回放/下载 INVITE 对话的播放控制：
- ``send_pause`` — 暂停（PAUSE）
- ``send_resume`` — 恢复（PLAY，npt=now-）
- ``send_seek`` — 拖动到指定时间点（PLAY，Range: npt=<seek>-）
- ``set_playback_started`` — 标记回放会话已开始（状态机初始化为 playing）

控制指令通过 SIP ``INFO`` 方法在已建立的 INVITE 对话内发送，Content-Type 为
``Application/MANSRTSP``，与 ``commander.SipCommander.send_stream_control`` 风格一致。

状态机：
- ``_playback_states``：``call_id -> "playing" | "paused"``
- ``send_pause`` 仅在 ``playing`` 时允许，成功后置为 ``paused``
- ``send_resume`` 仅在 ``paused`` 时允许，成功后置为 ``playing``
- ``send_seek`` 任意状态均允许
- ``BYE`` 处理时由 handlers.py 清理 ``_playback_states.pop(call_id, None)``

``_npt_results`` 缓存设备返回的 NPT 播放进度（由 handlers.py handle_info 解析后
通过 ``_npt_results_put`` 写入），供前端查询播放位置。使用带容量上限的 dict 避免
内存泄漏。
"""
from __future__ import annotations

import secrets
import time
from collections import OrderedDict
from typing import Any, Optional

from loguru import logger

from app.core.config import settings, sip_host_for_contact
from app.sip.send import send_sip_bytes

# SipMessage 延迟导入：app.sip.message 由并行 agent 提供，避免其在 WIP 状态下
# 导致本模块顶层导入失败（NEVER raise from a top-level import）。
_SipMessage = None


def _get_sip_message_cls():
    """惰性获取 SipMessage 类（首次调用时导入 app.sip.message）。"""
    global _SipMessage
    if _SipMessage is None:
        from app.sip.message import SipMessage
        _SipMessage = SipMessage
    return _SipMessage


def _attach_trace_header(req) -> None:
    call_id = (req.get_header("Call-ID") or "").strip()
    if call_id:
        req.headers["X-Trace-ID"] = call_id


# ---------------------------------------------------------------------------
# NPT 结果缓存（bounded dict）
# ---------------------------------------------------------------------------

_NPT_RESULTS_MAX = 500
_npt_results: "OrderedDict[str, dict[str, Any]]" = OrderedDict()


def _npt_results_put(call_id: str, data: dict[str, Any]) -> None:
    """写入 NPT 播放进度结果到有界缓存。

    被 ``handlers.handle_info`` 在解析到 ``Range: npt=...`` 响应时调用。
    超过 ``_NPT_RESULTS_MAX`` 时按 FIFO 淘汰最早条目。
    """
    if not call_id:
        return
    key = str(call_id)
    # 先删除旧键，再写入，保证其为最新（移到末尾）
    _npt_results.pop(key, None)
    _npt_results[key] = dict(data or {})
    while len(_npt_results) > _NPT_RESULTS_MAX:
        try:
            _npt_results.popitem(last=False)
        except KeyError:
            break


def get_npt_result(call_id: str) -> Optional[dict[str, Any]]:
    """读取 NPT 播放进度结果（供前端查询播放位置）。"""
    if not call_id:
        return None
    return _npt_results.get(str(call_id))


# ---------------------------------------------------------------------------
# PlaybackControl
# ---------------------------------------------------------------------------


class PlaybackControl:
    """GB28181 回放/下载流控制（MANSRTSP over SIP INFO）。

    ``sip_server`` 参数保留以兼容 lifespan 初始化（``PlaybackControl(sip_server)``）。
    """

    def __init__(self, sip_server: Any = None) -> None:
        self.sip_server = sip_server
        # call_id -> "playing" | "paused"
        self._playback_states: dict[str, str] = {}
        # FIX: [2026-07-03] seek 频率限制：per-call_id 最后一次 seek 时间戳 [全栈工程师]
        self._seek_last_ts: dict[str, float] = {}
        self._seek_min_interval: float = 1.0  # 最小间隔 1 秒
        # FIX: [2026-07-04] 存储 per-call_id 回放起始 Unix 秒，用于 NPT 相对时间计算 [全栈工程师]
        self._playback_start_ts: dict[str, int] = {}

    # ------------------------------------------------------------------
    # 状态机
    # ------------------------------------------------------------------

    def set_playback_started(self, call_id: str, start_time: int | None = None) -> None:
        """标记回放会话已开始（状态机初始化为 playing）。

        在 device_record.py 的 download/start 端点和 stream_play.py 的 playback 端点中
        于 INVITE 成功后调用。

        FIX: [2026-07-04] 新增 start_time 参数，存储回放起始 Unix 秒用于 NPT 相对时间计算 [全栈工程师]
        """
        if not call_id:
            return
        self._playback_states[str(call_id)] = "playing"
        # FIX: [2026-07-04] 记录回放起始 Unix 秒，send_seek 时转换为相对 NPT [全栈工程师]
        if start_time is not None and start_time > 0:
            self._playback_start_ts[str(call_id)] = int(start_time)

    def _get_state(self, call_id: str) -> str:
        return self._playback_states.get(str(call_id), "")

    def _set_state(self, call_id: str, state: str) -> None:
        self._playback_states[str(call_id)] = state

    # ------------------------------------------------------------------
    # SIP INFO 构造与发送
    # ------------------------------------------------------------------

    async def _send_info(
        self,
        asset: Any,
        channel_id: str,
        transport_info: tuple,
        call_id: str,
        cseq: int,
        from_tag: Optional[str],
        to_tag: Optional[str],
        mansrtsp_body: str,
    ) -> bool:
        """在已建立的回放对话内发送一条 MANSRTSP INFO 请求。

        返回 True 表示 SIP 发送成功。
        """
        device_id = str(getattr(asset, "gb_id", "") or "")
        addr, proto, transport = transport_info
        _SipMessage = _get_sip_message_cls()

        req = _SipMessage()
        req.method = "INFO"
        req.uri = f"sip:{channel_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"
        branch = f"z9hG4bKpb{secrets.token_hex(5)}"
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={from_tag or ''}"
        if to_tag:
            req.headers["To"] = f"<sip:{channel_id}@{settings.SIP_DOMAIN}>;tag={to_tag}"
        else:
            req.headers["To"] = f"<sip:{channel_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = str(call_id or "")
        req.headers["CSeq"] = f"{int(cseq or 1)} INFO"
        req.headers["Content-Type"] = "Application/MANSRTSP"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        req.body = mansrtsp_body

        data = req.to_bytes()
        try:
            sent_ok = await send_sip_bytes(proto, transport, addr, data)
        except Exception as e:
            logger.warning(f"Failed to send playback INFO to {channel_id} (call_id={call_id}): {e}")
            return False
        if not sent_ok:
            logger.warning(f"playback INFO send_sip_bytes returned False for {channel_id} (call_id={call_id})")
            return False
        logger.info(f"Sent playback INFO to {channel_id} (call_id={call_id}, device={device_id})")
        return True

    # ------------------------------------------------------------------
    # 控制命令
    # ------------------------------------------------------------------

    async def send_pause(
        self,
        asset: Any,
        channel_id: str,
        transport_info: tuple,
        call_id: str,
        cseq: int,
        from_tag: Optional[str] = None,
        to_tag: Optional[str] = None,
    ) -> bool:
        """暂停回放流。仅在状态为 ``playing`` 时允许。

        返回 False 表示状态机拒绝（未处于 playing）或 SIP 发送失败。
        """
        if self._get_state(call_id) != "playing":
            logger.debug(f"send_pause rejected: call_id={call_id} state={self._get_state(call_id)!r}")
            return False
        body = f"PAUSE RTSP/1.0\r\nCSeq: {int(cseq or 1)}\r\nPauseTime: now\r\n"
        ok = await self._send_info(
            asset, channel_id, transport_info, call_id, cseq, from_tag, to_tag, body
        )
        if ok:
            self._set_state(call_id, "paused")
        return ok

    async def send_resume(
        self,
        asset: Any,
        channel_id: str,
        transport_info: tuple,
        call_id: str,
        cseq: int,
        from_tag: Optional[str] = None,
        to_tag: Optional[str] = None,
    ) -> bool:
        """恢复回放流。仅在状态为 ``paused`` 时允许。"""
        if self._get_state(call_id) != "paused":
            logger.debug(f"send_resume rejected: call_id={call_id} state={self._get_state(call_id)!r}")
            return False
        body = f"PLAY RTSP/1.0\r\nCSeq: {int(cseq or 1)}\r\nRange: npt=now-\r\n"
        ok = await self._send_info(
            asset, channel_id, transport_info, call_id, cseq, from_tag, to_tag, body
        )
        if ok:
            self._set_state(call_id, "playing")
        return ok

    async def send_seek(
        self,
        asset: Any,
        channel_id: str,
        transport_info: tuple,
        call_id: str,
        seek_time: int,
        cseq: int,
        from_tag: Optional[str] = None,
        to_tag: Optional[str] = None,
    ) -> bool:
        """拖动回放流到指定时间点（Unix 秒）。任意状态均允许。

        FIX: [2026-07-04] NPT 时间语义修复 [全栈工程师]
        根因：原代码将 Unix 绝对秒直接作为 NPT 值（npt=1720000000-），但 MANSRTSP NPT
        是相对于媒体起始的偏移秒数。设备收到天文数字般的 NPT 值后行为不可预测。
        修复：用 seek_time - playback_start_ts 计算相对 NPT 偏移。
        """
        # FIX: [2026-07-03] seek 频率限制：同一 call_id 1 秒内只允许一次 seek [全栈工程师]
        _cid = str(call_id or "")
        _now = time.monotonic()
        _last = self._seek_last_ts.get(_cid, 0.0)
        if _now - _last < self._seek_min_interval:
            logger.debug(f"seek rate-limited for call_id={_cid}, interval={_now - _last:.3f}s")
            return False
        self._seek_last_ts[_cid] = _now

        # FIX: [2026-07-04] 计算 NPT 相对偏移：seek_unix - playback_start_unix [全栈工程师]
        _start_ts = self._playback_start_ts.get(_cid, 0)
        if _start_ts > 0:
            npt_offset = max(0, int(seek_time or 0) - _start_ts)
        else:
            # 无起始时间记录时降级为直接传值（兼容旧逻辑）
            npt_offset = int(seek_time or 0)
            logger.warning(f"send_seek: no playback_start_ts for call_id={_cid}, using raw seek_time as NPT")

        # seek 不改变状态机（playing 保持 playing，paused 保持 paused，
        # 因为部分设备 seek 后会自动恢复播放，但状态由后续 NPT 反馈校正更可靠）
        body = f"PLAY RTSP/1.0\r\nCSeq: {int(cseq or 1)}\r\nRange: npt={npt_offset}-\r\n"
        ok = await self._send_info(
            asset, channel_id, transport_info, call_id, cseq, from_tag, to_tag, body
        )
        # seek 成功后假定恢复播放
        if ok:
            self._set_state(call_id, "playing")
        return ok

    async def send_play_with_speed(
        self,
        asset: Any,
        channel_id: str,
        transport_info: tuple,
        call_id: str,
        speed: float,
        cseq: int,
        from_tag: Optional[str] = None,
        to_tag: Optional[str] = None,
    ) -> bool:
        """倍速播放回放流。

        FIX: [2026-07-04] 新增倍速播放方法 [全栈工程师]
        根因：PlaybackControl 缺少倍速控制方法，MANSRTSP Scale 头从未被发送。
        修复：通过 MANSRTSP PLAY + Scale 头实现倍速控制。
        Scale 值范围通常为 0.1~4.0，1.0 为正常速度。

        发送 ``PLAY RTSP/1.0`` with ``Scale: {speed}``。
        任意状态均允许（暂停状态调用倍速会自动恢复播放）。
        """
        # 参数校验
        try:
            speed = float(speed)
        except (TypeError, ValueError):
            logger.warning(f"send_play_with_speed: invalid speed={speed!r}")
            return False
        if speed <= 0 or speed > 8.0:
            logger.warning(f"send_play_with_speed: speed out of range: {speed}")
            return False

        body = f"PLAY RTSP/1.0\r\nCSeq: {int(cseq or 1)}\r\nScale: {speed:.2f}\r\n"
        ok = await self._send_info(
            asset, channel_id, transport_info, call_id, cseq, from_tag, to_tag, body
        )
        if ok:
            # 倍速播放意味着流在播放（从 paused 恢复）
            self._set_state(call_id, "playing")
        return ok

    async def send_teardown(
        self,
        asset: Any,
        channel_id: str,
        transport_info: tuple,
        call_id: str,
        cseq: int,
        from_tag: Optional[str] = None,
        to_tag: Optional[str] = None,
    ) -> bool:
        """发送 TEARDOWN 停止回放流（通常由 BYE 替代，此处保留兼容）。"""
        body = f"TEARDOWN RTSP/1.0\r\nCSeq: {int(cseq or 1)}\r\n"
        ok = await self._send_info(
            asset, channel_id, transport_info, call_id, cseq, from_tag, to_tag, body
        )
        if ok:
            self._playback_states.pop(str(call_id), None)
            # FIX: [2026-07-04] 同时清理 NPT 起始时间缓存 [全栈工程师]
            self._playback_start_ts.pop(str(call_id), None)
            self._seek_last_ts.pop(str(call_id), None)
        return ok


# 模块级单例：初始为 None，在 main.py lifespan 中赋值为 PlaybackControl(sip_server)
playback_control: Optional[PlaybackControl] = None
