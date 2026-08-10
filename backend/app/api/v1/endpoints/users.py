from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.models.user import User
from app.models.role import Role
from app.api import deps
from app.core import security
from app.core.config import settings
from app.core.role_permissions import DEFAULT_ROLE_PERMISSIONS, serialize_permission_codes
from app.core.totp import generate_base32_secret, verify_totp, encrypt_totp_secret, decrypt_totp_secret
# FIX: [2026-07-16 P1] 添加限流依赖，保护敏感账户操作端点
from app.core.ratelimit import limiter, get_tenant_remote_address
from app.services.auth_audit import safe_auth_audit
from app.api.v1.endpoints.login import _validate_password_strength  # W-11: Admin creates user must validate password strength

router = APIRouter()


def _audit_tid(user: User) -> str:
    return (user.tenant_id or "default").strip() or "default"


def _role_validation_audit_detail(exc: HTTPException) -> str:
    d = exc.detail
    if isinstance(d, str):
        if "不存在" in d:
            return "role_not_found"
        if "不能为空" in d:
            return "role_empty"
    return "invalid_role"

class UserCreate(BaseModel):
    username: str
    password: str
    email: str = None
    full_name: str = None
    is_superuser: bool = False
    tenant_id: str = "default"
    role: str = "viewer"


class UserUpdate(BaseModel):
    email: str | None = None
    full_name: str | None = None
    is_active: bool | None = None
    is_superuser: bool | None = None
    tenant_id: str | None = None
    role: str | None = None

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    email: str | None = None
    full_name: str | None = None
    is_active: bool
    is_superuser: bool
    tenant_id: str
    role: str
    totp_enabled: bool = False
    is_locked: bool = False
    locked_until: str | None = None


class TotpSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str


class TotpVerifyRequest(BaseModel):
    code: str


class EnableTotpRequest(BaseModel):
    code: str


class DisableTotpRequest(BaseModel):
    code: str


