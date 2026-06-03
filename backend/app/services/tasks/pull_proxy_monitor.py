import asyncio
import datetime
import os

import httpx  # M-16 同步requests替换为异步httpx
from sqlalchemy import select  # TECH_DEBT: 直接依赖具体实现，未来改为Protocol接口注入

from app.core.config import settings
from app.core.media_nodes import get_all_media_from_nodes
from app.core.media_nodes_db import get_active_media_node_id, get_db_media_node_by_id, select_best_db_node
from app.db.session import AsyncSessionLocal
from app.models.access_source import AccessSource
from app.services.zlm_stream_control import close_zlm_stream
from app.utils.stream_name import normalize_stream_name

_task: asyncio.Task | None = None
LOG_DIR = "logs/pull_proxy_monitor"

# M-16 同步requests替换为异步httpx — 共享httpx客户端
_http_client: httpx.AsyncClient | None = None


async def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=5.0)
    return _http_client


def _tok(s: str) -> str:
    return str(s or "").strip().replace(" ", "%20").replace("\t", "_")


def _append_pull_proxy_event(*, evt: str, stream: str, ok: bool, err: str | None = None) -> None:
    """evt: auto_stop | auto_retry（不写完整上游 URL）"""
    try:
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR, exist_ok=True)
        today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        log_file = os.path.join(LOG_DIR, f"pull_proxy_monitor_{today}.log")
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        st = _tok(stream)
        ev = str(evt or "").strip()
        if ev not in {"auto_stop", "auto_retry"}:
            return
        if ok:
            line = f"[{timestamp}] evt={ev} stream={st} ok=true\n"
        else:
            err_s = " ".join(str(err or "").split())[:300]
            line = f"[{timestamp}] evt={ev} stream={st} ok=false err={err_s}\n"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as e:
        logger.warning(f"Error: {e}")


def _parse_iso(dt_str: str | None) -> datetime.datetime | None:
    if not dt_str:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(dt_str)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=datetime.timezone.utc)
        return parsed.astimezone(datetime.timezone.utc)
    except Exception:
        return None


def _is_proxy_origin_type(origin_type: int | str | None) -> bool:
    try:
        v = int(origin_type or 0)
    except Exception:
        v = 0
    return v in {5, 6}


def _sanitize_target_url(url: str) -> str:
    s = (url or "").strip()
    if not s:
        return ""
    if "://" not in s:
        return s[:200]
    scheme, rest = s.split("://", 1)
    if "@" in rest and ":" in rest.split("@", 1)[0]:
        userinfo, after = rest.split("@", 1)
        username = userinfo.split(":", 1)[0]
        return f"{scheme}://{username}:***@{after}"[:200]
    return s[:200]


def _build_target_url(source: AccessSource) -> str:
    protocol = (source.protocol or "").upper()
    if protocol == "RTSP":
        auth = ""
        if source.username:
            auth = source.username
            if source.password:
                auth = f"{auth}:{source.password}"
            auth = f"{auth}@"
        path = (source.path or "").lstrip("/")
        return f"rtsp://{auth}{source.host}:{source.port or 554}/{path}"
    if protocol == "ONVIF":
        direct = (source.extra or {}).get("rtsp_url")
        if direct:
            return str(direct)
        auth = ""
        if source.username:
            auth = source.username
            if source.password:
                auth = f"{auth}:{source.password}"
            auth = f"{auth}@"
        path = (source.path or "Streaming/Channels/101").lstrip("/")
        return f"rtsp://{auth}{source.host}:{source.port or 554}/{path}"
    if protocol == "SDK":
        direct = (source.extra or {}).get("play_url")
        if not direct:
            raise ValueError("SDK integration source requires extra.play_url")
        return str(direct)
    raise ValueError("Only RTSP/ONVIF/SDK support pull proxy")


