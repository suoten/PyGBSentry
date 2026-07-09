"""流媒体核心重构单元测试。

覆盖任务 1-8：连接池、幂等性、熔断器、Secret 安全、异步会话、负载均衡、一致性、协议开关。
"""
from __future__ import annotations

import asyncio
import sys
import types
import unittest
from unittest import mock


def _install_test_settings_stub():
    """安装测试用 settings stub，避免依赖完整配置"""
    if "app.core.config" not in sys.modules:
        m = types.ModuleType("app.core.config")
        m.settings = types.SimpleNamespace(
            ZLM_POOL_MAX_CONNECTIONS=50,
            ZLM_POOL_KEEPALIVE_SECONDS=30,
            ZLM_POOL_TIMEOUT_SECONDS=10.0,
            ZLM_POOL_CONNECT_TIMEOUT=5.0,
            ZLM_POOL_HEALTH_CHECK_INTERVAL=60.0,
            ZLM_RETRY_MAX=3,
            SIP_INVITE_ZLM_CONNECT_RTP_TIMEOUT_SECONDS=5.0,
            ZLM_DEFAULT_ENABLE_HLS=0,
            ZLM_DEFAULT_ENABLE_MP4=0,
            ZLM_DEFAULT_ENABLE_RTSP=0,
            ZLM_DEFAULT_ENABLE_RTMP=0,
            ZLM_DEFAULT_ENABLE_FLV=1,
            ZLM_SCHEDULE_WEIGHT_STREAMS=0.5,
            ZLM_SCHEDULE_WEIGHT_CPU=0.3,
            ZLM_SCHEDULE_WEIGHT_MEM=0.2,
            STREAM_SESSION_CACHE_TTL_SECONDS=300,
            ZLM_CIRCUIT_RECOVERY_FAST_SECONDS=10.0,
            ZLM_AUTO_FAILOVER_ENABLED=True,
            CLUSTER_NODE_ID="",
            CLUSTER_ENABLED=False,
            API_V1_STR="/api/v1",
            MEDIA_SERVER_SECRET="test_secret",
            SQLALCHEMY_DATABASE_URI="sqlite+aiosqlite:///test.db",
            SQLALCHEMY_DATABASE_SYNC_URI="sqlite:///test.db",
            ACCESS_TOKEN_EXPIRE_MINUTES=30,
            JWT_ALGORITHM="HS256",
            BACKEND_CORS_ORIGINS=[],
            TENANT_HEADER_NAME="X-Tenant-ID",
            DEFAULT_TENANT_ID="default",
            AUDIT_LOG_ENABLED=False,
        )
        sys.modules["app.core.config"] = m


_install_test_settings_stub()


class TestZlmConnectionPool(unittest.IsolatedAsyncioTestCase):
    """Task 1: ZLM HTTP API 统一连接池"""

    def setUp(self):
        from app.services import zlm_rtp_server_service as mod
        # 重置连接池
        mod._zlm_pool._shared_client = None
        mod._zlm_pool._node_clients.clear()
        mod._zlm_pool._closed = False

    async def test_shared_client_creation(self):
        """测试共享客户端创建"""
        from app.services.zlm_rtp_server_service import get_shared_zlm_client
        client = await get_shared_zlm_client()
        self.assertIsNotNone(client)
        self.assertFalse(client.is_closed)

    async def test_shared_client_reuse(self):
        """测试共享客户端复用"""
        from app.services.zlm_rtp_server_service import get_shared_zlm_client
        client1 = await get_shared_zlm_client()
        client2 = await get_shared_zlm_client()
        self.assertIs(client1, client2)

    async def test_node_client_creation(self):
        """测试节点客户端创建"""
        from app.services.zlm_rtp_server_service import get_node_client
        client = await get_node_client("127.0.0.1", 8880, "node1")
        self.assertIsNotNone(client)
        self.assertFalse(client.is_closed)

    async def test_node_client_reuse_by_key(self):
        """测试节点客户端按 key 复用"""
        from app.services.zlm_rtp_server_service import get_node_client
        client1 = await get_node_client("127.0.0.1", 8880, "node1")
        client2 = await get_node_client("127.0.0.1", 8880, "node1")
        self.assertIs(client1, client2)

    async def test_close_all(self):
        """测试优雅关闭所有客户端"""
        from app.services.zlm_rtp_server_service import get_shared_zlm_client, get_node_client, close_shared_zlm_client
        shared = await get_shared_zlm_client()
        node = await get_node_client("127.0.0.1", 8880, "node1")
        await close_shared_zlm_client()
        self.assertTrue(shared.is_closed)
        self.assertTrue(node.is_closed)

    async def test_health_check_rebuilds_closed_client(self):
        """测试健康检查重建已关闭的客户端"""
        from app.services.zlm_rtp_server_service import _zlm_pool, get_shared_zlm_client
        client = await get_shared_zlm_client()
        await client.aclose()
        self.assertTrue(client.is_closed)
        await _zlm_pool.health_check()
        self.assertFalse(_zlm_pool._shared_client.is_closed)


