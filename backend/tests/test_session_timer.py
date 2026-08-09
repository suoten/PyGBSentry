"""Tests for SIP Session Timer (RFC 4028) implementation.

Covers four core scenarios required by the PyGBSentry Session Timer spec:

1. UAC adds Session-Expires / Min-SE headers to outgoing INVITE.
2. UAS negotiates Session-Expires in 200 OK (echoes header, picks refresher).
3. UAS responds 422 Session Interval Too Small when value < Min-SE.
4. Non-refresher side sends BYE on Session-Expires timeout (no refresh received).
"""
import asyncio
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure real app.core.config is loaded with test env (matches conftest.py pattern)
os.environ.setdefault("DATABASE_TYPE", "sqlite")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-not-for-production")


class TestSessionExpiresParsing(unittest.TestCase):
    """Scenario 1 & 2 — parse / build Session-Expires header (RFC 4028 §5)."""

    def setUp(self):
        from app.sip.invite_server_state import (
            parse_session_expires,
            build_session_expires_header,
        )
        self.parse = parse_session_expires
        self.build = build_session_expires_header

    def test_parse_plain_seconds(self):
        # "1800" without refresher parameter
        seconds, refresher = self.parse("1800")
        self.assertEqual(seconds, 1800)
        self.assertEqual(refresher, "")

    def test_parse_with_refresher_uac(self):
        seconds, refresher = self.parse("1800;refresher=uac")
        self.assertEqual(seconds, 1800)
        self.assertEqual(refresher, "uac")

    def test_parse_with_refresher_uas(self):
        seconds, refresher = self.parse("900;refresher=uas")
        self.assertEqual(seconds, 900)
        self.assertEqual(refresher, "uas")

    def test_parse_empty_header_returns_zero(self):
        seconds, refresher = self.parse("")
        self.assertEqual(seconds, 0)
        self.assertEqual(refresher, "")

    def test_parse_invalid_value_returns_zero(self):
        seconds, refresher = self.parse("not-a-number")
        self.assertEqual(seconds, 0)
        self.assertEqual(refresher, "")

    def test_build_plain(self):
        self.assertEqual(self.build(1800), "1800")

    def test_build_with_refresher(self):
        self.assertEqual(self.build(1800, "uac"), "1800;refresher=uac")

    def test_build_with_refresher_uas(self):
        self.assertEqual(self.build(900, "uas"), "900;refresher=uas")


class TestUacInviteHeaders(unittest.TestCase):
    """Scenario 1 — UAC INVITE carries Session-Expires + Min-SE headers."""

    def test_apply_session_expires_to_request_adds_both_headers(self):
        from app.sip.invite_server_state import apply_session_expires_to_request
        from app.sip.message import SipMessage

        req = SipMessage()
        req.method = "INVITE"
        req.uri = "sip:34020000001320000001@192.168.1.100:5060"
        req.version = "SIP/2.0"
        req.headers["Via"] = "SIP/2.0/UDP 127.0.0.1:5060;rport;branch=z9hG4bKtest"
        req.headers["From"] = "<sip:34020000002000000001@3402000000>;tag=abc"
        req.headers["To"] = "<sip:34020000001320000001@3402000000>"
        req.headers["Call-ID"] = "test-call@127.0.0.1"
        req.headers["CSeq"] = "1 INVITE"

        apply_session_expires_to_request(req, expires=1800, min_se=90)

        self.assertEqual(req.get_header("Session-Expires"), "1800")
        self.assertEqual(req.get_header("Min-SE"), "90")

    def test_apply_session_expires_to_request_uses_configured_defaults(self):
        # Verify Settings exposes the configured values (no getattr dynamic fetch)
        from app.core.config import settings
        self.assertEqual(settings.SIP_SESSION_EXPIRES_SECONDS, 1800)
        self.assertEqual(settings.SIP_SESSION_MIN_SE_SECONDS, 90)
        # Must be a real attribute on the Settings class, not a dynamic default
        self.assertTrue(hasattr(settings, "SIP_SESSION_EXPIRES_SECONDS"))
        self.assertTrue(hasattr(settings, "SIP_SESSION_MIN_SE_SECONDS"))


