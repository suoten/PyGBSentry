import asyncio
import datetime
import json
import os

import httpx
from sqlalchemy import select

from app.core.config import settings
from app.core.media_nodes import get_all_media_from_nodes
from app.core.media_nodes_db import get_active_media_node_id, get_db_media_node_by_id, select_best_db_node
from app.db.session import AsyncSessionLocal
from app.models.asset import Asset
from app.models.record_schedule import RecordSchedule
from app.models.record_schedule_runtime import RecordScheduleRuntime
from app.models.resource import Resource
from loguru import logger

_task: asyncio.Task | None = None
LOG_DIR = "logs/record_schedule_executor"


def _tok(s: str) -> str:
    return str(s or "").strip().replace(" ", "%20").replace("\t", "_")


def _append_rse_event(*, schedule_id: str, stream_gb: str, evt: str, err: str | None = None) -> None:
    """evt: start_ok|start_fail|stop_ok|stop_fail|blocked_stream"""
    try:
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR, exist_ok=True)
        today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        log_file = os.path.join(LOG_DIR, f"record_schedule_executor_{today}.log")
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        sid = _tok(schedule_id)
        st = _tok(stream_gb)
        ev = str(evt or "").strip()
        if ev == "blocked_stream":
            line = f"[{timestamp}] schedule={sid} stream={st} evt=blocked_stream\n"
        elif ev in {"start_ok", "stop_ok"}:
            line = f"[{timestamp}] schedule={sid} stream={st} evt={ev}\n"
        elif ev in {"start_fail", "stop_fail"}:
            err_s = " ".join(str(err or "").split())[:300]
            line = f"[{timestamp}] schedule={sid} stream={st} evt={ev} err={err_s}\n"
        else:
            return
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as e:
        logger.warning(f"Error: {e}")


def _parse_ranges(raw: str) -> list[dict]:
    try:
        arr = json.loads(raw or "[]")
        return arr if isinstance(arr, list) else []
    except Exception:
        return []


def _is_in_range(now: datetime.datetime, start_hm: str, end_hm: str) -> bool:
    try:
        sh, sm = [int(x) for x in start_hm.split(":", 1)]
        eh, em = [int(x) for x in end_hm.split(":", 1)]
    except Exception:
        return False
    start = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
    end = now.replace(hour=eh, minute=em, second=0, microsecond=0)
    if start <= end:
        return start <= now <= end
    return now >= start or now <= end


def _should_record_now(now: datetime.datetime, plan_type: str, enabled: bool, time_ranges_raw: str, runtime: RecordScheduleRuntime | None) -> bool:
    if not enabled:
        return False
    if runtime and runtime.forced_mode and runtime.forced_until:
        try:
            until = runtime.forced_until
            if until.tzinfo is None:
                until = until.replace(tzinfo=datetime.timezone.utc)
            if now <= until:
                return (runtime.forced_mode or "").lower() == "on"
        except Exception as e:
            logger.warning(f"Error: {e}")
    if (plan_type or "").lower() == "manual":
        return True
    weekday = now.weekday()
    for r in _parse_ranges(time_ranges_raw):
        days = r.get("days")
        if isinstance(days, list) and days and weekday not in days:
            continue
        start = str(r.get("start") or "00:00")
        end = str(r.get("end") or "23:59")
        if _is_in_range(now, start, end):
            return True
    return False


async def _select_media_node(db) -> tuple[str, int, str, str, int, str, str]:
    proxy_host = settings.MEDIA_SERVER_HOST
    proxy_http_port = int(getattr(settings, "MEDIA_SERVER_HTTP_PORT", 0) or 0)
    proxy_secret = settings.MEDIA_SERVER_SECRET
    public_host = settings.STREAM_PUBLIC_HOST
    public_http_port = int(getattr(settings, "STREAM_PUBLIC_HTTP_PORT", 0) or 0)
    selection_reason = "global"
    node_id = ""
    try:
        active_id = await get_active_media_node_id(db)
        db_node = await get_db_media_node_by_id(db, active_id) if active_id else None
        if not db_node:
            db_node = await select_best_db_node(db)
        if db_node:
            node_id = str(db_node.id)
            proxy_host = db_node.host or proxy_host
            proxy_http_port = int(db_node.http_port or proxy_http_port)
            proxy_secret = db_node.secret or proxy_secret
            public_host = db_node.public_host or public_host
            public_http_port = int(db_node.public_http_port or public_http_port)
            selection_reason = "active" if (active_id and db_node.id == active_id) else "auto"
    except Exception as e:
        logger.warning(f"Error: {e}")
    return proxy_host, proxy_http_port, proxy_secret, public_host, public_http_port, selection_reason, node_id


async def _start_record(proxy_host: str, proxy_http_port: int, proxy_secret: str, app: str, stream: str) -> None:
    # FIXED: replaced sync requests.get with async httpx to avoid blocking event loop
    url = f"http://{proxy_host}:{proxy_http_port}/index/api/startRecord"
    async with httpx.AsyncClient(timeout=5) as client:
        r = await client.get(url, params={"secret": proxy_secret, "vhost": "__defaultVhost__", "app": app, "stream": stream, "type": 1})
    if r.status_code >= 400:
        raise RuntimeError(f"startRecord http={r.status_code}")
    body = r.json()
    if body.get("code") not in {0, "0"}:
        raise RuntimeError(f"startRecord code={body.get('code')} msg={body.get('msg') or ''}".strip())


