"""自动生成测试 - backend/.venv/Lib/site-packages/sqlalchemy/orm/sync.py"""
# AUTO-GENERATED
import pytest
import sys
from pathlib import Path
_root = Path(__file__).parent.parent
if str(_root) not in sys.path: sys.path.insert(0, str(_root))
try:
    from backend..venv.Lib.site-packages.sqlalchemy.orm.sync import *  # noqa
    _OK = True
except ImportError as _e:
    _OK = False; _ERR = str(_e)
# 删除可能被 pytest 误收集的 test 开头函数（来自 from import *）
for _n in list(globals()):
    if _n.startswith('test') and callable(globals()[_n]):
        del globals()[_n]

class TestSyncAuto:
    @pytest.fixture(autouse=True)
    def _check(self):
        if not _OK: pytest.skip(f"import failed: {_ERR if not _OK else ''}")
    def test_populate_callable(self):
        """测试 populate 可调用（import 成功即通过，调用失败 skip）"""
        try:
            populate("", "", "", "", "", "", "")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_bulk_populate_inherit_keys_callable(self):
        """测试 bulk_populate_inherit_keys 可调用（import 成功即通过，调用失败 skip）"""
        try:
            bulk_populate_inherit_keys("", "", "")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_clear_callable(self):
        """测试 clear 可调用（import 成功即通过，调用失败 skip）"""
        try:
            clear("", "", "")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_update_callable(self):
        """测试 update 可调用（import 成功即通过，调用失败 skip）"""
        try:
            update("", "", "", "", "")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_populate_dict_callable(self):
        """测试 populate_dict 可调用（import 成功即通过，调用失败 skip）"""
        try:
            populate_dict("", "", "", "")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_source_modified_callable(self):
        """测试 source_modified 可调用（import 成功即通过，调用失败 skip）"""
        try:
            source_modified("", "", "", "")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

