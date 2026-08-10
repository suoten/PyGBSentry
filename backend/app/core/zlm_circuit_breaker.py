import asyncio
import time
from loguru import logger
from enum import Enum
from dataclasses import dataclass, field

try:
    from app.core.metrics import CIRCUIT_BREAKER_STATE, CIRCUIT_BREAKER_FAILURES
    _metrics_available = True
except ImportError:
    _metrics_available = False


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    name: str
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 3
    _state: CircuitState = CircuitState.CLOSED
    _failure_count: int = 0
    _success_count: int = 0
    _last_failure_time: float = 0.0
    _half_open_calls: int = 0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    # W-26 state property no longer mutates _state; transition logic moved to allow_request
    @property
    def state(self) -> CircuitState:
        return self._state

    def _transition(self, new_state: CircuitState) -> None:
        """Transition to a new state and update Prometheus metrics."""
        self._state = new_state
        if _metrics_available:
            try:
                CIRCUIT_BREAKER_STATE.labels(node=self.name).set(
                    {"closed": 0, "open": 1, "half_open": 2}.get(new_state.value, 0)
                )
            except Exception as _metric_err:
                # FIX [2026-07-17 P3-22]: 描述性日志替代静默吞异常
                logger.debug(f"CircuitBreaker [{self.name}]: failed to update state metric: {_metric_err}")

    async def allow_request(self) -> bool:
        async with self._lock:
            # OPEN -> HALF_OPEN transition now happens under lock
            if self._state == CircuitState.OPEN:
                if (time.time() - self._last_failure_time) > self.recovery_timeout:
                    self._transition(CircuitState.HALF_OPEN)
                    self._half_open_calls = 0
            current = self._state
            if current == CircuitState.CLOSED:
                return True
            if current == CircuitState.HALF_OPEN:
                if self._half_open_calls < self.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                return False
            return False

    async def record_success(self) -> None:
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.half_open_max_calls:
                    self._transition(CircuitState.CLOSED)
                    self._failure_count = 0
                    self._success_count = 0
                    logger.info(f"CircuitBreaker [{self.name}] recovered to CLOSED")
            elif self._state == CircuitState.CLOSED:
                self._failure_count = max(0, self._failure_count - 1)

    async def record_failure(self) -> None:
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if _metrics_available:
                try:
                    CIRCUIT_BREAKER_FAILURES.labels(node=self.name).inc()
                except Exception as _metric_err:
                    # FIX [2026-07-17 P3-22]: 描述性日志替代静默吞异常
                    logger.debug(f"CircuitBreaker [{self.name}]: failed to update failures metric: {_metric_err}")
            if self._state == CircuitState.HALF_OPEN:
                self._transition(CircuitState.OPEN)
                self._success_count = 0
                logger.warning(f"CircuitBreaker [{self.name}] HALF_OPEN -> OPEN (failure in half-open)")
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    self._transition(CircuitState.OPEN)
                    logger.warning(
                        f"CircuitBreaker [{self.name}] CLOSED -> OPEN "
                        f"(failures={self._failure_count}, threshold={self.failure_threshold})"
                    )

    def stats(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "last_failure_time": self._last_failure_time,
        }


class ZlmNodeClientManager:
    def __init__(self):
        self._clients: dict[str, dict] = {}
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = asyncio.Lock()

    async def get_or_create_client(self, node_id: str, host: str, http_port: int) -> dict:
        async with self._lock:
            if node_id not in self._clients:
                import httpx
                client = httpx.AsyncClient(
                    timeout=httpx.Timeout(5.0, connect=3.0),
                    limits=httpx.Limits(max_connections=50, max_keepalive_connections=10),
                )
                self._clients[node_id] = {
                    "client": client,
                    "host": host,
                    "http_port": http_port,
                    "base_url": f"http://{host}:{http_port}",
                }
                self._breakers[node_id] = CircuitBreaker(
                    name=f"zlm_{node_id}",
                    failure_threshold=5,
                    recovery_timeout=30.0,
                )
            return self._clients[node_id]

    async def get_breaker(self, node_id: str) -> CircuitBreaker | None:
        return self._breakers.get(node_id)

    async def close_all(self) -> None:
        async with self._lock:
            for info in self._clients.values():
                client = info.get("client")
                if client and not client.is_closed:
                    # FIX: [2026-07-16 P0] 原 contextlib 导入在文件末尾（line 193），
                    # close_all 方法定义时 contextlib 尚未导入，运行时 NameError。
                    # 同时将静默 suppress 改为带日志的 try/except 便于排查资源泄漏。
                    try:
                        await client.aclose()
                    except Exception as _close_err:
                        logger.warning(f"ZlmNodeClientManager: failed to close httpx client: {_close_err}")
            self._clients.clear()
            self._breakers.clear()

    async def call_zlm_api(
        self,
        node_id: str,
        api_path: str,
        params: dict | None = None,
        data: dict | None = None,
        timeout: float = 5.0,
    ) -> dict | None:
        # P1-fix [2026-07-17]: 删除 GET 通道，强制要求通过 POST body 传递参数
        # 原代码 `else: resp = await client.get(url, params=params or {})` 会将 secret
        # 等敏感参数拼到 URL query，违反项目硬约束。此方法当前未被调用（死代码），
        # 但保留 GET 通道是潜在陷阱。现在 data=None 时抛出 ValueError，强制调用方使用 POST。
        if data is None:
            raise ValueError(
                f"call_zlm_api requires 'data' (POST body); GET channel removed for security. "
                f"node={node_id} api={api_path}"
            )
        breaker = self._breakers.get(node_id)
        if breaker and not await breaker.allow_request():
            logger.warning(f"ZLM API call blocked by circuit breaker for node {node_id}: {api_path}")
            return None

        client_info = self._clients.get(node_id)
        if not client_info:
            logger.error(f"No HTTP client for node {node_id}")
            return None

        client = client_info["client"]
        base_url = client_info["base_url"]
        url = f"{base_url}/index/api/{api_path}"

        try:
            resp = await client.post(url, data=data, timeout=timeout)
            result = resp.json()
            if breaker:
                await breaker.record_success()
            return result
        except Exception as e:
            if breaker:
                await breaker.record_failure()
            logger.warning(f"ZLM API call failed for node {node_id} api={api_path}: {e}")
            return None

    def stats(self) -> dict:
        return {
            "nodes": list(self._clients.keys()),
            "breakers": {nid: b.stats() for nid, b in self._breakers.items()},
        }


zlm_node_client_manager = ZlmNodeClientManager()
