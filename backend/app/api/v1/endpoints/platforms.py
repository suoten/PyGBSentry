"""上级平台（级联）CRUD API；级联目录推送范围（直播推流转发可选通道）。"""
from fastapi import Query, APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, or_, desc, func
import json
from loguru import logger

from app.db.session import get_db
from app.models.platform import ParentPlatform
from app.models.platform_runtime import PlatformRuntime
from app.models.platform_catalog_resource import PlatformCatalogResource
from app.models.resource import Resource
from app.models.asset import Asset
from app.models.push_channel import PushChannel
from app.models.access_source import AccessSource
from app.models.user import User
from app.api import deps
from app.api.deps import get_or_404
import app.services.platform_service as platform_service_mod
from app.core.config import settings
from app.services.auth_audit import safe_auth_audit

router = APIRouter()


def _escape_ilike(val: str) -> str:
    return val.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _audit_tid(user: User) -> str:
    return (user.tenant_id or "default").strip() or "default"

@router.get("/server_config")
async def get_platform_server_config(
    current_user: User = Depends(deps.require_roles(["owner", "admin"])),
):
    return {
        "sip_id": settings.SIP_ID,
        "sip_domain": settings.SIP_DOMAIN,
        "sip_ip": settings.SIP_IP,
        "sip_port": settings.SIP_PORT,
        "sip_transport": settings.SIP_TRANSPORT,
        "backend_public_host": settings.BACKEND_PUBLIC_HOST,
        "backend_public_port": settings.BACKEND_PUBLIC_PORT,
    }


