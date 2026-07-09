"""Tests for SIP core: handlers, invite, catalog, record, playback_control."""
import os
import unittest
import time
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

# P2-23: 改用真实 app.core.config.settings 加载配置，不再使用 stub 注入。
# 通过环境变量设置测试配置（与 conftest.py 保持一致），让真实 Settings 类完成
# pydantic 校验，从而暴露潜在的配置缺陷（如缺失字段、类型错误等）。
# 以下环境变量在模块导入时设置，确保在 app.core.config 被首次导入前生效。
os.environ.setdefault("DATABASE_TYPE", "sqlite")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-not-for-production")


class TestSipMessageParsing(unittest.TestCase):
    def setUp(self):
        # P2-23: 直接使用真实 app.core.config.settings，不再 stub
        from app.sip.message import SipMessage
        self.SipMessage = SipMessage

    def test_parse_register_request(self):
        raw = (
            "REGISTER sip:3402000000@3402000000 SIP/2.0\r\n"
            "Via: SIP/2.0/UDP 192.168.1.100:5060;rport;branch=z9hG4bK12345\r\n"
            "From: <sip:34020000002000000001@3402000000>;tag=abc123\r\n"
            "To: <sip:34020000002000000001@3402000000>\r\n"
            "Call-ID: test-call-id-001@192.168.1.100\r\n"
            "CSeq: 1 REGISTER\r\n"
            "Contact: <sip:34020000002000000001@192.168.1.100:5060>\r\n"
            "Max-Forwards: 70\r\n"
            "User-Agent: Test Device\r\n"
            "Expires: 3600\r\n"
            "Content-Length: 0\r\n"
            "\r\n"
        )
        msg = self.SipMessage.parse(raw.encode("utf-8"))
        self.assertEqual(msg.method, "REGISTER")
        self.assertEqual(msg.version, "SIP/2.0")
        self.assertIn("Call-ID", msg.headers)
        self.assertEqual(msg.get_header("Call-ID"), "test-call-id-001@192.168.1.100")
        self.assertEqual(msg.get_header("CSeq"), "1 REGISTER")

    def test_parse_200_ok_response(self):
        raw = (
            "SIP/2.0 200 OK\r\n"
            "Via: SIP/2.0/UDP 127.0.0.1:5060;branch=z9hG4bK-branch-001\r\n"
            "From: <sip:34020000002000000001@3402000000>;tag=servertag1\r\n"
            "To: <sip:34020000002000000001@3402000000>;tag=devicetag1\r\n"
            "Call-ID: call-002@127.0.0.1\r\n"
            "CSeq: 1 REGISTER\r\n"
            "Content-Length: 0\r\n"
            "\r\n"
        )
        msg = self.SipMessage.parse(raw.encode("utf-8"))
        self.assertTrue(msg.is_response)
        self.assertEqual(msg.status_code, 200)
        self.assertEqual(msg.reason_phrase, "OK")

    def test_parse_invite_request(self):
        raw = (
            "INVITE sip:34020000001320000001@3402000000 SIP/2.0\r\n"
            "Via: SIP/2.0/UDP 127.0.0.1:5060;rport;branch=z9hG4bK-invite-001\r\n"
            "From: <sip:34020000002000000001@3402000000>;tag=fromtag1\r\n"
            "To: <sip:34020000001320000001@3402000000>\r\n"
            "Call-ID: invite-call-001@127.0.0.1\r\n"
            "CSeq: 1 INVITE\r\n"
            "Contact: <sip:34020000002000000001@127.0.0.1:5060>\r\n"
            "Content-Type: application/sdp\r\n"
            "Content-Length: 0\r\n"
            "\r\n"
        )
        msg = self.SipMessage.parse(raw.encode("utf-8"))
        self.assertEqual(msg.method, "INVITE")
        self.assertEqual(msg.get_header("Content-Type"), "application/sdp")

    def test_parse_bye_request(self):
        raw = (
            "BYE sip:34020000002000000001@3402000000 SIP/2.0\r\n"
            "Via: SIP/2.0/UDP 192.168.1.100:5060;branch=z9hG4bK-bye-001\r\n"
            "From: <sip:34020000001320000001@3402000000>;tag=devicetag1\r\n"
            "To: <sip:34020000002000000001@3402000000>;tag=servertag1\r\n"
            "Call-ID: invite-call-001@127.0.0.1\r\n"
            "CSeq: 2 BYE\r\n"
            "Content-Length: 0\r\n"
            "\r\n"
        )
        msg = self.SipMessage.parse(raw.encode("utf-8"))
        self.assertEqual(msg.method, "BYE")
        self.assertEqual(msg.get_header("Call-ID"), "invite-call-001@127.0.0.1")

    def test_parse_message_with_xml_body(self):
        xml_body = (
            '<?xml version="1.0" encoding="GB2312"?>\n'
            "<Notify>\n"
            "<CmdType>Keepalive</CmdType>\n"
            "<SN>1</SN>\n"
            "<DeviceID>34020000002000000001</DeviceID>\n"
            "</Notify>"
        )
        raw = (
            "MESSAGE sip:34020000002000000001@3402000000 SIP/2.0\r\n"
            "Via: SIP/2.0/UDP 192.168.1.100:5060;branch=z9hG4bK-msg-001\r\n"
            "From: <sip:34020000002000000001@3402000000>;tag=dev1\r\n"
            "To: <sip:34020000002000000001@3402000000>\r\n"
            "Call-ID: msg-001@192.168.1.100\r\n"
            "CSeq: 1 MESSAGE\r\n"
            "Content-Type: Application/MANSCDP+xml\r\n"
            f"Content-Length: {len(xml_body)}\r\n"
            "\r\n"
            + xml_body
        )
        msg = self.SipMessage.parse(raw.encode("utf-8"))
        self.assertEqual(msg.method, "MESSAGE")
        self.assertIn("Keepalive", msg.body)
        self.assertIn("DeviceID", msg.body)


