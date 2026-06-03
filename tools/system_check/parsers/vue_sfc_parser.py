from __future__ import annotations

import re
from pathlib import Path
from typing import Optional


class VueSfcParser:
    _SCRIPT_RE = re.compile(r"<script[^>]*>(.*?)</script>", re.DOTALL)
    _TEMPLATE_RE = re.compile(r"<template>(.*?)</template>", re.DOTALL)
    _STYLE_RE = re.compile(r"<style[^>]*>(.*?)</style>", re.DOTALL)

    _API_CALL_RE = re.compile(
        r"(?:api|axios|http|request)\s*\.\s*(get|post|put|delete|patch)\s*\(",
        re.IGNORECASE,
    )
    _EL_MESSAGE_SUCCESS_RE = re.compile(
        r"""ElMessage\s*\(\s*\{[^}]*type\s*:\s*['"]success['"]""",
        re.DOTALL,
    )
    _EL_MESSAGE_ERROR_RE = re.compile(
        r"""ElMessage\s*\(\s*\{[^}]*type\s*:\s*['"]error['"]""",
        re.DOTALL,
    )
    _EL_MESSAGE_BOX_CONFIRM_RE = re.compile(r"ElMessageBox\.confirm\s*\(", re.DOTALL)
    _EMIT_RE = re.compile(r"""emit\s*\(\s*['"](\w+)['"]""")
    _BUTTON_CLICK_RE = re.compile(r"""@click\s*=\s*['"](\w+)['"]""")

    _PLACEHOLDER_PATTERNS = [
        re.compile(r"功能开发中|即将上线|暂不支持|敬请期待", re.IGNORECASE),
        re.compile(r"coming\s+soon|under\s+development|work\s+in\s+progress|not\s+yet\s+available", re.IGNORECASE),
        re.compile(r"TODO|FIXME|HACK", re.IGNORECASE),
    ]

    @classmethod
    def parse_file(cls, file_path: str | Path) -> dict:
        path = Path(file_path)
        if not path.exists():
            return {}
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return {}
        return cls.parse_content(content, str(path))

    @classmethod
    def parse_content(cls, content: str, file_path: str = "") -> dict:
        script_match = cls._SCRIPT_RE.search(content)
        template_match = cls._TEMPLATE_RE.search(content)

        script_content = script_match.group(1).strip() if script_match else ""
        template_content = template_match.group(1).strip() if template_match else ""

        return {
            "file_path": file_path,
            "script": script_content,
            "template": template_content,
            "api_calls": cls._extract_api_calls(script_content, file_path),
            "el_message_success": bool(cls._EL_MESSAGE_SUCCESS_RE.search(script_content)),
            "el_message_error": bool(cls._EL_MESSAGE_ERROR_RE.search(script_content)),
            "el_message_box_confirm": bool(cls._EL_MESSAGE_BOX_CONFIRM_RE.search(script_content)),
            "button_clicks": cls._BUTTON_CLICK_RE.findall(template_content),
            "placeholders": cls._find_placeholders(template_content, script_content),
            "has_logic": bool(script_content.strip()),
            "is_empty_component": not bool(script_content.strip()),
        }

    @classmethod
    def parse_directory(cls, dir_path: str | Path) -> list[dict]:
        directory = Path(dir_path)
        if not directory.exists():
            return []
        results: list[dict] = []
        for f in directory.rglob("*.vue"):
            parsed = cls.parse_file(f)
            if parsed:
                results.append(parsed)
        return results

    @classmethod
    def _extract_api_calls(cls, script_content: str, file_path: str) -> list[dict]:
        calls: list[dict] = []
        for match in cls._API_CALL_RE.finditer(script_content):
            method = match.group(1).upper()
            start = match.end()
            path_str = cls._extract_call_path(script_content, start)
            calls.append({
                "method": method,
                "path": path_str,
                "file_path": file_path,
            })
        return calls

    @classmethod
    def _extract_call_path(cls, content: str, start: int) -> str:
        remainder = content[start:].lstrip()
        if not remainder:
            return ""
        if remainder[0] in ("'", '"'):
            quote = remainder[0]
            end = remainder.find(quote, 1)
            if end > 0:
                return remainder[1:end]
        elif remainder[0] == "`":
            end = remainder.find("`", 1)
            if end > 0:
                raw = remainder[1:end]
                return re.sub(r"\$\{(\w+)\}", r"{\1}", raw)
        return ""

    @classmethod
    def _find_placeholders(cls, template_content: str, script_content: str) -> list[dict]:
        placeholders: list[dict] = []
        combined = template_content + "\n" + script_content
        for pattern in cls._PLACEHOLDER_PATTERNS:
            for match in pattern.finditer(combined):
                line_num = combined[:match.start()].count("\n") + 1
                placeholders.append({
                    "text": match.group(),
                    "line": line_num,
                })
        return placeholders
