from __future__ import annotations

import re
import ipaddress
import time
import os
from loguru import logger

from app.core.config import settings


_RE_KEY_VALUE = re.compile(r"^([a-zA-Z])=(.*)$")

_UNSAFE_IPS = {
    "0.0.0.0", "127.0.0.1", "255.255.255.255",
    "::", "::1",
}


def _validate_sdp_connection_ip(ip: str) -> str | None:
    try:
        addr = ipaddress.ip_address(ip)
        if ip in _UNSAFE_IPS or addr.is_multicast or addr.is_reserved or addr.is_loopback:
            return None
    except ValueError:
        return None
    return ip


def parse_sdp(body: str, fallback_ip: str | None = None) -> dict:
    # Sanitizer: 兼容没有 \r 只有 \n 的情况，兼容多余空格
    text = (body or "").replace("\r\n", "\n").replace("\r", "\n")
    session_ip: str | None = None
    medias: list[dict] = []
    current_media: dict | None = None
    y_ssrc: str | None = None
    session_name: str | None = None

    # Pre-parse to fix missing c= line if fallback_ip is provided
    has_c_line = False
    for line in text.split("\n"):
        if line.strip().lower().startswith("c="):
            has_c_line = True
            break

    if not has_c_line and fallback_ip:
        # Insert a synthetic c= line right after o= line or s= line
        new_lines = []
        inserted = False
        for line in text.split("\n"):
            new_lines.append(line)
            if not inserted and (line.startswith("o=") or line.startswith("s=")):
                new_lines.append(f"c=IN IP4 {fallback_ip}")
                inserted = True
        text = "\n".join(new_lines)

    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        m = _RE_KEY_VALUE.match(line)
        if not m:
            continue
        k = m.group(1).lower()
        v = (m.group(2) or "").strip()
        if k == "c":
            # Sanitizer: Handle cases where there are multiple spaces like "IN  IP4   192.168.1.1"
            parts = [p for p in v.split() if p]
            if len(parts) >= 3:
                ip = parts[2].strip()
                validated_ip = _validate_sdp_connection_ip(ip)
                if validated_ip is None and ip not in _UNSAFE_IPS:
                    pass  # Allow unresolvable but non-obviously-unsafe IPs for compatibility
                elif validated_ip:
                    ip = validated_ip
                else:
                    ip = fallback_ip or ip  # Fallback for unsafe IPs
                if current_media is None:
                    session_ip = ip
                else:
                    current_media["connection_ip"] = ip
            continue
        if k == "m":
            parts = [p for p in v.split() if p]
            if len(parts) >= 3:
                kind = parts[0].strip().lower()
                try:
                    port = int(parts[1])
                except Exception:
                    port = 0
                proto = parts[2].strip()
                fmts = parts[3:] if len(parts) > 3 else []

                # Sanitizer: Some weird devices send "RTP/AVP/TCP" instead of "TCP/RTP/AVP"
                if "TCP" in proto.upper() and proto.upper() != "TCP/RTP/AVP":
                    proto = "TCP/RTP/AVP"

                current_media = {
                    "type": kind,
                    "port": port,
                    "proto": proto,
                    "formats": fmts,
                    "setup": None,
                    "connection_ip": None,
                    "rtpmap": {},
                    "fmtp": {},
                }
                # GB9 SDP port=0处理 — RFC 4566 Section 5.14 port=0表示拒绝媒体流
                if port == 0:
                    current_media["rejected"] = True
                medias.append(current_media)
            continue
        if k == "a" and current_media is not None:
            if v.lower().startswith("setup:"):
                current_media["setup"] = v.split(":", 1)[1].strip().lower()
            elif v.lower().startswith("rtpmap:"):
                # Parse rtpmap:96 PS/90000 or rtpmap:96 H264/90000
                rtpmap_str = v.split(":", 1)[1].strip()
                parts = rtpmap_str.split()
                if len(parts) >= 2:
                    pt = parts[0].strip()
                    encoding = parts[1].strip()
                    clock_rate = parts[2].strip() if len(parts) > 2 else "8000"
                    current_media.setdefault("rtpmap", {})[pt] = {
                        "encoding": encoding,
                        "clock_rate": clock_rate,
                    }
            # GB9 SDP fmtp解析 — H264 profile兼容性检测
            elif v.lower().startswith("fmtp:"):
                fmtp_str = v.split(":", 1)[1].strip()
                fmtp_parts = fmtp_str.split(None, 1)
                if len(fmtp_parts) >= 2:
                    pt = fmtp_parts[0].strip()
                    params_str = fmtp_parts[1].strip()
                    params = {}
                    for item in params_str.split(";"):
                        item = item.strip()
                        if "=" in item:
                            k2, _, v2 = item.partition("=")
                            params[k2.strip()] = v2.strip()
                        elif item:
                            params[item] = ""
                    current_media.setdefault("fmtp", {})[pt] = params
            continue
        if k == "y":
            y_ssrc = v.strip()
            # W-17 SDP y=行SSRC格式校验，非10位纯数字则忽略避免后续流匹配错误
            if y_ssrc and (not y_ssrc.isdigit() or len(y_ssrc) != 10):
                logger.warning(f"SDP y= line SSRC format invalid (expected 10 digits): '{y_ssrc}'")
                y_ssrc = ""
            continue
        if k == "s":
            session_name = v.strip()
            continue

    for md in medias:
        if not md.get("connection_ip"):
            md["connection_ip"] = session_ip

    # Sanitizer: Final fallback for session IP
    if not session_ip and fallback_ip:
        session_ip = fallback_ip
        for md in medias:
            if not md.get("connection_ip"):
                md["connection_ip"] = fallback_ip

    # GB9 SDP fmtp解析 — 收集所有媒体流的fmtp参数
    fmtp_params: dict[int, dict[str, str]] = {}
    for i, md in enumerate(medias):
        if md.get("fmtp"):
            for pt, params in md["fmtp"].items():
                fmtp_params[int(pt)] = params

    return {
        "connection_ip": session_ip,
        "medias": medias,
        "ssrc": y_ssrc,
        "session_name": session_name,
        "fmtp_params": fmtp_params,
    }


