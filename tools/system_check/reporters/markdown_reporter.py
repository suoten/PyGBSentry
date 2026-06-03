from __future__ import annotations

from tools.system_check.shared.models import (
    FullCheckReport,
    MatchStatus,
    MismatchResult,
    QualityIssue,
    Severity,
    StubRecord,
)


class MarkdownReporter:
    @classmethod
    def render(cls, report: FullCheckReport) -> str:
        parts: list[str] = []
        parts.append(cls._render_meta(report))
        parts.append(cls._render_summary(report))
        parts.append(cls._render_api_consistency(report))
        parts.append(cls._render_stubs(report))
        parts.append(cls._render_robustness(report))
        parts.append(cls._render_usability(report))
        parts.append(cls._render_ux_quality(report))
        parts.append(cls._render_extensibility(report))
        return "\n".join(parts)

    @classmethod
    def _render_meta(cls, report: FullCheckReport) -> str:
        m = report.meta
        return (
            f"# PyGBSentry 系统全面检查报告\n\n"
            f"| 属性 | 值 |\n"
            f"|------|----|\n"
            f"| 生成时间 | {m.timestamp} |\n"
            f"| 项目根目录 | {m.project_root} |\n"
            f"| 检查版本 | {', '.join(m.editions_checked)} |\n"
            f"| 工具版本 | {m.tool_version} |\n"
            f"| 总耗时 | {m.total_elapsed_seconds:.1f}秒 |\n"
        )

    @classmethod
    def _render_summary(cls, report: FullCheckReport) -> str:
        parts = ["\n## 总体统计\n"]
        parts.append("| 领域 | 开源版问题数 | 服务器版问题数 |")
        parts.append("|------|------------|-------------|")

        for key, label in [
            ("api_consistency", "API一致性"),
            ("stubs", "占位功能"),
            ("robustness", "健壮性"),
            ("usability", "可用性"),
            ("ux_quality", "好用性"),
            ("extensibility", "可扩展性"),
        ]:
            data = getattr(report, key)
            oss_count = cls._count_issues(data.get("open-source"))
            server_count = cls._count_issues(data.get("server"))
            parts.append(f"| {label} | {oss_count} | {server_count} |")

        return "\n".join(parts)

    @classmethod
    def _count_issues(cls, result) -> int:
        if result is None:
            return 0
        if hasattr(result, "total_count"):
            return result.total_count
        return 0

    @classmethod
    def _render_api_consistency(cls, report: FullCheckReport) -> str:
        parts = ["\n## API一致性检查\n"]
        for edition, result in report.api_consistency.items():
            parts.append(f"\n### {edition}\n")
            parts.append(
                f"- 前端API调用数: {result.total_frontend_calls}\n"
                f"- 后端路由数: {result.total_backend_routes}\n"
                f"- 匹配数: {result.matched_count}\n"
                f"- 正向不匹配(前端→后端): {len(result.forward_mismatches)}\n"
                f"- 反向不匹配(后端→前端): {len(result.reverse_mismatches)}\n"
            )

            if result.forward_mismatches:
                parts.append("\n#### 正向覆盖问题 (前端调用但后端缺失)\n")
                parts.append("| # | 方法 | 路径 | 状态 | 严重度 | 详情 |")
                parts.append("|---|------|------|------|--------|------|")
                for idx, m in enumerate(result.forward_mismatches, 1):
                    parts.append(f"| {idx} | {m.method} | `{m.path}` | {m.match_status.value} | {m.severity.value} | {m.detail[:50]} |")

            if result.reverse_mismatches:
                parts.append("\n#### 反向覆盖问题 (后端路由但前端未调用)\n")
                parts.append("| # | 方法 | 路径 | 状态 | 严重度 | 详情 |")
                parts.append("|---|------|------|------|--------|------|")
                for idx, m in enumerate(result.reverse_mismatches, 1):
                    parts.append(f"| {idx} | {m.method} | `{m.path}` | {m.match_status.value} | {m.severity.value} | {m.detail[:50]} |")

        return "\n".join(parts)

    @classmethod
    def _render_stubs(cls, report: FullCheckReport) -> str:
        parts = ["\n## 占位功能扫描\n"]
        for edition, result in report.stubs.items():
            parts.append(f"\n### {edition}\n")
            parts.append(f"- 总计: {result.total_count}\n")
            if result.by_type:
                parts.append("**按类型:**\n")
                for t, c in result.by_type.items():
                    parts.append(f"  - {t}: {c}")
            if result.by_priority:
                parts.append("\n**按优先级:**\n")
                for p, c in sorted(result.by_priority.items()):
                    parts.append(f"  - {p}: {c}")

            if result.stubs:
                parts.append("\n| # | 优先级 | 类型 | 位置 | 行号 | 描述 |")
                parts.append("|---|--------|------|------|------|------|")
                for idx, s in enumerate(result.stubs[:100], 1):
                    short_path = s.file_path.split("editions/")[-1] if "editions/" in s.file_path else s.file_path
                    parts.append(f"| {idx} | {s.priority.value} | {s.stub_type.value} | `{short_path}` | {s.line_number} | {s.description[:40]} |")

        return "\n".join(parts)

    @classmethod
    def _render_quality_section(cls, title: str, report: FullCheckReport, attr: str) -> str:
        parts = [f"\n## {title}\n"]
        data = getattr(report, attr)
        for edition, result in data.items():
            parts.append(f"\n### {edition}\n")
            parts.append(f"- 问题数: {result.total_count}\n")
            if result.by_category:
                parts.append("**按类别:**\n")
                for cat, cnt in result.by_category.items():
                    parts.append(f"  - {cat}: {cnt}")

            if result.issues:
                parts.append("\n| # | 严重度 | 类别 | 位置 | 行号 | 描述 |")
                parts.append("|---|--------|------|------|------|------|")
                for idx, issue in enumerate(result.issues[:100], 1):
                    short_path = issue.file_path.split("editions/")[-1] if "editions/" in issue.file_path else issue.file_path
                    parts.append(f"| {idx} | {issue.severity.value} | {issue.category.value} | `{short_path}` | {issue.line_number} | {issue.description[:40]} |")

        return "\n".join(parts)

    @classmethod
    def _render_robustness(cls, report: FullCheckReport) -> str:
        return cls._render_quality_section("健壮性检查", report, "robustness")

    @classmethod
    def _render_usability(cls, report: FullCheckReport) -> str:
        return cls._render_quality_section("可用性检查", report, "usability")

    @classmethod
    def _render_ux_quality(cls, report: FullCheckReport) -> str:
        return cls._render_quality_section("好用性检查", report, "ux_quality")

    @classmethod
    def _render_extensibility(cls, report: FullCheckReport) -> str:
        return cls._render_quality_section("可扩展性检查", report, "extensibility")
