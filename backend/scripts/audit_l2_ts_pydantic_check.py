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

# 同时匹配 `export interface X { ... }` 与 `export type X = { ... }` 两种声明
TS_INTERFACE_PATTERN = re.compile(
    r"export\s+(?:interface\s+(\w+)\s*|type\s+(\w+)\s*=\s*)\{([^}]*(?:\{[^}]*\}[^}]*)*)\}",
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
    "app.api.v1.endpoints.devices.devices_crud",
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

# TS 接口 → Pydantic 响应模型配对表。
# 配对原则：只配对"前端展示接口 ↔ 后端实际作为响应契约的模型"。
# 请求载荷（Create/Update/Query）不是响应契约，不得出现在此表中；
# 端点返回手写 dict 且无响应模型的领域暂不配对（避免假阳性）。
TS_TO_PYDANTIC_MAP: dict[str, str] = {
    # 响应模型配对（response_model 强制契约）
    "Device": "DeviceItem",            # GET /api/v1/devices
    "Alarm": "AlarmItem",              # GET /api/v1/alarms
    "CascadePlatform": "PlatformItem", # GET /api/v1/platforms
    "AuditLogItem": "AuditLogItem",    # GET /api/v1/audit-center/logs
    "DraftResponse": "DraftResponse",
    "DiffResponse": "DiffResponse",
    "PublishResponse": "PublishResponse",
    "RollbackResponse": "RollbackResponse",
}

SKIP_TS_FIELDS = {
    "[key: string]: unknown",
}


def parse_ts_interfaces(content: str) -> dict[str, set[str]]:
    interfaces: dict[str, set[str]] = {}
    for match in TS_INTERFACE_PATTERN.finditer(content):
        name = match.group(1) or match.group(2)
        body = match.group(3)
        # 剥离索引签名（如 `[key: string]: unknown`），
        # 防止其中的 `key` 被 TS_FIELD_PATTERN 误识别为数据字段。
        # 停止字符含逗号，避免单行接口写法误吞后续字段。
        body = re.sub(r"\[\s*\w+\s*:\s*string\s*\]\s*:\s*[^\n;,]+", " ", body)
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

    # 干净对比：不做任何字段剔除或补全。
    # 旧行为（从 Pydantic 侧剔除 created_at/updated_at/tenant_id 并补 id）
    # 会在 TS 合法持有这些字段时产生假阳性 ERROR，并掩盖真实缺失的 id。
    ts_fields_clean = ts_fields - SKIP_TS_FIELDS
    pydantic_fields_clean = set(pydantic_fields)

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

    for ts_name, pydantic_name in sorted(TS_TO_PYDANTIC_MAP.items()):
        ts_fields = ts_interfaces.get(ts_name)
        if ts_fields is None:
            # 配对声明的 TS 接口不存在（改名/删除）— 静默跳过会造成检测缺口
            all_issues.append({
                "level": "WARN",
                "type": "PAIR_TS_NOT_FOUND",
                "ts_interface": ts_name,
                "pydantic_model": pydantic_name,
                "field": "",
                "message": f"TS interface {ts_name} declared in TS_TO_PYDANTIC_MAP not found in frontend sources — pair check skipped",
            })
            continue
        pydantic_fields = pydantic_models.get(pydantic_name)
        if pydantic_fields is None:
            all_issues.append({
                "level": "WARN",
                "type": "PAIR_PYDANTIC_NOT_FOUND",
                "ts_interface": ts_name,
                "pydantic_model": pydantic_name,
                "field": "",
                "message": f"Pydantic model {pydantic_name} declared in TS_TO_PYDANTIC_MAP not importable — pair check skipped",
            })
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