class TestSecretRedaction(unittest.TestCase):
    """Task 4: ZLM Secret 安全传递"""

    def test_redact_secret_moves_to_header(self):
        """测试 secret 从 params 移到 headers"""
        from app.services.zlm_rtp_server_service import _redact_secret
        params = {"secret": "my_secret", "app": "live", "stream_id": "test"}
        params_clean, headers = _redact_secret(params, {})
        self.assertNotIn("secret", params_clean)
        self.assertEqual(headers["X-ZLM-Secret"], "my_secret")
        self.assertEqual(params_clean["app"], "live")

    def test_redact_secret_no_secret_in_params(self):
        """测试无 secret 时不添加 header"""
        from app.services.zlm_rtp_server_service import _redact_secret
        params = {"app": "live"}
        params_clean, headers = _redact_secret(params, {})
        self.assertNotIn("X-ZLM-Secret", headers)
        self.assertEqual(params_clean["app"], "live")

    def test_safe_log_excludes_secret(self):
        """测试安全日志不包含 secret"""
        from app.services.zlm_rtp_server_service import _safe_log
        params = {"secret": "my_secret", "app": "live"}
        log_msg = _safe_log("openRtpServer", params)
        self.assertNotIn("my_secret", log_msg)
        self.assertIn("live", log_msg)

    def test_build_headers_in_stream_control(self):
        """测试 zlm_stream_control 的 _build_headers"""
        from app.services.zlm_stream_control import _build_headers
        headers = _build_headers("test_secret")
        self.assertEqual(headers["X-ZLM-Secret"], "test_secret")

    def test_strip_secret_removes_secret(self):
        """测试 _strip_secret 移除 secret"""
        from app.services.zlm_stream_control import _strip_secret
        params = {"secret": "s", "app": "live"}
        cleaned = _strip_secret(params)
        self.assertNotIn("secret", cleaned)
        self.assertEqual(cleaned["app"], "live")


class TestIdempotencyProtection(unittest.TestCase):
    """Task 2: ZLM API 重试幂等性保护"""

    def test_idempotent_apis_classification(self):
        """测试幂等接口分类"""
        from app.services.zlm_rtp_server_service import _is_idempotent
        self.assertTrue(_is_idempotent("getRtpServerStatus"))
        self.assertTrue(_is_idempotent("getMediaList"))
        self.assertTrue(_is_idempotent("getStatistic"))
        self.assertFalse(_is_idempotent("openRtpServer"))
        self.assertFalse(_is_idempotent("closeRtpServer"))
        self.assertFalse(_is_idempotent("connectRtpServer"))

    def test_generate_request_id_unique(self):
        """测试唯一请求 ID 生成"""
        from app.services.zlm_rtp_server_service import _generate_request_id
        ids = {_generate_request_id() for _ in range(100)}
        self.assertEqual(len(ids), 100)  # 全部唯一

    def test_generate_request_id_length(self):
        """测试请求 ID 长度"""
        from app.services.zlm_rtp_server_service import _generate_request_id
        rid = _generate_request_id()
        self.assertEqual(len(rid), 16)


