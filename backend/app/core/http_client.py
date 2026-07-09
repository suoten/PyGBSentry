"""Shared async HTTP client (httpx) with sensible defaults.

A single reusable :class:`httpx.AsyncClient` is lazily created per process so
connection pooling is effective. Callers obtain it via ``await get_http_client()``.
"""
from __future__ import annotations

from typing import Optional

import httpx
from loguru import logger

from app.core.config import settings

_client: Optional[httpx.AsyncClient] = None


async def get_http_client() -> httpx.AsyncClient:
    """Return the process-wide shared :class:`httpx.AsyncClient`."""
    global _client
    if _client is not None and not _client.is_closed:
        return _client
    timeout = httpx.Timeout(
        timeout=float(getattr(settings, "HTTP_CLIENT_TIMEOUT", 30.0) or 30.0),
        connect=float(getattr(settings, "HTTP_CLIENT_CONNECT_TIMEOUT", 10.0) or 10.0),
    )
    limits = httpx.Limits(
        max_connections=int(getattr(settings, "HTTP_CLIENT_MAX_CONNECTIONS", 100) or 100),
        max_keepalive_connections=int(getattr(settings, "HTTP_CLIENT_MAX_KEEPALIVE", 20) or 20),
    )
    verify = bool(getattr(settings, "HTTP_CLIENT_VERIFY_SSL", True))
    _client = httpx.AsyncClient(timeout=timeout, limits=limits, verify=verify)
    logger.debug("http_client: created shared AsyncClient")
    return _client


async def close_http_client() -> None:
    """Close the shared client (called on shutdown)."""
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None
