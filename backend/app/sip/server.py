# -------------------------------------------------------------------------
# 🚀 Project: PyGBSentry
# ✍️ Author: suoten
# 📧 Email: suoten@163.com
# 📄 License: MIT
# -------------------------------------------------------------------------

import asyncio
import contextlib
import errno
from loguru import logger  # 统一使用 loguru 替代 logging
import hashlib
import secrets
import threading
import time
import re
from app.sip.message import SipMessage
from app.core.config import settings
from app.core.config import sip_host_for_contact
from app.core.async_utils import fire_and_forget  # P0-16: 安全的火-忘任务
from app.core.plugin_manager import plugin_manager



_VIA_BRANCH_RE = re.compile(r"(?:^|;)\s*branch=([^;]+)", re.IGNORECASE)
_TO_TAG_RE = re.compile(r";\s*tag=", re.IGNORECASE)


def _extract_via_branch(via_value: str) -> str:
    if not via_value:
        return ""
    m = _VIA_BRANCH_RE.search(via_value)
    return (m.group(1) or "").strip() if m else ""


def _extract_cseq_parts(cseq_value: str) -> tuple[int, str]:
    if not cseq_value:
        return (0, "")
    parts = [p for p in str(cseq_value).strip().split(" ") if p]
    if len(parts) < 2:
        return (0, "")
    try:
        n = int(parts[0])
    except Exception as e:
        logger.warning(f"Failed to parse CSeq value '{cseq_value}': {e}")
        n = 0
    return (n, parts[1].upper())


def _patch_via_received(via_value: str, received_addr: tuple) -> str:
    if not via_value or not received_addr:
        return via_value
    via_parts = via_value.split(";")
    new_via: list[str] = []
    rport_added = False
    for part in via_parts:
        p_strip = part.strip().lower()
        if p_strip == "rport" or p_strip.startswith("rport="):
            new_via.append(f"rport={received_addr[1]}")
            rport_added = True
        elif p_strip.startswith("received="):
            continue
        else:
            new_via.append(part)
    new_via.append(f"received={received_addr[0]}")
    if not rport_added and "rport" in via_value.lower():
        new_via.append(f"rport={received_addr[1]}")
    return ";".join(new_via)


def _stable_to_tag(call_id: str, cseq: str, method: str) -> str:
    src = f"{call_id}|{cseq}|{method}"
    return hashlib.sha256(src.encode("utf-8", errors="ignore")).hexdigest()[:8]


def _create_basic_response(request: SipMessage, status_code: int, reason: str, received_addr: tuple | None) -> SipMessage:
    from app.sip.handlers import create_response
    return create_response(request, status_code, reason, received_addr or ("0.0.0.0", 0))  # tuple|None → tuple


