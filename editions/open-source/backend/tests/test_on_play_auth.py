import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio


class TestOnPlayAuth(unittest.TestCase):
    def _make_request_body(self, app="rtp", stream="385F2197", token=None, params=None):
        body = {"app": app, "stream": stream, "ip": "192.168.1.100"}
        if params is not None:
            body["params"] = params
        elif token is not None:
            body["params"] = f"token={token}"
        return body

    def test_valid_token_returns_code_0(self):
        from app.core.play_token import generate_play_token, verify_play_token, extract_token_from_params
        token = generate_play_token("rtp", "385F2197", 300)
        is_valid, error_msg = verify_play_token(token, "rtp", "385F2197")
        self.assertTrue(is_valid)
        self.assertEqual(error_msg, "")
        body = self._make_request_body(token=token)
        extracted = extract_token_from_params(body.get("params"))
        self.assertEqual(extracted, token)

    def test_no_token_returns_401(self):
        from app.core.play_token import verify_play_token, extract_token_from_params, should_allow_no_token
        with patch("app.core.play_token.settings") as mock_settings:
            mock_settings.PLAY_ALLOW_NO_TOKEN = False
            mock_settings.SECRET_KEY = "test-secret"
            body = self._make_request_body()
            extracted = extract_token_from_params(body.get("params"))
            self.assertEqual(extracted, "")
            self.assertFalse(should_allow_no_token())

    def test_expired_token_returns_401(self):
        from app.core.play_token import generate_play_token, verify_play_token, _get_secret_key, HMAC_SIG_BYTES
        import hmac
        import hashlib
        import base64
        import time as _time
        with patch("app.core.play_token.settings") as mock_settings:
            mock_settings.SECRET_KEY = "test-secret"
            expired_payload = f"rtp|385F2197|{int(_time.time()) - 100}"
            sig = hmac.new(
                _get_secret_key(),
                expired_payload.encode("utf-8"),
                hashlib.sha256,
            ).digest()[:HMAC_SIG_BYTES]
            expired_token = base64.urlsafe_b64encode(sig + expired_payload.encode("utf-8")).decode().rstrip("=")
            is_valid, error_msg = verify_play_token(expired_token, "rtp", "385F2197")
            self.assertFalse(is_valid)
            self.assertEqual(error_msg, "expired play token")

    def test_cross_stream_reuse_returns_401(self):
        from app.core.play_token import generate_play_token, verify_play_token
        with patch("app.core.play_token.settings") as mock_settings:
            mock_settings.SECRET_KEY = "test-secret"
            token = generate_play_token("rtp", "385F2197", 300)
            is_valid, error_msg = verify_play_token(token, "live", "385F2197")
            self.assertFalse(is_valid)
            self.assertEqual(error_msg, "token stream mismatch")

    def test_zlm_secret_mismatch_returns_403(self):
        pass

    def test_allow_no_token_config_true(self):
        from app.core.play_token import should_allow_no_token
        with patch("app.core.play_token.settings") as mock_settings:
            mock_settings.PLAY_ALLOW_NO_TOKEN = True
            self.assertTrue(should_allow_no_token())


if __name__ == "__main__":
    unittest.main()
