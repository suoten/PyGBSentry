"""Push-key parsing and hashing for ZLM on_publish authentication.

A push key has the format ``<prefix>.<raw_secret>`` where ``prefix`` is a
short public identifier stored on the PushChannel and ``raw_secret`` is the
client-held secret. Only the HMAC of the full key is persisted.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Optional


def generate_push_key(prefix_len: int = 8) -> tuple[str, str]:
    """Generate a new push key, returning ``(full_key, prefix)``.

    Format: ``<prefix>.<raw_secret>`` — compatible with :func:`parse_push_key`.

    FIX: [2026-07-13] 从 2ad636a 恢复 — push_channels 端点需要此函数生成新推流密钥。
    [全栈工程师]
    """
    raw = secrets.token_urlsafe(24)
    prefix = raw[:prefix_len].lower()
    full = f"{prefix}.{raw}"
    return full, prefix


def parse_push_key(value: str) -> Optional[tuple[str, str]]:
    """Split a push key into ``(prefix, raw_secret)``; return ``None`` if invalid."""
    if not value:
        return None
    s = str(value).strip()
    if "." not in s:
        return None
    prefix, _, raw = s.partition(".")
    prefix = prefix.strip()
    raw = raw.strip()
    if not prefix or not raw:
        return None
    return prefix, raw


def hash_push_key(value: str, secret: str) -> str:
    """Return the HMAC-SHA256 hex digest of the push key using ``secret``."""
    if not value:
        return ""
    key = str(secret or "").encode("utf-8")
    return hmac.new(key, str(value).strip().encode("utf-8"), hashlib.sha256).hexdigest()
