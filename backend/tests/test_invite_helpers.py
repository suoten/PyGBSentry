"""测试 app/sip/invite.py 中的纯函数与 InviteState 类。

本测试聚焦不依赖 DB/网络的纯函数与状态管理：
  - _gb28181_playback_time：epoch → GB28181 时间字符串
  - _attach_trace_header：返回 Call-ID 用于日志关联（FIX [2026-07-21 P0] 不再设置 X-Trace-ID 头）
  - InviteState：构造函数初始化、cleanup() TTL 清理、invite_rate_stats 初始值

避免触发 send_sip_bytes / 数据库会话等重依赖路径，仅验证逻辑分支。
"""
import asyncio
import time

import pytest

from app.sip.message import SipMessage


# ---------------------------------------------------------------------------
# 1. _gb28181_playback_time
# ---------------------------------------------------------------------------

class TestGb28181PlaybackTime:
    """验证 _gb28181_playback_time 将 epoch 转为 GB28181 时间字符串的逻辑。"""

    def test_zero_epoch_returns_default(self):
        """epoch=0（falsy）应返回默认值 '19700101T000000Z'。"""
        from app.sip.invite import _gb28181_playback_time
        assert _gb28181_playback_time(0) == "19700101T000000Z"

    def test_negative_epoch_returns_default(self):
        """epoch=-1（<=0）应返回默认值。"""
        from app.sip.invite import _gb28181_playback_time
        assert _gb28181_playback_time(-1) == "19700101T000000Z"

    def test_valid_epoch_returns_correct_format(self):
        """合法 epoch 应返回 16 字符的 GB28181 时间字符串（YYYYMMDDTHHMMSSZ）。"""
        from app.sip.invite import _gb28181_playback_time
        # 1690000000 = 2023-07-22 04:26:40 UTC
        result = _gb28181_playback_time(1690000000)
        # 验证格式：%Y%m%dT%H%M%SZ
        assert len(result) == 16, f"GB28181 时间字符串长度必须为 16，实际: {len(result)}"
        assert result[8] == "T", "第 9 位必须是 'T' 分隔符"
        assert result[-1] == "Z", "末尾必须是 'Z' UTC 标记"
        # 验证具体值（UTC 时间）
        assert result == "20230722T042640Z", f"GB28181 时间字符串不匹配: {result}"

    def test_valid_epoch_format_only(self):
        """仅验证格式（不绑定具体时间），确保格式合规。"""
        from app.sip.invite import _gb28181_playback_time
        import re
        result = _gb28181_playback_time(1700000000)
        # YYYYMMDDTHHMMSSZ 模式
        pattern = r"^\d{8}T\d{6}Z$"
        assert re.match(pattern, result), f"格式不匹配 YYYYMMDDTHHMMSSZ: {result}"


# ---------------------------------------------------------------------------
# 2. _attach_trace_header
# ---------------------------------------------------------------------------

class TestAttachTraceHeader:
    """验证 _attach_trace_header 返回 Call-ID 用于日志关联。

    FIX: [2026-07-21 P0] _attach_trace_header 不再设置 X-Trace-ID 头域，
    以兼容 EasyGBS 等非标准 SIP 客户端（对非标准头域敏感，会返回 400 Bad Request）。
    函数签名变更为返回 Call-ID 字符串，供调用方用于日志关联。
    """

    def test_with_call_id_returns_call_id(self):
        """req 含 Call-ID 时，应返回相同值用于日志关联。"""
        from app.sip.invite import _attach_trace_header
        req = SipMessage()
        req.headers["Call-ID"] = "test-call-id-123"

        result = _attach_trace_header(req)

        assert result == "test-call-id-123"

    def test_with_call_id_does_not_set_x_trace_id_header(self):
        """FIX [2026-07-21 P0]: 不应再向 req 写入 X-Trace-ID 头域。"""
        from app.sip.invite import _attach_trace_header
        req = SipMessage()
        req.headers["Call-ID"] = "test-call-id-123"

        _attach_trace_header(req)

        assert "X-Trace-ID" not in req.headers
        assert req.get_header("X-Trace-ID") == ""

    def test_without_call_id_returns_empty_string(self):
        """req 无 Call-ID 时，应返回空字符串。"""
        from app.sip.invite import _attach_trace_header
        req = SipMessage()
        # 不设置 Call-ID
        result = _attach_trace_header(req)
        assert result == ""
        assert "X-Trace-ID" not in req.headers

    def test_empty_call_id_returns_empty_string(self):
        """空 Call-ID（""）应被视为无 Call-ID，返回空字符串。"""
        from app.sip.invite import _attach_trace_header
        req = SipMessage()
        req.headers["Call-ID"] = ""
        result = _attach_trace_header(req)
        assert result == ""
        assert "X-Trace-ID" not in req.headers

    def test_whitespace_call_id_stripped(self):
        """带空白的 Call-ID 应 strip 后返回（源码 .strip()）。"""
        from app.sip.invite import _attach_trace_header
        req = SipMessage()
        req.headers["Call-ID"] = "  trace-id-abc  "
        result = _attach_trace_header(req)
        # 源码：call_id = (req.get_header("Call-ID") or "").strip()
        # 返回值应为 strip 后的值
        assert result == "trace-id-abc"


