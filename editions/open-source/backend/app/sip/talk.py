from app.sip.message import SipMessage
from app.core.config import settings, sip_host_for_contact
from app.sip.send import send_sip_bytes
import logging
import secrets  # FIXED: P4 安全随机数 — random→secrets
import string
import socket
import asyncio
import time

logger = logging.getLogger(__name__)

# 对讲 200 OK 待办：call_id -> (event, result_dict)，用于端到端对讲拿到设备 RTP 地址
_talk_pending: dict[str, tuple[asyncio.Event, dict]] = {}
_talk_pending_max_size = 5000
_talk_pending_ttl_seconds = 300

def _parse_sdp_connection_and_audio_port(body: str) -> tuple[str | None, int | None]:
    from app.sip.sdp import parse_sdp, pick_media

    parsed = parse_sdp(body or "")
    md = pick_media(parsed, "audio") or {}
    ip = md.get("connection_ip") or parsed.get("connection_ip")
    try:
        port = int(md.get("port") or 0)
    except Exception:
        port = 0
    return (str(ip) if ip else None, port if port > 0 else None)

async def on_talk_200_ok(call_id: str, sdp_body: str, to_tag: str | None = None) -> None:
    """收到对讲 INVITE 的 200 OK 时调用，解析设备 RTP 地址、发送 ACK、通知等待方。"""
    entry = _talk_pending.get(call_id)
    if not entry:
        return
    event, result = entry
    ip, port = _parse_sdp_connection_and_audio_port(sdp_body)
    if ip is not None:
        result["target_ip"] = ip
    if port is not None:
        result["target_port"] = port
    if to_tag:
        result["to_tag"] = to_tag
    result["ok"] = True

    # FIXED: 收到 200 OK 后发送 ACK，完成 SIP 三次握手
    try:
        _branch = result.get("branch")
        _from_header = result.get("from_header")
        _to_header = result.get("to_header")
        _cseq = result.get("cseq", 1)
        _transport = result.get("transport")
        _addr = result.get("addr")
        _sip_host = result.get("sip_host")
        _sip_port = result.get("sip_port")
        _proto = result.get("proto") or "UDP"

        if _branch and _from_header and _to_header and _transport and _addr:
            # 构建 To header（追加 to_tag）
            ack_to_header = _to_header
            if to_tag and "tag=" not in ack_to_header:
                ack_to_header = f"{ack_to_header};tag={to_tag}"

            ack = SipMessage()
            ack.method = "ACK"
            ack.uri = f"sip:{ip or _addr[0]}:{port or _addr[1]}" if ip and port else f"sip:{_addr[0]}:{_addr[1]}"
            ack.version = "SIP/2.0"
            ack_branch = f"z9hG4bK{secrets.token_hex(10)}"  # FIXED: P4 RFC3261 — 2xx ACK使用新branch
            ack.headers["Via"] = f"SIP/2.0/{_proto} {_sip_host or ''}:{_sip_port or 5060};rport;branch={ack_branch}"
            ack.headers["From"] = _from_header
            ack.headers["To"] = ack_to_header
            ack.headers["Call-ID"] = call_id
            ack.headers["CSeq"] = f"{_cseq} ACK"
            ack.headers["Max-Forwards"] = "70"
            ack.headers["User-Agent"] = settings.PROJECT_NAME
            await send_sip_bytes(_proto, _transport, _addr, ack.to_bytes())
            logger.info(f"Sent ACK for talk INVITE, call_id={call_id}")
    except Exception as e:
        logger.warning(f"Failed to send ACK for talk INVITE: {e}")

    event.set()

async def wait_talk_200_ok(call_id: str, timeout: float = 5.0) -> dict:
    """等待对讲 200 OK，返回包含 target_ip、target_port 的字典；超时返回空/默认。"""
    entry = _talk_pending.get(call_id)
    if not entry:
        return {}
    event, result = entry
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
        return result
    except asyncio.TimeoutError:
        # FIXED-P0: C-22 超时后清理pending条目并关闭socket，防止资源泄漏
        _talk_pending.pop(call_id, None)
        _sock = result.pop("socket", None)
        if _sock:
            try:
                _sock.close()
            except Exception:
                pass
        return result

