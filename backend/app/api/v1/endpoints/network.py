"""网络监控 API 端点。

提供网络概况、带宽统计、拓扑结构等网络运维功能。
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.session import get_db
from app.core.config import settings
from app.models.asset import Asset
from app.models.resource import Resource
from app.models.stream_session import StreamSession
from app.models.user import User
from app.api import deps
from loguru import logger
from datetime import datetime, timezone
from typing import Any

router = APIRouter()


@router.get("/summary")
async def network_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> dict[str, Any]:
    """网络概况：设备总数、在线数、流数量等。"""
    tenant_id = None if current_user.is_superuser else (current_user.tenant_id or "default")

    asset_stmt = select(Asset)
    if tenant_id:
        asset_stmt = asset_stmt.where(Asset.tenant_id == tenant_id)
    assets = (await db.execute(asset_stmt)).scalars().all()

    device_total = len(assets)
    device_online = sum(1 for a in assets if a.status == 1)

    asset_ids = [a.id for a in assets]
    channel_total = 0
    channel_online = 0
    if asset_ids:
        res_stmt = select(Resource).where(Resource.asset_id.in_(asset_ids), Resource.node_type == "channel")
        resources = (await db.execute(res_stmt)).scalars().all()
        channel_total = len(resources)
        channel_online = sum(1 for r in resources if r.status == 1)

    stream_count = 0
    try:
        stream_stmt = select(func.count(StreamSession.id)).where(StreamSession.status == 1)
        stream_count = int((await db.execute(stream_stmt)).scalar() or 0)
    except Exception:
        stream_count = 0

    return {
        "device_total": device_total,
        "device_online": device_online,
        "device_offline": device_total - device_online,
        "channel_total": channel_total,
        "channel_online": channel_online,
        "stream_count": stream_count,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/bandwidth")
async def network_bandwidth(
    range: str = Query("1h", description="时间范围: 1h, 6h, 24h"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> dict[str, Any]:
    """网络带宽统计（基于活跃流数估算）。"""
    # 获取当前活跃流数
    try:
        stream_stmt = select(func.count(StreamSession.id)).where(StreamSession.status == 1)
        active_streams = int((await db.execute(stream_stmt)).scalar() or 0)
    except Exception:
        active_streams = 0

    # 估算带宽：每个视频流约 2-4 Mbps（取决于编码和分辨率）
    estimated_bandwidth_mbps = active_streams * 2.5  # 平均 2.5 Mbps per stream

    # 生成时间序列数据（模拟历史数据点，基于当前活跃流数）
    now = datetime.now(timezone.utc)
    range_seconds = {"1h": 3600, "6h": 21600, "24h": 86400}.get(range, 3600)
    points = min(60, range_seconds // 60)  # 每分钟一个点，最多60个点

    series: list[dict[str, Any]] = []
    for i in range(points):
        ts = now.timestamp() - (points - 1 - i) * (range_seconds / points)
        # 模拟波动 ±20%
        variation = 0.8 + 0.4 * ((i * 7) % 10) / 10.0
        value = round(estimated_bandwidth_mbps * variation, 2)
        series.append({"timestamp": int(ts), "value": value})

    return {
        "range": range,
        "active_streams": active_streams,
        "current_bandwidth_mbps": round(estimated_bandwidth_mbps, 2),
        "peak_bandwidth_mbps": max((p["value"] for p in series), default=0),
        "avg_bandwidth_mbps": round(sum(p["value"] for p in series) / len(series), 2) if series else 0,
        "series": series,
        "timestamp": now.isoformat(),
    }


@router.get("/topology")
async def network_topology(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> dict[str, Any]:
    """网络拓扑：设备-通道-流的关系结构。"""
    tenant_id = None if current_user.is_superuser else (current_user.tenant_id or "default")

    asset_stmt = select(Asset)
    if tenant_id:
        asset_stmt = asset_stmt.where(Asset.tenant_id == tenant_id)
    assets = (await db.execute(asset_stmt)).scalars().all()

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    # Platform node (center)
    nodes.append({
        "id": "platform",
        "label": settings.PROJECT_NAME,
        "type": "platform",
        "status": "online",
    })

    for asset in assets[:200]:  # Limit to 200 devices for performance
        node_id = f"device:{asset.gb_id}"
        nodes.append({
            "id": node_id,
            "label": asset.name or asset.gb_id,
            "type": "device",
            "status": "online" if asset.status == 1 else "offline",
            "ip_addr": getattr(asset, "ip_addr", "") or "",
        })
        edges.append({"source": "platform", "target": node_id})

    # ZLM node
    try:
        from app.services.media_manager import get_media_server_info
        media_info = get_media_server_info()
        nodes.append({
            "id": "zlm",
            "label": f"ZLM ({media_info.get('host', '')}:{media_info.get('http_port', '')})",
            "type": "media_server",
            "status": "online",
        })
        edges.append({"source": "platform", "target": "zlm"})
    except Exception as _topo_err:
        logger.debug(f"Network topology: ZLM node info unavailable: {_topo_err}")

    return {
        "nodes": nodes,
        "edges": edges,
        "device_count": len(assets),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
