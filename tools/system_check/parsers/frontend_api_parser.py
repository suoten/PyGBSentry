from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from tools.system_check.shared.models import ApiCallInfo
from tools.system_check.shared.path_matcher import PathMatcher


class FrontendApiParser:
    _HTTP_CALL_RE = re.compile(
        r"""(?:api|axios|http|request|fetch)\s*\.\s*(get|post|put|delete|patch|head)\s*\(\s*['"]([^'"]+)['"]""",
        re.IGNORECASE,
    )
    _TEMPLATE_CALL_RE = re.compile(
        r"(?:api|axios|http|request|fetch)\s*\.\s*(get|post|put|delete|patch|head)\s*\(\s*`([^`]+)`",
        re.IGNORECASE,
    )
    _FUNCTION_DEF_RE = re.compile(
        r"(?:export\s+)?(?:async\s+)?function\s+(\w+)|(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s+)?\(",
    )
    _CATCH_RE = re.compile(r"\.catch\s*\(|catch\s*\(", re.IGNORECASE)
    _THEN_RE = re.compile(r"\.then\s*\(", re.IGNORECASE)
    _AWAIT_RE = re.compile(r"\bawait\b")
    _TRY_CATCH_RE = re.compile(r"\btry\s*\{", re.IGNORECASE)

    @classmethod
    def parse_api_module(cls, api_file_path: str | Path) -> list[ApiCallInfo]:
        file_path = Path(api_file_path)
        if not file_path.exists():
            return []

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []

        return cls._parse_content(content, str(file_path))

    @classmethod
    def parse_api_directory(cls, api_dir: str | Path) -> list[ApiCallInfo]:
        dir_path = Path(api_dir)
        if not dir_path.exists():
            return []

        all_calls: list[ApiCallInfo] = []
        for f in dir_path.rglob("*.ts"):
            if f.name.endswith(".d.ts"):
                continue
            all_calls.extend(cls.parse_api_module(f))
        for f in dir_path.rglob("*.js"):
            all_calls.extend(cls.parse_api_module(f))
        return all_calls

    @classmethod
    def parse_composable_api_calls(cls, composable_dir: str | Path) -> list[ApiCallInfo]:
        dir_path = Path(composable_dir)
        if not dir_path.exists():
            return []

        all_calls: list[ApiCallInfo] = []
        for f in dir_path.rglob("*.ts"):
            calls = cls.parse_api_module(f)
            all_calls.extend(calls)
        return all_calls

    @classmethod
    def parse_views_api_calls(cls, views_dir: str | Path) -> list[ApiCallInfo]:
        dir_path = Path(views_dir)
        if not dir_path.exists():
            return []

        all_calls: list[ApiCallInfo] = []
        for f in dir_path.rglob("*.vue"):
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
                script_content = cls._extract_script(content)
                if script_content:
                    calls = cls._parse_content(script_content, str(f))
                    all_calls.extend(calls)
            except OSError:
                continue
        return all_calls

    @classmethod
    def _parse_content(cls, content: str, file_path: str) -> list[ApiCallInfo]:
        calls: list[ApiCallInfo] = []
        lines = content.splitlines()

        for i, line in enumerate(lines):
            for match in cls._HTTP_CALL_RE.finditer(line):
                method, path = match.group(1), match.group(2)
                calls.append(cls._create_call(method, path, path, file_path, i + 1, lines, i))

            for match in cls._TEMPLATE_CALL_RE.finditer(line):
                method, raw_path = match.group(1), match.group(2)
                normalized_path = PathMatcher.normalize_path(raw_path)
                normalized_path = cls._normalize_template_vars(normalized_path)
                calls.append(cls._create_call(method, normalized_path, raw_path, file_path, i + 1, lines, i))

        return calls

    @classmethod
    def _normalize_template_vars(cls, path: str) -> str:
        def replacer(m: re.Match) -> str:
            var_name = m.group(1)
            snake_name = PathMatcher.template_var_to_param(var_name)
            return "{" + snake_name + "}"
        return re.sub(r"\$\{(\w+)\}", replacer, path)

    @classmethod
    def _create_call(
        cls, method: str, path: str, raw_path: str, file_path: str,
        line_number: int, lines: list[str], line_idx: int
    ) -> ApiCallInfo:
        has_error_handler = cls._has_error_handler_nearby(lines, line_idx)
        has_success_handler = cls._has_success_handler_nearby(lines, line_idx)

        func_name = ""
        for j in range(line_idx, max(-1, line_idx - 10), -1):
            match = cls._FUNCTION_DEF_RE.search(lines[j] if j >= 0 else "")
            if match:
                func_name = match.group(1) or match.group(2) or ""
                break

        return ApiCallInfo(
            method=method.upper(),
            path=PathMatcher.normalize_path(path),
            function_name=func_name,
            file_path=file_path,
            line_number=line_number,
            raw_path=raw_path,
            has_error_handler=has_error_handler,
            has_success_handler=has_success_handler,
        )

    @classmethod
    def _has_error_handler_nearby(cls, lines: list[str], line_idx: int) -> bool:
        for j in range(line_idx, min(len(lines), line_idx + 8)):
            if cls._CATCH_RE.search(lines[j]) or cls._TRY_CATCH_RE.search(lines[j]):
                return True
        return False

    @classmethod
    def _has_success_handler_nearby(cls, lines: list[str], line_idx: int) -> bool:
        for j in range(line_idx, min(len(lines), line_idx + 8)):
            if "ElMessage" in lines[j] or ".then" in lines[j]:
                return True
        return False

    @classmethod
    def _extract_script(cls, content: str) -> Optional[str]:
        script_match = re.search(r"<script[^>]*>(.*?)</script>", content, re.DOTALL)
        if script_match:
            return script_match.group(1)
        return None
