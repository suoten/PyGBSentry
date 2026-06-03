"""代理/推流/广播/对讲相关端点。"""

from fastapi import Query, APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.core.config import settings
from app.models.asset import Asset
from app.models.resource import Resource
from app.models.stream_session import StreamSession
from app.models.user import User
from app.api import deps
import app.sip.invite as sip_invite_module
from app.sip.server import sip_server
from loguru import logger

from ._shared import (
    _stream_audit,
    _stream_play_token,
    _normalize_signal_proto,
    _build_signal_targets,
    _get_asset_resource,
)

router = APIRouter()


class BroadcastStartRequest(BaseModel):
    """语音广播开始请求"""
    device_id: str
    channel_id: str
    audio_file_url: str | None = Field(None, description="预先录制的音频文件URL (MP3/WAV)，如果提供则播报文件而不是麦克风")
    sdp_body: str | None = Field(None, description="前端 WebRTC SDP offer，如提供则使用真实 SDP 而非伪构造")


class BroadcastStopRequest(BaseModel):
    """语音广播停止请求"""
    device_id: str
    channel_id: str
    call_id: str


@router.get("/push-token")
async def get_push_token(
    stream_name: str,
    expire_seconds: int = Query(300, ge=60, le=86400),
    current_user: User = Depends(deps.get_current_active_user),
):
    """推流鉴权：获取带有时效的推流 token，用于 ZLM 等推流地址。前端/推流端将 token 作为参数携带。"""
    if not stream_name or len(stream_name) > 128:
        raise HTTPException(status_code=400, detail="stream_name invalid")
    token = _stream_play_token("live", stream_name, expire_seconds=expire_seconds)
    return {"token": token, "expire_seconds": expire_seconds, "stream_name": stream_name}


