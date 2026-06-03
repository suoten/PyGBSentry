from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.api import deps
from app.db.session import get_db
from app.models.user import User
from app.schemas.audit_center import AuditLogListResponse, AuditStatsResponse
from app.services.audit_center_service import audit_center_service

router = APIRouter()


@router.get("/logs", response_model=AuditLogListResponse)
async def list_logs(
    module: str | None = Query(default=None),
    action: str | None = Query(default=None),
    action_prefix: str | None = Query(default=None),
    operator: str | None = Query(default=None),
    result: str | None = Query(default=None),
    plugin_id: str | None = Query(default=None),
    source: str | None = Query(default=None),
    tenant_id: str | None = Query(default=None),
    status_code: int | None = Query(default=None),
    status_family: int | None = Query(default=None, ge=1, le=5),
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    return await audit_center_service.list_logs(
        db=db,
        module=module,
        action=action,
        action_prefix=action_prefix,
        operator=operator,
        result=result,
        plugin_id=plugin_id,
        source=source,
        tenant_id=tenant_id,
        status_code=status_code,
        status_family=status_family,
        start_at=start_at,
        end_at=end_at,
        page=page,
        page_size=page_size,
    )


@router.get("/export.csv")
async def export_audit_csv(
    module: str | None = Query(default=None),
    action: str | None = Query(default=None),
    action_prefix: str | None = Query(default=None),
    operator: str | None = Query(default=None),
    result: str | None = Query(default=None),
    plugin_id: str | None = Query(default=None),
    source: str | None = Query(default=None),
    tenant_id: str | None = Query(default=None),
    status_code: int | None = Query(default=None),
    status_family: int | None = Query(default=None, ge=1, le=5),
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    """导出审计日志为 CSV，使用与列表相同的筛选条件。"""
    csv_content = await audit_center_service.export_csv(
        db=db,
        module=module,
        action=action,
        action_prefix=action_prefix,
        operator=operator,
        result=result,
        plugin_id=plugin_id,
        source=source,
        tenant_id=tenant_id,
        status_code=status_code,
        status_family=status_family,
        start_at=start_at,
        end_at=end_at,
    )
    filename = f"audit-logs-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.csv"
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/stats", response_model=AuditStatsResponse)
async def get_audit_stats(
    module: str | None = Query(default=None),
    action: str | None = Query(default=None),
    action_prefix: str | None = Query(default=None),
    operator: str | None = Query(default=None),
    result: str | None = Query(default=None),
    plugin_id: str | None = Query(default=None),
    source: str | None = Query(default=None),
    tenant_id: str | None = Query(default=None),
    status_code: int | None = Query(default=None),
    status_family: int | None = Query(default=None, ge=1, le=5),
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    return await audit_center_service.get_stats(
        db=db,
        module=module,
        action=action,
        action_prefix=action_prefix,
        operator=operator,
        result=result,
        plugin_id=plugin_id,
        source=source,
        tenant_id=tenant_id,
        status_code=status_code,
        status_family=status_family,
        start_at=start_at,
        end_at=end_at,
    )
