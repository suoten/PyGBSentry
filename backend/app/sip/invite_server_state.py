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
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Optional

from loguru import logger

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
    ) -> None:
        """存入一条 INVITE 事务上下文。

        若同一 ``call_id`` 已存在则覆盖（先取消旧的重传任务）。
        """
        if not call_id:
            return
        async with self._lock:
            old = self._items.get(call_id)
            if old and old.retransmit_task:
                old.retransmit_task.cancel()
            self._items[call_id] = _InviteContext(message, addr, proto, transport)

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
            # TCP/TLS 可靠传输：不重传，但仍需 Timer H 等待 ACK
            proto_upper = (ctx.proto or "").upper()
            if proto_upper in ("TCP", "TLS", "SCTP"):
                logger.debug(f"start_2xx_retransmit: reliable transport {proto_upper}, no retransmit for call_id={call_id}")
            else:
                # UDP：启动重传任务
                ctx.retransmit_task = asyncio.create_task(self._retransmit_loop(call_id))

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