def pick_media(parsed: dict, media_type: str) -> dict | None:
    want = (media_type or "").strip().lower()
    for md in parsed.get("medias") or []:
        if str(md.get("type") or "").lower() == want:
            return md
    return (parsed.get("medias") or [None])[0]


def is_tcp_profile(proto: str | None) -> bool:
    p = (proto or "").upper()
    return "TCP" in p


def opposite_setup(setup: str | None) -> str | None:
    v = (setup or "").strip().lower()
    if v == "active":
        return "passive"
    if v == "passive":
        return "active"
    return None


def build_sdp(
    *,
    origin_id: str,
    session_name: str,
    connection_ip: str,
    media_type: str = "video",
    media_port: int = 0,
    media_profile: str = "RTP/AVP",
    direction: str = "recvonly",
    ssrc: str = "",
    setup: str | None = None,
    time_range: str = "0 0",
    u_line: str = "",
    download_speed: int | None = None,
    f_line: str = "",
    payload_types: list[int] | None = None,
    extended_rtpmap: bool = True,
    track: str | None = None,
) -> str:
    lines: list[str] = []
    lines.append("v=0")
    _session_id = f"{int(time.time() * 1000)}{os.getpid() % 10000:04d}"
    lines.append(f"o={origin_id} {_session_id} {_session_id} IN IP4 {connection_ip}")
    lines.append(f"s={session_name}")
    if u_line:
        lines.append(u_line)
    lines.append(f"c=IN IP4 {connection_ip}")
    lines.append(f"t={time_range}")

    if payload_types is None:
        payload_types = [96, 126, 125, 99, 34, 98, 97] if extended_rtpmap else [96, 98, 97]
    pt_str = " ".join(str(pt) for pt in payload_types)
    lines.append(f"m={media_type} {int(media_port)} {media_profile} {pt_str}")
    lines.append(f"a={direction}")

    # GB9 SDP GB28181必需属性 — a=tool 和 a=type
    sdp_lines_append_tool = True
    if sdp_lines_append_tool:
        lines.append(f"a=tool:{getattr(settings, 'PROJECT_NAME', 'PyGBSentry')}")
    # a=type depends on stream type (broadcast/individual)
    if direction == "recvonly":
        lines.append("a=type:broadcast")
    else:
        lines.append("a=type:individual")

    if setup:
        lines.append(f"a=setup:{setup}")
        lines.append("a=connection:new")

    if extended_rtpmap:
        lines.append("a=rtpmap:96 PS/90000")
        lines.append("a=fmtp:126 profile-level-id=42e01e")
        lines.append("a=rtpmap:126 H264/90000")
        lines.append("a=rtpmap:125 H264S/90000")
        lines.append("a=fmtp:125 profile-level-id=42e01e")
        lines.append("a=rtpmap:99 H265/90000")
        lines.append("a=fmtp:99 profile-level-id=1")  # H265 fmtp参数，GB/T 28181附录F.3要求声明profile-level-id
        lines.append("a=rtpmap:98 H264/90000")
        lines.append("a=rtpmap:97 MPEG4/90000")
    else:
        lines.append("a=rtpmap:96 PS/90000")
        lines.append("a=rtpmap:99 H265/90000")  # 非扩展模式也包含H265声明
        lines.append("a=fmtp:99 profile-level-id=1")  # H265 fmtp参数
        lines.append("a=rtpmap:98 H264/90000")
        lines.append("a=rtpmap:97 MPEG4/90000")

    if download_speed is not None:
        lines.append(f"a=downloadspeed:{download_speed}")

    # GB28181-2022 SDP 添加 a=track 行标识媒体轨道类型
    if track:
        lines.append(f"a=track:{track}")

    ssrc_str = str(ssrc).zfill(10)
    lines.append(f"y={ssrc_str}")
    if f_line:
        lines.append(f_line)

    return "\r\n".join(lines) + "\r\n"

