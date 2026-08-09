# -------------------------------------------------------------------------
# 多流媒体节点集群：自动选节点（开源默认）
# 解析 MEDIA_NODES 配置，按负载（当前流数）选择最优节点。
# -------------------------------------------------------------------------
#
# P-SEC 安全说明：ZLMediaKit RESTful API 的 secret 鉴权仅支持 URL 查询参数
# 或 POST 表单体，不支持 HTTP Header 方式。为避免 secret 出现在代理/访问日志
# 的 URL 中，所有 ZLM API 调用统一使用 POST 方法并将 secret 放入 POST body。

import asyncio
import json
from loguru import logger
import time
from typing import Any, Dict, List, Optional, TypedDict

from app.core.config import settings
from app.services.zlm_stream_control import _get_zlm_client

DEFAULT_NODE_ID = "default"

# FIX: [2026-07-14] ENV 节点探测失败日志限速：同一节点 60 秒内只输出一次 WARNING，
# 与 media_nodes_db.py 保持一致，避免 ZLM 宕机时 getMediaList 失败日志刷屏。
_ENV_NODE_FAIL_LOG_COOLDOWN: dict[str, float] = {}
_ENV_NODE_FAIL_LOG_COOLDOWN_SECONDS = 60.0


class MediaNode(TypedDict):
    """单个媒体节点配置信息（TypedDict，纯类型标注，不影响运行时 dict 行为）。

    运行时不需要验证（节点字典由本模块内部构造，结构已知），
    故使用 TypedDict 而非 Pydantic BaseModel，以保持 dict 访问语义
    （``node["host"]`` / ``node.get("id")``）不变。
    """

    id: str
    host: str
    http_port: int
    rtp_port: int
    public_host: str
    public_http_port: int
    secret: str


def _single_node() -> MediaNode:
    return {
        "id": DEFAULT_NODE_ID,
        "host": settings.MEDIA_SERVER_HOST,
        "http_port": settings.MEDIA_SERVER_HTTP_PORT,
        "rtp_port": settings.MEDIA_SERVER_RTP_PROXY_PORT,
        "public_host": settings.STREAM_PUBLIC_HOST or settings.MEDIA_SERVER_HOST,
        "public_http_port": settings.STREAM_PUBLIC_HTTP_PORT or settings.MEDIA_SERVER_HTTP_PORT,
        "secret": settings.MEDIA_SERVER_SECRET,
    }


def get_media_nodes() -> List[MediaNode]:
    raw = settings.MEDIA_NODES
    if not raw or not str(raw).strip():
        return [_single_node()]

    try:
        nodes = json.loads(raw)
    except Exception as e:
        logger.warning(f"MEDIA_NODES JSON parse failed，使用单节点: {e}")
        return [_single_node()]

    if not isinstance(nodes, list) or len(nodes) == 0:
        return [_single_node()]

    out: List[MediaNode] = []
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


def get_node_by_id(node_id: Optional[str]) -> Optional[MediaNode]:
    if not node_id:
        nodes = get_media_nodes()
        return nodes[0] if nodes else None
    for n in get_media_nodes():
        if n.get("id") == node_id:
            return n
    return None


def _zlm_secret(node: MediaNode) -> str:
    return str(node.get("secret") or "").strip() or str(settings.MEDIA_SERVER_SECRET or "").strip()


async def _async_get_stream_count_for_node(node: MediaNode) -> int:
    url = f"http://{node['host']}:{node['http_port']}/index/api/getMediaList"
    try:
        client = await _get_zlm_client()
        # P-SEC: secret 通过 POST body 传递，避免出现在 URL/代理日志中
        r = await client.post(url, data={"secret": _zlm_secret(node)}, timeout=2.0)
        if r.status_code >= 400:
            return 999999
        data = r.json()
        if data.get("code") not in (0, "0"):
            return 999999
        media_list = data.get("data")
        return len(media_list) if isinstance(media_list, list) else 0
    except Exception as e:
        # FIX: [2026-07-14] 日志限速：同一节点 60 秒内只输出一次 WARNING
        _nid = str(node.get('id') or node.get('host') or '?')
        _now = time.time()
        if _now - _ENV_NODE_FAIL_LOG_COOLDOWN.get(_nid, 0) >= _ENV_NODE_FAIL_LOG_COOLDOWN_SECONDS:
            logger.warning(f"节点 {_nid} getMediaList 失败: {e}")
            _ENV_NODE_FAIL_LOG_COOLDOWN[_nid] = _now
        return 999999


async def _get_stream_count_for_node(node: MediaNode) -> int:
    return await _async_get_stream_count_for_node(node)


