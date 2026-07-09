"""通道通用操作路由（共享层）。

由 ``app/main.py`` 挂载到 ``/api/common/channel``。提供：

- ``GET /``：分页列出通道（``Resource`` 中 ``node_type='channel'`` 的行）
- ``GET /{channel_id}``：按国标 ID 或主键获取通道详情
- ``POST /{channel_id}/play``：为通道启动点播，返回流地址

风格与 ``app/api/v1/endpoints/stream/stream_play.py`` 保持一致：使用
``get_current_active_user`` 鉴权、``get_db`` 注入会话、loguru 记录日志。
SIP/媒体相关模块（``app.sip.invite``、``app.services.media_manager``）惰性导入，
失败时返回 503 而非抛出未捕获异常。
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.config import settings
from app.db.session import get_db
from app.models.asset import Asset
from app.models.resource import Resource
from app.models.user import User

router = APIRouter()


def _resource_to_dict(res: Resource) -> dict[str, Any]:
    """将 Resource ORM 对象序列化为 JSON 字典。"""
    return {
        "id": str(res.id or ""),
        "gb_id": str(res.gb_id or ""),
        "name": str(res.name or ""),
        "type": int(res.type or 1),
        "status": int(res.status or 0),
        "node_type": str(res.node_type or "channel"),
        "asset_id": str(res.asset_id or "") or None,
        "parent_gb_id": str(res.parent_gb_id or "") or None,
        "civil_code": str(res.civil_code or "") or None,
        "region_parent_gb_id": str(res.region_parent_gb_id or "") or None,
        "longitude": res.longitude,
        "latitude": res.latitude,
        "ip_address": res.ip_address,
        "port": res.port,
        "manufacturer": getattr(res, "manufacturer", None),
        "address": res.address,
    }


@router.get("")
@router.get("/")
async def list_channels(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = Query(None, description="按名称/国标ID模糊搜索"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """分页列出通道。"""
    try:
        tenant_id = current_user.tenant_id or "default"
        stmt = select(Resource).where(Resource.node_type == "channel")
        if not current_user.is_superuser:
            stmt = stmt.where(Resource.tenant_id == tenant_id)
        if keyword:
            like = f"%{keyword}%"
            stmt = stmt.where(
                or_(Resource.name.like(like), Resource.gb_id.like(like))
            )
        # 总数
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = int((await db.execute(count_stmt)).scalar() or 0)
        # 分页
        stmt = stmt.order_by(Resource.created_at.desc()).offset(
            (page - 1) * page_size
        ).limit(page_size)
        rows = (await db.execute(stmt)).scalars().all()
        return {
            "code": 0,
            "msg": "ok",
            "data": {
                "total": total,
                "page": page,
                "page_size": page_size,
                "items": [_resource_to_dict(r) for r in rows],
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("common.channel list_channels failed: {}", e)
        raise HTTPException(status_code=500, detail=f"List channels failed: {e}")


@router.get("/{channel_id}")
async def get_channel(
    channel_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """按国标 ID 或主键获取通道详情。"""
    try:
        tenant_id = current_user.tenant_id or "default"
        stmt = select(Resource).where(Resource.node_type == "channel")
        # channel_id 可能是 gb_id 或主键 id
        stmt = stmt.where(or_(Resource.gb_id == channel_id, Resource.id == channel_id))
        if not current_user.is_superuser:
            stmt = stmt.where(Resource.tenant_id == tenant_id)
        res = (await db.execute(stmt)).scalars().first()
        if not res:
            raise HTTPException(status_code=404, detail="Channel not found")
        return {"code": 0, "msg": "ok", "data": _resource_to_dict(res)}
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("common.channel get_channel failed: {}", e)
        raise HTTPException(status_code=500, detail=f"Get channel failed: {e}")


@router.post("/{channel_id}/play")
async def play_channel(
    channel_id: str,
    stream_type: str = Query("main", description="main=主码流, sub=子码流"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """为通道启动点播，返回流地址。

    委托给 ``app.sip.invite.sip_invite``（惰性导入）发起 INVITE，成功后根据
    返回的 app/stream/node 构造 flv/ws/hls/rtsp 地址。
    """
    try:
        tenant_id = current_user.tenant_id or "default"
        # 1. 加载通道与设备
        ch_stmt = select(Resource).where(
            Resource.node_type == "channel",
            or_(Resource.gb_id == channel_id, Resource.id == channel_id),
        )
        if not current_user.is_superuser:
            ch_stmt = ch_stmt.where(Resource.tenant_id == tenant_id)
        resource = (await db.execute(ch_stmt)).scalars().first()
        if not resource:
            raise HTTPException(status_code=404, detail="Channel not found")
        if not resource.asset_id:
            raise HTTPException(status_code=400, detail="Channel has no bound device")
        asset = (
            await db.execute(select(Asset).where(Asset.id == resource.asset_id))
        ).scalars().first()
        if not asset:
            raise HTTPException(status_code=404, detail="Device not found")
        if not asset.ip_addr:
            raise HTTPException(status_code=500, detail="Device network information missing")

        # 2. 惰性导入 SIP invite 单例
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

        # 3. 解析媒体节点 host/http_port
        host = settings.STREAM_PUBLIC_HOST
        http_port = settings.STREAM_PUBLIC_HTTP_PORT
        try:
            if node_id:
                from app.core.media_nodes_db import get_db_media_node_by_id  # noqa: WPS433
                from app.core.media_nodes import get_node_by_id  # noqa: WPS433
                db_node = await get_db_media_node_by_id(db, node_id)
                node = None if db_node else get_node_by_id(node_id)
                if db_node:
                    host = str(db_node.public_host or db_node.host or host)
                    http_port = int(db_node.public_http_port or db_node.http_port or http_port)
                elif node:
                    host = str(node.get("public_host") or node.get("host") or host)
                    http_port = int(node.get("public_http_port") or node.get("http_port") or http_port)
        except Exception as node_err:
            logger.debug("common.channel play_channel media node lookup failed: {}", node_err)

        # 4. 构造播放地址
        flv_suffix = "" if app_name == "rtp" else ".live"
        flv_url = f"http://{host}:{http_port}/{app_name}/{stream_id}{flv_suffix}.flv"
        ws_url = f"ws://{host}:{http_port}/{app_name}/{stream_id}{flv_suffix}.flv"
        hls_url = f"http://{host}:{http_port}/{app_name}/{stream_id}/hls.m3u8"
        rtsp_port = int(getattr(settings, "ZLM_RTSP_PORT", 554) or 554)
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
                "call_id": result.get("call_id"),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("common.channel play_channel failed: {}", e)
        raise HTTPException(status_code=500, detail=f"Play channel failed: {e}")
