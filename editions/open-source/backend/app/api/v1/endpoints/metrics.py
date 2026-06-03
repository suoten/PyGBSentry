from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, case
from datetime import datetime, timedelta, timezone
from app.db.session import get_db
from app.core.config import settings
from app.models.asset import Asset
from app.models.resource import Resource
from app.models.alarm import Alarm
from app.models.user import User
from app.api import deps


router = APIRouter()


def _parse_range(
    start_time: datetime | None,
    end_time: datetime | None,
    default_hours: int = 1,
    max_days: int = 7,
) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    end = end_time or now
    start = start_time or (end - timedelta(hours=default_hours))
    if start > end:
        raise HTTPException(status_code=400, detail="start_time cannot be greater than end_time")
    if (end - start) > timedelta(days=max_days):
        raise HTTPException(status_code=400, detail=f"Time range too large, please limit to {max_days} days")
    return start, end


@router.get("/devices-overview")
async def devices_overview(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """设备/通道在线概览。按 tenant 聚合，不扫描明细。"""
    tenant_id = current_user.tenant_id or "default"

    # 设备总数 / 在线数
    base_assets = select(func.count()).select_from(Asset).where(Asset.tenant_id == tenant_id)
    total_devices = int((await db.execute(base_assets)).scalar() or 0)

    online_assets = base_assets.where(Asset.status == 1)
    online_devices = int((await db.execute(online_assets)).scalar() or 0)

    # 通道总数 / 在线数
    base_channels = select(func.count()).select_from(Resource).where(Resource.tenant_id == tenant_id)
    total_channels = int((await db.execute(base_channels)).scalar() or 0)
    online_channels = int(
        (await db.execute(base_channels.where(Resource.status == 1))).scalar() or 0
    )

    device_rate = round((online_devices / total_devices) * 100, 2) if total_devices > 0 else 0.0
    channel_rate = round((online_channels / total_channels) * 100, 2) if total_channels > 0 else 0.0

    return {
        "device_total": total_devices,
        "device_online": online_devices,
        "channel_total": total_channels,
        "channel_online": online_channels,
        "device_online_rate_pct": device_rate,
        "channel_online_rate_pct": channel_rate,
    }


@router.get("/alarms-trend")
async def alarms_trend(
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """报警趋势：按分钟统计报警数量与确认数量。"""
    start, end = _parse_range(start_time, end_time, default_hours=1, max_days=7)
    tenant_id = current_user.tenant_id or "default"

    # 按分钟聚合（SQLite 不支持 date_trunc，使用 strftime 替代）
    db_type = (getattr(settings, "DATABASE_TYPE", None) or "postgresql").lower()
    if db_type == "sqlite":
        bucket = func.strftime("%Y-%m-%d %H:%M", Alarm.time)
    else:
        bucket = func.date_trunc("minute", Alarm.time)
    stmt = (
        select(
            bucket.label("bucket"),
            func.count(Alarm.id).label("total"),
            func.sum(case((Alarm.status == 1, 1), else_=0)).label("acknowledged"),
        )
        .where(
            and_(
                Alarm.tenant_id == tenant_id,
                Alarm.time >= start,
                Alarm.time <= end,
            )
        )
        .group_by(bucket)
        .order_by(bucket)
    )
    result = await db.execute(stmt)
    rows = result.all()
    return [
        {
            "time": r.bucket,
            "total": int(r.total or 0),
            "acknowledged": int(r.acknowledged or 0),
        }
        for r in rows
    ]

