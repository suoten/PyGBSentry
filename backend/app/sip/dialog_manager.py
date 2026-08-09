import asyncio
import json
import time
from loguru import logger
from enum import Enum
from dataclasses import dataclass, field

# P1-fix [2026-07-17]: Session Timer 后台任务必须使用项目统一的 fire_and_forget
# （带异常回调和任务名），禁止裸 asyncio.create_task
from app.core.async_utils import fire_and_forget


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
                max_dialogs = settings.SIP_DIALOG_MAX_COUNT
            if ttl_seconds is None:
                ttl_seconds = settings.SIP_DIALOG_TTL_SECONDS
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
            self._redis_persist = (settings.SIP_STATE_BACKEND or "local").strip().lower() == "redis"
        except Exception:
            self._redis_persist = False
        # FIX R24-SEVERE: fire-and-forget persist task tracking to prevent GC
        self._pending_persist_tasks: set[asyncio.Task] = set()
        # SIP Session Timer (RFC 4028) 回调 — 由 main.py 启动时注册
        # _on_session_refresh: async (call_id, from_tag, dialog) -> bool
        # _on_session_timeout: async (call_id, from_tag, dialog) -> None
        self._on_session_refresh = None
        self._on_session_timeout = None

    def _key(self, call_id: str, from_tag: str) -> str:
        """Internal helper:  key."""
        return f"{call_id}|{from_tag}"

    def _get_redis(self):
        """Internal helper:  get redis."""
        try:
            from app.core.redis import redis_client
            if redis_client:
                return redis_client
        except Exception as _redis_err:
            # FIX [2026-07-17 P3-9]: 描述性日志替代 "silently_swallowed_exception"
            logger.warning(f"dialog_manager: failed to import redis_client: {_redis_err}")
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
            # P0-16 [2026-07-17]: 带异常回调和任务名的安全任务创建，
            # 避免异常静默吞没；任务存入 _pending_persist_tasks 防止 GC 回收
            task = asyncio.create_task(
                self._persist_snapshot(snapshot),
                name=f"dialog_persist:{snapshot.get('call_id', '?')}",
            )
            self._pending_persist_tasks.add(task)

            def _on_persist_done(t: asyncio.Task) -> None:
                self._pending_persist_tasks.discard(t)
                if t.cancelled():
                    return
                exc = t.exception()
                if exc is not None:
                    logger.error(
                        f"dialog persist task raised: {exc!r}",
                        exc_info=exc,
                    )

            task.add_done_callback(_on_persist_done)
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
                # FIX [2026-07-17 P1]: 终止对话时取消 Session Timer 后台任务，
                # 避免僵尸任务继续触发刷新/超时回调（RFC 4028 §9）
                timer_task = dialog.session_data.pop("_session_timer_task", None)
                if timer_task is not None and not timer_task.done():
                    try:
                        timer_task.cancel()
                    except Exception as _timer_cancel_err:
                        # FIX [2026-07-17 P3-9]: 描述性日志替代 "silently_swallowed_exception"
                        logger.warning(f"terminate_dialog: failed to cancel session_timer task for {call_id}: {_timer_cancel_err}")
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

    async def update_remote_seq(self, call_id: str, from_tag: str, remote_cseq: int) -> bool:
        """更新远端 CSeq 并校验单调递增（RFC 3261 §12.2.2）。

        P1-fix [2026-07-17]: 原代码 remote_seq 从不更新，导致：
        1. 无法检测乱序/重放攻击（CSeq 回退）
        2. 对话状态不完整，影响后续 in-dialog 请求的 CSeq 协商

        Returns:
            True — CSeq 合法（首次或递增），已更新 remote_seq
            False — CSeq 非法（回退或重复），调用方应回 500/400 拒绝
        """
        if remote_cseq < 0:
            return False
        key = self._key(call_id, from_tag)
        async with self._global_lock:
            dialog = self._dialogs.get(key)
            if not dialog:
                return True  # 对话不存在不阻断（由调用方决定是否拒绝）
            async with dialog._lock:
                # 首次（remote_seq==0）直接接受；后续必须严格递增
                if dialog.remote_seq > 0 and remote_cseq <= dialog.remote_seq:
                    logger.warning(
                        f"dialog CSeq monotonic violation: call_id={call_id} "
                        f"remote_seq={dialog.remote_seq} received={remote_cseq}"
                    )
                    return False
                if remote_cseq > dialog.remote_seq:
                    dialog.remote_seq = remote_cseq
                    dialog.updated_at = time.time()
                    self._schedule_persist(self._snapshot_dialog(dialog))
                return True

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

    # ------------------------------------------------------------------
    # SIP Session Timer (RFC 4028)
    # ------------------------------------------------------------------
    # PyGBSentry 同时可作为 UAC（点播设备）和 UAS（级联被点播）。Session Timer
    # 状态全部存入 dialog.session_data，便于 Redis 持久化与回放：
    #   - "session_expires":   int   — 协商后的过期秒数（0 表示无 Session Timer）
    #   - "session_refresher": str   — "uac" / "uas" / ""
    #   - "local_role":        str   — "uac" / "uas"（PyGBSentry 在该对话中的角色）
    #   - "last_refresh_at":   float — monotonic 时钟时间戳，避免壁钟漂移
    #   - "_session_timer_task": asyncio.Task — 进程内任务引用（不持久化）
    #
    # refresher 判定：当 session_refresher == local_role 时，本端为刷新方，
    # 在 expires/2 时发送会话内 re-INVITE 保活；否则为看门狗，在 expires 超时
    # 未收到刷新时主动发送 BYE 释放会话并联动释放 SSRC/RTP 端口。

    def set_session_timer_callbacks(self, on_refresh, on_timeout) -> None:
        """注册 Session Timer 刷新/超时回调。

        Args:
            on_refresh: ``async (call_id, from_tag, dialog) -> bool``
                refresher 方在 expires/2 时调用，返回 True 表示 re-INVITE 成功
                并更新 last_refresh_at；False 表示刷新失败，触发超时回调。
            on_timeout: ``async (call_id, from_tag, dialog) -> None``
                非刷新方超时或刷新失败时调用，应发送 BYE 并联动释放 SSRC/RTP 端口。
        """
        self._on_session_refresh = on_refresh
        self._on_session_timeout = on_timeout

    async def set_session_timer(
        self,
        call_id: str,
        from_tag: str,
        expires: int,
        refresher: str,
        local_role: str = "uac",
    ) -> bool:
        """为已存在的 dialog 设置 Session Timer 参数。

        Args:
            call_id: SIP Call-ID。
            from_tag: 本端 From tag。
            expires: 协商后的 Session-Expires 秒数。``0`` 表示无 Session Timer
                （GB28181 设备不支持时降级），仍会记录 ``session_expires=0`` 状态
                以便上层区分"已协商但禁用"与"未协商"，但返回 False 不启动定时器。
            refresher: ``"uac"`` / ``"uas"`` / ``""``。
            local_role: PyGBSentry 在该对话中的角色，``"uac"`` 或 ``"uas"``。
                默认 ``"uac"``（点播设备的常见场景）。

        Returns:
            True — 已写入状态且 expires>0（应启动定时器）；
            False — dialog 不存在或 expires<=0（不启动定时器，GB28181 降级）。
        """
        key = self._key(call_id, from_tag)
        async with self._global_lock:
            dialog = self._dialogs.get(key)
            if not dialog:
                return False
            async with dialog._lock:
                # 即使 expires=0 也写入状态，以便上层识别"已协商但禁用"
                dialog.session_data["session_expires"] = int(expires)
                dialog.session_data["session_refresher"] = str(refresher or "").lower()
                dialog.session_data["local_role"] = str(local_role or "uac").lower()
                # FIX [memory-lesson]: TTL 判断必须使用 monotonic 时钟，
                # 避免壁钟与进程秒数混用导致刷新判断失效
                dialog.session_data["last_refresh_at"] = time.monotonic()
                dialog.updated_at = time.time()
                self._schedule_persist(self._snapshot_dialog(dialog))
                return expires > 0

    async def update_session_refresh(self, call_id: str, from_tag: str) -> None:
        """更新 last_refresh_at 时间戳（收到对端 re-INVITE/UPDATE 或本端刷新成功时调用）。"""
        key = self._key(call_id, from_tag)
        async with self._global_lock:
            dialog = self._dialogs.get(key)
            if not dialog:
                return
            async with dialog._lock:
                dialog.session_data["last_refresh_at"] = time.monotonic()
                dialog.updated_at = time.time()
                self._schedule_persist(self._snapshot_dialog(dialog))

    def start_session_timer(self, call_id: str, from_tag: str) -> None:
        """为 dialog 启动 Session Timer 后台任务（refresher 刷新或 watchdog 超时）。

        必须先调用 :meth:`set_session_timer` 写入参数。任务通过项目统一的
        :func:`app.core.async_utils.fire_and_forget` 调度（带异常回调和任务名），
        引用存入 ``session_data["_session_timer_task"]`` 以便 :meth:`terminate_dialog`
        取消。expires<=0 时为 no-op（GB28181 降级路径）。
        """
        key = self._key(call_id, from_tag)
        # 同步读取 session_expires 与角色（不持锁，仅判断是否需要启动）
        dialog = self._dialogs.get(key)
        if not dialog:
            return
        expires = int(dialog.session_data.get("session_expires", 0) or 0)
        if expires <= 0:
            return
        # 取消已存在的旧任务
        old_task = dialog.session_data.get("_session_timer_task")
        if old_task is not None and not old_task.done():
            try:
                old_task.cancel()
            except Exception as _cancel_old_err:
                # FIX [2026-07-17 P3-9]: 描述性日志替代 "silently_swallowed_exception"
                logger.warning(f"start_session_timer: failed to cancel old task for {call_id}: {_cancel_old_err}")
        # 通过 fire_and_forget 调度（带异常回调和任务名）
        task = fire_and_forget(
            self._session_timer_task_loop(call_id, from_tag),
            name=f"session_timer:{call_id}",
        )
        if task is not None:
            dialog.session_data["_session_timer_task"] = task

    async def _session_timer_task_loop(self, call_id: str, from_tag: str) -> None:
        """Session Timer 单 dialog 守护协程。

        - refresher 方：在 expires/2 时调用 ``on_refresh`` 发送会话内 re-INVITE，
          成功后更新 last_refresh_at 并循环；失败则调用 ``on_timeout`` 终止。
        - 非刷新方（watchdog）：在 expires 超时后检查 last_refresh_at 是否更新，
          未更新则调用 ``on_timeout`` 发送 BYE 释放会话。
        """
        key = self._key(call_id, from_tag)
        # 读取参数（一次性快照；若对端 re-INVITE 协商新值会通过 set_session_timer 重置任务）
        dialog = self._dialogs.get(key)
        if not dialog:
            return
        expires = int(dialog.session_data.get("session_expires", 0) or 0)
        refresher = str(dialog.session_data.get("session_refresher", "") or "").lower()
        local_role = str(dialog.session_data.get("local_role", "uac") or "uac").lower()
        if expires <= 0:
            return
        local_is_refresher = (refresher == local_role) and refresher in ("uac", "uas")
        # 未指定 refresher 时按 RFC 4028 默认 UAC 刷新
        if not refresher:
            local_is_refresher = (local_role == "uac")

        try:
            if local_is_refresher:
                await self._refresher_loop(call_id, from_tag, expires)
            else:
                await self._watchdog_loop(call_id, from_tag, expires)
        except asyncio.CancelledError:
            logger.debug(f"session_timer cancelled for call_id={call_id}")
            raise
        except Exception as e:
            # fire_and_forget 已有 done_callback 兜底记录 ERROR，此处仅 debug
            logger.warning(f"session_timer loop error for call_id={call_id}: {e}")

    async def _refresher_loop(self, call_id: str, from_tag: str, expires: int) -> None:
        """刷新方循环：expires/2 间隔发送 re-INVITE 保活。"""
        # 防御性上限：单 dialog 最多刷新 100000 次（约 1800s/2 * 100000 ≈ 5 年）
        max_iterations = 100000
        for _ in range(max_iterations):
            # expires/2 触发刷新（RFC 4028 §7）
            await asyncio.sleep(max(float(expires) / 2.0, 1.0))
            # 重新读取最新状态（dialog 可能已被 terminate）
            dialog = await self.get_dialog(call_id, from_tag)
            if dialog is None or dialog.is_terminated():
                return
            # 调用刷新回调（发送会话内 re-INVITE）
            if self._on_session_refresh is None:
                logger.debug(f"session_timer: no refresh callback registered for {call_id}")
                return
            try:
                ok = await self._on_session_refresh(call_id, from_tag, dialog)
            except Exception as refresh_err:
                logger.warning(f"session_timer refresh callback error for {call_id}: {refresh_err}")
                ok = False
            if ok:
                await self.update_session_refresh(call_id, from_tag)
                logger.debug(f"session_timer refresh ok for {call_id}")
            else:
                # 刷新失败 → 触发超时（发 BYE）
                logger.warning(f"session_timer refresh failed for {call_id}, triggering timeout BYE")
                if self._on_session_timeout is not None:
                    try:
                        await self._on_session_timeout(call_id, from_tag, dialog)
                    except Exception as timeout_err:
                        logger.warning(f"session_timer timeout callback error after refresh-fail for {call_id}: {timeout_err}")
                await self.terminate_dialog(call_id, from_tag)
                return
        logger.warning(f"session_timer refresher_loop hit max_iterations for {call_id}")

    async def _watchdog_loop(self, call_id: str, from_tag: str, expires: int) -> None:
        """看门狗循环：expires 超时未收到刷新则发 BYE。"""
        # 最多 100000 次超时检查（实际 1 次超时即终止）
        for _ in range(100000):
            await asyncio.sleep(max(float(expires), 1.0))
            dialog = await self.get_dialog(call_id, from_tag)
            if dialog is None or dialog.is_terminated():
                return
            last_refresh = float(dialog.session_data.get("last_refresh_at", 0.0) or 0.0)
            now = time.monotonic()
            # 若距离上次刷新已超过 expires → 视为对端静默掉线
            if (now - last_refresh) >= float(expires):
                logger.warning(
                    f"session_timer watchdog timeout for call_id={call_id} "
                    f"(no refresh for {now - last_refresh:.0f}s, expires={expires}s), sending BYE"
                )
                if self._on_session_timeout is not None:
                    try:
                        await self._on_session_timeout(call_id, from_tag, dialog)
                    except Exception as timeout_err:
                        logger.warning(f"session_timer timeout callback error for {call_id}: {timeout_err}")
                await self.terminate_dialog(call_id, from_tag)
                return

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
