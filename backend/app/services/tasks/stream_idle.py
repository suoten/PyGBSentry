import asyncio
from loguru import logger
import datetime
import time
import os
import json

from app.models.stream_session import StreamSession
from app.models.media_node import MediaNode
from app.db.session import AsyncSessionLocal
from app.core.config import settings
from app.services.stream_session_service import release_stream_session
from app.models.system_setting import SystemSetting
from sqlalchemy import select



_task: asyncio.Task | None = None

PLUGIN_ID = "stream_idle"

_DEFAULT_BASE_CONFIG = {
    "enabled": True,
    "idle_timeout": 300,
    "check_interval": 60,
}

LOG_DIR = "logs/stream_idle"

_cfg_cache: dict = {}
_cfg_ts: float = 0.0
_cfg_ttl_sec: int = 10


async def _get_runtime_cfg() -> dict:
    """
    多租户兼容：聚合所有 tenant 的 plugin_runtime_config.*.stream_idle 配置。
    """
    global _cfg_cache, _cfg_ts
    now = time.time()
    if _cfg_cache and (now - _cfg_ts) < _cfg_ttl_sec:
        return _cfg_cache

    async with AsyncSessionLocal() as db:
        stmt = select(SystemSetting).where(
            SystemSetting.setting_key.like(f"plugin_runtime_config.%.{PLUGIN_ID}")
        )
        rows = (await db.execute(stmt)).scalars().all()

        merged = dict(_DEFAULT_BASE_CONFIG)
        any_enabled = False
        idle_timeout_max: int | None = None
        check_interval_max: int | None = None

        for r in rows:
            try:
                import json

                parsed = json.loads(r.setting_value or "{}")
                if not isinstance(parsed, dict):
                    continue
                if bool(parsed.get("enabled", False)):
                    any_enabled = True
                if "idle_timeout" in parsed:
                    try:
                        idle_iv = int(parsed.get("idle_timeout"))
                        idle_timeout_max = idle_iv if idle_timeout_max is None else max(idle_timeout_max, idle_iv)
                    except Exception as e:
                        logger.warning(f"Error: {e}")
                if "check_interval" in parsed:
                    try:
                        ci = int(parsed.get("check_interval"))
                        check_interval_max = ci if check_interval_max is None else max(check_interval_max, ci)
                    except Exception as e:
                        logger.warning(f"Error: {e}")
            except Exception:
                continue

        merged["enabled"] = any_enabled if any_enabled else bool(merged.get("enabled", True))
        if idle_timeout_max is not None:
            merged["idle_timeout"] = idle_timeout_max
        if check_interval_max is not None:
            merged["check_interval"] = check_interval_max

        _cfg_cache = merged
        _cfg_ts = now
        return _cfg_cache


async def _query_reader_count(node_host: str, node_http_port: int, secret: str, app: str, stream: str) -> int:
    try:
        from app.services.zlm_stream_control import _get_zlm_client
        sec = str(secret or "").strip() or str(getattr(settings, "MEDIA_SERVER_SECRET", "") or "").strip()
        url = f"http://{node_host}:{int(node_http_port)}/index/api/getMediaList"
        client = await _get_zlm_client()
        resp = await client.get(url, params={"secret": sec}, timeout=1.5)
        if resp.status_code >= 400:
            return -1
        payload = resp.json()
        if payload.get("code") not in (0, "0"):
            return -1
        rows = payload.get("data")
        if not isinstance(rows, list):
            return -1
        for item in rows:
            if not isinstance(item, dict):
                continue
            if str(item.get("app") or "") == str(app or "") and str(item.get("stream") or "") == str(stream or ""):
                return int(item.get("readerCount") or 0)
        return 0
    except Exception:
        return -1

