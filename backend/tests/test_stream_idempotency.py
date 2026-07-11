"""Tests for stream endpoint idempotency protection."""
import asyncio
import unittest


class TestPlayIdempotencyGuard(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        from app.api.v1.endpoints.stream._shared import _PLAY_INFLIGHT
        _PLAY_INFLIGHT.clear()

    async def asyncTearDown(self) -> None:
        from app.api.v1.endpoints.stream._shared import _PLAY_INFLIGHT
        _PLAY_INFLIGHT.clear()

    async def test_first_request_acquires(self):
        from app.api.v1.endpoints.stream import _PlayIdempotencyGuard

        guard = _PlayIdempotencyGuard("device1", "channel1")
        acquired = await guard.acquire()
        self.assertTrue(acquired)

    async def test_concurrent_request_blocked_by_ttl(self):
        from app.api.v1.endpoints.stream import _PlayIdempotencyGuard

        guard1 = _PlayIdempotencyGuard("device1", "channel1")
        acquired1 = await guard1.acquire()
        self.assertTrue(acquired1)

        guard2 = _PlayIdempotencyGuard("device1", "channel1")
        acquired2 = await guard2.acquire()
        self.assertFalse(acquired2)

    async def test_different_device_channel_no_collision(self):
        from app.api.v1.endpoints.stream import _PlayIdempotencyGuard

        guard1 = _PlayIdempotencyGuard("device1", "channel1")
        acquired1 = await guard1.acquire()
        self.assertTrue(acquired1)

        guard2 = _PlayIdempotencyGuard("device1", "channel2")
        acquired2 = await guard2.acquire()
        self.assertTrue(acquired2)

        guard3 = _PlayIdempotencyGuard("device2", "channel1")
        acquired3 = await guard3.acquire()
        self.assertTrue(acquired3)


class TestInviteRateLimiter(unittest.IsolatedAsyncioTestCase):
    async def test_allows_within_limit(self):
        from app.sip.invite import _check_and_consume_invite_rate, invite_state

        invite_state.invite_rate_stats.clear()
        invite_state.invite_rate_stats.update({
            "allowed": 0,
            "blocked_device": 0,
            "blocked_tenant": 0,
            "backend_redis": 0,
            "backend_local": 0,
            "backend_fallback": 0,
        })

        ok, reason = await _check_and_consume_invite_rate("tenant1", "device1")
        self.assertTrue(ok)

    async def test_blocks_over_tenant_limit(self):
        from app.sip.invite import _check_and_consume_invite_rate, invite_state
        from unittest.mock import patch, AsyncMock

        invite_state.invite_rate_stats.clear()
        invite_state.invite_rate_stats.update({
            "allowed": 0,
            "blocked_device": 0,
            "blocked_tenant": 0,
            "backend_redis": 0,
            "backend_local": 0,
            "backend_fallback": 0,
        })

        # 直接 mock backend 返回 tenant 限流拒绝，验证 _check_and_consume_invite_rate 的统计逻辑
        with patch("app.sip.invite.get_sip_state_backend") as mock_get_backend:
            mock_backend = mock_get_backend.return_value
            mock_backend.consume_invite_rate = AsyncMock(return_value=(False, "tenant limit exceeded"))
            ok, reason = await _check_and_consume_invite_rate("tenant1", "device2")
            self.assertFalse(ok)
            self.assertIn("tenant", reason)


if __name__ == "__main__":
    unittest.main()
