"""分享/嵌入链接(ROADMAP Phase2:嵌入场景官方化)。

解决 wvp #2033/#1846 类 iframe 嵌入痛点:
    * POST /links   —— 登录用户为通道生成**长周期 HMAC 嵌入令牌**(仅绑定通道,
                       不含密钥;默认最长 7 天,可配置)与嵌入页地址 + iframe 代码;
    * POST /resolve —— 嵌入页用令牌换发短周期(300s)播放地址:按需触发 SIP 点播,
                       等流就绪后返回带一次性 playToken 的 flv/hls 等 URL。
    * GET  /embed/play(挂在 main.py 根路由)—— 极简无框播放页(可被第三方 iframe 嵌入,
                       安全头中间件对该路径豁免 X-Frame-Options)。

安全模型:嵌入令牌 scope=embed,与点播令牌隔离;resolve 换发的点播令牌仍是 300s
短周期,泄漏窗口有限;令牌吊销可通过更换 SECRET_KEY 或后续引入 Redis 黑名单。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.config import settings
from app.core.play_token import issue_embed_token, issue_play_token, verify_embed_token
from app.db.session import get_db
from app.models.asset import Asset
from app.models.resource import Resource
from app.models.user import User

router = APIRouter()


class EmbedLinkRequest(BaseModel):
    channel_id: str
    device_id: Optional[str] = None
    ttl_hours: int = 24


class EmbedResolveRequest(BaseModel):
    token: str


@router.post("/links")
async def create_embed_link(
    payload: EmbedLinkRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """为通道生成嵌入链接(登录用户;租户隔离)。返回嵌入页 URL 与 iframe 代码。"""
    channel_id = str(payload.channel_id or "").strip()
    if not channel_id:
        raise HTTPException(status_code=400, detail="channel_id required")
    tenant_id = current_user.tenant_id or "default"

    stmt = select(Resource).where(Resource.node_type == "channel", Resource.gb_id == channel_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Resource.tenant_id == tenant_id)
    resource = (await db.execute(stmt.limit(1))).scalars().first()
    if not resource:
        raise HTTPException(status_code=404, detail="Channel not found")

    max_hours = max(1, int(settings.STREAM_EMBED_MAX_TTL_HOURS or 168))
    ttl_hours = max(1, min(int(payload.ttl_hours or 24), max_hours))
    token, exp = issue_embed_token(tenant_id, str(resource.gb_id), ttl_hours, issued_by=current_user.username or "")

    base = str(settings.STREAM_EMBED_PUBLIC_BASE_URL or "").strip().rstrip("/")
    if not base:
        base = str(request.base_url).rstrip("/")
    embed_url = f"{base}/embed/play?token={token}"
    iframe_code = (
        f'<iframe src="{embed_url}" width="640" height="360" '
        f'frameborder="0" allowfullscreen></iframe>'
    )
    return {
        "channel_id": str(resource.gb_id),
        "ttl_hours": ttl_hours,
        "expires_at": datetime.fromtimestamp(exp, tz=timezone.utc).isoformat(),
        "embed_url": embed_url,
        "iframe_code": iframe_code,
    }


@router.post("/resolve")
async def resolve_embed_link(
    payload: EmbedResolveRequest,
    db: AsyncSession = Depends(get_db),
):
    """嵌入页用令牌换发播放地址(令牌即凭证,无登录态)。

    校验嵌入令牌 → 按需触发 SIP 点播(租户取自令牌载荷) → 等流就绪(尽力) →
    换发 300s 短周期点播令牌并构造播放 URL。
    """
    token = str(payload.token or "").strip()
    claims = verify_embed_token(token)
    if not claims:
        raise HTTPException(status_code=401, detail="Invalid or expired embed token")
    tenant_id = str(claims.get("tenant") or "default")
    channel_id = str(claims.get("channel") or "")

    resource = (
        (await db.execute(select(Resource).where(Resource.node_type == "channel", Resource.gb_id == channel_id).limit(1)))
        .scalars()
        .first()
    )
    if not resource:
        raise HTTPException(status_code=404, detail="Channel not found")
    asset = (
        (await db.execute(select(Asset).where(Asset.id == getattr(resource, "asset_id", None)).limit(1)))
        .scalars()
        .first()
    )
    if not asset or not getattr(asset, "ip_addr", None):
        raise HTTPException(status_code=503, detail="Device network information missing")

    import app.sip.invite as sip_invite_module
    from app.sip.server import sip_server

    sip_invite = getattr(sip_invite_module, "sip_invite", None)
    if sip_invite is None:
        raise HTTPException(status_code=503, detail="SIP service not ready")

    target_ip = str(asset.ip_addr or "")
    try:
        target_port = int(asset.port or 5060)
    except (TypeError, ValueError):
        target_port = 5060
    proto = str(asset.transport or "UDP")
    transport = sip_server.get_transport(target_ip, target_port, proto)
    if transport is None and proto == "TCP":
        proto = "UDP"
        transport = sip_server.get_transport(target_ip, target_port, proto)
    if transport is None:
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")

    result = await sip_invite.send_invite(asset, resource, ((target_ip, target_port), proto, transport), stream_type="main")
    if not result:
        raise HTTPException(status_code=502, detail="Stream invite request failed")

    app_name = str(result.get("app") or "live")
    stream_id = str(result.get("stream") or resource.gb_id or "")
    node_id = result.get("node_id")

    # 等流就绪(尽力,不阻塞返回)
    try:
        from app.api.v1.endpoints.stream._shared import _wait_zlm_stream_ready

        host_probe = settings.STREAM_PUBLIC_HOST or settings.MEDIA_SERVER_HOST
        port_probe = settings.STREAM_PUBLIC_HTTP_PORT or settings.MEDIA_SERVER_HTTP_PORT
        _probe_secret = str(settings.MEDIA_SERVER_SECRET or "")
        await _wait_zlm_stream_ready(
            host_probe,
            port_probe,
            _probe_secret,
            app_name,
            stream_id,
            max_attempts=8,
            interval_seconds=0.6,
            extra_apps=["rtp"],
            ssrc=str(result.get("ssrc") or ""),
        )
    except Exception as probe_err:
        logger.debug(f"[embed] stream ready probe failed (non-fatal): {probe_err}")

    # 解析对外媒体端口(优先节点 public_*)
    media_host = settings.STREAM_PUBLIC_HOST
    http_port = settings.STREAM_PUBLIC_HTTP_PORT
    https_port = int(settings.STREAM_PUBLIC_HTTPS_PORT or 0)
    rtmp_port = settings.STREAM_PUBLIC_RTMP_PORT
    rtsp_port = settings.ZLM_RTSP_PORT
    try:
        if node_id:
            from app.core.media_nodes_db import get_db_media_node_by_id

            db_node = await get_db_media_node_by_id(db, node_id)
            if db_node:
                media_host = str(db_node.public_host or db_node.host or media_host)
                http_port = int(db_node.public_http_port or db_node.http_port or http_port)
                https_port = int(db_node.https_port or https_port)
                rtmp_port = int(db_node.rtmp_port or rtmp_port)
                rtsp_port = int(db_node.rtsp_port or rtsp_port)
    except Exception as node_err:
        logger.debug(f"[embed] media node lookup failed: {node_err}")

    play_token = issue_play_token(app_name, stream_id, ttl=300)
    from app.api.v1.endpoints.stream._response import _build_play_urls

    urls = _build_play_urls(
        app_name,
        stream_id,
        media_host,
        http_port,
        https_port,
        rtmp_port,
        0,
        rtsp_port,
        0,
        play_token,
    )
    # 嵌入页只需要 web 可播的协议族
    return {
        "channel_id": channel_id,
        "app": app_name,
        "stream": stream_id,
        "expires_at": datetime.fromtimestamp(int(claims.get("exp", 0)), tz=timezone.utc).isoformat(),
        "urls": {
            "flv": urls.get("flv"),
            "wss_flv": urls.get("wss_flv"),
            "ws_flv": urls.get("ws_flv"),
            "hls": urls.get("hls"),
            "https_hls": urls.get("https_hls"),
        },
        "cdn": {
            "flv_js": str(settings.STREAM_EMBED_FLV_JS_URL or ""),
            "hls_js": str(settings.STREAM_EMBED_HLS_JS_URL or ""),
        },
    }
