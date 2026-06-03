# -------------------------------------------------------------------------
# 多流媒体节点集群：自动选节点（开源默认）
# 解析 MEDIA_NODES 配置，按负载（当前流数）选择最优节点。
# -------------------------------------------------------------------------

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.services.zlm_stream_control import _get_zlm_client

logger = logging.getLogger(__name__)

DEFAULT_NODE_ID = "default"


def _single_node() -> Dict[str, Any]:
    return {
        "id": DEFAULT_NODE_ID,
        "host": settings.MEDIA_SERVER_HOST,
        "http_port": settings.MEDIA_SERVER_HTTP_PORT,
        "rtp_port": settings.MEDIA_SERVER_RTP_PROXY_PORT,
        "public_host": getattr(settings, "STREAM_PUBLIC_HOST", settings.MEDIA_SERVER_HOST),
        "public_http_port": getattr(settings, "STREAM_PUBLIC_HTTP_PORT", settings.MEDIA_SERVER_HTTP_PORT),
        "secret": settings.MEDIA_SERVER_SECRET,
    }


def get_media_nodes() -> List[Dict[str, Any]]:
    raw = getattr(settings, "MEDIA_NODES", None)
    if not raw or not str(raw).strip():
        return [_single_node()]

    try:
        nodes = json.loads(raw)
    except Exception as e:
        logger.warning("MEDIA_NODES JSON parse failed，使用单节点: %s", e)
        return [_single_node()]

    if not isinstance(nodes, list) or len(nodes) == 0:
        return [_single_node()]

    out: List[Dict[str, Any]] = []
    for i, n in enumerate(nodes):
        if not isinstance(n, dict):
            continue
        node_id = n.get("id") or f"node{i}"
        host = n.get("host") or settings.MEDIA_SERVER_HOST
        http_port = int(n.get("http_port") or settings.MEDIA_SERVER_HTTP_PORT)
        rtp_port = int(n.get("rtp_port") or settings.MEDIA_SERVER_RTP_PROXY_PORT)
        public_host = n.get("public_host") or host
        public_http_port = int(n.get("public_http_port") or http_port)
        secret = n.get("secret") or settings.MEDIA_SERVER_SECRET
        out.append({
            "id": node_id,
            "host": host,
            "http_port": http_port,
            "rtp_port": rtp_port,
            "public_host": public_host,
            "public_http_port": public_http_port,
            "secret": secret,
        })
    if not out:
        return [_single_node()]
    return out


def get_node_by_id(node_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not node_id:
        nodes = get_media_nodes()
        return nodes[0] if nodes else None
    for n in get_media_nodes():
        if n.get("id") == node_id:
            return n
    return None


def _zlm_secret(node: Dict[str, Any]) -> str:
    return str(node.get("secret") or "").strip() or str(getattr(settings, "MEDIA_SERVER_SECRET", "") or "").strip()


async def _async_get_stream_count_for_node(node: Dict[str, Any]) -> int:
    url = f"http://{node['host']}:{node['http_port']}/index/api/getMediaList"
    try:
        client = await _get_zlm_client()
        r = await client.get(url, params={"secret": _zlm_secret(node)}, timeout=2.0)
        if r.status_code >= 400:
            return 999999
        data = r.json()
        if data.get("code") not in (0, "0"):
            return 999999
        media_list = data.get("data")
        return len(media_list) if isinstance(media_list, list) else 0
    except Exception as e:
        logger.debug("节点 %s getMediaList 失败: %s", node.get("id"), e)
        return 999999


async def _get_stream_count_for_node(node: Dict[str, Any]) -> int:
    return await _async_get_stream_count_for_node(node)


async def get_all_media_from_nodes_async() -> List[Dict[str, Any]]:
    nodes = get_media_nodes()
    out: List[Dict[str, Any]] = []

    async def _fetch_node(node: Dict[str, Any]) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        url = f"http://{node['host']}:{node['http_port']}/index/api/getMediaList"
        try:
            client = await _get_zlm_client()
            r = await client.get(url, params={"secret": _zlm_secret(node)}, timeout=2.0)
            if r.status_code >= 400:
                return items
            data = r.json()
            if data.get("code") not in (0, "0"):
                return items
            media_list = data.get("data")
            if not isinstance(media_list, list):
                return items
            for item in media_list:
                items.append({**item, "node_id": node["id"]})
        except Exception as e:
            logger.debug("节点 %s getMediaList 失败: %s", node.get("id"), e)
        return items

    results = await asyncio.gather(*[_fetch_node(n) for n in nodes])
    for batch in results:
        out.extend(batch)
    return out


def get_all_media_from_nodes() -> List[Dict[str, Any]]:
    import concurrent.futures
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import threading
        result_container: list = [None]
        exception_container: list = [None]

        def _run_in_thread():
            try:
                result_container[0] = asyncio.run(get_all_media_from_nodes_async())
            except Exception as e:
                exception_container[0] = e

        t = threading.Thread(target=_run_in_thread, daemon=True)
        t.start()
        t.join(timeout=10)
        if exception_container[0]:
            raise exception_container[0]
        return result_container[0] or []
    return asyncio.run(get_all_media_from_nodes_async())


_select_best_cache: dict = {}
_select_best_cache_lock = asyncio.Lock()
_SELECT_BEST_CACHE_TTL = 2.0


async def select_best_node() -> Dict[str, Any] | None:
    nodes = get_media_nodes()
    if not nodes:
        return _single_node()
    if len(nodes) == 1:
        return nodes[0]

    async with _select_best_cache_lock:
        now = time.time()
        cached = _select_best_cache.get("result")
        cached_at = _select_best_cache.get("ts", 0)
        if cached and (now - cached_at) < _SELECT_BEST_CACHE_TTL:
            return cached

        counts = await asyncio.gather(*[_async_get_stream_count_for_node(n) for n in nodes])
        best_idx = -1
        best_count = float('inf')
        for i, count in enumerate(counts):
            if count < best_count and count < 999999:
                best_idx = i
                best_count = count
        if best_idx < 0:
            logger.warning("select_best_node: all ENV nodes unreachable")
            return None
        result = nodes[best_idx]
        _select_best_cache["result"] = result
        _select_best_cache["ts"] = now
        return result
