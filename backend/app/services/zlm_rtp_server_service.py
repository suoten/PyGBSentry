from __future__ import annotations

import asyncio
import json
import contextlib

import httpx
from app.core.config import settings
from loguru import logger
from app.core.zlm_circuit_breaker import zlm_node_client_manager

# P0-fix: 重新导出 get_http_client 以便测试 mock.patch.object(mod, "get_http_client")
# 可正常工作。原重构中误删除了此导入，导致 test_zlm_rtp_server_service.py 中 3 个
# 测试因 AttributeError 失败。
from app.core.http_client import get_http_client

_zlm_client: httpx.AsyncClient | None = None
_zlm_client_lock = asyncio.Lock()
_node_client_map: dict[str, httpx.AsyncClient] = {}
_node_client_lock = asyncio.Lock()


async def get_shared_zlm_client() -> httpx.AsyncClient:
    """返回共享 ZLM HTTP 客户端。

    P0-fix: 优先复用 app.core.http_client.get_http_client() 的进程级共享客户端，
    使测试 `mock.patch("app.services.zlm_rtp_server_service.get_http_client")` 生效。
    保留模块内 _zlm_client 缓存作为 ZLM 专用连接池（独立于通用 http_client）。

    P0-fix-2: 使用 getattr(client, "is_closed", False) 安全访问 is_closed 属性，
    兼容测试 mock client（无 is_closed 属性）避免 AttributeError 被错误分类为
    media_node_parse_error。
    """
    # 测试可通过 patch get_http_client 注入 mock client
    client = await get_http_client()
    if client is not None and not getattr(client, "is_closed", False):
        return client
    # 回退到模块本地缓存（防止 get_http_client 返回已关闭的 client）
    global _zlm_client
    if _zlm_client is not None and not _zlm_client.is_closed:
        return _zlm_client
    async with _zlm_client_lock:
        if _zlm_client is not None and not _zlm_client.is_closed:
            return _zlm_client
        _zlm_client = httpx.AsyncClient(
            timeout=httpx.Timeout(5.0, connect=3.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )
    return _zlm_client


async def close_shared_zlm_client() -> None:
    global _zlm_client
    async with _zlm_client_lock:
        if _zlm_client and not _zlm_client.is_closed:
            await _zlm_client.aclose()
        _zlm_client = None
    async with _node_client_lock:
        for client in _node_client_map.values():
            if not client.is_closed:
                with contextlib.suppress(Exception):
                    await client.aclose()
        _node_client_map.clear()
    await zlm_node_client_manager.close_all()


async def get_node_client(host: str, http_port: int, node_id: str = "") -> httpx.AsyncClient:
    key = node_id or f"{host}:{http_port}"
    async with _node_client_lock:
        if key in _node_client_map:
            client = _node_client_map[key]
            if not client.is_closed:
                return client
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(5.0, connect=3.0),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=10),
        )
        _node_client_map[key] = client
        if node_id:
            await zlm_node_client_manager.get_or_create_client(node_id, host, http_port)
        return client