class TestUasSessionExpiresNegotiation(unittest.TestCase):
    """Scenario 2 — UAS echoes Session-Expires in 200 OK with refresher negotiation."""

    def test_validate_accepts_valid_expires(self):
        from app.sip.invite_server_state import validate_session_expires_for_uas
        from app.sip.message import SipMessage

        req = SipMessage()
        req.method = "INVITE"
        req.headers["Session-Expires"] = "1800"

        ok, expires, refresher = validate_session_expires_for_uas(req, min_se=90)
        self.assertTrue(ok)
        self.assertEqual(expires, 1800)
        # No refresher in request → UAS (us) becomes refresher per RFC 4028 §5
        # (when omitted, the offerer is the refresher; here offerer is the UAC caller,
        #  but UAS may negotiate. We accept empty and let UAS decide.)
        self.assertEqual(refresher, "")

    def test_validate_accepts_with_refresher_uac(self):
        from app.sip.invite_server_state import validate_session_expires_for_uas
        from app.sip.message import SipMessage

        req = SipMessage()
        req.headers["Session-Expires"] = "1800;refresher=uac"

        ok, expires, refresher = validate_session_expires_for_uas(req, min_se=90)
        self.assertTrue(ok)
        self.assertEqual(expires, 1800)
        self.assertEqual(refresher, "uac")

    def test_validate_no_header_returns_ok_with_default(self):
        # GB28181 device without Session Timer support → degrade gracefully
        from app.sip.invite_server_state import validate_session_expires_for_uas
        from app.sip.message import SipMessage

        req = SipMessage()
        # No Session-Expires header at all
        ok, expires, refresher = validate_session_expires_for_uas(req, min_se=90)
        # No header → no Session Timer (degrade to existing behavior)
        self.assertTrue(ok)
        self.assertEqual(expires, 0)
        self.assertEqual(refresher, "")

    def test_apply_session_expires_to_response_adds_header(self):
        from app.sip.invite_server_state import apply_session_expires_to_response
        from app.sip.message import SipMessage

        resp = SipMessage()
        resp.status_code = 200
        resp.reason_phrase = "OK"
        resp.headers["Via"] = "SIP/2.0/UDP 127.0.0.1:5060;rport;branch=z9hG4bKtest"

        apply_session_expires_to_response(resp, expires=1800, refresher="uac")
        self.assertEqual(resp.get_header("Session-Expires"), "1800;refresher=uac")

    def test_apply_session_expires_to_response_no_refresher(self):
        from app.sip.invite_server_state import apply_session_expires_to_response
        from app.sip.message import SipMessage

        resp = SipMessage()
        resp.status_code = 200
        resp.headers["Via"] = "SIP/2.0/UDP 127.0.0.1:5060;rport;branch=z9hG4bKtest"

        apply_session_expires_to_response(resp, expires=900, refresher="")
        self.assertEqual(resp.get_header("Session-Expires"), "900")


