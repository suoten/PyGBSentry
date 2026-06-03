from app.core.config import settings
from app.models.stream_session import StreamSession
from app.db.session import AsyncSessionLocal
from sqlalchemy import select  # TECH_DEBT: 直接依赖具体实现，未来改为Protocol接口注入
import asyncio
from loguru import logger
import os
import datetime
import time
import json
import importlib

from app.models.system_setting import SystemSetting



_task: asyncio.Task | None = None

PLUGIN_ID = "timelapse"

LOG_DIR = "logs/timelapse"

_DEFAULT_BASE_CONFIG = {
    "enabled": True,
    "output_dir": "timelapse",
    "snap_interval": 300,  # 5 minutes
    "zlm_flv_base": "",
}

_cfg_cache: dict = {}
_cfg_ts: float = 0.0
_cfg_ttl_sec: int = 10


async def _get_runtime_cfg() -> dict:
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
    interval_max: int | None = None
    zlm_flv_base = ""
    for r in rows:
        try:
            parsed = json.loads(r.setting_value or "{}")
            if not isinstance(parsed, dict):
                continue
            if bool(parsed.get("enabled", False)):
                any_enabled = True
            if parsed.get("snap_interval") is not None:
                try:
                    ci = int(parsed.get("snap_interval") or 0)
                    if ci > 0:
                        interval_max = ci if interval_max is None else max(interval_max, ci)
                except Exception as e:
                    logger.warning(f"Error: {e}")
            if parsed.get("output_dir") and not merged.get("output_dir"):
                merged["output_dir"] = str(parsed.get("output_dir") or "").strip()
            if not zlm_flv_base and parsed.get("zlm_flv_base"):
                zlm_flv_base = str(parsed.get("zlm_flv_base") or "").strip()
        except Exception:
            continue

    merged["enabled"] = any_enabled if any_enabled else bool(merged.get("enabled", True))
    if interval_max is not None:
        merged["snap_interval"] = interval_max
    if zlm_flv_base:
        merged["zlm_flv_base"] = zlm_flv_base

    _cfg_cache = merged
    _cfg_ts = now
    return _cfg_cache

async def capture_snapshots():
    """
    Periodically capture snapshots from active streams
    """
    while True:
        cfg = await _get_runtime_cfg()
        enabled = bool(cfg.get("enabled", True))
        output_dir = str(cfg.get("output_dir") or _DEFAULT_BASE_CONFIG["output_dir"]).strip()
        snap_interval = int(cfg.get("snap_interval") or _DEFAULT_BASE_CONFIG["snap_interval"])
        snap_interval = max(10, min(86400, snap_interval))
        zlm_flv_base = str(cfg.get("zlm_flv_base") or "").strip()

        if not enabled:
            await asyncio.sleep(snap_interval)
            continue

        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        try:
            async with AsyncSessionLocal() as session:
                stmt = select(StreamSession).where(StreamSession.stream.isnot(None))
                result = await session.execute(stmt)
                streams = result.scalars().all()

                for stream in streams:
                    await _snap(stream, output_dir, zlm_flv_base)

        except Exception as e:
            logger.error(f"[Timelapse] Error: {e}")

        await asyncio.sleep(snap_interval)

async def _snap(stream, output_dir: str, zlm_flv_base: str):
    asset_id = getattr(stream, "asset_id", None)
    if not asset_id:
        return
    if zlm_flv_base:
        stream_url = f"{zlm_flv_base.rstrip('/')}/live/{stream.stream}.live.flv"
    else:
        stream_url = (
            f"http://{settings.MEDIA_SERVER_HOST}:{settings.MEDIA_SERVER_HTTP_PORT}"
            f"/live/{stream.stream}.live.flv"
        )
    device_dir = os.path.join(output_dir, str(asset_id))
    if not os.path.exists(device_dir):
        os.makedirs(device_dir)

    now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = os.path.join(device_dir, f"{now}.jpg")

    # Use OpenCV to snap
    loop = asyncio.get_running_loop()
    ok = await loop.run_in_executor(None, _cv_snap, stream_url, file_path)
    if ok:
        try:
            if not os.path.exists(LOG_DIR):
                os.makedirs(LOG_DIR, exist_ok=True)
            today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
            log_file = os.path.join(LOG_DIR, f"timelapse_{today}.log")
            timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S.%f")[:-3]
            rel = os.path.relpath(file_path, output_dir).replace("\\", "/")
            app_v = str(getattr(stream, "app", "") or "").strip()
            stream_v = str(getattr(stream, "stream", "") or "").strip()
            asset_v = str(getattr(stream, "asset_id", "") or "").strip()
            line = (
                f"[{timestamp}] app={app_v} stream={stream_v} asset_id={asset_v} file={rel}\n"
            )
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception as e:
            logger.warning(f"Error: {e}")

def _cv_snap(url, path):
    try:
        cv2 = importlib.import_module("cv2")
    except Exception:
        # opencv-python 未安装时，直接跳过
        return False

    # 显式指定 FFMPEG 后端，避免 HTTP 拒绝连接时回退到 CAP_IMAGES 引发断言异常
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    if cap.isOpened():
        ret, frame = cap.read()
        if ret:
            cv2.imwrite(path, frame)
    cap.release()
    try:
        return os.path.exists(path)
    except Exception:
        return False

async def start():
    global _task
    logger.info("[Timelapse] Plugin started")
    _task = asyncio.create_task(capture_snapshots())


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