@router.post("/broadcast/start")
async def broadcast_start(
    payload: BroadcastStartRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_superuser),  # W29 运维端点权限校验不足，改为superuser
):
    """开始语音广播（向设备喊话）"""
    from app.sip.broadcast import broadcast
    import random

    # Get asset and resource
    stmt = select(Asset).where(Asset.gb_id == payload.device_id)
    if not current_user.is_superuser:
        tenant_id = current_user.tenant_id or "default"
        stmt = stmt.where(Asset.tenant_id == tenant_id)
    result = await db.execute(stmt)
    asset = result.scalars().first()

    if not asset:
        await _stream_audit(
            db,
            current_user,
            action="broadcast_start",
            result="failed",
            status_code=404,
            detail="device_not_found",
            extra_summary=f"device_id={payload.device_id}",
        )
        raise HTTPException(status_code=404, detail="Device not found")

    resource_stmt = select(Resource).where(Resource.gb_id == payload.channel_id, Resource.asset_id == asset.id)
    resource_result = await db.execute(resource_stmt)
    resource = resource_result.scalars().first()

    if not resource:
        await _stream_audit(
            db,
            current_user,
            action="broadcast_start",
            result="failed",
            status_code=404,
            detail="channel_not_found",
            extra_summary=f"device_id={payload.device_id}; channel_id={payload.channel_id}",
        )
        raise HTTPException(status_code=404, detail="Channel not found")

    if not asset.ip_addr:
        await _stream_audit(
            db,
            current_user,
            action="broadcast_start",
            result="failed",
            status_code=500,
            detail="device_ip_missing",
            extra_summary=f"device_id={payload.device_id}",
        )
        raise HTTPException(status_code=500, detail="Device network information missing")

    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        await _stream_audit(
            db,
            current_user,
            action="broadcast_start",
            result="failed",
            status_code=503,
            detail="sip_transport_unavailable",
            extra_summary=f"device_id={payload.device_id}; channel_id={payload.channel_id}",
        )
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")

    # Generate SSRC
    ssrc = str(random.randint(1000000000, 9999999999))

    # Get media server info from settings
    media_server_ip = getattr(settings, "MEDIA_SERVER_IP", settings.SIP_IP)
    media_server_port = getattr(settings, "MEDIA_SERVER_BROADCAST_PORT", 20000)

    # 获取媒体服务器节点
    from app.models.media_node import MediaNode
    media_node_result = await db.execute(select(MediaNode).where(MediaNode.is_online == 1))
    media_node = media_node_result.scalars().first()

    ffmpeg_key = ""
    if media_node:
        from app.services.zlm_stream_control import add_ffmpeg_source

        # 如果提供了音频文件 URL，则作为转码源，否则使用前端推流地址
        if payload.audio_file_url:
            # N-05 防止FFmpeg协议注入 — 仅允许http/https协议
            _audio_url = payload.audio_file_url.strip()
            if not (_audio_url.startswith("http://") or _audio_url.startswith("https://")):
                raise HTTPException(status_code=400, detail="audio_file_url must use http:// or https:// protocol")
            # -re 保证按照真实速率读取，-stream_loop -1 保证无限循环播放
            src_url = f"-re -stream_loop -1 -i {_audio_url}"
        else:
            # 假设前端 WebRTC 推流到 broadcast/channel_id (AAC)
            # hardcoded fallback IP → use settings explicitly
            _fallback_host = str(getattr(settings, "MEDIA_SERVER_HOST", "") or "")  # I3 回退值不再硬编码127.0.0.1
            src_url = f"http://{media_node.host or _fallback_host}:{media_node.http_port or 80}/broadcast/{payload.channel_id}/hls.m3u8"

        # hardcoded fallback IP and RTMP port → use settings explicitly
        _fallback_host = str(getattr(settings, "MEDIA_SERVER_HOST", "") or "")  # I3 回退值不再硬编码127.0.0.1
        _rtmp_port = media_node.rtmp_port or getattr(settings, "STREAM_PUBLIC_RTMP_PORT", 1935) or 1935
        dst_url = f"rtmp://{media_node.host or _fallback_host}:{_rtmp_port}/broadcast/{payload.channel_id}_pcma"

        # 调用 ZLM 的 addFFmpegSource API 进行 AAC/MP3 -> PCMA 转码
        ffmpeg_key = await add_ffmpeg_source(
            host=media_node.host,
            http_port=media_node.http_port or 80,
            secret=media_node.secret or getattr(settings, "MEDIA_SERVER_SECRET", ""),
            src_url=src_url,
            dst_url=dst_url,
            timeout_ms=10000,
            enable_hls=0,
            enable_mp4=0
        )
        if ffmpeg_key:
            logger.info(f"Added FFmpeg source for AAC->PCMA transcoding: key={ffmpeg_key}")

    # Send broadcast invite
    call_id = await broadcast.send_broadcast_invite(
        asset, resource,
        ((asset.ip_addr, asset.port), asset.transport, transport),
        ssrc, media_server_ip, media_server_port
    )

    await _stream_audit(
        db,
        current_user,
        action="broadcast_start",
        result="success",
        status_code=200,
        detail="ok",
        extra_summary=f"device_id={payload.device_id}; channel_id={payload.channel_id}; call_id={call_id[:32]}",
    )
    return {
        "status": "ok",
        "action": "broadcast_start",
        "call_id": call_id,
        "ssrc": ssrc,
        "media_server_ip": media_server_ip,
        "media_server_port": media_server_port
    }


@router.post("/broadcast/stop")
async def broadcast_stop(
    payload: BroadcastStopRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_superuser),  # N-03 broadcast_stop权限升级为superuser，与broadcast_start一致
):
    """停止语音广播"""
    from app.sip.broadcast import broadcast

    # Get asset and resource
    stmt = select(Asset).where(Asset.gb_id == payload.device_id)
    if not current_user.is_superuser:
        tenant_id = current_user.tenant_id or "default"
        stmt = stmt.where(Asset.tenant_id == tenant_id)
    result = await db.execute(stmt)
    asset = result.scalars().first()

    if not asset:
        await _stream_audit(
            db,
            current_user,
            action="broadcast_stop",
            result="failed",
            status_code=404,
            detail="device_not_found",
            extra_summary=f"device_id={payload.device_id}",
        )
        raise HTTPException(status_code=404, detail="Device not found")

    resource_stmt = select(Resource).where(Resource.gb_id == payload.channel_id, Resource.asset_id == asset.id)
    resource_result = await db.execute(resource_stmt)
    resource = resource_result.scalars().first()

    if not resource:
        await _stream_audit(
            db,
            current_user,
            action="broadcast_stop",
            result="failed",
            status_code=404,
            detail="channel_not_found",
            extra_summary=f"device_id={payload.device_id}; channel_id={payload.channel_id}",
        )
        raise HTTPException(status_code=404, detail="Channel not found")

    if not asset.ip_addr:
        await _stream_audit(
            db,
            current_user,
            action="broadcast_stop",
            result="failed",
            status_code=500,
            detail="device_ip_missing",
            extra_summary=f"device_id={payload.device_id}",
        )
        raise HTTPException(status_code=500, detail="Device network information missing")

    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        await _stream_audit(
            db,
            current_user,
            action="broadcast_stop",
            result="failed",
            status_code=503,
            detail="sip_transport_unavailable",
            extra_summary=f"device_id={payload.device_id}; channel_id={payload.channel_id}",
        )
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")


    stream_session = (
        await db.execute(select(StreamSession).where(StreamSession.call_id == payload.call_id))
    ).scalars().first()
    if stream_session:
        await broadcast.send_broadcast_bye(
            asset,
            stream_session,
            ((asset.ip_addr, asset.port), asset.transport, transport),
        )
        await db.delete(stream_session)
        await db.commit()
    else:
        await broadcast.send_broadcast_bye(
            asset,
            StreamSession(
                app="broadcast",
                stream=resource.gb_id,
                resource_id=resource.id,
                asset_id=asset.id,
                call_id=payload.call_id,
                from_tag="",
                to_tag="",
                via_branch="",
                cseq=1,
                ssrc="",
                protocol=str(asset.transport or "UDP"),
                media_server_id="",
            ),
            ((asset.ip_addr, asset.port), asset.transport, transport),
        )

    await _stream_audit(
        db,
        current_user,
        action="broadcast_stop",
        result="success",
        status_code=200,
        detail="ok",
        extra_summary=f"device_id={payload.device_id}; channel_id={payload.channel_id}; call_id={payload.call_id[:32]}",
    )
    return {
        "status": "ok",
        "action": "broadcast_stop",
        "call_id": payload.call_id
    }