class TestRetryWithPreCheck(unittest.IsolatedAsyncioTestCase):
    """Task 2: 非幂等接口重试前检查"""

    async def test_retry_skips_when_already_done(self):
        """测试操作已生效时跳过重试"""
        from app.services.zlm_rtp_server_service import _retry_zlm_call, ZlmApiError

        call_count = 0

        async def _coro_factory():
            nonlocal call_count
            call_count += 1
            raise ZlmApiError("fail", operation="openRtpServer", retryable=True)

        async def _pre_check():
            return True  # 操作已生效

        result = await _retry_zlm_call(
            _coro_factory, max_retries=3, api_path="openRtpServer", pre_retry_check=_pre_check
        )
        self.assertEqual(call_count, 1)  # 只调用一次
        self.assertTrue(result.get("skipped_retry"))

    async def test_retry_continues_when_not_done(self):
        """测试操作未生效时继续重试"""
        from app.services.zlm_rtp_server_service import _retry_zlm_call, ZlmApiError

        call_count = 0

        async def _coro_factory():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ZlmApiError("fail", operation="openRtpServer", retryable=True)
            return {"code": 0}

        async def _pre_check():
            return False  # 操作未生效

        result = await _retry_zlm_call(
            _coro_factory, max_retries=3, api_path="openRtpServer", pre_retry_check=_pre_check
        )
        self.assertEqual(call_count, 2)
        self.assertEqual(result["code"], 0)


class TestCloseRtpServerIdempotentDelete(unittest.IsolatedAsyncioTestCase):
    """Task 2: 删除类接口忽略"已不存在"错误"""

    async def test_close_returns_success_on_connect_error(self):
        """测试连接失败时视为已关闭（幂等删除）"""
        from app.services.zlm_rtp_server_service import close_rtp_server
        import httpx

        with mock.patch("app.services.zlm_rtp_server_service.get_shared_zlm_client") as mock_get:
            mock_client = mock.AsyncMock()
            mock_client.post = mock.AsyncMock(side_effect=httpx.ConnectError("refused"))
            mock_get.return_value = mock_client
            result = await close_rtp_server(
                host="127.0.0.1", http_port=8880, secret="s", stream_id="test"
            )
            self.assertEqual(result["code"], 0)


class TestProtocolDefaults(unittest.TestCase):
    """Task 8: 协议开关默认关闭"""

    def test_protocol_defaults_disabled(self):
        """测试默认仅启用 FLV，其他关闭"""
        from app.services.zlm_rtp_server_service import _get_protocol_defaults
        defaults = _get_protocol_defaults()
        self.assertEqual(defaults["enable_hls"], 0)
        self.assertEqual(defaults["enable_mp4"], 0)
        self.assertEqual(defaults["enable_rtsp"], 0)
        self.assertEqual(defaults["enable_rtmp"], 0)
        self.assertEqual(defaults["enable_flv"], 1)  # 仅 FLV 默认开启

    def test_open_rtp_server_uses_defaults_when_none(self):
        """测试 open_rtp_server 未传入时使用默认值"""
        import inspect
        from app.services.zlm_rtp_server_service import open_rtp_server
        sig = inspect.signature(open_rtp_server)
        # 验证协议参数默认为 None（使用全局配置）
        self.assertIsNone(sig.parameters["enable_hls"].default)
        self.assertIsNone(sig.parameters["enable_rtsp"].default)
        self.assertIsNone(sig.parameters["enable_rtmp"].default)
        self.assertIsNone(sig.parameters["enable_flv"].default)


class TestSessionAffinity(unittest.IsolatedAsyncioTestCase):
    """Task 6: 会话亲和性"""

    async def test_set_and_get_affinity(self):
        """测试设置和获取会话亲和性"""
        from app.core.media_nodes_db import set_session_affinity, get_session_affinity, clear_session_affinity
        await set_session_affinity("device_001", "node_A")
        result = await get_session_affinity("device_001")
        self.assertEqual(result, "node_A")

    async def test_clear_affinity(self):
        """测试清除会话亲和性"""
        from app.core.media_nodes_db import set_session_affinity, get_session_affinity, clear_session_affinity
        await set_session_affinity("device_002", "node_B")
        await clear_session_affinity("device_002")
        result = await get_session_affinity("device_002")
        self.assertIsNone(result)

    async def test_empty_device_id_returns_none(self):
        """测试空 device_id 返回 None"""
        from app.core.media_nodes_db import get_session_affinity
        result = await get_session_affinity("")
        self.assertIsNone(result)


