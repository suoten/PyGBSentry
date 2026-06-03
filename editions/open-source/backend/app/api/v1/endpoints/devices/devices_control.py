"""设备控制/同步端点（目录同步/校时/查询/通道快照等）。"""

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.models.asset import Asset
from app.models.resource import Resource
from app.models.user import User
from app.models.stream_session import StreamSession
from app.api import deps
from app.core.config import settings
from app.core.media_nodes import get_node_by_id, get_media_nodes
from app.core.media_nodes_db import release_lease
import app.sip.invite as sip_invite_module
from app.services.zlm_stream_control import close_zlm_stream
from app.sip.server import sip_server
from app.sip.catalog_runtime import get_device_catalog_runtime
from typing import Any
from datetime import datetime, timezone
import os
import time
import asyncio
import contextlib
from app.core.http_client import get_http_client
import httpx
import logging

from . _common import (
    _normalize_default_stream_type,
    _tenant_id_for_user,
    BatchChannelSnapPayload,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# -------------------- Channel Snapshot --------------------
# 用于通道列表"快照"列：自动拉一帧并做短缓存
SNAPSHOT_SEMAPHORE = asyncio.Semaphore(settings.SNAPSHOT_CONCURRENCY_LIMIT)
SNAPSHOT_TTL_SECONDS = settings.SNAPSHOT_TTL_SECONDS


def _snapshot_cache_file(asset_gb_id: str, channel_gb_id: str, stream_type: str) -> str:
    st = str(stream_type or "main").strip().lower()
    if st in {"0", "main"}:
        st = "main"
    elif st in {"1", "sub"}:
        st = "sub"
    else:
        st = "main"
    cache_dir = os.path.join("www", "snap", str(asset_gb_id))
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"{channel_gb_id}_{st}.jpg")


async def _try_snap_async(host: str, http_port: int, secret: str, app: str, stream: str, cache_file: str, attempts: int = 2) -> bool:
    api = f"http://{host}:{http_port}/index/api/getSnap"
    zlm_attempts = max(1, min(int(attempts or 1), 3))
    for _ in range(zlm_attempts):
        local_flv = f"http://{host}:{http_port}/{app}/{stream}.live.flv?_snap_ts={int(time.time() * 1000)}"
        params = {
            "url": local_flv,
            "timeout_sec": 5,
            "expire_sec": 0,
            "secret": secret,
        }
        try:
            r = await (await get_http_client()).get(api, params=params, timeout=6)  # FIXED: 同步requests→异步httpx，避免阻塞事件循环
            if r.status_code == 200:
                data = r.content
                if data and len(data) > 128 and data.startswith(b"\xff\xd8"):
                    with open(cache_file, "wb") as f:
                        f.write(data)
                    return True
        except Exception as e:
            logger.warning(f"Error: {e}")
        await asyncio.sleep(0.5)

    stream_url = f"http://{host}:{http_port}/{app}/{stream}.live.flv"
    cap = None
    try:
        import cv2  # type: ignore
        # Explicitly use FFMPEG backend to avoid CAP_IMAGES fallback and assertion errors when connection refused
        cap = cv2.VideoCapture(stream_url, cv2.CAP_FFMPEG)
        with contextlib.suppress(Exception):
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        read_attempts = max(4, int(attempts or 1) * 2)
        for _ in range(read_attempts):
            ret, frame = cap.read()
            if ret and frame is not None:
                cv2.imwrite(cache_file, frame)
                return True
            await asyncio.sleep(0.25)
    except Exception as e:
        logger.warning(f"Error: {e}")
    finally:
        if cap is not None:
            with contextlib.suppress(Exception):
                cap.release()
    return False


