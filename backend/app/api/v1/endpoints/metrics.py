"""系统指标 API 端点。

提供设备概览、流指标等系统级监控指标。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.session import get_db
from app.models.asset import Asset
from app.models.resource import Resource
from app.models.stream_session import StreamSession
from app.models.record import Record
from app.models.user import User
from app.api import deps
from datetime import datetime, timezone
from typing import Any

router = APIRouter()


@router.get("/devices-overview")
async def devices_overview(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> dict[str, Any]:
    """设备概览指标：总数、在线数、离线数、通道数、活跃流数。"""
    tenant_id = None if current_user.is_superuser else (current_user.tenant_id or "default")

    asset_stmt = select(Asset)
    if tenant_id:
        asset_stmt = asset_stmt.where(Asset.tenant_id == tenant_id)
    assets = (await db.execute(asset_stmt)).scalars().all()

    device_total = len(assets)
    device_online = sum(1 for a in assets if a.status == 1)
    device_offline = device_total - device_online

    asset_ids = [a.id for a in assets]
    channel_total = 0
    channel_online = 0
    if asset_ids:
        ch_stmt = select(func.count(Resource.id)).where(
            Resource.asset_id.in_(asset_ids),
            Resource.node_type == "channel",
        )
        channel_total = int((await db.execute(ch_stmt)).scalar() or 0)

        ch_online_stmt = select(func.count(Resource.id)).where(
            Resource.asset_id.in_(asset_ids),
            Resource.node_type == "channel",
            Resource.status == 1,
        )
        channel_online = int((await db.execute(ch_online_stmt)).scalar() or 0)

    # Active streams
    active_streams = 0
    try:
        stream_stmt = select(func.count(StreamSession.id)).where(StreamSession.status == 1)
        active_streams = int((await db.execute(stream_stmt)).scalar() or 0)
    except Exception:
        active_streams = 0

    # Record count
    record_count = 0
    try:
        rec_stmt = select(func.count(Record.id))
        record_count = int((await db.execute(rec_stmt)).scalar() or 0)
    except Exception:
        record_count = 0

    online_rate = round(100.0 * device_online / device_total, 1) if device_total > 0 else 0

    return {
        "device_total": device_total,
        "device_online": device_online,
        "device_offline": device_offline,
        "channel_total": channel_total,
        "channel_online": channel_online,
        "active_streams": active_streams,
        "record_count": record_count,
        "online_rate_pct": online_rate,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/")
async def metrics_root(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> dict[str, Any]:
    """系统指标根端点（与 devices-overview 相同）。"""
    return await devices_overview(db=db, current_user=current_user)
