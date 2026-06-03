from __future__ import annotations
from loguru import logger

import asyncio
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

_WATCHDOG_CALLBACK_TIMEOUT = int(getattr(__import__("app.core.config", fromlist=["settings"]).settings, "WATCHDOG_CALLBACK_TIMEOUT_SECONDS", 30) or 30)

_tasks: dict[str, asyncio.Task] = {}


def cancel_watchdog(key: str) -> None:
    if not key:
        return
    task = _tasks.pop(key, None)
    if task and not task.done():
        task.cancel()


def start_watchdog(
    *,
    key: str,
    timeout_seconds: int,
    on_timeout: Callable[[], Awaitable[None]],
) -> None:
    if not key:
        return
    cancel_watchdog(key)

    async def _run():
        try:
            await asyncio.sleep(max(1, int(timeout_seconds or 1)))
            try:
                await asyncio.wait_for(on_timeout(), timeout=_WATCHDOG_CALLBACK_TIMEOUT)
            except asyncio.TimeoutError:
                # FIXED: Watchdog callback timeout - log ERROR instead of silent pass
                logger.error(f"Watchdog on_timeout callback exceeded {_WATCHDOG_CALLBACK_TIMEOUT}s for key={key}, resources may leak")
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error(f"Watchdog on_timeout callback failed for key={key}: {e}")
            return
        finally:
            current = _tasks.get(key)
            if current is asyncio.current_task():
                _tasks.pop(key, None)

    _tasks[key] = asyncio.create_task(_run())


# 流切换专用看门狗（独立于 INVITE 主流程）
_SWITCH_TASKS: dict[str, asyncio.Task] = {}


def cancel_stream_switch_watchdog(call_id: str) -> None:
    """取消流切换 Re-INVITE 的超时看门狗"""
    key = f"switch:{call_id}"
    task = _SWITCH_TASKS.pop(key, None)
    if task and not task.done():
        task.cancel()


def start_stream_switch_watchdog(
    *,
    call_id: str,
    timeout_seconds: int,
    on_timeout: Callable[[], Awaitable[None]],
) -> None:
    """
    启动流切换 Re-INVITE 的超时看门狗。
    超时后自动回退原码流，防止设备无响应时流切换永远挂起。
    """
    key = f"switch:{call_id}"
    cancel_stream_switch_watchdog(call_id)

    async def _run():
        try:
            await asyncio.sleep(max(1, int(timeout_seconds or 1)))
            try:
                await asyncio.wait_for(on_timeout(), timeout=_WATCHDOG_CALLBACK_TIMEOUT)
            except asyncio.TimeoutError:
                # FIXED: Stream switch watchdog callback timeout - log ERROR instead of silent pass
                logger.error(f"Stream switch watchdog on_timeout exceeded {_WATCHDOG_CALLBACK_TIMEOUT}s for call_id={call_id}")
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error(f"Stream switch watchdog on_timeout callback failed for key={key}: {e}")
            return
        finally:
            current = _SWITCH_TASKS.get(key)
            if current is asyncio.current_task():
                _SWITCH_TASKS.pop(key, None)

    _SWITCH_TASKS[key] = asyncio.create_task(_run())
