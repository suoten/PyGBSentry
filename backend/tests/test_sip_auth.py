"""SIP Digest Authentication tests.

Covers: nonce issuance/signing, RFC 2617 response calculation (MD5 / MD5-sess /
SHA-256), header parsing, algorithm negotiation, and replay-protection basics.
"""
import hashlib
import hmac
import sys
import types
import time
import unittest


def _install_test_settings() -> None:
    """Ensure app.core.config.settings has the minimum attributes tests need."""
    settings_obj = types.SimpleNamespace(
        SECRET_KEY="test-secret-key-for-testing",
        SIP_NONCE_SECRET="test-sip-nonce-secret",
        APP_ENV="test",
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


class TestSipDigestAuth(unittest.IsolatedAsyncioTestCase):
    """DigestAuth — RFC 2617 / 7616 compliance and SIP-specific extensions."""

    def setUp(self) -> None:
        _install_test_settings()

    # 1. Nonce format and signature ----------------------------------------

    async def test_generate_nonce_format(self):
        """Nonce must be ``timestamp:random_hex:hmac_hex`` (3 colon-separated parts)."""
        from app.sip.auth import DigestAuth

        nonce = DigestAuth.generate_nonce()
        parts = nonce.split(":")
        self.assertEqual(len(parts), 3)
        self.assertTrue(parts[0].isdigit(), "first part must be a unix timestamp")
        self.assertEqual(len(parts[1]), 16, "random part must be 16 hex chars")
        self.assertEqual(len(parts[2]), 64, "HMAC-SHA256 signature must be 64 hex chars")

    async def test_validate_nonce_signature_valid(self):
        """A freshly generated nonce must pass signature validation."""
        from app.sip.auth import DigestAuth

        nonce = DigestAuth.generate_nonce()
        self.assertTrue(DigestAuth.validate_nonce_signature(nonce))

    async def test_validate_nonce_tampered_rejected(self):
        """A tampered nonce (modified timestamp/random) must be rejected."""
        from app.sip.auth import DigestAuth

        nonce = DigestAuth.generate_nonce()
        ts, rnd, _sig = nonce.split(":")
        # Forge a different signature — must not validate
        forged = f"{ts}:{rnd}{'0' if rnd[-1] != '0' else '1'}:deadbeef" * 1
        forged = f"{ts}:{rnd}:{'a' * 64}"
        self.assertFalse(DigestAuth.validate_nonce_signature(forged))
        # Truncated nonce
        self.assertFalse(DigestAuth.validate_nonce_signature("abc"))
        self.assertFalse(DigestAuth.validate_nonce_signature(""))

    # 2. Response calculation (MD5) ----------------------------------------

    async def test_calculate_response_md5_no_qop(self):
        """RFC 2617 §3.2.2 — response = MD5(HA1:nonce:HA2) when qop is absent."""
        from app.sip.auth import DigestAuth

        username = "testuser"
        realm = "testrealm@host.com"
        password = "secret123"
        method = "REGISTER"
        uri = f"sip:{realm}"
        nonce = "dcd98b7102dd2f0e8b11d0f600bfb0c093"

        expected_ha1 = hashlib.md5(f"{username}:{realm}:{password}".encode()).hexdigest()
        expected_ha2 = hashlib.md5(f"{method}:{uri}".encode()).hexdigest()
        expected = hashlib.md5(f"{expected_ha1}:{nonce}:{expected_ha2}".encode()).hexdigest()

        result = DigestAuth.calculate_response(
            username=username, password=password, realm=realm,
            method=method, uri=uri, nonce=nonce,
        )
        self.assertEqual(result, expected)

    async def test_calculate_response_md5_qop_auth(self):
        """RFC 2617 qop=auth — response includes nc, cnonce, qop."""
        from app.sip.auth import DigestAuth

        username = "admin"
        realm = "pygbsentry.local"
        password = "admin_pass"
        method = "REGISTER"
        uri = f"sip:{realm}"
        nonce = "OA6MG9t3GzQK3b0OdQqNQbfqMzFRFm3A"
        nc = "00000001"
        cnonce = "0a4f113b"
        qop = "auth"

        ha1 = hashlib.md5(f"{username}:{realm}:{password}".encode()).hexdigest()
        ha2 = hashlib.md5(f"{method}:{uri}".encode()).hexdigest()
        expected = hashlib.md5(
            f"{ha1}:{nonce}:{nc}:{cnonce}:{qop}:{ha2}".encode()
        ).hexdigest()

        result = DigestAuth.calculate_response(
            username=username, password=password, realm=realm,
            method=method, uri=uri, nonce=nonce,
            nc=nc, cnonce=cnonce, qop=qop, algorithm="MD5",
        )
        self.assertEqual(result, expected)

    # 3. Response calculation (MD5-sess) -----------------------------------

    async def test_calculate_response_md5_sess(self):
        """MD5-sess — HA1 = MD5(MD5(user:realm:pass):nonce:cnonce)."""
        from app.sip.auth import DigestAuth

        username = "device001"
        realm = "3402000000"
        password = "device_pass"
        method = "REGISTER"
        uri = f"sip:{realm}"
        nonce = "nonce123"
        nc = "00000001"
        cnonce = "cnonce456"
        qop = "auth"

        ha1_base = hashlib.md5(f"{username}:{realm}:{password}".encode()).hexdigest()
        ha1 = hashlib.md5(f"{ha1_base}:{nonce}:{cnonce}".encode()).hexdigest()
        ha2 = hashlib.md5(f"{method}:{uri}".encode()).hexdigest()
        expected = hashlib.md5(
            f"{ha1}:{nonce}:{nc}:{cnonce}:{qop}:{ha2}".encode()
        ).hexdigest()

        result = DigestAuth.calculate_response(
            username=username, password=password, realm=realm,
            method=method, uri=uri, nonce=nonce,
            nc=nc, cnonce=cnonce, qop=qop, algorithm="MD5-SESS",
        )
        self.assertEqual(result, expected)

    # 4. Header parsing ----------------------------------------------------

    async def test_parse_auth_header(self):
        """Parse a realistic Digest Authorization header into a dict."""
        from app.sip.auth import DigestAuth

        header = (
            'Digest username="admin", realm="pygbsentry.local", '
            'nonce="abc123", uri="sip:pygbsentry.local", '
            'response="deadbeef", algorithm=MD5, qop=auth, '
            'nc=00000001, cnonce="0a4f113b"'
        )
        params = DigestAuth.parse_auth_header(header)
        self.assertEqual(params["username"], "admin")
        self.assertEqual(params["realm"], "pygbsentry.local")
        self.assertEqual(params["nonce"], "abc123")
        self.assertEqual(params["algorithm"], "MD5")
        self.assertEqual(params["qop"], "auth")
        self.assertEqual(params["nc"], "00000001")

    async def test_parse_auth_header_empty(self):
        """Empty / None headers must produce an empty dict, not raise."""
        from app.sip.auth import DigestAuth

        self.assertEqual(DigestAuth.parse_auth_header(""), {})
        self.assertEqual(DigestAuth.parse_auth_header(None), {})

    # 5. Algorithm negotiation --------------------------------------------

    async def test_select_preferred_algorithm_md5_default(self):
        """When no algorithm is specified, default to MD5 (RFC 2617)."""
        from app.sip.auth import DigestAuth

        self.assertEqual(DigestAuth.select_preferred_algorithm({}), "MD5")
        self.assertEqual(
            DigestAuth.select_preferred_algorithm({"algorithm": ""}),
            "MD5",
        )

    async def test_select_preferred_algorithm_sha256_preferred(self):
        """When both MD5 and SHA-256 are offered, SHA-256 should be preferred."""
        from app.sip.auth import DigestAuth

        params = {"algorithm": "MD5, SHA-256"}
        self.assertEqual(
            DigestAuth.select_preferred_algorithm(params),
            "SHA-256",
        )

    # 6. Wrong password produces different response ------------------------

    async def test_wrong_password_different_response(self):
        """A wrong password must produce a different response value."""
        from app.sip.auth import DigestAuth

        common = dict(
            username="user", realm="realm", method="REGISTER",
            uri="sip:realm", nonce="nonce123",
        )
        correct = DigestAuth.calculate_response(password="correct_pass", **common)
        wrong = DigestAuth.calculate_response(password="wrong_pass", **common)
        self.assertNotEqual(correct, wrong)

    async def test_hmac_compare_digest_timing_safe(self):
        """The response comparison must use hmac.compare_digest (timing-safe)."""
        from app.sip.auth import DigestAuth

        nonce = DigestAuth.generate_nonce()
        params = {
            "username": "user", "realm": "realm", "method": "REGISTER",
            "uri": "sip:realm", "nonce": nonce, "nc": "00000001",
            "cnonce": "cn", "qop": "auth", "algorithm": "MD5",
        }
        expected = DigestAuth.calculate_response(password="pass", **params)
        # compare_digest should return True for equal strings
        self.assertTrue(hmac.compare_digest(expected, expected))
        # And False for different strings
        self.assertFalse(hmac.compare_digest(expected, "0" * 32))


if __name__ == "__main__":
    unittest.main()
