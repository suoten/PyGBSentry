import asyncio
import datetime
import time as _time_module
from loguru import logger

from app.db.session import AsyncSessionLocal
from app.models.asset import Asset
from app.models.resource import Resource
from sqlalchemy import select, update


# FIX: [2026-07-03] _ensure_aware_utc 仅在 server.py 的局部作用域中定义，device_watchdog.py 引用未定义的名称导致 NameError [全栈工程师]
def _ensure_aware_utc(dt_val):
    """将 offset-naive datetime 视为 UTC 并添加 tzinfo。"""
    if dt_val is not None and hasattr(dt_val, 'tzinfo') and dt_val.tzinfo is None:
        return dt_val.replace(tzinfo=datetime.timezone.utc)
    return dt_val

_task: asyncio.Task | None = None

CHECK_INTERVAL_SECONDS = 30
# P0-fix: 旧逻辑 expires*3+5 在 expires=3600 时给出 10805s ≈ 3 小时，远超 GB28181 推荐的 3×60=180s
# 新逻辑：基于观测 Keepalive 间隔（默认 60s）的 3 倍，下限 180s，上限 600s 兼容慢心跳设备
DEFAULT_KEEPALIVE_INTERVAL_SECONDS = 60
OFFLINE_MISSES_REQUIRED = 3  # GB/T 28181-2022 §A.1：连续 3 次未收到 Keepalive 判定离线
OFFLINE_THRESHOLD_MIN_SECONDS = 180  # 下限：3 × 默认 60s
OFFLINE_THRESHOLD_MAX_SECONDS = 600  # 上限：兼容慢心跳设备

# S-03: 共享去重时间戳 — server._check_device_offline 每 5s 执行一次并更新此值，
# device_watchdog 执行前检查，若近期已由 server 执行则跳过，避免双重执行
_last_offline_check_ts: float = 0.0
_OFFLINE_CHECK_DEBOUNCE_SECONDS = 25  # server 每 5s 执行，25s 内已执行则跳过


async def _check_device_offline():
    # S-03: 若 server._check_device_offline 近期已执行，跳过避免双重执行
    # 两者都会调用 _cleanup_device_resources，双重执行导致竞态和资源浪费
    global _last_offline_check_ts
    _now_ts = _time_module.monotonic()
    if _now_ts - _last_offline_check_ts < _OFFLINE_CHECK_DEBOUNCE_SECONDS:
        logger.debug("Device watchdog: skipping, server._check_device_offline ran recently")
        return
    _last_offline_check_ts = _now_ts

    now = datetime.datetime.now(datetime.timezone.utc) # utcnow() deprecated in Python 3.12+
    offline_count = 0
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(Asset).where(Asset.status == 1)
            result = await session.execute(stmt)
            online_devices = result.scalars().all()

            offline_devices = []
            _offline_asset_ids = []
            for device in online_devices:
                if not device.last_keepalive:
                    continue
                # P0-fix: 改用基于 Keepalive 间隔的阈值，而非 REGISTER expires
                # GB28181 §A.1 推荐连续 3 次未收到心跳判定离线，默认间隔 60s → 180s 阈值
                _ka_interval = int(getattr(device, "keepalive_interval", 0) or 0)
                if _ka_interval <= 0:
                    _ka_interval = DEFAULT_KEEPALIVE_INTERVAL_SECONDS
                threshold = _ka_interval * OFFLINE_MISSES_REQUIRED
                # 限制在 [180s, 600s] 区间，避免极端配置导致误判或僵尸会话
                threshold = max(OFFLINE_THRESHOLD_MIN_SECONDS, min(threshold, OFFLINE_THRESHOLD_MAX_SECONDS))
                # FIX: [2026-07-03] last_keepalive 可能是 SQLite 返回的 naive datetime，转 aware 后再相减 [全栈工程师]
                last_keepalive_aware = _ensure_aware_utc(device.last_keepalive)
                elapsed = (now - last_keepalive_aware).total_seconds()
                if elapsed > threshold:
                    device.status = 0
                    offline_count += 1
                    offline_devices.append(device)
                    if device.id:
                        _offline_asset_ids.append(device.id)
                    logger.info(
                        "Device offline (heartbeat timeout): gb_id={} last_keepalive={} elapsed={:.0f}s threshold={}s ka_interval={}s",
                        device.gb_id,
                        device.last_keepalive.isoformat() if hasattr(device.last_keepalive, "isoformat") else str(device.last_keepalive),
                        elapsed,
                        threshold,
                        _ka_interval,
                    )

            # P0-N+1: 批量更新所有离线设备的通道状态，避免循环内逐条 UPDATE
            if _offline_asset_ids:
                await session.execute(
                    update(Resource).where(Resource.asset_id.in_(_offline_asset_ids)).values(status=0)
                )

            if offline_count > 0:
                await session.commit()
                logger.info("Device watchdog: marked {} device(s) offline", offline_count)
                # S-02 watchdog标记离线后也必须清理流会话/订阅/Dialog，与server._check_device_offline一致
                for device in offline_devices:
                    try:
                        from app.sip.handlers import _cleanup_device_resources
                        await _cleanup_device_resources(device.gb_id)
                    except Exception as cleanup_err:
                        logger.warning("Device watchdog cleanup failed for {}: {}", device.gb_id, cleanup_err)
    except Exception as e:
        logger.error("Device watchdog error: {}", e)


async def _watchdog_loop():
    logger.info("Device heartbeat watchdog started (interval={}s)", CHECK_INTERVAL_SECONDS)
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
    _task = asyncio.create_task(_watchdog_loop(), name="device_watchdog_loop")  # P2-fix: 便于任务排查


async def stop():
    global _task
    if _task and not _task.done():
        _task.cancel()
        try:
            await asyncio.wait_for(_task, timeout=5.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            logger.debug("task_cancelled")
    _task = None
