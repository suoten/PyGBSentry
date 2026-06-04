import asyncio
from loguru import logger

from app.services.tasks import record_schedule_executor
from app.services.tasks import pull_proxy_monitor
from app.services.tasks import rtmp_push_channel_monitor
from app.services.tasks import snapshot_refresh
from app.services.tasks import webhook_pusher
from app.services.tasks import sip_logger
from app.services.tasks import network_watchdog
from app.services.tasks import stream_health
from app.services.tasks import stream_idle
from app.services.tasks import timelapse
from app.services.tasks import ptz_tour
from app.services.tasks import auto_record
from app.services.tasks import record_index_verifier
from app.services.tasks import snmp_trap
from app.services.tasks import api_gateway
from app.services.tasks import log_collector
from app.services.tasks import event_bridge
from app.services.tasks import ssl_certbot_renewer
from app.services.tasks import device_watchdog

TASKS = [
    record_schedule_executor,
    pull_proxy_monitor,
    rtmp_push_channel_monitor,
    snapshot_refresh,
    webhook_pusher,
    sip_logger,
    network_watchdog,
    stream_health,
    stream_idle,
    timelapse,
    ptz_tour,
    auto_record,
    record_index_verifier,
    snmp_trap,
    api_gateway,
    log_collector,
    event_bridge,
    ssl_certbot_renewer,
    device_watchdog,
]

# Hook-based services: 在启动时注册 Hook
_HOOK_TASKS = [snmp_trap, api_gateway, log_collector, event_bridge, webhook_pusher, sip_logger]


async def _register_hooks(plugin_manager):
    for t in _HOOK_TASKS:
        if hasattr(t, "register"):
            try:
                t.register(plugin_manager)
                logger.info("Registered hooks from: %s", t.__name__)
            except Exception as e:
                logger.error(f"Failed to register hooks from {t.__name__}: {e}")

async def start_all_background_tasks(plugin_manager=None):
    logger.info("Starting default background tasks...")
    for t in TASKS:
        try:
            if hasattr(t, "start"):
                await t.start()
        except Exception as e:
            logger.error(f"Failed to start task {t.__name__}: {e}")
    if plugin_manager:
        await _register_hooks(plugin_manager)

async def stop_all_background_tasks():
    logger.info("Stopping default background tasks...")
    async def _stop_one(t):
        if hasattr(t, "stop"):
            try:
                await asyncio.wait_for(t.stop(), timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                logger.warning("(asyncio.CancelledError, asyncio.TimeoutError, Exception) occurred")
    await asyncio.gather(*[_stop_one(t) for t in TASKS], return_exceptions=True)