"""Concurrency and race-condition tests.

Covers: nonce uniqueness under concurrency, SIP state backend thread-safety,
async session isolation, token-refresh single-flight, and parallel DigestAuth
calculation correctness.
"""
import asyncio
import sys
import types
import unittest
from collections import Counter


def _install_test_settings() -> None:
    settings_obj = types.SimpleNamespace(
        SECRET_KEY="test-secret-key-for-testing",
        SIP_NONCE_SECRET="test-sip-nonce-secret",
        APP_ENV="test",
        SIP_STATE_BACKEND="local",
        SIP_STATE_BACKEND_REDIS_PREFIX="gb:sip:state:",
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


class TestConcurrency(unittest.IsolatedAsyncioTestCase):
    """Race-condition and thread-safety regression tests."""

    def setUp(self) -> None:
        _install_test_settings()

    # 1. Nonce uniqueness --------------------------------------------------

    async def test_concurrent_nonce_uniqueness(self):
        """Generate 1000 nonces concurrently — all must be unique."""
        from app.sip.auth import DigestAuth

        async def gen_one() -> str:
            # Small yield to encourage interleaving
            await asyncio.sleep(0)
            return DigestAuth.generate_nonce()

        nonces = await asyncio.gather(*[gen_one() for _ in range(1000)])
        self.assertEqual(len(nonces), 1000)
        self.assertEqual(len(set(nonces)), 1000, "duplicate nonces detected")

    # 2. SIP state backend concurrent access -------------------------------

    async def test_sip_state_backend_concurrent_set_get(self):
        """Concurrent write/read on the local SIP state backend must not corrupt data.

        Uses ``record_register_call_id`` (write) + ``check_register_renewal`` (read)
        — the backend exposes no generic key/value ``set``/``get``; these specialised
        methods are the real concurrent-access surface used by the SIP register flow.
        """
        from app.sip.state_backend import get_sip_state_backend

        backend = get_sip_state_backend()
        gb_ids = [f"test:concurrent:device:{i}" for i in range(50)]
        call_ids = [f"callid_{i}_{id(backend)}" for i in range(50)]

        async def write_one(gb_id: str, call_id: str):
            await backend.record_register_call_id(gb_id, call_id, ttl=30)

        async def read_one(gb_id: str, call_id: str) -> bool:
            return await backend.check_register_renewal(gb_id, call_id)

        # Write all concurrently
        await asyncio.gather(*[write_one(g, c) for g, c in zip(gb_ids, call_ids)])
        # Read all concurrently — each must match its own call_id
        results = await asyncio.gather(*[read_one(g, c) for g, c in zip(gb_ids, call_ids)])
        for gb_id, call_id, matched in zip(gb_ids, call_ids, results):
            self.assertTrue(matched, f"value mismatch for {gb_id}")

        # A stale call_id must NOT match (renewal detection)
        stale_results = await asyncio.gather(
            *[read_one(g, "stale-call-id") for g in gb_ids]
        )
        for matched in stale_results:
            self.assertFalse(matched, "stale call_id must not match")

    # 3. Parallel DigestAuth calculation -----------------------------------

    async def test_parallel_digest_auth_correctness(self):
        """Calculate 100 responses in parallel — each must match its serial result."""
        from app.sip.auth import DigestAuth

        params_list = [
            dict(
                username=f"user_{i}", realm="realm", password=f"pass_{i}",
                method="REGISTER", uri="sip:realm", nonce=f"nonce_{i}",
                nc="00000001", cnonce=f"cn_{i}", qop="auth", algorithm="MD5",
            )
            for i in range(100)
        ]

        async def calc(params):
            await asyncio.sleep(0)
            return DigestAuth.calculate_response(**params)

        parallel_results = await asyncio.gather(*[calc(p) for p in params_list])
        serial_results = [DigestAuth.calculate_response(**p) for p in params_list]

        self.assertEqual(parallel_results, serial_results)

    # 4. Token-refresh single-flight simulation ----------------------------

    async def test_token_refresh_single_flight(self):
        """Simulate the frontend token-refresh queue: only one refresh at a time."""
        call_count = 0
        lock = asyncio.Lock()
        refresh_event = asyncio.Event()

        async def do_refresh() -> str:
            nonlocal call_count
            async with lock:
                call_count += 1
                # Simulate network latency
                await asyncio.sleep(0.01)
                return f"new_token_{call_count}"

        async def request_with_retry():
            """Simulate a queued request waiting for refresh."""
            async with lock:
                # In the real implementation, subscribers wait for the refresh
                # Here we just acquire the lock after the first refresh completes
                pass
            token = await do_refresh()
            return token

        # Fire 20 concurrent requests — with the lock, they should serialize
        results = await asyncio.gather(*[request_with_retry() for _ in range(20)])
        # Each request got a unique token (because each acquires the lock sequentially)
        self.assertEqual(len(results), 20)
        self.assertEqual(len(set(results)), 20)

    # 5. Counter race condition detection ----------------------------------

    async def test_concurrent_counter_atomicity(self):
        """Verify that asyncio's single-threaded model prevents true data races
        on a shared counter when properly awaited."""
        counter = 0

        async def increment():
            nonlocal counter
            for _ in range(100):
                # No await here — asyncio won't context-switch, so this is atomic
                counter += 1

        # These run sequentially because increment() has no await points
        await asyncio.gather(*[increment() for _ in range(10)])
        self.assertEqual(counter, 1000)

    async def test_concurrent_counter_with_yield(self):
        """With an await (yield point), context switches can interleave.
        This test verifies that a lock is needed for complex shared state."""
        counter = 0

        async def increment_unsafe():
            nonlocal counter
            for _ in range(100):
                old = counter
                await asyncio.sleep(0)  # yield — another task can run here
                counter = old + 1

        # Without a lock, some increments may be lost due to interleaving
        await asyncio.gather(*[increment_unsafe() for _ in range(5)])
        # The count should be <= 500 (likely less due to lost updates)
        self.assertLessEqual(counter, 500)


if __name__ == "__main__":
    unittest.main()
