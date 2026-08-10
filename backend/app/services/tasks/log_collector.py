"""
日志采集服务：将录像事件、告警事件、流媒体事件以结构化 JSON 推送到 ELK（Loki / Elasticsearch）。
支持两种模式：
  - Loki: 通过 Loki HTTP API (POST /loki/api/v1/push) 推送
  - Elasticsearch: 通过 Bulk API 批量写入
配置项：
  targets: [{"type": "loki"|"elasticsearch", "url": "...", "index": "...", "enabled": true}, ...]
"""
import asyncio
import datetime
import json
from loguru import logger
import os
import time

import requests as _requests
from sqlalchemy import select  # TECH_DEBT: 直接依赖具体实现，未来改为Protocol接口注入

from app.core.plugin_manager import HOOK_ON_ALARM, HOOK_ON_STREAM_START, HOOK_ON_STREAM_STOP
from app.db.session import AsyncSessionLocal
from app.models.system_setting import SystemSetting



PLUGIN_ID = "log_collector"
LOG_DIR = "logs/log_collector"

_DEFAULT_CONFIG = {
    "enabled": False,
    "targets": [],
    "include_alarms": True,
    "include_streams": True,
    "batch_size": 100,
    "flush_interval_seconds": 30,
}

_cfg_cache: dict = {}
_cfg_ts: float = 0.0
_cfg_ttl: float = 10.0

# 内存缓冲，按 target 分组
_buffer: dict[str, list[dict]] = {}
_buffer_ts: float = 0.0


def _append_local_log(msg: str, level: str = "info") -> None:
    try:
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR, exist_ok=True)
        today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        log_file = os.path.join(LOG_DIR, f"log_collector_{today}.log")
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        line = f"[{ts}] [{level.upper()}] {msg}\n"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as e:
        logger.warning(f"Error: {e}")


async def _get_cfg() -> dict:
    global _cfg_cache, _cfg_ts
    now = time.time()
    if _cfg_cache and (now - _cfg_ts) < _cfg_ttl:
        return _cfg_cache
    async with AsyncSessionLocal() as db:
        stmt = select(SystemSetting).where(
            SystemSetting.setting_key.like(f"plugin_runtime_config.%.{PLUGIN_ID}")
        )
        rows = (await db.execute(stmt)).scalars().all()
    any_enabled = False
    cfg = dict(_DEFAULT_CONFIG)
    all_targets = []
    for r in rows:
        try:
            parsed = json.loads(r.setting_value or "{}")
            if isinstance(parsed, dict) and bool(parsed.get("enabled")):
                any_enabled = True
            for k in _DEFAULT_CONFIG:
                v = parsed.get(k)
                if k == "targets" and isinstance(v, list):
                    all_targets.extend(v)
                elif v is not None:
                    cfg[k] = v
        except Exception:
            continue
    cfg["enabled"] = any_enabled or bool(cfg.get("enabled"))
    cfg["targets"] = all_targets if all_targets else cfg.get("targets", [])
    _cfg_cache = cfg
    _cfg_ts = now
    return cfg


