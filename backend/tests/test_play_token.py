import unittest
import time
from unittest.mock import patch, MagicMock


class TestGeneratePlayToken(unittest.TestCase):
    def test_generate_token_basic(self):
        from app.core.play_token import generate_play_token, _decode_play_token, HMAC_SIG_BYTES
        token = generate_play_token("rtp", "385F2197", 300)
        self.assertTrue(len(token) > 0)
        decoded = _decode_play_token(token)
        self.assertIsNotNone(decoded)
        sig_bytes, payload_str = decoded
        self.assertEqual(len(sig_bytes), HMAC_SIG_BYTES)
        self.assertTrue(payload_str.startswith("rtp|385F2197|"))

    def test_generate_token_contains_app_stream_expire(self):
        from app.core.play_token import generate_play_token, _decode_play_token
        token = generate_play_token("live", "test_stream", 300)
        decoded = _decode_play_token(token)
        self.assertIsNotNone(decoded)
        _, payload_str = decoded
        parts = payload_str.split("|")
        self.assertEqual(len(parts), 3)
        self.assertEqual(parts[0], "live")
        self.assertEqual(parts[1], "test_stream")

    def test_generate_token_min_ttl(self):
        from app.core.play_token import generate_play_token, _decode_play_token, MIN_TOKEN_TTL
        token = generate_play_token("rtp", "test", 1)
        decoded = _decode_play_token(token)
        _, payload_str = decoded
        parts = payload_str.split("|")
        expire_ts = int(parts[2])
        now = int(time.time())
        self.assertGreaterEqual(expire_ts - now, MIN_TOKEN_TTL)


class TestVerifyPlayToken(unittest.TestCase):
    def test_valid_token(self):
        from app.core.play_token import generate_play_token, verify_play_token
        token = generate_play_token("rtp", "385F2197", 300)
        is_valid, error_msg = verify_play_token(token, "rtp", "385F2197")
        self.assertTrue(is_valid)
        self.assertEqual(error_msg, "")

    def test_empty_token(self):
        from app.core.play_token import verify_play_token
        is_valid, error_msg = verify_play_token("", "rtp", "385F2197")
        self.assertFalse(is_valid)
        self.assertEqual(error_msg, "missing or invalid play token")

    def test_invalid_base64_token(self):
        from app.core.play_token import verify_play_token
        is_valid, error_msg = verify_play_token("!!!invalid!!!", "rtp", "385F2197")
        self.assertFalse(is_valid)
        self.assertIn("invalid", error_msg)

    def test_tampered_signature(self):
        from app.core.play_token import generate_play_token, verify_play_token, _decode_play_token
        import base64
        token = generate_play_token("rtp", "385F2197", 300)
        padding = 4 - len(token) % 4
        if padding != 4:
            token_padded = token + "=" * padding
        else:
            token_padded = token
        decoded_bytes = base64.urlsafe_b64decode(token_padded)
        tampered = bytes([decoded_bytes[0] ^ 0xFF]) + decoded_bytes[1:]
        tampered_token = base64.urlsafe_b64encode(tampered).decode().rstrip("=")
        is_valid, error_msg = verify_play_token(tampered_token, "rtp", "385F2197")
        self.assertFalse(is_valid)
        self.assertEqual(error_msg, "invalid play token")

    def test_expired_token(self):
        from app.core.play_token import generate_play_token, verify_play_token, _get_secret_key, HMAC_SIG_BYTES
        import hmac
        import hashlib
        import base64
        with patch("app.core.play_token.settings") as mock_settings:
            mock_settings.SECRET_KEY = "test-secret"
            expired_payload = f"rtp|385F2197|{int(time.time()) - 100}"
            sig = hmac.new(
                _get_secret_key(),
                expired_payload.encode("utf-8"),
                hashlib.sha256,
            ).digest()[:HMAC_SIG_BYTES]
            expired_token = base64.urlsafe_b64encode(sig + expired_payload.encode("utf-8")).decode().rstrip("=")
            is_valid, error_msg = verify_play_token(expired_token, "rtp", "385F2197")
            self.assertFalse(is_valid)
            self.assertEqual(error_msg, "expired play token")

    def test_app_stream_mismatch(self):
        from app.core.play_token import generate_play_token, verify_play_token
        token = generate_play_token("rtp", "385F2197", 300)
        is_valid, error_msg = verify_play_token(token, "live", "385F2197")
        self.assertFalse(is_valid)
        self.assertEqual(error_msg, "token stream mismatch")
        is_valid2, error_msg2 = verify_play_token(token, "rtp", "OTHER_STREAM")
        self.assertFalse(is_valid2)
        self.assertEqual(error_msg2, "token stream mismatch")


class TestExtractTokenFromParams(unittest.TestCase):
    def test_string_format(self):
        from app.core.play_token import extract_token_from_params
        self.assertEqual(extract_token_from_params("token=abc123&other=xyz"), "abc123")

    def test_string_format_with_question_mark(self):
        from app.core.play_token import extract_token_from_params
        self.assertEqual(extract_token_from_params("?token=abc123&other=xyz"), "abc123")

    def test_dict_format(self):
        from app.core.play_token import extract_token_from_params
        self.assertEqual(extract_token_from_params({"token": "abc123", "other": "xyz"}), "abc123")

    def test_none_input(self):
        from app.core.play_token import extract_token_from_params
        self.assertEqual(extract_token_from_params(None), "")

    def test_missing_token_in_string(self):
        from app.core.play_token import extract_token_from_params
        self.assertEqual(extract_token_from_params("other=xyz"), "")

    def test_missing_token_in_dict(self):
        from app.core.play_token import extract_token_from_params
        self.assertEqual(extract_token_from_params({"other": "xyz"}), "")


class TestGetSecretKey(unittest.TestCase):
    @patch("app.core.play_token.settings")
    def test_fallback_secret(self, mock_settings):
        from app.core.play_token import _get_secret_key, FALLBACK_SECRET
        mock_settings.SECRET_KEY = ""
        key = _get_secret_key()
        self.assertEqual(key, FALLBACK_SECRET.encode("utf-8"))

    @patch("app.core.play_token.settings")
    def test_real_secret(self, mock_settings):
        from app.core.play_token import _get_secret_key
        mock_settings.SECRET_KEY = "my-test-secret"
        key = _get_secret_key()
        self.assertEqual(key, b"my-test-secret")


class TestShouldAllowNoToken(unittest.TestCase):
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
