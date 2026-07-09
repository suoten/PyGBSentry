"""ZLMediaKit RTP Server HTTP API 封装。

封装 ZLM 的 RTP 收流端口管理 API（``openRtpServer`` / ``closeRtpServer`` /
``connectRtpServer`` / ``updateRtpServerSSRC``），统一通过共享 ``httpx.AsyncClient``
发起请求，并将非零返回码转换为 :class:`ZlmApiError` 异常（携带 ``category`` /
``retryable`` 等结构化字段，供上层 invite 流程做端口耗尽重试 / 流已存在复用等决策）。

HTTP 客户端通过 ``app.core.http_client.get_http_client()`` 获取（进程级共享，
连接池复用）。``close_shared_zlm_client`` 在应用 shutdown 时调用。
"""
from __future__ import annotations

from typing import Any, Optional

import httpx
from loguru import logger

from app.core.config import settings
from app.core.http_client import get_http_client


class ZlmApiError(RuntimeError):
    """ZLM HTTP API 调用失败异常。

    继承 ``RuntimeError``（FastAPI 异常处理器据此返回结构化 JSON）。
    结构化字段供 invite 重试逻辑判断：

    - ``status_code``：HTTP 状态码或 ZLM 返回码（默认 502）
    - ``operation``：触发的 API 名（如 ``openRtpServer``）
    - ``category``：错误分类，取值：
        - ``media_port_exhausted``：端口耗尽（retryable=True，可换端口重试）
        - ``media_stream_already_exists``：stream_id 已存在（retryable=False，可复用）
        - ``auth_failed``：secret 校验失败（retryable=False，致命）
        - ``network_error``：连接 ZLM 失败（retryable=True）
        - ``unknown``：未分类错误
    - ``hint``：人类可读提示
    - ``retryable``：是否建议重试
    """

    def __init__(
        self,
        message: str,
        *,
        operation: str = "",
        category: str = "unknown",
        hint: str = "",
        retryable: bool = False,
        status_code: int = 502,
    ) -> None:
        """Internal helper:   init  ."""
        super().__init__(message)
        self.operation = operation
        self.category = category
        self.hint = hint or message
        self.retryable = bool(retryable)
        self.status_code = int(status_code)


def _classify_zlm_error(
    operation: str,
    code: Any,
    msg: str,
) -> ZlmApiError:
    """根据 ZLM 返回的 code/msg 构造分类好的 ZlmApiError。"""
    text = str(msg or "")
    low = text.lower()
    if "api secret" in low or "secret" in low and "invalid" in low:
        return ZlmApiError(
            f"ZLM {operation} auth failed: {text}",
            operation=operation,
            category="auth_failed",
            hint="MEDIA_SERVER_SECRET mismatch between backend and ZLMediaKit config.ini",
            retryable=False,
            status_code=401,
        )
    if "already exists" in low or "stream" in low and "exist" in low:
        return ZlmApiError(
            f"ZLM {operation} stream already exists: {text}",
            operation=operation,
            category="media_stream_already_exists",
            hint="stream_id already open on this ZLM node, reuse it",
            retryable=False,
            status_code=409,
        )
    if "port" in low or "range" in low or "exhaust" in low or "no available" in low or "端口" in text or "占用" in text:
        return ZlmApiError(
            f"ZLM {operation} port exhausted: {text}",
            operation=operation,
            category="media_port_exhausted",
            hint="No available RTP port on this node, try another port or node",
            retryable=True,
            status_code=503,
        )
    if "assertion failed" in low:
        return ZlmApiError(
            f"ZLM {operation} assertion failed: {text}",
            operation=operation,
            category="auth_failed",
            hint="ZLM assertion failed (usually secret mismatch or version incompatibility)",
            retryable=False,
            status_code=500,
        )
    return ZlmApiError(
        f"ZLM {operation} failed (code={code}): {text}",
        operation=operation,
        category="unknown",
        hint=text or "unknown ZLM error",
        retryable=False,
        status_code=502,
    )


