"""资产管理：设备台账、维保记录。"""
from fastapi import Query, APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.db.session import get_db
from app.models.asset import Asset
from app.models.asset_maintenance import AssetMaintenance
from app.models.user import User
from app.api import deps
from app.services.auth_audit import safe_auth_audit

router = APIRouter()


def _audit_tid(user: User) -> str:
    return (user.tenant_id or "default").strip() or "default"


class MaintenanceCreate(BaseModel):
    asset_id: str
    maintenance_type: str = "routine"
    maintenance_date: datetime
    note: Optional[str] = None
    operator: Optional[str] = None


class MaintenanceUpdate(BaseModel):
    maintenance_type: Optional[str] = None
    maintenance_date: Optional[datetime] = None
    note: Optional[str] = None
    operator: Optional[str] = None


@router.get("/ledger")
async def device_ledger(
    skip: int = Query(0, ge=0),  # FIXED
    limit: int = Query(100, ge=1, le=10000),  # FIXED
    keyword: str = "",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """设备台账：设备列表及维保摘要。"""
    stmt = select(Asset)
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
    if keyword:
        stmt = stmt.where(
            Asset.gb_id.ilike(f"%{keyword}%") | Asset.name.ilike(f"%{keyword}%")
        )
    stmt = stmt.offset(skip).limit(limit).order_by(Asset.created_at.desc())
    result = await db.execute(stmt)
    assets = result.scalars().all()
    asset_ids = [a.id for a in assets]
    # 维保次数
    count_stmt = select(AssetMaintenance.asset_id, func.count(AssetMaintenance.id)).where(
        AssetMaintenance.asset_id.in_(asset_ids)
    ).group_by(AssetMaintenance.asset_id)
    counts = {r[0]: r[1] for r in (await db.execute(count_stmt)).all()}
    out = []
    for a in assets:
        out.append({
            "id": a.id,
            "gb_id": a.gb_id,
            "name": a.name,
            "manufacturer": a.manufacturer,
            "model": a.model,
            "status": a.status,
            "maintenance_count": counts.get(a.id, 0),
        })
    return out


@router.get("/maintenances")
async def list_maintenances(
    asset_id: Optional[str] = None,
    skip: int = Query(0, ge=0),  # FIXED
    limit: int = Query(50, ge=1, le=10000),  # FIXED
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """维保记录列表。"""
    stmt = select(AssetMaintenance)
    if asset_id:
        stmt = stmt.where(AssetMaintenance.asset_id == asset_id)
    if not current_user.is_superuser:
        stmt = stmt.join(Asset, Asset.id == AssetMaintenance.asset_id).where(
            Asset.tenant_id == (current_user.tenant_id or "default")
        )
    stmt = stmt.offset(skip).limit(limit).order_by(AssetMaintenance.maintenance_date.desc())
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "asset_id": r.asset_id,
            "maintenance_type": r.maintenance_type,
            "maintenance_date": r.maintenance_date.isoformat() if r.maintenance_date else None,
            "note": r.note,
            "operator": r.operator,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.post("/maintenances", status_code=201)
async def create_maintenance(
    payload: MaintenanceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """新增维保记录。"""
    stmt = select(Asset).where(Asset.id == payload.asset_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
    asset = (await db.execute(stmt)).scalars().first()
    if not asset:
        await safe_auth_audit(
            db,
            module="asset_management",
            action="create_maintenance",
            source="asset_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="asset_not_found",
            extra_summary=f"asset_id={payload.asset_id}",
        )
        raise HTTPException(status_code=404, detail="Device not found")
    m = AssetMaintenance(
        asset_id=payload.asset_id,
        maintenance_type=payload.maintenance_type or "routine",
        maintenance_date=payload.maintenance_date,
        note=payload.note,
        operator=payload.operator or current_user.username,
    )
    db.add(m)
    await db.commit()
    await db.refresh(m)
    await safe_auth_audit(
        db,
        module="asset_management",
        action="create_maintenance",
        source="asset_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=201,
        detail="ok",
        extra_summary=f"maintenance_id={m.id}; asset_id={m.asset_id}; type={m.maintenance_type or ''}",
    )
    return {"id": m.id, "asset_id": m.asset_id}


@router.put("/maintenances/{maintenance_id}")
async def update_maintenance(
    maintenance_id: str,
    payload: MaintenanceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    stmt = select(AssetMaintenance).where(AssetMaintenance.id == maintenance_id)
    if not current_user.is_superuser:
        stmt = stmt.join(Asset, Asset.id == AssetMaintenance.asset_id).where(
            Asset.tenant_id == (current_user.tenant_id or "default")
        )
    m = (await db.execute(stmt)).scalars().first()
    if not m:
        await safe_auth_audit(
            db,
            module="asset_management",
            action="update_maintenance",
            source="asset_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="not_found",
            extra_summary=f"maintenance_id={maintenance_id}",
        )
        raise HTTPException(status_code=404, detail="Maintenance record not found")
    if payload.maintenance_type is not None:
        m.maintenance_type = payload.maintenance_type
    if payload.maintenance_date is not None:
        m.maintenance_date = payload.maintenance_date
    if payload.note is not None:
        m.note = payload.note
    if payload.operator is not None:
        m.operator = payload.operator
    await db.commit()
    await safe_auth_audit(
        db,
        module="asset_management",
        action="update_maintenance",
        source="asset_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"maintenance_id={m.id}; asset_id={m.asset_id}",
    )
    return {"status": "ok"}


@router.delete("/maintenances/{maintenance_id}")
async def delete_maintenance(
    maintenance_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    stmt = select(AssetMaintenance).where(AssetMaintenance.id == maintenance_id)
    if not current_user.is_superuser:
        stmt = stmt.join(Asset, Asset.id == AssetMaintenance.asset_id).where(
            Asset.tenant_id == (current_user.tenant_id or "default")
        )
    m = (await db.execute(stmt)).scalars().first()
    if not m:
        await safe_auth_audit(
            db,
            module="asset_management",
            action="delete_maintenance",
            source="asset_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="not_found",
            extra_summary=f"maintenance_id={maintenance_id}",
        )
        raise HTTPException(status_code=404, detail="Maintenance record not found")
    mid, aid = m.id, m.asset_id
    await db.delete(m)
    await db.commit()
    await safe_auth_audit(
        db,
        module="asset_management",
        action="delete_maintenance",
        source="asset_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"maintenance_id={mid}; asset_id={aid}",
    )
    return {"status": "ok"}
