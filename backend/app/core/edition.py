"""Edition detection and commercial feature separation.

Centralizes all ``APP_EDITION`` checks so that the rest of the codebase never
needs to inspect the raw config value. This keeps the open-source / commercial
boundary in one auditable place.

Usage::

    from app.core.edition import is_oss_edition, is_server_edition

    if is_server_edition():
        # server/commercial-only logic
        ...
    else:
        # open-source fallback
        ...
"""
from __future__ import annotations

from functools import lru_cache

from app.core.config import settings


@lru_cache(maxsize=1)
def _edition() -> str:
    """Return the normalised edition string (lower-case)."""
    return (settings.APP_EDITION or "oss").strip().lower()


def is_oss_edition() -> bool:
    """True when running as the open-source edition (the default)."""
    return _edition() in ("", "oss", "opensource", "open-source")


def is_server_edition() -> bool:
    """True when running as the server / commercial edition."""
    return _edition() in ("server", "enterprise", "pro", "commercial")


def edition_label() -> str:
    """Human-readable label for logging / health-check responses."""
    return "server" if is_server_edition() else "oss"


# Feature flags — each commercial feature has a dedicated guard so that
# individual features can be enabled/disabled independently in the future.

def has_plugin_marketplace() -> bool:
    """Plugin Marketplace is a server-edition feature; OSS exposes 501 stubs."""
    return bool(is_server_edition()) and settings.PLUGIN_MARKETPLACE_ENABLED


def has_license_verification() -> bool:
    """Paid-plugin license verification is a server-edition feature."""
    return bool(is_server_edition())


def has_quota_enforcement() -> bool:
    """Device/channel quota enforcement is a server-edition feature.

    OSS edition does not enforce quotas — :func:`commercial_guard.get_effective_limits`
    returns ``(0, 0)`` meaning "unlimited".
    """
    return bool(is_server_edition())
