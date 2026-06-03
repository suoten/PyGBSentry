from __future__ import annotations

import re
from pathlib import Path

from tools.system_check.parsers.vue_sfc_parser import VueSfcParser
from tools.system_check.shared.models import (
    IssueCategory,
    QualityIssue,
    Severity,
    UsabilityResult,
)


class UsabilityAnalyzer:
    _DELETE_RE = re.compile(r"(?:handleDelete|deleteItem|removeItem|onDelete|confirmDelete)", re.IGNORECASE)
    _PUBLISH_RE = re.compile(r"(?:handlePublish|publishItem|onPublish)", re.IGNORECASE)
    _SUBMIT_RE = re.compile(r"(?:handleSubmit|submitForm|onSubmit|handleSave|saveForm)", re.IGNORECASE)
    _BATCH_RE = re.compile(r"(?:batchDelete|batchUpdate|batchImport|bulkAction)", re.IGNORECASE)
    _EL_LOADING_RE = re.compile(r"v-loading|:loading\s*=", re.IGNORECASE)
    _EL_PROGRESS_RE = re.compile(r"el-progress|ElProgress", re.IGNORECASE)

    @classmethod
    def analyze(cls, edition: str, frontend_src_dir: str | Path) -> UsabilityResult:
        src_path = Path(frontend_src_dir)
        if not src_path.exists():
            return UsabilityResult(edition=edition)

        issues: list[QualityIssue] = []
        for vue_file in src_path.rglob("*.vue"):
            try:
                content = vue_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            parsed = VueSfcParser.parse_content(content, str(vue_file))
            script = parsed.get("script", "")
            template = parsed.get("template", "")

            issues.extend(cls._check_success_feedback(vue_file, script, edition))
            issues.extend(cls._check_failure_feedback(vue_file, script, edition))
            issues.extend(cls._check_confirmation_dialog(vue_file, script, template, edition))
            issues.extend(cls._check_loading_indicator(vue_file, script, template, edition))
            issues.extend(cls._check_silent_failure(vue_file, parsed, edition))
            issues.extend(cls._check_batch_operation_progress(vue_file, script, edition))

        by_category: dict[str, int] = {}
        for issue in issues:
            by_category[issue.category.value] = by_category.get(issue.category.value, 0) + 1

        return UsabilityResult(
            edition=edition,
            issues=issues,
            total_count=len(issues),
            by_category=by_category,
        )

    @classmethod
    def _check_success_feedback(cls, file_path: Path, script: str, edition: str) -> list[QualityIssue]:
        issues: list[QualityIssue] = []
        has_success = "ElMessage" in script and "success" in script
        has_submit = bool(cls._SUBMIT_RE.search(script))
        has_post_put = bool(re.search(r"(?:api|axios)\.\s*(?:post|put)\s*\(", script, re.IGNORECASE))

        if (has_submit or has_post_put) and not has_success:
            issues.append(QualityIssue(
                category=IssueCategory.NO_SUCCESS_FEEDBACK,
                severity=Severity.MEDIUM,
                file_path=str(file_path),
                line_number=1,
                description="写操作后无成功反馈提示",
                current_behavior="操作成功后无用户反馈",
                expected_behavior="使用ElMessage.success提示操作成功",
                edition=edition,
            ))
        return issues

    @classmethod
    def _check_failure_feedback(cls, file_path: Path, script: str, edition: str) -> list[QualityIssue]:
        issues: list[QualityIssue] = []
        has_error_msg = "ElMessage.error" in script or "errorMessage" in script
        has_catch = "catch" in script
        has_api_call = bool(re.search(r"(?:api|axios)\.\s*(?:get|post|put|delete)\s*\(", script, re.IGNORECASE))

        if has_api_call and has_catch and not has_error_msg:
            issues.append(QualityIssue(
                category=IssueCategory.NO_FAILURE_FEEDBACK,
                severity=Severity.MEDIUM,
                file_path=str(file_path),
                line_number=1,
                description="API调用有catch但无错误提示",
                current_behavior="操作失败时catch块无用户反馈",
                expected_behavior="在catch块中添加ElMessage.error",
                edition=edition,
            ))
        return issues

    @classmethod
    def _check_confirmation_dialog(cls, file_path: Path, script: str, template: str, edition: str) -> list[QualityIssue]:
        issues: list[QualityIssue] = []
        has_delete = bool(cls._DELETE_RE.search(script)) or bool(re.search(r"@click.*delete|@click.*remove", template, re.IGNORECASE))
        has_confirm = "ElMessageBox.confirm" in script or "confirm" in script
        has_publish = bool(cls._PUBLISH_RE.search(script))

        if has_delete and not has_confirm:
            issues.append(QualityIssue(
                category=IssueCategory.NO_CONFIRMATION,
                severity=Severity.HIGH,
                file_path=str(file_path),
                line_number=1,
                description="删除操作缺少二次确认对话框",
                current_behavior="删除操作直接执行",
                expected_behavior="使用ElMessageBox.confirm二次确认",
                edition=edition,
            ))

        if has_publish and not has_confirm:
            issues.append(QualityIssue(
                category=IssueCategory.NO_CONFIRMATION,
                severity=Severity.MEDIUM,
                file_path=str(file_path),
                line_number=1,
                description="发布操作缺少二次确认",
                current_behavior="发布操作直接执行",
                expected_behavior="使用ElMessageBox.confirm二次确认",
                edition=edition,
            ))
        return issues

    @classmethod
    def _check_loading_indicator(cls, file_path: Path, script: str, template: str, edition: str) -> list[QualityIssue]:
        issues: list[QualityIssue] = []
        has_api_call = bool(re.search(r"(?:api|axios)\.\s*(?:get|post|put|delete)\s*\(", script, re.IGNORECASE))
        has_loading = bool(cls._EL_LOADING_RE.search(template)) or "loading" in script
        has_progress = bool(cls._EL_PROGRESS_RE.search(template))

        if has_api_call and not has_loading and not has_progress:
            issues.append(QualityIssue(
                category=IssueCategory.NO_LOADING,
                severity=Severity.LOW,
                file_path=str(file_path),
                line_number=1,
                description="API调用无loading状态指示",
                current_behavior="请求期间无加载状态提示",
                expected_behavior="添加v-loading或loading状态",
                edition=edition,
            ))
        return issues

    @classmethod
    def _check_silent_failure(cls, file_path: Path, parsed: dict, edition: str) -> list[QualityIssue]:
        issues: list[QualityIssue] = []
        script = parsed.get("script", "")
        api_calls = parsed.get("api_calls", [])

        for call in api_calls:
            has_catch = "catch" in script
            has_then = ".then" in script
            if not has_catch and not has_then and "await" not in script:
                issues.append(QualityIssue(
                    category=IssueCategory.SILENT_FAILURE,
                    severity=Severity.MEDIUM,
                    file_path=str(file_path),
                    line_number=1,
                    description=f"API调用 {call['method']} {call['path']} 可能静默失败",
                    current_behavior="API调用无.then/.catch处理",
                    expected_behavior="添加.then/.catch或async/await错误处理",
                    edition=edition,
                ))
                break
        return issues

    @classmethod
    def _check_batch_operation_progress(cls, file_path: Path, script: str, edition: str) -> list[QualityIssue]:
        issues: list[QualityIssue] = []
        has_batch = bool(cls._BATCH_RE.search(script))
        has_progress = "progress" in script.lower() or "ElProgress" in script

        if has_batch and not has_progress:
            issues.append(QualityIssue(
                category=IssueCategory.BATCH_NO_PROGRESS,
                severity=Severity.MEDIUM,
                file_path=str(file_path),
                line_number=1,
                description="批量操作无进度反馈",
                current_behavior="批量操作执行中无进度提示",
                expected_behavior="添加进度条或分批处理提示",
                edition=edition,
            ))
        return issues
