import os
import pytest


class TestDockerRtpPort:
    def test_bare_metal_no_clip(self):
        from app.services.media_manager import MediaManager
        os.environ.pop("RUNNING_IN_DOCKER", None)
        mm = MediaManager()
        result = mm._normalize_rtp_port_range("30000-39000", 30000)
        assert result == "30000-39000"

    def test_docker_auto_clip(self, monkeypatch):
        monkeypatch.setenv("RUNNING_IN_DOCKER", "true")
        monkeypatch.setenv("DOCKER_RTP_PORT_RANGE_MAX", "200")
        from app.services.media_manager import MediaManager
        mm = MediaManager()
        result = mm._normalize_rtp_port_range("30000-39000", 30000)
        assert result == "30000-30199"

    def test_docker_custom_threshold(self, monkeypatch):
        monkeypatch.setenv("RUNNING_IN_DOCKER", "true")
        monkeypatch.setenv("DOCKER_RTP_PORT_RANGE_MAX", "100")
        from app.services.media_manager import MediaManager
        mm = MediaManager()
        result = mm._normalize_rtp_port_range("30000-39000", 30000)
        assert result == "30000-30099"

    def test_docker_small_range_no_clip(self, monkeypatch):
        monkeypatch.setenv("RUNNING_IN_DOCKER", "true")
        monkeypatch.setenv("DOCKER_RTP_PORT_RANGE_MAX", "200")
        from app.services.media_manager import MediaManager
        mm = MediaManager()
        result = mm._normalize_rtp_port_range("30000-30100", 30000)
        assert result == "30000-30100"
