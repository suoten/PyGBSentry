"""
GB28181 语音广播模块
支持：语音广播(Broadcast) - 向设备喊话
与语音对讲不同，广播是单向的：平台 -> 设备
"""
from app.sip.message import SipMessage
from app.sip.send import send_sip_bytes
from app.core.config import settings, sip_host_for_contact, sip_via_host, sip_from_to_host
# 统一使用 sip_trace 模块的 trace 函数，消除重复定义
from app.sip.sip_trace import sip_trace_log as _sip_trace_log
from app.db.session import AsyncSessionLocal
from app.models.stream_session import StreamSession
from sqlalchemy import select
from loguru import logger
import secrets  # P4 安全随机数 — random→secrets
import asyncio




def _attach_trace_header(req: SipMessage) -> str:
    """返回 Call-ID 作为 trace_id 用于日志关联。

    FIX: [2026-07-21 P0] 不再向 SIP 请求添加 X-Trace-ID 头域。
    实测发现 EasyGBS 等非标准 SIP 客户端对非标准头域（X- 开头）敏感，会返回 400 Bad Request。
    """
    return (req.get_header("Call-ID") or "").strip()


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
            # FIX: [2026-07-16 P1] 超时时清理残留的 StreamSession 记录，避免阻塞后续同 channel 广播
            try:
                from app.db.session import AsyncSessionLocal
                from sqlalchemy import delete as sa_delete
                async with AsyncSessionLocal() as session:
                    await session.execute(
                        sa_delete(StreamSession).where(StreamSession.call_id == call_id)
                    )
                    await session.commit()
                logger.info(f"[Broadcast] Cleaned up stale StreamSession for call_id={call_id}")
            except Exception as e:
                logger.warning(f"[Broadcast] Watchdog failed to clean StreamSession for call_id={call_id}: {e}")
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
        # P1-fix: Call-ID 改用 80 位随机十六进制，与 talk.py/invite.py 一致
        # 原实现仅 6 位十进制数（900,000 个值），批量广播场景下生日悖论约 1100 次后碰撞概率 >1%
        call_id = f"{secrets.token_hex(8)}_broadcast@{sip_via_host()}"
        # FIX [2026-07-17 P1]: tag 与 branch 提升至 64 位随机性（token_hex(8)），
        # 符合 RFC 3261 §8.1.1.7（branch 全局唯一）和 §19.3（from-tag 全局唯一）要求。
        # 原 token_hex(4)/token_hex(5) 仅 32/40 位，批量广播时碰撞概率非可忽略。
        tag = secrets.token_hex(8)
        branch = f"z9hG4bK{secrets.token_hex(8)}"

        # Build SDP
        # 广播SDP编码协商 — 同时提供PCMA和PCMU，让设备选择支持的编码
        # FIX: [2026-07-17 P1] SDP 行结束符使用 CRLF（RFC 4566 §5 要求）
        _sdp_lines = [
            "v=0",
            f"o={settings.SIP_ID} 0 0 IN IP4 {sip_host_for_contact()}",
            "s=Broadcast",
            f"u={channel_id}",
            f"c=IN IP4 {media_server_ip}",
            "t=0 0",
            f"m=audio {media_server_port} RTP/AVP 8 0",
            "a=rtpmap:8 PCMA/8000",
            "a=rtpmap:0 PCMU/8000",
            "a=sendonly",
            f"y={ssrc}",
            "f=v///a///",
        ]
        sdp_body = "\r\n".join(_sdp_lines) + "\r\n"

        req = SipMessage()
        req.method = "INVITE"
        req.uri = f"sip:{device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"

        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={tag}"
        req.headers["To"] = f"<sip:{device_id}@{sip_from_to_host()}>"
        req.headers["Call-ID"] = call_id
        # FIX [2026-07-17 P1]: CSeq 必须单调递增（RFC 3261 §22.2），原硬编码 "1 INVITE"
        # 会导致同一对话内的后续请求（如 BYE）CSeq 冲突，部分设备（如海康/大华）会
        # 因 CSeq 重复而拒绝。使用 commander._next_cseq() 进程级单调递增计数器。
        from app.sip.commander import _next_cseq as _broadcast_next_cseq
        _broadcast_cseq = _broadcast_next_cseq()
        req.headers["CSeq"] = f"{_broadcast_cseq} INVITE"
        req.headers["Content-Type"] = "application/sdp"
        req.headers["Contact"] = f"<sip:{settings.SIP_ID}@{sip_host_for_contact()}:{settings.SIP_PORT}>"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        req.headers["Subject"] = f"{channel_id}:{ssrc},{settings.SIP_ID}:2"
        _attach_trace_header(req)

        req.body = sdp_body

        from app.sip.invite import _register_invite_pending, invite_state
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
                        # FIX [2026-07-17 P1]: 持久化实际 CSeq 而非硬编码 1，
                        # 确保后续 BYE 请求的 CSeq 能正确递增。
                        cseq=_broadcast_cseq,
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
            self._broadcast_invite_watchdog(call_id, ssrc, timeout=self.BROADCAST_INVITE_TIMEOUT),
            name=f"broadcast_invite_watchdog:{call_id}",  # P2-fix: 便于任务排查
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
        branch = f"z9hG4bK{secrets.token_hex(8)}"  # FIX [2026-07-17 P1]: 64位随机性
        to_header = f"<sip:{channel_id}@{sip_from_to_host()}>" if channel_id else f"<sip:{device_id}@{sip_from_to_host()}>"
        if stream_session.to_tag:
            to_header = f"{to_header};tag={stream_session.to_tag}"

        req = SipMessage()
        req.method = "BYE"
        req.uri = f"sip:{device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"

        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={from_tag}"
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