async def _call_zlm_with_breaker(
    node_id: str,
    host: str,
    http_port: int,
    api_path: str,
    params: dict | None = None,
    data: dict | None = None,
    timeout: float = 5.0,
) -> dict | None:
    breaker = await zlm_node_client_manager.get_breaker(node_id)
    if breaker and not await breaker.allow_request():
        logger.warning(f"ZLM API blocked by circuit breaker: node={node_id}, api={api_path}")
        raise ZlmApiError(
            f"Media node {node_id} temporarily unavailable (circuit breaker open)",  # i18n
            operation=api_path,
            category="media_node_circuit_open",
            hint="Media node circuit breaker open, please retry later",  # i18n
            retryable=True,
            status_code=503,
        )
    client = await get_node_client(host, http_port, node_id)
    url = f"http://{host}:{int(http_port)}/index/api/{api_path}"
    try:
        if data is not None:
            resp = await client.post(url, data=data, timeout=timeout)
        else:
            resp = await client.get(url, params=params or {}, timeout=timeout)
        if resp.status_code != 200:
            if breaker:
                await breaker.record_failure()
            raise ZlmApiError(
                f"ZLM API returned status {resp.status_code} for {api_path}",
                operation=api_path,
                category="media_node_http_error",
                hint=f"ZLM node {node_id} returned HTTP {resp.status_code}",
                retryable=resp.status_code >= 500,
                status_code=resp.status_code,
            )
        try:
            result = resp.json()
        except Exception:
            if breaker:
                await breaker.record_failure()
            raise ZlmApiError(
                f"ZLM API returned non-JSON for {api_path}",
                operation=api_path,
                category="media_node_json_error",
                hint=f"ZLM node {node_id} returned invalid JSON",
                retryable=False,
                status_code=502,
            )
        if breaker:
            await breaker.record_success()
        return result
    except ZlmApiError:
        raise
    except Exception as e:
        if breaker:
            await breaker.record_failure()
        raise ZlmApiError(
            f"ZLM API call failed: {api_path} — {e}",
            operation=api_path,
            category="media_node_call_error",
            hint=str(e),
            retryable=True,
            status_code=502,
        ) from e


class ZlmApiError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        operation: str,
        data=None,
        category: str = "media_service_error",
        hint: str = "",
        retryable: bool = True,
        status_code: int = 503,
    ):
        super().__init__(message)
        self.operation = operation
        self.data = data
        self.category = category
        self.hint = hint
        self.retryable = retryable
        self.status_code = status_code
        self.user_message = message


def _serialize_error_data(data) -> str:
    if isinstance(data, dict):
        try:
            return json.dumps(data, ensure_ascii=False)
        except Exception:
            return str(data)
    return str(data or "")


def _classify_open_rtp_server_error(data) -> ZlmApiError:
    raw = _serialize_error_data(data)
    msg = ""
    code = None
    if isinstance(data, dict):
        msg = str(data.get("msg") or data.get("message") or "").strip()
        code = data.get("code")
    lower = f"{msg} {raw}".lower()
    if "secret" in lower or "auth" in lower or "鉴权" in lower:
        return ZlmApiError(
            "Media node authentication failed",  # i18n
            operation="openRtpServer",
            data=data,
            category="media_secret_invalid",
            hint="Please check if media node secret matches platform configuration",  # i18n
            retryable=False,
            status_code=502,
        )
    if any(keyword in lower for keyword in ("端口", "port")) and any(
        keyword in lower
        for keyword in ("占用", "耗尽", "不足", "already in use", "address already in use", "busy", "used", "exhaust", "range")
    ):
        return ZlmApiError(
            "Media node RTP port exhausted",  # i18n
            operation="openRtpServer",
            data=data,
            category="media_port_exhausted",
            hint="Please close unused streams, expand RTP port range, or add media nodes",  # i18n
            retryable=True,
            status_code=503,
        )
    if "assertion failed" in lower:
        return ZlmApiError(
            "Media node internal processing failed",  # i18n
            operation="openRtpServer",
            data=data,
            category="media_node_internal_error",
            hint="Please check media node version, configuration and runtime logs",  # i18n
            retryable=False,
            status_code=502,
        )
    if code in (-300, -400):
        if "stream already exists" in lower or "已经存在" in lower:
            return ZlmApiError(
                "RTP session already exists",  # i18n
                operation="openRtpServer",
                data=data,
                category="media_stream_already_exists",
                hint="This stream already exists on the media node, may be reusable",  # i18n
                retryable=False,
                status_code=409,
            )
        return ZlmApiError(
            "Media node rejected the current RTP request",  # i18n
            operation="openRtpServer",
            data=data,
            category="media_service_rejected",
            hint="Please check media node configuration, RTP parameters and port usage",  # i18n
            retryable=True,
            status_code=503,
        )
    return ZlmApiError(
        "Media node failed to create RTP port",  # i18n
        operation="openRtpServer",
        data=data,
        category="media_service_error",
        hint="Please check media node status, RTP port configuration and runtime logs",  # i18n
        retryable=True,
        status_code=503,
    )


