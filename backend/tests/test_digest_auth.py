"""Tests for Digest Auth replay protection."""
import unittest
import sys
import types
import time


def _install_test_settings_stub() -> None:
    settings_obj = types.SimpleNamespace(
        SECRET_KEY="test-secret-key-for-testing",
        APP_ENV="dev",
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
            setattr(existing.settings, k, v)


class TestDigestAuth(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        _install_test_settings_stub()

    async def test_issue_nonce_format(self):
        from app.sip.handlers import _issue_digest_nonce

        nonce = _issue_digest_nonce()
        parts = nonce.split(":")
        self.assertEqual(len(parts), 3)
        self.assertTrue(parts[0].isdigit())  # timestamp
        self.assertEqual(len(parts[1]), 16)  # random hex
        self.assertEqual(len(parts[2]), 64)  # hmac sha256

    async def test_validate_nonce_valid(self):
        from app.sip.handlers import _issue_digest_nonce, _validate_digest_replay

        nonce = _issue_digest_nonce()
        params = {"nonce": nonce, "nc": "00000001", "username": "testuser"}
        ok, reason = await _validate_digest_replay(params, "testuser")
        self.assertTrue(ok)
        self.assertEqual(reason, "")

    async def test_validate_nonce_stale(self):
        from app.sip.handlers import _validate_digest_replay

        old_ts = int(time.time()) - 600
        nonce = f"{old_ts}:abc123:deadbeef"
        params = {"nonce": nonce, "nc": "00000001", "username": "testuser"}
        ok, reason = await _validate_digest_replay(params, "testuser")
        # FIXED-P2: stale nonce应返回ok=False，与handlers.py中_validate_digest_replay实际行为一致
        self.assertFalse(ok)
        self.assertEqual(reason, "stale nonce")

    async def test_validate_nonce_invalid_format(self):
        from app.sip.handlers import _validate_digest_replay

        params = {"nonce": "invalid-nonce", "nc": "00000001", "username": "testuser"}
        ok, reason = await _validate_digest_replay(params, "testuser")
        # FIXED-P2: 默认严格模式下无效nonce格式应被拒绝
        self.assertFalse(ok)
        self.assertIn("invalid nonce format", reason)

    async def test_validate_nonce_replay_attack(self):
        from app.sip.handlers import _issue_digest_nonce, _validate_digest_replay

        nonce = _issue_digest_nonce()
        params = {"nonce": nonce, "nc": "00000001", "username": "testuser"}
        ok1, _ = await _validate_digest_replay(params, "testuser")
        self.assertTrue(ok1)

        params2 = {"nonce": nonce, "nc": "00000001", "username": "testuser"}
        ok2, reason = await _validate_digest_replay(params2, "testuser")
        self.assertTrue(ok2)
        self.assertIn("nc replay", reason)

    async def test_validate_nonce_greater_nc_allowed(self):
        from app.sip.handlers import _issue_digest_nonce, _validate_digest_replay

        nonce = _issue_digest_nonce()
        params1 = {"nonce": nonce, "nc": "00000001", "username": "testuser"}
        ok1, _ = await _validate_digest_replay(params1, "testuser")
        self.assertTrue(ok1)

        params2 = {"nonce": nonce, "nc": "00000002", "username": "testuser"}
        ok2, _ = await _validate_digest_replay(params2, "testuser")
        self.assertTrue(ok2)


class TestDigestAuthStrictMode(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        settings_obj = types.SimpleNamespace(
            SECRET_KEY="test-secret-key-for-testing",
            APP_ENV="prod",
        )
        existing = sys.modules.get("app.core.config")
        if existing is None:
            m = types.ModuleType("app.core.config")
            m.settings = settings_obj
            sys.modules["app.core.config"] = m
        else:
            if not hasattr(existing, "settings") or existing.settings is None:
                existing.settings = settings_obj
            else:
                for k, v in settings_obj.__dict__.items():
                    if not hasattr(existing.settings, k):
                        setattr(existing.settings, k, v)

    async def test_validate_nonce_stale_strict_rejects(self):
        from app.sip.handlers import _validate_digest_replay

        old_ts = int(time.time()) - 600
        nonce = f"{old_ts}:abc123:deadbeef"
        params = {"nonce": nonce, "nc": "00000001", "username": "testuser"}
        ok, reason = await _validate_digest_replay(params, "testuser")
        self.assertFalse(ok)
        self.assertEqual(reason, "stale nonce")

    async def test_validate_nonce_invalid_format_strict_rejects(self):
        from app.sip.handlers import _validate_digest_replay

        params = {"nonce": "invalid", "nc": "00000001", "username": "testuser"}
        ok, reason = await _validate_digest_replay(params, "testuser")
        self.assertFalse(ok)
        self.assertIn("invalid nonce format", reason)


if __name__ == "__main__":
    unittest.main()
