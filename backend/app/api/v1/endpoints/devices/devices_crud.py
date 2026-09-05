"""设备增删改查端点（列表/创建/更新/删除/详情/订阅/导出/拉黑等）。"""

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, func, desc, update, delete, case
from app.db.session import get_db
import io
import csv
import json as _json
from pydantic import BaseModel
from app.models.asset import Asset
from app.models.resource import Resource
from app.models.record import Record
from app.models.asset_maintenance import AssetMaintenance
from app.models.organization import Organization
from app.models.asset_stream_policy import AssetStreamPolicy
from app.models.asset_stream_health import AssetStreamHealth  # FIX: [2026-07-13] 级联删除流健康度记录
from app.models.ip_blacklist import IpBlacklist
try:
    # 可选依赖：部分部署/版本可能没有该模型与对应表
    from app.models.device_subscription import DeviceSubscription
except ModuleNotFoundError:  # pragma: no cover
    # P1-9: 运行时为 None 时所有调用点已做 `if DeviceSubscription is None` 守卫
    DeviceSubscription = None  # type: ignore[assignment]
from app.models.user import User
from app.api import deps
from app.api.deps import get_or_404
from app.sip.server import sip_server
import app.sip.commander as sip_commander_module
from app.sip.catalog_runtime import get_device_catalog_runtime_batch
from app.services.auth_audit import safe_auth_audit
from typing import Any
from datetime import datetime, timezone
from app.core.async_utils import fire_and_forget  # P0-16: 安全的火-忘任务

from . _common import (
    _tenant_id_for_user,
    _safe_val,
    StreamModeUpdate,
    DeviceOrganizationUpdate,
    CatalogSubscriptionUpdate,
    MobilePositionSubscriptionUpdate,
    DeviceCreatePayload,
    DeviceUpdatePayload,
    BatchDeletePayload,
    DeviceBlacklistRequest,
    DeviceExportPayload,
)

router = APIRouter()


class DeviceItem(BaseModel):
    """设备列表项响应模型（GET /api/v1/devices）。

    与列表端点的序列化 dict 字段一一对应，作为前后端契约的
    单一事实来源（frontend/src/types/models.ts Device 接口）。
    """

    id: str
    gb_id: str
    name: str | None = None
    organization_id: str | None = None
    transport: str | None = None
    ip_addr: str | None = None
    port: int | None = None
    manufacturer: str | None = None
    model: str | None = None
    firmware: str | None = None
    status: int | None = None
    is_online: bool
    last_keepalive: datetime | None = None
    register_time: datetime | None = None
    expires: int | None = None
    domain: str | None = None
    charset: str | None = None
    ssrc_check: bool | None = None
    geo_coord_sys: str | None = None
    as_message_channel: bool | None = None
    heartbeat_interval: int | None = None
    heartbeat_count: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    stream_mode: str
    catalog_sync_runtime: dict[str, Any] = {}
    channel_count: int
    catalog_subscribe_enabled: bool
    catalog_subscribe_cycle_seconds: int
    catalog_subscribe_last_sync_at: datetime | None = None
    catalog_subscribe_last_sync_ok: int
    catalog_subscribe_last_sync_error: str
    mobile_position_subscribe_enabled: bool
    mobile_position_interval_seconds: int
    mobile_position_last_subscribe_at: datetime | None = None
    mobile_position_last_subscribe_ok: int
    mobile_position_last_subscribe_error: str


class DeviceStats(BaseModel):
    total: int
    online: int
    offline: int


class DeviceListResponse(BaseModel):
    items: list[DeviceItem]
    total: int
    skip: int
    limit: int
    stats: DeviceStats


def _escape_ilike(val: str) -> str:
    return val.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# 导出端点全量加载无限制 → 添加 max_rows 限制
