from fastapi import Query, APIRouter, Depends, HTTPException
from pydantic import BaseModel
import uuid
try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def _uuid7_hex(n: int = 16) -> str:
    return _uuid7_impl().hex[:n]

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db, AsyncSessionLocal
from app.api.deps import get_or_404
from app.models.resource import Resource
from app.models.asset import Asset
from app.models.record import Record
from app.models.stream_session import StreamSession
from app.models.device_record_download_task import DeviceRecordDownloadTask
import app.sip.record as sip_record_module
from app.sip.record_handler import record_query_cache, record_query_meta_cache
from app.sip.server import sip_server
import app.sip.invite as sip_invite_module
from app.models.user import User
from app.api import deps
from app.services.auth_audit import safe_auth_audit
from datetime import datetime, timedelta, timezone
import asyncio
import json
import hashlib
from app.core.redis import redis_client
from loguru import logger

router = APIRouter()

# C-01 unbounded cache — add max size and eviction
_DOWNLOAD_MAP_MAX = 5000
_INMEM_QUERIES_MAX = 5000

_download_playback_map: dict[tuple[str, str], dict] = {}

_inmem_queries: dict[str, dict] = {}

def _evict_if_full(d: dict, max_size: int) -> None:
    if len(d) > max_size:
        keys_to_remove = list(d.keys())[: len(d) - max_size // 2]
        for k in keys_to_remove:
            d.pop(k, None)

def _audit_tid(user: User) -> str:
    return (user.tenant_id or "default").strip() or "default"


async def _device_record_audit(
    db: AsyncSession,
    user: User,
    *,
    action: str,
    result: str,
    status_code: int,
    detail: str,
    extra_summary: str = "",
) -> None:
    await safe_auth_audit(
        db,
        module="device_record",
        action=action,
        source="device_record_query",
        operator=user.username or "unknown",
        result=result,
        tenant_id=_audit_tid(user),
        status_code=status_code,
        detail=detail,
        extra_summary=extra_summary,
    )


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _gen_query_id() -> str:
    return _uuid7_hex()


def _sn_key(sn: str) -> str:
    return f"gb:records:{sn}"


def _sn_meta_key(sn: str) -> str:
    return f"gb:records_meta:{sn}"


def _query_key(query_id: str) -> str:
    return f"gb:record_query:{query_id}"


def _query_fingerprint_key(fingerprint: str) -> str:
    return f"gb:record_query:fp:{fingerprint}"


def _make_query_fingerprint(
    tenant_id: str,
    device_id: str,
    channel_id: str,
    start_time: datetime,
    end_time: datetime,
) -> str:
    raw = "|".join(
        [
            str(tenant_id or "default"),
            str(device_id or "").strip(),
            str(channel_id or "").strip(),
            start_time.astimezone(timezone.utc).isoformat(),
            end_time.astimezone(timezone.utc).isoformat(),
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


async def _store_query(query_id: str, payload: dict, ttl_seconds: int = 900) -> None:
    if redis_client:
        try:
            await redis_client.setex(_query_key(query_id), ttl_seconds, json.dumps(payload, ensure_ascii=False))
            return
        except Exception as e:
            logger.warning(f"非关键操作失败: {e}")
    _evict_if_full(_inmem_queries, _INMEM_QUERIES_MAX)  # C-01
    _inmem_queries[query_id] = payload


async def _load_query(query_id: str) -> dict | None:
    if redis_client:
        try:
            raw = await redis_client.get(_query_key(query_id))
            if raw:
                return json.loads(raw)
        except Exception as e:
            logger.warning(f"非关键操作失败: {e}")
    return _inmem_queries.get(query_id)


async def _store_query_fingerprint(fingerprint: str, query_id: str, ttl_seconds: int = 900) -> None:
    if redis_client:
        try:
            await redis_client.setex(_query_fingerprint_key(fingerprint), ttl_seconds, str(query_id))
            return
        except Exception as e:
            logger.warning(f"非关键操作失败: {e}")
    _evict_if_full(_inmem_queries, _INMEM_QUERIES_MAX)  # C-01
    _inmem_queries[f"fp:{fingerprint}"] = {
        "query_id": str(query_id),
        "expires_at": (_now_utc() + timedelta(seconds=max(60, int(ttl_seconds or 900)))).isoformat(),
    }


async def _load_query_id_by_fingerprint(fingerprint: str) -> str | None:
    if redis_client:
        try:
            raw = await redis_client.get(_query_fingerprint_key(fingerprint))
            if raw:
                return str(raw)
        except Exception as e:
            logger.warning(f"非关键操作失败: {e}")
    local = _inmem_queries.get(f"fp:{fingerprint}") or {}
    query_id = str(local.get("query_id") or "").strip()
    if not query_id:
        return None
    try:
        expires_at = datetime.fromisoformat(str(local.get("expires_at") or "").replace("Z", "+00:00"))
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if _now_utc() > expires_at:
            _inmem_queries.pop(f"fp:{fingerprint}", None)
            return None
    except Exception as e:
        logger.warning(f"非关键操作失败: {e}")
    return query_id or None


async def _load_records_by_sn(sn: str) -> tuple[list[dict], dict]:
    meta: dict = {"sn": sn, "sum_num": 0, "received": 0}
    records: list[dict] = []
    if redis_client:
        try:
            raw = await redis_client.get(_sn_key(sn))
            if raw:
                data = json.loads(raw)
                if isinstance(data, list):
                    records = data
        except Exception as e:
            logger.warning(f"操作失败,返回默认值: {e}")
            records = []
        try:
            mraw = await redis_client.get(_sn_meta_key(sn))
            if mraw:
                m = json.loads(mraw)
                if isinstance(m, dict):
                    meta.update(m)
        except Exception as e:
            logger.warning(f"非关键操作失败: {e}")
    if not records:
        try:
            cached = record_query_cache.get(str(sn))
            if isinstance(cached, list):
                records = cached
        except Exception as e:
            logger.warning(f"操作失败,返回默认值: {e}")
            records = []
        try:
            m = record_query_meta_cache.get(str(sn))
            if isinstance(m, dict):
                meta.update(m)
        except Exception as e:
            logger.warning(f"非关键操作失败: {e}")
    try:
        meta["received"] = int(len(records))
    except Exception as e:
        logger.warning(f"操作失败,返回默认值: {e}")
        meta["received"] = 0
    return records, meta


def _slice(items: list, offset: int, limit: int) -> list:
    offset = max(0, int(offset or 0))
    limit = max(1, min(int(limit or 2000), 10000))
    return items[offset: offset + limit]


def _parse_created_at(value: str | None) -> datetime:
    try:
        dt = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception as e:
        logger.warning(f"操作失败,返回默认值: {e}")
        return _now_utc()


def _build_query_progress(query_payload: dict, records: list[dict], meta: dict) -> dict:
    sum_num = int(meta.get("sum_num") or 0)
    received = int(meta.get("received") or len(records) or 0)
    try:
        timeout_seconds = int(query_payload.get("timeout_seconds") or 15)
    except (TypeError, ValueError):
        timeout_seconds = 15
    created_at = _parse_created_at(query_payload.get("created_at"))
    age_seconds = max(0, int((_now_utc() - created_at).total_seconds()))
    status = "pending"
    if received > 0:
        status = "running"
    if sum_num > 0 and received >= sum_num:
        status = "done"
    if status != "done" and age_seconds > timeout_seconds:
        status = "timeout" if received == 0 else "partial"
    completion_rate = 0.0
    if sum_num > 0:
        completion_rate = max(0.0, min(1.0, float(received) / float(sum_num)))
    return {
        "status": status,
        "sum_num": sum_num,
        "received": received,
        "timeout_seconds": timeout_seconds,
        "age_seconds": age_seconds,
        "completion_rate": round(completion_rate, 4),
    }


class DeviceRecordQueryPayload(BaseModel):
    device_id: str
    channel_id: str
    start_time: datetime | None = None
    end_time: datetime | None = None
    timeout_seconds: int = 15
    # dict→Pydantic schema，设备录像查询接口无类型校验


@router.post("/device/queries")
async def start_device_record_query(
    payload: DeviceRecordQueryPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    device_id = str(payload.device_id or "").strip()
    channel_id = str(payload.channel_id or "").strip()
    start_time_raw = payload.start_time
    end_time_raw = payload.end_time
    try:
        timeout_seconds = int(payload.timeout_seconds or 15)
    except (TypeError, ValueError):
        timeout_seconds = 15
    timeout_seconds = max(3, min(timeout_seconds, 60))
    if not device_id or not channel_id:
        await _device_record_audit(
            db,
            current_user,
            action="start_device_record_query",
            result="failed",
            status_code=400,
            detail="device_id/channel_id required",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=400, detail="device_id/channel_id required")
    try:
        start_time = datetime.fromisoformat(str(start_time_raw).replace("Z", "+00:00"))
        end_time = datetime.fromisoformat(str(end_time_raw).replace("Z", "+00:00"))
    except Exception as e:
        logger.warning(f"非关键操作失败: {e}")
        await _device_record_audit(
            db,
            current_user,
            action="start_device_record_query",
            result="failed",
            status_code=400,
            detail="start_time/end_time must be ISO datetime",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=400, detail="start_time/end_time must be ISO datetime")
    if start_time > end_time:
        await _device_record_audit(
            db,
            current_user,
            action="start_device_record_query",
            result="failed",
            status_code=400,
            detail="start_time cannot be greater than end_time",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=400, detail="start_time cannot be greater than end_time")
    if (end_time - start_time) > timedelta(days=7):
        await _device_record_audit(
            db,
            current_user,
            action="start_device_record_query",
            result="failed",
            status_code=400,
            detail="Time range too large, please limit to 7 days",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=400, detail="Time range too large, please limit to 7 days")

    asset, resource = await _get_asset_and_resource_or_raise(db, device_id, channel_id, current_user)
    tenant_id = current_user.tenant_id or "default"

    if not asset.ip_addr:
        await _device_record_audit(
            db,
            current_user,
            action="start_device_record_query",
            result="failed",
            status_code=500,
            detail="Device network info missing",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=500, detail="Device network info missing")
    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        await _device_record_audit(
            db,
            current_user,
            action="start_device_record_query",
            result="failed",
            status_code=503,
            detail="Device signaling transport unavailable",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")

    if not sip_record_module.sip_record:
        await _device_record_audit(
            db,
            current_user,
            action="start_device_record_query",
            result="failed",
            status_code=500,
            detail="SIP service not ready",
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        raise HTTPException(status_code=500, detail="SIP service not ready")

    fingerprint = _make_query_fingerprint(
        tenant_id=tenant_id,
        device_id=device_id,
        channel_id=channel_id,
        start_time=start_time,
        end_time=end_time,
    )
    reused_query_id = await _load_query_id_by_fingerprint(fingerprint)
    if reused_query_id:
        reused_query = await _load_query(reused_query_id)
        if reused_query:
            reused_sn = str(reused_query.get("sn") or "")
            reused_records, reused_meta = await _load_records_by_sn(reused_sn)
            progress = _build_query_progress(reused_query, reused_records, reused_meta)
            if progress["status"] in {"pending", "running", "partial", "done"}:
                await _device_record_audit(
                    db,
                    current_user,
                    action="start_device_record_query",
                    result="success",
                    status_code=200,
                    detail="reused",
                    extra_summary=f"query_id={reused_query_id}; sn={reused_sn[:16]}; device_id={device_id}; channel_id={channel_id}",
                )
                return {
                    "query_id": reused_query_id,
                    "sn": reused_sn,
                    "status": progress["status"],
                    "timeout_seconds": progress["timeout_seconds"],
                    "reused": True,
                    "received": progress["received"],
                    "sum_num": progress["sum_num"],
                    "completion_rate": progress["completion_rate"],
                }

    try:
        sn = await sip_record_module.sip_record.query_device_record(
            asset,
            resource,
            ((asset.ip_addr, asset.port), asset.transport, transport),
            start_time,
            end_time,
        )
    except Exception as e:
        await _device_record_audit(
            db,
            current_user,
            action="start_device_record_query",
            result="failed",
            status_code=502,
            detail=str(e)[:200],
            extra_summary=f"device_id={device_id}; channel_id={channel_id}",
        )
        # 不向前端泄露 SIP 异常细节，仅返回通用提示
        raise HTTPException(
            status_code=502,
            detail="Record query failed. Please check device status and try again.",
        )

    query_id = _gen_query_id()
    await _store_query(
        query_id,
        {
            "query_id": query_id,
            "sn": str(sn),
            "device_id": device_id,
            "channel_id": channel_id,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "created_at": _now_utc().isoformat(),
            "timeout_seconds": timeout_seconds,
        },
        ttl_seconds=max(60, timeout_seconds + 900),
    )
    await _store_query_fingerprint(
        fingerprint=fingerprint,
        query_id=query_id,
        ttl_seconds=max(60, timeout_seconds + 900),
    )
    await _device_record_audit(
        db,
        current_user,
        action="start_device_record_query",
        result="success",
        status_code=200,
        detail="ok",
        extra_summary=f"query_id={query_id}; sn={str(sn)[:16]}; device_id={device_id}; channel_id={channel_id}",
    )
    return {"query_id": query_id, "sn": str(sn), "status": "pending", "timeout_seconds": timeout_seconds, "reused": False}


async def _get_asset_and_resource_or_raise(
    db: AsyncSession,
    device_id: str,
    channel_id: str,
    current_user: User,
) -> tuple[Asset, Resource]:
    """
    获取资产和资源，并进行权限和状态校验。
    如果不存在或状态异常，抛出带有友好提示的 HTTPException。
    """
    tenant_id = current_user.tenant_id or "default"

    # 1. 查找资产
    asset_stmt = select(Asset).where(Asset.gb_id == device_id)
    if not current_user.is_superuser:
        asset_stmt = asset_stmt.where(Asset.tenant_id == tenant_id)
    asset = (await db.execute(asset_stmt)).scalars().first()

    if not asset:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "Device not found. Please verify the device ID or check if the device has been deleted.",  # i18n
                "reason_code": "asset_not_found"
            }
        )

    # 2. 检查设备在线状态
    if asset.status == 0:
        raise HTTPException(
            status_code=503,
            detail={
                "message": f"Device {asset.name or asset.gb_id} is offline, cannot perform this operation.",  # i18n
                "reason_code": "device_offline"
            }
        )

    # 3. 查找资源（通道）
    resource_stmt = select(Resource).where(Resource.gb_id == channel_id, Resource.asset_id == asset.id)
    # 如果不是超级管理员，资源也需要检查租户（虽然资源已经关联了资产，资产已经检查过租户，但为了严谨性可以加上）
    resource = (await db.execute(resource_stmt)).scalars().first()

    if not resource:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "Channel not found under this device. Please verify the channel ID.",  # i18n
                "reason_code": "channel_not_found_under_device"
            }
        )

    return asset, resource


@router.get("/device/queries/{query_id}")
async def get_device_record_query_status(
    query_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(2000, ge=1, le=10000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    q = await _load_query(query_id)
    if not q:
        raise HTTPException(status_code=404, detail="query not found")
    sn = str(q.get("sn") or "")
    records, meta = await _load_records_by_sn(sn)
    progress = _build_query_progress(q, records, meta)

    items = _slice(records, offset, limit)
    return {
        "query_id": query_id,
        "sn": sn,
        "device_id": q.get("device_id"),
        "channel_id": q.get("channel_id"),
        "start_time": q.get("start_time"),
        "end_time": q.get("end_time"),
        "status": progress["status"],
        "sum_num": progress["sum_num"],
        "received": progress["received"],
        "completion_rate": progress["completion_rate"],
        "age_seconds": progress["age_seconds"],
        "timeout_seconds": progress["timeout_seconds"],
        "offset": int(offset or 0),
        "limit": int(limit or 0),
        "total_items": int(len(records)),
        "items": items,
    }


@router.get("/device/query")
async def query_device_records(
    device_id: str,
    channel_id: str,
    start_time: datetime,
    end_time: datetime,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    timeout_seconds: int = Query(15, ge=5, le=120),
):
    """
    Query records stored on the device (NVR/SD Card)
    """
    # 1. Get Asset & Resource
    if start_time > end_time:
        raise HTTPException(status_code=400, detail="start_time cannot be greater than end_time")
    if (end_time - start_time) > timedelta(days=7):
        raise HTTPException(status_code=400, detail="Time range too large, please limit to 7 days")

    asset, resource = await _get_asset_and_resource_or_raise(db, device_id, channel_id, current_user)

    # 2. Send RecordInfo Query
    if not asset.ip_addr:
        raise HTTPException(status_code=500, detail="Device network info missing")

    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")

    timeout_seconds = max(3, min(int(timeout_seconds or 15), 60))
    if not sip_record_module.sip_record:
        raise HTTPException(status_code=500, detail="SIP service not ready")
    sn = await sip_record_module.sip_record.query_device_record(asset, resource, ((asset.ip_addr, asset.port), asset.transport, transport), start_time, end_time)

    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        records, meta = await _load_records_by_sn(str(sn))
        if records:
            sum_num = int(meta.get("sum_num") or 0)
            if sum_num <= 0 or int(meta.get("received") or len(records)) >= sum_num:
                try:
                    record_query_cache.pop(str(sn), None)
                except Exception as e:
                    logger.warning(f"非关键操作失败: {e}")
                return records
        await asyncio.sleep(0.5)
    records, _ = await _load_records_by_sn(str(sn))
    return records or []


class DeviceRecordDownloadStart(BaseModel):
    device_id: str
    channel_id: str
    # FIX: [2026-07-04] 时间格式契约与回放端点（stream_play.py 的 /playback）不一致——
    # 回放端点用 Unix 整数秒，下载端点原本只接受 ISO 8601 字符串，导致统一传 Unix 秒
    # 的调用方收到 422。改为同时接受 Unix 秒(int/float) 与 ISO 8601(str)，向后兼容
    # 现有前端（RecordTimeline.vue 仍传 toISOString()）。[全栈工程师]
    start_time: int | float | str
    end_time: int | float | str
    download_speed: float | None = None


def _parse_download_time(value: int | float | str, field_name: str) -> datetime:
    """解析下载端点的时间参数，兼容 Unix 秒(int/float) 与 ISO 8601(str) 两种格式。

    根因：原实现仅支持 ISO 8601，与回放端点（stream_play.py 使用 Unix 整数秒）
    契约不一致。本函数统一两种格式的解析入口，避免在调用方分散判断。
    """
    # FIX: [2026-07-04] 新增 Unix 秒解析分支，对齐回放端点契约 [全栈工程师]
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError) as e:
            raise HTTPException(status_code=400, detail=f"{field_name} invalid unix timestamp: {e}")
    # ISO 8601 字符串分支（保持原有行为）
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"{field_name} must be ISO datetime or unix timestamp: {e}")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


@router.post("/download/start")
async def start_device_record_download(
    payload: DeviceRecordDownloadStart,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("records.view")),  # 角色检查→权限码检查
):
    device_id = str(payload.device_id or "").strip()
    channel_id = str(payload.channel_id or "").strip()
    if not device_id or not channel_id:
        raise HTTPException(status_code=400, detail="device_id/channel_id required")
    # FIX: [2026-07-04] 使用统一解析函数，兼容 Unix 秒与 ISO 8601 [全栈工程师]
    start_dt = _parse_download_time(payload.start_time, "start_time")
    end_dt = _parse_download_time(payload.end_time, "end_time")
    if start_dt > end_dt:
        raise HTTPException(status_code=400, detail="start_time cannot be greater than end_time")
    if (end_dt - start_dt) > timedelta(days=7):
        raise HTTPException(status_code=400, detail="Time range too large, please limit to 7 days")

    asset, resource = await _get_asset_and_resource_or_raise(db, device_id, channel_id, current_user)
    tenant_id = current_user.tenant_id or "default"

    if not asset.ip_addr:
        raise HTTPException(status_code=500, detail="Device network information missing")

    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")
    if not sip_invite_module.sip_invite:
        raise HTTPException(status_code=503, detail="SIP module not initialized")

    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())
    # FIX R22-SEVERE: INVITE 调用前 commit+close 释放 DB 连接，避免 ZLM HTTP + SIP 等待（5-30s）期间持有连接
    # 原实现完全没有 commit/close，DB 连接在 INVITE 全程被持有，多路并发下载时连接池耗尽
    await db.commit()
    await db.close()
    try:
        invite_ret = await sip_invite_module.sip_invite.send_playback_invite(
            asset,
            resource,
            ((asset.ip_addr, asset.port), asset.transport, transport),
            start_time=start_ts,
            end_time=end_ts,
            download_speed=int(payload.download_speed) if payload.download_speed is not None else None,
        )
    except Exception as e:
        # FIX R22-SEVERE: 不直接返回 str(e)，避免泄露 SIP/ZLM 信令细节（设备 IP/端口/ZLM host）
        logger.warning(f"[start_device_record_download] INVITE failed: {e}")
        raise HTTPException(status_code=502, detail="Playback INVITE failed. Please check device status and try again.")

    task = DeviceRecordDownloadTask(
        tenant_id=(asset.tenant_id or tenant_id),
        asset_id=asset.id,
        resource_id=resource.id,
        stream_session_id=str(invite_ret.get("stream_session_id") or "") or None,
        call_id=str(invite_ret.get("call_id") or "") or None,
        app=str(invite_ret.get("app") or "playback"),
        stream=str(invite_ret.get("stream") or ""),
        start_time=start_dt.replace(tzinfo=None),
        end_time=end_dt.replace(tzinfo=None),
        status="pending",
        record_ids="[]",
        last_error="",
    )
    if not task.stream:
        # FIX R22-SEVERE: INVITE 已成功但 stream id 缺失，释放已分配的 ZLM 资源避免泄漏
        _ss_id = str(invite_ret.get("stream_session_id") or "") or None
        if _ss_id:
            try:
                async with AsyncSessionLocal() as _cleanup_db:
                    _ss_row = (await _cleanup_db.execute(select(StreamSession).where(StreamSession.id == _ss_id))).scalars().first()
                    if _ss_row:
                        from app.api.v1.endpoints.stream import _release_stream_session
                        await _release_stream_session(_cleanup_db, _ss_row)
                        await _cleanup_db.commit()
            except Exception as _cleanup_err:
                logger.warning(f"[start_device_record_download] cleanup for missing stream failed: {_cleanup_err}")
        raise HTTPException(status_code=502, detail="INVITE succeeded but stream id missing. Resources released.")

    # R3-03 回放会话开始时初始化状态机为"playing"
    if task.call_id:
        from app.sip.playback_control import playback_control as _pb_ctrl
        if _pb_ctrl:
            # FIX: [2026-07-04] 传入 start_time 用于 NPT 相对时间计算 [全栈工程师]
            _pb_ctrl.set_playback_started(task.call_id, start_time=start_ts)

    # FIX R22-SEVERE: db 已 close，INVITE 后的所有 DB 操作改用独立 session
    async with AsyncSessionLocal() as task_db:
        task_db.add(task)
        try:
            await task_db.commit()
            await task_db.refresh(task)
        except Exception as _commit_err:
            logger.warning(f"[start_device_record_download] db.commit failed, releasing ZLM resources: {_commit_err}")
            try:
                await task_db.rollback()
            except Exception as _rb_err:
                # FIX [2026-07-17 P3-13]: 描述性日志替代 "silently_swallowed_exception"
                logger.warning(f"[start_device_record_download] db.rollback also failed: {_rb_err}")
            _ss_id = str(invite_ret.get("stream_session_id") or "") or None
            if _ss_id:
                try:
                    async with AsyncSessionLocal() as _cleanup_db:
                        _ss_row = (await _cleanup_db.execute(select(StreamSession).where(StreamSession.id == _ss_id))).scalars().first()
                        if _ss_row:
                            from app.api.v1.endpoints.stream import _release_stream_session
                            await _release_stream_session(_cleanup_db, _ss_row)
                            await _cleanup_db.commit()
                except Exception as _cleanup_err:
                    logger.warning(f"[start_device_record_download] cleanup after commit failure also failed: {_cleanup_err}")
            raise HTTPException(status_code=500, detail="internal_server_error")  # i18n

        # 录像下载回放控制 — 下载开始时记录 PlaybackControl 所需的 dialog 信息映射
        # 从 StreamSession 获取完整的 dialog 信息（from_tag/to_tag/cseq）
        _ss_from_tag = ""
        _ss_to_tag = ""
        _ss_cseq = 1
        if task.stream_session_id:
            ss_row = (await task_db.execute(select(StreamSession).where(StreamSession.id == task.stream_session_id))).scalars().first()
            if ss_row:
                _ss_from_tag = str(ss_row.from_tag or "")
                _ss_to_tag = str(ss_row.to_tag or "")
                _ss_cseq = int(ss_row.cseq or 1)
        _evict_if_full(_download_playback_map, _DOWNLOAD_MAP_MAX)  # C-01
        _download_playback_map[(device_id, task.id)] = {
            "call_id": task.call_id or str(invite_ret.get("call_id") or ""),
            "from_tag": _ss_from_tag,
            "to_tag": _ss_to_tag,
            "cseq": _ss_cseq,
            "channel_id": channel_id,
            "stream_session_id": task.stream_session_id or "",
        }

        total_seconds = max(0, int((end_dt - start_dt).total_seconds()))
        return {
            "task_id": task.id,
            "status": task.status,
            "app": task.app,
            "stream": task.stream,
            "total_seconds": total_seconds,
        }


