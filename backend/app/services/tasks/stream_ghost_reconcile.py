"""幽灵流周期对账任务。

FIX [2026-11-20 P2] (wvp #2135 部分同款修复):ZLM 侧已注册但平台无对应 StreamSession
的"幽灵流"此前只在 on_stream_changed reg 时发一次插件事件,不关闭也不对账——设备残留
推流会一直占用 RTP 端口与带宽。本任务周期性:
    1. 聚合 ENV + DB 两个节点源的 getMediaList;
    2. 仅取 GB RTP 推流(originTypeStr == "rtp_push",RTMP 推送通道等排除在外);
    3. 与 StreamSession 按 (app, stream) 对账,无会话的流记为幽灵候选;
    4. 候选持续存在超过宽限期(STREAM_GHOST_RECONCILE_GRACE_SECONDS,默认 90s,容忍
       INVITE 建会话与 ZLM 首包到达的正常竞态)后强制 close_stream 关闭。

注意:无会话即关闭是安全方向——rtp_push 流必有 INVITE 建立的会话,没有会话说明没有
人请求过该流,留着只会白耗设备推流与节点资源。
"""

import asyncio
import time

from loguru import logger
from sqlalchemy import and_, or_, select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.stream_session import StreamSession

_task: asyncio.Task | None = None

# 幽灵候选:(node_id, app, stream) -> 首次观测到的 monotonic 时间
_ghost_candidates: dict[tuple[str, str, str], float] = {}

_RECONCILE_INTERVAL_MIN_SECONDS = 60
_GHOST_GRACE_MIN_SECONDS = 30
_SESSION_MATCH_PAIRS_CAP = 500  # 单轮对账的 (app, stream) 配对上限,防御异常规模


async def _enumerate_media_items() -> tuple[list[dict], dict]:
    """聚合 ENV + DB 两个节点源的 getMediaList。

    返回 (items, node_by_id):每个 item 带 _node 信息(host/http_port/secret)供关流使用。
    """
    items: list[dict] = []
    node_by_id: dict[str, dict] = {}

    try:
        from app.core.media_nodes import get_all_media_from_nodes_async, get_media_nodes

        env_nodes = {str(n.get("id") or ""): n for n in get_media_nodes()}
        env_items = await get_all_media_from_nodes_async()
        for it in env_items or []:
            if not isinstance(it, dict):
                continue
            nid = str(it.get("node_id") or "")
            env_node = env_nodes.get(nid)
            if env_node:
                it["_node"] = {
                    "host": env_node.get("host"),
                    "http_port": int(env_node.get("http_port") or 0),
                    "secret": env_node.get("secret") or settings.MEDIA_SERVER_SECRET,
                }
                node_by_id.setdefault(nid, it["_node"])
            items.append(it)
    except Exception as e:
        logger.debug(f"[GhostReconcile] ENV node enumeration failed: {e}")

    try:
        from app.core.media_nodes_db import get_all_media_from_nodes as _db_media_list, list_db_media_nodes

        async with AsyncSessionLocal() as db:
            db_nodes = await list_db_media_nodes(db)
        if db_nodes:
            db_items = await _db_media_list(db_nodes)
            for it in db_items or []:
                if not isinstance(it, dict):
                    continue
                nid = str(it.get("node_id") or "")
                for dn in db_nodes:
                    if str(dn.id) == nid:
                        it["_node"] = {
                            "host": dn.host,
                            "http_port": int(dn.http_port or 0),
                            "secret": dn.secret,
                        }
                        node_by_id.setdefault(nid, it["_node"])
                        break
            items.extend(db_items)
    except Exception as e:
        logger.debug(f"[GhostReconcile] DB node enumeration failed: {e}")

    return items, node_by_id


async def _close_ghost_stream(node: dict, app: str, stream: str, node_id: str) -> bool:
    """强制关闭 ZLM 侧幽灵流。RTP server 的收尾由关流触发的 unreg hook 链路处理。"""
    host = str(node.get("host") or "")
    http_port = int(node.get("http_port") or 0)
    secret = str(node.get("secret") or "") or str(settings.MEDIA_SERVER_SECRET or "")
    if not host or http_port <= 0:
        logger.warning(f"[GhostReconcile] node {node_id} addr missing, cannot close {app}/{stream}")
        return False
    from app.services.zlm_stream_control import _get_zlm_client

    try:
        client = await _get_zlm_client()
        r = await client.post(
            f"http://{host}:{http_port}/index/api/close_stream",
            data={"secret": secret, "app": app, "stream": stream, "force": 1},
            timeout=3.0,
        )
        if r.status_code >= 400:
            logger.warning(f"[GhostReconcile] close_stream HTTP {r.status_code} for {app}/{stream} on {node_id}")
            return False
        body = r.json()
        if body.get("code") not in (0, "0"):
            logger.warning(f"[GhostReconcile] close_stream code={body.get('code')} for {app}/{stream} on {node_id}")
            return False
        return True
    except Exception as e:
        logger.warning(f"[GhostReconcile] close_stream error for {app}/{stream} on {node_id}: {e}")
        return False


