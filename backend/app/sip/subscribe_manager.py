from __future__ import annotations

import asyncio
import random
import time
import secrets
from loguru import logger
import contextlib
from typing import Optional, Callable, Awaitable
from dataclasses import dataclass, field

_CHUNK_SIZE = 100  # GB3 Catalog NOTIFY分页 — 每个NOTIFY最多100个通道


@dataclass
class SubscribeInfo:
    device_id: str
    event: str
    call_id: str
    from_tag: str
    to_tag: str
    cseq: int
    expires: int
    sn: int
    created_at: float = field(default_factory=time.monotonic)
    last_renewed: float = field(default_factory=time.monotonic)
    remote_addr: tuple = field(default_factory=tuple)
    remote_proto: str = "UDP"

    @property
    def is_expired(self) -> bool:
        return (time.monotonic() - self.last_renewed) > self.expires

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.expires - (time.monotonic() - self.last_renewed))


@dataclass
class OutboundSubscribe:
    device_id: str
    event: str
    call_id: str
    from_tag: str
    to_tag: str
    cseq: int
    expires: int
    sn: int
    interval: int = 5
    created_at: float = field(default_factory=time.monotonic)
    last_sent: float = 0.0
    renew_task: asyncio.Task | None = None
    running: bool = False


class SubscribeManager:
    # 订阅字典添加上限，防止长期运行内存增长
    _MAX_INBOUND = 50000
    _MAX_OUTBOUND = 50000

    def __init__(self):
        self._inbound: dict[str, SubscribeInfo] = {}
        self._outbound: dict[str, OutboundSubscribe] = {}
        self._lock = asyncio.Lock()
        self._prune_task: asyncio.Task | None = None
        self._running = False
        self._on_catalog_change: list[Callable[..., Awaitable]] = []
        self._on_mobile_position: list[Callable[..., Awaitable]] = []
        self._on_alarm: list = []  # 新增报警订阅回调列表
        self._inbound_renew_tasks: dict[str, asyncio.Task] = {}  # 目录订阅自动续期 — 跟踪inbound续期任务

    def on_catalog_change(self, callback: Callable[..., Awaitable]):
        self._on_catalog_change.append(callback)

    def on_mobile_position(self, callback: Callable[..., Awaitable]):
        self._on_mobile_position.append(callback)

    # GB13 CSeq持久化 — 进程重启后CSeq从DB恢复
    async def _persist_cseq(self, call_id: str, cseq: int):
        """Persist CSeq to Redis/DB for recovery after restart"""
        try:
            from app.core.redis_state import get_redis_state
            state = get_redis_state()
            await state.set(f"sip:sub_cseq:{call_id}", str(cseq), ttl=86400)
        except Exception as e:
            logger.debug(f"CSeq persist failed: {e}")

    async def _restore_cseq(self, call_id: str) -> int:
        """Restore CSeq from Redis/DB"""
        try:
            from app.core.redis_state import get_redis_state
            state = get_redis_state()
            val = await state.get(f"sip:sub_cseq:{call_id}")
            if val:
                return int(val)
        except Exception as e:
            logger.warning(f"Failed to restore CSeq: {e}")  # W-08 _restore_cseq 吞异常 — 改为 warning 日志
        return 1

    def on_alarm(self, callback):
        """Register a callback for alarm notifications. GB5 报警订阅注册方法"""
        self._on_alarm.append(callback)

    async def start(self):
        self._running = True
        self._prune_task = asyncio.create_task(self._prune_loop())

    async def stop(self):
        self._running = False
        if self._prune_task and not self._prune_task.done():
            self._prune_task.cancel()
        # 目录订阅自动续期 — stop时取消所有inbound续期任务
        for key, task in list(self._inbound_renew_tasks.items()):
            if not task.done():
                task.cancel()
        self._inbound_renew_tasks.clear()
        for key, sub in list(self._outbound.items()):
            sub.running = False
            if sub.renew_task and not sub.renew_task.done():
                sub.renew_task.cancel()
        self._outbound.clear()

    async def _prune_loop(self):
        while self._running:
            try:
                await self._prune_inbound()
                await self._check_lost_outbound()
                # 订阅字典超限清理，防止长期运行内存增长
                if len(self._inbound) > self._MAX_INBOUND:
                    async with self._lock:
                        oldest = sorted(self._inbound.items(), key=lambda x: getattr(x[1], 'last_keepalive', 0))[:len(self._inbound) - self._MAX_INBOUND + 1000]
                        for k, _ in oldest:
                            self._inbound.pop(k, None)
                            _task = self._inbound_renew_tasks.pop(k, None)
                            if _task and not _task.done():
                                _task.cancel()
                    logger.warning(f"[SubscribeManager] Inbound subscriptions exceeded {self._MAX_INBOUND}, pruned {len(oldest)} oldest")
                if len(self._outbound) > self._MAX_OUTBOUND:
                    async with self._lock:
                        oldest = sorted(self._outbound.items(), key=lambda x: getattr(x[1], 'last_sent', 0))[:len(self._outbound) - self._MAX_OUTBOUND + 1000]
                        for k, _ in oldest:
                            sub = self._outbound.pop(k, None)
                            if sub and sub.renew_task and not sub.renew_task.done():
                                sub.renew_task.cancel()
                    logger.warning(f"[SubscribeManager] Outbound subscriptions exceeded {self._MAX_OUTBOUND}, pruned {len(oldest)} oldest")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[SubscribeManager] prune loop error: {e}")
            await asyncio.sleep(10)

    async def _prune_inbound(self):
        # S-07-01 在锁内收集过期条目并pop，锁外发送NOTIFY，防止与put_inbound续期竞态
        expired_subs = []
        async with self._lock:
            expired_keys = [k for k, v in self._inbound.items() if v.is_expired]
            for k in expired_keys:
                sub = self._inbound.pop(k, None)
                renew_task = self._inbound_renew_tasks.pop(k, None)
                if renew_task and not renew_task.done():
                    renew_task.cancel()
                if sub:
                    expired_subs.append(sub)
        for sub in expired_subs:
            logger.info(f"[SubscribeManager] Inbound subscribe expired: device={sub.device_id} event={sub.event}")
            try:
                await self._send_terminated_notify(sub)
            except Exception as e:
                logger.warning(f"[SubscribeManager] Failed to send terminated NOTIFY for {sub.device_id}/{sub.event}: {e}")

    async def _check_lost_outbound(self):
        # W-07-01 在锁内收集丢失条目并pop，锁外cancel，防止与put_outbound竞态
        lost_subs = []
        async with self._lock:
            now = time.monotonic()
            lost_keys = []
            for key, sub in list(self._outbound.items()):
                if not sub.running:
                    continue
                if sub.expires > 0 and sub.last_sent > 0:
                    elapsed_since_renew = now - sub.last_sent
                    if elapsed_since_renew > sub.expires * 2:
                        logger.warning(f"[SubscribeManager] Outbound subscribe appears lost: device={sub.device_id} event={sub.event}, last_sent={elapsed_since_renew:.0f}s ago, expires={sub.expires}s")
                        lost_keys.append(key)
            for key in lost_keys:
                sub = self._outbound.pop(key, None)
                if sub:
                    lost_subs.append(sub)
        for sub in lost_subs:
            if sub.renew_task and not sub.renew_task.done():
                sub.renew_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await sub.renew_task

    async def _send_terminated_notify(self, sub: SubscribeInfo) -> None:
        from app.sip.server import sip_server
        from app.sip.message import SipMessage
        from app.sip.send import send_sip_bytes
        from app.core.config import settings, sip_host_for_contact

        if not sub.remote_addr or not sub.remote_proto:
            return
        addr = sub.remote_addr
        proto = sub.remote_proto
        transport = sip_server.get_transport(addr[0], addr[1], proto)
        if not transport:
            return

        req = SipMessage()
        req.method = "NOTIFY"
        req.uri = f"sip:{sub.device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"

        branch = f"z9hG4bK{secrets.token_hex(6)}"
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={sub.to_tag}"
        req.headers["To"] = f"<sip:{sub.device_id}@{settings.SIP_DOMAIN}>;tag={sub.from_tag}"
        req.headers["Call-ID"] = sub.call_id
        req.headers["CSeq"] = f"{sub.cseq + 1} NOTIFY"
        sub.cseq += 1
        req.headers["Contact"] = f"<sip:{settings.SIP_ID}@{sip_host_for_contact()}:{settings.SIP_PORT}>"
        req.headers["Event"] = sub.event
        req.headers["Subscription-State"] = "terminated;reason=timeout"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME

        await send_sip_bytes(proto, transport, addr, req.to_bytes())
        logger.info(f"[SubscribeManager] Sent terminated NOTIFY for {sub.device_id} event={sub.event}")

    # 目录订阅自动续期 — 启动/重启inbound订阅续期任务
    def _start_inbound_renew(self, key: str, sub: SubscribeInfo):
        old_task = self._inbound_renew_tasks.get(key)
        if old_task and not old_task.done():
            old_task.cancel()
        task = asyncio.create_task(self._inbound_renew_loop(key, sub))
        self._inbound_renew_tasks[key] = task

    # 目录订阅自动续期 — 在订阅过期前20%时间发送SUBSCRIBE续期
    async def _inbound_renew_loop(self, key: str, sub: SubscribeInfo):
        try:
            wait_seconds = max(1, sub.expires * 0.8)
            await asyncio.sleep(wait_seconds)
            if not self._running:
                return
            # W-24 续期成功后重新获取最新订阅对象，避免更新过期引用
            async with self._lock:
                current = self._inbound.get(key)
                if current is None or current.call_id != sub.call_id:
                    return
                if current.is_expired:
                    return
            # 发送 SUBSCRIBE 续期请求，最多重试3次
            max_retries = 3
            for attempt in range(1, max_retries + 1):
                try:
                    # 每次重试前重新获取最新订阅对象
                    async with self._lock:
                        latest_sub = self._inbound.get(key)
                        if latest_sub is None or latest_sub.call_id != sub.call_id:
                            return
                    await self._send_inbound_subscribe_renew(latest_sub)
                    # 续期成功后再次获取最新对象更新时间戳
                    async with self._lock:
                        latest_sub = self._inbound.get(key)
                        if latest_sub and latest_sub.call_id == sub.call_id:
                            latest_sub.last_renewed = time.monotonic()
                    logger.info(f"[SubscribeManager] Renewed inbound subscribe: device={latest_sub.device_id} event={latest_sub.event} attempt={attempt}")
                    # 续期成功后启动下一轮续期
                    self._start_inbound_renew(key, latest_sub)
                    return
                except Exception as e:
                    logger.warning(f"[SubscribeManager] Inbound subscribe renew attempt {attempt}/{max_retries} failed: device={current.device_id} event={current.event} error={e}")
                    if attempt < max_retries:
                        await asyncio.sleep(10)
            logger.warning(f"[SubscribeManager] Inbound subscribe renew all {max_retries} attempts failed: device={sub.device_id} event={sub.event}")
            # W-02 续期全部失败后移除订阅条目，触发重新订阅流程
            async with self._lock:
                self._inbound.pop(key, None)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[SubscribeManager] Inbound renew loop error for {key}: {e}")
        finally:
            self._inbound_renew_tasks.pop(key, None)

    # 目录订阅自动续期 — 发送SUBSCRIBE续期请求
    async def _send_inbound_subscribe_renew(self, sub: SubscribeInfo) -> None:
        from app.sip.server import sip_server
        from app.sip.message import SipMessage
        from app.sip.send import send_sip_bytes
        from app.core.config import settings, sip_host_for_contact

        if not sub.remote_addr or not sub.remote_proto:
            raise RuntimeError("No remote address or protocol for inbound subscribe renew")
        addr = sub.remote_addr
        proto = sub.remote_proto
        transport = sip_server.get_transport(addr[0], addr[1], proto)
        if not transport:
            raise RuntimeError(f"No transport for {addr[0]}:{addr[1]}/{proto}")

        sub.cseq += 1
        await self._persist_cseq(sub.call_id, sub.cseq)

        req = SipMessage()
        req.method = "SUBSCRIBE"
        req.uri = f"sip:{sub.device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"

        branch = f"z9hG4bK{secrets.token_hex(6)}"
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={sub.to_tag}"
        req.headers["To"] = f"<sip:{sub.device_id}@{settings.SIP_DOMAIN}>;tag={sub.from_tag}"
        req.headers["Call-ID"] = sub.call_id
        req.headers["CSeq"] = f"{sub.cseq} SUBSCRIBE"
        req.headers["Contact"] = f"<sip:{settings.SIP_ID}@{sip_host_for_contact()}:{settings.SIP_PORT}>"
        req.headers["Event"] = sub.event
        req.headers["Expires"] = str(sub.expires)
        req.headers["Accept"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME

        await send_sip_bytes(proto, transport, addr, req.to_bytes())

    # N-01 重写_send_unsubscribe支持OutboundSubscribe（无remote_addr/remote_proto，需从DB查设备地址）
    async def _send_unsubscribe_outbound(self, sub: OutboundSubscribe) -> None:
        from app.sip.server import sip_server
        from app.sip.message import SipMessage
        from app.sip.send import send_sip_bytes
        from app.core.config import settings, sip_host_for_contact
        from app.db.session import AsyncSessionLocal
        from app.models.asset import Asset
        from sqlalchemy import select

        # OutboundSubscribe has no remote_addr/remote_proto, look up from DB
        async with AsyncSessionLocal() as session:
            asset = (await session.execute(select(Asset).where(Asset.gb_id == sub.device_id))).scalars().first()
        if not asset:
            logger.warning(f"[SubscribeManager] Device {sub.device_id} not found for unsubscribe")
            return

        addr = (str(asset.ip_addr or ""), int(asset.port or 5060))
        proto = str(getattr(asset, "transport", "UDP") or "UDP")
        transport = sip_server.get_transport(addr[0], addr[1], proto)
        if not transport:
            return

        sub.cseq += 1
        req = SipMessage()
        req.method = "SUBSCRIBE"
        req.uri = f"sip:{sub.device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"

        branch = f"z9hG4bK{secrets.token_hex(6)}"
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={sub.from_tag}"
        req.headers["To"] = f"<sip:{sub.device_id}@{settings.SIP_DOMAIN}>;tag={sub.to_tag}" if sub.to_tag else f"<sip:{sub.device_id}@{settings.SIP_DOMAIN}>"  # F-01 to_tag为空时不附加;tag=，避免畸形SIP头
        req.headers["Call-ID"] = sub.call_id
        req.headers["CSeq"] = f"{sub.cseq} SUBSCRIBE"
        req.headers["Contact"] = f"<sip:{settings.SIP_ID}@{sip_host_for_contact()}:{settings.SIP_PORT}>"
        req.headers["Event"] = sub.event
        req.headers["Expires"] = "0"
        req.headers["Accept"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME

        await send_sip_bytes(proto, transport, addr, req.to_bytes())
        logger.info(f"[SubscribeManager] Sent SUBSCRIBE expires=0 to device={sub.device_id} event={sub.event}")

    async def put_inbound(self, subscribe: SubscribeInfo) -> SubscribeInfo | None:
        # P2 竞态条件 — inbound操作添加锁保护
        key = f"{subscribe.device_id}:{subscribe.event}"
        async with self._lock:
            existing = self._inbound.get(key)
            if existing and existing.call_id == subscribe.call_id:
                existing.last_renewed = time.monotonic()
                existing.expires = subscribe.expires
                existing.cseq = subscribe.cseq
                existing.sn = subscribe.sn
                # GB13 CSeq持久化 — 更新时同步持久化
                await self._persist_cseq(existing.call_id, existing.cseq)
                # 目录订阅自动续期 — 续期时重启续期任务
                self._start_inbound_renew(key, existing)
                return existing
            if existing and existing.call_id != subscribe.call_id:
                logger.info(f"[SubscribeManager] Replacing inbound subscribe with new Call-ID: device={subscribe.device_id} event={subscribe.event} old_call_id={existing.call_id} new_call_id={subscribe.call_id}")
                # 目录订阅自动续期 — 替换时取消旧续期任务
                old_task = self._inbound_renew_tasks.pop(key, None)
                if old_task and not old_task.done():
                    old_task.cancel()
            # GB13 CSeq持久化 — 新订阅时尝试从Redis恢复CSeq
            restored_cseq = await self._restore_cseq(subscribe.call_id)
            if restored_cseq > subscribe.cseq:
                subscribe.cseq = restored_cseq
            self._inbound[key] = subscribe
            # 目录订阅自动续期 — 新订阅创建时启动续期任务
            self._start_inbound_renew(key, subscribe)
        logger.info(f"[SubscribeManager] New inbound subscribe: device={subscribe.device_id} event={subscribe.event} expires={subscribe.expires}")
        return subscribe

    # W-01 SubscribeManager全部方法添加锁保护，消除竞态条件
    async def get_inbound(self, device_id: str, event: str) -> SubscribeInfo | None:
        async with self._lock:
            return self._inbound.get(f"{device_id}:{event}")

    async def remove_inbound(self, device_id: str, event: str) -> SubscribeInfo | None:
        # P2 竞态条件 — inbound操作添加锁保护
        async with self._lock:
            return self._inbound.pop(f"{device_id}:{event}", None)

    # W-01 SubscribeManager全部方法添加锁保护，消除竞态条件
    async def put_outbound(self, subscribe: OutboundSubscribe) -> OutboundSubscribe:
        key = f"{subscribe.device_id}:{subscribe.event}"
        async with self._lock:
            old = self._outbound.get(key)
            if old:
                old.running = False
                if old.renew_task and not old.renew_task.done():
                    old.renew_task.cancel()
            self._outbound[key] = subscribe
        return subscribe

    # W-01 SubscribeManager全部方法添加锁保护，消除竞态条件
    async def get_outbound(self, device_id: str, event: str) -> OutboundSubscribe | None:
        async with self._lock:
            return self._outbound.get(f"{device_id}:{event}")

    # W-01 SubscribeManager全部方法添加锁保护，消除竞态条件
    async def remove_outbound(self, device_id: str, event: str) -> OutboundSubscribe | None:
        async with self._lock:
            sub = self._outbound.pop(f"{device_id}:{event}", None)
        if sub:
            sub.running = False
            if sub.renew_task and not sub.renew_task.done():
                sub.renew_task.cancel()
        return sub

    async def start_outbound_renew(self, device_id: str, event: str, send_func: Callable[..., Awaitable]):
        key = f"{device_id}:{event}"
        async with self._lock:
            sub = self._outbound.get(key)
            if not sub or sub.running:
                return
            sub.running = True
        sub.renew_task = asyncio.create_task(self._renew_loop(sub, send_func))

    async def _renew_loop(self, sub: OutboundSubscribe, send_func: Callable[..., Awaitable]):
        max_consecutive_failures = 5
        consecutive_failures = 0
        while sub.running:
            try:
                if consecutive_failures > 0:
                    backoff = min(10 * (2 ** (consecutive_failures - 1)), 300)
                    await asyncio.sleep(backoff)
                else:
                    renew_before = max(5, int(sub.expires * 0.1))
                    sleep_time = max(1, sub.expires - renew_before)
                    await asyncio.sleep(sleep_time)
                if not sub.running:
                    break
                sub.cseq += 1
                sub.sn += 1
                result = await send_func(sub)
                if result is False:
                    consecutive_failures += 1
                    logger.warning(
                        f"[SubscribeManager] Renew outbound subscribe rejected: "
                        f"device={sub.device_id} event={sub.event} "
                        f"({consecutive_failures}/{max_consecutive_failures})"
                    )
                    if consecutive_failures >= max_consecutive_failures:
                        sub.running = False
                        break
                    continue
                sub.last_sent = time.monotonic()
                consecutive_failures = 0
                logger.info(f"[SubscribeManager] Renewed outbound subscribe: device={sub.device_id} event={sub.event}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                consecutive_failures += 1
                logger.error(
                    f"[SubscribeManager] Renew outbound subscribe failed "
                    f"({consecutive_failures}/{max_consecutive_failures}): "
                    f"device={sub.device_id} event={sub.event} error={e}"
                )
                if consecutive_failures >= max_consecutive_failures:
                    logger.error(
                        f"[SubscribeManager] Giving up outbound subscribe after "
                        f"{max_consecutive_failures} consecutive failures: "
                        f"device={sub.device_id} event={sub.event}"
                    )
                    sub.running = False
                    break

    async def notify_catalog_change(self, device_id: str, channels: list):
        """设备目录变更后，向已订阅的上级发送 SIP NOTIFY"""
        # W-08 通知方法检查订阅过期状态，避免向过期订阅发送NOTIFY(RFC 3265)
        # R-11 通知方法添加锁保护，与put_inbound/remove_inbound一致
        key = f"{device_id}:Catalog"
        async with self._lock:
            sub = self._inbound.get(key)
            # GB28181协议 — 支持通配订阅
            if not sub:
                sub = self._inbound.get("*:Catalog")
            if not sub:
                return
            if sub.is_expired:
                return
        # 目录订阅NOTIFY — 变更后主动向订阅方发送SIP NOTIFY消息
        try:
            await self._send_catalog_notify(sub, channels)
        except Exception as e:
            logger.error(f"[SubscribeManager] Failed to send catalog NOTIFY for {device_id}: {e}")
        # 同时触发回调
        for callback in self._on_catalog_change:
            try:
                await callback(sub, channels)
            except Exception as e:
                logger.error(f"[SubscribeManager] catalog change callback error: {e}")

    async def _send_catalog_notify(self, sub: SubscribeInfo, channels: list) -> None:
        """构建并发送目录变更 SIP NOTIFY 消息"""
        # GB3 Catalog NOTIFY分页 — 通道数超过_CHUNK_SIZE时分多个NOTIFY发送
        from app.sip.server import sip_server
        from app.sip.message import SipMessage
        from app.sip.send import send_sip_bytes
        from app.core.config import settings, sip_host_for_contact
        from xml.sax.saxutils import escape as _xml_escape

        if not sub.remote_addr or not sub.remote_proto:
            return
        addr = sub.remote_addr
        proto = sub.remote_proto
        transport = sip_server.get_transport(addr[0], addr[1], proto)
        if not transport:
            return

        total = len(channels)

        def _build_items_xml(ch_list):
            items_xml = ""
            for ch in ch_list:
                ch_id = str(getattr(ch, "gb_id", "") or "")
                ch_name = _xml_escape(str(getattr(ch, "name", "") or ""))
                ch_status = str(getattr(ch, "status", "ON") or "ON").upper()
                ch_parent = str(getattr(ch, "parent_gb_id", "") or "")
                # GB28181协议 — Catalog Item补全Table 9必填字段
                items_xml += "<Item>"
                items_xml += f"<DeviceID>{ch_id}</DeviceID>"
                items_xml += f"<Name>{ch_name}</Name>"
                items_xml += f"<Manufacturer>{_xml_escape(str(getattr(ch, 'manufacturer', '') or ''))}</Manufacturer>"
                items_xml += f"<Model>{_xml_escape(str(getattr(ch, 'model', '') or ''))}</Model>"
                items_xml += f"<Owner>{_xml_escape(str(getattr(ch, 'owner', '') or ''))}</Owner>"
                items_xml += f"<CivilCode>{_xml_escape(str(getattr(ch, 'civil_code', '') or ''))}</CivilCode>"
                items_xml += f"<Address>{_xml_escape(str(getattr(ch, 'address', '') or ''))}</Address>"
                items_xml += f"<Parental>{_xml_escape(str(getattr(ch, 'parental', '') or ''))}</Parental>"
                items_xml += f"<SafetyWay>{_xml_escape(str(getattr(ch, 'safety_way', '') or ''))}</SafetyWay>"
                items_xml += f"<RegisterWay>{_xml_escape(str(getattr(ch, 'register_way', '') or ''))}</RegisterWay>"
                items_xml += f"<Secrecy>{_xml_escape(str(getattr(ch, 'secrecy', '') or ''))}</Secrecy>"
                items_xml += f"<Status>{ch_status}</Status>"
                if ch_parent:
                    items_xml += f"<ParentID>{ch_parent}</ParentID>"
                items_xml += "</Item>\n"
            return items_xml

        def _build_notify_req(chunk_channels, sn, chunk_num):
            items_xml = _build_items_xml(chunk_channels)
            xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Notify>
<CmdType>Catalog</CmdType>
<SN>{sn}</SN>
<DeviceID>{sub.device_id}</DeviceID>
<SumNum>{total}</SumNum>
<DeviceList Num="{len(chunk_channels)}">
{items_xml}</DeviceList>
</Notify>
"""
            req = SipMessage()
            req.method = "NOTIFY"
            req.uri = f"sip:{sub.device_id}@{addr[0]}:{addr[1]}"
            req.version = "SIP/2.0"
            branch = f"z9hG4bK{secrets.token_hex(6)}"
            req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
            req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={sub.to_tag}"
            req.headers["To"] = f"<sip:{sub.device_id}@{settings.SIP_DOMAIN}>;tag={sub.from_tag}"
            req.headers["Call-ID"] = sub.call_id
            req.headers["CSeq"] = f"{sub.cseq} NOTIFY"
            req.headers["Contact"] = f"<sip:{settings.SIP_ID}@{sip_host_for_contact()}:{settings.SIP_PORT}>"
            req.headers["Event"] = "Catalog"
            req.headers["Subscription-State"] = "active"
            req.headers["Content-Type"] = "Application/MANSCDP+xml"
            req.headers["Max-Forwards"] = "70"
            req.headers["User-Agent"] = settings.PROJECT_NAME
            req.body = xml_body
            return req

        if total <= _CHUNK_SIZE:
            # Send single NOTIFY (existing behavior)
            sn = int(time.time() * 1000) % 100000
            sub.cseq += 1  # M-02 单条Catalog NOTIFY CSeq递增顺序修正为先递增后构建
            await self._persist_cseq(sub.call_id, sub.cseq)  # M-01 Catalog/Alarm NOTIFY CSeq持久化
            req = _build_notify_req(channels, sn, 1)
            await send_sip_bytes(proto, transport, addr, req.to_bytes())
            logger.info(f"[SubscribeManager] Sent catalog NOTIFY to {sub.device_id} with {total} items")
        else:
            # Send paginated NOTIFYs
            page_count = (total + _CHUNK_SIZE - 1) // _CHUNK_SIZE
            for page_idx, offset in enumerate(range(0, total, _CHUNK_SIZE)):
                chunk = channels[offset:offset + _CHUNK_SIZE]
                sn = int(time.time() * 1000) % 100000 + page_idx
                sub.cseq += 1
                await self._persist_cseq(sub.call_id, sub.cseq)  # M-01 Catalog/Alarm NOTIFY CSeq持久化
                req = _build_notify_req(chunk, sn, page_idx + 1)
                # FIXED-P2: 逐页异常保护，单页发送失败不中断后续页面
                try:
                    await send_sip_bytes(proto, transport, addr, req.to_bytes())
                    logger.info(f"[SubscribeManager] Sent catalog NOTIFY page {page_idx + 1}/{page_count} to {sub.device_id} with {len(chunk)} items (total={total})")
                except Exception as _page_err:
                    logger.warning(f"[SubscribeManager] Failed to send catalog NOTIFY page {page_idx + 1}/{page_count} to {sub.device_id}: {_page_err}")

    # GB14 移动位置订阅通知分发
    async def notify_mobile_position(self, device_id: str, position: dict):
        """Dispatch mobile position notification to registered callbacks"""
        # W-08 通知方法检查订阅过期状态，避免向过期订阅发送NOTIFY(RFC 3265)
        # R-11 通知方法添加锁保护，与put_inbound/remove_inbound一致
        key = f"{device_id}:MobilePosition"
        async with self._lock:
            sub = self._inbound.get(key)
            if not sub:
                return
            if sub.is_expired:
                return
        # Send SIP NOTIFY to subscriber
        try:
            await self._send_mobile_position_notify(sub, position)
        except Exception as e:
            logger.error(f"[SubscribeManager] Failed to send MobilePosition NOTIFY for {device_id}: {e}")
        # Dispatch to registered callbacks
        for cb in self._on_mobile_position:
            try:
                maybe = cb(device_id, position)
                if asyncio.iscoroutine(maybe):
                    await maybe
            except Exception as e:
                logger.warning(f"Mobile position callback error: {e}")

    async def _send_mobile_position_notify(self, sub: SubscribeInfo, position: dict) -> None:
        """Build and send MobilePosition NOTIFY"""
        from app.sip.server import sip_server
        from app.sip.message import SipMessage
        from app.sip.send import send_sip_bytes
        from app.core.config import settings, sip_host_for_contact

        if not sub.remote_addr or not sub.remote_proto:
            return
        addr = sub.remote_addr
        proto = sub.remote_proto
        transport = sip_server.get_transport(addr[0], addr[1], proto)
        if not transport:
            return

        sn = int(time.time() * 1000) % 100000
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Notify>
<CmdType>MobilePosition</CmdType>
<SN>{sn}</SN>
<DeviceID>{sub.device_id}</DeviceID>
<Time>{position.get("time", "")}</Time>
<Longitude>{position.get("longitude", "")}</Longitude>
<Latitude>{position.get("latitude", "")}</Latitude>
<Speed>{position.get("speed", "")}</Speed>
<Direction>{position.get("direction", "")}</Direction>
<Altitude>{position.get("altitude", "")}</Altitude>
</Notify>
"""
        sub.cseq += 1
        await self._persist_cseq(sub.call_id, sub.cseq)
        req = SipMessage()
        req.method = "NOTIFY"
        req.uri = f"sip:{sub.device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"

        branch = f"z9hG4bK{secrets.token_hex(6)}"
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={sub.to_tag}"
        req.headers["To"] = f"<sip:{sub.device_id}@{settings.SIP_DOMAIN}>;tag={sub.from_tag}"
        req.headers["Call-ID"] = sub.call_id
        req.headers["CSeq"] = f"{sub.cseq} NOTIFY"
        req.headers["Contact"] = f"<sip:{settings.SIP_ID}@{sip_host_for_contact()}:{settings.SIP_PORT}>"
        req.headers["Event"] = "MobilePosition"
        req.headers["Subscription-State"] = "active"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        req.body = xml_body

        await send_sip_bytes(proto, transport, addr, req.to_bytes())
        logger.info(f"[SubscribeManager] Sent MobilePosition NOTIFY to {sub.device_id}")

    async def notify_alarm(self, device_id: str, alarm_info: dict):
        """Dispatch alarm notification to registered callbacks. GB5 报警通知分发"""
        # W-08 通知方法检查订阅过期状态，避免向过期订阅发送NOTIFY(RFC 3265)
        # R-11 通知方法添加锁保护，与put_inbound/remove_inbound一致
        async with self._lock:
            alarm_subs = [(k, sub) for k, sub in self._inbound.items()
                          if sub.event.lower() == "alarm" and sub.device_id == device_id and not sub.is_expired]
        for key, sub in alarm_subs:
            try:
                await self._send_alarm_notify(sub, alarm_info)
            except Exception as e:
                logger.warning(f"Failed to send alarm NOTIFY to {sub.device_id}: {e}")
        # GB5 触发已注册的报警回调
        for cb in self._on_alarm:
            try:
                maybe = cb(device_id, alarm_info)
                if asyncio.iscoroutine(maybe):
                    await maybe
            except Exception as e:
                logger.warning(f"Alarm notification callback error: {e}")

    async def _send_alarm_notify(self, sub: SubscribeInfo, alarm_info: dict):
        """构建并发送 Alarm NOTIFY"""
        # 构建 Alarm NOTIFY XML 并发送
        from app.sip.server import sip_server
        from app.sip.message import SipMessage
        from app.sip.send import send_sip_bytes
        from app.core.config import settings, sip_host_for_contact

        if not sub.remote_addr or not sub.remote_proto:
            return
        addr = sub.remote_addr
        proto = sub.remote_proto
        transport = sip_server.get_transport(addr[0], addr[1], proto)
        if not transport:
            return

        alarm_xml = (
            '<?xml version="1.0" encoding="GB2312"?>\n'
            '<Notify>\n'
            '<CmdType>Alarm</CmdType>\n'
            f'<SN>{int(time.time() * 1000) % 100000}</SN>\n'  # M-12 Alarm NOTIFY SN扩大值域
            f'<DeviceID>{sub.device_id}</DeviceID>\n'
            f'<AlarmPriority>{alarm_info.get("priority", "1")}</AlarmPriority>\n'
            f'<AlarmMethod>{alarm_info.get("method", "2")}</AlarmMethod>\n'
            f'<AlarmTime>{alarm_info.get("time", "")}</AlarmTime>\n'
            f'<AlarmDescription>{alarm_info.get("description", "")}</AlarmDescription>\n'
            '</Notify>'
        )

        sub.cseq += 1
        await self._persist_cseq(sub.call_id, sub.cseq)  # M-01 Catalog/Alarm NOTIFY CSeq持久化
        req = SipMessage()
        req.method = "NOTIFY"
        req.uri = f"sip:{sub.device_id}@{addr[0]}:{addr[1]}"
        req.version = "SIP/2.0"

        branch = f"z9hG4bK{secrets.token_hex(6)}"
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={sub.to_tag}"
        req.headers["To"] = f"<sip:{sub.device_id}@{settings.SIP_DOMAIN}>;tag={sub.from_tag}"
        req.headers["Call-ID"] = sub.call_id
        req.headers["CSeq"] = f"{sub.cseq} NOTIFY"
        req.headers["Contact"] = f"<sip:{settings.SIP_ID}@{sip_host_for_contact()}:{settings.SIP_PORT}>"
        req.headers["Event"] = "Alarm"
        req.headers["Subscription-State"] = "active"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        req.body = alarm_xml

        await send_sip_bytes(proto, transport, addr, req.to_bytes())
        logger.info(f"[SubscribeManager] Sent alarm NOTIFY to {sub.device_id}")

    # MobilePosition出站订阅 — 启动移动位置订阅，发送SUBSCRIBE并自动续期
    async def start_mobile_position_subscribe(
        self,
        device_id: str,
        expires: int = 3600,
        interval: int = 5,
    ) -> bool:
        """Send MobilePosition SUBSCRIBE to device and start auto-renew."""
        from app.sip.server import sip_server
        from app.sip.message import SipMessage
        from app.sip.send import send_sip_bytes
        from app.core.config import settings, sip_host_for_contact
        from app.db.session import AsyncSessionLocal
        from app.models.asset import Asset
        from sqlalchemy import select

        # Check if already subscribed
        key = f"{device_id}:MobilePosition"
        async with self._lock:
            existing = self._outbound.get(key)
        if existing and existing.running:
            logger.info(f"[SubscribeManager] MobilePosition subscribe already active for {device_id}")
            return True

        # Look up device address
        async with AsyncSessionLocal() as session:
            asset = (await session.execute(select(Asset).where(Asset.gb_id == device_id))).scalars().first()
        if not asset:
            logger.warning(f"[SubscribeManager] Device {device_id} not found for MobilePosition subscribe")
            return False

        addr = (str(asset.ip_addr or ""), int(asset.port or 5060))
        proto = str(getattr(asset, "transport", "UDP") or "UDP")
        transport = sip_server.get_transport(addr[0], addr[1], proto)
        if not transport:
            logger.warning(f"[SubscribeManager] No transport for device {device_id}")
            return False

        call_id = f"sub_MobilePosition_{device_id}_{secrets.token_hex(4)}@{sip_host_for_contact()}"
        from_tag = secrets.token_hex(4)
        sn = int(time.time() * 1000) % 100000
        domain = str(getattr(settings, "SIP_DOMAIN", sip_host_for_contact()))

        req = SipMessage()
        req.method = "SUBSCRIBE"
        req.uri = f"sip:{device_id}@{domain}"
        req.version = "SIP/2.0"

        branch = f"z9hG4bK{secrets.token_hex(6)}"
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{domain}>;tag={from_tag}"
        req.headers["To"] = f"<sip:{device_id}@{domain}>"
        req.headers["Call-ID"] = call_id
        req.headers["CSeq"] = "1 SUBSCRIBE"
        req.headers["Contact"] = f"<sip:{settings.SIP_ID}@{sip_host_for_contact()}:{settings.SIP_PORT}>"
        req.headers["Event"] = "MobilePosition"
        req.headers["Expires"] = str(expires)
        req.headers["Accept"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME

        body = f"""<?xml version="1.0" encoding="GB2312"?>
<Query>
<CmdType>MobilePosition</CmdType>
<SN>{sn}</SN>
<DeviceID>{device_id}</DeviceID>
<Interval>{interval}</Interval>
</Query>
"""
        req.body = body

        try:
            await send_sip_bytes(proto, transport, addr, req.to_bytes())
            logger.info(f"[SubscribeManager] Sent MobilePosition SUBSCRIBE to device {device_id}, expires={expires}, interval={interval}")
        except Exception as e:
            logger.error(f"[SubscribeManager] Failed to send MobilePosition SUBSCRIBE to {device_id}: {e}")
            return False

        sub = OutboundSubscribe(
            device_id=device_id,
            event="MobilePosition",
            call_id=call_id,
            from_tag=from_tag,
            to_tag="",
            cseq=1,
            expires=expires,
            sn=sn,
            interval=interval,
            last_sent=time.monotonic(),
        )
        await self.put_outbound(sub)
        try:
            await self.start_outbound_renew(
                device_id=device_id,
                event="MobilePosition",
                send_func=lambda sub_obj, dev_id=device_id, exp=expires, iv=interval:
                    self._renew_mobile_position_subscribe(sub_obj, dev_id, exp, iv),
            )
        except Exception as e:
            logger.warning(f"[SubscribeManager] Failed to start MobilePosition renew for {device_id}: {e}")
        return True

    async def _renew_mobile_position_subscribe(
        self, sub: OutboundSubscribe, device_id: str, expires: int, interval: int
    ) -> bool:
        """Renew MobilePosition SUBSCRIBE (called by renew loop)."""
        from app.sip.server import sip_server
        from app.sip.message import SipMessage
        from app.sip.send import send_sip_bytes
        from app.core.config import settings, sip_host_for_contact
        from app.db.session import AsyncSessionLocal
        from app.models.asset import Asset
        from sqlalchemy import select

        async with AsyncSessionLocal() as session:
            asset = (await session.execute(select(Asset).where(Asset.gb_id == device_id))).scalars().first()
        if not asset:
            return False

        addr = (str(asset.ip_addr or ""), int(asset.port or 5060))
        proto = str(getattr(asset, "transport", "UDP") or "UDP")
        transport = sip_server.get_transport(addr[0], addr[1], proto)
        if not transport:
            return False

        sn = int(time.time() * 1000) % 100000
        domain = str(getattr(settings, "SIP_DOMAIN", sip_host_for_contact()))

        req = SipMessage()
        req.method = "SUBSCRIBE"
        req.uri = f"sip:{device_id}@{domain}"
        req.version = "SIP/2.0"

        branch = f"z9hG4bK{secrets.token_hex(6)}"
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{domain}>;tag={sub.from_tag}"
        req.headers["To"] = f"<sip:{device_id}@{domain}>;tag={sub.to_tag}" if sub.to_tag else f"<sip:{device_id}@{domain}>"
        req.headers["Call-ID"] = sub.call_id
        req.headers["CSeq"] = f"{sub.cseq} SUBSCRIBE"
        req.headers["Contact"] = f"<sip:{settings.SIP_ID}@{sip_host_for_contact()}:{settings.SIP_PORT}>"
        req.headers["Event"] = "MobilePosition"
        req.headers["Expires"] = str(expires)
        req.headers["Accept"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME

        body = f"""<?xml version="1.0" encoding="GB2312"?>
<Query>
<CmdType>MobilePosition</CmdType>
<SN>{sn}</SN>
<DeviceID>{device_id}</DeviceID>
<Interval>{interval}</Interval>
</Query>
"""
        req.body = body

        try:
            await send_sip_bytes(proto, transport, addr, req.to_bytes())
            logger.info(f"[SubscribeManager] Renewed MobilePosition SUBSCRIBE to device {device_id}")
            return True
        except Exception as e:
            logger.error(f"[SubscribeManager] Failed to renew MobilePosition SUBSCRIBE to {device_id}: {e}")
            return False

    # MobilePosition出站订阅 — 停止移动位置订阅，发送expires=0取消
    async def stop_mobile_position_subscribe(self, device_id: str) -> bool:
        """Send MobilePosition SUBSCRIBE with expires=0 to cancel subscription."""
        from app.sip.server import sip_server
        from app.sip.message import SipMessage
        from app.sip.send import send_sip_bytes
        from app.core.config import settings, sip_host_for_contact
        from app.db.session import AsyncSessionLocal
        from app.models.asset import Asset
        from sqlalchemy import select

        key = f"{device_id}:MobilePosition"
        async with self._lock:
            sub = self._outbound.get(key)
        if not sub:
            logger.info(f"[SubscribeManager] No active MobilePosition subscribe for {device_id}")
            return False

        # Look up device address
        async with AsyncSessionLocal() as session:
            asset = (await session.execute(select(Asset).where(Asset.gb_id == device_id))).scalars().first()
        if not asset:
            logger.warning(f"[SubscribeManager] Device {device_id} not found for MobilePosition unsubscribe")
            # Still clean up the outbound record
            await self.remove_outbound(device_id, "MobilePosition")
            return False

        addr = (str(asset.ip_addr or ""), int(asset.port or 5060))
        proto = str(getattr(asset, "transport", "UDP") or "UDP")
        transport = sip_server.get_transport(addr[0], addr[1], proto)
        if not transport:
            logger.warning(f"[SubscribeManager] No transport for device {device_id}")
            await self.remove_outbound(device_id, "MobilePosition")
            return False

        sn = int(time.time() * 1000) % 100000
        domain = str(getattr(settings, "SIP_DOMAIN", sip_host_for_contact()))

        req = SipMessage()
        req.method = "SUBSCRIBE"
        req.uri = f"sip:{device_id}@{domain}"
        req.version = "SIP/2.0"

        branch = f"z9hG4bK{secrets.token_hex(6)}"
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{domain}>;tag={sub.from_tag}"
        req.headers["To"] = f"<sip:{device_id}@{domain}>;tag={sub.to_tag}" if sub.to_tag else f"<sip:{device_id}@{domain}>"
        req.headers["Call-ID"] = sub.call_id
        req.headers["CSeq"] = f"{sub.cseq + 1} SUBSCRIBE"
        req.headers["Contact"] = f"<sip:{settings.SIP_ID}@{sip_host_for_contact()}:{settings.SIP_PORT}>"
        req.headers["Event"] = "MobilePosition"
        req.headers["Expires"] = "0"
        req.headers["Accept"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME

        body = f"""<?xml version="1.0" encoding="GB2312"?>
<Query>
<CmdType>MobilePosition</CmdType>
<SN>{sn}</SN>
<DeviceID>{device_id}</DeviceID>
<Interval>0</Interval>
</Query>
"""
        req.body = body

        try:
            await send_sip_bytes(proto, transport, addr, req.to_bytes())
            logger.info(f"[SubscribeManager] Sent MobilePosition SUBSCRIBE expires=0 to device {device_id}")
        except Exception as e:
            logger.error(f"[SubscribeManager] Failed to send MobilePosition unsubscribe to {device_id}: {e}")

        # Clean up outbound record and cancel renew task
        await self.remove_outbound(device_id, "MobilePosition")
        return True

    # R-11 通知方法添加锁保护，与put_inbound/remove_inbound一致
    async def get_stats(self) -> dict:
        async with self._lock:
            return {
                "inbound_count": len(self._inbound),
                "outbound_count": len(self._outbound),
                "inbound_subscribes": [
                    {"device_id": v.device_id, "event": v.event, "expires": v.expires, "remaining": round(v.remaining_seconds, 1)}
                    for v in self._inbound.values()
                ],
                "outbound_subscribes": [
                    {"device_id": v.device_id, "event": v.event, "expires": v.expires, "running": v.running}
                    for v in self._outbound.values()
                ],
            }

    # R-11 通知方法添加锁保护，与put_inbound/remove_inbound一致
    async def remove_all_for_device(self, device_id: str) -> int:
        # N-02 锁内仅收集待清理条目，锁外执行网络I/O，避免长时间持锁
        subs_to_unsubscribe: list[OutboundSubscribe] = []
        async with self._lock:
            removed = 0
            keys_to_remove = [k for k in self._outbound if k.startswith(f"{device_id}:")]
            for k in keys_to_remove:
                sub = self._outbound.pop(k, None)
                if sub:
                    sub.running = False
                    if sub.renew_task and not sub.renew_task.done():
                        sub.renew_task.cancel()
                    subs_to_unsubscribe.append(sub)
                    removed += 1
            inbound_keys = [k for k in self._inbound if k.startswith(f"{device_id}:")]
            for k in inbound_keys:
                self._inbound.pop(k, None)
                renew_task = self._inbound_renew_tasks.pop(k, None)
                if renew_task and not renew_task.done():
                    renew_task.cancel()
                removed += 1
            if removed:
                logger.info(f"[SubscribeManager] Cleaned up {removed} subscriptions for offline device {device_id}")
        # N-01 使用_send_unsubscribe_outbound（支持OutboundSubscribe类型）
        for sub in subs_to_unsubscribe:
            try:
                await self._send_unsubscribe_outbound(sub)
            except Exception as e:
                logger.warning(f"Failed to send SUBSCRIBE expires=0 for {sub.device_id}/{sub.event}: {e}")
        return removed


async def send_subscribe_to_device(
    device_id: str,
    event: str,
    expires: int = 3600,
    interval: int = 5,
    cseq: int = 1,
    call_id: str | None = None,
    from_tag: str | None = None,
) -> bool:
    from app.sip.server import sip_server
    from app.sip.message import SipMessage
    from app.sip.send import send_sip_bytes
    from app.core.config import settings, sip_host_for_contact
    from app.db.session import AsyncSessionLocal
    from app.models.asset import Asset
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        asset = (await session.execute(select(Asset).where(Asset.gb_id == device_id))).scalars().first()
    if not asset:
        logger.warning(f"[SubscribeManager] Device {device_id} not found")
        return False

    addr = (str(asset.ip_addr or ""), int(asset.port or 5060))
    proto = str(getattr(asset, "transport", "UDP") or "UDP")
    transport = sip_server.get_transport(addr[0], addr[1], proto)
    if not transport:
        logger.warning(f"[SubscribeManager] No transport for device {device_id}")
        return False

    if not call_id:
        call_id = f"sub_{event}_{device_id}_{secrets.token_hex(4)}@{sip_host_for_contact()}"
    if not from_tag:
        from_tag = secrets.token_hex(4)
    sn = int(time.time() * 1000) % 100000

    domain = str(getattr(settings, "SIP_DOMAIN", sip_host_for_contact()))
    req = SipMessage()
    req.method = "SUBSCRIBE"
    req.uri = f"sip:{device_id}@{domain}"
    req.version = "SIP/2.0"

    branch = f"z9hG4bK{secrets.token_hex(6)}"
    req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
    req.headers["From"] = f"<sip:{settings.SIP_ID}@{domain}>;tag={from_tag}"
    req.headers["To"] = f"<sip:{device_id}@{domain}>"
    req.headers["Call-ID"] = call_id
    req.headers["CSeq"] = f"{cseq} SUBSCRIBE"
    req.headers["Contact"] = f"<sip:{settings.SIP_ID}@{sip_host_for_contact()}:{settings.SIP_PORT}>"
    req.headers["Event"] = event
    req.headers["Expires"] = str(expires)
    req.headers["Accept"] = "Application/MANSCDP+xml"
    req.headers["Max-Forwards"] = "70"
    req.headers["User-Agent"] = settings.PROJECT_NAME

    body = f"""<?xml version="1.0" encoding="GB2312"?>
<Query>
<CmdType>{event}</CmdType>
<SN>{sn}</SN>
<DeviceID>{device_id}</DeviceID>
<Interval>{interval}</Interval>
</Query>
"""
    req.body = body

    try:
        await send_sip_bytes(proto, transport, addr, req.to_bytes())
        logger.info(f"[SubscribeManager] Sent SUBSCRIBE {event} to device {device_id}")
    except Exception as e:
        logger.error(f"[SubscribeManager] Failed to send SUBSCRIBE to {device_id}: {e}")
        return False

    sub = OutboundSubscribe(
        device_id=device_id,
        event=event,
        call_id=call_id,
        from_tag=from_tag,
        to_tag="",
        cseq=cseq,
        expires=expires,
        sn=sn,
        interval=interval,
        last_sent=time.monotonic(),
    )
    await subscribe_manager.put_outbound(sub)
    try:
        await subscribe_manager.start_outbound_renew(  # async function call must be awaited
            device_id=device_id,
            event=event,
            send_func=lambda sub_obj, dev_id=device_id, ev=event, exp=expires, iv=interval:
                send_subscribe_to_device(dev_id, ev, exp, iv, cseq=sub_obj.cseq,
                                          call_id=sub_obj.call_id, from_tag=sub_obj.from_tag),
        )
    except Exception as e:
        logger.warning(f"[SubscribeManager] Failed to start outbound renew for {device_id}/{event}: {e}")
    return True


subscribe_manager = SubscribeManager()
