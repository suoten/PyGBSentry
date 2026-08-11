import asyncio
from loguru import logger
import time
import os
import datetime

import requests as _requests

from app.db.session import AsyncSessionLocal
from app.models.system_setting import SystemSetting
from sqlalchemy import select  # TECH_DEBT: 直接依赖具体实现，未来改为Protocol接口注入



PLUGIN_ID = "webhook_pusher"

LOG_DIR = "logs/webhook_pusher"

# Defaults should match `editions/server/backend/plugin_packages/webhook_pusher/plugin.json#config_template`
_DEFAULT_BASE_CONFIG = {
    "enabled": True,
    "webhook_url": "",
}

_cfg_cache: dict = {}
_cfg_ts: float = 0.0
_cfg_ttl_sec: int = 30


async def _get_runtime_cfg() -> dict:
    global _cfg_cache, _cfg_ts
    now = time.time()
    if _cfg_cache and (now - _cfg_ts) < _cfg_ttl_sec:
        return _cfg_cache
    # 多租户兼容：聚合所有 tenant 的 webhook_pusher 配置，取第一个有效 webhook_url。
    async with AsyncSessionLocal() as db:
        stmt = select(SystemSetting).where(
            SystemSetting.setting_key.like(f"plugin_runtime_config.%.{PLUGIN_ID}")
        )
        rows = (await db.execute(stmt)).scalars().all()
        merged = dict(_DEFAULT_BASE_CONFIG)
        any_enabled = False
        url_found = None
        for r in rows:
            try:
                import json

                parsed = json.loads(r.setting_value or "{}")
                if not isinstance(parsed, dict):
                    continue
                if bool(parsed.get("enabled", False)):
                    any_enabled = True
                    url = str(parsed.get("webhook_url") or "").strip()
                    if url_found is None and url:
                        url_found = url
            except Exception as e:
                logger.debug(f"webhook config parse failed: {e}")
                continue
        merged["enabled"] = any_enabled if any_enabled else bool(merged.get("enabled", True))
        if url_found:
            merged["webhook_url"] = url_found
        _cfg_cache = merged
        _cfg_ts = now
        return _cfg_cache


async def _push_webhook(*, device_id: str, status: str) -> None:
    cfg = await _get_runtime_cfg()
    if not cfg or not cfg.get("enabled", True):
        return
    webhook_url = str(cfg.get("webhook_url") or "").strip()
    if not webhook_url:
        return
    payload = {
        "device_id": device_id,
        "status": status,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    # 结构化日志：记录成功/失败（不写 webhook_url，避免敏感信息泄露）
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    log_file = os.path.join(LOG_DIR, f"webhook_pusher_{today}.log")
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S.%f")[:-3]
    try:
        await asyncio.to_thread(
            _requests.post, webhook_url, json=payload, timeout=2
        )
        logger.info(f"[Webhook] Pushed {status} for {device_id}")
        line = f"[{timestamp}] device={device_id} status={status} ok=true\n"
        try:
            if not os.path.exists(LOG_DIR):
                os.makedirs(LOG_DIR, exist_ok=True)
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception as log_err:
            logger.warning(f"Webhook 日志写入失败: {log_err}")
    except Exception as e:
        logger.error(f"[Webhook] Failed to push {status} for {device_id}: {e}")
        err_s = str(e)
        err_s = " ".join(err_s.split())[:300]
        line = f"[{timestamp}] device={device_id} status={status} ok=false err={err_s}\n"
        try:
            if not os.path.exists(LOG_DIR):
                os.makedirs(LOG_DIR, exist_ok=True)
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception as log_err:
            logger.warning(f"Webhook 日志写入失败: {log_err}")


async def on_device_register(device_id):
    await _push_webhook(device_id=str(device_id or "").strip(), status="online")

async def on_device_offline(device_id):
    await _push_webhook(device_id=str(device_id or "").strip(), status="offline")


def register(pm) -> None:
    from app.core.plugin_manager import HOOK_ON_DEVICE_REGISTER, HOOK_ON_DEVICE_OFFLINE
    pm.register_hook(HOOK_ON_DEVICE_REGISTER, on_device_register)
    pm.register_hook(HOOK_ON_DEVICE_OFFLINE, on_device_offline)
    logger.info("[WebhookPusher] Hook registered: HOOK_ON_DEVICE_REGISTER, HOOK_ON_DEVICE_OFFLINE")


async def stop():
    pass  # intentional: no background task to stop for webhook pusher
