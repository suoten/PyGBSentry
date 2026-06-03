from __future__ import annotations

from datetime import datetime
from pathlib import Path

from tools.system_check.shared.models import (
    ApiConsistencyResult,
    ExtensibilityResult,
    FullCheckReport,
    ReportMeta,
    RobustnessResult,
    StubScanResult,
    UsabilityResult,
    UxQualityResult,
)


class ReportAggregator:
    @classmethod
    def aggregate(
        cls,
        api_consistency: dict[str, ApiConsistencyResult] | None = None,
        stubs: dict[str, StubScanResult] | None = None,
        robustness: dict[str, RobustnessResult] | None = None,
        usability: dict[str, UsabilityResult] | None = None,
        ux_quality: dict[str, UxQualityResult] | None = None,
        extensibility: dict[str, ExtensibilityResult] | None = None,
        project_root: str = "",
        elapsed_seconds: float = 0.0,
    ) -> FullCheckReport:
        meta = ReportMeta(
            timestamp=datetime.now().isoformat(),
            project_root=str(project_root),
            editions_checked=[],
            tool_version="1.0.0",
            total_elapsed_seconds=elapsed_seconds,
        )

        all_editions: set[str] = set()
        for d in [api_consistency, stubs, robustness, usability, ux_quality, extensibility]:
            if d:
                all_editions.update(d.keys())
        meta.editions_checked = sorted(all_editions)

        return FullCheckReport(
            meta=meta,
            api_consistency=api_consistency or {},
            stubs=stubs or {},
            robustness=robustness or {},
            usability=usability or {},
            ux_quality=ux_quality or {},
            extensibility=extensibility or {},
        )
