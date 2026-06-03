from __future__ import annotations

import asyncio
import contextlib
from loguru import logger
import time
from dataclasses import dataclass
from typing import Any

from app.sip.message import SipMessage
from app.core.config import settings
from app.sip.send import send_sip_bytes


@dataclass
class InviteContext:
    call_id: str
    message: SipMessage
    addr: tuple
    proto: str
    transport: Any
    created_mono: float
    cancelled: bool = False
    acked: bool = False
    final_response: SipMessage | None = None
    retransmit_task: asyncio.Task | None = None
    retransmit_count: int = 0


class InviteServerState:
    def __init__(self):
        self._items: dict[str, InviteContext] = {}
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._running = False
        self.ttl_seconds = 300.0
        self.prune_interval_seconds = 15.0
        self._sender = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._prune_loop())

    def set_sender(self, sender) -> None:
        self._sender = sender

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        self._task = None
        async with self._lock:
            for ctx in self._items.values():
                if ctx.retransmit_task:
                    ctx.retransmit_task.cancel()
            self._items.clear()

    async def put(self, call_id: str, message: SipMessage, addr: tuple, proto: str, transport) -> None:
        cid = (call_id or "").strip()
        if not cid:
            return
        ctx = InviteContext(
            call_id=cid,
            message=message,
            addr=addr,
            proto=proto,
            transport=transport,
            created_mono=time.monotonic(),
            cancelled=False,
        )
        async with self._lock:
            old_ctx = self._items.get(cid)
            if old_ctx and old_ctx.retransmit_task and not old_ctx.retransmit_task.done():
                old_ctx.retransmit_task.cancel()
            self._items[cid] = ctx

    async def mark_cancelled(self, call_id: str) -> InviteContext | None:
        cid = (call_id or "").strip()
        if not cid:
            return None
        async with self._lock:
            ctx = self._items.get(cid)
            if not ctx:
                return None
            # RFC 3261 Section 9.2 — 2xx已发送后CANCEL不影响事务，重传必须继续
            if ctx.final_response is not None:
                return ctx
            ctx.cancelled = True
            if ctx.retransmit_task:
                ctx.retransmit_task.cancel()
            return ctx

    async def is_cancelled(self, call_id: str) -> bool:
        cid = (call_id or "").strip()
        if not cid:
            return False
        async with self._lock:
            ctx = self._items.get(cid)
            return bool(ctx and ctx.cancelled)

    async def pop(self, call_id: str) -> InviteContext | None:
        cid = (call_id or "").strip()
        if not cid:
            return None
        async with self._lock:
            ctx = self._items.pop(cid, None)
            if ctx and ctx.retransmit_task:
                ctx.retransmit_task.cancel()
            return ctx

    async def mark_acked(self, call_id: str) -> bool:
        cid = (call_id or "").strip()
        if not cid:
            return False
        async with self._lock:
            ctx = self._items.get(cid)
            if not ctx:
                return False
            ctx.acked = True
            if ctx.retransmit_task:
                ctx.retransmit_task.cancel()
            return True

    async def get_stats(self, call_id: str) -> dict | None:
        cid = (call_id or "").strip()
        if not cid:
            return None
        async with self._lock:
            ctx = self._items.get(cid)
            if not ctx:
                return None
            return {
                "call_id": cid,
                "cancelled": bool(ctx.cancelled),
                "acked": bool(ctx.acked),
                "retransmit_count": int(ctx.retransmit_count or 0),
                "final_response_sent": bool(ctx.final_response is not None),
            }

    async def start_2xx_retransmit(self, call_id: str, response: SipMessage) -> None:
        cid = (call_id or "").strip()
        if not cid:
            return
        async with self._lock:
            ctx = self._items.get(cid)
            if not ctx:
                return
            # S-01 CANCEL后487响应启动重传机制(RFC 3261 §17.2.1)，而非立即pop导致487无法重传
            # 487响应允许在cancelled上下文中启动重传；acked仍不允许
            status_code = int(getattr(response, "status_code", 0) or 0)
            if ctx.acked:
                return
            if ctx.cancelled and status_code != 487:
                return
            ctx.final_response = response
            if ctx.retransmit_task and not ctx.retransmit_task.done():
                return
            ctx.retransmit_task = asyncio.create_task(self._retransmit_2xx(cid))

    async def _send(self, ctx: InviteContext, msg: SipMessage) -> None:
        if self._sender:
            maybe = self._sender(ctx.transport, ctx.proto, ctx.addr, msg)
            if asyncio.iscoroutine(maybe):
                await maybe
            return
        data = msg.to_bytes()
        await send_sip_bytes(ctx.proto, ctx.transport, ctx.addr, data)

    async def _retransmit_2xx(self, call_id: str) -> None:
        max_seconds = float(getattr(settings, "SIP_INVITE_2XX_RETRANS_MAX_SECONDS", 32.0) or 32.0)
        t1 = float(getattr(settings, "SIP_TRANSACTION_T1_SECONDS", 1.0) or 1.0)
        t2 = float(getattr(settings, "SIP_TRANSACTION_T2_SECONDS", 8.0) or 8.0)
        t1 = max(0.05, min(t1, 2.0))
        t2 = max(t1, min(t2, 10.0))

        start = time.monotonic()
        delay = t1
        ctx_copy = None
        try:
            while True:
                await asyncio.sleep(delay)
                now = time.monotonic()
                async with self._lock:
                    ctx = self._items.get(call_id)
                    if not ctx:
                        return
                    if ctx.acked:
                        return
                    # S-01 CANCEL后487响应启动重传机制(RFC 3261 §17.2.1)
                    # cancelled上下文仅允许487重传；非cancelled上下文不允许重传cancelled状态
                    resp = ctx.final_response
                    if not resp:
                        return
                    status_code = int(getattr(resp, "status_code", 0) or 0)
                    if ctx.cancelled and status_code != 487:
                        return
                    if not ctx.cancelled and status_code not in (200, 201):
                        return
                    transport = (ctx.proto or "").upper()
                    if transport != "UDP":
                        return
                    if (now - start) > max_seconds:
                        ctx_copy = ctx
                        self._items.pop(call_id, None)
                        break
                    ctx.retransmit_count = int(ctx.retransmit_count or 0) + 1
                await self._send(ctx, resp)
                delay = min(delay * 2.0, t2)
        except asyncio.CancelledError:
            return
        else:
            if ctx_copy and ctx_copy.final_response:
                # S-01 487响应ACK超时不需要发送BYE（会话未建立），仅清理
                _final_status = int(getattr(ctx_copy.final_response, "status_code", 0) or 0)
                if _final_status in (200, 201):
                    try:
                        cseq_hdr = ctx_copy.message.get_header("CSeq") or "1 INVITE"
                        try:
                            cseq_num = int(cseq_hdr.split()[0]) + 1
                        except (ValueError, IndexError):
                            cseq_num = 2
                        bye = SipMessage()
                        bye.method = "BYE"
                        inv_from = ctx_copy.message.get_header("From") or ""
                        inv_to = ctx_copy.message.get_header("To") or ""
                        resp_from = ctx_copy.final_response.get_header("From") or inv_from
                        resp_to = ctx_copy.final_response.get_header("To") or inv_to
                        bye.uri = ctx_copy.message.uri
                        bye.version = "SIP/2.0"
                        import secrets as _secrets
                        from app.core.config import sip_host_for_contact
                        _branch = f"z9hG4bK{_secrets.token_hex(6)}"
                        bye.headers["Via"] = f"SIP/2.0/{ctx_copy.proto} {sip_host_for_contact()}:{settings.SIP_PORT};rport;branch={_branch}"
                        bye.headers["From"] = resp_to
                        bye.headers["To"] = resp_from
                        bye.headers["Call-ID"] = ctx_copy.call_id
                        bye.headers["CSeq"] = f"{cseq_num} BYE"
                        bye.headers["Max-Forwards"] = "70"
                        bye.headers["User-Agent"] = getattr(settings, "PROJECT_NAME", "PyGBSentry")
                        await self._send(ctx_copy, bye)
                        logger.info(f"[InviteServerState] Sent BYE for ACK-timeout call_id={ctx_copy.call_id}")
                    except Exception as e:
                        logger.warning(f"[InviteServerState] Failed to send BYE for ACK-timeout: {e}")
                elif _final_status == 487:
                    logger.info(f"[InviteServerState] 487 ACK-timeout, cleaning up call_id={ctx_copy.call_id}")

                try:
                    from app.db.session import AsyncSessionLocal
                    from app.models.stream_session import StreamSession
                    from sqlalchemy import select
                    _ack_timeout_ssrc = None
                    async with AsyncSessionLocal() as session:
                        ss = (await session.execute(
                            select(StreamSession).where(StreamSession.call_id == ctx_copy.call_id)
                        )).scalars().first()
                        if ss:
                            _ack_timeout_ssrc = str(getattr(ss, "ssrc", "") or "")
                            from app.services.stream_session_service import release_stream_session
                            await release_stream_session(session, ss, reason="invite_ack_timeout")
                            logger.info(f"[InviteServerState] Cleaned up stream session for ACK-timeout call_id={ctx_copy.call_id}")
                except Exception as cleanup_err:
                    logger.warning(f"[InviteServerState] Failed to cleanup stream session for ACK-timeout: {cleanup_err}")
                    # release_stream_session失败时显式释放SSRC，防止泄漏
                    if _ack_timeout_ssrc:
                        try:
                            from app.sip.ssrc_manager import ssrc_manager
                            await ssrc_manager.release(_ack_timeout_ssrc)
                        except Exception as _ssrc_fallback_err:
                            logger.warning(f"[InviteServerState] Fallback SSRC release failed for {_ack_timeout_ssrc}: {_ssrc_fallback_err}")

    async def _prune_loop(self) -> None:
        while self._running:
            try:
                await self._prune_once()
            except Exception as e:
                logger.warning(f"[InviteServerState] _prune_once failed: {e}")
            await asyncio.sleep(float(self.prune_interval_seconds))

    async def _prune_once(self) -> None:
        ttl = float(self.ttl_seconds)
        now = time.monotonic()
        expired_contexts = []
        async with self._lock:
            expired = [k for k, v in self._items.items() if (now - float(v.created_mono)) > ttl]
            for k in expired:
                ctx = self._items.pop(k, None)
                if ctx:
                    if ctx.retransmit_task:
                        ctx.retransmit_task.cancel()
                    expired_contexts.append(ctx)
        for ctx in expired_contexts:
            if ctx.final_response and int(getattr(ctx.final_response, "status_code", 0) or 0) in (200, 201):
                try:
                    from app.db.session import AsyncSessionLocal
                    from app.models.stream_session import StreamSession
                    from sqlalchemy import select
                    async with AsyncSessionLocal() as session:
                        ss = (await session.execute(
                            select(StreamSession).where(StreamSession.call_id == ctx.call_id)
                        )).scalars().first()
                        if ss:
                            from app.services.stream_session_service import finalize_stream_session
                            await finalize_stream_session(session, ss, reason="invite_server_state_pruned")
                            await session.commit()
                except Exception as e:
                    logger.warning(f"[InviteServerState] Failed to cleanup pruned entry {ctx.call_id}: {e}")


invite_server_state = InviteServerState()
