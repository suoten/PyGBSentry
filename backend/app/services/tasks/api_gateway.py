"""
API 网关回调服务。
报警/设备状态变更时，将标准化事件以 HTTP POST 回调到用户配置的 API 地址。
支持多租户、多回调地址配置。
"""
import asyncio
import datetime
import json
from loguru import logger
import os
import time

import requests as _requests
from sqlalchemy import select  # TECH_DEBT: 直接依赖具体实现，未来改为Protocol接口注入

from app.core.plugin_manager import HOOK_ON_ALARM, HOOK_ON_DEVICE_REGISTER, HOOK_ON_DEVICE_OFFLINE
from app.db.session import AsyncSessionLocal
from app.models.system_setting import SystemSetting



PLUGIN_ID = "api_gateway"
LOG_DIR = "logs/api_gateway"

_DEFAULT_CONFIG = {
    "enabled": False,
    "callback_url": "",
    "secret": "",
    "include_alarms": True,
    "include_devices": True,
    "retry_count": 2,
    "timeout_seconds": 5,
}

_cfg_cache: dict = {}
_cfg_ts: float = 0.0
_cfg_ttl: float = 10.0


def _append_log(event_type: str, url: str, status_code: int | None, ok: bool, err: str | None = None) -> None:
    try:
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR, exist_ok=True)
        today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        log_file = os.path.join(LOG_DIR, f"api_gateway_{today}.log")
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        safe_url = url[:80] if url else ""
        if ok:
            line = f"[{ts}] type={event_type} url={safe_url} status={status_code} ok=true\n"
        else:
            err_s = " ".join(str(err or "").split())[:200]
            line = f"[{ts}] type={event_type} url={safe_url} ok=false err={err_s}\n"
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
    callback_urls = []
    for r in rows:
        try:
            parsed = json.loads(r.setting_value or "{}")
            if isinstance(parsed, dict) and bool(parsed.get("enabled")):
                any_enabled = True
            for k in _DEFAULT_CONFIG:
                v = parsed.get(k)
                if v is not None and v != "":
                    cfg[k] = v
            url = str(parsed.get("callback_url") or "").strip()
            if url:
                callback_urls.append(url)
        except Exception:
            continue
    cfg["enabled"] = any_enabled or bool(cfg.get("enabled"))
    cfg["callback_urls"] = callback_urls if callback_urls else ([cfg.get("callback_url")] if cfg.get("callback_url") else [])
    _cfg_cache = cfg
    _cfg_ts = now
    return cfg


def _sign_payload(body: str, secret: str) -> str:
    import hashlib
    import hmac
    if not secret:
        return ""
    return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()


async def _do_callback(url: str, payload: dict, secret: str, timeout: int, retries: int) -> bool:
    body = json.dumps(payload, ensure_ascii=False)
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "PyGBSentry/1.0",
        "X-Event-Type": payload.get("event_type", "unknown"),
    }
    if secret:
        sig = _sign_payload(body, secret)
        headers["X-Signature"] = sig
    for attempt in range(retries + 1):
        try:
            r = await asyncio.to_thread(
                _requests.post, url, data=body, headers=headers, timeout=timeout
            )
            if 200 <= r.status_code < 300:
                _append_log(payload.get("event_type", ""), url, r.status_code, ok=True)
                return True
            _append_log(payload.get("event_type", ""), url, r.status_code, ok=False, err=f"http_{r.status_code}")
        except Exception as e:
            _append_log(payload.get("event_type", ""), url, None, ok=False, err=str(e))
            if attempt == retries:
                return False
            await asyncio.sleep(0.5 * (attempt + 1))
    return False


def _alarm_payload(alarm, event_type: str = "alarm") -> dict:
    device_id = str(getattr(alarm, "device_id", "") or "")
    channel_id = str(getattr(alarm, "channel_id", "") or device_id)
    t = getattr(alarm, "time", None)
    alarm_time = t.isoformat() if t and hasattr(t, "isoformat") else datetime.datetime.now(datetime.timezone.utc).isoformat()
    return {
        "event_type": event_type,
        "event_id": getattr(alarm, "id", "") or "",
        "device_id": device_id,
        "channel_id": channel_id,
        "alarm_type": str(getattr(alarm, "alarm_type", "") or "Alarm"),
        "priority": str(getattr(alarm, "priority", "4") or "4"),
        "description": str(getattr(alarm, "description", "") or ""),
        "alarm_time": alarm_time,
        "status": str(getattr(alarm, "status", "") or "0"),
        "tenant_id": getattr(alarm, "tenant_id", "default") or "default",
    }


async def on_alarm(alarm) -> None:
    cfg = await _get_cfg()
    if not cfg.get("enabled") or not bool(cfg.get("include_alarms")):
        return
    urls = cfg.get("callback_urls") or []
    if not urls:
        return
    payload = _alarm_payload(alarm, "alarm")
    tasks = [_do_callback(url, payload, cfg.get("secret", ""), cfg.get("timeout_seconds", 5), cfg.get("retry_count", 2)) for url in urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    ok_count = sum(1 for r in results if r is True)
    if ok_count:
        logger.info("[APIGateway] Alarm forwarded: device=%s ok_urls=%d/%d", payload["device_id"], ok_count, len(urls))


async def on_device_register(device_id) -> None:
    cfg = await _get_cfg()
    if not cfg.get("enabled") or not bool(cfg.get("include_devices")):
        return
    urls = cfg.get("callback_urls") or []
    if not urls:
        return
    payload = {
        "event_type": "device_online",
        "device_id": str(device_id or "").strip(),
        "status": "online",
        "time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "tenant_id": "default",
    }
    tasks = [_do_callback(url, payload, cfg.get("secret", ""), cfg.get("timeout_seconds", 5), cfg.get("retry_count", 2)) for url in urls]
    await asyncio.gather(*tasks, return_exceptions=True)


async def on_device_offline(device_id) -> None:
    cfg = await _get_cfg()
    if not cfg.get("enabled") or not bool(cfg.get("include_devices")):
        return
    urls = cfg.get("callback_urls") or []
    if not urls:
        return
    payload = {
        "event_type": "device_offline",
        "device_id": str(device_id or "").strip(),
        "status": "offline",
        "time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "tenant_id": "default",
    }
    tasks = [_do_callback(url, payload, cfg.get("secret", ""), cfg.get("timeout_seconds", 5), cfg.get("retry_count", 2)) for url in urls]
    await asyncio.gather(*tasks, return_exceptions=True)


_task: asyncio.Task | None = None


async def _run() -> None:
    while True:
        try:
            cfg = await _get_cfg()
            if not cfg.get("enabled"):
                await asyncio.sleep(30)
                continue
        except Exception as e:
            logger.error("[APIGateway] Run error: %s", e)
        await asyncio.sleep(60)


async def start() -> None:
    global _task
    logger.info("[APIGateway] Service started")
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


def register(pm) -> None:
    pm.register_hook(HOOK_ON_ALARM, on_alarm)
    pm.register_hook(HOOK_ON_DEVICE_REGISTER, on_device_register)
    pm.register_hook(HOOK_ON_DEVICE_OFFLINE, on_device_offline)
    logger.info("[APIGateway] Hooks registered: alarm, device_online, device_offline")
