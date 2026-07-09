"""SIP 流看门狗与码流切换看门狗定时器。

提供两类一次性超时定时器，用于在 GB28181 SIP 信令流程中守护那些"必须在有限
时间内完成"的异步操作：

1. **通用流看门狗** (:func:`start_watchdog` / :func:`cancel_watchdog`)
   - 按 ``key``（如 ``"invite:<call_id>"``）索引。
   - INVITE 发送后启动，收到 200 OK / 超时 / 主动取消时取消。
   - 超时回调 ``on_timeout`` 可为 ``async`` 函数（返回协程）或同步函数。

2. **码流切换看门狗** (:func:`start_stream_switch_watchdog` / :func:`cancel_stream_switch_watchdog`)
   - 按 ``call_id`` 索引（独立命名空间，避免与通用看门狗的 ``invite:<call_id>`` 冲突）。
   - Re-INVITE 码流切换后启动，设备超时未响应则回滚原码流。
   - ``on_timeout`` 通常为 ``lambda: self._do_stream_switch_rollback(call_id)``，
     返回协程。

定时器基于 :meth:`asyncio.loop.call_later`，超时后自动从内部表移除；取消时调用
``TimerHandle.cancel()``。所有启动/取消函数为同步函数（在已有事件循环的协程内
调用），超时回调的协程通过 :func:`app.core.async_utils.fire_and_forget` 调度，
确保异常被记录且任务引用被保留。

模块导入绝不抛异常。
"""
from __future__ import annotations

import asyncio
import inspect
from typing import Callable, Optional

from loguru import logger

from app.core.async_utils import fire_and_forget


# 通用看门狗定时器表：key -> asyncio.TimerHandle
_watchdogs: dict[str, asyncio.TimerHandle] = {}
# 码流切换看门狗定时器表：call_id -> asyncio.TimerHandle
_stream_switch_watchdogs: dict[str, asyncio.TimerHandle] = {}


def _invoke_callback(on_timeout: Callable) -> None:
    """调用超时回调；若返回协程则交给 fire_and_forget 调度。

    ``on_timeout`` 可能是：
        * ``async def`` 函数 —— 调用后返回协程，需 await / fire_and_forget。
        * 普通 ``def`` 函数返回协程 —— 同上。
        * 普通 ``def`` 函数返回 None —— 已同步执行完毕。
    """
    if on_timeout is None:
        return
    try:
        result = on_timeout()
    except Exception as e:
        logger.error(f"watchdog on_timeout callback raised synchronously: {e!r}", exc_info=e)
        return
    # 结果是协程/可等待对象 -> 用 fire_and_forget 调度
    if inspect.isawaitable(result):
        fire_and_forget(result)


def _make_fire_callback(label: str, key: str, table: dict[str, asyncio.TimerHandle], on_timeout: Callable):
    """构造 call_later 的同步回调，负责清理表并调用 on_timeout。"""

    def _fire() -> None:
        """Internal helper:  fire."""
        # 从表中移除（已触发）
        table.pop(key, None)
        logger.debug(f"watchdog fired: {label} key={key}")
        _invoke_callback(on_timeout)

    return _fire


def _get_running_loop() -> Optional[asyncio.AbstractEventLoop]:
    """安全获取当前运行的事件循环；无循环时返回 None。"""
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


# ---------------------------------------------------------------------------
# 通用流看门狗
# ---------------------------------------------------------------------------

