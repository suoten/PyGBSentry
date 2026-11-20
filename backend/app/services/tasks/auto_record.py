import asyncio
import datetime
import json
from loguru import logger
import os
import time

import httpx
from sqlalchemy import select

from app.core.config import settings
from app.core.media_nodes_db import get_active_media_node_id, get_db_media_node_by_id, select_best_db_node
from app.db.session import AsyncSessionLocal
from app.models.asset import Asset
from app.models.resource import Resource
from app.models.system_setting import SystemSetting


_task: asyncio.Task | None = None

PLUGIN_ID = "auto_record"
LOG_DIR = "logs/auto_record"


def _stream_token(s: str) -> str:
    return str(s or "").strip().replace(" ", "%20").replace("\t", "_")


def _append_auto_record_event(*, op: str, stream_gb: str, ok: bool, err: str | None = None) -> None:
    try:
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR, exist_ok=True)
        today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        log_file = os.path.join(LOG_DIR, f"auto_record_{today}.log")
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        op_v = "start_record" if op == "start_record" else "stop_record"
        st = _stream_token(stream_gb)
        if ok:
            line = f"[{timestamp}] op={op_v} stream={st} ok=true\n"
        else:
            err_s = " ".join(str(err or "").split())[:300]
            line = f"[{timestamp}] op={op_v} stream={st} ok=false err={err_s}\n"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as e:
        logger.warning(f"Error: {e}")


_DEFAULT_BASE_CONFIG = {
    "enabled": True,
    "check_interval": 60,
    # config_schema: schedules: [{start:"09:00", end:"18:00", days:[0..6]}]
    "schedules": [{"start": "09:00", "end": "18:00", "days": [0, 1, 2, 3, 4]}],
}

_cfg_cache: dict = {}
_cfg_ts: float = 0.0
_cfg_ttl_sec: int = 10


def _parse_hm(v: str) -> tuple[int, int] | None:
    try:
        sh, sm = [int(x) for x in str(v or "").strip().split(":", 1)]
        return sh, sm
    except (ValueError, TypeError):
        return None


def _is_in_range(now: datetime.datetime, start_hm: str, end_hm: str) -> bool:
    # 支持跨午夜：例如 23:00 - 02:00
    start = _parse_hm(start_hm)
    end = _parse_hm(end_hm)
    if not start or not end:
        return False
    sh, sm = start
    eh, em = end
    start_dt = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
    end_dt = now.replace(hour=eh, minute=em, second=0, microsecond=0)
    if start_dt <= end_dt:
        return start_dt <= now <= end_dt
    return now >= start_dt or now <= end_dt


def _parse_schedules(raw) -> list[dict]:
    if not raw:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return []
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for r in raw:
        if not isinstance(r, dict):
            continue
        start = str(r.get("start") or "").strip()
        end = str(r.get("end") or "").strip()
        days = r.get("days")
        if not start or not end:
            continue
        if days is None:
            days_list = []
        elif isinstance(days, list):
            days_list = []
            for d in days:
                try:
                    dd = int(d)
                    if 0 <= dd <= 6:
                        days_list.append(dd)
                except Exception as e:
                    logger.warning(f"Error: {e}")
        else:
            days_list = []

        out.append({"start": start, "end": end, "days": days_list})
    return out


def _should_record_now(now: datetime.datetime, schedules: list[dict]) -> bool:
    if not schedules:
        return False
    weekday = now.weekday()
    for r in schedules:
        days = r.get("days") or []
        if isinstance(days, list) and days and weekday not in days:
            continue
        if _is_in_range(now, str(r.get("start") or ""), str(r.get("end") or "")):
            return True
    return False


