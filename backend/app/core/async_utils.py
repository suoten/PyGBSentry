"""Async utilities — safe fire-and-forget background tasks.

``fire_and_forget`` schedules a coroutine on the running event loop while
keeping a strong reference in a module-level set so the task is not garbage
collected mid-flight (a common asyncio pitfall). Exceptions are logged rather
than raised, making it safe for non-critical background work (webhooks, plugin
event emission, SIEM push, etc.) — consistent with the ``P0-16`` annotation
used throughout the codebase.
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Optional, TypeVar

from loguru import logger

T = TypeVar("T")

# Strong references to in-flight tasks — prevents CPython from GC'ing the
# task object (and cancelling it) before it completes.
_background_tasks: set[asyncio.Task] = set()


def fire_and_forget(coro: Awaitable[T], *, name: Optional[str] = None) -> Optional[asyncio.Task]:
    """Schedule ``coro`` as a background task and return immediately.

    The task is tracked in ``_background_tasks`` to prevent garbage collection.
    Any exception raised by the coroutine is logged at ERROR level and swallowed
    so it never propagates to the caller. Returns ``None`` if no running event
    loop exists (e.g. called during import), in which case the coroutine is
    closed to avoid "never awaited" warnings.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop — close the coroutine to suppress the
        # "coroutine was never awaited" warning, then give up.
        try:
            coro.close()  # type: ignore[attr-defined]
        except Exception:
            logger.warning("silently_swallowed_exception", exc_info=True)
        return None

    task = loop.create_task(coro, name=name) if name else loop.create_task(coro)
    _background_tasks.add(task)

    def _on_done(t: asyncio.Task) -> None:
        """Internal helper:  on done."""
        _background_tasks.discard(t)
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            logger.error(f"fire_and_forget task raised: {exc!r}", exc_info=exc)

    task.add_done_callback(_on_done)
    return task