class TestNodeScoring(unittest.TestCase):
    """Task 6: 节点综合评分"""

    def test_lower_score_is_better(self):
        """测试分数越低越好"""
        from app.core.media_nodes_db import _compute_node_score
        score_low = _compute_node_score(1, 10.0, 20.0, 5.0)
        score_high = _compute_node_score(50, 80.0, 90.0, 100.0)
        self.assertLess(score_low, score_high)

    def test_zero_load_has_lowest_score(self):
        """测试零负载分数最低"""
        from app.core.media_nodes_db import _compute_node_score
        score = _compute_node_score(0, 0.0, 0.0, 0.0)
        self.assertEqual(score, 0.0)

    def test_full_load_has_highest_score(self):
        """测试满负载分数最高"""
        from app.core.media_nodes_db import _compute_node_score
        score = _compute_node_score(100, 100.0, 100.0, 100.0)
        self.assertAlmostEqual(score, 1.0, places=2)


class TestSessionCache(unittest.IsolatedAsyncioTestCase):
    """Task 7: 流会话一致性缓存"""

    async def test_cache_and_invalidate(self):
        """测试缓存写入和失效"""
        from app.services.stream_session_service import _cache_session, _invalidate_cached_session, _get_cached_session
        await _cache_session("test_sid", {"app": "live", "stream": "s1"})
        cached = await _get_cached_session("test_sid")
        self.assertIsNotNone(cached)
        self.assertEqual(cached["app"], "live")
        await _invalidate_cached_session("test_sid")
        cached = await _get_cached_session("test_sid")
        self.assertIsNone(cached)

    async def test_cache_returns_none_for_missing(self):
        """测试缓存未命中返回 None"""
        from app.services.stream_session_service import _get_cached_session
        result = await _get_cached_session("nonexistent_sid")
        self.assertIsNone(result)

    async def test_persist_and_close_clears_cache(self):
        """测试优雅关闭清空缓存"""
        from app.services.stream_session_service import _cache_session, persist_and_close_cache, _get_cached_session
        await _cache_session("sid1", {"app": "a"})
        await _cache_session("sid2", {"app": "b"})
        await persist_and_close_cache()
        self.assertIsNone(await _get_cached_session("sid1"))
        self.assertIsNone(await _get_cached_session("sid2"))


class TestStreamSessionContext(unittest.IsolatedAsyncioTestCase):
    """Task 5: 流会话异步上下文管理器"""

    async def test_context_manager_normal_exit(self):
        """测试正常退出不释放会话"""
        from app.services.stream_session_service import StreamSessionContext

        session = types.SimpleNamespace(id="test_sid")
        ctx = StreamSessionContext(None, session, auto_release=False)
        async with ctx as s:
            self.assertEqual(s.id, "test_sid")

    async def test_context_manager_exception_with_auto_release(self):
        """测试异常路径自动释放"""
        from app.services.stream_session_service import StreamSessionContext

        released = False

        async def mock_release(db, session, reason=""):
            nonlocal released
            released = True

        session = types.SimpleNamespace(id="test_sid")
        with mock.patch("app.services.stream_session_service.release_stream_session", mock_release):
            ctx = StreamSessionContext(None, session, auto_release=True, reason="test_error")
            try:
                async with ctx:
                    raise ValueError("test exception")
            except ValueError:
                pass
            self.assertTrue(released)

    async def test_context_manager_exception_without_auto_release(self):
        """测试异常路径不自动释放"""
        from app.services.stream_session_service import StreamSessionContext

        released = False

        async def mock_release(db, session, reason=""):
            nonlocal released
            released = True

        session = types.SimpleNamespace(id="test_sid")
        with mock.patch("app.services.stream_session_service.release_stream_session", mock_release):
            ctx = StreamSessionContext(None, session, auto_release=False)
            try:
                async with ctx:
                    raise ValueError("test exception")
            except ValueError:
                pass
            self.assertFalse(released)