@router.post("/download/stop/{task_id}")
async def stop_device_record_download(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("records.view")),  # 角色检查→权限码检查
):
    tid = str(task_id or "").strip()
    if not tid:
        raise HTTPException(status_code=400, detail="task_id required")
    tenant_id = current_user.tenant_id or "default"
    stmt = select(DeviceRecordDownloadTask).where(DeviceRecordDownloadTask.id == tid)
    if not current_user.is_superuser:
        stmt = stmt.where(DeviceRecordDownloadTask.tenant_id == tenant_id)
    task = get_or_404(await db.execute(stmt), detail="DeviceRecordDownloadTask not found")  # ORM查询结果空值判断

    try:
        from app.api.v1.endpoints.stream import _release_stream_session
        from app.services.zlm_stream_control import close_zlm_stream
        session_row = None
        if task.stream_session_id:
            session_row = (await db.execute(select(StreamSession).where(StreamSession.id == task.stream_session_id))).scalars().first()
        if session_row:
            await _release_stream_session(db, session_row)
            await db.commit()
        elif task.app and task.stream:
            try:
                await close_zlm_stream(task.app, task.stream)
            except Exception as e:
                logger.warning(f"非关键操作失败: {e}")
    except Exception as e:
        logger.warning(f"非关键操作失败: {e}")

    task.status = "cancelled"
    await db.commit()
    return {"ok": True, "task_id": task.id, "status": task.status}


