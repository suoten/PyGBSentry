"""网络诊断工具：Ping / Traceroute / 端口探测 / SIP探测 / 流媒体探测。"""

import asyncio
import ipaddress
import platform
import re
import socket
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.db.session import get_db
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
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=count * timeout + 10)
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
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=max_hops * timeout + 30)
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

    start = asyncio.get_running_loop().time()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout,
        )
        elapsed_ms = round((asyncio.get_running_loop().time() - start) * 1000, 2)
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
        elapsed_ms = round((asyncio.get_running_loop().time() - start) * 1000, 2)
        return {
            "host": host,
            "port": port,
            "is_open": False,
            "latency_ms": elapsed_ms,
            "reason": "timeout",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except (ConnectionRefusedError, OSError) as exc:
        elapsed_ms = round((asyncio.get_running_loop().time() - start) * 1000, 2)
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

    start = asyncio.get_running_loop().time()
    try:
        if transport.lower() == "udp":
            # UDP: 使用 asyncio Datagram
            result = await _sip_probe_udp(host, port, sip_options.encode(), timeout)
        else:
            # TCP: 使用 asyncio.open_connection
            result = await _sip_probe_tcp(host, port, sip_options.encode(), timeout)

        elapsed_ms = round((asyncio.get_running_loop().time() - start) * 1000, 2)
        result["latency_ms"] = elapsed_ms
        result["host"] = host
        result["port"] = port
        result["transport"] = transport
        result["timestamp"] = datetime.now(timezone.utc).isoformat()
        return result
    except Exception as exc:
        elapsed_ms = round((asyncio.get_running_loop().time() - start) * 1000, 2)
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
    loop = asyncio.get_running_loop()
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
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
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

    start = asyncio.get_running_loop().time()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=form_data, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                elapsed_ms = round((asyncio.get_running_loop().time() - start) * 1000, 2)
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
        elapsed_ms = round((asyncio.get_running_loop().time() - start) * 1000, 2)
        return {
            "host": host,
            "http_port": http_port,
            "reachable": False,
            "latency_ms": elapsed_ms,
            "reason": "timeout",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        elapsed_ms = round((asyncio.get_running_loop().time() - start) * 1000, 2)
        return {
            "host": host,
            "http_port": http_port,
            "reachable": False,
            "latency_ms": elapsed_ms,
            "reason": str(exc),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# ---------------------------------------------------------------------------
# 6. POST /diagnose-play — 播放失败一键诊断
# ---------------------------------------------------------------------------
# FIX [2026-11-21] (产品路线图 Phase1 / ROADMAP.md):
# 对照 wvp 456 个 issue,"收流超时/播放失败"占 1/4 且用户连问题都描述不出。
# 该端点把播放链路拆成可自检的关卡,一次性给出"哪一关没过 + 怎么修",
# 前端在播放失败界面直接展示,替代让用户翻文档猜配置。


def _diag_item(key: str, ok: bool, label_zh: str, label_en: str, detail_zh: str, detail_en: str, hint_zh: str = "", hint_en: str = "", severity: str = "") -> dict:
    """构造统一结构的诊断项;severity 缺省由 ok 推导(ok/fail)。"""
    sev = severity or ("ok" if ok else "fail")
    return {
        "key": key,
        "severity": sev,
        "ok": ok,
        "label": {"zh": label_zh, "en": label_en},
        "detail": {"zh": detail_zh, "en": detail_en},
        "hint": {"zh": hint_zh, "en": hint_en},
    }


async def _tcp_probe(host: str, port: int, timeout: float = 2.5) -> tuple[bool, float, str]:
    start = asyncio.get_running_loop().time()
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
        elapsed = round((asyncio.get_running_loop().time() - start) * 1000, 1)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True, elapsed, ""
    except asyncio.TimeoutError:
        return False, round((asyncio.get_running_loop().time() - start) * 1000, 1), "timeout"
    except OSError as e:
        return False, round((asyncio.get_running_loop().time() - start) * 1000, 1), str(e)


@router.post("/diagnose-play", summary="Play failure one-shot diagnosis")
async def diagnose_play(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """播放失败一键诊断:按播放链路逐关卡检查,返回结论与修复指引。

    关卡:设备注册 → 设备信令地址/传输 → 设备可达性 → 流媒体节点 → 对外播放地址 →
    SSRC 容量。每项返回 ok/severity + 双语 detail/hint,前端在播放失败界面直接渲染。
    """
    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models.asset import Asset
    from app.models.resource import Resource

    device_id = str((payload or {}).get("device_id") or "").strip()
    channel_id = str((payload or {}).get("channel_id") or "").strip()
    if not device_id and not channel_id:
        raise HTTPException(status_code=400, detail="device_id or channel_id required")

    items: list[dict] = []
    tenant_id = current_user.tenant_id or "default"

    # 1. 设备注册与租户归属
    asset = None
    resource = None
    stmt = select(Asset).where(Asset.gb_id == (device_id or channel_id))
    if not current_user.is_superuser:
        stmt = stmt.where(Asset.tenant_id == tenant_id)
    try:
        asset = (await db.execute(stmt.limit(1))).scalars().first()
        if not asset and channel_id:
            res_stmt = select(Resource).where(Resource.gb_id == channel_id)
            if not current_user.is_superuser:
                res_stmt = res_stmt.where(Resource.tenant_id == tenant_id)
            resource = (await db.execute(res_stmt.limit(1))).scalars().first()
            if resource and getattr(resource, "asset_id", None):
                asset = (await db.execute(select(Asset).where(Asset.id == resource.asset_id))).scalars().first()
    except Exception as e:
        logger.warning(f"diagnose-play db query failed: {e}")

    if asset is None:
        items.append(
            _diag_item(
                "device_registered",
                False,
                "设备已注册",
                "Device registered",
                "未找到该设备/通道的注册记录(或无权限查看)",
                "No registration record found for this device/channel (or no permission)",
                "确认设备国标编码是否正确、设备是否已接入本平台;租户账号只能查看本租户设备。",
                "Verify the GB ID is correct and the device is connected to this platform; tenant accounts can only see their own devices.",
            )
        )
        return _diag_verdict(items)

    items.append(
        _diag_item(
            "device_registered",
            (asset.status or 0) == 1,
            "设备已注册",
            "Device registered",
            f"设备在线状态: {'在线' if (asset.status or 0) == 1 else '离线'}",
            f"Device status: {'online' if (asset.status or 0) == 1 else 'offline'}",
            "" if (asset.status or 0) == 1 else "设备离线:检查摄像头网络、SIP 接入配置(服务器地址/端口/编码)与心跳;可先用「同步通道」探测。",
            "Device offline: check camera network, SIP access config (server addr/port/ID) and keepalive; try 'Sync channels' to probe.",
        )
    )

    # 2. 设备信令地址与平台传输
    dev_ip = str(getattr(asset, "ip_addr", "") or "").strip()
    try:
        dev_port = int(getattr(asset, "port", 0) or 0)
    except (TypeError, ValueError):
        dev_port = 0
    dev_proto = str(getattr(asset, "transport", "") or "UDP").upper()
    addr_ok = bool(dev_ip) and dev_port > 0
    items.append(
        _diag_item(
            "device_address",
            addr_ok,
            "设备信令地址",
            "Device signaling address",
            f"{dev_ip or '(空)'}:{dev_port or '(空)'} / {dev_proto}" if addr_ok else "数据库中设备地址缺失",
            f"{dev_ip or '(empty)'}:{dev_port or '(empty)'} / {dev_proto}" if addr_ok else "Device address missing in database",
            "" if addr_ok else "设备注册地址缺失——让设备重新注册(重启摄像头或重新保存接入配置)。",
            "" if addr_ok else "Registered device address missing — re-register the device (reboot camera or re-save access config).",
        )
    )

    # 3. 平台 SIP 传输可用性(设备为 UDP 时 TCP 探测不适用,注册成功本身即为可达证明)
    from app.sip.server import sip_server as _sip_server

    transport = _sip_server.get_transport(dev_ip, dev_port, dev_proto) if addr_ok else None
    if addr_ok and dev_proto == "TCP":
        reachable, latency, reason = await _tcp_probe(dev_ip, dev_port)
        items.append(
            _diag_item(
                "device_reachable",
                reachable,
                "设备信令可达(TCP)",
                "Device signaling reachable (TCP)",
                f"TCP 连接 {dev_ip}:{dev_port} {'成功, ' + str(latency) + 'ms' if reachable else '失败: ' + reason}",
                f"TCP connect {dev_ip}:{dev_port} {'ok, ' + str(latency) + 'ms' if reachable else 'failed: ' + reason}",
                "" if reachable else "设备信令端口不可达:检查摄像头侧 SIP 端口、防火墙与路由(设备重启后地址变化也常见)。",
                "" if reachable else "Device signaling port unreachable: check camera SIP port, firewall and routing (address change after reboot is common).",
            )
        )
    elif addr_ok:
        items.append(
            _diag_item(
                "device_reachable",
                transport is not None,
                "平台 SIP 传输就绪",
                "Platform SIP transport ready",
                f"{dev_proto} 传输通道{'可用' if transport is not None else '未建立'}(UDP 无平台侧可靠探测,实际可达性以点播 INVITE 实测为准)",
                f"{dev_proto} transport {'available' if transport is not None else 'not established'} (UDP cannot be probed reliably from platform side; actual reachability is proven by the INVITE attempt)",
                "" if transport is not None else "平台 SIP 服务未就绪或目标路由缺失——检查 SIP 服务状态页。",
                "" if transport is not None else "Platform SIP service not ready or route missing — check the SIP service status page.",
            )
        )

    # 4. 流媒体节点可达
    node_host = node_http_port = node_secret = node_id = None
    try:
        from app.core.media_nodes_db import get_active_media_node_id, select_best_db_node

        active_id = await get_active_media_node_id(db)
        db_node = await get_db_media_node_by_id(db, active_id) if active_id else None
        if not db_node:
            db_node = await select_best_db_node(db)
        if db_node:
            node_id = str(db_node.id)
            node_host = db_node.host
            node_http_port = int(db_node.http_port or 0)
            node_secret = db_node.secret
    except Exception as e:
        logger.debug(f"diagnose-play node select failed: {e}")
    if not node_host:
        from app.core.config import settings as _settings

        node_host = _settings.MEDIA_SERVER_HOST
        node_http_port = int(_settings.MEDIA_SERVER_HTTP_PORT or 0)
        node_secret = _settings.MEDIA_SERVER_SECRET
        node_id = "env"

    zlm_ok = False
    zlm_latency = 0.0
    zlm_reason = ""
    if node_host and node_http_port > 0:
        try:
            from app.services.zlm_stream_control import _get_zlm_client

            client = await _get_zlm_client()
            start = asyncio.get_running_loop().time()
            resp = await client.post(
                f"http://{node_host}:{node_http_port}/index/api/getMediaList",
                data={"secret": str(node_secret or "")},
                timeout=3.0,
            )
            zlm_latency = round((asyncio.get_running_loop().time() - start) * 1000, 1)
            if resp.status_code < 400:
                body = resp.json()
                zlm_ok = body.get("code") in (0, "0")
                if not zlm_ok:
                    zlm_reason = f"code={body.get('code')} (secret 可能不匹配)"
            else:
                zlm_reason = f"HTTP {resp.status_code}"
        except Exception as e:
            zlm_reason = str(e)[:120]
    else:
        zlm_reason = "流媒体节点地址/端口未配置"
    items.append(
        _diag_item(
            "media_node",
            zlm_ok,
            "流媒体服务(ZLM)可达",
            "Media server (ZLM) reachable",
            f"{node_host or '(空)'}:{node_http_port or '(空)'} [{node_id}] "
            + (f"正常, {zlm_latency}ms" if zlm_ok else f"不可达: {zlm_reason}"),
            f"{node_host or '(empty)'}:{node_http_port or '(empty)'} [{node_id}] "
            + (f"ok, {zlm_latency}ms" if zlm_ok else f"unreachable: {zlm_reason}"),
            "" if zlm_ok else "ZLM 不可达:确认流媒体服务已启动、HTTP 端口(默认 8880)可访问、节点 secret 与 ZLM 配置一致。",
            "" if zlm_ok else "ZLM unreachable: confirm the media server is running, HTTP port (default 8880) is accessible, and node secret matches ZLM config.",
        )
    )

    # 5. 对外播放地址(内网地址仅影响公网浏览器,标 warn 不算失败)
    play_host = ""
    try:
        from app.core.config import settings as _settings

        play_host = str(getattr(db_node, "public_host", "") if db_node else "") or str(_settings.STREAM_PUBLIC_HOST or "")
    except Exception:
        play_host = ""
    play_host_private = bool(play_host) and _is_private_host(play_host)
    items.append(
        _diag_item(
            "public_address",
            bool(play_host) and not play_host_private,
            "对外播放地址",
            "Public playback address",
            f"播放地址主机: {play_host or '(未配置)'}" + ("(内网地址)" if play_host_private else ""),
            f"Playback host: {play_host or '(not set)'}" + (" (private/LAN address)" if play_host_private else ""),
            (
                ""
                if (bool(play_host) and not play_host_private)
                else "未配置公网地址或配置的是内网地址:公网浏览器将无法播放。设置 STREAM_PUBLIC_HOST 或节点的 public_host 为公网 IP/域名;仅内网使用可忽略本项。"
            ),
            (
                ""
                if (bool(play_host) and not play_host_private)
                else "No public address configured (or it is a LAN address): public browsers cannot play. Set STREAM_PUBLIC_HOST or node public_host to a public IP/domain; ignore this item for LAN-only usage."
            ),
            severity=("ok" if (play_host and not play_host_private) else "warn"),
        )
    )
    if play_host_private:
        items[-1]["severity"] = "warn"

    # 6. SSRC 容量(泄漏耗尽会导致点播 503)
    try:
        from app.sip.ssrc_manager import ssrc_manager

        stats = ssrc_manager.stats()
        allocated = int(stats.get("live_allocated", 0)) + int(stats.get("playback_allocated", 0))
        items.append(
            _diag_item(
                "ssrc_capacity",
                allocated < 8000,
                "SSRC 资源余量",
                "SSRC capacity",
                f"已分配 {allocated}/10000(实时 {stats.get('live_allocated', 0)} / 回放 {stats.get('playback_allocated', 0)})",
                f"{allocated}/10000 allocated (live {stats.get('live_allocated', 0)} / playback {stats.get('playback_allocated', 0)})",
                "" if allocated < 8000 else "SSRC 余量不足(接近耗尽会导致点播 503):重启服务清理泄漏,并升级到包含 SSRC 对账修复的版本。",
                "" if allocated < 8000 else "SSRC capacity nearly exhausted (exhaustion causes 503 on play): restart the service and upgrade to a build with SSRC reconciliation.",
                severity=("ok" if allocated < 8000 else "warn"),
            )
        )
    except Exception as e:
        logger.debug(f"diagnose-play ssrc stats failed: {e}")

    return _diag_verdict(items)


def _diag_verdict(items: list[dict]) -> dict:
    """汇总判定:fail 阻塞播放,warn 仅提示。"""
    blockers = [i for i in items if i.get("severity") == "fail"]
    warnings = [i for i in items if i.get("severity") == "warn"]
    if blockers:
        verdict_zh = f"发现 {len(blockers)} 个阻塞项,按下方提示修复后重试"
        verdict_en = f"{len(blockers)} blocking issue(s) found; fix per the hints below and retry"
    elif warnings:
        verdict_zh = "链路可用,但有需要注意事项"
        verdict_en = "Play path usable, with warnings"
    else:
        verdict_zh = "各项检查通过,可正常点播;若仍失败请附本报告提交 issue"
        verdict_en = "All checks passed; if playback still fails, attach this report to an issue"
    return {
        "verdict": "blocked" if blockers else ("warning" if warnings else "ok"),
        "verdict_text": {"zh": verdict_zh, "en": verdict_en},
        "blockers": [i["key"] for i in blockers],
        "items": items,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
