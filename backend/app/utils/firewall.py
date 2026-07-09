"""Best-effort firewall port management.

On Linux this configures ``iptables``/``ufw``/``firewalld`` rules for the SIP
and media ports the platform listens on. On Windows or when no firewall tool
is available it logs a notice and returns without raising — firewall setup is
an operational convenience, never a startup blocker.
"""
from __future__ import annotations

import shutil
import subprocess
from typing import Iterable

from loguru import logger

from app.core.config import settings


def _ports_to_open() -> list[int]:
    ports: set[int] = set()
    sip_port = int(getattr(settings, "SIP_PORT", 5060) or 5060)
    ports.add(sip_port)
    media_http = int(getattr(settings, "MEDIA_SERVER_HTTP_PORT", 80) or 80)
    if media_http:
        ports.add(media_http)
    media_rtsp = int(getattr(settings, "MEDIA_SERVER_RTSP_PORT", 554) or 554)
    if media_rtsp:
        ports.add(media_rtsp)
    media_rtmp = int(getattr(settings, "MEDIA_SERVER_RTMP_PORT", 1935) or 1935)
    if media_rtmp:
        ports.add(media_rtmp)
    rtp_proxy = int(getattr(settings, "MEDIA_SERVER_RTP_PROXY_PORT", 10000) or 10000)
    if rtp_proxy:
        ports.add(rtp_proxy)
    backend_port = int(getattr(settings, "BACKEND_PUBLIC_PORT", 8000) or 8000)
    if backend_port:
        ports.add(backend_port)
    return sorted(ports)


def _open_with_ufw(ports: Iterable[int]) -> bool:
    if not shutil.which("ufw"):
        return False
    for p in ports:
        try:
            subprocess.run(
                ["ufw", "allow", str(p)],
                check=False,
                capture_output=True,
                timeout=10,
            )
        except Exception as e:
            logger.debug(f"firewall: ufw allow {p} failed: {e}")
    return True


def _open_with_firewalld(ports: Iterable[int]) -> bool:
    if not shutil.which("firewall-cmd"):
        return False
    for p in ports:
        try:
            subprocess.run(
                ["firewall-cmd", "--add-port={}/udp".format(p), "--permanent"],
                check=False, capture_output=True, timeout=10,
            )
            subprocess.run(
                ["firewall-cmd", "--add-port={}/tcp".format(p), "--permanent"],
                check=False, capture_output=True, timeout=10,
            )
        except Exception as e:
            logger.debug(f"firewall: firewalld allow {p} failed: {e}")
    try:
        subprocess.run(["firewall-cmd", "--reload"], check=False, capture_output=True, timeout=15)
    except Exception as e:
        logger.debug(f"firewall: firewalld reload failed: {e}")
    return True


def ensure_firewall_ports() -> None:
    """Open required platform ports in the host firewall (best-effort)."""
    ports = _ports_to_open()
    if not ports:
        return
    logger.info(f"firewall: ensuring ports {ports} are open")
    if _open_with_ufw(ports):
        return
    if _open_with_firewalld(ports):
        return
    # iptables fallback
    if shutil.which("iptables"):
        for p in ports:
            try:
                subprocess.run(
                    ["iptables", "-I", "INPUT", "-p", "tcp", "--dport", str(p), "-j", "ACCEPT"],
                    check=False, capture_output=True, timeout=10,
                )
                subprocess.run(
                    ["iptables", "-I", "INPUT", "-p", "udp", "--dport", str(p), "-j", "ACCEPT"],
                    check=False, capture_output=True, timeout=10,
                )
            except Exception as e:
                logger.debug(f"firewall: iptables allow {p} failed: {e}")
        return
    logger.warning(
        "firewall: no supported firewall tool found (ufw/firewalld/iptables); "
        "ensure ports are open manually"
    )