@router.get("/download/progress/{task_id}")
async def get_device_record_download_progress(
    task_id: str,
    auto_stop: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    tid = str(task_id or "").strip()
    if not tid:
        raise HTTPException(status_code=400, detail="task_id required")
    tenant_id = current_user.tenant_id or "default"
    stmt = select(DeviceRecordDownloadTask).where(DeviceRecordDownloadTask.id == tid)
    if not current_user.is_superuser:
        stmt = stmt.where(DeviceRecordDownloadTask.tenant_id == tenant_id)
    task = get_or_404(await db.execute(stmt), detail="DeviceRecordDownloadTask not found")  # ORM查询结果空值判断

    total_seconds = max(0, int((task.end_time - task.start_time).total_seconds()))
    records_stmt = select(Record).where(
        Record.stream_id == task.stream,
        Record.record_app == task.app,
        Record.resource_id == task.resource_id,
    ).order_by(Record.start_time.asc())
    if not current_user.is_superuser:
        records_stmt = records_stmt.where(Record.tenant_id == tenant_id)
    recs = (await db.execute(records_stmt)).scalars().all()

    recorded_end = None
    record_ids: list[str] = []
    for r in recs:
        record_ids.append(str(r.id))
        if r.end_time and (recorded_end is None or r.end_time > recorded_end):
            recorded_end = r.end_time
    recorded_seconds = 0
    if recorded_end:
        recorded_seconds = int(max(0.0, (min(recorded_end, task.end_time) - task.start_time).total_seconds()))
    percent = 0
    if total_seconds > 0:
        percent = max(0, min(100, int(recorded_seconds * 100 / total_seconds)))

    status = str(task.status or "pending")
    if status not in {"done", "failed", "cancelled"}:
        if record_ids and recorded_end and recorded_end >= task.end_time:
            status = "done"
        elif record_ids:
            status = "running"
        else:
            status = "pending"
    task.status = status
    task.record_ids = json.dumps(record_ids, ensure_ascii=False)
    await db.commit()

    if status == "done" and auto_stop:
        try:
            from app.api.v1.endpoints.stream import _release_stream_session
            session_row = None
            if task.stream_session_id:
                session_row = (await db.execute(select(StreamSession).where(StreamSession.id == task.stream_session_id))).scalars().first()
            if session_row:
                await _release_stream_session(db, session_row)
                await db.commit()
        except Exception as e:
            logger.warning(f"非关键操作失败: {e}")

    download_items = [{"record_id": str(r.id), "download_url": f"/api/v1/record/download/{r.id}"} for r in recs]
    return {
        "task_id": task.id,
        "status": status,
        "app": task.app,
        "stream": task.stream,
        "total_seconds": total_seconds,
        "recorded_seconds": recorded_seconds,
        "percent": percent,
        "records": download_items,
        "last_error": task.last_error or "",
    }


# ---- 录像下载回放控制端点 ----
# 通过 PlaybackControl 单例发送 MANSRTSP 控制命令，对下载中的回放流执行暂停/恢复/拖动

async def _get_download_playback_context(
    device_id: str, task_id: str, db: AsyncSession, current_user: User
) -> tuple[Asset, Resource, DeviceRecordDownloadTask, dict]:
    """获取下载任务的回放控制上下文，校验权限和状态。"""
    tenant_id = current_user.tenant_id or "default"
    stmt = select(DeviceRecordDownloadTask).where(DeviceRecordDownloadTask.id == task_id)
    if not current_user.is_superuser:
        stmt = stmt.where(DeviceRecordDownloadTask.tenant_id == tenant_id)
    task = get_or_404(await db.execute(stmt), detail="DeviceRecordDownloadTask not found")

    if task.status in ("done", "cancelled", "failed"):
        raise HTTPException(status_code=409, detail=f"Cannot control download in status: {task.status}")

    asset_stmt = select(Asset).where(Asset.id == task.asset_id)
    asset = (await db.execute(asset_stmt)).scalars().first()
    if not asset or not asset.ip_addr:
        raise HTTPException(status_code=503, detail="Device not found or offline")

    resource_stmt = select(Resource).where(Resource.id == task.resource_id)
    resource = (await db.execute(resource_stmt)).scalars().first()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    # 从缓存或 StreamSession 获取 dialog 信息
    ctx = _download_playback_map.get((device_id, task_id))
    if not ctx:
        # 尝试从 StreamSession 重新加载
        if task.stream_session_id:
            ss = (await db.execute(select(StreamSession).where(StreamSession.id == task.stream_session_id))).scalars().first()
            if ss:
                ctx = {
                    "call_id": str(ss.call_id or task.call_id or ""),
                    "from_tag": str(ss.from_tag or ""),
                    "to_tag": str(ss.to_tag or ""),
                    "cseq": int(ss.cseq or 1),
                    "channel_id": str(resource.gb_id or ""),
                    "stream_session_id": str(ss.id or ""),
                }
                _evict_if_full(_download_playback_map, _DOWNLOAD_MAP_MAX)  # C-01
                _download_playback_map[(device_id, task_id)] = ctx
    if not ctx:
        raise HTTPException(status_code=500, detail="Playback control context not found for this download task")

    return asset, resource, task, ctx


@router.post("/device-record/{device_id}/download/{task_id}/pause")
async def pause_download_playback(
    device_id: str,
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("records.view")),  # 角色检查→权限码检查
):
    """暂停下载中的回放流 — 录像下载回放控制"""
    from app.sip.playback_control import playback_control

    if not playback_control:
        raise HTTPException(status_code=503, detail="PlaybackControl not initialized")

    asset, resource, task, ctx = await _get_download_playback_context(device_id, task_id, db, current_user)

    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")

    cseq = int(ctx.get("cseq", 1)) + 1
    ctx["cseq"] = cseq

    # R3-04 检查send_pause返回值，状态机拒绝时返回错误
    result = await playback_control.send_pause(
        asset,
        channel_id=ctx["channel_id"],
        transport_info=((asset.ip_addr, asset.port), asset.transport, transport),
        call_id=ctx["call_id"],
        cseq=cseq,
        from_tag=ctx.get("from_tag"),
        to_tag=ctx.get("to_tag"),
    )
    if not result:
        raise HTTPException(status_code=409, detail="Playback state transition not allowed")
    return {"ok": True, "task_id": task_id, "action": "pause"}


