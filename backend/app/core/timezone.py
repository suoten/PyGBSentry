import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.config import settings
from loguru import logger


def get_app_timezone_name() -> str:
    tz_name = str(getattr(settings, "APP_TIMEZONE", "") or "").strip()
    if not tz_name:
        return "Asia/Shanghai"
    try:
        ZoneInfo(tz_name)
        return tz_name
    except Exception:
        return "Asia/Shanghai"


def get_app_timezone() -> ZoneInfo:
    return ZoneInfo(get_app_timezone_name())


def now_in_app_timezone() -> datetime:
    return datetime.now(get_app_timezone())


def apply_process_timezone() -> str:
    tz_name = get_app_timezone_name()
    os.environ["TZ"] = tz_name
    try:
        time.tzset()
    except Exception:
        # Windows does not support time.tzset(); silently ignore.
        logger.debug(f"time.tzset() unsupported on this platform; TZ env set to {tz_name}")
    return tz_name
