import asyncio
import time
import logging
from enum import Enum
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class DialogState(str, Enum):
    EARLY = "early"
    CONFIRMED = "confirmed"
    TERMINATED = "terminated"


@dataclass
class Dialog:
    call_id: str
    from_tag: str
    to_tag: str = ""
    cseq: int = 1
    state: DialogState = DialogState.EARLY
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    local_seq: int = 1
    remote_seq: int = 0
    remote_target: str = ""
    route_set: list[str] = field(default_factory=list)
    secure: bool = False
    session_data: dict = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    def is_confirmed(self) -> bool:
        return self.state == DialogState.CONFIRMED

    def is_terminated(self) -> bool:
        return self.state == DialogState.TERMINATED


class DialogManager:
    def __init__(self, max_dialogs: int = 50000, ttl_seconds: int = 86400):
        self._dialogs: dict[str, Dialog] = {}
        self._max_dialogs = max_dialogs
        self._ttl_seconds = ttl_seconds
        self._global_lock = asyncio.Lock()
        self._cleanup_interval = 300

    def _key(self, call_id: str, from_tag: str) -> str:
        return f"{call_id}|{from_tag}"

    async def create_dialog(
        self,
        call_id: str,
        from_tag: str,
        *,
        cseq: int = 1,
        remote_target: str = "",
        session_data: dict | None = None,
    ) -> Dialog:
        key = self._key(call_id, from_tag)
        async with self._global_lock:
            if key in self._dialogs:
                existing = self._dialogs[key]
                if existing.is_terminated():
                    del self._dialogs[key]
                else:
                    return existing
            dialog = Dialog(
                call_id=call_id,
                from_tag=from_tag,
                cseq=cseq,
                remote_target=remote_target,
                session_data=session_data or {},
            )
            self._dialogs[key] = dialog
            if len(self._dialogs) > self._max_dialogs:
                await self._evict_oldest()
            return dialog

    async def confirm_dialog(
        self,
        call_id: str,
        from_tag: str,
        to_tag: str,
        *,
        cseq: int | None = None,
        remote_target: str = "",
        route_set: list[str] | None = None,
    ) -> Dialog | None:
        """Confirm a dialog, optionally populating route_set from Record-Route headers.

        Args:
            call_id: SIP Call-ID header value.
            from_tag: From tag value.
            to_tag: To tag value from the confirming response.
            cseq: Optional CSeq number.
            remote_target: Optional Contact URI from the remote party.
            route_set: Optional list of Route header values (from Record-Route of the response).
        """
        key = self._key(call_id, from_tag)
        # FIXED-P0: 持有_global_lock的同时获取dialog._lock，消除竞态窗口
        # 之前：释放_global_lock后再获取dialog._lock，期间其他协程可terminate同一dialog
        async with self._global_lock:
            dialog = self._dialogs.get(key)
            if not dialog:
                return None
            async with dialog._lock:
                if dialog.is_terminated():
                    return None
                dialog.to_tag = to_tag
                dialog.state = DialogState.CONFIRMED
                dialog.updated_at = time.time()
                if cseq is not None:
                    dialog.cseq = cseq
                if remote_target:
                    dialog.remote_target = remote_target
                if route_set is not None:
                    dialog.route_set = route_set
                return dialog

    async def get_dialog(self, call_id: str, from_tag: str) -> Dialog | None:
        # FIXED: P2 竞态条件 — 读取方法添加锁保护
        key = self._key(call_id, from_tag)
        async with self._global_lock:
            return self._dialogs.get(key)

    async def find_by_call_id(self, call_id: str) -> list[Dialog]:
        # FIXED: P2 竞态条件 — 读取方法添加锁保护
        async with self._global_lock:
            return [d for d in self._dialogs.values() if d.call_id == call_id and not d.is_terminated()]

    async def terminate_dialog(self, call_id: str, from_tag: str) -> Dialog | None:
        key = self._key(call_id, from_tag)
        # FIXED-P0: 持有_global_lock的同时获取dialog._lock，消除竞态窗口
        async with self._global_lock:
            dialog = self._dialogs.get(key)
            if not dialog:
                return None
            async with dialog._lock:
                if dialog.is_terminated():
                    return dialog
                dialog.state = DialogState.TERMINATED
                dialog.updated_at = time.time()
                return dialog

    async def acquire_dialog_lock(self, call_id: str, from_tag: str) -> asyncio.Lock | None:
        key = self._key(call_id, from_tag)
        dialog = self._dialogs.get(key)
        if not dialog:
            return None
        return dialog._lock

    async def next_cseq(self, call_id: str, from_tag: str) -> int | None:
        # FIXED-P0: 持有_global_lock的同时获取dialog._lock，消除竞态窗口
        key = self._key(call_id, from_tag)
        async with self._global_lock:
            dialog = self._dialogs.get(key)
            if not dialog:
                return None
            async with dialog._lock:
                dialog.cseq += 1
                dialog.updated_at = time.time()
                return dialog.cseq

    async def update_session_data(self, call_id: str, from_tag: str, data: dict) -> None:
        # FIXED-P0: 持有_global_lock的同时获取dialog._lock，消除竞态窗口
        key = self._key(call_id, from_tag)
        async with self._global_lock:
            dialog = self._dialogs.get(key)
            if not dialog:
                return
            async with dialog._lock:
                dialog.session_data.update(data)
                dialog.updated_at = time.time()

    async def _evict_oldest(self) -> None:
        now = time.time()
        expired = [
            k for k, d in self._dialogs.items()
            if d.is_terminated() or (now - d.updated_at) > self._ttl_seconds
        ]
        for k in expired:
            self._dialogs.pop(k, None)
        if len(self._dialogs) > self._max_dialogs:
            sorted_items = sorted(self._dialogs.items(), key=lambda x: x[1].updated_at)
            over = len(self._dialogs) - self._max_dialogs + 100
            for i in range(min(over, len(sorted_items))):
                self._dialogs.pop(sorted_items[i][0], None)

    async def cleanup_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self._evict_oldest()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"DialogManager cleanup error: {e}")

    def stats(self) -> dict:
        states = {}
        for d in self._dialogs.values():
            s = d.state.value
            states[s] = states.get(s, 0) + 1
        return {
            "total": len(self._dialogs),
            "by_state": states,
        }


dialog_manager = DialogManager()
