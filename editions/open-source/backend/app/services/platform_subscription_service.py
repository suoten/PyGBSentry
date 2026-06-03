from __future__ import annotations

import asyncio
import contextlib
import datetime
import json
from loguru import logger

from sqlalchemy import select, delete  # TECH_DEBT: 直接依赖具体实现，未来改为Protocol接口注入

from app.core.redis import redis_client
from app.db.session import AsyncSessionLocal
from app.models.platform_subscription import PlatformSubscription
from app.models.platform_runtime import PlatformRuntime




def _utcnow_naive() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _normalize_event(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    return raw.split(";", 1)[0].strip()


class PlatformSubscriptionService:
    def __init__(self):
        self.running = False
        self.check_interval = 5
        self._task: asyncio.Task | None = None

    async def start(self):
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("PlatformSubscriptionService started")

    async def stop(self):
        self.running = False
        if not self._task:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def upsert_subscription(
        self,
        *,
        tenant_id: str,
        platform_id: str,
        event: str,
        expires_seconds: int,
        addr: str,
        transport: str,
        call_id: str,
        remote_from_tag: str = "",
        local_to_tag: str = "",
        remote_contact: str = "",
        record_route: str = "",
        now: datetime.datetime | None = None,
    ) -> None:
        ev = _normalize_event(event)
        if not ev:
            return
        now_dt = now or _utcnow_naive()
        exp = int(expires_seconds or 0)
        exp_at = (now_dt + datetime.timedelta(seconds=exp)) if exp > 0 else None

        async with AsyncSessionLocal() as session:
            row = (
                await session.execute(
                    select(PlatformSubscription).where(
                        PlatformSubscription.tenant_id == (tenant_id or "default"),
                        PlatformSubscription.platform_id == platform_id,
                        PlatformSubscription.event == ev,
                    )
                )
            ).scalars().first()
            if exp == 0:
                if row:
                    await session.delete(row)
                    await session.commit()
                await self._runtime_patch(tenant_id or "default", platform_id, {
                    f"subscribe.{ev}.active": False,
                    f"subscribe.{ev}.expires_at": "",
                    f"subscribe.{ev}.last_at": now_dt.isoformat(),
                })
                await self._redis_delete(tenant_id or "default", platform_id, ev)
                return

            if not row:
                row = PlatformSubscription(
                    tenant_id=tenant_id or "default",
                    platform_id=platform_id,
                    event=ev,
                )
                session.add(row)

            row.expires_seconds = exp
            row.expires_at = exp_at
            row.last_subscribe_at = now_dt
            row.last_addr = str(addr or "")
            row.last_transport = str(transport or "")
            row.last_call_id = str(call_id or "")
            if remote_from_tag:
                row.remote_from_tag = str(remote_from_tag or "")
            if remote_contact:
                row.remote_contact = str(remote_contact or "")
            if record_route:
                row.record_route = str(record_route or "")
            if local_to_tag and not (row.local_to_tag or ""):
                row.local_to_tag = str(local_to_tag or "")
            await session.commit()

        await self._runtime_patch(tenant_id or "default", platform_id, {
            f"subscribe.{ev}.active": True,
            f"subscribe.{ev}.expires_seconds": exp,
            f"subscribe.{ev}.expires_at": exp_at.isoformat() if exp_at else "",
            f"subscribe.{ev}.last_at": now_dt.isoformat(),
            f"subscribe.{ev}.last_addr": str(addr or ""),
            f"subscribe.{ev}.last_transport": str(transport or ""),
        })
        await self._redis_set(tenant_id or "default", platform_id, ev, exp, {
            "expires_at": exp_at.isoformat() if exp_at else "",
            "last_at": now_dt.isoformat(),
            "addr": str(addr or ""),
            "transport": str(transport or ""),
            "call_id": str(call_id or ""),
            "remote_from_tag": str(remote_from_tag or ""),
            "local_to_tag": str(local_to_tag or ""),
        })

    async def mark_notify(
        self,
        *,
        tenant_id: str,
        platform_id: str,
        event: str,
        now: datetime.datetime | None = None,
    ) -> None:
        ev = _normalize_event(event)
        if not ev:
            return
        now_dt = now or _utcnow_naive()
        async with AsyncSessionLocal() as session:
            row = (
                await session.execute(
                    select(PlatformSubscription).where(
                        PlatformSubscription.tenant_id == (tenant_id or "default"),
                        PlatformSubscription.platform_id == platform_id,
                        PlatformSubscription.event == ev,
                    )
                )
            ).scalars().first()
            if row:
                row.last_notify_at = now_dt
                await session.commit()
        await self._runtime_patch(tenant_id or "default", platform_id, {
            f"notify.{ev}.last_at": now_dt.isoformat(),
        })

    async def mark_notify_by_call_id(self, *, call_id: str, now: datetime.datetime | None = None) -> None:
        cid = (call_id or "").strip()
        if not cid:
            return
        now_dt = now or _utcnow_naive()
        async with AsyncSessionLocal() as session:
            row = (
                await session.execute(
                    select(PlatformSubscription).where(
                        PlatformSubscription.last_call_id == cid,
                        PlatformSubscription.expires_at.is_not(None),
                        PlatformSubscription.expires_at > now_dt,
                    )
                )
            ).scalars().first()
            if not row:
                return
            row.last_notify_at = now_dt
            tenant_id = row.tenant_id or "default"
            platform_id = row.platform_id
            event = row.event
            await session.commit()
        ev = _normalize_event(event)
        if ev:
            await self._runtime_patch(tenant_id, platform_id, {
                f"notify.{ev}.last_at": now_dt.isoformat(),
                f"notify.{ev}.last_call_id": cid,
            })

    async def remove_all_for_platform(self, *, tenant_id: str, platform_id: str, reason: str = "") -> None:
        async with AsyncSessionLocal() as session:
            rows = (
                await session.execute(
                    select(PlatformSubscription).where(
                        PlatformSubscription.tenant_id == (tenant_id or "default"),
                        PlatformSubscription.platform_id == platform_id,
                    )
                )
            ).scalars().all()
            if not rows:
                return
            events = [r.event for r in rows if r.event]
            await session.execute(
                delete(PlatformSubscription).where(
                    PlatformSubscription.tenant_id == (tenant_id or "default"),
                    PlatformSubscription.platform_id == platform_id,
                )
            )
            await session.commit()
        for ev in events:
            await self._redis_delete(tenant_id or "default", platform_id, ev)
            await self._runtime_patch(tenant_id or "default", platform_id, {
                f"subscribe.{ev}.active": False,
                f"subscribe.{ev}.expires_at": "",
                f"subscribe.{ev}.cleared_at": _utcnow_naive().isoformat(),
                f"subscribe.{ev}.cleared_reason": str(reason or ""),
            })

    async def _run_loop(self):
        while self.running:
            try:
                await self._purge_expired()
            except Exception as e:
                logger.error("PlatformSubscriptionService loop error: %s", e)
            await asyncio.sleep(self.check_interval)

    async def get_active_subscriptions(self, event: str) -> list[PlatformSubscription]:
        ev = _normalize_event(event)
        if not ev:
            return []
        now_dt = _utcnow_naive()
        async with AsyncSessionLocal() as session:
            rows = (
                await session.execute(
                    select(PlatformSubscription).where(
                        PlatformSubscription.event == ev,
                        PlatformSubscription.expires_at > now_dt,
                    )
                )
            ).scalars().all()
            return list(rows)

    async def _purge_expired(self) -> None:
        # FIXED-P2: M-11 使用单条DELETE替代SELECT+DELETE，消除TOCTOU
        now = _utcnow_naive()
        items: list[tuple[str, str, str]] = []
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                delete(PlatformSubscription)
                .where(
                    PlatformSubscription.expires_at.is_not(None),
                    PlatformSubscription.expires_at < now,
                )
                .returning(
                    PlatformSubscription.tenant_id,
                    PlatformSubscription.platform_id,
                    PlatformSubscription.event,
                )
            )
            for row in result:
                items.append((row.tenant_id or "default", row.platform_id, row.event))
            if items:
                await session.commit()
        for tenant_id, platform_id, ev in items:
            await self._redis_delete(tenant_id, platform_id, ev)
            await self._runtime_patch(tenant_id, platform_id, {
                f"subscribe.{ev}.active": False,
                f"subscribe.{ev}.expired_at": now.isoformat(),
            })

    async def _runtime_patch(self, tenant_id: str, platform_id: str, patch: dict) -> None:
        if not patch:
            return
        async with AsyncSessionLocal() as session:
            # FIXED-P2: N-08 使用FOR UPDATE行级锁防止并发丢失更新
            rt = (
                await session.execute(
                    select(PlatformRuntime).where(
                        PlatformRuntime.tenant_id == (tenant_id or "default"),
                        PlatformRuntime.platform_id == platform_id,
                    ).with_for_update()
                )
            ).scalars().first()
            data: dict = {}
            if rt and rt.data:
                try:
                    loaded = json.loads(rt.data)
                    if isinstance(loaded, dict):
                        data = loaded
                except Exception:
                    data = {}
            for k, v in patch.items():
                key = str(k or "").strip()
                if key:
                    data[key] = v
            if rt:
                rt.data = json.dumps(data, ensure_ascii=False)
            else:
                session.add(
                    PlatformRuntime(
                        tenant_id=(tenant_id or "default"),
                        platform_id=platform_id,
                        data=json.dumps(data, ensure_ascii=False),
                    )
                )
            with contextlib.suppress(Exception):
                await session.commit()

    async def _redis_set(self, tenant_id: str, platform_id: str, event: str, ttl_seconds: int, payload: dict) -> None:
        if not redis_client:
            return
        key = f"platform_sub:{tenant_id}:{platform_id}:{event}"
        try:
            await redis_client.set(key, json.dumps(payload, ensure_ascii=False), ex=max(1, int(ttl_seconds)))
        except Exception:
            return

    async def _redis_delete(self, tenant_id: str, platform_id: str, event: str) -> None:
        if not redis_client:
            return
        key = f"platform_sub:{tenant_id}:{platform_id}:{event}"
        with contextlib.suppress(Exception):
            await redis_client.delete(key)


platform_subscription_service = PlatformSubscriptionService()
