import time
import asyncio
from loguru import logger
import datetime
from sqlalchemy import update
from app.core.redis import redis_client
from app.db.session import AsyncSessionLocal
from app.models.asset import Asset
from app.models.platform import ParentPlatform



_keepalive_cache = {}  # {gb_id: (last_update_time, ip, port)}
KEEPALIVE_DB_INTERVAL = 60  # seconds

# Asynchronous queue for DB updates to smooth out storms
_db_update_queue = asyncio.Queue(maxsize=10000)

async def should_skip_keepalive_db_update(gb_id: str, ip: str, port: int) -> bool:
    """
    Check if we can skip hitting the DB for this keepalive.
    Uses Redis if available, else local memory cache.
    """
    now = time.time()

    if redis_client is not None:  # 显式 None 守卫避免 pyright Never
        try:
            key = f"pygbsentry:keepalive:{gb_id}"
            cached = await redis_client.hgetall(key)
            if cached:
                last_time = float(cached.get("time", 0))
                cached_ip = cached.get("ip")
                cached_port = int(cached.get("port", 0))

                if ip == cached_ip and port == cached_port and (now - last_time) < KEEPALIVE_DB_INTERVAL:
                    # Update TTL in redis but skip DB
                    await redis_client.expire(key, KEEPALIVE_DB_INTERVAL * 2)
                    return True

            # Needs DB update, set cache
            await redis_client.hset(key, mapping={"time": now, "ip": ip, "port": port})
            await redis_client.expire(key, KEEPALIVE_DB_INTERVAL * 2)
            return False
        except Exception as e:
            logger.warning(f"Redis error in keepalive smoothing: {e}")
            return False

    # Local fallback
    cached = _keepalive_cache.get(gb_id)
    if cached:
        last_time, cached_ip, cached_port = cached
        if ip == cached_ip and port == cached_port and (now - last_time) < KEEPALIVE_DB_INTERVAL:
            return True

    _keepalive_cache[gb_id] = (now, ip, port)
    # FIX: [2026-07-03] 清理本地缓存：先清除过期条目，仍超限时驱逐最旧条目，防止设备频繁注册/注销导致内存泄漏 [可靠性工程师]
    if len(_keepalive_cache) > 10000:
        to_del = [k for k, v in _keepalive_cache.items() if now - v[0] > KEEPALIVE_DB_INTERVAL * 2]
        for k in to_del:
            _keepalive_cache.pop(k, None)
        # 硬上限：若过期清理后仍超 15000，按时间戳排序驱逐最旧条目
        if len(_keepalive_cache) > 15000:
            sorted_keys = sorted(_keepalive_cache.items(), key=lambda x: x[1][0])
            over = len(_keepalive_cache) - 10000
            for k, _ in sorted_keys[:over]:
                _keepalive_cache.pop(k, None)

    return False

def enqueue_keepalive_update(gb_id: str, ip: str, port: int, proto: str):
    item = {
        "type": "keepalive",
        "gb_id": gb_id,
        "ip": ip,
        "port": port,
        "proto": proto,
        "time": datetime.datetime.now(datetime.timezone.utc)
    }
    try:
        _db_update_queue.put_nowait(item)
    except asyncio.QueueFull:
        # P1-fix [2026-07-17]: 队列满时禁止仅写入内存缓存而放弃 DB 更新
        # 原问题：队列满后心跳仅缓存于 _keepalive_cache，但 _check_device_offline
        # 仅读取 DB Asset.last_keepalive，缓存不被消费，超过 180 秒阈值后在线设备
        # 会被误判离线并触发 _cleanup_device_resources（清理流会话/订阅）。
        # 修复：当距上次 DB 更新超过 0.5*KEEPALIVE_DB_INTERVAL 时，触发紧急同步
        # DB 更新（绕过批量队列），确保 last_keepalive 不滞后超过阈值。
        now = time.time()
        cached = _keepalive_cache.get(gb_id)
        needs_emergency_update = True
        if cached:
            last_time, _, _ = cached
            if (now - last_time) < (KEEPALIVE_DB_INTERVAL * 0.5):
                needs_emergency_update = False
        _keepalive_cache[gb_id] = (now, ip, port)
        if needs_emergency_update:
            # fire-and-forget 紧急 DB 更新，避免阻塞 SIP 处理协程
            try:
                from app.core.async_utils import fire_and_forget
                fire_and_forget(_emergency_keepalive_update(gb_id, item["time"]))
            except Exception as e:
                logger.warning(f"Failed to dispatch emergency keepalive update for {gb_id}: {e}")
        logger.warning(
            f"Storm handler queue full, dispatched emergency DB update for {gb_id} "
            f"(emergency={needs_emergency_update})"
        )


async def _emergency_keepalive_update(gb_id: str, keepalive_time):
    """紧急同步更新单个设备的 last_keepalive，绕过批量队列。

    P1-fix [2026-07-17]: 风暴场景下批量队列满载时，为避免在线设备被误判离线，
    直接执行单条 DB 更新。失败时仅记录警告，不抛出异常（已是降级路径）。
    """
    try:
        async with AsyncSessionLocal() as session:
            stmt = update(Asset).where(Asset.gb_id == gb_id).values(
                last_keepalive=keepalive_time,
                status=1,
            )
            await session.execute(stmt)
            platform_stmt = update(ParentPlatform).where(
                (ParentPlatform.server_gb_id == gb_id) | (ParentPlatform.client_gb_id == gb_id)
            ).values(
                last_keepalive=keepalive_time,
            )
            await session.execute(platform_stmt)
            await session.commit()
    except Exception as e:
        logger.warning(f"Emergency keepalive update failed for {gb_id}: {e}")

