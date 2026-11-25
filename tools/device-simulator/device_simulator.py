#!/usr/bin/env python3
"""PyGBSentry 内置 GB28181 设备模拟器（纯 Python，零第三方依赖）。

模拟 GB28181 IPC/NVR：
    * REGISTER（Digest 认证：qop=auth / 无 qop、MD5 / SHA-256 / MD5-sess，
      与平台 auth.py 的 RFC 2617 实现兼容）
    * Keepalive 心跳（SN 以毫秒时间戳低位起步，重启不回退，
      兼容平台 Keepalive SN 单调性校验）
    * Catalog / DeviceInfo / DeviceStatus 查询响应（兼容平台 catalog.py
      的 SumNum / DeviceList@Num 解析约定）
    * INVITE 点播：SDP 协商（y=SSRC 回显 / f= 回显 / TCP setup 翻转），
      ACK 后向 SDP 目标发送 RTP 封装的 PS 流（UDP 直发；
      TCP 平台被动→设备主动连接；TCP 平台主动→设备监听，RFC 4571 帧式）
    * BYE 停流、DeviceControl(PTZ) 等 MESSAGE 一律 200 OK

PS 流由 ffmpeg 在启动时生成（testsrc2 测试卡），按 PS 包起始码 0x000001BA
切片，逐包按 fps 节拍实时发送。没有摄像头也能跑通平台全链路。

直接运行（docker 之外）：
    python device_simulator.py --platform 192.168.1.10:5060 \
        --server-id 34020000002000000001 --password 12345678 --count 2
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import random
import re
import secrets
import socket
import struct
import subprocess
import sys
import time
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass
class Config:
    platform_host: str = ""
    platform_port: int = 5060
    server_id: str = "34020000002000000001"
    domain: str = "340200"
    password: str = "12345678"
    device_base: str = "34020000001310000001"
    device_count: int = 2
    channels_per_device: int = 2
    keepalive_interval: int = 60
    register_expires: int = 3600
    fps: int = 25
    ps_file: str = "/tmp/sample.ps"
    media_duration: int = 30
    video_size: str = "704x576"
    tcp_media_base: int = 42000  # TCP 被动模式监听端口（每设备独占 10 个）

    @classmethod
    def from_env(cls) -> "Config":
        def _int(name: str, default: int) -> int:
            try:
                return int(env(name, str(default)) or default)
            except ValueError:
                return default
        return cls(
            platform_host=env("PLATFORM_HOST", "host.docker.internal"),
            platform_port=_int("PLATFORM_PORT", 5060),
            server_id=env("SERVER_ID", "34020000002000000001"),
            domain=env("SIP_DOMAIN", "340200"),
            password=env("DEVICE_PASSWORD", "12345678"),
            device_base=env("DEVICE_ID_BASE", "34020000001310000001"),
            device_count=_int("DEVICE_COUNT", 2),
            channels_per_device=_int("CHANNELS_PER_DEVICE", 2),
            keepalive_interval=_int("KEEPALIVE_INTERVAL", 60),
            register_expires=_int("REGISTER_EXPIRES", 3600),
            fps=_int("MEDIA_FPS", 25),
            ps_file=env("PS_FILE", "/tmp/sample.ps"),
            media_duration=_int("MEDIA_DURATION", 30),
            video_size=env("MEDIA_SIZE", "704x576"),
        )


# ---------------------------------------------------------------------------
# 最小 SIP 解析
# ---------------------------------------------------------------------------

_HEADER_SPLIT = re.compile(r"\r\n|\n")


@dataclass
class SipMsg:
    is_request: bool
    method: str = ""
    cseq_num: int = 0
    call_id: str = ""
    headers: list = None  # type: ignore[assignment]
    body: str = ""
    from_hdr: str = ""
    to_hdr: str = ""
    via: str = ""

    def header(self, name: str) -> str:
        name = name.lower()
        for k, v in self.headers or []:
            if k.lower() == name:
                return v
        return ""


def parse_sip(data: bytes) -> SipMsg | None:
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception:
        return None
    if "\r\n\r\n" in text:
        head, body = text.split("\r\n\r\n", 1)
    elif "\n\n" in text:
        head, body = text.split("\n\n", 1)
    else:
        head, body = text, ""
    lines = [ln for ln in _HEADER_SPLIT.split(head) if ln.strip()]
    if not lines:
        return None
    first = lines[0]
    headers: list = []
    last_name = ""
    for line in lines[1:]:
        if line.startswith((" ", "\t")) and headers:
            name, value = headers[-1]
            headers[-1] = (name, value + " " + line.strip())
            continue
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        last_name = name.strip()
        headers.append((last_name, value.strip()))
    msg = SipMsg(is_request=True, headers=headers, body=body)
    for k, v in headers:
        lk = k.lower()
        if lk == "from":
            msg.from_hdr = v
        elif lk == "to":
            msg.to_hdr = v
        elif lk == "via":
            msg.via = msg.via or v
        elif lk == "call-id":
            msg.call_id = v
    if first.startswith("SIP/2.0"):
        msg.is_request = False
        m = re.match(r"SIP/2\.0\s+(\d+)", first)
        msg.method = m.group(1) if m else ""
    else:
        m = re.match(r"(\S+)\s+\S+\s+SIP/2\.0", first)
        if not m:
            return None
        msg.method = m.group(1).upper()
    m = re.match(r"\s*(\d+)\s+(\S+)", msg.header("CSeq"))
    if m:
        msg.cseq_num = int(m.group(1))
        if msg.is_request:
            msg.method = m.group(2).upper()
    return msg


# ---------------------------------------------------------------------------
# Digest 认证（兼容 PyGBSentry backend/app/sip/auth.py）
# ---------------------------------------------------------------------------

_CHALLENGE_PARAM = re.compile(r'(\w+)\s*=\s*(?:"([^"]*)"|([^\s,]+))')


def parse_challenge(header_value: str) -> dict:
    params: dict = {}
    for m in _CHALLENGE_PARAM.finditer(header_value.split("Digest")[-1]):
        key = m.group(1).lower()
        params[key] = m.group(2) if m.group(2) is not None else m.group(3)
    return params


def _digest_hash(algorithm: str, data: str) -> str:
    algo = (algorithm or "MD5").strip().upper()
    if algo.startswith("SHA-256") or algo.startswith("SHA256"):
        return hashlib.sha256(data.encode()).hexdigest()
    return hashlib.md5(data.encode()).hexdigest()


def build_authorization(challenge: dict, method: str, uri: str,
                        username: str, password: str) -> str:
    algorithm = challenge.get("algorithm", "MD5")
    realm = challenge.get("realm", "")
    nonce = challenge.get("nonce", "")
    ha1 = _digest_hash(algorithm, f"{username}:{realm}:{password}")
    cnonce = ""
    if algorithm.upper().endswith("-SESS"):
        cnonce = secrets.token_hex(8)
        ha1 = _digest_hash("MD5", f"{ha1}:{nonce}:{cnonce}")
    # HA2 与 response 必须跟随质询算法（RFC 2617/7616），不能写死 MD5
    ha2 = _digest_hash(algorithm, f"{method}:{uri}")
    qop = challenge.get("qop", "")
    if qop:
        qop_name = "auth" if "auth" in qop.split(",") else qop.split(",")[0].strip()
        nc = "00000001"
        if not cnonce:
            cnonce = secrets.token_hex(8)
        response = _digest_hash(algorithm, f"{ha1}:{nonce}:{nc}:{cnonce}:{qop_name}:{ha2}")
        fields = [
            f'username="{username}"', f'realm="{realm}"', f'nonce="{nonce}"',
            f'uri="{uri}"', f'response="{response}"', f'algorithm={algorithm}',
            f'qop={qop_name}', f'nc={nc}', f'cnonce="{cnonce}"',
        ]
    else:
        response = _digest_hash(algorithm, f"{ha1}:{nonce}:{ha2}")
        fields = [
            f'username="{username}"', f'realm="{realm}"', f'nonce="{nonce}"',
            f'uri="{uri}"', f'response="{response}"', f'algorithm={algorithm}',
        ]
    return "Digest " + ", ".join(fields)


# ---------------------------------------------------------------------------
# 最小 SDP 解析
# ---------------------------------------------------------------------------


def parse_sdp(text: str) -> dict:
    result = {"conn_ip": "", "media_port": 0, "proto": "RTP/AVP",
              "setup": "", "ssrc": "", "f": ""}
    session_ip = ""
    media_ip = ""
    in_media = False
    for line in text.replace("\r\n", "\n").split("\n"):
        line = line.strip()
        if line.startswith("m="):
            in_media = True
            if line.startswith("m=video"):
                parts = line.split()
                if len(parts) >= 4:
                    result["media_port"] = int(parts[1])
                    result["proto"] = parts[2].upper()
        elif line.startswith("c="):
            parts = line.split()
            ip = parts[2].split("/")[0] if len(parts) >= 3 else ""
            if in_media:
                media_ip = media_ip or ip
            else:
                session_ip = session_ip or ip
        elif line.startswith("a=setup:"):
            result["setup"] = line.split(":", 1)[1].strip().lower()
        elif line.startswith("y="):
            result["ssrc"] = line[2:].strip()
        elif line.startswith("f="):
            result["f"] = line[2:].strip()
    result["conn_ip"] = media_ip or session_ip
    return result


# ---------------------------------------------------------------------------
# PS 流生成与切片
# ---------------------------------------------------------------------------


def generate_ps_file(cfg: Config) -> None:
    if os.path.exists(cfg.ps_file) and os.path.getsize(cfg.ps_file) > 100_000:
        return
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", f"testsrc2=size={cfg.video_size}:rate={cfg.fps}",
        "-t", str(cfg.media_duration),
        "-c:v", "libx264", "-preset", "veryfast", "-g", str(cfg.fps),
        "-pix_fmt", "yuv420p", "-b:v", "1500k",
        "-f", "mpeg", cfg.ps_file,
    ]
    print(f"[simulator] 生成测试 PS 流: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def split_ps_packs(data: bytes) -> list[bytes]:
    needle = b"\x00\x00\x01\xba"
    starts = []
    i = 0
    while True:
        i = data.find(needle, i)
        if i < 0:
            break
        starts.append(i)
        i += 4
    if not starts:
        return [data]
    packs = []
    for idx, s in enumerate(starts):
        e = starts[idx + 1] if idx + 1 < len(starts) else len(data)
        packs.append(data[s:e])
    return packs


def rtp_packet(ssrc: int, seq: int, ts: int, payload: bytes, marker: bool) -> bytes:
    b1 = 96 | (0x80 if marker else 0x00)
    return struct.pack("!BBHII", 0x80, b1, seq & 0xFFFF, ts & 0xFFFFFFFF,
                       ssrc & 0xFFFFFFFF) + payload


# ---------------------------------------------------------------------------
# 设备实例
# ---------------------------------------------------------------------------

class _RxProtocol(asyncio.DatagramProtocol):
    """把收到的数据报推进 asyncio.Queue，供收包循环消费。"""

    def __init__(self):
        self.queue: asyncio.Queue = asyncio.Queue()

    def datagram_received(self, data, addr):
        self.queue.put_nowait((data, addr))

    def error_received(self, exc):
        pass


_REASON = {200: "OK", 100: "Trying", 403: "Forbidden", 404: "Not Found",
           486: "Busy Here", 500: "Server Internal Error"}
_TCP_SETUP_OPPOSITE = {"active": "passive", "passive": "active", "actpass": "active"}


class SipDevice:
    def __init__(self, cfg: Config, index: int, packs: list[bytes]):
        self.cfg = cfg
        self.index = index
        self.log = f"[dev{index + 1}]"
        self.packs = packs
        self.device_id = str(int(cfg.device_base) + index)
        # 通道号：类型码换成 132，序号全局限定 0000001..N（跨设备不重叠）
        self.channels = []
        for c in range(cfg.channels_per_device):
            global_seq = index * cfg.channels_per_device + c + 1
            self.channels.append(cfg.device_base[:10] + "132" + f"{global_seq % 10_000_000:07d}")
        self.transport = None
        self.local_addr = ("0.0.0.0", 0)
        self.registered = False
        self.expires = cfg.register_expires
        # SN 单调：毫秒时间戳低位起步，进程重启后不会回退（平台有 SN 单调性校验）
        self.sn = int(time.time() * 1000) % 900_000_000
        self.cseq = 100
        self.call_seq = 0
        self.our_tag = secrets.token_hex(4)
        self.stream_task: asyncio.Task | None = None
        self.stream_call_id = ""
        self.pending_invite: dict | None = None
        self._last_invite_sdp = ""
        self.tcp_server: asyncio.AbstractServer | None = None
        # REGISTER 响应等待
        self._resp_event = asyncio.Event()
        self._resp_code = 0
        self._resp_challenge = ""

    # ---- 生命周期 ----

    async def start(self):
        loop = asyncio.get_running_loop()
        self.rx = _RxProtocol()
        self.transport, _ = await loop.create_datagram_endpoint(
            lambda: self.rx, local_addr=("0.0.0.0", 0))
        sock = self.transport.get_extra_info("socket")
        self.local_addr = sock.getsockname()[:2]
        print(f"{self.log} 设备 {self.device_id} SIP/UDP 绑定 "
              f"{self.local_addr[0]}:{self.local_addr[1]}，通道 {self.channels}")
        asyncio.create_task(self._recv_loop())
        asyncio.create_task(self._register_loop())
        asyncio.create_task(self._keepalive_loop())

    def _local_ip(self) -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((self.cfg.platform_host, self.cfg.platform_port))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    # ---- 收发 ----

    async def _recv_loop(self):
        while True:
            try:
                data, addr = await self.rx.queue.get()
            except Exception:
                await asyncio.sleep(0.5)
                continue
            msg = parse_sip(data)
            if not msg:
                continue
            try:
                await self._dispatch(msg, addr)
            except Exception as e:
                print(f"{self.log} 处理 SIP 消息异常: {e}")

    def _send(self, raw: bytes, addr=None):
        self.transport.sendto(raw, addr or (self.cfg.platform_host, self.cfg.platform_port))

    def _build(self, first_line: str, headers: list, body: str = "") -> bytes:
        body_bytes = body.encode("utf-8") if body else b""
        headers = list(headers) + [("Content-Length", str(len(body_bytes)))]
        lines = [first_line] + [f"{k}: {v}" for k, v in headers]
        return ("\r\n".join(lines) + "\r\n\r\n").encode("utf-8") + body_bytes

    def _request(self, method: str, uri: str, body: str = "",
                 extra: list | None = None) -> bytes:
        self.cseq += 1
        via = (f"SIP/2.0/UDP {self.local_addr[0]}:{self.local_addr[1]};rport;"
               f"branch=z9hG4bK{secrets.token_hex(8)}")
        headers = [
            ("Via", via),
            ("From", f"<sip:{self.device_id}@{self.cfg.domain}>;tag={self.our_tag}"),
            ("To", f"<{uri}>"),
            ("Call-ID", f"{self.device_id[-6:]}-{int(time.time())}-{self.call_seq}@sim"),
            ("CSeq", f"{self.cseq} {method}"),
            ("Max-Forwards", "70"),
            ("User-Agent", "PyGBSentry-DeviceSimulator/1.0"),
            ("Contact", f"<sip:{self.device_id}@{self.local_addr[0]}:{self.local_addr[1]}>"),
        ]
        if body:
            headers.append(("Content-Type", "Application/MANSCDP+xml"))
        if extra:
            headers.extend(extra)
        return self._build(f"{method} {uri} SIP/2.0", headers, body)

    async def _respond(self, msg: SipMsg, code: int, body: str = "",
                       extra: list | None = None,
                       content_type: str = "Application/MANSCDP+xml"):
        reason = _REASON.get(code, f"{code} Response")
        to = msg.to_hdr
        if code >= 200 and "tag=" not in to:
            to = to + f";tag={self.our_tag}"
        headers = [
            ("Via", msg.via),
            ("From", msg.from_hdr),
            ("To", to),
            ("Call-ID", msg.call_id),
            ("CSeq", f"{msg.cseq_num} {msg.method}"),
            ("User-Agent", "PyGBSentry-DeviceSimulator/1.0"),
        ]
        if body:
            headers.append(("Content-Type", content_type))
        if extra:
            headers.extend(extra)
        self._send(self._build(f"SIP/2.0 {code} {reason}", headers, body))

    def _new_message_body(self, body: str):
        uri = f"sip:{self.cfg.server_id}@{self.cfg.domain}"
        self._send(self._request("MESSAGE", uri, body=body))

    # ---- 请求分发 ----

    async def _dispatch(self, msg: SipMsg, addr):
        if not msg.is_request:
            self._on_response(msg)
            return
        method = msg.method
        if method == "INVITE":
            await self._on_invite(msg)
        elif method == "ACK":
            self._on_ack(msg)
        elif method == "BYE":
            await self._on_bye(msg)
        elif method == "MESSAGE":
            await self._on_message(msg)
        else:
            await self._respond(msg, 200)

    def _on_response(self, msg: SipMsg):
        try:
            code = int(msg.method)
        except ValueError:
            return
        if code in (200, 401, 403, 423):
            self._resp_code = code
            self._resp_challenge = msg.header("WWW-Authenticate")
            if code == 423:
                me = msg.header("Min-Expires")
                if me.isdigit():
                    self.expires = max(self.expires, int(me))
            self._resp_event.set()

    # ---- 注册 ----

    async def _register_loop(self):
        uri = f"sip:{self.cfg.server_id}@{self.cfg.domain}"
        while True:
            self._resp_event.clear()
            self._send(self._request("REGISTER", uri, extra=[
                ("Expires", str(self.expires)), ("Allow", "INVITE,ACK,CANCEL,BYE,MESSAGE"),
            ]))
            if not await self._wait_event(8.0):
                print(f"{self.log} 注册无响应（检查平台地址 / 网络）")
                await asyncio.sleep(3.0)
                continue
            if self._resp_code == 200:
                self.registered = True
                print(f"{self.log} 注册成功（expires={self.expires}）")
                await asyncio.sleep(max(60, int(self.expires * 0.5)))
                self.registered = False
                continue
            if self._resp_code == 401 and self._resp_challenge:
                auth = build_authorization(
                    parse_challenge(self._resp_challenge), "REGISTER", uri,
                    self.device_id, self.cfg.password)
                self._resp_event.clear()
                self._send(self._request("REGISTER", uri, extra=[
                    ("Expires", str(self.expires)), ("Authorization", auth),
                ]))
                if await self._wait_event(8.0) and self._resp_code == 200:
                    self.registered = True
                    print(f"{self.log} 注册成功（Digest 认证，expires={self.expires}）")
                    await asyncio.sleep(max(60, int(self.expires * 0.5)))
                    self.registered = False
                elif self._resp_code == 403:
                    print(f"{self.log} 认证被拒绝（403）——检查 DEVICE_PASSWORD 与平台设备密码是否一致")
                    await asyncio.sleep(10.0)
                else:
                    await asyncio.sleep(3.0)
                continue
            print(f"{self.log} 注册失败 code={self._resp_code}")
            await asyncio.sleep(3.0)

    async def _wait_event(self, timeout: float) -> bool:
        try:
            await asyncio.wait_for(self._resp_event.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            return False

    # ---- 心跳 ----

    async def _keepalive_loop(self):
        while True:
            await asyncio.sleep(self.cfg.keepalive_interval)
            if not self.registered:
                continue
            self.sn += 1
            body = (
                '<?xml version="1.0" encoding="UTF-8"?>\r\n'
                "<Notify>\r\n<CmdType>Keepalive</CmdType>\r\n"
                f"<SN>{self.sn}</SN>\r\n"
                f"<DeviceID>{self.device_id}</DeviceID>\r\n"
                "<Status>OK</Status>\r\n</Notify>"
            )
            self._new_message_body(body)

    # ---- MESSAGE 查询 ----

    async def _on_message(self, msg: SipMsg):
        await self._respond(msg, 200)
        body = msg.body or ""
        m = re.search(r"<CmdType>([^<]+)</CmdType>", body)
        cmd = m.group(1) if m else ""
        m = re.search(r"<SN>([^<]+)</SN>", body)
        sn = m.group(1) if m else "0"
        if cmd == "Catalog":
            self._send_catalog_response(sn)
        elif cmd == "DeviceInfo":
            self._new_message_body(
                '<?xml version="1.0" encoding="UTF-8"?>\r\n<Response>\r\n'
                "<CmdType>DeviceInfo</CmdType>\r\n"
                f"<SN>{sn}</SN>\r\n<DeviceID>{self.device_id}</DeviceID>\r\n"
                "<Result>OK</Result>\r\n<Manufacturer>PyGBSentry</Manufacturer>\r\n"
                "<Model>DeviceSimulator</Model>\r\n<Firmware>1.0.0</Firmware>\r\n"
                "</Response>")
        elif cmd == "DeviceStatus":
            self._new_message_body(
                '<?xml version="1.0" encoding="UTF-8"?>\r\n<Response>\r\n'
                "<CmdType>DeviceStatus</CmdType>\r\n"
                f"<SN>{sn}</SN>\r\n<DeviceID>{self.device_id}</DeviceID>\r\n"
                "<Result>OK</Result>\r\n<Status>ONLINE</Status>\r\n"
                "<Reason>OK</Reason>\r\n</Response>")
        elif cmd:
            print(f"{self.log} MESSAGE CmdType={cmd}：已回 200 OK（未实现具体响应）")

    def _send_catalog_response(self, sn: str):
        items = []
        for ch in self.channels:
            items.append(
                "<Item>\r\n"
                f"<DeviceID>{ch}</DeviceID>\r\n"
                f"<Name>模拟通道-{ch[-3:]}</Name>\r\n"
                "<Manufacturer>PyGBSentry</Manufacturer>\r\n"
                "<Model>DeviceSimulator</Model>\r\n"
                "<Owner>Owner</Owner>\r\n"
                f"<CivilCode>{self.cfg.domain}</CivilCode>\r\n"
                "<Address>模拟部署地址</Address>\r\n"
                "<Parental>0</Parental>\r\n<SafetyWay>0</SafetyWay>\r\n"
                "<RegisterWay>1</RegisterWay>\r\n<Secrecy>0</Secrecy>\r\n"
                f"<IPAddress>{self._local_ip()}</IPAddress>\r\n<Port>5060</Port>\r\n"
                "<Status>ON</Status>\r\n"
                f"<ParentID>{self.device_id}</ParentID>\r\n"
                "<PTZType>1</PTZType>\r\n"
                "<Longitude>116.397128</Longitude>\r\n"
                "<Latitude>39.916527</Latitude>\r\n"
                "</Item>")
        n = len(self.channels)
        self._new_message_body(
            '<?xml version="1.0" encoding="UTF-8"?>\r\n<Response>\r\n'
            "<CmdType>Catalog</CmdType>\r\n"
            f"<SN>{sn}</SN>\r\n<DeviceID>{self.device_id}</DeviceID>\r\n"
            f"<SumNum>{n}</SumNum>\r\n"
            f'<DeviceList Num="{n}">\r\n'
            + "\r\n".join(items) + "\r\n</DeviceList>\r\n</Response>")

    # ---- INVITE 点播 ----

    async def _on_invite(self, msg: SipMsg):
        # INVITE 重传幂等：同一 Call-ID 的重复 INVITE 只重发 200 OK，不重建会话
        if self.pending_invite and self.pending_invite["call_id"] == msg.call_id:
            await self._respond(msg, 200, body=self._last_invite_sdp or "",
                                content_type="application/sdp" if self._last_invite_sdp else "Application/MANSCDP+xml")
            return
        if self.stream_task:
            self.stream_task.cancel()
            self.stream_task = None
        if self.tcp_server:
            self.tcp_server.close()
            self.tcp_server = None
        sdp = parse_sdp(msg.body)
        m = re.search(r"<sip:(\d+)@", msg.to_hdr or "")
        channel = m.group(1) if m else (self.channels[0] if self.channels else self.device_id)
        self.pending_invite = {
            "call_id": msg.call_id, "sdp": sdp, "channel": channel, "acked": False,
        }
        self.stream_call_id = msg.call_id
        local_ip = self._local_ip()
        is_tcp = "TCP" in sdp.get("proto", "RTP/AVP")
        setup_reply = ""
        if is_tcp and sdp.get("setup"):
            setup_reply = _TCP_SETUP_OPPOSITE.get(sdp["setup"], "")
        # 设备被动监听端口（仅当平台 active、设备 passive 时需要）
        listen_port = self.cfg.tcp_media_base + self.index * 10 + 1
        media_port = listen_port if (is_tcp and setup_reply == "passive") else self.local_addr[1]
        sdp_lines = [
            "v=0",
            f"o={channel} 0 0 IN IP4 {local_ip}",
            "s=Play",
            f"c=IN IP4 {local_ip}",
            "t=0 0",
            f"m=video {media_port} {'TCP/RTP/AVP' if is_tcp else 'RTP/AVP'} 96",
            "a=sendonly",
            "a=rtpmap:96 PS/90000",
        ]
        if setup_reply:
            sdp_lines.append(f"a=setup:{setup_reply}")
            sdp_lines.append("a=connection:new")
        if sdp.get("f"):
            sdp_lines.append(f"f={sdp['f']}")
        if sdp.get("ssrc"):
            sdp_lines.append(f"y={sdp['ssrc']}")
        sdp_body = "\r\n".join(sdp_lines) + "\r\n"
        self._last_invite_sdp = sdp_body
        await self._respond(msg, 200, body=sdp_body,
                            content_type="application/sdp")
        # ACK 兜底：3 秒未收到 ACK 仍开始发流（宽容模式，便于联调）
        await asyncio.sleep(3)
        pending = self.pending_invite
        if pending and pending["call_id"] == msg.call_id and not pending["acked"]:
            print(f"{self.log} 未收到 ACK，超时兜底开始发流")
            self._start_stream(pending)

    def _on_ack(self, msg: SipMsg):
        pending = self.pending_invite
        if pending and pending["call_id"] == msg.call_id and not pending["acked"]:
            pending["acked"] = True
            self._start_stream(pending)

    def _start_stream(self, pending: dict):
        # 幂等：同一 Call-ID 的流已在跑（ACK 与兜底超时竞争时只启动一次）
        if (self.stream_task and not self.stream_task.done()
                and self.stream_call_id == pending["call_id"]):
            return
        self.stream_task = asyncio.get_running_loop().create_task(
            self._stream_loop(pending["sdp"], pending["channel"], pending["call_id"]))

    async def _stream_loop(self, sdp: dict, channel: str, call_id: str):
        dest_ip = sdp.get("conn_ip", "")
        dest_port = sdp.get("media_port", 0)
        if not dest_ip or not dest_port:
            print(f"{self.log} SDP 缺少媒体地址（c=/m=），无法发流；"
                  f"检查平台 BACKEND_PUBLIC_HOST 配置")
            return
        ssrc_str = sdp.get("ssrc") or "0100000001"
        try:
            ssrc = int(ssrc_str) & 0xFFFFFFFF
        except ValueError:
            ssrc = random.randint(1, 0x7FFFFFFF)
        is_tcp = "TCP" in sdp.get("proto", "RTP/AVP")
        setup = sdp.get("setup", "")
        writer: asyncio.StreamWriter | None = None
        udp_transport = None
        try:
            if is_tcp and setup in ("passive", ""):
                # 平台 passive → 设备主动连接（GB28181 最常见 TCP 模式）
                print(f"{self.log} TCP 主动模式：连接平台媒体端口 {dest_ip}:{dest_port}")
                _, writer = await asyncio.open_connection(dest_ip, dest_port)
            elif is_tcp and setup == "active":
                # 平台 active → 设备监听，等待平台连入后泵流
                port = self.cfg.tcp_media_base + self.index * 10 + 1
                self.tcp_server = await asyncio.start_server(
                    lambda r, w: self._tcp_pump(r, w, ssrc, call_id), "0.0.0.0", port)
                print(f"{self.log} TCP 被动模式：监听 {port} 等待平台连入")
                await self.tcp_server.serve_forever()
                return
            else:
                loop = asyncio.get_running_loop()
                udp_transport, _ = await loop.create_datagram_endpoint(
                    asyncio.DatagramProtocol, remote_addr=(dest_ip, dest_port))
            mode = "TCP(RFC4571)" if writer else "UDP"
            print(f"{self.log} 开始发流 -> {dest_ip}:{dest_port} [{mode}] "
                  f"SSRC={ssrc_str} 通道={channel} PS包={len(self.packs)}")
            await self._pump(writer, udp_transport, ssrc, call_id)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"{self.log} 发流异常: {e}")
        finally:
            if writer:
                writer.close()
            if udp_transport:
                udp_transport.close()

    async def _pump(self, writer, udp_transport, ssrc: int, call_id: str):
        fps = self.cfg.fps
        seq = random.randint(0, 0xFFFF)
        ts_base = 0
        ticks_per_pass = int(len(self.packs) * 90000 / fps)
        while True:  # 循环播放：BYE/新 INVITE 通过 stream_call_id 守卫退出
            start = time.monotonic()
            for i, pack in enumerate(self.packs):
                if self.stream_call_id != call_id:
                    return  # 已被新 INVITE/BYE 取代
                target = start + i / fps
                delay = target - time.monotonic()
                if delay > 0:
                    await asyncio.sleep(delay)
                ts = (ts_base + int(i * 90000 / fps)) & 0xFFFFFFFF
                for fi in range(0, len(pack), 1400):
                    chunk = pack[fi:fi + 1400]
                    marker = fi + 1400 >= len(pack)
                    seq += 1
                    pkt = rtp_packet(ssrc, seq, ts, chunk, marker)
                    if writer:
                        writer.write(struct.pack("!H", len(pkt)) + pkt)
                    else:
                        udp_transport.sendto(pkt)
                if writer:
                    await writer.drain()
            ts_base = (ts_base + ticks_per_pass) & 0xFFFFFFFF

    async def _tcp_pump(self, reader, writer, ssrc: int, call_id: str):
        print(f"[tcp] 平台已连入，开始 RFC4571 帧式发送")
        try:
            await self._pump(writer, None, ssrc, call_id)
        except Exception:
            pass
        finally:
            writer.close()

    async def _on_bye(self, msg: SipMsg):
        self.stream_call_id = ""
        if self.stream_task:
            self.stream_task.cancel()
            self.stream_task = None
        if self.tcp_server:
            self.tcp_server.close()
            self.tcp_server = None
        self.pending_invite = None
        await self._respond(msg, 200)
        print(f"{self.log} 收到 BYE，停止发流")


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


class SimulatorApp:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.devices: list[SipDevice] = []

    async def run(self):
        cfg = self.cfg
        generate_ps_file(cfg)
        with open(cfg.ps_file, "rb") as f:
            packs = split_ps_packs(f.read())
        print(f"[simulator] 平台 {cfg.platform_host}:{cfg.platform_port} "
              f"server_id={cfg.server_id} 域={cfg.domain}")
        print(f"[simulator] PS 流就绪：{len(packs)} 个包（{cfg.media_duration}s 循环 @ {cfg.fps}fps）")
        print(f"[simulator] 模拟 {cfg.device_count} 台设备，每台 {cfg.channels_per_device} 通道，"
              f"设备号基址 {cfg.device_base}")
        for i in range(cfg.device_count):
            dev = SipDevice(cfg, i, packs)
            self.devices.append(dev)
            await dev.start()
            await asyncio.sleep(0.2)
        while True:
            await asyncio.sleep(3600)


def apply_cli_overrides(cfg: Config) -> Config:
    args = sys.argv[1:]

    def get(flag: str) -> str | None:
        return args[args.index(flag) + 1] if flag in args and args.index(flag) + 1 < len(args) else None

    v = get("--platform")
    if v:
        host, _, port = v.partition(":")
        cfg.platform_host = host
        if port.isdigit():
            cfg.platform_port = int(port)
    for flag, attr, cast in [
        ("--server-id", "server_id", str), ("--password", "password", str),
        ("--base", "device_base", str), ("--domain", "domain", str),
        ("--count", "device_count", int), ("--channels", "channels_per_device", int),
        ("--fps", "fps", int),
    ]:
        v = get(flag)
        if v:
            setattr(cfg, attr, cast(v))
    return cfg


async def amain():
    cfg = apply_cli_overrides(Config.from_env())
    await SimulatorApp(cfg).run()


if __name__ == "__main__":
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        pass
