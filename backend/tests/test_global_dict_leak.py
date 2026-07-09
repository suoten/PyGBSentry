"""FIX-LEAK: 全局字典内存泄漏和竞态条件测试

覆盖三类全局字典的并发安全和定期清理机制：
1. _SEEN_REQUESTS (handlers.py) — 请求去重缓存
2. _auth_failure_tracker (state_backend.py) — 鉴权失败追踪
3. _cleanup_locks (handlers.py) — 设备清理锁

验收标准：
- 所有全局字典有定期清理机制
- 并发访问有锁保护
- 新增的后台清理 task 在应用关闭时正确取消
"""
import asyncio
import sys
import time
import unittest


def _ensure_config_loaded() -> None:
    """确保真实的 app.core.config 已加载，保留 sip_host_for_contact 等函数。"""
    if "app.core.config" not in sys.modules:
        import importlib
        importlib.import_module("app.core.config")


class TestSeenRequestsLock(unittest.IsolatedAsyncioTestCase):
    """_SEEN_REQUESTS 并发安全与清理机制测试。"""

    def setUp(self) -> None:
        _ensure_config_loaded()

    async def asyncSetUp(self) -> None:
        # 每个测试前清空全局字典，避免互相影响
        from app.sip import handlers as h
        async with h._seen_requests_lock:
            h._SEEN_REQUESTS.clear()

    async def test_check_and_record_seen_request_dedup(self):
        """同一 dedup_key 的非 INVITE 请求第二次应判定为重复。"""
        from app.sip.handlers import check_and_record_seen_request

        first = await check_and_record_seen_request("call1~1", "REGISTER")
        self.assertFalse(first, "首次记录应返回 False（非重复）")
        second = await check_and_record_seen_request("call1~1", "REGISTER")
        self.assertTrue(second, "重复请求应返回 True")

    async def test_invite_not_deduped(self):
        """INVITE 重传不应被去重（RFC 3261 §17.2.1）。"""
        from app.sip.handlers import check_and_record_seen_request

        first = await check_and_record_seen_request("call2~1", "INVITE")
        self.assertFalse(first)
        # INVITE 即使重复也不应被去重
        second = await check_and_record_seen_request("call2~1", "INVITE")
        self.assertFalse(second, "INVITE 重传不应被去重")

    async def test_empty_key_not_recorded(self):
        """空 dedup_key 应返回 False 且不记录。"""
        from app.sip.handlers import check_and_record_seen_request, _SEEN_REQUESTS

        result = await check_and_record_seen_request("", "REGISTER")
        self.assertFalse(result)
        self.assertEqual(len(_SEEN_REQUESTS), 0)

    async def test_concurrent_dedup_no_corruption(self):
        """100 个协程并发对同一 key 调用，字典状态应一致不损坏。"""
        from app.sip.handlers import check_and_record_seen_request, _SEEN_REQUESTS

        key = "concurrent~1"
        results = await asyncio.gather(
            *[check_and_record_seen_request(key, "REGISTER") for _ in range(100)]
        )
        # 恰好 1 个 False（首次记录），其余 99 个 True（重复）
        self.assertEqual(results.count(False), 1)
        self.assertEqual(results.count(True), 99)
        # 字典中只有 1 个条目
        self.assertEqual(len(_SEEN_REQUESTS), 1)
        self.assertIn(key, _SEEN_REQUESTS)

    async def test_concurrent_distinct_keys_all_recorded(self):
        """并发写入不同 key，所有 key 应被记录。"""
        from app.sip.handlers import check_and_record_seen_request, _SEEN_REQUESTS

        keys = [f"distinct~{i}" for i in range(50)]
        results = await asyncio.gather(
            *[check_and_record_seen_request(k, "REGISTER") for k in keys]
        )
        self.assertTrue(all(r is False for r in results), "所有不同 key 首次应返回 False")
        self.assertEqual(len(_SEEN_REQUESTS), 50)

    async def test_cleanup_seen_requests_removes_expired(self):
        """cleanup_seen_requests 应清理过期条目。"""
        from app.sip import handlers as h

        # 直接操作模块级字典，使用较短的 TTL 便于测试
        original_ttl = h._SEEN_REQUESTS_TTL
        h._SEEN_REQUESTS_TTL = 2
        try:
            h._SEEN_REQUESTS["keep~1"] = time.time()
            h._SEEN_REQUESTS["expired~1"] = time.time() - 100  # 已过期
            removed = await h.cleanup_seen_requests()
            self.assertEqual(removed, 1)
            self.assertNotIn("expired~1", h._SEEN_REQUESTS)
            self.assertIn("keep~1", h._SEEN_REQUESTS)
        finally:
            h._SEEN_REQUESTS_TTL = original_ttl

    async def test_size_triggered_cleanup(self):
        """字典超过 MAX_SIZE 时应触发内联清理。"""
        from app.sip import handlers as h

        # 直接设置模块级 MAX_SIZE 为较小值便于测试
        original_max = h._SEEN_REQUESTS_MAX
        original_ttl = h._SEEN_REQUESTS_TTL
        h._SEEN_REQUESTS_MAX = 10
        h._SEEN_REQUESTS_TTL = 2
        try:
            # 填入 10 个过期条目，第 11 次写入使 len=11 > MAX_SIZE=10 触发清理
            old_ts = time.time() - 100
            for i in range(10):
                h._SEEN_REQUESTS[f"old~{i}"] = old_ts
            # 写入新条目，触发 size-based cleanup
            await h.check_and_record_seen_request("new~1", "REGISTER")
            # 过期条目应被清理
            remaining_old = [k for k in h._SEEN_REQUESTS if k.startswith("old~")]
            self.assertEqual(len(remaining_old), 0, "size-triggered cleanup 应清理过期条目")
        finally:
            h._SEEN_REQUESTS_MAX = original_max
            h._SEEN_REQUESTS_TTL = original_ttl


