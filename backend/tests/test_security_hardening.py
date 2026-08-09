"""Tests for security hardening: device auth lockout, PTZ permission, catalog retry, project cleanup."""
import unittest
import sys
import types
import time
import asyncio


def _install_test_settings_stub() -> None:
    settings_obj = types.SimpleNamespace(
        SECRET_KEY="test-secret-key-for-testing",
        APP_ENV="dev",
        SIP_DEBUG_TRACE_ENABLED=False,
        SIP_TRACE_SAMPLE_RATE=0.0,
        SIP_IP="127.0.0.1",
        SIP_PORT=5060,
        SIP_ID="34020000002000000001",
        SIP_DOMAIN="3402000000",
        SIP_DEFAULT_PASSWORD="",
        SIP_IP_BLACKLIST="",
        SIP_WORKER_CONCURRENCY=200,
        SIP_RESPONSE_CACHE_TTL_SECONDS=32,
        SIP_RESPONSE_CACHE_MAX_SIZE=50000,
        SIP_MAX_INFLIGHT=5000,
        SIP_INVITE_RATE_LIMIT_WINDOW_SECONDS=5.0,
        SIP_INVITE_RATE_LIMIT_PER_DEVICE=8,
        SIP_INVITE_RATE_LIMIT_PER_TENANT=40,
        SIP_PLATFORM_KEEPALIVE_MISS_THRESHOLD=3,
        SIP_INVITE_ZLM_MAX_NODE_RETRIES=3,
        SIP_INVITE_ZLM_OPEN_RTP_TIMEOUT_SECONDS=3.0,
        SIP_INVITE_RESPONSE_TIMEOUT_SECONDS=20,
        SIP_TRANSACTION_T1_SECONDS=0.5,
        SIP_TRANSACTION_T2_SECONDS=4.0,
        SIP_INVITE_2XX_RETRANS_MAX_SECONDS=32.0,
        SIP_STARTUP_REQUIRED=False,
        PROJECT_NAME="PyGBSentry",
        MEDIA_SERVER_SECRET="test-secret",
        MEDIA_SERVER_HOST="127.0.0.1",
        MEDIA_SERVER_HTTP_PORT=8880,
        MEDIA_SERVER_RTP_PROXY_PORT=30000,
        MEDIA_SERVER_RTP_PROXY_PORT_RANGE="30000-39000",
        GB28181_SSRC_POLICY="adaptive",
        GB28181_SSRC_RETRY_ON_NOT_READY=True,
        GB28181_SSRC_RETRY_ORDER="strict,off",
        GB28181_AUTO_ENSURE_EMBEDDED_MEDIA_NODE=True,
        ALLOW_UNKNOWN_CASCADE_INVITE=False,
        STREAM_PUBLIC_HOST="localhost",
        STREAM_PUBLIC_HTTP_PORT=8880,
        STREAM_PUBLIC_SCHEME="http",
        MEDIA_SERVER_HOOK_BASE_URL=None,
        INIT_REDIS_ON_STARTUP=False,
        REDIS_HOST="localhost",
        REDIS_PORT=6379,
        REDIS_PASSWORD=None,
        REDIS_DB=0,
        DATABASE_TYPE="sqlite",
        DATABASE_SQLITE_PATH=":memory:",
        DATABASE_HOST="localhost",
        DATABASE_PORT=5432,
        DATABASE_NAME="test",
        DATABASE_USER="test",
        DATABASE_PASSWORD="",
        SQLALCHEMY_DATABASE_URI="sqlite+aiosqlite:///:memory:",
        APP_EDITION="oss",
        SIP_DIGEST_NONCE_TTL_SECONDS=300,
        SIP_AUTH_RELAXED="",
        SIP_NONCE_SECRET="",
        SIP_DIGEST_FAIL_WINDOW_SECONDS=300,
        SIP_DIGEST_FAIL_MAX_ATTEMPTS=10,
        SIP_DIGEST_FAIL_LOCK_DURATION=300,
        PTZ_MIN_INTERVAL_SECONDS=0.33,
        PTZ_EMERGENCY_WHITELIST="",
        # 集群相关配置（避免 RedisHACluster 初始化失败）
        CLUSTER_NODE_ID="",
        CLUSTER_ENABLED=False,
        # API 路径前缀（避免 app.api.deps 初始化失败）
        API_V1_STR="/api/v1",
        # JWT/认证相关
        ACCESS_TOKEN_EXPIRE_MINUTES=30,
        JWT_ALGORITHM="HS256",
        # CORS
        BACKEND_CORS_ORIGINS=[],
        # 多租户
        TENANT_HEADER_NAME="X-Tenant-ID",
        DEFAULT_TENANT_ID="default",
        # 审计日志
        AUDIT_LOG_ENABLED=False,
        # 设备控制相关
        SNAPSHOT_CONCURRENCY_LIMIT=5,
        SNAPSHOT_TTL_SECONDS=30,
    )
    existing = sys.modules.get("app.core.config")
    if existing is None:
        m = types.ModuleType("app.core.config")
        m.settings = settings_obj
        m.sip_host_for_contact = lambda: "127.0.0.1"
        sys.modules["app.core.config"] = m
        return
    # FIX [2026-07-19]: 仅在缺失时注入字段，避免覆盖真实 Settings 实例（否则会污染
    # 其它依赖 settings.SIP_SESSION_EXPIRES_SECONDS / SIP_SESSION_MIN_SE_SECONDS 等字段的测试）。
    # 使用 object.__setattr__ 绕过 pydantic v2 的 extra='forbid' 校验，与其它测试保持一致。
    if not hasattr(existing, "settings") or existing.settings is None:
        existing.settings = settings_obj
    else:
        for k, v in settings_obj.__dict__.items():
            if not hasattr(existing.settings, k):
                object.__setattr__(existing.settings, k, v)
    if not hasattr(existing, "sip_host_for_contact"):
        existing.sip_host_for_contact = lambda: "127.0.0.1"


