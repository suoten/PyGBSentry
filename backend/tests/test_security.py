"""Security penetration tests for the architecture-optimization surface area.

Covers the security-critical invariants introduced (or hardened) by the
architecture work:

* **Exception hierarchy** — ``AppException.to_dict()`` must not leak stack
  traces and every subclass must carry a stable ``error_code`` + ``status_code``.
* **Edition separation** — OSS edition must never report server-edition feature
  flags as enabled, and the centralised detector must reflect ``APP_EDITION``.
* **Field-encryption key isolation** — ``field_crypto`` must refuse to operate
  when ``FIELD_ENCRYPTION_KEY`` is absent; it must not silently fall back to
  ``SECRET_KEY`` (key-separation regression guard).
* **API version negotiation** — ``negotiate_version`` must honour URL path,
  ``Accept-Version`` header, and ``Accept`` content-type parameter, and must
  reject unknown versions by falling back to the default.
* **Nonce forgery prevention** — ``validate_nonce_signature`` must reject
  tampered / truncated / forged nonces so an attacker cannot mint valid nonces.

These are pure unit tests (no network, no DB) so they run in any environment.
"""
import sys
import types
import unittest


def _install_test_settings() -> None:
    """Install a minimal ``app.core.config.settings`` namespace for tests."""
    settings_obj = types.SimpleNamespace(
        SECRET_KEY="test-secret-key-for-testing",
        SIP_NONCE_SECRET="test-sip-nonce-secret",
        APP_ENV="test",
        APP_EDITION="oss",
        FIELD_ENCRYPTION_KEY="test-field-encryption-key-0123456789",
        PLUGIN_MARKETPLACE_ENABLED=False,
        PROJECT_NAME="PyGBSentry",
        SIP_REALM="pygbsentry.local",
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


def _make_request(path: str, headers: dict | None = None):
    """Build a minimal Starlette Request for ``negotiate_version`` testing."""
    from starlette.requests import Request

    raw_headers = [
        (k.lower().encode("latin-1"), v.encode("latin-1"))
        for k, v in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("latin-1"),
        "query_string": b"",
        "headers": raw_headers,
        "server": ("testserver", 80),
        "client": ("testclient", 12345),
        "root_path": "",
        "app": None,
        "state": None,
        "router": None,
        "endpoint": None,
        "session": {},
    }
    return Request(scope)


class TestSecurityPenetration(unittest.IsolatedAsyncioTestCase):
    """Security-focused regression tests for the architecture surface area."""

    def setUp(self) -> None:
        _install_test_settings()

    # 1. Exception hierarchy serialization --------------------------------

    async def test_exception_to_dict_structure(self):
        """``AppException.to_dict()`` must expose a stable, leak-free structure."""
        from app.core.exceptions import AppException

        exc = AppException("boom", details={"field": "value"})
        payload = exc.to_dict()
        self.assertEqual(payload["detail"], "boom")
        self.assertEqual(payload["message"], "boom")
        self.assertEqual(payload["status_code"], 400)
        self.assertEqual(payload["error_code"], "ERR_APP")
        self.assertEqual(payload["details"], {"field": "value"})
        # Must not leak Python stack/traceback internals
        for key in payload:
            self.assertNotIn("traceback", key.lower())
            self.assertNotIn("exc_info", key.lower())

    async def test_exception_subclass_status_codes(self):
        """Every subclass must carry its documented status_code + error_code."""
        from app.core.exceptions import (
            ValidationError,
            AuthenticationError,
            PermissionError,
            NotFoundError,
            BusinessError,
            ConflictException,
        )

        cases = [
            (ValidationError, 422, "ERR_VALIDATION"),
            (AuthenticationError, 401, "ERR_AUTHENTICATION"),
            (PermissionError, 403, "ERR_PERMISSION_DENIED"),
            (NotFoundError, 404, "ERR_NOT_FOUND"),
            (BusinessError, 400, "ERR_BUSINESS"),
            (ConflictException, 409, "ERR_CONFLICT"),
        ]
        for cls, expected_status, expected_code in cases:
            exc = cls("test")
            self.assertEqual(exc.status_code, expected_status, f"{cls.__name__} status")
            self.assertEqual(exc.error_code, expected_code, f"{cls.__name__} code")
            payload = exc.to_dict()
            self.assertEqual(payload["status_code"], expected_status)
            self.assertEqual(payload["error_code"], expected_code)

    async def test_exception_per_instance_override(self):
        """Callers may override status_code/error_code per instance."""
        from app.core.exceptions import BusinessError

        exc = BusinessError("custom", status_code=418, error_code="ERR_TEAPOT")
        self.assertEqual(exc.status_code, 418)
        self.assertEqual(exc.error_code, "ERR_TEAPOT")
        self.assertEqual(exc.to_dict()["error_code"], "ERR_TEAPOT")

    async def test_exception_backward_compat_aliases(self):
        """Backward-compatible aliases must resolve to the new classes."""
        from app.core import exceptions as exc_mod

        self.assertIs(exc_mod.ValidationException, exc_mod.ValidationError)
        self.assertIs(exc_mod.PermissionDeniedException, exc_mod.PermissionError)
        self.assertIs(exc_mod.NotFoundException, exc_mod.NotFoundError)

    # 2. Edition separation enforcement -----------------------------------

    async def test_oss_edition_defaults(self):
        """OSS edition must report is_oss_edition() True, is_server_edition() False."""
        from app.core.config import settings
        from app.core import edition

        settings.APP_EDITION = "oss"
        edition._edition.cache_clear()
        self.assertTrue(edition.is_oss_edition())
        self.assertFalse(edition.is_server_edition())
        self.assertEqual(edition.edition_label(), "oss")
        # Feature flags must all be off in OSS
        self.assertFalse(edition.has_plugin_marketplace())
        self.assertFalse(edition.has_license_verification())
        self.assertFalse(edition.has_quota_enforcement())

    async def test_server_edition_detection(self):
        """``APP_EDITION=server`` flips the flags but only marketplace is gated."""
        from app.core.config import settings
        from app.core import edition

        settings.APP_EDITION = "server"
        settings.PLUGIN_MARKETPLACE_ENABLED = True
        edition._edition.cache_clear()
        try:
            self.assertFalse(edition.is_oss_edition())
            self.assertTrue(edition.is_server_edition())
            self.assertEqual(edition.edition_label(), "server")
            self.assertTrue(edition.has_license_verification())
            self.assertTrue(edition.has_quota_enforcement())
            self.assertTrue(edition.has_plugin_marketplace())
        finally:
            # Restore OSS defaults so subsequent tests are not affected
            settings.APP_EDITION = "oss"
            settings.PLUGIN_MARKETPLACE_ENABLED = False
            edition._edition.cache_clear()

    async def test_edition_detector_unknown_value_defaults_oss(self):
        """An unrecognised APP_EDITION value must NOT be treated as server."""
        from app.core.config import settings
        from app.core import edition

        settings.APP_EDITION = "totally-bogus"
        edition._edition.cache_clear()
        try:
            self.assertFalse(edition.is_server_edition())
            self.assertEqual(edition.edition_label(), "oss")
        finally:
            settings.APP_EDITION = "oss"
            edition._edition.cache_clear()

    # 3. Field-encryption key isolation -----------------------------------

    async def test_field_encryption_no_secret_key_fallback(self):
        """Missing FIELD_ENCRYPTION_KEY must raise — never fall back to SECRET_KEY."""
        from app.core.config import settings
        from app.core import field_crypto

        original = getattr(settings, "FIELD_ENCRYPTION_KEY", "")
        settings.FIELD_ENCRYPTION_KEY = ""
        try:
            with self.assertRaises(ValueError):
                field_crypto.encrypt_field("secret-data")
            # The error message must guide operators, not mention a fallback
            with self.assertRaises(ValueError) as ctx:
                field_crypto._derive_key("sip_password")
            self.assertIn("FIELD_ENCRYPTION_KEY", str(ctx.exception))
        finally:
            settings.FIELD_ENCRYPTION_KEY = original

    async def test_field_encryption_round_trip(self):
        """encrypt → decrypt must return the original plaintext."""
        from app.core import field_crypto

        plaintext = "super-secret-sip-password"
        for purpose in ("sip_password", "platform_password", "custom_purpose"):
            ct = field_crypto.encrypt_field(plaintext, purpose=purpose)
            self.assertNotEqual(ct, plaintext, "ciphertext must not equal plaintext")
            self.assertNotEqual(ct, "", "ciphertext must not be empty")
            decrypted = field_crypto.decrypt_field(ct, purpose=purpose)
            self.assertEqual(decrypted, plaintext, f"round-trip failed for purpose={purpose}")

    async def test_field_encryption_different_purpose_different_ciphertext(self):
        """Different purposes must derive different keys → different ciphertexts."""
        from app.core import field_crypto

        plaintext = "same-plaintext"
        ct_a = field_crypto.encrypt_field(plaintext, purpose="purpose_a")
        ct_b = field_crypto.encrypt_field(plaintext, purpose="purpose_b")
        # AES-GCM uses a random nonce so ciphertexts differ even for same purpose,
        # but cross-purpose ciphertexts must definitely differ.
        self.assertNotEqual(ct_a, ct_b)

    async def test_field_encryption_tamper_detection(self):
        """Tampered ciphertext must fail to decrypt (returns None, not garbage)."""
        from app.core import field_crypto

        ct = field_crypto.encrypt_field("secret", purpose="sip_password")
        # Flip a character in the middle of the base64 payload
        tampered = ct[:8] + ("A" if ct[8] != "A" else "B") + ct[9:]
        result = field_crypto.decrypt_field(tampered, purpose="sip_password")
        self.assertIsNone(result, "tampered ciphertext must decrypt to None")

    # 4. API version negotiation ------------------------------------------

    async def test_negotiate_version_url_path(self):
        """URL path ``/api/v1/...`` must resolve to ``v1``."""
        from app.api.versioning import negotiate_version, DEFAULT_VERSION

        req = _make_request("/api/v1/devices")
        self.assertEqual(negotiate_version(req), "v1")
        # Exact version segment with no trailing path
        req2 = _make_request("/api/v1")
        self.assertEqual(negotiate_version(req2), "v1")
        # Non-API path falls through to default
        req3 = _make_request("/health")
        self.assertEqual(negotiate_version(req3), DEFAULT_VERSION)

    async def test_negotiate_version_accept_header(self):
        """``Accept-Version`` header must override the default."""
        from app.api.versioning import negotiate_version

        req = _make_request("/api/devices", headers={"Accept-Version": "v1"})
        self.assertEqual(negotiate_version(req), "v1")
        # Bare "1" must be normalised to "v1"
        req2 = _make_request("/api/devices", headers={"Accept-Version": "1"})
        self.assertEqual(negotiate_version(req2), "v1")

    async def test_negotiate_version_accept_content_type(self):
        """``Accept: application/json; version=1`` must be honoured."""
        from app.api.versioning import negotiate_version

        req = _make_request(
            "/api/devices",
            headers={"Accept": "application/json; version=1"},
        )
        self.assertEqual(negotiate_version(req), "v1")

    async def test_negotiate_version_unknown_falls_back(self):
        """An unknown version must fall back to the default, not raise."""
        from app.api.versioning import negotiate_version, DEFAULT_VERSION

        # Unknown version in header
        req = _make_request("/api/devices", headers={"Accept-Version": "v99"})
        self.assertEqual(negotiate_version(req), DEFAULT_VERSION)
        # Unknown version in URL path
        req2 = _make_request("/api/v99/devices")
        self.assertEqual(negotiate_version(req2), DEFAULT_VERSION)

    # 5. Nonce forgery prevention -----------------------------------------

    async def test_nonce_forgery_rejected(self):
        """Forged / tampered / truncated nonces must fail signature validation."""
        from app.sip.auth import DigestAuth

        valid = DigestAuth.generate_nonce()
        ts, rnd, _sig = valid.split(":")

        # Forged signature (correct format, wrong sig)
        forged_sig = "a" * 64
        self.assertFalse(DigestAuth.validate_nonce_signature(f"{ts}:{rnd}:{forged_sig}"))

        # Tampered random part
        tampered_rnd = rnd[:-1] + ("0" if rnd[-1] != "0" else "1")
        self.assertFalse(DigestAuth.validate_nonce_signature(f"{ts}:{tampered_rnd}:{_sig}"))

        # Tampered timestamp
        self.assertFalse(DigestAuth.validate_nonce_signature(f"{int(ts) + 1}:{rnd}:{_sig}"))

        # Truncated / malformed
        self.assertFalse(DigestAuth.validate_nonce_signature("abc"))
        self.assertFalse(DigestAuth.validate_nonce_signature(""))
        self.assertFalse(DigestAuth.validate_nonce_signature(None))  # type: ignore[arg-type]
        self.assertFalse(DigestAuth.validate_nonce_signature("a:b:c:d"))

    async def test_nonce_signature_not_constant_across_servers(self):
        """Nonces signed by one secret must not validate under a different secret."""
        from app.sip.auth import DigestAuth
        from app.core.config import settings

        original_secret = settings.SIP_NONCE_SECRET
        # Issue a nonce under secret A
        settings.SIP_NONCE_SECRET = "secret-alpha"
        nonce = DigestAuth.generate_nonce()
        # Switch to secret B — the nonce must no longer validate
        settings.SIP_NONCE_SECRET = "secret-beta"
        self.assertFalse(DigestAuth.validate_nonce_signature(nonce))
        # Switch back — it must validate again
        settings.SIP_NONCE_SECRET = original_secret
        self.assertTrue(DigestAuth.validate_nonce_signature(DigestAuth.generate_nonce()))


if __name__ == "__main__":
    unittest.main()
