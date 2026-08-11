"""Redis-backed implementation of SipStateBackend.

FIX [2026-07-13]: 此文件此前缺失，导致 SIP_STATE_BACKEND=redis 时：
  1. get_sip_state_backend() 抛 ImportError 后降级为 local（单进程）
  2. 服务器上手装了不完整版本，缺少 cleanup_auth_failures 方法，
     导致 server._prune_loop 定期报错：
     'RedisSipStateBackend' object has no attribute 'cleanup_auth_failures'

本实现完整实现 SipStateBackend Protocol 的所有 11 个方法，支持多实例部署
（CLUSTER_ENABLED=True 时跨节点共享 SIP 状态）。

设计要点：
  - SSRC 等待/通知：用 Redis List + BLPOP 实现跨进程事件通知（单等待者模式）
  - INVITE 速率限制：用 Sorted Set + Lua 脚本实现原子滑动窗口
  - nonce/nc 防重放：用 Redis key + Lua 脚本实现原子比较-设置
  - 鉴权失败记录：用 Sorted Set（score=时间戳）+ 自动 TTL 过期
  - 注册 call_id：用 Redis key + TTL 实现跨节点注册续约检测

容错策略（fail-open）：
  - Redis 不可用时，安全降级：速率限制放行、nonce 放行、SSRC 等待返回 False
  - 避免 Redis 故障导致 SIP 服务完全不可用
  - 所有异常被 catch 并 log warning，不向上抛出
"""

import asyncio
import math
import time
import uuid

from loguru import logger


# ---------------------------------------------------------------------------
# Lua 脚本（保证原子性）
# ---------------------------------------------------------------------------

# consume_invite_rate: 原子滑动窗口速率限制
# KEYS[1] = device_key, KEYS[2] = tenant_key
# ARGV[1] = now, ARGV[2] = window, ARGV[3] = per_device, ARGV[4] = per_tenant, ARGV[5] = member
_LUA_CONSUME_INVITE_RATE = """
local device_key = KEYS[1]
local tenant_key = KEYS[2]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local per_device = tonumber(ARGV[3])
local per_tenant = tonumber(ARGV[4])
local member = ARGV[5]
local cutoff = now - window
redis.call('ZREMRANGEBYSCORE', device_key, 0, cutoff)
redis.call('ZREMRANGEBYSCORE', tenant_key, 0, cutoff)
local device_count = redis.call('ZCARD', device_key)
local tenant_count = redis.call('ZCARD', tenant_key)
if device_count >= per_device then
    return {0, 'device_rate_limited (' .. device_count .. '/' .. per_device .. ' per ' .. window .. 's)'}
end
if tenant_count >= per_tenant then
    return {0, 'tenant_rate_limited (' .. tenant_count .. '/' .. per_tenant .. ' per ' .. window .. 's)'}
end
redis.call('ZADD', device_key, now, member)
redis.call('ZADD', tenant_key, now, member)
redis.call('EXPIRE', device_key, math.ceil(window * 2))
redis.call('EXPIRE', tenant_key, math.ceil(window * 2))
return {1, ''}
"""

# check_nonce_nc: 原子比较-设置 nonce/nc 防重放
# KEYS[1] = nonce_nc key
# ARGV[1] = new_nc, ARGV[2] = ttl
_LUA_CHECK_NONCE_NC = """
local key = KEYS[1]
local new_nc = tonumber(ARGV[1])
local ttl = tonumber(ARGV[2])
local old_val = redis.call('GET', key)
local old_nc = old_val and tonumber(old_val) or -1
if new_nc <= old_nc then
    return 0
end
redis.call('SET', key, ARGV[1], 'EX', ttl)
return 1
"""


