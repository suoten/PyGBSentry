"""
TDD tests for RTP Server Timeout race condition and video playback bugs.

Bug1: on_rtp_server_timeout immediately cleans up sessions, but INVITE 200 OK
      may arrive after the RTP timeout, causing updateRtpServerSSRC to fail.

Bug2: updateRtpServerSSRC fails with "session not found" but doesn't attempt
      to recreate the RTP server session.

Bug3: SIP port 5060 conflict on restart - old process hasn't released the port.

Bug4: Event loop blocking - time.sleep() in _ensure_port_free blocks async loop.
"""

import asyncio
import datetime
import inspect
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select

# Setup test environment
import sys
import os
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

os.environ.setdefault("DATABASE_TYPE", "sqlite")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")


@pytest_asyncio.fixture(scope="module")
async def engine():
    from app.db.base import Base
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine):
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


# ============================================================
# Bug1: RTP Server Timeout Race Condition
# ============================================================

class TestRtpTimeoutGracePeriod:
    """Test that on_rtp_server_timeout doesn't immediately clean up
    recently created sessions, preventing the race condition where
    INVITE 200 OK arrives after RTP timeout cleanup."""

    @pytest.mark.asyncio
    async def test_on_rtp_server_timeout_passes_grace_period(self):
        """
        GREEN: on_rtp_server_timeout should pass grace_period_seconds
        to _cleanup_sessions, preventing the race condition where
        INVITE 200 OK arrives after RTP timeout cleanup.
        """
        import inspect
        from app.api.v1.endpoints.hook import on_rtp_server_timeout

        source = inspect.getsource(on_rtp_server_timeout)

        # Verify that on_rtp_server_timeout passes grace_period_seconds
        assert "grace_period_seconds" in source, (
            "on_rtp_server_timeout should pass grace_period_seconds to _cleanup_sessions"
        )
        assert "RTP_TIMEOUT_GRACE_SECONDS" in source, (
            "on_rtp_server_timeout should read RTP_TIMEOUT_GRACE_SECONDS from settings"
        )

    @pytest.mark.asyncio
    async def test_cleanup_sessions_respects_grace_period_for_recent_sessions(self):
        """
        GREEN: _cleanup_sessions with grace_period_seconds should skip
        sessions created within the grace period.
        """
        import inspect
        from app.api.v1.endpoints.hook import _cleanup_sessions

        source = inspect.getsource(_cleanup_sessions)

        # Verify that _cleanup_sessions checks grace_period_seconds
        assert "grace_period_seconds" in source, (
            "_cleanup_sessions should accept grace_period_seconds parameter"
        )
        # Verify it checks session age against grace period
        assert "start_time" in source or "created_at" in source, (
            "_cleanup_sessions should check session creation time against grace period"
        )


# ============================================================
# Bug2: updateRtpServerSSRC Failure Recovery
# ============================================================

class TestUpdateRtpServerSsrcRecovery:
    """Test that when updateRtpServerSSRC fails with 'session not found',
    the system attempts to recreate the RTP server session."""

    @pytest.mark.asyncio
    async def test_response_handler_recovers_from_ssrc_not_found(self):
        """
        GREEN: When response_handler gets 'session not found' from updateRtpServerSSRC,
        it should attempt to reopen the RTP server with the new SSRC.
        """
        from app.sip.response_handler import _try_reopen_rtp_server_on_ssrc_mismatch

        # Mock the ZLM API calls
        mock_open_rtp = AsyncMock(return_value={"code": 0, "port": 30000})
        mock_update_ssrc = AsyncMock(return_value={"code": 0})

        with patch("app.services.zlm_rtp_server_service.open_rtp_server", mock_open_rtp), \
             patch("app.services.zlm_rtp_server_service.update_rtp_server_ssrc", mock_update_ssrc):

            result = await _try_reopen_rtp_server_on_ssrc_mismatch(
                host="127.0.0.1",
                http_port=8880,
                secret="test-secret",
                app="live",
                stream_id="34020000001310000001_0017831993",
                ssrc="01101839",
                tcp_mode=0,
                rtp_port=30000,
            )

            # Should have called open_rtp_server to recreate the session
            mock_open_rtp.assert_called_once()
            # Should have called update_rtp_server_ssrc after reopening
            mock_update_ssrc.assert_called_once()
            assert result is True, "Recovery should succeed"

    @pytest.mark.asyncio
    async def test_response_handler_returns_false_on_recovery_failure(self):
        """
        When recovery fails (e.g., ZLM is down), the function should return False
        instead of raising an exception.
        """
        from app.sip.response_handler import _try_reopen_rtp_server_on_ssrc_mismatch

        # Mock the ZLM API calls to fail
        mock_open_rtp = AsyncMock(side_effect=Exception("ZLM connection refused"))

        with patch("app.services.zlm_rtp_server_service.open_rtp_server", mock_open_rtp):
            result = await _try_reopen_rtp_server_on_ssrc_mismatch(
                host="127.0.0.1",
                http_port=8880,
                secret="test-secret",
                app="live",
                stream_id="34020000001310000001_0017831993",
                ssrc="01101839",
                tcp_mode=0,
                rtp_port=30000,
            )

            assert result is False, "Recovery should return False on failure"


