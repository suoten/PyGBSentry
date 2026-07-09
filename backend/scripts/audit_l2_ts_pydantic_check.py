#!/usr/bin/env python3
"""
L2 自动化审计：前端 TypeScript 接口 ↔ Pydantic Response 模型对照检测

CI 阶段运行，对比：
  - 前端 TypeScript interface 字段 ⊆ 后端 Pydantic Response 模型字段
  - 后端 Pydantic Response 字段 ⊆ 前端 TypeScript interface 字段

使用方式：
  python scripts/audit_l2_ts_pydantic_check.py [--backend-dir ...] [--frontend-dir ...]

退出码：
  0 — 通过
  1 — 发现偏差

环境变量：
  AUDIT_L2_ENABLED=true/false  — 是否启用（默认 true）
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

AUDIT_ENABLED = os.environ.get("AUDIT_L2_ENABLED", "true").lower() in {"true", "1", "yes"}

TS_INTERFACE_PATTERN = re.compile(
    r"export\s+interface\s+(\w+)\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}",
    re.DOTALL,
)

TS_FIELD_PATTERN = re.compile(
    r"(\w+)\s*(\?)?\s*:\s*([^;\n]+)",
)

PYDANTIC_MODULES = [
    "app.schemas.audit_center",
    "app.schemas.config_center",
    "app.schemas.release_center",
    "app.schemas.ssl_cert",
    "app.api.common.channel",
    "app.api.v1.endpoints.alarms",
    "app.api.v1.endpoints.billing",
    "app.api.v1.endpoints.control",
    "app.api.v1.endpoints.devices._common",
    "app.api.v1.endpoints.integrations",
    "app.api.v1.endpoints.login",
    "app.api.v1.endpoints.map",
    "app.api.v1.endpoints.organizations",
    "app.api.v1.endpoints.platforms",
    "app.api.v1.endpoints.health",
    "app.api.v1.endpoints.command",
    "app.api.v1.endpoints.config_center",
    "app.api.v1.endpoints.apps",
    "app.api.v1.endpoints.asset_management",
    "app.api.v1.endpoints.device_record",
]

TS_TYPE_FILES = [
    "src/types/models.ts",
    "src/api/index.ts",
    "src/api/auditCenter.ts",
    "src/api/configCenter.ts",
    "src/api/releaseCenter.ts",
    "src/api/organizations.ts",
    "src/types/center-fields.ts",
]

MOBILE_TS_API_DIR = "mobile/src/api"

TS_TO_PYDANTIC_MAP: dict[str, str] = {
    "Device": "DeviceUpdatePayload",
    "Channel": "ChannelUpdatePayload",
    "Alarm": "AlarmNotificationItem",
    "VideoRecord": "DeviceRecordQueryPayload",
    "BillingPlan": "BillingPlanCreate",
    "Subscription": "SubscriptionUpdate",
    "Order": "PluginOrderCreate",
    "CascadePlatform": "PlatformCreate",
    "AuditLog": "AuditLogItem",
    "ApiKey": "UserApiKey",
    "WorkOrder": "WorkOrderCreate",
    "AssetLedger": "AssetCreate",
    "MaintenanceRecord": "MaintenanceCreate",
    "StructuredEvent": "StructuredEventCreate",
    "Organization": "OrganizationCreate",
    "AuditLogItem": "AuditLogItem",
    "DraftResponse": "DraftResponse",
    "DiffResponse": "DiffResponse",
    "PublishResponse": "PublishResponse",
    "RollbackResponse": "RollbackResponse",
    "OrgNode": "OrganizationCreate",
    "OrgItem": "OrganizationCreate",
}

SKIP_TS_FIELDS = {
    "[key: string]: unknown",
}

SKIP_PYDANTIC_FIELDS = {
    "tenant_id",
    "created_at",
    "updated_at",
}


def parse_ts_interfaces(content: str) -> dict[str, set[str]]:
    interfaces: dict[str, set[str]] = {}
    for match in TS_INTERFACE_PATTERN.finditer(content):
        name = match.group(1)
        body = match.group(2)
        fields: set[str] = set()
        for field_match in TS_FIELD_PATTERN.finditer(body):
            field_name = field_match.group(1)
            if field_name == "[key":
                continue
            fields.add(field_name)
        interfaces[name] = fields
    return interfaces


def collect_ts_interfaces(frontend_dir: Path) -> dict[str, set[str]]:
    all_interfaces: dict[str, set[str]] = {}

    for rel_path in TS_TYPE_FILES:
        file_path = frontend_dir / rel_path
        if not file_path.exists():
            continue
        content = file_path.read_text(encoding="utf-8", errors="replace")
        interfaces = parse_ts_interfaces(content)
        for name, fields in interfaces.items():
            if name in all_interfaces:
                all_interfaces[name] |= fields
            else:
                all_interfaces[name] = fields

    mobile_api_dir = frontend_dir.parent / MOBILE_TS_API_DIR
    if mobile_api_dir.is_dir():
        for ts_file in mobile_api_dir.glob("*.ts"):
            content = ts_file.read_text(encoding="utf-8", errors="replace")
            interfaces = parse_ts_interfaces(content)
            for name, fields in interfaces.items():
                if name in all_interfaces:
                    all_interfaces[name] |= fields
                else:
                    all_interfaces[name] = fields

    return all_interfaces


def collect_pydantic_models(backend_dir: str) -> dict[str, set[str]]:
    sys.path.insert(0, backend_dir)
    os.chdir(backend_dir)

    pydantic_models: dict[str, set[str]] = {}
    for module_name in PYDANTIC_MODULES:
        try:
            mod = importlib.import_module(module_name)
        except Exception as e:
            print(f"  [DEBUG] skip Pydantic module {module_name}: {e}", file=sys.stderr)
            continue
        from pydantic import BaseModel
        for attr_name in dir(mod):
            attr = getattr(mod, attr_name, None)
            if attr is None:
                continue
            if not isinstance(attr, type):
                continue
            if not issubclass(attr, BaseModel):
                continue
            if attr is BaseModel:
                continue
            if attr_name.startswith("_"):
                continue
            fields = set(attr.model_fields.keys())
            pydantic_models[attr_name] = fields

    return pydantic_models


def check_pair(
    ts_name: str,
    ts_fields: set[str],
    pydantic_name: str,
    pydantic_fields: set[str],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []

    ts_fields_clean = ts_fields - SKIP_TS_FIELDS
    pydantic_fields_clean = (pydantic_fields - SKIP_PYDANTIC_FIELDS) | {"id"}

    ts_only = ts_fields_clean - pydantic_fields_clean
    for field in sorted(ts_only):
        issues.append({
            "level": "ERROR",
            "type": "TS_FIELD_NOT_IN_PYDANTIC",
            "ts_interface": ts_name,
            "pydantic_model": pydantic_name,
            "field": field,
            "message": f"TS {ts_name}.{field} not in Pydantic {pydantic_name}",
        })

    pydantic_only = pydantic_fields_clean - ts_fields_clean
    for field in sorted(pydantic_only):
        if field.startswith("_"):
            continue
        issues.append({
            "level": "WARN",
            "type": "PYDANTIC_FIELD_NOT_IN_TS",
            "ts_interface": ts_name,
            "pydantic_model": pydantic_name,
            "field": field,
            "message": f"Pydantic {pydantic_name}.{field} not in TS {ts_name}",
        })

    return issues


def main() -> int:
    if not AUDIT_ENABLED:
        print("L2 audit: skipped (AUDIT_L2_ENABLED=false)")
        return 0

    parser = argparse.ArgumentParser(description="L2 audit: TS ↔ Pydantic consistency check")
    parser.add_argument("--backend-dir", default=None, help="Backend directory (default: auto-detect)")
    parser.add_argument("--frontend-dir", default=None, help="Frontend directory (default: auto-detect)")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    backend_dir = str(script_dir.parent)
    if args.backend_dir is None:
        backend_candidate = script_dir
        while backend_candidate.parent != backend_candidate:
            if (backend_candidate / "app" / "main.py").exists():
                backend_dir = str(backend_candidate)
                break
            backend_candidate = backend_candidate.parent

    frontend_dir = Path(args.frontend_dir) if args.frontend_dir else None
    if frontend_dir is None:
        backend_path = Path(backend_dir)
        frontend_dir = backend_path.parent / "frontend"
        if not frontend_dir.exists():
            frontend_dir = backend_path / "frontend"

    print(f"L2 audit: backend_dir={backend_dir}")
    print(f"L2 audit: frontend_dir={frontend_dir}")

    print("L2 audit: collecting TypeScript interfaces...")
    ts_interfaces = collect_ts_interfaces(frontend_dir)
    print(f"L2 audit: found {len(ts_interfaces)} TS interfaces")

    print("L2 audit: collecting Pydantic models...")
    pydantic_models = collect_pydantic_models(backend_dir)
    print(f"L2 audit: found {len(pydantic_models)} Pydantic models")

    all_issues: list[dict[str, Any]] = []
    matched = 0

    for ts_name, ts_fields in sorted(ts_interfaces.items()):
        pydantic_name = TS_TO_PYDANTIC_MAP.get(ts_name)
        if pydantic_name is None:
            continue
        pydantic_fields = pydantic_models.get(pydantic_name)
        if pydantic_fields is None:
            continue
        matched += 1
        issues = check_pair(ts_name, ts_fields, pydantic_name, pydantic_fields)
        all_issues.extend(issues)

    error_count = sum(1 for i in all_issues if i["level"] == "ERROR")
    warn_count = sum(1 for i in all_issues if i["level"] == "WARN")

    if all_issues:
        print(f"\nL2 audit: {error_count} errors, {warn_count} warnings across {matched} pairs")
        for issue in all_issues:
            prefix = "ERROR" if issue["level"] == "ERROR" else "WARN"
            print(f"  [{prefix}] {issue['type']}: {issue['message']}")
    else:
        print(f"L2 audit: all {matched} interface pairs passed ✓")

    report_path = Path(backend_dir) / "audit_l2_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_errors": error_count,
            "total_warnings": warn_count,
            "matched_pairs": matched,
            "issues": all_issues,
        }, f, indent=2, ensure_ascii=False)
    print(f"L2 audit: report saved to {report_path}")

    return 1 if error_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())