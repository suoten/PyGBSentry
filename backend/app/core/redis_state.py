"""
Redis 状态适配器 — 统一抽象层

提供 RedisDict / RedisSet / RedisSortedSet / SsrcWaiterManager，
封装序列化/反序列化、TTL 管理、容错处理，
用于替代进程内全局变量（dict/set），支持多实例部署。
"""

import asyncio
import json
from loguru import logger
from typing import Any

from app.core.redis import redis_client
# P0-16 [2026-07-17]: 使用项目统一的 fire_and_forget 替代裸 create_task
from app.core.async_utils import fire_and_forget




class RedisStateError(Exception):
    """Redis 状态操作失败时抛出"""
    pass


def _ensure_redis():
    """确保 Redis 客户端可用，不可用时抛出 RedisStateError"""
    if not redis_client:
        raise RedisStateError("Redis not available")


class RedisDict:
    """Redis Hash 后端的 dict 替代品

    用法:
        rd = RedisDict("p3s:thin_job", ttl=3600)
        await rd.set("key1", {"field1": "val1", "field2": "val2"})
        data = await rd.get("key1")  # -> {"field1": "val1", "field2": "val2"} or None
    """

    def __init__(self, key_prefix: str, ttl: int | None = None):
        self._prefix = key_prefix
        self._ttl = ttl

    def _key(self, k: str) -> str:
        return f"{self._prefix}:{k}"

    async def get(self, k: str) -> dict[str, Any] | None:
        _ensure_redis()
        raw = await redis_client.hgetall(self._key(k))
        if not raw:
            return None
        result = {}
        for field, v in raw.items():
            if isinstance(v, str):
                try:
                    result[field] = json.loads(v)
                except (json.JSONDecodeError, TypeError):
                    result[field] = v
            else:
                result[field] = v
        return result

    async def set(self, k: str, value: dict[str, Any]) -> None:
        _ensure_redis()
        # 将 value 中的非字符串值序列化为 JSON 字符串存储
        mapped = {}
        for field, v in value.items():
            mapped[field] = json.dumps(v) if not isinstance(v, str) else v
        await redis_client.hset(self._key(k), mapping=mapped)
        if self._ttl:
            await redis_client.expire(self._key(k), self._ttl)

    async def delete(self, k: str) -> None:
        _ensure_redis()
        await redis_client.delete(self._key(k))

    async def keys(self) -> list[str]:
        _ensure_redis()
        pattern = f"{self._prefix}:*"
        # replaced KEYS with SCAN to avoid blocking Redis
        all_keys = []
        cursor = 0
        while True:
            cursor, batch = await redis_client.scan(cursor, match=pattern, count=200)
            all_keys.extend(batch)
            if cursor == 0:
                break
        prefix_len = len(self._prefix) + 1
        return [k[prefix_len:] for k in all_keys]

    async def size(self) -> int:
        _ensure_redis()
        # replaced KEYS with SCAN count to avoid blocking Redis
        count = 0
        cursor = 0
        pattern = f"{self._prefix}:*"
        while True:
            cursor, batch = await redis_client.scan(cursor, match=pattern, count=200)
            count += len(batch)
            if cursor == 0:
                break
        return count

    async def clear(self) -> None:
        _ensure_redis()
        # replaced KEYS with SCAN to avoid blocking Redis
        all_keys = []
        cursor = 0
        pattern = f"{self._prefix}:*"
        while True:
            cursor, batch = await redis_client.scan(cursor, match=pattern, count=200)
            all_keys.extend(batch)
            if cursor == 0:
                break
        if all_keys:
            await redis_client.delete(*all_keys)

    async def get_field(self, k: str, field: str) -> Any | None:
        """获取 Hash 中单个字段值，自动反序列化 JSON"""
        _ensure_redis()
        raw = await redis_client.hget(self._key(k), field)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    async def set_field(self, k: str, field: str, value: Any) -> None:
        """设置 Hash 中单个字段值，自动序列化非字符串值"""
        _ensure_redis()
        serialized = json.dumps(value) if not isinstance(value, str) else value
        await redis_client.hset(self._key(k), field, serialized)
        if self._ttl:
            await redis_client.expire(self._key(k), self._ttl)


