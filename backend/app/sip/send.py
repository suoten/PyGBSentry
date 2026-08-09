from __future__ import annotations
import asyncio
from loguru import logger
from app.core.async_utils import fire_and_forget  # P0-16: 安全的火-忘任务



async def send_sip_bytes(proto: str, transport, addr: tuple, data: bytes, parsed_msg=None, *, await_drain: bool = False) -> bool:
    """
    Send raw SIP bytes over UDP or TCP.

    Args:
        proto: Transport protocol ("UDP" or "TCP")
        transport: SIP transport layer object
        addr: (ip, port) tuple
        data: Raw SIP bytes
        parsed_msg: Optional pre-parsed SipMessage to avoid redundant parsing for tracing
        await_drain: If True, await transport.drain() for TCP to ensure data is sent (for critical responses)

    Returns:
        True if the bytes were sent (or queued for TCP), False on failure.
        R24-03: 之前静默吞异常导致调用方无法感知发送失败，PTZ 命令静默丢失。
    """
    if transport is None or getattr(transport, 'is_closing', lambda: False)():
        logger.warning(f"[send_sip_bytes] transport is None or closing, cannot send to {addr}")
        return False

    p = (proto or "UDP").upper()

    # Emit SIP TRACE for debugging (skip parsing if caller already parsed)
    if __debug__:
        try:
            from app.core.plugin_manager import plugin_manager
            msg = parsed_msg
            if msg is None:
                from app.sip.message import SipMessage
                msg = SipMessage.parse(data)
            fire_and_forget(plugin_manager.emit("ON_SIP_SEND", msg, addr, p))  # P0-16: 保存引用防 GC + 异常日志
        except Exception as e:
            logger.warning(f"Failed to emit SIP send event: {e}")

    if p == "UDP":
        try:
            transport.sendto(data, addr)
            return True
        except Exception as e:
            logger.warning(f"Failed to send SIP over UDP to {addr}: {e}")
            return False
    try:
        transport.write(data)
        if hasattr(transport, 'drain') and asyncio.iscoroutinefunction(transport.drain):
            try:
                loop = asyncio.get_running_loop()
                if await_drain:
                    # await_drain=True 时应真正 await drain，而非 create_task fire-and-forget
                    await transport.drain()
                else:
                    task = loop.create_task(transport.drain())
                    # FIX [2026-07-17 P2-7]: 原回调 t.exception() 被调用但未记录日志，异常被静默吞掉。
                    # 改为在回调中记录 warning 日志，确保 TCP drain 失败可被排查。
                    def _log_drain_exc(t: asyncio.Task) -> None:
                        if not t.cancelled():
                            exc = t.exception()
                            if exc:
                                logger.warning(f"[send_sip_bytes] TCP drain failed: {exc}")
                    task.add_done_callback(_log_drain_exc)
            except RuntimeError as _drain_rt_err:
                # FIX [2026-07-17 P2-7]: 描述性日志替代 "RuntimeError: {e}"
                logger.debug(f"[send_sip_bytes] TCP drain RuntimeError: {_drain_rt_err}")
        return True
    except Exception as e:
        logger.warning(f"Failed to send SIP over TCP to {addr}: {e}")
        return False


async def send_sip_message(proto: str, transport, addr: tuple, message) -> bool:
    """发送 SIP 消息，发送前校验 RFC 3261 必需头域。

    P0-fix [2026-07-17]: 原代码调用 validate_required_headers 但忽略返回值，
    缺失必需头域的请求仍被发出，导致对端直接丢弃且本地无错误日志。
    现在校验失败时拒绝发送并返回 False，调用方可据此记录上下文。
    """
    if not validate_required_headers(message):
        method = getattr(message, "method", "?")
        call_id = message.get_header("Call-ID") if hasattr(message, "get_header") else "?"
        logger.error(
            f"[send_sip_message] refused to send SIP {method} due to missing required headers "
            f"(call_id={call_id}, addr={addr}); see prior warning for details"
        )
        return False
    return await send_sip_bytes(proto, transport, addr, message.to_bytes())


# RFC 3261 §8.1.1 必需头域（请求）；§8.2.6.2 响应头域
_REQUIRED_REQUEST_HEADERS = ("Via", "From", "To", "Call-ID", "CSeq", "Max-Forwards")


def validate_required_headers(message) -> bool:
    """校验 SIP 消息是否包含 RFC 3261 必需头域。

    P1-fix [2026-07-17]: 原代码发送前不校验头域，缺少 Via/Call-ID/CSeq 等头域的
    请求会被对端直接丢弃，导致设备无响应且难以排查。

    Returns:
        True — 所有必需头域存在
        False — 缺失头域（已记录 warning 日志）
    """
    method = getattr(message, "method", "") or ""
    if not method:
        # 响应消息不强制校验（状态行已含足够信息）
        return True

    missing = []
    for hdr in _REQUIRED_REQUEST_HEADERS:
        val = message.get_header(hdr) if hasattr(message, "get_header") else None
        if not val:
            missing.append(hdr)

    if missing:
        call_id = message.get_header("Call-ID") if hasattr(message, "get_header") else "?"
        logger.warning(
            f"SIP request missing required headers: method={method} "
            f"call_id={call_id} missing={missing}"
        )
        return False
    return True
