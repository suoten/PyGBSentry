"""tests for tools.system_check.reporters — JSONReporter / MarkdownReporter / ReportAggregator。"""

from __future__ import annotations

import json
import unittest

from tools.system_check.reporters.json_reporter import JSONReporter
from tools.system_check.reporters.markdown_reporter import MarkdownReporter
from tools.system_check.reporters.report_aggregator import ReportAggregator
from tools.system_check.shared.models import (
    ApiConsistencyResult,
    ExtensibilityResult,
    FullCheckReport,
    IssueCategory,
    MismatchResult,
    MatchStatus,
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


def _build_simple_report() -> FullCheckReport:
    """构造一个含 open-source 版本数据的 FullCheckReport，用于 reporter 测试。"""
    meta = ReportMeta(
        timestamp="2026-06-29T00:00:00",
        project_root="/tmp/project",
        editions_checked=["open-source"],
        tool_version="1.0.0",
        total_elapsed_seconds=1.5,
    )

    api_consistency = {
        "open-source": ApiConsistencyResult(
            edition="open-source",
            total_frontend_calls=3,
            total_backend_routes=2,
            matched_count=2,
            forward_mismatches=[
                MismatchResult(
                    match_status=MatchStatus.MISSING_BACKEND,
                    severity=Severity.HIGH,
                    direction="forward",
                    method="GET",
                    path="/api/v1/widgets",
                    frontend_call=None,
                    backend_route=RouteInfo(
                        method="GET",
                        path="/api/v1/widgets",
                        function_name="list_widgets",
                        file_path="api/widgets.py",
                    ),
                    detail="前端调用了 /api/v1/widgets 但后端无对应路由",
                    edition="open-source",
                ),
            ],
            reverse_mismatches=[],
        ),
    }

    stubs = {
        "open-source": StubScanResult(
            edition="open-source",
            total_count=1,
            by_type={"pass": 1},
            by_priority={"P2": 1},
            stubs=[
                StubRecord(
                    stub_type=StubType.PASS,
                    priority=Priority.P2,
                    status=StubStatus.PENDING_IMPLEMENT,
                    file_path="editions/open-source/backend/app/example.py",
                    line_number=10,
                    description="函数 stub_function 仅有pass占位",
                    function_name="stub_function",
                    edition="open-source",
                ),
            ],
        ),
    }

    robustness = {
        "open-source": RobustnessResult(
            edition="open-source",
            total_count=1,
            by_category={"silent_failure": 1},
            issues=[
                QualityIssue(
                    category=IssueCategory.SILENT_FAILURE,
                    severity=Severity.MEDIUM,
                    file_path="editions/open-source/backend/app/example.py",
                    line_number=20,
                    description="异常被吞没",
                    edition="open-source",
                ),
            ],
        ),
    }

    usability = {"open-source": UsabilityResult(edition="open-source", total_count=0)}
    ux_quality = {"open-source": UxQualityResult(edition="open-source", total_count=0)}
    extensibility = {"open-source": ExtensibilityResult(edition="open-source", total_count=0)}

    return FullCheckReport(
        meta=meta,
        api_consistency=api_consistency,
        stubs=stubs,
        robustness=robustness,
        usability=usability,
        ux_quality=ux_quality,
        extensibility=extensibility,
    )


class TestJSONReporter(unittest.TestCase):
    def setUp(self):
        self.report = _build_simple_report()

    def test_render_returns_str(self):
        out = JSONReporter.render(self.report)
        self.assertIsInstance(out, str)

    def test_render_is_valid_json(self):
        out = JSONReporter.render(self.report)
        data = json.loads(out)  # 不抛异常即合法
        self.assertIsInstance(data, dict)

    def test_render_contains_meta_fields(self):
        data = json.loads(JSONReporter.render(self.report))
        self.assertIn("meta", data)
        self.assertEqual(data["meta"]["project_root"], "/tmp/project")
        self.assertEqual(data["meta"]["tool_version"], "1.0.0")
        self.assertEqual(data["meta"]["editions_checked"], ["open-source"])
        self.assertEqual(data["meta"]["timestamp"], "2026-06-29T00:00:00")

    def test_render_contains_all_top_level_sections(self):
        data = json.loads(JSONReporter.render(self.report))
        for key in [
            "meta",
            "api_consistency",
            "stubs",
            "robustness",
            "usability",
            "ux_quality",
            "extensibility",
        ]:
            self.assertIn(key, data)

    def test_enum_values_serialized_as_strings(self):
        data = json.loads(JSONReporter.render(self.report))
        stub = data["stubs"]["open-source"]["stubs"][0]
        self.assertEqual(stub["stub_type"], "pass")
        self.assertEqual(stub["priority"], "P2")
        self.assertEqual(stub["status"], "pending_implement")

        mismatch = data["api_consistency"]["open-source"]["forward_mismatches"][0]
        self.assertEqual(mismatch["match_status"], "missing_backend")
        self.assertEqual(mismatch["severity"], "high")

    def test_sanitize_default_keeps_non_sensitive_values(self):
        """render 默认开启 sanitize：非敏感字段值应原样保留。"""
        out = JSONReporter.render(self.report, sanitize=True)
        data = json.loads(out)
        # project_root 不是敏感 key，应原样保留
        self.assertEqual(data["meta"]["project_root"], "/tmp/project")
        # path/method/detail 等字段同样不应被脱敏
        self.assertEqual(data["api_consistency"]["open-source"]["forward_mismatches"][0]["path"],
                         "/api/v1/widgets")

    def test_render_with_sanitize_false(self):
        out = JSONReporter.render(self.report, sanitize=False)
        data = json.loads(out)
        self.assertEqual(data["meta"]["project_root"], "/tmp/project")

    def test_empty_report_renders(self):
        out = JSONReporter.render(FullCheckReport())
        data = json.loads(out)
        self.assertEqual(data["meta"]["editions_checked"], [])
        self.assertEqual(data["stubs"], {})


class TestMarkdownReporter(unittest.TestCase):
    def setUp(self):
        self.report = _build_simple_report()

    def test_render_returns_str(self):
        out = MarkdownReporter.render(self.report)
        self.assertIsInstance(out, str)
        self.assertGreater(len(out), 0)

    def test_render_contains_main_title(self):
        out = MarkdownReporter.render(self.report)
        self.assertIn("# PyGBSentry 系统全面检查报告", out)

    def test_render_contains_meta_table(self):
        out = MarkdownReporter.render(self.report)
        self.assertIn("生成时间", out)
        self.assertIn("项目根目录", out)
        self.assertIn("工具版本", out)
        self.assertIn("/tmp/project", out)

    def test_render_contains_summary_table(self):
        out = MarkdownReporter.render(self.report)
        self.assertIn("## 总体统计", out)
        self.assertIn("API一致性", out)
        self.assertIn("占位功能", out)
        self.assertIn("健壮性", out)

    def test_render_contains_section_headers(self):
        out = MarkdownReporter.render(self.report)
        self.assertIn("## API一致性检查", out)
        self.assertIn("## 占位功能扫描", out)
        self.assertIn("## 健壮性检查", out)
        self.assertIn("## 可用性检查", out)
        self.assertIn("## 好用性检查", out)
        self.assertIn("## 可扩展性检查", out)

    def test_render_contains_edition_subheader(self):
        out = MarkdownReporter.render(self.report)
        self.assertIn("### open-source", out)

    def test_render_contains_mismatch_table_row(self):
        out = MarkdownReporter.render(self.report)
        self.assertIn("/api/v1/widgets", out)
        self.assertIn("missing_backend", out)
        self.assertIn("high", out)

    def test_render_contains_stub_row(self):
        out = MarkdownReporter.render(self.report)
        self.assertIn("stub_function", out)  # description 中包含
        self.assertIn("pass", out)
        self.assertIn("P2", out)

    def test_render_contains_quality_issue_row(self):
        out = MarkdownReporter.render(self.report)
        self.assertIn("silent_failure", out)
        self.assertIn("medium", out)

    def test_empty_report_renders_without_error(self):
        out = MarkdownReporter.render(FullCheckReport())
        self.assertIn("# PyGBSentry 系统全面检查报告", out)


class TestReportAggregator(unittest.TestCase):
    def test_aggregate_returns_full_check_report(self):
        report = ReportAggregator.aggregate()
        self.assertIsInstance(report, FullCheckReport)

    def test_aggregate_default_meta_fields(self):
        report = ReportAggregator.aggregate(project_root="/tmp/x", elapsed_seconds=2.5)
        self.assertEqual(report.meta.project_root, "/tmp/x")
        self.assertEqual(report.meta.total_elapsed_seconds, 2.5)
        self.assertEqual(report.meta.tool_version, "1.0.0")
        self.assertIsInstance(report.meta.timestamp, str)
        self.assertGreater(len(report.meta.timestamp), 0)

    def test_aggregate_editions_checked_collected_from_all_sections(self):
        """aggregate 应从所有非空 result dict 中收集 edition 名。"""
        api = {"open-source": ApiConsistencyResult(edition="open-source")}
        stubs = {"server": StubScanResult(edition="server")}
        robustness = {"open-source": RobustnessResult(edition="open-source")}
        report = ReportAggregator.aggregate(
            api_consistency=api,
            stubs=stubs,
            robustness=robustness,
        )
        # editions_checked 应去重并排序
        self.assertEqual(report.meta.editions_checked, ["open-source", "server"])

    def test_aggregate_editions_checked_empty_when_no_inputs(self):
        report = ReportAggregator.aggregate()
        self.assertEqual(report.meta.editions_checked, [])

    def test_aggregate_editions_checked_sorted(self):
        # 输入顺序为 server、open-source，应排序为 open-source、server
        report = ReportAggregator.aggregate(
            stubs={"server": StubScanResult(edition="server"),
                   "open-source": StubScanResult(edition="open-source")},
        )
        self.assertEqual(report.meta.editions_checked, ["open-source", "server"])

    def test_aggregate_passes_through_section_data(self):
        api = {"open-source": ApiConsistencyResult(edition="open-source", matched_count=5)}
        report = ReportAggregator.aggregate(api_consistency=api)
        self.assertIs(report.api_consistency["open-source"], api["open-source"])
        # 未传入的 section 应为空 dict
        self.assertEqual(report.stubs, {})
        self.assertEqual(report.robustness, {})
        self.assertEqual(report.usability, {})
        self.assertEqual(report.ux_quality, {})
        self.assertEqual(report.extensibility, {})

    def test_aggregate_none_inputs_become_empty_dicts(self):
        report = ReportAggregator.aggregate(
            api_consistency=None,
            stubs=None,
            robustness=None,
            usability=None,
            ux_quality=None,
            extensibility=None,
        )
        for key in ["api_consistency", "stubs", "robustness", "usability", "ux_quality", "extensibility"]:
            self.assertEqual(getattr(report, key), {})


class TestAggregatorToReporterIntegration(unittest.TestCase):
    """验证 ReportAggregator -> JSONReporter / MarkdownReporter 端到端流程。"""

    def test_aggregate_then_json_render(self):
        report = ReportAggregator.aggregate(
            stubs={
                "open-source": StubScanResult(
                    edition="open-source",
                    total_count=1,
                    stubs=[
                        StubRecord(
                            stub_type=StubType.PASS,
                            priority=Priority.P2,
                            status=StubStatus.PENDING_IMPLEMENT,
                            file_path="editions/open-source/backend/app/x.py",
                            line_number=1,
                            description="占位",
                        )
                    ],
                )
            },
            project_root="/tmp/p",
        )
        out = JSONReporter.render(report)
        data = json.loads(out)
        self.assertEqual(data["meta"]["editions_checked"], ["open-source"])
        self.assertEqual(data["stubs"]["open-source"]["total_count"], 1)

    def test_aggregate_then_markdown_render(self):
        report = ReportAggregator.aggregate(
            robustness={
                "open-source": RobustnessResult(
                    edition="open-source",
                    total_count=1,
                    issues=[
                        QualityIssue(
                            category=IssueCategory.SILENT_FAILURE,
                            severity=Severity.LOW,
                            file_path="a.py",
                            line_number=1,
                            description="d",
                        )
                    ],
                )
            },
        )
        out = MarkdownReporter.render(report)
        self.assertIn("## 健壮性检查", out)
        self.assertIn("### open-source", out)


if __name__ == "__main__":
    unittest.main()