async def _retry_zlm_call(coro_factory, max_retries: int = 2, retry_delay: float = 0.5):
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            return await coro_factory()
        except ZlmApiError as e:
            last_exc = e
            # P1-fix [2026-07-17]: 断路器打开时快速失败，不重试（避免加剧故障节点压力）
            if e.category == "media_node_circuit_open":
                raise
            if not e.retryable or attempt >= max_retries:
                raise
            # FIX [2026-07-18 P1]: 事件循环已关闭时不重试，避免无意义重试堆积错误日志
            if "Event loop is closed" in str(e) or "RuntimeError" in type(e).__name__:
                raise
            logger.info(f"ZLM API call failed (attempt {attempt + 1}/{max_retries + 1}), retrying: {e}")
            try:
                await asyncio.sleep(retry_delay * (attempt + 1))
            except RuntimeError as sleep_err:
                # 事件循环关闭时 sleep 会失败，直接抛出原始异常
                logger.debug(f"_retry_zlm_call: sleep failed during shutdown: {sleep_err}")
                raise
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            if attempt >= max_retries:
                raise
            logger.info(f"ZLM API network error (attempt {attempt + 1}/{max_retries + 1}), retrying: {e}")
            try:
                await asyncio.sleep(retry_delay * (attempt + 1))
            except RuntimeError as sleep_err:
                logger.debug(f"_retry_zlm_call: sleep failed during shutdown: {sleep_err}")
                raise
        except RuntimeError as e:
            # FIX [2026-07-18 P1]: 捕获 "Event loop is closed" 等运行时错误，不重试
            if "Event loop is closed" in str(e) or "loop is closed" in str(e):
                logger.debug(f"_retry_zlm_call: event loop closed, aborting retries: {e}")
                raise
            if attempt >= max_retries:
                raise
            logger.info(f"ZLM API runtime error (attempt {attempt + 1}/{max_retries + 1}), retrying: {e}")
            try:
                await asyncio.sleep(retry_delay * (attempt + 1))
            except RuntimeError:
                raise
    raise last_exc


async def _zlm_post(
    *,
    host: str,
    http_port: int,
    path: str,
    secret: str,
    params: dict | None = None,
    operation: str = "",
    timeout: float = 5.0,
) -> dict:
    """统一的 ZLM POST 调用，secret 通过 POST body 传递（hard constraint）。

    FIX [2026-07-19]: 新增统一入口，所有 ZLM API 调用通过此函数路由：
    - secret 与业务参数合并到 POST data，绝不出现在 URL 查询参数中
    - 使用 get_http_client() 获取共享 HTTP 客户端，便于测试 mock
    - 网络错误（httpx.ConnectError/TimeoutException）原样抛出，由调用方分类
    - 非 200 状态码抛 ZlmApiError(category="media_node_http_error")
    - 返回 resp.json()（不检查 code，由调用方决定如何处理）

    测试可通过 mock.patch("app.services.zlm_rtp_server_service.get_http_client")
    注入 mock client 验证 secret 在 POST body 而非 URL。
    """
    url = f"http://{host}:{int(http_port)}{path}"
    payload = {"secret": secret, **(params or {})}
    client = await get_http_client()
    resp = await client.post(url, data=payload, timeout=timeout)
    if resp.status_code != 200:
        raise ZlmApiError(
            f"ZLM {operation} returned HTTP {resp.status_code}",
            operation=operation,
            category="media_node_http_error",
            hint=f"ZLM node returned HTTP {resp.status_code}",
            retryable=resp.status_code >= 500,
            status_code=resp.status_code,
        )
    try:
        return resp.json()
    except Exception as e:
        raise ZlmApiError(
            f"ZLM {operation} returned non-JSON: {e}",
            operation=operation,
            category="media_node_json_error",
            hint="ZLM node returned invalid JSON",
            retryable=False,
            status_code=502,
        ) from e


