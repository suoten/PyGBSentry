import unittest
import time
import json
from unittest.mock import patch, MagicMock


class TestIssuePlayToken(unittest.TestCase):
    """Tests for issue_play_token — produces 'payload_b64.sig' format tokens."""

    def test_issue_token_basic(self):
        from app.core.play_token import issue_play_token
        token = issue_play_token("rtp", "385F2197", 300)
        self.assertTrue(len(token) > 0)
        # Token format: payload_b64.sig
        self.assertIn(".", token)
        payload_b64, _, sig = token.rpartition(".")
        self.assertTrue(len(payload_b64) > 0)
        self.assertTrue(len(sig) > 0)

    def test_issue_token_contains_app_stream_expire(self):
        from app.core.play_token import issue_play_token, _b64url_decode
        token = issue_play_token("live", "test_stream", 300)
        payload_b64, _, _ = token.rpartition(".")
        body = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        self.assertEqual(body["app"], "live")
        self.assertEqual(body["stream"], "test_stream")
        self.assertIn("exp", body)

    def test_issue_token_default_ttl(self):
        from app.core.play_token import issue_play_token, _b64url_decode, _TTL_SECONDS
        token = issue_play_token("rtp", "test")
        payload_b64, _, _ = token.rpartition(".")
        body = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        now = int(time.time())
        # exp should be ~now + _TTL_SECONDS (7200)
        self.assertGreaterEqual(body["exp"] - now, _TTL_SECONDS - 10)
        self.assertLessEqual(body["exp"] - now, _TTL_SECONDS + 10)

    def test_issue_token_custom_ttl(self):
        from app.core.play_token import issue_play_token, _b64url_decode
        token = issue_play_token("rtp", "test", 60)
        payload_b64, _, _ = token.rpartition(".")
        body = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        now = int(time.time())
        self.assertGreaterEqual(body["exp"] - now, 50)
        self.assertLessEqual(body["exp"] - now, 70)


class TestVerifyPlayToken(unittest.TestCase):
    """Tests for verify_play_token — validates 'payload_b64.sig' tokens."""

    def test_valid_token(self):
        from app.core.play_token import issue_play_token, verify_play_token
        token = issue_play_token("rtp", "385F2197", 300)
        is_valid, error_msg = verify_play_token(token, "rtp", "385F2197")
        self.assertTrue(is_valid)
        self.assertEqual(error_msg, "")

    def test_empty_token(self):
        from app.core.play_token import verify_play_token
        is_valid, error_msg = verify_play_token("", "rtp", "385F2197")
        self.assertFalse(is_valid)
        self.assertEqual(error_msg, "missing play token")

    def test_malformed_token_no_dot(self):
        from app.core.play_token import verify_play_token
        is_valid, error_msg = verify_play_token("!!!invalid!!!", "rtp", "385F2197")
        self.assertFalse(is_valid)
        self.assertEqual(error_msg, "malformed play token")

    def test_tampered_signature(self):
        from app.core.play_token import issue_play_token, verify_play_token
        token = issue_play_token("rtp", "385F2197", 300)
        payload_b64, _, sig = token.rpartition(".")
        # Flip the last character of the signature to tamper it
        last = sig[-1]
        tampered_last = "A" if last != "A" else "B"
        tampered_sig = sig[:-1] + tampered_last
        tampered_token = f"{payload_b64}.{tampered_sig}"
        is_valid, error_msg = verify_play_token(tampered_token, "rtp", "385F2197")
        self.assertFalse(is_valid)
        self.assertEqual(error_msg, "invalid play token signature")

    def test_expired_token(self):
        from app.core.play_token import issue_play_token, verify_play_token
        token = issue_play_token("rtp", "385F2197", 300)
        # Mock time.time to return a far-future timestamp so the token appears expired
        future_time = time.time() + 100000
        with patch("app.core.play_token.time.time", return_value=future_time):
            is_valid, error_msg = verify_play_token(token, "rtp", "385F2197")
        self.assertFalse(is_valid)
        self.assertEqual(error_msg, "play token expired")

    def test_app_stream_mismatch(self):
        from app.core.play_token import issue_play_token, verify_play_token
        token = issue_play_token("rtp", "385F2197", 300)
        is_valid, error_msg = verify_play_token(token, "live", "385F2197")
        self.assertFalse(is_valid)
        self.assertEqual(error_msg, "play token does not match stream")
        is_valid2, error_msg2 = verify_play_token(token, "rtp", "OTHER_STREAM")
        self.assertFalse(is_valid2)
        self.assertEqual(error_msg2, "play token does not match stream")

    def test_malformed_payload(self):
        from app.core.play_token import verify_play_token, _secret, _b64url
        import base64
        import hmac
        import hashlib
        # Construct a payload that is valid base64 but not valid JSON
        junk_b64 = base64.urlsafe_b64encode(b"not_json").rstrip(b"=").decode("ascii")
        # Sign it with a valid HMAC so we pass the signature check and reach the JSON decode
        sig = _b64url(hmac.new(_secret(), junk_b64.encode("ascii"), hashlib.sha256).digest())
        malformed_token = f"{junk_b64}.{sig}"
        is_valid, error_msg = verify_play_token(malformed_token, "rtp", "385F2197")
        self.assertFalse(is_valid)
        self.assertEqual(error_msg, "malformed play token payload")


