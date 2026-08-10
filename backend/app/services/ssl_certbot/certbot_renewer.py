import asyncio
from loguru import logger
from datetime import datetime, timezone
from app.services.ssl_certbot.certbot_config import load_certbot_settings
from app.services.ssl_certbot.cert_checker import CertStatus
from app.services.ssl_certbot.certbot_manager import force_renew, get_status



_task: asyncio.Task | None = None


async def _renew_loop() -> None:
    cfg = load_certbot_settings()
    if not cfg.is_effective:
        return
    interval_s = cfg.renew_check_interval_hours * 3600
    while True:
        try:
            await asyncio.sleep(interval_s)
            now_hour = datetime.now(timezone.utc).hour
            if not (cfg.renew_window_start_hour <= now_hour < cfg.renew_window_end_hour):
                continue
            cert_info = await get_status()
            if cert_info.status in (CertStatus.EXPIRING_SOON, CertStatus.EXPIRED, CertStatus.MISSING):
                logger.info("SSL certbot renewer: certificate needs renewal (status=%s), triggering ...", cert_info.status)
                success, msg = await force_renew()
                if success:
                    logger.info("SSL certbot renewer: %s", msg)
                else:
                    logger.warning("SSL certbot renewer: %s", msg)
            else:
                logger.debug("SSL certbot renewer: certificate OK (status=%s, %d days remaining)", cert_info.status, cert_info.remaining_days)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("SSL certbot renewer error: %s, retrying in 60s", e)
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break


async def start() -> None:
    global _task
    cfg = load_certbot_settings()
    if not cfg.is_effective:
        return
    _task = asyncio.create_task(_renew_loop())
    logger.info("SSL certbot renewer: background task started (check every %dh, window %d-%dh)",
                cfg.renew_check_interval_hours, cfg.renew_window_start_hour, cfg.renew_window_end_hour)


async def stop() -> None:
    global _task
    if _task and not _task.done():
        _task.cancel()
        try:
            await asyncio.wait_for(_task, timeout=5.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            logger.warning("(asyncio.CancelledError, asyncio.TimeoutError) occurred")
    _task = None
    logger.info("SSL certbot renewer: stopped")