class TestCleanupLocksRelease(unittest.IsolatedAsyncioTestCase):
    """_cleanup_locks 锁回收机制测试。"""

    def setUp(self) -> None:
        _ensure_config_loaded()

    async def asyncSetUp(self) -> None:
        from app.sip import handlers as h
        async with h._cleanup_locks_guard:
            h._cleanup_locks.clear()

    async def test_release_cleanup_lock_removes_entry(self):
        """_release_cleanup_lock 应在锁未被持有时移除字典条目。"""
        from app.sip.handlers import _get_cleanup_lock, _release_cleanup_lock, _cleanup_locks

        gb_id = "test_device_1"
        lock = await _get_cleanup_lock(gb_id)
        self.assertIn(gb_id, _cleanup_locks)
        await _release_cleanup_lock(gb_id, lock)
        self.assertNotIn(gb_id, _cleanup_locks, "锁未被持有时应被移除")

    async def test_release_lock_keeps_held_lock(self):
        """若锁仍被持有，_release_cleanup_lock 不应移除（防止移除有等待者的锁）。"""
        from app.sip.handlers import _get_cleanup_lock, _release_cleanup_lock, _cleanup_locks

        gb_id = "test_device_2"
        lock = await _get_cleanup_lock(gb_id)
        # 持有锁
        await lock.acquire()
        try:
            await _release_cleanup_lock(gb_id, lock)
            # 锁仍被持有，不应被移除
            self.assertIn(gb_id, _cleanup_locks, "锁被持有时不应被移除")
        finally:
            lock.release()
        # 释放后可清理
        await _release_cleanup_lock(gb_id, lock)
        self.assertNotIn(gb_id, _cleanup_locks)

    async def test_cleanup_stale_locks(self):
        """cleanup_stale_cleanup_locks 应回收未被持有的锁。"""
        from app.sip.handlers import (
            _cleanup_locks,
            _get_cleanup_lock,
            cleanup_stale_cleanup_locks,
        )

        # 创建 3 个锁：2 个未持有，1 个被持有
        await _get_cleanup_lock("dev_1")
        await _get_cleanup_lock("dev_2")
        l3 = await _get_cleanup_lock("dev_3")
        await l3.acquire()
        try:
            removed = await cleanup_stale_cleanup_locks()
            self.assertEqual(removed, 2, "应回收 2 个未被持有的锁")
            self.assertNotIn("dev_1", _cleanup_locks)
            self.assertNotIn("dev_2", _cleanup_locks)
            self.assertIn("dev_3", _cleanup_locks, "被持有的锁不应被回收")
        finally:
            l3.release()

    async def test_concurrent_get_cleanup_lock_returns_same_instance(self):
        """并发获取同一 gb_id 的锁应返回同一实例。"""
        from app.sip.handlers import _get_cleanup_lock

        gb_id = "concurrent_device"
        locks = await asyncio.gather(*[_get_cleanup_lock(gb_id) for _ in range(20)])
        first = locks[0]
        for lock in locks:
            self.assertIs(lock, first, "同一 gb_id 应返回同一锁实例")


