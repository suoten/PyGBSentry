"""认证与用户管理等审计写入（失败不阻断业务）。"""
from sqlalchemy.ext.asyncio import AsyncSession  # TECH_DEBT: 直接依赖具体实现，未来改为Protocol接口注入

from app.services.audit_center_service import audit_center_service
from loguru import logger


async def safe_auth_audit(
    db: AsyncSession,
    *,
    module: str = "auth",
    action: str,
    source: str,
    operator: str,
    result: str,
    tenant_id: str,
    status_code: int,
    detail: str,
    extra_summary: str = "",
) -> None:
    try:
        tail = f"; {extra_summary.strip()}" if extra_summary.strip() else ""
        await audit_center_service.log(
            db=db,
            module=(module or "auth").strip() or "auth",
            action=action,
            operator=(operator or "unknown").strip() or "unknown",
            result=result,
            summary=(
                f"tenant_id={tenant_id}; "
                f"source={source}; "
                f"status_code={status_code}; "
                f"detail={detail}"
                f"{tail}"
            ),
        )
    except Exception as e:
        logger.warning(f"Error: {e}")
