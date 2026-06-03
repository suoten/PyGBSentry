from __future__ import annotations

import re
from pathlib import Path

from tools.system_check.parsers.backend_route_parser import BackendRouteParser
from tools.system_check.parsers.vue_sfc_parser import VueSfcParser
from tools.system_check.shared.models import (
    IssueCategory,
    QualityIssue,
    Severity,
    UxQualityResult,
)


class UxQualityAnalyzer:
    _UNDERSCORE_IN_PATH_RE = re.compile(r"/\w*_\w*")
    _CAMEL_IN_PATH_RE = re.compile(r"/[a-z]+[A-Z]")
    _VAGUE_ERROR_RE = re.compile(r"操作失败|系统错误|error occurred|an error|something went wrong|处理失败|请求失败", re.IGNORECASE)
    _TECH_JARGON_RE = re.compile(r"POST|GET|PUT|DELETE|SQL|HTTP|SELECT|INSERT|UPDATE", re.IGNORECASE)
    _TECH_DETAIL_RE = re.compile(r"traceback|Traceback|sql.*error|Error\s*\d{3}|errno|errno", re.IGNORECASE)
    _LEGACY_NAMES = {"device_record", "push_channels", "record_schedule", "gb_record", "cloud_records"}

    @classmethod
    def analyze(
        cls,
        edition: str,
        backend_api_file: str | Path,
        frontend_src_dir: str | Path,
    ) -> UxQualityResult:
        issues: list[QualityIssue] = []

        issues.extend(cls._check_api_path_naming(backend_api_file, edition))
        issues.extend(cls._check_error_message_quality(frontend_src_dir, edition))
        issues.extend(cls._check_ui_copy(frontend_src_dir, edition))
        issues.extend(cls._check_legacy_naming(backend_api_file, edition))

        by_category: dict[str, int] = {}
        for issue in issues:
            by_category[issue.category.value] = by_category.get(issue.category.value, 0) + 1

        return UxQualityResult(
            edition=edition,
            issues=issues,
            total_count=len(issues),
            by_category=by_category,
        )

    @classmethod
    def _check_api_path_naming(cls, api_file: str | Path, edition: str) -> list[QualityIssue]:
        issues: list[QualityIssue] = []
        routes = BackendRouteParser.parse_api_registration(api_file)

        for reg in routes:
            prefix = reg.get("prefix", "")
            if not prefix:
                continue

            if cls._UNDERSCORE_IN_PATH_RE.search(prefix):
                kebab_suggestion = re.sub(r"_", "-", prefix)
                issues.append(QualityIssue(
                    category=IssueCategory.NAMING_VIOLATION,
                    severity=Severity.LOW,
                    file_path=str(api_file),
                    line_number=reg.get("line_number", 0),
                    description=f"API路径 {prefix} 使用下划线而非kebab-case",
                    current_behavior=f"路径: {prefix}",
                    expected_behavior=f"建议: {kebab_suggestion}",
                    edition=edition,
                ))

            if cls._CAMEL_IN_PATH_RE.search(prefix):
                kebab_suggestion = re.sub(r"([a-z])([A-Z])", r"\1-\2", prefix).lower()
                issues.append(QualityIssue(
                    category=IssueCategory.NAMING_VIOLATION,
                    severity=Severity.LOW,
                    file_path=str(api_file),
                    line_number=reg.get("line_number", 0),
                    description=f"API路径 {prefix} 使用驼峰而非kebab-case",
                    current_behavior=f"路径: {prefix}",
                    expected_behavior=f"建议: {kebab_suggestion}",
                    edition=edition,
                ))

        return issues

    @classmethod
    def _check_error_message_quality(cls, src_dir: str | Path, edition: str) -> list[QualityIssue]:
        issues: list[QualityIssue] = []
        src_path = Path(src_dir)
        if not src_path.exists():
            return issues

        for vue_file in src_path.rglob("*.vue"):
            try:
                content = vue_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            script_match = re.search(r"<script[^>]*>(.*?)</script>", content, re.DOTALL)
            if not script_match:
                continue
            script = script_match.group(1)

            for match in cls._VAGUE_ERROR_RE.finditer(script):
                line_num = script[:match.start()].count("\n") + 1
                issues.append(QualityIssue(
                    category=IssueCategory.VAGUE_ERROR,
                    severity=Severity.MEDIUM,
                    file_path=str(vue_file),
                    line_number=line_num,
                    description=f"模糊错误提示: \"{match.group()}\"",
                    current_behavior=f"错误提示: {match.group()}",
                    expected_behavior="错误提示应直接指出问题字段和原因",
                    edition=edition,
                ))

            for match in cls._TECH_DETAIL_RE.finditer(script):
                line_num = script[:match.start()].count("\n") + 1
                issues.append(QualityIssue(
                    category=IssueCategory.TECH_JARGON,
                    severity=Severity.HIGH,
                    file_path=str(vue_file),
                    line_number=line_num,
                    description=f"错误提示暴露技术细节: \"{match.group()}\"",
                    current_behavior="错误提示包含技术术语或堆栈跟踪",
                    expected_behavior="错误提示应面向用户，隐藏技术细节",
                    edition=edition,
                ))

        return issues

    @classmethod
    def _check_ui_copy(cls, src_dir: str | Path, edition: str) -> list[QualityIssue]:
        issues: list[QualityIssue] = []
        src_path = Path(src_dir)
        if not src_path.exists():
            return issues

        for vue_file in src_path.rglob("*.vue"):
            try:
                content = vue_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            template_match = re.search(r"<template>(.*?)</template>", content, re.DOTALL)
            if not template_match:
                continue
            template = template_match.group(1)

            button_texts = re.findall(r"<el-button[^>]*>(.*?)</el-button>", template, re.DOTALL)
            for text in button_texts:
                text = text.strip()
                if cls._TECH_JARGON_RE.search(text) and len(text) < 20:
                    issues.append(QualityIssue(
                        category=IssueCategory.TECH_JARGON,
                        severity=Severity.LOW,
                        file_path=str(vue_file),
                        line_number=1,
                        description=f"按钮文本含技术术语: \"{text}\"",
                        current_behavior=f"按钮: {text}",
                        expected_behavior="使用业务语言描述按钮功能",
                        edition=edition,
                    ))

        return issues

    @classmethod
    def _check_legacy_naming(cls, api_file: str | Path, edition: str) -> list[QualityIssue]:
        issues: list[QualityIssue] = []
        try:
            content = Path(api_file).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return issues

        for legacy_name in cls._LEGACY_NAMES:
            if legacy_name in content:
                kebab = re.sub(r"_", "-", legacy_name)
                issues.append(QualityIssue(
                    category=IssueCategory.LEGACY_NAMING,
                    severity=Severity.LOW,
                    file_path=str(api_file),
                    line_number=1,
                    description=f"历史遗留命名: {legacy_name}",
                    current_behavior=f"路径包含: {legacy_name}",
                    expected_behavior=f"建议迁移至: {kebab}，保留兼容别名",
                    edition=edition,
                ))

        return issues

