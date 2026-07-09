"""设备 SIP 订阅服务（下级设备订阅）。

管理本平台对下级 GB28181 设备（``Asset``）发起的 SIP SUBSCRIBE，覆盖目录同步
（Catalog）与移动位置订阅（MobilePosition）。订阅配置持久化在
``device_subscriptions`` 表，每台设备至多一条订阅配置（``asset_id`` 唯一约束）。

核心方法（被 ``app/main.py`` 与 ``app/core/startup.py`` 调用，签名必须严格匹配）：

- ``start()`` / ``stop()``：启动/停止后台订阅刷新循环（best-effort，async）

任务规格要求的方法：

- ``subscribe_catalog(asset_id)``：向设备发起目录订阅
- ``subscribe_mobile_position(asset_id)``：向设备发起移动位置订阅
- ``unsubscribe(asset_id)``：取消设备订阅（Expires=0）并清理记录
- ``refresh_subscriptions()``：扫描全部订阅配置，按需重新发起订阅

为避免循环导入，``app.sip.commander`` 在函数内部惰性导入。模块级
``device_subscription_service`` 为单例。
"""
from __future__ import annotations

import asyncio
import datetime as _dt
from typing import Optional

from loguru import logger
from sqlalchemy import delete, select

from app.db.session import AsyncSessionLocal
from app.models.asset import Asset
from app.models.device_subscription import DeviceSubscription


def _utcnow() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


