"""Stream-name normalisation for proxy-compat and push flows."""
from __future__ import annotations

import re

_NON_SAFE = re.compile(r"[^A-Za-z0-9_\-]")


def normalize_stream_name(name: str, fallback: str = "stream") -> str:
    """Return a ZLM-safe stream name.

    ZLMediaKit stream names must match ``[A-Za-z0-9_-]+``. This strips or
    replaces any other characters and falls back to ``fallback`` when the
    result is empty.
    """
    if name is None:
        return fallback or "stream"
    cleaned = _NON_SAFE.sub("_", str(name).strip())
    if not cleaned:
        return fallback or "stream"
    return cleaned