async def _select_proxy_node(db) -> tuple[str, int, str, str, int, str]:
    from app.core.config import settings as _settings
    from loguru import logger

    proxy_host = _settings.MEDIA_SERVER_HOST
    proxy_http_port = _settings.MEDIA_SERVER_HTTP_PORT
    proxy_secret = _settings.MEDIA_SERVER_SECRET
    public_host = _settings.STREAM_PUBLIC_HOST
    public_http_port = _settings.STREAM_PUBLIC_HTTP_PORT
    selection_reason = "global"
    try:
        active_id = await get_active_media_node_id(db)
        db_node = await get_db_media_node_by_id(db, active_id) if active_id else None
        if not db_node:
            db_node = await select_best_db_node(db)
        if db_node:
            proxy_host = db_node.host or proxy_host
            proxy_http_port = db_node.http_port or proxy_http_port
            proxy_secret = db_node.secret or proxy_secret
            public_host = db_node.public_host or public_host
            public_http_port = db_node.public_http_port or public_http_port
            selection_reason = "active" if (active_id and db_node.id == active_id) else "auto"
    except Exception as e:
        logger.warning(f"Error: {e}")
    return proxy_host, int(proxy_http_port), proxy_secret, public_host, int(public_http_port), selection_reason


# M-16 同步requests替换为异步httpx
async def _add_stream_proxy(proxy_host: str, proxy_http_port: int, proxy_secret: str, stream_name: str, target_url: str) -> None:
    proxy_url = f"http://{proxy_host}:{proxy_http_port}/index/api/addStreamProxy"
    # 添加try-except避免ZLM不可达时崩溃
    try:
        client = await _get_http_client()
        response = await client.get(
            proxy_url,
            params={
                "secret": proxy_secret,
                "vhost": "__defaultVhost__",
                "app": "live",
                "stream": stream_name,
                "url": target_url,
                "enable_hls": 1,
                "enable_mp4": 0,
                "rtp_type": 0,
            },
        )
    except Exception as e:
        raise RuntimeError(f"addStreamProxy request failed: {e}") from e
    if response.status_code >= 400:
        raise RuntimeError(f"addStreamProxy http={response.status_code}")
    body = response.json()
    if body.get("code") not in {0, "0"}:
        raise RuntimeError(f"addStreamProxy code={body.get('code')} msg={body.get('msg') or ''}".strip())


