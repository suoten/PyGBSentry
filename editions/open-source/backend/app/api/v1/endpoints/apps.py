"""App 端日志上报与查询（手机版/小程序崩溃、行为日志）。"""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_, func
from typing import Optional
import json

from app.db.session import get_db
from app.models.app_log import AppLog
from app.models.user import User
from app.api import deps
from app.core.plugin_manager import plugin_manager
from app.services.audit_center_service import audit_center_service
from loguru import logger

router = APIRouter()

async def _safe_audit_log(
    *,
    db: AsyncSession,
    module: str,
    action: str,
    operator: str,
    result: str,
    summary: str,
):
    try:
        await audit_center_service.log(
            db=db,
            module=module,
            action=action,
            operator=operator,
            result=result,
            summary=summary,
        )
    except Exception as e:
        logger.debug(f"操作失败,返回默认值: {e}")
        # 审计失败不应影响业务
        return


def _paid_app_log_plugins() -> set[str]:
    # 纯开源版无“付费插件”，直接返回空集合
    return set()

def _can_verify_purchases() -> bool:
    # 纯开源版本地不与服务器做在线鉴权
    return False

async def _fetch_purchased_plugin_ids(request: Request, current_user: User) -> set[str]:
    """开源版本地无在线购买，返回空"""
    return set()


class AppLogCreate(BaseModel):
    plugin_id: str = "mobile_app_suite"   # mobile_app_suite | mini_program_suite
    app_version: str = ""
    platform: str = ""                    # android | ios | miniprogram
    log_type: str = "behavior"            # crash | behavior
    message: Optional[str] = None
    extra: Optional[str] = None