async def _zlm_post(
    host: str,
    http_port: int,
    path: str,
    secret: str,
    params: dict[str, Any],
    *,
    operation: str,
    timeout: float = 5.0,
) -> dict[str, Any]:
    """通用 ZLM POST 调用，返回 data dict；失败抛 ZlmApiError。

    P-SEC: ZLMediaKit 不支持 HTTP Header 鉴权，secret 通过 POST body 传递，
    避免出现在 URL/代理日志中。所有 ZLM API 调用应通过本函数或直接使用 POST
    方法 + data= 传递 secret，禁止使用 GET + params= 将 secret 暴露在 URL 中。
    """
    url = f"http://{host}:{http_port}{path}"
    payload = {"secret": secret, **params}
    try:
        client = await get_http_client()
        resp = await client.post(url, data=payload, timeout=timeout)
    except httpx.HTTPError as e:
        raise ZlmApiError(
            f"ZLM {operation} network error: {e}",
            operation=operation,
            category="network_error",
            hint=f"Cannot reach ZLM at {host}:{http_port}",
            retryable=True,
            status_code=503,
        ) from e
    if resp.status_code >= 400:
        raise ZlmApiError(
            f"ZLM {operation} HTTP {resp.status_code}",
            operation=operation,
            category="network_error",
            hint=f"ZLM returned HTTP {resp.status_code} for {operation}",
            retryable=True,
            status_code=resp.status_code,
        )
    try:
        data = resp.json()
    except Exception as e:
        raise ZlmApiError(
            f"ZLM {operation} returned non-JSON: {e}",
            operation=operation,
            category="unknown",
            hint=f"ZLM response not JSON: {resp.text[:200]}",
            retryable=False,
            status_code=502,
        ) from e

    code = data.get("code")
    if code not in (0, "0"):
        msg = str(data.get("msg") or data.get("message") or "")
        raise _classify_zlm_error(operation, code, msg)
    return data


# ---------------------------------------------------------------------------
# 共享 HTTP 客户端管理
# ---------------------------------------------------------------------------

# 每节点专用客户端缓存：(host, http_port) -> AsyncClient
_node_clients: dict[tuple[str, int], httpx.AsyncClient] = {}


async def get_shared_zlm_client() -> httpx.AsyncClient:
    """返回进程级共享的 httpx.AsyncClient（来自 app.core.http_client）。

    所有 ZLM HTTP 调用应优先使用此客户端以复用连接池。
    """
    return await get_http_client()


async def get_node_client(
    host: str,
    http_port: int,
    node_id: Optional[str] = None,
) -> httpx.AsyncClient:
    """返回指定节点的 httpx.AsyncClient（按 host:port 缓存）。

    用于需要针对特定节点做隔离连接池的场景（如 hook 校验观看者数）。
    node_id 仅用于日志，缓存键为 ``(host, http_port)``。
    """
    key = (str(host or ""), int(http_port or 0))
    client = _node_clients.get(key)
    if client is not None and not client.is_closed:
        return client
    timeout = httpx.Timeout(
        timeout=float(getattr(settings, "HTTP_CLIENT_TIMEOUT", 30.0) or 30.0),
        connect=float(getattr(settings, "HTTP_CLIENT_CONNECT_TIMEOUT", 10.0) or 10.0),
    )
    client = httpx.AsyncClient(timeout=timeout)
    _node_clients[key] = client
    return client


async def close_shared_zlm_client() -> None:
    """关闭所有 ZLM 相关 HTTP 客户端（共享 + 每节点），在 shutdown 时调用。"""
    # 共享客户端由 app.core.http_client 统一管理，此处仅关闭每节点缓存
    closed = 0
    for key, client in list(_node_clients.items()):
        try:
            if not client.is_closed:
                await client.aclose()
            closed += 1
        except Exception as e:
            logger.warning(f"close node client {key} failed: {e}")
    _node_clients.clear()
    if closed:
        logger.info(f"Closed {closed} per-node ZLM httpx clients")


# FIX: [2026-07-04] 定期清理已关闭/过期的 per-node HTTP 客户端，防止媒体节点移除后客户端残留 [可靠性工程师]
async def cleanup_stale_node_clients() -> int:
    """清理 _node_clients 中已关闭或无效的客户端。

    被 ``health_service._run_loop`` 周期性调用。
    返回清理的客户端数量。
    """
    if not _node_clients:
        return 0
    stale_keys: list[tuple[str, int]] = []
    for key, client in list(_node_clients.items()):
        try:
            if client.is_closed:
                stale_keys.append(key)
        except Exception:
            stale_keys.append(key)
    for key in stale_keys:
        client = _node_clients.pop(key, None)
        if client:
            try:
                await client.aclose()
            except Exception as e:
                logger.debug(f"zlm_rtp: failed to close stale client: {e}")
    if stale_keys:
        logger.debug(f"Cleaned up {len(stale_keys)} stale per-node ZLM httpx clients")
    return len(stale_keys)


# ---------------------------------------------------------------------------
# RTP Server 管理 API
# ---------------------------------------------------------------------------


