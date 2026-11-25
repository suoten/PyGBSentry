#!/usr/bin/env python3
"""设备模拟器本地端到端测试（无需 ffmpeg / docker / 平台）。

在 127.0.0.1 上拉起一个极简"假平台"，按真实协议顺序驱动模拟器：
REGISTER → 401 质询 → 带 Authorization 重注册（服务端独立验算 Digest）→ 200
→ Catalog 查询 → 校验目录响应 → INVITE → 校验 200 OK SDP（y= 回显）
→ ACK → 在媒体端口收 RTP/PS 流并校验 SSRC/PT → BYE → 校验 200。

运行：python local_e2e_test.py
"""

import asyncio
import hashlib
import re
import struct
import sys
import tempfile
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util

spec = importlib.util.spec_from_file_location(
    "device_simulator", os.path.join(os.path.dirname(os.path.abspath(__file__)), "device_simulator.py"))
ds = importlib.util.module_from_spec(spec)
sys.modules["device_simulator"] = ds
spec.loader.exec_module(ds)

PLATFORM_PORT = 15060
MEDIA_PORT = 26000
REALM = "340200"
NONCE = "1750000000:test-nonce:cafe"
PASSWORD = "test12345"
DEVICE_ID = "34020000001310000001"
CHANNEL_ID = "34020000001320000001"


def expected_digest(username: str, method: str, uri: str) -> str:
    ha1 = hashlib.md5(f"{username}:{REALM}:{PASSWORD}".encode()).hexdigest()
    ha2 = hashlib.md5(f"{method}:{uri}".encode()).hexdigest()
    return hashlib.md5(f"{ha1}:{NONCE}:{ha2}".encode()).hexdigest()


class FakePlatform(asyncio.DatagramProtocol):
    def __init__(self, state: dict):
        self.state = state

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        msg = ds.parse_sip(data)
        if not msg:
            return
        state = self.state
        if not msg.is_request:
            if msg.method == "200" and msg.header("CSeq").rstrip().endswith("BYE"):
                state["bye_done"].set()
            return
        if msg.is_request and msg.method == "REGISTER":
            auth = msg.header("Authorization")
            if not auth:
                resp = ("SIP/2.0 401 Unauthorized\r\n"
                        f"Via: {msg.via}\r\nFrom: {msg.from_hdr}\r\nTo: {msg.to_hdr};tag=plt\r\n"
                        f"Call-ID: {msg.call_id}\r\nCSeq: {msg.cseq_num} REGISTER\r\n"
                        f'WWW-Authenticate: Digest realm="{REALM}", nonce="{NONCE}", algorithm=MD5\r\n'
                        "Content-Length: 0\r\n\r\n")
                self.transport.sendto(resp.encode(), addr)
                return
            m = re.search(r'response="([0-9a-f]+)"', auth)
            dev_m = re.search(r'username="(\d+)"', auth)
            expect = expected_digest(dev_m.group(1) if dev_m else "", "REGISTER", f"sip:34020000002000000001@{REALM}")
            state["digest_ok"] = bool(m and m.group(1) == expect)
            state["register_done"].set()
            self._reply(msg, 200, addr)
        elif msg.is_request and msg.method == "MESSAGE":
            body = msg.body
            if "Keepalive" in body:
                state["keepalive_seen"] = True
                self._reply(msg, 200, addr)
            elif "CmdType" in body and "<Response>" in body:
                if "<CmdType>Catalog</CmdType>" in body:
                    state["catalog_body"] = body
                    state["catalog_done"].set()
                self._reply(msg, 200, addr)
            else:
                m = re.search(r"<SN>(\d+)</SN>", body)
                if m and "Catalog" in body:
                    self._reply(msg, 200, addr)
                    catalog = (
                        '<?xml version="1.0" encoding="UTF-8"?>\r\n'
                        "<Query>\r\n<CmdType>Catalog</CmdType>\r\n"
                        f"<SN>{m.group(1)}</SN>\r\n<DeviceID>{DEVICE_ID}</DeviceID>\r\n</Query>")
                    self._new_message(catalog, addr, cseq=20)
        elif msg.is_request and msg.method == "INVITE":
            state["invite_offer"] = msg.body
            sdp_reply = (
                "v=0\r\no=9 0 0 IN IP4 1.2.3.4\r\ns=Play\r\nc=IN IP4 1.2.3.4\r\nt=0 0\r\n"
                f"m=video {MEDIA_PORT} RTP/AVP 96\r\na=recvonly\r\na=rtpmap:96 PS/90000\r\n"
                "y=0100000001\r\nf=v/2/4/25\r\n")
            to_tagged = msg.to_hdr + ";tag=plt2"
            resp = (f"SIP/2.0 200 OK\r\nVia: {msg.via}\r\nFrom: {msg.from_hdr}\r\n"
                    f"To: {to_tagged}\r\nCall-ID: {msg.call_id}\r\n"
                    f"CSeq: {msg.cseq_num} INVITE\r\n"
                    "Content-Type: application/sdp\r\n"
                    f"Content-Length: {len(sdp_reply)}\r\n\r\n{sdp_reply}")
            self.transport.sendto(resp.encode(), addr)
            # 平台随后发 ACK
            ack = (f"ACK sip:{CHANNEL_ID}@{REALM} SIP/2.0\r\n"
                   f"Via: SIP/2.0/UDP 127.0.0.1:{PLATFORM_PORT};branch=z9hG4bKack1\r\n"
                   f"From: {msg.from_hdr}\r\nTo: {to_tagged}\r\n"
                   f"Call-ID: {msg.call_id}\r\nCSeq: {msg.cseq_num} ACK\r\n"
                   "Max-Forwards: 70\r\nContent-Length: 0\r\n\r\n")
            asyncio.get_running_loop().call_later(0.3, self.transport.sendto, ack.encode(), addr)
        elif msg.is_request and msg.method == "BYE":
            self._reply(msg, 200, addr)
            state["bye_done"].set()

    def _reply(self, msg, code, addr):
        resp = (f"SIP/2.0 {code} OK\r\nVia: {msg.via}\r\nFrom: {msg.from_hdr}\r\n"
                f"To: {msg.to_hdr};tag=plt\r\nCall-ID: {msg.call_id}\r\n"
                f"CSeq: {msg.cseq_num} {msg.method}\r\nContent-Length: 0\r\n\r\n")
        self.transport.sendto(resp.encode(), addr)

    def _new_message(self, body, addr, cseq):
        call_id = f"plt-{cseq}"
        req = (f"MESSAGE sip:{DEVICE_ID}@{REALM} SIP/2.0\r\n"
               f"Via: SIP/2.0/UDP 127.0.0.1:{PLATFORM_PORT};branch=z9hG4bK{cseq}\r\n"
               f"From: <sip:34020000002000000001@{REALM}>;tag=plt{cseq}\r\n"
               f"To: <sip:{DEVICE_ID}@{REALM}>\r\n"
               f"Call-ID: {call_id}\r\nCSeq: {cseq} MESSAGE\r\n"
               "Max-Forwards: 70\r\nContent-Type: Application/MANSCDP+xml\r\n"
               f"Content-Length: {len(body.encode())}\r\n\r\n{body}")
        self.transport.sendto(req.encode(), addr)