def start_watchdog(*, key: str, timeout_seconds: float, on_timeout: Callable) -> bool:
    """启动一个通用看门狗定时器。

    Args:
        key: 唯一标识（如 ``"invite:<call_id>"``）。若该 key 已存在定时器，
            先取消旧的再用新的覆盖（语义为"重置"）。
        timeout_seconds: 超时秒数；<=0 时不启动定时器但立即记日志（视为禁用）。
        on_timeout: 超时回调；可为 ``async def`` 或返回协程的同步函数。

    Returns:
        ``True`` 表示成功调度；``False`` 表示无运行事件循环或超时<=0。
    """
    if not key:
        logger.warning("start_watchdog: empty key, ignored")
        return False
    timeout = float(timeout_seconds or 0)
    if timeout <= 0:
        logger.debug(f"start_watchdog: non-positive timeout for key={key}, watchdog disabled")
        return False

    loop = _get_running_loop()
    if loop is None:
        logger.warning(f"start_watchdog: no running event loop, cannot schedule key={key}")
        return False

    # 若已存在同名定时器，先取消（重置语义）
    old = _watchdogs.pop(key, None)
    if old is not None:
        old.cancel()

    cb = _make_fire_callback("watchdog", key, _watchdogs, on_timeout)
    handle = loop.call_later(timeout, cb)
    _watchdogs[key] = handle
    logger.debug(f"start_watchdog: scheduled key={key} timeout={timeout}s")
    return True


def cancel_watchdog(key: str) -> None:
    """取消通用看门狗；key 不存在或已触发均为无操作。"""
    if not key:
        return
    handle = _watchdogs.pop(key, None)
    if handle is not None:
        handle.cancel()
        logger.debug(f"cancel_watchdog: cancelled key={key}")
    # 若 handle 为 None：已触发或从未启动，静默忽略


# ---------------------------------------------------------------------------
# 码流切换看门狗
# ---------------------------------------------------------------------------

def start_stream_switch_watchdog(*, call_id: str, timeout_seconds: float, on_timeout: Callable) -> bool:
    """启动码流切换看门狗（按 call_id 索引，独立命名空间）。

    语义与 :func:`start_watchdog` 一致，仅存储表不同，避免与通用看门狗的
    ``"invite:<call_id>"`` key 冲突。

    Args:
        call_id: SIP 对话 Call-ID。
        timeout_seconds: 超时秒数。
        on_timeout: 超时回调，通常为 ``lambda: rollback(call_id)`` 返回协程。

    Returns:
        ``True`` 表示成功调度。
    """
    if not call_id:
        logger.warning("start_stream_switch_watchdog: empty call_id, ignored")
        return False
    timeout = float(timeout_seconds or 0)
    if timeout <= 0:
        logger.debug(f"start_stream_switch_watchdog: non-positive timeout for call_id={call_id}, disabled")
        return False

    loop = _get_running_loop()
    if loop is None:
        logger.warning(f"start_stream_switch_watchdog: no running event loop, call_id={call_id}")
        return False

    old = _stream_switch_watchdogs.pop(call_id, None)
    if old is not None:
        old.cancel()

    cb = _make_fire_callback("stream_switch", call_id, _stream_switch_watchdogs, on_timeout)
    handle = loop.call_later(timeout, cb)
    _stream_switch_watchdogs[call_id] = handle
    logger.debug(f"start_stream_switch_watchdog: scheduled call_id={call_id} timeout={timeout}s")
    return True


def cancel_stream_switch_watchdog(call_id: str) -> None:
    """取消码流切换看门狗；call_id 不存在或已触发均为无操作。"""
    if not call_id:
        return
    handle = _stream_switch_watchdogs.pop(call_id, None)
    if handle is not None:
        handle.cancel()
        logger.debug(f"cancel_stream_switch_watchdog: cancelled call_id={call_id}")


# ---------------------------------------------------------------------------
# 调试 / 维护
# ---------------------------------------------------------------------------

def watchdog_stats() -> dict:
    """返回当前看门狗计数（调试用）。"""
    return {
        "watchdogs": len(_watchdogs),
        "stream_switch_watchdogs": len(_stream_switch_watchdogs),
    }


def cancel_all_watchdogs() -> None:
    """取消所有看门狗（主要用于测试 / 关闭清理）。"""
    for h in _watchdogs.values():
        try:
            h.cancel()
        except Exception as e:
            logger.warning(f"cancel_all_watchdogs: cancel watchdog failed: {e}")
    for h in _stream_switch_watchdogs.values():
        try:
            h.cancel()
        except Exception as e:
            logger.warning(f"cancel_all_watchdogs: cancel stream switch watchdog failed: {e}")
    _watchdogs.clear()
    _stream_switch_watchdogs.clear()
