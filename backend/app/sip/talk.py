from app.sip.message import SipMessage
from app.core.config import settings, sip_host_for_contact, sip_via_host
from app.sip.send import send_sip_bytes
from loguru import logger
import secrets  # P4 安全随机数 — random→secrets
import asyncio
import time

# 对讲 200 OK 待办：call_id -> (event, result_dict)，用于端到端对讲拿到设备 RTP 地址
_talk_pending: dict[str, tuple[asyncio.Event, dict]] = {}
_talk_pending_lock = asyncio.Lock()
_talk_pending_max_size = 5000
_talk_pending_ttl_seconds = 300
_talk_cleanup_interval = 60     # 全局定期清理间隔（秒）
_talk_stale_max_age = 600      # 超过此时间的条目视为 stale（秒）

# 对讲超时监控任务：call_id -> asyncio.Task，模块级以便 wait_talk_200_ok 超时分支可取消
_talk_timeout_tasks: dict[str, "asyncio.Task"] = {}

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
    async with _talk_pending_lock:
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
        event.set()

    # 收到 200 OK 后发送 ACK，完成 SIP 三次握手
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
            ack_branch = f"z9hG4bK{secrets.token_hex(10)}"  # P4 RFC3261 — 2xx ACK使用新branch
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

async def wait_talk_200_ok(call_id: str, timeout: float = 5.0) -> dict:
    """等待对讲 200 OK，返回包含 target_ip、target_port 的字典；超时返回空/默认。"""
    async with _talk_pending_lock:
        entry = _talk_pending.get(call_id)
    if not entry:
        return {}
    event, result = entry
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
        return result
    except asyncio.TimeoutError:
        async with _talk_pending_lock:
            _talk_pending.pop(call_id, None)
        # R25 Talk-8: 超时后发送 CANCEL 终止 INVITE 事务，
        # 否则设备可能在超时后收到 INVITE 并开始发送 RTP，但本地已无对应会话
        try:
            _addr = result.get("addr")
            _proto = result.get("proto") or "UDP"
            _transport = result.get("transport")
            _branch = result.get("branch")
            _from_h = result.get("from_header")
            _to_h = result.get("to_header")
            _sip_host = result.get("sip_host") or sip_host_for_contact()
            _sip_port = result.get("sip_port") or settings.SIP_PORT
            _cseq_val = result.get("cseq") or 1
            if _addr and _branch and _from_h and _transport:
                _cancel = SipMessage()
                _cancel.method = "CANCEL"
                _cancel.uri = f"sip:{_addr[0]}:{_addr[1]}"
                _cancel.version = "SIP/2.0"
                _cancel.headers["Via"] = f"SIP/2.0/{_proto} {_sip_host}:{_sip_port};rport;branch={_branch}"
                _cancel.headers["From"] = _from_h
                _cancel.headers["To"] = _to_h or ""
                _cancel.headers["Call-ID"] = call_id
                _cancel.headers["CSeq"] = f"{_cseq_val} CANCEL"
                _cancel.headers["Max-Forwards"] = "70"
                _cancel.headers["User-Agent"] = settings.PROJECT_NAME
                await send_sip_bytes(_proto, _transport, _addr, _cancel.to_bytes())
                logger.info(f"R25 Talk-8: Sent CANCEL for timed-out talk INVITE, call_id={call_id}")
        except Exception as _cancel_err:
            logger.warning(f"R25 Talk-8: Failed to send CANCEL for timed-out talk (call_id={call_id}): {_cancel_err}")
        _sock = result.pop("socket", None)
        if _sock:
            try:
                _sock.close()
            except Exception as _sock_err:
                # FIX [2026-07-17 P3-7]: 描述性日志替代 "silently_swallowed_exception"
                logger.warning(f"Talk: failed to close socket after timeout (call_id={call_id}): {_sock_err}")
        # FIX R23-SEVERE: 超时后释放 SSRC，避免泄漏
        _ssrc = result.get("ssrc")
        if _ssrc:
            try:
                from app.sip.ssrc_manager import ssrc_manager
                await ssrc_manager.release(_ssrc)
            except Exception as _e:
                logger.warning(f"wait_talk_200_ok: failed to release ssrc {_ssrc} on timeout: {_e}")
        # FIX R23-SEVERE: cancel 超时监控任务，避免 _talk_timeout_tasks 引用泄漏
        _timeout_task = _talk_timeout_tasks.pop(call_id, None)
        if _timeout_task and not _timeout_task.done():
            _timeout_task.cancel()
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
        "branch": branch,
        "from_header": from_header,
        "to_header": to_header,
        "transport": transport,
        "addr": addr,
        "sip_host": sip_host,
        "sip_port": sip_port,
        "proto": proto,
        "ssrc": None,
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
                        logger.warning(f"Exception: {e}")
                if not ev.is_set():
                    st["ok"] = False
                    st["reason"] = "evicted_from_overflow"
                    ev.set()
    _talk_pending[call_id] = (event, result)
    return event, result

