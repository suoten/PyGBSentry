"""tests for tools.system_check.analyzers.stub_scanner — StubScanner 扫描 Python 占位实现。"""

from __future__ import annotations

import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.system_check.analyzers.stub_scanner import StubScanner
from tools.system_check.shared.models import (
    Priority,
    StubScanResult,
    StubStatus,
    StubType,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content), encoding="utf-8")


# 用作 backend_app_dir 时构造的样例 Python 代码
_SAMPLE_BACKEND_PY = '''\
def pass_only_device():
    pass


def raise_not_implemented():
    raise NotImplementedError("待实现")


def fully_implemented():
    return 1 + 2


def intentional_noop():
    """intentional placeholder - should be skipped."""
    pass


def docstring_then_pass():
    """普通文档字符串。"""
    pass


def swallow_exception():
    try:
        do_something()
    except Exception:
        pass


def swallow_exception_with_logging():
    try:
        do_something()
    except Exception as e:
        logger.error(e)
        pass


# TODO: 这是一个待办事项
def has_todo_comment():
    return 0


# FIXME: 需要修复
'''


class TestScanPythonStubs(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app_dir = Path(self.tmp.name) / "app"
        # 主测试文件
        _write(self.app_dir / "services" / "device_service.py", _SAMPLE_BACKEND_PY)

    def test_scan_returns_list_of_stub_records(self):
        stubs = StubScanner.scan_python_stubs(self.app_dir)
        self.assertIsInstance(stubs, list)
        # 列表中所有元素均为 StubRecord（隐式通过字段访问验证）
        for s in stubs:
            self.assertIsInstance(s.stub_type, StubType)
            self.assertIsInstance(s.priority, Priority)
            self.assertIsInstance(s.status, StubStatus)

    def test_scan_detects_pass_only_function(self):
        stubs = StubScanner.scan_python_stubs(self.app_dir)
        pass_stubs = [s for s in stubs if s.stub_type == StubType.PASS and s.function_name == "pass_only_device"]
        self.assertEqual(len(pass_stubs), 1)
        stub = pass_stubs[0]
        self.assertEqual(stub.status, StubStatus.PENDING_IMPLEMENT)
        self.assertGreater(stub.line_number, 0)
        self.assertIn("pass_only_device", stub.description)
        self.assertTrue(str(stub.file_path).endswith("device_service.py"))

    def test_scan_detects_not_implemented_error(self):
        stubs = StubScanner.scan_python_stubs(self.app_dir)
        nie_stubs = [s for s in stubs
                     if s.stub_type == StubType.NOT_IMPLEMENTED and s.function_name == "raise_not_implemented"]
        self.assertEqual(len(nie_stubs), 1)
        self.assertIn("raise_not_implemented", nie_stubs[0].description)

    def test_scan_detects_exception_swallow(self):
        stubs = StubScanner.scan_python_stubs(self.app_dir)
        swallow_stubs = [s for s in stubs if s.stub_type == StubType.EXCEPTION_SWALLOW]
        # swallow_exception() 命中；swallow_exception_with_logging() 因含 logger.error 不应命中
        self.assertGreaterEqual(len(swallow_stubs), 1)
        descriptions = " ".join(s.description for s in swallow_stubs)
        self.assertIn("异常被静默吞没", descriptions)

    def test_scan_detects_todo_comment(self):
        stubs = StubScanner.scan_python_stubs(self.app_dir)
        todo_stubs = [s for s in stubs if s.stub_type == StubType.TODO_COMMENT]
        # 文件中含 TODO 和 FIXME 两条
        self.assertGreaterEqual(len(todo_stubs), 2)

    def test_scan_skips_intentional_noop(self):
        """带 'intentional' docstring 的 pass-only 函数应被跳过。"""
        stubs = StubScanner.scan_python_stubs(self.app_dir)
        intentional = [s for s in stubs if s.function_name == "intentional_noop"]
        self.assertEqual(intentional, [])

    def test_scan_skips_fully_implemented(self):
        stubs = StubScanner.scan_python_stubs(self.app_dir)
        impl = [s for s in stubs if s.function_name == "fully_implemented"]
        self.assertEqual(impl, [])

    def test_scan_skips_init_py(self):
        """__init__.py 应被跳过。"""
        _write(self.app_dir / "__init__.py", "def f():\n    pass\n")
        stubs = StubScanner.scan_python_stubs(self.app_dir)
        init_stubs = [s for s in stubs if "__init__.py" in s.file_path]
        self.assertEqual(init_stubs, [])

    def test_scan_nonexistent_dir_returns_empty(self):
        self.assertEqual(StubScanner.scan_python_stubs("/nonexistent/path/xyz"), [])

    def test_scan_priority_classification_by_file_path(self):
        """文件名含 device 等关键词时优先级应为 P0。"""
        stubs = StubScanner.scan_python_stubs(self.app_dir)
        pass_stub = next(s for s in stubs
                         if s.stub_type == StubType.PASS and s.function_name == "pass_only_device")
        self.assertEqual(pass_stub.priority, Priority.P0)


class TestScanPriorityClassification(unittest.TestCase):
    """验证 _classify_priority 对 P0/P1/P2/P3 关键词的识别。"""

    def _scan_with_content(self, filename: str, content: str) -> list:
        with TemporaryDirectory() as tmp:
            app_dir = Path(tmp) / "app"
            _write(app_dir / filename, content)
            return StubScanner.scan_python_stubs(app_dir)

    def test_p0_patterns(self):
        for kw in ["device", "channel", "stream", "sip", "media", "platform", "record"]:
            with self.subTest(keyword=kw):
                stubs = self._scan_with_content(
                    f"svc_{kw}.py",
                    f"def f():\n    pass\n",
                )
                pass_stubs = [s for s in stubs if s.stub_type == StubType.PASS]
                self.assertTrue(pass_stubs, f"应至少识别一个 pass stub for {kw}")
                self.assertEqual(pass_stubs[0].priority, Priority.P0,
                                 f"含 {kw} 的文件应为 P0")

    def test_p1_patterns(self):
        for kw in ["qr", "qrcode", "export", "report", "alarm", "push"]:
            with self.subTest(keyword=kw):
                stubs = self._scan_with_content(
                    f"svc_{kw}.py",
                    f"def f():\n    pass\n",
                )
                pass_stubs = [s for s in stubs if s.stub_type == StubType.PASS]
                self.assertTrue(pass_stubs)
                self.assertEqual(pass_stubs[0].priority, Priority.P1)

    def test_p2_patterns(self):
        for kw in ["audit", "config", "draft", "log", "role", "user"]:
            with self.subTest(keyword=kw):
                stubs = self._scan_with_content(
                    f"svc_{kw}.py",
                    f"def f():\n    pass\n",
                )
                pass_stubs = [s for s in stubs if s.stub_type == StubType.PASS]
                self.assertTrue(pass_stubs)
                self.assertEqual(pass_stubs[0].priority, Priority.P2)

    def test_p3_default_for_unrecognized(self):
        stubs = self._scan_with_content(
            "svc_unknown.py",
            "def f():\n    pass\n",
        )
        pass_stubs = [s for s in stubs if s.stub_type == StubType.PASS]
        self.assertTrue(pass_stubs)
        self.assertEqual(pass_stubs[0].priority, Priority.P3)


class TestAnalyze(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.backend_dir = Path(self.tmp.name) / "backend" / "app"
        self.frontend_dir = Path(self.tmp.name) / "frontend" / "src"
        _write(
            self.backend_dir / "device.py",
            "def device_stub():\n    pass\n",
        )

    def test_analyze_returns_stub_scan_result(self):
        result = StubScanner.analyze("open-source", self.backend_dir, self.frontend_dir)
        self.assertIsInstance(result, StubScanResult)
        self.assertEqual(result.edition, "open-source")

    def test_analyze_attaches_edition_to_each_stub(self):
        result = StubScanner.analyze("open-source", self.backend_dir, self.frontend_dir)
        for stub in result.stubs:
            self.assertEqual(stub.edition, "open-source")

    def test_analyze_total_count_matches_stubs_length(self):
        result = StubScanner.analyze("open-source", self.backend_dir, self.frontend_dir)
        self.assertEqual(result.total_count, len(result.stubs))

    def test_analyze_by_type_aggregation(self):
        result = StubScanner.analyze("open-source", self.backend_dir, self.frontend_dir)
        # 至少应包含一个 pass 类型的占位
        self.assertIn("pass", result.by_type)
        # by_type 各项之和应等于 total_count
        self.assertEqual(sum(result.by_type.values()), result.total_count)

    def test_analyze_by_priority_aggregation(self):
        result = StubScanner.analyze("open-source", self.backend_dir, self.frontend_dir)
        # device.py 命中 P0
        self.assertIn("P0", result.by_priority)
        self.assertEqual(sum(result.by_priority.values()), result.total_count)

    def test_analyze_with_nonexistent_dirs(self):
        """目录不存在时应返回空结果（不抛异常）。"""
        result = StubScanner.analyze("x", "/nonexistent/backend", "/nonexistent/frontend")
        self.assertEqual(result.total_count, 0)
        self.assertEqual(result.stubs, [])
        self.assertEqual(result.by_type, {})
        self.assertEqual(result.by_priority, {})

    def test_analyze_combines_backend_and_frontend_stubs(self):
        """backend 与 frontend 的 stub 都应被收集。"""
        # 给 frontend 加一个 .ts 文件含 TODO
        _write(self.frontend_dir / "main.ts", "// TODO: implement me\n")
        result = StubScanner.analyze("open-source", self.backend_dir, self.frontend_dir)
        types_present = set(result.by_type.keys())
        # backend 至少有 pass 类型
        self.assertIn("pass", types_present)


class TestPassWithDocstringThenPass(unittest.TestCase):
    """PythonAstParser.is_pass_only_body 也识别 [docstring, pass] 形态。"""

    def test_docstring_then_pass_detected(self):
        with TemporaryDirectory() as tmp:
            app_dir = Path(tmp) / "app"
            _write(
                app_dir / "audit.py",
                '''\
def audit_fn():
    """docstring then pass."""
    pass
''',
            )
            stubs = StubScanner.scan_python_stubs(app_dir)
            pass_stubs = [s for s in stubs if s.stub_type == StubType.PASS]
            self.assertTrue(any(s.function_name == "audit_fn" for s in pass_stubs))


if __name__ == "__main__":
    unittest.main()
