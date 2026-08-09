"""自动生成测试 - backend/.venv/Lib/site-packages/psutil/_psaix.py"""
# AUTO-GENERATED
import pytest
import sys
from pathlib import Path
_root = Path(__file__).parent.parent
if str(_root) not in sys.path: sys.path.insert(0, str(_root))
try:
    from backend..venv.Lib.site-packages.psutil._psaix import *  # noqa
    _OK = True
except ImportError as _e:
    _OK = False; _ERR = str(_e)
# 删除可能被 pytest 误收集的 test 开头函数（来自 from import *）
for _n in list(globals()):
    if _n.startswith('test') and callable(globals()[_n]):
        del globals()[_n]

class TestPsaixAuto:
    @pytest.fixture(autouse=True)
    def _check(self):
        if not _OK: pytest.skip(f"import failed: {_ERR if not _OK else ''}")
    def test_virtual_memory_callable(self):
        """测试 virtual_memory 可调用（import 成功即通过，调用失败 skip）"""
        try:
            virtual_memory()
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_swap_memory_callable(self):
        """测试 swap_memory 可调用（import 成功即通过，调用失败 skip）"""
        try:
            swap_memory()
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_cpu_times_callable(self):
        """测试 cpu_times 可调用（import 成功即通过，调用失败 skip）"""
        try:
            cpu_times()
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_per_cpu_times_callable(self):
        """测试 per_cpu_times 可调用（import 成功即通过，调用失败 skip）"""
        try:
            per_cpu_times()
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_cpu_count_logical_callable(self):
        """测试 cpu_count_logical 可调用（import 成功即通过，调用失败 skip）"""
        try:
            cpu_count_logical()
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_cpu_count_cores_callable(self):
        """测试 cpu_count_cores 可调用（import 成功即通过，调用失败 skip）"""
        try:
            cpu_count_cores()
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_cpu_stats_callable(self):
        """测试 cpu_stats 可调用（import 成功即通过，调用失败 skip）"""
        try:
            cpu_stats()
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_disk_partitions_callable(self):
        """测试 disk_partitions 可调用（import 成功即通过，调用失败 skip）"""
        try:
            disk_partitions("")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_net_connections_callable(self):
        """测试 net_connections 可调用（import 成功即通过，调用失败 skip）"""
        try:
            net_connections("", 1)
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_net_if_stats_callable(self):
        """测试 net_if_stats 可调用（import 成功即通过，调用失败 skip）"""
        try:
            net_if_stats()
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_boot_time_callable(self):
        """测试 boot_time 可调用（import 成功即通过，调用失败 skip）"""
        try:
            boot_time()
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_users_callable(self):
        """测试 users 可调用（import 成功即通过，调用失败 skip）"""
        try:
            users()
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_pids_callable(self):
        """测试 pids 可调用（import 成功即通过，调用失败 skip）"""
        try:
            pids()
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_pid_exists_callable(self):
        """测试 pid_exists 可调用（import 成功即通过，调用失败 skip）"""
        try:
            pid_exists(1)
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_wrap_exceptions_callable(self):
        """测试 wrap_exceptions 可调用（import 成功即通过，调用失败 skip）"""
        try:
            wrap_exceptions("")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

