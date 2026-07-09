from __future__ import annotations
from loguru import logger

import asyncio
import re
import time
from dataclasses import dataclass

from app.sip.message import SipMessage
from app.core.config import settings
from app.core.async_utils import fire_and_forget  # P0-16: 安全的火-忘任务

_VIA_BRANCH_RE = re.compile(r"(?:^|;)\s*branch=([^;]+)", re.IGNORECASE)
_VIA_TRANSPORT_RE = re.compile(r"^\s*SIP/2\.0/([A-Za-z]+)\s+", re.IGNORECASE)
_VIA_BRANCH_KV_RE = re.compile(r"((?:^|;)\s*branch=)([^;]+)", re.IGNORECASE)


def _extract_via_branch(via_value: str) -> str:
    if not via_value:
        return ""
    m = _VIA_BRANCH_RE.search(via_value)
    return (m.group(1) or "").strip() if m else ""

def _extract_via_transport(via_value: str) -> str:
    if not via_value:
        return ""
    m = _VIA_TRANSPORT_RE.search(via_value)
    return (m.group(1) or "").strip().upper() if m else ""


def _replace_via_branch(via_value: str, new_branch: str) -> str:
    if not via_value:
        return via_value
    if _VIA_BRANCH_KV_RE.search(via_value):
        return _VIA_BRANCH_KV_RE.sub(rf"\g<1>{new_branch}", via_value, count=1)
    return via_value + f";branch={new_branch}"


def _extract_cseq_parts(cseq_value: str) -> tuple[int, str]:
    if not cseq_value:
        return (0, "")
    parts = [p for p in str(cseq_value).strip().split(" ") if p]
    if len(parts) < 2:
        return (0, "")
    try:
        n = int(parts[0])
    except Exception:
        n = 0
    return (n, parts[1].upper())


def tx_key_from_request(msg: SipMessage) -> str:
    via = msg.get_header("Via") or msg.get_header("v") or ""
    branch = _extract_via_branch(via)
    call_id = msg.get_header("Call-ID") or msg.get_header("i") or ""
    cseq = msg.get_header("CSeq") or ""
    seq, method = _extract_cseq_parts(cseq)
    # ACK is a separate transaction, even if it has the same branch as the INVITE.
    if msg.method == "ACK":
        method = "ACK"
    base = f"{call_id}|{seq}|{method}|{branch}"
    if not branch:
        base = f"{call_id}|{seq}|{method}|{msg.method or ''}"
    return base


def tx_key_from_response(msg: SipMessage) -> str:
    via = msg.get_header("Via") or msg.get_header("v") or ""
    branch = _extract_via_branch(via)
    call_id = msg.get_header("Call-ID") or msg.get_header("i") or ""
    cseq = msg.get_header("CSeq") or ""
    seq, method = _extract_cseq_parts(cseq)
    base = f"{call_id}|{seq}|{method}|{branch}"
    if not branch:
        base = f"{call_id}|{seq}|{method}"
    return base


@dataclass
class SipServerTransaction:
    key: str
    created_at: float
    request: SipMessage
    last_response: SipMessage | None = None
    state: str = "Trying"
    timers: list[asyncio.Handle] | None = None
    ttl: float = 32.0  # 动态属性 _ttl 改为正式 dataclass 字段