async def _stop_record(proxy_host: str, proxy_http_port: int, proxy_secret: str, app: str, stream: str) -> None:
    # FIXED: replaced sync requests.get with async httpx to avoid blocking event loop
    url = f"http://{proxy_host}:{proxy_http_port}/index/api/stopRecord"
    async with httpx.AsyncClient(timeout=5) as client:
        r = await client.get(url, params={"secret": proxy_secret, "vhost": "__defaultVhost__", "app": app, "stream": stream, "type": 1})
    if r.status_code >= 400:
        raise RuntimeError(f"stopRecord http={r.status_code}")
    body = r.json()
    if body.get("code") not in {0, "0"}:
        raise RuntimeError(f"stopRecord code={body.get('code')} msg={body.get('msg') or ''}".strip())


async def _run_loop():
    interval = max(2, int(getattr(settings, "RECORD_SCHEDULE_EXECUTOR_INTERVAL_SECONDS", 10) or 10))
    while True:
        if not bool(getattr(settings, "RECORD_SCHEDULE_EXECUTOR_ENABLED", True)):
            await asyncio.sleep(interval)
            continue
        now = datetime.datetime.now(datetime.timezone.utc)
        now_naive = now.replace(tzinfo=None)
        now_iso = now.isoformat()
        try:
            media_list = await asyncio.to_thread(get_all_media_from_nodes)
            running = {}
            for item in (media_list or []):
                try:
                    if str(item.get("app") or "") != "live":
                        continue
                    stream = str(item.get("stream") or "")
                    if stream:
                        running[stream] = item
                except Exception:
                    continue

            async with AsyncSessionLocal() as session:
                result = await session.execute(select(RecordSchedule))
                schedules = result.scalars().all()
                if not schedules:
                    await asyncio.sleep(interval)
                    continue
                resource_ids = list({s.resource_id for s in schedules if s.resource_id})
                res_rows = (await session.execute(select(Resource).where(Resource.id.in_(resource_ids)))).scalars().all()
                res_by_id = {r.id: r for r in res_rows}
                asset_ids = list({r.asset_id for r in res_rows if getattr(r, "asset_id", None)})
                asset_rows = (await session.execute(select(Asset).where(Asset.id.in_(asset_ids)))).scalars().all()
                asset_by_id = {a.id: a for a in asset_rows}

                runtime_rows = (
                    await session.execute(
                        select(RecordScheduleRuntime).where(RecordScheduleRuntime.schedule_id.in_([s.id for s in schedules]))
                    )
                ).scalars().all()
                runtime_by_schedule = {rt.schedule_id: rt for rt in runtime_rows}

                proxy_host, proxy_http_port, proxy_secret, _, _, _, node_id = await _select_media_node(session)

                changed = False
                for sch in schedules:
                    res = res_by_id.get(sch.resource_id)
                    if not res:
                        continue
                    asset = asset_by_id.get(res.asset_id) if getattr(res, "asset_id", None) else None
                    tenant_id = (asset.tenant_id if asset else "default") or "default"
                    rt = runtime_by_schedule.get(sch.id)
                    if not rt:
                        rt = RecordScheduleRuntime(
                            tenant_id=tenant_id,
                            schedule_id=sch.id,
                            resource_id=sch.resource_id,
                            desired_recording=False,
                            is_recording=False,
                        )
                        session.add(rt)
                        runtime_by_schedule[sch.id] = rt
                        changed = True
                    if rt.tenant_id != tenant_id:
                        rt.tenant_id = tenant_id
                        changed = True

                    should = _should_record_now(now, sch.plan_type, bool(sch.enabled), sch.time_ranges or "[]", rt)
                    rt.desired_recording = bool(should)
                    rt.last_eval_at = now_naive
                    rt.last_media_node_id = node_id or rt.last_media_node_id
                    stream = str(res.gb_id or "")
                    is_running = stream in running
                    if is_running:
                        rt.last_stream_seen_at = now_naive

                    if should and (not rt.is_recording):
                        sch_id = str(getattr(sch, "id", "") or "")
                        if not is_running:
                            rt.last_action_at = now_naive
                            rt.last_action = "start_record"
                            rt.last_action_ok = False
                            rt.last_error = f"stream_not_running stream={stream}"
                            changed = True
                            _append_rse_event(
                                schedule_id=sch_id, stream_gb=stream, evt="blocked_stream"
                            )
                            continue
                        try:
                            await _start_record(proxy_host, proxy_http_port, proxy_secret, "live", stream)
                            rt.is_recording = True
                            rt.last_action_at = now_naive
                            rt.last_action = "start_record"
                            rt.last_action_ok = True
                            rt.last_error = ""
                            changed = True
                            _append_rse_event(
                                schedule_id=sch_id, stream_gb=stream, evt="start_ok"
                            )
                        except Exception as e:
                            rt.is_recording = False
                            rt.last_action_at = now_naive
                            rt.last_action = "start_record"
                            rt.last_action_ok = False
                            rt.last_error = f"start_failed {str(e)[:200]}"
                            changed = True
                            _append_rse_event(
                                schedule_id=sch_id,
                                stream_gb=stream,
                                evt="start_fail",
                                err=str(e),
                            )

                    if (not should) and rt.is_recording:
                        sch_id = str(getattr(sch, "id", "") or "")
                        try:
                            await _stop_record(proxy_host, proxy_http_port, proxy_secret, "live", stream)
                            rt.is_recording = False
                            rt.last_action_at = now_naive
                            rt.last_action = "stop_record"
                            rt.last_action_ok = True
                            rt.last_error = ""
                            changed = True
                            _append_rse_event(
                                schedule_id=sch_id, stream_gb=stream, evt="stop_ok"
                            )
                        except Exception as e:
                            rt.last_action_at = now_naive
                            rt.last_action = "stop_record"
                            rt.last_action_ok = False
                            rt.last_error = f"stop_failed {str(e)[:200]}"
                            changed = True
                            _append_rse_event(
                                schedule_id=sch_id,
                                stream_gb=stream,
                                evt="stop_fail",
                                err=str(e),
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



