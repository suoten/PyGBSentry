import redis.asyncio as redis
from app.core.config import settings
import asyncio
import uuid
import time
import json
from typing import Callable, Dict, Optional
from loguru import logger

# P0-16 [2026-07-17]: 使用项目统一的 fire_and_forget 替代裸 create_task
from app.core.async_utils import fire_and_forget

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    def _uuid7_impl():
        return uuid.uuid4()

def _uuid7():
    return _uuid7_impl().hex[:8]

# P2-13: 使用 Redis 类型别名替代 Any，提升类型安全
redis_client: Optional[redis.Redis] = None

REDIS_RECONNECT_INTERVAL_SECONDS: int = 10

_redis_watchdog_task: Optional[asyncio.Task] = None

async def init_redis():
    """Initialize Redis connection."""
    global redis_client
    if redis_client:
        try:
            await redis_client.close()
        except Exception as e:
            logger.warning(f"Failed to close Redis client: {e}")
        redis_client = None
    try:
        # 支持 Redis Sentinel 连接模式
        if settings.REDIS_SENTINEL_HOSTS:
            from redis.sentinel import Sentinel
            sentinel_addrs = [
                (h.strip(), int(p.strip()))
                for h_p in settings.REDIS_SENTINEL_HOSTS.split(",")
                if ":" in h_p
                for h, p in [h_p.strip().split(":", 1)]
            ]
            sentinel = Sentinel(
                sentinel_addrs,
                socket_timeout=5,
                password=settings.REDIS_SENTINEL_PASSWORD or None,
            )
            _sentinel_max_conn = settings.REDIS_MAX_CONNECTIONS
            _sentinel_pool = redis.ConnectionPool(
                max_connections=_sentinel_max_conn,
                retry_on_timeout=True,
                socket_timeout=5,
                socket_connect_timeout=5,
                decode_responses=True,
            )
            redis_client = sentinel.master_for(
                settings.REDIS_SENTINEL_MASTER,
                password=settings.REDIS_PASSWORD or None,
                connection_pool=_sentinel_pool,
            )
        elif settings.REDIS_CLUSTER_MODE:
            from redis import cluster as _redis_cluster
            redis_client = _redis_cluster.RedisCluster(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD or None,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5,
                retry_on_timeout=True,
                max_connections=settings.REDIS_MAX_CONNECTIONS,
            )
        else:
            redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD,
                db=settings.REDIS_DB,
                decode_responses=True,
                max_connections=settings.REDIS_MAX_CONNECTIONS,
                socket_connect_timeout=float(settings.REDIS_SOCKET_CONNECT_TIMEOUT or 3.0),
                socket_timeout=float(settings.REDIS_SOCKET_TIMEOUT or 3.0),
                retry_on_timeout=True,
            )
        await redis_client.ping()
        logger.info(f"Redis connected to {settings.REDIS_HOST}:{settings.REDIS_PORT}")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        if redis_client:
            try:
                await redis_client.close()
            except Exception as e2:
                logger.warning(f"Failed to close Redis client: {e2}")
        redis_client = None


async def close_redis():
    """Close Redis connection."""
    global redis_client, _redis_watchdog_task
    if _redis_watchdog_task and not _redis_watchdog_task.done():
        _redis_watchdog_task.cancel()
        _redis_watchdog_task = None
    if redis_client:
        await redis_client.close()
        logger.info("Redis connection closed")
    redis_client = None


async def get_redis() -> Optional[redis.Redis]:
    """获取 Redis 客户端；不可用（未连接/连接失败）时返回 None，不抛异常。

    供 logout 吊销、health_service 指标、log_masker 自定义规则等调用方使用。
    与 ensure_redis() 的区别：本函数直接返回客户端对象，由调用方判空。
    """
    global redis_client
    if redis_client is None:
        await ensure_redis()
    return redis_client


async def ensure_redis():
    """Ensure Redis client is available. Reconnect if needed.

    Returns:
        bool: True if Redis is available, False otherwise.
    """
    global redis_client
    if redis_client is not None:
        try:
            await redis_client.ping()
            return True
        except Exception:
            logger.warning("Redis ping failed in ensure_redis(), attempting reconnect...")
    try:
        await init_redis()
        return redis_client is not None
    except Exception as e:
        logger.error(f"Redis reconnect failed in ensure_redis(): {e}")
        return False


