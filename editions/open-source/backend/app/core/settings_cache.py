from typing import Optional, Any
from cachetools import TTLCache
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.system_setting import SystemSetting

# Global cache for system settings
# maxsize=500, ttl=60 seconds
_settings_cache = TTLCache(maxsize=500, ttl=60)

async def get_system_setting(db: AsyncSession, key: str, default: Any = None) -> Optional[str]:
    """
    Fetch a system setting from the database, utilizing a local TTLCache to reduce DB load.
    Cache expires every 60 seconds.
    """
    if key in _settings_cache:
        return _settings_cache[key]

    stmt = select(SystemSetting).where(SystemSetting.setting_key == key)
    result = await db.execute(stmt)
    row = result.scalars().first()

    val = row.setting_value if row and row.setting_value is not None else default  # FIXED: setting_value 可能为 None
    if val is not None:
        _settings_cache[key] = val
    return val

async def invalidate_system_setting(key: str) -> None:
    """
    Invalidate a specific key in the cache (e.g., after an update).
    """
    if key in _settings_cache:
        del _settings_cache[key]
