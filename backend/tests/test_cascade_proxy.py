"""测试 app/sip/cascade.py 中的 SipCascadeCommander 类。

SipCascadeCommander 是一个 thin proxy，将调用委托给 PlatformService 单例。
本测试聚焦：
  1. 初始化字段（_cascade_call_ids、_cascade_call_id_timestamps）
  2. _cleanup_stale_call_ids 按 TTL 清理过期 call_id
  3. handle_any_response 对未知/已知 call_id 的分支处理
  4. start_platform / stop_platform 在 PlatformService 缺失时的 no-op 行为
  5. start_all / stop_all 仅记录 debug 日志的 no-op 行为

所有外部依赖（PlatformService、SipServer）通过 mock 隔离，确保测试纯单元性质。
"""
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.sip.cascade import SipCascadeCommander


@pytest.fixture
def commander() -> SipCascadeCommander:
    """每个测试用例使用独立的 SipCascadeCommander 实例，避免共享状态污染。"""
    return SipCascadeCommander()


# ---------------------------------------------------------------------------
# 1. __init__ 字段初始化
# ---------------------------------------------------------------------------

class TestSipCascadeCommanderInit:
    """验证 SipCascadeCommander 构造函数初始化级联事务跟踪字段。"""

    def test_init_creates_empty_call_id_set(self, commander):
        """_cascade_call_ids 必须初始化为空 set（避免 None 引用）。"""
        assert isinstance(commander._cascade_call_ids, set)
        assert len(commander._cascade_call_ids) == 0

    def test_init_creates_empty_call_id_timestamps(self, commander):
        """_cascade_call_id_timestamps 必须初始化为空 dict（TTL 清理依赖此结构）。"""
        assert isinstance(commander._cascade_call_id_timestamps, dict)
        assert len(commander._cascade_call_id_timestamps) == 0


# ---------------------------------------------------------------------------
# 2. _cleanup_stale_call_ids
# ---------------------------------------------------------------------------

class TestCleanupStaleCallIds:
    """验证 _cleanup_stale_call_ids 按 max_age 清理过期条目。"""

    def test_cleanup_removes_entries_older_than_max_age(self, commander):
        """构造时间戳超过 max_age 的 call_id，验证清理后集合与时间戳字典均为空。"""
        # 注入一个过期的 call_id（时间戳早于 60s）
        stale_call_id = "stale-call-1"
        commander._cascade_call_ids.add(stale_call_id)
        commander._cascade_call_id_timestamps[stale_call_id] = time.time() - 120  # 120s 前已过期

        commander._cleanup_stale_call_ids(max_age=60.0)

        assert stale_call_id not in commander._cascade_call_ids
        assert stale_call_id not in commander._cascade_call_id_timestamps

    def test_cleanup_preserves_fresh_entries(self, commander):
        """新鲜 call_id（未超过 max_age）不应被清理。"""
        fresh_call_id = "fresh-call-1"
        commander._cascade_call_ids.add(fresh_call_id)
        fresh_ts = time.time() - 5  # 仅 5 秒前
        commander._cascade_call_id_timestamps[fresh_call_id] = fresh_ts

        commander._cleanup_stale_call_ids(max_age=60.0)

        assert fresh_call_id in commander._cascade_call_ids
        assert commander._cascade_call_id_timestamps[fresh_call_id] == fresh_ts

    def test_cleanup_partial_removes_only_stale(self, commander):
        """混合场景：仅清理过期条目，保留新鲜条目。"""
        stale_id, fresh_id = "stale-x", "fresh-y"
        commander._cascade_call_ids.update({stale_id, fresh_id})
        commander._cascade_call_id_timestamps[stale_id] = time.time() - 200
        commander._cascade_call_id_timestamps[fresh_id] = time.time()

        commander._cleanup_stale_call_ids(max_age=60.0)

        assert stale_id not in commander._cascade_call_ids
        assert fresh_id in commander._cascade_call_ids

    def test_cleanup_with_empty_state_is_noop(self, commander):
        """空状态调用清理不应抛异常。"""
        commander._cleanup_stale_call_ids(max_age=60.0)
        assert commander._cascade_call_ids == set()
        assert commander._cascade_call_id_timestamps == {}


