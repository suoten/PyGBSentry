from __future__ import annotations

import asyncio
from typing import Optional

import logging

logger = logging.getLogger(__name__)


async def _get_zlm_client():
    from app.services.zlm_rtp_server_service import get_shared_zlm_client
    return await get_shared_zlm_client()


async def close_zlm_client() -> None:
    from app.services.zlm_rtp_server_service import close_shared_zlm_client
    await close_shared_zlm_client()


async def _close_on_node_client(client, host: str, http_port: int, secret: str, app: str, stream: str) -> None:
    close_stream_url = f"http://{host}:{http_port}/index/api/close_stream"
    close_rtp_url = f"http://{host}:{http_port}/index/api/closeRtpServer"
    close_stream_params = {"secret": secret, "app": app, "stream": stream, "force": 1}
    close_rtp_params = {"secret": secret, "app": app, "stream_id": stream}
    try:
        r1, r2 = await asyncio.gather(
            client.post(close_stream_url, data=close_stream_params, timeout=2.0),
            client.post(close_rtp_url, data=close_rtp_params, timeout=2.0),
            return_exceptions=True,
        )
        rtp_close_failed = False
        for idx, r in enumerate((r1, r2)):
            if isinstance(r, Exception):
                logger.warning(f"ZLM close API error for {app}/{stream} on {host}: {r}")
                if idx == 1:
                    rtp_close_failed = True
                continue
            if r.status_code < 400:
                try:
                    if r.json().get("code") not in (0, "0"):
                        logger.warning(f"ZLM API returned non-zero for {app}/{stream} on {host}")
                        if idx == 1:
                            rtp_close_failed = True
                except Exception:
                    if idx == 1:
                        rtp_close_failed = True
            else:
                logger.warning(f"close_stream/closeRtpServer HTTP {r.status_code} for {app}/{stream} on {host}")
                if idx == 1:
                    rtp_close_failed = True
        if rtp_close_failed:
            logger.warning(f"closeRtpServer failed for {app}/{stream} on {host}, retrying with stream_id as port mapping")
            try:
                retry_rtp_url = f"http://{host}:{http_port}/index/api/closeRtpServer"
                retry_params = {"secret": secret, "app": app, "stream_id": stream}
                retry_resp = await client.post(retry_rtp_url, data=retry_params, timeout=2.0)
                if retry_resp.status_code >= 400 or (retry_resp.json().get("code") not in (0, "0")):
                    logger.error(f"closeRtpServer retry also failed for {app}/{stream} on {host}, port may leak")
            except Exception as retry_err:
                logger.error(f"closeRtpServer retry error for {app}/{stream} on {host}: {retry_err}")
    except Exception as e:
        logger.warning(f"close_stream failed for {app}/{stream} on {host}: {e}")


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
                    _secret = db_node.secret
            if db_node:
                await _close_on_node_client(client, _host, _http_port, _secret, app, stream)
                return
            logger.warning(f"close_zlm_stream: node_id={node_id} not found in ENV or DB, skipping broadcast close")
            return
        except Exception as e:
            logger.warning(f"Failed to get DB node for close_stream: {e}")
            return

    nodes = get_media_nodes()
    env_node_ids = set()
    await asyncio.gather(*[
        _close_on_node_client(client, n['host'], n['http_port'], n['secret'], app, stream)
        for n in nodes
    ])
    # FIXED: dedup by host:http_port instead of id, since ENV nodes have id="default" but DB nodes have UUID
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
        await asyncio.gather(*[
            _close_on_node_client(client, n.host, n.http_port, n.secret, app, stream)
            for n in deduped_db_nodes
        ])
    except Exception as e:
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
        logger.error(f"startSendRtp failed: {e}")
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
        logger.error(f"addFFmpegSource failed: {e}")
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
            if data.get("code") in (0, "0", -1):
                return True
    except Exception as e:
        logger.error(f"delFFmpegSource failed: {e}")
    return False