_EXPORT_MAX_ROWS = 10000
@router.get("", response_model=DeviceListResponse)
async def get_devices(
    organization_id: str | None = None,
    keyword: str = "",
    status: int | None = None,
    # 添加 Query 约束，与项目其他 endpoint 保持一致
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=10000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """设备列表；可选按组织筛选 organization_id。"""
    limit = max(1, min(int(limit or 50), 10000))
    skip = max(0, int(skip or 0))

    base_conditions = []
    if not current_user.is_superuser:
        base_conditions.append(Asset.tenant_id == (current_user.tenant_id or "default"))
    if organization_id is not None:
        base_conditions.append(Asset.organization_id == organization_id)
    keyword = (keyword or "").strip()
    if keyword:
        base_conditions.append(
            or_(
                Asset.gb_id.ilike(f"%{_escape_ilike(keyword)}%"),
                Asset.name.ilike(f"%{_escape_ilike(keyword)}%"),
                Asset.manufacturer.ilike(f"%{_escape_ilike(keyword)}%"),
                Asset.model.ilike(f"%{_escape_ilike(keyword)}%"),
            )
        )

    conditions = list(base_conditions)
    if status is not None:
        conditions.append(Asset.status == int(status))

    # 合并三个 COUNT 查询为一次查询
    stats_total_stmt = select(
        func.count().label("total"),
        func.sum(case((Asset.status == 1, 1), else_=0)).label("online"),
    ).select_from(Asset)
    if base_conditions:
        stats_total_stmt = stats_total_stmt.where(and_(*base_conditions))
    stats_result = await db.execute(stats_total_stmt)
    stats_row = stats_result.first()
    stats_total = int(stats_row.total or 0) if stats_row else 0
    online_total = int(stats_row.online or 0) if stats_row else 0
    offline_total = max(0, stats_total - online_total)

    # 带筛选条件的总数（用于分页）
    count_stmt = select(func.count()).select_from(Asset)
    if conditions:
        count_stmt = count_stmt.where(and_(*conditions))
    total = int((await db.execute(count_stmt)).scalar() or 0)

    stmt = select(Asset)
    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.order_by(desc(Asset.updated_at), desc(Asset.created_at)).offset(skip).limit(limit)
    asset_result = await db.execute(stmt)
    assets = asset_result.scalars().all()

    asset_ids = [a.id for a in assets]
    policy_map: dict[str, str] = {}
    if asset_ids:
        policy_stmt = select(AssetStreamPolicy).where(AssetStreamPolicy.asset_id.in_(asset_ids))
        policy_result = await db.execute(policy_stmt)
        policy_map = {policy.asset_id: policy.stream_mode for policy in policy_result.scalars().all()}

    # 通道数量（设备列表的"通道数"列）
    channel_count_map: dict[str, int] = {}
    if asset_ids:
        channel_count_stmt = (
            select(Resource.asset_id, func.count(Resource.id))
            .where(Resource.asset_id.in_(asset_ids), Resource.node_type == "channel")
            .group_by(Resource.asset_id)
        )
        channel_count_result = await db.execute(channel_count_stmt)
        channel_count_map = {str(asset_id): int(cnt) for asset_id, cnt in channel_count_result.all()}

    subs_map: dict[str, Any] = {}
    if asset_ids and DeviceSubscription is not None:
        subs_stmt = select(DeviceSubscription).where(DeviceSubscription.asset_id.in_(asset_ids))
        if not current_user.is_superuser:
            subs_stmt = subs_stmt.where(DeviceSubscription.tenant_id == (current_user.tenant_id or "default"))
        subs = (await db.execute(subs_stmt)).scalars().all()
        subs_map = {s.asset_id: s for s in subs}

    # 批量获取 catalog runtime，避免 N+1 查询
    gb_ids = [asset.gb_id for asset in assets]
    runtime_map = await get_device_catalog_runtime_batch(gb_ids)

    items = []
    for asset in assets:
        runtime = runtime_map.get(asset.gb_id, {})
        sub = subs_map.get(asset.id)
        cycle = int(getattr(sub, "catalog_cycle_seconds", 0) or 0) if sub else 0
        items.append(
            {
            "id": asset.id,
            "gb_id": asset.gb_id,
            "name": asset.name,
            "organization_id": asset.organization_id,
            "transport": asset.transport,
            "ip_addr": asset.ip_addr,
            "port": asset.port,
            "manufacturer": asset.manufacturer,
            "model": asset.model,
            "firmware": asset.firmware,
            "status": asset.status,
            "is_online": asset.status == 1,  # FIX: [2026-07-04] 响应缺少 is_online 布尔字段，前端/审计读取恒为 None [全栈工程师]
            "last_keepalive": asset.last_keepalive,
            "register_time": asset.register_time,
            "expires": asset.expires,
            "domain": getattr(asset, "domain", None),  # FIX: [2026-07-03] Asset 模型无 domain 列，使用 getattr 防止 AttributeError [全栈工程师]
            "charset": asset.charset,
            "ssrc_check": asset.ssrc_check,
            "geo_coord_sys": asset.geo_coord_sys,
            "as_message_channel": asset.as_message_channel,
            "heartbeat_interval": asset.heartbeat_interval,
            "heartbeat_count": asset.heartbeat_count,
            "created_at": asset.created_at,
            "updated_at": asset.updated_at,
            "stream_mode": policy_map.get(asset.id) or "GLOBAL",
            "catalog_sync_runtime": runtime,
            "channel_count": channel_count_map.get(str(asset.id), 0),
            "catalog_subscribe_enabled": bool(cycle > 0),
            "catalog_subscribe_cycle_seconds": cycle,
            "catalog_subscribe_last_sync_at": (sub.last_catalog_sync_at if sub else None),
            "catalog_subscribe_last_sync_ok": int(getattr(sub, "last_catalog_sync_ok", 0) or 0) if sub else 0,
            "catalog_subscribe_last_sync_error": str(getattr(sub, "last_catalog_sync_error", "") or "") if sub else "",
            "mobile_position_subscribe_enabled": bool(int(getattr(sub, "mobile_position_enabled", 0) or 0) == 1) if sub else False,
            "mobile_position_interval_seconds": int(getattr(sub, "mobile_position_interval_seconds", 60) or 60) if sub else 60,
            "mobile_position_last_subscribe_at": (sub.last_mobile_position_subscribe_at if sub else None),
            "mobile_position_last_subscribe_ok": int(getattr(sub, "last_mobile_position_subscribe_ok", 0) or 0) if sub else 0,
            "mobile_position_last_subscribe_error": str(getattr(sub, "last_mobile_position_subscribe_error", "") or "") if sub else "",
        }
        )
    return {
        "items": items,
        "total": total,
        "skip": skip,
        "limit": limit,
        "stats": {
            "total": stats_total,
            "online": online_total,
            "offline": offline_total,
        },
    }


@router.get("/{device_id}/subscriptions/catalog")
async def get_catalog_subscription(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    if DeviceSubscription is None:
        raise HTTPException(status_code=501, detail="Device subscription feature not enabled: DeviceSubscription model missing")  # i18n
    asset_result = await db.execute(select(Asset).where(Asset.gb_id == device_id))
    asset = get_or_404(asset_result, detail="Asset not found")  # ORM查询结果空值判断
    if not current_user.is_superuser and asset.tenant_id != (current_user.tenant_id or "default"):
        raise HTTPException(status_code=403, detail="Permission denied")  # i18n
    sub = (
        await db.execute(select(DeviceSubscription).where(DeviceSubscription.asset_id == asset.id))
    ).scalars().first()
    cycle = int(getattr(sub, "catalog_cycle_seconds", 0) or 0) if sub else 0
    return {
        "device_id": device_id,
        "enabled": bool(cycle > 0),
        "cycle_seconds": cycle,
        "last_sync_at": (sub.last_catalog_sync_at if sub else None),
        "last_sync_ok": int(getattr(sub, "last_catalog_sync_ok", 0) or 0) if sub else 0,
        "last_sync_error": str(getattr(sub, "last_catalog_sync_error", "") or "") if sub else "",
    }


@router.put("/{device_id}/subscriptions/catalog")
async def update_catalog_subscription(
    device_id: str,
    payload: CatalogSubscriptionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    if DeviceSubscription is None:
        raise HTTPException(status_code=501, detail="Device subscription feature not enabled: DeviceSubscription model missing")  # i18n
    # enabled=False 显式关闭订阅（cycle 归零）；否则采用请求的周期（0-86400s）
    cycle = int(payload.cycle_seconds or 0) if payload.enabled else 0
    cycle = max(0, min(cycle, 24 * 60 * 60))
    asset_result = await db.execute(select(Asset).where(Asset.gb_id == device_id))
    asset = get_or_404(asset_result, detail="Asset not found")  # ORM查询结果空值判断
    if not current_user.is_superuser and asset.tenant_id != (current_user.tenant_id or "default"):
        raise HTTPException(status_code=403, detail="Permission denied")  # i18n

    sub = (
        await db.execute(select(DeviceSubscription).where(DeviceSubscription.asset_id == asset.id))
    ).scalars().first()
    if not sub:
        sub = DeviceSubscription(asset_id=asset.id, tenant_id=(asset.tenant_id or (current_user.tenant_id or "default")))
        db.add(sub)
    sub.catalog_cycle_seconds = cycle
    await db.commit()
    return {"device_id": device_id, "enabled": bool(cycle > 0), "cycle_seconds": cycle}


@router.get("/{device_id}/subscriptions/mobile-position")
async def get_mobile_position_subscription(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    if DeviceSubscription is None:
        raise HTTPException(status_code=501, detail="Device subscription feature not enabled: DeviceSubscription model missing")  # i18n
    asset = get_or_404(await db.execute(select(Asset).where(Asset.gb_id == device_id)), detail="Asset not found")  # ORM查询结果空值判断
    if not current_user.is_superuser and asset.tenant_id != (current_user.tenant_id or "default"):
        raise HTTPException(status_code=403, detail="Permission denied")  # i18n
    sub = (await db.execute(select(DeviceSubscription).where(DeviceSubscription.asset_id == asset.id))).scalars().first()
    enabled = bool(int(getattr(sub, "mobile_position_enabled", 0) or 0) == 1) if sub else False
    interval = int(getattr(sub, "mobile_position_interval_seconds", 60) or 60) if sub else 60
    renew = int(getattr(sub, "mobile_position_renew_seconds", 300) or 300) if sub else 300
    return {
        "device_id": device_id,
        "enabled": enabled,
        "interval_seconds": interval,
        "renew_seconds": renew,
        "last_subscribe_at": (sub.last_mobile_position_subscribe_at if sub else None),
        "last_subscribe_ok": int(getattr(sub, "last_mobile_position_subscribe_ok", 0) or 0) if sub else 0,
        "last_subscribe_error": str(getattr(sub, "last_mobile_position_subscribe_error", "") or "") if sub else "",
    }


@router.put("/{device_id}/subscriptions/mobile-position")
async def update_mobile_position_subscription(
    device_id: str,
    payload: MobilePositionSubscriptionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    if DeviceSubscription is None:
        raise HTTPException(status_code=501, detail="Device subscription feature not enabled: DeviceSubscription model missing")  # i18n
    asset = get_or_404(await db.execute(select(Asset).where(Asset.gb_id == device_id)), detail="Asset not found")  # ORM查询结果空值判断
    if not current_user.is_superuser and asset.tenant_id != (current_user.tenant_id or "default"):
        raise HTTPException(status_code=403, detail="Permission denied")  # i18n

    enabled = bool(payload.enabled)
    interval = max(5, min(int(payload.interval_seconds or 60), 3600))
    renew = max(30, min(int(payload.renew_seconds or 300), 3600))

    sub = (await db.execute(select(DeviceSubscription).where(DeviceSubscription.asset_id == asset.id))).scalars().first()
    if not sub:
        sub = DeviceSubscription(asset_id=asset.id, tenant_id=(asset.tenant_id or (current_user.tenant_id or "default")))
        db.add(sub)
    sub.mobile_position_enabled = 1 if enabled else 0
    sub.mobile_position_interval_seconds = interval
    sub.mobile_position_renew_seconds = renew

    if enabled:
        if not asset.ip_addr:
            raise HTTPException(status_code=500, detail="Device network info missing")  # i18n
        transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
        if transport is None:
            raise HTTPException(status_code=503, detail="Device signaling transport unavailable")  # i18n
        if not sip_commander_module.sip_commander:
            raise HTTPException(status_code=503, detail="SIP service not ready")  # i18n
        try:
            await sip_commander_module.sip_commander.send_mobile_position_subscribe(
                device_id=device_id,
                transport_info=((asset.ip_addr, asset.port), asset.transport, transport),
                interval=interval,
            )
            sub.last_mobile_position_subscribe_at = datetime.now(timezone.utc)
            sub.last_mobile_position_subscribe_ok = 1
            sub.last_mobile_position_subscribe_error = ""
        except Exception as e:
            sub.last_mobile_position_subscribe_at = datetime.now(timezone.utc)
            sub.last_mobile_position_subscribe_ok = 0
            sub.last_mobile_position_subscribe_error = str(e)[:500]

    await db.commit()
    return {"device_id": device_id, "enabled": enabled, "interval_seconds": interval, "renew_seconds": renew}

@router.put("/{device_id}/stream-mode")
async def update_device_stream_mode(
    device_id: str,
    payload: StreamModeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"]))
):
    stream_mode = (payload.stream_mode or "").strip().upper()
    if stream_mode not in {"GLOBAL", "AUTO", "UDP", "TCP_PASSIVE", "TCP_ACTIVE"}:
        raise HTTPException(status_code=400, detail="Invalid stream transport mode")  # i18n

    # 优化点：直接查需要的字段，利用 device_id 索引快速定位，不加载整个对象
    stmt = select(Asset.id, Asset.tenant_id).where(Asset.gb_id == device_id)
    result = await db.execute(stmt)
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Device not found")  # i18n

    asset_id, tenant_id = row
    if not current_user.is_superuser and tenant_id != (current_user.tenant_id or "default"):
        raise HTTPException(status_code=403, detail="Permission denied")  # i18n

    policy_result = await db.execute(select(AssetStreamPolicy).where(AssetStreamPolicy.asset_id == asset_id))
    policy = policy_result.scalars().first()
    if not policy:
        policy = AssetStreamPolicy(asset_id=asset_id, stream_mode=stream_mode)
        db.add(policy)
    else:
        policy.stream_mode = stream_mode
    await db.commit()
    return {"device_id": device_id, "stream_mode": stream_mode}


@router.put("/{device_id}/organization")
async def update_device_organization(
    device_id: str,
    payload: DeviceOrganizationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    """设置设备所属组织（分级分权）。"""
    stmt = select(Asset).where(Asset.gb_id == device_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
    result = await db.execute(stmt)
    asset = get_or_404(result, detail="Asset not found")  # ORM查询结果空值判断
    new_oid = (payload.organization_id or "").strip() or None
    if new_oid:
        org_stmt = select(Organization).where(Organization.id == new_oid)
        if not current_user.is_superuser:
            org_stmt = org_stmt.where(Organization.tenant_id == (current_user.tenant_id or "default"))
        org = (await db.execute(org_stmt)).scalars().first()
        if not org:
            raise HTTPException(status_code=400, detail="Organization not found or permission denied")  # i18n
    asset.organization_id = new_oid
    await db.commit()
    return {"device_id": device_id, "organization_id": asset.organization_id}


@router.post("")
async def create_device(
    payload: DeviceCreatePayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    """手动添加设备"""
    gb_id = payload.gb_id.strip()
    name = payload.name.strip()
    if not gb_id or not name:
        raise HTTPException(status_code=400, detail="Device ID and device name are required")  # i18n
    if len(gb_id) > 20:
        raise HTTPException(status_code=400, detail="Device ID length cannot exceed 20")  # i18n

    tenant_id = _tenant_id_for_user(current_user)

    # FIX R22-SEVERE: GB28181 gb_id 全局唯一，需跨租户查重；但需避免跨租户信息泄露
    # 原实现问题：查询所有租户的 gb_id 重复，错误消息"Device ID already exists"会泄露其他租户设备存在性
    # 修复方案：
    #   - 仍跨租户查重（GB28181 国标要求 gb_id 全局唯一）
    #   - 如果 duplicate 属于当前租户 → 400 "Device ID already exists"
    #   - 如果 duplicate 属于其他租户 → 403 "Permission denied"（不泄露具体信息）
    dup_stmt = select(Asset).where(Asset.gb_id == gb_id)
    duplicate = (await db.execute(dup_stmt)).scalars().first()
    if duplicate:
        dup_tenant = (getattr(duplicate, "tenant_id", None) or "default").strip() or "default"
        if dup_tenant == (tenant_id or "default").strip():
            # 当前租户已有此 gb_id
            raise HTTPException(status_code=400, detail="Device ID already exists")  # i18n
        # 其他租户已占用此 gb_id（GB28181 国标全局唯一），不泄露具体信息
        raise HTTPException(status_code=403, detail="Permission denied")  # i18n

    transport = (payload.transport or "UDP").strip().upper()
    if transport not in {"UDP", "TCP"}:
        raise HTTPException(status_code=400, detail="Transport protocol must be UDP or TCP")  # i18n

    # FIX: [2026-08-22 P0] Asset 模型无 domain 列 — 原写法把 hasattr 守卫放在值表达式里，
    # domain kwarg 仍被无条件传入 Asset() → TypeError → POST /devices 必 500（测试发现）。
    # 修复：仅当模型真正声明该列时才追加 kwarg。
    asset_kwargs: dict = {
        "gb_id": gb_id,
        "name": name,
        "decrypted_password": payload.password.strip() if payload.password else None,
        "ip_addr": payload.ip_addr.strip() if payload.ip_addr else None,
        "port": payload.port,
        "transport": transport,
        "manufacturer": payload.manufacturer.strip() if payload.manufacturer else None,
        "model": payload.model.strip() if payload.model else None,
        "firmware": payload.firmware.strip() if payload.firmware else None,
        "charset": payload.charset,
        "ssrc_check": payload.ssrc_check,
        "geo_coord_sys": payload.geo_coord_sys,
        "as_message_channel": payload.as_message_channel,
        "heartbeat_interval": payload.heartbeat_interval,
        "heartbeat_count": payload.heartbeat_count,
        "status": 0,
        "tenant_id": tenant_id,
    }
    if hasattr(Asset, "domain") and payload.domain:
        asset_kwargs["domain"] = payload.domain.strip()
    asset = Asset(**asset_kwargs)
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return {"status": "ok", "device": {"id": asset.id, "gb_id": asset.gb_id, "name": asset.name}}


@router.put("/{device_id}")
async def update_device(
    device_id: str,
    payload: DeviceUpdatePayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    """编辑设备信息"""
    stmt = select(Asset).where(Asset.gb_id == device_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
    result = await db.execute(stmt)
    asset = get_or_404(result, detail="Asset not found")  # ORM查询结果空值判断

    if payload.name is not None:
        asset.name = payload.name.strip()
    if payload.password is not None:
        asset.decrypted_password = payload.password.strip() or None
    if payload.ip_addr is not None:
        asset.ip_addr = payload.ip_addr.strip() or None
    if payload.port is not None:
        asset.port = payload.port
    if payload.transport is not None:
        transport = payload.transport.strip().upper()
        if transport not in {"UDP", "TCP"}:
            raise HTTPException(status_code=400, detail="Transport protocol must be UDP or TCP")  # i18n
        asset.transport = transport
    if payload.manufacturer is not None:
        asset.manufacturer = payload.manufacturer.strip() or None
    if payload.model is not None:
        asset.model = payload.model.strip() or None
    if payload.firmware is not None:
        asset.firmware = payload.firmware.strip() or None
    if payload.domain is not None:
        asset.domain = payload.domain.strip() or None
    if payload.charset is not None:
        asset.charset = payload.charset
    if payload.ssrc_check is not None:
        asset.ssrc_check = payload.ssrc_check
    if payload.geo_coord_sys is not None:
        asset.geo_coord_sys = payload.geo_coord_sys
    if payload.as_message_channel is not None:
        asset.as_message_channel = payload.as_message_channel
    if payload.heartbeat_interval is not None:
        asset.heartbeat_interval = payload.heartbeat_interval
    if payload.heartbeat_count is not None:
        asset.heartbeat_count = payload.heartbeat_count

    await db.commit()
    return {"status": "ok", "device": {"id": asset.id, "gb_id": asset.gb_id, "name": asset.name}}


@router.delete("/{device_id}")
async def delete_device(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    """删除单个设备"""
    stmt = select(Asset).where(Asset.gb_id == device_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
    result = await db.execute(stmt)
    asset = get_or_404(result, detail="Asset not found")  # ORM查询结果空值判断

    # FIX: [2026-07-13] 级联删除关联记录，避免 ForeignKeyViolationError。
    # FIX: [2026-07-14] 补充 AssetStreamPolicy 级联删除，日志确认 asset_stream_policies_asset_id_fkey 约束违反导致删除 500。
    # FIX [2026-09-03 P1]: 补充 records（录像记录）级联删除 —— records.resource_id/assets_id
    # 双外键引用，PostgreSQL/MySQL 上删除设备报 records_resource_id_fkey 违反（SQLite 默认
    # 不启用外键强制因此本地不报，服务器上报）。
    await db.execute(delete(Record).where(Record.asset_id == asset.id))
    await db.execute(delete(AssetMaintenance).where(AssetMaintenance.asset_id == asset.id))
    await db.execute(delete(AssetStreamPolicy).where(AssetStreamPolicy.asset_id == asset.id))
    await db.execute(delete(AssetStreamHealth).where(AssetStreamHealth.asset_id == asset.id))
    # 子资源（有 parent_id，如目录/子目录）先删，再删其余，兼容 MySQL 逐行外键检查
    await db.execute(delete(Resource).where(Resource.asset_id == asset.id).where(Resource.parent_id.isnot(None)))
    await db.execute(delete(Resource).where(Resource.asset_id == asset.id))
    await db.delete(asset)
    await db.commit()
    return {"status": "ok", "message": "Device deleted"}  # i18n


@router.post("/batch-delete")
async def batch_delete_devices(
    payload: BatchDeletePayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    """批量删除设备"""
    gb_ids = [str(x).strip() for x in payload.gb_ids if str(x).strip()]
    if not gb_ids:
        raise HTTPException(status_code=400, detail="Device ID list cannot be empty")  # i18n

    stmt = select(Asset).where(Asset.gb_id.in_(gb_ids))
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))

    assets = (await db.execute(stmt)).scalars().all()
    if not assets:
        return {"status": "ok", "deleted_count": 0}

    # FIX: [2026-07-16 P0] 原在循环内逐个执行 delete（N+1 查询），删除 N 个设备
    # 会发起 3N+1 次 DB 往返。NVR 共 IP 场景下删除 100+ 路设备会耗尽连接池。
    # 改为批量 IN 查询，将 3N+1 次往返降为 4 次。
    asset_ids = [asset.id for asset in assets]
    # FIX [2026-09-03 P1]: 级联删除录像记录（records 对 asset/resource 均有外键）
    await db.execute(delete(Record).where(Record.asset_id.in_(asset_ids)))
    await db.execute(delete(AssetMaintenance).where(AssetMaintenance.asset_id.in_(asset_ids)))
    await db.execute(delete(AssetStreamPolicy).where(AssetStreamPolicy.asset_id.in_(asset_ids)))
    await db.execute(delete(AssetStreamHealth).where(AssetStreamHealth.asset_id.in_(asset_ids)))
    await db.execute(delete(Resource).where(Resource.asset_id.in_(asset_ids)).where(Resource.parent_id.isnot(None)))
    await db.execute(delete(Resource).where(Resource.asset_id.in_(asset_ids)))
    # 批量删除 Asset
    await db.execute(delete(Asset).where(Asset.id.in_(asset_ids)))

    await db.commit()
    return {"status": "ok", "deleted_count": len(assets)}


@router.post("/{device_id}/blacklist")
async def blacklist_device(
    device_id: str,
    req: DeviceBlacklistRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    """
    拉黑设备：
    1. 可以选择是否拉黑设备的 IP
    2. 可以选择是否删除当前设备
    3. 可以选择是否删除该 IP 下的所有设备
    """
    tid = (_tenant_id_for_user(current_user) or "default").strip() or "default"
    op = current_user.username or "unknown"
    target_ip = req.ip.strip()
    if not target_ip:
        await safe_auth_audit(
            db,
            module="devices",
            action="blacklist_device",
            source="device_admin",
            operator=op,
            result="failed",
            tenant_id=tid,
            status_code=400,
            detail="invalid_ip",
            extra_summary=f"device_id={device_id}",
        )
        raise HTTPException(status_code=400, detail="Invalid IP address")

    ip_row_added = 0
    assets_removed = 0

    # 1. 黑名单 IP
    if req.blacklist_ip:
        # 检查是否已存在
        exist_stmt = select(IpBlacklist).where(IpBlacklist.ip == target_ip)
        res = await db.execute(exist_stmt)
        if not res.scalars().first():
            new_bl = IpBlacklist(ip=target_ip, reason=f"Blacklisted via device {device_id}")
            db.add(new_bl)
            await db.commit()
            ip_row_added = 1

            # 刷新内存黑名单缓存（server.py 中维护的集合）
            if hasattr(sip_server, "reload_ip_blacklist"):
                fire_and_forget(sip_server.reload_ip_blacklist())  # P0-16: 保存引用防 GC + 异常日志

    # 2. 删除该 IP 下所有设备
    if req.delete_all_from_ip:
        stmt = select(Asset).where(Asset.ip_addr == target_ip)
        if not current_user.is_superuser:
            stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
        res = await db.execute(stmt)
        assets = res.scalars().all()
        assets_removed = len(assets)
        # FIX: [2026-07-16 P0] 批量 IN 删除替代循环内逐条删除
        if assets:
            asset_ids = [a.id for a in assets]
            # FIX [2026-09-03 P1]: 级联删除录像记录（records 对 asset/resource 均有外键）
            await db.execute(delete(Record).where(Record.asset_id.in_(asset_ids)))
            await db.execute(delete(AssetMaintenance).where(AssetMaintenance.asset_id.in_(asset_ids)))
            await db.execute(delete(AssetStreamPolicy).where(AssetStreamPolicy.asset_id.in_(asset_ids)))
            await db.execute(delete(AssetStreamHealth).where(AssetStreamHealth.asset_id.in_(asset_ids)))
            await db.execute(delete(Resource).where(Resource.asset_id.in_(asset_ids)).where(Resource.parent_id.isnot(None)))
            await db.execute(delete(Resource).where(Resource.asset_id.in_(asset_ids)))
            await db.execute(delete(Asset).where(Asset.id.in_(asset_ids)))
        await db.commit()
    # 3. 仅删除当前设备
    elif req.delete_current:
        stmt = select(Asset).where(Asset.gb_id == device_id)
        if not current_user.is_superuser:
            stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
        res = await db.execute(stmt)
        asset = res.scalars().first()
        if asset:
            # FIX: [2026-07-13] 级联删除 AssetStreamHealth，避免外键约束违反
            # FIX [2026-09-03 P1]: 级联删除录像记录（records 外键）
            await db.execute(delete(Record).where(Record.asset_id == asset.id))
            await db.execute(delete(AssetMaintenance).where(AssetMaintenance.asset_id == asset.id))
            await db.execute(delete(AssetStreamHealth).where(AssetStreamHealth.asset_id == asset.id))
            await db.execute(delete(Resource).where(Resource.asset_id == asset.id).where(Resource.parent_id.isnot(None)))
            await db.execute(delete(Resource).where(Resource.asset_id == asset.id))
            await db.execute(delete(Asset).where(Asset.id == asset.id))
            await db.commit()
            assets_removed = 1

    await safe_auth_audit(
        db,
        module="devices",
        action="blacklist_device",
        source="device_admin",
        operator=op,
        result="success",
        tenant_id=tid,
        status_code=200,
        detail="ok",
        extra_summary=(
            f"device_id={device_id}; target_ip={target_ip}; blacklist_ip={bool(req.blacklist_ip)}; "
            f"ip_row_added={ip_row_added}; delete_all_from_ip={bool(req.delete_all_from_ip)}; "
            f"delete_current={bool(req.delete_current)}; assets_removed={assets_removed}"
        ),
    )
    return {"message": "Success"}


@router.post("/export")
async def export_devices(
    payload: DeviceExportPayload | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    批量导出设备配置（支持 CSV / JSON）。
    - 不传 gb_ids 时导出全部设备
    - include_channels=true 时同时导出通道信息
    """
    payload = payload or DeviceExportPayload()
    format_ = str(payload.format or "csv").lower()
    include_channels = bool(payload.include_channels)
    tenant_id = current_user.tenant_id or "default"

    # 查询设备
    stmt = select(Asset).order_by(Asset.gb_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == tenant_id)
    if payload.gb_ids:
        stmt = stmt.where(Asset.gb_id.in_(payload.gb_ids))
    # FIX R22-SEVERE: 在 SQL 层直接 limit，避免全表加载到内存再截断
    # 原实现问题：assets = (await db.execute(stmt)).scalars().all() 先加载所有设备到内存
    #   - 10万+ 设备时内存占用巨大，可能导致 OOM
    #   - 即使有 _EXPORT_MAX_ROWS 截断，也已先全量加载
    # 修复方案：查询时 limit(_EXPORT_MAX_ROWS + 1)，多查 1 行用于判断是否截断
    stmt = stmt.limit(_EXPORT_MAX_ROWS + 1)
    assets = (await db.execute(stmt)).scalars().all()

    if not assets:
        raise HTTPException(status_code=404, detail="Device not found")  # i18n

    # 导出端点全量加载无限制 → 添加 max_rows 限制，超过时截断并警告
    truncated = False
    if len(assets) > _EXPORT_MAX_ROWS:
        from loguru import logger
        logger.warning(f"Export truncated: {len(assets)} devices exceed max_rows={_EXPORT_MAX_ROWS}")
        assets = assets[:_EXPORT_MAX_ROWS]
        truncated = True

    # 查询通道
    asset_ids = [a.id for a in assets if a.id]
    channels_map: dict[str, list] = {}
    if include_channels and asset_ids:
        ch_stmt = select(Resource).where(Resource.asset_id.in_(asset_ids)).order_by(Resource.gb_id)
        channels = (await db.execute(ch_stmt)).scalars().all()
        for ch in channels:
            aid = str(getattr(ch, "asset_id", "") or "")
            if aid not in channels_map:
                channels_map[aid] = []
            channels_map[aid].append(ch)

    # 字段列表
    device_fields = [
        "gb_id", "name", "manufacturer", "model", "owner", "civil_code",
        "address", "ip_addr", "port", "transport", "status",
        "has_ptz", "stream_type", "max_stream", "alarm_method",
        "created_at",
    ]
    channel_fields = [
        "gb_id", "asset_id", "name", "manufacturer", "model", "owner",
        "civil_code", "address", "parent_gb_id", "node_type", "status",
        "longitude", "latitude", "has_ptz",
    ]

    if format_ == "json":
        items = []
        for a in assets:
            dev = {k: _safe_val(getattr(a, k, "")) for k in device_fields}
            dev["channels"] = [
                {k: _safe_val(getattr(c, k, "")) for k in channel_fields}
                for c in channels_map.get(a.id, [])
            ]
            items.append(dev)
        # 导出端点全量加载无限制 → 截断时在 JSON 中添加警告
        export_data = {"total": len(items), "devices": items}
        if truncated:
            export_data["warning"] = f"Result truncated to {_EXPORT_MAX_ROWS} devices"
        content = _json.dumps(export_data, ensure_ascii=False, indent=2)
        filename = f"devices_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        return StreamingResponse(
            iter([content]),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    else:
        rows = []
        for a in assets:
            dev = {k: _safe_val(getattr(a, k, "")) for k in device_fields}
            if include_channels and channels_map.get(a.id):
                for ch in channels_map[a.id]:
                    row = dict(dev)
                    row.update({f"ch_{k}": _safe_val(getattr(ch, k, "")) for k in channel_fields})
                    rows.append(row)
            else:
                rows.append(dev)

        # 导出端点全量加载无限制 → CSV 行数也受 max_rows 限制
        if len(rows) > _EXPORT_MAX_ROWS:
            rows = rows[:_EXPORT_MAX_ROWS]

        buf = io.StringIO()
        if rows:
            writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        buf.seek(0)
        filename = f"devices_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        # 导出端点全量加载无限制 → 截断时在响应头添加警告
        if truncated:
            headers["X-Truncation-Warning"] = f"Result truncated to {_EXPORT_MAX_ROWS} devices"
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv",
            headers=headers,
        )


@router.post("/assets/cleanup-dummy")
async def cleanup_dummy_assets(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    """
    将所有 DUMMY* 虚拟设备资产的引用资源迁移到任意真实资产，
    然后删除 DUMMY* 资产本身，使行政区树中的"虚拟设备"节点消失。
    """
    tenant_id = _tenant_id_for_user(current_user)

    dummy_stmt = select(Asset).where(
        Asset.tenant_id == tenant_id,
        Asset.gb_id.like("DUMMY%"),
    )
    dummy_assets = (await db.execute(dummy_stmt)).scalars().all()
    dummy_ids = [a.id for a in dummy_assets if a and a.id]
    if not dummy_ids:
        return {"status": "ok", "dummy_deleted": 0, "resources_reassigned": 0}

    # 选择一个替换的真实资产（优先非 DUMMY，避免迁移到另一个虚拟资产）
    replace_stmt = (
        select(Asset)
        .where(Asset.tenant_id == tenant_id, ~Asset.gb_id.like("DUMMY%"))
        .order_by(desc(Asset.updated_at), desc(Asset.created_at))
        .limit(1)
    )
    replace_asset = (await db.execute(replace_stmt)).scalars().first()
    if not replace_asset:
        raise HTTPException(status_code=400, detail="No replaceable real asset found, cannot delete virtual device")  # i18n

    # 迁移资源外键
    res = await db.execute(
        update(Resource)
        .where(Resource.asset_id.in_(dummy_ids))
        .values(asset_id=replace_asset.id)
    )
    resources_reassigned = int(getattr(res, "rowcount", 0) or 0)

    # 删除虚拟资产
    del_stmt = select(Asset.id).where(Asset.id.in_(dummy_ids))
    del_ids = [r[0] for r in (await db.execute(del_stmt)).all() if r and r[0]]
    if del_ids:
        # FIX: [2026-07-13] 级联删除 AssetStreamHealth，避免外键约束违反
        await db.execute(delete(AssetStreamHealth).where(AssetStreamHealth.asset_id.in_(del_ids)))
        await db.execute(delete(Asset).where(Asset.id.in_(del_ids)))
    await db.commit()
    return {"status": "ok", "dummy_deleted": len(dummy_ids), "resources_reassigned": resources_reassigned}
