"""INVITE 服务端事务状态机（RFC 3261 §17.2.1）。

当 PyGBSentry 作为 SIP 服务端接收第三方平台/设备的 INVITE 请求时（如上级平台
点播下级设备、设备主动推流），需维护 INVITE 服务端事务状态以处理：

    * **2xx 响应重传（Timer G/H）** —— UDP 传输下 2xx 响应可能丢包，需按
      T1→T2 指数退避重传，直到收到 ACK 或 Timer H 超时。
    * **ACK 匹配** —— 收到 ACK 后停止重传（``mark_acked``），事务进入 Confirmed。
    * **CANCEL 处理** —— 收到 CANCEL 后标记取消（``mark_cancelled``），对原始
      INVITE 回 487 Request Terminated 并启动 487 重传。
    * **Timer H 超时** —— 64×T1（32s）内未收到 ACK，发送 BYE 拆除对话。

模块导出进程级单例 :data:`invite_server_state`，所有公开方法均为 ``async``。
``_lock`` 与 ``_items`` 属性被 ``handlers.py`` 直接访问（用于原子化读取上下文）。

本模块同时承载 SIP Session Timer (RFC 4028) 的纯函数工具：
    * :func:`parse_session_expires` — 解析 ``Session-Expires`` 头域
    * :func:`build_session_expires_header` — 构造 ``Session-Expires`` 头域
    * :func:`apply_session_expires_to_request` — UAC 在 INVITE 中添加头域
    * :func:`validate_session_expires_for_uas` — UAS 校验入参并协商
    * :func:`apply_session_expires_to_response` — UAS 在 200 OK 中回带头域
    * :func:`build_422_response` — Session-Expires < Min-SE 时构造 422 响应
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Any, Callable, Optional, Tuple

from loguru import logger
from app.core.async_utils import fire_and_forget  # P1-fix [2026-07-17]: 安全的火-忘任务（带异常回调与 GC 保护）


# ---------------------------------------------------------------------------
# SIP Session Timer (RFC 4028) 纯函数工具
# ---------------------------------------------------------------------------
# 这些函数不依赖任何全局状态，可独立单元测试。所有副作用（如修改 SipMessage
# 的 headers）由调用方在合适的时机触发。
# GB28181-2016 兼容：当对端不支持 Session Timer（无该头域）时，调用方应降级为
# 现有行为，仅记录 debug 日志，不得报错。

_REFRESHER_RE = re.compile(r";\s*refresher\s*=\s*([uU][aA][cC]|[uU][aA][sS])", re.IGNORECASE)


def parse_session_expires(header_value: str) -> Tuple[int, str]:
    """解析 ``Session-Expires`` 头域（RFC 4028 §5）。

    Args:
        header_value: 头域原始值，例如 ``"1800"`` 或 ``"1800;refresher=uac"``。

    Returns:
        ``(seconds, refresher)`` 二元组：
            - ``seconds`` — 会话过期秒数；空值/非法值返回 ``0``。
            - ``refresher`` — ``"uac"`` / ``"uas"`` / ``""``（未指定）。
            返回的 refresher 一律小写，便于后续比较。
    """
    if not header_value:
        return 0, ""
    raw = str(header_value).strip()
    if not raw:
        return 0, ""
    # 取分号前的秒数部分
    main = raw.split(";", 1)[0].strip()
    try:
        seconds = int(main)
    except (ValueError, TypeError):
        return 0, ""
    if seconds < 0:
        return 0, ""
    m = _REFRESHER_RE.search(raw)
    refresher = m.group(1).lower() if m else ""
    return seconds, refresher


def build_session_expires_header(seconds: int, refresher: str = "") -> str:
    """构造 ``Session-Expires`` 头域值。

    Args:
        seconds: 会话过期秒数。
        refresher: 可选，``"uac"`` / ``"uas"`` / ``""``。

    Returns:
        形如 ``"1800"`` 或 ``"1800;refresher=uac"`` 的字符串。
    """
    if seconds <= 0:
        return ""
    base = str(int(seconds))
    if refresher and refresher.lower() in ("uac", "uas"):
        return f"{base};refresher={refresher.lower()}"
    return base


def apply_session_expires_to_request(req: Any, expires: int, min_se: int) -> None:
    """UAC 在 INVITE 请求中添加 ``Session-Expires`` 与 ``Min-SE`` 头域。

    GB28181-2016 兼容：对端不支持时仅在 INVITE 中明示提议，对端若不识别则
    不会在 200 OK 中回带 — UAC 据此降级为无 Session Timer 行为。

    Args:
        req: :class:`app.sip.message.SipMessage` 实例（会就地修改 headers）。
        expires: Session-Expires 秒数（应来自 ``settings.SIP_SESSION_EXPIRES_SECONDS``）。
        min_se: Min-SE 秒数（应来自 ``settings.SIP_SESSION_MIN_SE_SECONDS``）。
    """
    if req is None or expires <= 0:
        return
    se_header = build_session_expires_header(expires)
    if se_header:
        req.headers["Session-Expires"] = se_header
    if min_se > 0:
        req.headers["Min-SE"] = str(int(min_se))


def validate_session_expires_for_uas(
    message: Any, min_se: int
) -> Tuple[bool, int, str]:
    """UAS 校验入站 INVITE 的 ``Session-Expires`` 头域并协商。

    RFC 4028 §6：若 ``Session-Expires`` 小于 ``Min-SE``，UAS 必须回 422
    Session Interval Too Small，并在响应中携带 ``Min-SE`` 头域指示可接受下限。

    GB28181-2016 兼容：当 INVITE 不携带 ``Session-Expires`` 头域时，返回
    ``(True, 0, "")`` — 调用方应跳过 Session Timer，降级为现有行为。

    Args:
        message: 入站 INVITE :class:`app.sip.message.SipMessage`。
        min_se: 配置的 Min-SE 下限（秒）。

    Returns:
        ``(ok, expires, refresher)`` 三元组：
            - ``ok=True`` — 通过校验，可继续处理（``expires=0`` 表示无该头域）。
            - ``ok=False`` — ``Session-Expires < Min-SE``，调用方应回 422。
            - ``expires`` — 解析到的秒数（即使拒绝也返回原值，便于日志）。
            - ``refresher`` — ``"uac"`` / ``"uas"`` / ``""``。
    """
    if message is None:
        return True, 0, ""
    header_val = ""
    try:
        header_val = message.get_header("Session-Expires") or ""
    except Exception as _se_hdr_err:
        # FIX [2026-07-17 P3-9]: 描述性日志替代 "silently_swallowed_exception"
        logger.debug(f"validate_session_expires_for_uas: get_header failed: {_se_hdr_err}")
        return True, 0, ""
    if not header_val:
        # 无 Session-Expires 头域 → 降级（GB28181 设备常见）
        return True, 0, ""
    seconds, refresher = parse_session_expires(header_val)
    if seconds <= 0:
        # 头域存在但解析失败 → 视为无效，按降级处理
        logger.debug(f"validate_session_expires_for_uas: unparseable header '{header_val}', degrading")
        return True, 0, ""
    if min_se > 0 and seconds < min_se:
        return False, seconds, refresher
    return True, seconds, refresher


def apply_session_expires_to_response(
    resp: Any, expires: int, refresher: str
) -> None:
    """UAS 在 200 OK 中回带协商后的 ``Session-Expires`` 头域。

    Args:
        resp: :class:`app.sip.message.SipMessage` 响应实例（就地修改）。
        expires: 协商后的过期秒数。
        refresher: 协商后的 refresher 角色（``"uac"`` / ``"uas"`` / ``""``）。
    """
    if resp is None or expires <= 0:
        return
    se_header = build_session_expires_header(expires, refresher)
    if se_header:
        resp.headers["Session-Expires"] = se_header


def build_422_response(request: Any, min_se: int) -> Any:
    """构造 422 Session Interval Too Small 响应（RFC 4028 §6）。

    Args:
        request: 触发 422 的原始 INVITE :class:`app.sip.message.SipMessage`。
        min_se: 在响应中携带的 ``Min-SE`` 头域值。

    Returns:
        :class:`app.sip.message.SipMessage` 响应实例（status_code=422）。
    """
    # 延迟导入避免循环依赖（handlers.py 在模块顶部导入本模块）
    from app.sip.message import SipMessage
    resp = SipMessage()
    resp.version = "SIP/2.0"
    resp.status_code = 422
    resp.reason_phrase = "Session Interval Too Small"
    # 回填对话标识头域
    for hdr in ("Via", "From", "To", "Call-ID", "CSeq"):
        try:
            val = request.get_header(hdr) if request is not None else ""
        except Exception:
            val = ""
        if val:
            if hdr == "Via":
                # Via 可能多值
                via_list = request.get_headers("Via") if hasattr(request, "get_headers") else [val]
                for i, v in enumerate(via_list):
                    if i == 0:
                        resp.headers["Via"] = v
                    else:
                        resp.headers.add("Via", v)
            else:
                resp.headers[hdr] = val
    if min_se > 0:
        resp.headers["Min-SE"] = str(int(min_se))
    return resp


# ---------------------------------------------------------------------------

# RFC 3261 定时器常量（秒）
_T1 = 0.5       # 初始重传间隔
_T2 = 4.0       # 最大重传间隔
_T1X64 = 64 * _T1  # Timer H 超时 = 32s


class _InviteContext:
    """单条 INVITE 服务端事务上下文。"""

    __slots__ = (
        "message", "addr", "proto", "transport",
        "cancelled", "acked", "final_response",
        "retransmit_task", "retransmit_count", "first_response_at",
        "created_at",
    )

    def __init__(
        self,
        message: Any,
        addr: tuple,
        proto: str,
        transport: Any,
    ) -> None:
        """Internal helper:   init  ."""
        self.message = message
        self.addr = addr
        self.proto = proto
        self.transport = transport
        self.cancelled: bool = False
        self.acked: bool = False
        self.final_response: Any = None  # 最后发送的 2xx/487 响应（SipMessage）
        self.retransmit_task: Optional[asyncio.Task] = None
        self.retransmit_count: int = 0
        self.first_response_at: float = 0.0
        self.created_at: float = time.monotonic()


class InviteServerState:
    """INVITE 服务端事务状态管理器（进程级单例 ``invite_server_state``）。"""

    def __init__(self) -> None:
        """Internal helper:   init  ."""
        self._lock = asyncio.Lock()
        self._items: dict[str, _InviteContext] = {}
        self._sender: Optional[Callable] = None
        self._started: bool = False

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def start(self) -> None:
        """初始化状态管理器（由 ``init_handlers`` 调用）。"""
        self._started = True
        logger.info("invite_server_state started")

    def set_sender(self, sender: Callable) -> None:
        """设置 SIP 响应发送回调。

        回调签名：``sender(transport, proto, addr, msg) -> None``（可为 async）。
        用于 Timer H 超时后发送 BYE。
        """
        self._sender = sender

    # ------------------------------------------------------------------
    # 事务状态操作
    # ------------------------------------------------------------------

    async def put(
        self,
        call_id: str,
        message: Any,
        addr: tuple,
        proto: str,
        transport: Any,
    ) -> Optional[str]:
        """存入一条 INVITE 事务上下文。

        若同一 ``call_id`` 已存在则覆盖（先取消旧的重传任务）。

        P1-fix [2026-07-17]: 处理 INVITE 重传场景。
        UDP 传输下 INVITE 重传时，若已有上下文处于以下状态，应触发不同行为：
        - 已 ACK（acked=True）：按 RFC 3261 §13.3.1.2 重传最终响应（不重新处理）
        - 已 CANCEL（cancelled=True）：重传 487 Request Terminated
        - 已发最终响应（final_response 非 None）：重传最终响应
        返回值：
        - "retransmitted_final" — 已重传最终响应，调用方不应重新处理
        - "retransmitted_487"   — 已重传 487，调用方不应重新处理
        - None                  — 已存入新上下文，调用方应正常处理
        """
        if not call_id:
            return None
        async with self._lock:
            old = self._items.get(call_id)
            if old is not None:
                # INVITE 重传场景：根据 RFC 3261 §13.3.1.2 处理
                if old.acked and old.final_response is not None and self._sender:
                    # 已 ACK 的会话收到重传 INVITE，重传最终响应
                    fire_and_forget(self._resend_final(old))
                    return "retransmitted_final"
                if old.cancelled and old.final_response is not None and self._sender:
                    # 已 CANCEL 的会话收到重传 INVITE，重传 487
                    fire_and_forget(self._resend_final(old))
                    return "retransmitted_487"
                if old.final_response is not None and self._sender:
                    # 已发最终响应但未 ACK，重传最终响应
                    fire_and_forget(self._resend_final(old))
                    return "retransmitted_final"
                # 上下文存在但无最终响应（仍在处理中），取消旧重传任务并覆盖
                if old.retransmit_task:
                    old.retransmit_task.cancel()
            self._items[call_id] = _InviteContext(message, addr, proto, transport)
            return None

    async def _resend_final(self, ctx: "_InviteContext") -> None:
        """重传最终响应（RFC 3261 §13.3.1.2）。"""
        if not ctx.final_response or not self._sender:
            return
        try:
            # FIX: [2026-08-22 PN] 原直接 await self._sender(...)，sync sender 返回
            # None 时 await None 抛 TypeError 被捕获，重传失败且计数不增加；
            # 改用 _do_send 兼容 sync/async sender。
            await self._do_send(ctx.transport, ctx.proto, ctx.addr, ctx.final_response)
            ctx.retransmit_count += 1
            logger.debug(f"Retransmitted final response for call_id (count={ctx.retransmit_count})")
        except Exception as e:
            logger.warning(f"Failed to retransmit final response: {e}")

    async def pop(self, call_id: str) -> Optional[_InviteContext]:
        """移除并返回事务上下文。取消关联的重传任务。"""
        if not call_id:
            return None
        async with self._lock:
            ctx = self._items.pop(call_id, None)
        if ctx and ctx.retransmit_task:
            ctx.retransmit_task.cancel()
            ctx.retransmit_task = None
        return ctx

    async def is_cancelled(self, call_id: str) -> bool:
        """检查事务是否已被 CANCEL。"""
        async with self._lock:
            ctx = self._items.get(call_id)
            return bool(ctx and ctx.cancelled)

    async def mark_cancelled(self, call_id: str) -> Optional[_InviteContext]:
        """标记事务为已取消，返回上下文（供调用方发送 487）。

        若事务不存在或已被取消则返回 None。
        """
        async with self._lock:
            ctx = self._items.get(call_id)
            if ctx is None or ctx.cancelled:
                return None
            ctx.cancelled = True
            return ctx

    async def mark_acked(self, call_id: str) -> bool:
        """标记收到 ACK，停止 2xx 重传。

        返回 True 表示成功标记（事务存在且未已 ACK）。
        """
        async with self._lock:
            ctx = self._items.get(call_id)
            if ctx is None or ctx.acked:
                return False
            ctx.acked = True
            if ctx.retransmit_task:
                ctx.retransmit_task.cancel()
                ctx.retransmit_task = None
            return True

    async def start_2xx_retransmit(self, call_id: str, resp: Any) -> None:
        """启动 2xx/487 响应重传（Timer G）。

        按 RFC 3261 §17.2.1：
            - UDP 传输时启用重传，TCP/TLS 不需要（可靠传输）。
            - 初始间隔 T1=0.5s，每次翻倍，上限 T2=4s。
            - 收到 ACK 后停止（由 ``mark_acked`` 取消任务）。
            - Timer H 超时（64×T1=32s）后发送 BYE 拆除对话。

        对于 TCP 传输，仅记录 final_response 但不启动重传任务。
        """
        if not call_id:
            return
        async with self._lock:
            ctx = self._items.get(call_id)
            if ctx is None:
                logger.debug(f"start_2xx_retransmit: no context for call_id={call_id}, ignoring")
                return
            # 取消旧的重传任务
            if ctx.retransmit_task:
                ctx.retransmit_task.cancel()
                ctx.retransmit_task = None
            ctx.final_response = resp
            ctx.first_response_at = time.monotonic()
            ctx.retransmit_count = 0
            # TCP/TLS 可靠传输：不重传 2xx，但仍需 Timer H 等待 ACK
            # P1-fix [2026-07-17]: 原代码 TCP/TLS 分支仅记录 final_response 但不启动任何任务，
            # 导致 ACK 永不到达时 Timer H 不触发、不发 BYE、对话永久泄漏。
            # 修复：为可靠传输启动 _timer_h_only_loop，仅做 ACK 超时检测 + BYE 发送，不重传。
            proto_upper = (ctx.proto or "").upper()
            if proto_upper in ("TCP", "TLS", "SCTP"):
                logger.debug(f"start_2xx_retransmit: reliable transport {proto_upper}, Timer-H only for call_id={call_id}")
                ctx.retransmit_task = asyncio.create_task(
                    self._timer_h_only_loop(call_id),
                    name=f"invite_timer_h:{call_id}",
                )
            else:
                # UDP：启动重传任务（含 Timer G 重传 + Timer H 超时）
                ctx.retransmit_task = asyncio.create_task(
                    self._retransmit_loop(call_id),
                    name=f"invite_retransmit:{call_id}",  # P2-fix: 便于任务排查
                )

    async def _timer_h_only_loop(self, call_id: str) -> None:
        """TCP/TLS 可靠传输的 Timer H 守护（RFC 3261 §17.2.1）。

        可靠传输无需重传 2xx（Timer G），但仍需在 64×T1=32s 内等待 ACK；
        超时未收到 ACK 则发送 BYE 拆除对话，防止对话资源永久泄漏。
        """
        deadline = _T1X64  # 32s
        try:
            await asyncio.sleep(deadline)
            # 超时仍未收到 ACK
            async with self._lock:
                ctx = self._items.get(call_id)
                if ctx is None or ctx.acked:
                    return  # 已 ACK 或已移除
            logger.warning(
                f"invite_server_state Timer H expired (TCP/TLS): no ACK for call_id={call_id} "
                f"after {deadline:.0f}s, sending BYE"
            )
            await self._send_bye_on_timeout(call_id)
            await self.pop(call_id)
        except asyncio.CancelledError:
            logger.debug(f"invite_server_state Timer-H-only cancelled for call_id={call_id}")

    async def _retransmit_loop(self, call_id: str) -> None:
        """2xx 响应重传循环（Timer G）+ ACK 超时（Timer H）。"""
        interval = _T1
        deadline = _T1X64  # 32s
        start = time.monotonic()

        try:
            while True:
                await asyncio.sleep(interval)
                elapsed = time.monotonic() - start

                # Timer H 超时：未收到 ACK，发送 BYE 拆除对话
                if elapsed >= deadline:
                    logger.warning(
                        f"invite_server_state Timer H expired: no ACK for call_id={call_id} "
                        f"after {deadline:.0f}s, sending BYE"
                    )
                    await self._send_bye_on_timeout(call_id)
                    await self.pop(call_id)
                    return

                # 检查是否已 ACK
                async with self._lock:
                    ctx = self._items.get(call_id)
                    if ctx is None or ctx.acked:
                        return  # 已 ACK 或已移除，停止重传
                    # 重传 2xx 响应
                    if ctx.final_response is not None and self._sender:
                        ctx.retransmit_count += 1
                        try:
                            await self._do_send(
                                ctx.transport, ctx.proto, ctx.addr, ctx.final_response
                            )
                            logger.debug(
                                f"invite_server_state retransmit 2xx: call_id={call_id} "
                                f"count={ctx.retransmit_count} interval={interval:.1f}s"
                            )
                        except Exception as e:
                            logger.warning(f"invite_server_state retransmit send failed: {e}")

                # 指数退避，上限 T2
                interval = min(interval * 2, _T2)

        except asyncio.CancelledError:
            logger.debug(f"invite_server_state retransmit cancelled for call_id={call_id}")

    async def _do_send(self, transport: Any, proto: str, addr: tuple, msg: Any) -> None:
        """调用 _sender 发送消息（兼容 sync/async sender）。"""
        if self._sender is None:
            return
        result = self._sender(transport, proto, addr, msg)
        if asyncio.iscoroutine(result):
            await result

    async def _send_bye_on_timeout(self, call_id: str) -> None:
        """Timer H 超时后发送 BYE 拆除对话。"""
        async with self._lock:
            ctx = self._items.get(call_id)
            if ctx is None or ctx.message is None:
                return
            # 构造 BYE 消息
            try:
                from app.sip.message import SipMessage
                bye = SipMessage()
                bye.method = "BYE"
                # 使用原始 INVITE 的 Request-URI
                bye.uri = ctx.message.uri or ""
                bye.version = "SIP/2.0"
                # 复制对话标识头
                for hdr in ("Via", "From", "To", "Call-ID", "CSeq"):
                    val = ctx.message.get_header(hdr) or ""
                    if val:
                        if hdr == "CSeq":
                            # CSeq 序号 +1，方法改为 BYE
                            parts = val.split(None, 1)
                            try:
                                cseq_num = int(parts[0]) if parts else 1
                            except ValueError:
                                cseq_num = 1
                            bye.headers[hdr] = f"{cseq_num + 1} BYE"
                        else:
                            bye.headers[hdr] = val
                bye.headers["Max-Forwards"] = "70"
            except Exception as e:
                logger.warning(f"invite_server_state: failed to build BYE for call_id={call_id}: {e}")
                return

        try:
            await self._do_send(ctx.transport, ctx.proto, ctx.addr, bye)
            logger.info(f"invite_server_state: sent BYE for call_id={call_id} (Timer H timeout)")
        except Exception as e:
            logger.warning(f"invite_server_state: failed to send BYE for call_id={call_id}: {e}")

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------

    async def get_stats(self, call_id: str) -> Optional[dict]:
        """获取事务统计信息。

        返回::

            {
                "call_id": str,
                "acked": bool,
                "cancelled": bool,
                "final_response_sent": bool,   # 是否已发送最终响应
                "retransmit_count": int,        # 2xx 重传次数
                "age_seconds": float,           # 事务存活时长
            }

        事务不存在时返回 None。
        """
        async with self._lock:
            ctx = self._items.get(call_id)
            if ctx is None:
                return None
            return {
                "call_id": call_id,
                "acked": ctx.acked,
                "cancelled": ctx.cancelled,
                "final_response_sent": ctx.final_response is not None,
                "retransmit_count": ctx.retransmit_count,
                "age_seconds": round(time.monotonic() - ctx.created_at, 3),
            }

    # ------------------------------------------------------------------
    # 维护
    # ------------------------------------------------------------------

    async def cleanup_stale(self, max_age: float = 300.0) -> int:
        """清理超过 ``max_age`` 秒的僵尸事务（调试/维护用）。"""
        now = time.monotonic()
        removed = 0
        async with self._lock:
            stale = [
                cid for cid, ctx in self._items.items()
                if now - ctx.created_at > max_age
            ]
            for cid in stale:
                ctx = self._items.pop(cid, None)
                if ctx and ctx.retransmit_task:
                    ctx.retransmit_task.cancel()
                removed += 1
        if removed:
            logger.info(f"invite_server_state cleanup_stale: removed {removed} stale transactions")
        return removed


# 进程级单例
invite_server_state = InviteServerState()
