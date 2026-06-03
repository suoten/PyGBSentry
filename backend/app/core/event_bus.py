import asyncio
from loguru import logger
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine


class MediaEventType(str, Enum):
    STREAM_REGISTERED = "stream_registered"
    STREAM_UNREGISTERED = "stream_unregistered"
    STREAM_NONE_READER = "stream_none_reader"
    STREAM_NOT_FOUND = "stream_not_found"
    RTP_SEND_STOPPED = "rtp_send_stopped"
    RTP_SERVER_TIMEOUT = "rtp_server_timeout"
    RECORD_MP4_COMPLETED = "record_mp4_completed"
    ZLM_SERVER_STARTED = "zlm_server_started"
    ZLM_SERVER_KEEPALIVE = "zlm_server_keepalive"
    PLAY_AUTH_REQUEST = "play_auth_request"
    PUBLISH_AUTH_REQUEST = "publish_auth_request"


@dataclass
class MediaEvent:
    type: MediaEventType
    data: dict = field(default_factory=dict)
    node_id: str = ""
    app: str = ""
    stream: str = ""
    ssrc: str = ""
    timestamp: float = field(default_factory=time.time) # __import__ 反模式改为标准 import

    @property
    def stream_key(self) -> str:
        return f"{self.app}/{self.stream}"


EventHandler = Callable[[MediaEvent], Coroutine[Any, Any, None]]


class EventBus:
    def __init__(self, max_history: int = 1000):
        self._handlers: dict[MediaEventType, list[EventHandler]] = {}
        self._wildcard_handlers: list[EventHandler] = []
        self._lock = asyncio.Lock()
        self._history: list[MediaEvent] = []
        self._max_history = max_history
        self._stats: dict[str, int] = {}

    async def subscribe(self, event_type: MediaEventType, handler: EventHandler) -> None:
        async with self._lock:
            if event_type not in self._handlers:
                self._handlers[event_type] = []
            self._handlers[event_type].append(handler)

    async def subscribe_all(self, handler: EventHandler) -> None:
        async with self._lock:
            self._wildcard_handlers.append(handler)

    async def unsubscribe(self, event_type: MediaEventType, handler: EventHandler) -> None:
        async with self._lock:
            handlers = self._handlers.get(event_type, [])
            with contextlib.suppress(ValueError):
                handlers.remove(handler)

    async def publish(self, event: MediaEvent) -> None:
        # W-21 publish方法中_stats/_history修改添加锁保护
        async with self._lock:
            self._stats[event.type.value] = self._stats.get(event.type.value, 0) + 1
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

        handlers = list(self._handlers.get(event.type, []))
        wildcard = list(self._wildcard_handlers)

        _handler_tasks: set[asyncio.Task] = set()

        # M-14 添加done callback捕获handler异常
        def _on_task_done(task: asyncio.Task):
            _handler_tasks.discard(task)
            if task.cancelled():
                return
            exc = task.exception()
            if exc:
                logger.warning(f"EventBus handler error for {event.type.value}: {exc}")

        for handler in handlers + wildcard:
            try:
                task = asyncio.create_task(handler(event))
                _handler_tasks.add(task)
                task.add_done_callback(_on_task_done)
            except Exception as e:
                logger.warning(f"EventBus handler error for {event.type.value}: {e}")

    async def publish_stream_registered(
        self, app: str, stream: str, ssrc: str = "", node_id: str = "", **kwargs
    ) -> None:
        await self.publish(MediaEvent(
            type=MediaEventType.STREAM_REGISTERED,
            app=app, stream=stream, ssrc=ssrc, node_id=node_id,
            data=kwargs,
        ))

    async def publish_stream_unregistered(
        self, app: str, stream: str, ssrc: str = "", node_id: str = "", **kwargs
    ) -> None:
        await self.publish(MediaEvent(
            type=MediaEventType.STREAM_UNREGISTERED,
            app=app, stream=stream, ssrc=ssrc, node_id=node_id,
            data=kwargs,
        ))

    async def publish_none_reader(
        self, app: str, stream: str, node_id: str = "", **kwargs
    ) -> None:
        await self.publish(MediaEvent(
            type=MediaEventType.STREAM_NONE_READER,
            app=app, stream=stream, node_id=node_id,
            data=kwargs,
        ))

    async def publish_rtp_send_stopped(
        self, app: str, stream: str, node_id: str = "", **kwargs
    ) -> None:
        await self.publish(MediaEvent(
            type=MediaEventType.RTP_SEND_STOPPED,
            app=app, stream=stream, node_id=node_id,
            data=kwargs,
        ))

    async def publish_record_completed(
        self, app: str, stream: str, node_id: str = "", **kwargs
    ) -> None:
        await self.publish(MediaEvent(
            type=MediaEventType.RECORD_MP4_COMPLETED,
            app=app, stream=stream, node_id=node_id,
            data=kwargs,
        ))

    def stats(self) -> dict:
        return {
            "event_counts": dict(self._stats),
            "handler_counts": {t.value: len(h) for t, h in self._handlers.items()},
            "wildcard_handlers": len(self._wildcard_handlers),
        }


import contextlib

event_bus = EventBus()