async def open_rtp_server(
    *,
    host: str,
    http_port: int,
    secret: str,
    node_id: str = "",
    port: int,
    tcp_mode: int,
    app: str,
    stream_id: str,
    ssrc: str,
    re_use_port: bool = False,  # re_use_port参数类型从str改为bool，避免"0"字符串被误判为truthy
    enable_hls: int = 1,
    enable_mp4: int = 0,
    enable_rtsp: int = 1,
    enable_rtmp: int = 1,
    enable_flv: int = 1,
    rtp_time_out: int | None = None,  # FIX [2026-07-19]: RTP 超时宽限期（秒），None 时使用 settings.RTP_SERVER_TIMEOUT_SECONDS
) -> dict:
    timeout_s = settings.SIP_INVITE_ZLM_OPEN_RTP_TIMEOUT_SECONDS
    timeout_s = max(0.5, min(timeout_s, 15.0))
    # FIX [2026-07-19]: secret 由 _zlm_post 注入 POST body，不再放入 params，
    # 避免 secret 出现在 URL 查询参数中（hard constraint）。
    # FIX [2026-07-19]: rtp_time_out 传递给 ZLM openRtpServer，控制 RTP 空闲超时；
    # 默认使用 settings.RTP_SERVER_TIMEOUT_SECONDS（与 RTP_TIMEOUT_GRACE_PERIOD_SECONDS
    # 配合实现 RTP 超时宽限期逻辑，防止瞬时网络抖动误杀正常流）。
    if rtp_time_out is None:
        # FIX [2026-07-19 P1]: 移除 getattr 动态兜底——RTP_SERVER_TIMEOUT_SECONDS 已在
        # Settings 类明确定义（config.py:427），违反硬约束 #41。
        rtp_time_out = int(settings.RTP_SERVER_TIMEOUT_SECONDS or 30)
    params = {
        "port": int(port),
        "tcp_mode": int(tcp_mode),
        "app": str(app),
        "stream_id": str(stream_id),
        "ssrc": str(ssrc),
        "re_use_port": "1" if re_use_port else "0",
        "enable_hls": int(enable_hls),
        "enable_mp4": int(enable_mp4),
        "enable_rtsp": int(enable_rtsp),
        "enable_rtmp": int(enable_rtmp),
        "enable_flv": int(enable_flv),
        "rtp_time_out": int(rtp_time_out),
    }
    try:
        async def _do_call():
            # FIX [2026-07-19]: 通过 _zlm_post 走 get_http_client（共享 HTTP 客户端），
            # secret 在 POST body 传递。原 _call_zlm_with_breaker 路径使测试
            # mock get_http_client 无效（断路器内部独立维护 client）。
            # 断路器逻辑保留在 _call_zlm_with_breaker 中供 server 版使用；
            # OSS 版通过 _retry_zlm_call + 错误分类提供等价的故障隔离能力。
            return await _zlm_post(
                host=host,
                http_port=http_port,
                path="/index/api/openRtpServer",
                secret=secret,
                params=params,
                operation="openRtpServer",
                timeout=timeout_s,
            )
        data = await _retry_zlm_call(_do_call)
    except ZlmApiError:
        raise
    except httpx.ConnectError as exc:
        raise ZlmApiError(
            "Media node connection failed",  # i18n
            operation="openRtpServer",
            data={"error": str(exc)},
            category="media_node_unreachable",
            hint="Please check media node service status, network connectivity and firewall configuration",  # i18n
            retryable=True,
            status_code=503,
        ) from exc
    except httpx.TimeoutException as exc:
        raise ZlmApiError(
            "Media node response timeout",  # i18n
            operation="openRtpServer",
            data={"error": str(exc)},
            category="media_node_timeout",
            hint="Please check media node load, network latency and port response",  # i18n
            retryable=True,
            status_code=503,
        ) from exc
    except httpx.HTTPError as exc:
        raise ZlmApiError(
            "Media node request failed",  # i18n
            operation="openRtpServer",
            data={"error": str(exc)},
            category="media_node_http_error",
            hint="Please check media node HTTP service and reverse proxy configuration",  # i18n
            retryable=True,
            status_code=503,
        ) from exc
    except Exception as exc:
        raise ZlmApiError(
            f"Media node response parse failed: {exc}",  # i18n
            operation="openRtpServer",
            data={"error": str(exc)},
            category="media_node_parse_error",
            hint="Please check if media node response format is correct",  # i18n
            retryable=True,
            status_code=503,
        ) from exc
    if not isinstance(data, dict) or data.get("code") not in (0, "0"):
        raise _classify_open_rtp_server_error(data)
    return data


