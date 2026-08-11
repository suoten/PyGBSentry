import asyncio
from loguru import logger
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from sqlalchemy import select  # TECH_DEBT: 直接依赖具体实现，未来改为Protocol接口注入
from fastapi import HTTPException

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.asset import Asset
from app.models.resource import Resource
from app.api.v1.endpoints.devices.devices_control import get_channel_snapshot
from app.services.auth_audit import safe_auth_audit



_task: asyncio.Task | None = None
LOG_DIR = "logs/snapshot_refresh"


def _snap_tok(s: str) -> str:
    return str(s or "").strip().replace(" ", "%20").replace("\t", "_")


def _append_snapshot_refresh_event(
    *, asset_gb: str, channel_gb: str, stream_type: str, ok: bool, err: str | None = None
) -> None:
    try:
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR, exist_ok=True)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_file = os.path.join(LOG_DIR, f"snapshot_refresh_{today}.log")
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        a = _snap_tok(asset_gb)
        c = _snap_tok(channel_gb)
        st = _snap_tok(stream_type or "main")
        if ok:
            line = f"[{timestamp}] asset={a} channel={c} stream_type={st} ok=true\n"
        else:
            err_s = " ".join(str(err or "").split())[:300]
            line = f"[{timestamp}] asset={a} channel={c} stream_type={st} ok=false err={err_s}\n"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as e:
        logger.warning(f"Error: {e}")

async def _plugin_snapshot_audit(
    db,
    *,
    action: str,
    result: str,
    status_code: int,
    detail: str,
    extra_summary: str = "",
) -> None:
    # 后台插件没有真实登录用户；固定 tenant_id，避免审计字段缺失
    await safe_auth_audit(
        db,
        module="plugins",
        action=action,
        source="plugin_runtime",
        operator="snapshot_refresh",
        result=result,
        tenant_id="default",
        status_code=status_code,
        detail=detail,
        extra_summary=extra_summary,
    )


def _in_window(now: datetime, start_hour: int, end_hour: int) -> bool:
    start = int(start_hour or 0) % 24
    end = int(end_hour or 0) % 24
    if start == end:
        return True
    if start < end:
        return start <= now.hour < end
    return now.hour >= start or now.hour < end


def _snap_path(asset_gb_id: str, channel_gb_id: str, stream_type: str) -> str:
    st = str(stream_type or "main").strip().lower()
    if st in {"0", "main"}:
        st = "main"
    elif st in {"1", "sub"}:
        st = "sub"
    else:
        st = "main"
    return os.path.join("www", "snap", str(asset_gb_id), f"{channel_gb_id}_{st}.jpg")


def _resolve_default_stream_type(resource: Resource) -> str:
    caps = getattr(resource, "capabilities", None) or {}
    if isinstance(caps, dict):
        st = str(caps.get("default_stream_type") or "main").strip().lower()
    else:
        st = "main"
    if st in {"0", "main"}:
        return "main"
    if st in {"1", "sub"}:
        return "sub"
    return "main"


def _is_stale(path: str, ttl_seconds: int) -> bool:
    if not os.path.exists(path):
        return True
    # 用户要求：空闲时间取快照只针对没有快照的通道，已有快照不再自动更新
    return False


