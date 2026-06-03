"""简单延时队列：在指定延迟后执行异步任务，用于级联目录推送等定时任务。"""
import asyncio
from loguru import logger
from typing import Coroutine, Any


# W-23 延时任务追踪字典，支持按 key 取消任务
_pending_tasks: dict[str, asyncio.Task] = {}


def run_after(delay_seconds: float, coro: Coroutine[Any, Any, Any], key: str | None = None) -> asyncio.Task:
    """在 delay_seconds 秒后执行 coro，返回 asyncio.Task。

    Args:
        delay_seconds: 延迟秒数
        coro: 要执行的协程
        key: 可选的任务标识，提供后可通过 cancel_delayed(key) 取消任务
    """
    async def _run():
        await asyncio.sleep(delay_seconds)
        try:
            await coro
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("Delay queue task failed: %s", e)
        finally:
            if key is not None:
                _pending_tasks.pop(key, None)

    task = asyncio.create_task(_run())
    if key is not None:
        # 如果已有同 key 的旧任务，先取消
        old_task = _pending_tasks.pop(key, None)
        if old_task and not old_task.done():
            old_task.cancel()
        _pending_tasks[key] = task
    return task


def cancel_delayed(key: str) -> bool:
    """取消指定 key 的延时任务。返回 True 表示成功取消，False 表示任务不存在或已完成。"""
    task = _pending_tasks.pop(key, None)
    if task is None:
        return False
    if not task.done():
        task.cancel()
        return True
    return False