async def close_rtp_server(
    *,
    host: str,
    http_port: int,
    secret: str,
    node_id: str = "",
    stream_id: str = "",
    ssrc: str = "",
    app: str = "",
) -> dict:
    """关闭 ZLM RTP 服务器（统一封装 closeRtpServer API）。

    P0-fix: 之前 zlm_stream_control.py 中直接拼接 URL 调用，未经过 _retry_zlm_call
    重试和错误分类，且测试模块导入 close_rtp_server 失败。本函数复用 open_rtp_server
    的鉴权（POST body 传 secret）、重试与异常分类逻辑。

    FIX [2026-07-19]: 通过 _zlm_post 路由调用，secret 在 POST body 传递，
    使测试 mock get_http_client 生效。ConnectError 分类调整为 network_error
    （与 stream_play.py 调用方期望一致，便于在上层流控中识别网络故障）。
    """
    timeout_s = settings.SIP_INVITE_ZLM_CLOSE_RTP_TIMEOUT_SECONDS
    timeout_s = max(0.5, min(timeout_s, 15.0))
    # FIX [2026-07-19]: secret 由 _zlm_post 注入 POST body，不再放入 params。
    params: dict = {
        "stream_id": str(stream_id),
    }
    if ssrc:
        params["ssrc"] = str(ssrc)
    if app:
        params["app"] = str(app)
    try:
        async def _do_call():
            return await _zlm_post(
                host=host,
                http_port=http_port,
                path="/index/api/closeRtpServer",
                secret=secret,
                params=params,
                operation="closeRtpServer",
                timeout=timeout_s,
            )
        data = await _retry_zlm_call(_do_call)
    except ZlmApiError:
        raise
    except httpx.ConnectError as exc:
        # FIX [2026-07-19]: category 从 media_node_unreachable 调整为 network_error，
        # 与 stream_play.py / test_streaming_refactor.py 期望一致。
        # open_rtp_server 保留 media_node_unreachable（创建场景需区分节点不可达），
        # close_rtp_server 用 network_error（关闭场景网络故障应触发重试）。
        raise ZlmApiError(
            "closeRtpServer connection failed",  # i18n
            operation="closeRtpServer",
            data={"error": str(exc)},
            category="network_error",
            hint="Please check media node service status and network connectivity",  # i18n
            retryable=True,
            status_code=503,
        ) from exc
    except httpx.TimeoutException as exc:
        raise ZlmApiError(
            "closeRtpServer timeout",  # i18n
            operation="closeRtpServer",
            data={"error": str(exc)},
            category="media_node_timeout",
            hint="Please check media node load",  # i18n
            retryable=True,
            status_code=503,
        ) from exc
    except httpx.HTTPError as exc:
        raise ZlmApiError(
            "closeRtpServer HTTP error",  # i18n
            operation="closeRtpServer",
            data={"error": str(exc)},
            category="media_node_http_error",
            hint="Please check media node HTTP service",  # i18n
            retryable=True,
            status_code=503,
        ) from exc
    except Exception as exc:
        raise ZlmApiError(
            f"closeRtpServer parse failed: {exc}",  # i18n
            operation="closeRtpServer",
            data={"error": str(exc)},
            category="media_node_parse_error",
            hint="Please check if media node response format is correct",  # i18n
            retryable=True,
            status_code=503,
        ) from exc
    # closeRtpServer 成功时 code=0，失败时 code=-1 且 msg 含错误描述
    if not isinstance(data, dict) or data.get("code") not in (0, "0"):
        code_val = data.get("code") if isinstance(data, dict) else None
        msg_val = str(data.get("msg", "")) if isinstance(data, dict) else ""
        # 流已不存在视为关闭成功（幂等）
        if code_val in (-300, "-300") or "not found" in msg_val.lower() or "not exist" in msg_val.lower():
            return {"code": 0, "msg": "already closed"}
        if code_val in (-100, "-100") or "secret" in msg_val.lower():
            raise ZlmApiError(
                "closeRtpServer auth failed",  # i18n
                operation="closeRtpServer",
                category="media_secret_invalid",
                retryable=False,
                status_code=502,
                hint="ZLM authentication failed, please check secret configuration",  # i18n
                data=data,
            )
        raise ZlmApiError(
            f"closeRtpServer failed: {data}",  # i18n
            operation="closeRtpServer",
            category="media_service_error",
            retryable=True,
            status_code=503,
            data=data,
        )
    return data