class DeviceSubscriptionService:
    """管理对下级设备的 SIP 订阅。"""

    def __init__(self) -> None:
        self._running: bool = False
        self._refresh_task: Optional[asyncio.Task] = None
        # 刷新循环间隔（秒）
        self._refresh_interval_seconds: int = 300

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #
    async def start(self) -> None:
        """启动后台订阅刷新循环。best-effort，永不抛异常。"""
        try:
            if self._running:
                return
            self._running = True
            from app.core.async_utils import fire_and_forget
            self._refresh_task = fire_and_forget(self._refresh_loop())
            logger.info("device_subscription_service started")
        except Exception as e:
            logger.warning("device_subscription_service.start failed (non-fatal): {}", e)

    async def stop(self) -> None:
        """停止后台订阅刷新循环。best-effort，永不抛异常。"""
        try:
            self._running = False
            task = self._refresh_task
            self._refresh_task = None
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    logger.debug("task_cancelled")
            logger.info("device_subscription_service stopped")
        except Exception as e:
            logger.warning("device_subscription_service.stop failed (non-fatal): {}", e)

    async def _refresh_loop(self) -> None:
        """周期性刷新设备订阅。"""
        while self._running:
            try:
                await asyncio.sleep(self._refresh_interval_seconds)
                if not self._running:
                    break
                await self.refresh_subscriptions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("device_subscription refresh loop error: {}", e)

    # ------------------------------------------------------------------ #
    # 主动 SUBSCRIBE（向下级设备发起）
    # ------------------------------------------------------------------ #
    async def subscribe_catalog(self, asset_id: str) -> bool:
        """向设备发起目录订阅。best-effort。"""
        return await self._send_subscribe(asset_id, kind="catalog")

    async def subscribe_mobile_position(self, asset_id: str) -> bool:
        """向设备发起移动位置订阅。best-effort。"""
        return await self._send_subscribe(asset_id, kind="mobile_position")

    async def unsubscribe(self, asset_id: str) -> bool:
        """取消设备订阅（Expires=0）并清理记录。best-effort。"""
        ok = await self._send_subscribe(asset_id, kind="catalog", expires=0)
        try:
            async with AsyncSessionLocal() as db:
                await db.execute(
                    delete(DeviceSubscription).where(DeviceSubscription.asset_id == asset_id)
                )
                await db.commit()
        except Exception as e:
            logger.warning("device_subscription unsubscribe cleanup failed: {}", e)
        return ok

    async def _send_subscribe(
        self,
        asset_id: str,
        *,
        kind: str,
        expires: int = 3600,
    ) -> bool:
        """构造并发送 SUBSCRIBE 给设备。惰性导入 commander 避免循环依赖。"""
        try:
            import app.sip.commander as commander_mod  # noqa: WPS433 (lazy import)
            commander = getattr(commander_mod, "sip_commander", None)
            if commander is None:
                logger.debug("device_subscription: sip_commander not ready, skip subscribe")
                return False
            async with AsyncSessionLocal() as db:
                asset = (
                    await db.execute(select(Asset).where(Asset.id == asset_id))
                ).scalars().first()
                if not asset:
                    logger.warning("device_subscription: asset {} not found", asset_id)
                    return False
                if not asset.ip_addr:
                    logger.debug("device_subscription: asset {} has no ip_addr, skip", asset_id)
                    return False
                addr = (str(asset.ip_addr or ""), int(asset.port or 5060))
                transport_info = (addr, str(asset.transport or "UDP"), None)
                now = _utcnow()
                if kind == "mobile_position":
                    if hasattr(commander, "send_mobile_position_subscribe"):
                        await commander.send_mobile_position_subscribe(
                            asset.gb_id, transport_info, expires=expires
                        )
                    await self._mark_mp_result(db, asset_id, now, ok=True)
                    return True
                # catalog
                if hasattr(commander, "send_catalog_subscribe"):
                    await commander.send_catalog_subscribe(
                        asset.gb_id, transport_info, expires=expires
                    )
                await self._mark_catalog_result(db, asset_id, now, ok=True)
                return True
        except Exception as e:
            logger.warning("device_subscription _send_subscribe failed: {}", e)
            try:
                async with AsyncSessionLocal() as db:
                    now = _utcnow()
                    if kind == "mobile_position":
                        await self._mark_mp_result(db, asset_id, now, ok=False, error=str(e))
                    else:
                        await self._mark_catalog_result(db, asset_id, now, ok=False, error=str(e))
            except Exception as mark_err:
                logger.warning("device_subscription: failed to mark result for asset {}: {}", asset_id, mark_err)
            return False

    async def _mark_catalog_result(
        self,
        db,
        asset_id: str,
        now: _dt.datetime,
        *,
        ok: bool,
        error: str = "",
    ) -> None:
        sub = (
            await db.execute(
                select(DeviceSubscription).where(DeviceSubscription.asset_id == asset_id)
            )
        ).scalars().first()
        if sub is None:
            return
        sub.last_catalog_sync_at = now
        sub.last_catalog_sync_ok = 1 if ok else 0
        sub.last_catalog_sync_error = (error or "")[:500]
        await db.commit()

    async def _mark_mp_result(
        self,
        db,
        asset_id: str,
        now: _dt.datetime,
        *,
        ok: bool,
        error: str = "",
    ) -> None:
        sub = (
            await db.execute(
                select(DeviceSubscription).where(DeviceSubscription.asset_id == asset_id)
            )
        ).scalars().first()
        if sub is None:
            return
        sub.last_mobile_position_subscribe_at = now
        sub.last_mobile_position_subscribe_ok = 1 if ok else 0
        sub.last_mobile_position_subscribe_error = (error or "")[:500]
        await db.commit()

    # ------------------------------------------------------------------ #
    # 批量刷新
    # ------------------------------------------------------------------ #
    async def refresh_subscriptions(self) -> int:
        """扫描全部订阅配置，按需重新发起订阅。返回处理的设备数。"""
        try:
            async with AsyncSessionLocal() as db:
                subs = (
                    await db.execute(select(DeviceSubscription))
                ).scalars().all()
            count = 0
            now = _utcnow()
            for sub in subs:
                try:
                    # 目录同步：按 cycle 周期触发
                    cycle = int(getattr(sub, "catalog_cycle_seconds", 0) or 0)
                    last_sync = getattr(sub, "last_catalog_sync_at", None)
                    need_catalog = cycle > 0 and (
                        last_sync is None
                        or (now - last_sync).total_seconds() >= cycle
                    )
                    if need_catalog:
                        await self.subscribe_catalog(sub.asset_id)
                        count += 1
                        continue
                    # 移动位置：按 renew 周期触发
                    mp_enabled = bool(int(getattr(sub, "mobile_position_enabled", 0) or 0))
                    renew = int(getattr(sub, "mobile_position_renew_seconds", 300) or 300)
                    last_mp = getattr(sub, "last_mobile_position_subscribe_at", None)
                    need_mp = mp_enabled and (
                        last_mp is None
                        or (now - last_mp).total_seconds() >= renew
                    )
                    if need_mp:
                        await self.subscribe_mobile_position(sub.asset_id)
                        count += 1
                except Exception as e:
                    logger.debug("device_subscription refresh for asset {} failed: {}", sub.asset_id, e)
            return count
        except Exception as e:
            logger.warning("device_subscription refresh_subscriptions failed: {}", e)
            return 0


# 模块级单例
device_subscription_service = DeviceSubscriptionService()
