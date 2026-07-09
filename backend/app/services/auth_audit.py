"""Safe authentication audit helper.

Wraps :class:`app.models.operation_audit.OperationAudit` writes so that
authentication/authorization events (login success/failure, API key use, RBAC
denials, rate-limit hits) are recorded for compliance (等保 2.0 三级审计要求)
without ever raising — an audit-logging failure must not break the auth flow.

Used pervasively by ``api/deps.py``, ``core/ratelimit.py`` and most endpoint
modules. Every call writes at most one row; all DB errors are caught and logged.
"""
from __future__ import annotations

from typing import Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.operation_audit import OperationAudit


async def safe_auth_audit(
    db: AsyncSession,
    *,
    module: str,
    action: str,
    source: str = "unknown",
    operator: str = "unknown",
    result: str = "success",
    tenant_id: Optional[str] = None,
    status_code: Optional[int] = None,
    detail: Optional[str] = None,
    extra_summary: Optional[str] = None,
) -> None:
    """Persist a single operation-audit row, swallowing all errors.

    ``status_code`` and ``detail``/``extra_summary`` are folded into the
    ``summary`` text field (the OperationAudit model stores a single summary
    column). The write is best-effort: any DB error is logged at WARNING.

    FIX: [2026-07-04] 原实现直接在调用方的 ``db`` session 上执行 ``commit()``/``rollback()``。
    并发场景下 SQLite "database is locked" 导致 ``commit()`` 失败后 ``rollback()``
    会使调用方 session 中所有 ORM 对象过期（expire），后续属性访问触发异步懒加载
    异常（MissingGreenlet）→ HTTP 500。根因：审计日志写入与业务操作共用同一 session，
    审计 rollback 污染了业务 session 的对象状态。修复：使用独立 session 写入审计日志。
    [全栈工程师]
    """
    # db 参数保留用于向后兼容，但实际写入使用独立 session
    del db  # 显式标记不使用

    summary_parts: list[str] = []
    if status_code is not None:
        summary_parts.append(f"status={status_code}")
    if source:
        summary_parts.append(f"source={source}")
    if detail:
        summary_parts.append(f"detail={detail}")
    if extra_summary:
        summary_parts.append(extra_summary)
    summary = " ".join(summary_parts)

    try:
        # FIX: [2026-07-04] 使用独立 session 写入审计日志，避免 commit/rollback
        # 污染调用方 session 中的 ORM 对象状态。 [全栈工程师]
        from app.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as audit_db:
            row = OperationAudit(
                module=str(module or "unknown")[:64],
                action=str(action or "unknown")[:64],
                operator=str(operator or "unknown")[:64],
                result=str(result or "success")[:24],
                summary=summary,
                tenant_id=str(tenant_id) if tenant_id is not None else None,
            )
            audit_db.add(row)
            await audit_db.commit()
    except Exception as e:
        logger.warning(f"safe_auth_audit: failed to persist audit row ({e}); module={module} action={action}")
