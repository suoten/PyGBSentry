"""SDP 解析与构造（RFC 4566 + GB28181 扩展）。

提供 GB28181 SIP 信令中 INVITE/200 OK 报文携带的 SDP（Session Description
Protocol）的解析与构造能力。

GB28181 在 RFC 4566 基础上扩展了两条非标准属性行：
    * ``y=<ssrc>``  —— 10 位十进制 SSRC（首位 0=实时流，1=回放流；2-6 位为
      域编码前缀；7-10 位为序号）。
    * ``f=<format>`` —— 媒体格式描述（如 ``f=v/2/4/25`` 表示视频 H.264 主码流
      4M 25fps）。

主要 API：
    * :func:`build_sdp` —— 按 GB28181 约定构造 SDP 字符串。
    * :func:`parse_sdp` —— 解析 SDP 文本为字典（含 ``medias`` 列表）。
    * :func:`pick_media` —— 从解析结果中按媒体类型（video/audio）取出媒体描述。
    * :func:`is_tcp_profile` —— 判断媒体 proto 是否为 TCP 传输。
    * :func:`opposite_setup` —— TCP 主动/被动模式翻转（用于 INVITE/200 OK 协商）。
"""
from __future__ import annotations

import re
from typing import Optional

from loguru import logger


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# GB28181 常用 payload type
# 96: PS, 98: H264, 26: JPEG, 8: PCMA(G.711a), 0: PCMU(G.711u)
_DEFAULT_VIDEO_PTS = "96 98"
_DEFAULT_AUDIO_PTS = "8"

# TCP 传输相关的 profile 前缀（RFC 4571 / GB28181）
_TCP_PROFILE_TOKENS = ("TCP", "TLS", "SCTP")

# setup 协商：INVITE 端与 200 OK 端的 setup 必须互补
_SETUP_OPPOSITE = {
    "active": "passive",
    "passive": "active",
    "actpass": "active",
    "holdconn": "passive",
}


# ---------------------------------------------------------------------------
# 解析
# ---------------------------------------------------------------------------

# 媒体行：m=<type> <port> <proto> <fmt...>
_M_LINE_RE = re.compile(r"^m=(\S+)\s+(\d+)\s+(\S+)\s+(.*)$")
# 连接行：c=IN IP4 <ip>  (也可能带 TTL / 数量后缀)
_C_LINE_RE = re.compile(r"^c=IN\s+IP[46]\s+([0-9a-fA-F\.:]+)", re.IGNORECASE)
# 属性行：a=<attr> 或 a=<attr>:<value>
_A_LINE_RE = re.compile(r"^a=([^:]+)(?::(.*))?$")
# o=<username> <sess-id> <sess-version> IN IP4 <addr>
_O_LINE_RE = re.compile(
    r"^o=(\S+)\s+(\S+)\s+(\S+)\s+IN\s+IP[46]\s+([0-9a-fA-F\.:]+)", re.IGNORECASE
)


