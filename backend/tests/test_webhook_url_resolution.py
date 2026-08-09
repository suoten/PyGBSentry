import pytest
from unittest.mock import patch
from types import SimpleNamespace


class TestWebhookUrlResolution:
    def test_bare_metal_loopback_allowed(self, monkeypatch):
        from app.services.media_manager import MediaManager
        # Replace the settings reference in media_manager module with a mock
        # that forces the fallback path (empty MEDIA_SERVER_HOOK_BASE_URL → /index/hook)
        monkeypatch.delenv("RUNNING_IN_DOCKER", raising=False)
        # FIX [2026-07-19]: 补齐 MediaManager.__init__ 与 _resolve_webhook_base 访问的所有
        # settings 属性，避免 SimpleNamespace 缺失属性导致 AttributeError。
        mock_settings = SimpleNamespace(
            EMBEDDED_ZLM_ENABLED=False,
            MEDIA_SERVER_HOOK_BASE_URL="",
            BACKEND_PUBLIC_HOST="localhost",
            BACKEND_PUBLIC_PORT=8000,
            API_V1_STR="/api/v1",
            MEDIA_SERVER_HOST="",
        )
        with patch("app.services.media_manager.settings", mock_settings):
            mm = MediaManager()
            result = mm._resolve_webhook_base(None)
            assert "hook" in result

    def test_docker_detect_method(self, monkeypatch):
        monkeypatch.setenv("RUNNING_IN_DOCKER", "true")
        from app.services.media_manager import MediaManager
        mm = MediaManager()
        assert mm._is_running_in_docker() is True

    def test_bare_metal_not_docker(self, monkeypatch):
        monkeypatch.delenv("RUNNING_IN_DOCKER", raising=False)
        from app.services.media_manager import MediaManager
        mm = MediaManager()
        assert mm._is_running_in_docker() is False

    def test_gateway_ip_parse(self):
        from app.services.media_manager import MediaManager
        mm = MediaManager()
        result = mm._detect_docker_gateway_ip()
        # In non-Docker environment, may return None
        assert result is None or isinstance(result, str)

    def test_non_loopback_host(self):
        from app.services.media_manager import MediaManager
        mm = MediaManager()
        assert mm._is_loopback_host("192.168.1.1") is False
        assert mm._is_loopback_host("localhost") is True
        assert mm._is_loopback_host("127.0.0.1") is True
        assert mm._is_loopback_host("0.0.0.0") is True
