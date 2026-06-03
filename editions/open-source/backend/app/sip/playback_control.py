"""
GB28181 录像回放控制模块
支持：暂停、恢复、拖动、倍速控制、TEARDOWN、NPT查询、回放保活
"""
from app.sip.message import SipMessage
from app.sip.send import send_sip_bytes
from app.core.config import settings, sip_host_for_contact
from loguru import logger
import random
import string
import asyncio
import secrets  # FIXED-P0: N-02 secrets.token_hex(5)生成Via branch但未导入


# FIXED: NPT 进度结果缓存，供 handlers.py handle_info 写入，wait_get_parameter_response 读取
_npt_results: dict[str, dict] = {}
_NPT_RESULTS_MAX_SIZE = 10000  # FIXED: W-30 _npt_results 无大小限制 — 添加最大容量


def _npt_results_put(call_id: str, value: dict) -> None:
    """写入 NPT 结果，超过最大容量时清理最旧的条目"""
    global _npt_results
    if len(_npt_results) >= _NPT_RESULTS_MAX_SIZE:
        # 清理最旧的一半条目（按插入顺序，dict 在 Python 3.7+ 保持插入顺序）
        keys_to_remove = list(_npt_results.keys())[:len(_npt_results) // 2]
        for k in keys_to_remove:
            _npt_results.pop(k, None)
    _npt_results[call_id] = value


async def _persist_cseq(call_id: str, cseq: int) -> None:
    try:
        from app.db.session import AsyncSessionLocal
        from app.models.stream_session import StreamSession
        from sqlalchemy import select
        async with AsyncSessionLocal() as session:
            ss = (await session.execute(select(StreamSession).where(StreamSession.call_id == call_id))).scalars().first()
            if ss:
                ss.cseq = cseq
                await session.commit()
    except Exception as e:
        logger.debug(f"Failed to persist CSeq for {call_id}: {e}")




def _attach_trace_header(req: SipMessage) -> None:
    call_id = (req.get_header("Call-ID") or "").strip()
    if call_id:
        req.headers["X-Trace-ID"] = call_id


from app.sip.sip_trace import sip_trace_log as _sip_trace_log


class PlaybackControl:
    """录像回放控制类"""

    def __init__(self, sip_server):
        self.sip_server = sip_server

    def _dialog_from(self, from_tag: str | None) -> str:
        tag = (from_tag or "").strip()
        if not tag:
            tag = "".join(random.choices(string.ascii_letters + string.digits, k=8))
        return f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={tag}"

    def _dialog_to(self, channel_id: str, to_tag: str | None) -> str:
        base = f"<sip:{channel_id}@{settings.SIP_DOMAIN}>"
        tag = (to_tag or "").strip()
        if not tag:
            return base
        return f"{base};tag={tag}"

    async def send_pause(
        self,
        asset,
        channel_id: str,
        transport_info: tuple,
        call_id: str,
        cseq: int = 2,
        from_tag: str | None = None,
        to_tag: str | None = None,
        wait_response: bool = False,  # FIXED: GB28181协议 — 回放控制添加响应等待机制
    ):
        """
        发送暂停回放命令 (PAUSE) - 基于 MANSRTSP 协议
        """
        addr, proto, transport = transport_info
        device_id = asset.gb_id

        # Build MANSRTSP body for PAUSE
        mansrtsp_body = f"PAUSE RTSP/1.0\r\nCSeq: {cseq}\r\nPauseTime: now\r\n"

        req = SipMessage()
        req.method = "INFO"
        req.uri = f"sip:{channel_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"

        branch = f"z9hG4bK{secrets.token_hex(5)}"  # FIXED-P2: W-09 random.choices→secrets

        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = self._dialog_from(from_tag)
        req.headers["To"] = self._dialog_to(channel_id, to_tag)
        req.headers["Call-ID"] = call_id
        req.headers["CSeq"] = f"{cseq} INFO"
        req.headers["Content-Type"] = "Application/MANSRTSP"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)

        req.body = mansrtsp_body

        # Send
        data = req.to_bytes()
        # FIXED-P0: S-01 wait_response=True时只通过tx_manager发送，避免重复发送
        if wait_response:
            try:
                from app.sip.transactions import client_tx_manager
                resp, meta = await client_tx_manager.send_and_wait(
                    request=req,
                    send_once=lambda: send_sip_bytes(proto, transport, addr, req.to_bytes()),
                    timeout_seconds=5.0,
                )
                await _persist_cseq(call_id, cseq)
                return int(resp.status_code or 0) == 200
            except Exception:
                return False
        try:
            await send_sip_bytes(proto, transport, addr, data)
        except Exception as e:
            logger.warning(f"Failed to send PLAYBACK PAUSE to {addr}: {e}")
            return False
        trace_id = req.get_header("Call-ID") or ""  # FIXED: trace_id赋值移到使用前，避免NameError
        logger.debug(f"[trace_id={trace_id}] PLAYBACK PAUSE sent as fire-and-forget (no 200 OK confirmation)")
        await _persist_cseq(call_id, cseq)
        logger.info(f"[trace_id={trace_id}] Sent PLAYBACK PAUSE to {channel_id}")
        _sip_trace_log(
            "playback_pause_sent",
            trace_id=trace_id,
            device_id=device_id,
            channel_id=channel_id,
            proto=proto,
            addr=str(addr),
        )

    async def send_resume(
        self,
        asset,
        channel_id: str,
        transport_info: tuple,
        call_id: str,
        cseq: int = 2,
        from_tag: str | None = None,
        to_tag: str | None = None,
        wait_response: bool = False,  # FIXED: GB28181协议 — 回放控制添加响应等待机制
    ):
        """
        发送恢复回放命令 (PLAY) - 基于 MANSRTSP 协议
        """
        addr, proto, transport = transport_info
        device_id = asset.gb_id

        # Build MANSRTSP body for PLAY (resume)
        mansrtsp_body = f"PLAY RTSP/1.0\r\nCSeq: {cseq}\r\nRange: npt=now-\r\n"

        req = SipMessage()
        req.method = "INFO"
        req.uri = f"sip:{channel_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"

        branch = f"z9hG4bK{secrets.token_hex(5)}"  # FIXED-P2: W-09 random.choices→secrets

        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = self._dialog_from(from_tag)
        req.headers["To"] = self._dialog_to(channel_id, to_tag)
        req.headers["Call-ID"] = call_id
        req.headers["CSeq"] = f"{cseq} INFO"
        req.headers["Content-Type"] = "Application/MANSRTSP"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)

        req.body = mansrtsp_body

        # Send
        data = req.to_bytes()
        # FIXED-P0: S-01 wait_response=True时只通过tx_manager发送，避免重复发送
        if wait_response:
            try:
                from app.sip.transactions import client_tx_manager
                resp, meta = await client_tx_manager.send_and_wait(
                    request=req,
                    send_once=lambda: send_sip_bytes(proto, transport, addr, req.to_bytes()),
                    timeout_seconds=5.0,
                )
                await _persist_cseq(call_id, cseq)
                return int(resp.status_code or 0) == 200
            except Exception:
                return False
        try:
            await send_sip_bytes(proto, transport, addr, data)
        except Exception as e:
            logger.warning(f"Failed to send PLAYBACK RESUME to {addr}: {e}")
            return False
        trace_id = req.get_header("Call-ID") or ""  # FIXED: trace_id赋值移到使用前，避免NameError
        logger.debug(f"[trace_id={trace_id}] PLAYBACK RESUME sent as fire-and-forget (no 200 OK confirmation)")
        await _persist_cseq(call_id, cseq)
        logger.info(f"[trace_id={trace_id}] Sent PLAYBACK RESUME to {channel_id}")
        _sip_trace_log(
            "playback_resume_sent",
            trace_id=trace_id,
            device_id=device_id,
            channel_id=channel_id,
            proto=proto,
            addr=str(addr),
        )

    async def send_seek(
        self,
        asset,
        channel_id: str,
        transport_info: tuple,
        call_id: str,
        seek_time: int,
        cseq: int = 2,
        from_tag: str | None = None,
        to_tag: str | None = None,
        wait_response: bool = False,  # FIXED: GB28181协议 — 回放控制添加响应等待机制
    ):
        """
        发送拖动播放命令 (SEEK) - 基于 MANSRTSP 协议
        """
        addr, proto, transport = transport_info
        device_id = asset.gb_id

        npt_time = abs(seek_time)
        npt_str = f"npt={npt_time}-"
        if getattr(settings, "GB28181_PLAYBACK_SEEK_RAW", False):
            npt_str = str(npt_time)

        mansrtsp_body = f"PLAY RTSP/1.0\r\nCSeq: {cseq}\r\nRange: {npt_str}\r\n"

        req = SipMessage()
        req.method = "INFO"
        req.uri = f"sip:{channel_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"

        branch = f"z9hG4bK{secrets.token_hex(5)}"  # FIXED-P2: W-09 random.choices→secrets

        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = self._dialog_from(from_tag)
        req.headers["To"] = self._dialog_to(channel_id, to_tag)
        req.headers["Call-ID"] = call_id
        req.headers["CSeq"] = f"{cseq} INFO"
        req.headers["Content-Type"] = "Application/MANSRTSP"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)

        req.body = mansrtsp_body

        # Send
        data = req.to_bytes()
        # FIXED-P0: S-01 wait_response=True时只通过tx_manager发送，避免重复发送
        if wait_response:
            try:
                from app.sip.transactions import client_tx_manager
                resp, meta = await client_tx_manager.send_and_wait(
                    request=req,
                    send_once=lambda: send_sip_bytes(proto, transport, addr, req.to_bytes()),
                    timeout_seconds=5.0,
                )
                await _persist_cseq(call_id, cseq)
                return int(resp.status_code or 0) == 200
            except Exception:
                return False
        try:
            await send_sip_bytes(proto, transport, addr, data)
        except Exception as e:
            logger.warning(f"Failed to send PLAYBACK SEEK to {addr}: {e}")
            return False
        trace_id = req.get_header("Call-ID") or ""  # FIXED: trace_id赋值移到使用前，避免NameError
        logger.debug(f"[trace_id={trace_id}] PLAYBACK SEEK sent as fire-and-forget (no 200 OK confirmation)")
        await _persist_cseq(call_id, cseq)
        logger.info(f"[trace_id={trace_id}] Sent PLAYBACK SEEK to {channel_id}, seek_time={seek_time}")
        _sip_trace_log(
            "playback_seek_sent",
            trace_id=trace_id,
            device_id=device_id,
            channel_id=channel_id,
            seek_time=seek_time,
            proto=proto,
            addr=str(addr),
        )

    async def send_speed(
        self,
        asset,
        channel_id: str,
        transport_info: tuple,
        call_id: str,
        speed: float,
        cseq: int = 2,
        from_tag: str | None = None,
        to_tag: str | None = None,
        wait_response: bool = False,  # FIXED: GB28181协议 — 回放控制添加响应等待机制
    ):
        """
        发送倍速播放命令 (SPEED) - 基于 MANSRTSP 协议
        """
        addr, proto, transport = transport_info
        device_id = asset.gb_id

        speed_str = str(int(speed)) if speed.is_integer() else str(speed)

        mansrtsp_body = f"PLAY RTSP/1.0\r\nCSeq: {cseq}\r\nScale: {speed_str}\r\n"

        req = SipMessage()
        req.method = "INFO"
        req.uri = f"sip:{channel_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"

        branch = f"z9hG4bK{secrets.token_hex(5)}"  # FIXED-P2: W-09 random.choices→secrets

        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = self._dialog_from(from_tag)
        req.headers["To"] = self._dialog_to(channel_id, to_tag)
        req.headers["Call-ID"] = call_id
        req.headers["CSeq"] = f"{cseq} INFO"
        req.headers["Content-Type"] = "Application/MANSRTSP"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)

        req.body = mansrtsp_body

        # Send
        data = req.to_bytes()
        # FIXED-P0: S-01 wait_response=True时只通过tx_manager发送，避免重复发送
        if wait_response:
            try:
                from app.sip.transactions import client_tx_manager
                resp, meta = await client_tx_manager.send_and_wait(
                    request=req,
                    send_once=lambda: send_sip_bytes(proto, transport, addr, req.to_bytes()),
                    timeout_seconds=5.0,
                )
                await _persist_cseq(call_id, cseq)
                return int(resp.status_code or 0) == 200
            except Exception:
                return False
        try:
            await send_sip_bytes(proto, transport, addr, data)
        except Exception as e:
            logger.warning(f"Failed to send PLAYBACK SPEED to {addr}: {e}")
            return False
        trace_id = req.get_header("Call-ID") or ""  # FIXED: trace_id赋值移到使用前，避免NameError
        logger.debug(f"[trace_id={trace_id}] PLAYBACK SPEED({speed}x) sent as fire-and-forget (no 200 OK confirmation)")
        await _persist_cseq(call_id, cseq)
        logger.info(f"[trace_id={trace_id}] Sent PLAYBACK SPEED({speed}x) to {channel_id}")
        _sip_trace_log(
            "playback_speed_sent",
            trace_id=trace_id,
            device_id=device_id,
            channel_id=channel_id,
            speed=speed,
            proto=proto,
            addr=str(addr),
        )

    async def send_teardown(self, asset, resource, stream_session, transport_info: tuple) -> None:
        """
        发送 TEARDOWN 指令，显式通知设备停止回放推流并释放资源。
        GB28181 MANSRTSP 协议要求：回放停止时应先发 TEARDOWN 再发 BYE。
        """
        addr, proto, transport = transport_info
        device_id = asset.gb_id
        channel_id = resource.gb_id
        call_id = stream_session.call_id or ""
        from_tag = stream_session.from_tag or ""
        to_tag = stream_session.to_tag or ""
        cseq = (stream_session.cseq or 1) + 1

        mansrtsp_body = f"TEARDOWN RTSP/1.0\r\nCSeq: {cseq}\r\n"

        branch = f"z9hG4bK{secrets.token_hex(5)}"  # FIXED-P2: W-09 random.choices→secrets
        req = SipMessage()
        req.method = "INFO"
        req.uri = f"sip:{channel_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={from_tag}"
        to_header = f"<sip:{channel_id}@{settings.SIP_DOMAIN}>"
        if to_tag:
            to_header = f"{to_header};tag={to_tag}"
        req.headers["To"] = to_header
        req.headers["Call-ID"] = call_id
        req.headers["CSeq"] = f"{cseq} INFO"
        req.headers["Content-Type"] = "Application/MANSRTSP"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        req.body = mansrtsp_body

        data = req.to_bytes()
        # FIXED: 回放控制指令裸调用无异常保护
        try:
            await send_sip_bytes(proto, transport, addr, data)
        except Exception as e:
            logger.warning(f"Failed to send PLAYBACK TEARDOWN to {addr}: {e}")
            return
        trace_id = req.get_header("Call-ID") or ""
        logger.info(f"[trace_id={trace_id}] Sent PLAYBACK TEARDOWN to {channel_id}")
        await _persist_cseq(call_id, cseq)
        _sip_trace_log(
            "playback_teardown_sent",
            trace_id=trace_id,
            device_id=device_id,
            channel_id=channel_id,
            proto=proto,
            addr=str(addr),
        )

    async def send_get_parameter(self, asset, resource, stream_session, transport_info: tuple) -> None:
        """
        发送 GET_PARAMETER 请求，获取当前 NPT（Normal Play Time）播放位置。
        用于回放进度查询和回放会话保活。
        """
        addr, proto, transport = transport_info
        device_id = asset.gb_id
        channel_id = resource.gb_id
        call_id = stream_session.call_id or ""
        from_tag = stream_session.from_tag or ""
        to_tag = stream_session.to_tag or ""
        cseq = (stream_session.cseq or 1) + 1

        mansrtsp_body = f"GET_PARAMETER RTSP/1.0\r\nCSeq: {cseq}\r\n"

        branch = f"z9hG4bK{secrets.token_hex(5)}"  # FIXED-P2: W-09 random.choices→secrets
        req = SipMessage()
        req.method = "INFO"
        req.uri = f"sip:{channel_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={from_tag}"
        to_header = f"<sip:{channel_id}@{settings.SIP_DOMAIN}>"
        if to_tag:
            to_header = f"{to_header};tag={to_tag}"
        req.headers["To"] = to_header
        req.headers["Call-ID"] = call_id
        req.headers["CSeq"] = f"{cseq} INFO"
        req.headers["Content-Type"] = "Application/MANSRTSP"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)
        req.body = mansrtsp_body

        data = req.to_bytes()
        # FIXED: 回放控制指令裸调用无异常保护
        try:
            await send_sip_bytes(proto, transport, addr, data)
        except Exception as e:
            logger.warning(f"Failed to send PLAYBACK GET_PARAMETER to {addr}: {e}")
            return
        trace_id = req.get_header("Call-ID") or ""
        logger.debug(f"[trace_id={trace_id}] Sent GET_PARAMETER (NPT query) to {channel_id}")
        await _persist_cseq(call_id, cseq)
        _sip_trace_log(
            "playback_npt_query_sent",
            trace_id=trace_id,
            device_id=device_id,
            channel_id=channel_id,
            proto=proto,
            addr=str(addr),
        )

    async def wait_get_parameter_response(self, call_id: str, timeout: float = 5.0) -> dict | None:
        """等待 GET_PARAMETER 200 OK 响应并解析 NPT 进度信息"""
        # FIXED: 实现 GET_PARAMETER 响应解析，获取回放 NPT 进度
        try:
            # 轮询等待 _npt_results 中出现结果
            deadline = asyncio.get_event_loop().time() + timeout
            while asyncio.get_event_loop().time() < deadline:
                result = _npt_results.pop(call_id, None)
                if result:
                    return result
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"wait_get_parameter_response error for {call_id}: {e}")
        return None

    # ---- 回放保活机制 ----
    _playback_keepalive_tasks: dict[str, asyncio.Task] = {}  # call_id -> keepalive Task

    async def start_playback_keepalive(self, asset, resource, stream_session, transport_info: tuple, interval: int = 30) -> None:
        """
        启动回放保活定时器。长时间暂停的回放会话可能因设备超时而终止，
        定期发送 GET_PARAMETER 保活。
        """
        call_id = stream_session.call_id or ""
        if call_id in self._playback_keepalive_tasks:
            return
        async def _keepalive_loop():
            try:
                while True:
                    await asyncio.sleep(interval)
                    try:
                        await self.send_get_parameter(asset, resource, stream_session, transport_info)
                    except Exception as e:
                        logger.warning(f"[Playback keepalive] GET_PARAMETER failed for {call_id}: {e}")
                        # FIXED-P1: W-04 保活失败后通知上层，更新StreamSession状态
                        try:
                            from app.core.database import AsyncSessionLocal
                            from app.models.stream_session import StreamSession
                            from sqlalchemy import select
                            async with AsyncSessionLocal() as session:
                                ss = (await session.execute(select(StreamSession).where(StreamSession.call_id == call_id))).scalars().first()
                                if ss:
                                    from app.services.stream_session_service import finalize_stream_session
                                    await finalize_stream_session(session, ss, reason="playback_keepalive_failed")
                                    await session.commit()
                        except Exception as _fin_err:
                            logger.debug(f"Playback keepalive finalize error: {_fin_err}")
                        break
            except asyncio.CancelledError:
                pass
            finally:
                self._playback_keepalive_tasks.pop(call_id, None)
        task = asyncio.create_task(_keepalive_loop())
        self._playback_keepalive_tasks[call_id] = task

    def stop_playback_keepalive(self, call_id: str) -> None:
        """停止回放保活定时器"""
        task = self._playback_keepalive_tasks.pop(call_id, None)
        if task and not task.done():
            task.cancel()


# FIXED: S-01 playback_control 单例未初始化导致 NameError
playback_control: "PlaybackControl | None" = None


def get_playback_control() -> "PlaybackControl | None":
    global playback_control
    return playback_control


def init_playback_control(sip_server) -> "PlaybackControl":
    """Initialize the PlaybackControl singleton. Called during SIP server startup."""
    global playback_control
    if playback_control is None:
        playback_control = PlaybackControl(sip_server)
    return playback_control