async def open_rtp_server(
    host: str,
    http_port: int,
    secret: str,
    port: int,
    tcp_mode: int = 0,
    app: str = "rtp",
    stream_id: str = "",
    ssrc: str = "0",
    re_use_port: str = "0",
    enable_hls: int = 0,
    enable_mp4: int = 0,
    enable_rtsp: int = 0,
    enable_rtmp: int = 0,
    enable_flv: int = 0,
    rtp_time_out: int | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """调用 ZLM ``/index/api/openRtpServer`` 打开 RTP 收流端口。

    返回 dict 至少包含 ``code`` 与 ``port``（实际监听端口）。
    失败时抛 :class:`ZlmApiError`（含分类化的 ``category`` / ``retryable``）。

    ``tcp_mode``：0=UDP，1=TCP被动，2=TCP主动。
    其余 enable_* 参数透传给 ZLM（部分版本支持在 openRtpServer 上直接控制派生流）。
    """
    params: dict[str, Any] = {
        "port": int(port or 0),
        "tcp_mode": int(tcp_mode or 0),
        "stream_id": str(stream_id or ""),
        "re_use_port": str(re_use_port or "0"),
    }
    # ssrc 仅在非 0 时下发，避免部分 ZLM 版本对 "0" 报错
    if ssrc and str(ssrc) != "0":
        params["ssrc"] = str(ssrc)
    # 透传 enable_* 开关（ZLM 4.0+ 支持）
    if enable_hls:
        params["enable_hls"] = int(enable_hls)
    if enable_mp4:
        params["enable_mp4"] = int(enable_mp4)
    if enable_rtsp:
        params["enable_rtsp"] = int(enable_rtsp)
    if enable_rtmp:
        params["enable_rtmp"] = int(enable_rtmp)
    if enable_flv:
        params["enable_flv"] = int(enable_flv)
    # P0-RTP: 传递 RTP 超时秒数给 ZLM，覆盖默认15秒（NAT场景下设备推流延迟可能>15秒）
    if rtp_time_out is None:
        rtp_time_out = int(getattr(settings, "RTP_SERVER_TIMEOUT_SECONDS", 30) or 30)
    if rtp_time_out > 0:
        params["rtp_time_out"] = int(rtp_time_out)
    # 透传额外 kwargs（兼容未来参数扩展）
    for k, v in kwargs.items():
        if v is not None:
            params[k] = v

    data = await _zlm_post(
        host, http_port, "/index/api/openRtpServer", secret, params,
        operation="openRtpServer",
    )
    # ZLM 返回的 port 字段为实际监听端口（port=0 时由 ZLM 自动分配）
    result = dict(data)
    result.setdefault("port", int(port or 0))
    return result


async def close_rtp_server(
    host: str,
    http_port: int,
    secret: str,
    stream_id: str,
) -> dict[str, Any]:
    """调用 ZLM ``/index/api/closeRtpServer`` 关闭 RTP 收流端口。"""
    params = {"stream_id": str(stream_id or "")}
    return await _zlm_post(
        host, http_port, "/index/api/closeRtpServer", secret, params,
        operation="closeRtpServer",
    )


async def update_rtp_server_ssrc(
    host: str,
    http_port: int,
    secret: str,
    app: str,
    stream_id: str,
    ssrc: str,
) -> dict[str, Any]:
    """调用 ZLM ``/index/api/updateRtpServerSSRC`` 更新已开 RTP 服务的 SSRC。

    用于设备在 200 OK 中修改 SSRC 后同步给 ZLM，避免 SSRC 校验失败丢包。
    """
    params = {
        "stream_id": str(stream_id or ""),
        "ssrc": str(ssrc or ""),
    }
    return await _zlm_post(
        host, http_port, "/index/api/updateRtpServerSSRC", secret, params,
        operation="updateRtpServerSSRC",
    )


async def connect_rtp_server(
    host: str,
    http_port: int,
    secret: str,
    dst_url: str,
    dst_port: int,
    app: str,
    stream_id: str,
) -> dict[str, Any]:
    """调用 ZLM ``/index/api/connectRtpServer`` 让 ZLM 主动连接设备的 TCP 主动端口。

    用于 TCP_ACTIVE 模式：设备在 200 OK 中返回其 TCP 监听地址，ZLM 作为客户端连接。
    """
    params = {
        "stream_id": str(stream_id or ""),
        "dst_url": str(dst_url or ""),
        "dst_port": int(dst_port or 0),
    }
    return await _zlm_post(
        host, http_port, "/index/api/connectRtpServer", secret, params,
        operation="connectRtpServer",
    )
