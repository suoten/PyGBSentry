import asyncio
import datetime
import os
import urllib.parse
from pathlib import Path

import requests
from sqlalchemy import select  # TECH_DEBT: 直接依赖具体实现，未来改为Protocol接口注入

from app.core.config import settings
from app.core.media_nodes_db import get_db_media_node_by_id
from app.db.session import AsyncSessionLocal
from app.models.record import Record
from loguru import logger

_task: asyncio.Task | None = None
LOG_DIR = "logs/record_index_verifier"


def _append_riv_event(*, record_id: str, ok: bool, code: int | None, note: str, err: str | None = None) -> None:
    try:
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR, exist_ok=True)
        today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        log_file = os.path.join(LOG_DIR, f"record_index_verifier_{today}.log")
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        rid = str(record_id or "").strip().replace(" ", "%20")
        code_s = str(int(code)) if code is not None else "-"
        nt = str(note or "ok").strip().replace(" ", "_")[:32]
        if ok:
            line = f"[{timestamp}] record_id={rid} ok=true code={code_s} note={nt}\n"
        else:
            err_s = " ".join(str(err or "").split())[:300]
            line = f"[{timestamp}] record_id={rid} ok=false code={code_s} err={err_s}\n"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as e:
        logger.warning(f"Error: {e}")


def _verify_path(url_or_path: str, fallback_path: str | None = None) -> tuple[bool, int | None, str]:
    value = (url_or_path or "").strip()
    if not value and fallback_path:
        value = str(fallback_path).strip()
    if not value:
        return False, None, "empty"
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme in {"http", "https"}:
        try:
            resp = requests.head(value, timeout=5, allow_redirects=True)
            code = int(resp.status_code)
            ok = 200 <= code < 400
            return ok, code, "" if ok else f"http={code}"
        except Exception as e:
            return False, None, str(e)[:200]
    p = Path(value)
    if not p.is_absolute() and fallback_path:
        p = Path(str(fallback_path))
    ok = p.exists() and p.is_file()
    return ok, None, "" if ok else "file_missing"


def _join_public_base(public_host: str, public_http_port: int) -> str:
    host = (public_host or "").strip()
    port = int(public_http_port or 0)
    if not host:
        return ""
    if port in {0, 80}:
        return f"http://{host}"
    return f"http://{host}:{port}"


def _derive_record_path(file_path: str, zlm_file_path: str | None) -> str:
    url = (file_path or "").strip()
    if url:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme in {"http", "https"}:
            path = parsed.path or ""
            q = parsed.query or ""
            return f"{path}?{q}" if q else path
        if "/record/" in url:
            idx = url.find("/record/")
            return url[idx:]
    fp = (str(zlm_file_path or "")).strip()
    if fp and "/record/" in fp:
        idx = fp.find("/record/")
        return fp[idx:]
    return ""


async def _run_loop():
    interval = max(5, int(getattr(settings, "RECORD_INDEX_VERIFY_INTERVAL_SECONDS", 60) or 60))
    batch_size = max(1, min(int(getattr(settings, "RECORD_INDEX_VERIFY_BATCH_SIZE", 50) or 50), 200))
    max_age_days = max(1, int(getattr(settings, "RECORD_INDEX_VERIFY_MAX_AGE_DAYS", 30) or 30))
    while True:
        if not bool(getattr(settings, "RECORD_INDEX_VERIFY_ENABLED", True)):
            await asyncio.sleep(interval)
            continue
        try:
            cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=max_age_days)
            cutoff_naive = cutoff.replace(tzinfo=None)
            now_naive = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
            async with AsyncSessionLocal() as session:
                node_cache: dict[str, object] = {}
                stmt = (
                    select(Record)
                    .where(Record.created_at >= cutoff_naive)
                    .order_by(Record.created_at.desc())
                    .limit(batch_size)
                )
                rows = (await session.execute(stmt)).scalars().all()
                if not rows:
                    await asyncio.sleep(interval)
                    continue

                changed = False
                for r in rows:
                    if getattr(r, "url_checked_at", None) and getattr(r, "url_ok", True):
                        continue
                    rid = str(getattr(r, "id", "") or "").strip()
                    file_path = str(r.file_path or "")
                    ok, code, err = await asyncio.to_thread(_verify_path, file_path, getattr(r, "zlm_file_path", None))
                    if (not ok) and (urllib.parse.urlparse(file_path.strip()).scheme in {"http", "https"}):
                        node_id = str(getattr(r, "media_node_id", "") or "").strip()
                        if node_id:
                            node = node_cache.get(node_id)
                            if node is None:
                                node = await get_db_media_node_by_id(session, node_id)
                                node_cache[node_id] = node
                            if node:
                                base = _join_public_base(getattr(node, "public_host", ""), int(getattr(node, "public_http_port", 0) or 0))
                                path = _derive_record_path(file_path, getattr(r, "zlm_file_path", None))
                                if base and path:
                                    if not path.startswith("/"):
                                        path = f"/{path}"
                                    candidate = f"{base}{path}"
                                    ok2, code2, err2 = await asyncio.to_thread(_verify_path, candidate, None)
                                    if ok2:
                                        r.file_path = candidate
                                        ok, code, err = ok2, code2, "auto_repaired"
                    r.url_checked_at = now_naive
                    r.url_ok = bool(ok)
                    r.url_status_code = code
                    r.url_error = err
                    changed = True
                    if ok:
                        note = "auto_repaired" if str(err or "") == "auto_repaired" else "ok"
                        _append_riv_event(
                            record_id=rid, ok=True, code=code, note=note, err=None
                        )
                    else:
                        _append_riv_event(
                            record_id=rid, ok=False, code=code, note="fail", err=str(err or "")
                        )

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
    global _task
    if not _task:
        return
    _task.cancel()
    try:
        await asyncio.wait_for(_task, timeout=5.0)
    except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
        logger.warning("(asyncio.CancelledError, asyncio.TimeoutError, Exception) occurred")
    _task = None