class TestUas422Response(unittest.TestCase):
    """Scenario 3 — UAS responds 422 when Session-Expires < Min-SE (RFC 4028 §6)."""

    def test_validate_rejects_below_min_se(self):
        from app.sip.invite_server_state import validate_session_expires_for_uas
        from app.sip.message import SipMessage

        req = SipMessage()
        req.headers["Session-Expires"] = "30"  # < Min-SE 90

        ok, expires, refresher = validate_session_expires_for_uas(req, min_se=90)
        self.assertFalse(ok)
        # expires carries the rejected value so caller can log it
        self.assertEqual(expires, 30)

    def test_validate_rejects_below_min_se_with_refresher(self):
        from app.sip.invite_server_state import validate_session_expires_for_uas
        from app.sip.message import SipMessage

        req = SipMessage()
        req.headers["Session-Expires"] = "60;refresher=uac"

        ok, expires, refresher = validate_session_expires_for_uas(req, min_se=90)
        self.assertFalse(ok)
        self.assertEqual(expires, 60)

    def test_build_422_response_carries_min_se_header(self):
        from app.sip.invite_server_state import build_422_response
        from app.sip.message import SipMessage

        req = SipMessage()
        req.method = "INVITE"
        req.uri = "sip:34020000001320000001@192.168.1.100:5060"
        req.version = "SIP/2.0"
        req.headers["Via"] = "SIP/2.0/UDP 127.0.0.1:5060;rport;branch=z9hG4bKtest"
        req.headers["From"] = "<sip:34020000002000000001@3402000000>;tag=abc"
        req.headers["To"] = "<sip:34020000001320000001@3402000000>"
        req.headers["Call-ID"] = "test-call@127.0.0.1"
        req.headers["CSeq"] = "1 INVITE"

        resp = build_422_response(req, min_se=90)
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.get_header("Min-SE"), "90")


