"""系统指标 API 端点。

提供设备概览、流指标等系统级监控指标。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, case
from app.db.session import get_db
from app.core.config import settings
from app.models.asset import Asset
from app.models.resource import Resource
from app.models.alarm import Alarm
from app.models.stream_session import StreamSession
from app.models.record import Record
from app.models.user import User
from app.api import deps
from datetime import datetime, timedelta, timezone
from typing import Any

router = APIRouter()


def _parse_range(
    start_time: datetime | None,
    end_time: datetime | None,
    default_hours: int = 1,
    max_days: int = 7,
) -> tuple[datetime, datetime]:
    """校验并填充时间范围，防止越界查询。

    FIXED: [2026-07-13] 恢复自 2ad636a — ConvergeLoop 删除了此辅助函数和 /alarms-trend 端点。
    UPGRADE_ACTION_PLAN.md 仍将 GET /api/v1/metrics/alarms-trend 列为验收项。
    """
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
        # FIX [2026-07-22 P1]: StreamSession 模型没有 status 列（会话结束即删除行），
        # 原 `StreamSession.status == 1` 永远抛 AttributeError 被 except 吞掉，
        # 导致 active_streams 恒为 0。行存在即视为活跃会话，直接统计总数。
        stream_stmt = select(func.count(StreamSession.id))
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


@router.get("/alarms-trend")
async def alarms_trend(
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> list[dict[str, Any]]:
    """报警趋势：按分钟统计报警数量与确认数量。

    FIXED: [2026-07-13] 恢复自 2ad636a — ConvergeLoop 删除了此端点。
    UPGRADE_ACTION_PLAN.md 将其列为验收项。
    支持 SQLite (strftime) 和 PostgreSQL (date_trunc) 双实现。
    """
    start, end = _parse_range(start_time, end_time, default_hours=1, max_days=7)
    tenant_id = None if current_user.is_superuser else (current_user.tenant_id or "default")

    # 按分钟聚合（SQLite 不支持 date_trunc，使用 strftime 替代）
    db_type = (settings.DATABASE_TYPE or "postgresql").lower()
    if db_type == "sqlite":
        bucket = func.strftime("%Y-%m-%d %H:%M", Alarm.time)
    else:
        bucket = func.date_trunc("minute", Alarm.time)

    conditions = [
        Alarm.time >= start,
        Alarm.time <= end,
    ]
    if tenant_id:
        conditions.append(Alarm.tenant_id == tenant_id)

    stmt = (
        select(
            bucket.label("bucket"),
            func.count(Alarm.id).label("total"),
            func.sum(case((Alarm.status == 1, 1), else_=0)).label("acknowledged"),
        )
        .where(and_(*conditions))
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
