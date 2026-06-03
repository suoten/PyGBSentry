from __future__ import annotations
import asyncio
import time
from loguru import logger
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.sip.state_backend import LocalSipStateBackend




class RedisSipStateBackend:
    def __init__(self):
        self._local_fallback: LocalSipStateBackend | None = None
        self._prefix: str = ""
        try:
            from app.core.config import settings
            self._prefix = getattr(settings, "SIP_STATE_BACKEND_REDIS_PREFIX", "gb:sip:state:") or "gb:sip:state:"
        except Exception:
            self._prefix = "gb:sip:state:"

    def _get_redis(self) -> Any:  # 添加返回类型注解，避免 pyright 推断为 Never
        try:
            from app.core.redis import redis_client
            if redis_client:
                return redis_client
        except Exception as e:
            logger.warning(f"Error: {e}")
        return None

    def _get_local_fallback(self):
        if self._local_fallback is None:
            from app.sip.state_backend import LocalSipStateBackend
            self._local_fallback = LocalSipStateBackend()
        return self._local_fallback

    async def register_ssrc_waiter(self, ssrc: str) -> None:
        r = self._get_redis()
        if r is None:  # 显式 None 守卫，避免 pyright reportGeneralTypeIssues
            await self._get_local_fallback().register_ssrc_waiter(ssrc)
            return
        try:
            await r.setex(f"{self._prefix}ssrc:waiter:{ssrc}", 30, "1")
        except Exception:
            logger.warning("Redis register_ssrc_waiter failed, falling back to local")
            await self._get_local_fallback().register_ssrc_waiter(ssrc)

    async def wait_ssrc_stream(self, ssrc: str, timeout: float = 8.0) -> bool:
        r = self._get_redis()
        if r is None:  # 显式 None 守卫
            return await self._get_local_fallback().wait_ssrc_stream(ssrc, timeout)
        try:
            waiter_key = f"{self._prefix}ssrc:waiter:{ssrc}"
            start = time.monotonic()
            pubsub = r.pubsub()
            channel = f"{self._prefix}ssrc:ready:{ssrc}"
            await pubsub.subscribe(channel)
            try:
                deadline = start + timeout
                while time.monotonic() < deadline:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    try:
                        msg = await asyncio.wait_for(pubsub.get_message(timeout=min(remaining, 1.0)), timeout=min(remaining, 1.0) + 0.5)
                        if msg and msg.get("type") == "message":
                            return True
                        elif msg and msg.get("type") in ("subscribe", "unsubscribe"):
                            continue
                    except asyncio.TimeoutError:
                        pass
                    val = await r.get(waiter_key)
                    if val is None:
                        logger.debug("Redis wait_ssrc_stream: waiter key deleted, stream ready (ssrc=%s)", ssrc)
                        return True
                return False
            finally:
                await pubsub.unsubscribe(channel)
                await pubsub.close()
        except Exception:
            logger.warning("Redis wait_ssrc_stream failed, falling back to local")
        return await self._get_local_fallback().wait_ssrc_stream(ssrc, timeout)

    async def notify_ssrc_registered(self, ssrc: str) -> None:
        r = self._get_redis()
        if r is None:  # 显式 None 守卫
            await self._get_local_fallback().notify_ssrc_registered(ssrc)
            return
        try:
            await r.publish(f"{self._prefix}ssrc:ready:{ssrc}", "1")
            await r.delete(f"{self._prefix}ssrc:waiter:{ssrc}")
        except Exception:
            logger.warning("Redis notify_ssrc_registered failed, falling back to local")
            await self._get_local_fallback().notify_ssrc_registered(ssrc)

    async def unregister_ssrc_waiter(self, ssrc: str) -> None:
        r = self._get_redis()
        if r is None:  # 显式 None 守卫
            await self._get_local_fallback().unregister_ssrc_waiter(ssrc)
            return
        try:
            await r.delete(f"{self._prefix}ssrc:waiter:{ssrc}")
        except Exception:
            logger.warning("Redis unregister_ssrc_waiter failed, falling back to local")
            await self._get_local_fallback().unregister_ssrc_waiter(ssrc)

    async def consume_invite_rate(
        self, tenant_id: str, device_id: str, window: float = 10.0, per_device: int = 30, per_tenant: int = 300
    ) -> tuple[bool, str]:
        r = self._get_redis()
        if r is None:  # 显式 None 守卫
            return await self._get_local_fallback().consume_invite_rate(tenant_id, device_id, window, per_device, per_tenant)
        try:
            now = time.time()
            device_key = f"{self._prefix}invite:rate:{tenant_id}:{device_id}"
            tenant_key = f"{self._prefix}invite:rate:{tenant_id}:__tenant__"
            pipe = r.pipeline()
            pipe.zremrangebyscore(device_key, 0, now - window)
            pipe.zremrangebyscore(tenant_key, 0, now - window)
            pipe.zcard(device_key)
            pipe.zcard(tenant_key)
            results = await pipe.execute()
            device_count = int(results[2] or 0)
            tenant_count = int(results[3] or 0)
            if device_count >= per_device:
                return False, f"device_rate_limited ({device_count}/{per_device} per {window}s)"
            if tenant_count >= per_tenant:
                return False, f"tenant_rate_limited ({tenant_count}/{per_tenant} per {window}s)"
            pipe2 = r.pipeline()
            pipe2.zadd(device_key, {str(now): now})
            pipe2.zadd(tenant_key, {str(now): now})
            pipe2.expire(device_key, int(window) + 5)
            pipe2.expire(tenant_key, int(window) + 5)
            await pipe2.execute()
            return True, ""
        except Exception:
            logger.warning("Redis consume_invite_rate failed, falling back to local")
        return await self._get_local_fallback().consume_invite_rate(tenant_id, device_id, window, per_device, per_tenant)

    async def check_nonce_nc(self, user: str, nonce: str, nc: int) -> bool:
        r = self._get_redis()
        if r is None:  # 显式 None 守卫
            return await self._get_local_fallback().check_nonce_nc(user, nonce, nc)
        try:
            key = f"{self._prefix}nonce:nc:{user}:{nonce}"
            last_nc_str = await r.get(key)
            last_nc = int(last_nc_str or -1) if last_nc_str is not None else -1
            if nc <= last_nc:
                return False
            await r.set(key, str(nc), ex=300)
            return True
        except Exception:
            logger.warning("Redis check_nonce_nc failed, falling back to local")
        return await self._get_local_fallback().check_nonce_nc(user, nonce, nc)

    async def record_auth_failure(self, ip: str) -> int:
        r = self._get_redis()
        if r is None:  # 显式 None 守卫
            return await self._get_local_fallback().record_auth_failure(ip)
        try:
            now = time.time()
            key = f"{self._prefix}auth:fail:{ip}"
            pipe = r.pipeline()
            pipe.zremrangebyscore(key, 0, now - 300)
            pipe.zadd(key, {str(now): now})
            pipe.zcard(key)
            pipe.expire(key, 310)
            results = await pipe.execute()
            return int(results[2] or 0)
        except Exception:
            logger.warning("Redis record_auth_failure failed, falling back to local")
        return await self._get_local_fallback().record_auth_failure(ip)

    async def clear_auth_failure(self, ip: str) -> None:
        r = self._get_redis()
        if r is None:  # 显式 None 守卫
            await self._get_local_fallback().clear_auth_failure(ip)
            return
        try:
            await r.delete(f"{self._prefix}auth:fail:{ip}")
        except Exception:
            logger.warning("Redis clear_auth_failure failed, falling back to local")
            await self._get_local_fallback().clear_auth_failure(ip)

    async def check_register_renewal(self, gb_id: str, call_id: str) -> bool:
        r = self._get_redis()
        if r is None:  # 显式 None 守卫
            return await self._get_local_fallback().check_register_renewal(gb_id, call_id)
        try:
            key = f"{self._prefix}register:callid:{gb_id}"
            existing = await r.get(key)
            if existing and (existing.decode("utf-8") if isinstance(existing, bytes) else str(existing)) == call_id:  # 运算符优先级导致注册续期判断错误
                return True
            return False
        except Exception:
            logger.warning("Redis check_register_renewal failed, falling back to local")
        return await self._get_local_fallback().check_register_renewal(gb_id, call_id)

    async def record_register_call_id(self, gb_id: str, call_id: str, ttl: int = 3660) -> None:
        r = self._get_redis()
        if r is None:  # 显式 None 守卫
            await self._get_local_fallback().record_register_call_id(gb_id, call_id, ttl)
            return
        try:
            key = f"{self._prefix}register:callid:{gb_id}"
            await r.setex(key, max(60, ttl), call_id)
        except Exception:
            logger.warning("Redis record_register_call_id failed, falling back to local")
            await self._get_local_fallback().record_register_call_id(gb_id, call_id, ttl)
