"""后台任务管理器（统一启动/停止）。

在 ``main.py`` lifespan 启动阶段调用 :func:`start_all_background_tasks` 启动所有
周期性后台任务，在关闭阶段调用 :func:`stop_all_background_tasks` 优雅停止。

当前管理的后台任务：
    * ``device_watchdog`` —— 设备心跳看门狗（定期检测离线设备）
    * ``record_cleanup`` —— 录像清理任务（可选，DB 可用时启动）

所有任务通过 :class:`asyncio.Task` 跟踪，``stop_all`` 时逐一 cancel 并等待退出。
"""
from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

# 已启动的后台任务句柄
_tasks: list[asyncio.Task] = []
# 已注册的 stop 回调（按注册逆序调用）
_stop_callbacks: list = []


async def start_all_background_tasks(plugin_manager: Any = None) -> None:
    """启动所有后台周期任务。

    Args:
        plugin_manager: 插件管理器单例（供插件 hook 使用，当前未直接使用）。

    每个任务独立启动，单个任务启动失败不影响其他任务。
    """
    global _tasks, _stop_callbacks
    _tasks.clear()
    _stop_callbacks.clear()

    # 1. 设备心跳看门狗
    try:
        from app.services.tasks import device_watchdog
        await device_watchdog.start()
        _stop_callbacks.append(device_watchdog.stop)
        logger.info("Background task started: device_watchdog")
    except Exception as e:
        logger.warning(f"Failed to start device_watchdog: {e}")

    # 2. 录像过期清理（可选，DB 不可用时静默跳过）
    try:
        from app.services.record_cleanup import start_record_cleanup_loop
        task = asyncio.create_task(start_record_cleanup_loop())
        _tasks.append(task)
        _stop_callbacks.append(lambda: _cancel_task(task))
        logger.info("Background task started: record_cleanup")
    except ImportError:
        logger.debug("record_cleanup module not available, skipping")
    except Exception as e:
        logger.debug(f"Failed to start record_cleanup: {e}")

    # 3. Catalog 定时刷新（自动同步设备新增/删除通道）
    try:
        from app.services.tasks import catalog_refresh
        await catalog_refresh.start()
        _stop_callbacks.append(catalog_refresh.stop)
        logger.info("Background task started: catalog_refresh")
    except Exception as e:
        logger.warning(f"Failed to start catalog_refresh: {e}")

    logger.info(f"start_all_background_tasks: {len(_tasks)} task(s) + {len(_stop_callbacks)} stop callback(s) registered")


async def stop_all_background_tasks() -> None:
    """优雅停止所有后台任务。

    按注册逆序调用 stop 回调，然后 cancel 所有剩余的 asyncio.Task。
    总超时 10s（由调用方 ``asyncio.wait_for`` 控制）。
    """
    global _tasks, _stop_callbacks

    # 逆序调用 stop 回调
    for cb in reversed(_stop_callbacks):
        try:
            result = cb()
            if asyncio.iscoroutine(result):
                await asyncio.wait_for(result, timeout=5.0)
        except Exception as e:
            logger.warning(f"Background task stop callback error: {e}")
    _stop_callbacks.clear()

    # Cancel 剩余的 asyncio.Task
    for task in _tasks:
        if not task.done():
            task.cancel()
    for task in _tasks:
        try:
            await asyncio.wait_for(task, timeout=3.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            logger.debug("task_cancelled")
        except Exception as e:
            logger.debug(f"Background task shutdown error: {e}")
    _tasks.clear()
    logger.info("stop_all_background_tasks: all tasks stopped")


async def _cancel_task(task: asyncio.Task) -> None:
    """取消单个 asyncio.Task 并等待退出。"""
    if not task.done():
        task.cancel()
    try:
        await asyncio.wait_for(task, timeout=3.0)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        logger.debug("task_cancelled")
    except Exception as e:
        logger.debug(f"task_manager: unexpected error during task cancellation: {e}")