async def _async_register_talk_pending(
    call_id: str,
    from_tag: str | None = None,
    cseq: int = 1,
    **kwargs,
) -> tuple[asyncio.Event, dict]:
    async with _talk_pending_lock:
        return _register_talk_pending(call_id, from_tag, cseq, **kwargs)

def _unregister_talk_pending(call_id: str) -> None:
    async def _do_unregister():
        async with _talk_pending_lock:
            entry = _talk_pending.pop(call_id, None)
        if entry:
            _, st = entry
            sock = st.get("socket")
            if sock:
                try:
                    sock.close()
                except Exception as e:
                    logger.warning(f"Exception: {e}")
                st.pop("socket", None)
    try:
        asyncio.get_running_loop()
        # P0-fix [2026-07-17]: 改用 fire_and_forget，提供 task name + done_callback + GC 保护
        # 原 loop.create_task(_do_unregister()) 无引用无异常回调，注销失败无任何日志
        from app.core.async_utils import fire_and_forget
        fire_and_forget(_do_unregister(), name=f"talk_unregister:{call_id}")
    except RuntimeError as _loop_err:
        # FIX [2026-07-17 P3-7]: 描述性日志替代 "swallowed_exception"，记录无事件循环场景
        logger.debug(f"unregister_talk_pending: no running loop to schedule cleanup task: {_loop_err}")