async def _get_runtime_cfg() -> dict:
    """
    多租户兼容：聚合所有 tenant 的 plugin_runtime_config.*.auto_record。
    """
    global _cfg_cache, _cfg_ts
    now_ts = time.time()
    if _cfg_cache and (now_ts - _cfg_ts) < _cfg_ttl_sec:
        return _cfg_cache

    merged = dict(_DEFAULT_BASE_CONFIG)
    any_enabled = False
    chosen_schedules = None
    check_interval_max: int | None = None

    async with AsyncSessionLocal() as db:
        stmt = select(SystemSetting).where(SystemSetting.setting_key.like(f"plugin_runtime_config.%.{PLUGIN_ID}"))
        rows = (await db.execute(stmt)).scalars().all()

    for r in rows:
        try:
            parsed = json.loads(r.setting_value or "{}")
            if not isinstance(parsed, dict):
                continue
            if bool(parsed.get("enabled", False)):
                any_enabled = True
            if chosen_schedules is None and parsed.get("schedules"):
                chosen_schedules = parsed.get("schedules")
            if parsed.get("check_interval") is not None:
                ci = int(parsed.get("check_interval") or 0)
                if ci > 0:
                    check_interval_max = ci if check_interval_max is None else max(check_interval_max, ci)
        except Exception:
            continue

    merged["enabled"] = any_enabled if any_enabled else bool(merged.get("enabled", True))
    if chosen_schedules is not None:
        merged["schedules"] = chosen_schedules
    if check_interval_max is not None:
        merged["check_interval"] = check_interval_max

    _cfg_cache = merged
    _cfg_ts = now_ts
    return _cfg_cache


async def _select_media_node(db) -> tuple[str, int, str]:
    # W-19 MEDIA_SERVER_HOST回退值改为空字符串，非本地部署时显式报错
    proxy_host = settings.MEDIA_SERVER_HOST or ""
    proxy_http_port = settings.MEDIA_SERVER_HTTP_PORT
    proxy_secret = settings.MEDIA_SERVER_SECRET

    try:
        active_id = await get_active_media_node_id(db)
        db_node = await get_db_media_node_by_id(db, active_id) if active_id else None
        if not db_node:
            db_node = await select_best_db_node(db)
        if db_node:
            proxy_host = db_node.host or proxy_host
            proxy_http_port = int(db_node.http_port or proxy_http_port or 0)
            proxy_secret = db_node.secret or proxy_secret
    except Exception as e:
        logger.warning(f"Error: {e}")

    return proxy_host, proxy_http_port, proxy_secret


async def _start_record(proxy_host: str, proxy_http_port: int, proxy_secret: str, stream: str) -> None:
    # replaced sync requests.get with async httpx to avoid blocking event loop
    url = f"http://{proxy_host}:{proxy_http_port}/index/api/startRecord"
    async with httpx.AsyncClient(timeout=5) as client:
        # FIX [2026-07-17 P1-D1]: secret 通过 POST body 传递
        r = await client.post(url, data={"secret": proxy_secret, "vhost": "__defaultVhost__", "app": "live", "stream": stream, "type": 1})
    if r.status_code >= 400:
        raise RuntimeError(f"startRecord http={r.status_code}")
    body = r.json()
    if body.get("code") not in {0, "0"}:
        raise RuntimeError(f"startRecord code={body.get('code')} msg={body.get('msg') or ''}".strip())


async def _stop_record(proxy_host: str, proxy_http_port: int, proxy_secret: str, stream: str) -> None:
    # replaced sync requests.get with async httpx to avoid blocking event loop
    url = f"http://{proxy_host}:{proxy_http_port}/index/api/stopRecord"
    async with httpx.AsyncClient(timeout=5) as client:
        # FIX [2026-07-17 P1-D1]: secret 通过 POST body 传递
        r = await client.post(url, data={"secret": proxy_secret, "vhost": "__defaultVhost__", "app": "live", "stream": stream, "type": 1})
    if r.status_code >= 400:
        raise RuntimeError(f"stopRecord http={r.status_code}")
    body = r.json()
    if body.get("code") not in {0, "0"}:
        raise RuntimeError(f"stopRecord code={body.get('code')} msg={body.get('msg') or ''}".strip())