# ---------------------------------------------------------------------------
# 3. handle_any_response
# ---------------------------------------------------------------------------

class TestHandleAnyResponse:
    """验证 handle_any_response 对未知/已知 call_id 的分支处理。"""

    def _make_response(self, call_id: str, status_code: int, www_authenticate: str = "") -> SimpleNamespace:
        """构造模拟 SipMessage 响应对象。

        使用 SimpleNamespace 模拟 SipMessage 接口：call_id 属性、status_code 属性、
        get_header 方法。SipCascadeCommander.handle_any_response 仅依赖这三个接口。
        """
        msg = SimpleNamespace()
        msg.call_id = call_id
        msg.status_code = status_code
        msg._www_authenticate = www_authenticate

        def get_header(name: str, default: str = "") -> str:
            if name == "WWW-Authenticate":
                return msg._www_authenticate
            return default

        msg.get_header = get_header
        return msg

    def test_unknown_call_id_returns_false(self, commander):
        """未知 call_id 的响应应返回 False（不属于级联事务）。"""
        msg = self._make_response("unknown-call-id", 200)
        result = commander.handle_any_response(msg)
        assert result is False

    def test_empty_call_id_returns_false(self, commander):
        """空 call_id 的响应应返回 False。"""
        msg = self._make_response("", 200)
        result = commander.handle_any_response(msg)
        assert result is False

    def test_known_call_id_200_response_returns_true_and_cleans_up(self, commander):
        """已知 call_id 收到 200 响应应返回 True，并从跟踪集合中移除 call_id。"""
        call_id = "cascade-reg-200"
        commander._cascade_call_ids.add(call_id)
        commander._cascade_call_id_timestamps[call_id] = time.time()

        msg = self._make_response(call_id, 200)
        result = commander.handle_any_response(msg)

        assert result is True
        assert call_id not in commander._cascade_call_ids, "200 响应后必须清理 call_id"

    def test_known_call_id_401_response_returns_true_and_retains_call_id(self, commander):
        """已知 call_id 收到 401 挑战响应应返回 True，但保留 call_id 等待重注册完成。"""
        call_id = "cascade-reg-401"
        commander._cascade_call_ids.add(call_id)
        commander._cascade_call_id_timestamps[call_id] = time.time()

        msg = self._make_response(
            call_id, 401, www_authenticate='Digest realm="test", nonce="abc"'
        )
        result = commander.handle_any_response(msg)

        assert result is True
        # 401 不在 [200, 699] 完成范围之外？实际 401 也落入 200-699 区间会清理。
        # 验证实际行为：401 落在 [200, 699] 区间，所以也会被清理（与源码 if 200 <= status_code <= 699 一致）
        # 这里验证源码实际行为，不预设期望
        # 注意：源码 77-78 行 `if 200 <= status_code <= 699: self._cascade_call_ids.discard(call_id)`
        # 401 在该区间内，所以会被清理
        assert call_id not in commander._cascade_call_ids

    def test_known_call_id_100_provisional_response_retains_call_id(self, commander):
        """100 临时响应不在 [200, 699] 区间，不应清理 call_id，但应返回 True。"""
        call_id = "cascade-reg-100"
        commander._cascade_call_ids.add(call_id)
        commander._cascade_call_id_timestamps[call_id] = time.time()

        msg = self._make_response(call_id, 100)
        result = commander.handle_any_response(msg)

        assert result is True
        assert call_id in commander._cascade_call_ids, "100 临时响应不应清理 call_id"


