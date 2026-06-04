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
    async def check_register_renewal(self, gb_id: str, call_id: str) -> bool: ...
    async def record_register_call_id(self, gb_id: str, call_id: str, ttl: int = 3660) -> None: ...


class LocalSipStateBackend:
    def __init__(self):
        self._ssrc_waiters: dict[str, asyncio.Event] = {}
        self._ssrc_waiters_lock = asyncio.Lock()
        self._ssrc_waiters_max_size = 5000
        self._invite_rate_buckets: dict[str, list[float]] = {}
        self._invite_rate_lock = asyncio.Lock()
        self._nonce_nc_tracker: dict[tuple[str, str], tuple[int, float]] = {}
        self._nonce_nc_max_size = 10000
        self._nonce_nc_ttl = 300
        self._auth_failure_tracker: dict[str, list[float]] = {}
        self._auth_failure_ttl = 300
        self._auth_failure_max_size = 5000
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
        now = time.time()
        key = str(ip or "")
        if key not in self._auth_failure_tracker:
            self._auth_failure_tracker[key] = []
        self._auth_failure_tracker[key] = [t for t in self._auth_failure_tracker[key] if now - t < self._auth_failure_ttl]
        self._auth_failure_tracker[key].append(now)
        if len(self._auth_failure_tracker) > self._auth_failure_max_size:
            sorted_ips = sorted(self._auth_failure_tracker.items(), key=lambda x: min(x[1]) if x[1] else now)
            for ip_key, _ in sorted_ips[:len(self._auth_failure_tracker) - self._auth_failure_max_size + 100]:
                self._auth_failure_tracker.pop(ip_key, None)
        return len(self._auth_failure_tracker[key])

    async def clear_auth_failure(self, ip: str) -> None:
        self._auth_failure_tracker.pop(str(ip or ""), None)

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
