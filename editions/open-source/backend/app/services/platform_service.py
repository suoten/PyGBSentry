import asyncio
from loguru import logger
import json
from app.db.session import AsyncSessionLocal
from app.models.platform import ParentPlatform
from app.api.deps import get_or_404


def _safe_create_task(coro):
    task = asyncio.create_task(coro)
    task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
    return task
from app.models.platform_runtime import PlatformRuntime
from app.models.resource import Resource
from app.models.platform_catalog_resource import PlatformCatalogResource
from app.models.stream_session import StreamSession
from app.sip.message import SipMessage
from app.sip.auth import DigestAuth
from app.sip.trace_events import should_warn_unknown_event_once
from app.services.sip_trace_store import schedule_store_sip_trace
from app.core.config import settings, sip_host_for_contact
from sqlalchemy import select, update
import time
import random
import string
import secrets
import datetime
import contextlib
import re
import hashlib
from xml.sax.saxutils import escape as _xml_escape
from app.sip.send import send_sip_bytes
from app.sip.sdp import build_sdp as _build_sdp



def _parse_host_port(value: str) -> tuple[str, int] | None:
    raw = (value or "").strip()
    if not raw:
        return None
    m = re.search(r"^\(\s*'([^']+)'\s*,\s*(\d+)\s*\)$", raw)
    if m:
        return (m.group(1), int(m.group(2)))
    m = re.search(r"^([0-9a-fA-F\.:]+)\s*:\s*(\d+)$", raw)
    if m:
        return (m.group(1), int(m.group(2)))
    return None

def _parse_sip_uri_host_port(value: str) -> tuple[str, int] | None:
    raw = (value or "").strip()
    if not raw:
        return None
    m = re.search(r"sip:(?:[^@;>]+@)?(?P<host>[^:;>]+)(?::(?P<port>\d+))?", raw, re.IGNORECASE)
    if not m:
        return None
    host = (m.group("host") or "").strip()
    if not host:
        return None
    port = int(m.group("port") or 5060)
    return (host, port)


def _attach_trace_header(req: SipMessage) -> str:
    call_id = (req.get_header("Call-ID") or "").strip()
    if call_id:
        req.headers["X-Trace-ID"] = call_id
    return call_id


def _platform_proto(p: ParentPlatform) -> str:
    transport = (getattr(p, "transport", None) or "UDP").strip().upper()
    return transport if transport in {"UDP", "TCP"} else "UDP"


def _sip_trace_should_log() -> bool:
    if not bool(getattr(settings, "SIP_DEBUG_TRACE_ENABLED", False)):
        return False
    try:
        rate = float(getattr(settings, "SIP_TRACE_SAMPLE_RATE", 1.0) or 1.0)
    except Exception:
        rate = 1.0
    rate = max(0.0, min(1.0, rate))
    if rate >= 1.0:
        return True
    if rate <= 0.0:
        return False
    return random.random() < rate


def _sip_trace_log(event: str, **fields):
    if not _sip_trace_should_log():
        return
    if should_warn_unknown_event_once(event):
        logger.warning(f"SIP_TRACE event not registered in trace_events.py: {event}")
    payload = {"event": event}
    payload.update(fields)
    logger.info(f"SIP_TRACE {payload}")
    schedule_store_sip_trace(payload)