async def _query_recording(proxy_host: str, proxy_http_port: int, proxy_secret: str, stream: str) -> bool:
    """查询 ZLM 指定流的 MP4(type=1) 录制是否真的在跑(录制看门狗查询原语)。

    兼容两种响应形态:{code,on} 与 {code,data:[{on}]}。失败向上抛异常。
    """
    url = f"http://{proxy_host}:{proxy_http_port}/index/api/isRecording"
    async with httpx.AsyncClient(timeout=5) as client:
        r = await client.post(url, data={"secret": proxy_secret, "vhost": "__defaultVhost__", "app": "live", "stream": stream, "type": 1})
    if r.status_code >= 400:
        raise RuntimeError(f"isRecording http={r.status_code}")
    body = r.json()
    if body.get("code") not in {0, "0"}:
        raise RuntimeError(f"isRecording code={body.get('code')} msg={body.get('msg') or ''}".strip())
    data = body.get("data")
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return bool(data[0].get("on"))
    return bool(body.get("on"))


async def _verify_recordings() -> None:
    """FIX [2026-11-20 P0] 录制看门狗(wvp #2145 同款修复):

    _run_loop 只在 should_record 状态翻转边沿批量 start/stop,"应当录制"持续为 True
    期间从不复查。ZLM 重启或流闪断后录制已死但无人重发 startRecord,静默丢录像。
    周期调用:逐流查询 ZLM 真实录制状态,中断的流重新 startRecord。
    """
    async with AsyncSessionLocal() as db:
        proxy_host, proxy_http_port, proxy_secret = await _select_media_node(db)
    if not proxy_host or proxy_http_port <= 0:
        logger.warning("[AutoRecord] media node http port missing, skip verify")
        return

    stream_ids = await _get_target_stream_ids()
    for sid in stream_ids:
        # FIX [2026-11-20 P1]: 与 start/stop 相同的流名解析(isRecording 也需真实流名)
        try:
            from app.services.recording_guard import find_channel_live_stream

            target = await find_channel_live_stream(sid) or sid
        except Exception:
            target = sid
        try:
            recording_on = await _query_recording(proxy_host, proxy_http_port, proxy_secret, target)
        except Exception as e:
            logger.debug(f"[AutoRecord] isRecording verify failed stream={target}: {e}")
            continue
        if recording_on:
            continue
        try:
            await _start_record(proxy_host, proxy_http_port, proxy_secret, target)
            _append_auto_record_event(op="start_record", stream_gb=target, ok=True)
            logger.info(f"[AutoRecord] watchdog restarted recording for stream={target}")
        except Exception as e:
            logger.error(f"[AutoRecord] watchdog restart stream={target} failed: {e}")
            _append_auto_record_event(op="start_record", stream_gb=target, ok=False, err=f"watchdog {e}")


async def _get_target_stream_ids() -> list[str]:
    """
    为每个启用的设备选择“第一个通道”（与旧逻辑一致），返回 stream gb_id 列表。
    """
    async with AsyncSessionLocal() as session:
        stmt = select(Resource).join(Asset, Asset.id == Resource.asset_id).where(Asset.status == 1).order_by(Resource.asset_id, Resource.id)
        rows = (await session.execute(stmt)).scalars().all()
        picked: dict[str, Resource] = {}
        for r in rows:
            asset_id = str(getattr(r, "asset_id", "") or "").strip()
            if not asset_id or asset_id in picked:
                continue
            picked[asset_id] = r
        stream_ids: list[str] = []
        for r in picked.values():
            sid = str(getattr(r, "gb_id", "") or "").strip()
            if sid:
                stream_ids.append(sid)
        return stream_ids


async def _start_all_recordings() -> None:
    async with AsyncSessionLocal() as db:
        proxy_host, proxy_http_port, proxy_secret = await _select_media_node(db)
    if not proxy_host or proxy_http_port <= 0:
        logger.warning("[AutoRecord] media node http port missing, skip start")
        return

    stream_ids = await _get_target_stream_ids()
    if not stream_ids:
        return

    for sid in stream_ids:
        # FIX [2026-11-20 P1]: 解析通道真实 ZLM 流名（{gb_id}_{ssrc}），原先用 gb_id 调
        # startRecord 永远打不到点播流
        try:
            from app.services.recording_guard import find_channel_live_stream

            target = await find_channel_live_stream(sid) or sid
        except Exception:
            target = sid
        try:
            await _start_record(proxy_host, proxy_http_port, proxy_secret, target)
            _append_auto_record_event(op="start_record", stream_gb=target, ok=True)
        except Exception as e:
            logger.error(f"[AutoRecord] startRecord stream={target} failed: {e}")
            _append_auto_record_event(op="start_record", stream_gb=target, ok=False, err=str(e))