# ---------------------------------------------------------------------------
# 3. InviteState 初始化与清理
# ---------------------------------------------------------------------------

class TestInviteStateInit:
    """验证 InviteState 构造函数初始化所有状态字段与信号量。"""

    def test_init_creates_stream_switch_lock(self):
        from app.sip.invite import InviteState
        state = InviteState()
        assert isinstance(state.stream_switch_lock, asyncio.Lock)

    def test_init_creates_empty_stream_switch_dicts(self):
        """stream_switch_pending 与 timestamps 应为空 dict。"""
        from app.sip.invite import InviteState
        state = InviteState()
        assert state.stream_switch_pending == {}
        assert state.stream_switch_pending_timestamps == {}
        assert state.stream_switch_rollback_depth == {}
        assert state.stream_switch_rollback_depth_timestamps == {}

    def test_init_stream_switch_limits(self):
        """max_size 与 ttl 应为预期常量值。"""
        from app.sip.invite import InviteState
        state = InviteState()
        assert state.stream_switch_rollback_depth_max == 500
        assert state.stream_switch_rollback_depth_ttl == 120
        assert state.stream_switch_pending_max == 1000
        assert state.stream_switch_pending_ttl == 60

    def test_init_invite_rate_stats_all_zero(self):
        """invite_rate_stats 应初始化为全 0 计数字典。"""
        from app.sip.invite import InviteState
        state = InviteState()
        expected_keys = {
            "allowed",
            "blocked_device",
            "blocked_tenant",
            "backend_redis",
            "backend_local",
            "backend_fallback",
        }
        assert set(state.invite_rate_stats.keys()) == expected_keys
        assert all(v == 0 for v in state.invite_rate_stats.values()), \
            "所有 invite_rate_stats 初始值必须为 0"

    def test_init_invite_pending_empty(self):
        """invite_pending / invite_provisional 应为空 dict。"""
        from app.sip.invite import InviteState
        state = InviteState()
        assert state.invite_pending == {}
        assert state.invite_provisional == {}

    def test_init_cascade_call_ids_empty_dict(self):
        """cascade_call_ids 应为 dict[str, float]（不是 set），用于 TTL 清理。"""
        from app.sip.invite import InviteState
        state = InviteState()
        assert isinstance(state.cascade_call_ids, dict)
        assert state.cascade_call_ids == {}
        assert state.cascade_call_ids_max == 2000
        assert state.cascade_call_ids_ttl == 300

    def test_init_global_invite_semaphore(self):
        """global_invite_semaphore 应为 asyncio.Semaphore 实例。"""
        from app.sip.invite import InviteState
        state = InviteState()
        assert isinstance(state.global_invite_semaphore, asyncio.Semaphore)

    def test_init_channel_invite_locks_empty(self):
        from app.sip.invite import InviteState
        state = InviteState()
        assert state.channel_invite_locks == {}

    def test_init_ssrc_gen_lock(self):
        from app.sip.invite import InviteState
        state = InviteState()
        assert isinstance(state.ssrc_gen_lock, asyncio.Lock)


