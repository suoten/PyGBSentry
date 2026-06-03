"""统一结构化检索 API（人脸/车牌/行为事件）。"""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, desc, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.db.session import get_db
from app.models.structured_event import StructuredEvent
from app.models.user import User
from app.api import deps

router = APIRouter()


class StructuredEventCreate(BaseModel):
    source_plugin: str = ""
    event_type: str = "face"  # face | plate | behavior
    device_id: Optional[str] = None
    channel_id: Optional[str] = None
    event_time: Optional[datetime] = None
    payload: Optional[str] = None


@router.post("/events")
async def create_structured_event(
    body: StructuredEventCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """接收插件或第三方同步写入的结构化事件（供 sync_urls 回调或插件内部调用）。"""
    event_type = (body.event_type or "face").strip().lower()
    if event_type not in ("face", "plate", "behavior"):
        event_type = "face"
    event_time = body.event_time or datetime.now(timezone.utc)
    row = StructuredEvent(
        tenant_id=current_user.tenant_id or "default",
        source_plugin=(body.source_plugin or "")[:64],
        event_type=event_type,
        device_id=(body.device_id or "")[:64] or None,
        channel_id=(body.channel_id or "")[:64] or None,
        event_time=event_time,
        payload=(body.payload or "")[:8000] or None,
    )
    db.add(row)
    await db.commit()
    return {"ok": True, "id": row.id}


@router.get("/search")
async def structured_search(
    event_type: Optional[str] = Query(None, description="face | plate | behavior"),
    device_id: Optional[str] = None,
    channel_id: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=10000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """统一结构化检索，支持按类型/设备/通道/时间筛选。"""
    limit = max(1, min(limit or 50, 200))
    skip = max(0, skip or 0)
    now = datetime.now(timezone.utc)
    end_time = end_time or now
    start_time = start_time or (end_time - timedelta(days=7))
    if start_time > end_time:
        start_time, end_time = end_time, start_time
    conditions = [
        StructuredEvent.event_time >= start_time,
        StructuredEvent.event_time <= end_time,
    ]
    if not current_user.is_superuser:
        conditions.append(StructuredEvent.tenant_id == (current_user.tenant_id or "default"))
    if event_type:
        conditions.append(StructuredEvent.event_type == event_type.strip().lower())
    if device_id:
        conditions.append(StructuredEvent.device_id == device_id)
    if channel_id:
        conditions.append(StructuredEvent.channel_id == channel_id)

    count_stmt = select(func.count()).select_from(StructuredEvent).where(and_(*conditions))
    total = (await db.execute(count_stmt)).scalar() or 0
    stmt = (
        select(StructuredEvent)
        .where(and_(*conditions))
        .order_by(desc(StructuredEvent.event_time))
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    items = [
        {
            "id": r.id,
            "source_plugin": r.source_plugin,
            "event_type": r.event_type,
            "device_id": r.device_id,
            "channel_id": r.channel_id,
            "event_time": r.event_time.isoformat() if r.event_time else None,
            "payload": r.payload,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
    return {"items": items, "total": total, "skip": skip, "limit": limit}