class SipServer:
    def __init__(self):
        self.udp_transport = None
        self.tcp_server = None
        self.tls_server = None  # SIP TLS (SIPS) server
        self.tls_ssl_context = None  # TLS 热加载：保存 SSLContext 引用
        self.tls_config = {}  # TLS 热加载：保存 TLS 配置参数
        self.handlers = {} # Method -> Handler Func
        self.response_handlers = [] # List of Handler Funcs
        self.running = False
        self.semaphore = asyncio.Semaphore(settings.SIP_WORKER_CONCURRENCY)
        self._tcp_clients = {} # (ip, port) -> writer
        self._response_cache = {}  # tx_key -> (SipMessage, ts)
        self._response_cache_lock = asyncio.Lock()
        self._response_cache_ttl = int(getattr(settings, "SIP_RESPONSE_CACHE_TTL_SECONDS", 32) or 32)
        self._response_cache_max_size = int(getattr(settings, "SIP_RESPONSE_CACHE_MAX_SIZE", 50000) or 50000)
        self._ip_rate_lock = threading.Lock()  # threading.Lock for sync _schedule_process
        self._inflight = 0
        self._inflight_lock = asyncio.Lock()
        self._max_inflight = int(getattr(settings, "SIP_MAX_INFLIGHT", 5000) or 5000)
        self.ip_blacklist_cache = set()
        self._ip_blacklist_last_reload = 0.0
        # Asyncio Queue for buffering burst traffic
        self._task_queue = asyncio.Queue(maxsize=10000)
        self._workers = []
        # IP rate limiting: sliding window
        self._ip_rate_tracker: dict[str, list[float]] = {}
        self._ip_rate_limit = int(getattr(settings, "SIP_IP_RATE_LIMIT", 100) or 100)
        self._ip_rate_window = 1.0  # seconds
        self._ip_only_fallback_count = 0
        self._background_tasks: set[asyncio.Task] = set()
        # FIX-LEAK: 全局字典定期清理配置（间隔可配置，从 settings 读取）
        self._seen_requests_cleanup_interval = int(
            getattr(settings, "SIP_SEEN_REQUESTS_CLEANUP_INTERVAL_SECONDS", 60) or 60)
        self._auth_failure_cleanup_interval = int(
            getattr(settings, "SIP_AUTH_FAILURE_CLEANUP_INTERVAL_SECONDS", 60) or 60)
        self._cleanup_locks_cleanup_interval = int(
            getattr(settings, "SIP_CLEANUP_LOCKS_CLEANUP_INTERVAL_SECONDS", 300) or 300)
        self._last_seen_requests_cleanup = 0.0
        self._last_auth_failure_cleanup = 0.0
        self._last_cleanup_locks_cleanup = 0.0

    def _track_background_task(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)

        def _on_done(t: asyncio.Task) -> None:
            self._background_tasks.discard(t)
            if t.cancelled():
                return
            exc = t.exception()
            if exc:
                logger.error(f"background task raised exception: {exc!r}", exc_info=exc)

        task.add_done_callback(_on_done)
        return task

    async def _worker_loop(self):
        while self.running:
            try:
                task = await self._task_queue.get()
                if task is None:
                    break
                data, addr, proto, transport = task
                await self._bounded_process(data, addr, proto, transport)
                self._task_queue.task_done()
            except Exception as e:
                logger.error(f"Worker loop error: {e}")

    def register_handler(self, method: str, handler):
        self.handlers[method] = handler

    def register_response_handler(self, handler):
        self.response_handlers.append(handler)

    def unregister_response_handler(self, handler):
        with contextlib.suppress(ValueError):
            self.response_handlers.remove(handler)

    def get_transport(self, ip: str, port: int, proto: str):
        protocol = (proto or "UDP").upper().replace("_", "-")
        if protocol.startswith("TCP"):
            protocol = "TCP"
        elif protocol.startswith("UDP"):
            protocol = "UDP"
        if protocol == "UDP":
            return self.udp_transport
        if protocol == "TCP":
            # 精确匹配 (ip, port)
            writer = self._tcp_clients.get((ip, port))
            if writer:
                return writer

            # 精确匹配失败后，尝试仅按 IP 匹配（记录警告日志）
            # 这在 NAT 环境下可能导致路由错误，标记为 debug 级别日志便于排查
            # 增加IP-only回退计数器，超过阈值自动禁用
            ip_only_matches = [(k, w) for k, w in self._tcp_clients.items() if k[0] == ip]
            if ip_only_matches:
                self._ip_only_fallback_count = getattr(self, '_ip_only_fallback_count', 0) + 1
                _max_fallback = int(getattr(settings, "SIP_TCP_IP_ONLY_FALLBACK_MAX", 100) or 100)  # 可配置阈值
                if self._ip_only_fallback_count > _max_fallback:
                    logger.warning(
                        "[SIP TCP Routing] IP-only fallback used %d times, disabling due to likely NAT. "
                        "Ensure devices register with correct port.",
                        self._ip_only_fallback_count
                    )
                    return None
                if len(ip_only_matches) == 1:
                    logger.debug(
                        f"[SIP TCP Routing] Fallback to IP-only match for {ip}:{port}, "
                        f"no exact port match available."
                    )
                    return ip_only_matches[0][1]
                else:
                    logger.warning(
                        f"[SIP TCP Routing] Multiple TCP connections from IP {ip}, "
                        f"ports={[k[1] for k, _ in ip_only_matches]}, "
                        f"requested port {port}. No exact match found. "
                        f"First connection will be used (may cause routing issues in shared-NAT scenarios)."
                    )
                    return ip_only_matches[0][1]
            return None
        return None

    class UdpProtocol(asyncio.DatagramProtocol):
        def __init__(self, server):
            self.server = server

        def connection_made(self, transport):
            self.server.udp_transport = transport
            logger.info(f"SIP UDP Listening on {settings.SIP_IP}:{settings.SIP_PORT}")

        def datagram_received(self, data, addr):
            self.server._schedule_process(data, addr, "UDP", self.server.udp_transport)

    async def _handle_tcp_client(self, reader, writer):
        addr = writer.get_extra_info('peername')
        _MAX_TCP_CLIENTS = int(getattr(settings, "SIP_MAX_TCP_CLIENTS", 1000) or 1000)
        if len(self._tcp_clients) >= _MAX_TCP_CLIENTS:
            logger.warning(f"TCP connection limit reached ({_MAX_TCP_CLIENTS}), rejecting {addr}")
            try:
                writer.close()
                await writer.wait_closed()
            except Exception as e:
                logger.warning(f"Exception: {e}")
            return
        logger.debug(f"New SIP TCP connection from {addr}")
        old_writer = self._tcp_clients.get(addr)
        if old_writer is not None and old_writer is not writer:
            try:
                try:
                    await asyncio.wait_for(old_writer.drain(), timeout=2.0)
                except Exception as e:
                    logger.warning(f"Exception: {e}")
                old_writer.close()
                await old_writer.wait_closed()
            except Exception as e:
                logger.warning(f"Failed to close old TCP writer for {addr}: {e}")
        self._tcp_clients[addr] = writer

        _TCP_MAX_BUFFER = 1048576
        _TCP_MAX_CONTENT_LENGTH = 1048576
        buffer = b""

        tcp_keepalive_interval = float(getattr(settings, "SIP_TCP_KEEPALIVE_INTERVAL_SECONDS", 30.0) or 30.0)
        tcp_keepalive_max_miss = int(getattr(settings, "SIP_TCP_KEEPALIVE_MAX_MISS", 3) or 3)
        keepalive_miss_count = 0
        last_data_time = time.monotonic()

        try:
            while self.running:
                try:
                    data = await asyncio.wait_for(reader.read(8192), timeout=tcp_keepalive_interval)
                except asyncio.TimeoutError:
                    now = __import__("time").monotonic()
                    idle_time = now - last_data_time
                    if idle_time >= tcp_keepalive_interval:
                        try:
                            crlf_keepalive = b"\r\n\r\n"
                            writer.write(crlf_keepalive)
                            await writer.drain()
                            try:
                                ack = await asyncio.wait_for(reader.read(64), timeout=5.0)
                                if ack:
                                    keepalive_miss_count = 0
                                    last_data_time = time.monotonic()
                                    if ack not in (b"\r\n\r\n", b"\r\n", b""):
                                        buffer += ack
                                        if len(buffer) > _TCP_MAX_BUFFER:
                                            logger.warning(f"TCP buffer overflow from {addr}, dropping connection")
                                            break
                                    continue
                            except asyncio.TimeoutError as e:
                                logger.debug(f"asyncio: {e}")
                            keepalive_miss_count += 1
                            if keepalive_miss_count > tcp_keepalive_max_miss:
                                logger.info(f"TCP keepalive miss count exceeded for {addr}, closing connection")
                                break
                        except Exception as e:
                            logger.warning(f"TCP keepalive send failed for {addr}: {e}")
                            break
                    continue

                if not data:
                    break

                last_data_time = time.monotonic()
                keepalive_miss_count = 0

                buffer += data
                if len(buffer) > _TCP_MAX_BUFFER:
                    logger.warning(f"TCP buffer overflow from {addr}, dropping connection")
                    break
                while b"\r\n\r\n" in buffer:
                    header_part, rest = buffer.split(b"\r\n\r\n", 1)
                    content_length = 0

                    header_lines = header_part.decode('utf-8', errors='ignore').split("\r\n")
                    for line in header_lines:
                        if line.lower().startswith("content-length:"):
                            try:
                                content_length = int(line.split(":", 1)[1].strip())
                            except (ValueError, IndexError):
                                content_length = 0
                            break

                    if content_length < 0 or content_length > _TCP_MAX_CONTENT_LENGTH:
                        logger.warning(f"Invalid Content-Length {content_length} from {addr}, dropping connection")
                        buffer = b""
                        break

                    if len(rest) >= content_length:
                        message_data = header_part + b"\r\n\r\n" + rest[:content_length]
                        buffer = rest[content_length:]
                        self._schedule_process(message_data, addr, "TCP", writer)
                    else:
                        break
        except Exception as e:
            logger.error(f"TCP Error from {addr}: {e}")
        finally:
            writer.close()
            await writer.wait_closed()
            if self._tcp_clients.get(addr) is writer:
                del self._tcp_clients[addr]
            logger.debug(f"SIP TCP connection closed from {addr}")

    async def _bounded_process(self, data, addr, proto, transport):
        async with self._inflight_lock:
            self._inflight += 1
        try:
            async with self.semaphore:
                await self.process_message(data, addr, proto, transport)
        finally:
            async with self._inflight_lock:
                self._inflight = max(0, self._inflight - 1)

    async def _send_overload_response(self, data: bytes, addr: tuple, proto: str, transport) -> None:
        try:
            msg = SipMessage.parse(data)
        except Exception as parse_err:
            # SIP过载时解析失败不再静默丢弃，记录warning日志
            logger.warning(f"SIP overload: failed to parse message from {addr} for 503 response: {parse_err}")
            return
        if not getattr(msg, "method", ""):
            return
        resp = _create_basic_response(msg, 503, "Service Unavailable", received_addr=addr)
        resp.headers["Retry-After"] = "1"

        # Use handlers.send_response for consistent UDP destination routing
        from app.sip.handlers import send_response
        await send_response(transport, proto, addr, resp)

    def _schedule_process(self, data, addr, proto, transport):
        if not self.running:
            return

        # 性能优化：对于非 SIP 报文或心跳包直接抛弃，避免进入队列
        if len(data) < 20:
            return

        # 防止超大 SIP 消息导致内存耗尽（上限 1MB）
        SIP_MAX_MESSAGE_SIZE = 1024 * 1024
        if len(data) > SIP_MAX_MESSAGE_SIZE:
            logger.warning(f"Drop oversized SIP packet from {addr}: {len(data)} bytes (max {SIP_MAX_MESSAGE_SIZE})")
            return

        # IP黑名单检查
        if addr and addr[0]:
            # IP rate limiting with lock to prevent race conditions
            now = time.time()
            ip = addr[0]
            with self._ip_rate_lock:
                timestamps = self._ip_rate_tracker.get(ip, [])
                timestamps = [t for t in timestamps if now - t < self._ip_rate_window]
                if len(timestamps) >= self._ip_rate_limit:
                    logger.warning(f"SIP rate limit exceeded for IP {ip}: {len(timestamps)} req/s (max {self._ip_rate_limit})")
                    return
                timestamps.append(now)
                self._ip_rate_tracker[ip] = timestamps
                # Periodic cleanup of stale entries
                if len(self._ip_rate_tracker) > 10000:
                    cutoff = now - self._ip_rate_window
                    self._ip_rate_tracker = {k: [t for t in v if t > cutoff] for k, v in self._ip_rate_tracker.items() if v}

            if ip in self.ip_blacklist_cache:
                logger.warning(f"Drop SIP packet from blacklisted IP: {addr[0]}")
                return
            blacklist_ttl = float(getattr(settings, "SIP_IP_BLACKLIST_CACHE_TTL_SECONDS", 60.0) or 60.0)
            if blacklist_ttl > 0 and (now - self._ip_blacklist_last_reload) > blacklist_ttl:
                fire_and_forget(self.reload_ip_blacklist())  # P0-16: 保存引用防 GC + 异常日志
            if settings.SIP_IP_BLACKLIST:
                black_ips = [ip.strip() for ip in settings.SIP_IP_BLACKLIST.split(",") if ip.strip()]
                if addr[0] in black_ips:
                    logger.warning(f"Drop SIP packet from blacklisted IP: {addr[0]}")
                    return

        if int(self._inflight) >= int(self._max_inflight) and self._task_queue.full():
            fire_and_forget(self._send_overload_response(data, addr, proto, transport))  # P0-16: 保存引用防 GC + 异常日志
            return

        try:
            self._task_queue.put_nowait((data, addr, proto, transport))
        except asyncio.QueueFull:
            fire_and_forget(self._send_overload_response(data, addr, proto, transport))  # P0-16: 保存引用防 GC + 异常日志

    def _tx_key_from_request(self, msg: SipMessage) -> str:
        via = msg.get_header("Via") or msg.get_header("v") or ""
        branch = _extract_via_branch(via)
        call_id = msg.get_header("Call-ID") or msg.get_header("i") or ""
        cseq = msg.get_header("CSeq") or ""
        seq, method = _extract_cseq_parts(cseq)
        base = f"{call_id}|{seq}|{method}|{branch}"
        if not branch:
            base = f"{call_id}|{seq}|{method}|{msg.method or ''}"
        return base

    def _tx_key_from_response(self, msg: SipMessage) -> str:
        via = msg.get_header("Via") or msg.get_header("v") or ""
        branch = _extract_via_branch(via)
        call_id = msg.get_header("Call-ID") or msg.get_header("i") or ""
        cseq = msg.get_header("CSeq") or ""
        seq, method = _extract_cseq_parts(cseq)
        base = f"{call_id}|{seq}|{method}|{branch}"
        if not branch:
            base = f"{call_id}|{seq}|{method}"
        return base

    async def cache_response(self, response: SipMessage) -> None:
        if not response or not response.is_response:
            return
        key = self._tx_key_from_response(response)
        if not key:
            return
        async with self._response_cache_lock:
            self._response_cache[key] = (response, time.time())

    async def _get_cached_response(self, tx_key: str) -> SipMessage | None:
        async with self._response_cache_lock:
            item = self._response_cache.get(tx_key)
            if not item:
                return None
            resp, ts = item
            if (time.time() - ts) > self._response_cache_ttl:
                self._response_cache.pop(tx_key, None)
                return None
            return resp

    async def _prune_response_cache(self) -> None:
        async with self._response_cache_lock:
            now = time.time()
            expired: list[str] = []
            for k, (_, ts) in self._response_cache.items():
                if (now - float(ts)) > float(self._response_cache_ttl):
                    expired.append(k)
            for k in expired:
                self._response_cache.pop(k, None)
            if len(self._response_cache) <= int(self._response_cache_max_size):
                return
            items = sorted(self._response_cache.items(), key=lambda x: float(x[1][1]))
            over = len(self._response_cache) - int(self._response_cache_max_size)
            for i in range(max(0, over)):
                self._response_cache.pop(items[i][0], None)

    async def _prune_loop(self):
        while self.running:
            try:
                await self._prune_response_cache()
                from app.sip.transactions import server_tx_manager, client_tx_manager
                await server_tx_manager.prune()  # W21 确认：server_tx_manager.prune() 已在此定时调用（每5秒）
                client_tx_manager.prune()  # W21 确认：client_tx_manager.prune() 已在此定时调用（每5秒）
            except Exception as e:
                logger.warning(f"Prune loop error: {e}")
            # I10 定期清理 invite.py 中的全局字典，防止内存泄漏
            try:
                from app.sip.invite import invite_state
                invite_state.cleanup()
            except Exception as e:
                logger.warning(f"Global dicts cleanup error: {e}")
            try:
                from app.sip.record_handler import periodic_cleanup_record_caches
                periodic_cleanup_record_caches()
            except Exception as e:
                logger.warning(f"Record cache cleanup error: {e}")  # GB28181协议 — 全局字典清理失败应warning级别
            # 设备离线检测 — 定期扫描超时设备并标记离线
            try:
                await self._check_device_offline()
            except Exception as e:
                logger.warning(f"Device offline check error: {e}")
            # FIX: [2026-07-03] 清理长时间无数据的 SIP TCP 客户端连接，防止连接泄漏 [可靠性工程师]
            try:
                await self._cleanup_stale_tcp_clients()
            except Exception as e:
                logger.warning(f"Stale TCP clients cleanup error: {e}")
            # FIX-LEAK: 全局字典定期清理 — 按配置间隔执行，避免内存泄漏
            # 清理逻辑均使用 asyncio.Lock 保护且无 I/O，不阻塞 SIP 主路径
            now = time.time()
            if now - self._last_seen_requests_cleanup >= self._seen_requests_cleanup_interval:
                try:
                    from app.sip.handlers import cleanup_seen_requests
                    await cleanup_seen_requests()
                except Exception as e:
                    logger.warning(f"Seen requests cleanup error: {e}")
                self._last_seen_requests_cleanup = now
            if now - self._last_auth_failure_cleanup >= self._auth_failure_cleanup_interval:
                try:
                    from app.sip.state_backend import get_sip_state_backend
                    await get_sip_state_backend().cleanup_auth_failures()
                except Exception as e:
                    logger.warning(f"Auth failure cleanup error: {e}")
                self._last_auth_failure_cleanup = now
            if now - self._last_cleanup_locks_cleanup >= self._cleanup_locks_cleanup_interval:
                try:
                    from app.sip.handlers import cleanup_stale_cleanup_locks
                    await cleanup_stale_cleanup_locks()
                except Exception as e:
                    logger.warning(f"Cleanup locks cleanup error: {e}")
                self._last_cleanup_locks_cleanup = now
            # FIX: [2026-07-04] 定期清理播放追踪/失败诊断/端点缓存，防止内存泄漏 [可靠性工程师]
            if now - getattr(self, "_last_stream_traces_cleanup", 0) >= 300:
                try:
                    from app.api.v1.endpoints.stream._shared import cleanup_stream_traces
                    cleaned = cleanup_stream_traces()
                    if cleaned:
                        logger.debug(f"Stream traces cleanup: removed {cleaned} stale entries")
                except Exception as e:
                    logger.warning(f"Stream traces cleanup error: {e}")
                self._last_stream_traces_cleanup = now
            await asyncio.sleep(5)

    # 设备离线检测 — 扫描 last_keepalive + expires < now 的设备，标记离线
    # 使用设备注册的 Expires 值作为基准，而非固定 60s 宽限时间
    async def _check_device_offline(self) -> int:
        # S-03: 更新共享去重时间戳，device_watchdog 据此跳过避免双重执行
        try:
            from app.services.tasks import device_watchdog
            import time as _time
            device_watchdog._last_offline_check_ts = _time.monotonic()
        except Exception:
            logger.warning("silently_swallowed_exception", exc_info=True)
        try:
            from app.db.session import AsyncSessionLocal
            from app.models.asset import Asset
            from app.models.resource import Resource
            from sqlalchemy import select, update
            import datetime
            now = datetime.datetime.now(datetime.timezone.utc)
            default_grace_seconds = int(getattr(settings, "DEVICE_OFFLINE_GRACE_SECONDS", 60) or 60)
            # use per-device expires for grace calculation: grace = max(expires, default) * 1.5
            # Devices with longer registration periods need longer grace times
            async with AsyncSessionLocal() as session:
                # First pass: devices where expires is set and grace should be longer than default
                # S-08 移除last_keepalive.isnot(None)条件，同时检测last_keepalive为NULL但status=1的设备
                # 这些设备可能注册后从未收到心跳，若注册时间超过宽限期应标记离线
                # FIX: [2026-07-04] _ensure_aware_utc 从 for 循环内移到循环外，确保无在线设备时
                #      ParentPlatform 离线检测仍能调用（否则 NameError） [全栈工程师]
                def _ensure_aware_utc(dt_val):
                    """将 offset-naive datetime 视为 UTC 并添加 tzinfo。"""
                    if dt_val is not None and hasattr(dt_val, 'tzinfo') and dt_val.tzinfo is None:
                        return dt_val.replace(tzinfo=datetime.timezone.utc)
                    return dt_val
                devices_result = await session.execute(
                    select(Asset.id, Asset.last_keepalive, Asset.expires, Asset.register_time)
                    .where(
                        Asset.status == 1,
                    )
                )
                offline_ids = []
                for row in devices_result:
                    device_expires = int(row.expires or 3600)  # 双重 or 3600 冗余，第二个永远不执行
                    # 宽限时间与设备expires成比例，而非max永远=600s
                    # 之前: max(min(e*2,300),600) 永远返回600，长expires设备10分钟即判离线
                    # 之后: grace = expires * 1.5，上限由 DEVICE_OFFLINE_MAX_GRACE_SECONDS 控制
                    # FIX: [2026-07-03] getattr 默认值从 1800 改为 300，与 config.py 保持一致 [全栈工程师]
                    max_grace_seconds = int(getattr(settings, "DEVICE_OFFLINE_MAX_GRACE_SECONDS", 300) or 300)
                    grace = max(device_expires * 1.5, default_grace_seconds)
                    grace = min(grace, max_grace_seconds)
                    cutoff = now - datetime.timedelta(seconds=grace)
                    # FIX: [2026-07-03] SQLite 返回 offset-naive datetime，与 offset-aware cutoff 比较会抛 TypeError [全栈工程师]
                    # 统一在比较前将 DB 读取的 naive datetime 加上 UTC tzinfo
                    last_ka = _ensure_aware_utc(row.last_keepalive)
                    reg_time = _ensure_aware_utc(row.register_time)
                    if last_ka and last_ka < cutoff:
                        offline_ids.append(row.id)
                    elif not row.last_keepalive:
                        # S-08 last_keepalive为NULL但status=1的设备，
                        # 若注册时间超过宽限期仍未收到心跳，应标记离线
                        if reg_time and reg_time < cutoff:
                            offline_ids.append(row.id)
                count = 0
                if offline_ids:
                    result = await session.execute(
                        update(Asset)
                        .where(Asset.id.in_(offline_ids))
                        .values(status=0)
                    )
                    count = result.rowcount
                    # 设备离线后通道状态未更新 — 同时将关联 Resource 状态设为 0
                    resource_result = await session.execute(
                        update(Resource)
                        .where(Resource.asset_id.in_(offline_ids))
                        .values(status=0)
                    )
                    resource_count = resource_result.rowcount
                    if count > 0:
                        await session.commit()
                        logger.info(f"Device offline check: marked {count} device(s) as offline, {resource_count} resource(s) status set to 0 (default_grace={default_grace_seconds}s)")
                        # 设备离线后清理流会话和订阅，避免僵尸会话残留
                        from app.sip.handlers import _cleanup_device_resources
                        from app.models.asset import Asset as _Asset
                        offline_gb_ids_result = await session.execute(
                            select(_Asset.gb_id).where(_Asset.id.in_(offline_ids))
                        )
                        for (gb_id,) in offline_gb_ids_result:
                            try:
                                await _cleanup_device_resources(gb_id)
                            except Exception as cleanup_err:
                                logger.warning(f"Failed to cleanup resources for offline device {gb_id}: {cleanup_err}")
                # FIX: [2026-07-04] 原仅检测 Asset 表设备离线，未检测 ParentPlatform（上级级联平台）
                #      离线。上级平台停止心跳后 is_online 长期保持 True，platform_service 不会触发重注册，
                #      导致向上级联链路静默中断。根因：离线巡检遗漏 ParentPlatform 表。 [全栈工程师]
                try:
                    from app.models.platform import ParentPlatform
                    platforms_result = await session.execute(
                        select(ParentPlatform.id, ParentPlatform.last_keepalive, ParentPlatform.keepalive_interval, ParentPlatform.server_gb_id)
                        .where(ParentPlatform.is_online == True, ParentPlatform.enable == True)  # noqa: E712
                    )
                    offline_platform_ids = []
                    for prow in platforms_result:
                        p_keepalive_interval = int(prow.keepalive_interval or 60)
                        # 上级平台宽限期 = keepalive_interval * 3（比设备更宽松，因上级平台重注册成本更高）
                        p_grace = max(p_keepalive_interval * 3, default_grace_seconds)
                        p_cutoff = now - datetime.timedelta(seconds=p_grace)
                        p_last_ka = _ensure_aware_utc(prow.last_keepalive)
                        if p_last_ka and p_last_ka < p_cutoff:
                            offline_platform_ids.append(prow.id)
                    if offline_platform_ids:
                        p_result = await session.execute(
                            update(ParentPlatform)
                            .where(ParentPlatform.id.in_(offline_platform_ids))
                            .values(is_online=False)
                        )
                        p_count = p_result.rowcount
                        if p_count > 0:
                            await session.commit()
                            logger.info(f"ParentPlatform offline check: marked {p_count} platform(s) as offline")
                            count += p_count
                except Exception as p_err:
                    logger.warning(f"ParentPlatform offline check failed (non-critical): {p_err}")
                return count
        except Exception as e:
            logger.warning(f"Device offline check failed (non-critical): {e}")
            return 0

    # FIX: [2026-07-03] 清理长时间无数据的 SIP TCP 客户端连接，防止连接泄漏 [可靠性工程师]
    async def _cleanup_stale_tcp_clients(self) -> int:
        """清理关闭状态的 TCP 客户端 writer 和长时间空闲的连接。

        遍历 _tcp_clients 字典，关闭已处于关闭状态的 writer，
        并从字典中移除无效引用，防止连接泄漏。
        """
        if not self._tcp_clients:
            return 0
        stale_keys: list[tuple] = []
        for addr, writer in list(self._tcp_clients.items()):
            try:
                if writer.is_closing():
                    stale_keys.append(addr)
                    continue
            except Exception:
                stale_keys.append(addr)
        for addr in stale_keys:
            writer = self._tcp_clients.pop(addr, None)
            if writer:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception as e:
                    logger.debug(f"Failed to close stale TCP client {addr}: {e}")
        if stale_keys:
            logger.info(f"Cleaned up {len(stale_keys)} stale SIP TCP client connections")
        return len(stale_keys)

    async def process_message(self, data: bytes, addr: tuple, proto: str, transport):
        try:
            msg = SipMessage.parse(data)

            # ==========================================
            # SIP L7 Firewall & Dynamic Blacklist
            # ==========================================
            client_ip = addr[0]

            # 集群模式下检查设备归属，非本节点则转发
            if settings.CLUSTER_ENABLED:
                try:
                    from app.core.redis import ha_cluster
                    if ha_cluster:
                        # 从 SIP 消息中提取设备 GB ID
                        from_header = msg.get_header("From") or ""
                        gb_id_match = re.search(r'sip:(\d+)@', from_header)
                        gb_id = gb_id_match.group(1) if gb_id_match else None
                        if gb_id:
                            owner = await ha_cluster.get_device_owner_node(gb_id)
                            if owner and owner != ha_cluster.node_id:
                                # 转发消息到归属节点
                                raw_msg = data.decode("utf-8", errors="ignore") if isinstance(data, bytes) else str(data)
                                method = msg.method or ""
                                await ha_cluster.publish("invite_route", {
                                    "target_node": owner,
                                    "method": method,
                                    "raw_message": raw_msg,
                                })
                                return
                except Exception as e:
                    logger.warning(f"Cluster route check failed: {e}")

            # 1. User-Agent 异常探测过滤 (拦截常见扫描器如 SIPVicious)
            ua = (msg.get_header("User-Agent") or "").lower()
            if "sipvicious" in ua or "friendly-scanner" in ua or "sipcli" in ua or "vaxip" in ua:
                logger.warning(f"[SIP L7 Firewall] Blocked malicious scanner UA '{ua}' from {client_ip}")
                # 记录拉黑
                await self._auto_blacklist_ip(client_ip, f"L7 firewall blocked: malicious scanner User-Agent '{ua}'")  # A-04 中文日志→英文
                return

            # 2. 异常 URI 格式拦截
            uri = msg.uri or ""
            if msg.method and (not uri.startswith("sip:") and not uri.startswith("sips:")):
                logger.warning(f"[SIP L7 Firewall] Blocked invalid URI format '{uri}' from {client_ip}")
                return

            # 3. 防止非法的 BYE 信令 (伪造攻击断流)
            if msg.method == "BYE":
                call_id = msg.get_header("Call-ID") or ""
                if len(call_id) < 10 or not re.match(r'^[a-zA-Z0-9_.\-@]+$', call_id):
                    logger.warning(f"[SIP L7 Firewall] Blocked suspicious BYE with abnormal Call-ID from {client_ip}")
                    return
            # ==========================================

            # Emit SIP TRACE
            fire_and_forget(plugin_manager.emit("ON_SIP_RECV", msg, addr, proto))  # P0-16: 保存引用防 GC + 异常日志

            if msg.method: # Request
                # R3-05 Via环路检测使用正则精确匹配host:port(RFC 3261 §18.2.1)，防止端口前缀误判
                via_header = msg.get_header("Via") or ""
                local_sip_addr = f"{sip_host_for_contact()}:{settings.SIP_PORT}"
                _via_loop_pattern = re.compile(
                    r'(?:^|[\s;/])' + re.escape(local_sip_addr) + r'(?:[:;\s]|$)',
                    re.MULTILINE
                )
                if _via_loop_pattern.search(via_header):
                    call_id = msg.get_header("Call-ID") or ""
                    logger.warning(f"[SIP Loop Protection] Via header contains local address, Call-ID={call_id}")
                    from app.sip.handlers import create_response, send_response
                    resp = create_response(msg, 482, "Loop Detected", received_addr=addr)
                    await send_response(transport, proto, addr, resp)
                    return

                # GB28181协议 — 入站请求递减Max-Forwards，防止信令路由循环
                max_forwards = msg.get_header("Max-Forwards")
                if max_forwards is not None:
                    try:
                        mf_val = int(max_forwards)
                        if mf_val <= 0:
                            logger.warning(f"[SIP Loop Protection] Max-Forwards=0, rejecting request from {client_ip}, Call-ID={msg.get_header('Call-ID')}")
                            resp = _create_basic_response(msg, 483, "Too Many Hops", received_addr=addr)
                            from app.sip.handlers import send_response
                            await send_response(transport, proto, addr, resp)
                            return
                        msg.headers["Max-Forwards"] = str(mf_val - 1)
                        # Max-Forwards递减到0时未拒绝请求 — GB28181/SIP规范要求返回483 Too Many Hops
                        if mf_val - 1 <= 0:
                            logger.warning(f"[SIP Loop Protection] Max-Forwards decremented to 0, rejecting request from {client_ip}, Call-ID={msg.get_header('Call-ID')}")
                            resp = _create_basic_response(msg, 483, "Too Many Hops", received_addr=addr)
                            from app.sip.handlers import send_response
                            await send_response(transport, proto, addr, resp)
                            return
                    except (ValueError, TypeError) as e:
                        logger.debug(f"Invalid Max-Forwards header: {e}")  # W-09 Max-Forwards 解析失败不再静默跳过
                        msg.headers["Max-Forwards"] = "70"  # W-09 解析失败时设置默认值 70

                # 信令路由循环防护 — 重复请求检测（Call-ID + CSeq）
                # FIX-LEAK: 改用锁保护的 check_and_record_seen_request()，消除并发读写竞态
                from app.sip.handlers import check_and_record_seen_request
                call_id = msg.get_header("Call-ID") or ""
                cseq = msg.get_header("CSeq") or ""
                dedup_key = f"{call_id}~{cseq}"
                # INVITE重传必须交给事务层处理(RFC 3261 Section 17.2.1)，
                # 不能在去重阶段丢弃，否则UDP丢包时UAC永远收不到200 OK
                if await check_and_record_seen_request(dedup_key, msg.method):
                    logger.debug(f"[SIP Loop Protection] Duplicate request detected, Call-ID={call_id}, CSeq={cseq}")
                    return

                from app.sip.transactions import server_tx_manager

                if msg.method != "ACK":
                    tx, is_new = await server_tx_manager.get_or_create(msg)
                    if not is_new:
                        handled = await server_tx_manager.handle_retransmission(tx, addr, proto, transport)
                        if handled:
                            return

                handler = self.handlers.get(msg.method)
                if handler:
                    await handler(msg, addr, proto, transport)
                else:
                    resp = _create_basic_response(msg, 501, "Not Implemented", received_addr=addr)
                    allow = sorted(list(self.handlers.keys()))
                    if allow:
                        resp.headers["Allow"] = ", ".join(allow)
                    from app.sip.handlers import send_response
                    await send_response(transport, proto, addr, resp)
            else: # Response
                with contextlib.suppress(Exception):
                    from app.sip.transactions import tx_manager
                    tx_manager.resolve_from_response(msg)
                for handler in list(self.response_handlers):
                    try:
                        await handler(msg, addr, proto, transport)
                    except Exception as handler_err:
                        logger.error(f"Response handler {getattr(handler, '__name__', handler)} failed: {handler_err}")

        except Exception as e:
            logger.error(f"Error processing SIP message from {addr}: {e}")

    async def _auto_blacklist_ip(self, ip: str, reason: str):
        if ip in self.ip_blacklist_cache:
            return
        try:
            from app.db.session import AsyncSessionLocal
            from app.models.ip_blacklist import IpBlacklist
            from sqlalchemy import select
            async with AsyncSessionLocal() as session:
                exist = await session.execute(select(IpBlacklist).where(IpBlacklist.ip == ip))
                if not exist.scalars().first():
                    bl = IpBlacklist(ip=ip, reason=reason)
                    session.add(bl)
                    await session.commit()
                    self.ip_blacklist_cache.add(ip)
                    logger.info(f"Dynamically blacklisted IP: {ip}")
        except Exception as e:
            logger.error(f"Failed to auto blacklist IP {ip}: {e}")

    async def reload_ip_blacklist(self):
        try:
            from app.db.session import AsyncSessionLocal
            from app.models.ip_blacklist import IpBlacklist
            from sqlalchemy import select
            async with AsyncSessionLocal() as session:
                res = await session.execute(select(IpBlacklist.ip))
                ips = res.scalars().all()
                self.ip_blacklist_cache = set(ips)
                self._ip_blacklist_last_reload = time.monotonic()
                logger.info(f"Loaded {len(self.ip_blacklist_cache)} IPs into blacklist cache.")
        except Exception as e:
            logger.error(f"Failed to reload IP blacklist: {e}")

    async def reload_tls_cert(self):
        """
        热加载 TLS 证书：收到 SIGHUP 信号或通过管理 API 调用时，
        重新加载 SSLContext 并重启 TLS 监听。
        """
        import ssl
        import os
        try:
            tls_cert = self.tls_config.get("cert") or getattr(settings, "SIPS_CERT_FILE", None)
            tls_key = self.tls_config.get("key") or getattr(settings, "SIPS_KEY_FILE", None)
            tls_ca_cert = self.tls_config.get("ca") or getattr(settings, "SIPS_CA_CERT_FILE", None)
            tls_port = self.tls_config.get("port") or getattr(settings, "SIPS_PORT", 5061)
            sip_ip = settings.SIP_IP or "0.0.0.0"

            if not tls_cert or not os.path.exists(tls_cert):
                logger.warning("[TLS] Certificate file not found, skipping reload")
                return
            if not tls_key or not os.path.exists(tls_key):
                logger.warning("[TLS] Key file not found, skipping reload")
                return

            new_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            new_context.load_cert_chain(certfile=tls_cert, keyfile=tls_key)
            if tls_ca_cert and os.path.exists(tls_ca_cert):
                new_context.verify_mode = ssl.CERT_REQUIRED
                new_context.load_verify_locations(cafile=tls_ca_cert)
                logger.info(f"[TLS] mTLS enabled (CA: {tls_ca_cert})")
            new_context.minimum_version = ssl.TLSVersion.TLSv1_2

            logger.info(f"[TLS] Certificate reloaded: cert={tls_cert}")

            # 先建后拆：先创建新TLS服务器，成功后再关闭旧的
            new_server = await asyncio.start_server(
                self._handle_tcp_client, sip_ip, tls_port, ssl=new_context, reuse_address=True
            )
            old_server = self.tls_server
            self.tls_server = new_server
            self.tls_ssl_context = new_context
            if old_server:
                old_server.close()
                await old_server.wait_closed()
            logger.info(f"[TLS] TLS server restarted on {sip_ip}:{tls_port} (build-new-then-teardown)")
        except Exception as e:
            logger.error(f"[TLS] Failed to reload TLS certificate, keeping old server: {e}")

    async def start(self):
        await self.reload_ip_blacklist()
        loop = asyncio.get_running_loop()
        sip_ip = settings.SIP_IP or "0.0.0.0"
        local_addr = (sip_ip, settings.SIP_PORT)

        # P0-SIP: 端口绑定重试 — 处理进程重启时旧端口尚未释放的竞态
        _max_retries = int(getattr(settings, "SIP_BIND_MAX_RETRIES", 3) or 3)
        _retry_delay = float(getattr(settings, "SIP_BIND_RETRY_DELAY", 1.0) or 1.0)
        _bind_attempt = 0

        while True:
            _bind_attempt += 1
            try:
                await loop.create_datagram_endpoint(
                    lambda: self.UdpProtocol(self),
                    local_addr=local_addr,
                )

                # ---------------------------------------------
                # SIP over TLS (SIPS) / TCP Server Initialization
                # ---------------------------------------------
                ssl_context = None
                tls_port = getattr(settings, "SIPS_PORT", 5061)
                tls_cert = getattr(settings, "SIPS_CERT_FILE", None)
                tls_key = getattr(settings, "SIPS_KEY_FILE", None)
                tls_ca_cert = getattr(settings, "SIPS_CA_CERT_FILE", None)

                if not getattr(settings, "ENABLE_SIPS", False):
                    _app_env = (getattr(settings, "APP_ENV", "dev") or "dev").lower()
                    if _app_env in {"prod", "production"}:
                        logger.warning("SECURITY: SIP TLS (SIPS) is disabled in production environment")

                if getattr(settings, "ENABLE_SIPS", False) and tls_cert and tls_key:
                    import ssl
                    import os
                    if os.path.exists(tls_cert) and os.path.exists(tls_key):
                        try:
                            ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
                            ssl_context.load_cert_chain(certfile=tls_cert, keyfile=tls_key)

                            # Enable mTLS if CA cert is provided
                            if tls_ca_cert and os.path.exists(tls_ca_cert):
                                ssl_context.verify_mode = ssl.CERT_REQUIRED
                                ssl_context.load_verify_locations(cafile=tls_ca_cert)
                                logger.info(f"SIPS mTLS enabled (CA: {tls_ca_cert})")

                            # 支持 TLS 1.2 及以上
                            ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
                            logger.info(f"SIPS TLS context loaded successfully (cert: {tls_cert})")
                        except Exception as e:
                            logger.error(f"Failed to load SIPS TLS context: {e}")
                            ssl_context = None

                self.tcp_server = await asyncio.start_server(
                    self._handle_tcp_client, sip_ip, settings.SIP_PORT, reuse_address=True
                )
                logger.info(f"SIP UDP/TCP Listening on {sip_ip}:{settings.SIP_PORT}")

                self.tls_server = None
                self.tls_ssl_context = ssl_context
                self.tls_config = {
                    "cert": tls_cert,
                    "key": tls_key,
                    "ca": tls_ca_cert,
                    "port": tls_port,
                }
                if ssl_context:
                    self.tls_server = await asyncio.start_server(
                        self._handle_tcp_client, sip_ip, tls_port, ssl=ssl_context, reuse_address=True
                    )
                    logger.info(f"SIP TLS (SIPS) Listening on {sip_ip}:{tls_port}")

                self.running = True

                # Start worker pool for processing SIP messages
                worker_count = settings.SIP_WORKER_CONCURRENCY
                self._workers = [asyncio.create_task(self._worker_loop()) for _ in range(worker_count)]

                self._track_background_task(self._prune_loop())

                try:
                    from app.sip.dialog_manager import dialog_manager
                    self._track_background_task(dialog_manager.cleanup_loop())
                except Exception as e:
                    logger.warning(f"Failed to start DialogManager cleanup_loop: {e}")
                try:
                    from app.sip.ssrc_manager import ssrc_manager
                    self._track_background_task(ssrc_manager.cleanup_loop())
                    try:
                        restored = await ssrc_manager.restore_from_db()
                        if restored > 0:
                            logger.info(f"SSRC Manager restored {restored} SSRCs from DB on startup")
                    except Exception as restore_err:
                        logger.error(f"SSRC Manager restore_from_db failed on startup, using larger random offset: {restore_err}")
                        ssrc_manager._live_counter = secrets.randbelow(500000000) + 1
                        ssrc_manager._playback_counter = secrets.randbelow(500000000) + 1
                except Exception as e:
                    logger.warning(f"Failed to start SsrcManager cleanup_loop: {e}")
            except OSError as e:
                err_text = f"{e}"
                if e.errno in {errno.EADDRINUSE, 98, 10048}:
                    err_text = f"SIP bind failed on {sip_ip}:{settings.SIP_PORT} (address already in use)"
                if self.udp_transport:
                    self.udp_transport.close()
                    self.udp_transport = None
                if self.tcp_server:
                    self.tcp_server.close()
                    await self.tcp_server.wait_closed()
                    self.tcp_server = None
                self.running = False
                # P0-SIP: 端口占用时重试，而非立即失败
                if _bind_attempt <= _max_retries and e.errno in {errno.EADDRINUSE, 98, 10048}:
                    logger.warning(
                        f"SIP bind attempt {_bind_attempt}/{_max_retries} failed: {err_text}, "
                        f"retrying in {settings.SIP_BIND_RETRY_DELAY}s..."
                    )
                    await asyncio.sleep(settings.SIP_BIND_RETRY_DELAY)
                    continue
                raise OSError(e.errno, err_text) from e
            except Exception as e:
                if self.udp_transport:
                    self.udp_transport.close()
                    self.udp_transport = None
                if self.tcp_server:
                    self.tcp_server.close()
                    await self.tcp_server.wait_closed()
                    self.tcp_server = None
                self.running = False
                # P0-SIP: 非端口占用异常也重试
                if _bind_attempt <= _max_retries:
                    logger.warning(
                        f"SIP start attempt {_bind_attempt}/{_max_retries} failed: {e}, "
                        f"retrying in {settings.SIP_BIND_RETRY_DELAY}s..."
                    )
                    await asyncio.sleep(settings.SIP_BIND_RETRY_DELAY)
                    continue
                raise
            # 成功绑定，跳出重试循环
            break

    async def stop(self):
        self.running = False

        for task in list(self._background_tasks):
            if not task.done():
                task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        self._background_tasks.clear()

        if self.udp_transport:
            self.udp_transport.close()
        if self.tcp_server:
            self.tcp_server.close()
            await self.tcp_server.wait_closed()
        if self.tls_server:
            self.tls_server.close()
            await self.tls_server.wait_closed()

        for _ in range(len(self._workers)):
            try:
                self._task_queue.put_nowait(None)
            except Exception as e:
                logger.warning(f"Failed to signal worker shutdown: {e}")

        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)

sip_server = SipServer()
