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
    # FIX: [2026-07-16 P0] 移除 getattr 动态获取，直接使用 Settings 中定义的字段，
    # 确保 .env 配置生效，且 mypy/pyright 可在编译期发现未定义字段。
    timeout = httpx.Timeout(
        timeout=settings.HTTP_CLIENT_TIMEOUT,
        connect=settings.HTTP_CLIENT_CONNECT_TIMEOUT,
    )
    limits = httpx.Limits(
        max_connections=settings.HTTP_CLIENT_MAX_CONNECTIONS,
        max_keepalive_connections=settings.HTTP_CLIENT_MAX_KEEPALIVE,
    )
    verify = settings.HTTP_CLIENT_VERIFY_SSL
    _client = httpx.AsyncClient(timeout=timeout, limits=limits, verify=verify)
    logger.debug("http_client: created shared AsyncClient")
    return _client


async def close_http_client() -> None:
    """Close the shared client (called on shutdown)."""
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None
