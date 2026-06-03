"""组织 API：树形管理，用于分级分权与资产归属。"""
from fastapi import Query, APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from app.db.session import get_db
from app.api import deps
from app.models.user import User
from app.models.organization import Organization
from app.models.asset import Asset
from app.services.auth_audit import safe_auth_audit
from collections import defaultdict

router = APIRouter()


def _audit_tid(user: User) -> str:
    return (user.tenant_id or "default").strip() or "default"


class OrganizationCreate(BaseModel):
    name: str
    parent_id: Optional[str] = None
    sort_order: int = 0


class OrganizationUpdate(BaseModel):
    name: Optional[str] = None
    parent_id: Optional[str] = None
    sort_order: Optional[int] = None


def _tenant_filter(stmt, user: User):
    if user.is_superuser:
        return stmt
    tid = user.tenant_id or "default"
    return stmt.where(Organization.tenant_id == tid)


@router.get("/tree")
async def get_organization_tree(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """返回组织树。"""
    stmt = select(Organization).order_by(Organization.sort_order, Organization.name)
    stmt = _tenant_filter(stmt, current_user)
    result = await db.execute(stmt)
    all_orgs = result.scalars().all()
    by_parent: dict = defaultdict(list)
    for o in all_orgs:
        pid = o.parent_id or "__root__"
        by_parent[pid].append({
            "id": o.id,
            "name": o.name,
            "parent_id": o.parent_id,
            "tenant_id": o.tenant_id,
            "sort_order": o.sort_order,
            "children": [],
        })

    def build(node: dict) -> dict:
        node["children"] = sorted(
            [build(n) for n in by_parent.get(node["id"], [])],
            key=lambda x: (x["sort_order"], x["name"]),
        )
        return node

    roots = sorted(by_parent.get("__root__", []), key=lambda x: (x["sort_order"], x["name"]))
    return [build(r) for r in roots]


@router.get("")
async def list_organizations(
    parent_id: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=10000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """列表（可按父节点筛选）。"""
    limit = min(limit, 500)
    stmt = select(Organization)
    stmt = _tenant_filter(stmt, current_user)
    if parent_id is not None:
        stmt = stmt.where(Organization.parent_id == parent_id)
    stmt = stmt.order_by(Organization.sort_order, Organization.name).offset(skip).limit(limit)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [
        {"id": r.id, "name": r.name, "parent_id": r.parent_id, "tenant_id": r.tenant_id, "sort_order": r.sort_order}
        for r in rows
    ]


@router.post("", status_code=201)
async def create_organization(
    payload: OrganizationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """新建组织。"""
    tenant_id = "default" if current_user.is_superuser else (current_user.tenant_id or "default")
    o = Organization(
        name=payload.name.strip(),
        parent_id=payload.parent_id,
        tenant_id=tenant_id,
        sort_order=payload.sort_order,
    )
    db.add(o)
    await db.commit()
    await db.refresh(o)
    await safe_auth_audit(
        db,
        module="organizations",
        action="create_organization",
        source="org_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=201,
        detail="ok",
        extra_summary=f"organization_id={o.id}; name={o.name}",
    )
    return {"id": o.id, "name": o.name, "parent_id": o.parent_id}


@router.put("/{organization_id}")
async def update_organization(
    organization_id: str,
    payload: OrganizationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """更新组织。"""
    stmt = select(Organization).where(Organization.id == organization_id)
    stmt = _tenant_filter(stmt, current_user)
    r = (await db.execute(stmt)).scalars().first()
    if not r:
        await safe_auth_audit(
            db,
            module="organizations",
            action="update_organization",
            source="org_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="not_found",
            extra_summary=f"organization_id={organization_id}",
        )
        raise HTTPException(status_code=404, detail="Organization not found")
    if payload.name is not None:
        r.name = payload.name.strip()
    if payload.parent_id is not None:
        r.parent_id = payload.parent_id
    if payload.sort_order is not None:
        r.sort_order = payload.sort_order
    await db.commit()
    await safe_auth_audit(
        db,
        module="organizations",
        action="update_organization",
        source="org_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"organization_id={r.id}; name={r.name}",
    )
    return {"status": "ok"}


@router.delete("/{organization_id}")
async def delete_organization(
    organization_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """删除组织（无子组织且无关联资产时方可删除）。"""
    stmt = select(Organization).where(Organization.id == organization_id)
    stmt = _tenant_filter(stmt, current_user)
    r = (await db.execute(stmt)).scalars().first()
    if not r:
        await safe_auth_audit(
            db,
            module="organizations",
            action="delete_organization",
            source="org_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="not_found",
            extra_summary=f"organization_id={organization_id}",
        )
        raise HTTPException(status_code=404, detail="Organization not found")
    children = (await db.execute(select(Organization).where(Organization.parent_id == organization_id))).scalars().all()
    if children:
        await safe_auth_audit(
            db,
            module="organizations",
            action="delete_organization",
            source="org_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="has_children",
            extra_summary=f"organization_id={organization_id}; child_count={len(children)}",
        )
        raise HTTPException(status_code=400, detail="Sub-organizations exist, cannot delete")
    bound_asset = (await db.execute(select(Asset).where(Asset.organization_id == organization_id))).scalars().first()
    if bound_asset:
        await safe_auth_audit(
            db,
            module="organizations",
            action="delete_organization",
            source="org_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="has_assets",
            extra_summary=f"organization_id={organization_id}",
        )
        raise HTTPException(status_code=400, detail="Assets exist under this organization, remove them first")
    oid, oname = r.id, r.name
    await db.delete(r)
    await db.commit()
    await safe_auth_audit(
        db,
        module="organizations",
        action="delete_organization",
        source="org_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"organization_id={oid}; name={oname}",
    )
    return {"status": "ok"}