@router.post("/talk/start")
async def talk_start(
    payload: BroadcastStartRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_superuser),  # W29 运维端点权限校验不足，改为superuser
):
    """
    发起双向对讲 (Talk)。使用 INVITE s=Talk 建立真正的双向音频流。
    通过 ZLM WHIP 端点接收前端音频上行，ZLM 再通过 RTP 转发给设备。
    返回 WHIP URL 供前端 WebRTC 推流使用。
    """
    try:
        asset, resource = await _get_asset_resource(
            db, payload.device_id, payload.channel_id, current_user
        )
        if not asset or not resource:
            raise HTTPException(status_code=404, detail="Device or channel not found")
        if not asset.ip_addr:
            raise HTTPException(status_code=500, detail="Device network information missing")

        signal_targets = await _build_signal_targets(db, asset)
        if not signal_targets:
            raise HTTPException(status_code=503, detail="Device signaling unavailable")

        target_ip, target_port, target_proto_raw = signal_targets[0]
        transport_proto = _normalize_signal_proto(target_proto_raw)
        transport = sip_server.get_transport(target_ip, target_port, transport_proto)
        if transport is None:
            raise HTTPException(status_code=503, detail="Device signaling transport unavailable")

        # 获取媒体服务器节点信息用于 ZLM WHIP 推流
        from app.models.media_node import MediaNode
        media_node_result = await db.execute(select(MediaNode).where(MediaNode.is_online == 1))
        media_node = media_node_result.scalars().first()

        zlm_host = settings.SIP_IP
        zlm_http_port = 80
        zlm_rtp_port = 0  # 对讲SDP需使用RTP端口
        zlm_stream_id = f"{payload.channel_id}_talk"

        if media_node:
            zlm_host = (
                getattr(media_node, 'stream_ip', None)
                or getattr(media_node, 'public_ip', None)
                or media_node.host
                or settings.SIP_IP
            )
            zlm_http_port = media_node.http_port or 80
            zlm_rtp_port = getattr(media_node, 'rtp_proxy_port', 0) or 0  # 获取RTP端口

        # 优先使用 SipTalk 双向对讲（a=sendrecv + ZLM WHIP 音频上行）
        from app.sip.talk import sip_talk
        if sip_talk:
            talk_result = await sip_talk.send_talk_invite(
                device_id=payload.device_id,
                channel_id=payload.channel_id,
                gb_domain=settings.SIP_DOMAIN,
                sip_id=settings.SIP_ID,
                sip_domain=settings.SIP_DOMAIN,
                device_host=target_ip,
                device_port=target_port,
                zlm_host=zlm_host,
                zlm_http_port=zlm_http_port,
                zlm_stream_id=zlm_stream_id,
                transport=transport_proto,
                zlm_rtp_port=zlm_rtp_port,  # 传入RTP端口
            )

            call_id = str(talk_result.get("call_id") or "")
            await _stream_audit(
                db,
                current_user,
                action="talk_start",
                result="success",
                status_code=200,
                detail="ok",
                extra_summary=(
                    f"device_id={payload.device_id}; channel_id={payload.channel_id}; "
                    f"call_id={call_id[:32]}; zlm_stream_id={zlm_stream_id}"
                ),
            )
            return {
                "status": "ok",
                "action": "talk_start",
                "call_id": talk_result["call_id"],
                "ssrc": talk_result["ssrc"],
                "whip_url": talk_result["whip_url"],
                "zlm_stream_id": talk_result["zlm_stream_id"],
            }

        # 回退：使用原有 invite 模块的对讲流程
        # SDP 构造：优先使用前端传入的真实 SDP offer，否则构造默认 Talk SDP
        if payload.sdp_body:
            sdp_body = payload.sdp_body
        else:
            # m=audio 端口应使用 RTP 端口而非 SIP 信令端口
            _fallback_rtp_port = zlm_rtp_port or getattr(settings, "MEDIA_SERVER_RTP_PROXY_PORT", 10000) or 10000
            sdp_body = (
                f"v=0\r\n"
                f"o={asset.gb_id} 0 0 IN IP4 {settings.SIP_IP}\r\n"
                f"s=Talk\r\n"
                f"c=IN IP4 {settings.SIP_IP}\r\n"
                f"t=0 0\r\n"
                f"m=audio {_fallback_rtp_port} RTP/AVP 8 0\r\n"
                f"a=sendrecv\r\n"
                f"a=rtpmap:8 PCMA/8000\r\n"
                f"a=rtpmap:0 PCMU/8000\r\n"
            )

        result = await sip_invite_module.sip_invite.send_talk_invite(
            asset,
            resource,
            ((target_ip, target_port), transport_proto, transport),
            sdp_body,
        )

        call_id = str(result.get("call_id") or "")
        stream_id = str(result.get("stream") or "")
        await _stream_audit(
            db,
            current_user,
            action="talk_start",
            result="success",
            status_code=200,
            detail="ok",
            extra_summary=(
                f"device_id={payload.device_id}; channel_id={payload.channel_id}; "
                f"call_id={call_id[:32]}; stream={stream_id[:80]}"
            ),
        )
        return {
            "status": "ok",
            "action": "talk_start",
            "app": result["app"],
            "stream": result["stream"],
            "call_id": result["call_id"],
            "sdp_response": result["sdp_response"],
        }
    except HTTPException as he:
        await _stream_audit(
            db,
            current_user,
            action="talk_start",
            result="failed",
            status_code=int(getattr(he, "status_code", 500) or 500),
            detail=str(getattr(he, "detail", "") or "")[:200] or "http_error",
            extra_summary=(
                f"device_id={payload.device_id}; channel_id={payload.channel_id}; "
                f"status_code={int(getattr(he, 'status_code', 500) or 500)}"
            ),
        )
        raise
    except Exception as e:
        await _stream_audit(
            db,
            current_user,
            action="talk_start",
            result="failed",
            status_code=500,
            detail="talk_invite_error",
            extra_summary=(
                f"device_id={payload.device_id}; channel_id={payload.channel_id}; "
                f"err={str(e)[:160]}"
            ),
        )
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/talk/stop")
async def talk_stop(
    payload: BroadcastStopRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_superuser),  # W29 运维端点权限校验不足，改为superuser
):
    """
    对讲停止（当前实现与广播通道一致，作为语义化别名接口保留）。
    """
    try:
        result = await broadcast_stop(
            payload=payload, db=db, current_user=current_user
        )
        if isinstance(result, dict):
            result["action"] = "talk_stop"

        await _stream_audit(
            db,
            current_user,
            action="talk_stop",
            result="success",
            status_code=200,
            detail="ok",
            extra_summary=(
                f"device_id={payload.device_id}; channel_id={payload.channel_id}; "
                f"call_id={str(payload.call_id or '')[:32]}"
            ),
        )
        return result
    except HTTPException as he:
        await _stream_audit(
            db,
            current_user,
            action="talk_stop",
            result="failed",
            status_code=int(getattr(he, "status_code", 500) or 500),
            detail=str(getattr(he, "detail", "") or "")[:200] or "http_error",
            extra_summary=(
                f"device_id={payload.device_id}; channel_id={payload.channel_id}; "
                f"call_id={str(payload.call_id or '')[:32]}"
            ),
        )
        raise
