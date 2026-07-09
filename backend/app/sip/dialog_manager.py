import asyncio
import json
import time
from loguru import logger
from enum import Enum
from dataclasses import dataclass, field


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
        """Check whether confirmed."""
        return self.state == DialogState.CONFIRMED

    def is_terminated(self) -> bool:
        """Check whether terminated."""
        return self.state == DialogState.TERMINATED


class DialogManager:
    def __init__(self, max_dialogs: int | None = None, ttl_seconds: int | None = None):
        """Internal helper:   init  ."""
        # P2-6: 硬编码上限配置化 — 通过 settings 覆盖默认值
        try:
            from app.core.config import settings
            if max_dialogs is None:
                max_dialogs = int(getattr(settings, "SIP_DIALOG_MAX_COUNT", 50000) or 50000)
            if ttl_seconds is None:
                ttl_seconds = int(getattr(settings, "SIP_DIALOG_TTL_SECONDS", 86400) or 86400)
        except Exception:
            if max_dialogs is None:
                max_dialogs = 50000
            if ttl_seconds is None:
                ttl_seconds = 86400

        self._dialogs: dict[str, Dialog] = {}
        self._max_dialogs = max_dialogs
        self._ttl_seconds = ttl_seconds
        self._global_lock = asyncio.Lock()
        self._cleanup_interval = 300
        self._redis_persist: bool = False
        try:
            from app.core.config import settings
            self._redis_persist = (getattr(settings, "SIP_STATE_BACKEND", "local") or "local").strip().lower() == "redis"
        except Exception:
            self._redis_persist = False
        # FIX R24-SEVERE: fire-and-forget persist task tracking to prevent GC
        self._pending_persist_tasks: set[asyncio.Task] = set()

    def _key(self, call_id: str, from_tag: str) -> str:
        """Internal helper:  key."""
        return f"{call_id}|{from_tag}"

    def _get_redis(self):
        """Internal helper:  get redis."""
        try:
            from app.core.redis import redis_client
            if redis_client:
                return redis_client
        except Exception:
            logger.warning("silently_swallowed_exception", exc_info=True)
        return None

    def _snapshot_dialog(self, dialog: Dialog) -> dict | None:
        """R24-02: 在锁内捕获 dialog 快照（无 I/O，安全在锁内调用）。

        返回可直接序列化的 dict，若 redis 持久化未启用则返回 None。
        """
        if not self._redis_persist:
            return None
        return {
            "call_id": dialog.call_id,
            "from_tag": dialog.from_tag,
            "to_tag": dialog.to_tag,
            "state": dialog.state.value,
            "cseq": dialog.cseq,
            "created_at": dialog.created_at,
            "updated_at": dialog.updated_at,
            "route_set": list(dialog.route_set or []),
            "session_data": dict(dialog.session_data or {}),
            "remote_target": dialog.remote_target or "",
            "local_seq": dialog.local_seq,
            "remote_seq": dialog.remote_seq,
            "secure": dialog.secure,
        }

    async def _persist_snapshot(self, snapshot: dict) -> None:
        """R24-02: 在锁外执行 Redis I/O 持久化快照。

        应通过 _schedule_persist 调度为 fire-and-forget task，避免在 _global_lock 内阻塞。
        """
        if not snapshot:
            return
        r = self._get_redis()
        if r is None:
            return
        try:
            redis_key = f"gb:sip:dialog:{snapshot['call_id']}|{snapshot['from_tag']}"
            await r.setex(redis_key, self._ttl_seconds, json.dumps(snapshot, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"Redis persist dialog failed: {e}")

    def _schedule_persist(self, snapshot: dict | None) -> None:
        """R24-02: 调度 fire-and-forget persist task（在锁内调用安全，不阻塞）。

        snapshot 为 None 时静默跳过（redis 持久化未启用）。
        """
        if not snapshot:
            return
        try:
            task = asyncio.create_task(self._persist_snapshot(snapshot))
            self._pending_persist_tasks.add(task)
            task.add_done_callback(self._pending_persist_tasks.discard)
        except RuntimeError:
            # No running event loop (e.g., during sync init), fall back to sync ignore
            pass

    async def _delete_persisted_dialog(self, call_id: str, from_tag: str) -> None:
        """Internal helper:  delete persisted dialog."""
        if not self._redis_persist:
            return
        r = self._get_redis()
        if r is None:
            return
        try:
            redis_key = f"gb:sip:dialog:{call_id}|{from_tag}"
            await r.delete(redis_key)
        except Exception as e:
            logger.warning(f"Redis delete persisted dialog failed: {e}")

    async def restore_from_redis(self) -> None:
        """Restore from redis."""
        if not self._redis_persist:
            return
        r = self._get_redis()
        if r is None:
            return
        try:
            cursor = 0
            restored = 0
            while True:
                cursor, keys = await r.scan(cursor, match="gb:sip:dialog:*", count=200)
                for key in keys:
                    if isinstance(key, bytes):
                        key = key.decode("utf-8")
                    raw = await r.get(key)
                    if not raw:
                        continue
                    try:
                        data = json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue
                    call_id = data.get("call_id", "")
                    from_tag = data.get("from_tag", "")
                    if not call_id or not from_tag:
                        continue
                    state_str = data.get("state", "early")
                    try:
                        state = DialogState(state_str)
                    except ValueError:
                        state = DialogState.EARLY
                    # Skip terminated dialogs during restore
                    if state == DialogState.TERMINATED:
                        await r.delete(key)
                        continue
                    dialog_key = self._key(call_id, from_tag)
                    if dialog_key in self._dialogs:
                        continue
                    dialog = Dialog(
                        call_id=call_id,
                        from_tag=from_tag,
                        to_tag=data.get("to_tag", ""),
                        cseq=data.get("cseq", 1),
                        state=state,
                        created_at=data.get("created_at", time.time()),
                        updated_at=data.get("updated_at", time.time()),
                    )
                    dialog.route_set = data.get("route_set", [])
                    dialog.session_data = data.get("session_data", {})
                    dialog.remote_target = data.get("remote_target", "")
                    dialog.local_seq = data.get("local_seq", 1)
                    dialog.remote_seq = data.get("remote_seq", 0)
                    dialog.secure = data.get("secure", False)
                    self._dialogs[dialog_key] = dialog
                    restored += 1
                if cursor == 0:
                    break
            if restored > 0:
                logger.info(f"Restored {restored} dialog(s) from Redis")
        except Exception as e:
            logger.warning(f"Restore dialogs from Redis failed: {e}")

    async def create_dialog(
        self,
        call_id: str,
        from_tag: str,
        *,
        cseq: int = 1,
        remote_target: str = "",
        session_data: dict | None = None,
    ) -> Dialog:
        """Create dialog."""
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
            # FIX R24-SEVERE: 锁内捕获快照，锁外 fire-and-forget 持久化（避免 Redis I/O 阻塞 _global_lock）
            self._schedule_persist(self._snapshot_dialog(dialog))
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
        # 持有_global_lock的同时获取dialog._lock，消除竞态窗口
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
                # FIX R24-SEVERE: 锁内捕获快照，锁外 fire-and-forget 持久化
                self._schedule_persist(self._snapshot_dialog(dialog))
                return dialog

    async def get_dialog(self, call_id: str, from_tag: str) -> Dialog | None:
        """Return dialog."""
        # P2 竞态条件 — 读取方法添加锁保护
        key = self._key(call_id, from_tag)
        async with self._global_lock:
            return self._dialogs.get(key)

    async def find_by_call_id(self, call_id: str) -> list[Dialog]:
        """Find by call id."""
        # P2 竞态条件 — 读取方法添加锁保护
        async with self._global_lock:
            return [d for d in self._dialogs.values() if d.call_id == call_id and not d.is_terminated()]

    async def terminate_dialog(self, call_id: str, from_tag: str) -> Dialog | None:
        """Terminate dialog."""
        key = self._key(call_id, from_tag)
        # 持有_global_lock的同时获取dialog._lock，消除竞态窗口
        async with self._global_lock:
            dialog = self._dialogs.get(key)
            if not dialog:
                return None
            async with dialog._lock:
                if dialog.is_terminated():
                    return dialog
                dialog.state = DialogState.TERMINATED
                dialog.updated_at = time.time()
                # FIX R24-SEVERE: 锁内捕获快照，锁外 fire-and-forget 持久化
                self._schedule_persist(self._snapshot_dialog(dialog))
                return dialog

    # W-05 acquire_dialog_lock添加全局锁保护，与其它方法一致
    async def acquire_dialog_lock(self, call_id: str, from_tag: str) -> asyncio.Lock | None:
        """Acquire the lock for a dialog.

        WARNING: There is an inherent race window between acquiring this lock
        and using the dialog. Callers MUST re-check dialog existence after
        acquiring the lock, e.g.:

            lock = await dialog_manager.acquire_dialog_lock(call_id, from_tag)
            if lock is None:
                return
            async with lock:
                dialog = await dialog_manager.get_dialog(call_id, from_tag)
                if dialog is None or dialog.state == DialogState.TERMINATED:
                    return
                # ... proceed with operation
        """
        key = self._key(call_id, from_tag)
        async with self._global_lock:
            dialog = self._dialogs.get(key)
            if not dialog:
                return None
            return dialog._lock

    async def next_cseq(self, call_id: str, from_tag: str) -> int | None:
        """Next cseq."""
        # 持有_global_lock的同时获取dialog._lock，消除竞态窗口
        key = self._key(call_id, from_tag)
        async with self._global_lock:
            dialog = self._dialogs.get(key)
            if not dialog:
                return None
            async with dialog._lock:
                dialog.cseq += 1
                dialog.updated_at = time.time()
                # FIX R23-SEVERE: 持久化 cseq 到 Redis，避免进程重启后 CSeq 回退
                # FIX R24-SEVERE: 锁内捕获快照，锁外 fire-and-forget 持久化（避免 Redis I/O 阻塞 _global_lock）
                self._schedule_persist(self._snapshot_dialog(dialog))
                return dialog.cseq

    async def update_session_data(self, call_id: str, from_tag: str, data: dict) -> None:
        """Update session data."""
        # 持有_global_lock的同时获取dialog._lock，消除竞态窗口
        key = self._key(call_id, from_tag)
        async with self._global_lock:
            dialog = self._dialogs.get(key)
            if not dialog:
                return
            async with dialog._lock:
                dialog.session_data.update(data)
                dialog.updated_at = time.time()
                # FIX R24-SEVERE: 锁内捕获快照，锁外 fire-and-forget 持久化
                self._schedule_persist(self._snapshot_dialog(dialog))

    async def terminate_dialogs_by_device(self, gb_id: str) -> list[Dialog]:
        """Terminate all dialogs associated with the given device GB ID.

        Searches session_data for a 'device_id' or 'gb_id' key matching gb_id,
        and terminates any non-terminated dialogs found.
        """
        to_terminate: list[Dialog] = []
        # FIXED-P2: 修复锁排序 — 与 confirm_dialog 一致，先 _global_lock 再 dialog._lock，避免死锁
        # FIXED-P2: 在 _global_lock 内完成搜索和终止，并持久化到 Redis
        async with self._global_lock:
            for key, dialog in list(self._dialogs.items()):
                if dialog.is_terminated():
                    continue
                sd = dialog.session_data or {}
                if sd.get("device_id") == gb_id or sd.get("gb_id") == gb_id:
                    to_terminate.append(dialog)
            for dialog in to_terminate:
                async with dialog._lock:
                    if not dialog.is_terminated():
                        dialog.state = DialogState.TERMINATED
                        dialog.updated_at = time.time()
                        # FIX R24-SEVERE: 锁内捕获快照，锁外 fire-and-forget 持久化
                        self._schedule_persist(self._snapshot_dialog(dialog))
        if to_terminate:
            logger.info(f"Terminated {len(to_terminate)} dialog(s) for device {gb_id}")
        return to_terminate

    async def _evict_oldest(self) -> None:
        """Internal helper:  evict oldest."""
        now = time.time()
        expired = [
            k for k, d in self._dialogs.items()
            if d.is_terminated() or (now - d.updated_at) > self._ttl_seconds
        ]
        for k in expired:
            self._dialogs.pop(k, None)
        if len(self._dialogs) > self._max_dialogs:
            # S-05: 优先驱逐 TERMINATED/EARLY 状态的 dialog，保护 CONFIRMED 活跃会话
            # 否则活跃通话可能被意外终止
            over = len(self._dialogs) - self._max_dialogs + 100
            # 先从非 CONFIRMED 的 dialog 中驱逐（按 updated_at 最旧优先）
            non_confirmed = [
                (k, d) for k, d in self._dialogs.items() if not d.is_confirmed()
            ]
            non_confirmed.sort(key=lambda x: x[1].updated_at)
            evicted = 0
            for k, d in non_confirmed:
                if evicted >= over:
                    break
                self._dialogs.pop(k, None)
                evicted += 1
            # 如果非 CONFIRMED 不足以腾出空间，才驱逐 CONFIRMED（最后手段）
            if evicted < over:
                confirmed = [
                    (k, d) for k, d in self._dialogs.items() if d.is_confirmed()
                ]
                confirmed.sort(key=lambda x: x[1].updated_at)
                for k, d in confirmed[:over - evicted]:
                    logger.warning(
                        f"S-05: Forced eviction of CONFIRMED dialog {k} "
                        f"(capacity limit {self._max_dialogs}, current {len(self._dialogs)})"
                    )
                    self._dialogs.pop(k, None)

    async def cleanup_loop(self) -> None:
        """Cleanup loop."""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self._evict_oldest()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"DialogManager cleanup error: {e}")

    def stats(self) -> dict:
        """Stats."""
        states = {}
        for d in self._dialogs.values():
            s = d.state.value
            states[s] = states.get(s, 0) + 1
        return {
            "total": len(self._dialogs),
            "by_state": states,
        }


dialog_manager = DialogManager()
