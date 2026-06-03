from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from loguru import logger
import jwt
from jwt import InvalidTokenError as JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.db.session import get_db
from app.models.user import User
from app.models.user_api_key import UserApiKey
from app.core import security
from app.core.api_key import parse_api_key, hash_api_key, secure_compare
from app.core.config import settings
from datetime import datetime, timezone

from app.services.auth_audit import safe_auth_audit


def get_or_404(result, detail: str = "Resource not found"):
    """# FIXED: ORM查询结果空值判断辅助函数"""
    obj = result.scalars().first() if hasattr(result, 'scalars') else result
    if obj is None:
        raise HTTPException(status_code=404, detail=detail)
    return obj

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/login/access-token", auto_error=False)

async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    token: str | None = Depends(oauth2_scheme),
) -> User:
    if not token:
        # FIXED: 空 token 应直接抛 401，原 pass 逻辑导致后续用空字符串继续校验
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated or session expired, please login again",
            headers={"WWW-Authenticate": "Bearer"},
        )
    bearer_token = (token or "").strip()

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated or session expired, please login again",  # FIXED: 中文错误消息→英文
        headers={"WWW-Authenticate": "Bearer"},
    )
    if bearer_token:
        try:
            payload = jwt.decode(
                bearer_token, settings.SECRET_KEY, algorithms=[security.ALGORITHM],
                # FIXED: enabled audience verification to prevent token type confusion
                audience="pygbsentry:access"
            )
            user_id = payload.get("sub")
            if user_id is None or str(user_id).strip() == "":
                await safe_auth_audit(
                    db,
                    module="auth",
                    action="jwt_auth",
                    source="bearer",
                    operator="unknown",
                    result="failed",
                    tenant_id="unknown",
                    status_code=401,
                    detail="missing_sub",
                )
                raise credentials_exception
            user_id = str(user_id).strip()
        except JWTError:
            await safe_auth_audit(
                db,
                module="auth",
                action="jwt_auth",
                source="bearer",
                operator="unknown",
                result="failed",
                tenant_id="unknown",
                status_code=401,
                detail="invalid_or_expired",
            )
            raise credentials_exception

        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalars().first()

        if user is None:
            await safe_auth_audit(
                db,
                module="auth",
                action="jwt_auth",
                source="bearer",
                operator="unknown",
                result="failed",
                tenant_id="unknown",
                status_code=401,
                detail="user_not_found",
                extra_summary=f"user_id={user_id}",
            )
            raise credentials_exception
        # Always use tenant_id and role from database, not from JWT payload.
        # This ensures that role/tenant changes take effect immediately
        # instead of being overridden by stale JWT claims.
        return user

    api_key_value = (request.headers.get("x-api-key") or request.headers.get("X-API-Key") or "").strip()
    if not api_key_value:
        raise credentials_exception

    parsed = parse_api_key(api_key_value)
    if not parsed:
        await safe_auth_audit(
            db,
            module="auth",
            action="api_key_auth",
            source="api_key",
            operator="unknown",
            result="failed",
            tenant_id="unknown",
            status_code=401,
            detail="malformed",
        )
        raise credentials_exception
    prefix, raw = parsed
    key_hash = hash_api_key(raw, settings.SECRET_KEY)

    stmt = select(UserApiKey).where(
        UserApiKey.key_prefix == prefix,
        UserApiKey.is_active == True,
        UserApiKey.revoked_at.is_(None),
    )
    result = await db.execute(stmt)
    candidates = result.scalars().all()
    matched: UserApiKey | None = None
    for item in candidates:
        if secure_compare(item.hashed_key, key_hash):
            matched = item
            break
    if not matched:
        await safe_auth_audit(
            db,
            module="auth",
            action="api_key_auth",
            source="api_key",
            operator="unknown",
            result="failed",
            tenant_id="unknown",
            status_code=401,
            detail="invalid_or_revoked",
            extra_summary=f"key_prefix={prefix}",
        )
        raise credentials_exception
    if matched.expires_at is not None:
        try:
            now = datetime.now(timezone.utc)
            expires_at = matched.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= now:
                await safe_auth_audit(
                    db,
                    module="auth",
                    action="api_key_auth",
                    source="api_key",
                    operator="unknown",
                    result="failed",
                    tenant_id=(matched.tenant_id or "default").strip() or "default",
                    status_code=401,
                    detail="expired",
                    extra_summary=f"key_id={matched.id}; key_prefix={matched.key_prefix}",
                )
                raise credentials_exception
        except HTTPException:
            raise
        except (ValueError, TypeError, AttributeError) as exc:
            logger.warning("API Key validation error: {}", exc)

    user_stmt = select(User).where(User.id == matched.user_id)
    user_result = await db.execute(user_stmt)
    user = user_result.scalars().first()
    if not user or not user.is_active:
        tid = (matched.tenant_id or "default").strip() or "default"
        detail = "subject_inactive" if user and not user.is_active else "subject_missing"
        await safe_auth_audit(
            db,
            module="auth",
            action="api_key_auth",
            source="api_key",
            operator=(user.username if user else None) or "unknown",
            result="failed",
            tenant_id=tid,
            status_code=401,
            detail=detail,
            extra_summary=(
                f"key_id={matched.id}; key_prefix={matched.key_prefix}; "
                f"subject_user_id={matched.user_id}"
            ),
        )
        raise credentials_exception
    if matched.tenant_id:
        user.tenant_id = matched.tenant_id

    try:
        await db.execute(
            update(UserApiKey)
            .where(UserApiKey.id == matched.id)
            .values(last_used_at=datetime.now(timezone.utc))
        )
        await db.commit()
    except Exception:
        await db.rollback()

    return user