async def check_idle_streams():
    while True:
        cfg = await _get_runtime_cfg()
        enabled = bool(cfg.get("enabled", True))
        idle_timeout = int(cfg.get("idle_timeout") or _DEFAULT_BASE_CONFIG["idle_timeout"])
        check_interval = int(cfg.get("check_interval") or _DEFAULT_BASE_CONFIG["check_interval"])
        idle_timeout = max(1, min(86400, idle_timeout))
        check_interval = max(1, min(3600, check_interval))

        if not enabled:
            await asyncio.sleep(check_interval)
            continue

        try:
            async with AsyncSessionLocal() as session:
                now = datetime.datetime.now(datetime.timezone.utc)
                cutoff = now - datetime.timedelta(seconds=idle_timeout)
                # S-19 使用JOIN一次性获取StreamSession+MediaNode，消除N+1查询
                stmt = (
                    select(StreamSession, MediaNode)
                    .join(MediaNode, MediaNode.id == StreamSession.media_server_id, isouter=True)
                    .where(StreamSession.start_time <= cutoff)
                )
                rows = (await session.execute(stmt)).all()
                # 构建stream+node配对列表
                stream_node_pairs = []
                for ss, node in rows:
                    node_id = str(getattr(ss, "media_server_id", "") or "").strip()
                    if not node_id or not node:
                        continue
                    host = str(getattr(node, "ip", "") or "").strip()
                    http_port = int(getattr(node, "http_port", 0) or 0)
                    secret = str(getattr(node, "secret", "") or "")
                    if not host or http_port <= 0:
                        continue
                    stream_node_pairs.append((ss, host, http_port, secret))

                # S-19 使用asyncio.gather+信号量并行化HTTP请求到ZLM
                _sem = asyncio.Semaphore(8)

                async def _check_and_release(pair):
                    ss, host, http_port, secret = pair
                    async with _sem:
                        readers = await _query_reader_count(
                            host, http_port, secret,
                            str(getattr(ss, "app", "") or ""),
                            str(getattr(ss, "stream", "") or ""),
                        )
                    if readers != 0 and readers != -1:
                        return None
                    return ss

                results = await asyncio.gather(*[_check_and_release(p) for p in stream_node_pairs], return_exceptions=True)
                cleaned = 0
                for res in results:
                    if res is None or isinstance(res, Exception):
                        if isinstance(res, Exception):
                            logger.error(f"[StreamIdle] check failed: {res}")
                        continue
                    ss = res
                    try:
                        await release_stream_session(session, ss, reason="plugin_stream_idle")
                        cleaned += 1

                        # 记录结构化事件日志，便于前端查询"断流了哪些流"
                        if not os.path.exists(LOG_DIR):
                            os.makedirs(LOG_DIR, exist_ok=True)
                        today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
                        log_file = os.path.join(LOG_DIR, f"stream_idle_{today}.log")
                        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S.%f")[:-3]
                        app_v = str(getattr(ss, "app", "") or "").strip()
                        stream_v = str(getattr(ss, "stream", "") or "").strip()
                        node_v = str(getattr(ss, "media_server_id", "") or "").strip()
                        start_v = getattr(ss, "start_time", None)
                        start_s = start_v.isoformat() if start_v and callable(getattr(start_v, "isoformat", None)) else ""
                        dur_s = int((now - start_v).total_seconds()) if start_v else 0
                        line = (
                            f"[{timestamp}] app={app_v} stream={stream_v} node={node_v} "
                            f"start={start_s} duration_s={dur_s} reason=plugin_stream_idle\n"
                        )
                        try:
                            with open(log_file, "a", encoding="utf-8") as f:
                                f.write(line)
                        except Exception as e:
                            logger.warning(f"Error: {e}")
                    except Exception as e:
                        logger.error(f"[StreamIdle] release failed: {e}")
                if cleaned > 0:
                    await session.commit()
                    logger.info(f"[StreamIdle] Cleaned {cleaned} idle sessions")
        except Exception as e:
            logger.error(f"[StreamIdle] Error: {e}")

        await asyncio.sleep(check_interval)

async def start():
    global _task
    logger.info("[StreamIdle] Plugin started")
    _task = asyncio.create_task(check_idle_streams())


async def stop():
    global _task
    if _task and not _task.done():
        _task.cancel()
        try:
            await asyncio.wait_for(_task, timeout=5.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            logger.warning("(asyncio.CancelledError, asyncio.TimeoutError) occurred")
        except Exception as e:
            logger.warning(f"Error: {e}")
    _task = None
