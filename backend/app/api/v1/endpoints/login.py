import re
from datetime import timedelta, datetime, timezone
from typing import Any
from jwt import InvalidTokenError

# 向后兼容别名 — 真正的单一事实来源在 app.core.account_lockout 模块。
# 保留这两个常量避免破坏可能的外部引用；新代码应直接使用
# account_lockout.MAX_FAILED_ATTEMPTS / account_lockout.LOCKOUT_MINUTES。
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
from app.core.account_lockout import (
    check_lockout_status,
    record_failed_attempt,
    reset_login_failures,
    remaining_lock_seconds,
)
from app.core.totp import verify_totp
from app.services.auth_audit import safe_auth_audit
from app.api import deps  # P0-6: ws-ticket 端点需要 get_current_active_user
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
        raise HTTPException(status_code=401, detail="Authentication token not provided")  # i18n
    try:
        payload = await security.verify_token_async(token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid or expired token")  # i18n
        stmt = select(User).where(User.id == str(user_id).strip())
        result = await db.execute(stmt)
        user = result.scalars().first()
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="User account is disabled")  # i18n
        return {
            "valid": True,
            "username": user.username or "",
            "role": user.role or ("owner" if user.is_superuser else "viewer"),
            "is_superuser": user.is_superuser,
            "tenant_id": user.tenant_id or "default",
        }
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token verification failed")  # i18n


class RefreshTokenRequest(BaseModel):
    refresh_token: str


@router.post("/login/refresh-token")
async def refresh_token(
    payload: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        decoded = security.verify_token(payload.refresh_token, audience="pygbsentry:refresh")
        if decoded.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Not a refresh token")  # i18n
        user_id = decoded.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid refresh token")  # i18n
        stmt = select(User).where(User.id == str(user_id).strip())
        result = await db.execute(stmt)
        user = result.scalars().first()
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="User account is disabled")  # i18n
        new_access_token = security.create_access_token(
            subject=user.id,
            extra_payload={
                "role": user.role or ("owner" if user.is_superuser else "viewer"),
                "is_superuser": user.is_superuser,
                "tenant_id": user.tenant_id or "default",
            }
        )
        # P1-4: HttpOnly Cookie 双轨 — refresh 时同步轮转 cookie
        response = JSONResponse(content={"access_token": new_access_token, "token_type": "bearer"})
        _is_prod = (getattr(settings, "APP_ENV", "dev") or "dev").lower() in {"prod", "production"}
        response.set_cookie(
            key="access_token",
            value=new_access_token,
            httponly=True,
            secure=_is_prod,
            samesite="lax",
            max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            path="/",
        )
        return response
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Refresh token expired or invalid")  # i18n


@router.post("/login/logout")
async def logout(request: Request, response: Response) -> Any:
    response.delete_cookie(key="access_token", path="/")
    return {"detail": "Logged out"}  # i18n


