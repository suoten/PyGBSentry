from fastapi import Query, APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.db.session import get_db
from app.models.map_config import MapConfig
from app.models.device_position import DevicePosition
from app.models.asset import Asset
from app.api import deps
from app.models.user import User
from app.core.plugin_manager import plugin_manager
from pydantic import BaseModel
from datetime import datetime, timezone
from app.sip.commander import sip_commander
from app.sip.server import sip_server
from app.services.auth_audit import safe_auth_audit
from loguru import logger

router = APIRouter()


def _audit_tid(user: User) -> str:
    return (user.tenant_id or "default").strip() or "default"

class MapConfigUpdate(BaseModel):
    provider: str
    api_key: str
    center_lng: float
    center_lat: float
    zoom_level: int
    vector_tile_url: str | None = None
    min_zoom: int = 1
    max_zoom: int = 20
    profile_id: str | None = None


class MapProfileCreate(BaseModel):
    name: str
    provider: str
    api_key: str = ""
    center_lng: float = 116.404
    center_lat: float = 39.915
    zoom_level: int = 12
    vector_tile_url: str | None = None
    min_zoom: int = 1
    max_zoom: int = 20


class MapProfileUpdate(BaseModel):
    name: str | None = None
    provider: str | None = None
    api_key: str | None = None
    center_lng: float | None = None
    center_lat: float | None = None
    zoom_level: int | None = None
    vector_tile_url: str | None = None
    min_zoom: int | None = None
    max_zoom: int | None = None


class TrajectoryPointCreate(BaseModel):
    device_id: str
    channel_id: str | None = None
    lng: float
    lat: float
    speed: float | None = None
    direction: float | None = None
    altitude: float | None = None
    time: str | None = None


class MobilePositionSubscribe(BaseModel):
    device_id: str
    interval: int = 60


def _tenant_id(user: User) -> str:
    return (user.tenant_id or "default").strip() or "default"


def _map_to_payload(cfg: MapConfig) -> dict:
    return {
        "id": cfg.id,
        "name": cfg.name or "默认地图",
        "provider": cfg.provider,
        "api_key": cfg.api_key or "",
        "vector_tile_url": cfg.vector_tile_url,
        "center_lng": cfg.center_lng,
        "center_lat": cfg.center_lat,
        "zoom_level": cfg.zoom_level,
        "min_zoom": cfg.min_zoom,
        "max_zoom": cfg.max_zoom,
        "is_active": bool(cfg.is_active),
        "is_default": bool(cfg.is_default),
    }


