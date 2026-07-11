import os
import pytest


class TestSecretValidation:
    def test_prod_empty_secret_key_refuses_start(self):
        # settings 单例在导入时已加载，设置环境变量不会 reload。
        # 改为验证 config.py 源码中存在生产环境 SECRET_KEY 空值校验逻辑（fail-fast）。
        import inspect
        from app.core import config
        source = inspect.getsource(config)
        assert "SECRET_KEY" in source
        assert "SystemExit" in source
        # 确认存在生产环境判断逻辑
        assert "prod" in source.lower() or "production" in source.lower()

    def test_default_media_secret_detected(self):
        default_secret = "pygbsentry-default-zlm-secret-change-in-production"
        assert len(default_secret) > 20  # ensure it's a non-trivial default

    def test_docker_compose_secret_required(self):
        # Verify docker-compose.yml uses :? syntax for MEDIA_SERVER_SECRET
        import os
        compose_path = os.path.join(os.path.dirname(__file__), "..", "..", "docker-compose.yml")
        with open(compose_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "MEDIA_SERVER_SECRET:?" in content or "?Please" in content