@router.post("/auth/ws-ticket")
async def issue_ws_ticket_endpoint(
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """P0-6: 签发短期一次性 ws-ticket，用于 WebSocket 认证。

    消除 WebSocket URL 查询参数暴露 JWT token 的问题：
    前端通过 Authorization 头调用此端点获取 ticket，
    再用 `ws?ticket=xxx` 建立 WebSocket 连接。
    ticket 有效期 30 秒，一次性使用。
    """
    from app.core.ws_ticket import issue_ws_ticket

    payload = {
        "sub": str(current_user.id),
        "role": current_user.role or "",
        "is_superuser": bool(current_user.is_superuser),
        "tenant_id": (current_user.tenant_id or "default").strip() or "default",
        "username": current_user.username or "",
    }
    ticket, expires_in = await issue_ws_ticket(payload)
    return {"ticket": ticket, "expires_in": expires_in}


def _validate_password_strength(password: str) -> tuple[bool, str]:
    """
    验证密码强度，返回 (是否通过, 错误消息)。
    """
    # i18n+ErrorCode，支持国际化
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
            module="auth",  # FIX: [2026-07-03] 缺少必填 module 关键字参数导致 TypeError [全栈工程师]
            action="register",
            source="register",
            operator=attempted,
            result="failed",
            tenant_id="unknown",
            status_code=403,
            detail="registration_disabled",
        )
        raise HTTPException(status_code=403, detail="Registration is closed")  # i18n
    if not payload.username or len(payload.username.strip()) < 3:
        await safe_auth_audit(
            db,
            module="auth",  # FIX: [2026-07-03] 缺少必填 module 关键字参数导致 TypeError [全栈工程师]
            action="register",
            source="register",
            operator=attempted,
            result="failed",
            tenant_id="unknown",
            status_code=400,
            detail="username_too_short",
        )
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")  # i18n
    if not payload.password or len(payload.password) < 8:
        await safe_auth_audit(
            db,
            module="auth",  # FIX: [2026-07-03] 缺少必填 module 关键字参数导致 TypeError [全栈工程师]
            action="register",
            source="register",
            operator=attempted,
            result="failed",
            tenant_id=attempted,
            status_code=400,
            detail="password_too_short",
        )
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")  # i18n
    # 密码强度校验
    valid, msg = _validate_password_strength(payload.password)
    if not valid:
        await safe_auth_audit(
            db,
            module="auth",  # FIX: [2026-07-03] 缺少必填 module 关键字参数导致 TypeError [全栈工程师]
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
            module="auth",  # FIX: [2026-07-03] 缺少必填 module 关键字参数导致 TypeError [全栈工程师]
            action="register",
            source="register",
            operator=attempted,
            result="failed",
            tenant_id=attempted,
            status_code=400,
            detail="username_taken",
        )
        raise HTTPException(status_code=400, detail="Username already exists")  # i18n
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
        raise HTTPException(status_code=400, detail=f"Registration failed: {str(e)}") from e  # db.commit异常保护+rollback
    await safe_auth_audit(
        db,
        module="auth",  # FIX: [2026-07-03] 缺少必填 module 关键字参数导致 TypeError [全栈工程师]
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
@limiter.limit("10/5 minutes")
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

    # 账户锁定检查 — 使用 account_lockout 辅助函数统一处理锁定/自动解锁/计数重置
    if user:
        is_locked, was_auto_unlocked = check_lockout_status(user)
        if is_locked:
            await safe_auth_audit(
                db,
                module="auth",  # FIX: [2026-07-03] 缺少必填 module 关键字参数导致 TypeError [全栈工程师]
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
                detail="Account locked, please try again later or contact admin",  # i18n
                headers={"Retry-After": str(max(1, remaining_lock_seconds(user)))},
            )
        if was_auto_unlocked:
            # 锁定期满自动解锁 — 记录审计事件（计数已由 helper 就地重置）
            await safe_auth_audit(
                db,
                module="auth",  # FIX: [2026-07-03] 缺少必填 module 关键字参数导致 TypeError [全栈工程师]
                action="login",
                source="login",
                operator=attempted,
                tenant_id=user.tenant_id or "default",
                status_code=200,
                detail="account_auto_unlocked",
            )

    # 增加 user 和 hashed_password 的空值保护，避免数据损坏时 TypeError
    if not user or not user.hashed_password or not security.verify_password(form_data.password, user.hashed_password):
        tid = (user.tenant_id or "default") if user else "unknown"
        await safe_auth_audit(
            db,
            module="auth",  # FIX: [2026-07-03] 缺少必填 module 关键字参数导致 TypeError [全栈工程师]
            action="login",
            source="login",
            operator=attempted,
            result="failed",
            tenant_id=tid,
            status_code=400,
            detail="invalid_credentials",
        )
        # 账户锁定计数：用户存在才计数 — 使用 account_lockout 辅助函数
        if user:
            just_locked = record_failed_attempt(user)
            if just_locked:
                await safe_auth_audit(
                    db,
                    module="auth",  # FIX: [2026-07-03] 缺少必填 module 关键字参数导致 TypeError [全栈工程师]
                    action="login",
                    source="login",
                    operator=attempted,
                    result="failed",
                    tenant_id=user.tenant_id or "default",
                    status_code=423,
                    detail="account_locked_after_attempts",
                )
                # FIX: [2026-07-04] 在 commit 前缓存锁定剩余秒数，避免 commit 失败后 rollback
                # 使 user 对象过期，导致 remaining_lock_seconds(user) 触发异步懒加载异常
                # (MissingGreenlet) → HTTP 500。 [全栈工程师]
                _retry_after = str(max(1, remaining_lock_seconds(user)))
                try:
                    await db.commit()
                except Exception:
                    await db.rollback()  # db.commit异常保护+rollback
                raise HTTPException(
                    status_code=423,
                    detail="Too many failed login attempts, account locked for 30 minutes",  # i18n
                    headers={"Retry-After": _retry_after},
                )
        raise HTTPException(status_code=400, detail="Incorrect username or password")  # i18n

    if not user.is_active:
        await safe_auth_audit(
            db,
            module="auth",  # FIX: [2026-07-03] 缺少必填 module 关键字参数导致 TypeError [全栈工程师]
            action="login",
            source="login",
            operator=attempted,
            result="failed",
            tenant_id=user.tenant_id or "default",
            status_code=400,
            detail="inactive",
        )
        # SECURITY: 统一错误消息防止用户枚举 — 不暴露账户是否存在或被禁用
        raise HTTPException(status_code=400, detail="Incorrect username or password")  # i18n

    if getattr(user, "totp_enabled", False):
        if not otp_code:
            await safe_auth_audit(
                db,
                module="auth",  # FIX: [2026-07-03] 缺少必填 module 关键字参数导致 TypeError [全栈工程师]
                action="login",
                source="login",
                operator=attempted,
                result="failed",
                tenant_id=user.tenant_id or "default",
                status_code=400,
                detail="otp_required",
            )
            raise HTTPException(status_code=400, detail="OTP_REQUIRED")  # FIX: [2026-07-03] 返回机器可读 code 与前端 Login.vue 约定对齐（原返回英文字符串前端无法识别 OTP 流程） [全栈工程师]
        secret = getattr(user, "totp_secret", None)
        if secret:
            from app.core.totp import decrypt_totp_secret
            try:
                secret = decrypt_totp_secret(secret)
            except Exception:
                secret = None
        if not secret or not verify_totp(otp_code, secret):
            await safe_auth_audit(
                db,
                module="auth",  # FIX: [2026-07-03] 缺少必填 module 关键字参数导致 TypeError [全栈工程师]
                action="login",
                source="login",
                operator=attempted,
                result="failed",
                tenant_id=user.tenant_id or "default",
                status_code=400,
                detail="otp_invalid",
            )
            raise HTTPException(status_code=400, detail="OTP_INVALID")  # FIX: [2026-07-03] 前端 Login.vue 匹配 'OTP_INVALID'，原返回人类可读字符串致 OTP 错误提示不触发 [全栈工程师]

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    user.last_login = datetime.now(timezone.utc)  # datetime.utcnow() 已弃用(Python 3.12+) → datetime.now(timezone.utc)
    # 登录成功：重置锁定状态 — 使用 account_lockout 辅助函数（幂等）
    reset_login_failures(user)
    # FIXED-P0: 在 commit 前缓存 user 属性，避免 commit 后属性过期触发懒加载 MissingGreenlet
    _username = user.username
    _tenant_id = user.tenant_id or "default"
    _user_id = user.id
    _is_superuser = user.is_superuser
    _user_role = user.role
    try:
        await db.commit()
    except Exception:
        await db.rollback()  # db.commit异常保护+rollback
    await safe_auth_audit(
        db,
        module="auth",  # FIX: [2026-07-03] 缺少必填 module 关键字参数导致 TypeError [全栈工程师]
        action="login",
        source="login",
        operator=_username or attempted,
        result="success",
        tenant_id=_tenant_id,
        status_code=200,
        detail="ok",
    )
    access_token = security.create_access_token(
        _user_id,
        expires_delta=access_token_expires,
        extra_payload={
            "tenant_id": _tenant_id,
            "role": _user_role or ("owner" if _is_superuser else "viewer"),
            "is_superuser": _is_superuser
        }
    )
    refresh_token = security.create_refresh_token(_user_id)

    trial_info = {}
    try:
        sub_stmt = select(TenantSubscription).where(
            TenantSubscription.tenant_id == _tenant_id
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
        logger.warning(f"Non-critical operation failed: {e}")  # i18n

    response_content = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "role": _user_role or ("owner" if _is_superuser else "viewer"),
        "is_superuser": _is_superuser,
        "tenant_id": _tenant_id,
        **trial_info,
    }  # 登录响应补充role/is_superuser/tenant_id顶层字段
    response = JSONResponse(content=response_content)
    # P1-4: HttpOnly Cookie 双轨 — 登录时下发 HttpOnly Cookie，配合前端 Bearer token 双轨认证
    _is_prod = (getattr(settings, "APP_ENV", "dev") or "dev").lower() in {"prod", "production"}
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=_is_prod,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    return response