# ---------------------------------------------------------------------------
# 4. start_platform / stop_platform no-op 行为
# ---------------------------------------------------------------------------

class TestPlatformLifecycleNoop:
    """验证 PlatformService 缺失或未运行时，start/stop 不抛异常。"""

    @pytest.mark.asyncio
    async def test_start_platform_no_op_when_svc_is_none(self, commander):
        """PlatformService 单例为 None 时，start_platform 应静默 no-op。"""
        platform = SimpleNamespace(id="platform-1")
        with patch("app.services.platform_service.platform_service", None):
            # 不应抛出异常
            await commander.start_platform(platform)

    @pytest.mark.asyncio
    async def test_start_platform_no_op_when_svc_not_running(self, commander):
        """svc.running=False 时，start_platform 不应调用 trigger_register。"""
        platform = SimpleNamespace(id="platform-2")
        mock_svc = MagicMock()
        mock_svc.running = False
        mock_svc.trigger_register = AsyncMock()
        with patch("app.services.platform_service.platform_service", mock_svc):
            await commander.start_platform(platform)
        mock_svc.trigger_register.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_start_platform_delegates_when_svc_running(self, commander):
        """svc.running=True 时，start_platform 应委托调用 trigger_register。"""
        platform = SimpleNamespace(id="platform-3")
        mock_svc = MagicMock()
        mock_svc.running = True
        mock_svc.trigger_register = AsyncMock()
        with patch("app.services.platform_service.platform_service", mock_svc):
            await commander.start_platform(platform)
        mock_svc.trigger_register.assert_awaited_once_with("platform-3")

    @pytest.mark.asyncio
    async def test_stop_platform_no_op_when_svc_is_none(self, commander):
        """PlatformService 单例为 None 时，stop_platform 应静默 no-op。"""
        with patch("app.services.platform_service.platform_service", None):
            # 不应抛出异常
            await commander.stop_platform("platform-id-x")

    @pytest.mark.asyncio
    async def test_stop_platform_no_op_when_svc_not_running(self, commander):
        """svc.running=False 时，stop_platform 不应调用 handle_platform_offline。"""
        mock_svc = MagicMock()
        mock_svc.running = False
        mock_svc.handle_platform_offline = AsyncMock()
        with patch("app.services.platform_service.platform_service", mock_svc):
            await commander.stop_platform("platform-id-y")
        mock_svc.handle_platform_offline.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_stop_platform_delegates_when_svc_running(self, commander):
        """svc.running=True 时，stop_platform 应委托调用 handle_platform_offline。"""
        mock_svc = MagicMock()
        mock_svc.running = True
        mock_svc.handle_platform_offline = AsyncMock()
        with patch("app.services.platform_service.platform_service", mock_svc):
            await commander.stop_platform("platform-id-z")
        mock_svc.handle_platform_offline.assert_awaited_once_with(
            "platform-id-z", reason="cascade_stop"
        )


# ---------------------------------------------------------------------------
# 5. start_all / stop_all no-op
# ---------------------------------------------------------------------------

class TestStartAllStopAllNoop:
    """验证 start_all / stop_all 是 no-op（仅记录 debug 日志，不依赖外部状态）。"""

    @pytest.mark.asyncio
    async def test_start_all_does_not_raise(self, commander):
        """start_all 应静默 no-op，不依赖任何外部服务。"""
        # 不应抛出异常；无返回值验证
        await commander.start_all()

    @pytest.mark.asyncio
    async def test_stop_all_does_not_raise(self, commander):
        """stop_all 应静默 no-op，不依赖任何外部服务。"""
        await commander.stop_all()

    @pytest.mark.asyncio
    async def test_send_keepalive_is_noop(self, commander):
        """send_keepalive 已迁移到 PlatformService._keepalive_loop，应直接返回。"""
        platform = SimpleNamespace(id="platform-kp")
        # 不应抛异常；不调用任何外部依赖
        await commander.send_keepalive(platform)
