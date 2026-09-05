"""stream 子模块共享的响应构建函数（URL 生成、错误封装、播放结果组装）。"""

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger
from app.core.config import settings
from app.models.asset import Asset
from app.models.resource import Resource
from app.models.asset_stream_health import AssetStreamHealth
from app.models.asset_stream_policy import AssetStreamPolicy
from app.services.zlm_rtp_server_service import ZlmApiError

import asyncio
from ._shared import (
    _safe_int,
    _node_value,
    _first_non_empty,
    _build_media_url,
    _append_token,
    _stream_play_token,
    _get_play_token_ttl,
    _probe_webrtc_capability,
    _load_bootstrap_runtime_config,
    _infer_bootstrap_transport_mode,
    _resolve_learning_rate_map,
    _should_promote_policy_to_auto,
    _probe_zlm_hls_ready,
    _validate_play_urls,
)


def _build_play_urls(
    app_name: str,
    stream_id: str,
    media_host: str | None,
    http_port: int | None,
    https_port: int | None,
    rtmp_port: int | None,
    rtmps_port: int | None,
    rtsp_port: int | None,
    rtsps_port: int | None,
    token: str,
    vhost: str = "__defaultVhost__",
) -> dict:
    # 流后缀：GB28181/RTP 推流流名没有 .live 后缀，其他 app 的流有
    _stream_suffix = "" if (app_name == "rtp" or stream_id.endswith(".live") or stream_id.endswith(".mp4") or stream_id.endswith(".ts")) else ".live"
    # 避免流名末尾已有 .live/.mp4/.ts 时再追加导致重复（如 xxx.live.live）
    _base_stream = stream_id
    for _suf in (".live", ".mp4", ".ts"):
        if _base_stream.endswith(_suf):
            _base_stream = _base_stream[:-len(_suf)]
            break

    # 处理虚拟主机路径
    def _media_path(path: str) -> str:
        # __defaultVhost__ 不加路径前缀，ZLM 会自动处理
        if vhost and vhost != "__defaultVhost__":
            return f"/{vhost}{path}"
        return path

    http_flv = _build_media_url("http", media_host, http_port, _media_path(f"/{app_name}/{_base_stream}{_stream_suffix}.flv"))
    https_flv = _build_media_url("https", media_host, https_port, _media_path(f"/{app_name}/{_base_stream}{_stream_suffix}.flv"))
    ws_flv = _build_media_url("ws", media_host, http_port, _media_path(f"/{app_name}/{_base_stream}{_stream_suffix}.flv"))
    wss_flv = _build_media_url("wss", media_host, https_port, _media_path(f"/{app_name}/{_base_stream}{_stream_suffix}.flv"))
    http_fmp4 = _build_media_url("http", media_host, http_port, _media_path(f"/{app_name}/{_base_stream}{_stream_suffix}.mp4"))
    https_fmp4 = _build_media_url("https", media_host, https_port, _media_path(f"/{app_name}/{_base_stream}{_stream_suffix}.mp4"))
    ws_fmp4 = _build_media_url("ws", media_host, http_port, _media_path(f"/{app_name}/{_base_stream}{_stream_suffix}.mp4"))
    wss_fmp4 = _build_media_url("wss", media_host, https_port, _media_path(f"/{app_name}/{_base_stream}{_stream_suffix}.mp4"))
    # WebRTC WHEP 接口：vhost 参数只在非默认时添加
    _whep_vhost_param = f"&vhost={vhost}" if vhost and vhost != "__defaultVhost__" else ""
    rtc_url = f"/index/api/whep?app={app_name}&stream={stream_id}{_whep_vhost_param}"
    rtc = _build_media_url("http", media_host, http_port, rtc_url)
    rtcs = _build_media_url("https", media_host, https_port, rtc_url)

    urls = {
        "hls": _build_media_url("http", media_host, http_port, _media_path(f"/{app_name}/{_base_stream}{_stream_suffix}/hls.m3u8")),
        "https_hls": _build_media_url("https", media_host, https_port, _media_path(f"/{app_name}/{_base_stream}{_stream_suffix}/hls.m3u8")),
        "ws_hls": _build_media_url("ws", media_host, http_port, _media_path(f"/{app_name}/{_base_stream}{_stream_suffix}/hls.m3u8")),
        "wss_hls": _build_media_url("wss", media_host, https_port, _media_path(f"/{app_name}/{_base_stream}{_stream_suffix}/hls.m3u8")),
        "ts": _build_media_url("http", media_host, http_port, _media_path(f"/{app_name}/{_base_stream}{_stream_suffix}.ts")),
        "https_ts": _build_media_url("https", media_host, https_port, _media_path(f"/{app_name}/{_base_stream}{_stream_suffix}.ts")),
        "ws_ts": _build_media_url("ws", media_host, http_port, _media_path(f"/{app_name}/{_base_stream}{_stream_suffix}.ts")),
        "wss_ts": _build_media_url("wss", media_host, https_port, _media_path(f"/{app_name}/{_base_stream}{_stream_suffix}.ts")),
        "rtmp": _build_media_url("rtmp", media_host, rtmp_port, _media_path(f"/{app_name}/{stream_id}")),
        "rtmps": _build_media_url("rtmps", media_host, rtmps_port, _media_path(f"/{app_name}/{stream_id}")),
        "rtsp": _build_media_url("rtsp", media_host, rtsp_port, _media_path(f"/{app_name}/{stream_id}")),
        "rtsps": _build_media_url("rtsps", media_host, rtsps_port, _media_path(f"/{app_name}/{stream_id}")),
        "rtc": rtc,
        "rtcs": rtcs,
    }
    # 添加 flv/fmp4/ts 到 urls 字典
    urls["flv"] = http_flv
    urls["https_flv"] = https_flv
    urls["ws_flv"] = ws_flv
    urls["wss_flv"] = wss_flv
    urls["fmp4"] = http_fmp4
    urls["https_fmp4"] = https_fmp4
    urls["ws_fmp4"] = ws_fmp4
    urls["wss_fmp4"] = wss_fmp4
    # FIX [2026-09-04 P1]: HTTPS 站点适配 —— 对外访问协议为 https 时，主地址族
    # （flv/hls/fmp4/ts/ws_*）升级为对应的安全变体（https/wss，端口取 https_port）。
    # 原实现主地址恒为 http://，而 nginx 只在 443(HTTPS) 对外提供流媒体时，
    # 会生成 http://host:443 这种 plain-HTTP 打 TLS 端口的必然失败地址，
    # 前端选中即黑屏/被混合内容拦截。
    if str(settings.STREAM_PUBLIC_SCHEME or "").strip().lower() == "https":
        secure_map = {
            "flv": "https_flv",
            "fmp4": "https_fmp4",
            "ts": "https_ts",
            "hls": "https_hls",
            "ws_flv": "wss_flv",
            "ws_fmp4": "wss_fmp4",
            "ws_ts": "wss_ts",
            "ws_hls": "wss_hls",
            "rtc": "rtcs",
        }
        for plain_key, secure_key in secure_map.items():
            if urls.get(secure_key):
                urls[plain_key] = urls[secure_key]
    for key in (
        "flv",
        "https_flv",
        "ws_flv",
        "wss_flv",
        "fmp4",
        "https_fmp4",
        "ws_fmp4",
        "wss_fmp4",
        "hls",
        "https_hls",
        "ws_hls",
        "wss_hls",
        "ts",
        "https_ts",
        "ws_ts",
        "wss_ts",
        "rtc",
        "rtcs",
    ):
        if urls[key]:
            urls[key] = _append_token(urls[key], token)
    return urls