class TestInviteStateCleanup:
    """验证 InviteState.cleanup() 按 TTL 清理过期条目。"""

    def test_cleanup_removes_stale_stream_switch_rollback_depth(self):
        """超过 rollback_depth_ttl 的条目应被 cleanup 移除。"""
        from app.sip.invite import InviteState
        state = InviteState()
        # 注入一个 200 秒前的条目（TTL=120）
        stale_key = "channel-stale"
        state.stream_switch_rollback_depth[stale_key] = 3
        state.stream_switch_rollback_depth_timestamps[stale_key] = time.time() - 200

        # 注入一个新鲜条目
        fresh_key = "channel-fresh"
        state.stream_switch_rollback_depth[fresh_key] = 1
        state.stream_switch_rollback_depth_timestamps[fresh_key] = time.time()

        state.cleanup()

        assert stale_key not in state.stream_switch_rollback_depth
        assert stale_key not in state.stream_switch_rollback_depth_timestamps
        assert fresh_key in state.stream_switch_rollback_depth

    def test_cleanup_removes_stale_stream_switch_pending(self):
        """超过 stream_switch_pending_ttl（60s）的 pending 条目应被清理。"""
        from app.sip.invite import InviteState
        state = InviteState()
        stale_key = "switch-stale"
        state.stream_switch_pending[stale_key] = "old-data"
        state.stream_switch_pending_timestamps[stale_key] = time.time() - 100  # 100s 前

        fresh_key = "switch-fresh"
        state.stream_switch_pending[fresh_key] = "new-data"
        state.stream_switch_pending_timestamps[fresh_key] = time.time()

        state.cleanup()

        assert stale_key not in state.stream_switch_pending
        assert fresh_key in state.stream_switch_pending

    def test_cleanup_removes_stale_cascade_call_ids(self):
        """超过 cascade_call_ids_ttl（300s）的 call_id 应被清理。"""
        from app.sip.invite import InviteState
        state = InviteState()
        stale_call_id = "cascade-stale"
        state.cascade_call_ids[stale_call_id] = time.time() - 400  # 400s 前

        fresh_call_id = "cascade-fresh"
        state.cascade_call_ids[fresh_call_id] = time.time()

        state.cleanup()

        assert stale_call_id not in state.cascade_call_ids
        assert fresh_call_id in state.cascade_call_ids

    def test_cleanup_removes_stale_invite_pending_with_event_signal(self):
        """invite_pending 超过 300s TTL 应被清理，且对应 asyncio.Event 应被 set。"""
        from app.sip.invite import InviteState
        state = InviteState()
        stale_call_id = "invite-stale"
        event = asyncio.Event()
        result = {
            "ok": False,
            "sdp_response": "",
            "to_tag": "",
            "status_code": 0,
            "reason": "",
            "from_tag": "",
            "ssrc": "",
            "stream_id": "",
            "app": "",
            "node_id": "",
            "lease_id": "",
            "original_sdp": "",
            "watchdog_on_timeout": None,
            "created_at": time.time() - 400,  # 400s 前
        }
        state.invite_pending[stale_call_id] = (event, result)

        state.cleanup()

        assert stale_call_id not in state.invite_pending
        # event 应被 set，让等待者解除阻塞
        assert event.is_set() is True
        # result.reason 应被标记为 cleanup_ttl_expired
        assert result["ok"] is False
        assert result["reason"] == "cleanup_ttl_expired"

    def test_cleanup_preserves_fresh_invite_pending(self):
        """新鲜的 invite_pending（< 300s）不应被清理。"""
        from app.sip.invite import InviteState
        state = InviteState()
        fresh_call_id = "invite-fresh"
        event = asyncio.Event()
        result = {"created_at": time.time(), "ok": False}
        state.invite_pending[fresh_call_id] = (event, result)

        state.cleanup()

        assert fresh_call_id in state.invite_pending
        assert event.is_set() is False  # 未被触发

    def test_cleanup_removes_stale_invite_provisional(self):
        """invite_provisional 超过 300s 应被清理。"""
        from app.sip.invite import InviteState
        state = InviteState()
        stale_key = "prov-stale"
        state.invite_provisional[stale_key] = {"timestamp": time.time() - 400}

        state.cleanup()

        assert stale_key not in state.invite_provisional

    def test_cleanup_with_empty_state_is_noop(self):
        """空状态调用 cleanup 不应抛异常。"""
        from app.sip.invite import InviteState
        state = InviteState()
        state.cleanup()  # 不抛异常即可
        assert state.stream_switch_rollback_depth == {}
        assert state.cascade_call_ids == {}
        assert state.invite_pending == {}
