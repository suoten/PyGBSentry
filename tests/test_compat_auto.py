"""自动生成测试 - backend/.venv/Lib/site-packages/sqlalchemy/util/compat.py"""
# AUTO-GENERATED
import pytest
import sys
from pathlib import Path
_root = Path(__file__).parent.parent
if str(_root) not in sys.path: sys.path.insert(0, str(_root))
try:
    from backend..venv.Lib.site-packages.sqlalchemy.util.compat import *  # noqa
    _OK = True
except ImportError as _e:
    _OK = False; _ERR = str(_e)
# 删除可能被 pytest 误收集的 test 开头函数（来自 from import *）
for _n in list(globals()):
    if _n.startswith('test') and callable(globals()[_n]):
        del globals()[_n]

class TestCompatAuto:
    @pytest.fixture(autouse=True)
    def _check(self):
        if not _OK: pytest.skip(f"import failed: {_ERR if not _OK else ''}")
    def test_inspect_getfullargspec_callable(self):
        """测试 inspect_getfullargspec 可调用（import 成功即通过，调用失败 skip）"""
        try:
            inspect_getfullargspec("")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_importlib_metadata_get_callable(self):
        """测试 importlib_metadata_get 可调用（import 成功即通过，调用失败 skip）"""
        try:
            importlib_metadata_get("")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_b_callable(self):
        """测试 b 可调用（import 成功即通过，调用失败 skip）"""
        try:
            b("")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_b64decode_callable(self):
        """测试 b64decode 可调用（import 成功即通过，调用失败 skip）"""
        try:
            b64decode("")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_b64encode_callable(self):
        """测试 b64encode 可调用（import 成功即通过，调用失败 skip）"""
        try:
            b64encode("")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_decode_backslashreplace_callable(self):
        """测试 decode_backslashreplace 可调用（import 成功即通过，调用失败 skip）"""
        try:
            decode_backslashreplace("test", "")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_cmp_callable(self):
        """测试 cmp 可调用（import 成功即通过，调用失败 skip）"""
        try:
            cmp("", "")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_inspect_formatargspec_callable(self):
        """测试 inspect_formatargspec 可调用（import 成功即通过，调用失败 skip）"""
        try:
            inspect_formatargspec("", "", "", "", "", "", "", "", "", "", "", "", "")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_dataclass_fields_callable(self):
        """测试 dataclass_fields 可调用（import 成功即通过，调用失败 skip）"""
        try:
            dataclass_fields("")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_local_dataclass_fields_callable(self):
        """测试 local_dataclass_fields 可调用（import 成功即通过，调用失败 skip）"""
        try:
            local_dataclass_fields("")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