class TestDialogManagerSessionTimer(unittest.IsolatedAsyncioTestCase):
    """Scenario 4 — non-refresher side triggers timeout BYE when no refresh received."""

    async def asyncSetUp(self):
        # Use a fresh DialogManager instance (not the singleton) to avoid polluting global state
        from app.sip.dialog_manager import DialogManager
        self.dm = DialogManager(max_dialogs=100, ttl_seconds=3600)
        self.refresh_cb = AsyncMock(name="on_refresh")
        self.timeout_cb = AsyncMock(name="on_timeout")
        self.dm.set_session_timer_callbacks(
            on_refresh=self.refresh_cb,
            on_timeout=self.timeout_cb,
        )

    async def test_set_session_timer_stores_state(self):
        call_id = "st-test-1@127.0.0.1"
        from_tag = "fromtag1"
        await self.dm.create_dialog(call_id, from_tag)
        ok = await self.dm.set_session_timer(call_id, from_tag, expires=1800, refresher="uac")
        self.assertTrue(ok)
        dialog = await self.dm.get_dialog(call_id, from_tag)
        self.assertIsNotNone(dialog)
        self.assertEqual(dialog.session_data.get("session_expires"), 1800)
        self.assertEqual(dialog.session_data.get("session_refresher"), "uac")
        self.assertGreater(dialog.session_data.get("last_refresh_at", 0), 0)

    async def test_set_session_timer_returns_false_for_missing_dialog(self):
        ok = await self.dm.set_session_timer("nonexistent", "missing", expires=1800, refresher="uac")
        self.assertFalse(ok)

    async def test_update_session_refresh_updates_timestamp(self):
        call_id = "st-test-2@127.0.0.1"
        from_tag = "fromtag2"
        await self.dm.create_dialog(call_id, from_tag)
        await self.dm.set_session_timer(call_id, from_tag, expires=1800, refresher="uac")
        dialog = await self.dm.get_dialog(call_id, from_tag)
        first_ts = dialog.session_data.get("last_refresh_at", 0)
        await asyncio.sleep(0.05)
        await self.dm.update_session_refresh(call_id, from_tag)
        dialog2 = await self.dm.get_dialog(call_id, from_tag)
        self.assertGreater(dialog2.session_data.get("last_refresh_at", 0), first_ts)

    async def test_non_refresher_timeout_triggers_bye(self):
        """Non-refresher side: when session_expires elapses with no refresh, fire timeout callback."""
        call_id = "st-timeout@127.0.0.1"
        from_tag = "fromtag-timeout"
        await self.dm.create_dialog(call_id, from_tag)
        # refresher="uas" means the remote (UAS/device) should refresh.
        # We are the UAC; we are NOT the refresher → we run the timeout watchdog.
        await self.dm.set_session_timer(call_id, from_tag, expires=1, refresher="uas")
        # Confirm dialog
        await self.dm.confirm_dialog(call_id, from_tag, to_tag="totag-timeout")
        # Start the per-dialog timer task
        self.dm.start_session_timer(call_id, from_tag)
        # Wait long enough for the 1s timeout to fire (with margin)
        await asyncio.sleep(1.5)
        # The timeout callback (send BYE) should have been invoked
        self.timeout_cb.assert_awaited()
        # Refresh callback should NOT have been invoked (we are non-refresher)
        self.refresh_cb.assert_not_awaited()

    async def test_refresher_side_sends_reinvite_at_half_interval(self):
        """Refresher side: at session_expires/2, fire refresh callback (send re-INVITE)."""
        call_id = "st-refresh@127.0.0.1"
        from_tag = "fromtag-refresh"
        await self.dm.create_dialog(call_id, from_tag)
        # refresher="uac" means we (the UAC) are the refresher → we send re-INVITE
        await self.dm.set_session_timer(call_id, from_tag, expires=2, refresher="uac")
        await self.dm.confirm_dialog(call_id, from_tag, to_tag="totag-refresh")
        self.dm.start_session_timer(call_id, from_tag)
        # expires/2 = 1s; wait a bit beyond that
        await asyncio.sleep(1.3)
        self.refresh_cb.assert_awaited()
        # Timeout should NOT have fired (we are the refresher, not the watchdog)
        self.timeout_cb.assert_not_awaited()

    async def test_terminate_dialog_cancels_timer_task(self):
        """When a dialog is terminated, its session timer task must be cancelled."""
        call_id = "st-cancel@127.0.0.1"
        from_tag = "fromtag-cancel"
        await self.dm.create_dialog(call_id, from_tag)
        await self.dm.set_session_timer(call_id, from_tag, expires=10, refresher="uac")
        await self.dm.confirm_dialog(call_id, from_tag, to_tag="totag-cancel")
        self.dm.start_session_timer(call_id, from_tag)
        # Capture the task reference
        dialog = await self.dm.get_dialog(call_id, from_tag)
        task_ref = dialog.session_data.get("_session_timer_task")
        self.assertIsNotNone(task_ref)
        self.assertFalse(task_ref.done())
        # Terminate the dialog
        await self.dm.terminate_dialog(call_id, from_tag)
        # The task should be cancelled (done) shortly after termination
        await asyncio.sleep(0.05)
        self.assertTrue(task_ref.done() or task_ref.cancelled())

    async def test_no_session_timer_when_expires_zero(self):
        """GB28181 device without Session-Expires → no timer started, no callbacks."""
        call_id = "st-none@127.0.0.1"
        from_tag = "fromtag-none"
        await self.dm.create_dialog(call_id, from_tag)
        # expires=0 means no Session Timer (degrade gracefully)
        ok = await self.dm.set_session_timer(call_id, from_tag, expires=0, refresher="")
        # expires=0 should be treated as "no timer"
        self.assertFalse(ok)
        self.dm.start_session_timer(call_id, from_tag)
        await asyncio.sleep(0.3)
        self.refresh_cb.assert_not_awaited()
        self.timeout_cb.assert_not_awaited()


