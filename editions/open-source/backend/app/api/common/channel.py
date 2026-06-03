"""
全局通道管理 API 兼容层（路径与语义对齐 /api/common/channel/*）。
仅覆盖当前数据模型所能映射的能力；推流/拉流/部标等类型列表可返回空集合。
"""
from __future__ import annotations
from loguru import logger

import hashlib
from typing import Any
from datetime import datetime
import time
import uuid
try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def _uuid7_hex(n: int = 16) -> str:
    return _uuid7_impl().hex[:n]

import math

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.db.session import get_db
from app.models.asset import Asset
from app.models.resource import Resource
from app.models.stream_session import StreamSession
from app.models.user import User
from app.api.v1.endpoints.stream import (
    StopStreamRequest,
    PlaybackControlRequest,
    PlaybackSeekRequest,
    PlaybackSpeedRequest,
    play_stream,
    playback_stream,
    stop_stream,
    playback_pause,
    playback_resume,
    playback_seek,
    playback_speed,
    _probe_zlm_stream,
    _build_stream_match_hints,
)
from app.api.v1.endpoints.control import (
    PTZRequest,
    PresetRequest,
    IrisRequest,
    FocusRequest,
    ScanRequest,
    CruiseRequest,
    WiperRequest,
    AuxSwitchRequest,
    control_ptz,
    call_preset,
    set_preset,
    delete_preset,
    query_preset,
    control_iris,
    control_focus,
    control_scan,
    control_cruise,
    control_wiper,
    control_aux_switch,
)
from app.api.v1.endpoints.device_record import query_device_records

router = APIRouter(tags=["common-channel"])

# Global state: Redis-backed with in-memory fallback for multi-instance support
from app.core.redis_state import FallbackDict
_map_level_cache = FallbackDict("p3s:map_level", ttl=86400)
_map_thin_jobs = FallbackDict("p3s:thin_job", ttl=3600)
_map_thin_default_id: str | None = None
_MAP_THIN_MAX_JOBS = 1000
_MAP_THIN_TTL_SECONDS = 3600  # 1 hour


async def _cleanup_thin_jobs() -> None:
    """Remove expired thin jobs and enforce max size limit."""
    global _map_thin_default_id
    now = time.time()
    all_items = await _map_thin_jobs.items()
    expired = [
        k for k, v in all_items
        if now - v.get("_created_at", 0) > _MAP_THIN_TTL_SECONDS
    ]
    for k in expired:
        await _map_thin_jobs.delete(k)
        if _map_thin_default_id == k:
            _map_thin_default_id = None
    # Enforce max size: remove oldest entries
    current_size = await _map_thin_jobs.size()
    if current_size > _MAP_THIN_MAX_JOBS:
        all_items = await _map_thin_jobs.items()
        oldest = sorted(all_items, key=lambda x: x[1].get("_created_at", 0))
        for k, _ in oldest[:current_size - _MAP_THIN_MAX_JOBS]:
            await _map_thin_jobs.delete(k)
            if _map_thin_default_id == k:
                _map_thin_default_id = None


def numeric_channel_id(resource_id: str) -> int:
    h = hashlib.sha256(resource_id.encode()).digest()
    return int.from_bytes(h[:4], "big") & 0x7FFFFFFF


def _parse_online_param(online: str | bool | None) -> bool | None:
    """Parse the 'online' query parameter into bool | None."""
    if isinstance(online, str):
        o = online.strip().lower()
        return o == "true" if o in ("true", "false") else None
    elif isinstance(online, bool):
        return online
    return None


def _ptz_type_text(ptz: int | None) -> str:
    m = {
        1: "Dome",  # FIXED: 中文错误消息→英文
        2: "Half-dome",  # FIXED: 中文错误消息→英文
        3: "Fixed box",  # FIXED: 中文错误消息→英文
        4: "PTZ box",  # FIXED: 中文错误消息→英文
        5: "PTZ half-dome",  # FIXED: 中文错误消息→英文
        6: "Multi-sensor panoramic/stitch channel",  # FIXED: 中文错误消息→英文
        7: "Multi-sensor split channel",  # FIXED: 中文错误消息→英文
    }
    if ptz is None:
        return "Unknown"  # FIXED: 中文错误消息→英文
    return m.get(int(ptz), "Unknown")  # FIXED: 中文错误消息→英文


def _norm_civil(prefix: str | None) -> str:
    return "".join(ch for ch in (prefix or "") if ch.isdigit())


def _parse_time_to_unix(value: str) -> int:
    v = str(value or "").strip()
    if not v:
        raise HTTPException(status_code=400, detail="Time parameter is required")  # FIXED: 中文错误消息→英文
    if v.isdigit():
        return int(v)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(v, fmt)
            return int(dt.timestamp())
        except ValueError:
            continue
    raise HTTPException(status_code=400, detail="Invalid time format, expected yyyy-MM-dd HH:mm:ss or unix seconds")  # FIXED: 中文错误消息→英文


def _to_common_record_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        start = it.get("startTime") or it.get("start_time") or it.get("time")
        end = it.get("endTime") or it.get("end_time")
        size = it.get("fileSize") or it.get("file_size") or it.get("size")
        out.append(
            {
                "startTime": "" if start is None else str(start),
                "endTime": "" if end is None else str(end),
                "fileSize": "0" if size is None else str(size),
            }
        )
    return out


def _tile_bbox_wgs84(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    n = 2**z
    lon_min = x / n * 360.0 - 180.0
    lon_max = (x + 1) / n * 360.0 - 180.0
    lat_max = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    lat_min = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return lon_min, lat_min, lon_max, lat_max


def _out_of_china(lon: float, lat: float) -> bool:
    return lon < 72.004 or lon > 137.8347 or lat < 0.8293 or lat > 55.8271


def _transform_lat(x: float, y: float) -> float:
    ret = (
        -100.0
        + 2.0 * x
        + 3.0 * y
        + 0.2 * y * y
        + 0.1 * x * y
        + 0.2 * math.sqrt(abs(x))
    )
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * math.pi) + 320 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lon(x: float, y: float) -> float:
    ret = (
        300.0
        + x
        + 2.0 * y
        + 0.1 * x * x
        + 0.1 * x * y
        + 0.1 * math.sqrt(abs(x))
    )
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
    return ret


def _wgs84_to_gcj02(lon: float, lat: float) -> tuple[float, float]:
    if _out_of_china(lon, lat):
        return lon, lat
    a = 6378245.0
    ee = 0.00669342162296594323
    dlat = _transform_lat(lon - 105.0, lat - 35.0)
    dlon = _transform_lon(lon - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - ee * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrtmagic) * math.pi)
    dlon = (dlon * 180.0) / (a / sqrtmagic * math.cos(radlat) * math.pi)
    return lon + dlon, lat + dlat


def _gcj02_to_wgs84(lon: float, lat: float) -> tuple[float, float]:
    if _out_of_china(lon, lat):
        return lon, lat
    glon, glat = _wgs84_to_gcj02(lon, lat)
    return lon * 2 - glon, lat * 2 - glat


def _normalize_to_wgs84(lon: float, lat: float, src_coord_sys: str | None) -> tuple[float, float]:
    src = (src_coord_sys or "WGS84").upper()
    if src == "GCJ02":
        return _gcj02_to_wgs84(lon, lat)
    return lon, lat


def _project_from_wgs84(lon: float, lat: float, target_coord_sys: str | None) -> tuple[float, float]:
    target = (target_coord_sys or "WGS84").upper()
    if target == "GCJ02":
        return _wgs84_to_gcj02(lon, lat)
    return lon, lat


def _pb_varint(v: int) -> bytes:
    out = bytearray()
    n = int(v) & 0xFFFFFFFFFFFFFFFF
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)


def _pb_key(field_no: int, wire_type: int) -> bytes:
    return _pb_varint((field_no << 3) | wire_type)


def _pb_len(field_no: int, payload: bytes) -> bytes:
    return _pb_key(field_no, 2) + _pb_varint(len(payload)) + payload


def _zigzag(v: int) -> int:
    return (v << 1) ^ (v >> 31)


def _encode_mvt_points(
    layer_name: str,
    features: list[dict[str, Any]],
    bbox: tuple[float, float, float, float],
    extent: int = 4096,
) -> bytes:
    if not features:
        return b""
    minx, miny, maxx, maxy = bbox
    dx = max(maxx - minx, 1e-9)
    dy = max(maxy - miny, 1e-9)

    keys: list[str] = []
    key_index: dict[str, int] = {}
    values: list[tuple[str, Any]] = []
    value_index: dict[tuple[str, Any], int] = {}

    def intern_key(k: str) -> int:
        if k not in key_index:
            key_index[k] = len(keys)
            keys.append(k)
        return key_index[k]

    def intern_value(v: Any) -> int:
        if isinstance(v, bool):
            sig = ("bool", v)
        elif isinstance(v, int):
            sig = ("int", v)
        else:
            sig = ("str", "" if v is None else str(v))
        if sig not in value_index:
            value_index[sig] = len(values)
            values.append(sig)
        return value_index[sig]

    layer_features = bytearray()
    for feat in features:
        lon = float(feat.get("gbLongitude"))
        lat = float(feat.get("gbLatitude"))
        # MVT coordinate range is [0, extent-1]
        qx = int(max(0, min(extent - 1, round((lon - minx) / dx * extent))))
        qy = int(max(0, min(extent - 1, round((maxy - lat) / dy * extent))))

        tags = bytearray()
        for k, v in feat.items():
            if k in {"gbLongitude", "gbLatitude"}:
                continue
            ki = intern_key(str(k))
            vi = intern_value(v)
            tags += _pb_varint(ki) + _pb_varint(vi)

        geom = bytearray()
        geom += _pb_varint((1 << 3) | 1)  # MoveTo, count 1
        geom += _pb_varint(_zigzag(qx))
        geom += _pb_varint(_zigzag(qy))

        feature_msg = bytearray()
        fid = int(feat.get("gbId", 0) or 0)
        if fid > 0:
            feature_msg += _pb_key(1, 0) + _pb_varint(fid)
        feature_msg += _pb_len(2, bytes(tags))
        feature_msg += _pb_key(3, 0) + _pb_varint(1)  # POINT
        feature_msg += _pb_len(4, bytes(geom))
        layer_features += _pb_len(2, bytes(feature_msg))

    layer_msg = bytearray()
    # vector_tile.proto: Layer.version=15, Layer.name=1, Layer.features=2,
    # Layer.keys=3, Layer.values=4, Layer.extent=5
    layer_msg += _pb_key(15, 0) + _pb_varint(2)  # version major
    layer_msg += _pb_len(1, layer_name.encode("utf-8"))
    layer_msg += _pb_key(5, 0) + _pb_varint(extent)
    layer_msg += layer_features
    for k in keys:
        layer_msg += _pb_len(3, k.encode("utf-8"))
    for tp, val in values:
        value_msg = bytearray()
        if tp == "bool":
            value_msg += _pb_key(7, 0) + _pb_varint(1 if bool(val) else 0)  # bool_value
        elif tp == "int":
            value_msg += _pb_key(4, 0) + _pb_varint(int(val))  # int_value
        else:
            value_msg += _pb_len(1, str(val).encode("utf-8"))  # string_value
        layer_msg += _pb_len(4, bytes(value_msg))

    tile_msg = _pb_len(3, bytes(layer_msg))
    return bytes(tile_msg)