async def _redis_watchdog_loop():
    """Background loop that monitors Redis connection and auto-reconnects."""
    global redis_client
    consecutive_failures = 0
    max_backoff = 300  # 5 minutes max backoff
    while True:
        try:
            await asyncio.sleep(REDIS_RECONNECT_INTERVAL_SECONDS)
            if redis_client is not None:
                try:
                    await redis_client.ping()
                    consecutive_failures = 0  # Reset on success
                except Exception:
                    consecutive_failures += 1
                    backoff = min(REDIS_RECONNECT_INTERVAL_SECONDS * (2 ** min(consecutive_failures - 1, 5)), max_backoff)
                    logger.warning(f"Redis ping failed (attempt {consecutive_failures}), reconnecting with {backoff}s backoff...")
                    await asyncio.sleep(backoff)
                    try:
                        await init_redis()
                        consecutive_failures = 0
                        logger.info("Redis reconnected successfully after failure")
                    except Exception as e:
                        logger.error(f"Redis reconnection failed: {e}")
            else:
                consecutive_failures += 1
                backoff = min(REDIS_RECONNECT_INTERVAL_SECONDS * (2 ** min(consecutive_failures - 1, 5)), max_backoff)
                logger.warning(f"Redis client is None (attempt {consecutive_failures}), attempting init with {backoff}s backoff...")
                await asyncio.sleep(backoff)
                try:
                    await init_redis()
                    consecutive_failures = 0
                    logger.info("Redis initialized successfully after being None")
                except Exception as e:
                    logger.error(f"Redis initialization failed: {e}")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Redis watchdog error: {e}")


def start_redis_watchdog():
    """Start the Redis watchdog background task."""
    global _redis_watchdog_task
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is None or loop.is_closed():
        logger.warning("Cannot start Redis watchdog: no running event loop.")
        return
    if _redis_watchdog_task is None or _redis_watchdog_task.done():
        # P0-16 [2026-07-17]: 使用 fire_and_forget 替代裸 create_task，带异常回调和任务名
        _redis_watchdog_task = fire_and_forget(
            _redis_watchdog_loop(),
            name="redis_watchdog_loop",
        )
        logger.info("Redis watchdog started.")


_CLUSTER_CHANNELS = {
    "device_change": "pygbsentry:cluster:device_change",
    "media_node_status": "pygbsentry:cluster:media_node_status",
    "invite_route": "pygbsentry:cluster:invite_route",
    "record_result": "pygbsentry:cluster:record_result",
    "config_reload": "pygbsentry:cluster:config_reload",
    "subscribe_notify": "gb:cluster:subscribe_notify",  # 订阅通知跨节点同步
    "alarm_notify": "gb:cluster:alarm_notify",  # 报警通知跨节点同步
    "ssrc_allocate": "gb:cluster:ssrc_allocate",  # SSRC分配跨节点协调
}


