"""
GB28181 语音广播模块
支持：语音广播(Broadcast) - 向设备喊话
与语音对讲不同，广播是单向的：平台 -> 设备
"""
from app.sip.message import SipMessage
from app.sip.send import send_sip_bytes
from app.core.config import settings, sip_host_for_contact
# 统一使用 sip_trace 模块的 trace 函数，消除重复定义
from app.sip.sip_trace import sip_trace_should_log as _sip_trace_should_log, sip_trace_log as _sip_trace_log
from app.db.session import AsyncSessionLocal
from app.models.stream_session import StreamSession
from sqlalchemy import select
from loguru import logger
import secrets  # P4 安全随机数 — random→secrets
import string
import asyncio
import time  # 缺少 import time 导致 time.time() NameError 崩溃




def _attach_trace_header(req: SipMessage) -> None:
    call_id = (req.get_header("Call-ID") or "").strip()
    if call_id:
        req.headers["X-Trace-ID"] = call_id


class Broadcast:
    """语音广播类"""

    BROADCAST_INVITE_TIMEOUT = 30

    def __init__(self, sip_server):
        self.sip_server = sip_server
        self._watchdog_tasks: dict[str, asyncio.Task] = {}

    async def _broadcast_invite_watchdog(self, call_id: str, ssrc: str, timeout: int = 30) -> None:
        try:
            await asyncio.sleep(timeout)
            from app.sip.invite import invite_state
            if call_id not in invite_state._invite_pending:
                return
            invite_state._invite_pending.pop(call_id, None)
            logger.warning(f"[Broadcast] INVITE watchdog timed out for call_id={call_id}, cleaning pending and releasing SSRC")
            from app.sip.ssrc_manager import ssrc_manager
            try:
                await ssrc_manager.release(ssrc)
            except Exception as e:
                logger.warning(f"[Broadcast] Watchdog failed to release SSRC {ssrc}: {e}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(f"[Broadcast] INVITE watchdog error for call_id={call_id}: {e}")
        finally:
            self._watchdog_tasks.pop(call_id, None)

    async def send_broadcast_invite(self, asset, resource, transport_info: tuple, ssrc: str, media_server_ip: str, media_server_port: int) -> str:
        """
        发送语音广播 INVITE 请求
        
        Args:
            asset: 设备资产对象
            channel_id: 通道ID
            transport_info: (addr, proto, transport) 传输信息
            ssrc: 同步源标识
            media_server_ip: 媒体服务器IP
            media_server_port: 媒体服务器端口
            
        Returns:
            call_id: SIP Call-ID
        """
        addr, proto, transport = transport_info
        device_id = asset.gb_id
        channel_id = resource.gb_id

        # Generate Call-ID and tag
        call_id = f"{secrets.randbelow(900000) + 100000}_broadcast@{sip_host_for_contact()}"  # P4 安全随机数 — random→secrets
        tag = secrets.token_hex(4)  # P4 安全随机数 — random→secrets
        branch = f"z9hG4bK{secrets.token_hex(5)}"  # P4 安全随机数 — random→secrets

        # Build SDP
        # 广播SDP编码协商 — 同时提供PCMA和PCMU，让设备选择支持的编码
        sdp_body = f"""v=0
o={settings.SIP_ID} 0 0 IN IP4 {sip_host_for_contact()}
s=Broadcast
u={channel_id}
c=IN IP4 {media_server_ip}
t=0 0
m=audio {media_server_port} RTP/AVP 8 0
a=rtpmap:8 PCMA/8000
a=rtpmap:0 PCMU/8000
a=sendonly
y={ssrc}
f=v///a///
"""

        req = SipMessage()
        req.method = "INVITE"
        req.uri = f"sip:{device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"

        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={tag}"
        req.headers["To"] = f"<sip:{device_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = call_id
        req.headers["CSeq"] = "1 INVITE"
        req.headers["Content-Type"] = "application/sdp"
        req.headers["Contact"] = f"<sip:{settings.SIP_ID}@{sip_host_for_contact()}:{settings.SIP_PORT}>"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        req.headers["Subject"] = f"{channel_id}:{ssrc},{settings.SIP_ID}:2"
        _attach_trace_header(req)

        req.body = sdp_body

        from app.sip.invite import register_ssrc_waiter, _register_invite_pending, invite_state
        _event, _result = _register_invite_pending(call_id)
        _result["type"] = "broadcast"
        _result["ssrc"] = ssrc

        try:
            data = req.to_bytes()
            await send_sip_bytes(proto, transport, addr, data)
        except Exception:
            invite_state.invite_pending.pop(call_id, None)
            from app.sip.ssrc_manager import ssrc_manager
            try:
                await ssrc_manager.release(ssrc)
            except Exception as _ssrc_err:
                logger.warning(f"[Broadcast] Failed to release SSRC {ssrc} after send failure: {_ssrc_err}")
            raise

        try:
            async with AsyncSessionLocal() as session:
                existing = (
                    await session.execute(select(StreamSession).where(StreamSession.call_id == call_id))
                ).scalars().first()
                if not existing:
                    stream_session = StreamSession(
                        app="broadcast",
                        stream=channel_id,
                        resource_id=resource.id,
                        asset_id=asset.id,
                        call_id=call_id,
                        from_tag=tag,
                        via_branch=branch,
                        cseq=1,
                        ssrc=ssrc,
                        protocol=str(proto or "UDP"),
                        media_server_id="",
                        media_ip=media_server_ip,
                        media_port=int(media_server_port or 0),
                        media_port_lease_id=None,
                    )
                    session.add(stream_session)
                    await session.commit()
        except Exception as e:
            logger.error(f"[Broadcast] StreamSession save failed for channel {channel_id}: {e}")

        trace_id = req.get_header("Call-ID") or ""
        logger.info(f"[trace_id={trace_id}] Sent BROADCAST INVITE to {channel_id}")

        _sip_trace_log(
            "broadcast_invite_sent",
            trace_id=trace_id,
            device_id=device_id,
            channel_id=channel_id,
            ssrc=ssrc,
            proto=proto,
            addr=str(addr),
        )

        watchdog_task = asyncio.create_task(
            self._broadcast_invite_watchdog(call_id, ssrc, timeout=self.BROADCAST_INVITE_TIMEOUT)
        )
        self._watchdog_tasks[call_id] = watchdog_task

        return call_id

    async def send_broadcast_bye(self, asset, stream_session: StreamSession, transport_info: tuple):
        """
        发送语音广播 BYE 请求（停止广播）
        
        Args:
            asset: 设备资产对象
            channel_id: 通道ID
            transport_info: (addr, proto, transport) 传输信息
            call_id: SIP Call-ID
        """
        addr, proto, transport = transport_info
        device_id = asset.gb_id
        channel_id = stream_session.stream or ""
        from_tag = stream_session.from_tag
        if not from_tag:
            logger.error(f"[Broadcast] Cannot send BYE without from_tag for session {stream_session.call_id}")
            from_tag = "untagged"
        branch = f"z9hG4bK{secrets.token_hex(5)}"  # P4 安全随机数 — random→secrets
        to_header = f"<sip:{channel_id}@{settings.SIP_DOMAIN}>" if channel_id else f"<sip:{device_id}@{settings.SIP_DOMAIN}>"
        if stream_session.to_tag:
            to_header = f"{to_header};tag={stream_session.to_tag}"

        req = SipMessage()
        req.method = "BYE"
        req.uri = f"sip:{device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"

        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={from_tag}"
        req.headers["To"] = to_header
        req.headers["Call-ID"] = stream_session.call_id
        req.headers["CSeq"] = f"{(stream_session.cseq or 1) + 1} BYE"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        _attach_trace_header(req)

        data = req.to_bytes()
        await send_sip_bytes(proto, transport, addr, data)

        trace_id = req.get_header("Call-ID") or ""
        logger.info(f"[trace_id={trace_id}] Sent BROADCAST BYE to {channel_id}")
        _sip_trace_log(
            "broadcast_bye_sent",
            trace_id=trace_id,
            device_id=device_id,
            channel_id=channel_id,
            proto=proto,
            addr=str(addr),
        )


# Singleton instance
broadcast = None


def get_broadcast() -> "Broadcast":
    """Get the Broadcast singleton. Raises RuntimeError if not initialized."""
    global broadcast
    if broadcast is None:
        raise RuntimeError("SipBroadcast not initialized. Call init_broadcast() first.")
    return broadcast


def init_broadcast(sip_server) -> "Broadcast":
    """Initialize the Broadcast singleton. Called during SIP server startup."""
    global broadcast
    if broadcast is None:
        broadcast = Broadcast(sip_server)
    return broadcast
