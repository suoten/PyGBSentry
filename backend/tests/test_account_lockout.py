"""Comprehensive tests for account lockout mechanism.

Covers:
- Pure helper functions in ``app/core/account_lockout.py`` (check_lockout_status,
  record_failed_attempt, reset_login_failures, remaining_lock_seconds) using a
  lightweight ``FakeUser`` so no database is required.
- Static-analysis of ``app/api/v1/endpoints/login.py`` to verify the rate-limit
  decorator string, helper imports, and audit-log detail strings are wired
  correctly — guarding against regressions if the endpoint is edited.
- End-to-end lockout scenarios that exercise the helpers in sequence.
"""
import inspect
import unittest
from datetime import datetime, timedelta, timezone


class FakeUser:
    """In-memory stand-in for ``app.models.user.User``.

    The account_lockout helpers use ``getattr``/``setattr`` so any object with
    ``failed_login_attempts`` and ``locked_until`` attributes works — no DB
    session needed, keeping these tests fast and deterministic.
    """

    def __init__(
        self,
        username: str = "tester",
        failed_login_attempts: int = 0,
        locked_until: datetime | None = None,
        tenant_id: str = "default",
    ) -> None:
        self.username = username
        self.failed_login_attempts = failed_login_attempts
        self.locked_until = locked_until
        self.tenant_id = tenant_id


# ---------------------------------------------------------------------------
# check_lockout_status
# ---------------------------------------------------------------------------
class TestCheckLockoutStatus(unittest.TestCase):
    """check_lockout_status must distinguish locked / unlocked / auto-unlocked."""

    def test_no_lock_returns_not_locked_not_unlocked(self):
        from app.core.account_lockout import check_lockout_status

        user = FakeUser(locked_until=None)
        is_locked, was_auto_unlocked = check_lockout_status(user)
        self.assertFalse(is_locked)
        self.assertFalse(was_auto_unlocked)

    def test_locked_in_future_returns_locked_not_unlocked(self):
        from app.core.account_lockout import check_lockout_status

        future = datetime.now(timezone.utc) + timedelta(minutes=20)
        user = FakeUser(locked_until=future, failed_login_attempts=5)
        is_locked, was_auto_unlocked = check_lockout_status(user)
        self.assertTrue(is_locked)
        self.assertFalse(was_auto_unlocked)

    def test_locked_in_future_preserves_counter(self):
        """A still-locked account must keep its failure counter untouched."""
        from app.core.account_lockout import check_lockout_status

        future = datetime.now(timezone.utc) + timedelta(minutes=20)
        user = FakeUser(locked_until=future, failed_login_attempts=5)
        check_lockout_status(user)
        self.assertEqual(user.failed_login_attempts, 5)
        self.assertIsNotNone(user.locked_until)

    def test_expired_lock_returns_unlocked_and_resets_counter(self):
        """CRITICAL: an expired lock must reset the failure counter in-place."""
        from app.core.account_lockout import check_lockout_status

        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        user = FakeUser(locked_until=past, failed_login_attempts=5)
        is_locked, was_auto_unlocked = check_lockout_status(user)
        self.assertFalse(is_locked)
        self.assertTrue(was_auto_unlocked)
        # The bug we fixed: counter must be reset, not left at 5
        self.assertEqual(user.failed_login_attempts, 0)

    def test_expired_lock_clears_locked_until(self):
        from app.core.account_lockout import check_lockout_status

        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        user = FakeUser(locked_until=past, failed_login_attempts=5)
        check_lockout_status(user)
        self.assertIsNone(user.locked_until)

    def test_naive_datetime_treated_as_utc(self):
        """SQLite returns naive datetimes; the helper must normalize before comparing."""
        from app.core.account_lockout import check_lockout_status

        # A naive future datetime should be treated as UTC and recognized as locked
        # (SQLite returns naive datetimes; use .replace(tzinfo=None) to simulate that
        # without triggering the deprecated datetime.utcnow() call.)
        naive_future = (datetime.now(timezone.utc) + timedelta(minutes=20)).replace(tzinfo=None)
        user = FakeUser(locked_until=naive_future, failed_login_attempts=5)
        is_locked, _ = check_lockout_status(user)
        self.assertTrue(is_locked)

    def test_injected_now_for_determinism(self):
        from app.core.account_lockout import check_lockout_status

        fixed = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        # locked_until exactly at `now` is NOT in the future → auto-unlock
        user = FakeUser(locked_until=fixed, failed_login_attempts=5)
        is_locked, was_auto_unlocked = check_lockout_status(user, now=fixed)
        self.assertFalse(is_locked)
        self.assertTrue(was_auto_unlocked)

        # locked_until one second after `now` → still locked
        user2 = FakeUser(locked_until=fixed + timedelta(seconds=1), failed_login_attempts=5)
        is_locked2, was_auto_unlocked2 = check_lockout_status(user2, now=fixed)
        self.assertTrue(is_locked2)
        self.assertFalse(was_auto_unlocked2)


