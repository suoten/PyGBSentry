from __future__ import annotations

import ast
import re
from typing import Optional


class PythonAstParser:
    TODO_PATTERNS = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b", re.IGNORECASE)

    @classmethod
    def parse_file(cls, file_path: str) -> Optional[ast.Module]:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                source = f.read()
            return ast.parse(source, filename=file_path)
        except (SyntaxError, OSError):
            return None

    @classmethod
    def get_source_lines(cls, file_path: str) -> list[str]:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                return f.readlines()
        except OSError:
            return []

    @classmethod
    def is_pass_only_body(cls, node: ast.AST) -> bool:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                return not cls.has_intentional_noop_comment(node)
            if (
                len(node.body) == 2
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[1], ast.Pass)
            ):
                return not cls.has_intentional_noop_comment(node)
        return False

    @classmethod
    def is_not_implemented_error(cls, node: ast.AST) -> bool:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return False
        for stmt in ast.walk(node):
            if isinstance(stmt, ast.Raise):
                if isinstance(stmt.exc, ast.Name) and stmt.exc.id == "NotImplementedError":
                    return True
                if (
                    isinstance(stmt.exc, ast.Call)
                    and isinstance(stmt.exc.func, ast.Name)
                    and stmt.exc.func.id == "NotImplementedError"
                ):
                    return True
        return False

    @classmethod
    def is_exception_swallow(cls, node: ast.ExceptHandler) -> bool:
        for stmt in node.body:
            if isinstance(stmt, ast.Pass):
                if not cls._has_logging_in_body(node.body, stmt):
                    return True
        return False

    @classmethod
    def _has_logging_in_body(cls, body: list[ast.stmt], pass_stmt: ast.Pass) -> bool:
        for stmt in body:
            if stmt is pass_stmt:
                continue
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                func = stmt.value.func
                if isinstance(func, ast.Attribute) and func.attr in (
                    "debug", "info", "warning", "error", "critical", "exception",
                ):
                    return True
                if isinstance(func, ast.Name) and func.id == "logger":
                    return True
        return False

    @classmethod
    def is_todo_comment(cls, node: ast.AST, source_lines: Optional[list[str]] = None) -> bool:
        if source_lines and hasattr(node, "lineno") and node.lineno > 0:
            line_idx = node.lineno - 1
            if 0 <= line_idx < len(source_lines):
                return bool(cls.TODO_PATTERNS.search(source_lines[line_idx]))
        return False

    @classmethod
    def has_intentional_noop_comment(cls, node: ast.AST) -> bool:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for deco in node.decorator_list:
                if isinstance(deco, ast.Name) and deco.id == "noop":
                    return True
            docstring = ast.get_docstring(node)
            if docstring and "intentional" in docstring.lower():
                return True
        return False

    @classmethod
    def find_all_functions(cls, tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
        results: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                results.append(node)
        return results

    @classmethod
    def find_all_classes(cls, tree: ast.Module) -> list[ast.ClassDef]:
        results: list[ast.ClassDef] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                results.append(node)
        return results

    @classmethod
    def find_decorated_functions(cls, tree: ast.Module, decorator_names: set[str]) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
        results: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for deco in node.decorator_list:
                    deco_name = ""
                    if isinstance(deco, ast.Name):
                        deco_name = deco.id
                    elif isinstance(deco, ast.Attribute):
                        deco_name = deco.attr
                    elif isinstance(deco, ast.Call):
                        if isinstance(deco.func, ast.Name):
                            deco_name = deco.func.id
                        elif isinstance(deco.func, ast.Attribute):
                            deco_name = deco.func.attr
                    if deco_name in decorator_names:
                        results.append(node)
                        break
        return results

    @classmethod
    def find_exception_handlers(cls, tree: ast.Module) -> list[ast.ExceptHandler]:
        results: list[ast.ExceptHandler] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                for handler in node.handlers:
                    results.append(handler)
        return results