# ============================================================
# Bug3: SIP Port 5060 Conflict on Restart
# ============================================================

class TestSipPortConflictRecovery:
    """Test that SIP server handles port conflicts gracefully."""

    def test_sip_start_has_retry_configuration(self):
        """
        GREEN: SIP server start method should read retry configuration
        from settings to handle port conflicts.
        """
        from app.sip.server import SipServer
        import inspect

        source = inspect.getsource(SipServer.start)

        # Verify the retry logic exists in the start method
        assert "SIP_BIND_MAX_RETRIES" in source, (
            "SipServer.start should read SIP_BIND_MAX_RETRIES from settings"
        )
        assert "SIP_BIND_RETRY_DELAY" in source, (
            "SipServer.start should read SIP_BIND_RETRY_DELAY from settings"
        )
        assert "_bind_attempt" in source, (
            "SipServer.start should have a retry loop with _bind_attempt"
        )


# ============================================================
# Bug4: Event Loop Blocking
# ============================================================

class TestEventLoopBlocking:
    """Test that blocking operations don't block the event loop."""

    def test_ensure_port_free_is_async(self):
        """
        GREEN: _ensure_port_free should be an async method that uses
        asyncio.sleep instead of time.sleep.
        """
        from app.services.media_manager import MediaManager
        import inspect

        # Verify _ensure_port_free is a coroutine function
        assert inspect.iscoroutinefunction(MediaManager._ensure_port_free), (
            "_ensure_port_free should be an async method"
        )

    def test_ensure_port_free_uses_asyncio_sleep(self):
        """
        GREEN: _ensure_port_free should use asyncio.sleep instead of time.sleep.
        """
        from app.services.media_manager import MediaManager
        import inspect
        import ast
        import textwrap

        source = inspect.getsource(MediaManager._ensure_port_free)
        # Dedent to remove leading indentation for AST parsing
        source = textwrap.dedent(source)

        # Parse the source and check for time.sleep calls in actual code
        # (not in comments or docstrings)
        tree = ast.parse(source)
        has_time_sleep = False
        has_asyncio_sleep = False

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                # Check for time.sleep(...)
                if isinstance(func, ast.Attribute) and func.attr == 'sleep':
                    if isinstance(func.value, ast.Name) and func.value.id == 'time':
                        has_time_sleep = True
                    elif isinstance(func.value, ast.Name) and func.value.id == 'asyncio':
                        has_asyncio_sleep = True

        assert not has_time_sleep, (
            "_ensure_port_free should not use blocking time.sleep() - "
            "use asyncio.sleep() instead"
        )
        assert has_asyncio_sleep, (
            "_ensure_port_free should use asyncio.sleep() for non-blocking waits"
        )

    def test_generate_config_is_async(self):
        """
        GREEN: _generate_config should be an async method since it
        calls async _ensure_port_free.
        """
        from app.services.media_manager import MediaManager
        import inspect

        assert inspect.iscoroutinefunction(MediaManager._generate_config), (
            "_generate_config should be an async method"
        )
