from __future__ import annotations

import re
from pathlib import Path

from tools.system_check.shared.models import (
    ExtensibilityResult,
    IssueCategory,
    QualityIssue,
    Severity,
)


class ExtensibilityAnalyzer:
    _MAGIC_NUMBER_THRESHOLD = 100
    _EXCLUDE_NUMBERS = {0, 1, -1, 2, 10, 100, 255, 256, 1000, 1024, 60, 3600, 86400}
    _FIXED_URL_RE = re.compile(r"""['"]https?://[^'"]+['"]""")
    _INLINE_LIMIT_RE = re.compile(r"(?:limit|pageSize|page_size|per_page)\s*[=:]\s*(\d+)")
    _INLINE_TIMEOUT_RE = re.compile(r"(?:timeout|TIMEOUT)\s*[=:]\s*(\d+)")
    _HARDCODED_PORT_RE = re.compile(r"(?:port|PORT)\s*[=:]\s*(\d{4,5})")
    _CONFIG_FIELD_RE = re.compile(r"([A-Z_]{2,})\s*[:=]\s*")
    _DIRECT_IMPORT_RE = re.compile(r"from\s+(redis|aioredis|httpx|aiohttp|kafka|pika|sqlalchemy)\s+import\s+")
    _SERVER_EDITION_CHECK_RE = re.compile(r"is_server_edition|APP_EDITION")

    @classmethod
    def analyze(
        cls,
        edition: str,
        backend_app_dir: str | Path,
        frontend_src_dir: str | Path,
        config_file: str | Path | None = None,
    ) -> ExtensibilityResult:
        backend_path = Path(backend_app_dir)
        frontend_path = Path(frontend_src_dir)

        issues: list[QualityIssue] = []
        issues.extend(cls._detect_hardcode(backend_path, frontend_path, edition))
        issues.extend(cls._check_config_coverage(backend_path, config_file, edition))
        issues.extend(cls._check_interface_abstraction(backend_path, edition))
        issues.extend(cls._check_version_diff_management(backend_path, edition))

        by_category: dict[str, int] = {}
        for issue in issues:
            by_category[issue.category.value] = by_category.get(issue.category.value, 0) + 1

        return ExtensibilityResult(
            edition=edition,
            issues=issues,
            total_count=len(issues),
            by_category=by_category,
        )

    @classmethod
    def _detect_hardcode(cls, backend_path: Path, frontend_path: Path, edition: str) -> list[QualityIssue]:
        issues: list[QualityIssue] = []
        issues.extend(cls._scan_python_hardcode(backend_path, edition))
        issues.extend(cls._scan_frontend_hardcode(frontend_path, edition))
        return issues

    @classmethod
    def _scan_python_hardcode(cls, app_dir: Path, edition: str) -> list[QualityIssue]:
        issues: list[QualityIssue] = []
        for py_file in app_dir.rglob("*.py"):
            if "__pycache__" in str(py_file) or "config.py" in str(py_file):
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            lines = content.splitlines()
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith("'") or stripped.startswith('"'):
                    continue
                if "import" in stripped or "from" in stripped:
                    continue

                for match in cls._FIXED_URL_RE.finditer(line):
                    url = match.group()
                    if "localhost" in url or "127.0.0.1" in url or "0.0.0.0" in url:
                        issues.append(QualityIssue(
                            category=IssueCategory.HARDCODE,
                            severity=Severity.HIGH,
                            file_path=str(py_file),
                            line_number=i + 1,
                            description=f"硬编码本地URL: {url}",
                            current_behavior=f"URL直接写在代码中: {url}",
                            expected_behavior="使用配置项替代硬编码URL",
                            edition=edition,
                        ))
                    elif "example.com" not in url and "docs" not in url:
                        issues.append(QualityIssue(
                            category=IssueCategory.HARDCODE,
                            severity=Severity.MEDIUM,
                            file_path=str(py_file),
                            line_number=i + 1,
                            description=f"固定URL: {url}",
                            current_behavior=f"URL直接写在代码中: {url}",
                            expected_behavior="使用配置项替代硬编码URL",
                            edition=edition,
                        ))

                for match in cls._INLINE_LIMIT_RE.finditer(line):
                    issues.append(QualityIssue(
                        category=IssueCategory.HARDCODE,
                        severity=Severity.LOW,
                        file_path=str(py_file),
                        line_number=i + 1,
                        description=f"内联limit配置: limit={match.group(1)}",
                        current_behavior=f"分页限制硬编码为 {match.group(1)}",
                        expected_behavior="使用配置项替代内联limit",
                        edition=edition,
                    ))

                for match in cls._INLINE_TIMEOUT_RE.finditer(line):
                    issues.append(QualityIssue(
                        category=IssueCategory.HARDCODE,
                        severity=Severity.LOW,
                        file_path=str(py_file),
                        line_number=i + 1,
                        description=f"内联timeout配置: timeout={match.group(1)}",
                        current_behavior=f"超时时间硬编码为 {match.group(1)}",
                        expected_behavior="使用配置项替代内联timeout",
                        edition=edition,
                    ))

                for match in cls._HARDCODED_PORT_RE.finditer(line):
                    port = int(match.group(1))
                    if port not in (80, 443, 8080, 8443, 3000, 5432, 6379):
                        issues.append(QualityIssue(
                            category=IssueCategory.HARDCODE,
                            severity=Severity.MEDIUM,
                            file_path=str(py_file),
                            line_number=i + 1,
                            description=f"硬编码端口号: port={port}",
                            current_behavior=f"端口号硬编码为 {port}",
                            expected_behavior="使用配置项替代硬编码端口",
                            edition=edition,
                        ))

        return issues

    @classmethod
    def _scan_frontend_hardcode(cls, src_dir: Path, edition: str) -> list[QualityIssue]:
        issues: list[QualityIssue] = []
        if not src_dir.exists():
            return issues

        for f in src_dir.rglob("*.ts"):
            if f.name.endswith(".d.ts"):
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            lines = content.splitlines()
            for i, line in enumerate(lines):
                for match in cls._FIXED_URL_RE.finditer(line):
                    url = match.group()
                    if "localhost" in url or "127.0.0.1" in url:
                        issues.append(QualityIssue(
                            category=IssueCategory.HARDCODE,
                            severity=Severity.HIGH,
                            file_path=str(f),
                            line_number=i + 1,
                            description=f"硬编码本地URL: {url}",
                            current_behavior=f"URL直接写在前端代码中: {url}",
                            expected_behavior="使用环境变量或配置替代",
                            edition=edition,
                        ))

        return issues

    @classmethod
    def _check_config_coverage(cls, app_dir: Path, config_file: str | Path | None, edition: str) -> list[QualityIssue]:
        issues: list[QualityIssue] = []
        if config_file is None:
            config_path = app_dir / "core" / "config.py"
        else:
            config_path = Path(config_file)

        if not config_path.exists():
            return issues

        try:
            content = config_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return issues

        config_fields = set(cls._CONFIG_FIELD_RE.findall(content))

        essential_fields = {"DATABASE_URL", "REDIS_URL", "SECRET_KEY", "ACCESS_TOKEN_EXPIRE_MINUTES"}
        if edition == "server":
            essential_fields.update({"BILLING_ENABLED", "PLUGIN_MARKETPLACE_URL", "LICENSE_PUBLIC_KEY"})

        missing = essential_fields - config_fields
        for field_name in missing:
            issues.append(QualityIssue(
                category=IssueCategory.MISSING_CONFIG,
                severity=Severity.MEDIUM,
                file_path=str(config_path),
                line_number=1,
                description=f"缺少配置项: {field_name}",
                current_behavior=f"{field_name} 未在config.py中定义",
                expected_behavior=f"在Settings类中添加 {field_name} 配置项",
                edition=edition,
            ))

        return issues

    @classmethod
    def _check_interface_abstraction(cls, app_dir: Path, edition: str) -> list[QualityIssue]:
        issues: list[QualityIssue] = []
        for py_file in app_dir.rglob("*.py"):
            if "__pycache__" in str(py_file) or "core/" in str(py_file) or "config" in str(py_file):
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            lines = content.splitlines()
            for i, line in enumerate(lines):
                for match in cls._DIRECT_IMPORT_RE.finditer(line):
                    dep = match.group(1)
                    issues.append(QualityIssue(
                        category=IssueCategory.DIRECT_DEPENDENCY,
                        severity=Severity.MEDIUM,
                        file_path=str(py_file),
                        line_number=i + 1,
                        description=f"直接依赖具体实现: {dep}",
                        current_behavior=f"直接import {dep}",
                        expected_behavior="通过接口/协议解耦，依赖注入",
                        edition=edition,
                    ))

        return issues

    @classmethod
    def _check_version_diff_management(cls, app_dir: Path, edition: str) -> list[QualityIssue]:
        issues: list[QualityIssue] = []
        api_file = app_dir / "api" / "v1" / "api.py"
        if not api_file.exists():
            return issues

        try:
            content = api_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return issues

        has_edition_check = bool(cls._SERVER_EDITION_CHECK_RE.search(content))
        if not has_edition_check:
            issues.append(QualityIssue(
                category=IssueCategory.CODE_DUPLICATION,
                severity=Severity.MEDIUM,
                file_path=str(api_file),
                line_number=1,
                description="版本差异未通过配置开关管理",
                current_behavior="开源版/服务器版代码可能大量重复",
                expected_behavior="使用APP_EDITION/is_server_edition配置开关管理版本差异",
                edition=edition,
            ))

        return issues
