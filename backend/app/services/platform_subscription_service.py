"""上级平台 SIP 订阅服务（级联订阅）。

管理本平台对上级级联平台（``ParentPlatform``）发起的 GB28181 SUBSCRIBE，
覆盖目录订阅（Catalog）、移动位置订阅（MobilePosition）、报警订阅（Alarm）等
SUBSCRIBE/NOTIFY 周期。订阅记录持久化在 ``platform_subscriptions`` 表，
``remote_*`` / ``local_*`` 对话标识用于后续 NOTIFY 匹配与续订。

核心方法（被 ``sip/handlers.py``、``services/notify_manager.py``、
``services/platform_service.py`` 调用，签名必须严格匹配）：

- ``start()`` / ``stop()``：启动/停止后台续订循环（best-effort，async）
- ``upsert_subscription(...)``：SUBSCRIBE 200 OK 后写入/更新订阅记录
- ``list_active_subscriptions(tenant_id=, event=)``：按租户+事件列出活跃订阅
- ``get_active_subscriptions(event_type)``：按事件列出活跃订阅（转发 NOTIFY 用）
- ``mark_notify(tenant_id=, platform_id=, event=)``：收到 NOTIFY 后更新时间戳
- ``mark_notify_by_call_id(call_id=)``：按 Call-ID 更新 NOTIFY 时间戳
- ``remove_all_for_platform(tenant_id=, platform_id=, reason=)``：平台离线时清理

为避免循环导入，``app.sip.commander`` / ``app.sip.server`` 均在函数内部惰性导入。
模块级 ``platform_subscription_service`` 为单例，``notify_manager`` 在模块加载时
即引用，故本模块导入必须始终成功。
"""
from __future__ import annotations

import asyncio
import datetime as _dt
from typing import Optional

from loguru import logger
from sqlalchemy import delete, select

from app.db.session import AsyncSessionLocal
from app.models.platform import ParentPlatform
from app.models.platform_subscription import PlatformSubscription


def _utcnow() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _expires_at(expires_seconds: int) -> Optional[_dt.datetime]:
    try:
        secs = int(expires_seconds or 0)
    except (TypeError, ValueError):
        secs = 0
    if secs <= 0:
        return None
    return _utcnow() + _dt.timedelta(seconds=secs)


