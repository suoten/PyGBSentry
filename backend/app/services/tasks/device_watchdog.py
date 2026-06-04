import asyncio
import datetime
from loguru import logger

from app.db.session import AsyncSessionLocal
from app.models.asset import Asset
from app.models.resource import Resource
from sqlalchemy import select, update

_task: asyncio.Task | None = None

CHECK_INTERVAL_SECONDS = 30
OFFLINE_THRESHOLD_MULTIPLIER = 3
OFFLINE_THRESHOLD_EXTRA_SECONDS = 5


async def _check_device_offline():
    now = datetime.datetime.now(datetime.timezone.utc) # utcnow() deprecated in Python 3.12+
    offline_count = 0
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(Asset).where(Asset.status == 1)
            result = await session.execute(stmt)
            online_devices = result.scalars().all()

            offline_devices = []
            for device in online_devices:
                if not device.last_keepalive:
                    continue
                expires = device.expires or 3600
                threshold = expires * OFFLINE_THRESHOLD_MULTIPLIER + OFFLINE_THRESHOLD_EXTRA_SECONDS
                elapsed = (now - device.last_keepalive).total_seconds()
                if elapsed > threshold:
                    device.status = 0
                    # S-10 设备离线时同步更新其下所有通道(Resource)状态为离线
                    await session.execute(update(Resource).where(Resource.asset_id == device.id).values(status=0))
                    offline_count += 1
                    offline_devices.append(device)
                    logger.info(
                        "Device offline (heartbeat timeout): gb_id=%s last_keepalive=%s elapsed=%.0fs threshold=%ds",
                        device.gb_id,
                        device.last_keepalive.isoformat() if hasattr(device.last_keepalive, "isoformat") else str(device.last_keepalive),
                        elapsed,
                        threshold,
                    )

            if offline_count > 0:
                await session.commit()
                logger.info("Device watchdog: marked %d device(s) offline", offline_count)
                # S-02 watchdog标记离线后也必须清理流会话/订阅/Dialog，与server._check_device_offline一致
                for device in offline_devices:
                    try:
                        from app.sip.handlers import _cleanup_device_resources
                        await _cleanup_device_resources(device.gb_id)
                    except Exception as cleanup_err:
                        logger.warning("Device watchdog cleanup failed for %s: %s", device.gb_id, cleanup_err)
    except Exception as e:
        logger.error("Device watchdog error: %s", e)


async def _watchdog_loop():
    logger.info("Device heartbeat watchdog started (interval=%ds)", CHECK_INTERVAL_SECONDS)
    while True:
        try:
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)
            await _check_device_offline()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Device watchdog loop error: {e}")


async def start():
    global _task
    _task = asyncio.create_task(_watchdog_loop())


async def stop():
    global _task
    if _task and not _task.done():
        _task.cancel()
        try:
            await asyncio.wait_for(_task, timeout=5.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
    _task = None
