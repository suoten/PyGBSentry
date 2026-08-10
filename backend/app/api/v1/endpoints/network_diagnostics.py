"""网络诊断工具：Ping / Traceroute / 端口探测 / SIP探测 / 流媒体探测。"""
import asyncio
import ipaddress
import platform
import re
import socket
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger

from app.api import deps
from app.models.user import User

router = APIRouter()

# ---------------------------------------------------------------------------
# SSRF 防护：禁止探测内网保留地址
# ---------------------------------------------------------------------------

_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _is_private_host(host: str) -> bool:
    """检查 host 是否解析到内网保留地址，防止 SSRF。"""
    try:
        addr_info = socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        return False
    for family, _type, _proto, _canon, sockaddr in addr_info:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        for net in _PRIVATE_NETWORKS:
            if ip in net:
                return True
    return False


def _validate_host(host: str) -> None:
    """校验 host 参数，拒绝内网保留地址以防止 SSRF。"""
    if _is_private_host(host):
        raise HTTPException(
            status_code=400,
            detail="Target host resolves to a private/reserved address, which is not allowed",
        )


# 缺少网络层诊断工具，仅依赖 SIP 信令层追踪无法定位网络故障
# 以下端点使用 asyncio.create_subprocess_exec 执行系统命令，避免阻塞事件循环

_IS_WINDOWS = platform.system().lower() == "windows"


# ---------------------------------------------------------------------------
# 1. POST /ping — Ping 诊断
# ---------------------------------------------------------------------------