def parse_sdp(sdp_text: str, fallback_ip: str = "") -> dict:
    """解析 SDP 文本为字典。

    返回结构示例::

        {
            "version": 0,
            "origin": {"username": "...", "sess_id": "...", "sess_version": "...", "addr": "..."},
            "session_name": "Play",
            "connection_ip": "1.2.3.4",   # 会话级 c= 行 IP
            "u_line": "...",
            "time_range": "0 0",
            "attributes": ["recvonly", "rtpmap:96 PS/90000"],
            "medias": [
                {
                    "media_type": "video",
                    "port": 5000,
                    "proto": "RTP/AVP",
                    "formats": ["96", "98"],
                    "connection_ip": "1.2.3.4",  # 媒体级 c=，缺省回退会话级
                    "direction": "recvonly",
                    "setup": "active",           # 无则 None
                    "connection_mode": "new",    # a=connection:new 的值，无则 None
                    "ssrc": "0123456789",        # y= 行
                    "f_line": "f=v/2/4/25",      # f= 行
                    "download_speed": "1",       # a=downloadspeed: 的值
                    "rtpmap": {"96": "PS/90000", "98": "H264/90000"},
                    "attributes": ["recvonly", "setup:active", ...],
                }
            ],
        }

    解析容错：无法识别的行被忽略并记 debug 日志。``fallback_ip`` 在会话级
    与媒体级 ``c=`` 均缺失时作为 ``connection_ip`` 兜底。
    """
    result: dict = {
        "version": 0,
        "origin": {},
        "session_name": "",
        "connection_ip": "",
        "u_line": "",
        "time_range": "",
        "attributes": [],
        "medias": [],
    }

    if not sdp_text:
        result["connection_ip"] = fallback_ip
        return result

    if isinstance(sdp_text, bytes):
        sdp_text = sdp_text.decode("utf-8", errors="ignore")

    lines = sdp_text.replace("\r\n", "\n").split("\n")
    current_media: dict | None = None

    def _ensure_media() -> dict:
        nonlocal current_media
        if current_media is None:
            current_media = _new_media_dict()
            result["medias"].append(current_media)
        return current_media

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if len(line) < 2 or line[1] != "=":
            continue
        prefix = line[0]
        value = line[2:]

        if prefix == "v":
            try:
                result["version"] = int(value.strip())
            except ValueError:
                logger.debug("swallowed_exception", exc_info=True)
        elif prefix == "o":
            m = _O_LINE_RE.match(line)
            if m:
                result["origin"] = {
                    "username": m.group(1),
                    "sess_id": m.group(2),
                    "sess_version": m.group(3),
                    "addr": m.group(4),
                }
        elif prefix == "s":
            result["session_name"] = value.strip()
        elif prefix == "u":
            result["u_line"] = value.strip()
        elif prefix == "c":
            m = _C_LINE_RE.match(line)
            ip = m.group(1) if m else ""
            if ip:
                if current_media is not None:
                    current_media["connection_ip"] = ip
                else:
                    result["connection_ip"] = ip
        elif prefix == "t":
            result["time_range"] = value.strip()
        elif prefix == "m":
            # 新建一个媒体描述
            current_media = _new_media_dict()
            result["medias"].append(current_media)
            m = _M_LINE_RE.match(line)
            if m:
                current_media["media_type"] = m.group(1).lower()
                try:
                    current_media["port"] = int(m.group(2))
                except ValueError:
                    current_media["port"] = 0
                current_media["proto"] = m.group(3)
                current_media["formats"] = [f for f in m.group(4).split() if f]
            else:
                # 兜底：按空白拆分
                parts = value.split()
                if len(parts) >= 4:
                    current_media["media_type"] = parts[0].lower()
                    try:
                        current_media["port"] = int(parts[1])
                    except ValueError:
                        logger.debug("swallowed_exception", exc_info=True)
                    current_media["proto"] = parts[2]
                    current_media["formats"] = parts[3:]
        elif prefix == "a":
            _consume_attribute(value, current_media, result)
        elif prefix == "y":
            # GB28181 SSRC 行（非 RFC 4566 标准属性，单独前缀）
            media = _ensure_media()
            media["ssrc"] = value.strip()
        elif prefix == "f":
            # GB28181 媒体格式描述行
            media = _ensure_media()
            media["f_line"] = value.strip()
        else:
            logger.debug(f"parse_sdp: ignored line: {line!r}")

    # 会话级 c= 兜底回退
    if not result["connection_ip"]:
        result["connection_ip"] = fallback_ip
    # 媒体级 c= 兜底回退到会话级
    session_ip = result["connection_ip"]
    for md in result["medias"]:
        if not md.get("connection_ip"):
            md["connection_ip"] = session_ip
    return result


def _new_media_dict() -> dict:
    return {
        "media_type": "",
        "port": 0,
        "proto": "RTP/AVP",
        "formats": [],
        "connection_ip": "",
        "direction": "",
        "setup": None,
        "connection_mode": None,
        "ssrc": "",
        "f_line": "",
        "download_speed": None,
        "rtpmap": {},
        "attributes": [],
    }


def _consume_attribute(value: str, current_media: dict | None, result: dict) -> None:
    """处理 ``a=<attr>[:<val>]`` 行。

    若处于媒体段内则同时写入媒体字典；否则写入会话级 attributes。
    """
    # 手动拆分 attr / val（比正则更稳，且能处理值中含冒号的情况）
    if ":" in value:
        attr, _, val = value.partition(":")
        attr = attr.strip()
        val = val.strip()
    else:
        attr = value.strip()
        val = ""

    # 媒体级属性
    if current_media is not None:
        current_media["attributes"].append(value.strip())
        if attr in ("sendonly", "recvonly", "sendrecv", "inactive"):
            current_media["direction"] = attr
        elif attr == "setup":
            current_media["setup"] = val
        elif attr == "connection":
            current_media["connection_mode"] = val
        elif attr == "rtpmap":
            # a=rtpmap:<pt> <encoding>
            parts = val.split(None, 1)
            if len(parts) == 2:
                current_media["rtpmap"][parts[0]] = parts[1]
        elif attr == "downloadspeed":
            current_media["download_speed"] = val
        elif attr == "ssrc":
            # 标准 RFC 5576 a=ssrc:<id> <attr>:<val>，部分设备用此格式
            # 这里仅保留首个 token 作为 ssrc（仅当 y= 行未设置时回退）
            if val and not current_media.get("ssrc"):
                current_media["ssrc"] = val.split()[0]
    else:
        # 会话级属性
        result["attributes"].append(value.strip())


# ---------------------------------------------------------------------------
# 媒体选择
# ---------------------------------------------------------------------------

def pick_media(parsed: dict, media_type: str) -> Optional[dict]:
    """从 :func:`parse_sdp` 结果中按媒体类型取出第一条媒体描述。

    ``media_type`` 不区分大小写（``"video"``/``"audio"``）。若没有精确匹配且
    只有一条媒体，则返回该条（兼容某些设备把视频放在 audio 段的异常情况）。
    找不到返回 ``None``。
    """
    if not parsed:
        return None
    medias = parsed.get("medias") or []
    if not medias:
        return None
    want = (media_type or "").strip().lower()
    for md in medias:
        if (md.get("media_type") or "").lower() == want:
            return md
    # 回退：若仅有一条媒体，返回它
    if len(medias) == 1:
        return medias[0]
    return None


