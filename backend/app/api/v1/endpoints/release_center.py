import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.api import deps
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.release_center import DiffResponse, PublishRequest, PublishResponse, RollbackRequest, RollbackResponse
from app.services.release_center_service import release_center_service
from app.services.auth_audit import safe_auth_audit

router = APIRouter()


def _audit_tid(user: User) -> str:
    return (user.tenant_id or "default").strip() or "default"


@router.get("/drafts/{draft_id}/diff", response_model=DiffResponse)
async def get_diff(
    draft_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    return await release_center_service.get_diff(db, draft_id)


@router.post("/publish", response_model=PublishResponse)
async def publish_draft(
    payload: PublishRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    # 凭证痕迹 — confirm_token 从环境变量读取而非硬编码
    _expected_token = settings.RELEASE_CONFIRM_TOKEN or os.environ.get("RELEASE_CONFIRM_TOKEN", "")
    # FIX [2026-09-19 P2]: 未配置 RELEASE_CONFIRM_TOKEN 时报错只说 "confirm_token invalid"，
    # 用户无从得知需要在服务器配置环境变量。区分两种失败并给出可行动的提示。
    if not _expected_token:
        await safe_auth_audit(
            db,
            module="release-center",
            action="publish",
            source="release_center",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="confirm_token_not_configured",
            extra_summary=f"draft_id={payload.draft_id}",
        )
        raise HTTPException(
            status_code=400,
            detail="发布确认令牌未配置：请在服务器环境变量 RELEASE_CONFIRM_TOKEN 中设置后重启服务，再输入该令牌发布",
        )
    if payload.confirm_token != _expected_token:
        await safe_auth_audit(
            db,
            module="release-center",
            action="publish",
            source="release_center",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="invalid_confirm_token",
            extra_summary=f"draft_id={payload.draft_id}",
        )
        raise HTTPException(status_code=400, detail="confirm_token invalid")
    try:
        return await release_center_service.publish(
            db=db,
            draft_id=payload.draft_id,
            operator=current_user.username,
            note=payload.publish_note,
        )
    except ValueError as e:
        await safe_auth_audit(
            db,
            module="release-center",
            action="publish",
            source="release_center",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="publish_rejected",
            extra_summary=f"draft_id={payload.draft_id}; message={str(e)[:200]}",
        )
        raise HTTPException(status_code=400, detail=str(e))


# 补充 response_model=RollbackResponse，使接口返回类型明确
@router.post("/rollback", response_model=RollbackResponse)
async def rollback_revision(
    payload: RollbackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    try:
        return await release_center_service.rollback(
            db=db,
            target_revision=payload.target_revision,
            operator=current_user.username,
            reason=payload.reason,
        )
    except ValueError as e:
        await safe_auth_audit(
            db,
            module="release-center",
            action="rollback",
            source="release_center",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="rollback_rejected",
            extra_summary=f"target_revision={payload.target_revision}; message={str(e)[:200]}",
        )
        raise HTTPException(status_code=400, detail=str(e))
