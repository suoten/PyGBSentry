from loguru import logger
import datetime
import os
import json
import time

from sqlalchemy import select  # TECH_DEBT: 直接依赖具体实现，未来改为Protocol接口注入

from app.db.session import AsyncSessionLocal
from app.models.system_setting import SystemSetting



PLUGIN_ID = "sip_logger"

_DEFAULT_BASE_CONFIG = {
    "enabled": True,
    "log_dir": "logs/sip_audit",
}

_cfg_cache: dict = {}
_cfg_ts: float = 0.0
_cfg_ttl_sec: int = 10


async def _get_runtime_cfg() -> dict:
    global _cfg_cache, _cfg_ts
    now = time.time()
    if _cfg_cache and (now - _cfg_ts) < _cfg_ttl_sec:
        return _cfg_cache

    async with AsyncSessionLocal() as db:
        stmt = select(SystemSetting).where(
            SystemSetting.setting_key.like(f"plugin_runtime_config.%.{PLUGIN_ID}")
        )
        rows = (await db.execute(stmt)).scalars().all()

    merged = dict(_DEFAULT_BASE_CONFIG)
    any_enabled = False
    chosen_log_dir = None

    for r in rows:
        try:
            parsed = json.loads(r.setting_value or "{}")
            if not isinstance(parsed, dict):
                continue
            if bool(parsed.get("enabled", False)):
                any_enabled = True
            if chosen_log_dir is None and parsed.get("log_dir"):
                chosen_log_dir = str(parsed.get("log_dir") or "").strip()
        except Exception:
            continue

    merged["enabled"] = any_enabled if any_enabled else bool(merged.get("enabled", True))
    if chosen_log_dir:
        merged["log_dir"] = chosen_log_dir

    _cfg_cache = merged
    _cfg_ts = now
    return _cfg_cache

async def _write_sip_audit(message, addr, proto, direction: str):
    """
    Log SIP message details to file
    """
    cfg = await _get_runtime_cfg()
    if not cfg or not cfg.get("enabled", True):
        return

    log_dir = str(cfg.get("log_dir") or _DEFAULT_BASE_CONFIG["log_dir"])
    if not log_dir:
        return

    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Rotate by day
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    log_file = os.path.join(log_dir, f"sip_{today}.log")

    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S.%f")[:-3]

    log_entry = f"""
[{timestamp}] [{direction}] [{proto}] {addr[0]}:{addr[1]}
{str(message)}
--------------------------------------------------
"""
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_entry)
    except Exception as e:
        logger.error(f"[SIPLogger] Write error: {e}")


async def log_sip_receive(message, addr, proto):
    await _write_sip_audit(message, addr, proto, "inbound")


async def log_sip_send(message, addr, proto):
    await _write_sip_audit(message, addr, proto, "outbound")


def register(pm) -> None:
    from app.core.plugin_manager import HOOK_ON_SIP_RECEIVE, HOOK_ON_SIP_SEND
    pm.register_hook(HOOK_ON_SIP_RECEIVE, log_sip_receive)
    pm.register_hook(HOOK_ON_SIP_SEND, log_sip_send)
    logger.info("[SIPLogger] Hook registered: HOOK_ON_SIP_RECEIVE, HOOK_ON_SIP_SEND")


_async_task = None
_log_file_handle = None


async def stop():
    global _async_task, _log_file_handle
    if _async_task is not None:
        _async_task.cancel()
        try:
            await _async_task
        except Exception as e:
            logger.warning(f"Exception: {e}")
        _async_task = None
    if _log_file_handle is not None:
        try:
            _log_file_handle.close()
        except Exception as e:
            logger.warning(f"Exception: {e}")
        _log_file_handle = None