class RedisSet:
    """Redis Set 后端的 set 替代品

    用法:
        rs = RedisSet("p3s:play_inflight")
        await rs.add("stream_1")
        exists = await rs.contains("stream_1")  # -> True
    """

    def __init__(self, key: str, ttl: int | None = None):
        self._key = key
        self._ttl = ttl

    async def add(self, member: str) -> None:
        _ensure_redis()
        await redis_client.sadd(self._key, member)
        if self._ttl:
            await redis_client.expire(self._key, self._ttl)

    async def remove(self, member: str) -> None:
        _ensure_redis()
        await redis_client.srem(self._key, member)

    async def contains(self, member: str) -> bool:
        _ensure_redis()
        return bool(await redis_client.sismember(self._key, member))

    async def members(self) -> set[str]:
        _ensure_redis()
        return set(await redis_client.smembers(self._key))

    async def size(self) -> int:
        _ensure_redis()
        return await redis_client.scard(self._key)

    async def clear(self) -> None:
        _ensure_redis()
        await redis_client.delete(self._key)


class RedisSortedSet:
    """Redis Sorted Set 后端，用于带时间戳的追踪数据

    用法:
        rz = RedisSortedSet("p3s:sip_auth_fail:192.168.1.1", ttl=300)
        await rz.add("attempt_1", time.time())
        count = await rz.card()
    """

    def __init__(self, key: str, ttl: int | None = None):
        self._key = key
        self._ttl = ttl

    async def add(self, member: str, score: float) -> None:
        _ensure_redis()
        await redis_client.zadd(self._key, {member: score})
        if self._ttl:
            await redis_client.expire(self._key, self._ttl)

    async def remove(self, member: str) -> None:
        _ensure_redis()
        await redis_client.zrem(self._key, member)

    async def remove_range_by_score(self, min_score: float, max_score: float) -> None:
        _ensure_redis()
        await redis_client.zremrangebyscore(self._key, min_score, max_score)

    async def card(self) -> int:
        _ensure_redis()
        return int(await redis_client.zcard(self._key) or 0)

    async def range_by_score(self, min_score: float, max_score: float,
                             start: int = 0, end: int = -1) -> list[str]:
        _ensure_redis()
        return await redis_client.zrangebyscore(self._key, min_score, max_score,
                                                 start=start, num=end if end != -1 else None)

    async def clear(self) -> None:
        _ensure_redis()
        await redis_client.delete(self._key)


class FallbackDict:
    """Redis 优先、内存回退的 dict 替代品

    当 Redis 可用时，数据存储在 Redis Hash 中（支持多实例共享）；
    当 Redis 不可用时，自动回退到进程内 dict（单实例模式）。

    用法:
        fd = FallbackDict("p3s:thin_job", ttl=3600)
        await fd.set("key1", {"field1": "val1"})
        data = await fd.get("key1")  # -> {"field1": "val1"} or None
        await fd.delete("key1")
        all_keys = await fd.keys()
    """

    def __init__(self, key_prefix: str, ttl: int | None = None):
        self._redis = RedisDict(key_prefix, ttl)
        self._fallback: dict[str, dict[str, Any]] = {}
        self._prefix = key_prefix
        self._was_fallback: bool = False  # P2 状态一致性 — Redis恢复后同步内存数据

    def _redis_available(self) -> bool:
        return redis_client is not None

    async def _sync_to_redis(self) -> None:
        """P2 状态一致性 — Redis恢复后同步内存数据"""
        if not self._fallback:
            return
        try:
            count = len(self._fallback)
            for k, v in self._fallback.items():
                await self._redis.set(k, v)
            self._fallback.clear()
            self._was_fallback = False
            logger.debug(f"FallbackDict._sync_to_redis: synced {count} keys back to Redis for prefix={self._prefix}")
        except Exception as e:
            logger.debug(f"FallbackDict._sync_to_redis failed: {e}")

    async def get(self, k: str) -> dict[str, Any] | None:
        if self._redis_available():
            try:
                return await self._redis.get(k)
            except Exception as e:
                logger.debug(f"RedisDict.get fallback: {e}")
        return self._fallback.get(k)

    async def set(self, k: str, value: dict[str, Any]) -> None:
        # P2 状态一致性 — Redis恢复后同步内存数据
        if self._redis_available():
            try:
                if self._was_fallback and self._fallback:
                    await self._sync_to_redis()
                await self._redis.set(k, value)
                return
            except Exception as e:
                logger.debug(f"RedisDict.set fallback: {e}")
        self._fallback[k] = value
        self._was_fallback = True

    async def delete(self, k: str) -> None:
        if self._redis_available():
            try:
                await self._redis.delete(k)
                return
            except Exception as e:
                logger.debug(f"RedisDict.delete fallback: {e}")
        self._fallback.pop(k, None)

    async def keys(self) -> list[str]:
        if self._redis_available():
            try:
                return await self._redis.keys()
            except Exception as e:
                logger.debug(f"RedisDict.keys fallback: {e}")
        return list(self._fallback.keys())

    async def size(self) -> int:
        if self._redis_available():
            try:
                return await self._redis.size()
            except Exception as e:
                logger.debug(f"RedisDict.size fallback: {e}")
        return len(self._fallback)

    async def clear(self) -> None:
        if self._redis_available():
            try:
                await self._redis.clear()
                return
            except Exception as e:
                logger.debug(f"RedisDict.clear fallback: {e}")
        self._fallback.clear()

    async def items(self) -> list[tuple[str, dict[str, Any]]]:
        """获取所有键值对（用于遍历，如清理过期条目）"""
        if self._redis_available():
            try:
                all_keys = await self._redis.keys()
                result = []
                for k in all_keys:
                    v = await self._redis.get(k)
                    if v is not None:
                        result.append((k, v))
                return result
            except Exception as e:
                logger.debug(f"RedisDict.items fallback: {e}")
        return list(self._fallback.items())

    async def pop(self, k: str, default: Any = None) -> dict[str, Any] | None:
        """删除并返回指定键的值"""
        val = await self.get(k)
        if val is not None:
            await self.delete(k)
            return val
        return default

    def get_sync(self, k: str) -> dict[str, Any] | None:
        """同步获取（仅从内存回退中读取，用于非 async 上下文）"""
        return self._fallback.get(k)

    def __contains__(self, k: str) -> bool:
        """同步包含检查（仅检查内存回退，用于非 async 上下文）"""
        return k in self._fallback

    def __len__(self) -> int:
        """同步长度（仅内存回退，用于非 async 上下文）"""
        return len(self._fallback)


