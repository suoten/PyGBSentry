# FIX: [2026-07-03] api.py 在 _ENDPOINT_MODULES 中引用 "platforms" 模块，但开源版中该文件
#      不存在，导致 _load("platforms") 返回 None，/platforms/* 路由全部 404。
#      根因：开源版拆分时遗漏了级联平台管理端点模块。修复：基于现有 ParentPlatform 模型重建。 [全栈工程师]
"""级联平台管理端点 — 管理上级平台注册与配置。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any

from app.db.session import get_db
from app.models.platform import ParentPlatform
from app.models.user import User
from app.api import deps
from app.core.config import settings
from app.services.auth_audit import safe_auth_audit

router = APIRouter()


class PlatformCreatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    server_gb_id: str
    server_ip: str
    server_port: int = 5060
    transport: str = "UDP"
    client_gb_id: str
    password: str | None = None


class PlatformUpdatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    server_ip: str | None = None
    server_port: int | None = None
    transport: str | None = None
    password: str | None = None


def _platform_to_dict(p: ParentPlatform) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "name": p.name,
        "server_gb_id": p.server_gb_id,
        "server_ip": p.server_ip,
        "server_port": p.server_port,
        "transport": p.transport,
        "client_gb_id": p.client_gb_id,
        "tenant_id": p.tenant_id,
    }


@router.get("")
async def list_platforms(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    base_where = []
    if not current_user.is_superuser:
        base_where.append(ParentPlatform.tenant_id == (current_user.tenant_id or "default"))

    count_stmt = select(func.count()).select_from(ParentPlatform)
    for cond in base_where:
        count_stmt = count_stmt.where(cond)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = select(ParentPlatform)
    for cond in base_where:
        stmt = stmt.where(cond)
    stmt = stmt.order_by(ParentPlatform.name).offset(skip).limit(limit)
    platforms = (await db.execute(stmt)).scalars().all()
    return {"items": [_platform_to_dict(p) for p in platforms], "total": total, "skip": skip, "limit": limit}


@router.get("/server_config")
async def get_server_config(
    current_user: User = Depends(deps.get_current_active_user),
):
    """返回本平台的 SIP 服务器配置（供前端级联页面使用）。"""
    return {
        "sip_id": getattr(settings, "SIP_ID", ""),
        "sip_domain": getattr(settings, "SIP_DOMAIN", ""),
        "sip_ip": getattr(settings, "SIP_IP", ""),
        "sip_port": getattr(settings, "SIP_PORT", 5060),
        "sip_password": "***",
    }


@router.post("")
async def create_platform(
    payload: PlatformCreatePayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    name = payload.name.strip()
    server_gb_id = payload.server_gb_id.strip()
    if not name or not server_gb_id:
        raise HTTPException(status_code=400, detail="Name and server_gb_id are required")

    existing = (await db.execute(
        select(ParentPlatform).where(ParentPlatform.server_gb_id == server_gb_id)
    )).scalars().first()
    if existing:
        raise HTTPException(status_code=400, detail="Platform with this server_gb_id already exists")

    tenant_id = current_user.tenant_id or "default"
    platform = ParentPlatform(
        tenant_id=tenant_id,
        name=name,
        server_gb_id=server_gb_id,
        server_ip=payload.server_ip.strip(),
        server_port=payload.server_port,
        transport=payload.transport.strip().upper(),
        client_gb_id=payload.client_gb_id.strip(),
    )
    if payload.password:
        platform.decrypted_password = payload.password.strip()

    db.add(platform)
    await db.commit()
    await db.refresh(platform)

    await safe_auth_audit(
        db,
        module="platforms",
        action="create_platform",
        source="platform_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=tenant_id,
        status_code=200,
        detail=f"server_gb_id={server_gb_id};name={name}",
    )

    return {"status": "ok", "platform": _platform_to_dict(platform)}


@router.put("/{platform_id}")
async def update_platform(
    platform_id: str,
    payload: PlatformUpdatePayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    platform = (await db.execute(
        select(ParentPlatform).where(ParentPlatform.id == platform_id)
    )).scalars().first()
    if not platform:
        raise HTTPException(status_code=404, detail="Platform not found")

    if not current_user.is_superuser and platform.tenant_id != (current_user.tenant_id or "default"):
        raise HTTPException(status_code=403, detail="Permission denied")

    if payload.name is not None:
        platform.name = payload.name.strip()
    if payload.server_ip is not None:
        platform.server_ip = payload.server_ip.strip()
    if payload.server_port is not None:
        platform.server_port = payload.server_port
    if payload.transport is not None:
        platform.transport = payload.transport.strip().upper()
    if payload.password is not None:
        platform.decrypted_password = payload.password.strip() or None

    await db.commit()
    await db.refresh(platform)
    return {"status": "ok", "platform": _platform_to_dict(platform)}


@router.delete("/{platform_id}")
async def delete_platform(
    platform_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    platform = (await db.execute(
        select(ParentPlatform).where(ParentPlatform.id == platform_id)
    )).scalars().first()
    if not platform:
        raise HTTPException(status_code=404, detail="Platform not found")

    if not current_user.is_superuser and platform.tenant_id != (current_user.tenant_id or "default"):
        raise HTTPException(status_code=403, detail="Permission denied")

    await db.delete(platform)
    await db.commit()
    return {"status": "ok", "message": "Platform deleted"}
