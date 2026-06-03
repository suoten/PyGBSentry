from __future__ import annotations


def normalize_stream_name(value: str | None, fallback: str) -> str:
    raw = (value or "").replace(" ", "_")
    normalized = "".join(ch for ch in raw if ch.isalnum() or ch in {"_", "-"}).lower()
    return normalized or (fallback or "")