class SsrcWaiterManager:
    """跨实例 SSRC 等待通知管理器

    使用 Redis Pub/Sub 实现跨实例事件通知，
    替代原 _SSRC_WAITERS: dict[str, asyncio.Event] 进程内变量。

    用法:
        mgr = SsrcWaiterManager()
        # 等待方:
        data = await mgr.wait("ssrc_123", timeout=10.0)
        # 通知方:
        await mgr.notify("ssrc_123", {"ssrc": "123", "port": 8000})
    """

    def __init__(self):
        self._local_events: dict[str, asyncio.Event] = {}
        self._local_results: dict[str, dict] = {}
        self._pubsub = None
        self._listener_task: asyncio.Task | None = None

    async def _ensure_listener(self):
        """确保 Pub/Sub 监听器已启动"""
        if self._listener_task is not None:
            return
        _ensure_redis()
        self._pubsub = redis_client.pubsub()
        await self._pubsub.psubscribe("p3s:sip:ssrc:ready:*")
        self._listener_task = fire_and_forget(
            self._listen_loop(),
            name="redis_state_ssrc_listener",
        )

    async def _listen_loop(self):
        """Pub/Sub 消息监听循环"""
        try:
            async for message in self._pubsub.listen():
                if message["type"] != "pmessage":
                    continue
                channel = message["channel"]
                if isinstance(channel, bytes):
                    channel = channel.decode()
                # 提取 ssrc: p3s:sip:ssrc:ready:{ssrc}
                parts = channel.split(":")
                ssrc = parts[-1] if parts else ""
                data_str = message["data"]
                if isinstance(data_str, bytes):
                    data_str = data_str.decode()
                try:
                    data = json.loads(data_str)
                except (json.JSONDecodeError, TypeError):
                    data = {}
                self._local_results[ssrc] = data
                event = self._local_events.get(ssrc)
                if event:
                    event.set()
        except asyncio.CancelledError:
            pass  # intentional: asyncio cancellation
        except Exception as e:
            logger.warning(f"SSRC Pub/Sub listener error: {e}")

    async def wait(self, ssrc: str, timeout: float = 10.0) -> dict:
        """等待 SSRC 就绪"""
        await self._ensure_listener()
        event = asyncio.Event()
        self._local_events[ssrc] = event
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return self._local_results.pop(ssrc, {})
        except asyncio.TimeoutError:
            raise TimeoutError(f"SSRC {ssrc} wait timed out after {timeout}s")
        finally:
            self._local_events.pop(ssrc, None)

    async def notify(self, ssrc: str, data: dict) -> None:
        """通知 SSRC 就绪"""
        _ensure_redis()
        await redis_client.publish(
            f"p3s:sip:ssrc:ready:{ssrc}",
            json.dumps(data, default=str)
        )

    async def close(self):
        """关闭 Pub/Sub 监听器"""
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass  # intentional: asyncio cancellation
            self._listener_task = None
        if self._pubsub:
            try:
                await self._pubsub.punsubscribe()
                await self._pubsub.close()
            except Exception as e:
                logger.warning(f"Error: {e}")
            self._pubsub = None