def enqueue_register_update(gb_id: str, ip: str, port: int, proto: str, expires: int):
    try:
        _db_update_queue.put_nowait({
            "type": "register",
            "gb_id": gb_id,
            "ip": ip,
            "port": port,
            "proto": proto,
            "expires": expires,
            "time": datetime.datetime.now(datetime.timezone.utc)
        })
    except asyncio.QueueFull:
        logger.warning(f"Storm handler queue full, dropping register update for {gb_id}")

async def _db_updater_worker():
    """
    Background worker that consumes the DB update queue and performs batch updates.
    """
    logger.info("Storm Handler DB updater worker started")
    while True:
        batch = []
        try:
            # Wait for at least one item
            item = await _db_update_queue.get()
            batch.append(item)

            # Try to grab up to 100 more items if available
            while len(batch) < 100 and not _db_update_queue.empty():
                batch.append(_db_update_queue.get_nowait())

            await _process_batch(batch)

            for _ in batch:
                _db_update_queue.task_done()

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in DB updater worker: {e}")
            await asyncio.sleep(1)

async def _process_batch(batch: list):
    if not batch:
        return

    # single session for entire batch instead of one session per item
    failed_items: list = []
    try:
        async with AsyncSessionLocal() as session:
            for item in batch:
                try:
                    if item["type"] == "keepalive":
                        # FIX R23-SEVERE: 心跳不更新 ip_addr/port/transport，防止设备劫持
                        # 原问题：心跳直接用源地址更新 DB 中设备的 ip_addr/port，
                        #   攻击者发送伪造 Keepalive（含目标设备 DeviceID）即可劫持设备
                        # 修复：心跳只更新 last_keepalive 和 status，
                        #   ip_addr/port/transport 仅在 REGISTER 时设置（注册时已验证源 IP）
                        #   NAT 端口变化场景由设备重新注册处理
                        stmt = update(Asset).where(Asset.gb_id == item["gb_id"]).values(
                            last_keepalive=item["time"],
                            status=1,
                        )
                        await session.execute(stmt)

                        platform_stmt = update(ParentPlatform).where(
                            (ParentPlatform.server_gb_id == item["gb_id"]) | (ParentPlatform.client_gb_id == item["gb_id"])
                        ).values(
                            last_keepalive=item["time"],
                        )
                        await session.execute(platform_stmt)

                    elif item["type"] == "register":
                        is_online = item["expires"] > 0
                        stmt = update(Asset).where(Asset.gb_id == item["gb_id"]).values(
                            register_time=item["time"],
                            status=1 if is_online else 0,
                            ip_addr=item["ip"],
                            port=item["port"],
                            transport=item["proto"]
                        )
                        await session.execute(stmt)

                        platform_stmt = update(ParentPlatform).where(
                            (ParentPlatform.server_gb_id == item["gb_id"]) | (ParentPlatform.client_gb_id == item["gb_id"])
                        ).values(
                            last_keepalive=item["time"],
                            is_online=is_online,
                            server_ip=item["ip"],
                            server_port=item["port"]
                        )
                        await session.execute(platform_stmt)

                except Exception as item_err:
                    logger.error(f"Failed to process batch item {item.get('gb_id', '?')}: {item_err}")
                    failed_items.append(item)

            await session.commit()
    except Exception as e:
        logger.error(f"Failed to process batch: {e}")
        # FIX R23-SEVERE: commit 失败时将整个 batch 重新入队，避免设备心跳丢失导致误判离线
        # 原问题：commit 失败仅记录日志，batch 中所有更新丢失且不重新入队
        # 修复：将失败的 item 重新入队（限制重试次数避免无限循环）
        failed_items = batch

    # FIX R23-SEVERE: 将失败 item 重新入队（限制重试次数）
    if failed_items:
        for item in failed_items:
            retry_count = item.get("_retry_count", 0)
            if retry_count < 3:  # 最多重试 3 次
                item["_retry_count"] = retry_count + 1
                try:
                    _db_update_queue.put_nowait(item)
                except asyncio.QueueFull:
                    logger.warning(f"Re-enqueue failed (queue full), dropping item for {item.get('gb_id', '?')}")
            else:
                logger.error(f"Max retries exceeded for {item.get('gb_id', '?')}, dropping")

_worker_task = None

def start_storm_handler():
    global _worker_task
    if _worker_task is None:
        # P0-16 [2026-07-17]: 使用 fire_and_forget 替代裸 create_task，带异常回调和任务名
        from app.core.async_utils import fire_and_forget
        _worker_task = fire_and_forget(
            _db_updater_worker(),
            name="storm_handler_db_updater_worker",
        )

def stop_storm_handler():
    global _worker_task
    if _worker_task:
        _worker_task.cancel()
        _worker_task = None
