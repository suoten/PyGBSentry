import asyncio
import threading
import time
from loguru import logger
from typing import Protocol, runtime_checkable


@runtime_checkable
class SipStateBackend(Protocol):
    async def register_ssrc_waiter(self, ssrc: str) -> None: ...
    async def wait_ssrc_stream(self, ssrc: str, timeout: float) -> bool: ...
    async def notify_ssrc_registered(self, ssrc: str) -> None: ...
    async def unregister_ssrc_waiter(self, ssrc: str) -> None: ...
    async def consume_invite_rate(self, tenant_id: str, device_id: str, window: float, per_device: int, per_tenant: int) -> tuple[bool, str]: ...
    async def check_nonce_nc(self, user: str, nonce: str, nc: int) -> bool: ...
    async def record_auth_failure(self, ip: str) -> int: ...
    async def clear_auth_failure(self, ip: str) -> None: ...
    async def cleanup_auth_failures(self) -> int: ...
    async def check_register_renewal(self, gb_id: str, call_id: str) -> bool: ...
    async def record_register_call_id(self, gb_id: str, call_id: str, ttl: int = 3660) -> None: ...


class LocalSipStateBackend:
    def __init__(self):
        # P2-6: 硬编码上限配置化 — 通过 settings 覆盖默认值
        try:
            from app.core.config import settings
            _ssrc_waiters_max = int(getattr(settings, "SIP_SSRC_WAITERS_MAX_SIZE", 5000) or 5000)
            _nonce_nc_max = int(getattr(settings, "SIP_NONCE_NC_MAX_SIZE", 10000) or 10000)
            _nonce_nc_ttl = int(getattr(settings, "SIP_NONCE_NC_TTL_SECONDS", 300) or 300)
            _auth_failure_max = int(getattr(settings, "SIP_AUTH_FAILURE_MAX_SIZE", 5000) or 5000)
        except Exception:
            _ssrc_waiters_max = 5000
            _nonce_nc_max = 10000
            _nonce_nc_ttl = 300
            _auth_failure_max = 5000

        self._ssrc_waiters: dict[str, asyncio.Event] = {}
        self._ssrc_waiters_lock = asyncio.Lock()
        self._ssrc_waiters_max_size = _ssrc_waiters_max
        self._invite_rate_buckets: dict[str, list[float]] = {}
        self._invite_rate_lock = asyncio.Lock()
        self._nonce_nc_tracker: dict[tuple[str, str], tuple[int, float]] = {}
        self._nonce_nc_max_size = _nonce_nc_max
        self._nonce_nc_ttl = _nonce_nc_ttl
        self._auth_failure_tracker: dict[str, list[float]] = {}
        # FIX-LEAK: 使用 asyncio.Lock 保护 _auth_failure_tracker 并发访问，消除竞态条件
        self._auth_failure_lock = asyncio.Lock()
        self._auth_failure_ttl = 300
        self._auth_failure_max_size = _auth_failure_max
        self._register_call_ids: dict[str, str] = {}
        self._register_call_ids_ts: dict[str, float] = {}  # 记录call_id写入时间戳，支持TTL过期

    async def register_ssrc_waiter(self, ssrc: str) -> None:
        key = str(ssrc or "").strip()
        if not key:
            return
        async with self._ssrc_waiters_lock:
            if key not in self._ssrc_waiters:
                if len(self._ssrc_waiters) >= self._ssrc_waiters_max_size:
                    stale_keys = list(self._ssrc_waiters.keys())[:self._ssrc_waiters_max_size // 10]
                    for k in stale_keys:
                        self._ssrc_waiters.pop(k, None)
                self._ssrc_waiters[key] = asyncio.Event()

    async def wait_ssrc_stream(self, ssrc: str, timeout: float = 8.0) -> bool:
        key = str(ssrc or "").strip()
        if not key:
            return False
        async with self._ssrc_waiters_lock:
            event = self._ssrc_waiters.get(key)
        if event is None:
            return False
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    async def notify_ssrc_registered(self, ssrc: str) -> None:
        key = str(ssrc or "").strip()
        if not key:
            return
        async with self._ssrc_waiters_lock:
            event = self._ssrc_waiters.get(key)
        if event and not event.is_set():
            event.set()

    async def unregister_ssrc_waiter(self, ssrc: str) -> None:
        key = str(ssrc or "").strip()
        if not key:
            return
        async with self._ssrc_waiters_lock:
            self._ssrc_waiters.pop(key, None)

    async def consume_invite_rate(
        self, tenant_id: str, device_id: str, window: float = 10.0, per_device: int = 30, per_tenant: int = 300
    ) -> tuple[bool, str]:
        now = time.time()
        device_key = f"{tenant_id}:{device_id}"
        tenant_key = f"{tenant_id}:__tenant__"
        async with self._invite_rate_lock:
            # 全局过期清理，防止 _invite_rate_buckets 字典无限增长
            if len(self._invite_rate_buckets) > 10000:
                expired_keys = [
                    k for k, bucket in self._invite_rate_buckets.items()
                    if not bucket or all(now - t >= window for t in bucket)
                ]
                for k in expired_keys:
                    self._invite_rate_buckets.pop(k, None)
            for key in (device_key, tenant_key):
                bucket = self._invite_rate_buckets.get(key, [])
                filtered = [t for t in bucket if now - t < window]
                if filtered:
                    self._invite_rate_buckets[key] = filtered
                else:
                    self._invite_rate_buckets.pop(key, None)
            device_count = len(self._invite_rate_buckets.get(device_key, []))
            tenant_count = len(self._invite_rate_buckets.get(tenant_key, []))
            if device_count >= per_device:
                return False, f"device_rate_limited ({device_count}/{per_device} per {window}s)"
            if tenant_count >= per_tenant:
                return False, f"tenant_rate_limited ({tenant_count}/{per_tenant} per {window}s)"
            self._invite_rate_buckets.setdefault(device_key, []).append(now)
            self._invite_rate_buckets.setdefault(tenant_key, []).append(now)
            return True, ""

    async def check_nonce_nc(self, user: str, nonce: str, nc: int) -> bool:
        key = (str(user or ""), str(nonce or ""))
        now = time.time()
        cutoff = now - self._nonce_nc_ttl
        self._nonce_nc_tracker = {k: v for k, v in self._nonce_nc_tracker.items() if v[1] > cutoff}
        last_nc_ts = self._nonce_nc_tracker.get(key)
        last_nc = last_nc_ts[0] if last_nc_ts else -1
        if nc <= last_nc:
            return False
        self._nonce_nc_tracker[key] = (nc, now)
        # Size-based cleanup as fallback
        if len(self._nonce_nc_tracker) > self._nonce_nc_max_size:
            sorted_items = sorted(self._nonce_nc_tracker.items(), key=lambda x: x[1][1])
            over = len(self._nonce_nc_tracker) - self._nonce_nc_max_size + 100
            for i in range(min(over, len(sorted_items))):
                self._nonce_nc_tracker.pop(sorted_items[i][0], None)
        return True

    async def record_auth_failure(self, ip: str) -> int:
        # FIX-LEAK: 所有 _auth_failure_tracker 读写操作在 _auth_failure_lock 保护下完成，
        # 消除并发场景下 list[float] 追加/过滤/弹出导致的竞态条件
        now = time.time()
        key = str(ip or "")
        async with self._auth_failure_lock:
            if key not in self._auth_failure_tracker:
                self._auth_failure_tracker[key] = []
            self._auth_failure_tracker[key] = [t for t in self._auth_failure_tracker[key] if now - t < self._auth_failure_ttl]
            self._auth_failure_tracker[key].append(now)
            # 容量超限时触发清理：移除最旧的 IP 记录，并清理空列表条目
            # 注意：排除当前 key，避免清理掉刚插入的记录导致返回时 KeyError
            if len(self._auth_failure_tracker) > self._auth_failure_max_size:
                other_items = [
                    (k, min(v) if v else now)
                    for k, v in self._auth_failure_tracker.items()
                    if k != key
                ]
                other_items.sort(key=lambda x: x[1])
                to_remove = len(self._auth_failure_tracker) - self._auth_failure_max_size + 100
                for ip_key, _ in other_items[:to_remove]:
                    self._auth_failure_tracker.pop(ip_key, None)
                # 顺便清理因过滤而过期的空 IP 列表，防止字典条目泄漏
                empty_keys = [k for k, v in self._auth_failure_tracker.items() if not v and k != key]
                for k in empty_keys:
                    self._auth_failure_tracker.pop(k, None)
            return len(self._auth_failure_tracker[key])

    async def clear_auth_failure(self, ip: str) -> None:
        # FIX-LEAK: 加锁保护，避免与 record_auth_failure 并发写入竞态
        async with self._auth_failure_lock:
            self._auth_failure_tracker.pop(str(ip or ""), None)

    async def cleanup_auth_failures(self) -> int:
        """FIX-LEAK: 定期清理过期的鉴权失败记录，防止 _auth_failure_tracker 字典无限增长。
        返回被清理的 IP 条目数。"""
        now = time.time()
        async with self._auth_failure_lock:
            expired_keys: list[str] = []
            empty_keys: list[str] = []
            for ip_key, timestamps in self._auth_failure_tracker.items():
                if not timestamps:
                    empty_keys.append(ip_key)
                    continue
                # 仅保留 TTL 内的失败记录
                fresh = [t for t in timestamps if now - t < self._auth_failure_ttl]
                if fresh:
                    self._auth_failure_tracker[ip_key] = fresh
                else:
                    expired_keys.append(ip_key)
            for k in expired_keys + empty_keys:
                self._auth_failure_tracker.pop(k, None)
            return len(expired_keys) + len(empty_keys)

    async def check_register_renewal(self, gb_id: str, call_id: str) -> bool:
        key = str(gb_id or "")
        cid = str(call_id or "")
        if not key or not cid:
            return False
        existing = self._register_call_ids.get(key)
        return existing == cid

    async def record_register_call_id(self, gb_id: str, call_id: str, ttl: int = 3660) -> None:
        key = str(gb_id or "")
        cid = str(call_id or "")
        if not key or not cid:
            return
        self._register_call_ids[key] = cid
        self._register_call_ids_ts[key] = time.time()
        if len(self._register_call_ids) > 10000:
            now = time.time()
            expired_keys = [k for k, ts in self._register_call_ids_ts.items() if now - ts > ttl * 2]
            for k in expired_keys:
                self._register_call_ids.pop(k, None)
                self._register_call_ids_ts.pop(k, None)


_backend_instance: SipStateBackend | None = None
_backend_lock = threading.Lock()


def get_sip_state_backend() -> SipStateBackend:
    global _backend_instance
    if _backend_instance is not None:
        return _backend_instance
    with _backend_lock:
        if _backend_instance is not None:
            return _backend_instance
        from app.core.config import settings
        backend_type = (getattr(settings, "SIP_STATE_BACKEND", "local") or "local").strip().lower()
        if backend_type == "redis":
            try:
                from app.core.redis import redis_client
                if not redis_client:
                    logger.warning(
                        "SIP_STATE_BACKEND=redis but redis_client is not available. "
                        "Falling back to local backend. Check INIT_REDIS_ON_STARTUP and Redis connection."
                    )
                else:
                    from app.sip.state_backend_redis import RedisSipStateBackend
                    _backend_instance = RedisSipStateBackend()
                    logger.info("SipStateBackend: using Redis implementation")
                    return _backend_instance
            except Exception as e:
                logger.warning(f"Failed to initialize RedisSipStateBackend, falling back to local: {e}")
        _backend_instance = LocalSipStateBackend()
        logger.info("SipStateBackend: using local (single-process) implementation")
        # 多实例部署检测告警 — CLUSTER_ENABLED但使用local后端时发出ERROR
        if getattr(settings, "CLUSTER_ENABLED", False):
            logger.error(
                "CLUSTER_ENABLED=True but SIP_STATE_BACKEND=local. "
                "Multi-instance deployment requires SIP_STATE_BACKEND=redis "
                "to avoid SSRC conflicts, nonce replay detection failures, "
                "and rate limit inconsistencies across instances. "
                "Set SIP_STATE_BACKEND=redis and INIT_REDIS_ON_STARTUP=true in .env."
            )
        return _backend_instance
