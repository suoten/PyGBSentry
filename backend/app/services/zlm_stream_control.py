from __future__ import annotations

import asyncio
import time as _time_mod
from typing import Optional

from loguru import logger


# FIX [2026-07-19 P2-2]: ZLM 节点不可达时的错误日志限速。
# 同一 (host, port, operation) 在 60 秒内只输出一次 ERROR，后续降级为 DEBUG。
# 避免开发/测试环境未启动 ZLM 时刷屏（aa.txt P2-2）。
_ZLM_NODE_ERROR_LOG_TTL = 60.0  # 秒
_zlm_node_error_last_log: dict[str, float] = {}


def _is_zlm_node_unreachable(error: BaseException) -> bool:
    """判断异常是否为 ZLM 节点不可达（网络/连接错误）。"""
    # httpx.ConnectError / httpx.ConnectTimeout / aiohttp.ClientConnectorError 等
    name = type(error).__name__
    if name in {
        "ConnectError", "ConnectTimeout", "ConnectionError",
        "ClientConnectorError", "ClientConnectError", "OSError",
        "ServerDisconnectedError", "ReadTimeout", "RemoteProtocolError",
    }:
        return True
    msg = str(error).lower()
    network_hints = (
        "connection refused", "network is unreachable", "network down",
        "connection reset", "timed out", "timeout",
        "no route to host", "connectex:", "wsastartup",
        "[errno 111]", "[errno 113]", "[errno 110]",
        "connectionabortederror", "connectionrefusederror",
    )
    return any(h in msg for h in network_hints)


def _log_zlm_node_error(host: str, port: int, operation: str, error: BaseException) -> None:
    """ZLM 节点错误日志，节点不可达时按 1 分钟/节点限速降级。"""
    if not _is_zlm_node_unreachable(error):
        # 非网络错误（如鉴权失败、参数错误）保持 ERROR，不限速
        logger.error(f"{operation} failed on {host}:{port}: {error}")
        return
    key = f"{host}:{port}:{operation}"
    now = _time_mod.monotonic()
    last = _zlm_node_error_last_log.get(key, 0.0)
    if now - last < _ZLM_NODE_ERROR_LOG_TTL:
        # 限速窗口内：降级 DEBUG，避免刷屏
        logger.debug(f"{operation} failed on {host}:{port} (suppressed, node unreachable): {error}")
        return
    _zlm_node_error_last_log[key] = now
    # 过期条目惰性清理，防止字典无限增长
    if len(_zlm_node_error_last_log) > 256:
        expired = [k for k, ts in _zlm_node_error_last_log.items() if now - ts > _ZLM_NODE_ERROR_LOG_TTL]
        for k in expired:
            _zlm_node_error_last_log.pop(k, None)
    logger.error(f"{operation} failed on {host}:{port} (node unreachable, suppressing further errors for {_ZLM_NODE_ERROR_LOG_TTL}s): {error}")


async def _get_zlm_client():
    from app.services.zlm_rtp_server_service import get_shared_zlm_client
    return await get_shared_zlm_client()


async def close_zlm_client() -> None:
    from app.services.zlm_rtp_server_service import close_shared_zlm_client
    await close_shared_zlm_client()


async def _close_on_node_client(client, host: str, http_port: int, secret: str, app: str, stream: str) -> None:
    # P1-fix [2026-07-17]: close_stream 仍直接调用（ZLM 无统一封装），
    # closeRtpServer 改用 zlm_rtp_server_service.close_rtp_server 封装，
    # 获得：_retry_zlm_call 指数退避重试、断路器保护、错误分类、幂等处理（-300 视为已关闭）
    close_stream_url = f"http://{host}:{http_port}/index/api/close_stream"
    close_stream_params = {"secret": secret, "app": app, "stream": stream, "force": 1}
    try:
        r1 = await client.post(close_stream_url, data=close_stream_params, timeout=2.0)
        if r1.status_code >= 400:
            logger.warning(f"close_stream HTTP {r1.status_code} for {app}/{stream} on {host}")
    except Exception as e:
        logger.warning(f"close_stream error for {app}/{stream} on {host}: {e}")

    # closeRtpServer 改用统一封装（含重试、断路器、错误分类、幂等）
    try:
        from app.services.zlm_rtp_server_service import close_rtp_server, ZlmApiError
        await close_rtp_server(
            host=host,
            http_port=http_port,
            secret=secret,
            stream_id=stream,
            app=app,
        )
    except ZlmApiError as e:
        # 幂等：流已不存在视为关闭成功
        if "not found" in str(e).lower() or "not exist" in str(e).lower() or e.category == "media_session_not_found":
            logger.debug(f"closeRtpServer idempotent (already closed) for {app}/{stream} on {host}")
        elif e.category == "media_secret_invalid":
            logger.error(f"closeRtpServer auth failed for {app}/{stream} on {host}: {e}")
        else:
            logger.warning(f"closeRtpServer failed for {app}/{stream} on {host}: {e}")
    except Exception as e:
        logger.warning(f"closeRtpServer unexpected error for {app}/{stream} on {host}: {e}")