def _effective_https_port(selected_node) -> int:
    """计算 HTTPS 族播放地址端口。

    FIX [2026-09-03 P1]: HTTPS 站点（STREAM_PUBLIC_SCHEME=https）未显式配置
    MEDIA_SERVER_HTTPS_PORT / 节点 https_port 时，端口为 0 导致 https 族地址
    全部为 null，HTTPS 页面只剩会被混合内容拦截的 http 地址（实时预览黑屏）。
    此时自动沿用 STREAM_PUBLIC_HTTP_PORT（nginx 443 反代场景的标准配置）。
    """
    https_port = _safe_int(
        _node_value(selected_node, "https_port"),
        _safe_int(settings.MEDIA_SERVER_HTTPS_PORT, 0),
    )
    if https_port <= 0 and str(settings.STREAM_PUBLIC_SCHEME or "").strip().lower() == "https":
        https_port = _safe_int(settings.STREAM_PUBLIC_HTTP_PORT, 443)
    return https_port


def _build_media_server_payload(selected_node, media_host: str | None, http_port: int | None, zlm_probe_ok: bool) -> dict:
    public_host = _first_non_empty(
        media_host,
        _node_value(selected_node, "public_host"),
        _node_value(selected_node, "stream_ip"),
        settings.STREAM_PUBLIC_HOST,
        settings.MEDIA_SERVER_HOST,
    )
    https_port = _effective_https_port(selected_node)
    rtmp_port = _safe_int(
        _node_value(selected_node, "rtmp_port"),
        _safe_int(settings.MEDIA_SERVER_RTMP_PORT, 0),
    )
    rtmps_port = _safe_int(
        _node_value(selected_node, "rtmps_port"),
        _safe_int(settings.MEDIA_SERVER_RTMPS_PORT, 0),
    )
    rtsp_port = _safe_int(
        _node_value(selected_node, "rtsp_port"),
        _safe_int(settings.MEDIA_SERVER_RTSP_PORT, 0),
    )
    rtsps_port = _safe_int(
        _node_value(selected_node, "rtsps_port"),
        _safe_int(settings.MEDIA_SERVER_RTSPS_PORT, 0),
    )
    public_http_port = _safe_int(http_port, 0)
    return {
        "id": str(_node_value(selected_node, "id") or ""),
        "ip": _first_non_empty(_node_value(selected_node, "host"), _node_value(selected_node, "ip")),
        "hookIp": _first_non_empty(_node_value(selected_node, "hook_ip"), _node_value(selected_node, "hookIp")),
        "sdpIp": _first_non_empty(_node_value(selected_node, "sdp_ip"), _node_value(selected_node, "sdpIp")),
        "streamIp": public_host,
        "httpPort": public_http_port or None,
        "httpSSlPort": https_port or None,
        "rtmpPort": rtmp_port or None,
        "flvPort": public_http_port or None,
        "flvSSLPort": (https_port or public_http_port) or None,
        "wsFlvPort": public_http_port or None,
        "wsFlvSSLPort": (https_port or public_http_port) or None,
        "rtmpSSlPort": rtmps_port or None,
        "rtpProxyPort": _safe_int(_node_value(selected_node, "rtp_port"), _safe_int(settings.MEDIA_SERVER_RTP_PROXY_PORT, 0)) or None,
        "rtspPort": rtsp_port or None,
        "rtspSSLPort": rtsps_port or None,
        "autoConfig": bool(_node_value(selected_node, "auto_config_enabled") or _node_value(selected_node, "autoConfig")),
        "secret": "***" if _node_value(selected_node, "secret") else "",
        "hookAliveInterval": None,
        "rtpEnable": True,
        "status": bool(zlm_probe_ok),
        "rtpPortRange": str(
            _node_value(selected_node, "rtp_port_range")
            or settings.MEDIA_SERVER_RTP_PROXY_PORT_RANGE
            or ""
        ) or None,
        "sendRtpPortRange": None,
        "recordAssistPort": _safe_int(_node_value(selected_node, "record_mgr_port"), 0) or None,
        "createTime": None,
        "updateTime": None,
        "lastKeepaliveTime": None,
        "defaultServer": False,
        "recordDay": 0,
        "recordPath": None,
        "type": "zlm",
        "transcodeSuffix": None,
    }


