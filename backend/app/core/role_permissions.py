"""Role permission-code parsing helpers (RBAC).

Roles store their granted permission codes in a single text column
(``Role.permission_codes``). This module parses that text into a normalised
set of lowercase permission codes, supporting several storage conventions:

    * comma-separated:  ``"device.view,device.control,alarm.ack"``
    * JSON array:       ``'["device.view","alarm.ack"]'``
    * wildcard:         ``"*"``  (grants every permission)

The ``role_code`` argument is used to expand a small set of legacy role names
(owner / admin / operator) into their canonical permission codes for backward
compatibility with deployments that predate fine-grained RBAC.
"""
from __future__ import annotations

import json
from typing import Iterable

from loguru import logger

# Wildcard token granting every permission.
WILDCARD = "*"

# Legacy role-name → permission-code expansion. Applied only when the role's
# ``permission_codes`` column is empty, so explicit grants always take precedence.
_LEGACY_ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "owner": (WILDCARD,),
    "admin": (WILDCARD,),
    "operator": (
        "device.view", "device.control", "channel.view",
        "record.view", "record.download", "alarm.view", "alarm.ack",
        "ptz.control", "stream.play", "stream.playback",
    ),
    "viewer": ("device.view", "channel.view", "record.view", "alarm.view", "stream.play", "stream.playback"),
}

# Public alias for backward-compatible role-permission lookup (used by PTZ
# permission helper and tests). Mirrors the internal legacy expansion table.
DEFAULT_ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = _LEGACY_ROLE_PERMISSIONS


def _normalize(code: str) -> str:
    return (code or "").strip().lower()


def parse_permission_codes(raw: str | None, role_code: str | None = None) -> set[str]:
    """Parse a role's permission-codes text into a normalised set.

    Args:
        raw:       The raw ``Role.permission_codes`` column value.
        role_code: The role's code, used to expand legacy role names when
                   ``raw`` is empty.

    Returns:
        A set of lowercase permission codes. Contains ``"*"`` if the role has
        wildcard access. Never raises — malformed JSON falls back to comma
        parsing, and an all-empty result yields the empty set.
    """
    codes: set[str] = set()
    text = (raw or "").strip()
    if not text:
        # Fall back to legacy role-name expansion.
        legacy = _LEGACY_ROLE_PERMISSIONS.get((role_code or "").strip().lower(), ())
        return set(legacy)

    # Try JSON array first.
    if text.startswith("["):
        try:
            items = json.loads(text)
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, str):
                        n = _normalize(item)
                        if n:
                            codes.add(n)
                if codes:
                    return codes
        except (json.JSONDecodeError, TypeError) as e:
            logger.debug(f"parse_permission_codes: JSON parse failed ({e}), falling back to comma split")

    # Comma-separated fallback.
    for part in text.split(","):
        n = _normalize(part)
        if n:
            codes.add(n)
    return codes


def has_permission(granted: Iterable[str], required: str) -> bool:
    """Return ``True`` if ``required`` is granted (or wildcard is present)."""
    granted_set = set(granted)
    return WILDCARD in granted_set or _normalize(required) in granted_set