class TestCircuitBreakerIntegration(unittest.IsolatedAsyncioTestCase):
    """Task 3: 熔断器全量接入"""

    async def test_call_with_breaker_exists(self):
        """测试 _call_with_breaker 函数存在且可调用"""
        from app.services.zlm_rtp_server_service import _call_with_breaker
        self.assertTrue(callable(_call_with_breaker))

    async def test_call_with_breaker_no_node_id_skips_breaker(self):
        """测试无 node_id 时跳过熔断器"""
        from app.services.zlm_rtp_server_service import _call_with_breaker
        import httpx

        mock_resp = mock.AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = mock.Mock(return_value={"code": 0})

        mock_client = mock.AsyncMock()
        mock_client.get = mock.AsyncMock(return_value=mock_resp)

        with mock.patch("app.services.zlm_rtp_server_service.get_shared_zlm_client", return_value=mock_client):
            result = await _call_with_breaker("", "127.0.0.1", 8880, "getServerConfig")
            self.assertEqual(result["code"], 0)

    async def test_call_with_breaker_secret_in_header(self):
        """测试熔断器调用时 secret 通过 Header 传递"""
        from app.services.zlm_rtp_server_service import _call_with_breaker

        mock_resp = mock.AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = mock.Mock(return_value={"code": 0})

        mock_client = mock.AsyncMock()
        mock_client.get = mock.AsyncMock(return_value=mock_resp)

        with mock.patch("app.services.zlm_rtp_server_service.get_shared_zlm_client", return_value=mock_client):
            await _call_with_breaker(
                "", "127.0.0.1", 8880, "getServerConfig",
                params={"secret": "my_secret", "app": "live"}
            )
            # 验证 get 调用时 headers 包含 X-ZLM-Secret
            call_args = mock_client.get.call_args
            headers = call_args.kwargs.get("headers", {})
            self.assertEqual(headers.get("X-ZLM-Secret"), "my_secret")
            # 验证 params 不包含 secret
            params = call_args.kwargs.get("params", {})
            self.assertNotIn("secret", params)


class TestOpenRtpServerSecretHeader(unittest.IsolatedAsyncioTestCase):
    """Task 4: open_rtp_server 使用 Secret Header"""

    async def test_open_rtp_server_passes_secret_in_header(self):
        """测试 open_rtp_server 通过 Header 传递 secret"""
        from app.services.zlm_rtp_server_service import open_rtp_server

        mock_resp = mock.Mock()
        mock_resp.json = mock.Mock(return_value={"code": 0, "port": 30000})

        mock_client = mock.AsyncMock()
        mock_client.post = mock.AsyncMock(return_value=mock_resp)

        with mock.patch("app.services.zlm_rtp_server_service.get_shared_zlm_client", return_value=mock_client):
            with mock.patch("app.services.zlm_rtp_server_service.get_rtp_server_status", return_value={"code": -1}):
                await open_rtp_server(
                    host="127.0.0.1", http_port=8880, secret="my_secret",
                    port=30000, tcp_mode=0, app="live", stream_id="test", ssrc="0100000001"
                )
                call_args = mock_client.post.call_args
                headers = call_args.kwargs.get("headers", {})
                self.assertEqual(headers.get("X-ZLM-Secret"), "my_secret")
                # 验证 data 不包含 secret
                data = call_args.kwargs.get("data", {})
                self.assertNotIn("secret", data)


class TestOpenRtpServerErrorClassification(unittest.IsolatedAsyncioTestCase):
    """验证原有错误分类仍然工作"""

    async def test_open_rtp_server_raises_on_nonzero_code(self):
        """测试非零 code 抛出异常"""
        from app.services.zlm_rtp_server_service import open_rtp_server, ZlmApiError

        with mock.patch(
            "app.services.zlm_rtp_server_service._zlm_post",
            side_effect=ZlmApiError(
                "ZLM openRtpServer failed (code=-1): failed",
                operation="openRtpServer",
                category="unknown",
            ),
        ):
            with self.assertRaises(ZlmApiError) as ctx:
                await open_rtp_server(
                    host="127.0.0.1", http_port=80, secret="s",
                    port=30000, tcp_mode=0, app="live", stream_id="x", ssrc="0100000001"
                )
            self.assertEqual(ctx.exception.category, "unknown")

    async def test_open_rtp_server_classifies_port_exhausted(self):
        """测试端口耗尽分类"""
        from app.services.zlm_rtp_server_service import open_rtp_server, ZlmApiError

        with mock.patch(
            "app.services.zlm_rtp_server_service._zlm_post",
            side_effect=ZlmApiError(
                "ZLM openRtpServer port exhausted: 端口已被占用",
                operation="openRtpServer",
                category="media_port_exhausted",
            ),
        ):
            with self.assertRaises(ZlmApiError) as ctx:
                await open_rtp_server(
                    host="127.0.0.1", http_port=80, secret="s",
                    port=30000, tcp_mode=0, app="live", stream_id="x", ssrc="0100000001"
                )
            self.assertEqual(ctx.exception.category, "media_port_exhausted")