# ---------------------------------------------------------------------------
# record_failed_attempt
# ---------------------------------------------------------------------------
class TestRecordFailedAttempt(unittest.TestCase):
    """record_failed_attempt increments the counter and locks at the threshold."""

    def test_first_failure_increments_to_1_not_locked(self):
        from app.core.account_lockout import record_failed_attempt

        user = FakeUser(failed_login_attempts=0)
        just_locked = record_failed_attempt(user)
        self.assertFalse(just_locked)
        self.assertEqual(user.failed_login_attempts, 1)
        self.assertIsNone(user.locked_until)

    def test_four_failures_not_locked(self):
        from app.core.account_lockout import record_failed_attempt

        user = FakeUser(failed_login_attempts=3)
        just_locked = record_failed_attempt(user)
        self.assertFalse(just_locked)
        self.assertEqual(user.failed_login_attempts, 4)
        self.assertIsNone(user.locked_until)

    def test_fifth_failure_locks(self):
        from app.core.account_lockout import record_failed_attempt

        user = FakeUser(failed_login_attempts=4)
        just_locked = record_failed_attempt(user)
        self.assertTrue(just_locked)
        self.assertEqual(user.failed_login_attempts, 5)
        self.assertIsNotNone(user.locked_until)

    def test_fifth_failure_sets_locked_until_30_minutes_in_future(self):
        from app.core.account_lockout import record_failed_attempt, LOCKOUT_MINUTES

        self.assertEqual(LOCKOUT_MINUTES, 30)
        before = datetime.now(timezone.utc)
        user = FakeUser(failed_login_attempts=4)
        record_failed_attempt(user)
        after = datetime.now(timezone.utc)
        self.assertIsNotNone(user.locked_until)
        lock = user.locked_until
        if lock.tzinfo is None:
            lock = lock.replace(tzinfo=timezone.utc)
        # locked_until should be ~30 min ahead, within a small clock skew window
        lower = before + timedelta(minutes=30) - timedelta(seconds=5)
        upper = after + timedelta(minutes=30) + timedelta(seconds=5)
        self.assertGreaterEqual(lock, lower)
        self.assertLessEqual(lock, upper)

    def test_max_failed_attempts_is_5(self):
        from app.core.account_lockout import MAX_FAILED_ATTEMPTS
        self.assertEqual(MAX_FAILED_ATTEMPTS, 5)

    def test_sixth_failure_after_lock_still_reports_just_locked(self):
        """Beyond the threshold the helper keeps reporting just_locked=True so
        the endpoint refreshes the lock window and re-emits the 423."""
        from app.core.account_lockout import record_failed_attempt

        user = FakeUser(failed_login_attempts=5)
        just_locked = record_failed_attempt(user)
        self.assertTrue(just_locked)
        self.assertEqual(user.failed_login_attempts, 6)

    def test_starts_from_existing_count(self):
        from app.core.account_lockout import record_failed_attempt

        user = FakeUser(failed_login_attempts=2)
        record_failed_attempt(user)
        self.assertEqual(user.failed_login_attempts, 3)


# ---------------------------------------------------------------------------
# reset_login_failures
# ---------------------------------------------------------------------------
class TestResetLoginFailures(unittest.TestCase):
    """reset_login_failures must clear both the counter and the lock, idempotently."""

    def test_resets_counter_and_lock(self):
        from app.core.account_lockout import reset_login_failures

        user = FakeUser(
            failed_login_attempts=5,
            locked_until=datetime.now(timezone.utc) + timedelta(minutes=20),
        )
        reset_login_failures(user)
        self.assertEqual(user.failed_login_attempts, 0)
        self.assertIsNone(user.locked_until)

    def test_idempotent_on_clean_user(self):
        from app.core.account_lockout import reset_login_failures

        user = FakeUser(failed_login_attempts=0, locked_until=None)
        reset_login_failures(user)
        self.assertEqual(user.failed_login_attempts, 0)
        self.assertIsNone(user.locked_until)

    def test_resets_after_partial_failures(self):
        from app.core.account_lockout import reset_login_failures, record_failed_attempt

        user = FakeUser()
        record_failed_attempt(user)
        record_failed_attempt(user)
        self.assertEqual(user.failed_login_attempts, 2)
        reset_login_failures(user)
        self.assertEqual(user.failed_login_attempts, 0)
        self.assertIsNone(user.locked_until)


