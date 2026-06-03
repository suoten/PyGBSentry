import re
from datetime import timedelta, datetime, timezone
from typing import Any
import jwt as _jwt
from jwt import InvalidTokenError

LOGIN_MAX_FAILED_ATTEMPTS = 5
LOGIN_LOCKOUT_MINUTES = 30
from fastapi import APIRouter, Depends, HTTPException, Request, Form, Response
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.core import security
from app.core.config import settings
from app.models.user import User
from app.models.billing import TenantSubscription
from app.core.ratelimit import limiter
from app.core.totp import verify_totp
from app.services.auth_audit import safe_auth_audit
from loguru import logger

router = APIRouter()


@router.get("/login/verify-token")
async def verify_token(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Any:
    token = request.cookies.get("access_token") or request.query_params.get("token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Authentication token not provided")  # FIXED: 中文→英文
    try:
        payload = _jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM],
            options={"verify_aud": True},
            audience="pygbsentry:access"
        )
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid or expired token")  # FIXED: 中文→英文
        stmt = select(User).where(User.id == str(user_id).strip())
        result = await db.execute(stmt)
        user = result.scalars().first()
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="User account is disabled")  # FIXED: 中文→英文
        return {
            "valid": True,
            "role": user.role or ("owner" if user.is_superuser else "viewer"),
            "is_superuser": user.is_superuser,
            "tenant_id": user.tenant_id or "default",
        }
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token verification failed")  # FIXED: 中文→英文


class RefreshTokenRequest(BaseModel):
    refresh_token: str


@router.post("/login/refresh-token")
async def refresh_token(
    payload: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        decoded = _jwt.decode(
            payload.refresh_token, settings.SECRET_KEY, algorithms=[security.ALGORITHM],
            options={"verify_aud": True},
            audience="pygbsentry:refresh"
        )
        if decoded.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Not a refresh token")  # FIXED: 中文→英文
        user_id = decoded.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid refresh token")  # FIXED: 中文→英文
        stmt = select(User).where(User.id == str(user_id).strip())
        result = await db.execute(stmt)
        user = result.scalars().first()
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="User account is disabled")  # FIXED: 中文→英文
        new_access_token = security.create_access_token(
            subject=user.id,
            extra_payload={
                "role": user.role or ("owner" if user.is_superuser else "viewer"),
                "is_superuser": user.is_superuser,
                "tenant_id": user.tenant_id or "default",
            }
        )
        return {"access_token": new_access_token, "token_type": "bearer"}
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Refresh token expired or invalid")  # FIXED: 中文→英文


@router.post("/login/logout")
async def logout(request: Request, response: Response) -> Any:
    response.delete_cookie(key="access_token", path="/")
    return {"detail": "Logged out"}  # FIXED: 中文→英文


def _validate_password_strength(password: str) -> tuple[bool, str]:
    """
    验证密码强度，返回 (是否通过, 错误消息)。
    """
    # FIXED: 中文错误消息→英文+ErrorCode，支持国际化
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r"\d", password):
        return False, "Password must contain at least one digit"
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", password):
        return False, "Password must contain at least one special character"
    return True, ""


class RegisterRequest(BaseModel):
    username: str
    password: str
    email: str | None = None
    full_name: str | None = None


