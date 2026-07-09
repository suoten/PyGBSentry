"""Regression tests for Content-Security-Policy hardening.

Verifies that connect-src no longer contains wildcard schemes (http:/https:/ws:/wss:)
and only allows 'self' + auto-derived stream origin + configured whitelist.
Also verifies img-src uses valid CSP wildcards (* not ?) for map tile hosts.
"""
import unittest
from unittest.mock import patch
import importlib
import sys


def _reload_main_with_settings(**overrides):
    """Reload app.main with a stubbed settings object containing the given overrides.

    Returns the reloaded app.main module so SecurityHeadersMiddleware can be inspected.
    """
    from app.core import config as _config
    base = {
        "STREAM_PUBLIC_SCHEME": "http",
        "STREAM_PUBLIC_HOST": "stream.example.com",
        "STREAM_PUBLIC_HTTP_PORT": 80,
        "CSP_CONNECT_SRC_DOMAINS": "https://basemaps.arcgis.com",
    }
    base.update(overrides)
    stub = type("Settings", (), {**{k: v for k, v in base.items()}})()
    # app.main does `from app.core.config import settings` at import time,
    # but _build_connect_sources reads via getattr(settings, ...) — so we patch
    # the settings reference in the already-imported app.main module.
    import app.main as _main
    with patch.object(_main, "settings", stub):
        sources = _main.SecurityHeadersMiddleware._build_connect_sources()
    return sources


class TestConnectSrcNoWildcards(unittest.TestCase):
    """connect-src must not contain scheme wildcards http:/https:/ws:/wss:."""

    def test_no_http_wildcard(self):
        sources = _reload_main_with_settings()
        joined = " ".join(sources)
        self.assertNotIn("http:", joined.split(),
                         "connect-src must not contain 'http:' wildcard scheme")

    def test_no_https_wildcard(self):
        sources = _reload_main_with_settings()
        joined = " ".join(sources)
        self.assertNotIn("https:", joined.split(),
                         "connect-src must not contain 'https:' wildcard scheme")

    def test_no_ws_wildcard(self):
        sources = _reload_main_with_settings()
        joined = " ".join(sources)
        self.assertNotIn("ws:", joined.split(),
                         "connect-src must not contain 'ws:' wildcard scheme")

    def test_no_wss_wildcard(self):
        sources = _reload_main_with_settings()
        joined = " ".join(sources)
        self.assertNotIn("wss:", joined.split(),
                         "connect-src must not contain 'wss:' wildcard scheme")


class TestConnectSrcContainsSelf(unittest.TestCase):
    """connect-src must always include 'self'."""

    def test_self_present(self):
        sources = _reload_main_with_settings()
        self.assertIn("'self'", sources,
                      "connect-src must include 'self' for same-origin API + WebSocket")


class TestStreamOriginAutoDerived(unittest.TestCase):
    """connect-src must auto-derive the ZLMediaKit streaming origin from STREAM_PUBLIC_*."""

    def test_http_stream_origin_included(self):
        sources = _reload_main_with_settings(
            STREAM_PUBLIC_SCHEME="http",
            STREAM_PUBLIC_HOST="media.example.com",
            STREAM_PUBLIC_HTTP_PORT=8880,
        )
        self.assertIn("http://media.example.com:8880", sources)

    def test_https_stream_origin_included(self):
        sources = _reload_main_with_settings(
            STREAM_PUBLIC_SCHEME="https",
            STREAM_PUBLIC_HOST="media.example.com",
            STREAM_PUBLIC_HTTP_PORT=443,
        )
        # Port 443 is default for https — should be omitted
        self.assertIn("https://media.example.com", sources)
        self.assertNotIn("https://media.example.com:443", sources)

    def test_ws_variant_for_http_scheme(self):
        sources = _reload_main_with_settings(
            STREAM_PUBLIC_SCHEME="http",
            STREAM_PUBLIC_HOST="media.example.com",
            STREAM_PUBLIC_HTTP_PORT=80,
        )
        # Port 80 is default for http — should be omitted; ws variant derived
        self.assertIn("ws://media.example.com", sources)

    def test_wss_variant_for_https_scheme(self):
        sources = _reload_main_with_settings(
            STREAM_PUBLIC_SCHEME="https",
            STREAM_PUBLIC_HOST="media.example.com",
            STREAM_PUBLIC_HTTP_PORT=8443,
        )
        self.assertIn("wss://media.example.com:8443", sources)

    def test_no_stream_origin_when_host_empty(self):
        sources = _reload_main_with_settings(
            STREAM_PUBLIC_HOST="",
        )
        # Only 'self' + configured domains, no stream origin
        self.assertEqual(sources, ["'self'", "https://basemaps.arcgis.com"])