# 注: 以下函数返回/收集的 media item 来自 ZLM getMediaList API 响应，
# 字段集是动态的（随媒体类型变化），且仅在响应中追加 "node_id" 键。
# 故保留 Dict[str, Any] 而非建模为 TypedDict/Pydantic（动态键名，向后兼容）。
async def get_all_media_from_nodes_async() -> List[Dict[str, Any]]:
    nodes = get_media_nodes()
    out: List[Dict[str, Any]] = []

    async def _fetch_node(node: MediaNode) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        url = f"http://{node['host']}:{node['http_port']}/index/api/getMediaList"
        try:
            client = await _get_zlm_client()
            # P-SEC: secret 通过 POST body 传递，避免出现在 URL/代理日志中
            r = await client.post(url, data={"secret": _zlm_secret(node)}, timeout=2.0)
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
            # FIX: [2026-07-14] 日志限速：同一节点 60 秒内只输出一次 WARNING
            _nid2 = str(node.get('id') or node.get('host') or '?')
            _now2 = time.time()
            if _now2 - _ENV_NODE_FAIL_LOG_COOLDOWN.get(_nid2, 0) >= _ENV_NODE_FAIL_LOG_COOLDOWN_SECONDS:
                logger.warning(f"节点 {_nid2} getMediaList 失败: {e}")
                _ENV_NODE_FAIL_LOG_COOLDOWN[_nid2] = _now2
        return items

    # P1-fix: 添加 return_exceptions=True，单节点异常不会取消其他节点的并发查询
    results = await asyncio.gather(*[_fetch_node(n) for n in nodes], return_exceptions=True)
    for batch in results:
        if isinstance(batch, Exception):
            logger.warning(f"get_all_media_list _fetch_node unexpected error: {batch}")
            continue
        out.extend(batch)
    return out


def get_all_media_from_nodes() -> List[Dict[str, Any]]:
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


# FIX R22-SEVERE: 移除 2s 全局缓存 + 全局锁串行化
# 原实现问题：
#   - 第 1 路进入锁，查询 count，写入缓存
#   - 第 2~10 路进入锁后命中缓存（2s 内）返回同一节点
#   - 导致突发并发全部命中同一节点，ZLM 线程池打满、RTP 端口耗尽
# 修复方案：
#   - 移除全局缓存（实时查询每次都获取最新 count）
#   - 移除全局锁（允许并发查询）
#   - 添加 in-flight 计数跟踪：选中节点后追加 timestamp，下次排序时加入 in-flight 计数
#     30s TTL 自动过期，无需调用方显式释放
_node_inflight: Dict[str, List[float]] = {}
# FIX [2026-07-17 P1-E4]: TTL 必须为 60 秒，与 media_nodes_db.py 一致，
# 匹配 INVITE 超时 + ZLM 探测时间，避免 in-flight 计数过早过期导致节点过载。
_INFLIGHT_TTL = 60.0


def _prune_inflight(node_id: str, now: float) -> int:
    """清理过期 in-flight 条目并返回当前有效计数。"""
    timestamps = _node_inflight.get(node_id)
    if not timestamps:
        return 0
    fresh = [t for t in timestamps if now - t < _INFLIGHT_TTL]
    if fresh:
        _node_inflight[node_id] = fresh
    else:
        _node_inflight.pop(node_id, None)
    return len(fresh)


def _add_inflight(node_id: str) -> None:
    """标记节点为 in-flight 分配状态。"""
    now = time.time()
    _prune_inflight(node_id, now)
    _node_inflight.setdefault(node_id, []).append(now)


def _decr_inflight(node_id: str) -> None:
    """显式释放 in-flight 计数（可选，TTL 兜底）。"""
    timestamps = _node_inflight.get(node_id)
    if not timestamps:
        return
    now = time.time()
    fresh = [t for t in timestamps if now - t < _INFLIGHT_TTL]
    if fresh:
        # 移除最早的一个 timestamp（FIFO）
        fresh.pop(0)
        if fresh:
            _node_inflight[node_id] = fresh
        else:
            _node_inflight.pop(node_id, None)
    else:
        _node_inflight.pop(node_id, None)


async def select_best_node() -> MediaNode | None:
    nodes = get_media_nodes()
    if not nodes:
        return _single_node()
    if len(nodes) == 1:
        return nodes[0]

    # FIX R22-SEVERE: 移除全局锁和缓存，允许并发查询；加入 in-flight 计数到排序
    # FIX [2026-07-17 P1-E1]: 启用 return_exceptions=True，单个节点查询失败不取消其他并发任务
    counts = await asyncio.gather(*[_async_get_stream_count_for_node(n) for n in nodes], return_exceptions=True)
    now = time.time()
    best_idx = -1
    best_score = float('inf')
    for i, count in enumerate(counts):
        # P1-E1: 跳过异常结果（Exception 实例），避免 TypeError 中断节点选择
        if isinstance(count, Exception):
            logger.warning(f"Node {nodes[i].get('id', f'node{i}')} stream count query failed: {count}")
            continue
        if count >= 999999:
            continue
        node_id = nodes[i].get("id") or f"node{i}"
        # 实际 count + in-flight 计数，避免突发并发全部命中同一节点
        score = count + _prune_inflight(node_id, now)
        if score < best_score:
            best_idx = i
            best_score = score
    if best_idx < 0:
        logger.warning("select_best_node: all ENV nodes unreachable")
        return None
    result = nodes[best_idx]
    _add_inflight(result.get("id") or f"node{best_idx}")
    return result