class TestAuthFailureTrackerLock(unittest.IsolatedAsyncioTestCase):
    """_auth_failure_tracker 并发安全与清理机制测试。"""

    def setUp(self) -> None:
        _ensure_config_loaded()

    async def asyncSetUp(self) -> None:
        from app.sip.state_backend import LocalSipStateBackend
        self.backend = LocalSipStateBackend()
        async with self.backend._auth_failure_lock:
            self.backend._auth_failure_tracker.clear()

    async def test_record_and_clear_auth_failure(self):
        """记录鉴权失败并清理后，字典应为空。"""
        count = await self.backend.record_auth_failure("1.2.3.4")
        self.assertGreaterEqual(count, 1)
        self.assertIn("1.2.3.4", self.backend._auth_failure_tracker)
        await self.backend.clear_auth_failure("1.2.3.4")
        self.assertNotIn("1.2.3.4", self.backend._auth_failure_tracker)

    async def test_concurrent_record_auth_failure_no_corruption(self):
        """100 个协程并发对同一 IP 记录失败，计数应一致。"""
        ip = "10.0.0.1"
        results = await asyncio.gather(
            *[self.backend.record_auth_failure(ip) for _ in range(100)]
        )
        # 最后一次返回的计数应为 100
        self.assertEqual(max(results), 100, "并发记录应全部成功，最终计数为 100")
        self.assertEqual(len(self.backend._auth_failure_tracker[ip]), 100)

    async def test_concurrent_distinct_ips_all_recorded(self):
        """并发记录不同 IP，所有 IP 应被记录。"""
        ips = [f"192.168.1.{i}" for i in range(50)]
        await asyncio.gather(*[self.backend.record_auth_failure(ip) for ip in ips])
        self.assertEqual(len(self.backend._auth_failure_tracker), 50)

    async def test_cleanup_auth_failures_removes_expired(self):
        """cleanup_auth_failures 应清理过期条目。"""
        from app.sip.state_backend import LocalSipStateBackend

        backend = LocalSipStateBackend()
        # TTL=300，写入一个过期条目和一个新鲜条目
        backend._auth_failure_tracker["expired_ip"] = [time.time() - 400]
        backend._auth_failure_tracker["fresh_ip"] = [time.time()]
        removed = await backend.cleanup_auth_failures()
        self.assertEqual(removed, 1)
        self.assertNotIn("expired_ip", backend._auth_failure_tracker)
        self.assertIn("fresh_ip", backend._auth_failure_tracker)

    async def test_cleanup_auth_failures_removes_empty_list(self):
        """cleanup_auth_failures 应清理空列表条目。"""
        from app.sip.state_backend import LocalSipStateBackend

        backend = LocalSipStateBackend()
        backend._auth_failure_tracker["empty_ip"] = []
        backend._auth_failure_tracker["valid_ip"] = [time.time()]
        removed = await backend.cleanup_auth_failures()
        self.assertEqual(removed, 1)
        self.assertNotIn("empty_ip", backend._auth_failure_tracker)
        self.assertIn("valid_ip", backend._auth_failure_tracker)

    async def test_size_triggered_cleanup_removes_oldest(self):
        """超过 _auth_failure_max_size 时应移除最旧的 IP 记录。"""
        from app.sip.state_backend import LocalSipStateBackend

        backend = LocalSipStateBackend()
        backend._auth_failure_max_size = 3
        # 写入 3 个不同时间戳的 IP
        backend._auth_failure_tracker["old_ip"] = [time.time() - 100]
        backend._auth_failure_tracker["mid_ip"] = [time.time() - 50]
        backend._auth_failure_tracker["new_ip"] = [time.time()]
        # 第 4 个触发清理
        count = await backend.record_auth_failure("trigger_ip")
        self.assertGreaterEqual(count, 1, "刚插入的 trigger_ip 应保留并返回其计数")
        # 最旧的 old_ip 应被移除
        self.assertNotIn("old_ip", backend._auth_failure_tracker)
        # trigger_ip 保留
        self.assertIn("trigger_ip", backend._auth_failure_tracker)