class TestCspConnectSrcDomainsConfig(unittest.TestCase):
    """CSP_CONNECT_SRC_DOMAINS entries must appear in connect-src."""

    def test_multiple_domains_parsed(self):
        sources = _reload_main_with_settings(
            CSP_CONNECT_SRC_DOMAINS="https://basemaps.arcgis.com,http://media2.example.com:80,wss://media2.example.com:80",
        )
        self.assertIn("https://basemaps.arcgis.com", sources)
        self.assertIn("http://media2.example.com:80", sources)
        self.assertIn("wss://media2.example.com:80", sources)

    def test_empty_domains_omitted(self):
        sources = _reload_main_with_settings(
            CSP_CONNECT_SRC_DOMAINS="https://basemaps.arcgis.com,,  ,http://extra.example.com",
        )
        self.assertIn("https://basemaps.arcgis.com", sources)
        self.assertIn("http://extra.example.com", sources)
        # Empty entries should not produce empty-string sources
        self.assertNotIn("", sources)

    def test_whitespace_trimmed(self):
        sources = _reload_main_with_settings(
            CSP_CONNECT_SRC_DOMAINS="  https://basemaps.arcgis.com  ,  http://extra.example.com  ",
        )
        self.assertIn("https://basemaps.arcgis.com", sources)
        self.assertIn("http://extra.example.com", sources)

    def test_duplicates_deduplicated(self):
        sources = _reload_main_with_settings(
            CSP_CONNECT_SRC_DOMAINS="https://basemaps.arcgis.com,https://basemaps.arcgis.com",
        )
        self.assertEqual(sources.count("https://basemaps.arcgis.com"), 1)


class TestImgSrcWildcards(unittest.TestCase):
    """img-src must use '*' (valid CSP wildcard) not '?' (invalid) for map tile hosts."""

    def test_img_src_uses_star_not_question(self):
        """Verify the CSP img-src does not contain invalid '?' wildcard patterns."""
        import app.main as _main
        import app.core.config as _config
        # Build a minimal CSP string by inspecting the source code — we check that
        # the hardcoded img-src uses '*' for tianditu/autonavi/bdimg, not '?'.
        import inspect
        src = inspect.getsource(_main.SecurityHeadersMiddleware.dispatch)
        self.assertIn("https://*.tianditu.gov.cn", src,
                      "img-src must use '*.tianditu.gov.cn' (valid CSP wildcard)")
        self.assertNotIn("https://t?.tianditu.gov.cn", src,
                         "img-src must not use 't?.tianditu.gov.cn' (invalid '?' wildcard)")
        self.assertIn("https://*.is.autonavi.com", src,
                      "img-src must use '*.is.autonavi.com' (valid CSP wildcard)")
        self.assertNotIn("https://web?.is.autonavi.com", src,
                         "img-src must not use 'web?.is.autonavi.com' (invalid '?' wildcard)")
        self.assertIn("https://*.bdimg.com", src,
                      "img-src must use '*.bdimg.com' (valid CSP wildcard)")
        self.assertNotIn("https://maponline?.bdimg.com", src,
                         "img-src must not use 'maponline?.bdimg.com' (invalid '?' wildcard)")


if __name__ == "__main__":
    unittest.main()
