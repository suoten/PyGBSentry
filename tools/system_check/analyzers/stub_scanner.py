from __future__ import annotations

import re
from pathlib import Path

from tools.system_check.parsers.python_ast_parser import PythonAstParser
from tools.system_check.parsers.vue_sfc_parser import VueSfcParser
from tools.system_check.shared.models import (
    Priority,
    StubRecord,
    StubScanResult,
    StubStatus,
    StubType,
)


class StubScanner:
    _TODO_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b", re.IGNORECASE)
    _MOCK_DATA_RE = re.compile(r"mock|Mock|fake|Fake|dummy|Dummy", re.IGNORECASE)

    _P0_PATTERNS = ["device", "channel", "stream", "sip", "media", "platform", "record"]
    _P1_PATTERNS = ["qr", "qrcode", "export", "report", "alarm", "push"]
    _P2_PATTERNS = ["audit", "config", "draft", "log", "role", "user"]
    _P3_PATTERNS = ["doc", "help", "about", "changelog", "demo"]

    @classmethod
    def scan_python_stubs(cls, app_dir: str | Path) -> list[StubRecord]:
        dir_path = Path(app_dir)
        if not dir_path.exists():
            return []

        stubs: list[StubRecord] = []
        for py_file in dir_path.rglob("*.py"):
            if py_file.name == "__init__.py":
                continue
            if "__pycache__" in str(py_file) or "site-packages" in str(py_file):
                continue
            stubs.extend(cls._scan_python_file(py_file))

        return stubs

    @classmethod
    def _scan_python_file(cls, file_path: Path) -> list[StubRecord]:
        tree = PythonAstParser.parse_file(str(file_path))
        if tree is None:
            return []

        source_lines = PythonAstParser.get_source_lines(str(file_path))
        stubs: list[StubRecord] = []
        rel_path = str(file_path)

        for func in PythonAstParser.find_all_functions(tree):
            if PythonAstParser.has_intentional_noop_comment(func):
                continue

            if PythonAstParser.is_pass_only_body(func):
                stubs.append(StubRecord(
                    stub_type=StubType.PASS,
                    priority=cls._classify_priority(rel_path, func.name),
                    status=StubStatus.PENDING_IMPLEMENT,
                    file_path=rel_path,
                    line_number=func.lineno,
                    description=f"函数 {func.name} 仅有pass占位",
                    function_name=func.name,
                ))

            if PythonAstParser.is_not_implemented_error(func):
                stubs.append(StubRecord(
                    stub_type=StubType.NOT_IMPLEMENTED,
                    priority=cls._classify_priority(rel_path, func.name),
                    status=StubStatus.PENDING_IMPLEMENT,
                    file_path=rel_path,
                    line_number=func.lineno,
                    description=f"函数 {func.name} 抛出NotImplementedError",
                    function_name=func.name,
                ))

        for handler in PythonAstParser.find_exception_handlers(tree):
            if PythonAstParser.is_exception_swallow(handler):
                stubs.append(StubRecord(
                    stub_type=StubType.EXCEPTION_SWALLOW,
                    priority=cls._classify_priority(rel_path, ""),
                    status=StubStatus.PENDING_IMPLEMENT,
                    file_path=rel_path,
                    line_number=handler.lineno if hasattr(handler, "lineno") else 0,
                    description="异常被静默吞没 (except ...: pass)",
                ))

        for i, line in enumerate(source_lines):
            if cls._TODO_RE.search(line):
                stubs.append(StubRecord(
                    stub_type=StubType.TODO_COMMENT,
                    priority=cls._classify_priority(rel_path, ""),
                    status=StubStatus.PENDING_IMPLEMENT,
                    file_path=rel_path,
                    line_number=i + 1,
                    description=f"TODO/FIXME注释: {line.strip()[:80]}",
                ))

        return stubs

    @classmethod
    def scan_frontend_stubs(cls, src_dir: str | Path) -> list[StubRecord]:
        dir_path = Path(src_dir)
        if not dir_path.exists():
            return []

        stubs: list[StubRecord] = []

        for vue_file in dir_path.rglob("*.vue"):
            parsed = VueSfcParser.parse_file(vue_file)
            if not parsed:
                continue

            rel_path = str(vue_file)

            for placeholder in parsed.get("placeholders", []):
                stubs.append(StubRecord(
                    stub_type=StubType.PLACEHOLDER_TEXT,
                    priority=cls._classify_priority(rel_path, ""),
                    status=StubStatus.PENDING_IMPLEMENT,
                    file_path=rel_path,
                    line_number=placeholder.get("line", 0),
                    description=f"占位文本: {placeholder.get('text', '')}",
                ))

            if parsed.get("is_empty_component", False):
                stubs.append(StubRecord(
                    stub_type=StubType.EMPTY_COMPONENT,
                    priority=cls._classify_priority(rel_path, ""),
                    status=StubStatus.PENDING_IMPLEMENT,
                    file_path=rel_path,
                    line_number=1,
                    description=f"空Vue组件: {vue_file.name}",
                ))

        for ts_file in dir_path.rglob("*.ts"):
            if ts_file.name.endswith(".d.ts"):
                continue
            try:
                content = ts_file.read_text(encoding="utf-8", errors="replace")
                for i, line in enumerate(content.splitlines()):
                    if cls._TODO_RE.search(line):
                        stubs.append(StubRecord(
                            stub_type=StubType.TODO_COMMENT,
                            priority=cls._classify_priority(str(ts_file), ""),
                            status=StubStatus.PENDING_IMPLEMENT,
                            file_path=str(ts_file),
                            line_number=i + 1,
                            description=f"TODO/FIXME注释: {line.strip()[:80]}",
                        ))
                    if cls._MOCK_DATA_RE.search(line) and "import" not in line:
                        pass
            except OSError:
                continue

        return stubs

    @classmethod
    def analyze(cls, edition: str, backend_app_dir: str | Path, frontend_src_dir: str | Path) -> StubScanResult:
        backend_stubs = cls.scan_python_stubs(backend_app_dir)
        frontend_stubs = cls.scan_frontend_stubs(frontend_src_dir)

        all_stubs = backend_stubs + frontend_stubs
        for stub in all_stubs:
            stub.edition = edition

        by_type: dict[str, int] = {}
        by_priority: dict[str, int] = {}
        for stub in all_stubs:
            by_type[stub.stub_type.value] = by_type.get(stub.stub_type.value, 0) + 1
            by_priority[stub.priority.value] = by_priority.get(stub.priority.value, 0) + 1

        return StubScanResult(
            edition=edition,
            stubs=all_stubs,
            total_count=len(all_stubs),
            by_type=by_type,
            by_priority=by_priority,
        )

    @classmethod
    def _classify_priority(cls, file_path: str, func_name: str) -> Priority:
        combined = (file_path + "/" + func_name).lower()
        for pattern in cls._P0_PATTERNS:
            if pattern in combined:
                return Priority.P0
        for pattern in cls._P1_PATTERNS:
            if pattern in combined:
                return Priority.P1
        for pattern in cls._P2_PATTERNS:
            if pattern in combined:
                return Priority.P2
        return Priority.P3
