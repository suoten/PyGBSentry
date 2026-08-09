from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.models.asset import Asset
from app.models.resource import Resource
from app.models.user import User
import app.sip.talk as sip_talk_module
from app.sip.talk import wait_talk_200_ok, _unregister_talk_pending
from app.sip.server import sip_server
from app.core.config import settings
from loguru import logger

router = APIRouter()


# FIX: [2026-07-03] 前端发送 PCM 16bit LE，SDP 协商 PCMA(G.711A)，需在服务端转码 [全栈工程师]
# G.711 A-law 编码查找表（PCM 16-bit → A-law 8-bit）
# 基于 ITU-T G.711 标准 A-law companding 算法预计算
_ALAW_ENCODE_TABLE = bytearray(65536)


def _build_alaw_table() -> None:
    """预构建 PCM 16-bit signed → G.711 A-law 查找表。"""
    for i in range(65536):
        # 将无符号 16-bit 映射到有符号 16-bit
        pcm_val = i - 32768
        sign = 0
        magnitude = pcm_val
        if pcm_val < 0:
            sign = 0x80
            magnitude = -pcm_val
        if magnitude > 32635:
            magnitude = 32635
        # A-law 编码
        if magnitude < 256:
            alaw_byte = magnitude >> 4
        else:
            # 找到最高有效位所在段
            exponent = 1
            tmp = magnitude >> 5
            while tmp != 0:
                exponent += 1
                tmp >>= 1
            mantissa = (magnitude >> (exponent + 3)) & 0x0F
            alaw_byte = ((exponent - 1) << 4) | mantissa
        # A-law 需要异或 0x55
        _ALAW_ENCODE_TABLE[i] = (alaw_byte | sign) ^ 0x55


_build_alaw_table()