def _resolve_codec(resource: Resource) -> str:
    capabilities = resource.capabilities or {}
    codec = str(
        capabilities.get("video_codec")
        or capabilities.get("codec")
        or capabilities.get("encode")
        or "h264"
    ).lower()
    if codec in {"h265", "hevc"}:
        return "h265"
    return "h264"


def _build_media_info_payload(
    app_name: str,
    stream_id: str,
    selected_node,
    media_server_payload: dict,
    media_item: dict | None,
    result: dict,
    resource: Resource,
    zlm_stream_ready: bool,
) -> dict:
    capabilities = resource.capabilities or {}
    width = _safe_int((media_item or {}).get("width") or capabilities.get("width"), 0) or None
    height = _safe_int((media_item or {}).get("height") or capabilities.get("height"), 0) or None
    reader_count = _safe_int((media_item or {}).get("readerCount"), 0)
    video_codec = str(
        (media_item or {}).get("videoCodec")
        or (media_item or {}).get("vcodec")
        or capabilities.get("video_codec")
        or capabilities.get("codec")
        or capabilities.get("encode")
        or _resolve_codec(resource)
        or ""
    ).upper() or None
    audio_codec = str((media_item or {}).get("audioCodec") or (media_item or {}).get("acodec") or "").upper() or None
    return {
        "app": app_name,
        "stream": stream_id,
        "mediaServer": media_server_payload,
        "schema": str((media_item or {}).get("schema") or "rtsp"),
        "readerCount": reader_count,
        "videoCodec": video_codec,
        "width": width,
        "height": height,
        "audioCodec": audio_codec,
        "audioChannels": _safe_int((media_item or {}).get("channels"), 0) or None,
        "audioSampleRate": _safe_int((media_item or {}).get("sampleRate") or (media_item or {}).get("sample_rate"), 0) or None,
        "duration": _safe_int((media_item or {}).get("duration"), 0) or None,
        "online": bool(zlm_stream_ready),
        "originType": (media_item or {}).get("originType", 3),
        "originUrl": (media_item or {}).get("originUrl") or f"rtp://{app_name}/{stream_id}",
        "aliveSecond": _safe_int((media_item or {}).get("aliveSecond"), 0),
        "bytesSpeed": _safe_int((media_item or {}).get("bytesSpeed"), 0),
        "callId": result.get("call_id"),
        "paramMap": {},
        "serverId": str(_node_value(selected_node, "server_id") or "000000"),
    }


