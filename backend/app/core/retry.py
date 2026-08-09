"""General-purpose retry utility with exponential backoff and jitter."""

from __future__ import annotations

import asyncio
import random
import functools
from typing import Any, Callable, Sequence, Type

from loguru import logger


def retry_async(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: Sequence[Type[Exception]] = (ConnectionError, TimeoutError, OSError),
    on_retry: Callable[[int, Exception, float], None] | None = None,
):
    """
    Decorator for async functions that retries on specified exceptions
    with exponential backoff and optional jitter.

    Args:
        max_attempts: Maximum number of attempts (including the first call).
        base_delay: Initial delay in seconds between retries.
        max_delay: Maximum delay in seconds between retries.
        exponential_base: Base for exponential backoff calculation.
        jitter: Whether to add random jitter to the delay.
        retryable_exceptions: Tuple of exception types that should trigger a retry.
        on_retry: Optional callback called on each retry: (attempt, exception, delay).
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except tuple(retryable_exceptions) as e:
                    last_exception = e
                    if attempt >= max_attempts:
                        logger.warning(
                            f"retry_async: {func.__name__} failed after {max_attempts} attempts: {e}"
                        )
                        raise
                    delay = min(base_delay * (exponential_base ** (attempt - 1)), max_delay)
                    if jitter:
                        delay = delay * random.uniform(0.5, 1.5)
                    delay = min(delay, max_delay)
                    logger.debug(
                        f"retry_async: {func.__name__} attempt {attempt}/{max_attempts} failed: {e}, "
                        f"retrying in {delay:.2f}s"
                    )
                    if on_retry:
                        try:
                            on_retry(attempt, e, delay)
                        except Exception as _cb_err:
                            # FIX [2026-07-17 P3-28]: 描述性日志替代静默吞异常
                            logger.warning(f"retry_async: on_retry callback for {func.__name__} failed: {_cb_err}")
                    await asyncio.sleep(delay)
            raise last_exception  # type: ignore[misc]

        return wrapper

    return decorator


async def retry_async_call(
    func: Callable,
    *args: Any,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: Sequence[Type[Exception]] = (ConnectionError, TimeoutError, OSError),
    **kwargs: Any,
) -> Any:
    """
    Programmatic async retry for one-off calls without decorator.

    Usage:
        result = await retry_async_call(some_async_func, arg1, arg2, max_attempts=5)
    """
    last_exception = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await func(*args, **kwargs)
        except tuple(retryable_exceptions) as e:
            last_exception = e
            if attempt >= max_attempts:
                logger.warning(
                    f"retry_async_call: {func.__name__} failed after {max_attempts} attempts: {e}"
                )
                raise
            delay = min(base_delay * (exponential_base ** (attempt - 1)), max_delay)
            if jitter:
                delay = delay * random.uniform(0.5, 1.5)
            delay = min(delay, max_delay)
            logger.debug(
                f"retry_async_call: {func.__name__} attempt {attempt}/{max_attempts} failed: {e}, "
                f"retrying in {delay:.2f}s"
            )
            await asyncio.sleep(delay)
    raise last_exception  # type: ignore[misc]
