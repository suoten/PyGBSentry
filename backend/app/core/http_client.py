from __future__ import annotations

import asyncio
import httpx

from app.core.config import settings


_http_client: httpx.AsyncClient | None = None
_http_client_lock = asyncio.Lock()


async def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        return _http_client
    async with _http_client_lock:
        if _http_client is not None and not _http_client.is_closed:
            return _http_client
        # 超时值从settings读取而非硬编码
        _http_timeout = float(getattr(settings, "HTTP_CLIENT_TIMEOUT", 10.0) or 10.0)
        _http_connect_timeout = float(getattr(settings, "HTTP_CLIENT_CONNECT_TIMEOUT", 5.0) or 5.0)
        _http_client = httpx.AsyncClient(timeout=httpx.Timeout(_http_timeout, connect=_http_connect_timeout))
    return _http_client


async def close_http_client() -> None:
    global _http_client
    async with _http_client_lock:
        if _http_client and not _http_client.is_closed:
            await _http_client.aclose()
        _http_client = None
