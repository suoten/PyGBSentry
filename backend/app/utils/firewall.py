from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass

from loguru import logger

from app.core.config import settings


@dataclass(frozen=True)
class PortRule:
    port: int
    proto: str  # "tcp" | "udp"
    desc: str


def _parse_range(text: str) -> tuple[int, int] | None:
    raw = (text or "").strip()
    if not raw or "-" not in raw:
        return None
    a, b = raw.split("-", 1)
    try:
        start = int(a.strip())
        end = int(b.strip())
        if start <= 0 or end <= 0 or end < start:
            return None
        return start, end
    except Exception:
        return None


def build_required_port_rules() -> tuple[list[PortRule], tuple[int, int] | None]:
    """
    返回 (离散端口规则, RTP范围)。
    - 离散端口：后端API、SIP、ZLM的 HTTP/RTSP/RTMP（若启用）
    - RTP范围：优先 MEDIA_SERVER_RTP_PROXY_PORT_RANGE（如 30000-39000）
    """
    rules: list[PortRule] = []

    # Backend API (给运维中心/Hook回调等)
    rules.append(PortRule(settings.BACKEND_PUBLIC_PORT, "tcp", "Backend API"))

    # SIP（GB28181 注册/信令）
    rules.append(PortRule(settings.SIP_PORT, "udp", "SIP (GB28181)"))
    rules.append(PortRule(settings.SIP_PORT, "tcp", "SIP (GB28181)"))

    # ZLM/MediaServer（若你在该机上跑内置或外置同机）
    rules.append(PortRule(settings.MEDIA_SERVER_HTTP_PORT, "tcp", "ZLM HTTP API/Play"))
    rules.append(PortRule(settings.MEDIA_SERVER_RTSP_PORT, "tcp", "ZLM RTSP"))
    rules.append(PortRule(settings.MEDIA_SERVER_RTMP_PORT, "tcp", "ZLM RTMP"))
    rules.append(PortRule(settings.MEDIA_SERVER_RTC_PORT, "udp", "ZLM WebRTC (RTC UDP)"))
    rules.append(PortRule(settings.MEDIA_SERVER_RTC_TCP_PORT, "tcp", "ZLM WebRTC (RTC TCP)"))

    rtp_range = _parse_range(str(settings.MEDIA_SERVER_RTP_PROXY_PORT_RANGE or ""))
    if not rtp_range:
        # 兜底：单端口（历史行为）
        p = settings.MEDIA_SERVER_RTP_PROXY_PORT
        rtp_range = (p, p)

    # 去重、过滤非法
    uniq: dict[tuple[int, str], PortRule] = {}
    for r in rules:
        if r.port <= 0 or r.port > 65535:
            continue
        key = (int(r.port), r.proto.lower())
        uniq[key] = PortRule(int(r.port), r.proto.lower(), r.desc)

    return list(uniq.values()), rtp_range


def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
        return 0, out.strip()
    except subprocess.CalledProcessError as e:
        return int(e.returncode or 1), (e.output or "").strip()
    except Exception as e:
        return 1, str(e)


def _has_cmd(name: str) -> bool:
    code, _ = _run(["/usr/bin/which", name])
    return code == 0


def ensure_firewall_ports() -> None:
    """
    启动时调用：
    - 总是打印“需要放行的端口 + 安全组提示”
    - 若 AUTO_OPEN_PORTS=true，则在 Linux 上 best-effort 尝试放行（ufw/firewalld）
    """
    rules, rtp = build_required_port_rules()

    # 1) 打印放行清单（含安全组提示）
    tcp_ports = sorted({r.port for r in rules if r.proto == "tcp"})
    udp_ports = sorted({r.port for r in rules if r.proto == "udp"})
    logger.warning(
        "Network ports required: tcp={tcp}, udp={udp}, rtp_udp_range={rtp}. "
        "IMPORTANT: if you are on cloud/VPS, also allow these in Security Group / Firewall rules.",
        tcp=tcp_ports,
        udp=udp_ports,
        rtp=(f"{rtp[0]}-{rtp[1]}" if rtp else "n/a"),
    )

    # 2) 可选：自动放行（只在 Linux）
    if not settings.AUTO_OPEN_PORTS:
        return
    if platform.system() != "Linux":
        logger.warning("AUTO_OPEN_PORTS is enabled but current OS is not Linux. Skip auto firewall changes.")
        return

    dry_run = settings.AUTO_OPEN_PORTS_DRY_RUN
    provider = str(settings.AUTO_OPEN_PORTS_PROVIDER or "auto").strip().lower()

    # ufw
    if provider in {"auto", "ufw"} and _has_cmd("ufw"):
        logger.warning("AUTO_OPEN_PORTS: using ufw (dry_run={dry_run})", dry_run=dry_run)
        cmds: list[list[str]] = []
        for r in rules:
            cmds.append(["ufw", "allow", f"{r.port}/{r.proto}"])
        if rtp:
            cmds.append(["ufw", "allow", f"{rtp[0]}:{rtp[1]}/udp"])
        if dry_run:
            for c in cmds:
                logger.warning("AUTO_OPEN_PORTS (dry-run): {cmd}", cmd=" ".join(c))
            return
        for c in cmds:
            code, out = _run(c)
            if code != 0:
                logger.warning("AUTO_OPEN_PORTS ufw failed: {cmd} | {out}", cmd=" ".join(c), out=out)
        return

    # firewalld
    if provider in {"auto", "firewalld"} and _has_cmd("firewall-cmd"):
        logger.warning("AUTO_OPEN_PORTS: using firewalld (dry_run={dry_run})", dry_run=dry_run)
        cmds = []
        for r in rules:
            cmds.append(["firewall-cmd", "--permanent", f"--add-port={r.port}/{r.proto}"])
        if rtp:
            cmds.append(["firewall-cmd", "--permanent", f"--add-port={rtp[0]}-{rtp[1]}/udp"])
        cmds.append(["firewall-cmd", "--reload"])
        if dry_run:
            for c in cmds:
                logger.warning("AUTO_OPEN_PORTS (dry-run): {cmd}", cmd=" ".join(c))
            return
        for c in cmds:
            code, out = _run(c)
            if code != 0:
                logger.warning("AUTO_OPEN_PORTS firewalld failed: {cmd} | {out}", cmd=" ".join(c), out=out)
        return

    logger.warning(
        "AUTO_OPEN_PORTS enabled but no supported firewall tool found (ufw/firewalld). "
        "Please open ports manually and also in Security Group."
    )