@router.post("/ping", summary="Ping diagnosis")
async def ping_diagnosis(
    host: str = Query(..., description="Target host IP or domain"),
    count: int = Query(4, ge=1, le=20, description="Number of pings"),
    timeout: int = Query(5, ge=1, le=30, description="Timeout in seconds"),
    current_user: User = Depends(deps.require_roles(["admin"])),
):
    """Ping a host and return statistics."""
    # 实现网络层 Ping 诊断
    _validate_host(host)

    if _IS_WINDOWS:
        cmd = ["ping", "-n", str(count), "-w", str(timeout * 1000), host]
    else:
        cmd = ["ping", "-c", str(count), "-W", str(timeout), host]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=count * timeout + 10
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Ping command timed out")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="ping command not found on server")

    output = stdout.decode(errors="replace")
    error = stderr.decode(errors="replace")

    if proc.returncode != 0 and not output:
        raise HTTPException(status_code=502, detail=f"Ping failed: {error.strip()}")

    # 解析输出，返回 min/avg/max/loss 统计
    stats = _parse_ping_output(output)
    return {
        "host": host,
        "count": count,
        "timeout": timeout,
        "raw_output": output,
        "statistics": stats,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _parse_ping_output(output: str) -> dict:
    """解析 ping 命令输出，提取延迟统计和丢包率。"""
    stats: dict = {
        "min_ms": None,
        "avg_ms": None,
        "max_ms": None,
        "packet_loss_percent": None,
        "packets_sent": None,
        "packets_received": None,
    }

    # 丢包率 — Windows: "Packets: Sent = 4, Received = 3, Lost = 1 (25% loss)"
    loss_match_win = re.search(
        r"Packets:\s*Sent\s*=\s*(\d+).*?Received\s*=\s*(\d+).*?Lost\s*=\s*\d+\s*\((\d+)%\s*loss\)",
        output,
        re.IGNORECASE,
    )
    if loss_match_win:
        stats["packets_sent"] = int(loss_match_win.group(1))
        stats["packets_received"] = int(loss_match_win.group(2))
        stats["packet_loss_percent"] = float(loss_match_win.group(3))

    # 丢包率 — Linux: "4 packets transmitted, 3 received, 25% packet loss"
    loss_match_linux = re.search(
        r"(\d+)\s+packets?\s+transmitted.*?(\d+)\s+received.*?([\d.]+)%\s*packet\s*loss",
        output,
        re.IGNORECASE,
    )
    if loss_match_linux:
        stats["packets_sent"] = int(loss_match_linux.group(1))
        stats["packets_received"] = int(loss_match_linux.group(2))
        stats["packet_loss_percent"] = float(loss_match_linux.group(3))

    # 延迟统计 — Windows: "Minimum = 1ms, Maximum = 5ms, Average = 2ms"
    latency_match_win = re.search(
        r"Minimum\s*=\s*([\d.]+)\s*ms.*?Maximum\s*=\s*([\d.]+)\s*ms.*?Average\s*=\s*([\d.]+)\s*ms",
        output,
        re.IGNORECASE,
    )
    if latency_match_win:
        stats["min_ms"] = float(latency_match_win.group(1))
        stats["max_ms"] = float(latency_match_win.group(2))
        stats["avg_ms"] = float(latency_match_win.group(3))

    # 延迟统计 — Linux: "rtt min/avg/max/mdev = 1.234/2.345/5.678/1.234 ms"
    latency_match_linux = re.search(
        r"rtt\s+min/avg/max/mdev\s*=\s*([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)\s*ms",
        output,
    )
    if latency_match_linux:
        stats["min_ms"] = float(latency_match_linux.group(1))
        stats["avg_ms"] = float(latency_match_linux.group(2))
        stats["max_ms"] = float(latency_match_linux.group(3))

    return stats


# ---------------------------------------------------------------------------
# 2. POST /traceroute — Traceroute 诊断
# ---------------------------------------------------------------------------

@router.post("/traceroute", summary="Traceroute diagnosis")
async def traceroute_diagnosis(
    host: str = Query(..., description="Target host IP or domain"),
    max_hops: int = Query(30, ge=1, le=64, description="Maximum hops"),
    timeout: int = Query(5, ge=1, le=30, description="Timeout in seconds"),
    current_user: User = Depends(deps.require_roles(["admin"])),
):
    """Traceroute to a host."""
    # 实现网络层 Traceroute 诊断
    _validate_host(host)

    if _IS_WINDOWS:
        cmd = ["tracert", "-h", str(max_hops), "-w", str(timeout * 1000), host]
    else:
        cmd = ["traceroute", "-m", str(max_hops), "-w", str(timeout), host]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=max_hops * timeout + 30
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Traceroute command timed out")
    except FileNotFoundError:
        # Linux 可能未安装 traceroute
        raise HTTPException(status_code=500, detail="traceroute command not found on server")

    output = stdout.decode(errors="replace")
    stderr.decode(errors="replace")

    hops = _parse_traceroute_output(output)

    return {
        "host": host,
        "max_hops": max_hops,
        "timeout": timeout,
        "hops": hops,
        "raw_output": output,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _parse_traceroute_output(output: str) -> list[dict]:
    """解析 traceroute/tracert 输出，提取每一跳信息。"""
    hops: list[dict] = []

    # Windows tracert: "  1    <1 ms    <1 ms    <1 ms  192.168.1.1"
    # Linux traceroute: " 1  192.168.1.1 (192.168.1.1)  0.534 ms  0.421 ms  0.398 ms"
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue

        # Windows 格式
        win_match = re.match(
            r"^\d+\s+"
            r"(?:<\d+\s+ms|\*|\d+\s+ms)\s+"
            r"(?:<\d+\s+ms|\*|\d+\s+ms)\s+"
            r"(?:<\d+\s+ms|\*|\d+\s+ms)\s+"
            r"(\S+)",
            line,
        )
        if win_match:
            hops.append({"host": win_match.group(1), "line": line})
            continue

        # Linux 格式
        linux_match = re.match(
            r"^\d+\s+(?:\S+\s+\((\S+)\)|(\S+))\s+",
            line,
        )
        if linux_match:
            hop_host = linux_match.group(1) or linux_match.group(2)
            hops.append({"host": hop_host, "line": line})
            continue

        # 超时行: " 2     *        *        *"
        if re.match(r"^\d+\s+(\*\s+){2,}\*?\s*$", line):
            hops.append({"host": "*", "line": line})

    return hops


# ---------------------------------------------------------------------------
# 3. POST /port-probe — 端口探测
# ---------------------------------------------------------------------------

@router.post("/port-probe", summary="TCP port probe")
async def port_probe(
    host: str = Query(..., description="Target host IP or domain"),
    port: int = Query(..., ge=1, le=65535, description="Target port"),
    timeout: float = Query(5.0, ge=0.5, le=30.0, description="Timeout in seconds"),
    current_user: User = Depends(deps.require_roles(["admin"])),
):
    """Probe if a TCP port is open."""
    # 实现端口探测，使用 asyncio.open_connection 测试 TCP 连通性
    _validate_host(host)

    start = asyncio.get_event_loop().time()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout,
        )
        elapsed_ms = round((asyncio.get_event_loop().time() - start) * 1000, 2)
        writer.close()
        await writer.wait_closed()
        return {
            "host": host,
            "port": port,
            "is_open": True,
            "latency_ms": elapsed_ms,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except asyncio.TimeoutError:
        elapsed_ms = round((asyncio.get_event_loop().time() - start) * 1000, 2)
        return {
            "host": host,
            "port": port,
            "is_open": False,
            "latency_ms": elapsed_ms,
            "reason": "timeout",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except (ConnectionRefusedError, OSError) as exc:
        elapsed_ms = round((asyncio.get_event_loop().time() - start) * 1000, 2)
        return {
            "host": host,
            "port": port,
            "is_open": False,
            "latency_ms": elapsed_ms,
            "reason": str(exc),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# ---------------------------------------------------------------------------
# 4. POST /sip-probe — SIP 服务探测
# ---------------------------------------------------------------------------

@router.post("/sip-probe", summary="SIP server probe")
async def sip_server_probe(
    host: str = Query(..., description="SIP server host"),
    port: int = Query(5060, ge=1, le=65535, description="SIP server port"),
    transport: str = Query("udp", pattern="^(udp|tcp)$"),
    timeout: float = Query(5.0, ge=0.5, le=30.0),
    current_user: User = Depends(deps.require_roles(["admin"])),
):
    """Probe SIP server by sending OPTIONS request."""
    # 实现 SIP 服务探测，发送 SIP OPTIONS 请求并等待响应
    _validate_host(host)

    branch = f"z9hG4bK-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
    sip_options = (
        f"OPTIONS sip:{host}:{port} SIP/2.0\r\n"
        f"Via: SIP/2.0/{transport.upper()} {host}:{port};branch={branch};rport\r\n"
        f"From: <sip:probe@{host}>;tag=probe\r\n"
        f"To: <sip:probe@{host}>\r\n"
        f"Call-ID: {branch}@{host}\r\n"
        f"CSeq: 1 OPTIONS\r\n"
        f"Contact: <sip:probe@{host}>\r\n"
        f"Max-Forwards: 70\r\n"
        f"Content-Length: 0\r\n"
        f"\r\n"
    )

    start = asyncio.get_event_loop().time()
    try:
        if transport.lower() == "udp":
            # UDP: 使用 asyncio Datagram
            result = await _sip_probe_udp(host, port, sip_options.encode(), timeout)
        else:
            # TCP: 使用 asyncio.open_connection
            result = await _sip_probe_tcp(host, port, sip_options.encode(), timeout)

        elapsed_ms = round((asyncio.get_event_loop().time() - start) * 1000, 2)
        result["latency_ms"] = elapsed_ms
        result["host"] = host
        result["port"] = port
        result["transport"] = transport
        result["timestamp"] = datetime.now(timezone.utc).isoformat()
        return result
    except Exception as exc:
        elapsed_ms = round((asyncio.get_event_loop().time() - start) * 1000, 2)
        return {
            "host": host,
            "port": port,
            "transport": transport,
            "reachable": False,
            "latency_ms": elapsed_ms,
            "reason": str(exc),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


async def _sip_probe_udp(host: str, port: int, data: bytes, timeout: float) -> dict:
    """通过 UDP 发送 SIP OPTIONS 并等待响应。"""
    loop = asyncio.get_event_loop()
    future = loop.create_future()

    class _SipUdpProtocol(asyncio.DatagramProtocol):
        def __init__(self, fut):
            self.fut = fut
            self.transport = None

        def connection_made(self, transport):
            self.transport = transport
            self.transport.sendto(data)

        def datagram_received(self, data, addr):
            if not self.fut.done():
                self.fut.set_result(data.decode(errors="replace"))
            if self.transport:
                self.transport.close()

        def error_received(self, exc):
            if not self.fut.done():
                self.fut.set_exception(exc)
            if self.transport:
                self.transport.close()

        def connection_lost(self, exc):
            if not self.fut.done():
                self.fut.set_exception(exc or ConnectionError("UDP connection lost"))

    transport, protocol = await loop.create_datagram_endpoint(
        lambda: _SipUdpProtocol(future),
        remote_addr=(host, port),
    )
    try:
        response = await asyncio.wait_for(future, timeout=timeout)
    except asyncio.TimeoutError:
        return {"reachable": False, "reason": "timeout"}
    finally:
        transport.close()

    return _parse_sip_response(response)


async def _sip_probe_tcp(host: str, port: int, data: bytes, timeout: float) -> dict:
    """通过 TCP 发送 SIP OPTIONS 并等待响应。"""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
    except (asyncio.TimeoutError, ConnectionRefusedError, OSError) as exc:
        return {"reachable": False, "reason": str(exc)}

    try:
        writer.write(data)
        await writer.drain()

        response_data = await asyncio.wait_for(reader.read(4096), timeout=timeout)
        response = response_data.decode(errors="replace")
    except asyncio.TimeoutError:
        return {"reachable": False, "reason": "response_timeout"}
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception as _close_err:
            # FIX [2026-07-17 P3-29]: 描述性日志替代静默吞异常，便于发现 socket 泄漏
            logger.debug(f"network_diagnostics: SIP probe writer.wait_closed failed: {_close_err}")

    return _parse_sip_response(response)


def _parse_sip_response(response: str) -> dict:
    """解析 SIP 响应，提取状态码和状态文本。"""
    first_line = response.splitlines()[0] if response else ""
    status_match = re.match(r"SIP/2\.0\s+(\d{3})\s+(.*)", first_line)
    if status_match:
        return {
            "reachable": True,
            "status_code": int(status_match.group(1)),
            "status_text": status_match.group(2).strip(),
            "response_first_line": first_line,
        }
    return {
        "reachable": True,
        "status_code": None,
        "status_text": None,
        "response_first_line": first_line,
    }


# ---------------------------------------------------------------------------
# 5. POST /media-probe — 流媒体服务探测
# ---------------------------------------------------------------------------

@router.post("/media-probe", summary="Media server probe")
async def media_server_probe(
    host: str = Query(..., description="Media server host"),
    http_port: int = Query(8880, ge=1, le=65535, description="Media server HTTP port"),
    secret: str = Query("", description="Media server API secret"),
    timeout: float = Query(5.0, ge=0.5, le=30.0),
    current_user: User = Depends(deps.require_roles(["admin"])),
):
    """Probe media server (ZLMediaKit) by calling getServerConfig API."""
    # 实现流媒体服务探测，调用 ZLM /index/api/getServerConfig API 测试连通性
    _validate_host(host)

    import aiohttp

    url = f"http://{host}:{http_port}/index/api/getServerConfig"
    # FIX [2026-07-17 P1-D1]: secret 通过 POST body 传递
    form_data = {"secret": secret} if secret else {}

    start = asyncio.get_event_loop().time()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=form_data, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                elapsed_ms = round((asyncio.get_event_loop().time() - start) * 1000, 2)
                await resp.text()
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    data = None

                if resp.status == 200 and data and data.get("code") == 0:
                    return {
                        "host": host,
                        "http_port": http_port,
                        "reachable": True,
                        "api_code": data.get("code"),
                        "latency_ms": elapsed_ms,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                else:
                    return {
                        "host": host,
                        "http_port": http_port,
                        "reachable": True,
                        "api_code": data.get("code") if data else None,
                        "http_status": resp.status,
                        "latency_ms": elapsed_ms,
                        "reason": "API returned non-zero code" if (data and data.get("code") != 0) else "unexpected response",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
    except asyncio.TimeoutError:
        elapsed_ms = round((asyncio.get_event_loop().time() - start) * 1000, 2)
        return {
            "host": host,
            "http_port": http_port,
            "reachable": False,
            "latency_ms": elapsed_ms,
            "reason": "timeout",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        elapsed_ms = round((asyncio.get_event_loop().time() - start) * 1000, 2)
        return {
            "host": host,
            "http_port": http_port,
            "reachable": False,
            "latency_ms": elapsed_ms,
            "reason": str(exc),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