def _pick_preferred_play_url(
    urls: dict,
    *,
    webrtc_supported: bool,
    media_schema: str | None = None,
    stream_id: str | None = None,
    url_availability: dict | None = None,
) -> str | None:
    schema = str(media_schema or "").strip().lower()
    # 判断是否是 RTP 流（GB28181 推流）
    is_rtp_stream = bool(stream_id and (str(stream_id).startswith("rtp") or schema == "rtp"))

    def _is_available(key: str) -> bool:
        """检查某个 URL key 是否真正可用（已在 ZLM 端点验证过）。"""
        avail = url_availability or {}
        val = avail.get(key)
        # None 表示不适用或未验证；True 表示已验证可用；False 表示已验证不可用
        return val is None or val is True

    def _score_key(key: str) -> int:
        """
        根据 URL 协议类型和可用性评分，返回 (availability_penalty, protocol_score)。
        availability_penalty: 不可用则 +10000（大幅降低优先级）
        protocol_score: 数值越小优先级越高
        """
        avail = url_availability or {}
        val = avail.get(key)
        unavail_penalty = 10000 if val is False else 0

        # HTTPS/WSS 安全协议优先
        if key in ("https_flv", "wss_flv"):
            return (unavail_penalty, 0)
        if key in ("https_fmp4", "wss_fmp4"):
            return (unavail_penalty, 1)
        if key in ("https_hls", "wss_hls"):
            return (unavail_penalty, 2)
        if key in ("https_ts", "wss_ts"):
            return (unavail_penalty, 3)
        # HTTP/WS 协议
        if key == "flv":
            return (unavail_penalty, 4)
        if key == "ws_flv":
            return (unavail_penalty, 5)
        if key in ("hls", "ws_hls"):
            return (unavail_penalty, 6)
        if key in ("fmp4", "ws_fmp4"):
            return (unavail_penalty, 7)
        if key in ("ts", "ws_ts"):
            return (unavail_penalty, 8)
        # WebRTC
        if key in ("rtcs", "rtc"):
            return (unavail_penalty, 9)
        # 其他协议（rtsp/rtmp 等）
        return (unavail_penalty, 100)

    if webrtc_supported and _is_available("rtc") or _is_available("rtcs"):
        rtc_order = ("rtcs", "rtc") if _is_available("rtcs") else ("rtc",)
    else:
        rtc_order = ()

    if is_rtp_stream:
        base_order = ("https_flv", "wss_flv", "flv", "ws_flv", "https_hls", "wss_hls", "hls", "ws_hls", "rtsp", "rtsps", "https_ts", "wss_ts", "ts", "ws_ts")
    elif schema == "hls":
        base_order = ("https_hls", "wss_hls", "hls", "ws_hls", "https_flv", "wss_flv", "flv", "ws_flv", "https_ts", "wss_ts", "ts", "ws_ts", "rtsp", "rtsps")
    elif schema == "ts":
        base_order = ("https_ts", "wss_ts", "ts", "ws_ts", "https_flv", "wss_flv", "flv", "ws_flv", "https_hls", "wss_hls", "hls", "ws_hls", "rtsp", "rtsps")
    elif schema == "rtsp":
        base_order = ("https_flv", "wss_flv", "flv", "ws_flv", "https_hls", "wss_hls", "hls", "ws_hls", "rtsp", "rtsps", "https_ts", "wss_ts", "ts", "ws_ts")
    else:
        base_order = ("https_flv", "wss_flv", "flv", "ws_flv", "https_hls", "wss_hls", "hls", "ws_hls", "https_ts", "wss_ts", "ts", "ws_ts", "rtsp", "rtsps")

    # 合并优先级列表，去重
    seen: set[str] = set()
    preferred_order: list[str] = []
    for key in rtc_order:
        if key not in seen and urls.get(key):
            seen.add(key)
            preferred_order.append(key)
    for key in base_order:
        if key not in seen and urls.get(key):
            seen.add(key)
            preferred_order.append(key)

    # 按可用性评分排序：优先选已验证可用的，其次按协议优先级
    ranked = sorted(
        [(key, _score_key(key)) for key in preferred_order if urls.get(key)],
        key=lambda kv: (kv[1][0], kv[1][1]),
    )

    for key, _ in ranked:
        value = urls.get(key)
        if value:
            return value
    return None


def _build_url_availability_summary(availability: dict | None) -> dict:
    """
    将 url_availability 详情转换为前端友好的摘要：
    - flv: 是否存在可用的 FLV 端点（ws/wss/http 任意一种）
    - hls: 是否存在可用的 HLS 端点
    - rtc: WebRTC 是否可用
    - rtsp: RTSP 端点（不验证，始终 None）
    """
    if not availability:
        return {"flv": None, "hls": None, "rtc": None, "rtsp": None}
    avail = availability
    flv_keys = {"flv", "https_flv", "ws_flv", "wss_flv"}
    hls_keys = {"hls", "https_hls", "ws_hls", "wss_hls"}
    rtc_keys = {"rtc", "rtcs"}
    return {
        "flv": any(avail.get(k) is True for k in flv_keys),
        "hls": any(avail.get(k) is True for k in hls_keys),
        "rtc": any(avail.get(k) is True for k in rtc_keys),
        "rtsp": None,
    }