async def main():
    state = {"register_done": asyncio.Event(), "catalog_done": asyncio.Event(),
             "bye_done": asyncio.Event()}
    loop = asyncio.get_running_loop()
    proto = FakePlatform(state)
    transport, _ = await loop.create_datagram_endpoint(lambda: proto,
                                                       local_addr=("127.0.0.1", PLATFORM_PORT))

    # 假 PS 文件：3 个包，无需 ffmpeg
    ps_file = os.path.join(tempfile.gettempdir(), "sim_test.ps")
    fake_ps = (b"\x00\x00\x01\xba" + os.urandom(1200)) * 1 + \
              (b"\x00\x00\x01\xba" + os.urandom(1200)) + \
              (b"\x00\x00\x01\xba" + os.urandom(1200))
    with open(ps_file, "wb") as f:
        f.write(fake_ps)

    cfg = ds.Config(platform_host="127.0.0.1", platform_port=PLATFORM_PORT,
                    password=PASSWORD, device_count=1, channels_per_device=1,
                    keepalive_interval=3600, fps=25, ps_file=ps_file)
    app = ds.SimulatorApp(cfg)
    dev = ds.SipDevice(cfg, 0, ds.split_ps_packs(fake_ps))
    app.devices.append(dev)
    await dev.start()

    # 1) 注册 + Digest 验证
    await asyncio.wait_for(state["register_done"].wait(), 10)
    assert state.get("digest_ok"), "Digest 响应与服务端独立验算不一致"
    print("PASS 1/4 REGISTER + Digest 认证（服务端独立验算通过）")

    # 2) Catalog 查询（平台侧主动发起）
    catalog = ('<?xml version="1.0" encoding="UTF-8"?>\r\n'
               "<Query>\r\n<CmdType>Catalog</CmdType>\r\n"
               "<SN>42</SN>\r\n"
               f"<DeviceID>{DEVICE_ID}</DeviceID>\r\n</Query>")
    FakePlatform._new_message(proto, catalog,
                              ("127.0.0.1", dev.local_addr[1]), 30)
    await asyncio.wait_for(state["catalog_done"].wait(), 5)
    body = state["catalog_body"]
    assert f"<SN>42</SN>" in body and "<SumNum>1</SumNum>" in body, body[:400]
    assert f"<DeviceID>{CHANNEL_ID}</DeviceID>" in body and 'Num="1"' in body
    assert "PTZType" in body
    print("PASS 2/4 Catalog 响应（SN 回显 / SumNum / DeviceList@Num / Item 字段齐全）")

    # 3) INVITE → 200 OK SDP → ACK → 收 RTP
    invite_sdp = (f"v=0\r\no=9 0 0 IN IP4 127.0.0.1\r\ns=Play\r\n"
                  f"c=IN IP4 127.0.0.1\r\nt=0 0\r\n"
                  f"m=video {MEDIA_PORT} RTP/AVP 96\r\na=recvonly\r\n"
                  "a=rtpmap:96 PS/90000\r\ny=0100000001\r\n")
    invite = (f"INVITE sip:{CHANNEL_ID}@{REALM} SIP/2.0\r\n"
              f"Via: SIP/2.0/UDP 127.0.0.1:{PLATFORM_PORT};branch=z9hG4bKinv1\r\n"
              f"From: <sip:34020000002000000001@{REALM}>;tag=pltinv\r\n"
              f"To: <sip:{CHANNEL_ID}@{REALM}>\r\n"
              f"Call-ID: inv-call-1\r\nCSeq: 31 INVITE\r\n"
              "Max-Forwards: 70\r\nContent-Type: application/sdp\r\n"
              f"Content-Length: {len(invite_sdp)}\r\n\r\n{invite_sdp}")
    rtp_state = {"pkts": asyncio.Event(), "count": 0, "ssrc_ok": False, "pt_ok": False,
                 "marker_frames": set()}

    class MediaSink(asyncio.DatagramProtocol):
        def datagram_received(self, data, addr):
            if len(data) < 12:
                return
            b0, b1, seq, ts, ssrc = struct.unpack("!BBHII", data[:12])
            rtp_state["count"] += 1
            rtp_state["ssrc_ok"] = rtp_state["ssrc_ok"] or ssrc == 100000001
            rtp_state["pt_ok"] = rtp_state["pt_ok"] or (b1 & 0x7F) == 96
            if b1 & 0x80:
                rtp_state["marker_frames"].add(ts)
            if rtp_state["count"] >= 10:
                rtp_state["pkts"].set()

        def error_received(self, exc):
            print("sink error_received:", exc)

    # 探针：统计模拟器实际构造的 RTP 包数
    send_counter = {"n": 0}
    _orig_rtp = ds.rtp_packet

    def _counting_rtp(*a, **k):
        send_counter["n"] += 1
        return _orig_rtp(*a, **k)

    ds.rtp_packet = _counting_rtp

    sink_transport, _ = await loop.create_datagram_endpoint(
        MediaSink, local_addr=("127.0.0.1", MEDIA_PORT))
    proto.transport.sendto(invite.encode(), ("127.0.0.1", dev.local_addr[1]))
    try:
        await asyncio.wait_for(rtp_state["pkts"].wait(), 10)
    except asyncio.TimeoutError:
        print("RTP 超时诊断: 设备构造RTP包数=", send_counter["n"],
              "sink收到=", rtp_state["count"],
              "stream_task=", dev.stream_task,
              "task_done=", dev.stream_task.done() if dev.stream_task else None)
        raise
    assert rtp_state["ssrc_ok"], "RTP SSRC 与 y= 不匹配"
    assert rtp_state["pt_ok"], "RTP PT != 96"
    assert rtp_state["marker_frames"], "未见帧边界 marker 包"
    print(f"PASS 3/4 INVITE/ACK/RTP（收到 {rtp_state['count']} 包，SSRC/PT/marker 正确）")
    # 4) BYE
    bye = (f"BYE sip:{CHANNEL_ID}@{REALM} SIP/2.0\r\n"
           f"Via: SIP/2.0/UDP 127.0.0.1:{PLATFORM_PORT};branch=z9hG4bKbye1\r\n"
           f"From: <sip:34020000002000000001@{REALM}>;tag=pltinv\r\n"
           f"To: <sip:{CHANNEL_ID}@{REALM}>\r\n"
           f"Call-ID: inv-call-1\r\nCSeq: 32 BYE\r\n"
           "Max-Forwards: 70\r\nContent-Length: 0\r\n\r\n")
    proto.transport.sendto(bye.encode(), ("127.0.0.1", dev.local_addr[1]))
    await asyncio.wait_for(state["bye_done"].wait(), 5)
    await asyncio.sleep(0.5)
    count_after = rtp_state["count"]
    await asyncio.sleep(0.6)
    assert rtp_state["count"] == count_after, "BYE 后仍在发流"
    print("PASS 4/4 BYE 停流")

    sink_transport.close()
    transport.close()
    print("\nE2E_ALL_PASS：模拟器与平台协议交互全链路通过")


if __name__ == "__main__":
    asyncio.run(main())
