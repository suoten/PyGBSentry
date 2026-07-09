"""Bounded delay queue for deferred coroutine execution.

:func:`run_after` schedules a coroutine to run after ``delay`` seconds using
:func:`asyncio.ensure_future`. The task reference is retained to prevent GC
and exceptions are logged via a done-callback. This is used by platform
catalog push pacing and stream-strategy backoff timers.
"""
from __future__ import annotations

import asyncio
from typing import Awaitable

from loguru import logger

_pending: set[asyncio.Task] = set()


def run_after(delay: float, coro: Awaitable) -> asyncio.Task | None:
    """Schedule ``coro`` to run after ``delay`` seconds.

    Safe to call from a running loop. Returns the created task (or ``None``
    when no loop is running, in which case the coroutine is closed).
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop — close the coroutine to avoid "never awaited" warning.
        try:
            coro.close()  # type: ignore[attr-defined]
        except Exception as e:
            logger.debug(f"delay_queue: failed to close coroutine: {e}")
        logger.debug("delay_queue: run_after called with no running loop; dropped")
        return None

    async def _runner() -> None:
        """Internal helper:  runner."""
        try:
            if delay > 0:
                await asyncio.sleep(delay)
            await coro
        except Exception as e:
            logger.warning(f"delay_queue: deferred task failed: {e}")

    task = loop.create_task(_runner())
    _pending.add(task)
    task.add_done_callback(_pending.discard)
    return task


def cancel_all() -> None:
    """Cancel all pending delayed tasks (called on shutdown)."""
    for t in list(_pending):
        if not t.done():
            t.cancel()
    _pending.clear()