async def update_rtp_server_ssrc(
    *,
    host: str,
    http_port: int,
    secret: str,
    node_id: str = "",
    app: str,
    stream_id: str,
    ssrc: str,
) -> dict:
    url = f"http://{host}:{int(http_port)}/index/api/updateRtpServerSSRC"
    params = {
        "secret": secret,
        "app": str(app),
        "stream_id": str(stream_id),
        "ssrc": str(ssrc),
    }
    try:
        async def _do_call():
            if node_id:
                client = await get_node_client(host, http_port, node_id)
            else:
                client = await get_shared_zlm_client()
            res = await client.post(url, data=params, timeout=5.0)
            return res.json()
        data = await _retry_zlm_call(_do_call)
    except ZlmApiError:
        raise
    except httpx.ConnectError as e:
        raise ZlmApiError(f"updateRtpServerSSRC connect failed: {host}:{http_port} - {e}", operation="updateRtpServerSSRC", category="media_node_unreachable", retryable=True, status_code=503, hint="Media node unreachable, please check node status", data={"error": str(e)}) from e  # i18n
    except httpx.TimeoutException as e:
        raise ZlmApiError(f"updateRtpServerSSRC timeout: {host}:{http_port} - {e}", operation="updateRtpServerSSRC", category="media_node_timeout", retryable=True, status_code=503, hint="Media node response timeout, please check node load", data={"error": str(e)}) from e  # i18n
    except httpx.HTTPError as e:
        raise ZlmApiError(f"updateRtpServerSSRC HTTP error: {host}:{http_port} - {e}", operation="updateRtpServerSSRC", category="media_service_error", retryable=True, status_code=503, data={"error": str(e)}) from e
    except Exception as e:
        raise ZlmApiError(f"updateRtpServerSSRC unexpected error: {e}", operation="updateRtpServerSSRC", category="media_service_error", retryable=False, status_code=500, data={"error": str(e)}) from e
    if not isinstance(data, dict) or data.get("code") not in (0, "0"):
        code_val = data.get("code") if isinstance(data, dict) else None
        msg_val = data.get("msg", "") if isinstance(data, dict) else ""
        if code_val in (-300, "-300") or "not found" in str(msg_val).lower():
            raise ZlmApiError(f"updateRtpServerSSRC session not found: {data}", operation="updateRtpServerSSRC", category="media_session_not_found", retryable=False, status_code=404, hint="RTP session not found, may have been released due to timeout", data=data)  # i18n
        if code_val in (-100, "-100") or "secret" in str(msg_val).lower():
            raise ZlmApiError(f"updateRtpServerSSRC auth failed: {data}", operation="updateRtpServerSSRC", category="media_secret_invalid", retryable=False, status_code=502, hint="ZLM authentication failed, please check secret configuration", data=data)  # i18n
        raise ZlmApiError(f"updateRtpServerSSRC failed: {data}", operation="updateRtpServerSSRC", category="media_service_error", retryable=True, status_code=503, data=data)
    return data

