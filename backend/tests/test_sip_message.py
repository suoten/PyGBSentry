import unittest
import sys
import types
import asyncio


def _install_test_settings_stub() -> None:
    settings_obj = types.SimpleNamespace(
        PROJECT_NAME="PyGBSentry",
        SQLALCHEMY_DATABASE_URI="sqlite+aiosqlite:///:memory:",
        SIP_IP="127.0.0.1",
        SIP_PORT=5060,
        SIP_ID="34020000002000000001",
        SIP_DOMAIN="3402000000",
        SIP_WORKER_CONCURRENCY=1000,
        SIP_RESPONSE_CACHE_TTL_SECONDS=32,
        SIP_RESPONSE_CACHE_MAX_SIZE=1000,
        SIP_MAX_INFLIGHT=1000,
        SIP_INVITE_RESPONSE_TIMEOUT_SECONDS=1,
    )
    existing = sys.modules.get("app.core.config")
    if existing is None:
        m = types.ModuleType("app.core.config")
        m.settings = settings_obj
        sys.modules["app.core.config"] = m
        return
    if not hasattr(existing, "settings") or existing.settings is None:
        existing.settings = settings_obj
        return
    for k, v in settings_obj.__dict__.items():
        if not hasattr(existing.settings, k):
            # Pydantic v2 __setattr__ rejects unknown fields when extra != 'allow'.
            object.__setattr__(existing.settings, k, v)


class TestSipMessage(unittest.TestCase):
    def test_multi_value_headers_roundtrip(self):
        from app.sip.message import SipMessage

        raw = (
            b"OPTIONS sip:34020000002000000001@3402000000 SIP/2.0\r\n"
            b"Via: SIP/2.0/UDP 1.1.1.1:5060;branch=z9hG4bK1\r\n"
            b"Via: SIP/2.0/UDP 2.2.2.2:5061;branch=z9hG4bK2\r\n"
            b"From: <sip:34020000002000000001@3402000000>;tag=abc\r\n"
            b"To: <sip:34020000002000000001@3402000000>\r\n"
            b"Call-ID: testcall\r\n"
            b"CSeq: 1 OPTIONS\r\n"
            b"Content-Length: 0\r\n"
            b"\r\n"
        )
        msg = SipMessage.parse(raw)
        vias = msg.get_headers("Via")
        self.assertEqual(len(vias), 2)
        out = msg.to_bytes()
        self.assertIn(b"\r\nVia: SIP/2.0/UDP 1.1.1.1:5060;branch=z9hG4bK1\r\n", out)
        self.assertIn(b"\r\nVia: SIP/2.0/UDP 2.2.2.2:5061;branch=z9hG4bK2\r\n", out)

    def test_create_response_adds_stable_to_tag(self):
        _install_test_settings_stub()
        from app.sip.message import SipMessage
        from app.sip import server as sip_server_module

        raw = (
            b"REGISTER sip:34020000002000000001@3402000000 SIP/2.0\r\n"
            b"Via: SIP/2.0/UDP 1.1.1.1:5060;branch=z9hG4bK1;rport\r\n"
            b"From: <sip:34020000002000000001@3402000000>;tag=abc\r\n"
            b"To: <sip:34020000002000000001@3402000000>\r\n"
            b"Call-ID: testcall\r\n"
            b"CSeq: 1 REGISTER\r\n"
            b"Content-Length: 0\r\n"
            b"\r\n"
        )
        req = SipMessage.parse(raw)
        r1 = sip_server_module._create_basic_response(req, 401, "Unauthorized", received_addr=("1.1.1.1", 5060))
        r2 = sip_server_module._create_basic_response(req, 401, "Unauthorized", received_addr=("1.1.1.1", 5060))
        self.assertRegex(r1.get_header("To") or "", r";\s*tag=")
        self.assertEqual(r1.get_header("To"), r2.get_header("To"))

    async def test_server_response_cache_hits(self):
        _install_test_settings_stub()
        from app.sip.message import SipMessage
        from app.sip.server import SipServer
        from app.sip import server as sip_server_module

        raw = (
            b"REGISTER sip:34020000002000000001@3402000000 SIP/2.0\r\n"
            b"Via: SIP/2.0/UDP 1.1.1.1:5060;branch=z9hG4bK1;rport\r\n"
            b"From: <sip:34020000002000000001@3402000000>;tag=abc\r\n"
            b"To: <sip:34020000002000000001@3402000000>\r\n"
            b"Call-ID: testcall\r\n"
            b"CSeq: 1 REGISTER\r\n"
            b"Content-Length: 0\r\n"
            b"\r\n"
        )
        req = SipMessage.parse(raw)
        resp = sip_server_module._create_basic_response(req, 401, "Unauthorized", received_addr=("1.1.1.1", 5060))
        s = SipServer()
        await s.cache_response(resp)
        key = s._tx_key_from_request(req)
        cached = await s._get_cached_response(key)
        self.assertIsNotNone(cached)
        self.assertEqual(cached.get_header("Call-ID"), "testcall")

    def test_sdp_parser_tcp_setup(self):
        from app.sip.sdp import parse_sdp, pick_media, is_tcp_profile, opposite_setup

        body = (
            "v=0\r\n"
            "o=3402000000 0 0 IN IP4 10.0.0.1\r\n"
            "s=Play\r\n"
            "c=IN IP4 1.2.3.4\r\n"
            "t=0 0\r\n"
            "m=video 15060 TCP/RTP/AVP 96\r\n"
            "a=setup:active\r\n"
            "a=connection:new\r\n"
            "y=0100000001\r\n"
        )
        parsed = parse_sdp(body)
        md = pick_media(parsed, "video") or {}
        self.assertEqual(md.get("connection_ip"), "1.2.3.4")
        self.assertTrue(is_tcp_profile(md.get("proto")))
        self.assertEqual(md.get("setup"), "active")
        self.assertEqual(opposite_setup(md.get("setup")), "passive")

    def test_invite_watchdog_cancel_is_idempotent(self):
        _install_test_settings_stub()
        from app.sip.watchdog import start_watchdog, cancel_watchdog

        async def noop():
            return

        async def main():
            cancel_watchdog("k1")
            start_watchdog(key="k1", timeout_seconds=1, on_timeout=noop)
            cancel_watchdog("k1")
            cancel_watchdog("k1")

        asyncio.run(main())


if __name__ == "__main__":
    unittest.main()
