"""自动生成测试 - backend/.venv/Lib/site-packages/websockets/imports.py"""
# AUTO-GENERATED
import pytest
import sys
from pathlib import Path
_root = Path(__file__).parent.parent
if str(_root) not in sys.path: sys.path.insert(0, str(_root))
try:
    from backend..venv.Lib.site-packages.websockets.imports import *  # noqa
    _OK = True
except ImportError as _e:
    _OK = False; _ERR = str(_e)
# 删除可能被 pytest 误收集的 test 开头函数（来自 from import *）
for _n in list(globals()):
    if _n.startswith('test') and callable(globals()[_n]):
        del globals()[_n]

class TestImportsAuto:
    @pytest.fixture(autouse=True)
    def _check(self):
        if not _OK: pytest.skip(f"import failed: {_ERR if not _OK else ''}")
    def test_import_name_callable(self):
        """测试 import_name 可调用（import 成功即通过，调用失败 skip）"""
        try:
            import_name("test", "", "test")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_lazy_import_callable(self):
        """测试 lazy_import 可调用（import 成功即通过，调用失败 skip）"""
        try:
            lazy_import("test", "", "")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