async def _run_loop():
    interval = max(2, int(getattr(settings, "PULL_PROXY_MONITOR_INTERVAL_SECONDS", 10) or 10))
    grace = max(0, int(getattr(settings, "PULL_PROXY_OFFLINE_GRACE_SECONDS", 20) or 20))
    auto_retry = bool(getattr(settings, "PULL_PROXY_AUTO_RETRY_ENABLED", True))
    max_retry = max(0, int(getattr(settings, "PULL_PROXY_AUTO_RETRY_MAX_COUNT", 5) or 5))
    while True:
        if not bool(getattr(settings, "PULL_PROXY_MONITOR_ENABLED", True)):
            await asyncio.sleep(max(2, interval))
            continue
        now = datetime.datetime.now(datetime.timezone.utc)
        now_iso = now.isoformat()
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(AccessSource).where(
                        AccessSource.enabled == True,
                        AccessSource.protocol.in_(["RTSP", "ONVIF", "SDK"]),
                    )
                )
                sources = result.scalars().all()
                if not sources:
                    await asyncio.sleep(interval)
                    continue
                stream_to_source = {}
                for s in sources:
                    stream_name = normalize_stream_name(s.stream_name or s.name or s.id, fallback=s.id)
                    stream_to_source[stream_name] = s

                media_list = await asyncio.to_thread(get_all_media_from_nodes)
                running = {}
                for item in (media_list or []):
                    try:
                        if str(item.get("app") or "") != "live":
                            continue
                        stream = str(item.get("stream") or "")
                        if stream in stream_to_source and _is_proxy_origin_type(item.get("originType", item.get("origin_type"))):
                            running[stream] = item
                    except Exception:
                        continue

                changed = False
                for stream_name, source in stream_to_source.items():
                    extra = source.extra if isinstance(getattr(source, "extra", None), dict) else {}
                    desired_state = str(extra.get("desired.state") or "running").strip().lower()
                    is_running = stream_name in running
                    extra["runtime.proxy.checked_at"] = now_iso
                    extra["runtime.proxy.stream"] = stream_name
                    extra["runtime.proxy.is_running"] = bool(is_running)

                    if is_running:
                        item = running.get(stream_name) or {}
                        extra["runtime.proxy.last_seen_at"] = now_iso
                        extra["runtime.proxy.last_seen_node_id"] = item.get("node_id") or ""
                        extra["runtime.proxy.reader_count"] = item.get("readerCount", item.get("reader_count", 0))
                        extra["runtime.proxy.bytes_speed"] = item.get("bytesSpeed", item.get("bytes_speed", 0))
                        extra["runtime.proxy.origin_type"] = item.get("originType", item.get("origin_type", 0))
                        extra["runtime.proxy.origin_url"] = _sanitize_target_url(str(item.get("originUrl", item.get("origin_url", "")) or ""))
                        extra["runtime.proxy.unhealthy"] = False
                        extra["runtime.proxy.unhealthy_reason"] = ""
                    else:
                        last_seen = _parse_iso(str(extra.get("runtime.proxy.last_seen_at") or ""))
                        missing_seconds = int((now - last_seen).total_seconds()) if last_seen else grace + 1
                        if desired_state == "running" and missing_seconds > grace:
                            extra["runtime.proxy.unhealthy"] = True
                            extra["runtime.proxy.unhealthy_reason"] = f"expected_running_but_missing missing_seconds={missing_seconds}"
                            extra["runtime.proxy.last_missing_at"] = now_iso
                        else:
                            extra["runtime.proxy.unhealthy"] = False
                            extra["runtime.proxy.unhealthy_reason"] = ""

                    if desired_state == "stopped" and is_running:
                        last_auto_stop = _parse_iso(str(extra.get("runtime.proxy.last_auto_stop_at") or ""))
                        if not last_auto_stop or (now - last_auto_stop).total_seconds() >= max(5, interval * 3):
                            try:
                                await close_zlm_stream("live", stream_name, None)
                                extra["runtime.proxy.last_auto_stop_at"] = now_iso
                                extra["runtime.proxy.last_auto_stop_ok"] = True
                                extra["runtime.proxy.last_auto_stop_message"] = ""
                                _append_pull_proxy_event(evt="auto_stop", stream=stream_name, ok=True)
                            except Exception as e:
                                extra["runtime.proxy.last_auto_stop_at"] = now_iso
                                extra["runtime.proxy.last_auto_stop_ok"] = False
                                extra["runtime.proxy.last_auto_stop_message"] = str(e)[:200]
                                _append_pull_proxy_event(evt="auto_stop", stream=stream_name, ok=False, err=str(e))

                    if auto_retry and desired_state == "running" and (not is_running):
                        retry_count = int(extra.get("runtime.proxy.retry_count") or 0)
                        last_retry_at = _parse_iso(str(extra.get("runtime.proxy.last_retry_at") or ""))
                        if retry_count < max_retry and (not last_retry_at or (now - last_retry_at).total_seconds() >= max(5, interval * 3)):
                            try:
                                target_url = _build_target_url(source)
                                proxy_host, proxy_http_port, proxy_secret, _, _, selection_reason = await _select_proxy_node(session)
                                await _add_stream_proxy(proxy_host, proxy_http_port, proxy_secret, stream_name, target_url)
                                extra["runtime.proxy.last_retry_at"] = now_iso
                                extra["runtime.proxy.retry_count"] = retry_count + 1
                                extra["runtime.proxy.last_retry_ok"] = True
                                extra["runtime.proxy.last_retry_error"] = ""
                                extra["runtime.proxy.last_start_node"] = f"{proxy_host}:{proxy_http_port}"
                                extra["runtime.proxy.last_start_reason"] = f"auto_retry reason={selection_reason}"
                                extra["runtime.proxy.last_target_url"] = _sanitize_target_url(target_url)
                                _append_pull_proxy_event(evt="auto_retry", stream=stream_name, ok=True)
                            except Exception as e:
                                extra["runtime.proxy.last_retry_at"] = now_iso
                                extra["runtime.proxy.retry_count"] = retry_count + 1
                                extra["runtime.proxy.last_retry_ok"] = False
                                extra["runtime.proxy.last_retry_error"] = str(e)[:200]
                                _append_pull_proxy_event(evt="auto_retry", stream=stream_name, ok=False, err=str(e))

                    source.extra = dict(extra)
                    changed = True

                if changed:
                    try:
                        await session.commit()
                    except Exception:
                        await session.rollback()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"Error: {e}")
        await asyncio.sleep(interval)


async def start():
    global _task
    if _task and not _task.done():
        return
    _task = asyncio.create_task(_run_loop())


async def stop():
    global _task, _http_client
    if not _task:
        return
    _task.cancel()
    try:
        await asyncio.wait_for(_task, timeout=5.0)
    except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
        logger.warning("(asyncio.CancelledError, asyncio.TimeoutError, Exception) occurred")
    _task = None
    # M-16 关闭共享httpx客户端
    if _http_client and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None