class RedisSipStateBackend:
    """Redis-backed SipStateBackend for multi-instance deployments.

    所有 SIP 状态（SSRC 等待、速率限制、nonce/nc、鉴权失败、注册续约）
    存储在 Redis 中，支持多节点共享。适用于 CLUSTER_ENABLED=True 场景。
    """

    def __init__(self):
        from app.core.config import settings

        # 配置项（与 LocalSipStateBackend 保持一致）
        try:
            self._nonce_nc_ttl = settings.SIP_NONCE_NC_TTL_SECONDS
        except Exception:
            self._nonce_nc_ttl = 300
        self._auth_failure_ttl = 300
        self._ssrc_wait_ttl = 60
        self._ssrc_notify_ttl = 10
        self._register_call_id_ttl = 3660

        # Key 前缀
        self._prefix = "pygbsentry:sip"
        self._ssrc_wait_prefix = f"{self._prefix}:ssrc_wait:"
        self._ssrc_notify_prefix = f"{self._prefix}:ssrc_notify:"
        self._invite_rate_prefix = f"{self._prefix}:invite_rate:"
        self._nonce_nc_prefix = f"{self._prefix}:nonce_nc:"
        self._auth_failure_prefix = f"{self._prefix}:auth_failure:"
        self._register_call_id_prefix = f"{self._prefix}:register_call_id:"

    def _get_client(self):
        """获取当前 Redis 客户端（每次调用获取最新引用，避免初始化时序问题）。"""
        try:
            from app.core.redis import redis_client
            return redis_client
        except Exception:
            return None

    # -------------------------------------------------------------------
    # SSRC 等待/通知（跨进程事件通知，单等待者模式）
    # -------------------------------------------------------------------

    async def register_ssrc_waiter(self, ssrc: str) -> None:
        """标记 SSRC 等待者存在。"""
        key = str(ssrc or "").strip()
        if not key:
            return
        client = self._get_client()
        if not client:
            return
        try:
            await client.set(f"{self._ssrc_wait_prefix}{key}", "1", ex=self._ssrc_wait_ttl)
        except Exception as e:
            logger.warning(f"RedisSipStateBackend.register_ssrc_waiter error: {e}")

    async def wait_ssrc_stream(self, ssrc: str, timeout: float = 8.0) -> bool:
        """阻塞等待 SSRC 流就绪通知。

        用 BLPOP 实现：notify 端 LPUSH 消息，wait 端 BLPOP 消费。
        超时返回 False，收到消息返回 True。
        """
        key = str(ssrc or "").strip()
        if not key:
            return False
        client = self._get_client()
        if not client:
            return False
        notify_key = f"{self._ssrc_notify_prefix}{key}"
        # BLPOP 的 timeout 参数：Redis 协议要求整数秒。
        # 用 max(1, ceil(timeout)) 确保至少 1 秒等待，且覆盖 float 精度。
        blpop_timeout = max(1, int(math.ceil(timeout)))
        try:
            result = await client.blpop(notify_key, timeout=blpop_timeout)
            return result is not None
        except asyncio.TimeoutError:
            return False
        except Exception as e:
            logger.warning(f"RedisSipStateBackend.wait_ssrc_stream error: {e}")
            return False

    async def notify_ssrc_registered(self, ssrc: str) -> None:
        """通知 SSRC 流已就绪。LPUSH 消息到通知 list。"""
        key = str(ssrc or "").strip()
        if not key:
            return
        client = self._get_client()
        if not client:
            return
        notify_key = f"{self._ssrc_notify_prefix}{key}"
        try:
            pipe = client.pipeline()
            pipe.lpush(notify_key, "1")
            pipe.expire(notify_key, self._ssrc_notify_ttl)
            await pipe.execute()
        except Exception as e:
            logger.warning(f"RedisSipStateBackend.notify_ssrc_registered error: {e}")

    async def unregister_ssrc_waiter(self, ssrc: str) -> None:
        """清理 SSRC 等待/通知 key。"""
        key = str(ssrc or "").strip()
        if not key:
            return
        client = self._get_client()
        if not client:
            return
        try:
            await client.delete(
                f"{self._ssrc_wait_prefix}{key}",
                f"{self._ssrc_notify_prefix}{key}",
            )
        except Exception as e:
            logger.warning(f"RedisSipStateBackend.unregister_ssrc_waiter error: {e}")

    # -------------------------------------------------------------------
    # INVITE 速率限制（原子滑动窗口）
    # -------------------------------------------------------------------

    async def consume_invite_rate(
        self, tenant_id: str, device_id: str, window: float = 10.0, per_device: int = 30, per_tenant: int = 300
    ) -> tuple[bool, str]:
        """消耗一次 INVITE 配额，基于滑动窗口速率限制。

        用 Lua 脚本保证 ZREMRANGEBYSCORE + ZCARD + ZADD 的原子性。
        fail-open: Redis 不可用时放行（避免阻塞 SIP 服务）。
        """
        t_id = str(tenant_id or "").strip()
        d_id = str(device_id or "").strip()
        if not t_id or not d_id:
            return True, ""
        client = self._get_client()
        if not client:
            # fail-open: Redis 不可用时放行
            return True, ""
        device_key = f"{self._invite_rate_prefix}{t_id}:{d_id}"
        tenant_key = f"{self._invite_rate_prefix}{t_id}:__tenant__"
        now = time.time()
        member = f"{now}:{uuid.uuid4().hex[:8]}"
        try:
            result = await client.eval(
                _LUA_CONSUME_INVITE_RATE,
                2,
                device_key,
                tenant_key,
                str(now),
                str(window),
                str(per_device),
                str(per_tenant),
                member,
            )
            if result and len(result) >= 2:
                allowed = bool(result[0])
                reason = str(result[1]) if result[1] else ""
                return allowed, reason
            return True, ""
        except Exception as e:
            logger.warning(f"RedisSipStateBackend.consume_invite_rate error: {e}")
            # fail-open
            return True, ""

    # -------------------------------------------------------------------
    # nonce/nc 防重放（原子比较-设置）
    # -------------------------------------------------------------------

    async def check_nonce_nc(self, user: str, nonce: str, nc: int) -> bool:
        """检查 nonce/nc 是否有效（递增），并记录新 nc。

        用 Lua 脚本保证 GET + 比较比较 + SET 的原子性。
        fail-open: Redis 不可用时放行（避免阻塞 SIP 注册）。
        """
        u = str(user or "").strip()
        n = str(nonce or "").strip()
        if not u or not n:
            return True
        try:
            nc_int = int(nc)
        except (TypeError, ValueError):
            return True
        client = self._get_client()
        if not client:
            return True
        key = f"{self._nonce_nc_prefix}{u}:{n}"
        try:
            result = await client.eval(
                _LUA_CHECK_NONCE_NC,
                1,
                key,
                str(nc_int),
                str(self._nonce_nc_ttl),
            )
            return bool(result)
        except Exception as e:
            logger.warning(f"RedisSipStateBackend.check_nonce_nc error: {e}")
            # fail-open
            return True

    # -------------------------------------------------------------------
    # 鉴权失败记录（Sorted Set + TTL）
    # -------------------------------------------------------------------

    async def record_auth_failure(self, ip: str) -> int:
        """记录一次鉴权失败，返回该 IP 在 TTL 窗口内的失败次数。"""
        key_ip = str(ip or "").strip()
        if not key_ip:
            return 0
        client = self._get_client()
        if not client:
            return 0
        key = f"{self._auth_failure_prefix}{key_ip}"
        now = time.time()
        member = f"{now}:{uuid.uuid4().hex[:8]}"
        try:
            pipe = client.pipeline()
            pipe.zadd(key, {member: now})
            pipe.zremrangebyscore(key, 0, now - self._auth_failure_ttl)
            pipe.zcard(key)
            pipe.expire(key, self._auth_failure_ttl * 2)
            results = await pipe.execute()
            # results[0] = zadd 返回新增数, [1] = zrem 返回删除数, [2] = zcard, [3] = expire
            return int(results[2]) if len(results) > 2 else 0
        except Exception as e:
            logger.warning(f"RedisSipStateBackend.record_auth_failure error: {e}")
            return 0

    async def clear_auth_failure(self, ip: str) -> None:
        """清除指定 IP 的鉴权失败记录。"""
        key_ip = str(ip or "").strip()
        if not key_ip:
            return
        client = self._get_client()
        if not client:
            return
        try:
            await client.delete(f"{self._auth_failure_prefix}{key_ip}")
        except Exception as e:
            logger.warning(f"RedisSipStateBackend.clear_auth_failure error: {e}")

    async def cleanup_auth_failures(self) -> int:
        """定期清理过期的鉴权失败记录。

        遍历所有 auth_failure key，用 ZREMRANGEBYSCORE 清理过期 score，
        删除空 key。返回被清理的记录总数。

        注意：record_auth_failure 已在写入时清理该 IP 的过期记录并设置 TTL，
        此方法主要清理"孤立" key（有 key 但长时间未被 record_auth_failure 触及）。
        """
        client = self._get_client()
        if not client:
            return 0
        now = time.time()
        cutoff = now - self._auth_failure_ttl
        cleaned = 0
        try:
            async for key in client.scan_iter(
                match=f"{self._auth_failure_prefix}*", count=200
            ):
                try:
                    removed = await client.zremrangebyscore(key, 0, cutoff)
                    cleaned += int(removed)
                    # 检查是否为空，空则删除
                    remaining = await client.zcard(key)
                    if remaining == 0:
                        await client.delete(key)
                except Exception as e:
                    logger.debug(f"cleanup_auth_failures: key {key} skipped: {e}")
                    continue
        except Exception as e:
            logger.warning(f"RedisSipStateBackend.cleanup_auth_failures error: {e}")
        return cleaned

    # -------------------------------------------------------------------
    # 注册续约检测（跨节点共享 call_id）
    # -------------------------------------------------------------------

    async def check_register_renewal(self, gb_id: str, call_id: str) -> bool:
        """检查是否为注册续约（同一 gb_id 的 call_id 未变）。

        fail-closed: Redis 不可用时返回 False（强制重新注册，更安全）。
        """
        g = str(gb_id or "").strip()
        c = str(call_id or "").strip()
        if not g or not c:
            return False
        client = self._get_client()
        if not client:
            return False
        try:
            existing = await client.get(f"{self._register_call_id_prefix}{g}")
            return existing == c
        except Exception as e:
            logger.warning(f"RedisSipStateBackend.check_register_renewal error: {e}")
            return False

    async def record_register_call_id(self, gb_id: str, call_id: str, ttl: int = 3660) -> None:
        """记录注册 call_id，用于续约检测。"""
        g = str(gb_id or "").strip()
        c = str(call_id or "").strip()
        if not g or not c:
            return
        client = self._get_client()
        if not client:
            return
        try:
            effective_ttl = int(ttl) if ttl and ttl > 0 else self._register_call_id_ttl
            await client.set(
                f"{self._register_call_id_prefix}{g}",
                c,
                ex=effective_ttl,
            )
        except Exception as e:
            logger.warning(f"RedisSipStateBackend.record_register_call_id error: {e}")
