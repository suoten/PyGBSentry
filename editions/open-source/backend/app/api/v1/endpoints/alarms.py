import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, text, func, and_
from app.db.session import get_db
from app.models.alarm import Alarm
from app.models.alarm_escalation import AlarmEscalation
from app.models.alarm_notification import AlarmNotification
from app.models.asset import Asset
from app.models.user import User
from app.models.system_setting import SystemSetting
from app.models.alarm_link_rule import AlarmLinkRule
from app.api import deps
from app.core.config import settings
from app.services.auth_audit import safe_auth_audit
from app.services.audit_center_service import audit_center_service
from pydantic import BaseModel
from typing import Optional, Literal, Any
import json
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

router = APIRouter()



def _audit_tid(user: User) -> str:
    return (user.tenant_id or "default").strip() or "default"

class AlarmManager:
    def __init__(self):
        # FIXED: active_connections 改为 set，与 discard() 方法一致，且避免遍历时修改列表
        self.active_connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    async def broadcast_alarm(self, alarm_data: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_text(json.dumps(alarm_data))
            except (RuntimeError, ConnectionError, OSError):
                self.active_connections.discard(connection)

alarm_manager = AlarmManager()
schema_ready = False


class AlarmNotificationItem(BaseModel):
    id: str
    tenant_id: str
    alarm_id: Optional[str]
    device_id: Optional[str]
    channel_id: Optional[str]
    channel: str
    status: str
    error_message: Optional[str]
    description: Optional[str]
    sent_at: datetime


class AlarmEscalationAction(BaseModel):
    note: Optional[str] = None

class SlaOverview(BaseModel):
    total_open: int
    escalated_open: int
    overdue_open: int
    acknowledged_today: int
    avg_ack_minutes_today: float


class SlaCompareOverview(BaseModel):
    days: int
    period_current: int
    period_previous: int
    period_change_pct: float
    day_current: int
    day_previous: int
    day_change_pct: float


class SlaQualitySlowSample(BaseModel):
    alarm_id: str
    device_id: Optional[str]
    alarm_type: str
    level: str
    organization_id: str
    ack_minutes: float
    alarm_time: Optional[str]
    ack_at: Optional[str]


class SlaQualityOverview(BaseModel):
    days: int
    p50_ack_minutes: float
    p90_ack_minutes: float
    samples: int
    level_distribution: dict[str, int]
    alarm_type_distribution: dict[str, int]
    organization_distribution: dict[str, int]
    slow_samples: list[SlaQualitySlowSample]


class AlarmDashboardPresetItem(BaseModel):
    name: str
    config: dict[str, Any]


class AlarmDashboardPresetPayload(BaseModel):
    items: list[AlarmDashboardPresetItem]


class AlarmDashboardPresetAuditItem(BaseModel):
    audit_id: str
    action: str
    operator: str
    result: str
    created_at: str
    summary: str
    preset_count: int

def _build_alarm_item(alarm: Alarm, escalation: AlarmEscalation | None) -> dict:
    return {
        "id": alarm.id,
        "tenant_id": alarm.tenant_id,
        "device_id": alarm.device_id,
        "channel_id": alarm.channel_id,
        "priority": alarm.priority,
        "method": alarm.method,
        "time": alarm.time.isoformat() if alarm.time else None,
        "description": alarm.description,
        "alarm_type": alarm.alarm_type,
        "status": alarm.status,
        "escalation_level": escalation.escalation_level if escalation else 0,
        "escalation_count": escalation.escalation_count if escalation else 0,
        "escalation_state": escalation.state if escalation else "open",
        "ack_at": escalation.ack_at.isoformat() if escalation and escalation.ack_at else None,
        "last_escalated_at": escalation.last_escalated_at.isoformat() if escalation and escalation.last_escalated_at else None,
        "escalation_note": escalation.escalation_note if escalation else None,
    }


def _dashboard_preset_setting_key(user: User) -> str:
    tid = (user.tenant_id or "default").strip() or "default"
    return f"mobile.alarm.dashboard.presets.{tid}"

async def ensure_alarm_escalation(alarm_id: str, db: AsyncSession) -> AlarmEscalation:
    stmt = select(AlarmEscalation).where(AlarmEscalation.alarm_id == alarm_id)
    result = await db.execute(stmt)
    item = result.scalars().first()
    if item:
        return item
    item = AlarmEscalation(alarm_id=alarm_id, state="open", escalation_level=0, escalation_count=0)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item

_escalation_schema_lock = asyncio.Lock()


async def ensure_alarm_escalation_schema(db: AsyncSession):
    global schema_ready
    if schema_ready:
        return
    async with _escalation_schema_lock:
        if schema_ready:
            return
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS alarm_escalations (
                id VARCHAR(32) PRIMARY KEY,
                alarm_id VARCHAR(32) UNIQUE NOT NULL,
                escalation_level INTEGER DEFAULT 0,
                escalation_count INTEGER DEFAULT 0,
                state VARCHAR(20) DEFAULT 'open',
                ack_user_id VARCHAR(32),
                ack_at TIMESTAMP NULL,
                last_escalated_at TIMESTAMP NULL,
                escalation_note TEXT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        dialect = ""
        try:
            d = getattr(db.bind, "dialect", None)
            if d is not None:
                dialect = str(getattr(d, "name", "") or "").lower()
        except Exception as e:
            logger.debug(f"获取数据库方言失败: {e}")
        for idx_name, idx_col in [
            ("idx_alarm_escalations_alarm_id", "alarm_id"),
            ("idx_alarm_escalations_state", "state"),
        ]:
            if dialect == "mysql":
                idx_stmt = f"CREATE INDEX {idx_name} ON alarm_escalations ({idx_col})"
            else:
                idx_stmt = f"CREATE INDEX IF NOT EXISTS {idx_name} ON alarm_escalations ({idx_col})"
            try:
                await db.execute(text(idx_stmt))
            except Exception:
                continue
        try:
            await db.commit()
        except Exception:
            logger.warning("Failed to commit alarm index creation")
        schema_ready = True


def _build_notification_item(row: AlarmNotification) -> dict:
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "alarm_id": row.alarm_id,
        "device_id": row.device_id,
        "channel_id": row.channel_id,
        "channel": row.channel,
        "status": row.status,
        "error_message": row.error_message,
        "description": row.description,
        "sent_at": row.sent_at.isoformat() if row.sent_at else None,
    }

@router.get("")
async def get_alarms(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    escalation_state: Optional[Literal["open", "acknowledged"]] = None,
    min_escalation_level: int = Query(0, ge=0),  # FIXED: 添加Query约束
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    await ensure_alarm_escalation_schema(db)
    limit = max(1, min(int(limit or 50), 200))
    skip = max(0, int(skip or 0))

    # 默认只拉最近 24 小时，避免超大表全量扫
    now = datetime.now(timezone.utc)
    end_time = end_time or now
    start_time = start_time or (end_time - timedelta(hours=24))
    if start_time > end_time:
        raise HTTPException(status_code=400, detail="start_time cannot be greater than end_time")  # FIXED: 中文错误消息→英文
    if (end_time - start_time) > timedelta(days=7):
        raise HTTPException(status_code=400, detail="Time range too large, please limit to 7 days")  # FIXED: 中文错误消息→英文

    conditions = [Alarm.time >= start_time, Alarm.time <= end_time]
    if not current_user.is_superuser:
        conditions.append(Alarm.tenant_id == (current_user.tenant_id or "default"))
    if escalation_state:
        # 把无 escalation 记录视作 open
        conditions.append(func.coalesce(AlarmEscalation.state, "open") == escalation_state)
    if min_escalation_level > 0:
        conditions.append(func.coalesce(AlarmEscalation.escalation_level, 0) >= int(min_escalation_level))

    count_stmt = (
        select(func.count())
        .select_from(Alarm)
        .outerjoin(AlarmEscalation, AlarmEscalation.alarm_id == Alarm.id)
        .where(and_(*conditions))
    )
    total = int((await db.execute(count_stmt)).scalar() or 0)

    stmt = (
        select(Alarm, AlarmEscalation)
        .outerjoin(AlarmEscalation, AlarmEscalation.alarm_id == Alarm.id)
        .where(and_(*conditions))
        .order_by(desc(Alarm.time))
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()
    items = [_build_alarm_item(alarm, escalation) for alarm, escalation in rows]
    return {"items": items, "total": total, "skip": skip, "limit": limit, "start_time": start_time, "end_time": end_time}


@router.get("/unread-count")
async def get_unread_alarm_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    await ensure_alarm_escalation_schema(db)
    conditions = [Alarm.status == 0]
    if not current_user.is_superuser:
        conditions.append(Alarm.tenant_id == (current_user.tenant_id or "default"))
    stmt = select(func.count()).select_from(Alarm).where(and_(*conditions))
    total = int((await db.execute(stmt)).scalar() or 0)
    return {"unread_count": total}


@router.get("/notifications")
async def get_alarm_notifications(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    channel: Optional[str] = None,
    status: Optional[Literal["success", "fail"]] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    告警通知发送记录：
    - 支持按时间范围、渠道、状态过滤
    - 默认拉最近 24 小时，最多 7 天
    """
    limit = max(1, min(int(limit or 50), 200))
    skip = max(0, int(skip or 0))
    now = datetime.now(timezone.utc)
    end_time = end_time or now
    start_time = start_time or (end_time - timedelta(hours=24))
    if start_time > end_time:
        raise HTTPException(status_code=400, detail="start_time cannot be greater than end_time")  # FIXED: 中文错误消息→英文
    if (end_time - start_time) > timedelta(days=7):
        raise HTTPException(status_code=400, detail="Time range too large, please limit to 7 days")  # FIXED: 中文错误消息→英文

    conditions = [AlarmNotification.sent_at >= start_time, AlarmNotification.sent_at <= end_time]
    if not current_user.is_superuser:
        conditions.append(AlarmNotification.tenant_id == (current_user.tenant_id or "default"))
    if channel:
        conditions.append(AlarmNotification.channel == channel)
    if status:
        conditions.append(AlarmNotification.status == status)

    count_stmt = select(func.count()).select_from(AlarmNotification).where(and_(*conditions))
    total = int((await db.execute(count_stmt)).scalar() or 0)

    stmt = (
        select(AlarmNotification)
        .where(and_(*conditions))
        .order_by(desc(AlarmNotification.sent_at))
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    items = [_build_notification_item(r) for r in rows]
    return {
        "items": items,
        "total": total,
        "skip": skip,
        "limit": limit,
        "start_time": start_time,
        "end_time": end_time,
    }

@router.get("/sla/overview", response_model=SlaOverview)
async def get_sla_overview(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    await ensure_alarm_escalation_schema(db)
    _ALARM_LIST_HARD_LIMIT = 1000  # FIXED: 魔法数字提取为常量
    alarms_stmt = select(Alarm).order_by(desc(Alarm.time)).limit(_ALARM_LIST_HARD_LIMIT)
    if not current_user.is_superuser:
        alarms_stmt = alarms_stmt.where(Alarm.tenant_id == (current_user.tenant_id or "default"))
    alarms_result = await db.execute(alarms_stmt)
    alarms = alarms_result.scalars().all()
    if not alarms:
        return SlaOverview(
            total_open=0,
            escalated_open=0,
            overdue_open=0,
            acknowledged_today=0,
            avg_ack_minutes_today=0,
        )
    alarm_ids = [item.id for item in alarms]
    escalation_stmt = select(AlarmEscalation).where(AlarmEscalation.alarm_id.in_(alarm_ids))
    escalation_result = await db.execute(escalation_stmt)
    escalation_map = {item.alarm_id: item for item in escalation_result.scalars().all()}
    now = datetime.now(timezone.utc)
    today = now.date()
    overdue_minutes = max(settings.ALARM_ESCALATION_FIRST_MINUTES, 1)
    total_open = 0
    escalated_open = 0
    overdue_open = 0
    ack_count = 0
    ack_minutes_sum = 0.0
    for alarm in alarms:
        escalation = escalation_map.get(alarm.id)
        state = escalation.state if escalation else "open"
        level = escalation.escalation_level if escalation else 0
        if state != "acknowledged":
            total_open += 1
            if level > 0:
                escalated_open += 1
            if alarm.time and (now - alarm.time).total_seconds() >= overdue_minutes * 60:
                overdue_open += 1
        if escalation and escalation.ack_at and escalation.ack_at.date() == today and alarm.time:
            ack_count += 1
            ack_minutes_sum += max((escalation.ack_at - alarm.time).total_seconds(), 0) / 60
    return SlaOverview(
        total_open=total_open,
        escalated_open=escalated_open,
        overdue_open=overdue_open,
        acknowledged_today=ack_count,
        avg_ack_minutes_today=round((ack_minutes_sum / ack_count), 2) if ack_count > 0 else 0,
    )


@router.get("/sla/compare", response_model=SlaCompareOverview)
async def get_sla_compare(
    days: int = Query(7, ge=1, le=365),  # FIXED: 添加Query约束
    alarm_type: Optional[str] = None,
    organization_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    await ensure_alarm_escalation_schema(db)
    days = max(3, min(int(days or 7), 30))
    now = datetime.now(timezone.utc)

    def _calc_change(current_value: int, previous_value: int) -> float:
        if previous_value <= 0:
            return 100.0 if current_value > 0 else 0.0
        return round(((current_value - previous_value) / previous_value) * 100, 2)

    async def _count_alarms(start_at: datetime, end_at: datetime) -> int:
        conditions = [Alarm.time >= start_at, Alarm.time <= end_at]
        if not current_user.is_superuser:
            conditions.append(Alarm.tenant_id == (current_user.tenant_id or "default"))
        if alarm_type:
            conditions.append(Alarm.alarm_type == alarm_type)

        org_id = (organization_id or "").strip()
        if org_id:
            if org_id == "__ungrouped__":
                conditions.append((Asset.organization_id.is_(None)) | (Asset.organization_id == ""))
            else:
                conditions.append(Asset.organization_id == org_id)

        stmt = select(func.count()).select_from(Alarm)
        if org_id:
            stmt = stmt.join(Asset, Asset.gb_id == Alarm.device_id)
            if not current_user.is_superuser:
                conditions.append(Asset.tenant_id == (current_user.tenant_id or "default"))
        stmt = stmt.where(and_(*conditions))
        return int((await db.execute(stmt)).scalar() or 0)

    current_start = now - timedelta(days=days)
    current_end = now
    previous_end = current_start
    previous_start = previous_end - timedelta(days=days)
    day_current_start = now - timedelta(days=1)
    day_previous_end = day_current_start
    day_previous_start = day_previous_end - timedelta(days=1)

    period_current = await _count_alarms(current_start, current_end)
    period_previous = await _count_alarms(previous_start, previous_end)
    day_current = await _count_alarms(day_current_start, current_end)
    day_previous = await _count_alarms(day_previous_start, day_previous_end)

    return SlaCompareOverview(
        days=days,
        period_current=period_current,
        period_previous=period_previous,
        period_change_pct=_calc_change(period_current, period_previous),
        day_current=day_current,
        day_previous=day_previous,
        day_change_pct=_calc_change(day_current, day_previous),
    )


@router.get("/sla/quality", response_model=SlaQualityOverview)
async def get_sla_quality(
    days: int = Query(7, ge=1, le=365),  # FIXED: 添加Query约束
    alarm_type: Optional[str] = None,
    organization_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    await ensure_alarm_escalation_schema(db)
    days = max(3, min(int(days or 7), 30))
    now = datetime.now(timezone.utc)
    start_at = now - timedelta(days=days)

    conditions = [Alarm.time >= start_at, Alarm.time <= now]
    if not current_user.is_superuser:
        conditions.append(Alarm.tenant_id == (current_user.tenant_id or "default"))
    if alarm_type:
        conditions.append(Alarm.alarm_type == alarm_type)

    org_id = (organization_id or "").strip()
    stmt = (
        select(Alarm, AlarmEscalation, Asset)
        .outerjoin(AlarmEscalation, AlarmEscalation.alarm_id == Alarm.id)
        .outerjoin(Asset, Asset.gb_id == Alarm.device_id)
    )
    if org_id:
        if org_id == "__ungrouped__":
            conditions.append((Asset.organization_id.is_(None)) | (Asset.organization_id == ""))
        else:
            conditions.append(Asset.organization_id == org_id)
        if not current_user.is_superuser:
            conditions.append(Asset.tenant_id == (current_user.tenant_id or "default"))
    stmt = stmt.where(and_(*conditions)).order_by(desc(Alarm.time)).limit(2000)
    rows = (await db.execute(stmt)).all()

    durations: list[float] = []
    level_map: dict[str, int] = {}
    type_map: dict[str, int] = {}
    org_map: dict[str, int] = {}
    slow_samples: list[SlaQualitySlowSample] = []
    for alarm, escalation, asset in rows:
        level_key = str((alarm.priority or alarm.alarm_type or "normal")).strip().lower() or "normal"
        level_map[level_key] = int(level_map.get(level_key, 0) + 1)
        type_key = str((alarm.alarm_type or "unknown")).strip().lower() or "unknown"
        type_map[type_key] = int(type_map.get(type_key, 0) + 1)
        org_raw = (getattr(asset, "organization_id", None) or "").strip()
        org_key = org_raw if org_raw else "__ungrouped__"
        org_map[org_key] = int(org_map.get(org_key, 0) + 1)

        if not escalation or not escalation.ack_at or not alarm.time:
            continue
        delta = (escalation.ack_at - alarm.time).total_seconds() / 60.0
        if delta >= 0:
            ack_minutes = round(float(delta), 2)
            durations.append(ack_minutes)
            slow_samples.append(
                SlaQualitySlowSample(
                    alarm_id=str(alarm.id),
                    device_id=alarm.device_id,
                    alarm_type=type_key,
                    level=level_key,
                    organization_id=org_key,
                    ack_minutes=ack_minutes,
                    alarm_time=alarm.time.isoformat() if alarm.time else None,
                    ack_at=escalation.ack_at.isoformat() if escalation.ack_at else None,
                )
            )

    durations.sort()

    def _percentile(values: list[float], p: int) -> float:
        if not values:
            return 0.0
        idx = max(0, min(len(values) - 1, int((p / 100.0) * len(values) + 0.999999) - 1))
        return round(float(values[idx]), 2)

    return SlaQualityOverview(
        days=days,
        p50_ack_minutes=_percentile(durations, 50),
        p90_ack_minutes=_percentile(durations, 90),
        samples=len(durations),
        level_distribution=level_map,
        alarm_type_distribution=type_map,
        organization_distribution=org_map,
        slow_samples=sorted(slow_samples, key=lambda x: x.ack_minutes, reverse=True)[:10],
    )


@router.get("/sla/presets")
async def get_sla_presets(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    key = _dashboard_preset_setting_key(current_user)
    row = (await db.execute(select(SystemSetting).where(SystemSetting.setting_key == key))).scalars().first()
    if not row or not (row.setting_value or "").strip():
        writable = bool(current_user.is_superuser or (getattr(current_user, "role", "") in {"owner", "admin"}))
        return {"items": [], "writable": writable}
    try:
        data = json.loads(row.setting_value)
        items = data.get("items", []) if isinstance(data, dict) else []
        if not isinstance(items, list):
            items = []
        writable = bool(current_user.is_superuser or (getattr(current_user, "role", "") in {"owner", "admin"}))
        return {"items": items, "writable": writable}
    except Exception:
        writable = bool(current_user.is_superuser or (getattr(current_user, "role", "") in {"owner", "admin"}))
        return {"items": [], "writable": writable}


@router.put("/sla/presets")
async def update_sla_presets(
    payload: AlarmDashboardPresetPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    key = _dashboard_preset_setting_key(current_user)
    items = payload.items[:30]
    compact_items: list[dict[str, Any]] = []
    for item in items:
        name = (item.name or "").strip()[:64]
        if not name:
            continue
        config = item.config if isinstance(item.config, dict) else {}
        compact_items.append({"name": name, "config": config})
    value = json.dumps({"items": compact_items}, ensure_ascii=False)
    row = (await db.execute(select(SystemSetting).where(SystemSetting.setting_key == key))).scalars().first()
    if row:
        row.setting_value = value
    else:
        db.add(SystemSetting(setting_key=key, setting_value=value))
    await db.commit()
    await safe_auth_audit(
        db,
        module="alarms",
        action="update_sla_presets",
        source="alarm_dashboard",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=(
            f"preset_count={len(compact_items)}; "
            f"preset_names={','.join([x['name'].replace(';', '.') for x in compact_items[:5]])}"
        ),
    )
    return {"items": compact_items}


@router.get("/sla/presets/audits", response_model=list[AlarmDashboardPresetAuditItem])
async def get_sla_preset_audits(
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    safe_limit = max(1, min(int(limit or 10), 50))
    tenant_id = _audit_tid(current_user)
    result = await audit_center_service.list_logs(
        db=db,
        module="alarms",
        action="update_sla_presets",
        tenant_id=tenant_id,
        page=1,
        page_size=safe_limit,
    )
    rows = result.get("items", []) if isinstance(result, dict) else []
    output: list[AlarmDashboardPresetAuditItem] = []
    for row in rows:
        summary = str(row.get("summary") or "")
        preset_count = 0
        for token in [x.strip() for x in summary.split(";") if x.strip()]:
            if token.startswith("preset_count="):
                try:
                    preset_count = int(token.split("=", 1)[1].strip() or "0")
                except Exception:
                    preset_count = 0
                break
        output.append(
            AlarmDashboardPresetAuditItem(
                audit_id=str(row.get("audit_id") or ""),
                action=str(row.get("action") or "update_sla_presets"),
                operator=str(row.get("operator") or "unknown"),
                result=str(row.get("result") or "unknown"),
                created_at=str(row.get("created_at") or ""),
                summary=summary,
                preset_count=preset_count,
            )
        )
    return output

@router.post("/{alarm_id}/ack")
async def acknowledge_alarm(
    alarm_id: str,
    payload: AlarmEscalationAction,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    await ensure_alarm_escalation_schema(db)
    stmt = select(Alarm).where(Alarm.id == alarm_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Alarm.tenant_id == (current_user.tenant_id or "default"))
    result = await db.execute(stmt)
    alarm = result.scalars().first()
    if not alarm:
        await safe_auth_audit(
            db,
            module="alarms",
            action="ack_alarm",
            source="alarm_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="alarm_not_found",
            extra_summary=f"alarm_id={alarm_id}",
        )
        raise HTTPException(status_code=404, detail="Alarm not found")  # FIXED: 中文错误消息→英文
    escalation = await ensure_alarm_escalation(alarm.id, db)
    escalation.state = "acknowledged"
    escalation.ack_user_id = current_user.id
    escalation.ack_at = datetime.now(timezone.utc)
    if payload.note is not None:
        escalation.escalation_note = payload.note
    alarm.status = 1
    await db.commit()
    await db.refresh(escalation)
    # FIXED: W-34 报警事件级联通知 — 确认报警后通知上级平台
    try:
        from app.services.platform_service import platform_service as _platform_svc
        from app.models.platform import ParentPlatform
        if _platform_svc:
            plat_stmt = select(ParentPlatform).where(
                ParentPlatform.tenant_id == (alarm.tenant_id or "default"),
                ParentPlatform.is_online == True,
                ParentPlatform.enable == True,
            )
            plat_result = await db.execute(plat_stmt)
            platforms = plat_result.scalars().all()
            for _plat in platforms:
                await _platform_svc.send_alarm_notify(
                    platform=_plat,
                    device_id=alarm.device_id or "",
                    channel_id=alarm.channel_id or "",
                    alarm_type=alarm.alarm_type or "",
                    priority=alarm.priority or "4",
                    description=alarm.description or "",
                    alarm_time_iso=alarm.time.isoformat() if alarm.time else None,
                )
    except Exception as _notify_err:
        logger.warning(f"W-34 alarm cascade notify failed on ack: {_notify_err}")
    await safe_auth_audit(
        db,
        module="alarms",
        action="ack_alarm",
        source="alarm_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"alarm_id={alarm_id}; state={escalation.state or ''}",
    )
    return {"ok": True, "alarm_id": alarm_id, "state": escalation.state}

@router.post("/{alarm_id}/escalate")
async def escalate_alarm(
    alarm_id: str,
    payload: AlarmEscalationAction,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    await ensure_alarm_escalation_schema(db)
    stmt = select(Alarm).where(Alarm.id == alarm_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Alarm.tenant_id == (current_user.tenant_id or "default"))
    result = await db.execute(stmt)
    alarm = result.scalars().first()
    if not alarm:
        await safe_auth_audit(
            db,
            module="alarms",
            action="escalate_alarm",
            source="alarm_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="alarm_not_found",
            extra_summary=f"alarm_id={alarm_id}",
        )
        raise HTTPException(status_code=404, detail="Alarm not found")  # FIXED: 中文错误消息→英文
    escalation = await ensure_alarm_escalation(alarm.id, db)
    if escalation.state == "acknowledged":
        await safe_auth_audit(
            db,
            module="alarms",
            action="escalate_alarm",
            source="alarm_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="already_acknowledged",
            extra_summary=f"alarm_id={alarm_id}",
        )
        raise HTTPException(status_code=400, detail="Acknowledged alarm cannot be escalated")  # FIXED: 中文错误消息→英文
    escalation.state = "open"
    escalation.escalation_level = min(escalation.escalation_level + 1, max(settings.ALARM_ESCALATION_MAX_LEVEL, 1))
    escalation.escalation_count = max(escalation.escalation_count + 1, escalation.escalation_level)
    escalation.last_escalated_at = datetime.now(timezone.utc)
    if payload.note is not None:
        escalation.escalation_note = payload.note
    await db.commit()
    await db.refresh(escalation)
    # FIXED: W-34 报警事件级联通知 — 升级报警后通知上级平台
    try:
        from app.services.platform_service import platform_service as _platform_svc
        from app.models.platform import ParentPlatform
        if _platform_svc:
            plat_stmt = select(ParentPlatform).where(
                ParentPlatform.tenant_id == (alarm.tenant_id or "default"),
                ParentPlatform.is_online == True,
                ParentPlatform.enable == True,
            )
            plat_result = await db.execute(plat_stmt)
            platforms = plat_result.scalars().all()
            for _plat in platforms:
                await _platform_svc.send_alarm_notify(
                    platform=_plat,
                    device_id=alarm.device_id or "",
                    channel_id=alarm.channel_id or "",
                    alarm_type=alarm.alarm_type or "",
                    priority=alarm.priority or "4",
                    description=alarm.description or "",
                    alarm_time_iso=alarm.time.isoformat() if alarm.time else None,
                )
    except Exception as _notify_err:
        logger.warning(f"W-34 alarm cascade notify failed on escalate: {_notify_err}")
    await safe_auth_audit(
        db,
        module="alarms",
        action="escalate_alarm",
        source="alarm_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=(
            f"alarm_id={alarm_id}; escalation_level={escalation.escalation_level}; "
            f"escalation_count={escalation.escalation_count}"
        ),
    )
    return {
        "ok": True,
        "alarm_id": alarm_id,
        "escalation_level": escalation.escalation_level,
        "escalation_count": escalation.escalation_count,
    }


ALARM_RECORD_LINK_KEY = "alarm_record_link_enabled"


@router.get("/config")
async def get_alarm_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """报警联动配置：报警录像联动是否开启。"""
    r = await db.execute(select(SystemSetting).where(SystemSetting.setting_key == ALARM_RECORD_LINK_KEY))
    row = r.scalars().first()
    value = (row.setting_value or "false").strip().lower() in ("1", "true", "yes") if row else False
    return {"alarm_record_link_enabled": value}


class AlarmConfigPayload(BaseModel):
    alarm_record_link_enabled: bool = False


@router.put("/config")
async def update_alarm_config(
    payload: AlarmConfigPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    """开启/关闭报警录像联动。开启后，设备上报报警时会触发 HOOK_ALARM_RECORD_LINK，插件可拉流录像。"""
    r = await db.execute(select(SystemSetting).where(SystemSetting.setting_key == ALARM_RECORD_LINK_KEY))
    row = r.scalars().first()
    value = "true" if payload.alarm_record_link_enabled else "false"
    if row:
        row.setting_value = value
    else:
        db.add(SystemSetting(setting_key=ALARM_RECORD_LINK_KEY, setting_value=value))
    await db.commit()
    await safe_auth_audit(
        db,
        module="alarms",
        action="update_alarm_config",
        source="alarm_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"alarm_record_link_enabled={bool(payload.alarm_record_link_enabled)}",
    )
    return {"alarm_record_link_enabled": payload.alarm_record_link_enabled}


class AlarmLinkRulePayload(BaseModel):
    id: Optional[str] = None
    name: str
    enabled: bool = True
    min_priority: Optional[int] = None
    max_priority: Optional[int] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    days: Optional[str] = None
    organization_id: Optional[str] = None
    link_record: bool = True
    link_wall: bool = False
    link_notify: bool = False


@router.get("/link-rules")
async def list_alarm_link_rules(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    tenant_id = current_user.tenant_id or "default"
    stmt = select(AlarmLinkRule).where(AlarmLinkRule.tenant_id == tenant_id).order_by(
        desc(AlarmLinkRule.enabled), desc(AlarmLinkRule.created_at)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "enabled": r.enabled,
            "min_priority": r.min_priority,
            "max_priority": r.max_priority,
            "start_time": r.start_time,
            "end_time": r.end_time,
            "days": r.days,
            "organization_id": r.organization_id,
            "link_record": r.link_record,
            "link_wall": r.link_wall,
            "link_notify": r.link_notify,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
        }
        for r in rows
    ]


@router.post("/link-rules")
async def create_alarm_link_rule(
    payload: AlarmLinkRulePayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    tenant_id = current_user.tenant_id or "default"
    item = AlarmLinkRule(
        tenant_id=tenant_id,
        name=payload.name.strip(),
        enabled=payload.enabled,
        min_priority=payload.min_priority,
        max_priority=payload.max_priority,
        start_time=(payload.start_time or "").strip() or None,
        end_time=(payload.end_time or "").strip() or None,
        days=(payload.days or "").strip() or None,
        organization_id=(payload.organization_id or "").strip() or None,
        link_record=payload.link_record,
        link_wall=payload.link_wall,
        link_notify=payload.link_notify,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    await safe_auth_audit(
        db,
        module="alarms",
        action="create_alarm_link_rule",
        source="alarm_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=201,
        detail="ok",
        extra_summary=f"rule_id={item.id}; name={(item.name or '').replace(';', '.')[:80]}",
    )
    return {"id": item.id}


@router.put("/link-rules/{rule_id}")
async def update_alarm_link_rule(
    rule_id: str,
    payload: AlarmLinkRulePayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    tenant_id = current_user.tenant_id or "default"
    stmt = select(AlarmLinkRule).where(
        AlarmLinkRule.id == rule_id, AlarmLinkRule.tenant_id == tenant_id
    )
    result = await db.execute(stmt)
    item = result.scalars().first()
    if not item:
        await safe_auth_audit(
            db,
            module="alarms",
            action="update_alarm_link_rule",
            source="alarm_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="rule_not_found",
            extra_summary=f"rule_id={rule_id}",
        )
        raise HTTPException(status_code=404, detail="Rule not found")  # FIXED: 中文错误消息→英文
    item.name = payload.name.strip()
    item.enabled = payload.enabled
    item.min_priority = payload.min_priority
    item.max_priority = payload.max_priority
    item.start_time = (payload.start_time or "").strip() or None
    item.end_time = (payload.end_time or "").strip() or None
    item.days = (payload.days or "").strip() or None
    item.organization_id = (payload.organization_id or "").strip() or None
    item.link_record = payload.link_record
    item.link_wall = payload.link_wall
    item.link_notify = payload.link_notify
    await db.commit()
    await db.refresh(item)
    await safe_auth_audit(
        db,
        module="alarms",
        action="update_alarm_link_rule",
        source="alarm_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"rule_id={item.id}; enabled={bool(item.enabled)}",
    )
    return {"id": item.id}


@router.delete("/link-rules/{rule_id}")
async def delete_alarm_link_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    tenant_id = current_user.tenant_id or "default"
    stmt = select(AlarmLinkRule).where(
        AlarmLinkRule.id == rule_id, AlarmLinkRule.tenant_id == tenant_id
    )
    result = await db.execute(stmt)
    item = result.scalars().first()
    if not item:
        await safe_auth_audit(
            db,
            module="alarms",
            action="delete_alarm_link_rule",
            source="alarm_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="rule_not_found",
            extra_summary=f"rule_id={rule_id}",
        )
        raise HTTPException(status_code=404, detail="Rule not found")  # FIXED: 中文错误消息→英文
    rid, rname = item.id, item.name or ""
    await db.delete(item)
    await db.commit()
    await safe_auth_audit(
        db,
        module="alarms",
        action="delete_alarm_link_rule",
        source="alarm_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"rule_id={rid}; name={rname.replace(';', '.')[:80]}",
    )
    return {"ok": True}


@router.websocket("/ws")
async def websocket_alarms(websocket: WebSocket):
    await alarm_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text() # Keep alive
    except WebSocketDisconnect:
        alarm_manager.disconnect(websocket)