class PlatformSubscriptionService:
    """管理对上级平台的 SIP 订阅与 NOTIFY 处理。"""

    def __init__(self) -> None:
        self._running: bool = False
        self._renew_task: Optional[asyncio.Task] = None
        # 续订循环间隔（秒）
        self._renew_interval_seconds: int = 300

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #
    async def start(self) -> None:
        """启动后台续订循环。best-effort，永不抛异常。"""
        try:
            if self._running:
                return
            self._running = True
            # 续订循环作为 fire-and-forget 后台任务，保存引用防 GC
            from app.core.async_utils import fire_and_forget
            self._renew_task = fire_and_forget(self._renewal_loop())
            logger.info("platform_subscription_service started")
        except Exception as e:
            logger.warning("platform_subscription_service.start failed (non-fatal): {}", e)

    async def stop(self) -> None:
        """停止后台续订循环。best-effort，永不抛异常。"""
        try:
            self._running = False
            task = self._renew_task
            self._renew_task = None
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    logger.debug("task_cancelled")
            logger.info("platform_subscription_service stopped")
        except Exception as e:
            logger.warning("platform_subscription_service.stop failed (non-fatal): {}", e)

    async def _renewal_loop(self) -> None:
        """周期性扫描即将过期的订阅并续订。"""
        while self._running:
            try:
                await asyncio.sleep(self._renew_interval_seconds)
                if not self._running:
                    break
                await self._refresh_expiring()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("platform_subscription renewal loop error: {}", e)

    async def _refresh_expiring(self) -> None:
        """续订即将过期的平台订阅（best-effort）。"""
        try:
            async with AsyncSessionLocal() as db:
                now = _utcnow()
                stmt = select(PlatformSubscription).where(
                    PlatformSubscription.expires_at.isnot(None),
                    PlatformSubscription.expires_at <= now,
                )
                subs = (await db.execute(stmt)).scalars().all()
                for sub in subs:
                    try:
                        await self.subscribe_catalog(sub.platform_id)
                    except Exception as e:
                        logger.debug("renew catalog subscribe for platform {} failed: {}", sub.platform_id, e)
        except Exception as e:
            logger.debug("platform_subscription _refresh_expiring failed: {}", e)

    # ------------------------------------------------------------------ #
    # 订阅记录 CRUD（被 handlers.py / platform_service.py 调用）
    # ------------------------------------------------------------------ #
    async def upsert_subscription(
        self,
        *,
        tenant_id: str = "default",
        platform_id: str,
        event: str,
        expires_seconds: int = 0,
        addr: str = "",
        transport: str = "",
        call_id: str = "",
        remote_from_tag: str = "",
        local_to_tag: str = "",
        remote_contact: str = "",
        record_route: str = "",
    ) -> Optional[PlatformSubscription]:
        """SUBSCRIBE 200 OK 后写入或更新订阅记录。"""
        try:
            async with AsyncSessionLocal() as db:
                stmt = select(PlatformSubscription).where(
                    PlatformSubscription.platform_id == platform_id,
                    PlatformSubscription.event == event,
                )
                sub = (await db.execute(stmt)).scalars().first()
                now = _utcnow()
                exp_at = _expires_at(expires_seconds)
                if sub is None:
                    sub = PlatformSubscription(
                        tenant_id=tenant_id or "default",
                        platform_id=platform_id,
                        event=event,
                        expires_seconds=int(expires_seconds or 0),
                        expires_at=exp_at,
                        last_subscribe_at=now,
                        last_notify_at=None,
                        last_addr=addr,
                        last_transport=transport,
                        last_call_id=call_id,
                        remote_from_tag=remote_from_tag,
                        local_to_tag=local_to_tag,
                        remote_contact=remote_contact,
                        record_route=record_route,
                        notify_cseq=1,
                    )
                    db.add(sub)
                else:
                    sub.tenant_id = tenant_id or sub.tenant_id or "default"
                    sub.expires_seconds = int(expires_seconds or 0)
                    sub.expires_at = exp_at
                    sub.last_subscribe_at = now
                    if addr:
                        sub.last_addr = addr
                    if transport:
                        sub.last_transport = transport
                    if call_id:
                        sub.last_call_id = call_id
                    if remote_from_tag:
                        sub.remote_from_tag = remote_from_tag
                    if local_to_tag:
                        sub.local_to_tag = local_to_tag
                    if remote_contact:
                        sub.remote_contact = remote_contact
                    if record_route:
                        sub.record_route = record_route
                await db.commit()
                await db.refresh(sub)
                return sub
        except Exception as e:
            logger.warning("platform_subscription upsert_subscription failed: {}", e)
            return None

    async def list_active_subscriptions(
        self,
        *,
        tenant_id: str = "default",
        event: str,
    ) -> list[PlatformSubscription]:
        """按租户+事件列出活跃订阅（未过期）。"""
        try:
            async with AsyncSessionLocal() as db:
                now = _utcnow()
                stmt = select(PlatformSubscription).where(
                    PlatformSubscription.event == event,
                    (PlatformSubscription.expires_at.is_(None))
                    | (PlatformSubscription.expires_at > now),
                )
                if tenant_id:
                    stmt = stmt.where(PlatformSubscription.tenant_id == tenant_id)
                return list((await db.execute(stmt)).scalars().all())
        except Exception as e:
            logger.warning("platform_subscription list_active_subscriptions failed: {}", e)
            return []

    async def get_active_subscriptions(self, event_type: str) -> list[PlatformSubscription]:
        """按事件类型列出所有活跃订阅（转发 NOTIFY 时使用，跨租户）。"""
        try:
            async with AsyncSessionLocal() as db:
                now = _utcnow()
                stmt = select(PlatformSubscription).where(
                    PlatformSubscription.event == event_type,
                    (PlatformSubscription.expires_at.is_(None))
                    | (PlatformSubscription.expires_at > now),
                )
                return list((await db.execute(stmt)).scalars().all())
        except Exception as e:
            logger.warning("platform_subscription get_active_subscriptions failed: {}", e)
            return []

    async def mark_notify(
        self,
        *,
        tenant_id: str = "default",
        platform_id: str,
        event: str,
    ) -> None:
        """收到 NOTIFY 后更新最后通知时间与 CSeq。"""
        try:
            async with AsyncSessionLocal() as db:
                now = _utcnow()
                stmt = select(PlatformSubscription).where(
                    PlatformSubscription.platform_id == platform_id,
                    PlatformSubscription.event == event,
                )
                if tenant_id:
                    stmt = stmt.where(PlatformSubscription.tenant_id == tenant_id)
                sub = (await db.execute(stmt)).scalars().first()
                if sub is None:
                    return
                sub.last_notify_at = now
                try:
                    sub.notify_cseq = int(getattr(sub, "notify_cseq", 0) or 0) + 1
                except Exception:
                    sub.notify_cseq = 1
                await db.commit()
        except Exception as e:
            logger.warning("platform_subscription mark_notify failed: {}", e)

    async def mark_notify_by_call_id(self, *, call_id: str) -> None:
        """按 Call-ID 更新 NOTIFY 时间戳（SUBSCRIBE 响应 200 OK 时调用）。"""
        try:
            if not call_id:
                return
            async with AsyncSessionLocal() as db:
                now = _utcnow()
                stmt = select(PlatformSubscription).where(
                    PlatformSubscription.last_call_id == call_id
                )
                sub = (await db.execute(stmt)).scalars().first()
                if sub is None:
                    return
                sub.last_notify_at = now
                try:
                    sub.notify_cseq = int(getattr(sub, "notify_cseq", 0) or 0) + 1
                except Exception:
                    sub.notify_cseq = 1
                await db.commit()
        except Exception as e:
            logger.warning("platform_subscription mark_notify_by_call_id failed: {}", e)

    async def remove_all_for_platform(
        self,
        *,
        tenant_id: str = "default",
        platform_id: str,
        reason: str = "",
    ) -> int:
        """平台离线时清理其所有订阅记录。返回删除条数。"""
        try:
            async with AsyncSessionLocal() as db:
                stmt = delete(PlatformSubscription).where(
                    PlatformSubscription.platform_id == platform_id
                )
                if tenant_id:
                    stmt = stmt.where(PlatformSubscription.tenant_id == tenant_id)
                result = await db.execute(stmt)
                await db.commit()
                deleted = int(getattr(result, "rowcount", 0) or 0)
                if deleted:
                    logger.info(
                        "platform_subscription removed {} subs for platform={} reason={}",
                        deleted, platform_id, reason,
                    )
                return deleted
        except Exception as e:
            logger.warning("platform_subscription remove_all_for_platform failed: {}", e)
            return 0

    # ------------------------------------------------------------------ #
    # 主动 SUBSCRIBE（向上级平台发起）
    # ------------------------------------------------------------------ #
    async def subscribe_catalog(self, platform_id: str) -> bool:
        """向上级平台发起目录订阅。best-effort。"""
        return await self._send_subscribe(platform_id, event="catalog", expires=3600)

    async def subscribe_mobile_position(self, platform_id: str) -> bool:
        """向上级平台发起移动位置订阅。best-effort。"""
        return await self._send_subscribe(platform_id, event="MobilePosition", expires=3600)

    async def unsubscribe(self, platform_id: str) -> bool:
        """向上级平台取消订阅（Expires=0）。best-effort。"""
        ok = await self._send_subscribe(platform_id, event="catalog", expires=0)
        # 同时清理本地订阅记录
        await self.remove_all_for_platform(platform_id=platform_id, reason="unsubscribe")
        return ok

    async def _send_subscribe(self, platform_id: str, *, event: str, expires: int) -> bool:
        """构造并发送 SUBSCRIBE 给上级平台。惰性导入 commander 避免循环依赖。"""
        try:
            import app.sip.commander as commander_mod  # noqa: WPS433 (lazy import)
            commander = getattr(commander_mod, "sip_commander", None)
            if commander is None:
                logger.debug("platform_subscription: sip_commander not ready, skip subscribe")
                return False
            async with AsyncSessionLocal() as db:
                plat = (
                    await db.execute(select(ParentPlatform).where(ParentPlatform.id == platform_id))
                ).scalars().first()
                if not plat:
                    logger.warning("platform_subscription: platform {} not found", platform_id)
                    return False
                addr = (str(plat.server_ip or ""), int(plat.server_port or 5060))
                transport_info = (addr, str(plat.transport or "UDP"), None)
                # 复用设备侧目录订阅方法向上级平台发送 SUBSCRIBE
                if hasattr(commander, "send_catalog_subscribe"):
                    await commander.send_catalog_subscribe(plat.server_gb_id, transport_info, expires=expires)
                    return True
                logger.debug("platform_subscription: commander has no send_catalog_subscribe")
                return False
        except Exception as e:
            logger.warning("platform_subscription _send_subscribe failed: {}", e)
            return False

    # ------------------------------------------------------------------ #
    # NOTIFY 处理入口（由 sip/handlers.py 调用）
    # ------------------------------------------------------------------ #
    async def handle_notify(
        self,
        *,
        platform_id: str,
        event: str,
        tenant_id: str = "default",
        body: str = "",
    ) -> None:
        """处理来自上级平台的 NOTIFY。更新订阅时间戳，body 由上层解析。"""
        await self.mark_notify(tenant_id=tenant_id, platform_id=platform_id, event=event)


# 模块级单例。notify_manager 在 import 时即引用，必须始终可用。
platform_subscription_service = PlatformSubscriptionService()
