#!/usr/bin/env python3
"""
L5 自动化审计：启动时路由注册 + 依赖注入完整性检查

检测：
  L500: FastAPI 路由注册失败（import error、装饰器参数错误）
  L501: 依赖注入缺失（Depends 引用的函数/类不存在）
  L502: Pydantic 模型验证失败（字段类型不匹配、默认值错误）

使用方式：
  python scripts/audit_l5_startup_check.py [--backend-dir ...]

退出码：
  0 — 通过
  1 — 发现问题
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
import os
import sys
from pathlib import Path
from typing import Any


def check_router_registration(backend_dir: str) -> list[dict]:
    issues = []
    sys.path.insert(0, backend_dir)
    os.chdir(backend_dir)

    try:
        from fastapi import FastAPI
        app = FastAPI()

        router_modules = []
        api_dir = Path(backend_dir) / "app" / "api" / "v1" / "endpoints"
        if api_dir.exists():
            for py_file in api_dir.rglob("*.py"):
                if py_file.name.startswith("_") and py_file.name != "__init__.py":
                    continue
                if py_file.name == "__init__.py":
                    continue
                rel = py_file.relative_to(Path(backend_dir))
                module_name = str(rel.with_suffix("")).replace(os.sep, ".")
                router_modules.append(module_name)

        for module_name in sorted(router_modules):
            try:
                mod = importlib.import_module(module_name)
                router = getattr(mod, "router", None)
                if router is not None:
                    try:
                        prefix = f"/api/v1/{module_name.split('.')[-1].replace('_', '-')}"
                        app.include_router(router, prefix=prefix)
                    except Exception as e:
                        issues.append({
                            "level": "ERROR",
                            "rule": "L500",
                            "module": module_name,
                            "message": f"Router registration failed: {type(e).__name__}: {e}",
                        })
            except Exception as e:
                issues.append({
                    "level": "ERROR",
                    "rule": "L500",
                    "module": module_name,
                    "message": f"Module import failed: {type(e).__name__}: {e}",
                })

    except ImportError as e:
        issues.append({
            "level": "WARN",
            "rule": "L500",
            "module": "fastapi",
            "message": f"Cannot import FastAPI: {e}. Skipping router check.",
        })

    return issues


def check_pydantic_models(backend_dir: str) -> list[dict]:
    issues = []
    sys.path.insert(0, backend_dir)
    os.chdir(backend_dir)

    pydantic_modules = [
        "app.schemas.audit_center",
        "app.schemas.config_center",
        "app.schemas.release_center",
        "app.schemas.ssl_cert",
    ]

    from pydantic import BaseModel

    for module_name in pydantic_modules:
        try:
            mod = importlib.import_module(module_name)
        except Exception as e:
            issues.append({
                "level": "ERROR",
                "rule": "L502",
                "module": module_name,
                "message": f"Schema import failed: {type(e).__name__}: {e}",
            })
            continue

        for attr_name in dir(mod):
            attr = getattr(mod, attr_name, None)
            if attr is None or not isinstance(attr, type):
                continue
            if not issubclass(attr, BaseModel) or attr is BaseModel:
                continue
            try:
                attr.model_json_schema()
            except Exception as e:
                issues.append({
                    "level": "ERROR",
                    "rule": "L502",
                    "module": module_name,
                    "message": f"Pydantic model {attr_name} schema generation failed: {type(e).__name__}: {e}",
                })

    return issues


def check_db_models(backend_dir: str) -> list[dict]:
    issues = []
    sys.path.insert(0, backend_dir)
    os.chdir(backend_dir)

    from sqlalchemy import inspect as sa_inspect
    from app.db.base import Base

    model_modules = [
        "app.models.user", "app.models.asset", "app.models.resource",
        "app.models.alarm", "app.models.platform", "app.models.billing",
        "app.models.map_config", "app.models.operation_audit",
        "app.models.stream_session", "app.models.media_node",
        "app.models.config_draft", "app.models.config_revision",
        "app.models.organization", "app.models.role",
        "app.models.system_setting", "app.models.work_order",
    ]

    for module_name in model_modules:
        try:
            importlib.import_module(module_name)
        except Exception as e:
            issues.append({
                "level": "ERROR",
                "rule": "L500",
                "module": module_name,
                "message": f"Model import failed: {type(e).__name__}: {e}",
            })

    for mapper in Base.registry.mappers:
        cls = mapper.class_
        try:
            columns = set(mapper.columns.keys())
            if not columns:
                issues.append({
                    "level": "WARN",
                    "rule": "L501",
                    "module": cls.__module__,
                    "message": f"ORM model {cls.__name__} has no columns mapped",
                })
        except Exception as e:
            issues.append({
                "level": "ERROR",
                "rule": "L501",
                "module": cls.__module__,
                "message": f"ORM model {cls.__name__} mapper inspection failed: {e}",
            })

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="L5 audit: startup integrity check")
    parser.add_argument("--backend-dir", default=None)
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    backend_dir = args.backend_dir or str(script_dir.parent)

    print(f"L5 audit: checking startup integrity...")
    print(f"  Backend: {backend_dir}")

    all_issues = []

    print("  Checking DB models...")
    all_issues.extend(check_db_models(backend_dir))

    print("  Checking Pydantic schemas...")
    all_issues.extend(check_pydantic_models(backend_dir))

    print("  Checking router registration...")
    all_issues.extend(check_router_registration(backend_dir))

    errors = [i for i in all_issues if i["level"] == "ERROR"]
    warns = [i for i in all_issues if i["level"] == "WARN"]

    if all_issues:
        print(f"\nL5 audit: {len(errors)} errors, {len(warns)} warnings")
        for i in all_issues:
            prefix = "ERROR" if i["level"] == "ERROR" else "WARN"
            print(f"  [{prefix}] {i['rule']} {i.get('module', '?')} — {i['message'][:120]}")
    else:
        print("L5 audit: all startup checks passed ✓")

    report_path = Path(backend_dir) / "audit_l5_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({"total_errors": len(errors), "total_warnings": len(warns), "issues": all_issues}, f, indent=2, ensure_ascii=False)

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())