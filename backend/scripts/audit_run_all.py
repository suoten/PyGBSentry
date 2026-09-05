#!/usr/bin/env python3
"""
PyGBSentry 自动化审计统一入口

运行全部5层审计：
  L1 — Pydantic 模型 ↔ ORM 列名对照检测（启动时自检）
  L2 — 前端 TypeScript 接口 ↔ Pydantic Response 对照（CI 阶段）
  L3 — 异常处理模式扫描（lint 规则）
  L4 — 运行时崩溃风险扫描（资源泄漏、事件循环阻塞、fire-and-forget）
  L5 — 启动时完整性检查（路由注册、模型验证、依赖注入）

使用方式：
  python scripts/audit_run_all.py [--layer 1|2|3|4|5|all] [--strict] [--ci]

退出码：
  0 — 全部通过
  1 — 发现 error 级别问题
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

AUDIT_REPORT_DIR = Path(__file__).resolve().parent.parent / "audit_reports"


def run_l1(backend_dir: Path, strict: bool = False) -> dict:
    if strict:
        os.environ["AUDIT_L1_STRICT"] = "true"
    os.environ["AUDIT_L1_ENABLED"] = "true"

    sys.path.insert(0, str(backend_dir))
    os.chdir(str(backend_dir))

    try:
        from app.core.audit_l1_schema_consistency import run_l1_audit_sync_safe
        issues = run_l1_audit_sync_safe()
    except Exception as e:
        return {"layer": "L1", "status": "error", "message": str(e), "issues": []}

    errors = [i for i in issues if i.get("level") == "ERROR"]
    warnings = [i for i in issues if i.get("level") == "WARN"]

    return {
        "layer": "L1",
        "status": "fail" if errors else "pass",
        "total_errors": len(errors),
        "total_warnings": len(warnings),
        "issues": issues,
    }


def run_l2(backend_dir: Path, frontend_dir: Path) -> dict:
    os.environ["AUDIT_L2_ENABLED"] = "true"

    script_path = backend_dir / "scripts" / "audit_l2_ts_pydantic_check.py"
    if not script_path.exists():
        return {"layer": "L2", "status": "skip", "message": f"Script not found: {script_path}", "issues": []}

    import subprocess
    result = subprocess.run(
        [sys.executable, str(script_path), "--backend-dir", str(backend_dir), "--frontend-dir", str(frontend_dir)],
        capture_output=True, text=True, timeout=60,
    )

    report_path = backend_dir / "audit_l2_report.json"
    report = {}
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    return {
        "layer": "L2",
        "status": "fail" if result.returncode != 0 else "pass",
        "total_errors": report.get("total_errors", 0),
        "total_warnings": report.get("total_warnings", 0),
        "issues": report.get("issues", []),
        "stdout": result.stdout[-500:] if result.stdout else "",
        "stderr": result.stderr[-500:] if result.stderr else "",
    }


def run_l3(backend_dir: Path, severity: str = "all") -> dict:
    os.environ["AUDIT_L3_ENABLED"] = "true"

    script_path = backend_dir / "scripts" / "audit_l3_exception_pattern_scan.py"
    if not script_path.exists():
        return {"layer": "L3", "status": "skip", "message": f"Script not found: {script_path}", "issues": []}

    import subprocess
    args = [sys.executable, str(script_path), "--src-dir", str(backend_dir / "app"), "--severity", severity]
    result = subprocess.run(args, capture_output=True, text=True, timeout=120)

    report_path = backend_dir / "audit_l3_report.json"
    report = {}
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    return {
        "layer": "L3",
        "status": "fail" if result.returncode != 0 else "pass",
        "total_errors": report.get("total_errors", 0),
        "total_warnings": report.get("total_warnings", 0),
        "issues": report.get("findings", []),
        "stdout": result.stdout[-500:] if result.stdout else "",
        "stderr": result.stderr[-500:] if result.stderr else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="PyGBSentry automated audit runner")
    parser.add_argument("--layer", choices=["1", "2", "3", "4", "5", "all"], default="all", help="Which audit layer(s) to run")
    parser.add_argument("--strict", action="store_true", help="Enable strict mode (L1: check ORM→Pydantic too)")
    parser.add_argument("--ci", action="store_true", help="CI mode: save reports to audit_reports/")
    parser.add_argument("--backend-dir", default=None, help="Backend directory")
    parser.add_argument("--frontend-dir", default=None, help="Frontend directory")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    backend_dir = Path(args.backend_dir) if args.backend_dir else script_dir.parent
    frontend_dir = Path(args.frontend_dir) if args.frontend_dir else backend_dir.parent / "frontend"

    print("=" * 60)
    print("PyGBSentry Automated Audit")
    print("=" * 60)
    print(f"Backend:  {backend_dir}")
    print(f"Frontend: {frontend_dir}")
    print(f"Layers:   {args.layer}")
    print(f"Strict:   {args.strict}")
    print()

    results: list[dict] = []
    total_errors = 0
    total_warnings = 0

    if args.layer in ("1", "all"):
        print("─" * 40)
        print("L1: Pydantic ↔ ORM Column Consistency Check")
        print("─" * 40)
        r = run_l1(backend_dir, strict=args.strict)
        results.append(r)
        total_errors += r.get("total_errors", 0)
        total_warnings += r.get("total_warnings", 0)
        print(f"  Status: {r['status']} | Errors: {r.get('total_errors', 0)} | Warnings: {r.get('total_warnings', 0)}")
        for issue in r.get("issues", [])[:10]:
            print(f"  [{issue.get('level', '?')}] {issue.get('message', '')}")
        if len(r.get("issues", [])) > 10:
            print(f"  ... and {len(r['issues']) - 10} more")
        print()

    if args.layer in ("2", "all"):
        print("─" * 40)
        print("L2: TypeScript ↔ Pydantic Response Consistency Check")
        print("─" * 40)
        r = run_l2(backend_dir, frontend_dir)
        results.append(r)
        total_errors += r.get("total_errors", 0)
        total_warnings += r.get("total_warnings", 0)
        print(f"  Status: {r['status']} | Errors: {r.get('total_errors', 0)} | Warnings: {r.get('total_warnings', 0)}")
        for issue in r.get("issues", [])[:10]:
            print(f"  [{issue.get('level', '?')}] {issue.get('message', '')}")
        if len(r.get("issues", [])) > 10:
            print(f"  ... and {len(r['issues']) - 10} more")
        print()

    if args.layer in ("3", "all"):
        print("─" * 40)
        print("L3: Exception Pattern Scan")
        print("─" * 40)
        r = run_l3(backend_dir)
        results.append(r)
        total_errors += r.get("total_errors", 0)
        total_warnings += r.get("total_warnings", 0)
        print(f"  Status: {r['status']} | Errors: {r.get('total_errors', 0)} | Warnings: {r.get('total_warnings', 0)}")
        for issue in r.get("issues", [])[:10]:
            print(f"  [{issue.get('level', '?')}] {issue.get('rule', '')} {issue.get('file', '')}:{issue.get('line', '')} — {issue.get('message', '')}")
        if len(r.get("issues", [])) > 10:
            print(f"  ... and {len(r['issues']) - 10} more")
        print()

    if args.layer in ("4", "all"):
        print("─" * 40)
        print("L4: Runtime Crash Risk Scan")
        print("─" * 40)
        os.environ["AUDIT_L4_ENABLED"] = "true"
        script_path = backend_dir / "scripts" / "audit_l4_runtime_crash_scan.py"
        if script_path.exists():
            import subprocess as _sp
            _l4_result = _sp.run(
                [sys.executable, str(script_path), "--src-dir", str(backend_dir / "app"), "--severity", "error"],
                capture_output=True, text=True, timeout=60,
            )
            report_path = backend_dir / "audit_l4_report.json"
            report = {}
            if report_path.exists():
                try:
                    report = json.loads(report_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
            r = {
                "layer": "L4",
                "status": "fail" if _l4_result.returncode != 0 else "pass",
                "total_errors": report.get("total_errors", 0),
                "total_warnings": report.get("total_warnings", 0),
                "issues": report.get("findings", []),
            }
            results.append(r)
            total_errors += r.get("total_errors", 0)
            total_warnings += r.get("total_warnings", 0)
            print(f"  Status: {r['status']} | Errors: {r.get('total_errors', 0)} | Warnings: {r.get('total_warnings', 0)}")
            for issue in r.get("issues", [])[:10]:
                print(f"  [{issue.get('level', '?')}] {issue.get('rule', '')} {issue.get('file', '')}:{issue.get('line', '')} — {issue.get('message', '')[:80]}")
            if len(r.get("issues", [])) > 10:
                print(f"  ... and {len(r['issues']) - 10} more")
        else:
            print("  SKIP: L4 script not found")
        print()

    if args.layer in ("5", "all"):
        print("─" * 40)
        print("L5: Startup Integrity Check")
        print("─" * 40)
        script_path = backend_dir / "scripts" / "audit_l5_startup_check.py"
        if script_path.exists():
            import subprocess as _sp
            _l5_result = _sp.run(
                [sys.executable, str(script_path), "--backend-dir", str(backend_dir)],
                capture_output=True, text=True, timeout=60,
            )
            report_path = backend_dir / "audit_l5_report.json"
            report = {}
            if report_path.exists():
                try:
                    report = json.loads(report_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
            r = {
                "layer": "L5",
                "status": "fail" if _l5_result.returncode != 0 else "pass",
                "total_errors": report.get("total_errors", 0),
                "total_warnings": report.get("total_warnings", 0),
                "issues": report.get("issues", []),
            }
            results.append(r)
            total_errors += r.get("total_errors", 0)
            total_warnings += r.get("total_warnings", 0)
            print(f"  Status: {r['status']} | Errors: {r.get('total_errors', 0)} | Warnings: {r.get('total_warnings', 0)}")
            for issue in r.get("issues", [])[:10]:
                print(f"  [{issue.get('level', '?')}] {issue.get('rule', '')} {issue.get('module', '')} — {issue.get('message', '')[:80]}")
        else:
            print("  SKIP: L5 script not found")
        print()

    print("=" * 60)
    print(f"TOTAL: {total_errors} errors, {total_warnings} warnings")
    print("=" * 60)

    if args.ci:
        AUDIT_REPORT_DIR.mkdir(parents=True, exist_ok=True)
        report_path = AUDIT_REPORT_DIR / "audit_full_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump({
                "total_errors": total_errors,
                "total_warnings": total_warnings,
                "results": results,
            }, f, indent=2, ensure_ascii=False)
        print(f"Report saved to {report_path}")

    return 1 if total_errors > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