def _collect_available_protocols(urls: dict) -> list[str]:
    pairs = (
        ("flv", "flv"),
        ("https_flv", "https_flv"),
        ("ws_flv", "ws_flv"),
        ("wss_flv", "wss_flv"),
        ("fmp4", "fmp4"),
        ("https_fmp4", "https_fmp4"),
        ("ws_fmp4", "ws_fmp4"),
        ("wss_fmp4", "wss_fmp4"),
        ("hls", "hls"),
        ("https_hls", "https_hls"),
        ("ws_hls", "ws_hls"),
        ("wss_hls", "wss_hls"),
        ("ts", "ts"),
        ("https_ts", "https_ts"),
        ("ws_ts", "ws_ts"),
        ("wss_ts", "wss_ts"),
        ("rtmp", "rtmp"),
        ("rtmps", "rtmps"),
        ("rtsp", "rtsp"),
        ("rtsps", "rtsps"),
        ("rtc", "rtc"),
        ("rtcs", "rtcs"),
    )
    return [label for key, label in pairs if urls.get(key)]


def _play_error_detail(
    status_code: int,
    reason_code: str,
    message: str,
    suggestion: str,
    *,
    retryable: bool,
    diagnostics: dict | None = None,
) -> dict:
    normalized_reason = str(reason_code or "play_error").strip().lower().replace(" ", "_").replace("-", "_")
    error_code = f"GB_STREAM_{normalized_reason.upper()}"
    return {
        "detail": message,
        "message": message,
        "reason_code": reason_code,
        "error_code": error_code,
        "suggestion": suggestion,
        "retryable": bool(retryable),
        "error": {
            "domain": "stream",
            "version": "2026-04",
            "code": error_code,
            "reason": normalized_reason,
            "http_status": int(status_code or 0),
        },
        "diagnostics": diagnostics or {},
    }


def _play_http_exception(
    status_code: int,
    reason_code: str,
    message: str,
    suggestion: str,
    *,
    retryable: bool,
    diagnostics: dict | None = None,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=_play_error_detail(
            status_code,
            reason_code,
            message,
            suggestion,
            retryable=retryable,
            diagnostics=diagnostics,
        ),
    )


def _build_play_success_response(
    *,
    app_name: str,
    stream_id: str,
    token: str,
    urls: dict,
    codec: str,
    media_server_id: str | None,
    media_info: dict,
    result: dict,
    zlm_probe_ok: bool,
    zlm_stream_ready: bool,
    webrtc_supported: bool,
    webrtc_hint: str,
    stream_type: str,
    auto_heal_profile: dict | None = None,
    sla_metrics: dict | None = None,
    url_availability: dict | None = None,
    hls_probe_detail: dict | None = None,
) -> dict:
    preferred_url = _pick_preferred_play_url(
        urls,
        webrtc_supported=webrtc_supported,
        media_schema=str((media_info or {}).get("schema") or ""),
        stream_id=str(app_name) + "/" + str(stream_id),
        url_availability=url_availability,
    )
    available_protocols = _collect_available_protocols(urls)
    # P1-fix [2026-07-17]: STUN_SERVER 为空时生成无效 ICE 服务器（stun: 无 host），
    # 导致浏览器 ICE 候选收集失败。仅在 STUN_SERVER 非空时才添加 STUN 条目。
    turn_servers = []
    _stun_server = str(settings.STUN_SERVER or '').strip()
    if _stun_server:
        turn_servers.append({"urls": [f"stun:{_stun_server}"]})
    if settings.TURN_SERVER:
        turn_username = settings.TURN_USERNAME
        turn_password = settings.TURN_PASSWORD
        if turn_username and turn_password:
            turn_servers.append({
                "urls": [f"turn:{settings.TURN_SERVER}"],
                "username": turn_username,
                "credential": turn_password
            })
        else:
            logger.warning("TURN_SERVER is configured but TURN_USERNAME/TURN_PASSWORD are not set; skipping TURN entry")  # 移除默认凭证admin/admin123，未配置时不返回TURN

    data = {
        "app": app_name,
        "stream": stream_id,
        "ip": None,
        **urls,
        "preferredUrl": preferred_url,
        "availableProtocols": available_protocols,
        "streamType": stream_type,
        "mediaServerId": media_server_id,
        "mediaInfo": media_info,
        "supports": {
            "webrtc": bool(webrtc_supported),
            "seek": True,
            "secureTransport": bool(urls.get("rtcs") or urls.get("https_flv") or urls.get("https_hls") or urls.get("rtsps") or urls.get("rtmps")),
        },
        "diagnostics": {
            "probeOk": bool(zlm_probe_ok),
            "streamReady": bool(zlm_stream_ready),
            "webrtcSupported": bool(webrtc_supported),
            "webrtcHint": webrtc_hint,
            "selectionReason": result.get("selection_reason"),
            "mediaPort": result.get("media_port"),
            "mediaProtocol": result.get("media_protocol"),
            "sdpIp": result.get("sdp_ip"),
            "ssrcPolicy": result.get("ssrc_policy"),
            "zlmSsrcCheck": result.get("zlm_ssrc_check"),
            "autoHealProfile": auto_heal_profile or {},
            "sla": sla_metrics or {},
        },
        "iceServers": turn_servers,
        "startTime": None,
        "endTime": None,
        "downLoadFilePath": None,
        "transcodeStream": None,
        "progress": 0.0,
        # URL 端点可用性验证结果：true=已验证可用，false=已验证不可用，null=不适用/未验证
        "urlAvailability": _build_url_availability_summary(url_availability),
        # HLS 探测详细结果
        "hlsProbeDetail": dict(hls_probe_detail or {}),
    }
    return {
        "code": 0,
        "msg": "Success",  # i18n
        "data": data,
        "app": app_name,
        "stream": stream_id,
        "codec": codec,
        "token": token,
        "flv": urls.get("flv"),
        "hls": urls.get("hls"),
        "webrtc": (urls.get("rtcs") or urls.get("rtc")) if webrtc_supported else None,
        "ice_servers": turn_servers,
        "preferred_url": preferred_url,
        "available_protocols": available_protocols,
        "stream_type": stream_type,
        "webrtc_supported": bool(webrtc_supported),
        "webrtc_hint": webrtc_hint,
        "seek_supported": True,
        "zlm_probe_ok": bool(zlm_probe_ok),
        "zlm_stream_ready": bool(zlm_stream_ready),
        "invite_sdp_ip": result.get("sdp_ip"),
        "invite_media_port": result.get("media_port"),
        "invite_media_protocol": result.get("media_protocol"),
        "invite_selection_reason": result.get("selection_reason"),
        "rtp_port_range": str(settings.MEDIA_SERVER_RTP_PROXY_PORT_RANGE or ""),
        "mediaServerId": media_server_id,
        "mediaInfo": media_info,
        "auto_heal_profile": auto_heal_profile or {},
        "sla": sla_metrics or {},
        # 新增：为不稳定流提供 HLS 备用链接
        "fallback_hls_url": urls.get("hls") or urls.get("https_hls") or urls.get("ws_hls") or urls.get("wss_hls"),
        # URL 端点可用性验证结果（按 key 分的详细状态）
        "urlAvailability": dict(url_availability or {}),
        "diagnostics": {
            "probeOk": bool(zlm_probe_ok),
            "streamReady": bool(zlm_stream_ready),
            "preferredProtocol": str(preferred_url.split("://")[0] if preferred_url else "unknown"),
            "schema": str((media_info or {}).get("schema") or "unknown"),
            "bytesSpeed": int((media_info or {}).get("bytesSpeed") or 0),
            "availableUrls": {
                "flv": bool(urls.get("flv")),
                "hls": bool(urls.get("hls")),
                "rtsp": bool(urls.get("rtsp")),
                "rtc": bool((urls.get("rtcs") or urls.get("rtc")) if webrtc_supported else False),
            },
            "urlAvailability": _build_url_availability_summary(url_availability),
            "hlsProbeDetail": dict(hls_probe_detail or {}),
        },
    }


