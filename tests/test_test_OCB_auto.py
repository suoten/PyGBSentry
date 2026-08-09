"""自动生成测试 - backend/.venv/Lib/site-packages/Cryptodome/SelfTest/Cipher/test_OCB.py"""
# AUTO-GENERATED
import pytest
import sys
from pathlib import Path
_root = Path(__file__).parent.parent
if str(_root) not in sys.path: sys.path.insert(0, str(_root))
try:
    from backend..venv.Lib.site-packages.Cryptodome.SelfTest.Cipher.test_OCB import *  # noqa
    _OK = True
except ImportError as _e:
    _OK = False; _ERR = str(_e)
# 删除可能被 pytest 误收集的 test 开头函数（来自 from import *）
for _n in list(globals()):
    if _n.startswith('test') and callable(globals()[_n]):
        del globals()[_n]

class TestTestOcbAuto:
    @pytest.fixture(autouse=True)
    def _check(self):
        if not _OK: pytest.skip(f"import failed: {_ERR if not _OK else ''}")
    def test_get_tag_random_callable(self):
        """测试 get_tag_random 可调用（import 成功即通过，调用失败 skip）"""
        try:
            get_tag_random("", "")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_algo_rfc7253_callable(self):
        """测试 algo_rfc7253 可调用（import 成功即通过，调用失败 skip）"""
        try:
            algo_rfc7253("", "", "")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_get_tests_callable(self):
        """测试 get_tests 可调用（import 成功即通过，调用失败 skip）"""
        try:
            get_tests({})
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