# ---------------------------------------------------------------------------
# remaining_lock_seconds
# ---------------------------------------------------------------------------
class TestRemainingLockSeconds(unittest.TestCase):
    """remaining_lock_seconds feeds the Retry-After header."""

    def test_no_lock_returns_0(self):
        from app.core.account_lockout import remaining_lock_seconds

        user = FakeUser(locked_until=None)
        self.assertEqual(remaining_lock_seconds(user), 0)

    def test_active_lock_returns_positive(self):
        from app.core.account_lockout import remaining_lock_seconds

        user = FakeUser(locked_until=datetime.now(timezone.utc) + timedelta(minutes=15))
        secs = remaining_lock_seconds(user)
        self.assertGreater(secs, 0)
        # ~15 minutes = ~900s, allow a generous skew window
        self.assertGreater(secs, 800)

    def test_expired_lock_returns_0(self):
        from app.core.account_lockout import remaining_lock_seconds

        user = FakeUser(locked_until=datetime.now(timezone.utc) - timedelta(minutes=1))
        self.assertEqual(remaining_lock_seconds(user), 0)

    def test_minimum_1_second_when_locked(self):
        """A lock expiring in <1s must still yield at least 1 to avoid an empty
        Retry-After header (which some clients treat as 'retry immediately')."""
        from app.core.account_lockout import remaining_lock_seconds

        user = FakeUser(locked_until=datetime.now(timezone.utc) + timedelta(milliseconds=200))
        self.assertGreaterEqual(remaining_lock_seconds(user), 1)


# ---------------------------------------------------------------------------
# Static analysis of login.py integration
# ---------------------------------------------------------------------------
def _read_login_source() -> str:
    """Read login.py source for static analysis (avoids importing the full app)."""
    import os
    path = os.path.join(
        os.path.dirname(__file__), "..", "app", "api", "v1", "endpoints", "login.py"
    )
    with open(path, encoding="utf-8") as f:
        return f.read()


class TestLoginRateLimitDecorator(unittest.TestCase):
    """The login endpoint must apply IP-level rate limiting of 10 requests / 5 minutes."""

    def test_rate_limit_is_10_per_5_minutes(self):
        src = _read_login_source()
        # The slowapi decorator should use the 10/5 minutes limit
        self.assertIn('"10/5 minutes"', src)

    def test_rate_limit_decorator_on_login_access_token(self):
        src = _read_login_source()
        self.assertIn('@limiter.limit("10/5 minutes")', src)


class TestLoginHelperImports(unittest.TestCase):
    """login.py must import and use the account_lockout helpers (single source of truth)."""

    def test_imports_check_lockout_status(self):
        src = _read_login_source()
        self.assertIn("check_lockout_status", src)

    def test_imports_record_failed_attempt(self):
        src = _read_login_source()
        self.assertIn("record_failed_attempt", src)

    def test_imports_reset_login_failures(self):
        src = _read_login_source()
        self.assertIn("reset_login_failures", src)

    def test_imports_remaining_lock_seconds(self):
        src = _read_login_source()
        self.assertIn("remaining_lock_seconds", src)

    def test_module_imports_succeed(self):
        """The login module must be importable (catches syntax / import errors)."""
        from app.api.v1.endpoints import login as _login  # noqa: F401
        self.assertTrue(inspect.ismodule(_login))


class TestLoginAuditLogging(unittest.TestCase):
    """Audit logging must record lock / auto-unlock / locked-attempt events."""

    def test_has_account_locked_detail(self):
        src = _read_login_source()
        self.assertIn('detail="account_locked"', src)

    def test_has_account_locked_after_attempts_detail(self):
        src = _read_login_source()
        self.assertIn('detail="account_locked_after_attempts"', src)

    def test_has_account_auto_unlocked_detail(self):
        """The previously-missing auto-unlock audit event must now be present."""
        src = _read_login_source()
        self.assertIn('detail="account_auto_unlocked"', src)

    def test_auto_unlock_uses_success_result_default(self):
        """auto-unlock audit must not be flagged as a failure (result defaults to success)."""
        src = _read_login_source()
        # The auto-unlock audit block should NOT set result="failed"
        # Locate the auto_unlocked block and ensure no result="failed" inside it
        idx = src.find('detail="account_auto_unlocked"')
        self.assertGreater(idx, 0, "auto_unlocked audit detail must exist")
        # Inspect the ~400 chars before the detail string (the safe_auth_audit call body)
        block = src[max(0, idx - 400): idx + 60]
        self.assertNotIn('result="failed"', block)