class SipServerTransactionManager:
    # S-04 SipServerTransactionManager全部方法添加锁保护，消除并发竞态
    def __init__(self):
        self._tx: dict[str, SipServerTransaction] = {}
        self._lock = asyncio.Lock()
        self._default_ttl = 32.0
        self._invite_ttl = float(getattr(settings, "SIP_INVITE_SERVER_TX_TTL_SECONDS", 120.0) or 120.0)

    async def get_or_create(self, request: SipMessage) -> tuple[SipServerTransaction, bool]:
        async with self._lock:
            key = tx_key_from_request(request)
            if key in self._tx:
                return self._tx[key], False

            is_invite = (request.method == "INVITE")
            ttl = self._invite_ttl if is_invite else self._default_ttl
            tx = SipServerTransaction(key=key, created_at=time.monotonic(), request=request, timers=[], ttl=ttl)  # 使用正式字段替代动态属性
            self._tx[key] = tx
            return tx, True

    # INVITE事务状态机不完整 — 添加 Confirmed/Terminated 状态转换
    async def update_state(self, key: str, response: SipMessage):
        async with self._lock:
            tx = self._tx.get(key)
            if not tx:
                return
            tx.last_response = response
            status = int(response.status_code or 0)

            is_invite = (tx.request.method == "INVITE")

            if 100 <= status <= 199:
                if tx.state not in ("Accepted", "Confirmed"):
                    tx.state = "Proceeding"
            elif 200 <= status <= 699:
                # Confirmed是终态，不可被重传的200 OK回退，符合RFC 3261 Section 17.2.1
                if tx.state == "Confirmed":
                    return
                if is_invite and 200 <= status <= 299:
                    tx.state = "Accepted"
                else:
                    tx.state = "Completed"
                    # W-01 Non-INVITE server transaction Timer J — RFC 3261 Section 17.2.2
                    # After entering Completed, start Timer J (default 64*T1 = 64*0.5 = 32s) to transition to Terminated
                    if not is_invite:
                        self._start_timer_j_locked(key)

    # W-01 Non-INVITE server transaction Timer J — RFC 3261 Section 17.2.2
    # Timer J fires after 64*T1 (config SIP_TRANSACTION_T1_SECONDS default 0.5s → 32s), transitioning Completed -> Terminated.
    def _start_timer_j_locked(self, key: str, timeout: float | None = None):
        """Start Timer J — caller must hold self._lock."""
        if timeout is None:
            t1 = float(getattr(settings, "SIP_TRANSACTION_T1_SECONDS", 0.5) or 0.5)
            timeout = 64 * t1  # RFC 3261 default: 64*T1 = 64*0.5 = 32s
        tx = self._tx.get(key)
        if not tx:
            return
        loop = asyncio.get_running_loop()

        def _on_timer_j():
            async def _async_on_timer_j():
                async with self._lock:
                    tx_j = self._tx.get(key)
                    if tx_j and tx_j.state == "Completed":
                        tx_j.state = "Terminated"
                        self._tx.pop(key, None)
                        if tx_j.timers:
                            for t in tx_j.timers:
                                t.cancel()
                        logger.debug(f"[TimerJ] Non-INVITE transaction terminated after Timer J: key={key}")
            fire_and_forget(_async_on_timer_j())  # P0-16: 保存引用防 GC + 异常日志

        handle = loop.call_later(timeout, _on_timer_j)
        if tx.timers is None:
            tx.timers = []
        tx.timers.append(handle)

    async def start_timer_j(self, key: str, timeout: float | None = None):
        """Public API: start Timer J with lock protection."""
        async with self._lock:
            self._start_timer_j_locked(key, timeout)

    # GB7 服务端INVITE事务Timer G/H/I — RFC 3261 Section 17.2.1
    # 注意: invite_server_state.py 已通过 InviteServerState.start_2xx_retransmit() 实现了
    # 2xx 重传逻辑（等效于 Timer G）和 ACK 超时处理（等效于 Timer H）。
    # 此处的 Timer G/H/I 方法在事务层提供状态跟踪，与 invite_server_state 互补。
    # 当 invite_server_state 已覆盖重传逻辑时，不重复调度定时器，仅做状态追踪。

    async def start_timer_g(self, key: str, response: SipMessage, addr: tuple, proto: str, transport):
        """Timer G: Retransmit 2xx response until ACK received (UDP only).
        Delegated to invite_server_state.start_2xx_retransmit() — no duplicate timer here."""
        async with self._lock:
            tx = self._tx.get(key)
            if not tx or proto.upper() != "UDP":
                return
            # invite_server_state already handles 2xx retransmission with exponential backoff
            # This method exists for state-tracking completeness at the transaction layer.
            logger.debug(f"[TimerG] 2xx retransmit delegated to invite_server_state for key={key}")

    async def start_timer_h(self, key: str, timeout: float = 64.0):
        """Timer H: Wait for ACK timeout = 64*T1. If no ACK, terminate transaction.
        Delegated to invite_server_state._retransmit_2xx() max_seconds — no duplicate timer here."""
        async with self._lock:
            tx = self._tx.get(key)
            if not tx:
                return
            # invite_server_state._retransmit_2xx already sends BYE on ACK timeout
            # This method exists for state-tracking completeness at the transaction layer.
            logger.debug(f"[TimerH] ACK timeout handled by invite_server_state for key={key}")

    def _start_timer_i_locked(self, key: str, timeout: float = 5.0):
        """Start Timer I — caller must hold self._lock."""
        tx = self._tx.get(key)
        if not tx:
            return
        loop = asyncio.get_running_loop()

        def _on_timer_i():
            async def _async_on_timer_i():
                async with self._lock:
                    tx_i = self._tx.get(key)
                    if tx_i and tx_i.state == "Confirmed":
                        tx_i.state = "Terminated"
                        self._tx.pop(key, None)
                        if tx_i.timers:
                            for t in tx_i.timers:
                                t.cancel()
                        logger.debug(f"[TimerI] Transaction deleted after ACK retransmission wait: key={key}")
            fire_and_forget(_async_on_timer_i())  # P0-16: 保存引用防 GC + 异常日志

        handle = loop.call_later(timeout, _on_timer_i)
        if tx.timers is None:
            tx.timers = []
        tx.timers.append(handle)

    async def start_timer_i(self, key: str, timeout: float = 5.0):
        """Public API: start Timer I with lock protection."""
        async with self._lock:
            self._start_timer_i_locked(key, timeout)

    # INVITE事务状态机不完整 — 收到ACK时调用，Accepted -> Confirmed
    async def confirm_transaction(self, key: str):
        async with self._lock:
            tx = self._tx.get(key)
            if not tx:
                return
            if tx.state == "Accepted":
                tx.state = "Confirmed"
                # GB7 收到ACK后启动Timer I（UDP下等待ACK重传超时后删除事务）
                # Timer G/H 由 invite_server_state 管理，收到ACK时其 mark_acked 会取消重传
                self._start_timer_i_locked(key, timeout=float(getattr(settings, "SIP_TRANSACTION_T1_SECONDS", 1.0) or 1.0) * 5.0)

    # INVITE事务状态机不完整 — Completed/Terminated 转换
    async def terminate_transaction(self, key: str):
        async with self._lock:
            tx = self._tx.get(key)
            if not tx:
                return
            if tx.state in ("Completed", "Confirmed", "Accepted"):
                tx.state = "Terminated"
            # GB7 终止事务时取消所有定时器
            if tx.timers:
                for t in tx.timers:
                    t.cancel()
                tx.timers = []
    # INVITE事务状态机不完整 — Confirmed状态不再重传200 OK
    async def handle_retransmission(self, tx: SipServerTransaction, addr: tuple, proto: str, transport) -> bool:
        async with self._lock:
            if tx.state in ("Proceeding", "Completed", "Accepted") and tx.last_response:
                data = tx.last_response.to_bytes()
                if proto == "UDP":
                    transport.sendto(data, addr)
                else:
                    transport.write(data)
                return True
            return False

    # INVITE事务状态机不完整 — 过期事务先设为Terminated再移除
    async def prune(self):
        async with self._lock:
            now = time.monotonic()
            expired = []
            for k, tx in self._tx.items():
                ttl = tx.ttl  # 直接访问 dataclass 字段
                if now - tx.created_at > ttl:
                    expired.append(k)
            for k in expired:
                tx = self._tx.get(k)
                if tx:
                    tx.state = "Terminated"
                tx = self._tx.pop(k, None)
                if tx and tx.timers:
                    for t in tx.timers:
                        t.cancel()

