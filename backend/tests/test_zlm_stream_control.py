"""测试 app/services/zlm_stream_control.py 中的 ZLM 流控制函数。

本测试聚焦以下函数：
  - start_rtp_pusher / stop_rtp_pusher：startSendRtp / stopSendRtp HTTP 接口
  - add_ffmpeg_source / del_ffmpeg_source：FFmpeg 源管理接口
  - close_zlm_stream_sync：在无事件循环时的回退路径

测试策略：
  - 通过 patch app.services.zlm_rtp_server_service.get_shared_zlm_client 注入 mock client
  - mock client.post 返回不同的状态码 / JSON 数据，覆盖成功与失败分支
  - 验证返回值与异常处理逻辑
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import zlm_stream_control as zlm_mod


@pytest.fixture
def mock_client():
    """构造一个 mock httpx.AsyncClient，post 返回值可在测试用例中覆盖。"""
    client = AsyncMock()
    return client


@pytest.fixture
def patch_zlm_client(mock_client):
    """patch get_shared_zlm_client 返回 mock_client，确保 _get_zlm_client 拿到 mock。"""
    with patch(
        "app.services.zlm_rtp_server_service.get_shared_zlm_client",
        AsyncMock(return_value=mock_client),
    ):
        yield mock_client


def _make_response(status_code: int = 200, json_data: dict = None):
    """构造模拟 httpx.Response 对象。"""
    response = MagicMock()
    response.status_code = status_code
    response.json = MagicMock(return_value=json_data or {})
    return response


# ---------------------------------------------------------------------------
# 1. start_rtp_pusher
# ---------------------------------------------------------------------------

class TestStartRtpPusher:
    """验证 start_rtp_pusher 在不同 ZLM 响应下的行为。"""

    @pytest.mark.asyncio
    async def test_success_returns_true(self, patch_zlm_client):
        """ZLM 返回 code=0 应判定为成功，返回 True。"""
        patch_zlm_client.post = AsyncMock(
            return_value=_make_response(200, {"code": 0})
        )
        result = await zlm_mod.start_rtp_pusher(
            host="127.0.0.1",
            http_port=80,
            secret="s",
            app="live",
            stream="test",
            dst_ip="127.0.0.1",
            dst_port=30000,
            ssrc="0100000001",
        )
        assert result is True
        patch_zlm_client.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_failure_code_nonzero_returns_false(self, patch_zlm_client):
        """ZLM 返回 code=-1 应判定为失败，返回 False。"""
        patch_zlm_client.post = AsyncMock(
            return_value=_make_response(200, {"code": -1, "msg": "fail"})
        )
        result = await zlm_mod.start_rtp_pusher(
            host="127.0.0.1",
            http_port=80,
            secret="s",
            app="live",
            stream="test",
            dst_ip="127.0.0.1",
            dst_port=30000,
            ssrc="0100000001",
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_http_error_status_returns_false(self, patch_zlm_client):
        """ZLM 返回 HTTP 5xx 应判定为失败。"""
        patch_zlm_client.post = AsyncMock(
            return_value=_make_response(500, {})
        )
        result = await zlm_mod.start_rtp_pusher(
            host="127.0.0.1",
            http_port=80,
            secret="s",
            app="live",
            stream="test",
            dst_ip="127.0.0.1",
            dst_port=30000,
            ssrc="0100000001",
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_network_exception_returns_false(self, patch_zlm_client):
        """client.post 抛异常（网络错误）应被捕获并返回 False。"""
        patch_zlm_client.post = AsyncMock(side_effect=ConnectionError("network down"))
        result = await zlm_mod.start_rtp_pusher(
            host="127.0.0.1",
            http_port=80,
            secret="s",
            app="live",
            stream="test",
            dst_ip="127.0.0.1",
            dst_port=30000,
            ssrc="0100000001",
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_string_code_zero_returns_true(self, patch_zlm_client):
        """ZLM 有时返回字符串 code='0'，应同样判定为成功。"""
        patch_zlm_client.post = AsyncMock(
            return_value=_make_response(200, {"code": "0"})
        )
        result = await zlm_mod.start_rtp_pusher(
            host="127.0.0.1",
            http_port=80,
            secret="s",
            app="live",
            stream="test",
            dst_ip="127.0.0.1",
            dst_port=30000,
            ssrc="0100000001",
        )
        assert result is True


# ---------------------------------------------------------------------------
# 2. stop_rtp_pusher
# ---------------------------------------------------------------------------

class TestStopRtpPusher:
    """验证 stop_rtp_pusher 在不同 ZLM 响应下的行为。"""

    @pytest.mark.asyncio
    async def test_success_returns_true(self, patch_zlm_client):
        """ZLM 返回 code=0 应判定为停止成功。"""
        patch_zlm_client.post = AsyncMock(
            return_value=_make_response(200, {"code": 0})
        )
        result = await zlm_mod.stop_rtp_pusher(
            host="127.0.0.1", http_port=80, secret="s", app="live", stream="test"
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_failure_code_nonzero_returns_false(self, patch_zlm_client):
        """ZLM 返回 code=-1 应判定为失败。"""
        patch_zlm_client.post = AsyncMock(
            return_value=_make_response(200, {"code": -1, "msg": "fail"})
        )
        result = await zlm_mod.stop_rtp_pusher(
            host="127.0.0.1", http_port=80, secret="s", app="live", stream="test"
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_http_error_status_returns_false(self, patch_zlm_client):
        """ZLM 返回 HTTP 4xx 应判定为失败。"""
        patch_zlm_client.post = AsyncMock(
            return_value=_make_response(404, {})
        )
        result = await zlm_mod.stop_rtp_pusher(
            host="127.0.0.1", http_port=80, secret="s", app="live", stream="test"
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_network_exception_returns_false(self, patch_zlm_client):
        """网络异常应被捕获并返回 False，不应抛出。"""
        patch_zlm_client.post = AsyncMock(side_effect=TimeoutError("timeout"))
        result = await zlm_mod.stop_rtp_pusher(
            host="127.0.0.1", http_port=80, secret="s", app="live", stream="test"
        )
        assert result is False


# ---------------------------------------------------------------------------
# 3. add_ffmpeg_source
# ---------------------------------------------------------------------------

class TestAddFfmpegSource:
    """验证 add_ffmpeg_source 提取 key 的逻辑。"""

    @pytest.mark.asyncio
    async def test_success_returns_key(self, patch_zlm_client):
        """ZLM 返回 code=0 + data.key 应返回该 key 字符串。"""
        patch_zlm_client.post = AsyncMock(
            return_value=_make_response(200, {"code": 0, "data": {"key": "test_key"}})
        )
        result = await zlm_mod.add_ffmpeg_source(
            host="127.0.0.1",
            http_port=80,
            secret="s",
            src_url="rtmp://src/live",
            dst_url="rtmp://dst/live",
        )
        assert result == "test_key"

    @pytest.mark.asyncio
    async def test_failure_code_nonzero_returns_empty(self, patch_zlm_client):
        """ZLM 返回 code=-1 应返回空字符串。"""
        patch_zlm_client.post = AsyncMock(
            return_value=_make_response(200, {"code": -1, "msg": "fail"})
        )
        result = await zlm_mod.add_ffmpeg_source(
            host="127.0.0.1",
            http_port=80,
            secret="s",
            src_url="rtmp://src/live",
            dst_url="rtmp://dst/live",
        )
        assert result == ""

    @pytest.mark.asyncio
    async def test_http_error_returns_empty(self, patch_zlm_client):
        """ZLM 返回 HTTP 5xx 应返回空字符串。"""
        patch_zlm_client.post = AsyncMock(
            return_value=_make_response(500, {})
        )
        result = await zlm_mod.add_ffmpeg_source(
            host="127.0.0.1",
            http_port=80,
            secret="s",
            src_url="rtmp://src/live",
            dst_url="rtmp://dst/live",
        )
        assert result == ""

    @pytest.mark.asyncio
    async def test_exception_returns_empty(self, patch_zlm_client):
        """网络异常应被捕获并返回空字符串。"""
        patch_zlm_client.post = AsyncMock(side_effect=ConnectionError("network down"))
        result = await zlm_mod.add_ffmpeg_source(
            host="127.0.0.1",
            http_port=80,
            secret="s",
            src_url="rtmp://src/live",
            dst_url="rtmp://dst/live",
        )
        assert result == ""

    @pytest.mark.asyncio
    async def test_missing_data_returns_empty(self, patch_zlm_client):
        """ZLM 返回 code=0 但缺少 data 字段时，应返回空字符串。"""
        patch_zlm_client.post = AsyncMock(
            return_value=_make_response(200, {"code": 0})
        )
        result = await zlm_mod.add_ffmpeg_source(
            host="127.0.0.1",
            http_port=80,
            secret="s",
            src_url="rtmp://src/live",
            dst_url="rtmp://dst/live",
        )
        assert result == ""


# ---------------------------------------------------------------------------
# 4. del_ffmpeg_source
# ---------------------------------------------------------------------------

class TestDelFfmpegSource:
    """验证 del_ffmpeg_source 的成功/幂等/失败判定。"""

    @pytest.mark.asyncio
    async def test_success_returns_true(self, patch_zlm_client):
        """ZLM 返回 code=0 应判定删除成功。"""
        patch_zlm_client.post = AsyncMock(
            return_value=_make_response(200, {"code": 0})
        )
        result = await zlm_mod.del_ffmpeg_source(
            host="127.0.0.1", http_port=80, secret="s", key="test_key"
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_idempotent_not_found_returns_true(self, patch_zlm_client):
        """ZLM 返回 code=-1 + msg='not found' 应判定为幂等成功。"""
        patch_zlm_client.post = AsyncMock(
            return_value=_make_response(200, {"code": -1, "msg": "not found"})
        )
        result = await zlm_mod.del_ffmpeg_source(
            host="127.0.0.1", http_port=80, secret="s", key="test_key"
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_idempotent_not_exist_chinese_returns_true(self, patch_zlm_client):
        """ZLM 返回中文 '未找到' 也应识别为幂等成功。"""
        patch_zlm_client.post = AsyncMock(
            return_value=_make_response(200, {"code": -1, "msg": "未找到该源"})
        )
        result = await zlm_mod.del_ffmpeg_source(
            host="127.0.0.1", http_port=80, secret="s", key="test_key"
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_failure_other_error_returns_false(self, patch_zlm_client):
        """ZLM 返回 code=-1 + 其他错误 msg 应判定为失败。"""
        patch_zlm_client.post = AsyncMock(
            return_value=_make_response(200, {"code": -1, "msg": "internal error"})
        )
        result = await zlm_mod.del_ffmpeg_source(
            host="127.0.0.1", http_port=80, secret="s", key="test_key"
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_http_error_returns_false(self, patch_zlm_client):
        """ZLM 返回 HTTP 5xx 应判定为失败。"""
        patch_zlm_client.post = AsyncMock(
            return_value=_make_response(500, {})
        )
        result = await zlm_mod.del_ffmpeg_source(
            host="127.0.0.1", http_port=80, secret="s", key="test_key"
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_exception_returns_false(self, patch_zlm_client):
        """网络异常应被捕获并返回 False。"""
        patch_zlm_client.post = AsyncMock(side_effect=ConnectionError("network down"))
        result = await zlm_mod.del_ffmpeg_source(
            host="127.0.0.1", http_port=80, secret="s", key="test_key"
        )
        assert result is False


# ---------------------------------------------------------------------------
# 5. close_zlm_stream_sync
# ---------------------------------------------------------------------------

class TestCloseZlmStreamSync:
    """验证 close_zlm_stream_sync 在无事件循环时的回退路径不崩溃。"""

    def test_no_running_loop_falls_back_to_asyncio_run(self):
        """在同步上下文（无运行中的事件循环）中调用 close_zlm_stream_sync 不应崩溃。

        close_zlm_stream_sync 设计为：
          - 有运行 loop 时：fire-and-forget 创建任务
          - 无运行 loop（RuntimeError）时：fallback 到 asyncio.run
        本测试在 pytest 同步上下文中调用，触发 RuntimeError 分支，
        验证即便底层 close_zlm_stream 因缺少媒体节点配置而抛异常，sync 包装层也不应向外抛出。
        """
        # close_zlm_stream 内部会尝试连接数据库/媒体节点，
        # 在测试环境无配置的情况下会抛异常，但 close_zlm_stream_sync 应吞下异常。
        try:
            zlm_mod.close_zlm_stream_sync(app="live", stream="test")
        except Exception as exc:  # pragma: no cover - 防御性断言
            pytest.fail(f"close_zlm_stream_sync 不应向外抛出异常，但抛出了: {exc}")

    def test_no_running_loop_with_node_id_does_not_crash(self):
        """指定 node_id 调用也不应崩溃。"""
        try:
            zlm_mod.close_zlm_stream_sync(
                app="live", stream="test", node_id="nonexistent-node"
            )
        except Exception as exc:  # pragma: no cover - 防御性断言
            pytest.fail(f"close_zlm_stream_sync(node_id) 不应抛出异常: {exc}")
