import asyncio
from loguru import logger
import warnings
from typing import Callable
from app.sip.message import SipMessage



warnings.warn(
    "app.sip.transport is deprecated and not used by SipServer. "
    "Server uses its own UdpProtocol and _handle_tcp_client instead. "
    "This module will be removed in a future version.",
    DeprecationWarning,
    stacklevel=2,
)

class UdpTransport(asyncio.DatagramProtocol):
    def __init__(self, message_callback: Callable[[SipMessage, tuple, str, object], None]):
        self.transport = None
        self.message_callback = message_callback

    def connection_made(self, transport):
        self.transport = transport
        sock = transport.get_extra_info('socket')
        addr = transport.get_extra_info('sockname')
        logger.info(f"SIP UDP Transport listening on {addr}")

    def datagram_received(self, data: bytes, addr: tuple):
        try:
            if data == b"\r\n\r\n" or data == b"\x00":
                return
            if len(data) < 4:
                return

            message = SipMessage.parse(data)
            coro = self.message_callback(message, addr, "UDP", self.transport)
            if coro is not None:  # FIXED: message_callback 可能返回 None
                asyncio.create_task(coro)
        except Exception as e:
            logger.error(f"Error parsing UDP SIP message from {addr}: {e}")

    def error_received(self, exc):
        logger.error(f"SIP UDP Transport error: {exc}")

    def connection_lost(self, exc):
        logger.info(f"SIP UDP Transport connection lost: {exc}")

class TcpProtocol(asyncio.Protocol):
    MAX_BUFFER_SIZE = 65536

    def __init__(self, message_callback: Callable[[SipMessage, tuple, str, object], None]):
        self.transport = None
        self.message_callback = message_callback
        self.buffer = b""
        self._closing = False

    def connection_made(self, transport):
        self.transport = transport
        peername = transport.get_extra_info('peername')
        logger.info(f"SIP TCP Connection from {peername}")

    def data_received(self, data: bytes):
        if self._closing:
            return
        self.buffer += data
        if len(self.buffer) > self.MAX_BUFFER_SIZE:
            logger.warning(f"SIP TCP buffer exceeded {self.MAX_BUFFER_SIZE} bytes, closing connection")
            self._closing = True
            if self.transport:  # FIXED: transport 可为 None
                self.transport.close()
            return
        while b"\r\n\r\n" in self.buffer:
            header_end = self.buffer.find(b"\r\n\r\n") + 4
            headers_raw = self.buffer[:header_end]

            try:
                headers_str = headers_raw.decode('utf-8', errors='strict')
            except UnicodeDecodeError:
                try:
                    headers_str = headers_raw.decode('gb18030', errors='strict')
                except UnicodeDecodeError:
                    headers_str = headers_raw.decode('latin-1')

            content_length = 0
            found_content_length = False
            for line in headers_str.split("\r\n"):
                if line.lower().startswith("content-length:"):
                    found_content_length = True
                    try:
                        content_length = int(line.split(":", 1)[1].strip())
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid Content-Length value in SIP TCP message, closing connection")
                        self._closing = True
                        if self.transport:  # FIXED: transport 可为 None
                            self.transport.close()
                        return
                    break

            if not found_content_length:
                logger.warning(f"Missing Content-Length header in SIP over TCP message, closing connection per RFC 3261")
                self._closing = True
                if self.transport:  # FIXED: transport 可为 None
                    self.transport.close()
                return

            total_len = header_end + content_length
            if len(self.buffer) >= total_len:
                msg_data = self.buffer[:total_len]
                self.buffer = self.buffer[total_len:]

                try:
                    addr = self.transport.get_extra_info('peername') if self.transport else None  # FIXED: transport 可为 None
                    if addr is None:
                        return
                    message = SipMessage.parse(msg_data)
                    coro = self.message_callback(message, addr, "TCP", self.transport)
                    if coro is not None:  # FIXED: message_callback 可能返回 None
                        asyncio.create_task(coro)
                except Exception as e:
                    logger.error(f"Error parsing TCP SIP message: {e}")
            else:
                break

    def connection_lost(self, exc):
        logger.info("SIP TCP Connection lost")
        self.buffer = b""
        self.transport = None
