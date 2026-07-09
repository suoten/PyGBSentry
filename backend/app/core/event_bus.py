"""In-process event bus for media lifecycle events.

Publishers (ZLM hooks, SIP handlers) emit media events; subscribers (stream
strategy, plugins, audit) react to them. The bus is fully async and dispatches
to all registered listeners. Each publish is best-effort: a failing listener
is logged and does not block other listeners or the publisher.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Awaitable

from loguru import logger


class MediaEventType(str, Enum):
    STREAM_REGISTERED = "stream_registered"
    STREAM_UNREGISTERED = "stream_unregistered"
    RTP_SEND_STOPPED = "rtp_send_stopped"
    STREAM_NONE_READER = "stream_none_reader"
    RTP_SERVER_TIMEOUT = "rtp_server_timeout"


Listener = Callable[..., Awaitable[Any]]


class _EventBus:
    def __init__(self) -> None:
        """Internal helper:   init  ."""
        self._listeners: dict[MediaEventType, list[Listener]] = {}

    def subscribe(self, event: MediaEventType, listener: Listener) -> None:
        """Subscribe."""
        self._listeners.setdefault(event, []).append(listener)

    async def _dispatch(self, event: MediaEventType, kwargs: dict) -> None:
        """Internal helper:  dispatch."""
        for listener in list(self._listeners.get(event, [])):
            try:
                await listener(**kwargs)
            except Exception as e:
                logger.warning(f"event_bus: listener for {event.value} failed: {e}")

    async def publish_stream_registered(self, *, app: str, stream: str, ssrc: str = "",
                                        node_id: str = "", raw_data: dict | None = None) -> None:
        """Publish stream registered."""
        await self._dispatch(MediaEventType.STREAM_REGISTERED, {
            "app": app, "stream": stream, "ssrc": ssrc, "node_id": node_id,
            "raw_data": raw_data or {},
        })

    async def publish_stream_unregistered(self, *, app: str, stream: str, ssrc: str = "",
                                          node_id: str = "", raw_data: dict | None = None) -> None:
        """Publish stream unregistered."""
        await self._dispatch(MediaEventType.STREAM_UNREGISTERED, {
            "app": app, "stream": stream, "ssrc": ssrc, "node_id": node_id,
            "raw_data": raw_data or {},
        })

    async def publish_rtp_send_stopped(self, *, app: str, stream: str, ssrc: str = "",
                                       node_id: str = "", raw_data: dict | None = None) -> None:
        """Publish rtp send stopped."""
        await self._dispatch(MediaEventType.RTP_SEND_STOPPED, {
            "app": app, "stream": stream, "ssrc": ssrc, "node_id": node_id,
            "raw_data": raw_data or {},
        })

    async def publish_none_reader(self, *, app: str, stream: str, node_id: str = "",
                                  ssrc: str = "", raw_data: dict | None = None) -> None:
        """Publish none reader."""
        await self._dispatch(MediaEventType.STREAM_NONE_READER, {
            "app": app, "stream": stream, "node_id": node_id, "ssrc": ssrc,
            "raw_data": raw_data or {},
        })

    async def publish_rtp_server_timeout(self, *, app: str, stream: str, ssrc: str = "",
                                         node_id: str = "", raw_data: dict | None = None) -> None:
        """Publish rtp server timeout."""
        await self._dispatch(MediaEventType.RTP_SERVER_TIMEOUT, {
            "app": app, "stream": stream, "ssrc": ssrc, "node_id": node_id,
            "raw_data": raw_data or {},
        })


event_bus = _EventBus()
