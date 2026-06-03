import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.db.session import get_db
from app.api import deps
from app.models.user import User
from app.models.user_api_key import UserApiKey
from app.core.api_key import generate_api_key, hash_api_key
from app.core.config import settings
from app.core.ratelimit import limiter
from app.services.auth_audit import safe_auth_audit

router = APIRouter()


class ApiKeyCreateRequest(BaseModel):
    name: str
    user_id: str | None = None
    tenant_id: str | None = None
    expires_at: str | None = None
    allowed_scopes: list[str] | None = None


def _audit_tid(user: User) -> str:
    return (user.tenant_id or "default").strip() or "default"


def _normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            s = str(item or "").strip()
            if s:
                out.append(s)
        return out
    s = str(value or "").strip()
    return [s] if s else []


@router.get("/me")
async def list_my_api_keys(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    stmt = (
        select(UserApiKey)
        .where(UserApiKey.user_id == current_user.id, UserApiKey.tenant_id == current_user.tenant_id)
        .order_by(UserApiKey.created_at.desc())
    )
    result = await db.execute(stmt)
    items = result.scalars().all()
    data = []
    for k in items:
        try:
            scopes = json.loads(k.scopes or "[]")
        except Exception:
            scopes = []
        data.append(
            {
                "id": k.id,
                "name": k.name,
                "tenant_id": k.tenant_id,
                "user_id": k.user_id,
                "key_prefix": k.key_prefix,
                "scopes": scopes if isinstance(scopes, list) else [],
                "expires_at": k.expires_at,
                "is_active": bool(k.is_active) and k.revoked_at is None,
                "revoked_at": k.revoked_at,
                "last_used_at": k.last_used_at,
                "created_at": k.created_at,
            }
        )
    return data


@router.post("")
@limiter.limit("10/minute")
async def create_api_key(
    payload: ApiKeyCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    name = (payload.name or "").strip()
    if not name:
        await safe_auth_audit(
            db,
            module="users",
            action="api_key_create",
            source="api_key",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="name_required",
        )
        raise HTTPException(status_code=400, detail="name is required")
    user_id = (payload.user_id or "").strip() or current_user.id
    tenant_id = (payload.tenant_id or "").strip() or current_user.tenant_id
    if (user_id != current_user.id or tenant_id != current_user.tenant_id) and not (
        current_user.is_superuser or (current_user.role or "").lower() in {"owner", "admin"}
    ):
        await safe_auth_audit(
            db,
            module="users",
            action="api_key_create",
            source="api_key",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=403,
            detail="permission_denied",
            extra_summary=f"subject_user_id={user_id}; tenant_id={tenant_id}",
        )
        raise HTTPException(status_code=403, detail="Permission denied")

    scopes = _normalize_list(payload.allowed_scopes)
    allowed_ips = _normalize_list(getattr(payload, 'allowed_ips', None))
    expires_at = payload.expires_at
    expires_dt = None
    if expires_at:
        try:
            expires_dt = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        except Exception:
            await safe_auth_audit(
                db,
                module="users",
                action="api_key_create",
                source="api_key",
                operator=current_user.username or "unknown",
                result="failed",
                tenant_id=_audit_tid(current_user),
                status_code=400,
                detail="invalid_expires_at",
                extra_summary=f"subject_user_id={user_id}",
            )
            raise HTTPException(status_code=400, detail="expires_at must be ISO datetime")

    full_key, prefix = generate_api_key()
    _, raw = full_key.split(".", 1)
    key_hash = hash_api_key(raw, settings.SECRET_KEY)
    record = UserApiKey(
        tenant_id=tenant_id,
        user_id=user_id,
        name=name,
        key_prefix=prefix,
        hashed_key=key_hash,
        scopes=json.dumps(scopes, ensure_ascii=False),
        allowed_ips=json.dumps(allowed_ips, ensure_ascii=False),
        expires_at=expires_dt,
        is_active=True,
    )
    db.add(record)
    await db.commit()

    await safe_auth_audit(
        db,
        module="users",
        action="api_key_create",
        source="api_key",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=(
            f"key_id={record.id}; key_prefix={record.key_prefix}; "
            f"subject_user_id={user_id}"
        ),
    )

    return {
        "id": record.id,
        "name": record.name,
        "tenant_id": record.tenant_id,
        "user_id": record.user_id,
        "key_prefix": record.key_prefix,
        "scopes": scopes,
        "expires_at": record.expires_at,
        "created_at": record.created_at,
        "api_key": full_key,
        "header_name": "X-API-Key",
    }


@router.post("/{key_id}/revoke")
async def revoke_api_key(
    key_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    stmt = select(UserApiKey).where(UserApiKey.id == key_id)
    result = await db.execute(stmt)
    record = result.scalars().first()
    if not record:
        await safe_auth_audit(
            db,
            module="users",
            action="api_key_revoke",
            source="api_key",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="key_not_found",
            extra_summary=f"key_id={key_id}",
        )
        raise HTTPException(status_code=404, detail="API key not found")
    if record.tenant_id != current_user.tenant_id:
        await safe_auth_audit(
            db,
            module="users",
            action="api_key_revoke",
            source="api_key",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=403,
            detail="tenant_mismatch",
            extra_summary=f"key_id={key_id}; key_tenant_id={record.tenant_id}",
        )
        raise HTTPException(status_code=403, detail="Permission denied")
    if record.user_id != current_user.id and not (
        current_user.is_superuser or (current_user.role or "").lower() in {"owner", "admin"}
    ):
        await safe_auth_audit(
            db,
            module="users",
            action="api_key_revoke",
            source="api_key",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=403,
            detail="permission_denied",
            extra_summary=(
                f"key_id={key_id}; subject_user_id={record.user_id}; "
                f"key_prefix={record.key_prefix}"
            ),
        )
        raise HTTPException(status_code=403, detail="Permission denied")

    await db.execute(
        update(UserApiKey)
        .where(UserApiKey.id == key_id)
        .values(is_active=False, revoked_at=datetime.now(timezone.utc))
    )
    await db.commit()
    await safe_auth_audit(
        db,
        module="users",
        action="api_key_revoke",
        source="api_key",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=(
            f"key_id={key_id}; key_prefix={record.key_prefix}; "
            f"subject_user_id={record.user_id}"
        ),
    )
    return {"ok": True}

