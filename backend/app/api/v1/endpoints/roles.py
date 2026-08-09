from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.db.session import get_db
from app.api import deps
from app.core.role_permissions import DEFAULT_ROLE_PERMISSIONS, parse_permission_codes, serialize_permission_codes
from app.models.user import User
from app.models.role import Role
from app.services.auth_audit import safe_auth_audit


router = APIRouter()


def _audit_tid(user: User) -> str:
    return (user.tenant_id or "default").strip() or "default"


SYSTEM_ROLES = [
    {"code": "viewer", "name": "查看者", "permission_codes": DEFAULT_ROLE_PERMISSIONS["viewer"]},
    {"code": "operator", "name": "操作员", "permission_codes": DEFAULT_ROLE_PERMISSIONS["operator"]},
    {"code": "admin", "name": "管理员", "permission_codes": DEFAULT_ROLE_PERMISSIONS["admin"]},
    {"code": "owner", "name": "所有者", "permission_codes": DEFAULT_ROLE_PERMISSIONS["owner"]},
]


async def ensure_system_roles(db: AsyncSession, tenant_id: str) -> None:
    rows = (await db.execute(select(Role).where(Role.tenant_id == tenant_id))).scalars().all()
    existing_by_code = {str(r.code or "").strip(): r for r in rows}
    changed = False
    for r in SYSTEM_ROLES:
        code = r["code"]
        row = existing_by_code.get(code)
        if row:
            # 仅确保系统角色存在，不在每次查询时强制覆盖已保存权限，
            # 避免“角色管理编辑后再次被重置”的问题。
            if not row.is_system:
                row.is_system = True
                changed = True
            # 历史数据兼容：只有权限为空时才补默认值，不覆盖用户已配置内容。
            if not (row.permission_codes or "").strip():
                row.permission_codes = serialize_permission_codes(r["permission_codes"])
                changed = True
            continue
        row = Role(
            tenant_id=tenant_id,
            code=code,
            name=r["name"],
            description="",
            permission_codes=serialize_permission_codes(r["permission_codes"]),
            is_system=True,
        )
        db.add(row)
        changed = True
    if changed:
        await db.commit()


def _to_role_out(row: Role) -> "RoleOut":
    return RoleOut(
        id=str(row.id),
        tenant_id=str(row.tenant_id or "default"),
        code=str(row.code or ""),
        name=str(row.name or ""),
        description=row.description or "",
        permission_codes=parse_permission_codes(row.permission_codes, row.code),
        is_system=bool(row.is_system),
    )


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    tenant_id: str
    code: str
    name: str
    description: str | None = ""
    permission_codes: list[str] = Field(default_factory=list)
    is_system: bool = False


class RoleCreate(BaseModel):
    code: str
    name: str
    description: str | None = ""
    permission_codes: list[str] | None = None


