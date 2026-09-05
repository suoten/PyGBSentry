"""定时 Catalog 刷新任务 — 定期重新查询在线设备的目录，自动同步新增/删除的通道。

解决"设备初始注册后新增通道不自动同步"的问题。
默认每 30 分钟刷新一次（可通过 CATALOG_REFRESH_INTERVAL_SECONDS 配置）。
"""
from __future__ import annotations

import asyncio
from loguru import logger
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.asset import Asset
from app.core.config import settings
from app.core.async_utils import fire_and_forget

# 刷新间隔（秒），默认 30 分钟
_REFRESH_INTERVAL = int(getattr(settings, "CATALOG_REFRESH_INTERVAL_SECONDS", 1800) or 1800)
# 单次刷新最大设备数（防止大量设备同时刷新打爆 SIP 栈）
_MAX_DEVICES_PER_CYCLE = 50

_task: asyncio.Task | None = None


async def _refresh_device_catalogs() -> None:
    """遍历在线设备，触发 catalog 重新同步。"""
    try:
        async with AsyncSessionLocal() as session:
            # 查询在线设备（status=1）
            stmt = (
                select(Asset)
                .where(Asset.status == 1)
                .order_by(Asset.last_keepalive.desc())
                .limit(_MAX_DEVICES_PER_CYCLE)
            )
            result = await session.execute(stmt)
            assets = result.scalars().all()

        if not assets:
            return

        logger.info(f"[CATALOG_REFRESH] Checking {len(assets)} online devices for catalog refresh")

        import app.sip.commander as sip_commander_module
        from app.sip.handlers import _schedule_device_catalog_retry, _device_last_seen_addr

        commander = getattr(sip_commander_module, "sip_commander", None)
        if not commander:
            logger.warning("[CATALOG_REFRESH] SIP commander not available, skipping")
            return

        refreshed = 0
        for asset in assets:
            gb_id = str(asset.gb_id or "")
            if not gb_id:
                continue

            # 使用 Keepalive 最新地址（NAT 安全），回退到 Asset 存储地址
            latest = _device_last_seen_addr.get(gb_id)
            if latest and len(latest) >= 3:
                addr = (latest[0], latest[1])
                proto = latest[2]
            else:
                ip = str(asset.ip_addr or "")
                port = int(asset.port or 5060)
                proto = str(asset.transport or "UDP")
                if not ip:
                    continue
                addr = (ip, port)

            # 获取 transport 对象（SIP server 有 UDP/TCP 双栈，根据协议选择）
            from app.sip.server import sip_server
            if proto.upper() == "TCP":
                transport = getattr(sip_server, "tcp_transport", None)
            else:
                transport = getattr(sip_server, "udp_transport", None)
            if transport is None:
                transport = getattr(sip_server, "transport", None)
            if transport is None:
                continue

            transport_info = (addr, proto, transport)
            fire_and_forget(
                _schedule_device_catalog_retry(gb_id, transport_info),
                name=f"catalog_refresh:{gb_id}",
            )
            refreshed += 1

        if refreshed > 0:
            logger.info(f"[CATALOG_REFRESH] Triggered catalog re-sync for {refreshed}/{len(assets)} devices")

    except Exception as e:
        logger.error(f"[CATALOG_REFRESH] Failed to refresh device catalogs: {e}", exc_info=True)


async def _catalog_refresh_loop() -> None:
    """Catalog 定时刷新主循环。"""
    logger.info(f"[CATALOG_REFRESH] Started (interval={_REFRESH_INTERVAL}s, max_devices={_MAX_DEVICES_PER_CYCLE}/cycle)")
    while True:
        try:
            await asyncio.sleep(_REFRESH_INTERVAL)
            await _refresh_device_catalogs()
        except asyncio.CancelledError:
            logger.info("[CATALOG_REFRESH] Stopped")
            raise
        except Exception as e:
            logger.error(f"[CATALOG_REFRESH] Loop error: {e}", exc_info=True)
            await asyncio.sleep(60)  # 出错后等 60 秒再重试


async def start() -> None:
    """启动 Catalog 定时刷新任务。"""
    global _task
    if _task is not None and not _task.done():
        return
    _task = fire_and_forget(_catalog_refresh_loop(), name="catalog_refresh_loop")


async def stop() -> None:
    """停止 Catalog 定时刷新任务。"""
    global _task
    if _task and not _task.done():
        _task.cancel()
        try:
            await asyncio.wait_for(_task, timeout=5.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
    _task = None
