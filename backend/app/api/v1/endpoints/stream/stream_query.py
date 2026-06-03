"""查询/状态查询相关端点。"""

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.core.config import settings
from app.core.media_nodes import get_all_media_from_nodes_async
from app.core.media_nodes_db import get_all_media_from_nodes as get_all_media_from_db_nodes, list_db_media_nodes
from app.models.asset import Asset
from app.models.stream_session import StreamSession
from app.models.user import User
from app.api import deps
from datetime import datetime, timezone
import asyncio
import re

_SAFE_NAME_RE = re.compile(r'^[A-Za-z0-9_-]+$')


router = APIRouter()


@router.get("/list")
async def list_streams(
    limit: int = Query(100, ge=1, le=500, description="每页最大条数"),  # 全量加载 → 添加分页限制
    offset: int = Query(0, ge=0, description="偏移量"),  # 全量加载 → 添加分页偏移
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    tenant_id = current_user.tenant_id or "default"
    session_stmt = select(StreamSession)
    if not current_user.is_superuser:
        allowed_asset_ids = set(
            (
                await db.execute(
                    select(Asset.id).where(Asset.tenant_id == tenant_id)
                )
            ).scalars().all()
        )
        if not allowed_asset_ids:
            return {"items": [], "total": 0, "limit": limit, "offset": offset}
        session_stmt = session_stmt.where(StreamSession.asset_id.in_(allowed_asset_ids))
    session_result = await db.execute(session_stmt)
    sessions = session_result.scalars().all()
    session_map = {(item.app, item.stream): item for item in sessions}
    try:
        db_nodes = await list_db_media_nodes(db)
        if db_nodes:
            zlm_items = await get_all_media_from_db_nodes(db_nodes)
        else:
            zlm_items = await get_all_media_from_nodes_async()
    except Exception:
        zlm_items = []
    payload = []
    now = datetime.now(timezone.utc)
    for item in zlm_items:
        app = str(item.get("app") or "")
        stream = str(item.get("stream") or "")
        if not app or not stream:
            continue
        related = session_map.get((app, stream))
        seconds = 0
        if related and related.start_time:
            started = related.start_time
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            seconds = max(0, int((now - started).total_seconds()))
        payload.append(
            {
                "app": app,
                "stream": stream,
                "schema": item.get("schema") or "rtsp",
                "origin_type": item.get("originType"),
                "origin_url": item.get("originUrl"),
                "reader_count": int(item.get("readerCount") or 0),
                "alive_second": seconds,
                "bytes_speed": int(item.get("bytesSpeed") or 0),
                "is_proxy": int(item.get("originType") or 0) in {5, 6},
                "asset_id": related.asset_id if related else None,
                "resource_id": related.resource_id if related else None
            }
        )
    if sessions and not payload:
        for item in sessions:
            seconds = 0
            if item.start_time:
                started = item.start_time
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)
                seconds = max(0, int((now - started).total_seconds()))
            payload.append(
                {
                    "app": item.app,
                    "stream": item.stream,
                    "schema": "gb28181",
                    "origin_type": None,
                    "origin_url": None,
                    "reader_count": 0,
                    "alive_second": seconds,
                    "bytes_speed": 0,
                    "is_proxy": False,
                    "asset_id": item.asset_id,
                    "resource_id": item.resource_id
                }
            )
    payload.sort(key=lambda x: (x["app"], x["stream"]))
    # 全量加载 → 添加分页截断
    total = len(payload)
    paged = payload[offset:offset + limit]
    return {"items": paged, "total": total, "limit": limit, "offset": offset}


@router.get("/{stream_id}/webrtc")
async def get_webrtc_url(
    stream_id: str,
    app_name: str = Query("live"),
    transcode: bool = Query(False, description="是否强制丢弃B帧并转码为H264 Baseline"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)  # WebRTC端点缺少认证保护
):
    """
    获取 WebRTC 播放地址 (基于 WHEP 标准化协议) 及其 STUN/TURN 穿透凭证。
    支持在请求时触发边缘丢弃 B 帧与 H265 智能转码。
    """
    stmt = select(StreamSession).where(StreamSession.stream == stream_id, StreamSession.app == app_name)
    if not current_user.is_superuser:
        stmt = stmt.where(StreamSession.tenant_id == (current_user.tenant_id or "default"))
    result = await db.execute(stmt)
    ss = result.scalars().first()
    if not ss:
        raise HTTPException(status_code=404, detail="Stream not ready")

    media_ip = ss.media_ip
    target_stream_id = stream_id

    if transcode:
        # 触发智能转码与 B 帧丢弃
        from app.services.ffmpeg_proxy_manager import ffmpeg_proxy_manager

        target_stream_id = f"{stream_id}_nobframes"
        if not ffmpeg_proxy_manager.is_running(target_stream_id):
            # S-03 防止FFmpeg参数注入 — 校验 app_name/stream_id 仅含安全字符
            if not _SAFE_NAME_RE.match(app_name) or not _SAFE_NAME_RE.match(stream_id):
                raise HTTPException(status_code=400, detail="Invalid app_name or stream_id: must contain only alphanumeric, hyphens, underscores")
            # 原始流地址 (ZLM 本地 RTSP)
            _media_host = getattr(settings, 'MEDIA_SERVER_HOST', '') or ''  # I3 回退值不再硬编码127.0.0.1
            src_url = f"rtsp://{_media_host}:{settings.STREAM_PUBLIC_RTSP_PORT or 554}/{app_name}/{stream_id}"
            # 目标流推回 ZLM
            dst_url = f"rtsp://{_media_host}:{settings.STREAM_PUBLIC_RTSP_PORT or 554}/{app_name}/{target_stream_id}"

            # 使用硬件加速 (尝试 qsv/nvenc，回退到 libx264) 并丢弃 B 帧
            cmd = f"ffmpeg -rtsp_transport tcp -i {src_url} -c:v libx264 -profile:v baseline -bf 0 -preset ultrafast -tune zerolatency -c:a copy -f rtsp -rtsp_transport tcp {dst_url}"
            ffmpeg_proxy_manager.start(target_stream_id, cmd)

            # 等待转码流上线
            await asyncio.sleep(2.0)

    # 使用 ZLM 标准 WHEP 接口
    whep_url = f"http://{media_ip}:{settings.STREAM_PUBLIC_HTTP_PORT or 80}/index/api/whep?app={app_name}&stream={target_stream_id}"

    # 注入 STUN/TURN 服务器配置，前端 WHEP 客户端 (如 WebRTC API) 会使用此配置打洞
    turn_servers = [
        {
            "urls": [f"stun:{getattr(settings, 'STUN_SERVER', 'stun.l.google.com:19302')}"],
        }
    ]

    # 移除TURN默认密码admin123，仅在配置了TURN服务器且设置了凭证时才返回
    _turn_username = getattr(settings, 'TURN_USERNAME', None)
    _turn_password = getattr(settings, 'TURN_PASSWORD', None)
    if getattr(settings, 'TURN_SERVER', None) and _turn_username and _turn_password:
        turn_servers.append({
            "urls": [f"turn:{settings.TURN_SERVER}"],
            "username": _turn_username,
            "credential": _turn_password
        })

    return {
        "code": 0,
        "whep_url": whep_url,
        "ice_servers": turn_servers
    }
