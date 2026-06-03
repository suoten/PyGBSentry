from datetime import datetime, timezone
from typing import Optional, Literal
from fastapi import Query, APIRouter, Depends, HTTPException
from pydantic import BaseModel, validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.db.session import get_db
from app.models.work_order import WorkOrder
from app.models.user import User
from app.api import deps
from app.services.auth_audit import safe_auth_audit

router = APIRouter()

class WorkOrderCreate(BaseModel):
    alarm_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    category: Literal["tech_support", "billing", "other"] = "other"
    priority: Literal["low", "medium", "high"] = "medium"
    assignee_user_id: Optional[str] = None

    @validator("title")
    def validate_title(cls, value: str):
        v = (value or "").strip()
        if len(v) < 2:
            raise ValueError("Title must be at least 2 characters")
        if len(v) > 255:
            raise ValueError("Title cannot exceed 255 characters")
        return v

    @validator("description")
    def validate_description(cls, value: Optional[str]):
        if value is None:
            return value
        v = value.strip()
        if v and len(v) < 4:
            raise ValueError("Description must be at least 4 characters")
        return v

class WorkOrderUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[Literal["tech_support", "billing", "other"]] = None
    priority: Optional[Literal["low", "medium", "high"]] = None
    status: Optional[Literal["open", "in_progress", "resolved", "closed"]] = None
    assignee_user_id: Optional[str] = None

    @validator("title")
    def validate_title(cls, value: Optional[str]):
        if value is None:
            return value
        v = value.strip()
        if len(v) < 2:
            raise ValueError("Title must be at least 2 characters")
        if len(v) > 255:
            raise ValueError("Title cannot exceed 255 characters")
        return v

    @validator("description")
    def validate_description(cls, value: Optional[str]):
        if value is None:
            return value
        v = value.strip()
        if v and len(v) < 4:
            raise ValueError("Description must be at least 4 characters")
        return v

def _scope_tenant_id(user: User) -> str:
    return user.tenant_id or "default"

def _can_edit_content(status: str) -> bool:
    return status in {"open", "in_progress", "resolved"}

def _can_delete(status: str) -> bool:
    return status == "closed"

def _status_transition_allowed(current: str, target: str) -> bool:
    if current == target:
        return True
    allowed = {
        "open": {"in_progress", "resolved", "closed"},
        "in_progress": {"open", "resolved", "closed"},
        "resolved": {"in_progress", "closed"},
        "closed": set(),
    }
    return target in allowed.get(current, set())

@router.get("")
async def list_work_orders(
    status: Optional[str] = None,
    limit: int = Query(100, ge=1, le=10000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    stmt = select(WorkOrder).order_by(desc(WorkOrder.created_at)).limit(limit)
    if not current_user.is_superuser:
        stmt = stmt.where(WorkOrder.tenant_id == _scope_tenant_id(current_user))
    if status:
        stmt = stmt.where(WorkOrder.status == status)
    result = await db.execute(stmt)
    return result.scalars().all()

@router.post("")
async def create_work_order(
    payload: WorkOrderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    item = WorkOrder(
        tenant_id=_scope_tenant_id(current_user),
        alarm_id=payload.alarm_id,
        title=payload.title,
        description=payload.description,
        category=payload.category,
        priority=payload.priority,
        assignee_user_id=payload.assignee_user_id,
        created_by_user_id=current_user.id,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    tid = _scope_tenant_id(current_user)
    await safe_auth_audit(
        db,
        module="work_orders",
        action="create_work_order",
        source="work_order_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=tid,
        status_code=201,
        detail="ok",
        extra_summary=(
            f"work_order_id={item.id}; priority={item.priority or ''}; "
            f"alarm_id={item.alarm_id or ''}"
        ),
    )
    return item

@router.put("/{work_order_id}")
async def update_work_order(
    work_order_id: str,
    payload: WorkOrderUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    stmt = select(WorkOrder).where(WorkOrder.id == work_order_id)
    if not current_user.is_superuser:
        stmt = stmt.where(WorkOrder.tenant_id == _scope_tenant_id(current_user))
    result = await db.execute(stmt)
    item = result.scalars().first()
    if not item:
        await safe_auth_audit(
            db,
            module="work_orders",
            action="update_work_order",
            source="work_order_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_scope_tenant_id(current_user),
            status_code=404,
            detail="not_found",
            extra_summary=f"work_order_id={work_order_id}",
        )
        raise HTTPException(status_code=404, detail="Work order not found")
    if payload.title is not None:
        if not _can_edit_content(item.status or "open"):
            raise HTTPException(status_code=400, detail="Current status does not allow editing title")
        item.title = payload.title
    if payload.description is not None:
        if not _can_edit_content(item.status or "open"):
            raise HTTPException(status_code=400, detail="Current status does not allow editing description")
        item.description = payload.description
    if payload.category is not None:
        if not _can_edit_content(item.status or "open"):
            raise HTTPException(status_code=400, detail="Current status does not allow editing category")
        item.category = payload.category
    if payload.priority is not None:
        if not _can_edit_content(item.status or "open"):
            raise HTTPException(status_code=400, detail="Current status does not allow editing priority")
        item.priority = payload.priority
    if payload.assignee_user_id is not None:
        if not _can_edit_content(item.status or "open"):
            raise HTTPException(status_code=400, detail="Current status does not allow editing assignee")
        item.assignee_user_id = payload.assignee_user_id
    if payload.status is not None:
        current_status = item.status or "open"
        if not _status_transition_allowed(current_status, payload.status):
            raise HTTPException(status_code=400, detail=f"Status transition from {current_status} to {payload.status} is not allowed")  # i18n
        item.status = payload.status
        if payload.status == "closed":
            item.closed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(item)
    await safe_auth_audit(
        db,
        module="work_orders",
        action="update_work_order",
        source="work_order_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_scope_tenant_id(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"work_order_id={item.id}; status={item.status or ''}",
    )
    return item

@router.delete("/{work_order_id}")
async def delete_work_order(
    work_order_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    stmt = select(WorkOrder).where(WorkOrder.id == work_order_id)
    if not current_user.is_superuser:
        stmt = stmt.where(WorkOrder.tenant_id == _scope_tenant_id(current_user))
    result = await db.execute(stmt)
    item = result.scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="Work order not found")
    if not _can_delete(item.status or "open"):
        raise HTTPException(status_code=400, detail="Only closed work orders can be deleted")
    await db.delete(item)
    await db.commit()
    await safe_auth_audit(
        db,
        module="work_orders",
        action="delete_work_order",
        source="work_order_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_scope_tenant_id(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"work_order_id={work_order_id}",
    )
    return {"ok": True}
