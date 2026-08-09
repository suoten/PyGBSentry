"""stream 子模块聚合：将所有子模块 router 合并为统一的 router 导出，并重新导出被外部引用的名称。"""

from fastapi import APIRouter

from .stream_play import router as play_router
from .stream_control import router as control_router
from .stream_query import router as query_router
from .stream_proxy import router as proxy_router

router = APIRouter()

router.include_router(play_router)
router.include_router(control_router)
router.include_router(query_router)
router.include_router(proxy_router)

# ---- 重新导出被外部模块引用的名称（保持向后兼容） ----

# 从 stream_play 重新导出
from .stream_play import (
    StopStreamRequest,
    play_stream,
    stop_stream,
    get_play_status,
    get_play_diagnostics,
    stream_error_catalog,
    switch_stream_type,
    _async_invite_wait_with_retry,
)

# 从 stream_control 重新导出
from .stream_control import (
    PlaybackControlRequest,
    PlaybackSeekRequest,
    PlaybackSpeedRequest,
    playback_stream,
    download_stream,
    control_playback_stream,
    playback_pause,
    playback_resume,
    playback_seek,
    playback_speed,
)

# 从 stream_query 重新导出
from .stream_query import (
    list_streams,
    get_webrtc_url,
)

# 从 stream_proxy 重新导出
from .stream_proxy import (
    BroadcastStartRequest,
    BroadcastStopRequest,
    get_push_token,
    broadcast_start,
    broadcast_stop,
    talk_start,
    talk_stop,
)

# 从 _shared 重新导出（被 device_record / response_handler / channel.py 等引用）
from ._shared import (
    _probe_zlm_stream,
    _build_stream_match_hints,
    _collect_probe_nodes,
    _probe_stream_across_nodes,
    _release_stream_session,
    _close_zlm_stream,
    _PlayIdempotencyGuard,
)

# FIX [2026-07-19]: 从 _response 重新导出 _build_full_play_response 和 _map_play_stream_error，
# 供测试模块（test_stream_play_alignment.py）和外部调用方使用。
from ._response import (
    _build_full_play_response,
    _map_play_stream_error,
)