class TestSessionTimerIntegration(unittest.IsolatedAsyncioTestCase):
    """End-to-end-ish checks that verify wiring without real network."""

    async def test_on_invite_response_starts_timer_when_header_present(self):
        """UAC receives 200 OK with Session-Expires → dialog_manager timer state set."""
        import app.sip.invite as invite_module
        from app.sip.dialog_manager import DialogManager

        # Use a private DialogManager so we don't pollute the singleton
        local_dm = DialogManager(max_dialogs=10, ttl_seconds=3600)
        refresh_cb = AsyncMock()
        timeout_cb = AsyncMock()
        local_dm.set_session_timer_callbacks(on_refresh=refresh_cb, on_timeout=timeout_cb)

        # Pre-register a pending INVITE entry (mimic _register_invite_pending)
        call_id = "resp-test@127.0.0.1"
        from_tag = "fromtag-resp"
        event = asyncio.Event()
        result = {
            "from_tag": from_tag,
            "ssrc": "0100000001",
            "stream_id": "ch1_0100000001",
            "app": "live",
            "node_id": "",
            "lease_id": "",
        }
        invite_module.invite_state.invite_pending[call_id] = (event, result)
        # Pre-create the dialog (mimic _send_invite_common_inner)
        await local_dm.create_dialog(call_id, from_tag, session_data={
            "asset_id": "a1", "resource_id": "r1", "ssrc": "0100000001",
            "stream_id": "ch1_0100000001", "app": "live", "device_id": "dev1",
        })

        try:
            with patch.object(invite_module, "dialog_manager", local_dm):
                # Simulate 200 OK with Session-Expires header
                invite_module.on_invite_response(
                    call_id,
                    status_code=200,
                    reason="OK",
                    sdp_body="",
                    to_tag="totag-resp",
                    record_route=None,
                    session_expires_header="1800;refresher=uac",
                )
            # event should be set
            self.assertTrue(event.is_set())
            # Yield to event loop so fire_and_forget tasks (confirm_dialog,
            # _setup_session_timer) can complete before assertions.
            await asyncio.sleep(0.1)
            # dialog should have session timer state
            dialog = await local_dm.get_dialog(call_id, from_tag)
            self.assertIsNotNone(dialog)
            self.assertEqual(dialog.session_data.get("session_expires"), 1800)
            self.assertEqual(dialog.session_data.get("session_refresher"), "uac")
            # dialog should be confirmed (to_tag set)
            self.assertEqual(dialog.to_tag, "totag-resp")
        finally:
            invite_module.invite_state.invite_pending.pop(call_id, None)

    async def test_on_invite_response_no_header_does_not_set_timer(self):
        """200 OK without Session-Expires → no timer (GB28181 degrade path)."""
        import app.sip.invite as invite_module
        from app.sip.dialog_manager import DialogManager

        local_dm = DialogManager(max_dialogs=10, ttl_seconds=3600)
        refresh_cb = AsyncMock()
        timeout_cb = AsyncMock()
        local_dm.set_session_timer_callbacks(on_refresh=refresh_cb, on_timeout=timeout_cb)

        call_id = "resp-none@127.0.0.1"
        from_tag = "fromtag-none2"
        event = asyncio.Event()
        result = {"from_tag": from_tag, "ssrc": "x", "stream_id": "x", "app": "live", "node_id": "", "lease_id": ""}
        invite_module.invite_state.invite_pending[call_id] = (event, result)
        await local_dm.create_dialog(call_id, from_tag)

        try:
            with patch.object(invite_module, "dialog_manager", local_dm):
                invite_module.on_invite_response(
                    call_id,
                    status_code=200,
                    reason="OK",
                    sdp_body="",
                    to_tag="totag-none2",
                    record_route=None,
                    session_expires_header="",  # no Session-Expires
                )
            # Yield to event loop so fire_and_forget tasks (confirm_dialog,
            # _setup_session_timer) can complete before assertions.
            await asyncio.sleep(0.1)
            dialog = await local_dm.get_dialog(call_id, from_tag)
            self.assertIsNotNone(dialog)
            # No session_expires recorded (GB28181 degrade: session_expires=0)
            self.assertEqual(dialog.session_data.get("session_expires"), 0)
            self.assertEqual(dialog.session_data.get("session_refresher"), "")
        finally:
            invite_module.invite_state.invite_pending.pop(call_id, None)


if __name__ == "__main__":
    unittest.main()
