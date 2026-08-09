"""行政区域 API：省-市-县区树形管理。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from app.db.session import get_db
from app.api import deps
from app.models.user import User
from app.models.region import Region
from app.services.auth_audit import safe_auth_audit
from collections import defaultdict

router = APIRouter()


def _audit_tid(user: User) -> str:
    return (user.tenant_id or "default").strip() or "default"


class RegionCreate(BaseModel):
    code: str
    name: str
    parent_id: Optional[str] = None
    level: int = 0
    sort_order: int = 0


class RegionUpdate(BaseModel):
    name: Optional[str] = None
    parent_id: Optional[str] = None
    level: Optional[int] = None
    sort_order: Optional[int] = None


@router.get("/tree")
async def get_region_tree(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """返回行政区域树（省-市-县）。"""
    result = await db.execute(select(Region).order_by(Region.level, Region.sort_order, Region.code))
    all_regions = result.scalars().all()
    by_parent: dict = defaultdict(list)
    for r in all_regions:
        pid = r.parent_id or "__root__"
        by_parent[pid].append({
            "id": r.id,
            "code": r.code,
            "name": r.name,
            "parent_id": r.parent_id,
            "level": r.level,
            "sort_order": r.sort_order,
            "children": [],
        })
    def build(node: dict) -> dict:
        node["children"] = sorted(
            [build(n) for n in by_parent.get(node["id"], [])],
            key=lambda x: (x["sort_order"], x["code"]),
        )
        return node
    roots = sorted(by_parent.get("__root__", []), key=lambda x: (x["sort_order"], x["code"]))
    return [build(r) for r in roots]


@router.get("")
async def list_regions(
    parent_id: Optional[str] = None,
    level: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """列表（可按父节点、层级筛选）。"""
    stmt = select(Region)
    if parent_id is not None:
        stmt = stmt.where(Region.parent_id == parent_id)
    if level is not None:
        stmt = stmt.where(Region.level == level)
    stmt = stmt.order_by(Region.level, Region.sort_order, Region.code)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [{"id": r.id, "code": r.code, "name": r.name, "parent_id": r.parent_id, "level": r.level, "sort_order": r.sort_order} for r in rows]


@router.post("", status_code=201)
async def create_region(
    payload: RegionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_superuser),
):
    """新建区域（仅超级管理员）。"""
    existing = (await db.execute(select(Region).where(Region.code == payload.code))).scalars().first()
    if existing:
        await safe_auth_audit(
            db,
            module="regions",
            action="create_region",
            source="region_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="duplicate_code",
            extra_summary=f"code={payload.code.strip()}",
        )
        raise HTTPException(status_code=400, detail="Administrative division code already exists")
    r = Region(
        code=payload.code.strip(),
        name=payload.name.strip(),
        parent_id=payload.parent_id,
        level=payload.level,
        sort_order=payload.sort_order,
    )
    db.add(r)
    await db.commit()
    await db.refresh(r)
    await safe_auth_audit(
        db,
        module="regions",
        action="create_region",
        source="region_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=201,
        detail="ok",
        extra_summary=f"region_id={r.id}; code={r.code}",
    )
    return {"id": r.id, "code": r.code, "name": r.name}


@router.put("/{region_id}")
async def update_region(
    region_id: str,
    payload: RegionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_superuser),
):
    """更新区域。"""
    r = (await db.execute(select(Region).where(Region.id == region_id))).scalars().first()
    if not r:
        await safe_auth_audit(
            db,
            module="regions",
            action="update_region",
            source="region_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="not_found",
            extra_summary=f"region_id={region_id}",
        )
        raise HTTPException(status_code=404, detail="Region not found")
    if payload.name is not None:
        r.name = payload.name.strip()
    if payload.parent_id is not None:
        r.parent_id = payload.parent_id
    if payload.level is not None:
        r.level = payload.level
    if payload.sort_order is not None:
        r.sort_order = payload.sort_order
    await db.commit()
    await safe_auth_audit(
        db,
        module="regions",
        action="update_region",
        source="region_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"region_id={r.id}; code={r.code}",
    )
    return {"status": "ok"}


@router.delete("/{region_id}")
async def delete_region(
    region_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_superuser),
):
    """删除区域（无子节点时方可删除）。"""
    r = (await db.execute(select(Region).where(Region.id == region_id))).scalars().first()
    if not r:
        await safe_auth_audit(
            db,
            module="regions",
            action="delete_region",
            source="region_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="not_found",
            extra_summary=f"region_id={region_id}",
        )
        raise HTTPException(status_code=404, detail="Region not found")
    children = (await db.execute(select(Region).where(Region.parent_id == region_id))).scalars().all()
    if children:
        await safe_auth_audit(
            db,
            module="regions",
            action="delete_region",
            source="region_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="has_children",
            extra_summary=f"region_id={region_id}; child_count={len(children)}",
        )
        raise HTTPException(status_code=400, detail="Sub-regions exist, cannot delete")
    rid, rcode = r.id, r.code
    await db.delete(r)
    await db.commit()
    await safe_auth_audit(
        db,
        module="regions",
        action="delete_region",
        source="region_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"region_id={rid}; code={rcode}",
    )
    return {"status": "ok"}
