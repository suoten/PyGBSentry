"""录像计划 API：按通道配置定时/移动侦测/报警联动/手动录像策略；录像存储配置。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from app.db.session import get_db
from app.models.record_schedule import RecordSchedule
from app.models.record_schedule_runtime import RecordScheduleRuntime
from app.models.resource import Resource
from app.models.asset import Asset
from app.models.system_setting import SystemSetting
from app.api import deps
from app.models.user import User
import json
from datetime import datetime, timezone, timedelta
from app.core.http_client import get_http_client
import httpx
from app.core.config import settings
from app.core.media_nodes_db import get_active_media_node_id, get_db_media_node_by_id, select_best_db_node
from app.services.auth_audit import safe_auth_audit
from loguru import logger

router = APIRouter()


def _audit_tid(user: User) -> str:
    return (user.tenant_id or "default").strip() or "default"

RECORD_STORAGE_ROOT_KEY = "record_storage_root"
RECORD_STORAGE_NODES_KEY = "record_storage_nodes"


class RecordScheduleCreate(BaseModel):
    resource_id: str
    plan_type: str = "timed"  # timed | motion | alarm | manual
    enabled: bool = True
    time_ranges: List[dict] = []  # [{"start":"00:00","end":"23:59","days":[0,1,...,6]}]
    priority: int = 0


class RecordScheduleUpdate(BaseModel):
    plan_type: Optional[str] = None
    enabled: Optional[bool] = None
    time_ranges: Optional[List[dict]] = None
    priority: Optional[int] = None


@router.get("")
async def list_schedules(
    resource_id: Optional[str] = None,
    plan_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """查询录像计划列表，可按通道、类型筛选。"""
    stmt = select(RecordSchedule)
    if resource_id:
        stmt = stmt.where(RecordSchedule.resource_id == resource_id)
    if plan_type:
        stmt = stmt.where(RecordSchedule.plan_type == plan_type)
    if not current_user.is_superuser:
        stmt = stmt.join(Resource, Resource.id == RecordSchedule.resource_id).join(
            Asset, Asset.id == Resource.asset_id
        ).where(Asset.tenant_id == (current_user.tenant_id or "default"))
    result = await db.execute(stmt.order_by(RecordSchedule.priority.desc(), RecordSchedule.created_at.desc()))
    rows = result.scalars().all()
    out = []
    for r in rows:
        try:
            tr = json.loads(r.time_ranges) if r.time_ranges else []
        except Exception:
            tr = []
        out.append({
            "id": r.id,
            "resource_id": r.resource_id,
            "plan_type": r.plan_type,
            "enabled": r.enabled,
            "time_ranges": tr,
            "priority": r.priority,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        })
    return out


@router.post("", status_code=201)
async def create_schedule(
    payload: RecordScheduleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """新建录像计划。"""
    stmt = select(Resource).where(Resource.id == payload.resource_id)
    if not current_user.is_superuser:
        stmt = stmt.join(Asset, Asset.id == Resource.asset_id).where(
            Asset.tenant_id == (current_user.tenant_id or "default")
        )
    res = (await db.execute(stmt)).scalars().first()
    if not res:
        await safe_auth_audit(
            db,
            module="record_schedule",
            action="create_schedule",
            source="record_schedule_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="resource_not_found",
            extra_summary=f"resource_id={payload.resource_id}",
        )
        raise HTTPException(status_code=404, detail="Channel not found")
    plan = RecordSchedule(
        resource_id=payload.resource_id,
        plan_type=payload.plan_type or "timed",
        enabled=payload.enabled,
        time_ranges=json.dumps(payload.time_ranges or []),
        priority=payload.priority,
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    await safe_auth_audit(
        db,
        module="record_schedule",
        action="create_schedule",
        source="record_schedule_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=201,
        detail="ok",
        extra_summary=(
            f"schedule_id={plan.id}; resource_id={plan.resource_id}; "
            f"plan_type={plan.plan_type or ''}; enabled={bool(plan.enabled)}"
        ),
    )
    return {"id": plan.id, "resource_id": plan.resource_id, "plan_type": plan.plan_type, "enabled": plan.enabled}


@router.put("/{schedule_id}")
async def update_schedule(
    schedule_id: str,
    payload: RecordScheduleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """更新录像计划。"""
    stmt = select(RecordSchedule).where(RecordSchedule.id == schedule_id)
    if not current_user.is_superuser:
        stmt = stmt.join(Resource, Resource.id == RecordSchedule.resource_id).join(
            Asset, Asset.id == Resource.asset_id
        ).where(Asset.tenant_id == (current_user.tenant_id or "default"))
    row = (await db.execute(stmt)).scalars().first()
    if not row:
        await safe_auth_audit(
            db,
            module="record_schedule",
            action="update_schedule",
            source="record_schedule_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="not_found",
            extra_summary=f"schedule_id={schedule_id}",
        )
        raise HTTPException(status_code=404, detail="Record schedule not found")
    if payload.plan_type is not None:
        row.plan_type = payload.plan_type
    if payload.enabled is not None:
        row.enabled = payload.enabled
    if payload.time_ranges is not None:
        row.time_ranges = json.dumps(payload.time_ranges)
    if payload.priority is not None:
        row.priority = payload.priority
    await db.commit()
    await safe_auth_audit(
        db,
        module="record_schedule",
        action="update_schedule",
        source="record_schedule_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"schedule_id={row.id}; resource_id={row.resource_id}",
    )
    return {"status": "ok"}


@router.delete("/{schedule_id}")
async def delete_schedule(
    schedule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """删除录像计划。"""
    stmt = select(RecordSchedule).where(RecordSchedule.id == schedule_id)
    if not current_user.is_superuser:
        stmt = stmt.join(Resource, Resource.id == RecordSchedule.resource_id).join(
            Asset, Asset.id == Resource.asset_id
        ).where(Asset.tenant_id == (current_user.tenant_id or "default"))
    row = (await db.execute(stmt)).scalars().first()
    if not row:
        await safe_auth_audit(
            db,
            module="record_schedule",
            action="delete_schedule",
            source="record_schedule_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="not_found",
            extra_summary=f"schedule_id={schedule_id}",
        )
        raise HTTPException(status_code=404, detail="Record schedule not found")
    rid, resid, ptype = row.id, row.resource_id, row.plan_type or ""
    await db.delete(row)
    await db.commit()
    await safe_auth_audit(
        db,
        module="record_schedule",
        action="delete_schedule",
        source="record_schedule_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"schedule_id={rid}; resource_id={resid}; plan_type={ptype}",
    )
    return {"status": "ok"}


class StorageConfigPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    storage_root: str | None = None


class StorageNodeItem(BaseModel):
    id: str
    name: str
    path: str


class StorageNodesPayload(BaseModel):
    nodes: Optional[List[StorageNodeItem]] = None


@router.get("/storage-config")
async def get_storage_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """获取录像存储配置（存储根路径，扩展存储池时可增加节点列表）。"""
    r = (await db.execute(select(SystemSetting).where(SystemSetting.setting_key == RECORD_STORAGE_ROOT_KEY))).scalars().first()
    value = (r.setting_value if r else "").strip()
    return {"storage_root": value or ""}


@router.put("/storage-config")
async def update_storage_config(
    payload: StorageConfigPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("records.view")),  # 角色检查→权限码检查
):
    """设置录像存储根路径（用于存储扩容/存储池扩展）。"""
    value = (payload.storage_root or "").strip()
    r = (await db.execute(select(SystemSetting).where(SystemSetting.setting_key == RECORD_STORAGE_ROOT_KEY))).scalars().first()
    if r:
        r.setting_value = value
    else:
        db.add(SystemSetting(setting_key=RECORD_STORAGE_ROOT_KEY, setting_value=value))
    await db.commit()
    root_hint = value.replace(";", ".")[:160] if value else ""
    await safe_auth_audit(
        db,
        module="record_schedule",
        action="update_storage_config",
        source="record_schedule_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"storage_root_set={bool(value)}; path_hint={root_hint}",
    )
    return {"storage_root": value}





@router.get("/storage-nodes")
async def get_storage_nodes(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    r = (await db.execute(select(SystemSetting).where(SystemSetting.setting_key == RECORD_STORAGE_NODES_KEY))).scalars().first()
    if not r or not (r.setting_value or "").strip():
        return {"nodes": []}
    try:
        data = json.loads(r.setting_value)
        nodes = data if isinstance(data, list) else data.get("nodes", [])
    except Exception:
        nodes = []
    return {"nodes": nodes}


@router.put("/storage-nodes")
async def set_storage_nodes(
    payload: StorageNodesPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("records.view")),  # 角色检查→权限码检查
):
    """设置录像存储节点列表（存储池扩展占位）。"""
    raw = [{"id": n.id, "name": n.name, "path": n.path} for n in (payload.nodes or [])]
    value = json.dumps(raw)
    r = (await db.execute(select(SystemSetting).where(SystemSetting.setting_key == RECORD_STORAGE_NODES_KEY))).scalars().first()
    if r:
        r.setting_value = value
    else:
        db.add(SystemSetting(setting_key=RECORD_STORAGE_NODES_KEY, setting_value=value))
    await db.commit()
    await safe_auth_audit(
        db,
        module="record_schedule",
        action="set_storage_nodes",
        source="record_schedule_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"node_count={len(raw)}",
    )
    return {"nodes": raw}


@router.get("/runtimes")
async def list_schedule_runtimes(
    resource_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    stmt = select(RecordScheduleRuntime)
    if resource_id:
        stmt = stmt.where(RecordScheduleRuntime.resource_id == resource_id)
    if not current_user.is_superuser:
        stmt = stmt.where(RecordScheduleRuntime.tenant_id == (current_user.tenant_id or "default"))
    rows = (await db.execute(stmt.order_by(RecordScheduleRuntime.updated_at.desc()))).scalars().all()
    return [
        {
            "id": r.id,
            "tenant_id": r.tenant_id,
            "schedule_id": r.schedule_id,
            "resource_id": r.resource_id,
            "forced_mode": r.forced_mode,
            "forced_until": (r.forced_until.isoformat() if r.forced_until else None),
            "desired_recording": bool(r.desired_recording),
            "is_recording": bool(r.is_recording),
            "last_eval_at": (r.last_eval_at.isoformat() if r.last_eval_at else None),
            "last_stream_seen_at": (r.last_stream_seen_at.isoformat() if r.last_stream_seen_at else None),
            "last_action_at": (r.last_action_at.isoformat() if r.last_action_at else None),
            "last_action": r.last_action,
            "last_action_ok": bool(r.last_action_ok),
            "last_error": r.last_error or "",
            "last_media_node_id": r.last_media_node_id or "",
            "updated_at": (r.updated_at.isoformat() if r.updated_at else None),
        }
        for r in rows
    ]


class ForceActionPayload(BaseModel):
    minutes: int = 60


async def _select_media_node(db: AsyncSession) -> tuple[str, int, str]:
    proxy_host = settings.MEDIA_SERVER_HOST
    proxy_http_port = int(getattr(settings, "MEDIA_SERVER_HTTP_PORT", 0) or 0)
    proxy_secret = settings.MEDIA_SERVER_SECRET
    try:
        active_id = await get_active_media_node_id(db)
        db_node = await get_db_media_node_by_id(db, active_id) if active_id else None
        if not db_node:
            db_node = await select_best_db_node(db)
        if db_node:
            proxy_host = db_node.host or proxy_host
            proxy_http_port = int(db_node.http_port or proxy_http_port)
            proxy_secret = db_node.secret or proxy_secret
    except Exception as e:
        logger.warning(f"Error: {e}")
    return proxy_host, proxy_http_port, proxy_secret


async def _start_record(proxy_host: str, proxy_http_port: int, proxy_secret: str, stream: str) -> None:
    url = f"http://{proxy_host}:{proxy_http_port}/index/api/startRecord"
    try:
        # P-SEC: secret 通过 POST body 传递，避免出现在 URL/代理日志中
        r = await (await get_http_client()).post(url, data={"secret": proxy_secret, "vhost": "__defaultVhost__", "app": "live", "stream": stream, "type": 1}, timeout=5)  # 同步requests→异步httpx，避免阻塞事件循环
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError) as e:
        raise RuntimeError(f"startRecord request failed: {e}") from e
    # requests.get无try-catch，ZLM离线时ConnectionError未捕获
    if r.status_code >= 400:
        raise RuntimeError(f"startRecord http={r.status_code}")
    body = r.json()
    if body.get("code") not in {0, "0"}:
        raise RuntimeError(f"startRecord code={body.get('code')} msg={body.get('msg') or ''}".strip())


async def _stop_record(proxy_host: str, proxy_http_port: int, proxy_secret: str, stream: str) -> None:
    url = f"http://{proxy_host}:{proxy_http_port}/index/api/stopRecord"
    try:
        # P-SEC: secret 通过 POST body 传递，避免出现在 URL/代理日志中
        r = await (await get_http_client()).post(url, data={"secret": proxy_secret, "vhost": "__defaultVhost__", "app": "live", "stream": stream, "type": 1}, timeout=5)  # 同步requests→异步httpx，避免阻塞事件循环
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError) as e:
        raise RuntimeError(f"stopRecord request failed: {e}") from e
    # requests.get无try-catch，ZLM离线时ConnectionError未捕获
    if r.status_code >= 400:
        raise RuntimeError(f"stopRecord http={r.status_code}")
    body = r.json()
    if body.get("code") not in {0, "0"}:
        raise RuntimeError(f"stopRecord code={body.get('code')} msg={body.get('msg') or ''}".strip())


@router.post("/{schedule_id}/actions/force-start")
async def force_start_schedule(
    schedule_id: str,
    payload: ForceActionPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("records.view")),  # 角色检查→权限码检查
):
    sch = (await db.execute(select(RecordSchedule).where(RecordSchedule.id == schedule_id))).scalars().first()
    if not sch:
        await safe_auth_audit(
            db,
            module="record_schedule",
            action="force_start_record",
            source="record_schedule_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="schedule_not_found",
            extra_summary=f"schedule_id={schedule_id}",
        )
        raise HTTPException(status_code=404, detail="Record schedule not found")
    res = (await db.execute(select(Resource).where(Resource.id == sch.resource_id))).scalars().first()
    if not res:
        await safe_auth_audit(
            db,
            module="record_schedule",
            action="force_start_record",
            source="record_schedule_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="resource_not_found",
            extra_summary=f"schedule_id={schedule_id}; resource_id={sch.resource_id}",
        )
        raise HTTPException(status_code=404, detail="Channel not found")
    if not current_user.is_superuser:
        asset = (await db.execute(select(Asset).where(Asset.id == res.asset_id))).scalars().first()
        if not asset or asset.tenant_id != (current_user.tenant_id or "default"):
            await safe_auth_audit(
                db,
                module="record_schedule",
                action="force_start_record",
                source="record_schedule_admin",
                operator=current_user.username or "unknown",
                result="failed",
                tenant_id=_audit_tid(current_user),
                status_code=403,
                detail="forbidden",
                extra_summary=f"schedule_id={schedule_id}",
            )
            raise HTTPException(status_code=403, detail="Permission denied")
    stream = str(res.gb_id or "")
    if not stream:
        await safe_auth_audit(
            db,
            module="record_schedule",
            action="force_start_record",
            source="record_schedule_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="missing_gb_id",
            extra_summary=f"schedule_id={schedule_id}; resource_id={res.id}",
        )
        raise HTTPException(status_code=400, detail="Channel missing gb_id")
    proxy_host, proxy_http_port, proxy_secret = await _select_media_node(db)
    now = datetime.now(timezone.utc)
    minutes = max(1, min(int(payload.minutes or 60), 24 * 60))
    until = now + timedelta(minutes=minutes)
    rt = (await db.execute(select(RecordScheduleRuntime).where(RecordScheduleRuntime.schedule_id == schedule_id))).scalars().first()
    if not rt:
        tenant_id = current_user.tenant_id or "default"
        rt = RecordScheduleRuntime(tenant_id=tenant_id, schedule_id=schedule_id, resource_id=sch.resource_id)
        db.add(rt)
    rt.forced_mode = "on"
    rt.forced_until = until.replace(tzinfo=None)
    rt.last_action_at = now.replace(tzinfo=None)
    rt.last_action = "force_start"
    try:
        await _start_record(proxy_host, proxy_http_port, proxy_secret, stream)  # 同步requests→异步httpx，避免阻塞事件循环
        rt.is_recording = True
        rt.last_action_ok = True
        rt.last_error = ""
    except Exception as e:
        rt.is_recording = False
        rt.last_action_ok = False
        rt.last_error = f"force_start_failed {str(e)[:200]}"
    await db.commit()
    await safe_auth_audit(
        db,
        module="record_schedule",
        action="force_start_record",
        source="record_schedule_admin",
        operator=current_user.username or "unknown",
        result="success" if rt.last_action_ok else "failed",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok" if rt.last_action_ok else "zlm_action_failed",
        extra_summary=(
            f"schedule_id={schedule_id}; resource_id={sch.resource_id}; minutes={minutes}; "
            f"last_action_ok={bool(rt.last_action_ok)}"
        ),
    )
    return {"ok": True, "forced_until": until.isoformat()}


@router.post("/{schedule_id}/actions/force-stop")
async def force_stop_schedule(
    schedule_id: str,
    payload: ForceActionPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("records.view")),  # 角色检查→权限码检查
):
    sch = (await db.execute(select(RecordSchedule).where(RecordSchedule.id == schedule_id))).scalars().first()
    if not sch:
        await safe_auth_audit(
            db,
            module="record_schedule",
            action="force_stop_record",
            source="record_schedule_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="schedule_not_found",
            extra_summary=f"schedule_id={schedule_id}",
        )
        raise HTTPException(status_code=404, detail="Record schedule not found")
    res = (await db.execute(select(Resource).where(Resource.id == sch.resource_id))).scalars().first()
    if not res:
        await safe_auth_audit(
            db,
            module="record_schedule",
            action="force_stop_record",
            source="record_schedule_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="resource_not_found",
            extra_summary=f"schedule_id={schedule_id}; resource_id={sch.resource_id}",
        )
        raise HTTPException(status_code=404, detail="Channel not found")
    if not current_user.is_superuser:
        asset = (await db.execute(select(Asset).where(Asset.id == res.asset_id))).scalars().first()
        if not asset or asset.tenant_id != (current_user.tenant_id or "default"):
            await safe_auth_audit(
                db,
                module="record_schedule",
                action="force_stop_record",
                source="record_schedule_admin",
                operator=current_user.username or "unknown",
                result="failed",
                tenant_id=_audit_tid(current_user),
                status_code=403,
                detail="forbidden",
                extra_summary=f"schedule_id={schedule_id}",
            )
            raise HTTPException(status_code=403, detail="Permission denied")
    stream = str(res.gb_id or "")
    if not stream:
        await safe_auth_audit(
            db,
            module="record_schedule",
            action="force_stop_record",
            source="record_schedule_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="missing_gb_id",
            extra_summary=f"schedule_id={schedule_id}; resource_id={res.id}",
        )
        raise HTTPException(status_code=400, detail="Channel missing gb_id")
    proxy_host, proxy_http_port, proxy_secret = await _select_media_node(db)
    now = datetime.now(timezone.utc)
    minutes = max(1, min(int(payload.minutes or 10), 24 * 60))
    until = now + timedelta(minutes=minutes)
    rt = (await db.execute(select(RecordScheduleRuntime).where(RecordScheduleRuntime.schedule_id == schedule_id))).scalars().first()
    if not rt:
        tenant_id = current_user.tenant_id or "default"
        rt = RecordScheduleRuntime(tenant_id=tenant_id, schedule_id=schedule_id, resource_id=sch.resource_id)
        db.add(rt)
    rt.forced_mode = "off"
    rt.forced_until = until.replace(tzinfo=None)
    rt.last_action_at = now.replace(tzinfo=None)
    rt.last_action = "force_stop"
    try:
        await _stop_record(proxy_host, proxy_http_port, proxy_secret, stream)  # 同步requests→异步httpx，避免阻塞事件循环
        rt.is_recording = False
        rt.last_action_ok = True
        rt.last_error = ""
    except Exception as e:
        rt.last_action_ok = False
        rt.last_error = f"force_stop_failed {str(e)[:200]}"
    await db.commit()
    await safe_auth_audit(
        db,
        module="record_schedule",
        action="force_stop_record",
        source="record_schedule_admin",
        operator=current_user.username or "unknown",
        result="success" if rt.last_action_ok else "failed",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok" if rt.last_action_ok else "zlm_action_failed",
        extra_summary=(
            f"schedule_id={schedule_id}; resource_id={sch.resource_id}; minutes={minutes}; "
            f"last_action_ok={bool(rt.last_action_ok)}"
        ),
    )
    return {"ok": True, "forced_until": until.isoformat()}
