import asyncio
import datetime
from loguru import logger
import os
import time

from sqlalchemy import select  # TECH_DEBT: 直接依赖具体实现，未来改为Protocol接口注入

from app.db.session import AsyncSessionLocal
from app.models.asset import Asset
from app.models.resource import Resource
from app.models.system_setting import SystemSetting
from app.sip.ptz import sip_ptz
from app.sip.server import sip_server


_task: asyncio.Task | None = None

PLUGIN_ID = "ptz_tour"
LOG_DIR = "logs/ptz_tour"


def _gb_token(s: str) -> str:
    return str(s or "").strip().replace(" ", "%20").replace("\t", "_")


def _is_in_schedule(schedule: list | None) -> bool:
    """
    判断当前时间是否在任意一个时间段内。
    None 或空列表表示始终有效。
    schedule 格式: [{"start": "08:00", "end": "18:00"}, ...]
    支持跨天（如 {"start": "22:00", "end": "02:00"}）。
    """
    if not schedule:
        return True
    now = datetime.datetime.now(datetime.timezone.utc)
    current_minutes = now.hour * 60 + now.minute
    for window in schedule:
        try:
            start = window.get("start", "00:00")
            end = window.get("end", "23:59")
            sh, sm = int(start.split(":")[0]), int(start.split(":")[1])
            eh, em = int(end.split(":")[0]), int(end.split(":")[1])
            sm_min = sh * 60 + sm
            em_min = eh * 60 + em
            if sm_min <= em_min:
                if sm_min <= current_minutes <= em_min:
                    return True
            else:
                if current_minutes >= sm_min or current_minutes <= em_min:
                    return True
        except Exception:
            continue
    return False


def _append_ptz_event(*, device_gb: str, channel_gb: str, preset: int, ok: bool, err: str | None = None) -> None:
    try:
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR, exist_ok=True)
        today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        log_file = os.path.join(LOG_DIR, f"ptz_tour_{today}.log")
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        d = _gb_token(device_gb)
        c = _gb_token(channel_gb)
        if ok:
            line = f"[{timestamp}] device={d} channel={c} preset={int(preset)} ok=true\n"
        else:
            err_s = " ".join(str(err or "").split())[:300]
            line = f"[{timestamp}] device={d} channel={c} preset={int(preset)} ok=false err={err_s}\n"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as e:
        logger.warning(f"Error: {e}")


# tour_config 支持两种格式：
#   旧版（向后兼容）: { "<gb_id>": [1, 2, 3] }
#   新版（推荐）    : { "<gb_id>": {
#       "presets": [1, 2, 3],
#       "interval": 10,
#       "schedule": [{"start": "08:00", "end": "18:00"}, ...]
#   } }
_DEFAULT_BASE_CONFIG = {
    "enabled": True,
    "interval": 10,
    "tour_config": {},
}

_cfg_cache: dict = {}
_cfg_ts: float = 0.0
_cfg_ttl_sec: int = 10


async def _get_runtime_cfg() -> dict:
    """
    缓存从 system_settings 里读取的插件运行配置，减少 DB 压力。
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
    interval_max: int | None = None
    merged_tour_config: dict = {}
    for r in rows:
        try:
            import json
            parsed = json.loads(r.setting_value or "{}")
            if not isinstance(parsed, dict):
                continue
        except Exception:
            continue

        any_enabled = any_enabled or bool(parsed.get("enabled", merged.get("enabled", True)))
        try:
            iv = int(parsed.get("interval") or merged.get("interval") or 10)
            interval_max = iv if interval_max is None else max(interval_max, iv)
        except Exception as e:
            logger.warning(f"Error: {e}")
        tc = parsed.get("tour_config") or {}
        if isinstance(tc, dict):
            merged_tour_config.update(tc)

    merged["enabled"] = any_enabled if any_enabled else bool(merged.get("enabled", True))
    if interval_max is not None:
        merged["interval"] = interval_max
    if merged_tour_config:
        merged["tour_config"] = merged_tour_config
    _cfg_cache = merged
    _cfg_ts = now
    return merged


async def run_tour():
    while True:
        try:
            cfg = await _get_runtime_cfg()
            if not cfg or not cfg.get("enabled", True):
                await asyncio.sleep(2)
                continue

            interval = int(cfg.get("interval") or _DEFAULT_BASE_CONFIG["interval"] or 10)
            interval = max(1, min(3600, interval))
            tour_config = cfg.get("tour_config") or {}
            if not isinstance(tour_config, dict) or not tour_config:
                await asyncio.sleep(5)
                continue

            async with AsyncSessionLocal() as session:
                for device_id, channel_cfg in tour_config.items():
                    if not device_id:
                        continue

                    # 兼容旧版格式（直接是 list）
                    if isinstance(channel_cfg, list):
                        presets = channel_cfg
                        channel_interval = interval
                        schedule = None
                    else:
                        presets = channel_cfg.get("presets") if isinstance(channel_cfg, dict) else channel_cfg
                        channel_interval = int(channel_cfg.get("interval", interval) if isinstance(channel_cfg, dict) else interval)
                        schedule = channel_cfg.get("schedule") if isinstance(channel_cfg, dict) else None

                    if not isinstance(presets, list) or not presets:
                        continue

                    # 时间段过滤
                    if not _is_in_schedule(schedule):
                        continue

                    stmt = select(Asset).where(Asset.gb_id == str(device_id).strip())
                    result = await session.execute(stmt)
                    asset = result.scalars().first()

                    if not asset or asset.status != 1:
                        continue

                    stmt2 = select(Resource).where(Resource.gb_id == str(device_id).strip())
                    r2 = await session.execute(stmt2)
                    resource = r2.scalars().first()
                    if not resource:
                        continue

                    if not asset.ip_addr:
                        continue

                    presets_clean: list[int] = []
                    for p in presets:
                        try:
                            pv = int(p)
                            if 1 <= pv <= 255:
                                presets_clean.append(pv)
                        except Exception:
                            continue
                    if not presets_clean:
                        continue

                    # 按通道级 interval round-robin
                    idx = int(time.time() / channel_interval) % len(presets_clean)
                    preset_id = presets_clean[idx]

                    transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
                    if transport is None:
                        continue
                    if not sip_ptz:
                        continue

                    try:
                        await sip_ptz.send_preset(
                            asset,
                            resource,
                            ((asset.ip_addr, int(asset.port)), asset.transport, transport),
                            preset_id,
                        )
                        _append_ptz_event(
                            device_gb=str(asset.gb_id or ""),
                            channel_gb=str(resource.gb_id or ""),
                            preset=int(preset_id),
                            ok=True,
                        )
                    except Exception as ex:
                        logger.error(
                            f"[PTZTour] send_preset device={asset.gb_id} preset={preset_id}: {ex}"
                        )
                        _append_ptz_event(
                            device_gb=str(asset.gb_id or ""),
                            channel_gb=str(resource.gb_id or ""),
                            preset=int(preset_id),
                            ok=False,
                            err=str(ex),
                        )

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"[PTZTour] Error: {e}")

        await asyncio.sleep(interval)


async def start():
    global _task
    logger.info("[PTZTour] Service started (with schedule support)")
    _task = asyncio.create_task(run_tour())


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