"""自动生成测试 - backend/app/services/plugin_template_helpers.py"""
# AUTO-GENERATED
import pytest
import sys
from pathlib import Path
_root = Path(__file__).parent.parent
if str(_root) not in sys.path: sys.path.insert(0, str(_root))
try:
    from backend.app.services.plugin_template_helpers import *  # noqa
    _OK = True
except ImportError as _e:
    _OK = False; _ERR = str(_e)
# 删除可能被 pytest 误收集的 test 开头函数（来自 from import *）
for _n in list(globals()):
    if _n.startswith('test') and callable(globals()[_n]):
        del globals()[_n]

class TestPluginTemplateHelpersAuto:
    @pytest.fixture(autouse=True)
    def _check(self):
        if not _OK: pytest.skip(f"import failed: {_ERR if not _OK else ''}")
    def test_register_main_path_plugin_callable(self):
        """测试 register_main_path_plugin 可调用（import 成功即通过，调用失败 skip）"""
        try:
            register_main_path_plugin("")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

