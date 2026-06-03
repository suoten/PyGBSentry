"""统一解析当前应访问的 ZLM HTTP API 目标（与 ops / 流媒体插件共用）。"""

from __future__ import annotations
from loguru import logger

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.media_nodes import get_media_nodes, select_best_node
from app.core.media_nodes_db import get_active_media_node_id, get_db_media_node_by_id, select_best_db_node
from app.db.session import AsyncSessionLocal


async def resolve_zlm_api_target(db_session: AsyncSession | None = None, node_id: str | None = None):
    """
    统一 ZLM 目标选择：
    1) 指定 node_id → 直接查询该节点
    2) DB active/auto
    3) ENV MEDIA_NODES(auto)
    4) 全局 MEDIA_SERVER_*

    返回: host, http_port, secret, node_id, select_reason
    """
    zlm_host = settings.MEDIA_SERVER_HOST
    zlm_port = settings.MEDIA_SERVER_HTTP_PORT
    zlm_secret = settings.MEDIA_SERVER_SECRET
    zlm_node_id = None
    zlm_select_reason = "global"

    try:
        if db_session is None:
            async with AsyncSessionLocal() as db:
                # 优先使用指定的 node_id
                if node_id:
                    db_node = await get_db_media_node_by_id(db, node_id)
                    if db_node:
                        return (
                            db_node.host or zlm_host,
                            db_node.http_port or zlm_port,
                            db_node.secret or zlm_secret,
                            db_node.id,
                            "specified",
                        )
                active_id = await get_active_media_node_id(db)
                db_node = await get_db_media_node_by_id(db, active_id) if active_id else None
                if not db_node:
                    db_node = await select_best_db_node(db)
                if db_node:
                    return (
                        db_node.host or zlm_host,
                        db_node.http_port or zlm_port,
                        db_node.secret or zlm_secret,
                        db_node.id,
                        "active" if (active_id and db_node.id == active_id) else "auto",
                    )
        else:
            # 优先使用指定的 node_id
            if node_id:
                db_node = await get_db_media_node_by_id(db_session, node_id)
                if db_node:
                    return (
                        db_node.host or zlm_host,
                        db_node.http_port or zlm_port,
                        db_node.secret or zlm_secret,
                        db_node.id,
                        "specified",
                    )
            active_id = await get_active_media_node_id(db_session)
            db_node = await get_db_media_node_by_id(db_session, active_id) if active_id else None
            if not db_node:
                db_node = await select_best_db_node(db_session)
            if db_node:
                return (
                    db_node.host or zlm_host,
                    db_node.http_port or zlm_port,
                    db_node.secret or zlm_secret,
                    db_node.id,
                    "active" if (active_id and db_node.id == active_id) else "auto",
                )
    except Exception as e:
        logger.warning(f"Error: {e}")

    try:
        nodes = get_media_nodes()
        if nodes:
            node = await select_best_node()
            if node:
                zlm_host = node.get("host") or zlm_host
                zlm_port = int(node.get("http_port") or zlm_port)
                zlm_secret = node.get("secret") or zlm_secret
                zlm_node_id = node.get("id")
                zlm_select_reason = "env_auto"
    except Exception as e:
        logger.warning(f"Error: {e}")

    return zlm_host, zlm_port, zlm_secret, zlm_node_id, zlm_select_reason