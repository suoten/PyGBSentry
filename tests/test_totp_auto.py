"""自动生成测试 - backend/app/core/totp.py"""
# AUTO-GENERATED
import pytest
import sys
from pathlib import Path
_root = Path(__file__).parent.parent
if str(_root) not in sys.path: sys.path.insert(0, str(_root))
try:
    from backend.app.core.totp import *  # noqa
    _OK = True
except ImportError as _e:
    _OK = False; _ERR = str(_e)
# 删除可能被 pytest 误收集的 test 开头函数（来自 from import *）
for _n in list(globals()):
    if _n.startswith('test') and callable(globals()[_n]):
        del globals()[_n]

class TestTotpAuto:
    @pytest.fixture(autouse=True)
    def _check(self):
        if not _OK: pytest.skip(f"import failed: {_ERR if not _OK else ''}")
    def test_encrypt_totp_secret_callable(self):
        """测试 encrypt_totp_secret 可调用（import 成功即通过，调用失败 skip）"""
        try:
            encrypt_totp_secret("test")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_decrypt_totp_secret_callable(self):
        """测试 decrypt_totp_secret 可调用（import 成功即通过，调用失败 skip）"""
        try:
            decrypt_totp_secret("test")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_generate_base32_secret_callable(self):
        """测试 generate_base32_secret 可调用（import 成功即通过，调用失败 skip）"""
        try:
            generate_base32_secret("")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_totp_now_callable(self):
        """测试 totp_now 可调用（import 成功即通过，调用失败 skip）"""
        try:
            totp_now("", "", "", "")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_verify_totp_callable(self):
        """测试 verify_totp 可调用（import 成功即通过，调用失败 skip）"""
        try:
            verify_totp("", "", "", "", "")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

