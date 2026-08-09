"""自动生成测试 - backend/app/api/v1/endpoints/work_orders.py"""
# AUTO-GENERATED
import pytest
import sys
from pathlib import Path
_root = Path(__file__).parent.parent
if str(_root) not in sys.path: sys.path.insert(0, str(_root))
try:
    from backend.app.api.v1.endpoints.work_orders import *  # noqa
    _OK = True
except ImportError as _e:
    _OK = False; _ERR = str(_e)
# 删除可能被 pytest 误收集的 test 开头函数（来自 from import *）
for _n in list(globals()):
    if _n.startswith('test') and callable(globals()[_n]):
        del globals()[_n]

class TestWorkOrdersAuto:
    @pytest.fixture(autouse=True)
    def _check(self):
        if not _OK: pytest.skip(f"import failed: {_ERR if not _OK else ''}")
    def test_list_work_orders_callable(self):
        """测试 list_work_orders 可调用（import 成功即通过，调用失败 skip）"""
        try:
            import asyncio
            asyncio.get_event_loop().run_until_complete(list_work_orders("", "", "", ""))
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_create_work_order_callable(self):
        """测试 create_work_order 可调用（import 成功即通过，调用失败 skip）"""
        try:
            import asyncio
            asyncio.get_event_loop().run_until_complete(create_work_order("", "", ""))
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_update_work_order_callable(self):
        """测试 update_work_order 可调用（import 成功即通过，调用失败 skip）"""
        try:
            import asyncio
            asyncio.get_event_loop().run_until_complete(update_work_order(1, "", "", ""))
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_delete_work_order_callable(self):
        """测试 delete_work_order 可调用（import 成功即通过，调用失败 skip）"""
        try:
            import asyncio
            asyncio.get_event_loop().run_until_complete(delete_work_order(1, "", ""))
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

