from __future__ import annotations

import ast
import re
from pathlib import Path

from tools.system_check.parsers.python_ast_parser import PythonAstParser
from tools.system_check.parsers.vue_sfc_parser import VueSfcParser
from tools.system_check.shared.models import (
    IssueCategory,
    QualityIssue,
    RobustnessResult,
    Severity,
)


class RobustnessAnalyzer:
    _EXCEPT_PASS_RE = re.compile(r"except\s+.*?:\s*pass\s*$", re.MULTILINE)
    _BARE_EXCEPT_PASS_RE = re.compile(r"except:\s*pass\s*$", re.MULTILINE)
    _LOGGER_CALL_RE = re.compile(r"logger\.\w+\(|log\.\w+\(", re.IGNORECASE)
    _PYDANTIC_MODEL_RE = re.compile(r"(?:BaseModel|Schema)\b")
    _EXTERNAL_DEPS = {"redis", "Redis", "aioredis", "ZLM", "zlm", "sip", "SIP", "httpx", "aiohttp", "kafka", "pika"}
    _GLOBAL_HANDLER_RE = re.compile(r"@app\.exception_handler|@exception_handler", re.IGNORECASE)
    _STACK_TRACE_RE = re.compile(r"traceback|exc_info|format_exc|print_exc", re.IGNORECASE)

    @classmethod
    def analyze(cls, edition: str, backend_app_dir: str | Path, frontend_src_dir: str | Path) -> RobustnessResult:
        dir_path = Path(backend_app_dir)
        src_path = Path(frontend_src_dir)

        issues: list[QualityIssue] = []
        issues.extend(cls._check_exception_handling(dir_path, edition))
        issues.extend(cls._check_pydantic_coverage(dir_path, edition))
        issues.extend(cls._check_external_dependency_handling(dir_path, edition))
        issues.extend(cls._check_exception_swallow_deep(dir_path, edition))
        issues.extend(cls._check_global_exception_handler(dir_path, edition))
        issues.extend(cls._check_frontend_error_boundary(src_path, edition))

        by_category: dict[str, int] = {}
        for issue in issues:
            by_category[issue.category.value] = by_category.get(issue.category.value, 0) + 1

        return RobustnessResult(
            edition=edition,
            issues=issues,
            total_count=len(issues),
            by_category=by_category,
        )

    @classmethod
    def _check_exception_handling(cls, app_dir: Path, edition: str) -> list[QualityIssue]:
        issues: list[QualityIssue] = []
        for py_file in app_dir.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            for match in cls._EXCEPT_PASS_RE.finditer(content):
                line_num = content[:match.start()].count("\n") + 1
                surrounding = content[max(0, match.start() - 200):match.end() + 200]
                if not cls._LOGGER_CALL_RE.search(surrounding):
                    issues.append(QualityIssue(
                        category=IssueCategory.EXCEPTION_SWALLOW,
                        severity=Severity.HIGH,
                        file_path=str(py_file),
                        line_number=line_num,
                        description=f"异常被静默吞没: {match.group().strip()[:60]}",
                        current_behavior="异常被静默吞没",
                        expected_behavior="至少记录WARNING日志或向上传播",
                        edition=edition,
                    ))

            for match in cls._BARE_EXCEPT_PASS_RE.finditer(content):
                line_num = content[:match.start()].count("\n") + 1
                issues.append(QualityIssue(
                    category=IssueCategory.EXCEPTION_SWALLOW,
                    severity=Severity.HIGH,
                    file_path=str(py_file),
                    line_number=line_num,
                    description=f"裸except:pass: {match.group().strip()[:60]}",
                    current_behavior="裸异常捕获并吞没",
                    expected_behavior="至少记录WARNING日志，使用具体异常类型",
                    edition=edition,
                ))

        return issues

    @classmethod
    def _check_pydantic_coverage(cls, app_dir: Path, edition: str) -> list[QualityIssue]:
        issues: list[QualityIssue] = []
        endpoints_dir = app_dir / "api" / "v1" / "endpoints"
        if not endpoints_dir.exists():
            return issues

        for py_file in endpoints_dir.rglob("*.py"):
            tree = PythonAstParser.parse_file(str(py_file))
            if tree is None:
                continue

            for func in PythonAstParser.find_decorated_functions(tree, {"get", "post", "put", "delete", "patch"}):
                has_body_param = False
                for arg in func.args.args:
                    if arg.arg in ("self", "cls", "request", "response", "db", "current_user", "user", "deps"):
                        continue
                    if arg.annotation:
                        ann_str = ast_dump_safe(arg.annotation)
                        if any(kw in ann_str for kw in ("Body", "BaseModel", "Schema", "Create", "Update", "Form")):
                            has_body_param = True
                            break

                if not has_body_param and func.args.args:
                    non_trivial = [a for a in func.args.args if a.arg not in ("self", "cls", "request", "response", "db", "current_user", "user", "deps")]
                    if non_trivial:
                        pass

        return issues

    @classmethod
    def _check_external_dependency_handling(cls, app_dir: Path, edition: str) -> list[QualityIssue]:
        issues: list[QualityIssue] = []
        for py_file in app_dir.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            lines = content.splitlines()
            for i, line in enumerate(lines):
                for dep in cls._EXTERNAL_DEPS:
                    if dep in line and "import" in line:
                        has_try = False
                        for j in range(max(0, i - 5), min(len(lines), i + 20)):
                            if "try:" in lines[j]:
                                has_try = True
                                break
                        if not has_try:
                            pass
                        break

        return issues

    @classmethod
    def _check_exception_swallow_deep(cls, app_dir: Path, edition: str) -> list[QualityIssue]:
        issues: list[QualityIssue] = []
        for py_file in app_dir.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            tree = PythonAstParser.parse_file(str(py_file))
            if tree is None:
                continue

            for handler in PythonAstParser.find_exception_handlers(tree):
                if PythonAstParser.is_exception_swallow(handler):
                    has_raise = any(
                        isinstance(stmt, ast.Raise)
                        for stmt in ast.walk(handler)
                        if isinstance(stmt, ast.Raise)
                    )
                    has_return = any(
                        isinstance(stmt, ast.Return)
                        for stmt in handler.body
                    )
                    if not has_raise and not has_return:
                        source_lines = PythonAstParser.get_source_lines(str(py_file))
                        issues.append(QualityIssue(
                            category=IssueCategory.EXCEPTION_SWALLOW,
                            severity=Severity.HIGH,
                            file_path=str(py_file),
                            line_number=handler.lineno if hasattr(handler, "lineno") else 0,
                            description="except:pass 且无raise/return，异常完全吞没",
                            current_behavior="异常被静默吞没，无日志无传播",
                            expected_behavior="至少记录WARNING日志或向上传播",
                            edition=edition,
                        ))

        return issues

    @classmethod
    def _check_global_exception_handler(cls, app_dir: Path, edition: str) -> list[QualityIssue]:
        issues: list[QualityIssue] = []
        main_file = app_dir / "main.py"
        if main_file.exists():
            try:
                content = main_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return issues

            if not cls._GLOBAL_HANDLER_RE.search(content):
                issues.append(QualityIssue(
                    category=IssueCategory.NO_GLOBAL_HANDLER,
                    severity=Severity.HIGH,
                    file_path=str(main_file),
                    line_number=1,
                    description="缺少全局异常处理器 (@app.exception_handler)",
                    current_behavior="未捕获的异常返回原始堆栈跟踪",
                    expected_behavior="全局异常处理器返回友好错误信息",
                    suggestion="添加 @app.exception_handler(Exception) 返回 {\"detail\": \"内部服务错误\"}",
                    edition=edition,
                ))

            if cls._STACK_TRACE_RE.search(content) and "logger" in content:
                pass

        return issues

    @classmethod
    def _check_frontend_error_boundary(cls, src_dir: Path, edition: str) -> list[QualityIssue]:
        issues: list[QualityIssue] = []
        if not src_dir.exists():
            return issues

        for vue_file in src_dir.rglob("*.vue"):
            parsed = VueSfcParser.parse_file(vue_file)
            if not parsed:
                continue

            for api_call in parsed.get("api_calls", []):
                script = parsed.get("script", "")
                has_catch = "catch" in script or ".catch" in script or "try" in script
                has_then_error = "ElMessage.error" in script or "errorMessage" in script

                if not has_catch and not has_then_error:
                    issues.append(QualityIssue(
                        category=IssueCategory.NO_ERROR_BOUNDARY,
                        severity=Severity.MEDIUM,
                        file_path=str(vue_file),
                        line_number=1,
                        description=f"API调用 {api_call['method']} {api_call['path']} 无错误处理",
                        current_behavior="API调用失败时无用户反馈",
                        expected_behavior="添加.catch或try-catch错误处理",
                        edition=edition,
                    ))

        return issues


def ast_dump_safe(node) -> str:
    try:
        import ast
        return ast.dump(node)
    except Exception:
        return ""
