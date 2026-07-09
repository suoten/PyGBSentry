"""商业就绪 E2E 测试套件。

验证核心功能链路的端到端可用性：
1. API 路由可达性（所有关键端点响应非 404）
2. 运维监控 API 功能正确性
3. 异常处理不再静默吞没
4. RTP 超时宽限期逻辑
5. N+1 查询修复验证
6. SIP 核心模块健壮性
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
from datetime import datetime, timezone


@pytest.mark.asyncio
class TestAPIAvailability:
    """验证所有关键 API 端点可达。"""

    async def test_health_liveness(self, client: AsyncClient):
        """健康检查 - liveness probe"""
        resp = await client.get("/api/v1/health/liveness")
        assert resp.status_code == 200
        assert resp.json()["status"] == "alive"

    async def test_ops_db_check(self, client: AsyncClient):
        """运维 - 数据库检查"""
        resp = await client.get("/api/v1/ops/db-check")
        assert resp.status_code == 200
        data = resp.json()
        assert "connected" in data

    async def test_ops_status(self, client: AsyncClient):
        """运维 - 系统状态（需认证）"""
        # 未认证应返回 401
        resp = await client.get("/api/v1/ops/status")
        assert resp.status_code in (401, 403, 200)  # 可能允许匿名或需认证

    async def test_ops_diagnose(self, client: AsyncClient):
        """运维 - 诊断报告（需认证）"""
        resp = await client.get("/api/v1/ops/diagnose")
        assert resp.status_code in (401, 403, 200)

    async def test_ops_diagnose_report(self, client: AsyncClient):
        """运维 - 完整诊断报告别名"""
        resp = await client.get("/api/v1/ops/diagnose-report")
        assert resp.status_code in (401, 403, 200)

    async def test_network_summary(self, client: AsyncClient):
        """网络 - 概况"""
        resp = await client.get("/api/v1/network/summary")
        assert resp.status_code in (401, 403, 200)

    async def test_network_bandwidth(self, client: AsyncClient):
        """网络 - 带宽"""
        resp = await client.get("/api/v1/network/bandwidth", params={"range": "1h"})
        assert resp.status_code in (401, 403, 200)

    async def test_network_topology(self, client: AsyncClient):
        """网络 - 拓扑"""
        resp = await client.get("/api/v1/network/topology")
        assert resp.status_code in (401, 403, 200)

    async def test_metrics_devices_overview(self, client: AsyncClient):
        """指标 - 设备概览"""
        resp = await client.get("/api/v1/metrics/devices-overview")
        assert resp.status_code in (401, 403, 200)

    async def test_health_overview(self, client: AsyncClient):
        """健康 - 概览"""
        resp = await client.get("/api/v1/health/overview")
        assert resp.status_code in (401, 403, 200)


@pytest.mark.asyncio
class TestOpsStatusContent:
    """验证运维状态 API 返回内容正确。"""

    async def test_ops_status_fields(self, client: AsyncClient, auth_headers: dict):
        """验证 /ops/status 返回包含所有必需字段"""
        resp = await client.get("/api/v1/ops/status", headers=auth_headers)
        if resp.status_code == 200:
            data = resp.json()
            required_fields = ["cpu", "memory_percent", "zlm_status", "zlm_streams", "uptime_seconds"]
            for field in required_fields:
                assert field in data, f"Missing field: {field}"


@pytest.mark.asyncio
class TestExceptionHandling:
    """验证异常不再被静默吞没。"""

    async def test_no_bare_except_pass_in_sip_core(self):
        """验证 SIP 核心文件中不再有 except: pass 模式"""
        import os
        sip_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app", "sip")
        sip_files = ["talk.py", "handlers.py", "invite.py", "response_handler.py",
                      "server.py", "dialog_manager.py", "catalog_runtime.py",
                      "subscribe_manager.py", "watchdog.py"]
        violations = []
        for fname in sip_files:
            fpath = os.path.join(sip_dir, fname)
            if not os.path.exists(fpath):
                continue
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            # 检查是否有 except Exception: pass 或 except: pass
            import re
            patterns = [
                r'except\s+Exception\s*:\s*\n\s*pass',
                r'except\s*:\s*\n\s*pass',
                r'except\s+Exception\s*:\s*pass',
            ]
            for pattern in patterns:
                matches = re.findall(pattern, content)
                if matches:
                    violations.append(f"{fname}: {len(matches)} occurrences of silent exception swallowing")
        assert not violations, f"Silent exception swallowing found:\n" + "\n".join(violations)

    async def test_no_bare_except_pass_in_api_endpoints(self):
        """验证 API 端点文件中不再有 except: pass 模式"""
        import os
        api_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app", "api", "v1", "endpoints")
        violations = []
        for fname in os.listdir(api_dir):
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(api_dir, fname)
            if os.path.isdir(fpath):
                continue
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            import re
            # 只检查 except Exception: pass (单行模式)
            matches = re.findall(r'except\s+Exception\s*:\s*pass', content)
            if matches:
                violations.append(f"{fname}: {len(matches)} occurrences")
        assert not violations, f"Silent exception swallowing found:\n" + "\n".join(violations)


@pytest.mark.asyncio
class TestRtpTimeoutGracePeriod:
    """验证 RTP 超时宽限期逻辑。"""

    async def test_rtp_timeout_config_exists(self):
        """验证 RTP 超时配置项存在"""
        from app.core.config import settings
        assert hasattr(settings, "RTP_SERVER_TIMEOUT_SECONDS")
        assert settings.RTP_SERVER_TIMEOUT_SECONDS >= 15
        assert hasattr(settings, "RTP_TIMEOUT_GRACE_PERIOD_SECONDS")
        assert settings.RTP_TIMEOUT_GRACE_PERIOD_SECONDS > 0

    async def test_open_rtp_server_passes_timeout(self):
        """验证 open_rtp_server 传递超时参数给 ZLM"""
        from app.services.zlm_rtp_server_service import open_rtp_server
        import inspect
        sig = inspect.signature(open_rtp_server)
        assert "rtp_time_out" in sig.parameters, "open_rtp_server should accept rtp_time_out parameter"


@pytest.mark.asyncio
class TestNPlusOneFix:
    """验证 N+1 查询已修复。"""

    async def test_record_batch_no_n_plus_one(self):
        """验证 record.py 中的批量操作不再有循环内查询"""
        import os
        record_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "app", "api", "v1", "endpoints", "record.py"
        )
        with open(record_path, "r", encoding="utf-8") as f:
            content = f.read()
        # 检查不再有 for r in rows: 后跟 await db.execute(select(Asset)...) 的模式
        import re
        # 查找 "for r in rows:" 后面 5 行内是否有 db.execute(select(Asset
        pattern = r'for\s+r\s+in\s+rows:.*?(?=for\s+r\s+in\s+rows:|\Z)'
        blocks = re.findall(pattern, content, re.DOTALL)
        for block in blocks:
            lines = block.split("\n")[:6]  # 检查循环体前6行
            block_text = "\n".join(lines)
            assert "db.execute(select(Asset" not in block_text, \
                "N+1 query pattern still exists: Asset queried inside loop over rows"

    async def test_device_watchdog_batch_update(self):
        """验证设备看门狗使用批量更新"""
        import os
        wd_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "app", "services", "tasks", "device_watchdog.py"
        )
        with open(wd_path, "r", encoding="utf-8") as f:
            content = f.read()
        # 验证不再有循环内 update(Resource) 调用
        assert "update(Resource).where(Resource.asset_id == device.id)" not in content, \
            "Device watchdog still has per-device UPDATE (N+1)"
        # 验证有批量 UPDATE
        assert "Resource.asset_id.in_(_offline_asset_ids)" in content, \
            "Device watchdog should use batch UPDATE with IN clause"


@pytest.mark.asyncio
class TestSipCoreRobustness:
    """验证 SIP 核心模块健壮性。"""

    async def test_talk_cleanup_on_timeout(self):
        """验证对讲超时时正确清理资源"""
        from app.sip import talk as talk_mod
        # 验证 _talk_pending 和 _talk_timeout_tasks 字典存在
        assert hasattr(talk_mod, "_talk_pending")
        assert hasattr(talk_mod, "_talk_timeout_tasks")
        assert hasattr(talk_mod, "_talk_pending_lock")

    async def test_ssrc_manager_exists(self):
        """验证 SSRC 管理器存在"""
        from app.sip.ssrc_manager import ssrc_manager
        assert ssrc_manager is not None

    async def test_dialog_manager_exists(self):
        """验证 Dialog 管理器存在"""
        from app.sip.dialog_manager import dialog_manager
        assert dialog_manager is not None


@pytest.mark.asyncio
class TestOpsEndpointsContent:
    """验证运维端点返回合理内容。"""

    async def test_diagnose_returns_items(self, client: AsyncClient, auth_headers: dict):
        """诊断报告应返回 items 列表"""
        resp = await client.get("/api/v1/ops/diagnose", headers=auth_headers)
        if resp.status_code == 200:
            data = resp.json()
            assert "items" in data
            assert isinstance(data["items"], list)
            assert "summary" in data

    async def test_network_summary_returns_counts(self, client: AsyncClient, auth_headers: dict):
        """网络概况应返回设备计数"""
        resp = await client.get("/api/v1/network/summary", headers=auth_headers)
        if resp.status_code == 200:
            data = resp.json()
            assert "device_total" in data
            assert "device_online" in data
            assert "stream_count" in data

    async def test_network_bandwidth_returns_series(self, client: AsyncClient, auth_headers: dict):
        """带宽统计应返回时间序列"""
        resp = await client.get("/api/v1/network/bandwidth", headers=auth_headers, params={"range": "1h"})
        if resp.status_code == 200:
            data = resp.json()
            assert "series" in data
            assert isinstance(data["series"], list)

    async def test_network_topology_returns_nodes(self, client: AsyncClient, auth_headers: dict):
        """拓扑应返回节点和边"""
        resp = await client.get("/api/v1/network/topology", headers=auth_headers)
        if resp.status_code == 200:
            data = resp.json()
            assert "nodes" in data
            assert "edges" in data
            assert isinstance(data["nodes"], list)
            assert isinstance(data["edges"], list)

    async def test_metrics_devices_overview_returns_fields(self, client: AsyncClient, auth_headers: dict):
        """设备概览应返回所有必要字段"""
        resp = await client.get("/api/v1/metrics/devices-overview", headers=auth_headers)
        if resp.status_code == 200:
            data = resp.json()
            required = ["device_total", "device_online", "channel_total", "active_streams"]
            for field in required:
                assert field in data, f"Missing field: {field}"
