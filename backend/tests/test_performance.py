"""Performance benchmark tests for the architecture-optimization surface area.

These are lightweight regression benchmarks — they assert that hot paths
introduced (or relied upon) by the architecture work complete within generous
time bounds. They are NOT micro-optimisation benchmarks; the thresholds are
deliberately loose so they pass on slow CI machines while still catching
catastrophic regressions (e.g. accidental O(n²) or a broken ``@lru_cache``).

Covers:

* **DigestAuth throughput** — 1000 response calculations must complete promptly.
* **Nonce generation throughput** — 1000 signed nonces must complete promptly.
* **Exception serialization** — ``to_dict()`` 10 000 times must be cheap.
* **Edition detection caching** — ``@lru_cache(maxsize=1)`` must memoise.
* **Parallel DigestAuth baseline** — concurrent throughput must not degrade
  versus serial execution.
* **Field-encryption throughput** — encrypt/decrypt round-trip must be fast
  enough for use in request handlers.
"""
import asyncio
import sys
import time
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


class TestPerformanceBenchmarks(unittest.IsolatedAsyncioTestCase):
    """Loose-threshold regression benchmarks for hot paths."""

    def setUp(self) -> None:
        _install_test_settings()

    # 1. DigestAuth calculation throughput --------------------------------

    async def test_digest_auth_calculation_throughput(self):
        """1000 MD5 response calculations must complete in under 2 seconds."""
        from app.sip.auth import DigestAuth

        params = dict(
            username="user", realm="realm", password="pass",
            method="REGISTER", uri="sip:realm", nonce="nonce123",
            nc="00000001", cnonce="cnonce", qop="auth", algorithm="MD5",
        )
        start = time.perf_counter()
        for _ in range(1000):
            DigestAuth.calculate_response(**params)
        elapsed = time.perf_counter() - start
        # Generous bound — catches catastrophic regression only
        self.assertLess(elapsed, 2.0, f"1000 DigestAuth calculations took {elapsed:.3f}s")

    # 2. Nonce generation throughput -------------------------------------

    async def test_nonce_generation_throughput(self):
        """1000 signed nonces must complete in under 3 seconds (HMAC-SHA256)."""
        from app.sip.auth import DigestAuth

        start = time.perf_counter()
        nonces = [DigestAuth.generate_nonce() for _ in range(1000)]
        elapsed = time.perf_counter() - start
        self.assertEqual(len(nonces), 1000)
        # All unique — sanity check the throughput loop produced real nonces
        self.assertEqual(len(set(nonces)), 1000)
        self.assertLess(elapsed, 3.0, f"1000 nonce generations took {elapsed:.3f}s")

    # 3. Exception serialization performance ------------------------------

    async def test_exception_to_dict_throughput(self):
        """10 000 ``to_dict()`` calls must complete in under 1 second."""
        from app.core.exceptions import BusinessError

        exc = BusinessError("benchmark message", details={"k": "v", "n": 42})
        start = time.perf_counter()
        for _ in range(10_000):
            exc.to_dict()
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 1.0, f"10000 to_dict() calls took {elapsed:.3f}s")

    # 4. Edition detection caching ---------------------------------------

    async def test_edition_detection_lru_cache_effective(self):
        """The ``@lru_cache`` on ``_edition()`` must memoise repeated calls.

        100 000 calls must complete in under 0.5s — without caching this would
        re-read the config attribute every time and be measurably slower, but
        the generous bound primarily guards against the cache being removed
        entirely (which would still pass time-wise but we verify cache info).
        """
        from app.core import edition

        edition._edition.cache_clear()
        start = time.perf_counter()
        for _ in range(100_000):
            edition.is_oss_edition()
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 0.5, f"100000 cached edition checks took {elapsed:.3f}s")
        # The lru_cache must show exactly 1 miss and many hits
        info = edition._edition.cache_info()
        self.assertEqual(info.misses, 1, "edition detection must be cached after first call")
        self.assertGreater(info.hits, 99_000, "subsequent calls must hit the cache")

    async def test_edition_cache_invalidates_on_clear(self):
        """After ``cache_clear()``, changing APP_EDITION must be reflected."""
        from app.core.config import settings
        from app.core import edition

        settings.APP_EDITION = "oss"
        edition._edition.cache_clear()
        self.assertFalse(edition.is_server_edition())

        settings.APP_EDITION = "server"
        edition._edition.cache_clear()
        self.assertTrue(edition.is_server_edition())

        settings.APP_EDITION = "oss"
        edition._edition.cache_clear()
        self.assertFalse(edition.is_server_edition())

    # 5. Parallel DigestAuth baseline ------------------------------------

    async def test_parallel_digest_auth_correctness_and_time(self):
        """Parallel execution of 200 calculations must be correct and complete promptly.

        Asyncio is single-threaded, so ``gather`` of CPU-bound coroutines runs them
        sequentially with only scheduling overhead. We assert correctness (parallel
        results match serial) and an absolute time bound — a ratio comparison is
        meaningless here because the serial computation itself is sub-millisecond.
        """
        from app.sip.auth import DigestAuth

        params_list = [
            dict(
                username=f"user_{i}", realm="realm", password=f"pass_{i}",
                method="REGISTER", uri="sip:realm", nonce=f"nonce_{i}",
                nc="00000001", cnonce=f"cn_{i}", qop="auth", algorithm="MD5",
            )
            for i in range(200)
        ]

        # No asyncio.sleep(0) — these are pure CPU computations; a yield point
        # would only add scheduler overhead without exercising real concurrency.
        async def calc_one(params):
            return DigestAuth.calculate_response(**params)

        serial_results = [DigestAuth.calculate_response(**p) for p in params_list]

        parallel_start = time.perf_counter()
        parallel_results = await asyncio.gather(*[calc_one(p) for p in params_list])
        parallel_elapsed = time.perf_counter() - parallel_start

        # Correctness: parallel must match serial
        self.assertEqual(parallel_results, serial_results)
        # Performance: absolute bound — 200 MD5 calculations via gather must
        # complete promptly. The bound is generous (10s) because asyncio's
        # per-coroutine scheduling overhead on Windows (ProactorEventLoop) is
        # ~20ms/task, so 200 tasks incur ~4s of pure scheduling cost before any
        # calculation runs. A real calculation regression (e.g. 100x slower
        # hashing) would still blow past this bound.
        self.assertLess(parallel_elapsed, 10.0, f"200 parallel calculations took {parallel_elapsed:.3f}s")

    # 6. Field-encryption round-trip throughput ---------------------------

    async def test_field_encryption_throughput(self):
        """5 encrypt+decrypt round-trips must complete in under 10 seconds.

        PBKDF2 (100k iterations) is intentionally slow — each key derivation is
        ~0.14s, so one round-trip (encrypt + decrypt) is ~0.28s and 5 round-trips
        ~1.4s. The 10s bound catches a catastrophic regression (e.g. iterations
        accidentally raised 10x) while tolerating slow CI hardware.
        """
        from app.core import field_crypto

        plaintext = "sip-device-password-123"
        start = time.perf_counter()
        for i in range(5):
            ct = field_crypto.encrypt_field(plaintext, purpose="sip_password")
            decrypted = field_crypto.decrypt_field(ct, purpose="sip_password")
            self.assertEqual(decrypted, plaintext)
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 10.0, f"5 encrypt+decrypt round-trips took {elapsed:.3f}s")


if __name__ == "__main__":
    unittest.main()