class SipTalk:
    def __init__(self, sip_server):
        self.sip_server = sip_server

    async def _generate_ssrc(self, domain_code: str) -> str:  # C-20 改为async，通过ssrc_manager统一分配
        from app.sip.ssrc_manager import ssrc_manager
        ssrc = await ssrc_manager.allocate()
        # W-14 SSRC分配耗尽时返回空字符串，需检查避免构造无效SDP
        if not ssrc:
            raise RuntimeError("SSRC allocation failed: no available SSRC for talk session")
        return ssrc

    async def send_broadcast_invite(self, asset, resource, transport_info: tuple):
        """
        Send INVITE for Voice Broadcast (Audio Out)

        FIX: [2026-07-04] NAT 穿透修复 [全栈工程师]
        根因：原实现创建原始 UDP socket 绑定 0.0.0.0:0，SDP 中使用 sip_host_for_contact()
        和随机端口。NAT/Docker 环境下设备无法到达该地址。
        修复：使用 ZLM 的 host 和 RTP proxy port 作为 SDP 媒体地址，音频经 ZLM 转发。
        """
        addr, proto, transport = transport_info
        device_id = asset.gb_id
        channel_id = resource.gb_id # Usually audio channel or device ID

        # FIX: [2026-07-04] 使用 ZLM 的 host 和 RTP 端口，而非原始 UDP socket [全栈工程师]
        zlm_host = str(settings.MEDIA_SERVER_HOST or "") or str(settings.STREAM_PUBLIC_HOST or "") or sip_host_for_contact()
        zlm_http_port = settings.MEDIA_SERVER_HTTP_PORT or settings.STREAM_PUBLIC_HTTP_PORT

        # FIX [2026-07-17 P4-1]: 优先从活跃媒体节点获取解密后的明文 secret，
        # 避免多节点部署或节点 secret 与全局不一致时 ZLM API 鉴权失败。
        _zlm_api_secret = ""
        try:
            from app.db.session import AsyncSessionLocal
            from app.core.media_nodes_db import get_active_media_node_id, get_db_node_by_id
            async with AsyncSessionLocal() as _db:
                _active_id = await get_active_media_node_id(_db)
                if _active_id:
                    _node = await get_db_node_by_id(_db, _active_id)
                    if _node:
                        _zlm_api_secret = str(_node.decrypted_secret or "").strip()
        except Exception as _node_err:
            logger.warning(f"talk: failed to read active node secret, falling back to global: {_node_err}")
        if not _zlm_api_secret:
            _zlm_api_secret = str(settings.MEDIA_SERVER_SECRET or '')

        # 查询 ZLM RTP proxy 端口（与 send_talk_invite 一致的逻辑）
        _rtp_port = settings.MEDIA_SERVER_RTP_PROXY_PORT
        if not _rtp_port:
            try:
                from app.core.http_client import get_http_client
                _client = await get_http_client()
                _url = f"http://{zlm_host}:{zlm_http_port}/index/api/getServerConfig"
                _resp = await _client.post(_url, data={"secret": _zlm_api_secret}, timeout=3.0)
                if _resp.status_code == 200:
                    _data = _resp.json() or {}
                    if _data.get("code") in (0, "0"):
                        for _item in (_data.get("data") or []):
                            if _item.get("key") == "rtp_proxy.port":
                                _rtp_port = int(_item.get("value") or 0)
                                break
            except Exception as _zlm_cfg_err:
                logger.warning(f"Failed to query ZLM getServerConfig for broadcast RTP port: {_zlm_cfg_err}")
        if not _rtp_port:
            raise RuntimeError("Cannot determine ZLM RTP port for broadcast INVITE")

        media_ip = zlm_host  # 使用 ZLM 的 host 作为媒体地址
        local_port = _rtp_port  # 使用 ZLM 的 RTP proxy 端口
        ssrc = await self._generate_ssrc(settings.SIP_DOMAIN)  # C-20 _generate_ssrc已改为async

        # SDP for Audio Broadcast (G.711A/PCMA or G.711U/PCMU)
        # s=Play
        # m=audio <port> RTP/AVP 8
        # 对讲SDP编码协商 — 同时提供PCMA和PCMU，让设备选择支持的编码
        sdp_lines = [
            "v=0",
            f"o={settings.SIP_ID} 0 0 IN IP4 {media_ip}",
            "s=Play",
            f"c=IN IP4 {media_ip}",
            "t=0 0",
            f"m=audio {local_port} RTP/AVP 8 0",
            "a=rtpmap:8 PCMA/8000",
            "a=rtpmap:0 PCMU/8000",
            "a=sendonly",
            f"y={ssrc}",
        ]
        # FIX: [2026-07-17 P1] SDP 行结束符使用 CRLF（RFC 4566 §5 要求）
        sdp = "\r\n".join(sdp_lines) + "\r\n"
        req = SipMessage()
        req.method = "INVITE"
        req.uri = f"sip:{device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"

        branch = f"z9hG4bK{secrets.token_hex(10)}"
        tag = secrets.token_hex(8)
        call_id = f"{secrets.token_hex(10)}@{sip_via_host()}"

        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={tag}"
        req.headers["To"] = f"<sip:{device_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = call_id
        # FIX [2026-07-17 P1]: CSeq 单调递增（RFC 3261 §22.2）
        from app.sip.commander import _next_cseq as _talk_next_cseq
        req.headers["CSeq"] = f"{_talk_next_cseq()} INVITE"
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
            raise

        logger.info(f"Sent Broadcast INVITE to {device_id} (SSRC: {ssrc}, ZLM RTP Port: {local_port})")
        await _async_register_talk_pending(
            call_id, from_tag=tag, cseq=1,
            branch=branch,
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
            st["ssrc"] = ssrc  # S-06 存储ssrc到pending，供错误路径释放
            # FIX: [2026-07-04] 存储 ZLM app/stream，send_bye 中 close_zlm_stream 需要正确参数关闭流 [全栈工程师]
            # 根因：send_bye 默认使用 app="talk"/stream=call_id 关闭 ZLM 流，
            # 但广播端点实际使用 app="broadcast"/stream=f"broadcast_{call_id}"，
            # 参数不匹配导致 ZLM 流无法关闭，RTP Server 端口泄漏。
            st["app"] = "broadcast"
            st["stream"] = f"broadcast_{call_id}"
        # FIX: [2026-07-04] 返回 ZLM 信息，WebSocket 端点用于发送 RTP 和 startSendRtp [全栈工程师]
        return {
            "socket": None,  # 不再使用原始 socket
            "ssrc": ssrc,
            "call_id": call_id,
            "from_tag": tag,
            "zlm_host": zlm_host,
            "zlm_http_port": zlm_http_port,
            "zlm_rtp_port": local_port,
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
        # 实现双向对讲 INVITE — SDP 中 a=sendrecv 替代 a=sendonly
        ssrc = await self._generate_ssrc(gb_domain)  # C-20 _generate_ssrc已改为async
        call_id = f"talk_{int(time.time() * 1000)}_{secrets.randbelow(9000) + 1000}@{sip_via_host()}"  # P4 安全随机数 — random→secrets
        branch = f"z9hG4bK{secrets.token_hex(10)}"
        tag = secrets.token_hex(8)

        # S-15 Talk INVITE不应回退到硬编码端口10000
        # zlm_rtp_port 为 0 时查询 ZLM 获取实际 RTP 端口，而非使用硬编码值
        from app.core.config import settings as _settings
        _rtp_port = zlm_rtp_port
        if not _rtp_port:
            _rtp_port = getattr(_settings, "MEDIA_SERVER_RTP_PROXY_PORT", 0) or 0
        if not _rtp_port:
            # FIX [2026-07-17 P4-1]: 优先从活跃媒体节点获取解密后的明文 secret，
            # 避免多节点部署或节点 secret 与全局不一致时 ZLM API 鉴权失败。
            _zlm_api_secret = ""
            try:
                from app.db.session import AsyncSessionLocal
                from app.core.media_nodes_db import get_active_media_node_id, get_db_node_by_id
                async with AsyncSessionLocal() as _db:
                    _active_id = await get_active_media_node_id(_db)
                    if _active_id:
                        _node = await get_db_node_by_id(_db, _active_id)
                        if _node:
                            _zlm_api_secret = str(_node.decrypted_secret or "").strip()
            except Exception as _node_err:
                logger.warning(f"talk: failed to read active node secret for talk INVITE: {_node_err}")
            if not _zlm_api_secret:
                _zlm_api_secret = str(getattr(_settings, 'MEDIA_SERVER_SECRET', '') or '')
            # 尝试从 ZLM getServerConfig API 查询实际 rtp_proxy.port
            try:
                from app.core.http_client import get_http_client
                _client = await get_http_client()
                _url = f"http://{zlm_host}:{zlm_http_port}/index/api/getServerConfig"
                # P-SEC: secret 通过 POST body 传递，避免出现在 URL/代理日志中
                _resp = await _client.post(_url, data={"secret": _zlm_api_secret}, timeout=3.0)
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
        # FIX: [2026-07-04] 双向对讲 INVITE URI 使用 device_id 而非 channel_id [全栈工程师]
        # 根因：GB28181 对讲 INVITE 的 Request-URI 应为目标设备 ID（与广播一致），
        # 原代码使用 channel_id 导致设备无法识别对讲请求（设备-as-通道回退时尤甚）。
        # 修复：URI 和 To 头使用 device_id，Subject 头保留 channel_id。
        to_header = f"<sip:{device_id}@{sip_domain}>"

        req = SipMessage()
        req.method = "INVITE"
        req.uri = f"sip:{device_id}@{device_host}:{device_port}"
        req.version = "SIP/2.0"
        req.headers["Via"] = f"SIP/2.0/{transport.upper()} {sip_via_host()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = from_header
        req.headers["To"] = to_header
        req.headers["Call-ID"] = call_id
        # FIX [2026-07-17 P1]: CSeq 单调递增（RFC 3261 §22.2）
        from app.sip.commander import _next_cseq as _talk_next_cseq2
        req.headers["CSeq"] = f"{_talk_next_cseq2()} INVITE"
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
            # 传输层不可用时抛出明确异常
            raise RuntimeError(f"SIP transport unavailable for {device_host}:{device_port}/{proto}")

        # 先注册pending，再发送INVITE，避免快速200 OK丢失
        await _async_register_talk_pending(
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
        async with _talk_pending_lock:
            _talk_entry = _talk_pending.get(call_id)
        if _talk_entry:
            _, _talk_st = _talk_entry
            _talk_st["ssrc"] = ssrc
            # FIX: [2026-07-04] 存储 ZLM app/stream，send_bye 中 close_zlm_stream 需要正确参数关闭流 [全栈工程师]
            # 根因：send_bye 默认使用 stream=call_id 关闭 ZLM 流，
            # 但双向对讲实际使用 stream=zlm_stream_id（如 talk_{channel_id}_{ws_id}），
            # 参数不匹配导致 ZLM 流无法关闭，RTP Server 端口泄漏。
            _talk_st["app"] = "talk"
            _talk_st["stream"] = zlm_stream_id

        try:
            await send_sip_bytes(proto, _transport, addr, req.to_bytes())
        except Exception:
            async with _talk_pending_lock:
                _talk_pending.pop(call_id, None)
            from app.sip.ssrc_manager import ssrc_manager
            try:
                await ssrc_manager.release(ssrc)
            except Exception as _ssrc_err:
                logger.warning(f"[Talk] Failed to release SSRC {ssrc} after send failure: {_ssrc_err}")
            raise
        logger.info(f"Sent Talk INVITE to {channel_id}@{device_host}:{device_port} (SSRC: {ssrc})")

        whip_url = f"http://{zlm_host}:{zlm_http_port}/index/api/whip?app=talk&stream={zlm_stream_id}"

        result = {
            "call_id": call_id,
            "ssrc": ssrc,
            "whip_url": whip_url,
            "zlm_stream_id": zlm_stream_id,
            "status": "inviting",
            "from_tag": tag,
        }

        # GB28181协议 — 保存超时任务引用以便取消
        task = asyncio.create_task(self.start_talk_timeout_monitor(call_id))
        _talk_timeout_tasks[call_id] = task

        return result

    async def start_talk_timeout_monitor(self, call_id: str, timeout: int = 300):
        """对讲会话超时自动挂断（默认5分钟无RTP流自动BYE）"""
        await asyncio.sleep(timeout)
        async with _talk_pending_lock:
            pending = _talk_pending.get(call_id)
        if pending:
            state = pending[1]
            # FIX: [2026-08-22 PN] status=ended 仅跳过 BYE 发送；
            # 原实现 ended 时跳过整个清理块 → pending 残留、SSRC 泄漏
            if state.get("status") != "ended":
                logger.info(f"Talk session {call_id} timed out, sending BYE")
                try:
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
                        bye.headers["Via"] = f"SIP/2.0/{_proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={bye_branch}"
                        bye.headers["From"] = _from_header
                        bye.headers["To"] = bye_to
                        bye.headers["Call-ID"] = call_id
                        bye.headers["CSeq"] = f"{_cseq} BYE"
                        bye.headers["Max-Forwards"] = "70"
                        bye.headers["User-Agent"] = settings.PROJECT_NAME
                        await send_sip_bytes(_proto, _transport, _addr, bye.to_bytes())

                    state["status"] = "ended"
                except Exception as e:
                    logger.warning(f"Failed to send BYE for timed-out talk session {call_id}: {e}")
            # 清理（无论是否 ended）：释放 SSRC 并移除 pending
            try:
                # S-17 对讲超时挂断时释放SSRC，防止泄漏
                _timeout_ssrc = state.get("ssrc")
                if _timeout_ssrc:
                    try:
                        from app.sip.ssrc_manager import ssrc_manager
                        await ssrc_manager.release(str(_timeout_ssrc))
                    except Exception as _ssrc_rel_err:
                        logger.warning(f"Failed to release SSRC for timed-out talk session {call_id}: {_ssrc_rel_err}")
                async with _talk_pending_lock:
                    _talk_pending.pop(call_id, None)
            except Exception as e:
                logger.warning(f"Failed to cleanup timed-out talk session {call_id}: {e}")

    async def send_bye(self, asset, transport_info: tuple, call_id: str) -> bool:
        async with _talk_pending_lock:
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
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_via_host()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={from_tag}" if from_tag else f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>"
        req.headers["To"] = to_header
        req.headers["Call-ID"] = call_id
        req.headers["CSeq"] = f"{cseq} BYE"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        data = req.to_bytes()
        # R25 Talk-9: send_sip_bytes 未 try/except，失败会导致后续清理（socket/SSRC/dialog）全部跳过
        try:
            await send_sip_bytes(proto, transport, addr, data)
        except Exception as _bye_send_err:
            logger.warning(f"Talk BYE send_sip_bytes failed for call_id={call_id}: {_bye_send_err}")
        sock = state.get("socket")
        if sock:
            try:
                sock.close()
            except Exception as e:
                logger.warning(f"Exception: {e}")
            state.pop("socket", None)
        async with _talk_pending_lock:
            _talk_pending.pop(call_id, None)
        _timeout_task = _talk_timeout_tasks.pop(call_id, None)
        if _timeout_task and not _timeout_task.done():
            _timeout_task.cancel()
        # 对讲BYE后释放dialog
        try:
            from app.sip.dialog_manager import dialog_manager
            from_tag_val = (state.get("from_tag") or "").strip()
            if call_id and from_tag_val:
                await dialog_manager.terminate_dialog(call_id, from_tag_val)
        except Exception as e:
            logger.warning(f"Failed to terminate dialog for talk BYE {call_id}: {e}")
        # GB28181协议 — 对讲BYE后释放SSRC和关闭ZLM流
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

async def start_talk_cleanup_loop() -> None:
    """全局定期清理 stale 的对讲会话条目，关闭其中的 socket 并释放 SSRC。"""
    while True:
        await asyncio.sleep(_talk_cleanup_interval)
        try:
            now = time.time()
            stale_keys = []
            async with _talk_pending_lock:
                for call_id, (ev, st) in _talk_pending.items():
                    age = now - st.get("created_at", 0)
                    if age > _talk_stale_max_age:
                        stale_keys.append(call_id)
            for call_id in stale_keys:
                async with _talk_pending_lock:
                    removed = _talk_pending.pop(call_id, None)
                if removed:
                    ev, st = removed
                    sock = st.get("socket")
                    if sock:
                        try:
                            sock.close()
                        except Exception as _sock_err:
                            # FIX [2026-07-17 P3-7]: 描述性日志替代 "silently_swallowed_exception"
                            logger.warning(f"Talk cleanup loop: failed to close socket: {_sock_err}")
                    ssrc = st.get("ssrc")
                    if ssrc:
                        try:
                            from app.sip.ssrc_manager import ssrc_manager
                            await ssrc_manager.release(str(ssrc))
                        except Exception as _ssrc_err:
                            logger.warning(f"Cleanup loop: failed to release SSRC {ssrc}: {_ssrc_err}")
                    if not ev.is_set():
                        st["ok"] = False
                        st["reason"] = "cleaned_up_stale"
                        ev.set()
                    logger.info(f"Talk cleanup: removed stale session {call_id}")
        except Exception as e:
            logger.warning(f"Talk cleanup loop error: {e}")

# Singleton
sip_talk = None


def get_sip_talk() -> "SipTalk":
    """Get the SipTalk singleton. Raises RuntimeError if not initialized."""
    global sip_talk
    if sip_talk is None:
        raise RuntimeError("SipTalk not initialized. Call init_sip_talk() first.")
    return sip_talk


def init_sip_talk(sip_server) -> "SipTalk":
    """Initialize the SipTalk singleton. Called during SIP server startup."""
    global sip_talk
    if sip_talk is None:
        sip_talk = SipTalk(sip_server)
    return sip_talk
