from __future__ import annotations

import asyncio
from loguru import logger
from typing import Any, Awaitable, Callable

from app.core.plugin_manager import HOOK_ON_SHUTDOWN, HOOK_ON_ZLM_STREAM_REG
from app.services.main_path_plugin_controller import MainPathPluginController, StreamPolicy, StartMode



AnalysisHandler = Callable[[Any, asyncio.Event], Awaitable[None]]


def register_main_path_plugin(
    pm: Any,
    *,
    plugin_id: str,
    analysis_handler: AnalysisHandler,
    # 默认值仅在运行时配置缺失时生效
    default_stream_policy: StreamPolicy = "both",
    default_start_mode: StartMode = "fallback_start",
    default_dedup_by_ssrc: bool = True,
    default_stop_preempted_stream: bool = True,
    enabled_key: str = "enabled",
) -> MainPathPluginController:
    """
    插件作者最小接入：只要提供 plugin_id + analysis_handler
    控制器会自动：
    - 注册 ON_ZLM_STREAM_REG
    - 注册 HOOK_ON_SHUTDOWN 取消任务
    - 读取运行时 plugin_runtime_config 覆盖 enabled/stream_policy/start_mode/stop_preempted_stream/dedup_by_ssrc
    """
    meta = pm.metadata.get(plugin_id, {}) or {}
    cfg = meta.get("config_template") or {}
    enabled_default = bool(cfg.get(enabled_key, True))
    stream_policy = cfg.get("stream_policy", default_stream_policy) or default_stream_policy
    start_mode = cfg.get("start_mode", default_start_mode) or default_start_mode
    dedup_by_ssrc = bool(cfg.get("dedup_by_ssrc", default_dedup_by_ssrc))
    stop_preempted_stream = bool(cfg.get("stop_preempted_stream", default_stop_preempted_stream))

    controller = MainPathPluginController(
        plugin_id=plugin_id,
        enabled_default=enabled_default,
        enabled_key=enabled_key,
        debug_default=bool(cfg.get("debug", False)),
        stream_policy=stream_policy,
        start_mode=start_mode,
        dedup_by_ssrc=dedup_by_ssrc,
        stop_preempted_stream=stop_preempted_stream,
        operator="plugin",
        analysis_handler=analysis_handler,
    )
    pm.register_hook(HOOK_ON_ZLM_STREAM_REG, controller.handle_event)
    pm.register_hook(HOOK_ON_SHUTDOWN, controller.shutdown)
    logger.info(
        "[PluginTemplate] Registered main-path plugin_id=%s stream_policy=%s start_mode=%s dedup_by_ssrc=%s stop_preempted_stream=%s enabled_default=%s",
        plugin_id,
        stream_policy,
        start_mode,
        dedup_by_ssrc,
        stop_preempted_stream,
        enabled_default,
    )
    return controller

