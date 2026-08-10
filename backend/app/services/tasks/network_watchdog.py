from app.db.session import AsyncSessionLocal
from app.models.asset import Asset
from sqlalchemy import select  # TECH_DEBT: 直接依赖具体实现，未来改为Protocol接口注入
import asyncio
from loguru import logger
import os
import platform
import subprocess
import time

import datetime

from app.models.system_setting import SystemSetting



_task: asyncio.Task | None = None

PLUGIN_ID = "network_watchdog"

_DEFAULT_BASE_CONFIG = {
    "enabled": True,
    "check_interval": 60,
}

LOG_DIR = "logs/network_watchdog"

_cfg_cache: dict = {}
_cfg_ts: float = 0.0
_cfg_ttl_sec: int = 10


async def _get_runtime_cfg() -> dict:
    global _cfg_cache, _cfg_ts
    now = time.time()
    if _cfg_cache and (now - _cfg_ts) < _cfg_ttl_sec:
        return _cfg_cache

    # 多租户兼容：取第一个 enabled=true 的配置（check_interval 不敏感可全局取最大）
    async with AsyncSessionLocal() as db:
        stmt = select(SystemSetting).where(
            SystemSetting.setting_key.like(f"plugin_runtime_config.%.{PLUGIN_ID}")
        )
        rows = (await db.execute(stmt)).scalars().all()

    merged = dict(_DEFAULT_BASE_CONFIG)
    any_enabled = False
    interval_max: int | None = None
    for r in rows:
        try:
            import json

            parsed = json.loads(r.setting_value or "{}")
            if not isinstance(parsed, dict):
                continue
            if bool(parsed.get("enabled", False)):
                any_enabled = True
            if "check_interval" in parsed:
                ci = int(parsed.get("check_interval") or 0)
                if ci > 0:
                    interval_max = ci if interval_max is None else max(interval_max, ci)
        except Exception:
            continue

    merged["enabled"] = any_enabled if any_enabled else bool(merged.get("enabled", True))
    if interval_max is not None:
        merged["check_interval"] = interval_max

    _cfg_cache = merged
    _cfg_ts = now
    return _cfg_cache

def ping(host):
    """
    Returns True if host (str) responds to a ping request.
    """
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    command = ['ping', param, '1', host]
    try:
        # 防止命令不存在时watchdog崩溃
        return subprocess.call(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
    except (OSError, FileNotFoundError):
        return False

async def watchdog():
    while True:
        cfg = await _get_runtime_cfg()
        enabled = bool(cfg.get("enabled", True))
        check_interval = int(cfg.get("check_interval") or _DEFAULT_BASE_CONFIG["check_interval"])
        check_interval = max(1, min(3600, check_interval))

        if not enabled:
            await asyncio.sleep(check_interval)
            continue

        try:
            async with AsyncSessionLocal() as session:
                stmt = select(Asset).where(Asset.status == 1)
                result = await session.execute(stmt)
                assets = result.scalars().all()

                for asset in assets:
                    if asset.ip_addr:
                        # Run ping in executor
                        loop = asyncio.get_running_loop()
                        is_alive = await loop.run_in_executor(None, ping, asset.ip_addr)

                        if not is_alive:
                            # 写入结构化文件日志，便于前端查询/展示
                            if not os.path.exists(LOG_DIR):
                                os.makedirs(LOG_DIR, exist_ok=True)
                            today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
                            log_file = os.path.join(LOG_DIR, f"network_watchdog_{today}.log")
                            timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S.%f")[:-3]
                            line = f"[{timestamp}] device={asset.gb_id} ip={asset.ip_addr} unreachable\n"
                            try:
                                with open(log_file, "a", encoding="utf-8") as f:
                                    f.write(line)
                            except Exception as e:
                                logger.warning(f"Failed to write network watchdog log: {e}")

                            logger.warning(f"[NetworkWatchdog] {line.strip()}")
                        else:
                            pass  # Device is reachable — no action needed

        except Exception as e:
            logger.error(f"[NetworkWatchdog] Error: {e}")

        await asyncio.sleep(check_interval)

async def start():
    global _task
    logger.info("[NetworkWatchdog] Plugin started")
    _task = asyncio.create_task(watchdog())


async def stop():
    global _task
    if _task and not _task.done():
        _task.cancel()
        try:
            await asyncio.wait_for(_task, timeout=5.0)
        except (asyncio.CancelledError, asyncio.TimeoutError) as e:
            logger.warning(f"(asyncio.CancelledError, asyncio.TimeoutError): {e}")
        except Exception as e:
            logger.warning(f"Error: {e}")
    _task = None
