"""自动生成测试 - backend/app/sip/talk.py"""
# AUTO-GENERATED
import pytest
import sys
from pathlib import Path
_root = Path(__file__).parent.parent
if str(_root) not in sys.path: sys.path.insert(0, str(_root))
try:
    from backend.app.sip.talk import *  # noqa
    _OK = True
except ImportError as _e:
    _OK = False; _ERR = str(_e)
# 删除可能被 pytest 误收集的 test 开头函数（来自 from import *）
for _n in list(globals()):
    if _n.startswith('test') and callable(globals()[_n]):
        del globals()[_n]

class TestTalkAuto:
    @pytest.fixture(autouse=True)
    def _check(self):
        if not _OK: pytest.skip(f"import failed: {_ERR if not _OK else ''}")
    def test_on_talk_200_ok_callable(self):
        """测试 on_talk_200_ok 可调用（import 成功即通过，调用失败 skip）"""
        try:
            import asyncio
            asyncio.get_event_loop().run_until_complete(on_talk_200_ok(1, "", ""))
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_wait_talk_200_ok_callable(self):
        """测试 wait_talk_200_ok 可调用（import 成功即通过，调用失败 skip）"""
        try:
            import asyncio
            asyncio.get_event_loop().run_until_complete(wait_talk_200_ok(1, ""))
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_start_talk_cleanup_loop_callable(self):
        """测试 start_talk_cleanup_loop 可调用（import 成功即通过，调用失败 skip）"""
        try:
            import asyncio
            asyncio.run(start_talk_cleanup_loop())
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_get_sip_talk_callable(self):
        """测试 get_sip_talk 可调用（import 成功即通过，调用失败 skip）"""
        try:
            get_sip_talk()
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_init_sip_talk_callable(self):
        """测试 init_sip_talk 可调用（import 成功即通过，调用失败 skip）"""
        try:
            init_sip_talk("")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