@router.post("/device-record/{device_id}/download/{task_id}/resume")
async def resume_download_playback(
    device_id: str,
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("records.view")),  # 角色检查→权限码检查
):
    """恢复下载中的回放流 — 录像下载回放控制"""
    from app.sip.playback_control import playback_control

    if not playback_control:
        raise HTTPException(status_code=503, detail="PlaybackControl not initialized")

    asset, resource, task, ctx = await _get_download_playback_context(device_id, task_id, db, current_user)

    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")

    cseq = int(ctx.get("cseq", 1)) + 1
    ctx["cseq"] = cseq

    # R3-04 检查send_resume返回值，状态机拒绝时返回错误
    result = await playback_control.send_resume(
        asset,
        channel_id=ctx["channel_id"],
        transport_info=((asset.ip_addr, asset.port), asset.transport, transport),
        call_id=ctx["call_id"],
        cseq=cseq,
        from_tag=ctx.get("from_tag"),
        to_tag=ctx.get("to_tag"),
    )
    if not result:
        raise HTTPException(status_code=409, detail="Playback state transition not allowed")
    return {"ok": True, "task_id": task_id, "action": "resume"}


class DownloadSeekRequest(BaseModel):
    seek_time: int  # Unix timestamp in seconds


@router.post("/device-record/{device_id}/download/{task_id}/seek")
async def seek_download_playback(
    device_id: str,
    task_id: str,
    payload: DownloadSeekRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("records.view")),  # 角色检查→权限码检查
):
    """拖动下载中的回放流到指定时间点 — 录像下载回放控制"""
    from app.sip.playback_control import playback_control

    if not playback_control:
        raise HTTPException(status_code=503, detail="PlaybackControl not initialized")

    asset, resource, task, ctx = await _get_download_playback_context(device_id, task_id, db, current_user)

    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")

    cseq = int(ctx.get("cseq", 1)) + 1
    ctx["cseq"] = cseq

    # R4-02 检查send_seek返回值
    result = await playback_control.send_seek(
        asset,
        channel_id=ctx["channel_id"],
        transport_info=((asset.ip_addr, asset.port), asset.transport, transport),
        call_id=ctx["call_id"],
        seek_time=payload.seek_time,
        cseq=cseq,
        from_tag=ctx.get("from_tag"),
        to_tag=ctx.get("to_tag"),
    )
    if not result:
        raise HTTPException(status_code=409, detail="Playback state transition not allowed")
    return {"ok": True, "task_id": task_id, "action": "seek", "seek_time": payload.seek_time}