class RedisHACluster:
    """High-availability cluster support with Redis Pub/Sub RPC.

    Channels:
        device_change:    Broadcast device info changes (channel add/delete, name modification).
        media_node_status: Sync ZLM media node status (online/offline, load).
        invite_route:     Cross-node INVITE request routing.
        record_result:    Recording query result aggregation.
        config_reload:    Configuration hot-reload broadcast.
    """

    def __init__(self):
        self.node_id = settings.CLUSTER_NODE_ID
        if not self.node_id:
            self.node_id = _uuid7()
        self._node_prefix = "pygbsentry:node"
        self._node_key = f"{self._node_prefix}:{self.node_id}"
        self.pubsub = None
        self._running = True
        self._handlers: Dict[str, Callable] = {}
        self._subscriber_task: Optional[asyncio.Task] = None

    async def register_node(self):
        """注册当前节点到集群，包含负载信息"""
        if not redis_client or not settings.CLUSTER_ENABLED:
            return
        try:
            # 节点注册增加负载信息
            load_info = {
                "ts": time.time(),
                "cpu": 0,
                "mem": 0,
                "streams": 0,  # 从 media_manager 获取活跃流数
            }
            try:
                import psutil
                load_info["cpu"] = psutil.cpu_percent(interval=0)
                load_info["mem"] = psutil.virtual_memory().percent
            except ImportError:
                logger.debug("optional_import_skipped")
            # 尝试获取活跃流数
            try:
                from app.services.media_manager import media_manager
                if media_manager:
                    load_info["streams"] = getattr(media_manager, "active_stream_count", 0)
            except Exception as _mm_err:
                # FIX [2026-07-17 P3-5]: 描述性日志替代 "silently_swallowed_exception"
                logger.warning(f"[Cluster HA] Failed to read active_stream_count from media_manager: {_mm_err}")
            await redis_client.hset(self._node_key, mapping=load_info)
            # 同时写入旧格式以保持兼容
            await redis_client.hset("pygbsentry:nodes", self.node_id, time.time())
            logger.info(f"[Cluster HA] Node {self.node_id} registered to cluster")
        except Exception as e:
            logger.warning(f"[Cluster HA] Register failed: {e}")

    def stop(self):
        """Stop the cluster service."""
        self._running = False
        if self._subscriber_task and not self._subscriber_task.done():
            self._subscriber_task.cancel()

    async def keepalive_loop(self):
        """Periodic heartbeat to maintain node registration."""
        while self._running:
            try:
                if redis_client and settings.CLUSTER_ENABLED:
                    await redis_client.hset("pygbsentry:nodes", self.node_id, time.time())
                    now = time.time()
                    all_nodes = await redis_client.hgetall("pygbsentry:nodes")
                    stale_nodes = [
                        nid for nid, ts_str in all_nodes.items()
                        if nid != self.node_id and now - float(ts_str or 0) > 60
                    ]
                    if stale_nodes:
                        await redis_client.hdel("pygbsentry:nodes", *stale_nodes)
                        logger.info(f"[Cluster HA] Cleaned {len(stale_nodes)} stale node(s)")
            except Exception as e:
                logger.warning(f"Failed to update cluster node heartbeat: {e}")
            await asyncio.sleep(10)

    def register_handler(self, channel_type: str, handler: Callable) -> None:
        """Register a callback for a specific cluster channel type.

        Args:
            channel_type: One of 'device_change', 'media_node_status',
                          'invite_route', 'record_result', 'config_reload',
                          'subscribe_notify', 'alarm_notify', 'ssrc_allocate'.
            handler: Async callable accepting (source_node: str, data: dict).
        """
        if channel_type not in _CLUSTER_CHANNELS:
            logger.warning(f"[Cluster HA] Unknown channel type: {channel_type}")
            return
        self._handlers[channel_type] = handler

    async def start_subscriber(self) -> None:
        """Start the Pub/Sub subscriber loop for all cluster channels."""
        if not redis_client or not settings.CLUSTER_ENABLED:
            return
        try:
            self.pubsub = redis_client.pubsub()
            channels = list(_CLUSTER_CHANNELS.values())
            await self.pubsub.subscribe(*channels)
            self._subscriber_task = fire_and_forget(
                self._subscriber_loop(),
                name="cluster_ha_subscriber_loop",
            )
            logger.info(f"[Cluster HA] Subscriber started for {len(channels)} channels")
        except Exception as e:
            logger.warning(f"[Cluster HA] Failed to start subscriber: {e}")

    async def _subscriber_loop(self) -> None:
        """Internal loop that reads Pub/Sub messages and dispatches to handlers."""
        while self._running and self.pubsub:
            try:
                msg = await asyncio.wait_for(self.pubsub.get_message(timeout=1.0), timeout=2.0)
                if msg and msg.get("type") == "message":
                    channel_name = msg.get("channel", "")
                    payload = msg.get("data", "")
                    await self._dispatch_message(channel_name, payload)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[Cluster HA] Subscriber loop error: {e}")
                await asyncio.sleep(1)

    async def _dispatch_message(self, channel_name: str, payload: str) -> None:
        """Parse and dispatch a Pub/Sub message to the registered handler."""
        channel_type = None
        for ctype, cname in _CLUSTER_CHANNELS.items():
            if cname == channel_name:
                channel_type = ctype
                break
        if not channel_type:
            return

        try:
            data = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"[Cluster HA] Invalid JSON on {channel_type}: {payload[:200]}")
            return

        source_node = data.get("source_node", "")
        if source_node == self.node_id:
            return

        handler = self._handlers.get(channel_type)
        if handler:
            try:
                await handler(source_node, data.get("data", {}))
            except Exception as e:
                logger.warning(f"[Cluster HA] Handler error for {channel_type}: {e}")

    async def publish(self, channel_type: str, data: dict) -> None:
        """Publish a message to a cluster channel.

        Args:
            channel_type: One of the defined channel types.
            data: The payload to broadcast.
        """
        if not redis_client or not settings.CLUSTER_ENABLED:
            return
        channel_name = _CLUSTER_CHANNELS.get(channel_type)
        if not channel_name:
            logger.warning(f"[Cluster HA] Unknown channel type for publish: {channel_type}")
            return
        payload = json.dumps({
            "source_node": self.node_id,
            "timestamp": time.time(),
            "type": channel_type,
            "data": data,
        })
        try:
            await redis_client.publish(channel_name, payload)
        except Exception as e:
            logger.warning(f"[Cluster HA] Publish failed on {channel_type}: {e}")

    async def broadcast_device_change(self, gb_id: str, change_type: str, details: dict = None) -> None:
        """Broadcast a device info change to all cluster nodes.

        Args:
            gb_id: The device GB ID that changed.
            change_type: 'channel_added', 'channel_removed', 'name_changed', 'status_changed'.
            details: Optional dict with additional info.
        """
        await self.publish("device_change", {
            "gb_id": gb_id,
            "change_type": change_type,
            "details": details or {},
        })

    async def broadcast_media_node_status(self, node_id: str, status: str, load: dict = None) -> None:
        """Broadcast a media node (ZLM) status change.

        Args:
            node_id: The media node identifier.
            status: 'online', 'offline'.
            load: Optional dict with load info.
        """
        await self.publish("media_node_status", {
            "node_id": node_id,
            "status": status,
            "load": load or {},
        })

    async def request_invite_route(self, gb_id: str, callback_channel: str) -> None:
        """Request cross-node INVITE routing for a device.

        Args:
            gb_id: The target device/channel GB ID.
            callback_channel: A unique channel name where the owning node should respond.
        """
        await self.publish("invite_route", {
            "gb_id": gb_id,
            "callback_channel": callback_channel,
            "requester_node": self.node_id,
        })

    async def broadcast_record_result(self, query_key: str, records: list, source_node: str = "") -> None:
        """Broadcast recording query results for aggregation.

        Args:
            query_key: A unique key identifying the query.
            records: List of record dicts.
            source_node: The node that produced these results.
        """
        await self.publish("record_result", {
            "query_key": query_key,
            "records": records,
            "source_node": source_node or self.node_id,
        })

    async def broadcast_config_reload(self, config_keys: list = None) -> None:
        """Broadcast a configuration hot-reload signal.

        Args:
            config_keys: Optional list of specific config keys that changed.
        """
        await self.publish("config_reload", {
            "config_keys": config_keys or [],
        })

    async def get_device_owner_node(self, gb_id: str) -> Optional[str]:
        """Look up which cluster node owns a given device.

        Args:
            gb_id: The device GB ID.

        Returns:
            The node_id of the owning node, or None if not found.
        """
        if not redis_client or not settings.CLUSTER_ENABLED:
            return None
        try:
            owner = await redis_client.hget("pygbsentry:device_owners", gb_id)
            return owner
        except Exception as e:
            logger.warning(f"[Cluster HA] get_device_owner_node failed: {e}")
            return None

    async def register_device_owner(self, gb_id: str) -> None:
        """Register the current node as the owner of a device.

        Args:
            gb_id: The device GB ID.
        """
        if not redis_client or not settings.CLUSTER_ENABLED:
            return
        try:
            await redis_client.hset("pygbsentry:device_owners", gb_id, self.node_id)
        except Exception as e:
            logger.warning(f"[Cluster HA] register_device_owner failed: {e}")

    async def unregister_device_owner(self, gb_id: str) -> None:
        """Remove device ownership registration.

        Args:
            gb_id: The device GB ID.
        """
        if not redis_client or not settings.CLUSTER_ENABLED:
            return
        try:
            await redis_client.hdel("pygbsentry:device_owners", gb_id)
        except Exception as e:
            logger.warning(f"[Cluster HA] unregister_device_owner failed: {e}")

    async def get_cluster_health(self) -> dict:
        """获取集群健康状态"""
        # 实现集群健康检查
        nodes = {}
        if not redis_client or not settings.CLUSTER_ENABLED:
            return {"total_nodes": 0, "alive_nodes": 0, "nodes": nodes, "healthy": False}
        try:
            async for key in redis_client.scan_iter(f"{self._node_prefix}:*"):
                node_id = key.split(":")[-1]
                data = await redis_client.hgetall(key)
                if data:
                    ts = float(data.get("ts", 0))
                    is_alive = (time.time() - ts) < 60
                    nodes[node_id] = {
                        "alive": is_alive,
                        "cpu": float(data.get("cpu", 0)),
                        "mem": float(data.get("mem", 0)),
                        "streams": int(data.get("streams", 0)),
                        "last_seen": ts,
                    }
        except Exception as e:
            logger.warning(f"[Cluster HA] get_cluster_health scan failed: {e}")
        alive_count = sum(1 for n in nodes.values() if n["alive"])
        return {
            "total_nodes": len(nodes),
            "alive_nodes": alive_count,
            "nodes": nodes,
            "healthy": alive_count > 0,
        }


ha_cluster = RedisHACluster()