async def _ensure_default_config(db: AsyncSession, current_user: User) -> MapConfig:
    tenant_id = _tenant_id(current_user)
    stmt = select(MapConfig).where(MapConfig.tenant_id == tenant_id).order_by(MapConfig.is_default.desc(), MapConfig.id.asc())
    configs = (await db.execute(stmt)).scalars().all()
    if configs:
        default_cfg = next((c for c in configs if c.is_default), None) or configs[0]
        if not default_cfg.is_default:
            default_cfg.is_default = True
            await db.commit()
            await db.refresh(default_cfg)
        return default_cfg

    cfg = MapConfig(
        tenant_id=tenant_id,
        name="默认地图",
        provider="tianditu",
        api_key="",
        center_lng=116.404,
        center_lat=39.915,
        zoom_level=12,
        min_zoom=1,
        max_zoom=20,
        is_active=True,
        is_default=True,
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    return cfg


@router.get("/devices-latest-positions")
async def list_devices_latest_positions(
    limit: int = Query(2000, ge=1, le=10000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    tenant_id = current_user.tenant_id or "default"
    limit = max(1, min(int(limit or 2000), 5000))
    assets_stmt = select(Asset).order_by(Asset.created_at.desc()).limit(limit)
    if not current_user.is_superuser:
        assets_stmt = assets_stmt.where(Asset.tenant_id == tenant_id)
    assets = (await db.execute(assets_stmt)).scalars().all()
    if not assets:
        return []
    asset_map = {a.gb_id: a for a in assets if a and a.gb_id}
    device_ids = list(asset_map.keys())
    if not device_ids:
        return []

    pos_stmt = (
        select(DevicePosition)
        .where(DevicePosition.device_id.in_(device_ids))
        .order_by(DevicePosition.time.desc())
        .limit(len(device_ids) * 3)
    )
    positions = (await db.execute(pos_stmt)).scalars().all()
    latest: dict[str, DevicePosition] = {}
    for p in positions:
        did = str(getattr(p, "device_id", "") or "")
        if did and did not in latest:
            latest[did] = p

    out = []
    for did, a in asset_map.items():
        p = latest.get(did)
        out.append(
            {
                "gb_id": did,
                "name": a.name,
                "status": a.status,
                "longitude": float(p.longitude) if p else None,
                "latitude": float(p.latitude) if p else None,
                "time": p.time.isoformat() if p and p.time else None,
                "speed": p.speed if p else None,
                "direction": p.direction if p else None,
                "altitude": p.altitude if p else None,
            }
        )
    return out


@router.get("/device-latest-position")
async def get_device_latest_position(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    tenant_id = current_user.tenant_id or "default"
    did = (device_id or "").strip()
    if not did:
        raise HTTPException(status_code=400, detail="device_id is required")
    asset_stmt = select(Asset).where(Asset.gb_id == did)
    if not current_user.is_superuser:
        asset_stmt = asset_stmt.where(Asset.tenant_id == tenant_id)
    asset = (await db.execute(asset_stmt)).scalars().first()
    if not asset:
        raise HTTPException(status_code=404, detail="Device not found")

    pos_stmt = (
        select(DevicePosition)
        .where(DevicePosition.device_id == did)
        .order_by(DevicePosition.time.desc())
        .limit(1)
    )
    pos = (await db.execute(pos_stmt)).scalars().first()
    return {
        "gb_id": did,
        "name": asset.name,
        "status": asset.status,
        "longitude": float(pos.longitude) if pos else None,
        "latitude": float(pos.latitude) if pos else None,
        "time": pos.time.isoformat() if pos and pos.time else None,
        "speed": pos.speed if pos else None,
        "direction": pos.direction if pos else None,
        "altitude": pos.altitude if pos else None,
    }

@router.get("/trajectory")
async def get_trajectory(
    device_id: str,
    channel_id: str | None = None,
    start_time: str = None,
    end_time: str = None,
    limit: int = Query(1000, ge=1, le=10000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    获取设备历史轨迹。
    """
    tenant_id = current_user.tenant_id or "default"
    asset_stmt = select(Asset).where(Asset.gb_id == device_id)
    if not current_user.is_superuser:
        asset_stmt = asset_stmt.where(Asset.tenant_id == tenant_id)
    asset = (await db.execute(asset_stmt)).scalars().first()
    if not asset:
        raise HTTPException(status_code=404, detail="Device not found")

    stmt = select(DevicePosition).where(DevicePosition.device_id == device_id)
    if channel_id:
        stmt = stmt.where(DevicePosition.channel_id == channel_id)

    if start_time:
        try:
            st = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            stmt = stmt.where(DevicePosition.time >= st)
        except (ValueError, TypeError):
            logger.warning("(ValueError, TypeError) occurred")

    if end_time:
        try:
            et = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
            stmt = stmt.where(DevicePosition.time <= et)
        except (ValueError, TypeError):
            logger.warning("(ValueError, TypeError) occurred")

    limit = max(1, min(int(limit or 1000), 10000))
    stmt = stmt.order_by(DevicePosition.time.asc()).limit(limit)
    result = await db.execute(stmt)
    rows = result.scalars().all()

    return [
        {
            "lng": r.longitude,
            "lat": r.latitude,
            "device_id": r.device_id,
            "channel_id": r.channel_id,
            "time": r.time.isoformat() if r.time else None,
            "speed": r.speed,
            "direction": r.direction,
            "altitude": r.altitude
        }
        for r in rows
    ]


@router.post("/mobile-position/subscribe")
async def subscribe_mobile_position(
    payload: MobilePositionSubscribe,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    tenant_id = current_user.tenant_id or "default"
    device_id = (payload.device_id or "").strip()
    if not device_id:
        await safe_auth_audit(
            db,
            module="map",
            action="mobile_position_subscribe",
            source="map_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="device_id_required",
        )
        raise HTTPException(status_code=400, detail="device_id is required")
    interval = max(5, min(int(payload.interval or 60), 3600))

    stmt = select(Asset).where(Asset.gb_id == device_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == tenant_id)
    asset = (await db.execute(stmt)).scalars().first()
    if not asset:
        await safe_auth_audit(
            db,
            module="map",
            action="mobile_position_subscribe",
            source="map_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=404,
            detail="device_not_found",
            extra_summary=f"device_id={device_id}",
        )
        raise HTTPException(status_code=404, detail="Device not found")
    if not asset.ip_addr:
        await safe_auth_audit(
            db,
            module="map",
            action="mobile_position_subscribe",
            source="map_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=500,
            detail="device_network_missing",
            extra_summary=f"device_id={device_id}",
        )
        raise HTTPException(status_code=500, detail="Device network information missing")
    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        await safe_auth_audit(
            db,
            module="map",
            action="mobile_position_subscribe",
            source="map_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=503,
            detail="transport_unavailable",
            extra_summary=f"device_id={device_id}",
        )
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")
    await sip_commander.send_mobile_position_subscribe(
        device_id=device_id,
        transport_info=((asset.ip_addr, asset.port), asset.transport, transport),
        interval=interval,
    )
    await safe_auth_audit(
        db,
        module="map",
        action="mobile_position_subscribe",
        source="map_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"device_id={device_id}; interval={interval}",
    )
    return {"ok": True, "device_id": device_id, "interval": interval}


@router.post("/trajectory")
async def create_trajectory_point(
    payload: TrajectoryPointCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    if abs(payload.lng) > 180 or abs(payload.lat) > 90:
        await safe_auth_audit(
            db,
            module="map",
            action="create_trajectory_point",
            source="map_admin",
            operator=current_user.username or "unknown",
            result="failed",
            tenant_id=_audit_tid(current_user),
            status_code=400,
            detail="lng_lat_out_of_range",
            extra_summary=f"device_id={(payload.device_id or '').strip()}",
        )
        raise HTTPException(status_code=400, detail="Latitude/longitude out of range")
    event_time = datetime.now(timezone.utc)
    if payload.time:
        try:
            event_time = datetime.fromisoformat(payload.time.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            event_time = datetime.now(timezone.utc)
    row = DevicePosition(
        device_id=payload.device_id.strip(),
        channel_id=(payload.channel_id or "").strip() or None,
        longitude=float(payload.lng),
        latitude=float(payload.lat),
        speed=payload.speed,
        direction=payload.direction,
        altitude=payload.altitude,
        time=event_time,
    )
    db.add(row)
    await db.commit()
    await safe_auth_audit(
        db,
        module="map",
        action="create_trajectory_point",
        source="map_admin",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_audit_tid(current_user),
        status_code=200,
        detail="ok",
        extra_summary=f"point_id={row.id}; device_id={row.device_id or ''}",
    )
    return {"ok": True, "id": row.id}

@router.get("")
async def get_map_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    config = await _ensure_default_config(db, current_user)
    return _map_to_payload(config)


@router.get("/providers")
async def list_map_profiles(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    tenant_id = _tenant_id(current_user)
    stmt = select(MapConfig).where(MapConfig.tenant_id == tenant_id).order_by(MapConfig.is_default.desc(), MapConfig.name.asc(), MapConfig.id.asc())
    rows = (await db.execute(stmt)).scalars().all()
    if not rows:
        rows = [await _ensure_default_config(db, current_user)]
    return {"items": [_map_to_payload(row) for row in rows]}


@router.post("/providers")
async def create_map_profile(
    payload: MapProfileCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    tenant_id = _tenant_id(current_user)
    count_stmt = select(MapConfig.id).where(MapConfig.tenant_id == tenant_id)
    exists_any = (await db.execute(count_stmt.limit(1))).scalars().first() is not None
    name = (payload.name or "").strip() or "未命名地图"
    cfg = MapConfig(
        tenant_id=tenant_id,
        name=name[:64],
        provider=(payload.provider or "tianditu").strip() or "tianditu",
        api_key=(payload.api_key or "").strip(),
        vector_tile_url=(payload.vector_tile_url or "").strip() or None,
        center_lng=float(payload.center_lng),
        center_lat=float(payload.center_lat),
        zoom_level=int(payload.zoom_level),
        min_zoom=int(payload.min_zoom),
        max_zoom=int(payload.max_zoom),
        is_active=True,
        is_default=not exists_any,
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    return _map_to_payload(cfg)


@router.put("/providers/{profile_id}")
async def update_map_profile(
    profile_id: str,
    payload: MapProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    tenant_id = _tenant_id(current_user)
    stmt = select(MapConfig).where(MapConfig.id == profile_id, MapConfig.tenant_id == tenant_id)
    cfg = (await db.execute(stmt)).scalars().first()
    if not cfg:
        raise HTTPException(status_code=404, detail="Map config not found")
    if payload.name is not None:
        cfg.name = (payload.name or "").strip()[:64] or cfg.name
    if payload.provider is not None:
        cfg.provider = (payload.provider or "").strip() or cfg.provider
    if payload.api_key is not None:
        cfg.api_key = (payload.api_key or "").strip()
    if payload.vector_tile_url is not None:
        cfg.vector_tile_url = (payload.vector_tile_url or "").strip() or None
    if payload.center_lng is not None:
        cfg.center_lng = float(payload.center_lng)
    if payload.center_lat is not None:
        cfg.center_lat = float(payload.center_lat)
    if payload.zoom_level is not None:
        cfg.zoom_level = int(payload.zoom_level)
    if payload.min_zoom is not None:
        cfg.min_zoom = int(payload.min_zoom)
    if payload.max_zoom is not None:
        cfg.max_zoom = int(payload.max_zoom)
    await db.commit()
    await db.refresh(cfg)
    return _map_to_payload(cfg)


@router.post("/providers/{profile_id}/activate")
async def activate_map_profile(
    profile_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    tenant_id = _tenant_id(current_user)
    stmt = select(MapConfig).where(MapConfig.id == profile_id, MapConfig.tenant_id == tenant_id)
    cfg = (await db.execute(stmt)).scalars().first()
    if not cfg:
        raise HTTPException(status_code=404, detail="Map config not found")
    await db.execute(
        update(MapConfig)
        .where(MapConfig.tenant_id == tenant_id)
        .values(is_default=False)
    )
    cfg.is_default = True
    cfg.is_active = True
    await db.commit()
    await db.refresh(cfg)
    return _map_to_payload(cfg)


@router.delete("/providers/{profile_id}")
async def delete_map_profile(
    profile_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    tenant_id = _tenant_id(current_user)
    stmt = select(MapConfig).where(MapConfig.id == profile_id, MapConfig.tenant_id == tenant_id)
    cfg = (await db.execute(stmt)).scalars().first()
    if not cfg:
        raise HTTPException(status_code=404, detail="Map config not found")
    all_stmt = select(MapConfig).where(MapConfig.tenant_id == tenant_id).order_by(MapConfig.id.asc())
    all_rows = (await db.execute(all_stmt)).scalars().all()
    if len(all_rows) <= 1:
        raise HTTPException(status_code=400, detail="At least one map config must be kept")
    was_default = bool(cfg.is_default)
    await db.delete(cfg)
    await db.flush()
    if was_default:
        next_cfg = next((r for r in all_rows if r.id != profile_id), None)
        if next_cfg:
            next_cfg.is_default = True
    await db.commit()
    return {"status": "ok"}

@router.get("/command-config")
async def get_visual_command_config(
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    可视化指挥配置：报警点位闪烁、视频联动、轨迹追踪。
    安装 visual_command_suite 插件后返回其配置；否则返回默认启用配置。
    """
    meta = getattr(plugin_manager, "metadata", {}).get("visual_command_suite") or {}
    cfg = meta.get("config_template") or {}
    return {
        "enabled": cfg.get("enabled", True),
        "alarm_blink_seconds": int(cfg.get("alarm_blink_seconds", 5)),
        "trajectory_max_points": int(cfg.get("trajectory_max_points", 50)),
        "message": "Alarm point blinking, click for video linkage, track list below",  # i18n
    }


@router.post("")
async def update_map_config(
    config_in: MapConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    tenant_id = _tenant_id(current_user)
    target: MapConfig | None = None
    profile_id = (config_in.profile_id or "").strip()
    if profile_id:
        stmt = select(MapConfig).where(MapConfig.id == profile_id, MapConfig.tenant_id == tenant_id)
        target = (await db.execute(stmt)).scalars().first()
        if not target:
            raise HTTPException(status_code=404, detail="Map config not found")
    else:
        stmt = (
            select(MapConfig)
            .where(MapConfig.tenant_id == tenant_id)
            .order_by(MapConfig.is_default.desc(), MapConfig.id.asc())
        )
        target = (await db.execute(stmt)).scalars().first()
    if not target:
        target = await _ensure_default_config(db, current_user)
    target.provider = config_in.provider
    target.api_key = config_in.api_key
    target.center_lng = config_in.center_lng
    target.center_lat = config_in.center_lat
    target.zoom_level = config_in.zoom_level
    target.vector_tile_url = config_in.vector_tile_url
    target.min_zoom = config_in.min_zoom
    target.max_zoom = config_in.max_zoom
    await db.commit()
    key_set = bool((config_in.api_key or "").strip())
    prov = (config_in.provider or "").replace(";", ".")[:40]
    await safe_auth_audit(
        db,
        module="map",
        action="update_map_config",
        source="map_config",
        operator=current_user.username or "unknown",
        result="success",
        tenant_id=_tenant_id(current_user),
        status_code=200,
        detail="ok",
        extra_summary=(
            f"provider={prov}; zoom_level={config_in.zoom_level}; "
            f"api_key_configured={key_set}"
        ),
    )
    await db.refresh(target)
    return _map_to_payload(target)