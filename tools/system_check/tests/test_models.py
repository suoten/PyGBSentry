"""tests for tools.system_check.shared.models — Enum 值与 dataclass 默认值/字段。"""

from __future__ import annotations

import unittest
from dataclasses import fields, is_dataclass

from tools.system_check.shared.models import (
    ApiCallInfo,
    ApiConsistencyResult,
    Edition,
    ExtensibilityResult,
    FullCheckReport,
    IssueCategory,
    MatchStatus,
    MismatchResult,
    Priority,
    QualityIssue,
    ReportMeta,
    RobustnessResult,
    RouteInfo,
    Severity,
    StubRecord,
    StubScanResult,
    StubStatus,
    StubType,
    UsabilityResult,
    UxQualityResult,
)


class TestEditionEnum(unittest.TestCase):
    def test_edition_values(self):
        self.assertEqual(Edition.OPEN_SOURCE.value, "open-source")
        self.assertEqual(Edition.SERVER.value, "server")

    def test_edition_is_str_enum(self):
        # str 基类确保可直接当字符串使用
        self.assertIsInstance(Edition.OPEN_SOURCE, str)
        self.assertEqual(Edition.OPEN_SOURCE, "open-source")

    def test_edition_lookup_by_value(self):
        self.assertIs(Edition("open-source"), Edition.OPEN_SOURCE)
        self.assertIs(Edition("server"), Edition.SERVER)


class TestSeverityEnum(unittest.TestCase):
    def test_severity_values(self):
        self.assertEqual(Severity.HIGH.value, "high")
        self.assertEqual(Severity.MEDIUM.value, "medium")
        self.assertEqual(Severity.LOW.value, "low")
        self.assertEqual(Severity.INFO.value, "info")

    def test_severity_count(self):
        self.assertEqual(len(Severity), 4)


class TestMatchStatusEnum(unittest.TestCase):
    def test_match_status_values(self):
        self.assertEqual(MatchStatus.MATCHED.value, "matched")
        self.assertEqual(MatchStatus.MISSING_BACKEND.value, "missing_backend")
        self.assertEqual(MatchStatus.MISSING_FRONTEND.value, "missing_frontend")
        self.assertEqual(MatchStatus.PARAM_MISMATCH.value, "param_mismatch")
        self.assertEqual(MatchStatus.RESPONSE_MISMATCH.value, "response_mismatch")
        self.assertEqual(MatchStatus.DYNAMIC_NEEDS_REVIEW.value, "dynamic_needs_review")
        self.assertEqual(MatchStatus.DEPRECATED.value, "deprecated")


class TestStubTypeEnum(unittest.TestCase):
    def test_stub_type_values(self):
        self.assertEqual(StubType.PASS.value, "pass")
        self.assertEqual(StubType.NOT_IMPLEMENTED.value, "not_implemented")
        self.assertEqual(StubType.EXCEPTION_SWALLOW.value, "exception_swallow")
        self.assertEqual(StubType.TODO_COMMENT.value, "todo_comment")
        self.assertEqual(StubType.PLACEHOLDER_TEXT.value, "placeholder_text")
        self.assertEqual(StubType.EMPTY_COMPONENT.value, "empty_component")
        self.assertEqual(StubType.MOCK_DATA.value, "mock_data")


class TestStubStatusEnum(unittest.TestCase):
    def test_stub_status_values(self):
        self.assertEqual(StubStatus.PENDING_IMPLEMENT.value, "pending_implement")
        self.assertEqual(StubStatus.PENDING_REMOVE.value, "pending_remove")
        self.assertEqual(StubStatus.DEFERRED.value, "deferred")
        self.assertEqual(StubStatus.DONE.value, "done")


class TestPriorityEnum(unittest.TestCase):
    def test_priority_values(self):
        self.assertEqual(Priority.P0.value, "P0")
        self.assertEqual(Priority.P1.value, "P1")
        self.assertEqual(Priority.P2.value, "P2")
        self.assertEqual(Priority.P3.value, "P3")


class TestIssueCategoryEnum(unittest.TestCase):
    def test_some_categories(self):
        self.assertEqual(IssueCategory.EXCEPTION_SWALLOW.value, "exception_swallow")
        self.assertEqual(IssueCategory.NO_PYDANTIC.value, "no_pydantic")
        self.assertEqual(IssueCategory.SILENT_FAILURE.value, "silent_failure")
        self.assertEqual(IssueCategory.HARDCODE.value, "hardcode")

    def test_all_categories_unique(self):
        values = [c.value for c in IssueCategory]
        self.assertEqual(len(values), len(set(values)))


class TestRouteInfo(unittest.TestCase):
    def test_required_fields(self):
        info = RouteInfo(method="GET", path="/api/v1/devices", function_name="list_devices", file_path="api.py")
        self.assertEqual(info.method, "GET")
        self.assertEqual(info.path, "/api/v1/devices")
        self.assertEqual(info.function_name, "list_devices")
        self.assertEqual(info.file_path, "api.py")

    def test_defaults(self):
        info = RouteInfo(method="GET", path="/", function_name="f", file_path="a.py")
        self.assertEqual(info.line_number, 0)
        self.assertEqual(info.prefix, "")
        self.assertEqual(info.full_path, "")
        self.assertFalse(info.has_pydantic)
        self.assertIsNone(info.response_model)
        self.assertFalse(info.is_deprecated)
        self.assertEqual(info.edition_scope, "both")
        self.assertFalse(info.is_internal)

    def test_is_dataclass(self):
        self.assertTrue(is_dataclass(RouteInfo))