class TestExtractTokenFromParams(unittest.TestCase):
    """Tests for extract_token_from_params — pulls playToken/token from hook params."""

    def test_string_format(self):
        from app.core.play_token import extract_token_from_params
        self.assertEqual(extract_token_from_params("token=abc123&other=xyz"), "abc123")

    def test_string_format_with_question_mark(self):
        from app.core.play_token import extract_token_from_params
        self.assertEqual(extract_token_from_params("?token=abc123&other=xyz"), "abc123")

    def test_playToken_key_in_string(self):
        from app.core.play_token import extract_token_from_params
        self.assertEqual(extract_token_from_params("playToken=xyz789&other=abc"), "xyz789")

    def test_dict_format(self):
        from app.core.play_token import extract_token_from_params
        self.assertEqual(extract_token_from_params({"token": "abc123", "other": "xyz"}), "abc123")

    def test_playToken_key_in_dict(self):
        from app.core.play_token import extract_token_from_params
        self.assertEqual(extract_token_from_params({"playToken": "xyz789"}), "xyz789")

    def test_none_input(self):
        from app.core.play_token import extract_token_from_params
        self.assertEqual(extract_token_from_params(None), "")

    def test_missing_token_in_string(self):
        from app.core.play_token import extract_token_from_params
        self.assertEqual(extract_token_from_params("other=xyz"), "")

    def test_missing_token_in_dict(self):
        from app.core.play_token import extract_token_from_params
        self.assertEqual(extract_token_from_params({"other": "xyz"}), "")


class TestSecret(unittest.TestCase):
    """Tests for _secret — returns the HMAC key derived from settings.SECRET_KEY."""

    @patch("app.core.play_token.settings")
    def test_empty_secret(self, mock_settings):
        from app.core.play_token import _secret
        mock_settings.SECRET_KEY = ""
        key = _secret()
        self.assertEqual(key, b"")

    @patch("app.core.play_token.settings")
    def test_real_secret(self, mock_settings):
        from app.core.play_token import _secret
        mock_settings.SECRET_KEY = "my-test-secret"
        key = _secret()
        self.assertEqual(key, b"my-test-secret")

    @patch("app.core.play_token.settings")
    def test_none_secret_falls_back_to_empty(self, mock_settings):
        from app.core.play_token import _secret
        mock_settings.SECRET_KEY = None
        key = _secret()
        self.assertEqual(key, b"")


class TestShouldAllowNoToken(unittest.TestCase):
    """Tests for should_allow_no_token — checks PLAY_ALLOW_NO_TOKEN setting."""

    @patch("app.core.play_token.settings")
    def test_default_false(self, mock_settings):
        from app.core.play_token import should_allow_no_token
        mock_settings.PLAY_ALLOW_NO_TOKEN = False
        self.assertFalse(should_allow_no_token())

    @patch("app.core.play_token.settings")
    def test_config_true(self, mock_settings):
        from app.core.play_token import should_allow_no_token
        mock_settings.PLAY_ALLOW_NO_TOKEN = True
        self.assertTrue(should_allow_no_token())


if __name__ == "__main__":
    unittest.main()
