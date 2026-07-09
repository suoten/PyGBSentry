"""System-setting cache backed by the ``system_settings`` table.

Reads are cached in-process with a short TTL so the SIP hot loop does not hit
the database on every message. All functions are async and never raise — a
missing/failed read returns ``default``.

# FIX: [2026-07-03] 增加 _MAX_CACHE_SIZE 容量上限和 evict_expired 清理逻辑,
# 防止高频写入场景下 _cache 字典无限增长导致内存泄漏 [可靠性工程师]
"""
from __future__ import annotations

import time
from typing import Any, Optional

from loguru import logger

_cache: dict[str, tuple[Any, float]] = {}
_TTL_SECONDS = 30.0
# FIX: [2026-07-03] 缓存条目上限，超过时按 LRU 策略驱逐最旧条目 [可靠性工程师]
_MAX_CACHE_SIZE = 500


async def get_system_setting(session, key: str, default: Any = None) -> Any:
    """Return the system setting ``key`` (cached for ~30s)."""
    now = time.time()
    hit = _cache.get(key)
    if hit is not None and (now - hit[1]) < _TTL_SECONDS:
        return hit[0]
    try:
        from app.models.system_setting import SystemSetting
        from sqlalchemy import select
        result = await session.execute(select(SystemSetting).where(SystemSetting.setting_key == key))
        row = result.scalars().first()
        value = row.setting_value if row is not None else default
    except Exception as e:
        logger.debug(f"settings_cache: read '{key}' failed: {e}")
        value = default
    _cache[key] = (value, now)
    _evict_if_needed()
    return value


def _evict_if_needed() -> None:
    """# FIX: [2026-07-03] 缓存超限时驱逐过期和最旧条目，防止内存泄漏 [可靠性工程师]"""
    if len(_cache) <= _MAX_CACHE_SIZE:
        return
    # 先驱逐已过期条目
    now = time.time()
    expired = [k for k, (_, ts) in _cache.items() if (now - ts) >= _TTL_SECONDS]
    for k in expired:
        _cache.pop(k, None)
    # 如果仍超限，按时间戳排序驱逐最旧条目
    if len(_cache) > _MAX_CACHE_SIZE:
        sorted_keys = sorted(_cache.items(), key=lambda x: x[1][1])
        over = len(_cache) - _MAX_CACHE_SIZE
        for k, _ in sorted_keys[:over]:
            _cache.pop(k, None)


async def set_system_setting(session, key: str, value: str) -> None:
    """Persist and cache a system setting."""
    try:
        from app.models.system_setting import SystemSetting
        from sqlalchemy import select
        result = await session.execute(select(SystemSetting).where(SystemSetting.setting_key == key))
        row = result.scalars().first()
        if row is None:
            row = SystemSetting(setting_key=key, setting_value=str(value))
            session.add(row)
        else:
            row.setting_value = str(value)
        await session.commit()
    except Exception as e:
        logger.debug(f"settings_cache: write '{key}' failed: {e}")
    _cache[key] = (value, time.time())
    _evict_if_needed()


def invalidate(key: Optional[str] = None) -> None:
    """Drop the cache entry for ``key`` (or the whole cache when ``None``)."""
    if key is None:
        _cache.clear()
    else:
        _cache.pop(key, None)
