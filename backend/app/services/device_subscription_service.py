import asyncio
from loguru import logger
from datetime import datetime, timezone

from sqlalchemy import select  # TECH_DEBT: 直接依赖具体实现，未来改为Protocol接口注入

from app.db.session import AsyncSessionLocal
from app.models.asset import Asset
from app.models.device_subscription import DeviceSubscription
from app.sip.server import sip_server




def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class DeviceSubscriptionService:
    def __init__(self):
        self.running = False
        self.check_interval = 5
        self._task: asyncio.Task | None = None

    async def start(self):
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("DeviceSubscriptionService started")

    async def stop(self):
        self.running = False
        if not self._task:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass  # intentional: asyncio cancellation
        self._task = None

    async def _run_loop(self):
        while self.running:
            try:
                await self._run_catalog_subscriptions()
                await self._run_mobile_position_subscriptions()
            except Exception as e:
                logger.error(f"DeviceSubscriptionService loop error: {e}")
            await asyncio.sleep(self.check_interval)

    async def _run_catalog_subscriptions(self):
        if not getattr(sip_server, "running", False):
            return
        from app.sip.catalog import catalog

        now = _utcnow_naive()
        async with AsyncSessionLocal() as session:
            rows = (
                await session.execute(
                    select(DeviceSubscription, Asset)
                    .join(Asset, DeviceSubscription.asset_id == Asset.id)
                    .where(DeviceSubscription.catalog_cycle_seconds > 0)
                )
            ).all()
            if not rows:
                return
            for sub, asset in rows:
                cycle = int(getattr(sub, "catalog_cycle_seconds", 0) or 0)
                if cycle <= 0:
                    continue
                last_at = getattr(sub, "last_catalog_sync_at", None)
                if last_at and (now - last_at).total_seconds() < cycle:
                    continue
                if not asset or not asset.ip_addr:
                    sub.last_catalog_sync_at = now
                    sub.last_catalog_sync_ok = 0
                    sub.last_catalog_sync_error = "设备网络信息缺失"
                    continue
                transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
                if transport is None:
                    sub.last_catalog_sync_at = now
                    sub.last_catalog_sync_ok = 0
                    sub.last_catalog_sync_error = "Device signaling transport unavailable"
                    continue
                try:
                    await catalog.send_catalog_query(asset, ((asset.ip_addr, asset.port), asset.transport, transport))
                    sub.last_catalog_sync_at = now
                    sub.last_catalog_sync_ok = 1
                    sub.last_catalog_sync_error = ""
                except Exception as e:
                    sub.last_catalog_sync_at = now
                    sub.last_catalog_sync_ok = 0
                    sub.last_catalog_sync_error = str(e)[:500]
            await session.commit()

    async def _run_mobile_position_subscriptions(self):
        if not getattr(sip_server, "running", False):
            return
        from app.sip.commander import sip_commander

        now = _utcnow_naive()
        async with AsyncSessionLocal() as session:
            rows = (
                await session.execute(
                    select(DeviceSubscription, Asset)
                    .join(Asset, DeviceSubscription.asset_id == Asset.id)
                    .where(DeviceSubscription.mobile_position_enabled == 1)
                )
            ).all()
            if not rows:
                return
            for sub, asset in rows:
                renew = int(getattr(sub, "mobile_position_renew_seconds", 0) or 0)
                renew = max(30, min(renew, 3600))
                last_at = getattr(sub, "last_mobile_position_subscribe_at", None)
                if last_at and (now - last_at).total_seconds() < renew:
                    continue
                interval = int(getattr(sub, "mobile_position_interval_seconds", 60) or 60)
                interval = max(5, min(interval, 3600))
                if not asset or not asset.ip_addr:
                    sub.last_mobile_position_subscribe_at = now
                    sub.last_mobile_position_subscribe_ok = 0
                    sub.last_mobile_position_subscribe_error = "设备网络信息缺失"
                    continue
                transport = sip_server.get_transport(asset.ip_addr, asset.port, asset.transport)
                if transport is None:
                    sub.last_mobile_position_subscribe_at = now
                    sub.last_mobile_position_subscribe_ok = 0
                    sub.last_mobile_position_subscribe_error = "Device signaling transport unavailable"
                    continue
                try:
                    await sip_commander.send_mobile_position_subscribe(
                        device_id=asset.gb_id,
                        transport_info=((asset.ip_addr, asset.port), asset.transport, transport),
                        interval=interval,
                        wait_response=True,
                    )
                    sub.last_mobile_position_subscribe_at = now
                    sub.last_mobile_position_subscribe_ok = 1
                    sub.last_mobile_position_subscribe_error = ""
                except Exception as e:
                    sub.last_mobile_position_subscribe_at = now
                    sub.last_mobile_position_subscribe_ok = 0
                    sub.last_mobile_position_subscribe_error = str(e)[:500]
            await session.commit()


device_subscription_service = DeviceSubscriptionService()