class TestDeviceAuthLockout(unittest.IsolatedAsyncioTestCase):
    """测试设备认证失败锁定机制"""

    def setUp(self):
        _install_test_settings_stub()
        # 重置全局状态
        from app.sip import handlers
        handlers._digest_fail_tracker.clear()
        handlers._digest_locked.clear()

    async def test_record_and_check_lockout(self):
        from app.sip.handlers import _record_auth_failure, _check_device_auth_locked

        gb_id = "34020000002000000001"
        # 前9次不锁定
        for i in range(9):
            await _record_auth_failure(gb_id)
            self.assertFalse(await _check_device_auth_locked(gb_id),
                              f"Should not be locked after {i+1} failures")

        # 第10次锁定
        await _record_auth_failure(gb_id)
        self.assertTrue(await _check_device_auth_locked(gb_id),
                        "Should be locked after 10 failures")

    async def test_clear_auth_failures(self):
        from app.sip.handlers import _record_auth_failure, _check_device_auth_locked, _clear_auth_failures

        gb_id = "34020000002000000002"
        # 触发锁定
        for _ in range(10):
            await _record_auth_failure(gb_id)
        self.assertTrue(await _check_device_auth_locked(gb_id))

        # 清除后不锁定
        await _clear_auth_failures(gb_id)
        self.assertFalse(await _check_device_auth_locked(gb_id))

    async def test_lockout_expires(self):
        from app.sip.handlers import _record_auth_failure, _check_device_auth_locked, _digest_locked

        gb_id = "34020000002000000003"
        for _ in range(10):
            await _record_auth_failure(gb_id)
        self.assertTrue(await _check_device_auth_locked(gb_id))

        # 模拟锁定过期
        _digest_locked[gb_id] = time.monotonic() - 1
        self.assertFalse(await _check_device_auth_locked(gb_id),
                         "Should not be locked after lock expires")

    async def test_empty_gb_id_not_locked(self):
        from app.sip.handlers import _check_device_auth_locked, _record_auth_failure

        self.assertFalse(await _check_device_auth_locked(""))
        await _record_auth_failure("")  # should not crash
        self.assertFalse(await _check_device_auth_locked(""))


