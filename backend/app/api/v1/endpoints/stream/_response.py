# FIX: [2026-07-03] stream_play.py 从 ._response 导入 3 个符号，但 _response.py 文件
#      在包拆分时遗漏创建，导致 stream_play.py 无法导入、实时预览全部 API 返回 404。
#      根因：refactoring 时遗漏了响应构建模块的创建。修复：按使用方式重建 _response.py。 [全栈工程师]
"""实时预览端点响应构建工具。

由 stream_play.py 使用。
"""
from __future__ import annotations

from typing import Any
from fastapi import HTTPException

from app.core.config import settings


def _play_http_exception(
    status_code: int,
    reason_code: str,
    message: str,
    suggestion: str = "",
    *,
    retryable: bool = False,
    diagnostics: dict[str, Any] | None = None,
) -> HTTPException:
    """构建结构化的播放 HTTP 异常。"""
    error_code = f"GB_STREAM_{reason_code.upper()}"
    detail: dict[str, Any] = {
        "error_code": error_code,
        "reason_code": reason_code,
        "message": message,
        "retryable": retryable,
    }
    if suggestion:
        detail["suggestion"] = suggestion
    if diagnostics:
        detail["diagnostics"] = diagnostics
    return HTTPException(status_code=status_code, detail=detail)


def _map_play_stream_error(
    exc: Exception,
    *,
    device_id: str = "",
    channel_id: str = "",
) -> HTTPException:
    """将底层异常映射为用户友好的 HTTP 异常。"""
    exc_str = str(exc)[:500]
    if "port" in exc_str.lower() and "exhaust" in exc_str.lower():
        return _play_http_exception(
            503,
            "media_port_exhausted",
            "Media node RTP port exhausted",
            "Please scale up media node RTP port pool or release occupied sessions",
            retryable=True,
        )
    if "timeout" in exc_str.lower():
        return _play_http_exception(
            504,
            "stream_not_ready",
            "Stream not ready (timeout)",
            "Please verify the device is streaming and retry",
            retryable=True,
        )
    return _play_http_exception(
        502,
        "play_request_failed",
        "Stream invite request failed",
        f"Detail: {exc_str}",
        retryable=True,
    )


async def _build_full_play_response(
    *,
    db: Any = None,
    app_name: str,
    stream_id: str,
    stream_type: str,
    selected_node: Any,
    media_host: str,
    media_port: int,
    node_host: str,
    node_http_port: int,
    is_embedded_node: bool,
    zlm_probe_ok: bool,
    zlm_stream_ready: bool,
    media_item: dict[str, Any],
    result: dict[str, Any],
    resource: Any = None,
    node_id: str | None = None,
    sla_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构建完整的播放响应（包含 flv/ws/hls/rtsp 播放地址）。

    FIX: [2026-07-03] 三重缺陷修复：
    (a) 原为 `def`（同步），但 stream_play.py:582/1186 以 `await` 调用 → TypeError；改为 async。
    (b) 原无 sla_metrics 形参，但 stream_play.py:1203 传 sla_metrics= → TypeError；补齐形参。
    (c) 原返回 JSONResponse，但 stream_play.py:600-601 以 res["data"]["status"]=... 当 dict 访问/赋值
        → TypeError；改为返回可变 dict（FastAPI 会自动序列化 dict 返回值为 JSON）。[全栈工程师]
    """
    # 构建播放 URL
    base_http = f"http://{media_host}:{media_port}"
    base_ws = f"ws://{media_host}:{media_port}"
    base_rtsp = f"rtsp://{media_host}:{settings.STREAM_PUBLIC_RTSP_PORT or 554}"

    # 从 media_item 中提取实际 app/stream（可能被 ZLM 重定向到 rtp app）
    url_app = str((media_item or {}).get("matched_app") or app_name or "live")
    url_stream = str((media_item or {}).get("matched_stream") or stream_id or "")

    ssrc = str((result or {}).get("ssrc") or "")
    call_id = str((result or {}).get("call_id") or "")

    data: dict[str, Any] = {
        "status": "ready" if zlm_stream_ready else "waiting",
        "session_id": str((result or {}).get("stream_session_id") or ""),
        "call_id": call_id,
        "ssrc": ssrc,
        "app": url_app,
        "stream": url_stream,
        "node_id": str(node_id or ""),
        "media_protocol": str((result or {}).get("media_protocol") or ""),
        "media_ip": str((result or {}).get("sdp_ip") or ""),
        "media_port": int((result or {}).get("media_port") or 0),
        "flv": f"{base_http}/{url_app}/{url_stream}.flv",
        "ws": f"{base_ws}/{url_app}/{url_stream}.flv",
        "hls": f"{base_http}/{url_app}/{url_stream}/hls.m3u8",
        "rtsp": f"{base_rtsp}/{url_app}/{url_stream}",
        # FIX: [2026-07-04] WebRTC 地址条件构建 [全栈工程师]
        # 根因：原代码无条件构造 webrtc URL，但 ZLM 未启用 [rtc] 段时 WebRTC 不可用，
        # 前端拿到无效 URL 后播放失败。修复：仅在 ZLM_WRITE_RTC_SECTION=True 时返回 URL。
        "webrtc": (
            f"{base_http}/index/api/webrtc?app={url_app}&stream={url_stream}&type=play"
            if getattr(settings, "ZLM_WRITE_RTC_SECTION", False)
            else ""
        ),
        "webrtc_enabled": getattr(settings, "ZLM_WRITE_RTC_SECTION", False),
        "zlm_probe_ok": zlm_probe_ok,
        "zlm_stream_ready": zlm_stream_ready,
    }

    if resource:
        data["channel_id"] = str(getattr(resource, "gb_id", "") or "")
        data["channel_name"] = str(getattr(resource, "name", "") or "")

    # FIX: [2026-07-04] 返回 codec 字段供前端选择播放器（H.265 需用专用播放器）[全栈工程师]
    # 根因：_build_full_play_response 未返回 codec 字段，直播预览响应缺少编码信息，
    # 前端默认用 H.264 播放器播放 H.265 流导致黑屏。
    # 修复：从 media_item 提取 codec 并返回，前端据此选择 Jessibuca(H.264) 或 h265web(H.265)。
    _codec = str((media_item or {}).get("codec") or "").lower()
    data["codec"] = _codec
    data["is_h265"] = _codec in ("h265", "hevc", "h.265")

    if sla_metrics:
        data["sla"] = sla_metrics

    return {
        "code": 200,
        "msg": "ok",
        "data": data,
    }