@router.post("/logs")
async def create_app_log(
    payload: AppLogCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    接收 App 端上报的崩溃/行为日志（无需登录，供手机版、小程序调用）。
    """
    plugin_id = (payload.plugin_id or "").strip() or "mobile_app_suite"
    if plugin_id not in ("mobile_app_suite", "mini_program_suite"):
        plugin_id = "mobile_app_suite"
    platform = (payload.platform or "").strip() or "unknown"
    log_type = (payload.log_type or "").strip() or "behavior"
    if log_type not in ("crash", "behavior"):
        log_type = "behavior"
    msg = (payload.message or "")[:2000] if payload.message else None
    extra = (payload.extra or "")[:4000] if payload.extra else None

    row = AppLog(
        tenant_id="default",
        plugin_id=plugin_id,
        app_version=(payload.app_version or "")[:32],
        platform=platform[:32],
        log_type=log_type,
        message=msg,
        extra=extra,
    )
    db.add(row)
    await db.commit()
    return {"ok": True, "id": row.id}


@router.get("/logs")
async def list_app_logs(
    request: Request,
    plugin_id: Optional[str] = None,
    platform: Optional[str] = None,
    log_type: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    skip: int = Query(0, ge=0),  # FIXED: 添加Query约束
    limit: int = Query(50, ge=1, le=10000),  # FIXED: 添加Query约束
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    查询 App 日志（需登录，支持按应用/版本/平台/类型/时间筛选）。
    """
    limit = max(1, min(limit or 50, 200))
    skip = max(0, skip or 0)
    now = datetime.now(timezone.utc)
    end_time = end_time or now
    start_time = start_time or (end_time - timedelta(days=7))
    if start_time > end_time:
        raise HTTPException(status_code=400, detail="start_time cannot be greater than end_time")
    if (end_time - start_time) > timedelta(days=30):
        raise HTTPException(status_code=400, detail="Time range must be within 30 days")

    conditions = [
        AppLog.created_at >= start_time,
        AppLog.created_at <= end_time,
    ]
    if not current_user.is_superuser:
        conditions.append(AppLog.tenant_id == (current_user.tenant_id or "default"))

    # 付费插件门控：未购买不应查看 App 日志
    if not current_user.is_superuser:
        if _can_verify_purchases():
            purchased_ids = await _fetch_purchased_plugin_ids(request, current_user)
            paid_plugins = _paid_app_log_plugins()
            if plugin_id:
                plugin_id = plugin_id.strip()
                if plugin_id in paid_plugins and plugin_id not in purchased_ids:
                    await _safe_audit_log(
                        db=db,
                        module="apps",
                        action="app_logs_list",
                        operator=current_user.username or "unknown",
                        result="failed",
                        summary=(
                            f"plugin_id={plugin_id}; "
                            f"tenant_id={current_user.tenant_id or 'default'}; "
                            f"source=app_logs; "
                            f"status_code=403; "
                            f"detail=not_purchased"
                        ),
                    )
                    raise HTTPException(status_code=403, detail="App log feature requires purchase/authorization to view")
            else:
                # 未指定 plugin_id 时：仅展示已购买的付费插件日志
                allowed = paid_plugins.intersection(purchased_ids)
                if allowed:
                    conditions.append(AppLog.plugin_id.in_(list(allowed)))
                else:
                    # plugin_id 未指定但用户未购买任何付费 App 日志能力：
                    # 为了让审计中心的 plugin_id 过滤可命中，这里为每个付费能力都写一条 403。
                    for denied_plugin_id in paid_plugins:
                        await _safe_audit_log(
                            db=db,
                            module="apps",
                            action="app_logs_list",
                            operator=current_user.username or "unknown",
                            result="failed",
                            summary=(
                                f"plugin_id={denied_plugin_id}; "
                                f"tenant_id={current_user.tenant_id or 'default'}; "
                                f"source=app_logs; "
                                f"status_code=403; "
                                f"detail=not_purchased"
                            ),
                        )
                    return {"items": [], "total": 0, "skip": skip, "limit": limit}
    if plugin_id:
        conditions.append(AppLog.plugin_id == plugin_id)
    if platform:
        conditions.append(AppLog.platform == platform)
    if log_type:
        conditions.append(AppLog.log_type == log_type)

    count_stmt = select(func.count()).select_from(AppLog).where(and_(*conditions))
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(AppLog)
        .where(and_(*conditions))
        .order_by(desc(AppLog.created_at))
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    await _safe_audit_log(
        db=db,
        module="apps",
        action="app_logs_list",
        operator=current_user.username or "unknown",
        result="success",
        summary=(
            f"plugin_id={(plugin_id or '').strip()}; "
            f"tenant_id={current_user.tenant_id or 'default'}; "
            f"source=app_logs; "
            f"status_code=200; "
            f"platform={(platform or '').strip()}; "
            f"log_type={(log_type or '').strip()}; "
            f"skip={skip}; limit={limit}; total={int(total)}"
        ),
    )
    items = [
        {
            "id": r.id,
            "tenant_id": r.tenant_id,
            "plugin_id": r.plugin_id,
            "app_version": r.app_version,
            "platform": r.platform,
            "log_type": r.log_type,
            "message": r.message,
            "extra": r.extra,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.get("/stats")
async def app_log_stats(
    request: Request,
    plugin_id: Optional[str] = None,
    days: int = Query(1, ge=1, le=365),  # FIXED: 添加Query约束
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    days = max(1, min(days or 1, 30))
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(days=days)
    conditions = [AppLog.created_at >= start_time, AppLog.created_at <= now]
    if not current_user.is_superuser:
        conditions.append(AppLog.tenant_id == (current_user.tenant_id or "default"))

    # 付费插件门控
    if not current_user.is_superuser:
        if _can_verify_purchases():
            purchased_ids = await _fetch_purchased_plugin_ids(request, current_user)
            paid_plugins = _paid_app_log_plugins()
            if plugin_id:
                plugin_id = plugin_id.strip()
                if plugin_id in paid_plugins and plugin_id not in purchased_ids:
                    await _safe_audit_log(
                        db=db,
                        module="apps",
                        action="app_logs_stats",
                        operator=current_user.username or "unknown",
                        result="failed",
                        summary=(
                            f"plugin_id={plugin_id}; "
                            f"tenant_id={current_user.tenant_id or 'default'}; "
                            f"source=app_logs; "
                            f"status_code=403; "
                            f"detail=not_purchased"
                        ),
                    )
                    raise HTTPException(status_code=403, detail="App log feature requires purchase/authorization to view")
            else:
                allowed = paid_plugins.intersection(purchased_ids)
                if allowed:
                    conditions.append(AppLog.plugin_id.in_(list(allowed)))
                else:
                    # plugin_id 未指定但用户未购买任何付费 App 日志能力：
                    # 为了让审计中心的 plugin_id 过滤可命中，这里为每个付费能力都写一条 403。
                    for denied_plugin_id in paid_plugins:
                        await _safe_audit_log(
                            db=db,
                            module="apps",
                            action="app_logs_stats",
                            operator=current_user.username or "unknown",
                            result="failed",
                            summary=(
                                f"plugin_id={denied_plugin_id}; "
                                f"tenant_id={current_user.tenant_id or 'default'}; "
                                f"source=app_logs; "
                                f"status_code=403; "
                                f"detail=not_purchased"
                            ),
                        )
                    # 没有已购买的付费插件：返回空统计
                    return {"days": days, "total": 0, "crash_total": 0, "grouped": []}

    if plugin_id:
        conditions.append(AppLog.plugin_id == plugin_id)
    total = (
        await db.execute(
            select(func.count()).select_from(AppLog).where(and_(*conditions))
        )
    ).scalar() or 0
    crash_total = (
        await db.execute(
            select(func.count()).select_from(AppLog).where(and_(*(conditions + [AppLog.log_type == "crash"])))
        )
    ).scalar() or 0
    group_stmt = (
        select(AppLog.plugin_id, AppLog.platform, AppLog.log_type, func.count(AppLog.id))
        .where(and_(*conditions))
        .group_by(AppLog.plugin_id, AppLog.platform, AppLog.log_type)
        .order_by(desc(func.count(AppLog.id)))
    )
    grouped = (await db.execute(group_stmt)).all()
    await _safe_audit_log(
        db=db,
        module="apps",
        action="app_logs_stats",
        operator=current_user.username or "unknown",
        result="success",
        summary=(
            f"plugin_id={(plugin_id or '').strip()}; "
            f"tenant_id={current_user.tenant_id or 'default'}; "
            f"source=app_logs; "
            f"status_code=200; "
            f"days={int(days)}; "
            f"total={int(total)}; crash_total={int(crash_total)}"
        ),
    )
    return {
        "days": days,
        "total": int(total),
        "crash_total": int(crash_total),
        "grouped": [
            {
                "plugin_id": r[0] or "",
                "platform": r[1] or "",
                "log_type": r[2] or "",
                "count": int(r[3] or 0),
            }
            for r in grouped
        ],
    }


@router.get("/remote-config")
async def app_remote_config(
    plugin_id: str,
    app_version: str = "",
):
    if plugin_id not in ("mobile_app_suite", "mini_program_suite"):
        return {"plugin_id": plugin_id, "config": {}}
    meta = plugin_manager.metadata.get(plugin_id) or {}
    cfg = meta.get("config_template") or {}
    raw = cfg.get("remote_config_json") or "{}"
    parsed = {}
    if isinstance(raw, dict):
        parsed = raw
    elif isinstance(raw, str):
        try:
            loaded = json.loads(raw)
            if isinstance(loaded, dict):
                parsed = loaded
        except Exception as e:
            logger.debug(f"操作失败,返回默认值: {e}")
            parsed = {}
    return {
        "plugin_id": plugin_id,
        "app_version": app_version,
        "config": parsed,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
