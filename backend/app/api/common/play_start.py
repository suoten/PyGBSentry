"""点播启动路由（共享层）。

由 ``app/main.py`` 挂载到 ``/api/play``。提供 ``POST /start`` 端点：接受通道/
设备标识与码流模式，触发 SIP INVITE 点播会话，返回 flv/ws/hls/rtsp 播放地址
及 ``ssrc``。响应结构与 ``app/api/v1/endpoints/stream/stream_play.py`` 保持一致
（包含 ``flv``/``ws``/``hls``/``rtsp`` URL 与 ``ssrc``）。

SIP/媒体相关模块（``app.sip.invite``、``app.services.media_manager``）惰性导入，
失败时返回 HTTPException 而非抛出未捕获异常。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.config import settings
from app.db.session import get_db
from app.models.asset import Asset
from app.models.resource import Resource
from app.models.user import User

router = APIRouter()


class PlayStartRequest(BaseModel):
    """点播启动请求体。"""

    channel_id: str
    device_id: Optional[str] = None
    # main=主码流, sub=子码流, auto=通道默认
    mode: str = "main"


@router.post("/start")
@router.post("/")
async def start_play(
    body: PlayStartRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """启动点播，返回播放地址。"""
    try:
        tenant_id = current_user.tenant_id or "default"
        stream_type = (body.mode or "main").strip().lower()
        if stream_type not in ("main", "sub", "auto"):
            stream_type = "main"

        # 1. 定位通道
        ch_stmt = select(Resource).where(
            Resource.node_type == "channel",
            or_(Resource.gb_id == body.channel_id, Resource.id == body.channel_id),
        )
        if not current_user.is_superuser:
            ch_stmt = ch_stmt.where(Resource.tenant_id == tenant_id)
        resource = (await db.execute(ch_stmt)).scalars().first()
        if not resource:
            raise HTTPException(status_code=404, detail="Channel not found")

        # 2. 定位设备
        asset = None
        if resource.asset_id:
            asset = (
                await db.execute(select(Asset).where(Asset.id == resource.asset_id))
            ).scalars().first()
        if asset is None and body.device_id:
            asset = (
                await db.execute(select(Asset).where(Asset.gb_id == body.device_id))
            ).scalars().first()
        if not asset:
            raise HTTPException(status_code=404, detail="Device not found")
        if not asset.ip_addr:
            raise HTTPException(status_code=500, detail="Device network information missing")

        # 3. 惰性导入 SIP invite 单例
        import app.sip.invite as sip_invite_module  # noqa: WPS433
        from app.sip.server import sip_server  # noqa: WPS433
        sip_invite = getattr(sip_invite_module, "sip_invite", None)
        if sip_invite is None:
            raise HTTPException(status_code=503, detail="SIP service not ready")

        target_ip = str(asset.ip_addr or "")
        target_port = int(asset.port or 5060)
        proto = str(asset.transport or "UDP")
        transport = sip_server.get_transport(target_ip, target_port, proto)
        if transport is None and proto == "TCP":
            proto = "UDP"
            transport = sip_server.get_transport(target_ip, target_port, proto)
        if transport is None:
            raise HTTPException(status_code=503, detail="Device signaling transport unavailable")

        result = await sip_invite.send_invite(
            asset,
            resource,
            ((target_ip, target_port), proto, transport),
            stream_type=stream_type,
        )
        if not result:
            raise HTTPException(status_code=502, detail="Stream invite request failed")

        app_name = str(result.get("app") or "live")
        stream_id = str(result.get("stream") or resource.gb_id or "")
        ssrc = str(result.get("ssrc") or "")
        node_id = result.get("node_id")
        call_id = result.get("call_id")

        # 4. 解析媒体节点 host/http_port
        host = settings.STREAM_PUBLIC_HOST
        http_port = settings.STREAM_PUBLIC_HTTP_PORT
        # FIX: [2026-07-16] 增加流就绪探测前的默认值
        _probe_secret = str(settings.MEDIA_SERVER_SECRET or "")
        try:
            if node_id:
                from app.core.media_nodes_db import get_db_media_node_by_id  # noqa: WPS433
                from app.core.media_nodes import get_node_by_id  # noqa: WPS433
                db_node = await get_db_media_node_by_id(db, node_id)
                node = None if db_node else get_node_by_id(node_id)
                if db_node:
                    host = str(db_node.public_host or db_node.host or host)
                    http_port = int(db_node.public_http_port or db_node.http_port or http_port)
                    _probe_secret = str(db_node.secret or _probe_secret)
                elif node:
                    host = str(node.get("public_host") or node.get("host") or host)
                    http_port = int(node.get("public_http_port") or node.get("http_port") or http_port)
                    _probe_secret = str(node.get("secret") or _probe_secret)
        except Exception as node_err:
            logger.debug("common.play_start media node lookup failed: {}", node_err)

        # FIX: [2026-07-16] 在返回播放 URL 之前，等待 ZLM 流注册就绪。
        # 原问题：send_invite 返回后立即构造 URL 返回前端，但 200 OK 到达时设备才开始推流，
        # ZLM 需要额外几秒才能注册流。前端拿到 URL 后播放器报"流不存在"或黑屏。
        # 复用 stream_play.py 的 _wait_zlm_stream_ready 逻辑，最长等待 5 秒。
        try:
            from app.api.v1.endpoints.stream._shared import _wait_zlm_stream_ready
            _max_attempts = settings.PLAY_START_STREAM_READY_MAX_ATTEMPTS
            _interval = settings.PLAY_START_STREAM_READY_INTERVAL
            _zlm_ok, _stream_ready, _media_item, _detail = await _wait_zlm_stream_ready(
                host,
                http_port,
                _probe_secret,
                app_name,
                stream_id,
                max_attempts=_max_attempts,
                interval_seconds=_interval,
                extra_apps=["rtp"],
                ssrc=ssrc,
            )
            if not _stream_ready:
                logger.warning(
                    f"[play_start] ZLM stream not ready after {_max_attempts * _interval:.1f}s "
                    f"(app={app_name}, stream={stream_id}) - returning URL anyway, frontend should retry"
                )
        except Exception as _probe_err:
            logger.warning(f"[play_start] ZLM stream ready probe failed: {_probe_err} - returning URL anyway")

        # 5. 构造播放地址（与 stream_play 响应结构保持一致）
        flv_suffix = "" if app_name == "rtp" else ".live"
        flv_url = f"http://{host}:{http_port}/{app_name}/{stream_id}{flv_suffix}.flv"
        ws_url = f"ws://{host}:{http_port}/{app_name}/{stream_id}{flv_suffix}.flv"
        hls_url = f"http://{host}:{http_port}/{app_name}/{stream_id}/hls.m3u8"
        rtsp_port = settings.ZLM_RTSP_PORT
        rtsp_url = f"rtsp://{host}:{rtsp_port}/{app_name}/{stream_id}"

        return {
            "code": 0,
            "msg": "ok",
            "data": {
                "flv": flv_url,
                "ws": ws_url,
                "hls": hls_url,
                "rtsp": rtsp_url,
                "ssrc": ssrc,
                "app": app_name,
                "stream": stream_id,
                "node_id": node_id,
                "call_id": call_id,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("common.play_start start_play failed: {}", e)
        raise HTTPException(status_code=500, detail=f"Start play failed: {e}")
