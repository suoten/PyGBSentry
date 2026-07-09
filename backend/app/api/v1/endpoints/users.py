# FIX: [2026-07-03] api.py 在 _ENDPOINT_MODULES 中引用 "users" 模块，但开源版中该文件
#      不存在，导致 _load("users") 返回 None，/users/* 路由全部 404。
#      根因：开源版拆分时遗漏了用户管理端点模块。修复：基于现有 User 模型重建。 [全栈工程师]
"""用户管理端点 — 基于开源版 User 模型提供基础 CRUD。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any

from app.db.session import get_db
from app.models.user import User
from app.api import deps
from app.core import security
from app.services.auth_audit import safe_auth_audit

router = APIRouter()


class UserCreatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str
    password: str
    email: str | None = None
    full_name: str | None = None
    role: str = "viewer"
    tenant_id: str | None = None
    is_active: bool = True


class UserUpdatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str | None = None
    full_name: str | None = None
    role: str | None = None
    password: str | None = None
    is_active: bool | None = None


def _user_to_dict(u: User) -> dict[str, Any]:
    return {
        "id": str(u.id),
        "username": u.username,
        "email": u.email,
        "full_name": u.full_name,
        "role": u.role,
        "site_role": getattr(u, "site_role", "normal"),
        "tenant_id": u.tenant_id,
        "is_active": u.is_active,
        "is_superuser": u.is_superuser,
        "auth_domain": getattr(u, "auth_domain", "tenant"),
    }


@router.get("/me")
async def get_current_user_info(
    current_user: User = Depends(deps.get_current_active_user),
):
    return _user_to_dict(current_user)


@router.get("")
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    keyword: str | None = Query(None, max_length=64),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    base_where = []
    if not current_user.is_superuser:
        base_where.append(User.tenant_id == (current_user.tenant_id or "default"))
    if keyword and keyword.strip():
        pattern = f"%{keyword.strip()}%"
        base_where.append((User.username.ilike(pattern)) | (User.email.ilike(pattern)))

    count_stmt = select(func.count()).select_from(User)
    for cond in base_where:
        count_stmt = count_stmt.where(cond)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = select(User)
    for cond in base_where:
        stmt = stmt.where(cond)
    stmt = stmt.order_by(User.username).offset(skip).limit(limit)
    users = (await db.execute(stmt)).scalars().all()
    return {"items": [_user_to_dict(u) for u in users], "total": total, "skip": skip, "limit": limit}


@router.post("")
async def create_user(
    payload: UserCreatePayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    username = payload.username.strip()
    if not username or not payload.password:
        raise HTTPException(status_code=400, detail="Username and password are required")

    existing = (await db.execute(select(User).where(User.username == username))).scalars().first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")

    tenant_id = payload.tenant_id or (current_user.tenant_id or "default")
    if not current_user.is_superuser and tenant_id != (current_user.tenant_id or "default"):
        raise HTTPException(status_code=403, detail="Cannot create user for another tenant")

    user = User(
        username=username,
        hashed_password=security.hash_password(payload.password),
        email=payload.email,
        full_name=payload.full_name,
        role=payload.role,
        tenant_id=tenant_id,
        is_active=payload.is_active,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    await safe_auth_audit(
        db,
        module="users",
        action="create_user",
        source="user_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=tenant_id,
        status_code=200,
        detail=f"username={username};role={payload.role}",
    )

    return {"status": "ok", "user": _user_to_dict(user)}


@router.put("/{user_id}")
async def update_user(
    user_id: str,
    payload: UserUpdatePayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    user = (await db.execute(select(User).where(User.id == user_id))).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not current_user.is_superuser and user.tenant_id != (current_user.tenant_id or "default"):
        raise HTTPException(status_code=403, detail="Permission denied")

    if payload.email is not None:
        user.email = payload.email
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.password is not None:
        user.hashed_password = security.hash_password(payload.password)

    await db.commit()
    await db.refresh(user)
    return {"status": "ok", "user": _user_to_dict(user)}


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    user = (await db.execute(select(User).where(User.id == user_id))).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.is_superuser and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Cannot delete superuser")

    if not current_user.is_superuser and user.tenant_id != (current_user.tenant_id or "default"):
        raise HTTPException(status_code=403, detail="Permission denied")

    if str(user.id) == str(current_user.id):
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    await db.delete(user)
    await db.commit()
    return {"status": "ok", "message": "User deleted"}