@router.get("/channels/{channel_id}/snap")
async def get_channel_snapshot(
    channel_id: str,
    stream_type: str = "auto",  # auto/main/sub
    prefer_existing: bool = Query(True),
    allow_invite: bool = Query(True),
    force: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    返回通道截图（JPG）。

    为了对齐通道主/辅码流偏好：
    - 若 stream_type=auto，会读取 Resource.capabilities.default_stream_type。
    - 未产生实时流时，会临时发起一次 INVITE 获取首帧，然后立即释放。
    """
    t0 = time.perf_counter()
    existing_snap_timeout = float(getattr(settings, "SNAPSHOT_EXISTING_TIMEOUT_SECONDS", 12.0) or 12.0)
    invite_snap_timeout = float(getattr(settings, "SNAPSHOT_INVITE_TIMEOUT_SECONDS", 40.0) or 40.0)
    db_query_ms = 0.0
    existing_lookup_ms = 0.0
    existing_snap_ms = 0.0
    invite_ms = 0.0
    invite_snap_ms = 0.0
    cleanup_ms = 0.0
    stage = "init"
    from sqlalchemy import or_
    stmt = select(Resource, Asset).join(Asset, Asset.id == Resource.asset_id).where(
        or_(Resource.gb_id == channel_id, Resource.id == channel_id)
    )
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
    db_t0 = time.perf_counter()
    result = await db.execute(stmt)
    db_query_ms = (time.perf_counter() - db_t0) * 1000
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Channel not found or permission denied")
    resource: Resource = row[0]
    asset: Asset = row[1]

    # stream_type 解析
    st = (stream_type or "auto").strip().lower()
    if st == "auto":
        caps = resource.capabilities or {}
        if isinstance(caps, dict):
            st = str(caps.get("default_stream_type") or "main").strip().lower()
        else:
            st = "main"
    if st in {"0", "main"}:
        st = "main"
    elif st in {"1", "sub"}:
        st = "sub"
    else:
        st = "main"

    snap_key = str(resource.gb_id or channel_id)
    cache_file = _snapshot_cache_file(str(asset.gb_id), snap_key, st)
    if not force and os.path.exists(cache_file):
        stage = "cache_hit"
        logger.info(
            "snapshot_profile channel=%s stage=%s total_ms=%.2f db_ms=%.2f prefer_existing=%s allow_invite=%s force=%s",
            snap_key,
            stage,
            (time.perf_counter() - t0) * 1000,
            db_query_ms,
            prefer_existing,
            allow_invite,
            force,
        )
        return FileResponse(cache_file, media_type="image/jpeg")

    async def _find_existing_stream_node() -> tuple[dict | None, str, str]:
        nodes = get_media_nodes()
        for n in nodes:
            host = str(n.get("host") or "").strip()
            try:
                http_port = int(n.get("http_port") or 0)  # FIXED: 防止http_port非数字时ValueError
            except ValueError:
                http_port = 0
            if not host or not http_port:
                continue
            sec = str(n.get("secret") or settings.MEDIA_SERVER_SECRET or "").strip()
            url = f"http://{host}:{http_port}/index/api/getMediaList"
            try:
                r = await (await get_http_client()).get(url, params={"secret": sec, "app": "live"}, timeout=0.6)  # FIXED: 同步requests→异步httpx，避免阻塞事件循环
                if r.status_code >= 400:
                    continue
                payload = r.json()
                if payload.get("code") not in (0, "0"):
                    continue
                lst = payload.get("data")
                if not isinstance(lst, list):
                    continue
                for item in lst:
                    if not isinstance(item, dict):
                        continue
                    st_name = str(item.get("stream") or "")
                    if str(item.get("app") or "") == "live" and (st_name == snap_key or st_name.startswith(f"{snap_key}_")):
                        return n, "live", st_name
            except Exception:
                continue
        return None, "", ""

    if prefer_existing:
        existing_t0 = time.perf_counter()
        # 1. 优先从 StreamSession 中找活跃记录，这样最快且精确
        ss_stmt = select(StreamSession).where(StreamSession.resource_id == resource.id, StreamSession.app == "live").order_by(StreamSession.start_time.desc())
        ss_res = await db.execute(ss_stmt)
        ss = ss_res.scalars().first()
        existing_node = None
        actual_app = "live"
        actual_stream_id = snap_key
        
        if ss and ss.media_server_id:
            node = get_node_by_id(ss.media_server_id)
            if node:
                existing_node = node
                actual_app = ss.app or "live"
                actual_stream_id = ss.stream or snap_key
        
        if not existing_node:
            # 2. 兜底，遍历 ZLM 查询
            existing_node, actual_app, actual_stream_id = await _find_existing_stream_node()  # FIXED: 同步requests→异步httpx，避免阻塞事件循环
            
        if existing_node and actual_stream_id:
            host = str(existing_node.get("host") or "").strip()
            http_port = int(existing_node.get("http_port") or 0)
            sec = str(existing_node.get("secret") or settings.MEDIA_SERVER_SECRET or "").strip()
            if host and http_port:
                stage = "existing_snap"
                existing_snap_t0 = time.perf_counter()
                try:
                    ok = await asyncio.wait_for(
                        _try_snap_async(host, http_port, sec, actual_app, actual_stream_id, cache_file, 2),
                        timeout=existing_snap_timeout,
                    )  # FIXED: 同步requests→异步httpx，避免阻塞事件循环
                except asyncio.TimeoutError:
                    ok = False
                    logger.warning(
                        "snapshot_profile channel=%s stage=existing_timeout timeout_s=%.2f",
                        snap_key,
                        existing_snap_timeout,
                    )
                existing_snap_ms = (time.perf_counter() - existing_snap_t0) * 1000
                if ok and os.path.exists(cache_file):
                    with contextlib.suppress(Exception):
                        caps = resource.capabilities or {}
                        if isinstance(caps, dict):
                            caps = {**caps}
                            caps["snapshot"] = {
                                "file": cache_file,
                                "stream_type": st,
                                "updated_at": datetime.now(timezone.utc).isoformat() + "Z",
                            }
                            resource.capabilities = caps
                            await db.commit()
                    existing_lookup_ms = (time.perf_counter() - existing_t0) * 1000
                    stage = "existing_ok"
                    logger.info(
                        "snapshot_profile channel=%s stage=%s total_ms=%.2f db_ms=%.2f existing_lookup_ms=%.2f existing_snap_ms=%.2f prefer_existing=%s allow_invite=%s force=%s",
                        snap_key,
                        stage,
                        (time.perf_counter() - t0) * 1000,
                        db_query_ms,
                        existing_lookup_ms,
                        existing_snap_ms,
                        prefer_existing,
                        allow_invite,
                        force,
                    )
                    return FileResponse(cache_file, media_type="image/jpeg")
        existing_lookup_ms = (time.perf_counter() - existing_t0) * 1000

    if not allow_invite:
        # 如果不允许主动呼叫（如前端列表默认请求），且没有已有流/缓存
        # 直接返回 404 会导致前端 el-image 组件在控制台报错
        # 我们可以返回一个极小的透明 1x1 GIF，避免报错
        transparent_gif = b'GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'
        from fastapi.responses import Response
        stage = "allow_invite_false"
        logger.info(
            "snapshot_profile channel=%s stage=%s total_ms=%.2f db_ms=%.2f existing_lookup_ms=%.2f prefer_existing=%s allow_invite=%s force=%s",
            snap_key,
            stage,
            (time.perf_counter() - t0) * 1000,
            db_query_ms,
            existing_lookup_ms,
            prefer_existing,
            allow_invite,
            force,
        )
        return Response(content=transparent_gif, media_type="image/gif")

    if not asset.ip_addr:
        raise HTTPException(status_code=500, detail="Device network information missing")
    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")

    async with SNAPSHOT_SEMAPHORE:
        if not sip_invite_module.sip_invite:
            raise HTTPException(status_code=500, detail="SIP service not ready")
        stage = "invite"
        invite_t0 = time.perf_counter()
        invite_result = await sip_invite_module.sip_invite.send_invite(
            asset,
            resource,
            ((asset.ip_addr, asset.port), asset.transport, transport),
            stream_type=st,
        )
        invite_ms = (time.perf_counter() - invite_t0) * 1000
        stream_session_id = invite_result.get("stream_session_id")
        node_id = invite_result.get("node_id")
        invited_app = str(invite_result.get("app") or "live")
        invited_stream = str(invite_result.get("stream") or snap_key)

        node = get_node_by_id(node_id)
        if not node:
            node = {"host": settings.MEDIA_SERVER_HOST, "http_port": settings.MEDIA_SERVER_HTTP_PORT}
        media_host = str(node.get("host") or settings.MEDIA_SERVER_HOST)
        media_http_port = int(node.get("http_port") or settings.MEDIA_SERVER_HTTP_PORT)
        media_sec = str(node.get("secret") or settings.MEDIA_SERVER_SECRET or "").strip()

        loop = asyncio.get_running_loop()
        ok = False
        try:
            stage = "invite_snap"
            invite_snap_t0 = time.perf_counter()
            try:
                ok = await asyncio.wait_for(
                    _try_snap_async(media_host, media_http_port, media_sec, invited_app, invited_stream, cache_file, 15),
                    timeout=invite_snap_timeout,
                )  # FIXED: 同步requests→异步httpx，避免阻塞事件循环
            except asyncio.TimeoutError:
                ok = False
                logger.warning(
                    "snapshot_profile channel=%s stage=invite_timeout timeout_s=%.2f",
                    snap_key,
                    invite_snap_timeout,
                )
            invite_snap_ms = (time.perf_counter() - invite_snap_t0) * 1000
        finally:
            if stream_session_id:
                cleanup_t0 = time.perf_counter()
                with contextlib.suppress(Exception):
                    # Check if there are active viewers before closing the stream
                    async def _get_reader_count():
                        try:
                            sec = str(node.get("secret") or settings.MEDIA_SERVER_SECRET or "")
                            url = f"http://{media_host}:{media_http_port}/index/api/getMediaList"
                            r = await (await get_http_client()).get(url, params={"secret": sec, "app": invited_app, "stream": invited_stream}, timeout=1)  # FIXED: 同步requests→异步httpx，避免阻塞事件循环
                            if r.status_code == 200:
                                data = r.json()
                                if data.get("code") in (0, "0") and data.get("data"):
                                    # FIXED: 使用.get()防止ZLM返回格式异常时KeyError
                                    for item in data.get("data", []):
                                        if str(item.get("app")) == invited_app and str(item.get("stream")) == invited_stream:
                                            return int(item.get("readerCount") or 0)
                        except Exception as e:
                            logger.warning(f"Error: {e}")
                        return 0
                        
                    # Give ZLM a tiny bit of time to update readerCount after OpenCV releases
                    await asyncio.sleep(0.5)
                    reader_count = await _get_reader_count()  # FIXED: 同步requests→异步httpx，避免阻塞事件循环
                    
                    if reader_count == 0:
                        ss_stmt = select(StreamSession).where(StreamSession.id == stream_session_id)
                        ss_res = await db.execute(ss_stmt)
                        ss = ss_res.scalars().first()
                        if ss:
                            with contextlib.suppress(Exception):
                                if sip_invite_module.sip_invite:
                                    await sip_invite_module.sip_invite.send_bye(asset, ss, resource.gb_id)
                            with contextlib.suppress(Exception):
                                await close_zlm_stream(app=ss.app, stream=ss.stream, node_id=ss.media_server_id)
                            with contextlib.suppress(Exception):
                                await release_lease(db, getattr(ss, "media_port_lease_id", None))
                            with contextlib.suppress(Exception):
                                await db.delete(ss)
                                await db.commit()
                cleanup_ms = (time.perf_counter() - cleanup_t0) * 1000

        if not ok or not os.path.exists(cache_file):
            stage = "failed"
            logger.warning(
                "snapshot_profile channel=%s stage=%s total_ms=%.2f db_ms=%.2f existing_lookup_ms=%.2f existing_snap_ms=%.2f invite_ms=%.2f invite_snap_ms=%.2f cleanup_ms=%.2f prefer_existing=%s allow_invite=%s force=%s",
                snap_key,
                stage,
                (time.perf_counter() - t0) * 1000,
                db_query_ms,
                existing_lookup_ms,
                existing_snap_ms,
                invite_ms,
                invite_snap_ms,
                cleanup_ms,
                prefer_existing,
                allow_invite,
                force,
            )
            raise HTTPException(status_code=404, detail="Screenshot failed or channel has no stream")

        with contextlib.suppress(Exception):
            caps = resource.capabilities or {}
            if isinstance(caps, dict):
                caps = {**caps}
                caps["snapshot"] = {
                    "file": cache_file,
                    "stream_type": st,
                    "updated_at": datetime.now(timezone.utc).isoformat() + "Z",
                }
                resource.capabilities = caps
                await db.commit()

        stage = "invite_ok"
        logger.info(
            "snapshot_profile channel=%s stage=%s total_ms=%.2f db_ms=%.2f existing_lookup_ms=%.2f existing_snap_ms=%.2f invite_ms=%.2f invite_snap_ms=%.2f cleanup_ms=%.2f prefer_existing=%s allow_invite=%s force=%s",
            snap_key,
            stage,
            (time.perf_counter() - t0) * 1000,
            db_query_ms,
            existing_lookup_ms,
            existing_snap_ms,
            invite_ms,
            invite_snap_ms,
            cleanup_ms,
            prefer_existing,
            allow_invite,
            force,
        )
        return FileResponse(cache_file, media_type="image/jpeg")


@router.post("/channels/snap-batch")
async def batch_channel_snapshot(
    payload: BatchChannelSnapPayload | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    profile: bool = Query(False),
    item_timeout_seconds: float = Query(
        float(getattr(settings, "SNAPSHOT_BATCH_ITEM_TIMEOUT_SECONDS", 45.0) or 45.0),
        ge=5.0,
        le=120.0,
    ),
):
    """
    接收一个前端发送的 channel_id 列表，并在服务端并发（限制并发数以防卡死）调用快照获取逻辑。
    无需前端发出多个请求。
    """
    if payload is None:
        raise HTTPException(status_code=400, detail='Request body cannot be empty, example: {"channel_ids":["34020000001320000001"]}')  # FIXED-P3: i18n
    channel_ids = list(dict.fromkeys(str(x).strip() for x in payload.channel_ids if str(x).strip()))
    if not channel_ids:
        return {"status": "ok", "count": 0}

    sem = asyncio.Semaphore(max(1, int(getattr(settings, "SNAPSHOT_BATCH_CONCURRENCY", 5) or 5)))
    stats = {"ok": 0, "failed": 0}
    profile_items: list[dict[str, Any]] = []
    profile_lock = asyncio.Lock()
    batch_t0 = time.perf_counter()

    async def _snap(cid: str):
        async with sem:
            ch_t0 = time.perf_counter()
            error_type = ""
            try:
                async for new_db in get_db():
                    await asyncio.wait_for(
                        get_channel_snapshot(
                            channel_id=cid,
                            stream_type="auto",
                            prefer_existing=True,
                            allow_invite=True,
                            force=True,
                            db=new_db,
                            current_user=current_user
                        ),
                        timeout=item_timeout_seconds,
                    )
                    stats["ok"] += 1
                    elapsed_ms = (time.perf_counter() - ch_t0) * 1000
                    if profile:
                        async with profile_lock:
                            profile_items.append({"channel_id": cid, "ok": True, "elapsed_ms": round(elapsed_ms, 2)})
                    return
            except asyncio.TimeoutError:
                error_type = "TimeoutError"
                stats["failed"] += 1
                elapsed_ms = (time.perf_counter() - ch_t0) * 1000
                if profile:
                    async with profile_lock:
                        profile_items.append({"channel_id": cid, "ok": False, "elapsed_ms": round(elapsed_ms, 2), "error": error_type})
                logger.warning(
                    "snapshot_batch_item channel=%s ok=%s elapsed_ms=%.2f error=%s",
                    cid,
                    False,
                    elapsed_ms,
                    error_type,
                )
            except Exception as e:
                error_type = type(e).__name__
                stats["failed"] += 1
                elapsed_ms = (time.perf_counter() - ch_t0) * 1000
                if profile:
                    async with profile_lock:
                        profile_items.append({"channel_id": cid, "ok": False, "elapsed_ms": round(elapsed_ms, 2), "error": error_type})
                logger.warning(
                    "snapshot_batch_item channel=%s ok=%s elapsed_ms=%.2f error=%s",
                    cid,
                    False,
                    elapsed_ms,
                    error_type or "",
                )

    tasks = [_snap(cid) for cid in channel_ids]
    await asyncio.gather(*tasks)
    total_ms = (time.perf_counter() - batch_t0) * 1000
    result: dict[str, Any] = {"status": "ok", "count": len(channel_ids), "ok": stats["ok"], "failed": stats["failed"]}
    if profile:
        elapsed_list = [float(x.get("elapsed_ms") or 0.0) for x in profile_items]
        result["profile"] = {
            "total_ms": round(total_ms, 2),
            "avg_ms": round((sum(elapsed_list) / len(elapsed_list)) if elapsed_list else 0.0, 2),
            "max_ms": round(max(elapsed_list) if elapsed_list else 0.0, 2),
            "min_ms": round(min(elapsed_list) if elapsed_list else 0.0, 2),
            "items": profile_items,
        }
    logger.info(
        "snapshot_batch_summary count=%s ok=%s failed=%s total_ms=%.2f profile=%s",
        len(channel_ids),
        stats["ok"],
        stats["failed"],
        total_ms,
        profile,
    )
    return result


# ==================== 设备控制/同步接口 ====================

@router.post("/{device_id}/time-sync")
async def device_time_sync(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """国标网络校时：向指定设备下发一次 TimeSync MESSAGE（北京时间）。"""
    import app.sip.commander as sip_commander_module

    stmt = select(Asset).where(Asset.gb_id == device_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
    result = await db.execute(stmt)
    asset = result.scalars().first()

    # 兼容：path 参数可能是 Asset.id（你前端使用的 id）而不是 gb_id
    if not asset:
        stmt2 = select(Asset).where(Asset.id == device_id)
        if not current_user.is_superuser:
            stmt2 = stmt2.where(Asset.tenant_id == (current_user.tenant_id or "default"))
        asset = (await db.execute(stmt2)).scalars().first()

    if not asset:
        raise HTTPException(status_code=404, detail="Device not found")
    if not asset.ip_addr or not asset.port:
        raise HTTPException(status_code=400, detail="Device network info missing, cannot send time sync")
    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")
    if not getattr(sip_commander_module, "sip_commander", None):
        raise HTTPException(status_code=503, detail="SIP service not ready")
    await sip_commander_module.sip_commander.send_time_sync(
        asset.gb_id,
        ((asset.ip_addr, asset.port), asset.transport, transport),
    )
    return {"status": "ok", "message": "Time sync command sent"}  # FIXED: hardcoded Chinese → English


@router.get("/{device_id}/catalog-runtime")
async def get_catalog_runtime(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    # 兼容：path 参数可能是 Asset.id 或 gb_id
    stmt = select(Asset).where(Asset.gb_id == device_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
    asset = (await db.execute(stmt)).scalars().first()

    if not asset:
        stmt2 = select(Asset).where(Asset.id == device_id)
        if not current_user.is_superuser:
            stmt2 = stmt2.where(Asset.tenant_id == (current_user.tenant_id or "default"))
        asset = (await db.execute(stmt2)).scalars().first()

    if not asset:
        raise HTTPException(status_code=404, detail="Device not found")

    return {
        "device_id": asset.id,
        "gb_id": asset.gb_id,
        "catalog_sync_runtime": await get_device_catalog_runtime(asset.gb_id),
    }


@router.post("/{device_id}/sync")
async def sync_device_channels(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    """
    同步设备通道（发送Catalog查询命令）
    
    向设备发送目录查询命令，设备会返回其下的所有通道信息。
    注意：实际的通道数据更新需要设备响应后，在SIP消息处理器中处理。
    """
    from app.sip.handlers import _schedule_device_catalog_retry
    
    stmt = select(Asset).where(Asset.gb_id == device_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
    result = await db.execute(stmt)
    asset = result.scalars().first()
    
    if not asset:
        raise HTTPException(status_code=404, detail="Device not found")
    
    if not asset.ip_addr:
        raise HTTPException(status_code=500, detail="Device network information missing")
    
    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")
    
    transport_info = ((asset.ip_addr, asset.port), asset.transport, transport)
    # 使用与注册目录下发一致的"带重试+运行态打点"流程
    # 这样前端才能拿到 catalog_sync_runtime 的进度/状态
    await _schedule_device_catalog_retry(device_id, transport_info)
    
    return {
        "status": "ok",
        "message": "Device channel sync request sent",  # FIXED-P3: i18n
        "device_id": device_id,
        "sn": None,
        "note": "Channel info will be updated automatically after device responds"  # FIXED-P3: i18n
    }


@router.post("/{device_id}/query-info")
async def query_device_info(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    """
    查询设备信息（发送DeviceInfo查询命令）
    
    向设备发送信息查询命令，获取设备的详细信息（厂商、型号、固件版本等）。
    """
    from app.sip.catalog import catalog as catalog_singleton, Catalog
    
    stmt = select(Asset).where(Asset.gb_id == device_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
    result = await db.execute(stmt)
    asset = result.scalars().first()
    
    if not asset:
        raise HTTPException(status_code=404, detail="Device not found")
    
    if not asset.ip_addr:
        raise HTTPException(status_code=500, detail="Device network information missing")
    
    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")
    
    # Send device info query
    catalog = catalog_singleton or Catalog(sip_server)
    sn = await catalog.send_device_info_query(
        asset,
        ((asset.ip_addr, asset.port), asset.transport, transport)
    )
    
    return {
        "status": "ok",
        "message": "Device info query request sent",  # FIXED-P3: i18n
        "device_id": device_id,
        "sn": sn
    }


@router.post("/{device_id}/query-status")
async def query_device_status(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    """
    查询设备状态（发送DeviceStatus查询命令）
    
    向设备发送状态查询命令，获取设备的在线状态、报警状态等信息。
    """
    from app.sip.catalog import catalog as catalog_singleton, Catalog
    from loguru import logger
    
    stmt = select(Asset).where(Asset.gb_id == device_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
    result = await db.execute(stmt)
    asset = result.scalars().first()
    
    if not asset:
        raise HTTPException(status_code=404, detail="Device not found")
    
    if not asset.ip_addr:
        raise HTTPException(status_code=500, detail="Device network information missing")
    
    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")
    
    # Send device status query
    catalog = catalog_singleton or Catalog(sip_server)
    sn = await catalog.send_device_status_query(
        asset,
        ((asset.ip_addr, asset.port), asset.transport, transport)
    )
    
    return {
        "status": "ok",
        "message": "Device status query request sent",  # FIXED: hardcoded Chinese → English
        "device_id": device_id,
        "sn": sn
    }


@router.get("/{device_id}/directory-query")
async def query_directory(
    device_id: str,
    parent_directory_id: str = Query(""),
    begin_time: str = Query(""),
    end_time: str = Query(""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    """
    # FIXED: GB28181-2022 文件目录检索
    向设备发送文件目录检索查询命令，获取文件目录信息。
    """
    import app.sip.commander as sip_commander_module

    stmt = select(Asset).where(Asset.gb_id == device_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
    result = await db.execute(stmt)
    asset = result.scalars().first()

    if not asset:
        stmt2 = select(Asset).where(Asset.id == device_id)
        if not current_user.is_superuser:
            stmt2 = stmt2.where(Asset.tenant_id == (current_user.tenant_id or "default"))
        asset = (await db.execute(stmt2)).scalars().first()

    if not asset:
        raise HTTPException(status_code=404, detail="Device not found")

    if not asset.ip_addr:
        raise HTTPException(status_code=400, detail="Device network info missing, cannot send directory query")

    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")

    if not getattr(sip_commander_module, "sip_commander", None):
        raise HTTPException(status_code=503, detail="SIP service not ready")

    sn = await sip_commander_module.sip_commander.send_directory_query(
        asset.gb_id,
        ((asset.ip_addr, asset.port), asset.transport, transport),
        parent_directory_id=parent_directory_id,
        begin_time=begin_time,
        end_time=end_time,
    )

    return {
        "status": "ok",
        "message": "Directory query request sent",
        "device_id": device_id,
        "sn": sn,
    }


@router.get("/{device_id}/alarm-code-query")
async def query_alarm_code(
    device_id: str,
    alarm_code_type: str = Query("1"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    """
    # FIXED: GB28181-2022 布防报警分类查询
    向设备发送布防报警分类查询命令，获取报警分类信息。
    alarm_code_type: 1=报警设备类型, 2=报警方式
    """
    import app.sip.commander as sip_commander_module

    stmt = select(Asset).where(Asset.gb_id == device_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
    result = await db.execute(stmt)
    asset = result.scalars().first()

    if not asset:
        stmt2 = select(Asset).where(Asset.id == device_id)
        if not current_user.is_superuser:
            stmt2 = stmt2.where(Asset.tenant_id == (current_user.tenant_id or "default"))
        asset = (await db.execute(stmt2)).scalars().first()

    if not asset:
        raise HTTPException(status_code=404, detail="Device not found")

    if not asset.ip_addr:
        raise HTTPException(status_code=400, detail="Device network info missing, cannot send alarm code query")

    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")

    if not getattr(sip_commander_module, "sip_commander", None):
        raise HTTPException(status_code=503, detail="SIP service not ready")

    sn = await sip_commander_module.sip_commander.send_alarm_code_query(
        asset.gb_id,
        ((asset.ip_addr, asset.port), asset.transport, transport),
        alarm_code_type=alarm_code_type,
    )

    return {
        "status": "ok",
        "message": "Alarm code query request sent",
        "device_id": device_id,
        "sn": sn,
    }


@router.post("/{device_id}/config-upload")
async def config_upload(
    device_id: str,
    config_type: str = Body("BasicParam", embed=True),
    config_data: str = Body("", embed=True),
    channel_id: str = Body("", embed=True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    """
    设备配置设置/下发（发送ConfigUpload命令）

    向设备下发配置，支持 BasicParam(基本参数)、VideoParamOpt(视频参数-编码)、VideoParamEnc(视频参数-编码)等。
    """
    # FIXED: 实现ConfigUpload设备配置设置/下发
    import app.sip.commander as sip_commander_module

    stmt = select(Asset).where(Asset.gb_id == device_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
    result = await db.execute(stmt)
    asset = result.scalars().first()

    # 兼容：path 参数可能是 Asset.id 而不是 gb_id
    if not asset:
        stmt2 = select(Asset).where(Asset.id == device_id)
        if not current_user.is_superuser:
            stmt2 = stmt2.where(Asset.tenant_id == (current_user.tenant_id or "default"))
        asset = (await db.execute(stmt2)).scalars().first()

    if not asset:
        raise HTTPException(status_code=404, detail="Device not found")

    if not asset.ip_addr:
        raise HTTPException(status_code=500, detail="Device network information missing")

    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")

    if not getattr(sip_commander_module, "sip_commander", None):
        raise HTTPException(status_code=503, detail="SIP service not ready")

    sn = await sip_commander_module.sip_commander.send_config_upload(
        device_id=asset.gb_id,
        channel_id=channel_id or asset.gb_id,
        transport_info=((asset.ip_addr, asset.port), asset.transport, transport),
        config_type=config_type,
        config_data=config_data,
    )

    return {
        "status": "ok",
        "message": "Config upload command sent",
        "device_id": device_id,
        "sn": sn,
    }


@router.post("/{device_id}/config-download")
async def config_download(
    device_id: str,
    config_type: str = Body("BasicParam", embed=True),
    channel_id: str = Body("", embed=True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    """
    Query device configuration (send ConfigDownload command)

    Query device configuration parameters, supports BasicParam, VideoParamOpt, VideoParamEnc, etc.
    """
    # FIXED-P4: 补充ConfigDownload API端点，SIP层已有但API层缺失，与wvp对齐
    import app.sip.commander as sip_commander_module

    stmt = select(Asset).where(Asset.gb_id == device_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
    result = await db.execute(stmt)
    asset = result.scalars().first()

    if not asset:
        stmt2 = select(Asset).where(Asset.id == device_id)
        if not current_user.is_superuser:
            stmt2 = stmt2.where(Asset.tenant_id == (current_user.tenant_id or "default"))
        asset = (await db.execute(stmt2)).scalars().first()

    if not asset:
        raise HTTPException(status_code=404, detail="Device not found")

    if not asset.ip_addr:
        raise HTTPException(status_code=500, detail="Device network information missing")

    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
    if transport is None:
        raise HTTPException(status_code=503, detail="Device signaling transport unavailable")

    if not getattr(sip_commander_module, "sip_commander", None):
        raise HTTPException(status_code=503, detail="SIP service not ready")

    sn = await sip_commander_module.sip_commander.send_config_download(
        device_id=asset.gb_id,
        channel_id=channel_id or asset.gb_id,
        transport_info=((asset.ip_addr, asset.port), asset.transport, transport),
        config_type=config_type,
    )

    return {
        "status": "ok",
        "message": "Config download query sent",
        "device_id": device_id,
        "sn": sn,
    }


# ==================== 移动位置订阅接口 ====================

@router.post("/{device_id}/mobile-position/subscribe")
async def mobile_position_subscribe(
    device_id: str,
    expires: int = Body(3600),
    interval: int = Body(5),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    """
    启动移动位置订阅

    向设备发送 MobilePosition SUBSCRIBE 请求，设备将按指定间隔上报位置信息。
    - expires: 订阅有效期（秒），默认3600
    - interval: 位置上报间隔（秒），默认5
    """
    from app.sip.subscribe_manager import subscribe_manager

    stmt = select(Asset).where(Asset.gb_id == device_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
    result = await db.execute(stmt)
    asset = result.scalars().first()

    # 兼容：path 参数可能是 Asset.id 而不是 gb_id
    if not asset:
        stmt2 = select(Asset).where(Asset.id == device_id)
        if not current_user.is_superuser:
            stmt2 = stmt2.where(Asset.tenant_id == (current_user.tenant_id or "default"))
        asset = (await db.execute(stmt2)).scalars().first()

    if not asset:
        raise HTTPException(status_code=404, detail="Device not found")

    if not asset.ip_addr:
        raise HTTPException(status_code=500, detail="Device network information missing")

    ok = await subscribe_manager.start_mobile_position_subscribe(
        device_id=asset.gb_id,
        expires=expires,
        interval=interval,
    )
    if not ok:
        raise HTTPException(status_code=503, detail="Failed to send MobilePosition SUBSCRIBE")

    return {
        "status": "ok",
        "message": "MobilePosition subscribe request sent",
        "device_id": asset.gb_id,
        "expires": expires,
        "interval": interval,
    }


@router.post("/{device_id}/mobile-position/unsubscribe")
async def mobile_position_unsubscribe(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_roles(["owner", "admin", "operator"])),
):
    """
    停止移动位置订阅

    向设备发送 MobilePosition SUBSCRIBE expires=0 取消订阅。
    """
    from app.sip.subscribe_manager import subscribe_manager

    stmt = select(Asset).where(Asset.gb_id == device_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
    result = await db.execute(stmt)
    asset = result.scalars().first()

    if not asset:
        stmt2 = select(Asset).where(Asset.id == device_id)
        if not current_user.is_superuser:
            stmt2 = stmt2.where(Asset.tenant_id == (current_user.tenant_id or "default"))
        asset = (await db.execute(stmt2)).scalars().first()

    if not asset:
        raise HTTPException(status_code=404, detail="Device not found")

    ok = await subscribe_manager.stop_mobile_position_subscribe(device_id=asset.gb_id)

    return {
        "status": "ok",
        "message": "MobilePosition unsubscribe request sent" if ok else "No active MobilePosition subscription found",
        "device_id": asset.gb_id,
        "unsubscribed": ok,
    }


@router.get("/{device_id}/position")
async def get_device_position(
    device_id: str,
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    获取设备最新位置

    返回设备最近的位置记录，包括经纬度、速度、方向、海拔等。
    - limit: 返回记录数量，默认10
    """
    from app.models.device_position import DevicePosition

    stmt = select(Asset).where(Asset.gb_id == device_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == (current_user.tenant_id or "default"))
    result = await db.execute(stmt)
    asset = result.scalars().first()

    if not asset:
        stmt2 = select(Asset).where(Asset.id == device_id)
        if not current_user.is_superuser:
            stmt2 = stmt2.where(Asset.tenant_id == (current_user.tenant_id or "default"))
        asset = (await db.execute(stmt2)).scalars().first()

    if not asset:
        raise HTTPException(status_code=404, detail="Device not found")

    pos_stmt = (
        select(DevicePosition)
        .where(DevicePosition.device_id == asset.gb_id)
        .order_by(DevicePosition.time.desc())
        .limit(limit)
    )
    pos_result = await db.execute(pos_stmt)
    positions = pos_result.scalars().all()

    return {
        "device_id": asset.gb_id,
        "count": len(positions),
        "positions": [
            {
                "latitude": p.latitude,
                "longitude": p.longitude,
                "speed": p.speed,
                "direction": p.direction,
                "altitude": p.altitude,
                "time": p.time.isoformat() if p.time else None,
            }
            for p in positions
        ],
    }