@router.post("/register")
@limiter.limit("2/minute")
async def register_user(
    request: Request,
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    attempted = (payload.username or "").strip() or "unknown"
    if not bool(getattr(settings, "ALLOW_PUBLIC_REGISTRATION", False)):
        await safe_auth_audit(
            db,
            action="register",
            source="register",
            operator=attempted,
            result="failed",
            tenant_id="unknown",
            status_code=403,
            detail="registration_disabled",
        )
        raise HTTPException(status_code=403, detail="Registration is closed")  # FIXED: 中文→英文
    if not payload.username or len(payload.username.strip()) < 3:
        await safe_auth_audit(
            db,
            action="register",
            source="register",
            operator=attempted,
            result="failed",
            tenant_id="unknown",
            status_code=400,
            detail="username_too_short",
        )
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")  # FIXED: 中文→英文
    if not payload.password or len(payload.password) < 8:
        await safe_auth_audit(
            db,
            action="register",
            source="register",
            operator=attempted,
            result="failed",
            tenant_id=attempted,
            status_code=400,
            detail="password_too_short",
        )
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")  # FIXED: 中文→英文
    # 密码强度校验
    valid, msg = _validate_password_strength(payload.password)
    if not valid:
        await safe_auth_audit(
            db,
            action="register",
            source="register",
            operator=attempted,
            result="failed",
            tenant_id=attempted,
            status_code=400,
            detail="password_weak",
        )
        raise HTTPException(status_code=400, detail=msg)
    stmt = select(User).where(User.username == payload.username)
    result = await db.execute(stmt)
    if result.scalars().first():
        await safe_auth_audit(
            db,
            action="register",
            source="register",
            operator=attempted,
            result="failed",
            tenant_id=attempted,
            status_code=400,
            detail="username_taken",
        )
        raise HTTPException(status_code=400, detail="Username already exists")  # FIXED: 中文→英文
    tenant_id = payload.username.strip() or "default"
    user = User(
        username=payload.username,
        hashed_password=security.get_password_hash(payload.password),
        email=payload.email,
        full_name=payload.full_name,
        tenant_id=tenant_id,
        role="viewer",
        is_superuser=False,
        is_active=True,
    )
    try:
        db.add(user)
        await db.commit()
        await db.refresh(user)
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=f"Registration failed: {str(e)}") from e  # FIXED: db.commit异常保护+rollback
    await safe_auth_audit(
        db,
        action="register",
        source="register",
        operator=user.username or attempted,
        result="success",
        tenant_id=user.tenant_id or tenant_id,
        status_code=200,
        detail="ok",
        extra_summary=f"user_id={user.id}; role={user.role or 'viewer'}",
    )
    return {
        "id": user.id,
        "username": user.username,
        "tenant_id": user.tenant_id,
        "role": user.role
    }

