import asyncio
import datetime
import os

from sqlalchemy import select  # TECH_DEBT: 直接依赖具体实现，未来改为Protocol接口注入

from app.core.config import settings
from app.core.media_nodes import get_all_media_from_nodes
from app.db.session import AsyncSessionLocal
from app.models.access_source import AccessSource
from app.models.push_channel import PushChannel
from app.models.resource import Resource
from app.services.zlm_stream_control import close_zlm_stream
from app.utils.stream_name import normalize_stream_name
from loguru import logger

_task: asyncio.Task | None = None
LOG_DIR = "logs/rtmp_push_channel_monitor"


def _tok(s: str) -> str:
    return str(s or "").strip().replace(" ", "%20").replace("\t", "_")


def _append_rtmp_monitor_event(
    *,
    evt: str,
    stream: str,
    source_id: str,
    ok: bool | None = None,
    status: int | None = None,
    err: str | None = None,
) -> None:
    try:
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR, exist_ok=True)
        today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        log_file = os.path.join(LOG_DIR, f"rtmp_push_channel_monitor_{today}.log")
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        st = _tok(stream)
        sid = _tok(source_id)
        ev = str(evt or "").strip()
        if ev == "resource_status" and status is not None:
            line = f"[{timestamp}] evt=resource_status stream={st} source_id={sid} status={int(status)}\n"
        elif ev == "auto_stop" and ok is not None:
            if ok:
                line = f"[{timestamp}] evt=auto_stop stream={st} source_id={sid} ok=true\n"
            else:
                err_s = " ".join(str(err or "").split())[:300]
                line = f"[{timestamp}] evt=auto_stop stream={st} source_id={sid} ok=false err={err_s}\n"
        else:
            return
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as e:
        logger.warning(f"Error: {e}")


def _parse_iso(dt_str: str | None) -> datetime.datetime | None:
    if not dt_str:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(dt_str)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=datetime.timezone.utc)
        return parsed.astimezone(datetime.timezone.utc)
    except Exception:
        return None


