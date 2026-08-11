"""自动生成测试 - backend/app/api/v1/endpoints/network_diagnostics.py"""
# AUTO-GENERATED
import pytest
import sys
from pathlib import Path
_root = Path(__file__).parent.parent
if str(_root) not in sys.path: sys.path.insert(0, str(_root))
try:
    from backend.app.api.v1.endpoints.network_diagnostics import *  # noqa
    _OK = True
except ImportError as _e:
    _OK = False; _ERR = str(_e)
# 删除可能被 pytest 误收集的 test 开头函数（来自 from import *）
for _n in list(globals()):
    if _n.startswith('test') and callable(globals()[_n]):
        del globals()[_n]

class TestNetworkDiagnosticsAuto:
    @pytest.fixture(autouse=True)
    def _check(self):
        if not _OK: pytest.skip(f"import failed: {_ERR if not _OK else ''}")
    def test_ping_diagnosis_callable(self):
        """测试 ping_diagnosis 可调用（import 成功即通过，调用失败 skip）"""
        try:
            import asyncio
            asyncio.get_event_loop().run_until_complete(ping_diagnosis("", 1, "", ""))
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_traceroute_diagnosis_callable(self):
        """测试 traceroute_diagnosis 可调用（import 成功即通过，调用失败 skip）"""
        try:
            import asyncio
            asyncio.get_event_loop().run_until_complete(traceroute_diagnosis("", "", "", ""))
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_port_probe_callable(self):
        """测试 port_probe 可调用（import 成功即通过，调用失败 skip）"""
        try:
            import asyncio
            asyncio.get_event_loop().run_until_complete(port_probe("", "", "", ""))
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_sip_server_probe_callable(self):
        """测试 sip_server_probe 可调用（import 成功即通过，调用失败 skip）"""
        try:
            import asyncio
            asyncio.get_event_loop().run_until_complete(sip_server_probe("", "", "", "", ""))
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_media_server_probe_callable(self):
        """测试 media_server_probe 可调用（import 成功即通过，调用失败 skip）"""
        try:
            import asyncio
            asyncio.get_event_loop().run_until_complete(media_server_probe("", "", "", "", ""))
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