def _thin_distance_for_zoom(zoom_param: Any, z: int) -> float:
    if isinstance(zoom_param, dict):
        if str(z) in zoom_param:
            try:
                return float(zoom_param[str(z)])
            except (TypeError, ValueError):
                return 0.0
        candidates: list[tuple[int, float]] = []
        for k, v in zoom_param.items():
            try:
                candidates.append((int(k), float(v)))
            except (TypeError, ValueError):
                continue
        if not candidates:
            return 0.0
        candidates.sort(key=lambda x: abs(x[0] - z))
        return max(0.0, candidates[0][1])
    return 0.0


def _apply_grid_thin(
    features: list[dict[str, Any]],
    bbox: tuple[float, float, float, float],
    distance: float,
) -> list[dict[str, Any]]:
    if distance <= 0:
        return features
    minx, miny, _maxx, _maxy = bbox
    picked: dict[tuple[int, int], dict[str, Any]] = {}
    for feat in features:
        lon = float(feat.get("gbLongitude"))
        lat = float(feat.get("gbLatitude"))
        gx = int((lon - minx) / distance)
        gy = int((lat - miny) / distance)
        key = (gx, gy)
        if key not in picked:
            picked[key] = feat
    return list(picked.values())


async def _query_map_tile_features(
    db: AsyncSession,
    current_user: User,
    bbox: tuple[float, float, float, float],
    z: int,
    target_geo_coord_sys: str | None = None,
    thin_job: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    minx, miny, maxx, maxy = bbox
    target_geo = (target_geo_coord_sys or "WGS84").upper()
    if target_geo == "GCJ02":
        p1 = _gcj02_to_wgs84(minx, miny)
        p2 = _gcj02_to_wgs84(maxx, maxy)
        minx, miny = min(p1[0], p2[0]), min(p1[1], p2[1])
        maxx, maxy = max(p1[0], p2[0]), max(p1[1], p2[1])
    stmt = (
        select(Resource, Asset)
        .join(Asset, Asset.id == Resource.asset_id)
        .where(
            Resource.node_type == "channel",
            Resource.longitude.is_not(None),
            Resource.latitude.is_not(None),
            Resource.longitude >= minx,
            Resource.longitude <= maxx,
            Resource.latitude >= miny,
            Resource.latitude <= maxy,
        )
    )
    if thin_job and isinstance(thin_job.get("extent"), dict):
        ext = thin_job["extent"]
        try:
            ex_min_lng = float(ext.get("minLng"))
            ex_min_lat = float(ext.get("minLat"))
            ex_max_lng = float(ext.get("maxLng"))
            ex_max_lat = float(ext.get("maxLat"))
            stmt = stmt.where(
                Resource.longitude >= ex_min_lng,
                Resource.longitude <= ex_max_lng,
                Resource.latitude >= ex_min_lat,
                Resource.latitude <= ex_max_lat,
            )
        except (TypeError, ValueError):
            logger.warning("(TypeError, ValueError) occurred")
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
    rows = (await db.execute(stmt)).all()

    features: list[dict[str, Any]] = []
    for r, a in rows:
        wgs_lon, wgs_lat = _normalize_to_wgs84(float(r.longitude), float(r.latitude), a.geo_coord_sys)
        out_lon, out_lat = _project_from_wgs84(wgs_lon, wgs_lat, target_geo)
        # 精确二次过滤，避免坐标系转换引入边界误差
        raw_minx, raw_miny, raw_maxx, raw_maxy = bbox
        if out_lon < raw_minx or out_lon > raw_maxx or out_lat < raw_miny or out_lat > raw_maxy:
            continue
        features.append(
            {
                "gbId": numeric_channel_id(r.id),
                "gbName": r.name or "",
                "gbStatus": "ON" if int(r.status or 0) == 1 else "OFF",
                "gbLongitude": out_lon,
                "gbLatitude": out_lat,
                "deviceId": a.gb_id,
                "hasAudio": bool(getattr(r, "has_audio", True)),
            }
        )
    if thin_job:
        dist = _thin_distance_for_zoom(thin_job.get("zoomParam"), z)
        features = _apply_grid_thin(features, bbox, dist)
    return features


async def _resolve_channel_asset_pair(
    db: AsyncSession, current_user: User, channel_id: int
) -> tuple[Resource, Asset]:
    rows = await _resolve_resources_by_numeric_ids(
        db,
        current_user.tenant_id or "default",
        current_user.is_superuser,
        [channel_id],
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Channel not found")  # FIXED: 中文错误消息→英文
    resource = rows[0]
    asset = await db.get(Asset, resource.asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Device not found")  # FIXED: 中文错误消息→英文
    return resource, asset


async def _resolve_resources_by_numeric_ids(
    db: AsyncSession,
    tenant_id: str,
    superuser: bool,
    raw_ids: list[int],
) -> list[Resource]:
    if not raw_ids:
        return []
    want = set(int(x) for x in raw_ids)
    # Use pre-computed numeric_channel_id column with index for fast lookup
    stmt = select(Resource).where(
        Resource.node_type == "channel",
        Resource.numeric_channel_id.in_(want),
    )
    if not superuser:
        stmt = stmt.join(Asset, Asset.id == Resource.asset_id).where(Asset.tenant_id == tenant_id)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    if len(rows) != len(want):
        # Fallback: some rows may not have numeric_channel_id populated yet
        # Compute on the fly for any missing IDs
        found_ids = {r.numeric_channel_id for r in rows if r.numeric_channel_id is not None}
        missing_ids = want - found_ids
        if missing_ids:
            # Full scan fallback for rows without pre-computed column
            stmt2 = select(Resource).where(Resource.node_type == "channel")
            if not superuser:
                stmt2 = stmt2.join(Asset, Asset.id == Resource.asset_id).where(Asset.tenant_id == tenant_id)
            result2 = await db.execute(stmt2)
            all_rows = result2.scalars().all()
            for r in all_rows:
                nid = numeric_channel_id(r.id)
                if nid in missing_ids and r not in rows:
                    rows.append(r)
                    # Backfill the column for future lookups
                    r.numeric_channel_id = nid
            found_after = {numeric_channel_id(r.id) for r in rows}
            if found_after != want:
                raise HTTPException(status_code=400, detail="Some channel IDs do not exist or are not authorized")  # FIXED: 中文错误消息→英文
    return rows


async def _stream_id_map(db: AsyncSession, resource_ids: list[str]) -> dict[str, str]:
    if not resource_ids:
        return {}
    # 必须按 app 过滤并按 start_time 排序，否则可能返回旧会话的 stream 值。
    stmt = (
        select(StreamSession.resource_id, StreamSession.stream)
        .where(
            StreamSession.resource_id.in_(resource_ids),
            StreamSession.app.in_(["live", "rtp"]),
        )
        .order_by(StreamSession.start_time.desc())
    )
    result = await db.execute(stmt)
    m: dict[str, str] = {}
    for rid, sid in result.all():
        rid_str = str(rid) if rid else ""
        sid_str = str(sid) if sid else ""
        if rid_str and sid_str and rid_str not in m:
            m[rid_str] = sid_str
    return m


def _resource_to_common_row(
    r: Resource,
    asset: Asset,
    stream_id: str | None,
) -> dict[str, Any]:
    caps = r.capabilities or {}
    dst = "main"
    if isinstance(caps, dict):
        dst = str(caps.get("default_stream_type") or "main").lower()
        if dst not in {"main", "sub"}:
            dst = "main"
    has_video = caps.get("has_video") if isinstance(caps, dict) else None
    return {
        "id": r.id,
        "gbId": numeric_channel_id(r.id),
        "gbDeviceId": r.gb_id,
        "gbName": r.name or "",
        "gbManufacturer": asset.manufacturer or "",
        "gbModel": asset.model or "",
        "gbCivilCode": r.civil_code or "",
        "gbParentId": r.parent_gb_id or "",
        "gbBusinessGroupId": r.business_group_id or "",
        "gbStatus": "ON" if int(r.status or 0) == 1 else "OFF",
        "gbLongitude": r.longitude,
        "gbLatitude": r.latitude,
        "gbPtzType": int(r.ptz_type or 0),
        "gbPtzTypeText": _ptz_type_text(r.ptz_type),
        "ptzType": str(r.ptz_type or 0),
        "ptzTypeText": _ptz_type_text(r.ptz_type),
        "dataType": 1,
        "dataDeviceId": numeric_channel_id(asset.id),
        "deviceId": asset.gb_id,
        "streamId": stream_id or "",
        "hasAudio": bool(getattr(r, "has_audio", True)),
        "hasVideo": bool(has_video) if has_video is not None else None,
        "enableBroadcast": 0,
        "recordPLan": None,
        "createTime": None,
        "updateTime": None,
    }


async def _query_channel_page(
    db: AsyncSession,
    current_user: User,
    page: int,
    count: int,
    query: str | None,
    online: bool | None,
    channel_type: int | None,
    civil_code: str | None,
    parent_device_id: str | None,
    *,
    region_mode: bool = False,
    group_mode: bool = False,
) -> tuple[list[tuple[Resource, Asset]], int]:
    if channel_type in (2, 3, 200):
        return [], 0

    limit = max(1, min(int(count or 15), 1000))
    page = max(1, int(page or 1))
    skip = (page - 1) * limit

    stmt = select(Resource, Asset).join(Asset, Asset.id == Resource.asset_id)
    conditions: list = [Resource.node_type == "channel"]

    if query:
        q = f"%{query.strip()}%"
        conditions.append(or_(Resource.gb_id.ilike(q), Resource.name.ilike(q)))
    if online is not None:
        conditions.append(Resource.status == (1 if online else 0))

    cc_raw = (civil_code or "").strip()
    cc = _norm_civil(civil_code)
    if region_mode and cc_raw:
        rid = cc_raw.replace("region:", "").strip()
        cc2 = _norm_civil(rid)
        if cc2:
            conditions.append(
                or_(
                    Resource.civil_code == cc2,
                    Resource.civil_code.like(f"{cc2}%"),
                    Resource.region_parent_gb_id == cc_raw,
                    Resource.region_parent_gb_id == f"region:{cc2}",
                )
            )
    elif cc:
        conditions.append(Resource.civil_code.like(f"{cc}%"))

    pid = (parent_device_id or "").strip()
    if group_mode and pid:
        conditions.append(Resource.parent_gb_id == pid)
    elif pid:
        conditions.append(Resource.parent_gb_id == pid)

    tenant_id = current_user.tenant_id or "default"
    if not current_user.is_superuser:
        conditions.append(Asset.tenant_id == tenant_id)

    if conditions:
        stmt = stmt.where(and_(*conditions))

    count_stmt = select(func.count()).select_from(Resource).join(Asset, Asset.id == Resource.asset_id)
    if conditions:
        count_stmt = count_stmt.where(and_(*conditions))
    total = int((await db.execute(count_stmt)).scalar() or 0)

    stmt = (
        stmt.order_by(Resource.gb_id.asc(), Resource.id.asc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()
    return rows, total


def _rows_to_list_payload(rows: list[tuple[Resource, Asset]], stream_map: dict[str, str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r, a in rows:
        out.append(_resource_to_common_row(r, a, stream_map.get(r.id)))
    return out


async def _query_unusual_channel_page(
    db: AsyncSession,
    current_user: User,
    page: int,
    count: int,
    query: str | None,
    online: bool | None,
    channel_type: int | None,
    *,
    unusual_kind: str,
) -> tuple[list[tuple[Resource, Asset]], int]:
    if channel_type in (2, 3, 200):
        return [], 0
    limit = max(1, min(int(count or 15), 1000))
    page = max(1, int(page or 1))
    skip = (page - 1) * limit
    stmt = select(Resource, Asset).join(Asset, Asset.id == Resource.asset_id)
    conditions: list = [Resource.node_type == "channel"]
    if query:
        q = f"%{query.strip()}%"
        conditions.append(or_(Resource.gb_id.ilike(q), Resource.name.ilike(q)))
    if online is not None:
        conditions.append(Resource.status == (1 if online else 0))
    if unusual_kind == "civil":
        conditions.append(func.length(func.coalesce(Resource.civil_code, "")) > 0)
        conditions.append(or_(Resource.region_parent_gb_id.is_(None), Resource.region_parent_gb_id == ""))
    elif unusual_kind == "parent":
        conditions.append(func.length(func.coalesce(Resource.parent_gb_id, "")) > 0)
        conditions.append(or_(Resource.business_group_id.is_(None), Resource.business_group_id == ""))
    else:
        raise HTTPException(status_code=400, detail="unusual kind invalid")
    tenant_id = current_user.tenant_id or "default"
    if not current_user.is_superuser:
        conditions.append(Asset.tenant_id == tenant_id)
    stmt = stmt.where(and_(*conditions))
    count_stmt = select(func.count()).select_from(Resource).join(Asset, Asset.id == Resource.asset_id).where(and_(*conditions))
    total = int((await db.execute(count_stmt)).scalar() or 0)
    rows = (
        await db.execute(
            stmt.order_by(Resource.gb_id.asc(), Resource.id.asc()).offset(skip).limit(limit)
        )
    ).all()
    return rows, total


@router.get("/list")
async def channel_list(
    page: int = Query(1, ge=1),
    count: int = Query(15, ge=1, le=1000),
    query: str | None = None,
    online: str | bool | None = None,
    has_record_plan: bool | None = Query(None, alias="hasRecordPlan"),
    channel_type: int | None = Query(None, alias="channelType"),
    civil_code: str | None = Query(None, alias="civilCode"),
    parent_device_id: str | None = Query(None, alias="parentDeviceId"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ = has_record_plan
    ob = _parse_online_param(online)

    rows, total = await _query_channel_page(
        db,
        current_user,
        page,
        count,
        query.strip() if query else None,
        ob,
        channel_type,
        civil_code,
        parent_device_id,
        region_mode=False,
        group_mode=False,
    )
    rids = [r.id for r, _ in rows]
    smap = await _stream_id_map(db, rids)
    lst = _rows_to_list_payload(rows, smap)
    return {"total": total, "list": lst}


@router.get("/civilcode/list")
async def channel_civilcode_list(
    page: int = Query(1, ge=1),
    count: int = Query(15, ge=1, le=1000),
    query: str | None = None,
    online: str | bool | None = None,
    channel_type: int | None = Query(None, alias="channelType"),
    civil_code: str | None = Query(None, alias="civilCode"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    ob: bool | None
    if isinstance(online, str):
        o = online.strip().lower()
        ob = o == "true" if o in ("true", "false") else None
    elif isinstance(online, bool):
        ob = online
    else:
        ob = None

    rows, total = await _query_channel_page(
        db,
        current_user,
        page,
        count,
        query.strip() if query else None,
        ob,
        channel_type,
        civil_code,
        None,
        region_mode=True,
        group_mode=False,
    )
    rids = [r.id for r, _ in rows]
    smap = await _stream_id_map(db, rids)
    return {"total": total, "list": _rows_to_list_payload(rows, smap)}


@router.get("/parent/list")
async def channel_parent_list(
    page: int = Query(1, ge=1),
    count: int = Query(15, ge=1, le=1000),
    query: str | None = None,
    online: str | bool | None = None,
    channel_type: int | None = Query(None, alias="channelType"),
    group_device_id: str | None = Query(None, alias="groupDeviceId"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    ob: bool | None
    if isinstance(online, str):
        o = online.strip().lower()
        ob = o == "true" if o in ("true", "false") else None
    elif isinstance(online, bool):
        ob = online
    else:
        ob = None

    rows, total = await _query_channel_page(
        db,
        current_user,
        page,
        count,
        query.strip() if query else None,
        ob,
        channel_type,
        None,
        group_device_id,
        region_mode=False,
        group_mode=True,
    )
    rids = [r.id for r, _ in rows]
    smap = await _stream_id_map(db, rids)
    return {"total": total, "list": _rows_to_list_payload(rows, smap)}


@router.get("/civilCode/unusual/list")
async def channel_civilcode_unusual_list(
    page: int = Query(1, ge=1),
    count: int = Query(15, ge=1, le=1000),
    query: str | None = None,
    online: str | bool | None = None,
    channel_type: int | None = Query(None, alias="channelType"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    ob: bool | None
    if isinstance(online, str):
        o = online.strip().lower()
        ob = o == "true" if o in ("true", "false") else None
    elif isinstance(online, bool):
        ob = online
    else:
        ob = None
    rows, total = await _query_unusual_channel_page(
        db, current_user, page, count, query.strip() if query else None, ob, channel_type, unusual_kind="civil"
    )
    smap = await _stream_id_map(db, [r.id for r, _ in rows])
    return {"total": total, "list": _rows_to_list_payload(rows, smap)}


@router.get("/parent/unusual/list")
async def channel_parent_unusual_list(
    page: int = Query(1, ge=1),
    count: int = Query(15, ge=1, le=1000),
    query: str | None = None,
    online: str | bool | None = None,
    channel_type: int | None = Query(None, alias="channelType"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    ob: bool | None
    if isinstance(online, str):
        o = online.strip().lower()
        ob = o == "true" if o in ("true", "false") else None
    elif isinstance(online, bool):
        ob = online
    else:
        ob = None
    rows, total = await _query_unusual_channel_page(
        db, current_user, page, count, query.strip() if query else None, ob, channel_type, unusual_kind="parent"
    )
    smap = await _stream_id_map(db, [r.id for r, _ in rows])
    return {"total": total, "list": _rows_to_list_payload(rows, smap)}


class ChannelToRegionBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    civil_code: str = Field(..., alias="civilCode")
    channel_ids: list[int] = Field(default_factory=list, alias="channelIds")
    all_: bool | None = Field(None, alias="all")


class ChannelToGroupBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    parent_id: str = Field(..., alias="parentId")
    business_group: str = Field(..., alias="businessGroup")
    channel_ids: list[int] = Field(default_factory=list, alias="channelIds")


class ChannelRegionDeleteBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    civil_code: str | None = Field(None, alias="civilCode")
    channel_ids: list[int] = Field(default_factory=list, alias="channelIds")
    all_: bool | None = Field(None, alias="all")


class ChannelGroupDeleteBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    parent_id: str | None = Field(None, alias="parentId")
    business_group: str | None = Field(None, alias="businessGroup")
    channel_ids: list[int] = Field(default_factory=list, alias="channelIds")


class ChannelUpdateBody(BaseModel):
    id: int | None = None
    gb_id: int | None = Field(default=None, alias="gbId")
    gb_name: str | None = Field(None, alias="gbName")
    gb_manufacturer: str | None = Field(None, alias="gbManufacturer")
    gb_model: str | None = Field(None, alias="gbModel")
    gb_civil_code: str | None = Field(None, alias="gbCivilCode")
    gb_parent_id: str | None = Field(None, alias="gbParentId")
    gb_business_group_id: str | None = Field(None, alias="gbBusinessGroupId")
    gb_device_id: str | None = Field(default=None, alias="gbDeviceId")
    gb_longitude: float | None = Field(None, alias="gbLongitude")
    gb_latitude: float | None = Field(None, alias="gbLatitude")
    ptz_type: int | None = Field(None, alias="ptzType")
    gb_ptz_type: int | None = Field(default=None, alias="gbPtzType")


class ChannelResetBody(BaseModel):
    id: int
    channel_fields: list[str] = Field(default_factory=list, alias="channelFields")


class ChannelAddBody(BaseModel):
    gb_device_id: str = Field(..., alias="gbDeviceId")
    device_id: str = Field(..., alias="deviceId")
    gb_name: str = Field(..., alias="gbName")
    gb_manufacturer: str | None = Field(None, alias="gbManufacturer")
    gb_model: str | None = Field(None, alias="gbModel")
    gb_civil_code: str | None = Field(None, alias="gbCivilCode")
    gb_parent_id: str | None = Field(None, alias="gbParentId")
    gb_business_group_id: str | None = Field(None, alias="gbBusinessGroupId")
    gb_longitude: float | None = Field(None, alias="gbLongitude")
    gb_latitude: float | None = Field(None, alias="gbLatitude")
    ptz_type: int | None = Field(None, alias="ptzType")
    gb_ptz_type: int | None = Field(None, alias="gbPtzType")


class ChannelToRegionByDeviceBody(BaseModel):
    civil_code: str = Field(..., alias="civilCode")
    device_ids: list[str] = Field(default_factory=list, alias="deviceIds")


class ChannelToGroupByDeviceBody(BaseModel):
    parent_id: str = Field(..., alias="parentId")
    business_group: str = Field(..., alias="businessGroup")
    device_ids: list[str] = Field(default_factory=list, alias="deviceIds")


class ChannelDeviceIdsBody(BaseModel):
    device_ids: list[str] = Field(default_factory=list, alias="deviceIds")


class ChannelUnusualClearBody(BaseModel):
    all_: bool | None = Field(False, alias="all")
    channel_ids: list[int] = Field(default_factory=list, alias="channelIds")


class ChannelMapSaveLevelBody(BaseModel):
    id: int | None = None
    level: int | None = None


class ChannelMapThinDrawBody(BaseModel):
    zoom_param: dict[str, Any] | list[Any] = Field(default_factory=dict, alias="zoomParam")
    extent: Any | None = None
    geo_coord_sys: str | None = Field(None, alias="geoCoordSys")


@router.post("/region/add")
async def region_add(
    body: ChannelToRegionBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    code = _norm_civil(body.civil_code)
    if len(code) < 6:
        raise HTTPException(status_code=400, detail="Invalid administrative division code")  # FIXED: 中文错误消息→英文
    chans = await _resolve_resources_by_numeric_ids(
        db, current_user.tenant_id or "default", current_user.is_superuser, body.channel_ids
    )
    target_region = f"region:{code}"
    for r in chans:
        r.civil_code = code
        r.region_parent_gb_id = target_region
    await db.commit()
    return {"status": "ok"}


@router.post("/region/device/add")
async def region_add_by_device(
    body: ChannelToRegionByDeviceBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    code = _norm_civil(body.civil_code)
    if len(code) < 6:
        raise HTTPException(status_code=400, detail="Invalid administrative division code")  # FIXED: 中文错误消息→英文
    device_ids = [str(x or "").strip() for x in body.device_ids if str(x or "").strip()]
    if not device_ids:
        raise HTTPException(status_code=400, detail="deviceIds is required")  # FIXED: 中文错误消息→英文

    tenant_id = current_user.tenant_id or "default"
    asset_stmt = select(Asset.id).where(Asset.gb_id.in_(device_ids))
    if not current_user.is_superuser:
        asset_stmt = asset_stmt.where(Asset.tenant_id == tenant_id)
    asset_ids = [x for x in (await db.execute(asset_stmt)).scalars().all()]
    if not asset_ids:
        return {"status": "ok", "updated": 0}

    ch_stmt = select(Resource).where(
        Resource.node_type == "channel",
        Resource.asset_id.in_(asset_ids),
    )
    channels = (await db.execute(ch_stmt)).scalars().all()
    target_region = f"region:{code}"
    for r in channels:
        r.civil_code = code
        r.region_parent_gb_id = target_region
    await db.commit()
    return {"status": "ok", "updated": len(channels)}


@router.post("/group/add")
async def group_add(
    body: ChannelToGroupBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    pid = (body.parent_id or "").strip()
    bg = (body.business_group or "").strip()
    if not pid or not bg:
        raise HTTPException(status_code=400, detail="parentId and businessGroup are required")  # FIXED: 中文错误消息→英文
    chans = await _resolve_resources_by_numeric_ids(
        db, current_user.tenant_id or "default", current_user.is_superuser, body.channel_ids
    )
    for r in chans:
        r.parent_gb_id = pid
        r.business_group_id = bg
    await db.commit()
    return {"status": "ok"}


@router.post("/group/device/add")
async def group_add_by_device(
    body: ChannelToGroupByDeviceBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    pid = (body.parent_id or "").strip()
    bg = (body.business_group or "").strip()
    if not pid or not bg:
        raise HTTPException(status_code=400, detail="parentId and businessGroup are required")  # FIXED: 中文错误消息→英文
    device_ids = [str(x or "").strip() for x in body.device_ids if str(x or "").strip()]
    if not device_ids:
        raise HTTPException(status_code=400, detail="deviceIds is required")  # FIXED: 中文错误消息→英文

    tenant_id = current_user.tenant_id or "default"
    asset_stmt = select(Asset.id).where(Asset.gb_id.in_(device_ids))
    if not current_user.is_superuser:
        asset_stmt = asset_stmt.where(Asset.tenant_id == tenant_id)
    asset_ids = [x for x in (await db.execute(asset_stmt)).scalars().all()]
    if not asset_ids:
        return {"status": "ok", "updated": 0}

    ch_stmt = select(Resource).where(
        Resource.node_type == "channel",
        Resource.asset_id.in_(asset_ids),
    )
    channels = (await db.execute(ch_stmt)).scalars().all()
    for r in channels:
        r.parent_gb_id = pid
        r.business_group_id = bg
    await db.commit()
    return {"status": "ok", "updated": len(channels)}


@router.post("/region/delete")
async def region_delete(
    body: ChannelRegionDeleteBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    if not body.channel_ids:
        raise HTTPException(status_code=400, detail="channelIds is required")  # FIXED: 中文错误消息→英文
    chans = await _resolve_resources_by_numeric_ids(
        db, current_user.tenant_id or "default", current_user.is_superuser, body.channel_ids
    )
    for r in chans:
        r.civil_code = None
        r.region_parent_gb_id = None
    await db.commit()
    return {"status": "ok"}


@router.post("/region/device/delete")
async def region_delete_by_device(
    body: ChannelDeviceIdsBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    device_ids = [str(x or "").strip() for x in body.device_ids if str(x or "").strip()]
    if not device_ids:
        raise HTTPException(status_code=400, detail="deviceIds is required")  # FIXED: 中文错误消息→英文
    tenant_id = current_user.tenant_id or "default"
    asset_stmt = select(Asset.id).where(Asset.gb_id.in_(device_ids))
    if not current_user.is_superuser:
        asset_stmt = asset_stmt.where(Asset.tenant_id == tenant_id)
    asset_ids = [x for x in (await db.execute(asset_stmt)).scalars().all()]
    if not asset_ids:
        return {"status": "ok", "updated": 0}
    ch_stmt = select(Resource).where(
        Resource.node_type == "channel",
        Resource.asset_id.in_(asset_ids),
    )
    channels = (await db.execute(ch_stmt)).scalars().all()
    for r in channels:
        r.civil_code = None
        r.region_parent_gb_id = None
    await db.commit()
    return {"status": "ok", "updated": len(channels)}


@router.post("/group/delete")
async def group_delete(
    body: ChannelGroupDeleteBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    if not body.channel_ids:
        raise HTTPException(status_code=400, detail="channelIds is required")  # FIXED: 中文错误消息→英文
    chans = await _resolve_resources_by_numeric_ids(
        db, current_user.tenant_id or "default", current_user.is_superuser, body.channel_ids
    )
    for r in chans:
        r.parent_gb_id = None
        r.business_group_id = None
    await db.commit()
    return {"status": "ok"}


@router.post("/group/device/delete")
async def group_delete_by_device(
    body: ChannelDeviceIdsBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    device_ids = [str(x or "").strip() for x in body.device_ids if str(x or "").strip()]
    if not device_ids:
        raise HTTPException(status_code=400, detail="deviceIds is required")  # FIXED: 中文错误消息→英文
    tenant_id = current_user.tenant_id or "default"
    asset_stmt = select(Asset.id).where(Asset.gb_id.in_(device_ids))
    if not current_user.is_superuser:
        asset_stmt = asset_stmt.where(Asset.tenant_id == tenant_id)
    asset_ids = [x for x in (await db.execute(asset_stmt)).scalars().all()]
    if not asset_ids:
        return {"status": "ok", "updated": 0}
    ch_stmt = select(Resource).where(
        Resource.node_type == "channel",
        Resource.asset_id.in_(asset_ids),
    )
    channels = (await db.execute(ch_stmt)).scalars().all()
    for r in channels:
        r.parent_gb_id = None
        r.business_group_id = None
    await db.commit()
    return {"status": "ok", "updated": len(channels)}


@router.post("/civilCode/unusual/clear")
async def channel_civilcode_unusual_clear(
    body: ChannelUnusualClearBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    tenant_id = current_user.tenant_id or "default"
    if body.all_:
        stmt = select(Resource).where(Resource.node_type == "channel")
        if not current_user.is_superuser:
            stmt = stmt.join(Asset, Asset.id == Resource.asset_id).where(Asset.tenant_id == tenant_id)
        rows = (await db.execute(stmt)).scalars().all()
        channels = [r for r in rows if (r.civil_code or "").strip() and not (r.region_parent_gb_id or "").strip()]
    else:
        channels = await _resolve_resources_by_numeric_ids(db, tenant_id, current_user.is_superuser, body.channel_ids)
    for r in channels:
        r.civil_code = None
        r.region_parent_gb_id = None
    await db.commit()
    return {"status": "ok", "updated": len(channels)}


@router.post("/parent/unusual/clear")
async def channel_parent_unusual_clear(
    body: ChannelUnusualClearBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    tenant_id = current_user.tenant_id or "default"
    if body.all_:
        stmt = select(Resource).where(Resource.node_type == "channel")
        if not current_user.is_superuser:
            stmt = stmt.join(Asset, Asset.id == Resource.asset_id).where(Asset.tenant_id == tenant_id)
        rows = (await db.execute(stmt)).scalars().all()
        channels = [r for r in rows if (r.parent_gb_id or "").strip() and not (r.business_group_id or "").strip()]
    else:
        channels = await _resolve_resources_by_numeric_ids(db, tenant_id, current_user.is_superuser, body.channel_ids)
    for r in channels:
        r.parent_gb_id = None
        r.business_group_id = None
    await db.commit()
    return {"status": "ok", "updated": len(channels)}


@router.get("/one")
async def channel_one(
    id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    rows = await _resolve_resources_by_numeric_ids(
        db, current_user.tenant_id or "default", current_user.is_superuser, [id]
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Channel not found")  # FIXED: 中文错误消息→英文
    r = rows[0]
    a = await db.get(Asset, r.asset_id)
    if not a:
        raise HTTPException(status_code=404, detail="Device not found")  # FIXED: 中文错误消息→英文
    smap = await _stream_id_map(db, [r.id])
    return _resource_to_common_row(r, a, smap.get(r.id))


@router.post("/update")
async def channel_update(
    body: ChannelUpdateBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    target_id = body.id if body.id is not None else body.gb_id
    if target_id is None:
        raise HTTPException(status_code=400, detail="Missing channel identifier (id or gbId)")  # FIXED: 中文错误消息→英文

    rows = await _resolve_resources_by_numeric_ids(
        db,
        current_user.tenant_id or "default",
        current_user.is_superuser,
        [int(target_id)],
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Channel not found")  # FIXED: 中文错误消息→英文
    r = rows[0]
    a = await db.get(Asset, r.asset_id)
    if not a:
        raise HTTPException(status_code=404, detail="Device not found")  # FIXED: 中文错误消息→英文

    changed = 0
    if body.gb_name is not None:
        r.name = body.gb_name
        changed += 1
    if body.gb_manufacturer is not None:
        a.manufacturer = body.gb_manufacturer
        changed += 1
    if body.gb_model is not None:
        a.model = body.gb_model
        changed += 1
    if body.gb_civil_code is not None:
        r.civil_code = _norm_civil(body.gb_civil_code) or None
        changed += 1
    if body.gb_parent_id is not None:
        r.parent_gb_id = (body.gb_parent_id or "").strip() or None
        changed += 1
    if body.gb_business_group_id is not None:
        r.business_group_id = (body.gb_business_group_id or "").strip() or None
        changed += 1
    if body.gb_device_id is not None:
        new_gb_device_id = (body.gb_device_id or "").strip()
        if not new_gb_device_id:
            raise HTTPException(status_code=400, detail="gbDeviceId is required")  # FIXED: 中文错误消息→英文
        tenant_id = current_user.tenant_id or "default"
        exists_stmt = select(Resource.id).where(
            Resource.gb_id == new_gb_device_id,
            Resource.id != r.id,
        )
        if not current_user.is_superuser:
            exists_stmt = (
                exists_stmt.join(Asset, Asset.id == Resource.asset_id)
                .where(Asset.tenant_id == tenant_id)
            )
        exists = (await db.execute(exists_stmt)).scalar_one_or_none()
        if exists:
            raise HTTPException(status_code=400, detail="Channel ID already exists")  # FIXED: 中文错误消息→英文
        r.gb_id = new_gb_device_id
        changed += 1
    if body.gb_longitude is not None:
        r.longitude = body.gb_longitude
        changed += 1
    if body.gb_latitude is not None:
        r.latitude = body.gb_latitude
        changed += 1
    new_ptz_type = body.ptz_type if body.ptz_type is not None else body.gb_ptz_type
    if new_ptz_type is not None:
        r.ptz_type = int(new_ptz_type)
        changed += 1
    if changed <= 0:
        raise HTTPException(status_code=400, detail="No changes made")  # FIXED: 中文错误消息→英文
    await db.commit()
    return {"status": "ok"}


@router.post("/reset")
async def channel_reset(
    body: ChannelResetBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    if not body.channel_fields:  # FIXED: chanel_fields拼写错误→channel_fields
        raise HTTPException(status_code=400, detail="Fields to reset cannot be empty")  # FIXED: 中文错误消息→英文
    rows = await _resolve_resources_by_numeric_ids(
        db, current_user.tenant_id or "default", current_user.is_superuser, [body.id]
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Channel not found")  # FIXED: 中文错误消息→英文
    r = rows[0]
    a = await db.get(Asset, r.asset_id)
    if not a:
        raise HTTPException(status_code=404, detail="Device not found")  # FIXED: 中文错误消息→英文

    for field in body.channel_fields:  # FIXED: chanel_fields拼写错误→channel_fields
        f = str(field or "").strip()
        if f == "gbCivilCode":
            r.civil_code = None
            r.region_parent_gb_id = None
        elif f == "gbParentId":
            r.parent_gb_id = None
        elif f == "gbBusinessGroupId":
            r.business_group_id = None
        elif f == "gbLongitude":
            r.longitude = None
        elif f == "gbLatitude":
            r.latitude = None
        elif f == "ptzType" or f == "gbPtzType":
            r.ptz_type = 0
        elif f == "gbName":
            r.name = ""
        elif f == "gbManufacturer":
            a.manufacturer = ""
        elif f == "gbModel":
            a.model = ""
    await db.commit()
    return {"status": "ok"}


@router.post("/add")
async def channel_add(
    body: ChannelAddBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    tenant_id = current_user.tenant_id or "default"
    dev_stmt = select(Asset).where(Asset.gb_id == body.device_id)
    if not current_user.is_superuser:
        dev_stmt = dev_stmt.where(Asset.tenant_id == tenant_id)
    asset = (await db.execute(dev_stmt)).scalars().first()
    if not asset:
        raise HTTPException(status_code=404, detail="Device not found")  # FIXED: 中文错误消息→英文

    ch_code = (body.gb_device_id or "").strip()
    if not ch_code:
        raise HTTPException(status_code=400, detail="gbDeviceId is required")  # FIXED: 中文错误消息→英文
    name = (body.gb_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="gbName is required")  # FIXED: 中文错误消息→英文

    exists_stmt = select(Resource.id).where(Resource.gb_id == ch_code)
    if not current_user.is_superuser:
        exists_stmt = exists_stmt.join(Asset, Asset.id == Resource.asset_id).where(Asset.tenant_id == tenant_id)
    exists = (await db.execute(exists_stmt)).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail="Channel ID already exists")  # FIXED: 中文错误消息→英文

    resource = Resource(
        tenant_id=asset.tenant_id or tenant_id,
        asset_id=asset.id,
        gb_id=ch_code,
        name=name,
        status=1,
        longitude=body.gb_longitude,
        latitude=body.gb_latitude,
        parent_gb_id=(body.gb_parent_id or "").strip() or None,
        business_group_id=(body.gb_business_group_id or "").strip() or None,
        civil_code=_norm_civil(body.gb_civil_code) or None,
        node_type="channel",
        ptz_type=int((body.ptz_type if body.ptz_type is not None else body.gb_ptz_type) or 0),
    )
    if body.gb_manufacturer is not None:
        asset.manufacturer = body.gb_manufacturer
    if body.gb_model is not None:
        asset.model = body.gb_model
    db.add(resource)
    await db.commit()
    return {"status": "ok", "id": resource.id, "gbId": numeric_channel_id(resource.id)}


@router.get("/map/list")
async def channel_map_list(
    page: int = Query(1, ge=1),
    count: int = Query(5000, ge=1, le=10000),
    query: str | None = None,
    online: str | bool | None = None,
    has_record_plan: bool | None = Query(None, alias="hasRecordPlan"),
    channel_type: int | None = Query(None, alias="channelType"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ = has_record_plan
    ob = _parse_online_param(online)
    rows, total = await _query_channel_page(
        db,
        current_user,
        page=page,
        count=count,
        query=query.strip() if query else None,
        online=ob,
        channel_type=channel_type,
        civil_code=None,
        parent_device_id=None,
        region_mode=False,
        group_mode=False,
    )
    smap = await _stream_id_map(db, [r.id for r, _ in rows])
    payload = _rows_to_list_payload(rows, smap)
    payload["total"] = total
    return payload


@router.post("/map/save-level")
async def channel_map_save_level(
    body: ChannelMapSaveLevelBody,
    _user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    await _map_level_cache.set("current", {"id": body.id, "level": body.level})
    return {"status": "ok", "id": body.id, "level": body.level}


@router.post("/map/reset-level")
async def channel_map_reset_level(
    _user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    # 与前端「还原抽稀结果」行为对齐：
    # - 清空当前薄化默认 thinId
    # - 清空薄化任务
    # - 清空层级缓存
    global _map_thin_default_id
    await _map_thin_jobs.clear()
    _map_thin_default_id = None
    await _map_level_cache.set("current", {"id": None, "level": None})
    return {"status": "ok"}


@router.post("/map/thin/draw")
async def channel_map_thin_draw(
    body: ChannelMapThinDrawBody,
    _user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    zoom_param = body.zoom_param
    if isinstance(zoom_param, dict):
        has_zoom = len(zoom_param) > 0
    elif isinstance(zoom_param, list):
        has_zoom = len(zoom_param) > 0
    else:
        has_zoom = False
    if not has_zoom:
        raise HTTPException(status_code=400, detail="zoomParam is required")  # FIXED: 中文错误消息→英文
    thin_id = _uuid7_hex()
    await _cleanup_thin_jobs()
    await _map_thin_jobs.set(thin_id, {
        "drawThinId": thin_id,
        "process": 1,
        "msg": "done",  # FIXED: 硬编码中文→英文
        "geoCoordSys": (body.geo_coord_sys or "WGS84").upper(),
        "extent": body.extent,
        "zoomParam": body.zoom_param,
        "_created_at": time.time(),
    })
    return thin_id


@router.get("/map/thin/clear")
async def channel_map_thin_clear(
    id: str = Query(...),
    _user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    global _map_thin_default_id
    await _map_thin_jobs.delete(id)
    if _map_thin_default_id == id:
        _map_thin_default_id = None
    return {"status": "ok", "id": id}


@router.get("/map/thin/progress")
async def channel_map_thin_progress(
    id: str = Query(...),
    _user: User = Depends(deps.get_current_active_user),
):
    job = await _map_thin_jobs.get(id)
    if job:
        process = float(job.get("process", 1))
        msg = str(job.get("msg", "done"))  # FIXED: 硬编码中文→英文
    else:
        process = 1
        msg = "done"  # FIXED: 硬编码中文→英文
    # 对齐前端读取字段：process(0-1)、msg、drawThinId
    return {
        "drawThinId": id,
        "process": process,
        "msg": msg,
        "id": id,
        "percent": int(max(0, min(100, round(process * 100)))),
        "status": "done" if process >= 1 else "running",
    }


@router.get("/map/thin/save")
async def channel_map_thin_save(
    id: str = Query(...),
    _user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    global _map_thin_default_id
    if not await _map_thin_jobs.get(id):
        raise HTTPException(status_code=404, detail="Thinning task not found")  # FIXED: 中文错误消息→英文
    _map_thin_default_id = id
    return {"status": "ok", "id": id}


@router.get("/map/tile/{z}/{x}/{y}")
async def channel_map_tile(
    z: int,
    x: int,
    y: int,
    geo_coord_sys: str | None = Query(None, alias="geoCoordSys"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ = geo_coord_sys
    bbox = _tile_bbox_wgs84(z, x, y)
    features = await _query_map_tile_features(
        db, current_user, bbox, z, target_geo_coord_sys=geo_coord_sys, thin_job=None
    )
    payload = _encode_mvt_points("channel", features, bbox)
    return Response(content=payload, media_type="application/x-protobuf")


@router.get("/map/thin/tile/{z}/{x}/{y}")
async def channel_map_thin_tile(
    z: int,
    x: int,
    y: int,
    thin_id: str | None = Query(None, alias="thinId"),
    geo_coord_sys: str | None = Query(None, alias="geoCoordSys"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(deps.get_current_active_user),
):
    _ = geo_coord_sys
    job: dict[str, Any] | None = None
    if thin_id and not await _map_thin_jobs.get(thin_id):
        raise HTTPException(status_code=404, detail="thinId not found")  # FIXED: 中文错误消息→英文
    if not thin_id and _map_thin_default_id:
        thin_id = _map_thin_default_id
    if thin_id:
        job = await _map_thin_jobs.get(thin_id)
    bbox = _tile_bbox_wgs84(z, x, y)
    features = await _query_map_tile_features(
        db, _user, bbox, z, target_geo_coord_sys=geo_coord_sys, thin_job=job
    )
    payload = _encode_mvt_points("channel", features, bbox)
    return Response(content=payload, media_type="application/x-protobuf")


@router.get("/type/list")
async def channel_type_list(_user: User = Depends(deps.get_current_active_user)):
    return [
        {"code": "1", "name": "Camera"},  # FIXED: 硬编码中文→英文
        {"code": "2", "name": "Audio Device"},  # FIXED: 硬编码中文→英文
    ]


@router.get("/industry/list")
async def industry_list(_user: User = Depends(deps.get_current_active_user)):
    return []


@router.get("/network/identification/list")
async def network_identification_list(_user: User = Depends(deps.get_current_active_user)):
    return []


@router.get("/play")
async def channel_play(
    device_id: str | None = Query(None, alias="deviceId"),
    channel_id: str | None = Query(None, alias="channelId"),
    stream_type: str = Query("auto", alias="streamType"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    if not device_id:
        if not channel_id:
            raise HTTPException(status_code=400, detail="channelId is required")  # FIXED: 中文错误消息→英文
        try:
            nid = int(channel_id)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid channelId format")  # FIXED: 中文错误消息→英文
        resource, asset = await _resolve_channel_asset_pair(db, current_user, nid)
        device_id = asset.gb_id
        channel_id = resource.gb_id
    if not channel_id:
        raise HTTPException(status_code=400, detail="channelId is required")  # FIXED: 中文错误消息→英文
    return await play_stream(
        device_id=device_id,
        channel_id=channel_id,
        stream_type=stream_type or "auto",
        db=db,
        current_user=current_user,
    )


@router.post("/play/stop")  # FIXED: I9 play/stop使用GET方法改为POST
async def channel_play_stop(
    payload: StopStreamRequest,  # FIXED: I9 GET→POST，参数从Query改为Body
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    stream = payload.stream
    if not stream and payload.app:
        # FIXED: S-10 当 stream 未提供时，尝试通过 app+device_id+channel_id 查找活跃流（兼容旧调用方式）
        try:
            from app.models.stream_session import StreamSession
            _q = select(StreamSession.stream).where(StreamSession.app == payload.app)
            if payload.device_id:
                _q = _q.where(StreamSession.device_id == payload.device_id)
            if payload.channel_id:
                _q = _q.where(StreamSession.channel_id == payload.channel_id)
            _q = _q.limit(1)
            _row = (await db.execute(_q)).scalars().first()
            if _row:
                stream = _row
                payload.stream = stream
        except Exception as e:
            logger.debug(f"channel_play_stop: fallback stream lookup failed: {e}")
    if not stream:
        raise HTTPException(status_code=400, detail="stream parameter is required")  # FIXED: 中文错误消息→英文
    return await stop_stream(payload=payload, db=db, current_user=current_user)


@router.get("/front-end/scan/set/speed")
async def channel_scan_set_speed(
    channel_id: int = Query(..., alias="channelId"),
    scan_id: int = Query(..., alias="scanId"),
    speed: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    resource, asset = await _resolve_channel_asset_pair(db, current_user, channel_id)
    body = ScanRequest(scan_id=scan_id, action="set_speed", speed=speed)
    return await control_scan(asset.gb_id, resource.gb_id, body, db, current_user)


@router.get("/front-end/scan/set/left")
async def channel_scan_set_left(
    channel_id: int = Query(..., alias="channelId"),
    scan_id: int = Query(..., alias="scanId"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    resource, asset = await _resolve_channel_asset_pair(db, current_user, channel_id)
    body = ScanRequest(scan_id=scan_id, action="set_left", speed=128)
    return await control_scan(asset.gb_id, resource.gb_id, body, db, current_user)


@router.get("/front-end/scan/set/right")
async def channel_scan_set_right(
    channel_id: int = Query(..., alias="channelId"),
    scan_id: int = Query(..., alias="scanId"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    resource, asset = await _resolve_channel_asset_pair(db, current_user, channel_id)
    body = ScanRequest(scan_id=scan_id, action="set_right", speed=128)
    return await control_scan(asset.gb_id, resource.gb_id, body, db, current_user)


@router.get("/front-end/scan/start")
async def channel_scan_start(
    channel_id: int = Query(..., alias="channelId"),
    scan_id: int = Query(..., alias="scanId"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    resource, asset = await _resolve_channel_asset_pair(db, current_user, channel_id)
    body = ScanRequest(scan_id=scan_id, action="start", speed=128)
    return await control_scan(asset.gb_id, resource.gb_id, body, db, current_user)


@router.get("/front-end/scan/stop")
async def channel_scan_stop(
    channel_id: int = Query(..., alias="channelId"),
    scan_id: int = Query(..., alias="scanId"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    resource, asset = await _resolve_channel_asset_pair(db, current_user, channel_id)
    body = ScanRequest(scan_id=scan_id, action="stop", speed=128)
    return await control_scan(asset.gb_id, resource.gb_id, body, db, current_user)


@router.get("/front-end/preset/query")
async def channel_preset_query(
    channel_id: int = Query(..., alias="channelId"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    resource, asset = await _resolve_channel_asset_pair(db, current_user, channel_id)
    data = await query_preset(asset.gb_id, resource.gb_id, db, current_user)
    preset_list = data.get("preset_list", []) if isinstance(data, dict) else []
    out: list[dict[str, Any]] = []
    for it in preset_list:
        if isinstance(it, dict):
            out.append(
                {
                    "presetId": int(it.get("preset_id", 0) or 0),
                    "presetName": str(it.get("preset_name") or ""),
                }
            )
    return out


@router.get("/front-end/tour/point/add")
async def channel_tour_point_add(
    channel_id: int = Query(..., alias="channelId"),
    tour_id: int = Query(..., alias="tourId"),
    preset_id: int = Query(..., alias="presetId"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    resource, asset = await _resolve_channel_asset_pair(db, current_user, channel_id)
    body = CruiseRequest(cruise_id=tour_id, preset_id=preset_id, action="add", speed=128, stay_time=5)
    return await control_cruise(asset.gb_id, resource.gb_id, body, db, current_user)


@router.get("/front-end/tour/point/delete")
async def channel_tour_point_delete(
    channel_id: int = Query(..., alias="channelId"),
    tour_id: int = Query(..., alias="tourId"),
    preset_id: int = Query(..., alias="presetId"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    resource, asset = await _resolve_channel_asset_pair(db, current_user, channel_id)
    body = CruiseRequest(cruise_id=tour_id, preset_id=preset_id, action="delete", speed=128, stay_time=5)
    return await control_cruise(asset.gb_id, resource.gb_id, body, db, current_user)


@router.get("/front-end/tour/speed")
async def channel_tour_speed(
    channel_id: int = Query(..., alias="channelId"),
    tour_id: int = Query(..., alias="tourId"),
    preset_id: int = Query(..., alias="presetId"),
    speed: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    resource, asset = await _resolve_channel_asset_pair(db, current_user, channel_id)
    body = CruiseRequest(
        cruise_id=tour_id, preset_id=preset_id, action="set_speed", speed=speed, stay_time=5
    )
    return await control_cruise(asset.gb_id, resource.gb_id, body, db, current_user)


@router.get("/front-end/tour/time")
async def channel_tour_time(
    channel_id: int = Query(..., alias="channelId"),
    tour_id: int = Query(..., alias="tourId"),
    preset_id: int = Query(..., alias="presetId"),
    time: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    resource, asset = await _resolve_channel_asset_pair(db, current_user, channel_id)
    body = CruiseRequest(
        cruise_id=tour_id, preset_id=preset_id, action="set_time", speed=128, stay_time=time
    )
    return await control_cruise(asset.gb_id, resource.gb_id, body, db, current_user)


@router.get("/front-end/tour/start")
async def channel_tour_start(
    channel_id: int = Query(..., alias="channelId"),
    tour_id: int = Query(..., alias="tourId"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    resource, asset = await _resolve_channel_asset_pair(db, current_user, channel_id)
    body = CruiseRequest(cruise_id=tour_id, preset_id=1, action="start", speed=128, stay_time=5)
    return await control_cruise(asset.gb_id, resource.gb_id, body, db, current_user)


@router.get("/front-end/tour/stop")
async def channel_tour_stop(
    channel_id: int = Query(..., alias="channelId"),
    tour_id: int = Query(..., alias="tourId"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    resource, asset = await _resolve_channel_asset_pair(db, current_user, channel_id)
    body = CruiseRequest(cruise_id=tour_id, preset_id=1, action="stop", speed=128, stay_time=5)
    return await control_cruise(asset.gb_id, resource.gb_id, body, db, current_user)


@router.get("/front-end/preset/add")
async def channel_preset_add(
    channel_id: int = Query(..., alias="channelId"),
    preset_id: int = Query(..., alias="presetId"),
    preset_name: str = Query(..., alias="presetName"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    resource, asset = await _resolve_channel_asset_pair(db, current_user, channel_id)
    _ = preset_name
    body = PresetRequest(preset_id=preset_id)
    return await set_preset(asset.gb_id, resource.gb_id, body, db, current_user)


@router.get("/front-end/preset/call")
async def channel_preset_call(
    channel_id: int = Query(..., alias="channelId"),
    preset_id: int = Query(..., alias="presetId"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    resource, asset = await _resolve_channel_asset_pair(db, current_user, channel_id)
    body = PresetRequest(preset_id=preset_id)
    return await call_preset(asset.gb_id, resource.gb_id, body, db, current_user)


@router.get("/front-end/preset/delete")
async def channel_preset_delete(
    channel_id: int = Query(..., alias="channelId"),
    preset_id: int = Query(..., alias="presetId"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    resource, asset = await _resolve_channel_asset_pair(db, current_user, channel_id)
    body = PresetRequest(preset_id=preset_id)
    return await delete_preset(asset.gb_id, resource.gb_id, body, db, current_user)


@router.get("/front-end/auxiliary")
async def channel_auxiliary(
    channel_id: int = Query(..., alias="channelId"),
    command: str = Query(...),
    auxiliary_id: int | None = Query(None, alias="auxiliaryId"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    resource, asset = await _resolve_channel_asset_pair(db, current_user, channel_id)
    body = AuxSwitchRequest(aux_id=auxiliary_id or 2, command=command)
    return await control_aux_switch(asset.gb_id, resource.gb_id, body, db, current_user)


@router.get("/front-end/wiper")
async def channel_wiper(
    channel_id: int = Query(..., alias="channelId"),
    command: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    resource, asset = await _resolve_channel_asset_pair(db, current_user, channel_id)
    body = WiperRequest(command=command)
    return await control_wiper(asset.gb_id, resource.gb_id, body, db, current_user)


@router.get("/front-end/ptz")
async def channel_ptz(
    channel_id: int = Query(..., alias="channelId"),
    command: str = Query(...),
    pan_speed: int | None = Query(None, alias="panSpeed"),
    tilt_speed: int | None = Query(None, alias="tiltSpeed"),
    zoom_speed: int | None = Query(None, alias="zoomSpeed"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    resource, asset = await _resolve_channel_asset_pair(db, current_user, channel_id)
    speed = int(
        max(
            [v for v in [pan_speed, tilt_speed, zoom_speed] if isinstance(v, int)],
            default=50,
        )
    )
    body = PTZRequest(command=command, speed=max(0, min(255, speed)))
    return await control_ptz(asset.gb_id, resource.gb_id, body, db, current_user)


@router.get("/front-end/fi/iris")
async def channel_fi_iris(
    channel_id: int = Query(..., alias="channelId"),
    command: str = Query(...),
    speed: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    resource, asset = await _resolve_channel_asset_pair(db, current_user, channel_id)
    body = IrisRequest(command=command, speed=128 if speed is None else int(speed))
    return await control_iris(asset.gb_id, resource.gb_id, body, db, current_user)


@router.get("/front-end/fi/focus")
async def channel_fi_focus(
    channel_id: int = Query(..., alias="channelId"),
    command: str = Query(...),
    speed: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    resource, asset = await _resolve_channel_asset_pair(db, current_user, channel_id)
    body = FocusRequest(command=command, speed=128 if speed is None else int(speed))
    return await control_focus(asset.gb_id, resource.gb_id, body, db, current_user)


@router.get("/playback")
async def channel_playback(
    channel_id: int = Query(..., alias="channelId"),
    start_time: str = Query(..., alias="startTime"),
    end_time: str = Query(..., alias="endTime"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    rows = await _resolve_resources_by_numeric_ids(
        db, current_user.tenant_id or "default", current_user.is_superuser, [channel_id]
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Channel not found")  # FIXED: 中文错误消息→英文
    r = rows[0]
    a = await db.get(Asset, r.asset_id)
    if not a:
        raise HTTPException(status_code=404, detail="Device not found")  # FIXED: 中文错误消息→英文
    return await playback_stream(
        device_id=a.gb_id,
        channel_id=r.gb_id,
        start_time=_parse_time_to_unix(start_time),
        end_time=_parse_time_to_unix(end_time),
        db=db,
        current_user=current_user,
    )


@router.get("/playback/query")
async def channel_playback_query(
    channel_id: int = Query(..., alias="channelId"),
    start_time: str = Query(..., alias="startTime"),
    end_time: str = Query(..., alias="endTime"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    rows = await _resolve_resources_by_numeric_ids(
        db, current_user.tenant_id or "default", current_user.is_superuser, [channel_id]
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Channel not found")  # FIXED: 中文错误消息→英文
    r = rows[0]
    a = await db.get(Asset, r.asset_id)
    if not a:
        raise HTTPException(status_code=404, detail="Device not found")  # FIXED: 中文错误消息→英文
    st = datetime.fromtimestamp(_parse_time_to_unix(start_time))
    et = datetime.fromtimestamp(_parse_time_to_unix(end_time))
    records = await query_device_records(
        device_id=a.gb_id,
        channel_id=r.gb_id,
        start_time=st,
        end_time=et,
        db=db,
        current_user=current_user,
        timeout_seconds=15,
    )
    return _to_common_record_items(records if isinstance(records, list) else [])


@router.get("/playback/stop")
async def channel_playback_stop(
    channel_id: int = Query(..., alias="channelId"),
    stream: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ = channel_id
    payload = StopStreamRequest(app="playback", stream=stream)
    return await stop_stream(payload=payload, db=db, current_user=current_user)


@router.get("/playback/pause")
async def channel_playback_pause(
    channel_id: int = Query(..., alias="channelId"),
    stream: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ = channel_id
    payload = PlaybackControlRequest(app="playback", stream=stream)
    return await playback_pause(payload=payload, db=db, current_user=current_user)


@router.get("/playback/resume")
async def channel_playback_resume(
    channel_id: int = Query(..., alias="channelId"),
    stream: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ = channel_id
    payload = PlaybackControlRequest(app="playback", stream=stream)
    return await playback_resume(payload=payload, db=db, current_user=current_user)


@router.get("/playback/seek")
async def channel_playback_seek(
    channel_id: int = Query(..., alias="channelId"),
    stream: str = Query(...),
    seek_time: int = Query(..., alias="seekTime"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ = channel_id
    payload = PlaybackSeekRequest(app="playback", stream=stream, seek_time=seek_time)
    return await playback_seek(payload=payload, db=db, current_user=current_user)


@router.get("/playback/speed")
async def channel_playback_speed(
    channel_id: int = Query(..., alias="channelId"),
    stream: str = Query(...),
    speed: float = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    _ = channel_id
    payload = PlaybackSpeedRequest(app="playback", stream=stream, speed=speed)
    return await playback_speed(payload=payload, db=db, current_user=current_user)


class ChannelStreamStatusResponse(BaseModel):
    channelId: int
    resourceId: str  # UUID (Resource.id)，供前端缓存 key 使用
    channelGbId: str
    streamActive: bool = False
    hasVideo: bool = False
    hasAudio: bool = True
    codec: str | None = None
    streamSchema: str | None = Field(default=None, alias="schema")
    bytesSpeed: int = 0
    readerCount: int = 0
    reason: str = ""
    nodeHost: str | None = None
    nodeHttpPort: int | None = None

    class Config:
        populate_by_name = True


@router.get("/stream-status", response_model=dict)
async def channel_stream_status(
    ids: str = Query(..., description="逗号分隔的通道ID列表，最多50个"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    批量探测通道的实时流状态（ZLM流探测）。
    返回每个通道当前是否有活跃的视频流（不发送SIP INVITE，仅读ZLM状态）。
    用于在通道列表中展示"可预览"状态，无需点开才知道。
    """
    # 解析并去重 ID：同时支持 UUID 字符串（Resource.id）和 numeric_channel_id（SHA256哈希）
    raw_ids = [x.strip() for x in str(ids).split(",") if x.strip()]
    if not raw_ids:
        return {"channels": []}
    if len(raw_ids) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 channels can be probed simultaneously")  # FIXED: 中文错误消息→英文

    # 将所有 ID 统一转为 numeric_channel_id 用于结果匹配
    # numeric_id -> (resource_uuid, numeric_id)
    # resource_uuid -> resource_uuid（直接查询）
    want_numeric_ids: set[int] = set()
    want_resource_uuids: list[str] = []

    for x in raw_ids:
        if x.isdigit():
            want_numeric_ids.add(int(x))
        else:
            # 可能是 UUID 格式的 resource.id
            try:
                # 验证是否为合法 UUID
                uuid.UUID(x)
                want_resource_uuids.append(x)
            except (ValueError, AttributeError):
                # 既不是数字也不是 UUID，忽略
                pass

    # 查询通道信息（返回 Resource, Asset 元组）
    # 策略1：按 numeric_channel_id 查
    numeric_rid_map: dict[int, tuple[Resource, Asset]] = {}  # numeric_id -> (Resource, Asset)
    # 策略2：按 resource UUID 查
    uuid_rid_map: dict[str, tuple[Resource, Asset]] = {}  # resource_uuid -> (Resource, Asset)

    # 按 numeric ID 查询（通过全表扫描 + 内存过滤，限制查询范围避免全表）
    if want_numeric_ids:
        # 先通过 GB ID 关联查询（更高效）
        stmt_numeric = (
            select(Resource, Asset)
            .join(Asset, Asset.id == Resource.asset_id)
            .where(Resource.node_type == "channel")
        )
        if not current_user.is_superuser:
            stmt_numeric = stmt_numeric.where(Asset.tenant_id == (current_user.tenant_id or "default"))
        result = await db.execute(stmt_numeric)
        for r, a in result.all():
            nid = numeric_channel_id(r.id)
            if nid in want_numeric_ids and nid not in numeric_rid_map:
                numeric_rid_map[nid] = (r, a)

    # 按 resource UUID 查询
    if want_resource_uuids:
        stmt_uuid = (
            select(Resource, Asset)
            .join(Asset, Asset.id == Resource.asset_id)
            .where(Resource.node_type == "channel", Resource.id.in_(want_resource_uuids))
        )
        if not current_user.is_superuser:
            stmt_uuid = stmt_uuid.where(Asset.tenant_id == (current_user.tenant_id or "default"))
        result = await db.execute(stmt_uuid)
        for r, a in result.all():
            numeric_id = numeric_channel_id(r.id)
            want_numeric_ids.add(numeric_id)
            if r.id not in uuid_rid_map:
                uuid_rid_map[r.id] = (r, a)

    # 合并两个映射：numeric_id -> (Resource, Asset)
    channel_map: dict[int, tuple[Resource, Asset]] = {**numeric_rid_map}
    for uuid_val, (r, a) in uuid_rid_map.items():
        nid = numeric_channel_id(r.id)
        if nid not in channel_map:
            channel_map[nid] = (r, a)

    # 查询当前活跃的流会话
    # 注意：必须按 app in ("live","rtp") 过滤并按 start_time 降序排序，
    # 因为邀请成功后 stream 会从 "device_channel" 更新为 "channel_ssrc" 格式，
    # 如果不过滤 app，可能匹配到旧会话的 stream（导致探测错误的流 ID）。
    active_rids = [str(r.id) for r, _ in channel_map.values()]
    stream_map: dict[str, str] = {}
    if active_rids:
        ss_stmt = (
            select(StreamSession.resource_id, StreamSession.stream)
            .where(
                StreamSession.resource_id.in_(active_rids),
                StreamSession.app.in_(["live", "rtp"]),
            )
            .order_by(StreamSession.start_time.desc())
        )
        ss_result = await db.execute(ss_stmt)
        for rid, sid in ss_result.all():
            rid_str = str(rid) if rid else ""
            sid_str = str(sid) if sid else ""
            if rid_str and sid_str and rid_str not in stream_map:
                stream_map[rid_str] = sid_str

    results: list[ChannelStreamStatusResponse] = []

    for nid in list(want_numeric_ids):
        entry = channel_map.get(nid)
        if not entry:
            continue
        r, a = entry
        resource_id = str(r.id)
        stream_key = stream_map.get(resource_id)

        # 从 capabilities 读取 has_video（Catalog 时写入）
        caps = r.capabilities or {}
        catalog_has_video = caps.get("has_video") if isinstance(caps, dict) else None

        # 根据类型判断默认 has_video
        # type=3 → 音频通道，type=2 → 报警通道，都没有视频
        channel_type = int(r.type or 1)
        default_has_video = channel_type in (1,)  # 仅摄像头默认有视频

        # 最终 has_video 优先级：Catalog 已知 > 类型推断
        final_has_video: bool | None = None
        if catalog_has_video is not None:
            final_has_video = bool(catalog_has_video)
        elif channel_type == 3:
            final_has_video = False
        elif channel_type == 2:
            final_has_video = False

        if not stream_key:
            results.append(ChannelStreamStatusResponse(
                channelId=nid,
                resourceId=resource_id,
                channelGbId=str(r.gb_id or ""),
                streamActive=False,
                hasVideo=final_has_video if final_has_video is not None else default_has_video,
                hasAudio=bool(getattr(r, "has_audio", True)),
                reason="no_active_stream",
                nodeHost=None,
                nodeHttpPort=None,
            ))
            continue

        # 查询关联的媒体节点
        # 必须按 app in ("live", "rtp") 过滤并按 start_time 排序，
        # 避免匹配到 playback 等其他 app 的旧会话。
        from app.core.media_nodes_db import get_db_media_node_by_id
        from app.core.media_nodes import get_node_by_id
        ss_node_stmt = select(
            StreamSession.media_server_id,
            StreamSession.app,
            StreamSession.stream,
        ).where(
            StreamSession.resource_id == resource_id,
            StreamSession.app.in_(["live", "rtp"]),
        ).order_by(StreamSession.start_time.desc()).limit(1)
        ss_node_result = await db.execute(ss_node_stmt)
        ss_row = ss_node_result.first()
        node_id = str(ss_row[0]) if ss_row and ss_row[0] is not None else None
        # 优先使用会话中实际的 app 和 stream（可能已被更新为 channel_ssrc 格式）
        effective_app = str(ss_row[1]) if ss_row and ss_row[1] is not None else "live"
        effective_stream = str(ss_row[2]) if ss_row and ss_row[2] is not None else stream_key

        node_host: str | None = None
        node_http_port: int | None = None

        if node_id:
            db_node = await get_db_media_node_by_id(db, node_id)
            if db_node:
                node_host = str(db_node.host or "")
                node_http_port = int(db_node.http_port or 0)
                node_secret = str(db_node.secret or "")
            else:
                mem_node = get_node_by_id(node_id)
                if mem_node:
                    node_host = str(mem_node.get("host") or "")
                    node_http_port = int(mem_node.get("http_port") or 0)
                    node_secret = str(mem_node.get("secret") or "")
                else:
                    node_secret = ""
        else:
            node_secret = ""

        if not node_host:
            results.append(ChannelStreamStatusResponse(
                channelId=nid,
                resourceId=resource_id,
                channelGbId=str(r.gb_id or ""),
                streamActive=False,
                hasVideo=final_has_video if final_has_video is not None else default_has_video,
                hasAudio=bool(getattr(r, "has_audio", True)),
                reason="media_node_not_found",
                nodeHost=None,
                nodeHttpPort=None,
            ))
            continue

        # 探测 ZLM
        stream_hints = _build_stream_match_hints(effective_stream, None)
        probe_ok, stream_found, media_item = await _probe_zlm_stream(
            node_host,
            node_http_port or 0,
            node_secret,
            effective_app or "live",
            effective_stream or stream_key or "",
            stream_hints=stream_hints,
            extra_apps=["rtp", "live"],
        )

        # 从 media_item 提取 tracks 信息判断 hasVideo/hasAudio
        has_video_stream = False
        has_audio_stream = False
        codec = None
        schema = None
        bytes_speed = 0
        reader_count = 0

        if isinstance(media_item, dict):
            schema = str(media_item.get("schema") or "")
            bytes_speed = int(media_item.get("bytesSpeed") or 0)
            reader_count = int(media_item.get("readerCount") or 0)
            tracks = media_item.get("tracks") or []
            if isinstance(tracks, list):
                for track in tracks:
                    codec_type = str(track.get("codec_type") or track.get("type") or "").lower()
                    codec_id = str(track.get("codec_id") or track.get("codec") or "").upper()
                    if codec_type in ("video", "0") or codec_id in ("V_H264", "V_H265", "V_MPEG4", "H264", "H265"):
                        has_video_stream = True
                        if not codec:
                            codec = str(track.get("codec") or codec_id or "")
                    elif codec_type in ("audio", "1") or codec_id in ("A_G711U", "A_G711A", "A_AAC", "G711U", "G711A"):
                        has_audio_stream = True
                        if not codec:
                            codec = str(track.get("codec") or codec_id or "")

        if not probe_ok:
            results.append(ChannelStreamStatusResponse(
                channelId=nid,
                resourceId=resource_id,
                channelGbId=str(r.gb_id or ""),
                streamActive=False,
                hasVideo=final_has_video if final_has_video is not None else default_has_video,
                hasAudio=bool(getattr(r, "has_audio", True)),
                reason="zlm_unreachable",
                nodeHost=node_host,
                nodeHttpPort=node_http_port,
            ))
        elif not stream_found:
            results.append(ChannelStreamStatusResponse(
                channelId=nid,
                resourceId=resource_id,
                channelGbId=str(r.gb_id or ""),
                streamActive=False,
                hasVideo=final_has_video if final_has_video is not None else default_has_video,
                hasAudio=bool(getattr(r, "has_audio", True)),
                reason="stream_not_found_in_zlm",
                nodeHost=node_host,
                nodeHttpPort=node_http_port,
            ))
        else:
            effective_has_video = has_video_stream
            if not has_video_stream and final_has_video is False:
                effective_has_video = False

            results.append(ChannelStreamStatusResponse(
                channelId=nid,
                resourceId=resource_id,
                channelGbId=str(r.gb_id or ""),
                streamActive=stream_found,
                hasVideo=effective_has_video,
                hasAudio=has_audio_stream or bool(getattr(r, "has_audio", True)),
                codec=codec,
                streamSchema=schema,
                bytesSpeed=bytes_speed,
                readerCount=reader_count,
                reason="",
                nodeHost=node_host,
                nodeHttpPort=node_http_port,
            ))

    return {"channels": [r.model_dump() for r in results]}