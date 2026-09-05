from datetime import datetime

from fastapi import Query, APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.db.session import get_db
from app.models.sip_trace_event import SipTraceEvent
from app.models.user import User

router = APIRouter()


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    s = value.strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


@router.get("")
async def list_trace_events(
    platform_id: str | None = None,
    device_id: str | None = None,
    channel_id: str | None = None,
    trace_id: str | None = None,
    event: str | None = None,
    start_at: str | None = None,
    end_at: str | None = None,
    limit: int = Query(200, ge=1, le=10000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    tenant_id = current_user.tenant_id or "default"
    limit = max(1, min(int(limit or 200), 500))
    stmt = select(SipTraceEvent).where(SipTraceEvent.tenant_id == tenant_id)
    if platform_id:
        stmt = stmt.where(SipTraceEvent.platform_id == platform_id)
    if device_id:
        stmt = stmt.where(SipTraceEvent.device_id == device_id)
    if channel_id:
        stmt = stmt.where(SipTraceEvent.channel_id == channel_id)
    if trace_id:
        stmt = stmt.where(SipTraceEvent.trace_id == trace_id)
    if event:
        stmt = stmt.where(SipTraceEvent.event == event)
    start_dt = _parse_dt(start_at)
    end_dt = _parse_dt(end_at)
    if start_dt:
        stmt = stmt.where(SipTraceEvent.created_at >= start_dt)
    if end_dt:
        stmt = stmt.where(SipTraceEvent.created_at <= end_dt)
    stmt = stmt.order_by(SipTraceEvent.created_at.desc()).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": r.id,
            "trace_id": r.trace_id,
            "event": r.event,
            "platform_id": r.platform_id,
            "device_id": r.device_id,
            "channel_id": r.channel_id,
            "payload": r.payload,
            "created_at": (r.created_at.isoformat() if r.created_at else None),
        }
        for r in rows
    ]


@router.get("/raw")
async def list_raw_sip_traces(
    limit: int = Query(100, ge=1, le=10000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    提供实时的 SIP 信令收发记录抓包。
    优先从内存队列获取最新数据，回退到数据库查询。
    此接口仅供管理员或拥有特定权限的用户在前端"SIP抓包"工具中使用。
    """
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    from app.core.plugin_manager import plugin_manager
    traces = getattr(plugin_manager, "recent_sip_traces", [])

    if traces:
        return {
            "count": len(traces),
            "traces": traces[-limit:]
        }

    tenant_id = current_user.tenant_id or "default"
    limit = max(1, min(int(limit or 100), 500))
    stmt = (
        select(SipTraceEvent)
        .where(SipTraceEvent.tenant_id == tenant_id)
        .order_by(SipTraceEvent.created_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return {
        "count": len(rows),
        "traces": [
            {
                "id": r.id,
                "trace_id": r.trace_id,
                "event": r.event,
                "platform_id": r.platform_id,
                "device_id": r.device_id,
                "channel_id": r.channel_id,
                "payload": r.payload,
                "created_at": (r.created_at.isoformat() if r.created_at else None),
            }
            for r in rows
        ],
    }

@router.get("/platforms/{platform_id}")
async def list_platform_trace_events(
    platform_id: str,
    limit: int = Query(200, ge=1, le=10000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return await list_trace_events(platform_id=platform_id, limit=limit, db=db, current_user=current_user)