server_tx_manager = SipServerTransactionManager()

@dataclass
class SipClientTransaction:
    key: str
    created_at: float
    future: asyncio.Future
    attempts: int = 0
    last_send_at: float = 0.0
    timers: list[asyncio.Handle] | None = None
    # S-06 分离最终超时定时器(Timer B/F)与重传定时器(Timer A/E)，
    # 1xx临时响应只取消重传定时器，保留超时定时器继续运行（RFC 3261 Section 17.1.1.2）
    timeout_timer: asyncio.Handle | None = None
    state: str = "Trying"  # GB6 非INVITE客户端事务状态机 — RFC 3261 Section 17.1.2


class SipClientTransactionManager:
    def __init__(self):
        self._tx: dict[str, SipClientTransaction] = {}
        self._lock = asyncio.Lock()
        # GB28181 网络环境通常存在高延迟问题，调整 T1/T2 参数
        # T1: 初始重传间隔，默认 1.0 秒（原 0.5 秒），适合城域/企业网络
        #      如果在高延迟网络（如 4G/卫星链路）仍有问题，可通过配置项覆盖
        # T2: 最大重传间隔，默认 8.0 秒（原 4.0 秒），给予设备更多响应时间
        self._t1 = float(getattr(settings, "SIP_TRANSACTION_T1_SECONDS", 1.0) or 1.0)
        self._t2 = float(getattr(settings, "SIP_TRANSACTION_T2_SECONDS", 8.0) or 8.0)
        # 确保 T1 <= T2
        self._t1 = max(0.1, min(self._t1, 5.0))
        self._t2 = max(self._t1, min(self._t2, 16.0))
        self._default_ttl = 32.0
        self._invite_ttl = float(getattr(settings, "SIP_INVITE_SERVER_TX_TTL_SECONDS", 120.0) or 120.0)

    async def send_and_wait(
        self,
        *,
        request: SipMessage,
        send_once,
        timeout_seconds: float,
        retries: int = 0,
    ) -> tuple[SipMessage, dict]:
        timeout_seconds = float(timeout_seconds or 0)
        if timeout_seconds <= 0:
            timeout_seconds = 2.0

        # 从实例属性读取 T1/T2，允许通过配置覆盖
        t1 = float(getattr(settings, "SIP_TRANSACTION_T1_SECONDS", self._t1) or self._t1)
        t2 = float(getattr(settings, "SIP_TRANSACTION_T2_SECONDS", self._t2) or self._t2)
        t1 = max(0.1, min(t1, 5.0))
        t2 = max(t1, min(t2, 16.0))

        base_via = request.get_header("Via") or ""
        transport = _extract_via_transport(base_via)
        is_udp = (transport or "").upper() == "UDP"

        last_error: str = ""
        for cycle in range(0, max(0, int(retries)) + 1):
            if cycle > 0 and base_via:
                new_branch = f"{_extract_via_branch(base_via) or 'z9hG4bK'}r{cycle}{int(time.monotonic() * 1000)}"
                request.headers["Via"] = _replace_via_branch(base_via, new_branch)

            key = tx_key_from_request(request)
            loop = asyncio.get_running_loop()
            fut = loop.create_future()
            created_at = time.monotonic()
            timers: list[asyncio.Handle] = []

            async with self._lock:
                old = self._tx.pop(key, None)
                if old and not old.future.done():
                    old.future.cancel()
                self._tx[key] = SipClientTransaction(key=key, created_at=created_at, future=fut, timers=timers)

            async def _fire_send() -> None:
                async with self._lock:
                    tx = self._tx.get(key)
                    if not tx or tx.future.done():
                        return
                    tx.attempts = int(tx.attempts) + 1
                    tx.last_send_at = time.monotonic()
                maybe = send_once()
                if asyncio.iscoroutine(maybe):
                    fire_and_forget(maybe)  # P0-16: 保存引用防 GC + 异常日志

            try:
                await _fire_send()
                if is_udp:
                    delay = float(t1)
                    elapsed = 0.0
                    while True:
                        elapsed += delay
                        if elapsed >= timeout_seconds:
                            break
                        timers.append(loop.call_later(elapsed, lambda: fire_and_forget(_fire_send())))
                        delay = min(delay * 2.0, float(t2))

                resp: SipMessage = await asyncio.wait_for(fut, timeout=timeout_seconds)
                rtt_ms = int((time.monotonic() - created_at) * 1000)
                # GB6 非INVITE事务状态转换 — 收到最终响应后设为 Completed
                async with self._lock:
                    tx = self._tx.pop(key, None)
                if tx:
                    status_code = int(getattr(resp, "status_code", 0) or 0)
                    if 100 <= status_code <= 199:
                        tx.state = "Proceeding"
                    elif 200 <= status_code <= 699:
                        tx.state = "Completed"
                    if tx.timers:
                        for h in tx.timers:
                            h.cancel()
                    # S-06 同时取消超时定时器
                    if tx.timeout_timer:
                        tx.timeout_timer.cancel()
                meta = {
                    "tx_key": key,
                    "cycle": cycle,
                    "attempts": int(getattr(tx, "attempts", 1) or 1),
                    "rtt_ms": rtt_ms,
                    "error": "",
                    "transport": transport or "",
                }
                return resp, meta
            except asyncio.TimeoutError:
                last_error = "timeout"
                async with self._lock:
                    tx = self._tx.pop(key, None)
                if tx and tx.timers:
                    for h in tx.timers:
                        h.cancel()
                if tx and tx.timeout_timer:
                    tx.timeout_timer.cancel()
                if cycle >= int(retries):
                    break
            except asyncio.CancelledError:
                async with self._lock:
                    tx = self._tx.pop(key, None)
                if tx and tx.timers:
                    for h in tx.timers:
                        h.cancel()
                if tx and tx.timeout_timer:
                    tx.timeout_timer.cancel()
                raise
            except Exception as e:
                last_error = f"wait_failed: {e}"
                async with self._lock:
                    tx = self._tx.pop(key, None)
                if tx and tx.timers:
                    for h in tx.timers:
                        h.cancel()
                if tx and tx.timeout_timer:
                    tx.timeout_timer.cancel()
                break

        raise asyncio.TimeoutError(last_error or "timeout")

    def resolve_from_response(self, response: SipMessage) -> bool:
        key = tx_key_from_response(response)
        if not key:
            return False
        tx = self._tx.get(key)
        if not tx:
            return False
        if tx.future.done():
            return False
        status_code = int(getattr(response, "status_code", 0) or 0)
        cseq = str(response.get_header("CSeq") or "")
        method = cseq.split(" ", 1)[1].strip() if " " in cseq else ""
        if method.upper() == "INVITE" and 100 <= status_code < 200:
            # S-09 1xx 临时响应应向上传递给 TU（RFC 3261 Section 17.1.1.2）
            # S-06 只取消重传定时器(Timer A/E)，保留最终超时定时器(Timer B/F)继续运行
            # 收到1xx后停止重传，但仍需等待最终响应；若最终响应超时Timer B/F仍应触发
            if tx.timers:
                for h in tx.timers:
                    h.cancel()
                tx.timers = []
            # 注意：不取消 tx.timeout_timer，让Timer B/F继续运行等待最终响应
            # 通过 _provisional_result 属性传递 1xx，不 resolve future
            # （future 只能 set_result 一次，留给最终响应）
            if not hasattr(tx, 'provisional_responses'):
                tx.provisional_responses = []
            tx.provisional_responses.append(response)
            return True
        # GB6 非INVITE事务状态转换
        if 100 <= status_code <= 199:
            tx.state = "Proceeding"
        elif 200 <= status_code <= 699:
            tx.state = "Completed"
        tx.future.set_result(response)
        if tx.timers:
            for h in tx.timers:
                h.cancel()
        # S-06 最终响应时同时取消超时定时器(Timer B/F)
        if tx.timeout_timer:
            tx.timeout_timer.cancel()
            tx.timeout_timer = None
        return True

    async def send_request(self, request: SipMessage, addr: tuple, proto: str, transport) -> None:
        """Fire and forget a request but handle UDP retransmissions automatically via timers."""
        key = tx_key_from_request(request)
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        timers = []
        created_at = time.monotonic()

        async with self._lock:
            old = self._tx.pop(key, None)
            if old:
                if old.timers:
                    for h in old.timers:
                        h.cancel()
                # S-06 同时取消旧事务的超时定时器
                if old.timeout_timer:
                    old.timeout_timer.cancel()
                if not old.future.done():
                    old.future.cancel()
            self._tx[key] = SipClientTransaction(key=key, created_at=created_at, future=fut, timers=timers)

        data = request.to_bytes()
        is_udp = proto.upper() == "UDP"

        # 从实例属性读取 T1/T2，允许通过配置覆盖
        t1 = float(getattr(settings, "SIP_TRANSACTION_T1_SECONDS", self._t1) or self._t1)
        t2 = float(getattr(settings, "SIP_TRANSACTION_T2_SECONDS", self._t2) or self._t2)
        t1 = max(0.1, min(t1, 5.0))
        t2 = max(t1, min(t2, 16.0))

        def _do_send():
            try:
                # 检查是否已经收到回复，收到回复就停止重传
                if fut.done():
                    return
                if getattr(transport, 'is_closing', lambda: False)():
                    return
                if is_udp:
                    transport.sendto(data, addr)
                else:
                    transport.write(data)
            except Exception as e:
                logger.warning(f"Error: {e}")

        _do_send()

        if is_udp:
            # GB28181 标准中建议 INVITE 超时时间长一些（例如 64*T1 = 64秒），非 INVITE 较短（例如 10秒）
            # 但实际应用中，设备通常在 5-10 秒内响应，故设置 20-30 秒
            is_invite = request.method == "INVITE"
            timeout = float(getattr(settings, "SIP_TRANSACTION_TIMEOUT_SECONDS", 30.0 if is_invite else 15.0))

            delay = t1
            elapsed = 0.0
            while elapsed + delay < timeout:
                elapsed += delay
                timers.append(loop.call_later(elapsed, _do_send))
                # T1, 2*T1, 4*T1 ... but max is T2
                delay = min(delay * 2.0, t2)

            # Cleanup timer (Timer B/F — 最终响应超时)
            def _cleanup():
                async def _clean():
                    async with self._lock:
                        tx = self._tx.pop(key, None)
                        if tx and tx.timers:
                            for h in tx.timers:
                                h.cancel()
                        # S-06 超时定时器已触发，无需再cancel自身
                        if tx and not tx.future.done():
                            tx.future.cancel()
                fire_and_forget(_clean())  # P0-16: 保存引用防 GC + 异常日志

            # S-06 将最终超时定时器(Timer B/F)存储在timeout_timer而非timers列表，
            # 以便1xx响应时只取消重传定时器而保留超时定时器
            tx_ref = self._tx.get(key)
            if tx_ref:
                tx_ref.timeout_timer = loop.call_later(timeout, _cleanup)

    def prune(self):
        now = time.monotonic()
        expired = []
        for k, tx in self._tx.items():
            is_invite = "|INVITE|" in k or k.endswith("|INVITE")
            ttl = self._invite_ttl if is_invite else self._default_ttl
            if now - tx.created_at > ttl:
                expired.append(k)
        for k in expired:
            tx = self._tx.pop(k, None)
            if tx and tx.timers:
                for h in tx.timers:
                    h.cancel()
            if tx and not tx.future.done():
                tx.future.cancel()

client_tx_manager = SipClientTransactionManager()
tx_manager = client_tx_manager