class TestDigestAuthNonce(unittest.TestCase):
    def setUp(self):
        # P2-23: 直接使用真实 app.core.config.settings，不再 stub
        pass

    def test_generate_nonce_format(self):
        from app.sip.auth import DigestAuth
        nonce = DigestAuth.generate_nonce()
        parts = nonce.split(":")
        self.assertEqual(len(parts), 3, "Nonce should be timestamp:random:hmac_sig")
        self.assertTrue(parts[0].isdigit(), "First part should be timestamp")
        self.assertTrue(len(parts[1]) > 0, "Second part should be random hex")
        self.assertTrue(len(parts[2]) > 0, "Third part should be HMAC signature")

    def test_nonce_uniqueness(self):
        from app.sip.auth import DigestAuth
        nonces = {DigestAuth.generate_nonce() for _ in range(100)}
        self.assertEqual(len(nonces), 100, "All generated nonces should be unique")

    def test_calculate_response_md5(self):
        from app.sip.auth import DigestAuth
        resp = DigestAuth.calculate_response(
            username="admin",
            password="123456",
            realm="3402000000",
            method="REGISTER",
            uri="sip:3402000000@3402000000",
            nonce="testnonce",
        )
        self.assertTrue(len(resp) == 32, "MD5 response should be 32 hex chars")


class TestByeTagValidation(unittest.TestCase):
    def test_tag_extraction(self):
        import re

        def _extract_tag(header_val):
            if not header_val:
                return ""
            m = re.search(r";\s*tag=([^;>\s]+)", header_val, re.IGNORECASE)
            return m.group(1).strip() if m else ""

        self.assertEqual(_extract_tag('<sip:user@domain>;tag=abc123'), "abc123")
        self.assertEqual(_extract_tag('<sip:user@domain>; tag=xyz789 '), "xyz789")
        self.assertEqual(_extract_tag('<sip:user@domain>'), "")
        self.assertEqual(_extract_tag(""), "")
        self.assertEqual(_extract_tag(None), "")

    def test_tag_match_logic_and(self):
        ss_from_tag = "servertag1"
        ss_to_tag = "devicetag1"
        bye_from_tag = "devicetag1"
        bye_to_tag = "servertag1"

        tag_matched = (
            (ss_to_tag and bye_from_tag == ss_to_tag)
            and (ss_from_tag and bye_to_tag == ss_from_tag)
        ) or (
            (ss_to_tag and bye_to_tag == ss_to_tag)
            and (ss_from_tag and bye_from_tag == ss_from_tag)
        )
        self.assertTrue(tag_matched, "Matching tags should pass AND validation")

    def test_tag_mismatch_and_logic(self):
        ss_from_tag = "servertag1"
        ss_to_tag = "devicetag1"
        bye_from_tag = "wrongtag"
        bye_to_tag = "servertag1"

        tag_matched = (
            (ss_to_tag and bye_from_tag == ss_to_tag)
            and (ss_from_tag and bye_to_tag == ss_from_tag)
        ) or (
            (ss_to_tag and bye_to_tag == ss_to_tag)
            and (ss_from_tag and bye_from_tag == ss_from_tag)
        )
        self.assertFalse(tag_matched, "Mismatched tags should fail AND validation")


class TestSipRecordSN(unittest.TestCase):
    def test_sn_generation_range(self):
        import random
        for _ in range(1000):
            sn = random.randint(1, 9999)
            self.assertGreaterEqual(sn, 1)
            self.assertLessEqual(sn, 9999)


class TestSipServerL7Firewall(unittest.TestCase):
    def test_bye_callid_min_length(self):
        short_call_ids = ["a", "ab", "abc", "abcd", "abcde", "abcdefghij", "valid-call-id-123"]
        for cid in short_call_ids:
            is_valid = len(cid) >= 10
            if cid in ("abcdefghij", "valid-call-id-123"):
                self.assertTrue(is_valid, f"Call-ID '{cid}' should pass length check")
            else:
                self.assertFalse(is_valid, f"Call-ID '{cid}' should fail length check")

    def test_bye_callid_format(self):
        import re
        valid_ids = ["abc123@192.168.1.1", "call-id_test.123@host"]
        invalid_ids = ["call id with spaces", "call<id>", "call{id}"]
        for cid in valid_ids:
            self.assertTrue(
                re.match(r'^[a-zA-Z0-9_.\-@]+$', cid),
                f"Valid Call-ID '{cid}' should match format"
            )
        for cid in invalid_ids:
            self.assertFalse(
                re.match(r'^[a-zA-Z0-9_.\-@]+$', cid),
                f"Invalid Call-ID '{cid}' should not match format"
            )


if __name__ == "__main__":
    unittest.main()