async def _build_auto_heal_profile(
    db: AsyncSession,
    *,
    asset_id: str | None,
    media_info: dict | None,
    result: dict | None,
) -> dict:
    aid = str(asset_id or "").strip()
    asset = None
    if aid:
        asset = (await db.execute(select(Asset).where(Asset.id == aid))).scalars().first()
    runtime_cfg = await _load_bootstrap_runtime_config(db)
    bootstrap_mode, bootstrap_reason = _infer_bootstrap_transport_mode(asset, runtime_cfg.get("templates"))
    learning_map = _resolve_learning_rate_map(runtime_cfg.get("learning_state"), bootstrap_reason)
    schema = str((media_info or {}).get("schema") or "").strip().lower()
    is_live = schema in {"rtp", "live", ""} or not schema
    default_preferred_player = "flv" if is_live else "hls"
    default_profile = {
        "preferredPlayer": default_preferred_player,
        "preferStability": bool(schema in {"hls", "ts"}),
        "maxAutoHealAttempts": 2,
        "waitingHealMs": 14000,
        "recommendedTransport": str((result or {}).get("media_protocol") or "AUTO"),
        "currentPolicy": "AUTO" if bootstrap_mode == "AUTO" else bootstrap_mode,
        "canPromoteToAuto": False,
        "bootstrapTemplate": bootstrap_reason,
        "learningProfile": bootstrap_reason,
        "learningScore": learning_map,
        "failureRate": 0.0,
        "consecutiveFailures": 0,
    }
    if not aid:
        return default_profile
    health = (
        await db.execute(select(AssetStreamHealth).where(AssetStreamHealth.asset_id == aid))
    ).scalars().first()
    policy = (
        await db.execute(select(AssetStreamPolicy).where(AssetStreamPolicy.asset_id == aid))
    ).scalars().first()
    if not health:
        if policy and getattr(policy, "stream_mode", None):
            default_profile["recommendedTransport"] = str(getattr(policy, "stream_mode", "AUTO") or "AUTO")
            default_profile["currentPolicy"] = str(getattr(policy, "stream_mode", "AUTO") or "AUTO")
        return default_profile
    success_total = int(getattr(health, "success_total", 0) or 0)
    fail_total = int(getattr(health, "fail_total", 0) or 0)
    consecutive_failures = int(getattr(health, "consecutive_failures", 0) or 0)
    total = success_total + fail_total
    failure_rate = (float(fail_total) / float(total)) if total > 0 else 0.0
    prefer_stability = bool(schema in {"hls", "ts"} or failure_rate >= 0.25 or consecutive_failures >= 1)
    preferred_player = "hls" if prefer_stability else "flv"
    max_auto_heal_attempts = 3 if (failure_rate >= 0.35 or consecutive_failures >= 2) else 2
    waiting_heal_ms = 10000 if (failure_rate >= 0.35 or consecutive_failures >= 2) else 14000
    recommended_transport = str((result or {}).get("media_protocol") or "").strip() or "AUTO"
    current_policy = "AUTO"
    if policy and getattr(policy, "stream_mode", None):
        recommended_transport = str(getattr(policy, "stream_mode") or recommended_transport)
        current_policy = str(getattr(policy, "stream_mode") or "AUTO")
    can_promote_to_auto = _should_promote_policy_to_auto(
        success_total=success_total,
        fail_total=fail_total,
        consecutive_failures=consecutive_failures,
        auto_switch_count=int(getattr(health, "auto_switch_count", 0) or 0),
    )
    return {
        "preferredPlayer": preferred_player,
        "preferStability": prefer_stability,
        "maxAutoHealAttempts": max_auto_heal_attempts,
        "waitingHealMs": waiting_heal_ms,
        "recommendedTransport": recommended_transport,
        "currentPolicy": current_policy,
        "canPromoteToAuto": bool(can_promote_to_auto),
        "bootstrapTemplate": bootstrap_reason,
        "learningProfile": bootstrap_reason,
        "learningScore": learning_map,
        "failureRate": round(float(failure_rate), 4),
        "consecutiveFailures": consecutive_failures,
    }