def _push_to_buffer(target_id: str, event: dict) -> None:
    global _buffer
    # FIX: [2026-07-16 P1] 每个 target buffer 设置上限，防止 Loki/ES 不可达时 OOM
    _MAX_BUFFER_PER_TARGET = 10000
    if target_id not in _buffer:
        _buffer[target_id] = []
    buf = _buffer[target_id]
    if len(buf) >= _MAX_BUFFER_PER_TARGET:
        # 丢弃最旧的 10% 事件，腾出空间
        drop_count = max(1, _MAX_BUFFER_PER_TARGET // 10)
        del buf[:drop_count]
        logger.warning(f"[LogCollector] Buffer for {target_id} full, dropped {drop_count} oldest events (max={_MAX_BUFFER_PER_TARGET})")
    buf.append(event)


async def _batch_and_flush(target_id: str, events: list[dict]) -> bool:
    global _cfg_cache
    cfg = _cfg_cache or {}
    targets: list[dict] = cfg.get("targets") or []
    target = next((t for t in targets if str(id(t)) == target_id or t.get("url", "").startswith(target_id)), None)
    if not target:
        return False
    t_type = str(target.get("type", "loki")).lower()
    url = str(target.get("url", "")).strip()
    index = str(target.get("index", "pygbsentry")).strip()
    if not url:
        return False
    try:
        if t_type == "loki":
            return await asyncio.to_thread(_push_to_loki, url, index, events)
        elif t_type == "elasticsearch":
            return await asyncio.to_thread(_push_to_elasticsearch, url, index, events)
        else:
            logger.warning("[LogCollector] Unknown target type: %s", t_type)
            return False
    except Exception as e:
        logger.error("[LogCollector] Flush error (%s %s): %s", t_type, target_id, e)
        return False


def _push_to_loki(url: str, stream_name: str, events: list[dict]) -> bool:
    streams = {}
    for ev in events:
        ts_ns = int(time.time() * 1e9)
        line = json.dumps(ev, ensure_ascii=False)
        label_key = ev.get("event_type", "default")
        if label_key not in streams:
            streams[label_key] = []
        streams[label_key].append({"ts": str(ts_ns), "line": line})
    payload = {
        "streams": [
            {"stream": {"job": stream_name, "type": k}, "values": v}
            for k, v in streams.items()
        ]
    }
    # 添加try-except避免Loki不可达时崩溃
    # R-01 _push_to_loki是同步函数（被asyncio.to_thread调用），不能使用await，恢复同步requests调用
    try:
        r = _requests.post(f"{url.rstrip('/')}/loki/api/v1/push", json=payload, timeout=5)
    except Exception as e:
        _append_local_log(f"Loki push error: {e}", "warning")
        return False
    if r.ok:
        _append_local_log(f"Loki push ok: {len(events)} events", "info")
        return True
    _append_local_log(f"Loki push failed: {r.status_code} {r.text[:100]}", "warning")
    return False


def _push_to_elasticsearch(url: str, index: str, events: list[dict]) -> bool:
    index_name = f"{index}-{datetime.datetime.now(datetime.timezone.utc).strftime('%Y.%m.%d')}"
    bulk_lines = []
    for ev in events:
        action = {"index": {"_index": index_name, "_type": "_doc"}}
        bulk_lines.append(json.dumps(action, ensure_ascii=False))
        bulk_lines.append(json.dumps(ev, ensure_ascii=False))
    if not bulk_lines:
        return True
    body = "\n".join(bulk_lines) + "\n"
    # 添加try-except避免ES不可达时崩溃
    # R-01 _push_to_elasticsearch是同步函数（被asyncio.to_thread调用），不能使用await，恢复同步requests调用
    try:
        r = _requests.post(
            f"{url.rstrip('/')}/_bulk",
            data=body.encode("utf-8"),
            headers={"Content-Type": "application/x-ndjson"},
            timeout=10,
        )
    except Exception as e:
        _append_local_log(f"Elasticsearch push error: {e}", "warning")
        return False
    if r.ok:
        _append_local_log(f"Elasticsearch bulk push ok: {len(events)} events", "info")
        return True
    _append_local_log(f"Elasticsearch push failed: {r.status_code} {r.text[:100]}", "warning")
    return False


async def _flush_all() -> None:
    global _buffer, _buffer_ts
    cfg = await _get_cfg()
    if not cfg.get("enabled"):
        return
    batch_size = max(10, min(int(cfg.get("batch_size", 100)), 500))
    flush_interval = max(10, min(int(cfg.get("flush_interval_seconds", 30)), 300))

    now = time.time()
    should_flush = (now - _buffer_ts) >= flush_interval
    targets: list[dict] = cfg.get("targets") or []

    for target in targets:
        if not bool(target.get("enabled", True)):
            continue
        t_id = str(target.get("url", ""))[:32]
        events = _buffer.get(t_id, [])
        if not events:
            continue
        if should_flush or len(events) >= batch_size:
            batch = events[:batch_size]
            _buffer[t_id] = events[batch_size:]
            ok = await _batch_and_flush(t_id, batch)
            if not ok:
                _buffer[t_id] = batch + _buffer[t_id]

    if should_flush:
        _buffer_ts = now


async def _collect_event(event_type: str, data: dict) -> None:
    cfg = await _get_cfg()
    if not cfg.get("enabled"):
        return
    if event_type == "alarm" and not cfg.get("include_alarms"):
        return
    if event_type in ("stream_start", "stream_stop") and not cfg.get("include_streams"):
        return

    targets: list[dict] = cfg.get("targets") or []
    event = {
        "@timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "event_type": event_type,
        "tenant_id": data.get("tenant_id", "default"),
        **{k: v for k, v in data.items() if k != "tenant_id"},
    }
    for target in targets:
        if not bool(target.get("enabled", True)):
            continue
        t_id = str(target.get("url", ""))[:32]
        _push_to_buffer(t_id, event)

    await _flush_all()


async def on_alarm(alarm) -> None:
    device_id = str(getattr(alarm, "device_id", "") or "")
    channel_id = str(getattr(alarm, "channel_id", "") or device_id)
    t = getattr(alarm, "time", None)
    await _collect_event("alarm", {
        "device_id": device_id,
        "channel_id": channel_id,
        "alarm_type": str(getattr(alarm, "alarm_type", "") or "Alarm"),
        "priority": str(getattr(alarm, "priority", "4") or "4"),
        "description": str(getattr(alarm, "description", "") or ""),
        "alarm_time": t.isoformat() if t and hasattr(t, "isoformat") else datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "status": str(getattr(alarm, "status", "") or "0"),
        "tenant_id": getattr(alarm, "tenant_id", "default") or "default",
    })


async def on_stream_start(session) -> None:
    await _collect_event("stream_start", {
        "stream": str(getattr(session, "stream", "") or ""),
        "app": str(getattr(session, "app", "") or ""),
        "resource_id": str(getattr(session, "resource_id", "") or ""),
        "media_ip": str(getattr(session, "media_ip", "") or ""),
        "media_port": int(getattr(session, "media_port", 0) or 0),
        "ssrc": str(getattr(session, "ssrc", "") or ""),
        "start_time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "tenant_id": "default",
    })


async def on_stream_stop(session) -> None:
    await _collect_event("stream_stop", {
        "stream": str(getattr(session, "stream", "") or ""),
        "app": str(getattr(session, "app", "") or ""),
        "resource_id": str(getattr(session, "resource_id", "") or ""),
        "stop_time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "tenant_id": "default",
    })


_task: asyncio.Task | None = None


async def _run() -> None:
    global _buffer_ts
    _buffer_ts = time.time()
    while True:
        try:
            await _flush_all()
        except Exception as e:
            logger.error("[LogCollector] Run error: %s", e)
        await asyncio.sleep(15)


async def start() -> None:
    global _task
    logger.info("[LogCollector] Service started")
    _task = asyncio.create_task(_run())


async def stop() -> None:
    global _task
    if _task:
        _task.cancel()
        try:
            await asyncio.wait_for(_task, timeout=5.0)
        except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
            logger.warning("(asyncio.CancelledError, asyncio.TimeoutError, Exception) occurred")
        _task = None
    global _buffer
    _buffer = {}


def register(pm) -> None:
    pm.register_hook(HOOK_ON_ALARM, on_alarm)
    pm.register_hook(HOOK_ON_STREAM_START, on_stream_start)
    pm.register_hook(HOOK_ON_STREAM_STOP, on_stream_stop)
    logger.info("[LogCollector] Hooks registered: alarm, stream_start, stream_stop")