async def close_zlm_stream(app: str, stream: str, node_id: Optional[str] = None) -> None:
    from app.core.media_nodes import get_media_nodes, get_node_by_id

    client = await _get_zlm_client()
    if node_id:
        node = get_node_by_id(node_id)
        if node:
            await _close_on_node_client(client, node['host'], node['http_port'], node["secret"], app, stream)
            return
        try:
            from app.core.media_nodes_db import get_db_node_by_id
            from app.db.session import AsyncSessionLocal
            async with AsyncSessionLocal() as session:
                db_node = await get_db_node_by_id(session, node_id)
                if db_node:
                    _host = db_node.ip
                    _http_port = db_node.http_port
                    _secret = db_node.decrypted_secret  # P0-02: ORM 对象，decrypted_secret 解密
            if db_node:
                await _close_on_node_client(client, _host, _http_port, _secret, app, stream)
                return
            # FIX R23-SEVERE: 节点未找到时回退到广播关闭，而不是静默跳过
            # 原问题：node_id 指定的节点在 ENV 和 DB 中均未找到时直接 return，ZLM 流和 RTP 端口永久泄漏
            # 修复：回退到广播关闭所有节点上的流，确保资源被释放
            logger.warning(f"close_zlm_stream: node_id={node_id} not found in ENV or DB, falling back to broadcast close")
            # 不 return，继续执行下面的广播关闭逻辑
        except Exception as e:
            logger.warning(f"Failed to get DB node for close_stream: {e}, falling back to broadcast close")
            # 不 return，继续执行下面的广播关闭逻辑

    nodes = get_media_nodes()
    env_node_ids = set()
    # P1-fix [2026-07-17]: gather 添加 return_exceptions=True，单节点失败不影响其他节点
    await asyncio.gather(*[
        _close_on_node_client(client, n['host'], n['http_port'], n['secret'], app, stream)
        for n in nodes
    ], return_exceptions=True)
    # dedup by host:http_port instead of id, since ENV nodes have id="default" but DB nodes have UUID
    env_node_ids = {f"{n['host']}:{n['http_port']}" for n in nodes}

    try:
        from app.core.media_nodes_db import list_db_media_nodes
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            db_nodes = await list_db_media_nodes(session)
        deduped_db_nodes = [
            n for n in db_nodes
            if f"{n.host}:{n.http_port}" not in env_node_ids
        ]
        # P1-fix [2026-07-17]: gather 添加 return_exceptions=True
        await asyncio.gather(*[
            _close_on_node_client(client, n.host, n.http_port, n.secret, app, stream)
            for n in deduped_db_nodes
        ], return_exceptions=True)
    except Exception as e:
        # FIX [2026-07-19 P1-2]: 区分 sqlite "no such table" 与真实数据库异常。
        # 测试/开发环境未创建 media_nodes 表时，每次 close 都会触发 OperationalError，
        # 原日志 WARNING 刷屏。改为 DEBUG 级别 silent fallback；其他异常保持 WARNING。
        msg = str(e).lower()
        if "no such table" in msg or "does not exist" in msg:
            logger.debug(f"media_nodes table not available, skipping DB node close for {app}/{stream}: {e}")
        else:
            logger.warning(f"Failed to list DB media nodes for close_stream: {e}")


def close_zlm_stream_sync(app: str, stream: str, node_id: Optional[str] = None) -> None:
    try:
        loop = asyncio.get_running_loop()
        task = loop.create_task(close_zlm_stream(app, stream, node_id))
        def _on_done(t):
            if not t.cancelled():
                exc = t.exception()
                if exc:
                    logger.warning(f"[ZLM Control] close_zlm_stream async error: {exc}")
        task.add_done_callback(_on_done)
    except RuntimeError:
        try:
            asyncio.run(close_zlm_stream(app, stream, node_id))
        except Exception as e:
            logger.warning(f"[ZLM Control] close_zlm_stream fallback failed: {e}")


