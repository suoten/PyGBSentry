"""流控制/质量调整相关端点（回放、下载、回放控制）。"""

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.session import get_db
from app.core.config import settings
from app.core.media_nodes import get_node_by_id
from app.core.media_nodes_db import get_db_media_node_by_id
from app.models.asset import Asset
from app.models.resource import Resource
from app.models.stream_session import StreamSession
from app.models.user import User
from app.api import deps
import app.sip.commander as sip_commander_module
import app.sip.invite as sip_invite_module
from app.sip.server import sip_server
import time
import shlex
import re

_SAFE_NAME_RE = re.compile(r'^[A-Za-z0-9_-]+$')

from ._shared import (
    _stream_audit,
    _stream_play_token,
    _append_token,
    _get_play_token_ttl,
    _get_max_concurrent_streams,
    _public_stream_scheme,
    _normalize_signal_proto,
    _build_signal_targets,
    _resolve_media_mode_candidates,
)
from ._response import (
    _resolve_codec,
    _map_play_stream_error,
    _play_http_exception,
)

router = APIRouter()


@router.post("/playback/{device_id}/{channel_id}")
async def playback_stream(
    device_id: str,
    channel_id: str,
    start_time: int,
    end_time: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    req_t0 = time.perf_counter()
    stmt = select(Asset).where(Asset.gb_id == device_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
    result = await db.execute(stmt)
    asset = result.scalars().first()

    stmt = select(Resource).where(Resource.gb_id == channel_id)
    if not current_user.is_superuser:
        stmt = stmt.join(Asset, Asset.id == Resource.asset_id).where(Asset.tenant_id == (current_user.tenant_id or "default"))
    result = await db.execute(stmt)
    resource = result.scalars().first()

    if not asset or not resource:
        await _stream_audit(
            db,
            current_user,
            action="playback_stream",
            result="failed",
            status_code=404,
            detail="asset_or_channel_not_found",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=404, detail="Device or channel not found")

    if not asset.ip_addr:
        await _stream_audit(
            db,
            current_user,
            action="playback_stream",
            result="failed",
            status_code=500,
            detail="device_ip_missing",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=500, detail="Device network information missing")

    max_streams = _get_max_concurrent_streams()
    if max_streams > 0:
        tenant_id = current_user.tenant_id or "default"
        count_stmt = select(func.count(StreamSession.id)).select_from(StreamSession).join(Asset, StreamSession.asset_id == Asset.id).where(Asset.tenant_id == tenant_id)
        cnt = (await db.execute(count_stmt)).scalar() or 0
        if cnt >= max_streams:
            await _stream_audit(
                db,
                current_user,
                action="playback_stream",
                result="failed",
                status_code=429,
                detail="max_concurrent_streams",
                extra_summary=f"limit={max_streams}; device_id={device_id}; channel_id={channel_id}",
            )
            raise HTTPException(status_code=429, detail=f"Concurrent stream limit reached ({max_streams}), please close some playback sessions and retry")  # i18n

    # VOD Edge Cache: Check if the requested playback is already cached as a record
    from datetime import datetime, timezone
    from app.models.record import Record
    requested_start_dt = datetime.fromtimestamp(start_time, tz=timezone.utc).replace(tzinfo=None)
    requested_end_dt = datetime.fromtimestamp(end_time, tz=timezone.utc).replace(tzinfo=None)

    cache_stmt = select(Record).where(
        Record.resource_id == resource.id,
        Record.start_time <= requested_start_dt,
        Record.end_time >= requested_end_dt,
        Record.url_ok,
        Record.file_path is not None
    )
    cache_result = await db.execute(cache_stmt)
    cached_record = cache_result.scalars().first()

    if cached_record and cached_record.file_path:
        # VOD Cache hit! Bypass SIP INVITE and return cached MP4
        return {
            "app": cached_record.record_app or "record",
            "stream": cached_record.stream_id or "",
            "codec": _resolve_codec(resource),
            "token": "cached",
            "flv": cached_record.file_path,
            "hls": cached_record.file_path,
            "webrtc": "",
            "raw": cached_record.file_path,
            "ws_flv": cached_record.file_path,
            "ws_raw": cached_record.file_path,
            "is_cached": True
        }

    signal_targets = await _build_signal_targets(db, asset)
    if not signal_targets:
        await _stream_audit(
            db,
            current_user,
            action="playback_stream",
            result="failed",
            status_code=503,
            detail="device_transport_unavailable",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise _play_http_exception(
            503,
            "device_transport_unavailable",
            "Device signaling transport unavailable",
            "Please verify the device is online, registered, and the SIP transport channel is available",  # W-14 hardcoded Chinese→English
            retryable=True,
        )

    if not sip_invite_module.sip_invite:
        await _stream_audit(
            db,
            current_user,
            action="playback_stream",
            result="failed",
            status_code=503,
            detail="sip_service_unavailable",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise _play_http_exception(
            503,
            "sip_service_unavailable",
            "SIP service not ready",
            "Please check if the platform SIP service has started",  # W-14 hardcoded Chinese→English
            retryable=True,
        )

    result = None
    last_exc = None
    used_target = None
    media_mode_candidates = await _resolve_media_mode_candidates(db, getattr(asset, "id", None), asset=asset)
    for target_ip, target_port, target_proto_raw in signal_targets:
        transport_proto = _normalize_signal_proto(target_proto_raw)
        transport = sip_server.get_transport(target_ip, target_port, transport_proto)
        if transport is None and transport_proto == "TCP":
            transport_proto = "UDP"
            transport = sip_server.get_transport(target_ip, target_port, transport_proto)
        if transport is None:
            continue
        for media_mode in media_mode_candidates:
            try:
                result = await sip_invite_module.sip_invite.send_playback_invite(
                    asset, resource, ((target_ip, target_port), transport_proto, transport),
                    start_time, end_time, media_mode_override=media_mode
                )
                used_target = (target_ip, target_port, transport_proto)
                break
            except HTTPException:
                raise
            except Exception as exc:
                last_exc = exc
                continue
        if result:
            break
    if not result:
        if last_exc:
            await _stream_audit(
                db,
                current_user,
                action="playback_stream",
                result="failed",
                status_code=503,
                detail="playback_invite_error",
                extra_summary=f"device_id={device_id}; channel_id={channel_id}; err={str(last_exc)[:160]}",
            )
            raise _map_play_stream_error(last_exc)
        await _stream_audit(
            db,
            current_user,
            action="playback_stream",
            result="failed",
            status_code=503,
            detail="playback_invite_unavailable",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise _play_http_exception(
            503,
            "device_transport_unavailable",
            "Device signaling transport unavailable",
            "Please verify the device is online, registered, and the SIP transport channel is available",  # W-14 hardcoded Chinese→English
            retryable=True,
        )
    stream_id = result.get("stream", "")  # 使用.get()防止KeyError
    app_name = result.get("app", "live")  # 使用.get()防止KeyError

    # R3-03 回放会话开始时初始化状态机为"playing"
    if result.get("call_id"):
        from app.sip.playback_control import playback_control as _pb_ctrl
        if _pb_ctrl:
            _pb_ctrl.set_playback_started(result["call_id"])

    # 无缝预加载 (Seamless Timeline Pre-fetching)
    if end_time - start_time > 3600:
        from app.services.playback_timeline import start_prefetch_task
        start_prefetch_task(
            asset_id=asset.id,
            resource_id=resource.id,
            start_time=start_time,
            end_time=end_time,
            used_target=used_target,
            stream_id=stream_id,
            tenant_id=current_user.tenant_id or "default"
        )

    node_id = result.get("node_id")
    node = get_node_by_id(node_id)
    media_host = None
    media_port = None
    if node:
        media_host, media_port = node["public_host"], node["public_http_port"]
    else:
        db_node = await get_db_media_node_by_id(db, node_id)
        if db_node:
            media_host, media_port = db_node.public_host, db_node.public_http_port
    if not media_host or not media_port:
        media_host = settings.STREAM_PUBLIC_HOST
        media_port = settings.STREAM_PUBLIC_HTTP_PORT
    token = _stream_play_token(app_name, stream_id, expire_seconds=_get_play_token_ttl())
    scheme = _public_stream_scheme()
    base_flv = f"{scheme}://{media_host}:{media_port}/{app_name}/{stream_id}.live.flv"
    base_hls = f"{scheme}://{media_host}:{media_port}/{app_name}/{stream_id}/hls.m3u8"
    base_webrtc = f"{scheme}://{media_host}:{media_port}/index/api/webrtc?app={app_name}&stream={stream_id}&type=play"
    await _stream_audit(
        db,
        current_user,
        action="playback_stream",
        result="success",
        status_code=200,
        detail="ok",
        extra_summary=f"device_id={device_id}; channel_id={channel_id}; app={app_name}; stream={str(stream_id)[:80]}; start={start_time}; end={end_time}",
    )
    total_ms = round((time.perf_counter() - req_t0) * 1000, 2)
    sla_metrics = {"mode": "sync_playback", "first_frame_ms": total_ms, "total_ms": total_ms}
    return {
        "app": app_name,
        "stream": stream_id,
        "codec": _resolve_codec(resource),
        "token": token,
        "flv": _append_token(base_flv, token),
        "hls": _append_token(base_hls, token),
        "webrtc": _append_token(base_webrtc, token),
        "seek_supported": True,
        "sla": sla_metrics,
    }

@router.post("/download/{device_id}/{channel_id}")
async def download_stream(
    device_id: str,
    channel_id: str,
    start_time: int,
    end_time: int,
    download_speed: int = Query(4, description="下载倍速(例如1, 2, 4)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    stmt = select(Asset).where(Asset.gb_id == device_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
    result = await db.execute(stmt)
    asset = result.scalars().first()

    stmt = select(Resource).where(Resource.gb_id == channel_id)
    if not current_user.is_superuser:
        stmt = stmt.join(Asset, Asset.id == Resource.asset_id).where(Asset.tenant_id == (current_user.tenant_id or "default"))
    result = await db.execute(stmt)
    resource = result.scalars().first()

    if not asset or not resource:
        await _stream_audit(
            db,
            current_user,
            action="download_stream",
            result="failed",
            status_code=404,
            detail="asset_or_channel_not_found",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=404, detail="Device or channel not found")

    if not asset.ip_addr:
        await _stream_audit(
            db,
            current_user,
            action="download_stream",
            result="failed",
            status_code=500,
            detail="device_ip_missing",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=500, detail="Device network information missing")

    max_streams = _get_max_concurrent_streams()
    if max_streams > 0:
        tenant_id = current_user.tenant_id or "default"
        count_stmt = select(func.count(StreamSession.id)).select_from(StreamSession).join(Asset, StreamSession.asset_id == Asset.id).where(Asset.tenant_id == tenant_id)
        cnt = (await db.execute(count_stmt)).scalar() or 0
        if cnt >= max_streams:
            await _stream_audit(
                db,
                current_user,
                action="download_stream",
                result="failed",
                status_code=429,
                detail="max_concurrent_streams",
                extra_summary=f"limit={max_streams}; device_id={device_id}; channel_id={channel_id}",
            )
            raise HTTPException(status_code=429, detail=f"Concurrent stream limit reached ({max_streams}), please close some playback sessions and retry")  # i18n

    signal_targets = await _build_signal_targets(db, asset)
    if not signal_targets:
        await _stream_audit(
            db,
            current_user,
            action="download_stream",
            result="failed",
            status_code=503,
            detail="device_transport_unavailable",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise _play_http_exception(503, "device_transport_unavailable", "Device signaling unavailable", "请确认设备在线")

    result = None
    last_exc = None
    media_mode_candidates = await _resolve_media_mode_candidates(db, getattr(asset, "id", None), asset=asset)
    for target_ip, target_port, target_proto_raw in signal_targets:
        transport_proto = _normalize_signal_proto(target_proto_raw)
        transport = sip_server.get_transport(target_ip, target_port, transport_proto)
        if transport is None and transport_proto == "TCP":
            transport_proto = "UDP"
            transport = sip_server.get_transport(target_ip, target_port, transport_proto)
        if transport is None:
            continue
        for media_mode in media_mode_candidates:
            try:
                result = await sip_invite_module.sip_invite.send_playback_invite(
                    asset, resource, ((target_ip, target_port), transport_proto, transport),
                    start_time, end_time, media_mode_override=media_mode, download_speed=download_speed
                )
                break
            except HTTPException:
                raise
            except Exception as exc:
                last_exc = exc
                continue
        if result:
            break
    if not result:
        if last_exc:
            await _stream_audit(
                db,
                current_user,
                action="download_stream",
                result="failed",
                status_code=503,
                detail="download_invite_error",
                extra_summary=f"device_id={device_id}; channel_id={channel_id}; err={str(last_exc)[:160]}",
            )
            raise _map_play_stream_error(last_exc)
        await _stream_audit(
            db,
            current_user,
            action="download_stream",
            result="failed",
            status_code=503,
            detail="download_invite_unavailable",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise _play_http_exception(503, "device_transport_unavailable", "Device signaling transport unavailable", "请确认设备在线")

    stream_id = result.get("stream", "")  # 使用.get()防止KeyError
    app_name = result.get("app", "live")  # 使用.get()防止KeyError

    # R3-03 回放会话开始时初始化状态机为"playing"
    if result.get("call_id"):
        from app.sip.playback_control import playback_control as _pb_ctrl
        if _pb_ctrl:
            _pb_ctrl.set_playback_started(result["call_id"])

    await _stream_audit(
        db,
        current_user,
        action="download_stream",
        result="success",
        status_code=200,
        detail="ok",
        extra_summary=f"device_id={device_id}; channel_id={channel_id}; app={app_name}; stream={str(stream_id)[:80]}; speed={download_speed}",
    )
    return {
        "app": app_name,
        "stream": stream_id,
        "msg": "Download command sent, stream is transmitting"  # i18n
    }


@router.post("/playback/{stream_id}/control")
async def control_playback_stream(
    stream_id: str,
    action: str = Query(..., description="PAUSE, PLAY, TEARDOWN"),
    speed: float = Query(1.0, description="播放倍速"),
    seek_time: int = Query(0, description="拖拽秒数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    _ALLOWED_PLAYBACK_ACTIONS = {"PAUSE", "PLAY", "TEARDOWN"}
    if action.upper() not in _ALLOWED_PLAYBACK_ACTIONS:
        raise HTTPException(status_code=400, detail=f"Invalid playback action: {action}")
    action = action.upper()
    """
    发送 INFO 指令控制设备端的回放流 (暂停、恢复、倍速、拖拽、拆除)
    """
    stmt = select(StreamSession, Asset).join(Asset, StreamSession.asset_id == Asset.id).where(
        StreamSession.stream == stream_id,
        StreamSession.app == "playback"
    )
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))

    result = await db.execute(stmt)
    row = result.first()
    if not row:
        await _stream_audit(
            db,
            current_user,
            action="playback_stream_control",
            result="failed",
            status_code=404,
            detail="session_not_found",
            extra_summary=f"stream_id={stream_id}; action={action}",
        )
        raise HTTPException(status_code=404, detail="Playback stream session not found or permission denied")  # i18n

    session_obj, asset = row

    if not sip_commander_module.sip_commander:
        await _stream_audit(
            db,
            current_user,
            action="playback_stream_control",
            result="failed",
            status_code=500,
            detail="sip_commander_unavailable",
            extra_summary=f"stream_id={stream_id}; action={action}",
        )
        raise HTTPException(status_code=500, detail="SIP Commander not ready")

    # Build transport info
    _transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport or "UDP")
    if _transport is None:
        await _stream_audit(
            db,
            current_user,
            action="control_playback_stream",
            result="failed",
            status_code=503,
            detail="device_transport_unavailable",
            extra_summary=f"stream_id={stream_id}; action={action}",
        )
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")
    transport_info = ((asset.ip_addr, asset.port), asset.transport or "UDP", _transport)

    session_dict = {
        "call_id": session_obj.call_id,
        "from_tag": session_obj.from_tag,
        "to_tag": session_obj.to_tag
    }

    # We need the resource gb_id
    stmt_res = select(Resource.gb_id).where(Resource.id == session_obj.resource_id)
    res_gb_id = (await db.execute(stmt_res)).scalar()

    await sip_commander_module.sip_commander.send_stream_control(
        device_id=asset.gb_id,
        channel_id=res_gb_id or asset.gb_id,
        transport_info=transport_info,
        action=action,
        stream_session=session_dict,
        speed=speed,
        seek_time=seek_time
    )

    await _stream_audit(
        db,
        current_user,
        action="playback_stream_control",
        result="success",
        status_code=200,
        detail="ok",
        extra_summary=f"stream_id={stream_id}; sip_action={action}; speed={speed}; seek_time={seek_time}",
    )
    return {"msg": f"Stream control {action} sent"}


# Playback control endpoints
class PlaybackControlRequest(BaseModel):
    app: str
    stream: str
    seek_time: int | None = None


class PlaybackSeekRequest(BaseModel):
    app: str
    stream: str
    seek_time: int  # Unix timestamp in seconds


class PlaybackSpeedRequest(BaseModel):
    app: str
    stream: str
    speed: float  # 0.25, 0.5, 1, 2, 4, 8


@router.post("/playback/pause")
async def playback_pause(
    payload: PlaybackControlRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """暂停录像回放"""
    from app.sip.playback_control import playback_control
    from app.sip.server import sip_server

    # Find the playback session
    stmt = select(StreamSession).where(
        StreamSession.stream == payload.stream,
        StreamSession.app == "playback"
    )
    if not current_user.is_superuser:
        tenant_id = current_user.tenant_id or "default"
        stmt = stmt.join(Asset, StreamSession.asset_id == Asset.id).where(Asset.tenant_id == tenant_id)
    result = await db.execute(stmt)
    session = result.scalars().first()

    if not session:
        await _stream_audit(
            db,
            current_user,
            action="playback_pause",
            result="failed",
            status_code=404,
            detail="session_not_found",
            extra_summary=f"app={payload.app}; stream={payload.stream[:80]}",
        )
        raise HTTPException(status_code=404, detail="Playback session not found")

    # Get asset and resource
    asset_result = await db.execute(select(Asset).where(Asset.id == session.asset_id))
    asset = asset_result.scalars().first()
    resource_result = await db.execute(select(Resource).where(Resource.id == session.resource_id))
    resource = resource_result.scalars().first()

    if not asset or not resource:
        await _stream_audit(
            db,
            current_user,
            action="playback_pause",
            result="failed",
            status_code=404,
            detail="asset_or_channel_not_found",
            extra_summary=f"app={payload.app}; stream={payload.stream[:80]}",
        )
        raise HTTPException(status_code=404, detail="Device or channel not found")

    if not asset.ip_addr:
        await _stream_audit(
            db,
            current_user,
            action="playback_pause",
            result="failed",
            status_code=500,
            detail="device_ip_missing",
            extra_summary=f"app={payload.app}; stream={payload.stream[:80]}",
        )
        raise HTTPException(status_code=500, detail="Device network information missing")

    # VOD Edge Cache: 检查 Seek 目标时间是否已存在于本地/云端 MP4 缓存中
    from datetime import timedelta
    from app.models.record import Record
    if getattr(session, "start_time", None) and payload.seek_time is not None:
        seek_dt = session.start_time + timedelta(seconds=payload.seek_time)

        cache_stmt = select(Record).where(
            Record.resource_id == resource.id,
            Record.start_time <= seek_dt,
            Record.end_time >= seek_dt,
            Record.url_ok,
            Record.file_path is not None
        )
        cache_result = await db.execute(cache_stmt)
        cached_record = cache_result.scalars().first()

        if cached_record and cached_record.file_path:
            if not cached_record.start_time:  # W-08-01 start_time为None时跳过缓存Seek，避免TypeError
                cached_record = None
            else:
                from app.services.ffmpeg_proxy_manager import ffmpeg_proxy_manager

                offset_sec = (seek_dt - cached_record.start_time).total_seconds()
                if offset_sec < 0:
                    offset_sec = 0
                try:
                    offset_sec = float(offset_sec)
                    if not (0 <= offset_sec <= 86400 * 7):
                        offset_sec = 0.0
                except (TypeError, ValueError):
                    offset_sec = 0.0

                from app.sip.invite import sip_invite
                transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
                if transport:
                    await sip_invite.send_bye(asset, session, resource.gb_id)

                # hardcoded 127.0.0.1 and 554 → use settings with explicit variable
                _media_host = str(settings.MEDIA_SERVER_HOST or "")  # I3 回退值不再硬编码127.0.0.1
                _rtsp_port = settings.STREAM_PUBLIC_RTSP_PORT or 554
                # S-02 防止FFmpeg参数注入 — 校验 app/stream 仅含安全字符
                if not _SAFE_NAME_RE.match(payload.app) or not _SAFE_NAME_RE.match(payload.stream):
                    raise HTTPException(status_code=400, detail="Invalid app or stream name: must contain only alphanumeric, hyphens, underscores")
                dst_url = f"rtsp://{_media_host}:{_rtsp_port}/{payload.app}/{payload.stream}"
                safe_path = shlex.quote(str(cached_record.file_path))
                cmd = f"ffmpeg -re -ss {offset_sec} -i {safe_path} -c copy -f rtsp -rtsp_transport tcp {dst_url}"
                ffmpeg_proxy_manager.start(payload.stream, cmd)

                await _stream_audit(
                    db,
                    current_user,
                    action="playback_seek",
                result="success",
                status_code=200,
                detail="cache_hit",
                extra_summary=f"app={payload.app}; stream={payload.stream}; offset={offset_sec}",
                )
                return {"status": "ok", "action": "seek", "stream": payload.stream, "seek_time": payload.seek_time, "cached": True}

    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        await _stream_audit(
            db,
            current_user,
            action="playback_pause",
            result="failed",
            status_code=503,
            detail="sip_transport_unavailable",
            extra_summary=f"app={payload.app}; stream={payload.stream[:80]}",
        )
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")

    # R3-04 检查send_pause返回值，状态机拒绝时返回错误
    result = await playback_control.send_pause(
        asset, resource.gb_id,
        ((asset.ip_addr, asset.port), asset.transport, transport),
        session.call_id,
        cseq=session.cseq + 1,
        from_tag=session.from_tag,
        to_tag=session.to_tag,
    )
    if not result:
        raise HTTPException(status_code=409, detail="Playback state transition not allowed")

    # Update session cseq
    session.cseq += 1
    await db.commit()

    await _stream_audit(
        db,
        current_user,
        action="playback_pause",
        result="success",
        status_code=200,
        detail="ok",
        extra_summary=f"app={payload.app}; stream={payload.stream[:80]}",
    )
    return {"status": "ok", "action": "pause", "stream": payload.stream}


@router.post("/playback/resume")
async def playback_resume(
    payload: PlaybackControlRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """恢复录像回放"""
    from app.sip.playback_control import playback_control
    from app.sip.server import sip_server

    stmt = select(StreamSession).where(
        StreamSession.stream == payload.stream,
        StreamSession.app == "playback"
    )
    if not current_user.is_superuser:
        tenant_id = current_user.tenant_id or "default"
        stmt = stmt.join(Asset, StreamSession.asset_id == Asset.id).where(Asset.tenant_id == tenant_id)
    result = await db.execute(stmt)
    session = result.scalars().first()

    if not session:
        await _stream_audit(
            db,
            current_user,
            action="playback_resume",
            result="failed",
            status_code=404,
            detail="session_not_found",
            extra_summary=f"app={payload.app}; stream={payload.stream[:80]}",
        )
        raise HTTPException(status_code=404, detail="Playback session not found")

    asset_result = await db.execute(select(Asset).where(Asset.id == session.asset_id))
    asset = asset_result.scalars().first()
    resource_result = await db.execute(select(Resource).where(Resource.id == session.resource_id))
    resource = resource_result.scalars().first()

    if not asset or not resource:
        await _stream_audit(
            db,
            current_user,
            action="playback_resume",
            result="failed",
            status_code=404,
            detail="asset_or_channel_not_found",
            extra_summary=f"app={payload.app}; stream={payload.stream[:80]}",
        )
        raise HTTPException(status_code=404, detail="Device or channel not found")

    if not asset.ip_addr:
        await _stream_audit(
            db,
            current_user,
            action="playback_resume",
            result="failed",
            status_code=500,
            detail="device_ip_missing",
            extra_summary=f"app={payload.app}; stream={payload.stream[:80]}",
        )
        raise HTTPException(status_code=500, detail="Device network information missing")

    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        await _stream_audit(
            db,
            current_user,
            action="playback_resume",
            result="failed",
            status_code=503,
            detail="sip_transport_unavailable",
            extra_summary=f"app={payload.app}; stream={payload.stream[:80]}",
        )
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")

    # R3-04 检查send_resume返回值，状态机拒绝时返回错误
    result = await playback_control.send_resume(
        asset, resource.gb_id,
        ((asset.ip_addr, asset.port), asset.transport, transport),
        session.call_id,
        cseq=session.cseq + 1,
        from_tag=session.from_tag,
        to_tag=session.to_tag,
    )
    if not result:
        raise HTTPException(status_code=409, detail="Playback state transition not allowed")

    session.cseq += 1
    await db.commit()

    await _stream_audit(
        db,
        current_user,
        action="playback_resume",
        result="success",
        status_code=200,
        detail="ok",
        extra_summary=f"app={payload.app}; stream={payload.stream[:80]}",
    )
    return {"status": "ok", "action": "resume", "stream": payload.stream}


@router.post("/playback/seek")
async def playback_seek(
    payload: PlaybackSeekRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """拖动录像回放位置"""
    from app.sip.playback_control import playback_control
    from app.sip.server import sip_server

    stmt = select(StreamSession).where(
        StreamSession.stream == payload.stream,
        StreamSession.app == "playback"
    )
    if not current_user.is_superuser:
        tenant_id = current_user.tenant_id or "default"
        stmt = stmt.join(Asset, StreamSession.asset_id == Asset.id).where(Asset.tenant_id == tenant_id)
    result = await db.execute(stmt)
    session = result.scalars().first()

    if not session:
        await _stream_audit(
            db,
            current_user,
            action="playback_seek",
            result="failed",
            status_code=404,
            detail="session_not_found",
            extra_summary=f"app={payload.app}; stream={payload.stream[:80]}",
        )
        raise HTTPException(status_code=404, detail="Playback session not found")

    asset_result = await db.execute(select(Asset).where(Asset.id == session.asset_id))
    asset = asset_result.scalars().first()
    resource_result = await db.execute(select(Resource).where(Resource.id == session.resource_id))
    resource = resource_result.scalars().first()

    if not asset or not resource:
        await _stream_audit(
            db,
            current_user,
            action="playback_seek",
            result="failed",
            status_code=404,
            detail="asset_or_channel_not_found",
            extra_summary=f"app={payload.app}; stream={payload.stream[:80]}",
        )
        raise HTTPException(status_code=404, detail="Device or channel not found")

    if not asset.ip_addr:
        await _stream_audit(
            db,
            current_user,
            action="playback_seek",
            result="failed",
            status_code=500,
            detail="device_ip_missing",
            extra_summary=f"app={payload.app}; stream={payload.stream[:80]}",
        )
        raise HTTPException(status_code=500, detail="Device network information missing")

    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        await _stream_audit(
            db,
            current_user,
            action="playback_seek",
            result="failed",
            status_code=503,
            detail="sip_transport_unavailable",
            extra_summary=f"app={payload.app}; stream={payload.stream[:80]}",
        )
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")

    # R4-02 检查send_seek返回值
    result = await playback_control.send_seek(
        asset, resource.gb_id,
        ((asset.ip_addr, asset.port), asset.transport, transport),
        session.call_id,
        seek_time=payload.seek_time,
        cseq=session.cseq + 1,
        from_tag=session.from_tag,
        to_tag=session.to_tag,
    )
    if not result:
        raise HTTPException(status_code=409, detail="Playback state transition not allowed")

    session.cseq += 1
    await db.commit()

    await _stream_audit(
        db,
        current_user,
        action="playback_seek",
        result="success",
        status_code=200,
        detail="ok",
        extra_summary=f"app={payload.app}; stream={payload.stream[:80]}; seek_time={payload.seek_time}",
    )
    return {"status": "ok", "action": "seek", "stream": payload.stream, "seek_time": payload.seek_time}


@router.post("/playback/speed")
async def playback_speed(
    payload: PlaybackSpeedRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """设置录像回放倍速 (0.25, 0.5, 1, 2, 4, 8)"""
    from app.sip.playback_control import playback_control
    from app.sip.server import sip_server

    # Validate speed
    valid_speeds = [0.25, 0.5, 1, 2, 4, 8]
    if payload.speed not in valid_speeds:
        await _stream_audit(
            db,
            current_user,
            action="playback_speed",
            result="failed",
            status_code=400,
            detail="invalid_speed",
            extra_summary=f"app={payload.app}; stream={payload.stream[:80]}; speed={payload.speed}",
        )
        raise HTTPException(status_code=400, detail=f"Invalid speed value, supported speeds: {valid_speeds}")  # i18n

    stmt = select(StreamSession).where(
        StreamSession.stream == payload.stream,
        StreamSession.app == "playback"
    )
    if not current_user.is_superuser:
        tenant_id = current_user.tenant_id or "default"
        stmt = stmt.join(Asset, StreamSession.asset_id == Asset.id).where(Asset.tenant_id == tenant_id)
    result = await db.execute(stmt)
    session = result.scalars().first()

    if not session:
        await _stream_audit(
            db,
            current_user,
            action="playback_speed",
            result="failed",
            status_code=404,
            detail="session_not_found",
            extra_summary=f"app={payload.app}; stream={payload.stream[:80]}",
        )
        raise HTTPException(status_code=404, detail="Playback session not found")

    asset_result = await db.execute(select(Asset).where(Asset.id == session.asset_id))
    asset = asset_result.scalars().first()
    resource_result = await db.execute(select(Resource).where(Resource.id == session.resource_id))
    resource = resource_result.scalars().first()

    if not asset or not resource:
        await _stream_audit(
            db,
            current_user,
            action="playback_speed",
            result="failed",
            status_code=404,
            detail="asset_or_channel_not_found",
            extra_summary=f"app={payload.app}; stream={payload.stream[:80]}",
        )
        raise HTTPException(status_code=404, detail="Device or channel not found")

    if not asset.ip_addr:
        await _stream_audit(
            db,
            current_user,
            action="playback_speed",
            result="failed",
            status_code=500,
            detail="device_ip_missing",
            extra_summary=f"app={payload.app}; stream={payload.stream[:80]}",
        )
        raise HTTPException(status_code=500, detail="Device network information missing")

    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        await _stream_audit(
            db,
            current_user,
            action="playback_speed",
            result="failed",
            status_code=503,
            detail="sip_transport_unavailable",
            extra_summary=f"app={payload.app}; stream={payload.stream[:80]}",
        )
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")

    # R4-02 检查send_speed返回值
    result = await playback_control.send_speed(
        asset, resource.gb_id,
        ((asset.ip_addr, asset.port), asset.transport, transport),
        session.call_id,
        speed=payload.speed,
        cseq=session.cseq + 1,
        from_tag=session.from_tag,
        to_tag=session.to_tag,
    )
    if not result:
        raise HTTPException(status_code=409, detail="Playback state transition not allowed")

    session.cseq += 1
    await db.commit()

    await _stream_audit(
        db,
        current_user,
        action="playback_speed",
        result="success",
        status_code=200,
        detail="ok",
        extra_summary=f"app={payload.app}; stream={payload.stream[:80]}; speed={payload.speed}",
    )
    return {"status": "ok", "action": "speed", "stream": payload.stream, "speed": payload.speed}