def _map_play_stream_error(exc: Exception) -> HTTPException:
    from loguru import logger as _logger
    message = str(exc or "").strip() or "Play request failed"
    lower_message = message.lower()
    _logger.warning(f"Stream play error: {message}")
    if isinstance(exc, ZlmApiError):
        return _play_http_exception(
            int(getattr(exc, "status_code", 503) or 503),
            str(getattr(exc, "category", "media_service_error") or "media_service_error"),
            str(getattr(exc, "user_message", "Media service error") or "Media service error"),
            "Check media node status, port config and runtime logs",
            retryable=bool(getattr(exc, "retryable", True)),
            diagnostics={"operation": getattr(exc, "operation", "")},
        )
    if "empty_secret" in lower_message:
        return _play_http_exception(
            502,
            "media_secret_invalid",
            "Media node auth secret missing",
            "Check media node secret configuration",
            retryable=False,
        )
    if "no media node is ready" in lower_message:
        return _play_http_exception(
            503,
            "media_node_unavailable",
            "No available media node to receive stream",
            "Check media node online status, port range and network connectivity",
            retryable=True,
        )
    if "all connection attempts failed" in lower_message or "connection refused" in lower_message or "timeout" in lower_message:
        return _play_http_exception(
            503,
            "media_node_unreachable",
            "Media node connection failed",
            "Check media node service status, network connectivity and firewall config",
            retryable=True,
        )
    if "port" in lower_message and any(keyword in lower_message for keyword in ("exhaust", "used", "busy", "range", "occup", "占用", "耗尽", "不足")):
        return _play_http_exception(
            503,
            "media_port_exhausted",
            "Media node RTP port exhausted",
            "Close unused streams, expand RTP port range, or add media nodes",
            retryable=True,
        )
    if "openrtpserver" in lower_message:
        return _play_http_exception(
            503,
            "media_service_error",
            "Media node failed to create RTP server port",
            "Check media node runtime status, port config and logs",
            retryable=True,
        )
    return _play_http_exception(
        502,
        "play_request_failed",
        "Stream play request failed",
        "Check device online status, media node status and playback params, then retry",
        retryable=True,
    )


