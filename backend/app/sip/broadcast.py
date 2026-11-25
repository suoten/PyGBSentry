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
import time


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

            # FIX: [2026-08-22 PN] 原访问不存在的 invite_state._invite_pending（实际属性名
            # 为 invite_pending），AttributeError 被外层 except 吞掉，导致看门狗超时后
            # SSRC/StreamSession/pending 条目泄漏。
            if call_id not in invite_state.invite_pending:
                return
            invite_state.invite_pending.pop(call_id, None)
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
                    await session.execute(sa_delete(StreamSession).where(StreamSession.call_id == call_id))
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

    # ---- 前置 MESSAGE 探测学习(ROADMAP Phase2:厂商模式自动探测) ----
    # FIX [2026-11-21]:开启 BROADCAST_PRE_MESSAGE_ENABLED 后不再需要按厂商手工判断——
    # 平台自动探测每台设备对标准流程的支持:
    #   设备 200 OK 确认 → 清除记忆,后续继续走 MESSAGE 前置;
    #   设备 4xx/6xx 拒绝 → 记忆 24h,后续直接 INVITE(不认标准流程的机型);
    #   等待超时   → 记忆 1h(短周期),后续先直接 INVITE 避免每次喊话都干等超时,
    #               1h 后会重新探测一次(设备固件可能升级)。
    # 进程内存缓存即可(重启后重新探测一次,代价可忽略)。
    _pre_message_skip_until: dict[str, float] = {}
    _PRE_MSG_SKIP_DENY_TTL_SECONDS = 24 * 3600.0
    _PRE_MSG_SKIP_TIMEOUT_TTL_SECONDS = 3600.0

    def _pre_message_skipped(self, device_id: str) -> bool:
        until = self._pre_message_skip_until.get(device_id, 0.0)
        if until <= 0.0:
            return False
        if time.monotonic() >= until:
            self._pre_message_skip_until.pop(device_id, None)
            return False
        return True

    def _remember_pre_message_skip(self, device_id: str, ttl_seconds: float) -> None:
        self._pre_message_skip_until[device_id] = time.monotonic() + max(60.0, float(ttl_seconds))
        if len(self._pre_message_skip_until) > 20000:
            now = time.monotonic()
            for k in [k for k, v in self._pre_message_skip_until.items() if v <= now][:10000]:
                self._pre_message_skip_until.pop(k, None)

    async def send_broadcast_message(self, asset, channel_id: str, transport_info: tuple) -> bool:
        """发送标准 GB28181 §9.2.1 Broadcast MESSAGE(喊话前置信令)并等待设备最终响应。

        FIX [2026-11-20 P1] (wvp #2268/#2265 大华喊话兼容):标准流程要求平台先发
        Broadcast MESSAGE(SourceID/TargetID),设备 200 OK 确认后平台再 INVITE 音频流。
        原实现跳过 MESSAGE 直接 INVITE,大华等严格按标准流程的设备会拒绝喊话。
        返回 True=设备确认(或发出成功但未等响应的降级路径);False=发送失败。
        调用方无论结果都应继续 INVITE(MESSAGE 只是兼容前置,不是硬性握手)。

        FIX [2026-11-21] (ROADMAP Phase2 厂商模式自动探测):对每台设备自动学习其对
        标准流程的支持情况——拒绝(记 24h)/超时(记 1h)的设备后续直接 INVITE,
        确认的设备继续 MESSAGE 前置。开启开关后无需按厂商手工区分。
        """
        addr, proto, transport = transport_info
        device_id = str(getattr(asset, "gb_id", "") or "")
        if not device_id or not channel_id:
            return False
        if self._pre_message_skipped(device_id):
            logger.debug(f"[Broadcast] Pre-MESSAGE skipped for {device_id} (device does not support it, cached)")
            return True
        sn = secrets.randbelow(900000) + 100000
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Notify>
<CmdType>Broadcast</CmdType>
<SN>{sn}</SN>
<SourceID>{settings.SIP_ID}</SourceID>
<TargetID>{channel_id}</TargetID>
</Notify>
"""
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"
        call_id = f"{secrets.token_hex(8)}_bcpre@{sip_via_host()}"
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch=z9hG4bK{secrets.token_hex(8)}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{sip_from_to_host()}>;tag={secrets.token_hex(8)}"
        req.headers["To"] = f"<sip:{device_id}@{sip_from_to_host()}>"
        req.headers["Call-ID"] = call_id
        from app.sip.commander import _next_cseq as _bc_next_cseq

        req.headers["CSeq"] = f"{_bc_next_cseq()} MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        req.body = xml_body
        _attach_trace_header(req)

        timeout_seconds = max(1.0, float(getattr(settings, "BROADCAST_PRE_MESSAGE_TIMEOUT_SECONDS", 5.0)))
        tx_manager = None
        try:
            from app.sip.invite import _get_client_tx_manager

            tx_manager = _get_client_tx_manager()
        except Exception:
            tx_manager = None

        if tx_manager:
            event = asyncio.Event()
            result = {"status": 0}

            async def _bc_message_response(msg: SipMessage, addr_t: tuple, proto_t: str, transport_t):
                if msg.get_header("Call-ID") != call_id:
                    return False
                cseq_val = str(msg.get_header("CSeq") or "").strip()
                cseq_method = cseq_val.split(" ", 1)[1].strip().upper() if " " in cseq_val else ""
                if cseq_method != "MESSAGE":
                    return False
                status_code = int(getattr(msg, "status_code", 0) or 0)
                if 200 <= status_code < 300:
                    result["status"] = status_code
                    event.set()
                    return True
                if 400 <= status_code < 700:
                    result["status"] = status_code
                    event.set()
                    return True
                return False

            try:
                self.sip_server.register_response_handler(_bc_message_response)
                try:
                    await tx_manager.send_request(req, addr, proto, transport)
                    await asyncio.wait_for(event.wait(), timeout=timeout_seconds)
                except asyncio.TimeoutError:
                    logger.info(
                        f"[Broadcast] Pre-MESSAGE no response from {device_id} in {timeout_seconds}s (device may not require it), continuing INVITE"
                    )
                    # 自动探测:超时设备短周期跳过,避免每次喊话干等超时;1h 后重新探测
                    self._remember_pre_message_skip(device_id, self._PRE_MSG_SKIP_TIMEOUT_TTL_SECONDS)
                    return True
                finally:
                    try:
                        self.sip_server.unregister_response_handler(_bc_message_response)
                    except Exception:
                        pass
                if 200 <= result["status"] < 300:
                    logger.info(f"[Broadcast] Pre-MESSAGE confirmed by {device_id} ({result['status']})")
                    self._pre_message_skip_until.pop(device_id, None)
                    return True
                logger.warning(f"[Broadcast] Pre-MESSAGE rejected by {device_id} ({result['status']}), continuing INVITE anyway")
                # 自动探测:设备明确拒绝标准流程 → 记忆 24h,后续直接 INVITE
                self._remember_pre_message_skip(device_id, self._PRE_MSG_SKIP_DENY_TTL_SECONDS)
                return False
            except Exception as e:
                logger.warning(f"[Broadcast] Pre-MESSAGE via tx_manager failed: {e}, falling back to direct send")

        try:
            await send_sip_bytes(proto, transport, addr, req.to_bytes())
            logger.info(f"[Broadcast] Pre-MESSAGE sent (fire-and-forget) to {device_id}")
            return True
        except Exception as e:
            logger.warning(f"[Broadcast] Pre-MESSAGE send failed for {device_id}: {e}")
            return False

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
                existing = (await session.execute(select(StreamSession).where(StreamSession.call_id == call_id))).scalars().first()
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