class DownloadSpeedRequest(BaseModel):
    speed: float  # 倍速值（0.1~4.0，1.0 为正常速度）


@router.post("/device-record/{device_id}/download/{task_id}/speed")
async def speed_download_playback(
    device_id: str,
    task_id: str,
    payload: DownloadSpeedRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_permission("records.view")),
):
    """设置下载回放倍速。

    FIX: [2026-07-04] 新增下载回放倍速端点 [全栈工程师]
    根因：下载回放控制端点缺少倍速控制，PlaybackControl.send_play_with_speed 从未被调用。
    """
    from app.sip.playback_control import playback_control

    if not playback_control:
        raise HTTPException(status_code=503, detail="PlaybackControl not initialized")

    # 参数校验
    if payload.speed <= 0 or payload.speed > 8.0:
        raise HTTPException(status_code=400, detail="speed must be between 0.1 and 8.0")

    asset, resource, task, ctx = await _get_download_playback_context(device_id, task_id, db, current_user)

    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")

    cseq = int(ctx.get("cseq", 1)) + 1
    ctx["cseq"] = cseq

    result = await playback_control.send_play_with_speed(
        asset,
        channel_id=ctx["channel_id"],
        transport_info=((asset.ip_addr, asset.port), asset.transport, transport),
        call_id=ctx["call_id"],
        speed=payload.speed,
        cseq=cseq,
        from_tag=ctx.get("from_tag"),
        to_tag=ctx.get("to_tag"),
    )
    if not result:
        raise HTTPException(status_code=409, detail="Speed control failed (send failure or invalid speed)")
    return {"ok": True, "task_id": task_id, "action": "speed", "speed": payload.speed}
