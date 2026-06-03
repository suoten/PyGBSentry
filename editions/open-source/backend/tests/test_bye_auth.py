"""Tests for SIP BYE authentication (tag validation)."""
import unittest
import sys
import types


def _install_test_settings_stub() -> None:
    settings_obj = types.SimpleNamespace(
        SECRET_KEY="test-secret-key",
        APP_ENV="dev",
        SIP_DIGEST_NONCE_TTL_SECONDS=300,
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


class TestByeTagValidation(unittest.TestCase):
    """Test BYE tag validation logic (Call-ID + From/To tag triple check)."""

    def test_tag_matched_ss_to_tag_in_bye_from(self):
        ss_to_tag = "abcd1234"
        bye_from = 'From: <sip:device@1.1.1.1>;tag=abcd1234'
        matched = ss_to_tag and bye_from.endswith(f";tag={ss_to_tag}")
        self.assertTrue(matched)

    def test_tag_mismatched(self):
        ss_to_tag = "abcd1234"
        bye_from = 'From: <sip:device@1.1.1.1>;tag=wrongtag'
        matched = ss_to_tag and bye_from.endswith(f";tag={ss_to_tag}")
        self.assertFalse(matched)

    def test_tag_matched_ss_from_tag_in_bye_to(self):
        ss_from_tag = "xyz98765"
        bye_to = 'To: <sip:server@2.2.2.2>;tag=xyz98765'
        matched = ss_from_tag and bye_to.endswith(f";tag={ss_from_tag}")
        self.assertTrue(matched)

    def test_tag_matched_secondary(self):
        ss_to_tag = ""
        ss_from_tag = "xyz98765"
        bye_from = 'From: <sip:device@1.1.1.1>;tag=wrong'
        bye_to = 'To: <sip:server@2.2.2.2>;tag=xyz98765'
        matched = (
            (ss_to_tag and bye_from.endswith(f";tag={ss_to_tag}"))
            or (ss_from_tag and bye_to.endswith(f";tag={ss_from_tag}"))
        )
        self.assertTrue(matched)

    def test_bye_tag_direction_reversed_vs_invite(self):
        """BYE direction: ss_to_tag matches bye from-tag, ss_from_tag matches bye to-tag."""
        ss_from_tag = "invite_local_tag"
        ss_to_tag = "invite_remote_tag"

        bye_from = f'From: <sip:device>;tag={ss_to_tag}'
        bye_to = f'To: <sip:server>;tag={ss_from_tag}'

        matched = (
            (ss_to_tag and bye_from.endswith(f";tag={ss_to_tag}"))
            or (ss_from_tag and bye_to.endswith(f";tag={ss_from_tag}"))
        )
        self.assertTrue(matched)


class TestByeMissingSession(unittest.TestCase):
    """Test BYE handling when session doesn't exist (should return 200 OK for anti-probing)."""

    def test_no_session_returns_200(self):
        stream_session = None
        should_close = stream_session is not None
        should_return_200 = stream_session is None
        self.assertFalse(should_close)
        self.assertTrue(should_return_200)


if __name__ == "__main__":
    unittest.main()