class TestLoginRetryAfterHeader(unittest.TestCase):
    """Retry-After must be dynamic (from remaining_lock_seconds), not a hardcoded 1800."""

    def test_no_hardcoded_1800_retry_after(self):
        src = _read_login_source()
        self.assertNotIn('"Retry-After": "1800"', src)

    def test_retry_after_uses_remaining_lock_seconds(self):
        src = _read_login_source()
        self.assertIn("remaining_lock_seconds(user)", src)


# ---------------------------------------------------------------------------
# End-to-end lockout scenarios (helper-level, no DB)
# ---------------------------------------------------------------------------
class TestEndToEndLockoutScenario(unittest.TestCase):
    """Full lockout lifecycle exercising the helpers in sequence."""

    def test_full_lockout_cycle(self):
        """5 failures lock → lock expires → counter reset → successful login resets."""
        from app.core.account_lockout import (
            check_lockout_status,
            record_failed_attempt,
            reset_login_failures,
            remaining_lock_seconds,
        )

        user = FakeUser()
        # Simulate 5 consecutive failed logins
        for i in range(4):
            just_locked = record_failed_attempt(user)
            self.assertFalse(just_locked, f"should not lock on attempt {i + 1}")
        # 5th failure triggers the lock
        just_locked = record_failed_attempt(user)
        self.assertTrue(just_locked)
        self.assertEqual(user.failed_login_attempts, 5)
        self.assertIsNotNone(user.locked_until)

        # While locked, check_lockout_status reports locked
        is_locked, was_auto_unlocked = check_lockout_status(user)
        self.assertTrue(is_locked)
        self.assertFalse(was_auto_unlocked)
        self.assertGreater(remaining_lock_seconds(user), 0)

        # Now simulate the lock expiring (rewind locked_until into the past)
        user.locked_until = datetime.now(timezone.utc) - timedelta(seconds=1)
        is_locked, was_auto_unlocked = check_lockout_status(user)
        self.assertFalse(is_locked)
        self.assertTrue(was_auto_unlocked)
        # Counter reset by the auto-unlock
        self.assertEqual(user.failed_login_attempts, 0)

        # A subsequent successful login resets state (idempotent)
        reset_login_failures(user)
        self.assertEqual(user.failed_login_attempts, 0)
        self.assertIsNone(user.locked_until)

    def test_auto_unlock_resets_counter_so_next_failure_starts_fresh(self):
        """REGRESSION: the bug we fixed. Without the in-place reset, the next
        failed attempt after expiry would immediately re-lock (count jumps 5→6)."""
        from app.core.account_lockout import check_lockout_status, record_failed_attempt

        user = FakeUser(failed_login_attempts=5, locked_until=datetime.now(timezone.utc) - timedelta(minutes=1))
        # Lock expired → auto-unlock resets counter to 0
        is_locked, was_auto_unlocked = check_lockout_status(user)
        self.assertTrue(was_auto_unlocked)
        self.assertEqual(user.failed_login_attempts, 0)

        # Next single failure should NOT re-lock (only 1 failure, threshold is 5)
        just_locked = record_failed_attempt(user)
        self.assertFalse(just_locked)
        self.assertEqual(user.failed_login_attempts, 1)
        self.assertIsNone(user.locked_until)

    def test_success_resets_partial_failures(self):
        """A successful login after a few failures must clear the counter."""
        from app.core.account_lockout import record_failed_attempt, reset_login_failures

        user = FakeUser()
        record_failed_attempt(user)
        record_failed_attempt(user)
        record_failed_attempt(user)
        self.assertEqual(user.failed_login_attempts, 3)
        # Successful login
        reset_login_failures(user)
        self.assertEqual(user.failed_login_attempts, 0)
        self.assertIsNone(user.locked_until)

    def test_relock_after_full_cycle_extends_lock_window(self):
        """After auto-unlock + 5 more failures, the account locks again with a
        fresh 30-minute window (the counter genuinely restarted from 0)."""
        from app.core.account_lockout import check_lockout_status, record_failed_attempt

        # Start from an expired-locked state
        user = FakeUser(
            failed_login_attempts=5,
            locked_until=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        check_lockout_status(user)  # auto-unlock → counter = 0
        self.assertEqual(user.failed_login_attempts, 0)

        # 5 fresh failures
        for _ in range(4):
            self.assertFalse(record_failed_attempt(user))
        just_locked = record_failed_attempt(user)
        self.assertTrue(just_locked)
        self.assertEqual(user.failed_login_attempts, 5)
        self.assertIsNotNone(user.locked_until)
        # New lock window must be in the future
        lock = user.locked_until
        if lock.tzinfo is None:
            lock = lock.replace(tzinfo=timezone.utc)
        self.assertGreater(lock, datetime.now(timezone.utc))


if __name__ == "__main__":
    unittest.main()