class TestClusterStatusEndpoint(unittest.TestCase):
    """Task 6: 集群监控接口"""

    def test_get_cluster_status_exists(self):
        """测试 get_cluster_status 函数存在"""
        from app.core.media_nodes_db import get_cluster_status
        self.assertTrue(callable(get_cluster_status))

    def test_cluster_status_endpoint_registered(self):
        """测试集群状态 API 端点已注册"""
        import inspect
        from app.api.v1.endpoints import media
        source = inspect.getsource(media)
        self.assertIn("/cluster-status", source)
        self.assertIn("get_cluster_status", source)


class TestConfigSettings(unittest.TestCase):
    """验证配置项已添加（直接检查 Settings 类字段定义，避免 stub 干扰）"""

    @classmethod
    def setUpClass(cls):
        """加载真实的 Settings 类以检查字段定义"""
        # 临时移除 stub，加载真实 config 模块
        real_config = sys.modules.pop("app.core.config", None)
        try:
            from app.core.config import Settings as _RealSettings
            cls._real_settings_cls = _RealSettings
        finally:
            if real_config is not None:
                sys.modules["app.core.config"] = real_config

    def test_pool_config_exists(self):
        """测试连接池配置项存在"""
        fields = self._real_settings_cls.model_fields
        self.assertIn("ZLM_POOL_MAX_CONNECTIONS", fields)
        self.assertIn("ZLM_POOL_KEEPALIVE_SECONDS", fields)
        self.assertIn("ZLM_POOL_TIMEOUT_SECONDS", fields)
        # 验证默认值
        self.assertEqual(fields["ZLM_POOL_MAX_CONNECTIONS"].default, 50)
        self.assertEqual(fields["ZLM_POOL_KEEPALIVE_SECONDS"].default, 30)
        self.assertEqual(fields["ZLM_POOL_TIMEOUT_SECONDS"].default, 10.0)

    def test_protocol_defaults_exist(self):
        """测试协议开关配置项存在"""
        fields = self._real_settings_cls.model_fields
        self.assertIn("ZLM_DEFAULT_ENABLE_HLS", fields)
        self.assertIn("ZLM_DEFAULT_ENABLE_FLV", fields)
        self.assertEqual(fields["ZLM_DEFAULT_ENABLE_HLS"].default, 0)
        self.assertEqual(fields["ZLM_DEFAULT_ENABLE_FLV"].default, 1)

    def test_schedule_weights_exist(self):
        """测试调度权重配置项存在"""
        fields = self._real_settings_cls.model_fields
        self.assertIn("ZLM_SCHEDULE_WEIGHT_STREAMS", fields)
        self.assertIn("ZLM_SCHEDULE_WEIGHT_CPU", fields)
        self.assertIn("ZLM_SCHEDULE_WEIGHT_MEM", fields)
        self.assertEqual(fields["ZLM_SCHEDULE_WEIGHT_STREAMS"].default, 0.5)
        self.assertEqual(fields["ZLM_SCHEDULE_WEIGHT_CPU"].default, 0.3)
        self.assertEqual(fields["ZLM_SCHEDULE_WEIGHT_MEM"].default, 0.2)

    def test_session_cache_ttl_exists(self):
        """测试会话缓存 TTL 配置项存在"""
        fields = self._real_settings_cls.model_fields
        self.assertIn("STREAM_SESSION_CACHE_TTL_SECONDS", fields)
        self.assertEqual(fields["STREAM_SESSION_CACHE_TTL_SECONDS"].default, 300)


if __name__ == "__main__":
    unittest.main()