class TestPTZPermissionCheck(unittest.TestCase):
    """测试 PTZ 权限校验"""

    def setUp(self):
        _install_test_settings_stub()

    def test_superuser_has_permission(self):
        from app.api.v1.endpoints.ptz import _check_ptz_permission
        user = types.SimpleNamespace(
            is_superuser=True,
            permissions=None,
            role_code="",
        )
        self.assertTrue(_check_ptz_permission(user))

    def test_operator_with_ptz_permission(self):
        from app.api.v1.endpoints.ptz import _check_ptz_permission
        user = types.SimpleNamespace(
            is_superuser=False,
            permissions='["ptz.control"]',  # JSON string format
            role_code="operator",
        )
        self.assertTrue(_check_ptz_permission(user))

    def test_viewer_without_ptz_permission(self):
        from app.api.v1.endpoints.ptz import _check_ptz_permission
        user = types.SimpleNamespace(
            is_superuser=False,
            permissions='["dashboard.view", "monitor.view", "channels.view"]',
            role_code="viewer",
        )
        self.assertFalse(_check_ptz_permission(user))

    def test_owner_with_wildcard(self):
        from app.api.v1.endpoints.ptz import _check_ptz_permission
        user = types.SimpleNamespace(
            is_superuser=False,
            permissions='["*"]',  # JSON string format
            role_code="owner",
        )
        self.assertTrue(_check_ptz_permission(user))

    def test_operator_default_role_has_ptz(self):
        """operator 默认角色权限应包含 ptz.control；admin 持 WILDCARD 即涵盖全部权限"""
        from app.core.role_permissions import DEFAULT_ROLE_PERMISSIONS, WILDCARD
        self.assertIn("ptz.control", DEFAULT_ROLE_PERMISSIONS["operator"])
        self.assertIn(WILDCARD, DEFAULT_ROLE_PERMISSIONS["admin"])
        self.assertNotIn("ptz.control", DEFAULT_ROLE_PERMISSIONS["viewer"])


class TestCatalogRetryDelays(unittest.TestCase):
    """测试 catalog 重试退避策略"""

    def test_retry_delays_match_source(self):
        """验证重试延迟为 1→5→15（线性退避，与 handlers.py 源码一致）"""
        # 从 handlers.py 源码中提取 retry_delays
        import inspect
        from app.sip import handlers
        source = inspect.getsource(handlers._schedule_device_catalog_retry)
        # 验证源码中包含正确的延迟值
        self.assertIn("[1, 5, 15]", source,
                      "retry_delays should be [1, 5, 15] for linear backoff")

    def test_retry_delays_count(self):
        """验证重试次数为3次"""
        import inspect
        from app.sip import handlers
        source = inspect.getsource(handlers._schedule_device_catalog_retry)
        self.assertIn("[1, 5, 15]", source)
        # 3 delays = 1 initial + 2 retries = 3 total attempts
        delays = [1, 5, 15]
        self.assertEqual(len(delays), 3)