class UserMeUpdate(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


SYSTEM_ROLE_CODES = {"viewer", "operator", "admin", "owner"}


async def _ensure_system_roles(db: AsyncSession, tenant_id: str) -> None:
    rows = (await db.execute(select(Role).where(Role.tenant_id == tenant_id))).scalars().all()
    existing_by_code = {str(r.code or "").strip(): r for r in rows}
    changed = False
    for code, name in (("viewer", "Viewer"), ("operator", "Operator"), ("admin", "Admin"), ("owner", "Owner")):  # W-15: hardcoded Chinese→English
        row = existing_by_code.get(code)
        if row:
            # 仅保证系统角色存在；不在运行时覆盖管理员已配置的权限。
            if not row.is_system:
                row.is_system = True
                changed = True
            # 仅历史空值时补默认权限，避免“角色编辑成功后又被回写默认”。
            if not (row.permission_codes or "").strip():
                row.permission_codes = serialize_permission_codes(DEFAULT_ROLE_PERMISSIONS.get(code, []))
                changed = True
            continue
        db.add(
            Role(
                tenant_id=tenant_id,
                code=code,
                name=name,
                description="",
                permission_codes=serialize_permission_codes(DEFAULT_ROLE_PERMISSIONS.get(code, [])),
                is_system=True,
            )
        )
        changed = True
    if changed:
        await db.commit()


async def _validate_role(db: AsyncSession, tenant_id: str, role: str) -> None:
    r = (role or "").strip()
    if not r:
        raise HTTPException(status_code=400, detail="Role is required")  # i18n
    if r in SYSTEM_ROLE_CODES:
        await _ensure_system_roles(db, tenant_id)
        return
    row = (await db.execute(select(Role).where(Role.tenant_id == tenant_id, Role.code == r))).scalars().first()
    if not row:
        raise HTTPException(status_code=400, detail="Role not found")  # i18n

@router.get("", response_model=List[UserOut])
async def read_users(
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Retrieve users. Only for superusers.
    """
    stmt = select(User)
    if not current_user.is_superuser:
        stmt = stmt.where(User.tenant_id == (current_user.tenant_id or "default"))
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()

@router.post("", response_model=UserOut)
async def create_user(
    *,
    db: AsyncSession = Depends(get_db),
    user_in: UserCreate,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Create new user. Only for superusers.
    """
    stmt = select(User).where(User.username == user_in.username)
    result = await db.execute(stmt)
    if result.scalars().first():
        tid_dup = user_in.tenant_id if current_user.is_superuser else (current_user.tenant_id or "default")
        await safe_auth_audit(
            db,
            module="users",
            action="create_user",
            source="user_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="duplicate_username",
            extra_summary=f"target_username={user_in.username}; tenant_id={tid_dup}",
        )
        raise HTTPException(
            status_code=400,
            detail="Username already exists",  # i18n
        )

    tenant_id = user_in.tenant_id if current_user.is_superuser else (current_user.tenant_id or "default")
    try:
        await _validate_role(db, tenant_id, user_in.role)
    except HTTPException as e:
        await safe_auth_audit(
            db,
            module="users",
            action="create_user",
            source="user_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=e.status_code,
            detail=_role_validation_audit_detail(e),
            extra_summary=f"target_username={user_in.username}; role={user_in.role!s}; tenant_id={tenant_id}",
        )
        raise
    # W-11 Admin creates user must validate password strength
    valid_pwd, pwd_msg = _validate_password_strength(user_in.password)
    if not valid_pwd:
        await safe_auth_audit(
            db,
            module="users",
            action="create_user",
            source="user_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="password_weak",
            extra_summary=f"target_username={user_in.username}; reason={pwd_msg}",
        )
        raise HTTPException(status_code=400, detail=pwd_msg)
    user = User(
        username=user_in.username,
        hashed_password=security.get_password_hash(user_in.password),
        email=user_in.email,
        full_name=user_in.full_name,
        is_superuser=user_in.is_superuser,
        tenant_id=tenant_id,
        role=user_in.role,
    )
    try:
        db.add(user)
        await db.commit()
        await db.refresh(user)
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=f"Create user failed: {str(e)}") from e  # db.commit异常保护+rollback
    await safe_auth_audit(
        db,
        module="users",
        action="create_user",
        source="user_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(user),
        status_code=200,
        detail="ok",
        extra_summary=f"target_user_id={user.id}; target_username={user.username}",
    )
    return user


@router.put("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: str,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    stmt = select(User).where(User.id == user_id)
    if not current_user.is_superuser:
        stmt = stmt.where(User.tenant_id == (current_user.tenant_id or "default"))
    row = (await db.execute(stmt)).scalars().first()
    if not row:
        await safe_auth_audit(
            db,
            module="users",
            action="update_user",
            source="user_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="user_not_found",
            extra_summary=f"target_user_id={user_id}",
        )
        raise HTTPException(status_code=404, detail="User not found")
    if payload.email is not None:
        row.email = payload.email
    if payload.full_name is not None:
        row.full_name = payload.full_name
    if payload.is_active is not None:
        row.is_active = bool(payload.is_active)
    if current_user.is_superuser:
        if payload.is_superuser is not None:
            row.is_superuser = bool(payload.is_superuser)
        if payload.tenant_id is not None:
            row.tenant_id = (payload.tenant_id or "default").strip() or "default"
    if payload.role is not None:
        try:
            await _validate_role(db, row.tenant_id or "default", payload.role)
        except HTTPException as e:
            await safe_auth_audit(
                db,
                module="users",
                action="update_user",
                source="user_admin",
                operator=current_user.username or "unknown",
                result="failed",
                tenant_id=_audit_tid(current_user),
                status_code=e.status_code,
                detail=_role_validation_audit_detail(e),
                extra_summary=(
                    f"target_user_id={row.id}; role={payload.role!s}; "
                    f"tenant_id={row.tenant_id or 'default'}"
                ),
            )
            raise
        row.role = (payload.role or "").strip()
    await db.commit()
    await db.refresh(row)
    await safe_auth_audit(
        db,
        module="users",
        action="update_user",
        source="user_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(row),
        status_code=200,
        detail="ok",
        extra_summary=f"target_user_id={row.id}; target_username={row.username or ''}",
    )
    return row


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_superuser),
):
    stmt = select(User).where(User.id == user_id)
    if not current_user.is_superuser:
        stmt = stmt.where(User.tenant_id == (current_user.tenant_id or "default"))
    row = (await db.execute(stmt)).scalars().first()
    if not row:
        await safe_auth_audit(
            db,
            module="users",
            action="delete_user",
            source="user_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="user_not_found",
            extra_summary=f"target_user_id={user_id}",
        )
        raise HTTPException(status_code=404, detail="User not found")
    if row.id == current_user.id:
        await safe_auth_audit(
            db,
            module="users",
            action="delete_user",
            source="user_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="cannot_delete_self",
            extra_summary=f"target_user_id={row.id}",
        )
        raise HTTPException(status_code=400, detail="Cannot delete current logged-in user")
    target_username = row.username or ""
    target_tid = _audit_tid(row)
    target_uid = row.id
    await db.delete(row)
    await db.commit()
    await safe_auth_audit(
        db,
        module="users",
        action="delete_user",
        source="user_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=target_tid,
        status_code=200,
        detail="ok",
        extra_summary=f"target_user_id={target_uid}; target_username={target_username}",
    )
    return {"ok": True}