class TestPruneLoopCleanup(unittest.IsolatedAsyncioTestCase):
    """server._prune_loop() 定期清理集成测试。"""

    def setUp(self) -> None:
        _ensure_config_loaded()

    async def test_prune_loop_invokes_all_cleanups(self):
        """_prune_loop 应在配置间隔内调用所有 3 类清理函数。

        通过 mock 验证清理函数被调用，避免 DB/网络依赖导致的测试不稳定。
        """
        from app.sip import handlers as h
        from app.sip.state_backend import LocalSipStateBackend

        # 准备过期数据 — 时间戳需超过默认 TTL（_SEEN_REQUESTS_TTL=300s, _auth_failure_ttl=300s）
        async with h._seen_requests_lock:
            h._SEEN_REQUESTS["expired_req~1"] = time.time() - 400
        backend = LocalSipStateBackend()
        backend._auth_failure_tracker["expired_ip"] = [time.time() - 400]
        async with h._cleanup_locks_guard:
            h._cleanup_locks["stale_lock_dev"] = asyncio.Lock()

        # Mock get_sip_state_backend 返回我们的 backend 实例
        import app.sip.state_backend as sb_mod
        original_get = sb_mod.get_sip_state_backend
        sb_mod.get_sip_state_backend = lambda: backend
        try:
            from app.sip.server import SipServer
            server = SipServer.__new__(SipServer)
            server.running = True
            server._response_cache = {}
            server._response_cache_lock = asyncio.Lock()
            server._response_cache_ttl = 32
            server._response_cache_max_size = 50000
            server._seen_requests_cleanup_interval = 0  # 立即触发
            server._auth_failure_cleanup_interval = 0
            server._cleanup_locks_cleanup_interval = 0
            server._last_seen_requests_cleanup = 0.0
            server._last_auth_failure_cleanup = 0.0
            server._last_cleanup_locks_cleanup = 0.0

            # Mock DB/网络依赖的方法，避免 _prune_loop 卡在 DB 查询上
            async def _noop():
                return 0
            server._prune_response_cache = _noop
            server._check_device_offline = _noop

            # 运行一次循环后立即停止
            async def _run_once():
                task = asyncio.create_task(server._prune_loop())
                await asyncio.sleep(0.2)  # 让一次循环完成
                server.running = False
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            await _run_once()
        finally:
            sb_mod.get_sip_state_backend = original_get

        # 验证清理结果
        async with h._seen_requests_lock:
            self.assertNotIn("expired_req~1", h._SEEN_REQUESTS, "过期请求应被清理")
        self.assertNotIn("expired_ip", backend._auth_failure_tracker, "过期鉴权失败应被清理")
        async with h._cleanup_locks_guard:
            self.assertNotIn("stale_lock_dev", h._cleanup_locks, "未被持有的锁应被回收")


class TestBackgroundTaskCancellation(unittest.IsolatedAsyncioTestCase):
    """后台清理 task 在应用关闭时正确取消测试。"""

    def setUp(self) -> None:
        _ensure_config_loaded()

    async def test_stop_cancels_background_tasks(self):
        """SipServer.stop() 应取消所有 _background_tasks（包括 _prune_loop）。"""
        from app.sip.server import SipServer

        server = SipServer.__new__(SipServer)
        server.running = True
        server._background_tasks = set()
        # 初始化 stop() 中会访问的属性（使用 __new__ 跳过 __init__）
        server.udp_transport = None
        server.tcp_server = None
        server.tls_server = None
        server._workers = []
        server._task_queue = asyncio.Queue()

        # 启动一个模拟的 _prune_loop
        async def _fake_prune():
            while server.running:
                await asyncio.sleep(0.05)

        server._track_background_task(_fake_prune())
        self.assertGreater(len(server._background_tasks), 0, "应有后台 task 被跟踪")

        await server.stop()

        self.assertFalse(server.running)
        for task in server._background_tasks:
            self.assertTrue(task.done() or task.cancelled(), "所有后台 task 应被取消")


if __name__ == "__main__":
    unittest.main()
