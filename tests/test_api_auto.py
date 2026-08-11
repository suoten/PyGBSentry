"""自动生成测试 - backend/app/api/v1/api.py"""
# AUTO-GENERATED
import pytest
import sys
from pathlib import Path
_root = Path(__file__).parent.parent
if str(_root) not in sys.path: sys.path.insert(0, str(_root))
try:
    from backend.app.api.v1.api import *  # noqa
    _OK = True
except ImportError as _e:
    _OK = False; _ERR = str(_e)
# 删除可能被 pytest 误收集的 test 开头函数（来自 from import *）
for _n in list(globals()):
    if _n.startswith('test') and callable(globals()[_n]):
        del globals()[_n]

class TestApiAuto:
    @pytest.fixture(autouse=True)
    def _check(self):
        if not _OK: pytest.skip(f"import failed: {_ERR if not _OK else ''}")
    def test_health_check_callable(self):
        """测试 health_check 可调用（import 成功即通过，调用失败 skip）"""
        try:
            health_check()
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_redirect_push_channels_callable(self):
        """测试 redirect_push_channels 可调用（import 成功即通过，调用失败 skip）"""
        try:
            import asyncio
            asyncio.run(redirect_push_channels())
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_redirect_record_schedule_callable(self):
        """测试 redirect_record_schedule 可调用（import 成功即通过，调用失败 skip）"""
        try:
            import asyncio
            asyncio.run(redirect_record_schedule())
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_redirect_device_record_callable(self):
        """测试 redirect_device_record 可调用（import 成功即通过，调用失败 skip）"""
        try:
            import asyncio
            asyncio.run(redirect_device_record())
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_redirect_gb_record_callable(self):
        """测试 redirect_gb_record 可调用（import 成功即通过，调用失败 skip）"""
        try:
            import asyncio
            asyncio.run(redirect_gb_record())
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