async def _reconcile_once(grace_seconds: int) -> None:
    items, node_by_id = await _enumerate_media_items()
    if not items:
        _ghost_candidates.clear()
        return

    # 只对 GB RTP 推流做会话对账(rtp_push);RTMP/RTSP 推送通道、拉流代理、MP4 点播
    # 等生命周期与本平台会话表无关,一律排除
    rtp_items = []
    seen_pairs: set[tuple[str, str]] = set()
    for it in items:
        if str(it.get("originTypeStr") or "") != "rtp_push":
            continue
        app = str(it.get("app") or "")
        stream = str(it.get("stream") or "")
        if not app or not stream:
            continue
        pair = (app, stream)
        if pair not in seen_pairs:
            seen_pairs.add(pair)
            rtp_items.append(it)
    if not rtp_items:
        _ghost_candidates.clear()
        return

    async with AsyncSessionLocal() as session:
        pairs = list(seen_pairs)[:_SESSION_MATCH_PAIRS_CAP]
        # 有任一会话存在即视为"有主"(多节点/多 app 场景按 app+stream 精确匹配)
        cond = or_(*[and_(StreamSession.app == a, StreamSession.stream == s) for a, s in pairs])
        rows = (await session.execute(select(StreamSession.app, StreamSession.stream).where(cond))).all()
        owned_pairs = {(str(r[0] or ""), str(r[1] or "")) for r in rows}

    now_mono = time.monotonic()
    alive_keys: set[tuple[str, str, str]] = set()
    closed = 0
    for it in rtp_items:
        app = str(it.get("app") or "")
        stream = str(it.get("stream") or "")
        node_id = str(it.get("node_id") or "")
        key = (node_id, app, stream)
        alive_keys.add(key)
        if (app, stream) in owned_pairs:
            # 有主:清掉候选标记
            _ghost_candidates.pop(key, None)
            continue
        first = _ghost_candidates.setdefault(key, now_mono)
        if now_mono - first < grace_seconds:
            continue
        node = it.get("_node") or node_by_id.get(node_id) or {}
        if await _close_ghost_stream(node, app, stream, node_id):
            closed += 1
            logger.info(f"[GhostReconcile] closed ghost stream {app}/{stream} on node {node_id} (ghost for {int(now_mono - first)}s)")
        _ghost_candidates.pop(key, None)

    # 候选键清理:流已消失的候选不再保留
    for stale_key in [k for k in _ghost_candidates if k not in alive_keys]:
        _ghost_candidates.pop(stale_key, None)

    if closed:
        logger.info(f"[GhostReconcile] pass done: rtp_streams={len(rtp_items)} owned={len(owned_pairs)} closed_ghosts={closed}")


async def _run_loop() -> None:
    interval = max(_RECONCILE_INTERVAL_MIN_SECONDS, int(settings.STREAM_GHOST_RECONCILE_INTERVAL_SECONDS))
    grace = max(_GHOST_GRACE_MIN_SECONDS, int(settings.STREAM_GHOST_RECONCILE_GRACE_SECONDS))
    while True:
        if not settings.STREAM_GHOST_RECONCILE_ENABLED:
            await asyncio.sleep(interval)
            continue
        try:
            await _reconcile_once(grace)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"[GhostReconcile] reconcile pass failed: {e}")
        await asyncio.sleep(interval)


async def start() -> None:
    global _task
    if _task and not _task.done():
        return
    if not settings.STREAM_GHOST_RECONCILE_ENABLED:
        logger.info("[GhostReconcile] disabled by config, not started")
        return
    _task = asyncio.create_task(_run_loop())
    logger.info("[GhostReconcile] ghost stream reconciliation started")


async def stop() -> None:
    global _task
    if not _task:
        return
    _task.cancel()
    try:
        await asyncio.wait_for(_task, timeout=5.0)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        logger.warning("[GhostReconcile] stop cancelled/timeout")
    except Exception as e:
        logger.warning(f"[GhostReconcile] stop error: {e}")
    _task = None