async def _run_loop():
    interval = max(2, int(getattr(settings, "PUSH_CHANNEL_MONITOR_INTERVAL_SECONDS", 10) or 10))
    grace = max(0, int(getattr(settings, "PUSH_CHANNEL_OFFLINE_GRACE_SECONDS", 20) or 20))
    while True:
        if not bool(getattr(settings, "PUSH_CHANNEL_MONITOR_ENABLED", True)):
            await asyncio.sleep(max(2, interval))
            continue
        now = datetime.datetime.now(datetime.timezone.utc)
        now_iso = now.isoformat()
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(AccessSource).where(
                        AccessSource.protocol == "RTMP",
                        AccessSource.enabled == True,
                    )
                )
                sources = result.scalars().all()
                if not sources:
                    await asyncio.sleep(interval)
                    continue
                stream_to_source = {}
                source_ids = []
                for s in sources:
                    stream_name = normalize_stream_name(s.stream_name or s.name or s.id, fallback=s.id)
                    stream_to_source[stream_name] = s
                    source_ids.append(s.id)

                pc_rows = (
                    await session.execute(
                        select(PushChannel).where(
                            PushChannel.id.in_(source_ids),
                            PushChannel.gb_enabled == True,
                        )
                    )
                ).scalars().all()
                pc_by_id = {p.id: p for p in pc_rows}

                media_list = await asyncio.to_thread(get_all_media_from_nodes)
                running = {}
                for item in (media_list or []):
                    try:
                        if str(item.get("app") or "") != "live":
                            continue
                        stream = str(item.get("stream") or "")
                        if stream in stream_to_source:
                            running[stream] = item
                    except Exception:
                        continue

                enforce_stopped = bool(getattr(settings, "PUSH_CHANNEL_ENFORCE_STOPPED", True))

                changed = False
                for stream_name, source in stream_to_source.items():
                    extra = source.extra if isinstance(getattr(source, "extra", None), dict) else {}
                    desired_state = str(extra.get("desired.state") or "running").strip().lower()
                    is_running = stream_name in running
                    extra["runtime.rtmp.checked_at"] = now_iso
                    extra["runtime.rtmp.stream"] = stream_name
                    extra["runtime.rtmp.is_running"] = bool(is_running)

                    if is_running:
                        item = running.get(stream_name) or {}
                        extra["runtime.rtmp.last_seen_at"] = now_iso
                        extra["runtime.rtmp.last_seen_node_id"] = item.get("node_id") or ""
                        extra["runtime.rtmp.reader_count"] = item.get("readerCount", item.get("reader_count", 0))
                        extra["runtime.rtmp.bytes_speed"] = item.get("bytesSpeed", item.get("bytes_speed", 0))
                        extra["runtime.rtmp.origin_type"] = item.get("originType", item.get("origin_type", 0))
                        extra["runtime.rtmp.origin_url"] = item.get("originUrl", item.get("origin_url", "")) or ""
                        extra["runtime.rtmp.unhealthy"] = False
                        extra["runtime.rtmp.unhealthy_reason"] = ""
                    else:
                        last_seen = _parse_iso(str(extra.get("runtime.rtmp.last_seen_at") or "")) or _parse_iso(
                            str(extra.get("runtime.last_seen_at") or "")
                        )
                        missing_seconds = int((now - last_seen).total_seconds()) if last_seen else grace + 1
                        if desired_state == "running" and missing_seconds > grace:
                            extra["runtime.rtmp.unhealthy"] = True
                            extra["runtime.rtmp.unhealthy_reason"] = f"expected_running_but_missing missing_seconds={missing_seconds}"
                            extra["runtime.rtmp.last_missing_at"] = now_iso
                        else:
                            extra["runtime.rtmp.unhealthy"] = False
                            extra["runtime.rtmp.unhealthy_reason"] = ""

                    if enforce_stopped and desired_state == "stopped" and is_running:
                        last_auto_stop = _parse_iso(str(extra.get("runtime.rtmp.last_auto_stop_at") or ""))
                        if not last_auto_stop or (now - last_auto_stop).total_seconds() >= max(5, interval * 3):
                            try:
                                await close_zlm_stream("live", stream_name, None)
                                extra["runtime.rtmp.last_auto_stop_at"] = now_iso
                                extra["runtime.rtmp.last_auto_stop_ok"] = True
                                extra["runtime.rtmp.last_auto_stop_message"] = ""
                                _append_rtmp_monitor_event(
                                    evt="auto_stop",
                                    stream=stream_name,
                                    source_id=str(getattr(source, "id", "") or ""),
                                    ok=True,
                                )
                            except Exception as e:
                                extra["runtime.rtmp.last_auto_stop_at"] = now_iso
                                extra["runtime.rtmp.last_auto_stop_ok"] = False
                                extra["runtime.rtmp.last_auto_stop_message"] = str(e)[:200]
                                _append_rtmp_monitor_event(
                                    evt="auto_stop",
                                    stream=stream_name,
                                    source_id=str(getattr(source, "id", "") or ""),
                                    ok=False,
                                    err=str(e),
                                )
                    source.extra = dict(extra)
                    changed = True

                    pc = pc_by_id.get(source.id)
                    if pc and pc.gb_resource_id:
                        res = (
                            await session.execute(
                                select(Resource).where(
                                    Resource.id == pc.gb_resource_id,
                                    Resource.tenant_id == (source.tenant_id or "default"),
                                )
                            )
                        ).scalars().first()
                        if res:
                            next_status = 1 if is_running else 0
                            if int(getattr(res, "status", 0) or 0) != next_status:
                                res.status = next_status
                                changed = True
                                _append_rtmp_monitor_event(
                                    evt="resource_status",
                                    stream=stream_name,
                                    source_id=str(getattr(source, "id", "") or ""),
                                    status=next_status,
                                )

                if changed:
                    try:
                        await session.commit()
                    except Exception:
                        await session.rollback()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"Error: {e}")
        await asyncio.sleep(interval)


async def start():
    global _task
    if _task and not _task.done():
        return
    _task = asyncio.create_task(_run_loop())


async def stop():
    global _task
    if not _task:
        return
    _task.cancel()
    try:
        await asyncio.wait_for(_task, timeout=5.0)
    except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
        logger.warning("(asyncio.CancelledError, asyncio.TimeoutError, Exception) occurred")
    _task = None