async def _build_full_play_response(
    db: AsyncSession,
    app_name: str,
    stream_id: str,
    stream_type: str,
    selected_node,
    media_host: str | None,
    media_port: int | None,
    node_host: str | None,
    node_http_port: int | None,
    is_embedded_node: bool,
    zlm_probe_ok: bool,
    zlm_stream_ready: bool,
    media_item: dict | None,
    result: dict,
    resource: Resource,
    node_id: str | None,
    sla_metrics: dict | None = None,
) -> dict:
    if not media_host or not media_port:
        media_host, media_port = settings.STREAM_PUBLIC_HOST, settings.STREAM_PUBLIC_HTTP_PORT
    token = _stream_play_token(app_name, stream_id, expire_seconds=_get_play_token_ttl())
    webrtc_supported = True
    webrtc_hint = ""
    # P1-fix [2026-07-17]: 传入节点 secret，避免 ZLM 启用鉴权时探测返回 401 误判为可用
    _webrtc_probe_secret = str(_node_value(selected_node, "secret") or "") or str(settings.MEDIA_SERVER_SECRET or "")
    if node_host and node_http_port:
        webrtc_supported, webrtc_hint = await _probe_webrtc_capability(node_host, int(node_http_port), app_name, stream_id, secret=_webrtc_probe_secret)
    elif media_host and media_port:
        webrtc_supported, webrtc_hint = await _probe_webrtc_capability(media_host, int(media_port), app_name, stream_id, secret=_webrtc_probe_secret)
    if not webrtc_supported and is_embedded_node:
        webrtc_hint = f"Built-in ZLM WebRTC not ready, check ZLM startup logs and RTC port config. {webrtc_hint}"  # i18n
    elif not webrtc_supported:
        webrtc_hint = f"Current media node may not have WebRTC enabled. {webrtc_hint}"  # i18n
    http_port = _safe_int(
        media_port,
        _safe_int(_node_value(selected_node, "public_http_port"), _safe_int(settings.STREAM_PUBLIC_HTTP_PORT, 0)),
    )
    https_port = _effective_https_port(selected_node)
    rtsp_port = _safe_int(_node_value(selected_node, "rtsp_port"), _safe_int(settings.MEDIA_SERVER_RTSP_PORT, 0))
    rtsps_port = _safe_int(_node_value(selected_node, "rtsps_port"), _safe_int(settings.MEDIA_SERVER_RTSPS_PORT, 0))
    rtmp_port = _safe_int(_node_value(selected_node, "rtmp_port"), _safe_int(settings.MEDIA_SERVER_RTMP_PORT, 0))
    rtmps_port = _safe_int(_node_value(selected_node, "rtmps_port"), _safe_int(settings.MEDIA_SERVER_RTMPS_PORT, 0))
    urls = _build_play_urls(
        app_name=app_name,
        stream_id=stream_id,
        media_host=media_host,
        http_port=http_port,
        https_port=https_port,
        rtmp_port=rtmp_port,
        rtmps_port=rtmps_port,
        rtsp_port=rtsp_port,
        rtsps_port=rtsps_port,
        token=token,
        vhost=str((media_item or {}).get("vhost") or (media_item or {}).get("schema") or "__defaultVhost__"),
    )
    media_server_payload = _build_media_server_payload(selected_node, media_host, http_port, zlm_probe_ok)
    media_info = _build_media_info_payload(
        app_name=app_name,
        stream_id=stream_id,
        selected_node=selected_node,
        media_server_payload=media_server_payload,
        media_item=media_item,
        result=result,
        resource=resource,
        zlm_stream_ready=zlm_stream_ready,
    )
    auto_heal_profile = await _build_auto_heal_profile(
        db,
        asset_id=str(getattr(resource, "asset_id", "") or ""),
        media_info=media_info,
        result=result,
    )

    # 核心修复：在返回 URL 之前，逐一验证每个端点的 HTTP 可访问性
    # 这能确保前端不会拿到 404 的 URL
    url_availability: dict = {}
    hls_probe_detail: dict = {}
    if node_host and node_http_port and zlm_probe_ok:
        # 并行执行 HLS 探测 + URL 验证，节省 1~2s 等待时间
        # HLS: 最多 5 次 x 0.5s = 2.5s；URL 验证: ~2s
        # 两者互不依赖，一起跑最多耗时 max(2.5s, 2s)
        hls_coro = _probe_zlm_hls_ready(
            node_host,
            int(node_http_port),
            app_name,
            stream_id,
            max_attempts=5,
            interval_seconds=0.5,
        )
        url_coro = _validate_play_urls(
            urls,
            node_host,
            int(node_http_port),
            str(_node_value(selected_node, "secret") or ""),
            app_name,
            stream_id,
        )
        hls_result, url_result = await asyncio.gather(hls_coro, url_coro)
        hls_ready, _, hls_probe_detail = hls_result
        url_availability = url_result
        if not hls_ready:
            for hls_key in ("hls", "https_hls", "ws_hls", "wss_hls"):
                if hls_key in url_availability and url_availability.get(hls_key) is not None:
                    url_availability[hls_key] = False

    return _build_play_success_response(
        app_name=app_name,
        stream_id=stream_id,
        token=token,
        urls=urls,
        codec=_resolve_codec(resource),
        media_server_id=str(node_id or ""),
        media_info=media_info,
        result=result,
        zlm_probe_ok=zlm_probe_ok,
        zlm_stream_ready=zlm_stream_ready,
        webrtc_supported=webrtc_supported,
        webrtc_hint=webrtc_hint,
        stream_type=stream_type,
        auto_heal_profile=auto_heal_profile,
        sla_metrics=sla_metrics,
        url_availability=url_availability,
        hls_probe_detail=hls_probe_detail,
    )