async def _stop_all_recordings() -> None:
    async with AsyncSessionLocal() as db:
        proxy_host, proxy_http_port, proxy_secret = await _select_media_node(db)
    if not proxy_host or proxy_http_port <= 0:
        logger.warning("[AutoRecord] media node http port missing, skip stop")
        return

    stream_ids = await _get_target_stream_ids()
    if not stream_ids:
        return

    for sid in stream_ids:
        # FIX [2026-11-20 P1]: 与 start 相同的流名解析
        try:
            from app.services.recording_guard import find_channel_live_stream

            target = await find_channel_live_stream(sid) or sid
        except Exception:
            target = sid
        try:
            await _stop_record(proxy_host, proxy_http_port, proxy_secret, target)
            _append_auto_record_event(op="stop_record", stream_gb=target, ok=True)
        except Exception as e:
            logger.error(f"[AutoRecord] stopRecord stream={target} failed: {e}")
            _append_auto_record_event(op="stop_record", stream_gb=target, ok=False, err=str(e))


async def _run_loop() -> None:
    prev_should_record: bool | None = None
    # 录制看门狗:上次全量校验的 monotonic 时间戳(节流,避免每轮全查)
    last_verify_mono: float = 0.0
    while True:
        try:
            cfg = await _get_runtime_cfg()
            enabled = bool(cfg.get("enabled", True))
            check_interval = int(cfg.get("check_interval") or _DEFAULT_BASE_CONFIG["check_interval"])
            check_interval = max(5, min(86400, check_interval))

            if not enabled:
                await asyncio.sleep(check_interval)
                continue

            schedules = _parse_schedules(cfg.get("schedules"))
            should_record = _should_record_now(datetime.datetime.now(), schedules)

            if prev_should_record is None:
                prev_should_record = should_record
                if should_record:
                    await _start_all_recordings()
            else:
                if should_record and not prev_should_record:
                    await _start_all_recordings()
                elif (not should_record) and prev_should_record:
                    await _stop_all_recordings()
                prev_should_record = should_record

            # FIX [2026-11-20 P0] 录制看门狗(wvp #2145 同款修复):"应当录制"持续为 True
            # 期间周期复查 ZLM 真实录制状态,中断自愈(节流同 RECORD_SCHEDULE_VERIFY_INTERVAL_SECONDS)
            if should_record:
                verify_interval = max(30, int(settings.RECORD_SCHEDULE_VERIFY_INTERVAL_SECONDS))
                if time.monotonic() - last_verify_mono >= verify_interval:
                    last_verify_mono = time.monotonic()
                    await _verify_recordings()

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"[AutoRecord] loop error: {e}")

        # 轮询间隔
        cfg = None
        try:
            cfg = await _get_runtime_cfg()
            check_interval = int(cfg.get("check_interval") or _DEFAULT_BASE_CONFIG["check_interval"])
        except Exception:
            check_interval = _DEFAULT_BASE_CONFIG["check_interval"]
        check_interval = max(5, min(86400, check_interval))
        await asyncio.sleep(check_interval)


async def start():
    global _task
    logger.info("[AutoRecord] Plugin started")
    _task = asyncio.create_task(_run_loop())


async def stop():
    global _task
    if _task and not _task.done():
        _task.cancel()
        try:
            await asyncio.wait_for(_task, timeout=5.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            logger.warning("(asyncio.CancelledError, asyncio.TimeoutError) occurred")
        except Exception as e:
            logger.warning(f"Error: {e}")
    _task = None
