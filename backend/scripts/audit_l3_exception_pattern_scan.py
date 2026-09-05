#!/usr/bin/env python3
"""
L3 自动化审计：异常处理模式扫描

检测以下反模式：
  1. `except Exception` 后 `return None` / `return []` / `return False` / `return 0` / `return {}`
     — 吞掉异常信息，应 raise 或 return Result 类型
  2. `except Exception: pass` — 空 except 块吞掉异常
  3. `except Exception` 后仅 `logger.warning/error` 但不 re-raise
     — 日志后应 raise 或返回明确错误响应
  4. 裸 `except:` (无异常类型) — 过宽捕获

使用方式：
  python scripts/audit_l3_exception_pattern_scan.py [--src-dir ...] [--severity error|warning|all]

退出码：
  0 — 通过（或仅 warning）
  1 — 发现 error 级别问题

环境变量：
  AUDIT_L3_ENABLED=true/false  — 是否启用（默认 true）
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

AUDIT_ENABLED = os.environ.get("AUDIT_L3_ENABLED", "true").lower() in {"true", "1", "yes"}


@dataclass
class Finding:
    file: str
    line: int
    col: int
    rule: str
    level: str
    message: str
    snippet: str = ""


_NON_CRITICAL_CONTEXT_PATTERNS = {
    "background", "cleanup", "notify", "drain", "health", "watchdog",
    "monitor", "heartbeat", "keepalive", "refresh", "cache", "metrics",
    "telemetry", "diagnostic", "probe", "poll", "schedule", "cron",
    "webhook", "callback", "event_handler", "on_", "graceful",
}

_NON_CRITICAL_LOG_PATTERNS = {
    "non-critical", "非关键", "optional", "best-effort", "fire-and-forget",
    "fallback", "降级", "兜底", "忽略", "skip", "tolerate",
}


def _is_non_critical_context(source: str, node: ast.ExceptHandler) -> bool:
    start_line = max(1, node.lineno - 5)
    end_line = min(len(source.split('\n')), node.end_lineno or node.lineno + 5)
    lines = source.split('\n')
    context_lines = lines[start_line-1:end_line]
    context_text = '\n'.join(context_lines).lower()
    if any(kw in context_text for kw in _NON_CRITICAL_LOG_PATTERNS):
        return True
    if any(kw in context_text for kw in ("fallback", "降级", "兜底")):
        return True
    for line in context_lines:
        stripped = line.strip()
        if stripped.startswith("async def ") or stripped.startswith("def "):
            func_name = stripped.split("(")[0].split()[-1].lower()
            if any(p in func_name for p in _NON_CRITICAL_CONTEXT_PATTERNS):
                return True
    return False


_BARE_RETURN_VALUES = {
    ast.Constant: lambda n: n.value in (None, False, 0, [], {}, ""),
    ast.List: lambda n: len(n.elts) == 0,
    ast.Dict: lambda n: len(n.keys) == 0,
    ast.Tuple: lambda n: len(n.elts) == 0,
    ast.Set: lambda n: len(n.elts) == 0,
}


def _is_bare_return_value(node: ast.expr) -> bool:
    for typ, check in _BARE_RETURN_VALUES.items():
        if isinstance(node, typ):
            try:
                return check(node)
            except Exception:
                return False
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return _is_bare_return_value(node.operand)
    return False


def _has_raise_in_body(body: list[ast.stmt]) -> bool:
    for stmt in body:
        if isinstance(stmt, ast.Raise):
            return True
        if isinstance(stmt, (ast.If, ast.For, ast.While, ast.With, ast.Try)):
            inner = []
            if isinstance(stmt, ast.If):
                inner = stmt.body + (stmt.orelse or [])
            elif isinstance(stmt, (ast.For, ast.While)):
                inner = stmt.body + (stmt.orelse or [])
            elif isinstance(stmt, ast.With):
                inner = stmt.body
            elif isinstance(stmt, ast.Try):
                inner = stmt.body + stmt.orelse
                for handler in stmt.handlers:
                    inner.extend(handler.body)
                inner.extend(stmt.finalbody)
            if _has_raise_in_body(inner):
                return True
    return False


def _has_return_in_body(body: list[ast.stmt]) -> bool:
    for stmt in body:
        if isinstance(stmt, ast.Return):
            return True
        if isinstance(stmt, (ast.If, ast.For, ast.While, ast.With, ast.Try)):
            inner = []
            if isinstance(stmt, ast.If):
                inner = stmt.body + (stmt.orelse or [])
            elif isinstance(stmt, (ast.For, ast.While)):
                inner = stmt.body + (stmt.orelse or [])
            elif isinstance(stmt, ast.With):
                inner = stmt.body
            elif isinstance(stmt, ast.Try):
                inner = stmt.body + stmt.orelse
                for handler in stmt.handlers:
                    inner.extend(handler.body)
                inner.extend(stmt.finalbody)
            if _has_return_in_body(inner):
                return True
    return False


def _get_source_segment(source: str, node: ast.AST) -> str:
    try:
        return ast.get_source_segment(source, node) or ""
    except Exception:
        return ""


class ExceptionPatternScanner(ast.NodeVisitor):
    def __init__(self, filepath: str, source: str):
        self.filepath = filepath
        self.source = source
        self.findings: list[Finding] = []

    def _add_finding(self, node: ast.AST, rule: str, level: str, message: str, snippet: str = ""):
        self.findings.append(Finding(
            file=self.filepath,
            line=node.lineno,
            col=node.col_offset,
            rule=rule,
            level=level,
            message=message,
            snippet=snippet[:120],
        ))

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        self._check_except_handler(node)
        self.generic_visit(node)

    def _check_except_handler(self, node: ast.ExceptHandler):
        is_bare_except = node.type is None
        is_exception_except = (
            node.type is not None
            and isinstance(node.type, ast.Name)
            and node.type.id == "Exception"
        )

        if is_bare_except:
            self._add_finding(
                node,
                rule="L300",
                level="ERROR",
                message="Bare `except:` catches all exceptions including SystemExit/KeyboardInterrupt. Use `except Exception:` or more specific type.",
                snippet=_get_source_segment(self.source, node),
            )
            return

        if not is_exception_except:
            return

        if not node.body:
            return

        has_raise = _has_raise_in_body(node.body)
        has_return = _has_return_in_body(node.body)

        if not has_raise and not has_return and len(node.body) == 1:
            only_stmt = node.body[0]
            if isinstance(only_stmt, ast.Pass):
                self._add_finding(
                    node,
                    rule="L301",
                    level="ERROR",
                    message="`except Exception: pass` silently swallows all exceptions. Log the error and either re-raise or return an explicit error.",
                    snippet=_get_source_segment(self.source, node),
                )
                return

        if not has_raise and has_return:
            has_log_in_body = False
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.Call):
                    func = stmt.func
                    if isinstance(func, ast.Attribute):
                        if func.attr in ("warning", "error", "exception", "critical", "debug", "info"):
                            if isinstance(func.value, ast.Name) and func.value.id in ("logger", "log", "logging"):
                                has_log_in_body = True
                                break
                    elif isinstance(func, ast.Name):
                        if func.id in ("log", "print", "_log_pool_error", "_append_log", "_append_local_log"):
                            has_log_in_body = True
                            break
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.Return) and stmt.value is not None:
                    if _is_bare_return_value(stmt.value):
                        if has_log_in_body:
                            level = "INFO"
                        else:
                            level = "ERROR"
                        self._add_finding(
                            node,
                            rule="L302",
                            level=level,
                            message=f"`except Exception` followed by `return {ast.dump(stmt.value)}` swallows exception and returns falsy value. Use raise or return Result type.",
                            snippet=_get_source_segment(self.source, node),
                        )
                        break

        if not has_raise and not has_return:
            has_log = False
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.Call):
                    func = stmt.func
                    if isinstance(func, ast.Attribute):
                        if func.attr in ("warning", "error", "exception", "critical", "debug", "info"):
                            if isinstance(func.value, ast.Name) and func.value.id in ("logger", "log", "logging"):
                                has_log = True
                                break
                    elif isinstance(func, ast.Name):
                        if func.id in ("log", "print", "_log_pool_error", "_append_log", "_append_local_log"):
                            has_log = True
                            break

            if has_log and not has_raise:
                body_strs = []
                for stmt in node.body:
                    seg = _get_source_segment(self.source, stmt)
                    if seg:
                        body_strs.append(seg.strip())
                is_only_logging = all(
                    s.startswith(("logger.", "log.", "logging.", "print(", "_log_pool_error", "_append_log", "_append_local_log"))
                    for s in body_strs
                    if s
                )
                if is_only_logging:
                    level = "INFO" if _is_non_critical_context(self.source, node) else "WARN"
                    self._add_finding(
                        node,
                        rule="L303",
                        level=level,
                        message="`except Exception` only logs without re-raising or returning error. Consider whether the exception should propagate.",
                        snippet=_get_source_segment(self.source, node),
                    )


def scan_file(filepath: Path) -> list[Finding]:
    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return []

    scanner = ExceptionPatternScanner(str(filepath), source)
    scanner.visit(tree)
    return scanner.findings


def scan_directory(src_dir: Path, severity: str = "all") -> list[Finding]:
    all_findings: list[Finding] = []
    py_files = list(src_dir.rglob("*.py"))

    skip_dirs = {
        "__pycache__", ".git", ".venv", "venv", "node_modules",
        "site-packages", ".mypy_cache", ".ruff_cache", ".pytest_cache",
        "alembic", "migrations",
    }

    for py_file in py_files:
        if any(part in skip_dirs for part in py_file.parts):
            continue
        findings = scan_file(py_file)
        all_findings.extend(findings)

    if severity == "error":
        all_findings = [f for f in all_findings if f.level == "ERROR"]
    elif severity == "warning":
        all_findings = [f for f in all_findings if f.level in ("ERROR", "WARN")]
    elif severity == "info":
        all_findings = [f for f in all_findings if f.level in ("ERROR", "WARN", "INFO")]

    return all_findings


def main() -> int:
    if not AUDIT_ENABLED:
        print("L3 audit: skipped (AUDIT_L3_ENABLED=false)")
        return 0

    parser = argparse.ArgumentParser(description="L3 audit: exception pattern scan")
    parser.add_argument("--src-dir", default=None, help="Source directory to scan (default: auto-detect)")
    parser.add_argument("--severity", choices=["error", "warning", "info", "all"], default="warning", help="Filter by severity (default: warning=ERROR+WARN)")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    if args.src_dir:
        src_dir = Path(args.src_dir)
    else:
        src_dir = script_dir.parent / "app"
        if not src_dir.exists():
            src_dir = script_dir / "app"

    print(f"L3 audit: scanning {src_dir}...")

    findings = scan_directory(src_dir, args.severity)

    error_count = sum(1 for f in findings if f.level == "ERROR")
    warn_count = sum(1 for f in findings if f.level == "WARN")
    info_count = sum(1 for f in findings if f.level == "INFO")

    if findings:
        findings.sort(key=lambda f: (f.file, f.line))
        print(f"\nL3 audit: {error_count} errors, {warn_count} warnings, {info_count} info")
        for f in findings:
            print(f"  [{f.level}] {f.rule} {f.file}:{f.line}:{f.col} — {f.message}")
            if f.snippet:
                snippet_line = f.snippet.replace("\n", " ")[:100]
                print(f"         {snippet_line}")
    else:
        print("L3 audit: no exception pattern issues found ✓")

    report_path = script_dir.parent / "audit_l3_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_errors": error_count,
            "total_warnings": warn_count,
            "total_info": info_count,
            "findings": [
                {"file": f.file, "line": f.line, "col": f.col, "rule": f.rule, "level": f.level, "message": f.message}
                for f in findings
            ],
        }, f, indent=2, ensure_ascii=False)
    print(f"L3 audit: report saved to {report_path}")

    return 1 if error_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
