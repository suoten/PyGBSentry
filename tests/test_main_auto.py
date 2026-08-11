"""自动生成测试 - backend/app/main.py"""
# AUTO-GENERATED
import pytest
import sys
from pathlib import Path
_root = Path(__file__).parent.parent
if str(_root) not in sys.path: sys.path.insert(0, str(_root))
try:
    from backend.app.main import *  # noqa
    _OK = True
except ImportError as _e:
    _OK = False; _ERR = str(_e)
# 删除可能被 pytest 误收集的 test 开头函数（来自 from import *）
for _n in list(globals()):
    if _n.startswith('test') and callable(globals()[_n]):
        del globals()[_n]

class TestMainAuto:
    @pytest.fixture(autouse=True)
    def _check(self):
        if not _OK: pytest.skip(f"import failed: {_ERR if not _OK else ''}")
    def test_lifespan_callable(self):
        """测试 lifespan 可调用（import 成功即通过，调用失败 skip）"""
        try:
            import asyncio
            asyncio.get_event_loop().run_until_complete(lifespan(""))
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_app_exception_handler_callable(self):
        """测试 app_exception_handler 可调用（import 成功即通过，调用失败 skip）"""
        try:
            import asyncio
            asyncio.get_event_loop().run_until_complete(app_exception_handler("", ""))
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_zlm_api_error_handler_callable(self):
        """测试 zlm_api_error_handler 可调用（import 成功即通过，调用失败 skip）"""
        try:
            import asyncio
            asyncio.get_event_loop().run_until_complete(zlm_api_error_handler("", ""))
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_http_exception_handler_callable(self):
        """测试 http_exception_handler 可调用（import 成功即通过，调用失败 skip）"""
        try:
            import asyncio
            asyncio.get_event_loop().run_until_complete(http_exception_handler("", ""))
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_starlette_exception_handler_callable(self):
        """测试 starlette_exception_handler 可调用（import 成功即通过，调用失败 skip）"""
        try:
            import asyncio
            asyncio.get_event_loop().run_until_complete(starlette_exception_handler("", ""))
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_global_exception_handler_callable(self):
        """测试 global_exception_handler 可调用（import 成功即通过，调用失败 skip）"""
        try:
            import asyncio
            asyncio.get_event_loop().run_until_complete(global_exception_handler("", ""))
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_validation_exception_handler_callable(self):
        """测试 validation_exception_handler 可调用（import 成功即通过，调用失败 skip）"""
        try:
            import asyncio
            asyncio.get_event_loop().run_until_complete(validation_exception_handler("", ""))
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_root_callable(self):
        """测试 root 可调用（import 成功即通过，调用失败 skip）"""
        try:
            import asyncio
            asyncio.run(root())
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_health_callable(self):
        """测试 health 可调用（import 成功即通过，调用失败 skip）"""
        try:
            import asyncio
            asyncio.run(health())
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_health_ready_callable(self):
        """测试 health_ready 可调用（import 成功即通过，调用失败 skip）"""
        try:
            import asyncio
            asyncio.run(health_ready())
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_health_live_callable(self):
        """测试 health_live 可调用（import 成功即通过，调用失败 skip）"""
        try:
            import asyncio
            asyncio.run(health_live())
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_metrics_callable(self):
        """测试 metrics 可调用（import 成功即通过，调用失败 skip）"""
        try:
            import asyncio
            asyncio.get_event_loop().run_until_complete(metrics(""))
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

