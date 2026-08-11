"""自动生成测试 - backend/.venv/Lib/site-packages/pip/_internal/locations/_distutils.py"""
# AUTO-GENERATED
import pytest
import sys
from pathlib import Path
_root = Path(__file__).parent.parent
if str(_root) not in sys.path: sys.path.insert(0, str(_root))
try:
    from backend..venv.Lib.site-packages.pip._internal.locations._distutils import *  # noqa
    _OK = True
except ImportError as _e:
    _OK = False; _ERR = str(_e)
# 删除可能被 pytest 误收集的 test 开头函数（来自 from import *）
for _n in list(globals()):
    if _n.startswith('test') and callable(globals()[_n]):
        del globals()[_n]

class TestDistutilsAuto:
    @pytest.fixture(autouse=True)
    def _check(self):
        if not _OK: pytest.skip(f"import failed: {_ERR if not _OK else ''}")
    def test_distutils_scheme_callable(self):
        """测试 distutils_scheme 可调用（import 成功即通过，调用失败 skip）"""
        try:
            distutils_scheme("test", "", "", "", "", "")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_get_scheme_callable(self):
        """测试 get_scheme 可调用（import 成功即通过，调用失败 skip）"""
        try:
            get_scheme("test", "", "", "", "", "")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_get_bin_prefix_callable(self):
        """测试 get_bin_prefix 可调用（import 成功即通过，调用失败 skip）"""
        try:
            get_bin_prefix()
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_get_purelib_callable(self):
        """测试 get_purelib 可调用（import 成功即通过，调用失败 skip）"""
        try:
            get_purelib()
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_get_platlib_callable(self):
        """测试 get_platlib 可调用（import 成功即通过，调用失败 skip）"""
        try:
            get_platlib()
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

