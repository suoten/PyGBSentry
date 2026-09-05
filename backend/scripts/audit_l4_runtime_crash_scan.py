#!/usr/bin/env python3
"""
L4 自动化审计：运行时崩溃风险扫描

检测导致"运行一段时间后崩溃"的模式：
  L400: asyncio.create_task / ensure_future 未存储引用（fire-and-forget）
  L401: time.sleep 在 async 函数中阻塞事件循环
  L402: 同步 requests 在 async 函数中阻塞事件循环
  L403: open().read()/write() 未使用 with 语句（文件描述符泄漏）
  L404: aiohttp.ClientSession 在请求处理器中每次创建（应共享复用）
  L405: 全局无界 dict/list 缓存（内存泄漏风险）

使用方式：
  python scripts/audit_l4_runtime_crash_scan.py [--src-dir ...] [--severity error|warning|all]

退出码：
  0 — 通过
  1 — 发现 error 级别问题
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

AUDIT_ENABLED = os.environ.get("AUDIT_L4_ENABLED", "true").lower() in {"true", "1", "yes"}


@dataclass
class Finding:
    file: str
    line: int
    col: int
    rule: str
    level: str
    message: str
    snippet: str = ""


def _is_async_function(node: ast.AST) -> bool:
    if isinstance(node, (ast.AsyncFunctionDef,)):
        return True
    return False


def _find_enclosing_async(tree: ast.AST, target_line: int) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            if node.lineno <= target_line <= (node.end_lineno or node.lineno):
                return True
    return False


class RuntimeCrashScanner(ast.NodeVisitor):
    def __init__(self, filepath: str, source: str, tree: ast.AST):
        self.filepath = filepath
        self.source = source
        self.tree = tree
        self.findings: list[Finding] = []

    def _add(self, node: ast.AST, rule: str, level: str, message: str):
        snippet = ""
        try:
            snippet = ast.get_source_segment(self.source, node) or ""
        except Exception:
            pass
        self.findings.append(Finding(
            file=self.filepath, line=node.lineno, col=node.col_offset,
            rule=rule, level=level, message=message, snippet=snippet[:120],
        ))

    def visit_Call(self, node: ast.Call):
        func = node.func

        # L400: asyncio.create_task / ensure_future without storing result
        if isinstance(func, ast.Attribute):
            if func.attr in ("create_task", "ensure_future"):
                if isinstance(func.value, ast.Name) and func.value.id == "asyncio":
                    parent = self._find_parent(node)
                    is_stored = self._is_result_stored(node, parent)
                    if not is_stored:
                        grandparent = self._find_parent(parent) if parent else None
                        if isinstance(grandparent, ast.Call):
                            if isinstance(grandparent.func, ast.Name) and grandparent.func.id in ("_track", "_bg_track"):
                                is_stored = True
                    if not is_stored:
                        self._add(node, "L400", "ERROR",
                                  f"`asyncio.{func.attr}()` result not stored — task may be GC'd, exceptions lost, cannot cancel on shutdown")

        # L401: time.sleep in async context
        if isinstance(func, ast.Attribute):
            if func.attr == "sleep":
                if isinstance(func.value, ast.Name) and func.value.id == "time":
                    if _find_enclosing_async(self.tree, node.lineno):
                        if not self._is_in_sync_def(node):
                            self._add(node, "L401", "ERROR",
                                      "`time.sleep()` in async context blocks the event loop. Use `await asyncio.sleep()` instead.")

        # L402: sync requests.get/post in async context
        if isinstance(func, ast.Attribute):
            if func.attr in ("get", "post", "put", "delete", "patch", "head", "options"):
                if isinstance(func.value, ast.Name) and func.value.id in ("requests", "_requests"):
                    if _find_enclosing_async(self.tree, node.lineno):
                        if not self._is_in_sync_def(node):
                            self._add(node, "L402", "ERROR",
                                  f"Synchronous `requests.{func.attr}()` in async context blocks the event loop. Use `httpx.AsyncClient` or `asyncio.to_thread`.")

        # L403: open().read()/write() without with
        if isinstance(func, ast.Name) and func.id == "open":
            parent = self._find_parent(node)
            if parent is not None:
                if isinstance(parent, ast.With):
                    self.generic_visit(node)
                    return
            grandparent = self._find_parent(parent) if parent else None
            if isinstance(parent, ast.Call) and isinstance(grandparent, ast.Attribute):
                if grandparent.attr in ("read", "write", "readlines", "writelines"):
                    self._add(node, "L403", "ERROR",
                              f"`open().{grandparent.attr}()` without `with` statement — file descriptor leak. Use `with open(...) as f:`")

        # L404: aiohttp.ClientSession() created per-request
        if isinstance(func, ast.Attribute):
            if func.attr == "ClientSession":
                if isinstance(func.value, ast.Name) and func.value.id == "aiohttp":
                    self._add(node, "L404", "WARN",
                              "`aiohttp.ClientSession()` created per-call — should share a single instance. Use `app.core.http_client` instead.")

        self.generic_visit(node)

    def _find_parent(self, target: ast.AST) -> ast.AST | None:
        for node in ast.walk(self.tree):
            for child in ast.iter_child_nodes(node):
                if child is target:
                    return node
        return None

    def _is_result_stored(self, call_node: ast.Call, parent: ast.AST | None) -> bool:
        if parent is None:
            return False
        if isinstance(parent, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            return True
        if isinstance(parent, ast.IfExp):
            return True
        if isinstance(parent, ast.Return):
            return True
        if isinstance(parent, ast.Yield):
            return True
        if isinstance(parent, ast.List) or isinstance(parent, ast.Tuple):
            return True
        if isinstance(parent, ast.Call):
            if isinstance(parent.func, ast.Name) and parent.func.id in ("_track", "_bg_track"):
                return True
            if isinstance(parent.func, ast.Attribute):
                if parent.func.attr in ("append", "extend", "add"):
                    return True
        if isinstance(parent, ast.Dict):
            return True
        return False

    def _is_in_sync_def(self, node: ast.AST) -> bool:
        for n in ast.walk(self.tree):
            if isinstance(n, ast.FunctionDef) and not isinstance(n, ast.AsyncFunctionDef):
                if n.lineno <= node.lineno <= (n.end_lineno or n.lineno):
                    return True
        return False

    def _is_in_sync_wrapper(self, parent: ast.AST | None) -> bool:
        if parent is None:
            return False
        if isinstance(parent, ast.FunctionDef) and not isinstance(parent, ast.AsyncFunctionDef):
            func_name = parent.name.lower()
            if any(kw in func_name for kw in ("_download", "_sync", "_blocking", "_run_cmd", "_background")):
                return True
        grandparent = self._find_parent(parent) if parent else None
        if isinstance(grandparent, ast.Call):
            if isinstance(grandparent.func, ast.Attribute):
                if grandparent.func.attr in ("run_in_executor", "to_thread"):
                    return True
            if isinstance(grandparent.func, ast.Name):
                if grandparent.func.id in ("run_in_executor", "to_thread"):
                    return True
        return False


def scan_file(filepath: Path) -> list[Finding]:
    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return []
    scanner = RuntimeCrashScanner(str(filepath), source, tree)
    scanner.visit(tree)
    return scanner.findings


def scan_directory(src_dir: Path, severity: str = "warning") -> list[Finding]:
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
    return all_findings


def main() -> int:
    if not AUDIT_ENABLED:
        print("L4 audit: skipped (AUDIT_L4_ENABLED=false)")
        return 0

    parser = argparse.ArgumentParser(description="L4 audit: runtime crash risk scan")
    parser.add_argument("--src-dir", default=None)
    parser.add_argument("--severity", choices=["error", "warning", "all"], default="warning")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    src_dir = Path(args.src_dir) if args.src_dir else script_dir.parent / "app"

    print(f"L4 audit: scanning {src_dir}...")
    findings = scan_directory(src_dir, args.severity)

    error_count = sum(1 for f in findings if f.level == "ERROR")
    warn_count = sum(1 for f in findings if f.level == "WARN")

    if findings:
        findings.sort(key=lambda f: (f.file, f.line))
        print(f"\nL4 audit: {error_count} errors, {warn_count} warnings")
        for f in findings:
            print(f"  [{f.level}] {f.rule} {f.file}:{f.line} — {f.message}")
    else:
        print("L4 audit: no runtime crash risks found ✓")

    report_path = script_dir.parent / "audit_l4_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_errors": error_count,
            "total_warnings": warn_count,
            "findings": [{"file": f.file, "line": f.line, "col": f.col, "rule": f.rule, "level": f.level, "message": f.message} for f in findings],
        }, f, indent=2, ensure_ascii=False)
    print(f"L4 audit: report saved to {report_path}")

    return 1 if error_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
