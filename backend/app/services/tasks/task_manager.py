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

    # 4. 幽灵流周期对账（FIX [2026-11-20 P2]:ZLM 有 GB RTP 推流但无会话的流,宽限后关闭）
    try:
        from app.services.tasks import stream_ghost_reconcile

        await stream_ghost_reconcile.start()
        _stop_callbacks.append(stream_ghost_reconcile.stop)
        logger.info("Background task started: stream_ghost_reconcile")
    except Exception as e:
        logger.warning(f"Failed to start stream_ghost_reconcile: {e}")

    # 5. 流量账单采样（ROADMAP Phase3:按通道累计流量进 traffic_daily）
    try:
        from app.services.tasks import traffic_meter

        await traffic_meter.start()
        _stop_callbacks.append(traffic_meter.stop)
        logger.info("Background task started: traffic_meter")
    except Exception as e:
        logger.warning(f"Failed to start traffic_meter: {e}")

    # 5. 迁移自 plugins 的周期任务与 hook 模块统一接线
    # FIX [2026-11-20 P0]:scripts/migrate_plugins.py 把这些模块从 plugins/ 迁入 tasks/ 时
    # 剥掉了 HOOK_ON_STARTUP/register() 启动接线,新接线从未补上,导致它们整体成为死代码
    # （含录制计划执行器/自动录制/空闲流回收/快照刷新/拉流代理自愈/流健康监测等核心功能）。
    # 此处只负责启动;每个模块是否真正运行由其自带开关决定(settings 或
    # plugin_runtime_config.*.<id>,多数默认开启,详见各模块 _DEFAULT_BASE_CONFIG / config.py)。
    # ssl_certbot_renewer 为空文件未列入。事件类模块通过 register(pm) 挂接 hook。
    for _task_name in (
        # 设置项开关（config.py）
        "record_schedule_executor",   # RECORD_SCHEDULE_EXECUTOR_ENABLED（默认开）
        "record_index_verifier",      # RECORD_INDEX_VERIFY_ENABLED（默认开）
        "snapshot_refresh",           # SNAPSHOT_REFRESH_ENABLED（默认开）
        "pull_proxy_monitor",         # PULL_PROXY_MONITOR_ENABLED（默认开）
        "rtmp_push_channel_monitor",  # PUSH_CHANNEL_MONITOR_ENABLED（默认开）
        # 运行时配置开关（SystemSetting.plugin_runtime_config.*，默认开）
        "auto_record",
        "stream_idle",
        "stream_health",
        "network_watchdog",
        "ptz_tour",
        "timelapse",
        "webhook_pusher",
        # hook 型模块（register(pm) 挂接事件钩子，部分另有轻量 start）
        "api_gateway",
        "event_bridge",
        "log_collector",
        "sip_logger",
        "snmp_trap",
    ):
        try:
            mod = __import__(f"app.services.tasks.{_task_name}", fromlist=["*"])
        except Exception as e:
            logger.warning(f"Failed to import task module {_task_name}: {e}")
            continue
        try:
            if plugin_manager is not None and hasattr(mod, "register"):
                mod.register(plugin_manager)
        except Exception as e:
            logger.warning(f"Failed to register hooks for {_task_name}: {e}")
        try:
            _start_fn = getattr(mod, "start", None)
            if callable(_start_fn):
                _result = _start_fn()
                if asyncio.iscoroutine(_result):
                    await _result
                _stop_fn = getattr(mod, "stop", None)
                if callable(_stop_fn):
                    _stop_callbacks.append(_stop_fn)
                logger.info(f"Background task started: {_task_name}")
            elif hasattr(mod, "register"):
                logger.info(f"Background hooks registered: {_task_name}")
        except Exception as e:
            logger.warning(f"Failed to start {_task_name}: {e}")

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
