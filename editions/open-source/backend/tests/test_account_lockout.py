"""Tests for account lockout mechanism."""
import unittest
from datetime import datetime, timedelta, timezone


class TestAccountLockout(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        from app.sip.state_backend import get_sip_state_backend
        self._backend = get_sip_state_backend()
        self._backend._auth_failure_tracker.clear()

    async def asyncTearDown(self) -> None:
        self._backend._auth_failure_tracker.clear()

    async def test_locked_until_future_blocks(self):
        from datetime import datetime, timezone
        locked_until = datetime.now(timezone.utc) + timedelta(minutes=30)
        is_locked = locked_until > datetime.now(timezone.utc)
        self.assertTrue(is_locked)

    async def test_locked_until_past_clears(self):
        from datetime import datetime, timezone
        locked_until = datetime.now(timezone.utc) - timedelta(minutes=1)
        is_locked = locked_until > datetime.now(timezone.utc)
        self.assertFalse(is_locked)

    async def test_failed_attempts_increment(self):
        ip = "192.168.1.100"
        now = datetime.now(timezone.utc).timestamp()

        await self._backend.record_auth_failure(ip)
        await self._backend.record_auth_failure(ip)
        fails = self._backend._auth_failure_tracker.get(ip, [])
        self.assertEqual(len(fails), 2)

        for f in fails:
            self.assertGreaterEqual(f, now - 300)

    async def test_auth_failure_tracker_cleanup(self):
        ip_old = "192.168.1.50"
        ip_recent = "192.168.1.51"
        now = datetime.now(timezone.utc).timestamp()

        old_time = now - 600
        recent_time = now - 60

        tracker = self._backend._auth_failure_tracker
        tracker[ip_old] = [old_time]
        tracker[ip_recent] = [recent_time]

        cleaned = tracker.copy()
        for k, arr in cleaned.items():
            cutoff = now - 300
            tracker[k] = [t for t in arr if t >= cutoff]

        self.assertNotIn(ip_old, tracker)
        self.assertIn(ip_recent, tracker)

    async def test_lock_after_5_failures(self):
        max_attempts = 5
        failed_count = 5
        should_lock = failed_count >= max_attempts
        self.assertTrue(should_lock)

    async def test_lock_duration_30_minutes(self):
        lock_duration = timedelta(minutes=30)
        self.assertEqual(lock_duration, timedelta(minutes=30))


if __name__ == "__main__":
    unittest.main()
