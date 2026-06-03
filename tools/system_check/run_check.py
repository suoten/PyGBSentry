#!/usr/bin/env python3
"""PyGBSentry 系统全面检查工具 CLI 入口"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.system_check.shared.check_config import CheckConfig
from tools.system_check.analyzers.api_consistency import ApiConsistencyAnalyzer
from tools.system_check.analyzers.stub_scanner import StubScanner
from tools.system_check.analyzers.robustness import RobustnessAnalyzer
from tools.system_check.analyzers.usability import UsabilityAnalyzer
from tools.system_check.analyzers.ux_quality import UxQualityAnalyzer
from tools.system_check.analyzers.extensibility import ExtensibilityAnalyzer
from tools.system_check.reporters.report_aggregator import ReportAggregator
from tools.system_check.reporters.markdown_reporter import MarkdownReporter
from tools.system_check.reporters.json_reporter import JSONReporter


ALL_CHECKS = ["api-consistency", "stub", "robustness", "usability", "ux-quality", "extensibility"]


def run_checks(
    editions: list[str],
    checks: list[str],
    config: CheckConfig,
    output_format: str = "markdown",
    output_path: str | None = None,
) -> None:
    start_time = time.time()

    api_consistency_results = {}
    stub_results = {}
    robustness_results = {}
    usability_results = {}
    ux_quality_results = {}
    extensibility_results = {}

    for edition in editions:
        paths = config.get_edition_paths(edition)
        if not paths:
            print(f"⚠️ 版本 {edition} 路径不存在，跳过")
            continue

        print(f"\n🔍 检查版本: {edition}")

        if "api-consistency" in checks:
            print("  正在执行API一致性检查...")
            t0 = time.time()
            api_consistency_results[edition] = ApiConsistencyAnalyzer.analyze(
                edition=edition,
                backend_api_file=paths.backend_api_file,
                frontend_src_dir=paths.frontend_src_dir,
                frontend_api_dir=paths.frontend_api_dir,
                frontend_views_dir=paths.frontend_views_dir,
                frontend_composable_dir=paths.frontend_composable_dir,
            )
            print(f"  ✅ API一致性检查完成，耗时{time.time()-t0:.1f}秒")

        if "stub" in checks:
            print("  正在执行占位功能扫描...")
            t0 = time.time()
            stub_results[edition] = StubScanner.analyze(
                edition=edition,
                backend_app_dir=paths.backend_app_dir,
                frontend_src_dir=paths.frontend_src_dir,
            )
            print(f"  ✅ 占位功能扫描完成，耗时{time.time()-t0:.1f}秒")

        if "robustness" in checks:
            print("  正在执行健壮性检查...")
            t0 = time.time()
            robustness_results[edition] = RobustnessAnalyzer.analyze(
                edition=edition,
                backend_app_dir=paths.backend_app_dir,
                frontend_src_dir=paths.frontend_src_dir,
            )
            print(f"  ✅ 健壮性检查完成，耗时{time.time()-t0:.1f}秒")

        if "usability" in checks:
            print("  正在执行可用性检查...")
            t0 = time.time()
            usability_results[edition] = UsabilityAnalyzer.analyze(
                edition=edition,
                frontend_src_dir=paths.frontend_src_dir,
            )
            print(f"  ✅ 可用性检查完成，耗时{time.time()-t0:.1f}秒")

        if "ux-quality" in checks:
            print("  正在执行好用性检查...")
            t0 = time.time()
            ux_quality_results[edition] = UxQualityAnalyzer.analyze(
                edition=edition,
                backend_api_file=paths.backend_api_file,
                frontend_src_dir=paths.frontend_src_dir,
            )
            print(f"  ✅ 好用性检查完成，耗时{time.time()-t0:.1f}秒")

        if "extensibility" in checks:
            print("  正在执行可扩展性检查...")
            t0 = time.time()
            config_file = paths.backend_app_dir / "core" / "config.py"
            extensibility_results[edition] = ExtensibilityAnalyzer.analyze(
                edition=edition,
                backend_app_dir=paths.backend_app_dir,
                frontend_src_dir=paths.frontend_src_dir,
                config_file=config_file if config_file.exists() else None,
            )
            print(f"  ✅ 可扩展性检查完成，耗时{time.time()-t0:.1f}秒")

    elapsed = time.time() - start_time
    report = ReportAggregator.aggregate(
        api_consistency=api_consistency_results,
        stubs=stub_results,
        robustness=robustness_results,
        usability=usability_results,
        ux_quality=ux_quality_results,
        extensibility=extensibility_results,
        project_root=str(config.project_root),
        elapsed_seconds=elapsed,
    )

    if output_format == "markdown":
        content = MarkdownReporter.render(report)
    else:
        content = JSONReporter.render(report)

    if output_path:
        Path(output_path).write_text(content, encoding="utf-8")
        print(f"\n📄 报告已保存至: {output_path}")
    else:
        print(f"\n{'='*60}")
        print(content)

    print(f"\n⏱️ 总耗时: {elapsed:.1f}秒")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PyGBSentry 系统全面检查工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--edition",
        choices=["open-source", "server", "all"],
        default="all",
        help="检查的版本 (默认: all)",
    )
    parser.add_argument(
        "--checks",
        nargs="+",
        choices=ALL_CHECKS,
        default=ALL_CHECKS,
        help="执行的检查项 (默认: 全部)",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        dest="output_format",
        help="输出格式 (默认: markdown)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="输出文件路径",
    )
    parser.add_argument(
        "--project-root",
        type=str,
        default=str(PROJECT_ROOT),
        help="项目根目录",
    )

    args = parser.parse_args()

    config = CheckConfig.from_project_root(args.project_root)

    if args.edition == "all":
        editions = config.available_editions()
    else:
        editions = [args.edition]

    if not editions:
        print("❌ 未找到可检查的版本目录")
        sys.exit(1)

    run_checks(
        editions=editions,
        checks=args.checks,
        config=config,
        output_format=args.output_format,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