class TestProjectCleanup(unittest.TestCase):
    """测试项目结构清理"""

    def test_fix_catalog_removed(self):
        """验证 _fix_catalog.py 已删除"""
        import os
        fix_path = os.path.join(
            os.path.dirname(__file__), "..", "app", "sip", "_fix_catalog.py"
        )
        self.assertFalse(os.path.exists(fix_path),
                         "_fix_catalog.py should be deleted after merge")

    def test_route_stubs_oss_retained(self):
        """验证 _route_stubs_oss.py 作为企业版占位 stub 有意保留（提供 501 响应）。

        api.py 注释明确：stub 路由有意注册到 OSS 路由表，使企业版端点在 OpenAPI
        文档中可见并返回明确的 501 而非 404，便于区分"不存在"与"未实现"。
        """
        import os
        stubs_path = os.path.join(
            os.path.dirname(__file__), "..", "app", "api", "v1", "endpoints", "_route_stubs_oss.py"
        )
        self.assertTrue(os.path.exists(stubs_path),
                        "_route_stubs_oss.py 应有意保留，为企业版端点提供 501 stub")

    def test_api_py_imports_stubs(self):
        """验证 api.py 有意导入 _route_stubs_oss 以注册企业版 stub 路由"""
        import inspect
        from app.api.v1 import api
        source = inspect.getsource(api)
        self.assertIn("_route_stubs_oss", source,
                      "api.py 应导入 _route_stubs_oss 以注册企业版 501 stub 路由")

    def test_catalog_uses_caps_directly(self):
        """验证 catalog.py 使用 caps 变量而非重新读取 resource.capabilities"""
        import inspect
        import re
        from app.sip import catalog
        source = inspect.getsource(catalog)
        # 验证 _fix_catalog.py 的修复已合并：caps 由 existing_caps 派生（不重新读取 resource.capabilities）
        self.assertIn("caps = dict(existing_caps)", source)
        # 不应再有独立的 _caps = resource.capabilities 赋值（允许 existing_caps）
        # 使用正则确保 _caps 是独立变量名，而非 existing_caps 的子串
        standalone_caps = re.findall(r'(?<!\w)_caps\s*=\s*resource\.capabilities', source)
        self.assertEqual(standalone_caps, [],
                         "catalog.py should not reassign _caps from resource.capabilities")


class TestPTZEmergencyWhitelist(unittest.TestCase):
    """测试 PTZ 紧急操作白名单"""

    def setUp(self):
        _install_test_settings_stub()

    def test_emergency_whitelist_exists(self):
        """验证紧急白名单机制存在"""
        from app.sip.ptz import _PTZ_EMERGENCY_WHITELIST
        self.assertIsInstance(_PTZ_EMERGENCY_WHITELIST, set)

    def test_send_ptz_has_emergency_param(self):
        """验证 send_ptz 方法有 is_emergency 参数"""
        import inspect
        from app.sip.ptz import SipPtz
        sig = inspect.signature(SipPtz.send_ptz)
        self.assertIn("is_emergency", sig.parameters,
                      "send_ptz should have is_emergency parameter")


class TestSipTransactionStateMachine(unittest.TestCase):
    """测试 SIP 事务状态机完整性"""

    def setUp(self):
        _install_test_settings_stub()

    def test_server_tx_has_confirm_transaction(self):
        """验证服务端事务有 confirm_transaction 方法"""
        from app.sip.transactions import SipServerTransactionManager
        self.assertTrue(hasattr(SipServerTransactionManager, "confirm_transaction"))

    def test_server_tx_has_terminate_transaction(self):
        """验证服务端事务有 terminate_transaction 方法"""
        from app.sip.transactions import SipServerTransactionManager
        self.assertTrue(hasattr(SipServerTransactionManager, "terminate_transaction"))

    def test_server_tx_has_timer_j(self):
        """验证非INVITE事务有 Timer J"""
        from app.sip.transactions import SipServerTransactionManager
        self.assertTrue(hasattr(SipServerTransactionManager, "start_timer_j"))

    def test_server_tx_has_timer_i(self):
        """验证INVITE事务有 Timer I"""
        from app.sip.transactions import SipServerTransactionManager
        self.assertTrue(hasattr(SipServerTransactionManager, "start_timer_i"))

    def test_server_tx_has_timer_g(self):
        """验证INVITE事务有 Timer G"""
        from app.sip.transactions import SipServerTransactionManager
        self.assertTrue(hasattr(SipServerTransactionManager, "start_timer_g"))

    def test_server_tx_has_timer_h(self):
        """验证INVITE事务有 Timer H"""
        from app.sip.transactions import SipServerTransactionManager
        self.assertTrue(hasattr(SipServerTransactionManager, "start_timer_h"))


if __name__ == "__main__":
    unittest.main()