async def start_rtp_pusher(host: str, http_port: int, secret: str, app: str, stream: str, dst_ip: str, dst_port: int, ssrc: str, is_tcp: bool = False):
    url = f"http://{host}:{http_port}/index/api/startSendRtp"
    params = {
        "secret": secret,
        "vhost": "__defaultVhost__",
        "app": app,
        "stream": stream,
        "ssrc": ssrc,
        "dst_url": dst_ip,
        "dst_port": dst_port,
        "is_udp": 0 if is_tcp else 1
    }
    try:
        client = await _get_zlm_client()
        r = await client.post(url, data=params, timeout=3.0)
        if r.status_code < 400:
            data = r.json()
            if data.get("code") in (0, "0"):
                return True
            else:
                logger.warning(f"startSendRtp returned code={data.get('code')} for {app}/{stream} on {host}:{http_port}")
        else:
            logger.warning(f"startSendRtp HTTP {r.status_code} for {app}/{stream} on {host}:{http_port}")
    except Exception as e:
        # FIX [2026-07-19 P2-2]: ZLM 节点不可达时按 1分钟/节点限速，避免刷屏
        _log_zlm_node_error(host, http_port, "startSendRtp", e)
    return False


async def stop_rtp_pusher(host: str, http_port: int, secret: str, app: str, stream: str) -> bool:
    url = f"http://{host}:{http_port}/index/api/stopSendRtp"
    params = {
        "secret": secret,
        "vhost": "__defaultVhost__",
        "app": app,
        "stream": stream
    }
    try:
        client = await _get_zlm_client()
        r = await client.post(url, data=params, timeout=2.0)
        if r.status_code < 400:
            data = r.json()
            code = data.get("code")
            if code not in (0, "0"):
                logger.warning(f"stopSendRtp returned code={code} for {app}/{stream} on {host}:{http_port}")
                return False
            return True
        else:
            logger.warning(f"stopSendRtp HTTP {r.status_code} for {app}/{stream} on {host}:{http_port}")
            return False
    except Exception as e:
        logger.warning(f"stop_rtp_pusher failed: {e}")
        return False


async def add_ffmpeg_source(host: str, http_port: int, secret: str, src_url: str, dst_url: str, timeout_ms: int = 10000, enable_hls: int = 0, enable_mp4: int = 0) -> str:
    url = f"http://{host}:{http_port}/index/api/addFFmpegSource"
    params = {
        "secret": secret,
        "src_url": src_url,
        "dst_url": dst_url,
        "timeout_ms": timeout_ms,
        "enable_hls": enable_hls,
        "enable_mp4": enable_mp4
    }
    try:
        client = await _get_zlm_client()
        r = await client.post(url, data=params, timeout=5.0)
        if r.status_code < 400:
            data = r.json()
            if data.get("code") in (0, "0"):
                return data.get("data", {}).get("key", "")
    except Exception as e:
        # FIX [2026-07-19 P2-2]: ZLM 节点不可达时按 1分钟/节点限速，避免刷屏
        _log_zlm_node_error(host, http_port, "addFFmpegSource", e)
    return ""


async def del_ffmpeg_source(host: str, http_port: int, secret: str, key: str) -> bool:
    url = f"http://{host}:{http_port}/index/api/delFFmpegSource"
    params = {
        "secret": secret,
        "key": key
    }
    try:
        client = await _get_zlm_client()
        r = await client.post(url, data=params, timeout=3.0)
        if r.status_code < 400:
            data = r.json()
            # P1-fix [2026-07-17]: 仅接受 ZLM code=0 为成功
            # 原代码 `code in (0, "0", -1)` 将 ZLM 的 -1 错误码视为成功，掩盖真实失败：
            # ZLM API 中 code=-1 通常表示错误（如 key 不存在、source 已停止），
            # 这会让调用方误以为 FFmpeg source 已删除，后续 addFFmpegSource 因 key 冲突失败。
            # 幂等场景（已不存在视为成功）通过显式判断 msg 文本识别。
            if data.get("code") in (0, "0"):
                return True
            msg_val = str(data.get("msg") or data.get("message") or "").lower()
            if any(kw in msg_val for kw in ("not found", "not exist", "不存在", "未找到")):
                # 幂等：源已不存在视为成功
                return True
            logger.warning(f"delFFmpegSource returned non-success: code={data.get('code')} msg={data.get('msg')}")
    except Exception as e:
        # FIX [2026-07-19 P2-2]: ZLM 节点不可达时按 1分钟/节点限速，避免刷屏
        _log_zlm_node_error(host, http_port, "delFFmpegSource", e)
    return False