@router.get("/me", response_model=UserOut)
async def read_user_me(
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get current user.
    """
    return current_user


@router.put("/me", response_model=UserOut)
async def update_user_me(
    payload: UserMeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    if payload.email is not None:
        current_user.email = (str(payload.email).strip() or None)
    if payload.full_name is not None:
        current_user.full_name = (str(payload.full_name).strip() or None)
    await db.commit()
    await db.refresh(current_user)
    await safe_auth_audit(
        db,
        module="users",
        action="update_profile",
        source="self_service",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
    )
    return current_user


@router.post("/me/change-password")
@limiter.limit("5/minute", key_func=get_tenant_remote_address)  # FIX: [2026-07-16 P1] 限制密码修改频率
async def change_user_password(
    request: Request,
    payload: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    old_pwd = (payload.current_password or "").strip()
    new_pwd = (payload.new_password or "").strip()
    if not old_pwd or not new_pwd:
        await safe_auth_audit(
            db,
            module="users",
            action="change_password",
            source="self_service",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="missing_password",
        )
        raise HTTPException(status_code=400, detail="Password cannot be empty")
    if len(new_pwd) < 8:
        await safe_auth_audit(
            db,
            module="users",
            action="change_password",
            source="self_service",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="password_too_short",
        )
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")
    if old_pwd == new_pwd:
        await safe_auth_audit(
            db,
            module="users",
            action="change_password",
            source="self_service",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="password_unchanged",
        )
        raise HTTPException(status_code=400, detail="New password cannot be same as current")
    if not security.verify_password(old_pwd, current_user.hashed_password):
        await safe_auth_audit(
            db,
            module="users",
            action="change_password",
            source="self_service",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="invalid_current_password",
        )
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    current_user.hashed_password = security.get_password_hash(new_pwd)
    await db.commit()
    from app.core.redis import redis_client
    if redis_client:
        import time as _time
        await redis_client.set(
            f"user_token_revoked:{current_user.id}",
            str(_time.time()),
            ex=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
    await safe_auth_audit(
        db,
        module="users",
        action="change_password",
        source="self_service",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
    )
    return {"ok": True}


@router.post("/me/2fa/setup", response_model=TotpSetupResponse)
@limiter.limit("5/minute", key_func=get_tenant_remote_address)  # FIX: [2026-07-16 P1] 限制 2FA 设置频率
async def setup_totp(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """生成 TOTP secret（不直接启用，需 verify 后启用）。"""
    secret = generate_base32_secret()
    current_user.totp_secret = encrypt_totp_secret(secret)
    current_user.totp_enabled = False
    await db.commit()
    issuer = "PyGBSentry"
    label = f"{issuer}:{current_user.username}"
    otpauth_uri = f"otpauth://totp/{label}?secret={secret}&issuer={issuer}&digits=6&period=30"
    await safe_auth_audit(
        db,
        action="totp_setup",
        source="2fa",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
    )
    return {"secret": secret, "otpauth_uri": otpauth_uri}


@router.post("/me/2fa/enable")
@limiter.limit("5/minute", key_func=get_tenant_remote_address)  # FIX: [2026-07-16 P1] 限制 2FA 启用频率
async def enable_totp(
    request: Request,
    payload: EnableTotpRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    encrypted_secret = getattr(current_user, "totp_secret", None)
    if not encrypted_secret:
        await safe_auth_audit(
            db,
            action="totp_enable",
            source="2fa",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="setup_required",
        )
        raise HTTPException(status_code=400, detail="Please set up 2FA first")
    try:
        decrypted_secret = decrypt_totp_secret(encrypted_secret)
    except ValueError:
        import logging as _logging
        _logging.getLogger(__name__).warning("TOTP secret decryption failed for user %s during enable", getattr(current_user, "id", "unknown"))
        raise HTTPException(status_code=500, detail="TOTP secret decryption failed. Please contact administrator to reset 2FA.")
    if not verify_totp(payload.code, decrypted_secret):
        await safe_auth_audit(
            db,
            action="totp_enable",
            source="2fa",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="invalid_otp",
        )
        raise HTTPException(status_code=400, detail="Verification code incorrect")
    current_user.totp_enabled = True
    await db.commit()
    await safe_auth_audit(
        db,
        action="totp_enable",
        source="2fa",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
    )
    return {"ok": True, "totp_enabled": True}


@router.post("/me/2fa/disable")
@limiter.limit("3/minute", key_func=get_tenant_remote_address)  # FIX: [2026-07-16 P1] 限制 2FA 禁用频率（更严格）
async def disable_totp(
    request: Request,
    payload: DisableTotpRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    if not getattr(current_user, "totp_enabled", False):
        await safe_auth_audit(
            db,
            action="totp_disable",
            source="2fa",
            operator=current_user.username or "unknown",
            result="success",
            tenant_id=_audit_tid(current_user),
            status_code=200,
            detail="already_disabled",
        )
        return {"ok": True, "totp_enabled": False}
    encrypted_secret = getattr(current_user, "totp_secret", None)
    if not encrypted_secret:
        await safe_auth_audit(
            db,
            action="totp_disable",
            source="2fa",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="invalid_otp",
        )
        raise HTTPException(status_code=400, detail="Verification code incorrect")
    try:
        decrypted_secret = decrypt_totp_secret(encrypted_secret)
    except ValueError:
        import logging as _logging
        _logging.getLogger(__name__).warning("TOTP secret decryption failed for user %s during disable", getattr(current_user, "id", "unknown"))
        raise HTTPException(status_code=500, detail="TOTP secret decryption failed. Please contact administrator to reset 2FA.")
    if not verify_totp(payload.code, decrypted_secret):
        await safe_auth_audit(
            db,
            action="totp_disable",
            source="2fa",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="invalid_otp",
        )
        raise HTTPException(status_code=400, detail="Verification code incorrect")
    current_user.totp_enabled = False
    current_user.totp_secret = None
    await db.commit()
    await safe_auth_audit(
        db,
        action="totp_disable",
        source="2fa",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
    )
    return {"ok": True, "totp_enabled": False}


@router.post("/{user_id}/unlock")
@limiter.limit("5/minute", key_func=get_tenant_remote_address)  # FIX: [2026-07-16 P1] 限制账户解锁频率
async def unlock_user(
    request: Request,
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("users.manage")),  # 角色检查→权限码检查
) -> Any:
    stmt = select(User).where(User.id == user_id, User.tenant_id == current_user.tenant_id)  # S-05 添加租户隔离
    result = await db.execute(stmt)
    target = result.scalars().first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    target.failed_login_attempts = 0
    target.locked_until = None
    await db.commit()
    return {"ok": True, "user_id": user_id}