@router.get("/exist/{server_gb_id}")
async def platform_exist_check(
    server_gb_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    gb_id = (server_gb_id or "").strip()
    if not gb_id:
        raise HTTPException(status_code=400, detail="server_gb_id is required")  # i18n
    stmt = select(ParentPlatform).where(ParentPlatform.server_gb_id == gb_id)
    if not current_user.is_superuser:
        stmt = stmt.where(ParentPlatform.tenant_id == (current_user.tenant_id or "default"))
    row = (await db.execute(stmt)).scalars().first()
    return {"exists": bool(row is not None), "server_gb_id": gb_id}

def _load_runtime_dict(rt: PlatformRuntime | None) -> dict:
    if not rt or not rt.data:
        return {}
    try:
        loaded = json.loads(rt.data)
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        logger.warning("Failed to parse platform runtime JSON")
        return {}


def _normalize_transport(value: str | None) -> str:
    transport = (value or "UDP").strip().upper()
    return transport if transport in {"UDP", "TCP"} else "UDP"


@router.get("/channels/flat")
async def list_platform_shareable_channels_flat(
    channel_type: int = Query(0, ge=0),
    keyword: str = "",
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=10000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    limit = max(1, min(int(limit or 200), 5000))
    skip = max(0, int(skip or 0))
    t = int(channel_type or 0)
    tenant_id = current_user.tenant_id or "default"

    items: list[dict] = []
    kw = (keyword or "").strip()

    if t == 0:
        stmt = select(Resource, Asset).join(Asset, Asset.id == Resource.asset_id).where(Resource.node_type == "channel")
        if kw:
            stmt = stmt.where(or_(Resource.gb_id.ilike(f"%{_escape_ilike(kw)}%"), Resource.name.ilike(f"%{_escape_ilike(kw)}%"), Asset.gb_id.ilike(f"%{_escape_ilike(kw)}%"), Asset.name.ilike(f"%{_escape_ilike(kw)}%")))
        if not current_user.is_superuser:
            stmt = stmt.where(Asset.tenant_id == tenant_id)
        # C-15 分页total应返回总条数而非当前页条数
        count_stmt = select(func.count()).select_from(Resource).join(Asset, Asset.id == Resource.asset_id).where(Resource.node_type == "channel")
        if kw:
            count_stmt = count_stmt.where(or_(Resource.gb_id.ilike(f"%{_escape_ilike(kw)}%"), Resource.name.ilike(f"%{_escape_ilike(kw)}%"), Asset.gb_id.ilike(f"%{_escape_ilike(kw)}%"), Asset.name.ilike(f"%{_escape_ilike(kw)}%")))
        if not current_user.is_superuser:
            count_stmt = count_stmt.where(Asset.tenant_id == tenant_id)
        total = (await db.execute(count_stmt)).scalar() or 0
        stmt = stmt.order_by(Resource.gb_id.asc(), Resource.id.asc()).offset(skip).limit(limit)
        rows = (await db.execute(stmt)).all()
        for res, asset in rows:
            items.append(
                {
                    "id": res.id,
                    "gb_id": res.gb_id,
                    "name": res.name,
                    "status": res.status,
                    "channel_type": 0,
                    "device_id": asset.gb_id,
                    "device_name": asset.name,
                }
            )
        return {"items": items, "total": total}

    if t == 1:
        stmt = (
            select(Resource, PushChannel, AccessSource)
            .join(PushChannel, PushChannel.gb_resource_id == Resource.id)
            .join(AccessSource, AccessSource.id == PushChannel.id)
            .where(PushChannel.gb_enabled == True)
        )
        if kw:
            stmt = stmt.where(or_(Resource.gb_id.ilike(f"%{_escape_ilike(kw)}%"), Resource.name.ilike(f"%{_escape_ilike(kw)}%"), AccessSource.name.ilike(f"%{_escape_ilike(kw)}%")))
        if not current_user.is_superuser:
            stmt = stmt.where(PushChannel.tenant_id == tenant_id)
        # C-15 分页total应返回总条数而非当前页条数
        count_stmt = (
            select(func.count())
            .select_from(Resource)
            .join(PushChannel, PushChannel.gb_resource_id == Resource.id)
            .join(AccessSource, AccessSource.id == PushChannel.id)
            .where(PushChannel.gb_enabled == True)
        )
        if kw:
            count_stmt = count_stmt.where(or_(Resource.gb_id.ilike(f"%{_escape_ilike(kw)}%"), Resource.name.ilike(f"%{_escape_ilike(kw)}%"), AccessSource.name.ilike(f"%{_escape_ilike(kw)}%")))
        if not current_user.is_superuser:
            count_stmt = count_stmt.where(PushChannel.tenant_id == tenant_id)
        total = (await db.execute(count_stmt)).scalar() or 0
        stmt = stmt.order_by(Resource.gb_id.asc(), Resource.id.asc()).offset(skip).limit(limit)
        rows = (await db.execute(stmt)).all()
        for res, pc, src in rows:
            items.append(
                {
                    "id": res.id,
                    "gb_id": res.gb_id,
                    "name": res.name,
                    "status": res.status,
                    "channel_type": 1,
                    "source_id": src.id,
                    "source_name": src.name,
                    "protocol": "RTMP",
                }
            )
        return {"items": items, "total": total}

    if t == 2:
        stmt = (
            select(Resource, AccessSource)
            .join(AccessSource, AccessSource.gb_resource_id == Resource.id)
            .where(AccessSource.gb_enabled == True)
            .where(AccessSource.protocol.in_(["RTSP", "ONVIF", "SDK"]))
        )
        if kw:
            stmt = stmt.where(or_(Resource.gb_id.ilike(f"%{_escape_ilike(kw)}%"), Resource.name.ilike(f"%{_escape_ilike(kw)}%"), AccessSource.name.ilike(f"%{_escape_ilike(kw)}%")))
        if not current_user.is_superuser:
            stmt = stmt.where(AccessSource.tenant_id == tenant_id)
        # C-15 分页total应返回总条数而非当前页条数
        count_stmt = (
            select(func.count())
            .select_from(Resource)
            .join(AccessSource, AccessSource.gb_resource_id == Resource.id)
            .where(AccessSource.gb_enabled == True)
            .where(AccessSource.protocol.in_(["RTSP", "ONVIF", "SDK"]))
        )
        if kw:
            count_stmt = count_stmt.where(or_(Resource.gb_id.ilike(f"%{_escape_ilike(kw)}%"), Resource.name.ilike(f"%{_escape_ilike(kw)}%"), AccessSource.name.ilike(f"%{_escape_ilike(kw)}%")))
        if not current_user.is_superuser:
            count_stmt = count_stmt.where(AccessSource.tenant_id == tenant_id)
        total = (await db.execute(count_stmt)).scalar() or 0
        stmt = stmt.order_by(Resource.gb_id.asc(), Resource.id.asc()).offset(skip).limit(limit)
        rows = (await db.execute(stmt)).all()
        for res, src in rows:
            items.append(
                {
                    "id": res.id,
                    "gb_id": res.gb_id,
                    "name": res.name,
                    "status": res.status,
                    "channel_type": 2,
                    "source_id": src.id,
                    "source_name": src.name,
                    "protocol": src.protocol,
                }
            )
        return {"items": items, "total": total}

    raise HTTPException(status_code=400, detail="channel_type only supports 0/1/2")  # i18n


def _get_keepalive_threshold() -> int:
    try:
        v = settings.SIP_PLATFORM_KEEPALIVE_MISS_THRESHOLD
    except Exception:
        v = 3
    return max(1, v)


def _build_diagnosis(p: ParentPlatform, runtime: dict) -> dict:  # N-15 诊断信息国际化
    items = []
    now_online = bool(getattr(p, "is_online", False))
    enabled = bool(getattr(p, "enable", True))
    miss_count = 0
    try:
        miss_count = int(runtime.get("keepalive.miss_count") or 0)
    except Exception:
        miss_count = 0
    threshold = _get_keepalive_threshold()

    last_register_code = str(runtime.get("register.last_status_code") or "").strip()
    last_register_error = str(runtime.get("register.last_error") or "").strip()
    last_register_at = str(runtime.get("register.last_ok_at") or runtime.get("register.last_failed_at") or runtime.get("register.last_sent_at") or "").strip()

    last_catalog_ok = runtime.get("catalog.last_push_ok")
    last_catalog_error = str(runtime.get("catalog.last_push_error") or "").strip()
    last_catalog_at = str(runtime.get("catalog.last_push_finished_at") or runtime.get("catalog.last_push_started_at") or "").strip()
    ack_ok = runtime.get("catalog.ack_ok_count")
    ack_total = runtime.get("catalog.ack_total")

    if not enabled:
        items.append(
            {
                "key": "platform.disabled",
                "level": "warn",
                "title": "平台已禁用",
                "detail": "该上级平台当前为禁用状态，系统不会自动注册与保活。",
                "suggestion": "如需级联生效，请在列表中启用该平台。",
            }
        )

    if not now_online:
        if last_register_code and last_register_code != "200":
            items.append(
                {
                    "key": "register.failed",
                    "level": "error",
                    "title": "Registration Failed",
                    "detail": f"Last registration status code: {last_register_code}; time: {last_register_at or '—'}; reason: {last_register_error or '—'}",
                    "suggestion": "Check upstream platform IP/port, GB ID/password, network connectivity and transport (UDP/TCP), then click 'Register Now'.",
                }
            )
        else:
            items.append(
                {
                    "key": "register.unknown",
                    "level": "warn",
                    "title": "Offline (No Successful Registration Observed)",
                    "detail": f"Last registration time: {last_register_at or '—'}",
                    "suggestion": "Click 'Register Now' to trigger a registration; if still offline, check upstream platform address and network.",
                }
            )
    else:
        if last_register_code != "200":
            items.append(
                {
                    "key": "register.not200",
                    "level": "warn",
                    "title": "Online but Registration Status Abnormal",
                    "detail": f"Last registration status code: {last_register_code or '—'}; time: {last_register_at or '—'}; reason: {last_register_error or '—'}",
                    "suggestion": "Click 'Register Now' to refresh registration status, and check upstream platform authentication config.",
                }
            )

    if now_online:
        if miss_count >= threshold:
            items.append(
                {
                    "key": "keepalive.miss_threshold",
                    "level": "error",
                    "title": "Keepalive Misses Exceeded Threshold",
                    "detail": f"miss_count={miss_count}, threshold={threshold}",
                    "suggestion": "Check upstream platform reachability, firewall/port mapping, UDP/TCP transport; switch transport or adjust threshold if needed.",
                }
            )
        elif miss_count >= max(1, threshold - 1):
            items.append(
                {
                    "key": "keepalive.miss_warn",
                    "level": "warn",
                    "title": "Keepalive Miss Risk Detected",
                    "detail": f"miss_count={miss_count}, threshold={threshold}",
                    "suggestion": "Check network jitter and NAT/firewall policies; observe if keepalive ack is stable.",
                }
            )

    inbound_reg_ok_at = str(runtime.get("inbound.register.last_ok_at") or "").strip()
    inbound_reg_addr = str(runtime.get("inbound.register.last_addr") or "").strip()
    inbound_reg_transport = str(runtime.get("inbound.register.last_transport") or "").strip()
    inbound_reg_contact = str(runtime.get("inbound.register.last_contact") or "").strip()
    inbound_reg_resp_contact = str(runtime.get("inbound.register.last_resp_contact") or "").strip()
    inbound_keepalive_at = str(runtime.get("inbound.keepalive.last_at") or "").strip()
    inbound_keepalive_addr = str(runtime.get("inbound.keepalive.last_addr") or "").strip()
    inbound_keepalive_transport = str(runtime.get("inbound.keepalive.last_transport") or "").strip()
    if inbound_reg_ok_at:
        items.append(
            {
                "key": "inbound.register.seen",
                "level": "info",
                "title": "Inbound Registration Received",
                "detail": f"Last inbound REGISTER OK at: {inbound_reg_ok_at}; source: {inbound_reg_addr or '—'}; transport: {inbound_reg_transport or '—'}; Contact: {inbound_reg_contact or '—'}; resp Contact: {inbound_reg_resp_contact or '—'}",
                "suggestion": "If upstream platform still shows offline, prioritize: whether upstream received 200 (check cascade logs), NAT reply port mismatch, upstream timeout window too small.",
            }
        )
    if inbound_keepalive_at:
        items.append(
            {
                "key": "inbound.keepalive.seen",
                "level": "info",
                "title": "Inbound Keepalive Received",
                "detail": f"Last inbound Keepalive at: {inbound_keepalive_at}; source: {inbound_keepalive_addr or '—'}; transport: {inbound_keepalive_transport or '—'}",
                "suggestion": "If local side receives peer keepalive but peer still judges offline, usually the peer cannot receive local response (network/port/firewall/NAT reply path).",
            }
        )

    try:
        local_sip_port = settings.SIP_PORT
    except Exception:
        local_sip_port = 0
    if local_sip_port and int(getattr(p, "server_port", 0) or 0) != 0:
        items.append(
            {
                "key": "sip.port.hint",
                "level": "info",
                "title": "SIP Listening Port Hint",
                "detail": f"Local SIP listening port: {local_sip_port}; upstream platform configured port: {int(getattr(p, 'server_port', 0) or 0)}",
                "suggestion": "If cascading upstream->local (local as subordinate), ensure the target port filled by upstream matches the actual local listening port, and UDP/TCP and firewall rules are consistent.",
            }
        )

    rtt_ms = runtime.get("register.last_rtt_ms")
    if rtt_ms is not None:
        items.append(
            {
                "key": "register.rtt",
                "level": "info",
                "title": "Registration Round-Trip Time",
                "detail": f"Last REGISTER response RTT: {rtt_ms}ms",
                "suggestion": "If upstream platform occasionally goes offline with high RTT, prioritize checking DB lock wait/CPU/network jitter, and enable SIP_TRACE to check for timeouts.",
            }
        )

    sub_catalog_active = runtime.get("subscribe.Catalog.active")
    sub_catalog_expires_at = str(runtime.get("subscribe.Catalog.expires_at") or "").strip()
    if now_online and sub_catalog_active is False:
        items.append(
            {
                "key": "subscribe.catalog.missing",
                "level": "warn",
                "title": "Catalog Subscription Not Established",
                "detail": "Upstream platform has not established SUBSCRIBE for Catalog events; catalog push may need to be triggered by peer Catalog Query.",
                "suggestion": "For automatic push, enable 'Push/Subscribe' capability on upstream platform, or click 'Push Channels' on this platform.",
            }
        )
    if now_online and sub_catalog_active is True and sub_catalog_expires_at:
        items.append(
            {
                "key": "subscribe.catalog.active",
                "level": "info",
                "title": "Catalog Subscription Active",
                "detail": f"Catalog subscription expires at: {sub_catalog_expires_at}",
                "suggestion": "If catalog still not synced, check Catalog push batch ACK and peer response codes.",
            }
        )

    if last_catalog_error:
        items.append(
            {
                "key": "catalog.error",
                "level": "error",
                "title": "Catalog Push Error",
                "detail": f"Time: {last_catalog_at or '—'}; reason: {last_catalog_error}",
                "suggestion": "Click 'Push Catalog' to retry; for multi-batch pushes, observe ack progress and status codes.",
            }
        )
    else:
        if last_catalog_ok is False:
            items.append(
                {
                    "key": "catalog.not_ok",
                    "level": "warn",
                    "title": "Catalog Push Status Unknown",
                    "detail": f"Time: {last_catalog_at or '—'}; ack: {ack_ok or 0}/{ack_total or 0}",
                    "suggestion": "Click 'Push Catalog' to trigger a catalog push to verify the cascade link.",
                }
            )

    level_order = {"error": 3, "warn": 2, "info": 1, "ok": 0}
    max_level = "ok"
    for it in items:
        lv = str(it.get("level") or "info")
        if level_order.get(lv, 1) > level_order.get(max_level, 0):
            max_level = lv

    return {"platform_id": p.id, "level": max_level, "items": items}


class PlatformCreate(BaseModel):
    name: str
    server_gb_id: str
    server_ip: str
    server_port: int = 5060
    transport: str = "UDP"
    client_gb_id: str
    password: str = ""
    register_interval: int = 3600
    keepalive_interval: int = 60
    enable: bool = True


class PlatformUpdate(BaseModel):
    name: str | None = None
    server_gb_id: str | None = None
    server_ip: str | None = None
    server_port: int | None = None
    transport: str | None = None
    client_gb_id: str | None = None
    password: str | None = None
    register_interval: int | None = None
    keepalive_interval: int | None = None
    catalog_batch_size: int | None = None
    catalog_push_delay_seconds: int | None = None
    enable: bool | None = None


@router.get("")
async def list_platforms(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    tenant_id = current_user.tenant_id or "default"
    result = await db.execute(
        select(ParentPlatform, PlatformRuntime)
        .outerjoin(
            PlatformRuntime,
            (PlatformRuntime.platform_id == ParentPlatform.id) & (PlatformRuntime.tenant_id == ParentPlatform.tenant_id),
        )
        .where(ParentPlatform.tenant_id == tenant_id)
        .order_by(ParentPlatform.name)
    )
    rows = result.all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "server_gb_id": p.server_gb_id,
            "server_ip": p.server_ip,
            "server_port": p.server_port,
            "transport": _normalize_transport(getattr(p, "transport", None)),
            "client_gb_id": p.client_gb_id,
            "tenant_id": p.tenant_id,
            "is_online": p.is_online,
            "register_interval": p.register_interval,
            "keepalive_interval": p.keepalive_interval,
            "catalog_batch_size": getattr(p, "catalog_batch_size", 0) or 0,
            "catalog_push_delay_seconds": getattr(p, "catalog_push_delay_seconds", 0) or 0,
            "enable": p.enable,
            "runtime": _load_runtime_dict(rt),
        }
        for (p, rt) in rows
    ]

@router.get("/{platform_id}/runtime")
async def get_platform_runtime(
    platform_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    tenant_id = current_user.tenant_id or "default"
    result = await db.execute(
        select(ParentPlatform, PlatformRuntime)
        .outerjoin(
            PlatformRuntime,
            (PlatformRuntime.platform_id == ParentPlatform.id) & (PlatformRuntime.tenant_id == ParentPlatform.tenant_id),
        )
        .where(ParentPlatform.id == platform_id, ParentPlatform.tenant_id == tenant_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Parent platform not found")  # i18n
    p, rt = row
    return {
        "platform": {
            "id": p.id,
            "name": p.name,
            "server_gb_id": p.server_gb_id,
            "server_ip": p.server_ip,
            "server_port": p.server_port,
            "transport": _normalize_transport(getattr(p, "transport", None)),
            "client_gb_id": p.client_gb_id,
            "tenant_id": p.tenant_id,
            "is_online": p.is_online,
            "register_interval": p.register_interval,
            "keepalive_interval": p.keepalive_interval,
            "catalog_batch_size": getattr(p, "catalog_batch_size", 0) or 0,
            "catalog_push_delay_seconds": getattr(p, "catalog_push_delay_seconds", 0) or 0,
            "enable": p.enable,
        },
        "runtime": _load_runtime_dict(rt),
    }


@router.get("/inbound/diagnosis")
async def get_inbound_cascade_diagnosis(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    入站级联诊断：查看有哪些下级平台向本端发起了注册，以及SIP链路状态。
    用于排查"其他平台注册到我这里但注册不上"的问题。
    """
    tenant_id = current_user.tenant_id or "default"

    # 1. 从 sip_trace_events 表查最近的入站注册事件
    from app.models.sip_trace_event import SipTraceEvent

    register_events_stmt = (
        select(SipTraceEvent)
        .where(SipTraceEvent.tenant_id == tenant_id)
        .where(
            or_(
                SipTraceEvent.event == "register_received",
                SipTraceEvent.event == "register_401_challenge",
                SipTraceEvent.event == "register_ok_platform",
                SipTraceEvent.event == "register_ok_device",
                SipTraceEvent.event == "register_auth_failed",
            )
        )
        .order_by(desc(SipTraceEvent.created_at))
        .limit(200)
    )
    register_result = await db.execute(register_events_stmt)
    register_events = register_result.scalars().all()

    # 2. 从 PlatformRuntime 查入站运行时数据
    runtime_stmt = select(PlatformRuntime).where(PlatformRuntime.tenant_id == tenant_id)
    runtime_result = await db.execute(runtime_stmt)
    runtimes = runtime_result.scalars().all()

    inbound_platforms = []
    for rt in runtimes:
        if not rt.data:
            continue
        try:
            data = json.loads(rt.data)
        except Exception:
            continue
        inbound_data = data.get("inbound", {})
        if not inbound_data:
            continue
        reg_ok_at = inbound_data.get("register.last_ok_at") or ""
        reg_addr = inbound_data.get("register.last_addr") or ""
        reg_transport = inbound_data.get("register.last_transport") or ""
        reg_auth = inbound_data.get("register.auth") or ""
        reg_contact = inbound_data.get("register.last_contact") or ""
        reg_resp_contact = inbound_data.get("register.last_resp_contact") or ""
        reg_gb_id = inbound_data.get("register.last_gb_id") or ""
        keepalive_at = inbound_data.get("keepalive.last_at") or ""
        keepalive_addr = inbound_data.get("keepalive.last_addr") or ""
        if not reg_ok_at and not reg_addr:
            continue
        inbound_platforms.append({
            "platform_id": rt.platform_id,
            "register": {
                "last_ok_at": reg_ok_at,
                "last_addr": reg_addr,
                "last_transport": reg_transport,
                "auth": reg_auth,
                "last_contact": reg_contact,
                "resp_contact": reg_resp_contact,
                "last_gb_id": reg_gb_id,
            },
            "keepalive": {"last_at": keepalive_at, "last_addr": keepalive_addr},
            "catalog": {
                "query_received_at": data.get("inbound.catalog.query_received_at") or "",
                "query_sn": data.get("inbound.catalog.query_sn") or "",
            },
        })

    # 3. 按 trace_id 分组
    trace_by_trace_id = {}
    for evt in register_events:
        tid = evt.trace_id or "unknown"
        if tid not in trace_by_trace_id:
            trace_by_trace_id[tid] = []
        try:
            payload = json.loads(evt.payload) if evt.payload else {}
        except Exception:
            payload = {}
        trace_by_trace_id[tid].append({
            "event": evt.event,
            "created_at": str(evt.created_at) if evt.created_at else "",
            "payload": payload,
        })

    # 4. 生成诊断结论
    diagnostics = []

    if not inbound_platforms:
        diagnostics.append({
            "level": "error",
            "key": "no_inbound_register",
            "title": "No inbound registrations detected",  # i18n
            "detail": "No subordinate platform has registered recently. Possible causes: 1) Subordinate platform not sending REGISTER; 2) SIP link blocked (firewall/port); 3) REGISTER not reaching this side.",  # i18n
            "suggestion": "On the subordinate platform: a) Verify target IP/port points to this side; b) Ensure SIP port (5060) is open in firewall; c) Run tcpdump on this server: tcpdump -i any -n 'port 5060'.",  # i18n
        })
    else:
        diagnostics.append({
            "level": "info",
            "key": "inbound_register_seen",
            "title": f"{len(inbound_platforms)} inbound registration(s) detected",  # W-13 hardcoded Chinese→English
            "detail": "A subordinate platform has registered to this side.",  # W-13 hardcoded Chinese→English
            "suggestion": "Check the 'Inbound Platform List' below to confirm whether registration succeeded.",  # W-13 hardcoded Chinese→English
        })

    failed_events = [e for e in register_events if e.event == "register_auth_failed"]
    if failed_events:
        try:
            latest_fail = json.loads(failed_events[0].payload) if failed_events[0].payload else {}
        except Exception:
            latest_fail = {}
        diagnostics.append({
            "level": "error",
            "key": "register_auth_failed",
            "title": f"{len(failed_events)} registration auth failure(s) detected",  # W-13 hardcoded Chinese→English
            "detail": f"Latest failure: {failed_events[0].created_at}, reason: {latest_fail.get('reason', 'unknown')}",  # W-13 hardcoded Chinese→English
            "suggestion": "Common causes: 1) Password mismatch; 2) Realm mismatch; 3) Username/GB ID mismatch.",  # W-13 hardcoded Chinese→English
        })

    ok_events = [e for e in register_events if e.event in ("register_ok_platform", "register_ok_device")]
    received_count = len([e for e in register_events if e.event == "register_received"])
    challenge_count = len([e for e in register_events if e.event == "register_401_challenge"])
    if received_count > 0 and len(ok_events) == 0:
        diagnostics.append({
            "level": "error",
            "key": "no_200_ok",
            "title": "REGISTER Received but No 200 OK Returned",
            "detail": f"Received {received_count} REGISTER(s), {challenge_count} 401 challenge(s), but no successful registration record.",
            "suggestion": "Check if the subordinate GB ID exists in the ParentPlatform table (server_gb_id or client_gb_id field), and whether the platform is enabled (enable=true).",
        })

    sip_ip = settings.SIP_IP
    sip_port = settings.SIP_PORT
    sip_domain = settings.SIP_DOMAIN
    sip_id = settings.SIP_ID

    if sip_ip in ("0.0.0.0", "") or not sip_ip:
        diagnostics.append({
            "level": "warn",
            "key": "sip_ip_not_public",
            "title": "SIP_IP is configured as 0.0.0.0",  # W-13 hardcoded Chinese→English
            "detail": "SIP_IP=0.0.0.0 means listening on all addresses, but the subordinate platform must use the actual reachable address of this side.",  # W-13 hardcoded Chinese→English
            "suggestion": "If the subordinate platform is not on the same internal network, ensure this side has a public IP or correct NAT mapping.",  # W-13 hardcoded Chinese→English
        })

    if not sip_domain:
        diagnostics.append({
            "level": "warn",
            "key": "sip_domain_empty",
            "title": "SIP_DOMAIN is empty",  # W-13 hardcoded Chinese→English
            "detail": "SIP_DOMAIN is the realm for Digest Auth and must not be empty.",  # W-13 hardcoded Chinese→English
            "suggestion": "Set SIP_DOMAIN in .env (usually the area code), and ensure the subordinate platform's realm config matches.",  # W-13 hardcoded Chinese→English
        })

    return {
        "sip_config": {
            "sip_id": sip_id,
            "sip_domain": sip_domain,
            "sip_ip": sip_ip,
            "sip_port": sip_port,
        },
        "inbound_platforms": inbound_platforms,
        "recent_trace_events_count": {
            "register_received": len([e for e in register_events if e.event == "register_received"]),
            "register_401_challenge": len([e for e in register_events if e.event == "register_401_challenge"]),
            "register_ok_platform": len([e for e in register_events if e.event == "register_ok_platform"]),
            "register_ok_device": len([e for e in register_events if e.event == "register_ok_device"]),
            "register_auth_failed": len([e for e in register_events if e.event == "register_auth_failed"]),
        },
        "recent_trace_by_trace_id": trace_by_trace_id,
        "diagnostics": diagnostics,
    }


@router.get("/{platform_id}/diagnosis")
async def get_platform_diagnosis(
    platform_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    tenant_id = current_user.tenant_id or "default"
    result = await db.execute(
        select(ParentPlatform, PlatformRuntime)
        .outerjoin(
            PlatformRuntime,
            (PlatformRuntime.platform_id == ParentPlatform.id) & (PlatformRuntime.tenant_id == ParentPlatform.tenant_id),
        )
        .where(ParentPlatform.id == platform_id, ParentPlatform.tenant_id == tenant_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Parent platform not found")  # i18n
    p, rt = row
    runtime = _load_runtime_dict(rt)
    diagnosis = _build_diagnosis(p, runtime)
    diagnosis["platform"] = {
        "id": p.id,
        "name": p.name,
        "server_gb_id": p.server_gb_id,
        "server_ip": p.server_ip,
        "server_port": p.server_port,
        "transport": _normalize_transport(getattr(p, "transport", None)),
        "client_gb_id": p.client_gb_id,
        "tenant_id": p.tenant_id,
        "is_online": p.is_online,
        "enable": p.enable,
    }
    diagnosis["runtime"] = runtime
    diagnosis["keepalive_threshold"] = _get_keepalive_threshold()
    return diagnosis


@router.post("/{platform_id}/actions/register")
async def trigger_platform_register(
    platform_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("devices.manage")),  # 角色检查→权限码检查
):
    tenant_id = current_user.tenant_id or "default"
    p = (
        await db.execute(
            select(ParentPlatform).where(
                ParentPlatform.id == platform_id,
                ParentPlatform.tenant_id == tenant_id,
            )
        )
    ).scalars().first()
    if not p:
        await safe_auth_audit(
            db,
            module="platforms",
            action="platform_register",
            source="platform_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="not_found",
            extra_summary=f"platform_id={platform_id}",
        )
        raise HTTPException(status_code=404, detail="Parent platform not found")  # i18n
    if not p.enable:
        await safe_auth_audit(
            db,
            module="platforms",
            action="platform_register",
            source="platform_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="platform_disabled",
            extra_summary=f"platform_id={platform_id}",
        )
        raise HTTPException(status_code=400, detail="Platform is disabled")  # i18n
    svc = getattr(platform_service_mod, "platform_service", None)
    if not svc or not getattr(svc, "running", False):
        await safe_auth_audit(
            db,
            module="platforms",
            action="platform_register",
            source="platform_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=503,
            detail="cascade_service_unavailable",
            extra_summary=f"platform_id={platform_id}",
        )
        raise HTTPException(status_code=503, detail="Cascade service not started (SIP not running or service not initialized)")  # i18n
    await svc.trigger_register(platform_id)
    await safe_auth_audit(
        db,
        module="platforms",
        action="platform_register",
        source="platform_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"platform_id={platform_id}; server_gb_id={p.server_gb_id or ''}",
    )
    return {"ok": True}


@router.post("/{platform_id}/actions/push-catalog")
async def trigger_platform_push_catalog(
    platform_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("devices.manage")),  # 角色检查→权限码检查
):
    tenant_id = current_user.tenant_id or "default"
    p = (
        await db.execute(
            select(ParentPlatform).where(
                ParentPlatform.id == platform_id,
                ParentPlatform.tenant_id == tenant_id,
            )
        )
    ).scalars().first()
    if not p:
        await safe_auth_audit(
            db,
            module="platforms",
            action="platform_push_catalog",
            source="platform_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="not_found",
            extra_summary=f"platform_id={platform_id}",
        )
        raise HTTPException(status_code=404, detail="Parent platform not found")  # i18n
    if not p.enable:
        await safe_auth_audit(
            db,
            module="platforms",
            action="platform_push_catalog",
            source="platform_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="platform_disabled",
            extra_summary=f"platform_id={platform_id}",
        )
        raise HTTPException(status_code=400, detail="Platform is disabled")  # i18n
    svc = getattr(platform_service_mod, "platform_service", None)
    if not svc or not getattr(svc, "running", False):
        await safe_auth_audit(
            db,
            module="platforms",
            action="platform_push_catalog",
            source="platform_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=503,
            detail="cascade_service_unavailable",
            extra_summary=f"platform_id={platform_id}",
        )
        raise HTTPException(status_code=503, detail="Cascade service not started (SIP not running or service not initialized)")  # i18n
    await svc.trigger_push_catalog(platform_id)
    await safe_auth_audit(
        db,
        module="platforms",
        action="platform_push_catalog",
        source="platform_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"platform_id={platform_id}; server_gb_id={p.server_gb_id or ''}",
    )
    return {"ok": True}

@router.post("")
async def create_platform(
    payload: PlatformCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("devices.manage")),  # 角色检查→权限码检查  # N-06 平台写操作权限升级
):
    tenant_id = current_user.tenant_id or "default"
    existing = await db.execute(
        select(ParentPlatform).where(
            ParentPlatform.tenant_id == tenant_id,
            ParentPlatform.server_gb_id == payload.server_gb_id.strip()
        )
    )
    if existing.scalars().first():
        await safe_auth_audit(
            db,
            module="platforms",
            action="create_platform",
            source="platform_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="duplicate_server_gb_id",
            extra_summary=f"server_gb_id={payload.server_gb_id.strip()}",
        )
        raise HTTPException(status_code=400, detail="Parent platform GB ID already exists")  # i18n
    p = ParentPlatform(
        tenant_id=tenant_id,
        name=payload.name.strip(),
        server_gb_id=payload.server_gb_id.strip(),
        server_ip=payload.server_ip.strip(),
        server_port=payload.server_port,
        transport=_normalize_transport(payload.transport),
        client_gb_id=payload.client_gb_id.strip(),
        password=(payload.password.strip() if payload.password and payload.password.strip() else (settings.SIP_DEFAULT_PASSWORD or "")),  # 移除弱密码回退"12345678"
        register_interval=payload.register_interval,
        keepalive_interval=payload.keepalive_interval,
        enable=payload.enable,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    await safe_auth_audit(
        db,
        module="platforms",
        action="create_platform",
        source="platform_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=201,
        detail="ok",
        extra_summary=f"platform_id={p.id}; server_gb_id={p.server_gb_id or ''}; name={p.name or ''}",
    )
    return {"id": p.id, "name": p.name}


@router.put("/{platform_id}")
async def update_platform(
  platform_id: str,
  payload: PlatformUpdate,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(deps.require_permission("devices.manage")),  # 角色检查→权限码检查
):
    tenant_id = current_user.tenant_id or "default"
    result = await db.execute(
        select(ParentPlatform).where(
            ParentPlatform.id == platform_id,
            ParentPlatform.tenant_id == tenant_id
        )
    )
    p = result.scalars().first()
    if not p:
        await safe_auth_audit(
            db,
            module="platforms",
            action="update_platform",
            source="platform_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="not_found",
            extra_summary=f"platform_id={platform_id}",
        )
        raise HTTPException(status_code=404, detail="Parent platform not found")  # i18n
    if payload.name is not None:
        p.name = payload.name.strip()
    if payload.server_gb_id is not None:
        next_gb_id = payload.server_gb_id.strip()
        if next_gb_id and next_gb_id != p.server_gb_id:
            dup = await db.execute(
                select(ParentPlatform).where(
                    ParentPlatform.tenant_id == tenant_id,
                    ParentPlatform.server_gb_id == next_gb_id,
                    ParentPlatform.id != platform_id,
                )
            )
            if dup.scalars().first():
                await safe_auth_audit(
                    db,
                    module="platforms",
                    action="update_platform",
                    source="platform_admin",
                    operator=current_user.username or "unknown",
                    result="failed",
                    tenant_id=_audit_tid(current_user),
                    status_code=400,
                    detail="duplicate_server_gb_id",
                    extra_summary=f"platform_id={platform_id}; server_gb_id={next_gb_id}",
                )
                raise HTTPException(status_code=400, detail="Parent platform GB ID already exists")  # i18n
            p.server_gb_id = next_gb_id
    if payload.server_ip is not None:
        p.server_ip = payload.server_ip.strip()
    if payload.server_port is not None:
        p.server_port = payload.server_port
    if payload.transport is not None:
        p.transport = _normalize_transport(payload.transport)
    if payload.client_gb_id is not None:
        p.client_gb_id = payload.client_gb_id.strip()
    if payload.password is not None:
        if str(payload.password).strip():
            p.password = str(payload.password).strip()
    if payload.register_interval is not None:
        p.register_interval = payload.register_interval
    if payload.keepalive_interval is not None:
        p.keepalive_interval = payload.keepalive_interval
    if payload.catalog_batch_size is not None:
        p.catalog_batch_size = max(0, payload.catalog_batch_size)
    if payload.catalog_push_delay_seconds is not None:
        p.catalog_push_delay_seconds = max(0, payload.catalog_push_delay_seconds)
    if payload.enable is not None:
        p.enable = payload.enable
    await db.commit()
    await db.refresh(p)
    await safe_auth_audit(
        db,
        module="platforms",
        action="update_platform",
        source="platform_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"platform_id={p.id}; server_gb_id={p.server_gb_id or ''}",
    )
    return {"id": p.id}


@router.delete("/{platform_id}")
async def delete_platform(
  platform_id: str,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(deps.require_permission("devices.manage")),  # 角色检查→权限码检查
):
    tenant_id = current_user.tenant_id or "default"
    result = await db.execute(
        select(ParentPlatform).where(
            ParentPlatform.id == platform_id,
            ParentPlatform.tenant_id == tenant_id
        )
    )
    p = result.scalars().first()
    if not p:
        await safe_auth_audit(
            db,
            module="platforms",
            action="delete_platform",
            source="platform_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="not_found",
            extra_summary=f"platform_id={platform_id}",
        )
        raise HTTPException(status_code=404, detail="Parent platform not found")  # i18n
    pgid, pgb = p.id, p.server_gb_id or ""
    await db.execute(delete(PlatformCatalogResource).where(PlatformCatalogResource.platform_id == platform_id))
    await db.delete(p)
    await db.commit()
    # C-27 删除平台时清理_catalog_ack_counter残留条目
    try:
        from app.services.platform_service import platform_service
        if platform_service:
            platform_service._catalog_ack_counter.pop((tenant_id, platform_id), None)
    except Exception as _cleanup_err:
        # FIX [2026-07-17 P3-32]: 描述性日志替代静默吞异常
        logger.warning(f"platforms: failed to clean _catalog_ack_counter for platform {platform_id}: {_cleanup_err}")
    await safe_auth_audit(
        db,
        module="platforms",
        action="delete_platform",
        source="platform_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"platform_id={pgid}; server_gb_id={pgb}",
    )
    return {"status": "ok"}


class CatalogResourceMapping(BaseModel):
    resource_id: str
    virtual_gb_id: str | None = None
    virtual_name: str | None = None
    virtual_parent_id: str | None = None

class CatalogResourcesPayload(BaseModel):
    resource_ids: list[str] = [] # Legacy support
    mappings: list[CatalogResourceMapping] | None = None

@router.get("/{platform_id}/catalog-resources")
async def get_platform_catalog_resources(
    platform_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """获取该上级平台的目录推送通道列表；空表示推全部通道。"""
    tenant_id = current_user.tenant_id or "default"
    p = get_or_404(
        await db.execute(
            select(ParentPlatform).where(
                ParentPlatform.id == platform_id,
                ParentPlatform.tenant_id == tenant_id
            )
        ),
        detail="ParentPlatform not found"
    )  # ORM查询结果空值判断
    r = await db.execute(
        select(PlatformCatalogResource).where(PlatformCatalogResource.platform_id == platform_id)
    )
    mappings = r.scalars().all()

    result_mappings = []
    resource_ids = []
    for m in mappings:
        resource_ids.append(m.resource_id)
        result_mappings.append({
            "resource_id": m.resource_id,
            "virtual_gb_id": m.virtual_gb_id,
            "virtual_name": m.virtual_name,
            "virtual_parent_id": m.virtual_parent_id,
        })

    return {
        "platform_id": platform_id,
        "resource_ids": resource_ids,
        "mappings": result_mappings
    }


@router.put("/{platform_id}/catalog-resources")
async def set_platform_catalog_resources(
    platform_id: str,
    payload: CatalogResourcesPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("devices.manage")),  # 角色检查→权限码检查  # M-05 目录推送范围修改权限升级
):
    """设置该上级平台仅接收的通道列表及其虚拟映射规则；空列表表示推全部。"""
    tenant_id = current_user.tenant_id or "default"
    p = (
        await db.execute(
            select(ParentPlatform).where(
                ParentPlatform.id == platform_id,
                ParentPlatform.tenant_id == tenant_id
            )
        )
    ).scalars().first()
    if not p:
        await safe_auth_audit(
            db,
            module="platforms",
            action="set_catalog_resources",
            source="platform_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="not_found",
            extra_summary=f"platform_id={platform_id}",
        )
        raise HTTPException(status_code=404, detail="Parent platform not found")  # i18n

    await db.execute(delete(PlatformCatalogResource).where(PlatformCatalogResource.platform_id == platform_id))

    # Process mappings if provided, otherwise fallback to resource_ids
    inserted_ids = set()

    if payload.mappings is not None:
        for m in payload.mappings:
            rid = m.resource_id.strip()
            if not rid or rid in inserted_ids: continue

            existing = (
                await db.execute(
                    select(Resource).where(
                        Resource.id == rid,
                        Resource.tenant_id == tenant_id
                    )
                )
            ).scalars().first()
            if existing:
                db.add(PlatformCatalogResource(
                    platform_id=platform_id,
                    resource_id=rid,
                    virtual_gb_id=m.virtual_gb_id.strip() if m.virtual_gb_id else None,
                    virtual_name=m.virtual_name.strip() if m.virtual_name else None,
                    virtual_parent_id=m.virtual_parent_id.strip() if m.virtual_parent_id else None
                ))
                inserted_ids.add(rid)
    else:
        ids = list(dict.fromkeys([x.strip() for x in (payload.resource_ids or []) if x and x.strip()]))
        for rid in ids:
            existing = (
                await db.execute(
                    select(Resource).where(
                        Resource.id == rid,
                        Resource.tenant_id == tenant_id
                    )
                )
            ).scalars().first()
            if existing:
                db.add(PlatformCatalogResource(platform_id=platform_id, resource_id=rid))
                inserted_ids.add(rid)

    await db.commit()
    mode = "mappings" if payload.mappings is not None else "resource_ids"
    await safe_auth_audit(
        db,
        module="platforms",
        action="set_catalog_resources",
        source="platform_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=(
            f"platform_id={platform_id}; mode={mode}; "
            f"resource_count={len(inserted_ids)}"
        ),
    )
    return {"platform_id": platform_id, "resource_ids": list(inserted_ids)}