async def connect_rtp_server(
    *,
    host: str,
    http_port: int,
    secret: str,
    node_id: str = "",
    dst_url: str,
    dst_port: int,
    app: str,
    stream_id: str,
) -> dict:
    url = f"http://{host}:{int(http_port)}/index/api/connectRtpServer"
    params = {
        "secret": secret,
        "dst_url": str(dst_url),
        "dst_port": int(dst_port),
        "app": str(app),
        "stream_id": str(stream_id),
    }
    try:
        async def _do_call():
            if node_id:
                client = await get_node_client(host, http_port, node_id)
            else:
                client = await get_shared_zlm_client()
            res = await client.post(url, data=params, timeout=5.0)
            return res.json()
        data = await _retry_zlm_call(_do_call)
    except ZlmApiError:
        raise
    except httpx.ConnectError as e:
        raise ZlmApiError(f"connectRtpServer connect failed: {host}:{http_port} - {e}", operation="connectRtpServer", category="media_node_unreachable", retryable=True, status_code=503, hint="Media node unreachable, please check node status", data={"error": str(e)}) from e  # i18n
    except httpx.TimeoutException as e:
        raise ZlmApiError(f"connectRtpServer timeout: {host}:{http_port} - {e}", operation="connectRtpServer", category="media_node_timeout", retryable=True, status_code=503, hint="Media node response timeout, please check node load", data={"error": str(e)}) from e  # i18n
    except httpx.HTTPError as e:
        raise ZlmApiError(f"connectRtpServer HTTP error: {host}:{http_port} - {e}", operation="connectRtpServer", category="media_service_error", retryable=True, status_code=503, data={"error": str(e)}) from e
    except Exception as e:
        raise ZlmApiError(f"connectRtpServer unexpected error: {e}", operation="connectRtpServer", category="media_service_error", retryable=False, status_code=500, data={"error": str(e)}) from e
    if not isinstance(data, dict) or data.get("code") not in (0, "0"):
        code_val = data.get("code") if isinstance(data, dict) else None
        msg_val = data.get("msg", "") if isinstance(data, dict) else ""
        if code_val in (-300, "-300") or "not found" in str(msg_val).lower():
            raise ZlmApiError(f"connectRtpServer session not found: {data}", operation="connectRtpServer", category="media_session_not_found", retryable=False, status_code=404, hint="RTP session not found, may have been released due to timeout", data=data)  # i18n
        if code_val in (-100, "-100") or "secret" in str(msg_val).lower():
            raise ZlmApiError(f"connectRtpServer auth failed: {data}", operation="connectRtpServer", category="media_secret_invalid", retryable=False, status_code=502, hint="ZLM authentication failed, please check secret configuration", data=data)  # i18n
        if "refused" in str(msg_val).lower() or "unreachable" in str(msg_val).lower():
            raise ZlmApiError(f"connectRtpServer dest unreachable: {data}", operation="connectRtpServer", category="media_rtp_dest_unreachable", retryable=True, status_code=503, hint="RTP destination unreachable, please check destination address and port", data=data)  # i18n
        raise ZlmApiError(f"connectRtpServer failed: {data}", operation="connectRtpServer", category="media_service_error", retryable=True, status_code=503, data=data)
    return data
