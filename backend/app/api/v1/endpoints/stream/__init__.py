# FIX: [2026-07-03] stream/ 包缺少 __init__.py，导致 api.py 中 _mount(stream, ...) 找不到
#      router 属性，实时预览全部 API 返回 404。根因：包拆分时遗漏了 __init__.py。
#      修复：创建 __init__.py，导出 stream_play 的路由和 _shared 中的公共函数。 [全栈工程师]
"""实时预览端点包 — 导出播放/停止路由及共享函数。"""

from fastapi import APIRouter

from .stream_play import router as play_router
from ._shared import (
    logger,
    _PlayIdempotencyGuard,
    _stream_audit,
    _record_play_trace,
    _read_play_trace,
    _record_play_failure,
    _normalize_signal_proto,
    _media_mode_label,
    _build_signal_targets,
    _build_live_session_stream_key,
    _build_stream_match_hints,
    _wait_zlm_stream_ready,
    _probe_stream_across_nodes,
    _probe_zlm_stream,
    _record_runtime_play_health,
    _resolve_media_mode_candidates,
    _get_gb28181_play_config,
    _ssrc_policy_chain,
    _INVITE_ENDPOINT_HINTS,
    _PLAY_STATUS_RECENT_FAILURE,
    _do_warmup_flv,
    _get_max_concurrent_streams,
    _release_stream_session,
    list_streams,
    cleanup_stream_traces,
)
from ._response import (
    _build_full_play_response,
    _map_play_stream_error,
    _play_http_exception,
)

# 合并路由
router = APIRouter()
router.include_router(play_router)

__all__ = [
    "router",
    "list_streams",
    "_PlayIdempotencyGuard",
    "_stream_audit",
    "_record_play_trace",
    "_read_play_trace",
    "_record_play_failure",
    "_normalize_signal_proto",
    "_media_mode_label",
    "_build_signal_targets",
    "_build_live_session_stream_key",
    "_build_stream_match_hints",
    "_wait_zlm_stream_ready",
    "_probe_stream_across_nodes",
    "_probe_zlm_stream",
    "_record_runtime_play_health",
    "_resolve_media_mode_candidates",
    "_get_gb28181_play_config",
    "_ssrc_policy_chain",
    "_INVITE_ENDPOINT_HINTS",
    "_PLAY_STATUS_RECENT_FAILURE",
    "_do_warmup_flv",
    "_get_max_concurrent_streams",
    "_release_stream_session",
    "cleanup_stream_traces",
    "_build_full_play_response",
    "_map_play_stream_error",
    "_play_http_exception",
    "logger",
]