def is_tcp_profile(profile: str) -> bool:
    """判断媒体 proto 是否为 TCP 传输（如 ``TCP/RTP/AVP``、``TCP/RTP/AVPF``）。"""
    if not profile:
        return False
    upper = profile.upper()
    for tok in _TCP_PROFILE_TOKENS:
        if upper.startswith(tok):
            return True
    return False


def opposite_setup(setup: str) -> str:
    """返回与给定 setup 互补的 setup 值（用于 INVITE/200 OK 协商）。

    ``active`` <-> ``passive``；``actpass`` -> ``active``；未知值回退 ``passive``。
    """
    key = (setup or "").strip().lower()
    return _SETUP_OPPOSITE.get(key, "passive")


# ---------------------------------------------------------------------------
# 构造
# ---------------------------------------------------------------------------

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
    setup: Optional[str] = None,
    time_range: Optional[str] = None,
    u_line: Optional[str] = None,
    download_speed: Optional[int] = None,
    f_line: Optional[str] = None,
    extended_rtpmap: bool = True,
    track: Optional[str] = None,
) -> str:
    """按 GB28181 约定构造 SDP 字符串。

    参数说明：
        * ``origin_id`` —— ``o=`` 行的用户名（GB28181 通常放通道 ID / 设备 ID）。
        * ``connection_ip`` —— ``c=`` 行 IP（会话级，同时用于媒体级）。
        * ``media_profile`` —— ``m=`` 行 proto，如 ``RTP/AVP``/``TCP/RTP/AVP``。
        * ``direction`` —— ``a=recvonly``/``a=sendonly``/``a=sendrecv``。
        * ``ssrc`` —— GB28181 ``y=`` 行的 10 位 SSRC。
        * ``setup`` —— TCP 主动/被动（``active``/``passive``），仅 TCP profile 时有意义。
        * ``time_range`` —— ``t=`` 行（回放场景传 ``<start> <end>``，实时传 ``"0 0"``）。
        * ``f_line`` —— GB28181 ``f=`` 行。
        * ``extended_rtpmap`` —— 是否追加 ``a=rtpmap:96 PS/90000`` 等映射（视频默认 True）。
        * ``track`` —— 通道/码流标识（部分设备放 ``a=track:<id>``）。

    缺省 ``time_range`` 为 ``"0 0"``（实时流）。``media_port`` 为 0 时仍写入，
    由调用方保证端口正确。
    """
    if not connection_ip:
        logger.warning("build_sdp: connection_ip is empty, SDP will be invalid")

    lines: list[str] = []
    # v=0
    lines.append("v=0")
    # o=<username> <sess-id> <sess-version> IN IP4 <addr>
    # GB28181: sess-id/sess-version 通常用 0，username 放通道ID
    lines.append(f"o={origin_id or '0'} 0 0 IN IP4 {connection_ip}")
    # s=<session>
    lines.append(f"s={session_name or 'Play'}")
    if u_line:
        lines.append(f"u={u_line}")
    # c=IN IP4 <ip>
    lines.append(f"c=IN IP4 {connection_ip}")
    # t=<start> <end>
    lines.append(f"t={time_range or '0 0'}")

    # m=<type> <port> <proto> <fmt>
    media_type = (media_type or "video").lower()
    fmts = _DEFAULT_VIDEO_PTS if media_type == "video" else _DEFAULT_AUDIO_PTS
    lines.append(f"m={media_type} {int(media_port or 0)} {media_profile or 'RTP/AVP'} {fmts}")

    # a= direction
    direction = (direction or "recvonly").strip().lower()
    if direction:
        lines.append(f"a={direction}")

    # a=rtpmap (extended)
    if extended_rtpmap:
        if media_type == "video":
            lines.append("a=rtpmap:96 PS/90000")
            lines.append("a=rtpmap:98 H264/90000")
        else:
            lines.append("a=rtpmap:8 PCMA/8000")

    # a=setup / a=connection:new (TCP)
    if is_tcp_profile(media_profile or ""):
        if setup:
            lines.append(f"a=setup:{setup}")
        # GB28181 TCP 模式通常携带 a=connection:new
        lines.append("a=connection:new")

    # a=downloadspeed
    if download_speed is not None:
        try:
            lines.append(f"a=downloadspeed:{int(download_speed)}")
        except (ValueError, TypeError):
            logger.debug("swallowed_exception", exc_info=True)

    # a=track
    if track:
        lines.append(f"a=track:{track}")

    # y=<ssrc>  (GB28181)
    if ssrc:
        lines.append(f"y={ssrc}")

    # f=<f_line> (GB28181)
    if f_line:
        lines.append(f"f={f_line}")

    return "\r\n".join(lines) + "\r\n"