@router.post("/login/access-token")
@limiter.limit("5/minute")
async def login_access_token(
    request: Request,
    db: AsyncSession = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends(),
    otp_code: str | None = Form(default=None),
) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests
    """
    stmt = select(User).where(User.username == form_data.username)
    result = await db.execute(stmt)
    user = result.scalars().first()
    attempted = (form_data.username or "").strip() or "unknown"

    # 账户锁定检查
    if user:
        locked_until = getattr(user, "locked_until", None)
        if locked_until:
            # FIXED: SQLite returns naive datetime; normalize before comparing
            if locked_until.tzinfo is None:
                locked_until = locked_until.replace(tzinfo=timezone.utc)
            if locked_until > datetime.now(timezone.utc):
                await safe_auth_audit(
                    db,
                    action="login",
                    source="login",
                    operator=attempted,
                    result="failed",
                    tenant_id=user.tenant_id or "default",
                    status_code=423,
                    detail="account_locked",
                )
                raise HTTPException(
                    status_code=423,
                    detail="Account locked, please try again later or contact admin",  # FIXED: 中文→英文
                    headers={"Retry-After": "1800"},
                )

    # FIXED: 增加 user 和 hashed_password 的空值保护，避免数据损坏时 TypeError
    if not user or not user.hashed_password or not security.verify_password(form_data.password, user.hashed_password):
        tid = (user.tenant_id or "default") if user else "unknown"
        await safe_auth_audit(
            db,
            action="login",
            source="login",
            operator=attempted,
            result="failed",
            tenant_id=tid,
            status_code=400,
            detail="invalid_credentials",
        )
        # 账户锁定计数：用户存在才计数
        if user:
            failed_count = int(getattr(user, "failed_login_attempts", 0) or 0) + 1
            user.failed_login_attempts = failed_count
            if failed_count >= LOGIN_MAX_FAILED_ATTEMPTS:
                user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=LOGIN_LOCKOUT_MINUTES)  # FIXED: datetime.utcnow() 已弃用(Python 3.12+) → datetime.now(timezone.utc)
                await safe_auth_audit(
                    db,
                    action="login",
                    source="login",
                    operator=attempted,
                    result="failed",
                    tenant_id=user.tenant_id or "default",
                    status_code=423,
                    detail="account_locked_after_attempts",
                )
                try:
                    await db.commit()
                except Exception:
                    await db.rollback()  # FIXED: db.commit异常保护+rollback
                raise HTTPException(
                    status_code=423,
                    detail="Too many failed login attempts, account locked for 30 minutes",  # FIXED: 中文→英文
                    headers={"Retry-After": "1800"},
                )
        raise HTTPException(status_code=400, detail="Incorrect username or password")  # FIXED: 中文→英文

    if not user.is_active:
        await safe_auth_audit(
            db,
            action="login",
            source="login",
            operator=attempted,
            result="failed",
            tenant_id=user.tenant_id or "default",
            status_code=400,
            detail="inactive",
        )
        raise HTTPException(status_code=400, detail="Account is deactivated")  # FIXED: 中文→英文

    if getattr(user, "totp_enabled", False):
        if not otp_code:
            await safe_auth_audit(
                db,
                action="login",
                source="login",
                operator=attempted,
                result="failed",
                tenant_id=user.tenant_id or "default",
                status_code=400,
                detail="otp_required",
            )
            raise HTTPException(status_code=400, detail="OTP verification code required")  # FIXED: 中文→英文
        secret = getattr(user, "totp_secret", None)
        if not secret or not verify_totp(otp_code, secret):
            await safe_auth_audit(
                db,
                action="login",
                source="login",
                operator=attempted,
                result="failed",
                tenant_id=user.tenant_id or "default",
                status_code=400,
                detail="otp_invalid",
            )
            raise HTTPException(status_code=400, detail="Invalid OTP verification code")  # FIXED: 中文→英文

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    user.last_login = datetime.now(timezone.utc)  # FIXED: datetime.utcnow() 已弃用(Python 3.12+) → datetime.now(timezone.utc)
    # 登录成功：重置锁定状态
    user.failed_login_attempts = 0
    user.locked_until = None
    try:
        await db.commit()
    except Exception:
        await db.rollback()  # FIXED: db.commit异常保护+rollback
    await safe_auth_audit(
        db,
        action="login",
        source="login",
        operator=user.username or attempted,
        result="success",
        tenant_id=user.tenant_id or "default",
        status_code=200,
        detail="ok",
    )
    access_token = security.create_access_token(
        user.id,
        expires_delta=access_token_expires,
        extra_payload={
            "tenant_id": user.tenant_id or "default",
            "role": user.role or ("owner" if user.is_superuser else "viewer"),
            "is_superuser": user.is_superuser
        }
    )
    refresh_token = security.create_refresh_token(user.id)

    trial_info = {}
    try:
        sub_stmt = select(TenantSubscription).where(
            TenantSubscription.tenant_id == (user.tenant_id or "default")
        )
        sub_result = await db.execute(sub_stmt)
        sub = sub_result.scalars().first()
        if sub and sub.status == "trial" and sub.trial_ends_at:
            trial_end = sub.trial_ends_at
            if trial_end.tzinfo is None:
                trial_end = trial_end.replace(tzinfo=timezone.utc)
            now_utc = datetime.now(timezone.utc)
            remaining = max(0, (trial_end - now_utc).days) if trial_end > now_utc else 0
            trial_info = {
                "trial_status": "expired" if trial_end <= now_utc else "active",
                "trial_ends_at": trial_end.isoformat(),
                "trial_days_remaining": remaining,
            }
    except Exception as e:
        logger.debug(f"Non-critical operation failed: {e}")  # FIXED: 硬编码中文→英文

    response_content = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "role": user.role or ("owner" if user.is_superuser else "viewer"),
        "is_superuser": user.is_superuser,
        "tenant_id": user.tenant_id or "default",
        **trial_info,
    }  # FIXED: 登录响应补充role/is_superuser/tenant_id顶层字段
    response = JSONResponse(content=response_content)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.APP_ENV == "prod",
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    return response