def _register_talk_pending(
    call_id: str,
    from_tag: str | None = None,
    cseq: int = 1,
    *,
    branch: str | None = None,
    from_header: str | None = None,
    to_header: str | None = None,
    transport = None,
    addr: tuple | None = None,
    sip_host: str | None = None,
    sip_port: int | None = None,
    proto: str | None = None,
) -> tuple[asyncio.Event, dict]:
    event = asyncio.Event()
    result = {
        "ok": False,
        "target_ip": None,
        "target_port": None,
        "from_tag": (from_tag or "").strip() or None,
        "to_tag": None,
        "cseq": int(cseq or 1),
        "created_at": time.time(),
        # FIXED: 保存 ACK 所需的上下文字段
        "branch": branch,
        "from_header": from_header,
        "to_header": to_header,
        "transport": transport,
        "addr": addr,
        "sip_host": sip_host,
        "sip_port": sip_port,
        "proto": proto,
        "ssrc": None,  # FIXED-P0: S-06 存储ssrc，供错误路径释放
    }
    if len(_talk_pending) >= _talk_pending_max_size:
        now = time.time()
        stale = [k for k, (ev, st) in _talk_pending.items() if ev.is_set() or (now - st.get("created_at", 0)) > _talk_pending_ttl_seconds]
        for k in stale:
            removed = _talk_pending.pop(k, None)
            if removed:
                ev, st = removed
                sock = st.get("socket")
                if sock:
                    try:
                        sock.close()
                    except Exception as e:
                        logger.debug(f"Exception: {e}")
                if not ev.is_set():
                    st["ok"] = False
                    st["reason"] = "evicted_from_overflow"
                    ev.set()
    _talk_pending[call_id] = (event, result)
    return event, result

def _unregister_talk_pending(call_id: str) -> None:
    entry = _talk_pending.pop(call_id, None)
    if entry:
        _, st = entry
        sock = st.get("socket")
        if sock:
            try:
                sock.close()
            except Exception as e:
                logger.debug(f"Exception: {e}")
            st.pop("socket", None)