class PlatformService:
    def __init__(self, sip_server):
        self.sip_server = sip_server
        self.platforms = {} # GBID -> Platform Info
        self.running = False
        self._reg_states = {} # CallID -> {platform_id, status, last_auth}
        self._outbound_tcp = {}  # (ip, port) -> asyncio.StreamWriter
        self._keepalive_miss_count = {}  # server_gb_id -> int
        self._catalog_states = {}  # CallID -> {platform_id, tenant_id, batch_idx, batch_total}
        self._catalog_ack_counter = {}  # (tenant_id, platform_id) -> {total, ok, last_status_code}
        self._cascade_record_queries = {}  # local_sn -> {platform_id, server_gb_id, original_sn, original_channel_id, real_channel_id, created_at}

    async def start(self):
        self.running = True
        # Register response handler for cascade
        self.sip_server.register_response_handler(self._handle_response)
        _safe_create_task(self._run_loop())

    async def trigger_register(self, platform_id: str) -> None:
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(ParentPlatform).where(ParentPlatform.id == platform_id)
                result = await session.execute(stmt)
                p = result.scalars().first()
        except Exception as e:
            logger.error(f"trigger_register DB error: {e}")
            return
        if not p or not p.enable:
            return
        await self._runtime_patch(p.tenant_id or "default", platform_id, {
            "action.last_manual_register_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        })
        await self._register(p)

    async def trigger_push_catalog(self, platform_id: str) -> None:
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(ParentPlatform).where(ParentPlatform.id == platform_id)
                result = await session.execute(stmt)
                p = result.scalars().first()
        except Exception as e:
            logger.error(f"trigger_push_catalog DB error: {e}")
            return
        if not p or not p.enable:
            return
        await self._runtime_patch(p.tenant_id or "default", platform_id, {
            "action.last_manual_push_catalog_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        })
        _safe_create_task(self._push_catalog(platform_id))

    async def trigger_notify(self, platform_id: str, event: str, xml_body: str) -> None:
        ev0 = (event or "").split(";", 1)[0].strip()
        if not ev0:
            return
        try:
            async with AsyncSessionLocal() as session:
                p = (
                    await session.execute(select(ParentPlatform).where(ParentPlatform.id == platform_id))
                ).scalars().first()
                if not p or not p.is_online:
                    return
                from app.models.platform_subscription import PlatformSubscription
                now_dt = datetime.datetime.now(datetime.timezone.utc)
                sub = (
                    await session.execute(
                        select(PlatformSubscription).where(
                            PlatformSubscription.tenant_id == (p.tenant_id or "default"),
                            PlatformSubscription.platform_id == platform_id,
                            PlatformSubscription.event == ev0,
                            PlatformSubscription.expires_at.is_not(None),
                            PlatformSubscription.expires_at > now_dt,
                        )
                    )
                ).scalars().first()
                if not sub:
                    return
                if not (sub.last_call_id or "") or not (sub.remote_from_tag or "") or not (sub.local_to_tag or ""):
                    return
                cseq = int(sub.notify_cseq or 1)
                sub.notify_cseq = cseq + 1
                await session.commit()
        except Exception as e:
            logger.error(f"trigger_notify DB error: {e}")
            return

        req = SipMessage()
        req.method = "NOTIFY"
        req_proto = (sub.last_transport or "").strip() or _platform_proto(p)

        uri = ""
        contact = (sub.remote_contact or "").strip()
        if contact:
            m = re.search(r"<\s*(sip:[^>]+)\s*>", contact, re.IGNORECASE)
            uri = (m.group(1) if m else contact).strip()
        if not uri:
            uri = f"sip:{p.server_gb_id}@{p.server_ip}:{p.server_port}"
        req.uri = uri

        req.headers["Via"] = f"SIP/2.0/{req_proto} {settings.SIP_IP}:{settings.SIP_PORT};rport;branch=z9hG4bKnotify{cseq}{int(time.time() * 1000)}"
        req.headers["Max-Forwards"] = "70"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={sub.local_to_tag}"
        req.headers["To"] = f"<sip:{p.server_gb_id}@{settings.SIP_DOMAIN}>;tag={sub.remote_from_tag}"
        req.headers["Call-ID"] = str(sub.last_call_id or "")
        req.headers["CSeq"] = f"{cseq} NOTIFY"
        req.headers["Event"] = ev0
        exp_remain = 0
        try:
            if sub.expires_at:
                exp_remain = max(0, int((sub.expires_at - datetime.datetime.now(datetime.timezone.utc)).total_seconds()))
        except Exception:
            exp_remain = 0
        if exp_remain > 0:
            req.headers["Subscription-State"] = f"active;expires={exp_remain}"
        else:
            req.headers["Subscription-State"] = "active"
        rr = (sub.record_route or "").strip()
        if rr:
            req.headers["Route"] = rr
        req.headers["Contact"] = f"<sip:{settings.SIP_ID}@{settings.SIP_IP}:{settings.SIP_PORT}>"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.body = xml_body

        trace_id = _attach_trace_header(req)

        try:
            dst = _parse_host_port(str(sub.last_addr or "")) or _parse_sip_uri_host_port(uri) or (p.server_ip, int(p.server_port))
            _safe_create_task(
                    self._send_sip_request_and_wait(
                        req=req,
                        ip=dst[0],
                        port=int(dst[1]),
                        proto=req_proto,
                        timeout_seconds=2.2,
                        retries=1,
                    )
                )
            _sip_trace_log(
                "platform_notify_sent",
                trace_id=trace_id,
                platform_id=platform_id,
                server_gb_id=p.server_gb_id,
                event=ev0,
            )
        except Exception as e:
            logger.error(f"Failed to send NOTIFY to {platform_id}: {e}")

    async def _runtime_patch(self, tenant_id: str, platform_id: str, patch: dict) -> None:
        if not patch:
            return
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(PlatformRuntime).where(
                PlatformRuntime.platform_id == platform_id,
                PlatformRuntime.tenant_id == tenant_id,
            )
            result = await session.execute(stmt)
            runtime = result.scalars().first()
            data: dict = {}
            if runtime and runtime.data:
                try:
                    loaded = json.loads(runtime.data)
                    if isinstance(loaded, dict):
                        data = loaded
                except Exception:
                    data = {}
            for k, v in patch.items():
                key = str(k or "").strip()
                if not key:
                    continue
                data[key] = v
            if runtime:
                runtime.data = json.dumps(data, ensure_ascii=False)
            else:
                runtime = PlatformRuntime(
                    tenant_id=tenant_id,
                    platform_id=platform_id,
                    data=json.dumps(data, ensure_ascii=False),
                )
                session.add(runtime)
            try:
                await session.commit()
            except Exception:
                await session.rollback()
        except Exception as e:
            logger.error(f"_runtime_patch DB error: {e}")

    async def stop(self):
        self.running = False
        for writer in list(self._outbound_tcp.values()):
            with contextlib.suppress(Exception):
                writer.close()
                await writer.wait_closed()
        self._outbound_tcp.clear()

    async def handle_platform_offline(self, platform_id: str, reason: str) -> None:
        try:
            async with AsyncSessionLocal() as session:
                p = (await session.execute(select(ParentPlatform).where(ParentPlatform.id == platform_id))).scalars().first()
                if not p:
                    return
                tenant_id = p.tenant_id or "default"
        except Exception as e:
            logger.error(f"handle_platform_offline DB error: {e}")
            return

        try:
            from app.services.platform_subscription_service import platform_subscription_service
            await platform_subscription_service.remove_all_for_platform(
                tenant_id=tenant_id,
                platform_id=platform_id,
                reason=reason or "offline",
            )
        except Exception as e:
            logger.warning(f"Error: {e}")

        try:
            from app.services.stream_session_service import stop_cascade_push_session, release_stream_session
            async with AsyncSessionLocal() as session:
                # FIXED-P2: S-12 平台离线时清理cascade_push、cascade_bypass及匹配platform_id的所有会话
                # 1) 清理 cascade_push 会话
                rows = (
                    await session.execute(
                        select(StreamSession).where(
                            StreamSession.cascade_platform_id == platform_id,
                            StreamSession.from_tag == "cascade_push",
                        )
                    )
                ).scalars().all()
                for s in rows:
                    await stop_cascade_push_session(session, s, reason=reason or "platform_offline")
                # 2) 清理 cascade_bypass 会话
                bypass_rows = (
                    await session.execute(
                        select(StreamSession).where(
                            StreamSession.cascade_platform_id == platform_id,
                            StreamSession.app == "cascade_bypass",
                        )
                    )
                ).scalars().all()
                for s in bypass_rows:
                    await release_stream_session(session, s, reason=reason or "platform_offline")
                # 3) 清理其他匹配 platform_id 的会话
                other_rows = (
                    await session.execute(
                        select(StreamSession).where(
                            StreamSession.cascade_platform_id == platform_id,
                        )
                    )
                ).scalars().all()
                cleaned_ids = {s.id for s in rows} | {s.id for s in bypass_rows}
                for s in other_rows:
                    if s.id not in cleaned_ids:
                        await release_stream_session(session, s, reason=reason or "platform_offline")
                await session.commit()
        except Exception as e:
            logger.warning(f"Error: {e}")

        self._keepalive_miss_count.pop(str(getattr(p, "server_gb_id", "") or ""), None)
        keys_to_remove = [k for k, v in self._reg_states.items() if v.get("platform_id") == platform_id]
        for k in keys_to_remove:
            self._reg_states.pop(k, None)
        keys_to_remove2 = [k for k, v in self._catalog_states.items() if v.get("platform_id") == platform_id]
        for k in keys_to_remove2:
            self._catalog_states.pop(k, None)
        # FIXED-P4: W-17 平台离线时清理 _catalog_ack_counter 残留条目，防止内存泄漏
        ack_keys_to_remove = [k for k in self._catalog_ack_counter if k[1] == platform_id]
        for k in ack_keys_to_remove:
            self._catalog_ack_counter.pop(k, None)
        await self._runtime_patch(tenant_id, platform_id, {
            "offline.cleanup_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "offline.cleanup_reason": str(reason or ""),
        })

    async def _handle_response(self, message: SipMessage, addr: tuple, proto: str, transport):
        """
        Handle SIP responses from parent platforms
        """
        call_id = message.call_id
        _sip_trace_log(
            "platform_response_received",
            trace_id=call_id,
            status_code=message.status_code,
            cseq=message.get_header("CSeq") or "",
            from_header=message.get_header("From") or "",
            to_header=message.get_header("To") or "",
            proto=proto,
            addr=str(addr),
        )
        if call_id.startswith("keep_") and message.status_code == 200:
            server_gb_id = call_id.split("@", 1)[0].replace("keep_", "", 1)
            if server_gb_id:
                self._keepalive_miss_count[server_gb_id] = 0
                async with AsyncSessionLocal() as session:
                    stmt = update(ParentPlatform).where(
                        ParentPlatform.server_gb_id == server_gb_id
                    ).values(
                        is_online=True,
                        last_keepalive=datetime.datetime.now(datetime.timezone.utc)
                    )
                    await session.execute(stmt)
                    await session.commit()
                async with AsyncSessionLocal() as session:
                    p_result = await session.execute(select(ParentPlatform).where(ParentPlatform.server_gb_id == server_gb_id))
                    p = p_result.scalars().first()
                if p:
                    await self._runtime_patch(p.tenant_id or "default", p.id, {
                        "keepalive.last_ack_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        "keepalive.last_ack_addr": str(addr),
                        "keepalive.last_ack_transport": str(proto or ""),
                        "keepalive.miss_count": 0,
                    })
                _sip_trace_log(
                    "platform_keepalive_ack",
                    trace_id=call_id,
                    server_gb_id=server_gb_id,
                    status_code=message.status_code,
                )
            return
        try:
            cseq = message.get_header("CSeq") or ""
            method = (cseq.split(" ", 1)[1] if " " in cseq else "").strip().upper()
        except Exception:
            method = ""
        if method == "NOTIFY" and int(message.status_code or 0) == 200:
            try:
                from app.services.platform_subscription_service import platform_subscription_service
                await platform_subscription_service.mark_notify_by_call_id(call_id=call_id)
            except Exception as e:
                logger.warning(f"Error: {e}")
            return
        if call_id.startswith("cat_"):
            state = self._catalog_states.pop(call_id, None)
            if not state:
                return
            platform_id = state.get("platform_id")
            tenant_id = state.get("tenant_id") or "default"
            batch_idx = int(state.get("batch_idx") or 0)
            batch_total = int(state.get("batch_total") or 0)
            status_code = int(message.status_code or 0)
            key = (tenant_id, platform_id)
            counter = self._catalog_ack_counter.get(key) or {"total": batch_total, "ok": 0, "last_status_code": None}
            counter["total"] = max(int(counter.get("total") or 0), batch_total)
            counter["last_status_code"] = status_code
            if status_code == 200:
                counter["ok"] = int(counter.get("ok") or 0) + 1
            self._catalog_ack_counter[key] = counter
            await self._runtime_patch(tenant_id, platform_id, {
                "catalog.last_ack_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "catalog.last_ack_call_id": call_id,
                "catalog.last_ack_status_code": status_code,
                "catalog.ack_ok_count": int(counter.get("ok") or 0),
                "catalog.ack_total": int(counter.get("total") or 0),
            })
            if status_code != 200:
                await self._runtime_patch(tenant_id, platform_id, {
                    "catalog.last_push_ok": False,
                    "catalog.last_push_error": f"catalog_ack_failed status={status_code}",
                })
            if int(counter.get("total") or 0) > 0 and int(counter.get("ok") or 0) >= int(counter.get("total") or 0):
                await self._runtime_patch(tenant_id, platform_id, {
                    "catalog.last_ack_finished_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "catalog.last_ack_ok": True,
                })
                self._catalog_ack_counter.pop(key, None)
            _sip_trace_log(
                "platform_catalog_ack",
                trace_id=call_id,
                platform_id=platform_id,
                status_code=status_code,
                batch_idx=batch_idx,
                batch_total=batch_total,
            )
            return

    async def _start_session_tasks(self, platform_id: str):
        if not hasattr(self, '_active_keepalive_tasks'):
            self._active_keepalive_tasks: dict[str, asyncio.Task] = {}
        old_task = self._active_keepalive_tasks.get(platform_id)
        if not old_task or old_task.done():
            task = _safe_create_task(self._keepalive_loop(platform_id))
            self._active_keepalive_tasks[platform_id] = task
        async with AsyncSessionLocal() as session:
            stmt = select(ParentPlatform).where(ParentPlatform.id == platform_id)
            r = await session.execute(stmt)
            p = get_or_404(r, detail="ParentPlatform not found")  # FIXED: ORM查询结果空值判断
        delay = getattr(p, "catalog_push_delay_seconds", None) or 0
        if delay > 0:
            from app.core.delay_queue import run_after
            if p:
                await self._runtime_patch(p.tenant_id or "default", platform_id, {
                    "catalog.first_push_scheduled_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "catalog.first_push_delay_seconds": float(delay),
                })
            run_after(float(delay), self._push_catalog(platform_id))
        else:
            if p:
                await self._runtime_patch(p.tenant_id or "default", platform_id, {
                    "catalog.first_push_scheduled_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "catalog.first_push_delay_seconds": 0,
                })
            _safe_create_task(self._push_catalog(platform_id))

    async def _keepalive_loop(self, platform_id: str):
        while self.running:
            keepalive_interval = 60
            async with AsyncSessionLocal() as session:
                stmt = select(ParentPlatform).where(ParentPlatform.id == platform_id)
                result = await session.execute(stmt)
                p = result.scalars().first()
                if not p or not p.is_online:
                    break
                keepalive_interval = int(p.keepalive_interval or 60) or 60

                # FIXED: 级联注册续期 — 注册有效期80%时间已过时主动发送REGISTER续期
                register_interval = int(p.register_interval or 3600) or 3600
                call_id = f"reg_{p.server_gb_id}@{settings.SIP_IP}"
                state = self._reg_states.get(call_id, {})
                last_ok_time = state.get("last_ok_time", 0)
                elapsed_since_ok = time.time() - last_ok_time
                if last_ok_time > 0 and elapsed_since_ok >= register_interval * 0.8:
                    try:
                        logger.info(f"[PlatformService] Register renewal due for {p.server_gb_id}, elapsed={elapsed_since_ok:.0f}s, interval={register_interval}s")
                        await self._register(p)
                    except Exception as e:
                        logger.warning(f"[PlatformService] Register renewal failed for {p.server_gb_id}: {e}")

                await self._send_keepalive(p)
                miss = self._keepalive_miss_count.get(p.server_gb_id, 0)
                threshold = max(1, int(getattr(settings, "SIP_PLATFORM_KEEPALIVE_MISS_THRESHOLD", 3) or 3))
                if miss >= threshold:
                    _sip_trace_log(
                        "platform_keepalive_miss_re_register",
                        trace_id=f"reg_{p.server_gb_id}@{settings.SIP_IP}",
                        server_gb_id=p.server_gb_id,
                        miss_count=miss,
                        threshold=threshold,
                    )
                    try:
                        await session.execute(
                            update(ParentPlatform).where(ParentPlatform.id == platform_id).values(
                                is_online=False,
                            )
                        )
                        await session.commit()
                    except Exception:
                        await session.rollback()
                    await self._runtime_patch(p.tenant_id or "default", platform_id, {
                        "keepalive.offline_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        "keepalive.offline_reason": f"miss_threshold_reached miss={miss} threshold={threshold}",
                    })
                    _safe_create_task(self.handle_platform_offline(platform_id, reason="keepalive_miss_threshold"))
                    self._keepalive_miss_count[p.server_gb_id] = 0
                    await self._register(p)
            await asyncio.sleep(keepalive_interval)

    async def _send_keepalive(self, p: ParentPlatform):
        sn = int(time.time()) % 100000
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Notify>
<CmdType>Keepalive</CmdType>
<SN>{sn}</SN>
<DeviceID>{p.client_gb_id}</DeviceID>
<Status>OK</Status>
</Notify>
"""
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{p.server_gb_id}@{p.server_ip}:{p.server_port}"
        req_proto = _platform_proto(p)
        req.headers["Via"] = f"SIP/2.0/{req_proto} {settings.SIP_IP}:{settings.SIP_PORT};rport;branch=z9hG4bKkeep{sn}"
        req.headers["From"] = f"<sip:{p.client_gb_id}@{settings.SIP_DOMAIN}>;tag=keep{sn}"
        req.headers["To"] = f"<sip:{p.server_gb_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = f"keep_{p.server_gb_id}@{settings.SIP_IP}"
        req.headers["CSeq"] = f"{sn} MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"

        req.body = xml_body
        trace_id = _attach_trace_header(req)
        self._keepalive_miss_count[p.server_gb_id] = self._keepalive_miss_count.get(p.server_gb_id, 0) + 1
        _safe_create_task(self._send_keepalive_tx(p, req, req_proto))
        await self._runtime_patch(p.tenant_id or "default", p.id, {
            "keepalive.last_sent_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "keepalive.last_sent_call_id": f"keep_{p.server_gb_id}@{settings.SIP_IP}",
            "keepalive.last_sent_transport": req_proto,
            "keepalive.miss_count": self._keepalive_miss_count.get(p.server_gb_id, 0),
        })
        logger.info(f"[trace_id={trace_id}] Sent platform keepalive to {p.server_gb_id}")
        _sip_trace_log(
            "platform_keepalive_sent",
            trace_id=trace_id,
            server_gb_id=p.server_gb_id,
            server_ip=p.server_ip,
            server_port=p.server_port,
            transport=req_proto,
            miss_count=self._keepalive_miss_count.get(p.server_gb_id, 0),
        )

    async def _send_keepalive_tx(self, p: ParentPlatform, req: SipMessage, proto: str) -> None:
        try:
            resp, meta = await self._send_sip_request_and_wait(
                req=req,
                ip=p.server_ip,
                port=p.server_port,
                proto=proto,
                timeout_seconds=2.2,
                retries=0,
            )
            await self._runtime_patch(p.tenant_id or "default", p.id, {
                "keepalive.last_tx_ok_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "keepalive.last_tx_status_code": int(resp.status_code or 0),
                "keepalive.last_tx_rtt_ms": int(meta.get("rtt_ms") or 0),
                "keepalive.last_tx_attempts": int(meta.get("attempts") or 0),
            })
        except asyncio.TimeoutError:
            await self._runtime_patch(p.tenant_id or "default", p.id, {
                "keepalive.last_tx_timeout_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            })
        except Exception:
            await self._runtime_patch(p.tenant_id or "default", p.id, {
                "keepalive.last_tx_error_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            })

    async def _push_catalog(self, platform_id: str):
        """
        Push local device catalog to parent platform
        """
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(ParentPlatform).where(ParentPlatform.id == platform_id)
                result = await session.execute(stmt)
                p = result.scalars().first()
                if not p:
                    return

                scope_stmt = select(PlatformCatalogResource).where(PlatformCatalogResource.platform_id == platform_id)
                scope_result = await session.execute(scope_stmt)
                scope_mappings = {m.resource_id: m for m in scope_result.scalars().all()}
                scope_ids = list(scope_mappings.keys())

                stmt = select(Resource).where(Resource.tenant_id == (p.tenant_id or "default"))
                if scope_ids:
                    stmt = stmt.where(Resource.id.in_(scope_ids))
                # FIXED-P2: S-18 使用partitions分批加载，避免list()全量物化Resource表导致OOM
                result = await session.execute(stmt.execution_options(yield_per=500))
                resources = []
                for partition in result.scalars().partitions(500):
                    resources.extend(partition)
                if not resources:
                    await self._runtime_patch(p.tenant_id or "default", platform_id, {
                        "catalog.last_push_started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        "catalog.last_push_ok": True,
                        "catalog.last_push_error": "",
                        "catalog.scope_count": len(scope_ids),
                        "catalog.total_count": 0,
                        "catalog.batch_total": 0,
                        "catalog.batch_idx": 0,
                    })
                    return

                await self._runtime_patch(p.tenant_id or "default", platform_id, {
                    "catalog.last_push_started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "catalog.last_push_ok": False,
                    "catalog.last_push_error": "",
                    "catalog.scope_count": len(scope_ids),
                    "catalog.total_count": len(resources),
                    "catalog.batch_idx": 0,
                    "catalog.ack_ok_count": 0,
                    "catalog.ack_total": 0,
                })
                batch_size = getattr(p, "catalog_batch_size", None) or 0
                if batch_size <= 0:
                    batch_size = len(resources)
                batches = [resources[i:i + batch_size] for i in range(0, len(resources), batch_size)]
                await self._runtime_patch(p.tenant_id or "default", platform_id, {
                    "catalog.batch_total": len(batches),
                    "catalog.batch_size": int(batch_size),
                })
                self._catalog_ack_counter[(p.tenant_id or "default", platform_id)] = {"total": len(batches), "ok": 0, "last_status_code": None}

                # Push administrative divisions as catalog items before channel items
                try:
                    from app.models.region import Region
                    region_stmt = select(Region).where(Resource.tenant_id == (p.tenant_id or "default") if hasattr(Region, 'tenant_id') else True).order_by(Region.level.asc(), Region.code.asc())
                    region_result = await session.execute(region_stmt)
                    regions = region_result.scalars().all()
                    if regions:
                        region_items_xml = ""
                        for rg in regions:
                            region_parent = rg.parent_id or p.client_gb_id
                            # GB28181: 行政区划作为目录节点，Parental=1
                            region_items_xml += f"""<Item>
<DeviceID>{rg.code}</DeviceID>
<Name>{_xml_escape(rg.name or rg.code)}</Name>
<Manufacturer>PyGBSentry</Manufacturer>
<Model>Region</Model>
<Owner>Owner</Owner>
<CivilCode>{rg.code[:6]}</CivilCode>
<Parental>1</Parental>
<ParentID>{region_parent}</ParentID>
<SafetyWay>0</SafetyWay>
<RegisterWay>1</RegisterWay>
<Secrecy>0</Secrecy>
<Status>ON</Status>
</Item>
"""
                        region_sn = (int(time.time()) + 99990) % 100000
                        region_xml = f"""<?xml version="1.0" encoding="GB2312"?>
<Response>
<CmdType>Catalog</CmdType>
<SN>{region_sn}</SN>
<DeviceID>{p.client_gb_id}</DeviceID>
<SumNum>{len(regions)}</SumNum>
<DeviceList Num="{len(regions)}">
{region_items_xml}
</DeviceList>
</Response>
"""
                        region_req = SipMessage()
                        region_req.method = "MESSAGE"
                        region_req.uri = f"sip:{p.server_gb_id}@{p.server_ip}:{p.server_port}"
                        region_req.headers["Content-Type"] = "Application/MANSCDP+xml"
                        region_req.body = region_xml
                        req_proto = _platform_proto(p)
                        region_req.headers["Via"] = f"SIP/2.0/{req_proto} {settings.SIP_IP}:{settings.SIP_PORT};rport;branch=z9hG4bKcatrg{region_sn}"
                        region_req.headers["From"] = f"<sip:{p.client_gb_id}@{settings.SIP_DOMAIN}>;tag=catrg{region_sn}"
                        region_req.headers["To"] = f"<sip:{p.server_gb_id}@{settings.SIP_DOMAIN}>"
                        region_req.headers["Call-ID"] = f"cat_rg_{p.server_gb_id}@{settings.SIP_IP}"
                        region_req.headers["CSeq"] = f"{region_sn} MESSAGE"
                        _attach_trace_header(region_req)
                        try:
                            await self._send_sip_request_and_wait(
                                req=region_req, ip=p.server_ip, port=p.server_port,
                                proto=req_proto, timeout_seconds=2.2, retries=1,
                            )
                            logger.info(f"[PlatformService] Pushed {len(regions)} region items to platform {platform_id}")
                        except Exception as rg_err:
                            logger.warning(f"[PlatformService] Failed to push region items: {rg_err}")
                except ImportError:
                    logger.debug("Region model not available, skipping region catalog push")
                except Exception as e:
                    logger.warning(f"[PlatformService] Region catalog push error: {e}")

                for batch_idx, batch in enumerate(batches):
                    sn = (int(time.time()) + batch_idx) % 100000
                    items_xml = ""
                    for res in batch:
                        mapping = scope_mappings.get(res.id)

                        output_gb_id = res.gb_id
                        output_name = res.name or res.gb_id
                        output_parent_id = res.parent_gb_id or p.client_gb_id

                        if mapping:
                            if mapping.virtual_gb_id:
                                output_gb_id = mapping.virtual_gb_id
                            if mapping.virtual_name:
                                output_name = mapping.virtual_name
                            if mapping.virtual_parent_id:
                                output_parent_id = mapping.virtual_parent_id

                        civil = (res.civil_code or "340200")[:6]
                        is_dir = getattr(res, "node_type", "channel") == "directory"
                        parental = "1" if is_dir else "0"

                        items_xml += f"""<Item>
<DeviceID>{output_gb_id}</DeviceID>
<Name>{output_name}</Name>
<Manufacturer>PyGBSentry</Manufacturer>
<Model>AI-Sentry</Model>
<Owner>Owner</Owner>
<CivilCode>{civil}</CivilCode>
<Address>Address</Address>
<Parental>{parental}</Parental>
<ParentID>{output_parent_id}</ParentID>
<SafetyWay>0</SafetyWay>
<RegisterWay>1</RegisterWay>
<Secrecy>0</Secrecy>
<Status>{"ON" if res.status else "OFF"}</Status>
</Item>
"""
                    xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Response>
<CmdType>Catalog</CmdType>
<SN>{sn}</SN>
<DeviceID>{p.client_gb_id}</DeviceID>
<SumNum>{len(resources)}</SumNum>
<DeviceList Num="{len(batch)}">
{items_xml}
</DeviceList>
</Response>
"""
                    req = SipMessage()
                    req.method = "MESSAGE"
                    req.uri = f"sip:{p.server_gb_id}@{p.server_ip}:{p.server_port}"
                    req.headers["Content-Type"] = "Application/MANSCDP+xml"
                    req.body = xml_body
                    req_proto = _platform_proto(p)
                    req.headers["Via"] = f"SIP/2.0/{req_proto} {settings.SIP_IP}:{settings.SIP_PORT};rport;branch=z9hG4bKcat{sn}"
                    req.headers["From"] = f"<sip:{p.client_gb_id}@{settings.SIP_DOMAIN}>;tag=cat{sn}"
                    req.headers["To"] = f"<sip:{p.server_gb_id}@{settings.SIP_DOMAIN}>"
                    call_id = f"cat_{p.server_gb_id}_{batch_idx}@{settings.SIP_IP}"
                    req.headers["Call-ID"] = call_id
                    req.headers["CSeq"] = f"{sn} MESSAGE"
                    trace_id = _attach_trace_header(req)
                    self._catalog_states[call_id] = {
                        "platform_id": platform_id,
                        "tenant_id": p.tenant_id or "default",
                        "batch_idx": batch_idx + 1,
                        "batch_total": len(batches),
                    }
                    try:
                        resp, meta = await self._send_sip_request_and_wait(
                            req=req,
                            ip=p.server_ip,
                            port=p.server_port,
                            proto=req_proto,
                            timeout_seconds=2.2,
                            retries=2,
                        )
                        await self._runtime_patch(p.tenant_id or "default", platform_id, {
                            "catalog.last_batch_status_code": int(resp.status_code or 0),
                            "catalog.last_batch_rtt_ms": int(meta.get("rtt_ms") or 0),
                            "catalog.last_batch_attempts": int(meta.get("attempts") or 0),
                        })
                        if int(resp.status_code or 0) != 200:
                            await self._runtime_patch(p.tenant_id or "default", platform_id, {
                                "catalog.last_push_ok": False,
                                "catalog.last_push_error": f"catalog_batch_failed status={int(resp.status_code or 0)}",
                            })
                            break
                    except asyncio.TimeoutError as e:
                        await self._runtime_patch(p.tenant_id or "default", platform_id, {
                            "catalog.last_push_ok": False,
                            "catalog.last_push_error": f"catalog_batch_timeout: {e}",
                        })
                        break
                    await self._runtime_patch(p.tenant_id or "default", platform_id, {
                        "catalog.last_batch_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        "catalog.batch_idx": batch_idx + 1,
                        "catalog.last_batch_call_id": call_id,
                    })
                    logger.info(f"[trace_id={trace_id}] Sent platform catalog batch {batch_idx + 1}/{len(batches)} to {p.server_gb_id}")
                    _sip_trace_log(
                        "platform_catalog_sent",
                        trace_id=trace_id,
                        platform_id=platform_id,
                        server_gb_id=p.server_gb_id,
                        transport=req_proto,
                        batch_idx=batch_idx + 1,
                        batch_total=len(batches),
                        batch_size=len(batch),
                    )
                    if len(batches) > 1:
                        await asyncio.sleep(0.2)
                logger.info(f"Pushed catalog ({len(resources)} items in {len(batches)} batch/batches) to platform {p.name}")
                await self._runtime_patch(p.tenant_id or "default", platform_id, {
                    "catalog.last_push_finished_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "catalog.last_push_ok": True,
                    "catalog.last_push_error": "",
                })
        except Exception as e:
            try:
                async with AsyncSessionLocal() as session:
                    stmt = select(ParentPlatform).where(ParentPlatform.id == platform_id)
                    result = await session.execute(stmt)
                    p = result.scalars().first()
                tenant_id = (p.tenant_id if p else "default") or "default"
            except Exception:
                tenant_id = "default"
            await self._runtime_patch(tenant_id, platform_id, {
                "catalog.last_push_finished_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "catalog.last_push_ok": False,
                "catalog.last_push_error": f"push_catalog_failed {str(e)[:200]}",
            })
            _sip_trace_log(
                "platform_catalog_failed",
                trace_id=f"cat_{platform_id}",
                platform_id=platform_id,
                error=str(e)[:200],
            )

    async def push_catalog_incremental(self, tenant_id: str, platform_id: str, changed_resources: list) -> None:
        """
        FIXED: 级联增量目录同步 — 仅推送变更的通道条目，替代全量推送。
        当设备上下线时调用此方法，通过 SIP NOTIFY 推送增量变更给上级平台。
        """
        try:
            async with AsyncSessionLocal() as session:
                p = await get_or_404(session, ParentPlatform, platform_id)
                if not p.is_online or not p.catalog_subscribed:
                    return
                from app.core.config import settings, sip_host_for_contact
                from app.sip.send import send_sip_bytes
                from xml.sax.saxutils import escape as _xml_escape

                addr = (p.server_ip, p.server_port or 5060)
                proto = p.transport_protocol or "UDP"
                transport = sip_server.get_transport(addr[0], addr[1], proto) if sip_server else None
                if not transport:
                    return

                # 构建增量 Catalog Notify XML
                items_xml = ""
                for res in changed_resources:
                    res_gb_id = str(getattr(res, "gb_id", "") or "")
                    res_name = _xml_escape(str(getattr(res, "name", "") or ""))
                    res_status = "ON" if getattr(res, "status", 0) == 1 else "OFF"
                    res_parent = str(getattr(res, "parent_gb_id", "") or p.client_gb_id)
                    items_xml += f"<Item><DeviceID>{res_gb_id}</DeviceID><Name>{res_name}</Name>"
                    items_xml += f"<Status>{res_status}</Status><ParentID>{res_parent}</ParentID></Item>\n"

                sn = int(time.time() * 1000) % 100000
                xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Notify>
<CmdType>Catalog</CmdType>
<SN>{sn}</SN>
<DeviceID>{p.client_gb_id}</DeviceID>
<SumNum>{len(changed_resources)}</SumNum>
<DeviceList Num="{len(changed_resources)}">
{items_xml}</DeviceList>
</Notify>
"""
                sub_key = f"plat_{platform_id}"
                sub_state = self._reg_states.get(sub_key, {})
                cseq = sub_state.get("notify_cseq", 0) + 1
                sub_state["notify_cseq"] = cseq
                self._reg_states[sub_key] = sub_state

                branch = f"z9hG4bK{secrets.token_hex(6)}"
                req = SipMessage()
                req.method = "NOTIFY"
                req.uri = f"sip:{p.server_gb_id}@{addr[0]}:{addr[1]}"
                req.version = "SIP/2.0"
                req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
                req.headers["From"] = f"<sip:{p.client_gb_id}@{settings.SIP_DOMAIN}>;tag={sub_state.get('from_tag', 'pygb')}"
                req.headers["To"] = f"<sip:{p.server_gb_id}@{settings.SIP_DOMAIN}>;tag={sub_state.get('to_tag', '')}"
                req.headers["Call-ID"] = sub_state.get("catalog_call_id", f"cat_{p.server_gb_id}@{settings.SIP_IP}")
                req.headers["CSeq"] = f"{cseq} NOTIFY"
                req.headers["Contact"] = f"<sip:{p.client_gb_id}@{sip_host_for_contact()}:{settings.SIP_PORT}>"
                req.headers["Event"] = "Catalog"
                req.headers["Subscription-State"] = "active"
                req.headers["Content-Type"] = "Application/MANSCDP+xml"
                req.headers["Max-Forwards"] = "70"
                req.headers["User-Agent"] = settings.PROJECT_NAME
                req.body = xml_body

                await send_sip_bytes(proto, transport, addr, req.to_bytes())
                logger.info(f"[PlatformService] Sent incremental catalog NOTIFY to {p.server_gb_id} with {len(changed_resources)} items")

        except Exception as e:
            logger.error(f"[PlatformService] Incremental catalog push failed for {platform_id}: {e}")

    async def send_platform_time_sync(self, tenant_id: str, platform_id: str) -> None:
        """
        FIXED: 平台间时间同步 — 向上级平台发送TimeSync消息，
        确保级联平台间时间一致，避免录像查询时间范围偏差。
        """
        try:
            async with AsyncSessionLocal() as session:
                p = await get_or_404(session, ParentPlatform, platform_id)
                if not p.is_online:
                    return
                from app.core.config import settings, sip_host_for_contact
                from app.sip.send import send_sip_bytes
                from datetime import datetime, timezone, timedelta

                addr = (p.server_ip, p.server_port or 5060)
                proto = p.transport_protocol or "UDP"
                transport = sip_server.get_transport(addr[0], addr[1], proto) if sip_server else None
                if not transport:
                    return

                sn = int(time.time() * 1000) % 100000
                now = datetime.now(timezone(timedelta(hours=float(getattr(settings, "APP_TIMEZONE_OFFSET_HOURS", 8)))))  # FIXED-P2: W-17 使用配置项替代硬编码UTC+8
                time_str = now.strftime("%Y-%m-%dT%H:%M:%S")

                xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Notify>
<CmdType>TimeSync</CmdType>
<SN>{sn}</SN>
<DeviceID>{p.client_gb_id}</DeviceID>
<Time>{time_str}</Time>
</Notify>
"""
                sub_key = f"plat_{platform_id}"
                sub_state = self._reg_states.get(sub_key, {})
                cseq = sub_state.get("ts_cseq", 0) + 1
                sub_state["ts_cseq"] = cseq
                self._reg_states[sub_key] = sub_state

                branch = f"z9hG4bK{secrets.token_hex(6)}"
                req = SipMessage()
                req.method = "MESSAGE"
                req.uri = f"sip:{p.server_gb_id}@{addr[0]}:{addr[1]}"
                req.version = "SIP/2.0"
                req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
                req.headers["From"] = f"<sip:{p.client_gb_id}@{settings.SIP_DOMAIN}>;tag={sub_state.get('from_tag', 'pygb')}"
                req.headers["To"] = f"<sip:{p.server_gb_id}@{settings.SIP_DOMAIN}>"
                req.headers["Call-ID"] = sub_state.get("ts_call_id", f"ts_{p.server_gb_id}@{settings.SIP_IP}")
                req.headers["CSeq"] = f"{cseq} MESSAGE"
                req.headers["Content-Type"] = "Application/MANSCDP+xml"
                req.headers["Max-Forwards"] = "70"
                req.headers["User-Agent"] = settings.PROJECT_NAME
                req.body = xml_body

                await send_sip_bytes(proto, transport, addr, req.to_bytes())
                logger.info(f"[PlatformService] Sent TimeSync to {p.server_gb_id}, time={time_str}")

        except Exception as e:
            logger.error(f"[PlatformService] TimeSync failed for {platform_id}: {e}")

    async def _run_loop(self):
        while self.running:
            try:
                # FIXED-P4: W-16 定期清理过期的级联录像查询条目，防止内存泄漏
                self.prune_stale_cascade_record_queries()

                async with AsyncSessionLocal() as session:
                    stmt = select(ParentPlatform).where(ParentPlatform.enable == True)
                    result = await session.execute(stmt)
                    platforms = result.scalars().all()

                    for p in platforms:
                        call_id = f"reg_{p.server_gb_id}@{settings.SIP_IP}"
                        state = self._reg_states.get(call_id, {})
                        last_ok = state.get("last_ok_time", 0)

                        if not p.is_online or (time.time() - last_ok) >= max(30, (p.register_interval or 3600) * 0.9):
                            await self._runtime_patch(p.tenant_id or "default", p.id, {
                                "register.last_auto_attempt_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                            })
                            await self._register(p)

            except Exception as e:
                logger.error(f"Platform loop error: {e}")
            await asyncio.sleep(30)

    async def _register(self, p: ParentPlatform, auth_header: str = None, call_id: str = None, _auth_depth: int = 0):
        """
        Register this platform to parent platform with Digest Auth support
        # FIXED: S-04 added _auth_depth parameter to prevent infinite recursion on repeated 401
        """
        if _auth_depth > 3:
            logger.warning(f"[PlatformService] Register auth recursion depth exceeded for platform {p.server_gb_id}, giving up")
            return
        if not call_id:
            call_id = f"reg_{p.server_gb_id}@{settings.SIP_IP}"

        state = self._reg_states.get(call_id) or {"platform_id": p.id, "cseq": 0, "nc": 0}
        state["platform_id"] = p.id
        state["sent_mono"] = time.monotonic()
        if "from_tag" not in state:
            state["from_tag"] = secrets.token_hex(4)
        try:
            state["cseq"] = (int(state.get("cseq") or 0) + 1) & 0x7FFFFFFF
            if state["cseq"] == 0:
                state["cseq"] = 1
        except Exception:
            state["cseq"] = 1
        self._reg_states[call_id] = state
        await self._runtime_patch(p.tenant_id or "default", p.id, {
            "register.last_sent_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "register.last_call_id": call_id,
            "register.last_target": f"{p.server_ip}:{p.server_port}",
            "register.last_transport": _platform_proto(p),
            "register.last_has_auth": bool(auth_header),
        })

        req = SipMessage()
        req.method = "REGISTER"
        req.uri = f"sip:{p.server_gb_id}@{p.server_ip}:{p.server_port}"
        req_proto = _platform_proto(p)
        branch = f"z9hG4bK{secrets.token_hex(8)}"
        req.headers["Via"] = f"SIP/2.0/{req_proto} {settings.SIP_IP}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{p.client_gb_id}@{settings.SIP_DOMAIN}>;tag={state['from_tag']}"
        req.headers["To"] = f"<sip:{p.server_gb_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = call_id
        req.headers["CSeq"] = f"{int(state.get('cseq') or 1)} REGISTER"
        req.headers["Expires"] = str(p.register_interval)
        req.headers["Contact"] = f"<sip:{p.client_gb_id}@{settings.SIP_IP}:{settings.SIP_PORT}>"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME

        if auth_header:
            auth_params = DigestAuth.parse_auth_header(auth_header)
            qop_raw = (auth_params.get("qop") or "").strip()
            qop_tokens = [token.strip().lower() for token in qop_raw.split(",") if token.strip()]
            qop = "auth" if "auth" in qop_tokens else ""
            new_nonce = auth_params.get("nonce") or ""
            if new_nonce != state.get("last_nonce"):
                state["nc"] = 0
                state["last_nonce"] = new_nonce
            nc_val = int(state.get("nc") or 0) + 1
            state["nc"] = nc_val
            nc = f"{nc_val:08x}" if qop else None
            cnonce = secrets.token_hex(8) if qop else None  # FIXED-P2: W-07 random.choice→secrets
            algorithm = (auth_params.get("algorithm") or "MD5").upper()
            if algorithm in ("SHA-256", "SHA256"):
                algorithm = "SHA-256"
            else:
                algorithm = "MD5"
            response = DigestAuth.calculate_response(
                username=p.client_gb_id,
                password=p.password,
                realm=auth_params.get("realm"),
                method="REGISTER",
                uri=req.uri,
                nonce=auth_params.get("nonce"),
                nc=nc,
                cnonce=cnonce,
                qop=qop or None,
                algorithm=algorithm,
            )
            auth_parts = [
                f'username="{p.client_gb_id}"',
                f'realm="{auth_params.get("realm")}"',
                f'nonce="{auth_params.get("nonce")}"',
                f'uri="{req.uri}"',
                f'response="{response}"',
                f"algorithm={algorithm}",
            ]
            opaque = (auth_params.get("opaque") or "").strip()
            if opaque:
                auth_parts.append(f'opaque="{opaque}"')
            if qop:
                auth_parts.extend([f"qop={qop}", f"nc={nc}", f'cnonce="{cnonce}"'])
            req.headers["Authorization"] = "Digest " + ", ".join(auth_parts)

        trace_id = _attach_trace_header(req)
        logger.info(f"[trace_id={trace_id}] Sent platform REGISTER to {p.server_gb_id} (auth={'yes' if bool(auth_header) else 'no'})")
        _sip_trace_log(
            "platform_register_sent",
            trace_id=trace_id,
            platform_id=p.id,
            server_gb_id=p.server_gb_id,
            server_ip=p.server_ip,
            server_port=p.server_port,
            transport=req_proto,
            has_auth=bool(auth_header),
        )

        try:
            resp, meta = await self._send_sip_request_and_wait(
                req=req,
                ip=p.server_ip,
                port=p.server_port,
                proto=req_proto,
                timeout_seconds=2.2,
                retries=2,
            )
            await self._handle_register_response(resp, (p.server_ip, p.server_port), req_proto, call_id, p.id, state.get("sent_mono", 0.0))
        except asyncio.TimeoutError:
            rtt_ms = int((time.monotonic() - state.get("sent_mono", time.monotonic())) * 1000)
            await self._runtime_patch(p.tenant_id or "default", p.id, {
                "register.last_failed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "register.last_status_code": 408,
                "register.last_error": "register_timeout",
                "register.last_addr": f"{p.server_ip}:{p.server_port}",
                "register.last_transport": str(req_proto or ""),
                "register.last_rtt_ms": rtt_ms,
            })
            _sip_trace_log(
                "platform_register_timeout",
                trace_id=call_id,
                platform_id=p.id,
            )
        except Exception as e:
            logger.error(f"Error sending REGISTER to platform {p.server_gb_id}: {e}")

    async def _handle_register_response(self, message: SipMessage, addr: tuple, proto: str, call_id: str, platform_id: str, sent_mono: float):
        _sip_trace_log(
            "platform_response_received",
            trace_id=call_id,
            status_code=message.status_code,
            cseq=message.get_header("CSeq") or "",
            from_header=message.get_header("From") or "",
            to_header=message.get_header("To") or "",
            proto=proto,
            addr=str(addr),
        )

        if message.status_code == 401:
            auth_header = message.get_header("WWW-Authenticate")
            if not auth_header:
                return

            state = self._reg_states.get(call_id)
            if state:
                auth_retry_count = int(state.get("auth_retry_count") or 0) + 1
                state["auth_retry_count"] = auth_retry_count
                if auth_retry_count > 3:
                    logger.warning(f"[PlatformService] Too many 401 auth challenges for platform_id={platform_id}, giving up")
                    return
            else:
                return

            async with AsyncSessionLocal() as session:
                stmt = select(ParentPlatform).where(ParentPlatform.id == platform_id)
                result = await session.execute(stmt)
                p = result.scalars().first()
                if p:
                    rtt_ms = int((time.monotonic() - sent_mono) * 1000) if sent_mono > 0 else 0
                    await self._runtime_patch(p.tenant_id or "default", platform_id, {
                        "register.last_challenge_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        "register.last_status_code": 401,
                        "register.last_www_auth": (auth_header or "")[:256],
                        "register.last_addr": str(addr),
                        "register.last_transport": str(proto or ""),
                        "register.last_rtt_ms": rtt_ms,
                    })
                    await self._register(p, auth_header=auth_header, call_id=call_id, _auth_depth=_auth_depth + 1)  # FIXED: S-04 pass depth counter

        elif message.status_code == 200:
            # Registration Success
            state = self._reg_states.get(call_id)
            if state:
                state["last_ok_time"] = time.time()

            async with AsyncSessionLocal() as session:
                stmt = update(ParentPlatform).where(ParentPlatform.id == platform_id).values(
                    is_online=True,
                    last_keepalive=datetime.datetime.now(datetime.timezone.utc)
                )
                await session.execute(stmt)
                await session.commit()
            async with AsyncSessionLocal() as session:
                p_result = await session.execute(select(ParentPlatform).where(ParentPlatform.id == platform_id))
                p = p_result.scalars().first()
            if p:
                rtt_ms = int((time.monotonic() - sent_mono) * 1000) if sent_mono > 0 else 0
                await self._runtime_patch(p.tenant_id or "default", platform_id, {
                    "register.last_ok_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "register.last_status_code": 200,
                    "register.last_addr": str(addr),
                    "register.last_transport": str(proto or ""),
                    "register.last_rtt_ms": rtt_ms,
                })
            logger.info(f"Successfully registered to parent platform {platform_id}")

            # Start Keepalive & Catalog Push
            _safe_create_task(self._start_session_tasks(platform_id))
        else:
            async with AsyncSessionLocal() as session:
                p_result = await session.execute(select(ParentPlatform).where(ParentPlatform.id == platform_id))
                p = p_result.scalars().first()
            if p:
                rtt_ms = int((time.monotonic() - sent_mono) * 1000) if sent_mono > 0 else 0
                await self._runtime_patch(p.tenant_id or "default", platform_id, {
                    "register.last_failed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "register.last_status_code": int(message.status_code or 0),
                    "register.last_error": f"register_failed status={int(message.status_code or 0)}",
                    "register.last_addr": str(addr),
                    "register.last_transport": str(proto or ""),
                    "register.last_rtt_ms": rtt_ms,
                })
            _sip_trace_log(
                "platform_register_failed",
                trace_id=call_id,
                platform_id=platform_id,
                status_code=int(message.status_code or 0),
            )

    async def _send_sip_request(self, req: SipMessage, ip: str, port: int, proto: str):
        data = req.to_bytes()
        protocol = (proto or "UDP").upper()
        if protocol == "TCP":
            writer = self.sip_server.get_transport(ip, port, "TCP")
            if writer:
                try:
                    writer.write(data)
                    await writer.drain()
                    return
                except Exception as e:
                    logger.warning(f"TCP send failed via sip_server transport to {ip}:{port}: {e}")
            key = (ip, port)
            writer = self._outbound_tcp.get(key)
            if writer is None or writer.is_closing():
                if writer:
                    with contextlib.suppress(Exception):
                        writer.close()
                    self._outbound_tcp.pop(key, None)
                try:
                    _, writer = await asyncio.open_connection(ip, port)
                    self._outbound_tcp[key] = writer
                except Exception as e:
                    logger.warning(f"TCP connect failed for {ip}:{port}: {e}")
                    self._outbound_tcp.pop(key, None)
                    return
            try:
                writer.write(data)
                await writer.drain()
            except Exception as e:
                logger.warning(f"TCP send failed to {ip}:{port}: {e}")
                with contextlib.suppress(Exception):
                    writer.close()
                self._outbound_tcp.pop(key, None)
            return
        if self.sip_server.udp_transport:
            self.sip_server.udp_transport.sendto(data, (ip, port))

    async def _send_sip_request_and_wait(
        self,
        *,
        req: SipMessage,
        ip: str,
        port: int,
        proto: str,
        timeout_seconds: float,
        retries: int,
    ) -> tuple[SipMessage, dict]:
        from app.sip.transactions import tx_manager

        async def _send_once():
            await self._send_sip_request(req, ip, port, proto)

        resp, meta = await tx_manager.send_and_wait(
            request=req,
            send_once=_send_once,
            timeout_seconds=float(timeout_seconds),
            retries=int(retries or 0),
        )
        return resp, meta

    async def _send_sip_message(self, proto: str, addr: tuple, msg: SipMessage) -> None:
        """Send a SIP message (request or response) via the appropriate transport."""
        transport = self.sip_server.get_transport(addr[0], addr[1], proto)
        if not transport:
            logger.warning(f"[PlatformService] Transport not available for {addr[0]}:{addr[1]}/{proto}")
            return
        await send_sip_bytes(proto, transport, addr, msg.to_bytes())

    async def send_invite_response(self, platform: ParentPlatform, request: SipMessage, sdp_ip: str, sdp_port: int, ssrc: str, is_tcp: bool = False) -> None:
        """Respond to a cascade INVITE from a parent platform with 200 OK + SDP."""
        addr = (platform.server_ip, platform.server_port)
        proto = _platform_proto(platform)
        device_id = platform.client_gb_id or ""
        channel_id = request.uri.split("sip:")[1].split("@")[0] if "sip:" in request.uri else device_id
        resp = SipMessage()
        resp.method = ""
        resp.status_code = 200
        resp.reason_phrase = "OK"
        resp.version = "SIP/2.0"
        resp.headers["Via"] = request.headers.get("Via", "")
        resp.headers["From"] = request.headers.get("From", "")
        to_header = request.headers.get("To", "")
        if "tag=" not in to_header:
            to_header += f";tag={secrets.token_hex(4)}"
        resp.headers["To"] = to_header
        resp.headers["Call-ID"] = request.headers.get("Call-ID", "")
        resp.headers["CSeq"] = request.headers.get("CSeq", "")
        resp.headers["Contact"] = f"<sip:{device_id}@{sip_host_for_contact()}:{settings.SIP_PORT}>"
        resp.headers["Content-Type"] = "Application/SDP"
        resp.headers["User-Agent"] = settings.PROJECT_NAME
        t_line = "0 0"
        session_name = "Play"
        req_sdp = request.body
        if req_sdp and "s=Playback" in req_sdp:
            session_name = "Playback"
            for line in req_sdp.splitlines():
                if line.startswith("t="):
                    t_line = line[2:]
                    break
        media_proto = "TCP/RTP/AVP" if is_tcp else "RTP/AVP"
        setup_val = "active" if is_tcp else None
        sdp = _build_sdp(origin_id=channel_id, session_name=session_name, connection_ip=sdp_ip, media_type="video", media_port=sdp_port, media_profile=media_proto, direction="sendonly", ssrc=ssrc, setup=setup_val, time_range=t_line, extended_rtpmap=True)
        resp.body = sdp
        await self._send_sip_message(proto, addr, resp)
        logger.info(f"[PlatformService] Sent 200 OK (INVITE) to {platform.server_gb_id}, port={sdp_port}")

    async def send_alarm_notify(self, platform: ParentPlatform, device_id: str, channel_id: str, alarm_type: str, priority: str, description: str, alarm_time_iso: str) -> None:
        """Send an alarm notification to a parent platform."""
        # FIXED-P2: W-16 检查上级平台是否订阅了Alarm事件，未订阅则跳过
        try:
            from app.models.platform_subscription import PlatformSubscription
            from sqlalchemy import select as _sel
            async with AsyncSessionLocal() as _chk_session:
                _sub = (await _chk_session.execute(
                    _sel(PlatformSubscription).where(
                        PlatformSubscription.platform_id == platform.id,
                        PlatformSubscription.event_type == "Alarm",
                        PlatformSubscription.expires_at > datetime.datetime.now(datetime.timezone.utc),
                    )
                )).scalars().first()
                if not _sub:
                    logger.debug(f"[PlatformService] Platform {platform.server_gb_id} has no active Alarm subscription, skipping notify")
                    return
        except Exception as _chk_err:
            logger.debug(f"Alarm subscription check failed: {_chk_err}")
        addr = (platform.server_ip, platform.server_port)
        proto = _platform_proto(platform)
        local_device_id = platform.client_gb_id or ""
        domain = platform.server_ip or ""
        sn = secrets.randbelow(900000) + 100000  # FIXED-P2: W-10 random.randint→secrets
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Notify>
<CmdType>Alarm</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(local_device_id)}</DeviceID>
<AlarmPriority>{_xml_escape(priority or "4")}</AlarmPriority>
<AlarmMethod>5</AlarmMethod>
<AlarmTime>{_xml_escape(alarm_time_iso)}</AlarmTime>
</Notify>
"""
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{platform.server_gb_id}@{domain}"
        req.version = "SIP/2.0"
        branch = f"z9hG4bK{secrets.token_hex(6)}"
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{local_device_id}@{domain}>;tag={secrets.token_hex(4)}"
        req.headers["To"] = f"<sip:{platform.server_gb_id}@{domain}>"
        req.headers["Call-ID"] = f"{sn}alarm@{sip_host_for_contact()}"
        req.headers["CSeq"] = f"{sn} MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        req.body = xml_body
        await self._send_sip_message(proto, addr, req)
        logger.info(f"[PlatformService] Sent Alarm notify to {platform.server_gb_id}: device={local_device_id} priority={priority} type={alarm_type}")

    async def send_catalog_response(self, platform: ParentPlatform, sn: str, channels: list, from_tag: str) -> None:
        """Send a Catalog query response (MESSAGE) to a parent platform."""
        addr = (platform.server_ip, platform.server_port)
        proto = _platform_proto(platform)
        domain = platform.server_ip or ""
        device_id = platform.client_gb_id or ""
        device_list_xml = ""
        for ch in channels:
            ch_gb_id = getattr(ch, "gb_id", "") or ""
            ch_name = getattr(ch, "name", None) or ch_gb_id
            ch_manufacturer = getattr(ch, "manufacturer", None) or "PyGBSentry"
            ch_model = getattr(ch, "model", None) or "Camera"
            ch_owner = getattr(ch, "owner", None) or "Owner"
            ch_civil_code = getattr(ch, "civil_code", None) or ""
            ch_address = getattr(ch, "address", None) or "Address"
            ch_node_type = getattr(ch, "node_type", "channel")
            ch_parent_gb_id = getattr(ch, "parent_gb_id", None) or device_id
            ch_status = getattr(ch, "status", 0)
            device_list_xml += f"""<Item>
<DeviceID>{_xml_escape(ch_gb_id)}</DeviceID>
<Name>{_xml_escape(ch_name)}</Name>
<Manufacturer>{_xml_escape(ch_manufacturer)}</Manufacturer>
<Model>{_xml_escape(ch_model)}</Model>
<Owner>{_xml_escape(ch_owner)}</Owner>
<CivilCode>{_xml_escape(ch_civil_code)}</CivilCode>
<Address>{_xml_escape(ch_address)}</Address>
<Parental>{1 if ch_node_type == 'directory' else 0}</Parental>
<ParentID>{_xml_escape(ch_parent_gb_id)}</ParentID>
<SafetyWay>0</SafetyWay>
<RegisterWay>1</RegisterWay>
<Secrecy>0</Secrecy>
<Status>{"ON" if ch_status == 1 else "OFF"}</Status>
</Item>
"""
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Response>
<CmdType>Catalog</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(device_id)}</DeviceID>
<SumNum>{len(channels)}</SumNum>
<DeviceList Num="{len(channels)}">
{device_list_xml}
</DeviceList>
</Response>
"""
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{platform.server_gb_id}@{domain}"
        req.version = "SIP/2.0"
        branch = f"z9hG4bK{secrets.token_hex(6)}"
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{device_id}@{domain}>;tag={secrets.token_hex(4)}"
        to_header = f"<sip:{platform.server_gb_id}@{domain}>;tag={from_tag}" if from_tag else f"<sip:{platform.server_gb_id}@{domain}>"
        req.headers["To"] = to_header
        req.headers["Call-ID"] = f"{sn}catalog@{sip_host_for_contact()}"
        req.headers["CSeq"] = f"{sn} MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        req.body = xml_body
        await self._send_sip_message(proto, addr, req)
        logger.info(f"[PlatformService] Sent Catalog Response to {platform.server_gb_id}, items: {len(channels)}")

    async def send_catalog_notify(self, platform: ParentPlatform, channels: list, status: str = "ON") -> None:
        """Send a Catalog NOTIFY (incremental update) to a parent platform based on active subscription."""
        addr = (platform.server_ip, platform.server_port)
        proto = _platform_proto(platform)
        domain = platform.server_ip or ""
        device_id = platform.client_gb_id or ""
        sn = secrets.randbelow(900000) + 100000  # FIXED-P2: W-10 random.randint→secrets
        sub_call_id = ""
        sub_from_tag = ""
        sub_to_tag = ""
        sub_cseq = 1
        sub_obj = None
        try:
            from app.models.platform_subscription import PlatformSubscription
            async with AsyncSessionLocal() as session:
                sub_result = await session.execute(select(PlatformSubscription).where(PlatformSubscription.platform_id == platform.id, PlatformSubscription.event == "catalog", PlatformSubscription.expires_seconds > 0).order_by(PlatformSubscription.id.desc()))
                sub_obj = sub_result.scalars().first()
                if sub_obj:
                    sub_call_id = str(getattr(sub_obj, "last_call_id", "") or "")
                    sub_from_tag = str(getattr(sub_obj, "local_to_tag", "") or "")
                    sub_to_tag = str(getattr(sub_obj, "remote_from_tag", "") or "")
                    sub_cseq = int(getattr(sub_obj, "notify_cseq", 0) or 0) + 1
        except Exception as e:
            logger.debug(f"[PlatformService] Failed to load subscription dialog info: {e}")
        if not sub_call_id:
            logger.warning(f"[PlatformService] No active catalog subscription for {platform.server_gb_id}, skipping NOTIFY")
            return
        device_list_xml = ""
        for ch in channels:
            ch_gb_id = getattr(ch, "gb_id", "") or ""
            ch_name = getattr(ch, "name", None) or ch_gb_id
            ch_manufacturer = getattr(ch, "manufacturer", None) or "PyGBSentry"
            ch_model = getattr(ch, "model", None) or "Camera"
            ch_owner = getattr(ch, "owner", None) or "Owner"
            ch_civil_code = getattr(ch, "civil_code", None) or ""
            ch_address = getattr(ch, "address", None) or "Address"
            ch_node_type = getattr(ch, "node_type", "channel")
            ch_parent_gb_id = getattr(ch, "parent_gb_id", None) or device_id
            ch_status = getattr(ch, "status", 0)
            device_list_xml += f"""<Item>
<DeviceID>{_xml_escape(ch_gb_id)}</DeviceID>
<Name>{_xml_escape(ch_name)}</Name>
<Manufacturer>{_xml_escape(ch_manufacturer)}</Manufacturer>
<Model>{_xml_escape(ch_model)}</Model>
<Owner>{_xml_escape(ch_owner)}</Owner>
<CivilCode>{_xml_escape(ch_civil_code)}</CivilCode>
<Address>{_xml_escape(ch_address)}</Address>
<Parental>{1 if ch_node_type == 'directory' else 0}</Parental>
<ParentID>{_xml_escape(ch_parent_gb_id)}</ParentID>
<SafetyWay>0</SafetyWay>
<RegisterWay>1</RegisterWay>
<Secrecy>0</Secrecy>
<Event>{"ON" if status == "ON" else "OFF"}</Event>
</Item>
"""
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Notify>
<CmdType>Catalog</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(device_id)}</DeviceID>
<SumNum>{len(channels)}</SumNum>
<DeviceList Num="{len(channels)}">
{device_list_xml}
</DeviceList>
</Notify>
"""
        req = SipMessage()
        req.method = "NOTIFY"
        req.uri = f"sip:{platform.server_gb_id}@{domain}"
        req.version = "SIP/2.0"
        branch = f"z9hG4bK{secrets.token_hex(6)}"
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{device_id}@{domain}>;tag={sub_from_tag or secrets.token_hex(4)}"
        req.headers["To"] = f"<sip:{platform.server_gb_id}@{domain}>;tag={sub_to_tag}" if sub_to_tag else f"<sip:{platform.server_gb_id}@{domain}>"
        req.headers["Call-ID"] = sub_call_id
        req.headers["CSeq"] = f"{sub_cseq} NOTIFY"
        req.headers["Event"] = "catalog"
        req.headers["Subscription-State"] = "active"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        req.body = xml_body
        await self._send_sip_message(proto, addr, req)
        if sub_call_id and sub_obj:
            try:
                async with AsyncSessionLocal() as session:
                    from app.models.platform_subscription import PlatformSubscription
                    db_sub = (await session.execute(select(PlatformSubscription).where(PlatformSubscription.id == sub_obj.id))).scalars().first()
                    if db_sub:
                        db_sub.notify_cseq = sub_cseq
                        await session.commit()
            except Exception as e:
                logger.debug(f"[PlatformService] Failed to update subscription CSeq: {e}")
        logger.info(f"[PlatformService] Sent Catalog NOTIFY (Event: {status}) to {platform.server_gb_id}, items: {len(channels)}")

    async def forward_cascade_device_control(self, channel_id: str, ptz_cmd_xml: str, sn: str) -> bool:
        """Forward a DeviceControl (PTZ) command from upstream platform to the real device."""
        from app.models.resource import Resource
        from app.models.asset import Asset
        from app.sip.server import sip_server as _sip_server
        real_gb_id = channel_id
        resource_id = None
        asset_id = None
        async with AsyncSessionLocal() as session:
            mapping = (await session.execute(select(PlatformCatalogResource).where(PlatformCatalogResource.virtual_gb_id == channel_id))).scalars().first()
            if mapping:
                mapped_resource = (await session.execute(select(Resource).where(Resource.id == mapping.resource_id))).scalars().first()
                if mapped_resource:
                    real_gb_id = mapped_resource.gb_id
                    resource_id = mapped_resource.id
                    asset_id = mapped_resource.asset_id
            if not resource_id:
                res = (await session.execute(select(Resource).where(Resource.gb_id == channel_id))).scalars().first()
                if res:
                    real_gb_id = res.gb_id
                    resource_id = res.id
                    asset_id = res.asset_id
            if not asset_id:
                logger.warning(f"[PlatformService] Cannot forward DeviceControl: no asset for channel {channel_id}")
                return False
            asset = (await session.execute(select(Asset).where(Asset.id == asset_id))).scalars().first()
            if not asset:
                logger.warning(f"[PlatformService] Cannot forward DeviceControl: asset {asset_id} not found")
                return False
            device_gb_id = asset.gb_id
            device_ip = getattr(asset, "ip", None) or ""
            device_port = getattr(asset, "port", None) or 5060
            device_proto = getattr(asset, "transport", None) or "UDP"
            if not device_ip:
                logger.warning(f"[PlatformService] Cannot forward DeviceControl: device {device_gb_id} has no IP")
                return False
        transport = _sip_server.get_transport(device_ip, device_port, device_proto)
        if not transport:
            logger.warning(f"[PlatformService] Cannot forward DeviceControl: no transport to {device_ip}:{device_port}/{device_proto}")
            return False
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Control>
<CmdType>DeviceControl</CmdType>
<SN>{sn}</SN>
<DeviceID>{_xml_escape(real_gb_id)}</DeviceID>
{ptz_cmd_xml}
</Control>
"""
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{device_gb_id}@{device_ip}:{device_port}"
        req.version = "SIP/2.0"
        branch = f"z9hG4bK{secrets.token_hex(6)}"
        req.headers["Via"] = f"SIP/2.0/{device_proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={secrets.token_hex(4)}"
        req.headers["To"] = f"<sip:{device_gb_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = f"{sn}devctrl@{sip_host_for_contact()}"
        req.headers["CSeq"] = f"{sn} MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        req.body = xml_body
        await self._send_sip_message(device_proto, (device_ip, device_port), req)
        logger.info(f"[PlatformService] Forwarded DeviceControl to device {device_gb_id}, channel={real_gb_id}")
        return True

    async def forward_cascade_config_download(self, channel_id: str, config_type: str, sn: str) -> bool:
        """Forward a ConfigDownload query from upstream platform to the real device."""
        from app.models.resource import Resource
        from app.models.asset import Asset
        from app.sip.server import sip_server as _sip_server
        real_gb_id = channel_id
        asset_id = None
        async with AsyncSessionLocal() as session:
            mapping = (await session.execute(select(PlatformCatalogResource).where(PlatformCatalogResource.virtual_gb_id == channel_id))).scalars().first()
            if mapping:
                mapped_resource = (await session.execute(select(Resource).where(Resource.id == mapping.resource_id))).scalars().first()
                if mapped_resource:
                    real_gb_id = mapped_resource.gb_id
                    asset_id = mapped_resource.asset_id
            if not asset_id:
                res = (await session.execute(select(Resource).where(Resource.gb_id == channel_id))).scalars().first()
                if res:
                    real_gb_id = res.gb_id
                    asset_id = res.asset_id
            if not asset_id:
                logger.warning(f"[PlatformService] Cannot forward ConfigDownload: no asset for channel {channel_id}")
                return False
            asset = (await session.execute(select(Asset).where(Asset.id == asset_id))).scalars().first()
            if not asset:
                logger.warning(f"[PlatformService] Cannot forward ConfigDownload: asset {asset_id} not found")
                return False
            device_gb_id = asset.gb_id
            device_ip = getattr(asset, "ip", None) or getattr(asset, "ip_addr", None) or ""
            device_port = getattr(asset, "port", None) or 5060
            device_proto = getattr(asset, "transport", None) or "UDP"
            if not device_ip:
                logger.warning(f"[PlatformService] Cannot forward ConfigDownload: device {device_gb_id} has no IP")
                return False
        local_sn = secrets.randbelow(900000) + 100000
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Query>
<CmdType>ConfigDownload</CmdType>
<SN>{local_sn}</SN>
<DeviceID>{_xml_escape(real_gb_id)}</DeviceID>
<ConfigType>{_xml_escape(config_type or 'BasicParam')}</ConfigType>
</Query>
"""
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{device_gb_id}@{device_ip}:{device_port}"
        req.version = "SIP/2.0"
        branch = f"z9hG4bK{secrets.token_hex(6)}"
        req.headers["Via"] = f"SIP/2.0/{device_proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={secrets.token_hex(4)}"
        req.headers["To"] = f"<sip:{device_gb_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = f"{local_sn}cfgdl@{sip_host_for_contact()}"
        req.headers["CSeq"] = f"{local_sn} MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        req.body = xml_body
        await self._send_sip_message(device_proto, (device_ip, device_port), req)
        logger.info(f"[PlatformService] Forwarded ConfigDownload to device {device_gb_id}, channel={real_gb_id}, type={config_type}")
        return True

    async def forward_cascade_record_query(self, platform: ParentPlatform, channel_id: str, start_time: str, end_time: str, query_type: str, sn: str) -> bool:
        """Forward a RecordInfo query from upstream platform to the real device."""
        from app.models.resource import Resource
        from app.models.asset import Asset
        from app.sip.server import sip_server as _sip_server
        real_gb_id = channel_id
        resource_id = None
        asset_id = None
        async with AsyncSessionLocal() as session:
            mapping = (await session.execute(select(PlatformCatalogResource).where(PlatformCatalogResource.virtual_gb_id == channel_id))).scalars().first()
            if mapping:
                mapped_resource = (await session.execute(select(Resource).where(Resource.id == mapping.resource_id))).scalars().first()
                if mapped_resource:
                    real_gb_id = mapped_resource.gb_id
                    resource_id = mapped_resource.id
                    asset_id = mapped_resource.asset_id
            if not resource_id:
                res = (await session.execute(select(Resource).where(Resource.gb_id == channel_id))).scalars().first()
                if res:
                    real_gb_id = res.gb_id
                    resource_id = res.id
                    asset_id = res.asset_id
            if not asset_id:
                logger.warning(f"[PlatformService] Cannot forward RecordInfo query: no asset for channel {channel_id}")
                return False
            asset = (await session.execute(select(Asset).where(Asset.id == asset_id))).scalars().first()
            if not asset:
                logger.warning(f"[PlatformService] Cannot forward RecordInfo query: asset {asset_id} not found")
                return False
            device_gb_id = asset.gb_id
            device_ip = getattr(asset, "ip", None) or getattr(asset, "ip_addr", None) or ""
            device_port = getattr(asset, "port", None) or 5060
            device_proto = getattr(asset, "transport", None) or "UDP"
            if not device_ip:
                logger.warning(f"[PlatformService] Cannot forward RecordInfo query: device {device_gb_id} has no IP")
                return False
        local_sn = random.randint(100000, 999999)
        xml_body = f"""<?xml version="1.0" encoding="GB2312"?>
<Query>
<CmdType>RecordInfo</CmdType>
<SN>{local_sn}</SN>
<DeviceID>{_xml_escape(real_gb_id)}</DeviceID>
<StartTime>{_xml_escape(start_time)}</StartTime>
<EndTime>{_xml_escape(end_time)}</EndTime>
<Type>{_xml_escape(query_type or 'all')}</Type>
</Query>
"""
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{device_gb_id}@{device_ip}:{device_port}"
        req.version = "SIP/2.0"
        branch = f"z9hG4bK{secrets.token_hex(6)}"
        req.headers["Via"] = f"SIP/2.0/{device_proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{settings.SIP_ID}@{settings.SIP_DOMAIN}>;tag={secrets.token_hex(4)}"
        req.headers["To"] = f"<sip:{device_gb_id}@{settings.SIP_DOMAIN}>"
        req.headers["Call-ID"] = f"{local_sn}recq@{sip_host_for_contact()}"
        req.headers["CSeq"] = f"{local_sn} MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        req.body = xml_body
        await self._send_sip_message(device_proto, (device_ip, device_port), req)
        self._cascade_record_queries[local_sn] = {"platform_id": str(platform.id), "server_gb_id": platform.server_gb_id, "original_sn": sn, "original_channel_id": channel_id, "real_channel_id": real_gb_id, "created_at": time.monotonic()}
        logger.info(f"[PlatformService] Forwarded RecordInfo query to device {device_gb_id}, channel={real_gb_id}, local_sn={local_sn}, original_sn={sn}")
        return True

    async def forward_cascade_record_response(self, local_sn: int, xml_body: str) -> None:
        """Forward a RecordInfo response from a device back to the upstream platform."""
        query_info = self._cascade_record_queries.pop(local_sn, None)
        if not query_info:
            return
        from app.core.xml_utils import parse_xml, get_xml_text
        root = parse_xml(xml_body)
        if root is None:
            return
        platform_id = query_info["platform_id"]
        server_gb_id = query_info["server_gb_id"]
        original_sn = query_info["original_sn"]
        original_channel_id = query_info["original_channel_id"]
        async with AsyncSessionLocal() as session:
            platform = (await session.execute(select(ParentPlatform).where(ParentPlatform.id == int(platform_id)))).scalars().first()
            if not platform:
                logger.warning(f"[PlatformService] Cannot forward RecordInfo response: platform {platform_id} not found")
                return
        addr = (platform.server_ip, platform.server_port)
        proto = _platform_proto(platform)
        domain = platform.server_ip or ""
        device_id = platform.client_gb_id or ""
        sum_num = get_xml_text(root, "SumNum") or "0"
        record_list_xml = ""
        record_items = root.findall(".//Item") if root is not None else []
        for item in record_items:
            item_device_id = get_xml_text(item, "DeviceID") or ""
            item_name = get_xml_text(item, "Name") or ""
            item_file_path = get_xml_text(item, "FilePath") or ""
            item_start = get_xml_text(item, "StartTime") or ""
            item_end = get_xml_text(item, "EndTime") or ""
            record_list_xml += f"""<Item>
<DeviceID>{_xml_escape(item_device_id)}</DeviceID>
<Name>{_xml_escape(item_name)}</Name>
<FilePath>{_xml_escape(item_file_path)}</FilePath>
<StartTime>{_xml_escape(item_start)}</StartTime>
<EndTime>{_xml_escape(item_end)}</EndTime>
</Item>
"""
        response_sn = random.randint(100000, 999999)
        xml_response = f"""<?xml version="1.0" encoding="GB2312"?>
<Response>
<CmdType>RecordInfo</CmdType>
<SN>{original_sn}</SN>
<DeviceID>{_xml_escape(original_channel_id)}</DeviceID>
<SumNum>{sum_num}</SumNum>
<RecordList Num="{len(record_items)}">
{record_list_xml}
</RecordList>
</Response>
"""
        req = SipMessage()
        req.method = "MESSAGE"
        req.uri = f"sip:{server_gb_id}@{domain}"
        req.version = "SIP/2.0"
        branch = f"z9hG4bK{secrets.token_hex(6)}"
        req.headers["Via"] = f"SIP/2.0/{proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={branch}"
        req.headers["From"] = f"<sip:{device_id}@{domain}>;tag={secrets.token_hex(4)}"
        req.headers["To"] = f"<sip:{server_gb_id}@{domain}>"
        req.headers["Call-ID"] = f"{response_sn}recresp@{sip_host_for_contact()}"
        req.headers["CSeq"] = f"{response_sn} MESSAGE"
        req.headers["Content-Type"] = "Application/MANSCDP+xml"
        req.headers["Max-Forwards"] = "70"
        req.headers["User-Agent"] = settings.PROJECT_NAME
        req.body = xml_response
        await self._send_sip_message(proto, addr, req)
        logger.info(f"[PlatformService] Forwarded RecordInfo response to {server_gb_id}, items={len(record_items)}, original_sn={original_sn}")

    def prune_stale_cascade_record_queries(self, max_age_seconds: int = 300) -> None:
        """Remove stale cascade record query entries older than max_age_seconds."""
        now = time.monotonic()
        stale_keys = [k for k, v in self._cascade_record_queries.items() if now - v.get("created_at", 0) > max_age_seconds]
        for k in stale_keys:
            self._cascade_record_queries.pop(k, None)
        if stale_keys:
            logger.debug(f"[PlatformService] Pruned {len(stale_keys)} stale cascade record queries")

# Singleton
platform_service = None