class TestApiCallInfo(unittest.TestCase):
    def test_required_fields(self):
        info = ApiCallInfo(method="POST", path="/login")
        self.assertEqual(info.method, "POST")
        self.assertEqual(info.path, "/login")

    def test_defaults(self):
        info = ApiCallInfo(method="GET", path="/")
        self.assertEqual(info.function_name, "")
        self.assertEqual(info.file_path, "")
        self.assertEqual(info.line_number, 0)
        self.assertEqual(info.raw_path, "")
        self.assertEqual(info.params, {})
        self.assertFalse(info.has_error_handler)
        self.assertFalse(info.has_success_handler)

    def test_default_params_isolated(self):
        """default_factory 必须为每个实例返回独立 dict。"""
        a = ApiCallInfo(method="GET", path="/")
        b = ApiCallInfo(method="GET", path="/")
        a.params["x"] = 1
        self.assertNotIn("x", b.params)


class TestMismatchResult(unittest.TestCase):
    def test_required_fields(self):
        m = MismatchResult(
            match_status=MatchStatus.MISSING_BACKEND,
            severity=Severity.HIGH,
            direction="forward",
            method="GET",
            path="/api/v1/devices",
        )
        self.assertEqual(m.match_status, MatchStatus.MISSING_BACKEND)
        self.assertEqual(m.severity, Severity.HIGH)
        self.assertEqual(m.direction, "forward")
        self.assertEqual(m.method, "GET")
        self.assertEqual(m.path, "/api/v1/devices")
        self.assertIsNone(m.frontend_call)
        self.assertIsNone(m.backend_route)
        self.assertEqual(m.detail, "")
        self.assertEqual(m.edition, "")


class TestStubRecord(unittest.TestCase):
    def test_required_fields(self):
        rec = StubRecord(
            stub_type=StubType.PASS,
            priority=Priority.P2,
            status=StubStatus.PENDING_IMPLEMENT,
            file_path="app/x.py",
            line_number=10,
            description="占位",
        )
        self.assertEqual(rec.stub_type, StubType.PASS)
        self.assertEqual(rec.priority, Priority.P2)
        self.assertEqual(rec.status, StubStatus.PENDING_IMPLEMENT)
        self.assertEqual(rec.file_path, "app/x.py")
        self.assertEqual(rec.line_number, 10)
        self.assertEqual(rec.description, "占位")
        self.assertEqual(rec.function_name, "")
        self.assertEqual(rec.edition, "")
        self.assertIsNone(rec.defer_deadline)


class TestQualityIssue(unittest.TestCase):
    def test_required_fields(self):
        issue = QualityIssue(
            category=IssueCategory.SILENT_FAILURE,
            severity=Severity.MEDIUM,
            file_path="a.py",
            line_number=5,
            description="silent",
        )
        self.assertEqual(issue.category, IssueCategory.SILENT_FAILURE)
        self.assertEqual(issue.severity, Severity.MEDIUM)
        self.assertEqual(issue.current_behavior, "")
        self.assertEqual(issue.expected_behavior, "")
        self.assertEqual(issue.suggestion, "")
        self.assertEqual(issue.edition, "")


class TestResultDataclasses(unittest.TestCase):
    """验证各 *Result 数据类的默认集合字段为独立实例。"""

    def test_api_consistency_result_defaults(self):
        r = ApiConsistencyResult()
        self.assertEqual(r.edition, "")
        self.assertEqual(r.forward_mismatches, [])
        self.assertEqual(r.reverse_mismatches, [])
        self.assertEqual(r.total_frontend_calls, 0)
        self.assertEqual(r.total_backend_routes, 0)
        self.assertEqual(r.matched_count, 0)

    def test_stub_scan_result_defaults(self):
        r = StubScanResult()
        self.assertEqual(r.edition, "")
        self.assertEqual(r.stubs, [])
        self.assertEqual(r.total_count, 0)
        self.assertEqual(r.by_type, {})
        self.assertEqual(r.by_priority, {})

    def test_robustness_result_defaults(self):
        r = RobustnessResult()
        self.assertEqual(r.total_count, 0)
        self.assertEqual(r.issues, [])
        self.assertEqual(r.by_category, {})

    def test_usability_and_ux_extensibility_defaults(self):
        for cls in (UsabilityResult, UxQualityResult, ExtensibilityResult):
            r = cls()
            self.assertEqual(r.edition, "")
            self.assertEqual(r.total_count, 0)
            self.assertEqual(r.issues, [])
            self.assertEqual(r.by_category, {})


class TestReportMeta(unittest.TestCase):
    def test_defaults(self):
        m = ReportMeta()
        self.assertEqual(m.timestamp, "")
        self.assertEqual(m.project_root, "")
        self.assertEqual(m.editions_checked, [])
        self.assertEqual(m.tool_version, "1.0.0")
        self.assertEqual(m.total_elapsed_seconds, 0.0)


class TestFullCheckReport(unittest.TestCase):
    def test_defaults(self):
        report = FullCheckReport()
        self.assertIsInstance(report.meta, ReportMeta)
        self.assertEqual(report.api_consistency, {})
        self.assertEqual(report.stubs, {})
        self.assertEqual(report.robustness, {})
        self.assertEqual(report.usability, {})
        self.assertEqual(report.ux_quality, {})
        self.assertEqual(report.extensibility, {})

    def test_default_dict_isolated_between_instances(self):
        a = FullCheckReport()
        b = FullCheckReport()
        a.api_consistency["open-source"] = ApiConsistencyResult()
        self.assertNotIn("open-source", b.api_consistency)

    def test_all_dataclass_fields_present(self):
        expected = {
            "meta",
            "api_consistency",
            "stubs",
            "robustness",
            "usability",
            "ux_quality",
            "extensibility",
        }
        names = {f.name for f in fields(FullCheckReport)}
        self.assertEqual(names, expected)


if __name__ == "__main__":
    unittest.main()