async def _refresh_once():
    if not settings.SNAPSHOT_REFRESH_ENABLED:
        return
    now = datetime.now(timezone.utc)
    if not _in_window(
        now,
        settings.SNAPSHOT_REFRESH_WINDOW_START_HOUR,
        settings.SNAPSHOT_REFRESH_WINDOW_END_HOUR,
    ):
        return
    ttl = settings.SNAPSHOT_REFRESH_TTL_SECONDS
    limit = max(1, settings.SNAPSHOT_REFRESH_MAX_PER_CYCLE)
    prefer_existing = settings.SNAPSHOT_REFRESH_PREFER_EXISTING
    allow_invite = settings.SNAPSHOT_REFRESH_ALLOW_INVITE

    async with AsyncSessionLocal() as db:
        stmt = (
            select(Resource, Asset)
            .join(Asset, Asset.id == Resource.asset_id)
            .where(Resource.node_type == "channel")
            .where(Resource.status == 1)
            .where(Asset.status == 1)
            .limit(limit * 3)
        )
        rows = (await db.execute(stmt)).all()

        candidates: list[dict[str, str]] = []
        for resource, asset in rows:
            gb_id = str(getattr(resource, "gb_id", "") or "").strip()
            if not gb_id:
                continue
            st = _resolve_default_stream_type(resource)
            asset_gb_id = str(asset.gb_id or "").strip()
            path = _snap_path(asset_gb_id, gb_id, st)
            if _is_stale(path, ttl):
                candidates.append(
                    {
                        "channel_gb_id": gb_id,
                        "asset_gb_id": asset_gb_id,
                        "stream_type": st,
                        "snap_path": path,
                    }
                )
            if len(candidates) >= limit:
                break

        if not candidates:
            return

        fake_user = SimpleNamespace(is_superuser=True, tenant_id="default")
        should_audit = allow_invite
        for c in candidates:
            try:
                channel_gb_id = c.get("channel_gb_id") or ""
                st = c.get("stream_type") or "main"
                snap_path = str(c.get("snap_path") or "")
                await get_channel_snapshot(
                    channel_id=channel_gb_id,
                    stream_type=st,
                    prefer_existing=prefer_existing,
                    allow_invite=allow_invite,
                    force=True,
                    db=db,
                    current_user=fake_user,
                )
                if not (snap_path and os.path.exists(snap_path) and os.path.getsize(snap_path) > 128):
                    if not allow_invite:
                        await get_channel_snapshot(
                            channel_id=channel_gb_id,
                            stream_type=st,
                            prefer_existing=prefer_existing,
                            allow_invite=True,
                            force=True,
                            db=db,
                            current_user=fake_user,
                        )
                if not (snap_path and os.path.exists(snap_path) and os.path.getsize(snap_path) > 128):
                    raise HTTPException(status_code=404, detail="snapshot_not_generated")
                _append_snapshot_refresh_event(
                    asset_gb=str(c.get("asset_gb_id") or ""),
                    channel_gb=channel_gb_id,
                    stream_type=st,
                    ok=True,
                )
                if should_audit:
                    await _plugin_snapshot_audit(
                        db,
                        action="snapshot_refresh",
                        result="success",
                        status_code=200,
                        detail="ok",
                        extra_summary=(
                            f"asset_gb_id={c.get('asset_gb_id')}; "
                            f"channel_id={channel_gb_id}; "
                            f"stream_type={st}; "
                            f"snap_path={c.get('snap_path')}"
                        ),
                    )
            except HTTPException as he:
                _append_snapshot_refresh_event(
                    asset_gb=str(c.get("asset_gb_id") or ""),
                    channel_gb=str(c.get("channel_gb_id") or ""),
                    stream_type=str(c.get("stream_type") or "main"),
                    ok=False,
                    err=f"http {getattr(he, 'status_code', 500)} {str(getattr(he, 'detail', '') or '')[:200]}",
                )
                if should_audit:
                    await _plugin_snapshot_audit(
                        db,
                        action="snapshot_refresh",
                        result="failed",
                        status_code=int(getattr(he, "status_code", 500) or 500),
                        detail=str(getattr(he, "detail", "") or "http_error")[:200],
                        extra_summary=(
                            f"asset_gb_id={c.get('asset_gb_id')}; "
                            f"channel_id={c.get('channel_gb_id')}; "
                            f"stream_type={c.get('stream_type')}"
                        ),
                    )
                continue
            except Exception as ex:
                _append_snapshot_refresh_event(
                    asset_gb=str(c.get("asset_gb_id") or ""),
                    channel_gb=str(c.get("channel_gb_id") or ""),
                    stream_type=str(c.get("stream_type") or "main"),
                    ok=False,
                    err=str(ex),
                )
                if should_audit:
                    await _plugin_snapshot_audit(
                        db,
                        action="snapshot_refresh",
                        result="failed",
                        status_code=500,
                        detail="snapshot_refresh_exception",
                        extra_summary=(
                            f"asset_gb_id={c.get('asset_gb_id')}; "
                            f"channel_id={c.get('channel_gb_id')}; "
                            f"stream_type={c.get('stream_type')}"
                        ),
                    )
                continue


async def _loop():
    interval = max(30, settings.SNAPSHOT_REFRESH_INTERVAL_SECONDS)
    while True:
        try:
            await _refresh_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(f"[SnapshotRefresh] Error: {exc}")
        await asyncio.sleep(interval)


async def start():
    global _task
    if _task and not _task.done():
        return
    if not settings.SNAPSHOT_REFRESH_ENABLED:
        return
    _task = asyncio.create_task(_loop())


async def stop():
    global _task
    if not _task:
        return
    try:
        _task.cancel()
        await asyncio.wait_for(_task, timeout=5.0)
    except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
        logger.warning("(asyncio.CancelledError, asyncio.TimeoutError, Exception) occurred")
    _task = None


