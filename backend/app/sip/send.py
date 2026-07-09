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
                    task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
            except RuntimeError as e:
                logger.debug(f"RuntimeError: {e}")
        return True
    except Exception as e:
        logger.warning(f"Failed to send SIP over TCP to {addr}: {e}")
        return False


async def send_sip_message(proto: str, transport, addr: tuple, message) -> None:
    await send_sip_bytes(proto, transport, addr, message.to_bytes())