@router.get("", response_model=list[RoleOut])
async def list_roles(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    tenant_id = current_user.tenant_id or "default"
    await ensure_system_roles(db, tenant_id)
    stmt = select(Role)
    if not current_user.is_superuser:
        stmt = stmt.where(Role.tenant_id == tenant_id)
    stmt = stmt.order_by(Role.is_system.desc(), Role.code.asc())
    rows = (await db.execute(stmt)).scalars().all()
    return [_to_role_out(row) for row in rows]


@router.post("", response_model=RoleOut)
async def create_role(
    payload: RoleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("roles.manage"))  # 角色检查→权限码检查,
):
    tenant_id = current_user.tenant_id or "default"
    await ensure_system_roles(db, tenant_id)
    code = (payload.code or "").strip()
    name = (payload.name or "").strip()
    if not code or not name:
        await safe_auth_audit(
            db,
            module="roles",
            action="create_role",
            source="role_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="code_or_name_required",
        )
        raise HTTPException(status_code=400, detail="code/name required")
    stmt = select(Role).where(Role.tenant_id == tenant_id, Role.code == code)
    if (await db.execute(stmt)).scalars().first():
        await safe_auth_audit(
            db,
            module="roles",
            action="create_role",
            source="role_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="duplicate_code",
            extra_summary=f"code={code}",
        )
        raise HTTPException(status_code=400, detail="role code already exists")
    row = Role(
        tenant_id=tenant_id,
        code=code,
        name=name,
        description=(payload.description or "").strip(),
        permission_codes=serialize_permission_codes(payload.permission_codes),
        is_system=False,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    await safe_auth_audit(
        db,
        module="roles",
        action="create_role",
        source="role_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"role_id={row.id}; code={row.code}",
    )
    return _to_role_out(row)


@router.put("/{role_id}", response_model=RoleOut)
async def update_role(
    role_id: str,
    payload: RoleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("roles.manage"))  # 角色检查→权限码检查,
):
    tenant_id = current_user.tenant_id or "default"
    row = (await db.execute(select(Role).where(Role.id == role_id, Role.tenant_id == tenant_id))).scalars().first()
    if not row:
        await safe_auth_audit(
            db,
            module="roles",
            action="update_role",
            source="role_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="not_found",
            extra_summary=f"role_id={role_id}",
        )
        raise HTTPException(status_code=404, detail="role not found")
    code = (payload.code or "").strip()
    name = (payload.name or "").strip()
    if not code or not name:
        await safe_auth_audit(
            db,
            module="roles",
            action="update_role",
            source="role_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="code_or_name_required",
            extra_summary=f"role_id={role_id}",
        )
        raise HTTPException(status_code=400, detail="code/name required")
    if not row.is_system and code != row.code:
        exists = (await db.execute(select(Role).where(Role.tenant_id == tenant_id, Role.code == code, Role.id != row.id))).scalars().first()
        if exists:
            await safe_auth_audit(
                db,
                module="roles",
                action="update_role",
                source="role_admin",
                operator=current_user.username or "unknown",
                result="failed",
                tenant_id=_audit_tid(current_user),
                status_code=400,
                detail="duplicate_code",
                extra_summary=f"role_id={role_id}; code={code}",
            )
            raise HTTPException(status_code=400, detail="role code already exists")
    if not row.is_system:
        row.code = code
    row.name = name
    row.description = (payload.description or "").strip()
    row.permission_codes = serialize_permission_codes(payload.permission_codes)
    await db.commit()
    await safe_auth_audit(
        db,
        module="roles",
        action="update_role",
        source="role_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"role_id={row.id}; code={row.code}",
    )
    await db.refresh(row)
    return _to_role_out(row)


@router.delete("/{role_id}")
async def delete_role(
    role_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("roles.manage"))  # 角色检查→权限码检查,
):
    tenant_id = current_user.tenant_id or "default"
    row = (await db.execute(select(Role).where(Role.id == role_id, Role.tenant_id == tenant_id))).scalars().first()
    if not row:
        await safe_auth_audit(
            db,
            module="roles",
            action="delete_role",
            source="role_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="not_found",
            extra_summary=f"role_id={role_id}",
        )
        raise HTTPException(status_code=404, detail="role not found")
    if row.is_system:
        await safe_auth_audit(
            db,
            module="roles",
            action="delete_role",
            source="role_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="system_role_readonly",
            extra_summary=f"role_id={role_id}; code={row.code}",
        )
        raise HTTPException(status_code=400, detail="System role cannot be deleted")
    cnt = int((await db.execute(select(func.count(User.id)).where(User.tenant_id == tenant_id, User.role == row.code))).scalar() or 0)
    if cnt > 0:
        await safe_auth_audit(
            db,
            module="roles",
            action="delete_role",
            source="role_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="role_in_use",
            extra_summary=f"role_id={row.id}; code={row.code}; user_count={cnt}",
        )
        raise HTTPException(status_code=400, detail="Role is still used by users, cannot delete")
    rid, rcode = row.id, row.code
    await db.delete(row)
    await db.commit()
    await safe_auth_audit(
        db,
        module="roles",
        action="delete_role",
        source="role_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"role_id={rid}; code={rcode}",
    )
    return {"ok": True}
