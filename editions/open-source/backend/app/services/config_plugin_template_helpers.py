from __future__ import annotations

import contextlib
from typing import Any, Awaitable, Callable

from app.core.plugin_manager import HOOK_ON_SHUTDOWN, HOOK_ON_STARTUP
from app.db.session import AsyncSessionLocal
from app.services.plugin_runtime_config_helper import load_plugin_runtime_config



ConfigHook = Callable[[dict[str, Any]], Awaitable[None]]


def register_config_plugin(
    pm: Any,
    *,
    plugin_id: str,
    on_config: ConfigHook,
    enabled_key: str = "enabled",
):
    """
    配置型/界面型插件通用模板：
    - 不强制注册流事件
    - 在需要配置时由 on_config 调用者完成：示例里在启动时尝试加载一次
    """
    meta = pm.metadata.get(plugin_id, {}) or {}
    cfg = meta.get("config_template") or {}
    enabled_default = bool(cfg.get(enabled_key, True))

    async def _load_and_fire() -> None:
        # OSS/主系统里 tenant 通常由当前登录用户决定；这里示例走 default tenant
        tenant_id = "default"
        base_config = cfg if isinstance(cfg, dict) else {}
        async with AsyncSessionLocal() as db:
            effective = await load_plugin_runtime_config(
                db,
                plugin_id=plugin_id,
                tenant_id=tenant_id,
                base_config=base_config,
            )
        enabled = effective.get(enabled_key, enabled_default)
        if not bool(enabled):
            return
        await on_config(effective)

    task_holder: dict[str, Any] = {"task": None}

    async def on_startup() -> None:
        # 只跑一次初始化；真正使用时建议由具体 API/页面逻辑触发加载
        task_holder["task"] = pm and _load_and_fire()
        # 不直接 create_task：避免 hook 返回非协程导致时序问题，这里直接 await
        await task_holder["task"]

    async def on_shutdown() -> None:
        # 当前模板没有常驻任务；保留接口以便扩展
        with contextlib.suppress(Exception):
            t = task_holder.get("task")
            if hasattr(t, "cancel"):
                t.cancel()

    pm.register_hook(HOOK_ON_STARTUP, on_startup)
    pm.register_hook(HOOK_ON_SHUTDOWN, on_shutdown)