async def get_current_active_user(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not current_user.is_active:
        tid = (current_user.tenant_id or "default").strip() or "default"
        await safe_auth_audit(
            db,
            module="auth",
            action="jwt_auth",
            source="bearer",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=tid,
            status_code=400,
            detail="inactive_user",
            extra_summary=f"user_id={current_user.id}",
        )
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

async def get_current_active_superuser(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not current_user.is_superuser:
        tid = (current_user.tenant_id or "default").strip() or "default"
        r = (current_user.role or "").strip()
        await safe_auth_audit(
            db,
            module="auth",
            action="superuser_required",
            source="rbac",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=tid,
            status_code=400,
            detail="not_superuser",
            extra_summary=f"user_id={current_user.id}; role={r}",
        )
        raise HTTPException(
            status_code=400, detail="The user doesn't have enough privileges"
        )
    return current_user

def require_roles(allowed_roles: list[str]):
    normalized_allowed = [item.lower() for item in allowed_roles]

    async def _checker(
        request: Request,
        current_user: User = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        if current_user.is_superuser:
            return current_user
        role = (current_user.role or "").lower()
        if role not in normalized_allowed:
            if settings.AUDIT_RBAC_ROLE_DENIALS:
                tid = (current_user.tenant_id or "default").strip() or "default"
                roles_csv = ",".join(sorted(set(normalized_allowed)))
                path = (request.url.path or "")[:220]
                await safe_auth_audit(
                    db,
                    module="auth",
                    action="role_required",
                    source="rbac",
                    operator=current_user.username or "unknown",
                    result="failed",
                    tenant_id=tid,
                    status_code=403,
                    detail="role_denied",
                    extra_summary=(
                        f"user_role={role}; allowed_roles={roles_csv}; path={path}"
                    ),
                )
            raise HTTPException(
                status_code=403, detail="Permission denied"
            )
        return current_user
    return _checker

async def require_server_edition() -> None:
    if (settings.APP_EDITION or "oss").lower() != "server":
        raise HTTPException(status_code=403, detail="This feature requires the server edition")