class SipTalk:
    def __init__(self, sip_server):
        self.sip_server = sip_server

    async def _generate_ssrc(self, domain_code: str) -> str:  # FIXED-P1: C-20 改为async，通过ssrc_manager统一分配
        from app.sip.ssrc_manager import ssrc_manager
        return await ssrc_manager.allocate()

    async def send_broadcast_invite(self, asset, resource, transport_info: tuple):
        """
        Send INVITE for Voice Broadcast (Audio Out)
        """
        addr, proto, transport = transport_info
        device_id = asset.gb_id
        channel_id = resource.gb_id # Usually audio channel or device ID
        
        # Audio sender needs a UDP port.
        # For prototype, we will bind a random UDP port for RTP sending
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('0.0.0.0', 0))
            local_port = sock.getsockname()[1]
        except Exception:
            if sock:
                sock.close()
            raise
        
        media_ip = sip_host_for_contact()
        ssrc = await self._generate_ssrc(settings.SIP_DOMAIN)  # FIXED-P1: C-20 _generate_ssrc已改为async
        
        # SDP for Audio Broadcast (G.711A/PCMA or G.711U/PCMU)
        # s=Play
        # m=audio <port> RTP/AVP 8
        # FIXED: 对讲SDP编码协商 — 同时提供PCMA和PCMU，让设备选择支持的编码
        sdp_lines = [
            f"v=0",
            f"o={settings.SIP_ID} 0 0 IN IP4 {media_ip}",
            f"s=Play",
            f"c=IN IP4 {media_ip}",
            f"t=0 0",
            f"m=audio {local_port} RTP/AVP 8 0",
            f"a=rtpmap:8 PCMA/8000",
            f"a=rtpmap:0 PCMU/8000",
            f"a=sendonly",
            f"y={ssrc}",
        ]
        sdp = "\n".join(sdp_lines) + "\n"
        req = SipMessage()
        req.method = "INVITE"
        req.uri = f"sip:{device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"
        
        branch = f"z9hG4bK{secrets.token_hex(10)}"
        tag = secrets.token_hex(8)
        call_id = f"{secrets.token_hex(10)}@{sip_host_for_contact()}"
        
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={tag}"
        req.headers["To"] = f"<sip:{device_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = call_id
        req.headers["CSeq"] = "1 INVITE"
        req.headers["Contact"] = f"<sip:{settings.SIP_ID}@{sip_host_for_contact()}:{settings.SIP_PORT}>"
        req.headers["Content-Type"] = "application/sdp"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        req.headers["Subject"] = f"{channel_id}:{ssrc},{settings.SIP_ID}:0"
        
        req.body = sdp
        
        # Send
        data = req.to_bytes()
        try:
            await send_sip_bytes(proto, transport, addr, data)
        except Exception:
            if sock:
                sock.close()
            raise
            
        logger.info(f"Sent Broadcast INVITE to {device_id} (SSRC: {ssrc}, Local Port: {local_port})")
        _register_talk_pending(
            call_id, from_tag=tag, cseq=1,
            branch=branch,  # FIXED-P0: C-13 补充ACK所需上下文，否则三次握手无法完成
            from_header=f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={tag}",
            to_header=f"<sip:{device_id}@{settings.SIP_DOMAIN}>",
            transport=transport,
            addr=addr,
            sip_host=sip_host_for_contact(),
            sip_port=settings.SIP_PORT,
            proto=proto,
        )
        entry = _talk_pending.get(call_id)
        if entry:
            _, st = entry
            st["socket"] = sock
            st["ssrc"] = ssrc  # FIXED-P0: S-06 存储ssrc到pending，供错误路径释放
        return {
            "socket": sock,
            "ssrc": ssrc,
            "call_id": call_id,
            "from_tag": tag,
        }

    async def send_talk_invite(
        self,
        device_id: str,
        channel_id: str,
        gb_domain: str,
        sip_id: str,
        sip_domain: str,
        device_host: str,
        device_port: int,
        zlm_host: str,
        zlm_http_port: int,
        zlm_stream_id: str,
        transport: str = "udp",
        zlm_rtp_port: int = 0,
    ) -> dict:
        """发送双向对讲 INVITE (a=sendrecv)，通过 ZLM WHIP 接收前端音频上行"""
        # FIXED: 实现双向对讲 INVITE — SDP 中 a=sendrecv 替代 a=sendonly
        ssrc = await self._generate_ssrc(gb_domain)  # FIXED-P1: C-20 _generate_ssrc已改为async
        call_id = f"talk_{int(time.time() * 1000)}_{secrets.randbelow(9000) + 1000}@{sip_host_for_contact()}"  # FIXED: P4 安全随机数 — random→secrets
        branch = f"z9hG4bK{secrets.token_hex(10)}"
        tag = secrets.token_hex(8)

        # FIXED-P2: S-15 Talk INVITE不应回退到硬编码端口10000
        # zlm_rtp_port 为 0 时查询 ZLM 获取实际 RTP 端口，而非使用硬编码值
        from app.core.config import settings as _settings
        _rtp_port = zlm_rtp_port
        if not _rtp_port:
            _rtp_port = getattr(_settings, "MEDIA_SERVER_RTP_PROXY_PORT", 0) or 0
        if not _rtp_port:
            # 尝试从 ZLM getServerConfig API 查询实际 rtp_proxy.port
            try:
                from app.core.http_client import get_http_client
                _client = await get_http_client()
                _url = f"http://{zlm_host}:{zlm_http_port}/index/api/getServerConfig"
                _resp = await _client.get(_url, params={"secret": getattr(_settings, 'MEDIA_SERVER_SECRET', '') or ''}, timeout=3.0)
                if _resp.status_code == 200:
                    _data = _resp.json() or {}
                    if _data.get("code") in (0, "0"):
                        for _item in (_data.get("data") or []):
                            if _item.get("key") == "rtp_proxy.port":
                                _rtp_port = int(_item.get("value") or 0)
                                break
            except Exception as _zlm_cfg_err:
                logger.warning(f"Failed to query ZLM getServerConfig for RTP port: {_zlm_cfg_err}")
        if not _rtp_port:
            raise RuntimeError(f"Cannot determine ZLM RTP port for talk INVITE: zlm_rtp_port={zlm_rtp_port}, MEDIA_SERVER_RTP_PROXY_PORT={getattr(_settings, 'MEDIA_SERVER_RTP_PROXY_PORT', None)}")

        # 构建 SDP — 双向音频
        sdp_body = (
            f"v=0\r\n"
            f"o={sip_id} 0 0 IN IP4 {zlm_host}\r\n"
            f"s=Talk\r\n"
            f"c=IN IP4 {zlm_host}\r\n"
            f"t=0 0\r\n"
            f"m=audio {_rtp_port} RTP/AVP 8 0\r\n"
            f"a=rtpmap:8 PCMA/8000\r\n"
            f"a=rtpmap:0 PCMU/8000\r\n"
            f"a=sendrecv\r\n"
            f"y={ssrc}\r\n"
            f"f=v/0/0/0 a/1/8/1\r\n"
        )

        subject = f"{channel_id}:{ssrc},{sip_id}:0"

        from_header = f"<sip:{sip_id}@{sip_domain}>;tag={tag}"
        to_header = f"<sip:{channel_id}@{sip_domain}>"

        req = SipMessage()
        req.method = "INVITE"
        req.uri = f"sip:{channel_id}@{device_host}:{device_port}"
        req.version = "SIP/2.0"
        req.headers["Via"] = f"SIP/2.0/{transport.upper()} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = from_header
        req.headers["To"] = to_header
        req.headers["Call-ID"] = call_id
        req.headers["CSeq"] = "1 INVITE"
        req.headers["Contact"] = f"<sip:{sip_id}@{sip_host_for_contact()}:{settings.SIP_PORT}>"
        req.headers["Content-Type"] = "application/sdp"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        req.headers["Subject"] = subject
        req.body = sdp_body

        # 获取 SIP 传输层
        proto = transport.upper()
        _transport = self.sip_server.get_transport(device_host, device_port, proto)
        addr = (device_host, device_port)

        if _transport is None:
            # FIXED: 传输层不可用时抛出明确异常
            raise RuntimeError(f"SIP transport unavailable for {device_host}:{device_port}/{proto}")

        # 发送 INVITE
        await send_sip_bytes(proto, _transport, addr, req.to_bytes())
        logger.info(f"Sent Talk INVITE to {channel_id}@{device_host}:{device_port} (SSRC: {ssrc})")

        # 使用 ZLM WHIP 端点作为音频上行入口
        # 前端通过 WebRTC WHIP 推流到 ZLM，ZLM 再通过 RTP 转发给设备
        whip_url = f"http://{zlm_host}:{zlm_http_port}/index/api/whip?app=talk&stream={zlm_stream_id}"

        result = {
            "call_id": call_id,
            "ssrc": ssrc,
            "whip_url": whip_url,
            "zlm_stream_id": zlm_stream_id,
            "status": "inviting",
            "from_tag": tag,
        }

        # FIXED: 注册 pending 时保存 ACK 所需的完整上下文
        _register_talk_pending(
            call_id,
            from_tag=tag,
            cseq=1,
            branch=branch,
            from_header=from_header,
            to_header=to_header,
            transport=_transport,
            addr=addr,
            sip_host=sip_host_for_contact(),
            sip_port=settings.SIP_PORT,
            proto=proto,
        )
        # FIXED-P0: S-06 存储ssrc到pending，供错误路径释放
        _talk_entry = _talk_pending.get(call_id)
        if _talk_entry:
            _, _talk_st = _talk_entry
            _talk_st["ssrc"] = ssrc
        # FIXED: GB28181协议 — 保存超时任务引用以便取消
        self._talk_timeout_tasks = getattr(self, '_talk_timeout_tasks', {})
        task = asyncio.create_task(self.start_talk_timeout_monitor(call_id))
        self._talk_timeout_tasks[call_id] = task

        return result

    async def start_talk_timeout_monitor(self, call_id: str, timeout: int = 300):
        """对讲会话超时自动挂断（默认5分钟无RTP流自动BYE）"""
        # FIXED: 对讲会话超时自动挂断
        await asyncio.sleep(timeout)
        pending = _talk_pending.get(call_id)
        if pending and pending[1].get("status") != "ended":
            logger.info(f"Talk session {call_id} timed out, sending BYE")
            try:
                state = pending[1]
                _addr = state.get("addr")
                _transport = state.get("transport")
                _proto = state.get("proto") or "UDP"
                _from_tag = (state.get("from_tag") or "").strip()
                _to_tag = (state.get("to_tag") or "").strip()
                _from_header = state.get("from_header") or ""
                _to_header = state.get("to_header") or ""
                _cseq = int(state.get("cseq") or 1) + 1

                if _addr and _transport:
                    bye_branch = f"z9hG4bK{secrets.token_hex(10)}"
                    bye_to = _to_header
                    if _to_tag and "tag=" not in bye_to:
                        bye_to = f"{bye_to};tag={_to_tag}"

                    bye = SipMessage()
                    bye.method = "BYE"
                    bye.uri = f"sip:{_addr[0]}:{_addr[1]}"
                    bye.version = "SIP/2.0"
                    bye.headers["Via"] = f"SIP/2.0/{_proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={bye_branch}"
                    bye.headers["From"] = _from_header
                    bye.headers["To"] = bye_to
                    bye.headers["Call-ID"] = call_id
                    bye.headers["CSeq"] = f"{_cseq} BYE"
                    bye.headers["Max-Forwards"] = "70"
                    bye.headers["User-Agent"] = settings.PROJECT_NAME
                    await send_sip_bytes(_proto, _transport, _addr, bye.to_bytes())

                state["status"] = "ended"
                # FIXED-P2: S-17 对讲超时挂断时释放SSRC，防止泄漏
                _timeout_ssrc = state.get("ssrc")
                if _timeout_ssrc:
                    try:
                        from app.sip.ssrc_manager import ssrc_manager
                        await ssrc_manager.release(str(_timeout_ssrc))
                    except Exception as _ssrc_rel_err:
                        logger.warning(f"Failed to release SSRC for timed-out talk session {call_id}: {_ssrc_rel_err}")
                _talk_pending.pop(call_id, None)
            except Exception as e:
                logger.warning(f"Failed to send BYE for timed-out talk session {call_id}: {e}")

    async def send_bye(self, asset, transport_info: tuple, call_id: str) -> bool:
        entry = _talk_pending.get(call_id)
        if not entry:
            return False
        _, state = entry
        addr, proto, transport = transport_info
        device_id = asset.gb_id
        from_tag = (state.get("from_tag") or "").strip()
        to_tag = (state.get("to_tag") or "").strip()
        cseq = int(state.get("cseq") or 1) + 1
        state["cseq"] = cseq

        branch = f"z9hG4bK{secrets.token_hex(10)}"
        to_header = f"<sip:{device_id}@{settings.SIP_DOMAIN}>"
        if to_tag:
            to_header = f"{to_header};tag={to_tag}"
        req = SipMessage()
        req.method = "BYE"
        req.uri = f"sip:{device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={from_tag}" if from_tag else f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>"
        req.headers["To"] = to_header
        req.headers["Call-ID"] = call_id
        req.headers["CSeq"] = f"{cseq} BYE"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        data = req.to_bytes()
        await send_sip_bytes(proto, transport, addr, data)
        sock = state.get("socket")
        if sock:
            try:
                sock.close()
            except Exception as e:
                logger.debug(f"Exception: {e}")
            state.pop("socket", None)
        _talk_pending.pop(call_id, None)
        # FIXED: GB28181协议 — 取消对讲超时监控任务
        self._talk_timeout_tasks = getattr(self, '_talk_timeout_tasks', {})
        _timeout_task = self._talk_timeout_tasks.pop(call_id, None)
        if _timeout_task and not _timeout_task.done():
            _timeout_task.cancel()
        # FIXED: 对讲BYE后释放dialog
        try:
            from app.sip.dialog_manager import dialog_manager
            from_tag_val = (state.get("from_tag") or "").strip()
            if call_id and from_tag_val:
                await dialog_manager.terminate_dialog(call_id, from_tag_val)
        except Exception as e:
            logger.warning(f"Failed to terminate dialog for talk BYE {call_id}: {e}")
        # FIXED: GB28181协议 — 对讲BYE后释放SSRC和关闭ZLM流
        try:
            from app.sip.ssrc_manager import ssrc_manager
            _ssrc = state.get("ssrc")
            if _ssrc:
                await ssrc_manager.release(_ssrc)
        except Exception as e:
            logger.warning(f"Failed to release SSRC for talk session {call_id}: {e}")
        try:
            from app.services.zlm_stream_control import close_zlm_stream
            _talk_app = str(state.get("app", "") or "talk")
            _talk_stream = str(state.get("stream", "") or call_id)
            _talk_node_id = str(state.get("media_server_id", "") or "")
            await close_zlm_stream(app=_talk_app, stream=_talk_stream, node_id=_talk_node_id or None)
        except Exception as e:
            logger.warning(f"Failed to close ZLM stream for talk session {call_id}: {e}")
        return True

# Singleton
sip_talk = None