def pcm16le_to_alaw(pcm_data: bytes) -> bytes:
    """将 PCM 16-bit little-endian 数据转换为 G.711 A-law (PCMA) 字节流。"""
    if len(pcm_data) < 2:
        return b""
    # 确保数据长度为偶数（每个采样 2 字节）
    aligned_len = len(pcm_data) & ~1
    result = bytearray(aligned_len // 2)
    for j in range(0, aligned_len, 2):
        # 将 2 字节 LE 转为 0-65535 无符号索引
        idx = pcm_data[j] | (pcm_data[j + 1] << 8)
        result[j // 2] = _ALAW_ENCODE_TABLE[idx]
    return bytes(result)


# RTP Header Construction
def create_rtp_packet(payload: bytes, ssrc: int, seq: int, timestamp: int) -> bytes:
    # V=2, P=0, X=0, CC=0, M=0, PT=8 (PCMA)
    header = bytearray(12)
    header[0] = 0x80
    header[1] = 0x08 # Payload Type 8 (PCMA)

    # Sequence Number
    header[2] = (seq >> 8) & 0xFF
    header[3] = seq & 0xFF

    # Timestamp
    header[4] = (timestamp >> 24) & 0xFF
    header[5] = (timestamp >> 16) & 0xFF
    header[6] = (timestamp >> 8) & 0xFF
    header[7] = timestamp & 0xFF

    # SSRC
    header[8] = (ssrc >> 24) & 0xFF
    header[9] = (ssrc >> 16) & 0xFF
    header[10] = (ssrc >> 8) & 0xFF
    header[11] = ssrc & 0xFF

    return header + payload

@router.websocket("/ws/talk/{device_id}")
async def websocket_talk(websocket: WebSocket, device_id: str, ticket: str = Query(default=""), db: AsyncSession = Depends(get_db)):
    # P0-6: 改用短期一次性 ws-ticket 认证，消除 URL 暴露 JWT token
    # C-02 WebSocket auth — verify before accepting connection
    if not ticket:
        await websocket.close(code=4401, reason="Authentication required")
        return
    from app.core.ws_ticket import consume_ws_ticket
    jwt_payload = await consume_ws_ticket(ticket)
    if not jwt_payload or not jwt_payload.get("sub"):
        await websocket.close(code=4401, reason="Invalid or expired ticket")
        return

    # N-04 添加租户隔离 — 从payload获取user_id，查询用户tenant_id
    _user_id = jwt_payload.get("sub")
    _user_stmt = select(User).where(User.id == _user_id)
    _user_row = (await db.execute(_user_stmt)).scalars().first()
    _tenant_id = (_user_row.tenant_id or "default") if _user_row else "default"

    # FIX: [2026-07-04] WebSocket 端点缺少 RBAC 权限校验，viewer 只读用户可发起广播 [全栈工程师]
    _user_role = ((_user_row.role or "") if _user_row else "").lower()
    if _user_role == "viewer":
        await websocket.close(code=4403, reason="Permission denied: insufficient role")
        return

    await websocket.accept()

    # 1. Prepare Device
    # N-04 添加租户隔离
    stmt = select(Asset).where(Asset.gb_id == device_id, Asset.tenant_id == _tenant_id)
    result = await db.execute(stmt)
    asset = result.scalars().first()

    if not asset or not asset.ip_addr:
        await websocket.close(code=1000, reason="Device not found")
        return

    # Use asset itself as resource for broadcast usually
    resource = asset

    # M-07 检查sip_server就绪状态
    if not sip_server or not (sip_server.udp_transport or sip_server.tcp_server):
        await websocket.close(code=1011, reason="SIP service not ready")
        return

    if asset.transport == "UDP":
        transport = sip_server.udp_transport
    else:
        transport = sip_server.tcp_server  # M-06 TCP传输时保留transport="TCP"而非设为None


    if not transport:
        await websocket.close(code=1011, reason="SIP transport unavailable")
        return

    if not sip_talk_module.sip_talk:
        await websocket.close(code=1011, reason="SIP service not ready")
        return

    # 2. Start SIP Session
    call_id = None
    sock = None  # FIX: [2026-07-04] 初始化 sock 变量，避免 finally 中 NameError [全栈工程师]
    _rtp_pusher_started = False  # 标记是否已启动 ZLM RTP pusher
    try:
        session_info = await sip_talk_module.sip_talk.send_broadcast_invite(asset, resource, ((asset.ip_addr, asset.port), asset.transport, transport))
        # FIX: [2026-07-04] 使用 ZLM 路由音频，不再使用原始 socket 直接发送 [全栈工程师]
        ssrc_int = int(session_info["ssrc"])
        call_id = session_info.get("call_id")
        zlm_host = session_info.get("zlm_host") or settings.MEDIA_SERVER_HOST or settings.STREAM_PUBLIC_HOST
        zlm_http_port = session_info.get("zlm_http_port") or int(settings.MEDIA_SERVER_HTTP_PORT or 0) or int(settings.STREAM_PUBLIC_HTTP_PORT or 0)
        zlm_rtp_port = session_info.get("zlm_rtp_port") or int(settings.MEDIA_SERVER_RTP_PROXY_PORT or 0)

        # 创建 UDP socket 用于向 ZLM RTP 端口发送音频
        import socket as _socket
        sock = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
        sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
        sock.bind(('0.0.0.0', 0))

        target_ip = asset.ip_addr
        target_port = settings.SIP_TALK_DEFAULT_PORT
        if call_id:
            rtp_info = await wait_talk_200_ok(call_id, timeout=5.0)
            if rtp_info.get("target_ip"):
                target_ip = rtp_info["target_ip"]
            if rtp_info.get("target_port") is not None:
                target_port = rtp_info["target_port"]
            logger.info(f"Talk RTP target from 200 OK: {target_ip}:{target_port}")

            # FIX: [2026-07-04] 通过 ZLM startSendRtp 将音频转发到设备 [全栈工程师]
            # 根因：原始实现直接用 UDP socket 发送 RTP 到设备，NAT 环境下不可达。
            # 修复：先通过 ZLM RTP proxy 接收后端音频，再用 startSendRtp 转发到设备。
            try:
                from app.services.zlm_stream_control import start_rtp_pusher
                _broadcast_app = "broadcast"
                _broadcast_stream = f"broadcast_{call_id}"
                _pusher_ok = await start_rtp_pusher(
                    host=zlm_host,
                    http_port=zlm_http_port,
                    secret=settings.MEDIA_SERVER_SECRET or '',
                    app=_broadcast_app,
                    stream=_broadcast_stream,
                    dst_ip=target_ip,
                    dst_port=target_port,
                    ssrc=str(ssrc_int),
                    is_tcp=False,
                )
                if _pusher_ok:
                    _rtp_pusher_started = True
                    logger.info(f"Broadcast RTP pusher started: ZLM -> {target_ip}:{target_port}")
                else:
                    logger.warning("Broadcast RTP pusher failed, falling back to direct UDP")
            except Exception as _pusher_err:
                logger.warning(f"Broadcast start_rtp_pusher error: {_pusher_err}")

        logger.info("Talk session started. Waiting for audio...")

        seq = 0
        timestamp = 0

        while True:
            # FIX: [2026-07-03] 前端发送 PCM 16bit LE，后端需转码为 G.711A 后再封装 RTP [全栈工程师]
            # Receive PCM 16-bit LE data from frontend
            pcm_data = await websocket.receive_bytes()

            # Convert PCM 16-bit to G.711 A-law (PCMA)
            alaw_data = pcm16le_to_alaw(pcm_data)

            # Encapsulate RTP
            packet = create_rtp_packet(alaw_data, ssrc_int, seq, timestamp)

            # FIX: [2026-07-04] 发送到 ZLM RTP proxy 端口（而非直接发送到设备）[全栈工程师]
            sock.sendto(packet, (zlm_host, zlm_rtp_port))

            seq = (seq + 1) % 65536
            timestamp += len(alaw_data) # 1 byte = 1 sample for G.711

    except WebSocketDisconnect:
        logger.info("Talk session ended")
    except Exception as e:
        logger.error(f"Talk error: {e}")
    finally:
        # FIX: [2026-07-04] 停止 ZLM RTP pusher 并关闭 socket [全栈工程师]
        if _rtp_pusher_started:
            try:
                from app.services.zlm_stream_control import stop_rtp_pusher
                await stop_rtp_pusher(zlm_host, zlm_http_port, settings.MEDIA_SERVER_SECRET or '', "broadcast", f"broadcast_{call_id}")
            except Exception as _stop_err:
                logger.warning(f"Broadcast stop_rtp_pusher error: {_stop_err}")
        if call_id:
            try:
                if sip_talk_module.sip_talk and transport:
                    await sip_talk_module.sip_talk.send_bye(asset, ((asset.ip_addr, asset.port), asset.transport, transport), call_id)
            except Exception as e:
                logger.warning(f"发送BYE失败: {e}")
            _unregister_talk_pending(call_id)
        if sock:
            try:
                sock.close()
            except Exception as e:
                logger.debug(f"talk: failed to close socket: {e}")


# 双向对讲 WebSocket 端点 — 接入 send_talk_invite 实现双向音频
@router.websocket("/talk/bidirectional/{device_id}/{channel_id}")
async def websocket_bidirectional_talk(
    websocket: WebSocket,
    device_id: str,
    channel_id: str,
    ticket: str = Query(default=""),  # P0-6: 改用 ws-ticket（原 C-14 JWT 鉴权）
    db: AsyncSession = Depends(get_db),
):
    """
    双向对讲 WebSocket 端点。
    - 前端→设备: 前端通过 WebSocket 发送 PCMA 音频→服务端封装 RTP→发送到 ZLM RTP 端口→ZLM 转发给设备
    - 设备→前端: 设备发送 RTP→ZLM 接收→前端通过 WHEP/HLS 拉流获取
    """
    # P0-6: 改用短期一次性 ws-ticket 认证，消除 URL 暴露 JWT token
    # C-14 防止未授权访问
    if not ticket:
        await websocket.close(code=4401, reason="Authentication required")
        return
    from app.core.ws_ticket import consume_ws_ticket
    jwt_payload = await consume_ws_ticket(ticket)
    if not jwt_payload or not jwt_payload.get("sub"):
        await websocket.close(code=4401, reason="Invalid or expired ticket")
        return

    # N-04 添加租户隔离 — 从payload获取user_id，查询用户tenant_id
    _user_id = jwt_payload.get("sub")
    _user_stmt = select(User).where(User.id == _user_id)
    _user_row = (await db.execute(_user_stmt)).scalars().first()
    _tenant_id = (_user_row.tenant_id or "default") if _user_row else "default"

    # FIX: [2026-07-04] WebSocket 双向对讲端点缺少 RBAC 权限校验 [全栈工程师]
    _user_role = ((_user_row.role or "") if _user_row else "").lower()
    if _user_role == "viewer":
        await websocket.close(code=4403, reason="Permission denied: insufficient role")
        return

    await websocket.accept()

    # 1. 查找设备和通道
    # N-04 添加租户隔离
    asset_stmt = select(Asset).where(Asset.gb_id == device_id, Asset.tenant_id == _tenant_id)
    asset = (await db.execute(asset_stmt)).scalars().first()
    if not asset or not asset.ip_addr:
        await websocket.close(code=1000, reason="Device not found or offline")
        return

    resource_stmt = select(Resource).where(Resource.gb_id == channel_id, Resource.asset_id == asset.id)
    resource = (await db.execute(resource_stmt)).scalars().first()
    if not resource:
        # FIX: [2026-07-04] 设备-as-通道回退时使用 device_id 作为 channel_id [全栈工程师]
        # 根因：Resource 不存在时回退 resource=asset，但 send_talk_invite 的 channel_id
        # 仍用 URL 中的 channel_id（可能不匹配设备实际通道），导致设备拒绝对讲请求。
        # 修复：回退时将 channel_id 设为 device_id（设备自身作为音频通道）。
        logger.info(f"Resource {channel_id} not found for asset {device_id}, using device_id as channel for talk")
        channel_id = device_id

    if not sip_talk_module.sip_talk:
        await websocket.close(code=1011, reason="SIP service not ready")
        return

    # 2. 获取传输层
    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        await websocket.close(code=1011, reason="SIP transport unavailable")
        return

    # 3. 调用 send_talk_invite 建立双向对讲
    call_id = None
    _rtp_pusher_started = False  # FIX: [2026-07-04] 标记 ZLM RTP pusher 是否已启动 [全栈工程师]
    try:
        zlm_host = settings.MEDIA_SERVER_HOST
        zlm_http_port = settings.MEDIA_SERVER_HTTP_PORT
        zlm_stream_id = f"talk_{channel_id}_{id(websocket)}"

        invite_result = await sip_talk_module.sip_talk.send_talk_invite(
            device_id=device_id,
            channel_id=channel_id,
            gb_domain=settings.SIP_DOMAIN,
            sip_id=settings.SIP_ID,
            sip_domain=settings.SIP_DOMAIN,
            device_host=asset.ip_addr,
            device_port=asset.port,
            zlm_host=zlm_host,
            zlm_http_port=zlm_http_port,
            zlm_stream_id=zlm_stream_id,
            transport=asset.transport or "udp",
            zlm_rtp_port=settings.MEDIA_SERVER_RTP_PROXY_PORT,
        )
        call_id = invite_result.get("call_id")
        ssrc_str = invite_result.get("ssrc", "")
        whip_url = invite_result.get("whip_url", "")

        # 4. 等待设备 200 OK，获取设备 RTP 地址
        target_ip = asset.ip_addr
        target_port = settings.SIP_TALK_DEFAULT_PORT
        if call_id:
            rtp_info = await wait_talk_200_ok(call_id, timeout=5.0)
            if rtp_info.get("target_ip"):
                target_ip = rtp_info["target_ip"]
            if rtp_info.get("target_port") is not None:
                target_port = rtp_info["target_port"]
            logger.info(f"Bidirectional talk RTP target from 200 OK: {target_ip}:{target_port}")

            # FIX: [2026-07-04] 双向对讲缺少 start_rtp_pusher，音频无法从 ZLM 转发到设备 [全栈工程师]
            # 根因：广播端点在获取设备 200 OK 后调用 start_rtp_pusher 创建 ZLM→设备的 RTP 转发，
            # 但双向对讲端点获取了设备 RTP 地址后未创建 pusher，导致前端音频到达 ZLM 后
            # 无法转发到设备。这与广播端点的实现不一致。
            # 修复：与广播端点对齐，在获取设备 RTP 地址后创建 start_rtp_pusher。
            try:
                from app.services.zlm_stream_control import start_rtp_pusher
                _pusher_ok = await start_rtp_pusher(
                    host=zlm_host,
                    http_port=zlm_http_port,
                    secret=settings.MEDIA_SERVER_SECRET or '',
                    app="talk",
                    stream=zlm_stream_id,
                    dst_ip=target_ip,
                    dst_port=target_port,
                    ssrc=ssrc_str,
                    is_tcp=False,
                )
                if _pusher_ok:
                    _rtp_pusher_started = True
                    logger.info(f"Bidirectional talk RTP pusher started: ZLM -> {target_ip}:{target_port}")
                else:
                    logger.warning("Bidirectional talk RTP pusher failed, falling back to direct UDP")
            except Exception as _pusher_err:
                logger.warning(f"Bidirectional talk start_rtp_pusher error: {_pusher_err}")

        # 5. 通过 WebSocket 发送 ZLM 流信息给前端（前端用于拉取设备回传音频）
        whep_url = f"http://{zlm_host}:{zlm_http_port}/index/api/whep?app=talk&stream={zlm_stream_id}"
        hls_url = f"http://{zlm_host}:{zlm_http_port}/live/talk/{zlm_stream_id}.m3u8"
        await websocket.send_json({
            "type": "session_ready",
            "call_id": call_id,
            "ssrc": ssrc_str,
            "whip_url": whip_url,
            "whep_url": whep_url,
            "hls_url": hls_url,
            "zlm_stream_id": zlm_stream_id,
        })

        # 6. 创建 UDP socket 用于向 ZLM RTP 端口发送音频
        import socket as _socket
        sock = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
        sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
        sock.bind(('0.0.0.0', 0))

        zlm_rtp_port = settings.MEDIA_SERVER_RTP_PROXY_PORT
        ssrc_int = int(ssrc_str) if ssrc_str and ssrc_str.isdigit() else 0
        seq = 0
        timestamp = 0

        # 7. 循环接收前端 PCM 16-bit 音频，转码为 PCMA 后封装 RTP 发送到 ZLM
        # FIX: [2026-07-03] 前端发送 PCM 16bit LE，后端需转码为 G.711A 后再封装 RTP [全栈工程师]
        while True:
            pcm_data = await websocket.receive_bytes()
            alaw_data = pcm16le_to_alaw(pcm_data)
            packet = create_rtp_packet(alaw_data, ssrc_int, seq, timestamp)
            sock.sendto(packet, (zlm_host, zlm_rtp_port))
            seq = (seq + 1) % 65536
            timestamp += len(alaw_data)

    except WebSocketDisconnect:
        logger.info("Bidirectional talk session ended by client")
    except Exception as e:
        logger.error(f"Bidirectional talk error: {e}")
    finally:
        # 8. 清理：停止 ZLM RTP pusher + 发送 BYE 挂断
        # FIX: [2026-07-04] 添加 stop_rtp_pusher 清理，与广播端点对齐 [全栈工程师]
        if _rtp_pusher_started:
            try:
                from app.services.zlm_stream_control import stop_rtp_pusher
                _zlm_host = locals().get('zlm_host', settings.MEDIA_SERVER_HOST)
                _zlm_http_port = locals().get('zlm_http_port', int(settings.MEDIA_SERVER_HTTP_PORT or 0))
                _zlm_stream_id = locals().get('zlm_stream_id', '')
                if _zlm_stream_id:
                    await stop_rtp_pusher(
                        _zlm_host, _zlm_http_port,
                        settings.MEDIA_SERVER_SECRET or '',
                        "talk", _zlm_stream_id
                    )
            except Exception as _stop_err:
                logger.warning(f"Bidirectional talk stop_rtp_pusher error: {_stop_err}")
        if call_id:
            try:
                if sip_talk_module.sip_talk and transport:
                    await sip_talk_module.sip_talk.send_bye(
                        asset,
                        ((asset.ip_addr, asset.port), asset.transport, transport),
                        call_id,
                    )
            except Exception as e:
                logger.warning(f"Bidirectional talk BYE failed: {e}")
            _unregister_talk_pending(call_id)
        if 'sock' in locals():
            try:
                sock.close()
            except Exception as _sock_err:
                # FIX [2026-07-17 P3-12]: 描述性日志替代 "silently_swallowed_exception"
                logger.warning(f"talk endpoint: failed to close talk socket: {_sock_err}")
