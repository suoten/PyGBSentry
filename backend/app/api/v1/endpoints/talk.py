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
from app.core import security
from loguru import logger

router = APIRouter()


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
async def websocket_talk(websocket: WebSocket, device_id: str, token: str = Query(default=""), db: AsyncSession = Depends(get_db)):
    # C-02 WebSocket auth — verify JWT before accepting connection
    if not token:
        await websocket.close(code=4401, reason="Authentication required")
        return
    try:
        jwt_payload = security.verify_token(token)
    except Exception:
        await websocket.close(code=4401, reason="Invalid or expired token")
        return

    # N-04 添加租户隔离 — 从JWT获取user_id，查询用户tenant_id
    _user_id = jwt_payload.get("sub")
    _user_stmt = select(User).where(User.id == _user_id)
    _user_row = (await db.execute(_user_stmt)).scalars().first()
    _tenant_id = (_user_row.tenant_id or "default") if _user_row else "default"

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

    transport_info = ((asset.ip_addr, asset.port), asset.transport, transport)

    if not transport:
        await websocket.close(code=1011, reason="SIP transport unavailable")
        return

    if not sip_talk_module.sip_talk:
        await websocket.close(code=1011, reason="SIP service not ready")
        return

    # 2. Start SIP Session
    call_id = None
    try:
        session_info = await sip_talk_module.sip_talk.send_broadcast_invite(asset, resource, ((asset.ip_addr, asset.port), asset.transport, transport))
        sock = session_info["socket"]
        ssrc_int = int(session_info["ssrc"])
        call_id = session_info.get("call_id")
        target_ip = asset.ip_addr
        target_port = settings.SIP_TALK_DEFAULT_PORT
        if call_id:
            rtp_info = await wait_talk_200_ok(call_id, timeout=5.0)
            if rtp_info.get("target_ip"):
                target_ip = rtp_info["target_ip"]
            if rtp_info.get("target_port") is not None:
                target_port = rtp_info["target_port"]
            logger.info("Talk RTP target from 200 OK: %s:%s", target_ip, target_port)
        logger.info("Talk session started. Waiting for audio...")

        seq = 0
        timestamp = 0

        while True:
            # Receive G.711A (PCMA) data from frontend
            data = await websocket.receive_bytes()

            # Encapsulate RTP
            packet = create_rtp_packet(data, ssrc_int, seq, timestamp)

            # Send UDP
            sock.sendto(packet, (target_ip, target_port))

            seq = (seq + 1) % 65536
            timestamp += len(data) # Assuming 1 byte = 1 sample for G.711

    except WebSocketDisconnect:
        logger.info("Talk session ended")
    except Exception as e:
        logger.error(f"Talk error: {e}")
    finally:
        if call_id:
            try:
                if sip_talk_module.sip_talk and transport:
                    await sip_talk_module.sip_talk.send_bye(asset, ((asset.ip_addr, asset.port), asset.transport, transport), call_id)
            except Exception as e:
                logger.warning(f"发送BYE失败: {e}")
            _unregister_talk_pending(call_id)
        if 'sock' in locals():
            sock.close()


# 双向对讲 WebSocket 端点 — 接入 send_talk_invite 实现双向音频
@router.websocket("/talk/bidirectional/{device_id}/{channel_id}")
async def websocket_bidirectional_talk(
    websocket: WebSocket,
    device_id: str,
    channel_id: str,
    token: str = Query(default=""),  # C-14 双向对讲WebSocket添加JWT鉴权
    db: AsyncSession = Depends(get_db),
):
    """
    双向对讲 WebSocket 端点。
    - 前端→设备: 前端通过 WebSocket 发送 PCMA 音频→服务端封装 RTP→发送到 ZLM RTP 端口→ZLM 转发给设备
    - 设备→前端: 设备发送 RTP→ZLM 接收→前端通过 WHEP/HLS 拉流获取
    """
    # C-14 验证JWT token，防止未授权访问
    if not token:
        await websocket.close(code=4401, reason="Authentication required")
        return
    try:
        jwt_payload = security.verify_token(token)
    except Exception:
        await websocket.close(code=4401, reason="Invalid or expired token")
        return

    # N-04 添加租户隔离 — 从JWT获取user_id，查询用户tenant_id
    _user_id = jwt_payload.get("sub")
    _user_stmt = select(User).where(User.id == _user_id)
    _user_row = (await db.execute(_user_stmt)).scalars().first()
    _tenant_id = (_user_row.tenant_id or "default") if _user_row else "default"

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
        # 回退：使用 asset 自身作为 resource
        resource = asset

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

        # 7. 循环接收前端 PCMA 音频，封装 RTP 发送到 ZLM
        while True:
            data = await websocket.receive_bytes()
            packet = create_rtp_packet(data, ssrc_int, seq, timestamp)
            sock.sendto(packet, (zlm_host, zlm_rtp_port))
            seq = (seq + 1) % 65536
            timestamp += len(data)

    except WebSocketDisconnect:
        logger.info("Bidirectional talk session ended by client")
    except Exception as e:
        logger.error(f"Bidirectional talk error: {e}")
    finally:
        # 8. 清理：发送 BYE 挂断
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
            except Exception:
                pass