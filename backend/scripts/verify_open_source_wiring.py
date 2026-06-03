#!/usr/bin/env python3
"""
校验开源版「模型注册 / 入口一致性」，避免只加模型文件却未加入 model_registry 导致 create_all 缺表。

用法（在 backend 目录）:
  python scripts/verify_open_source_wiring.py
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _model_modules_from_filesystem() -> set[str]:
    models_dir = PROJECT_ROOT / "app" / "models"
    out: set[str] = set()
    for p in sorted(models_dir.glob("*.py")):
        if p.name.startswith("_"):
            continue
        if p.name == "__init__.py":
            continue
        stem = p.stem
        out.add(f"app.models.{stem}")
    return out


def _model_modules_from_registry_source() -> set[str]:
    reg_path = PROJECT_ROOT / "app" / "db" / "model_registry.py"
    tree = ast.parse(reg_path.read_text(encoding="utf-8"), filename=str(reg_path))
    modules: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "_MODEL_MODULES":
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                modules.add(elt.value)
    return modules


def main() -> int:
    fs = _model_modules_from_filesystem()
    reg = _model_modules_from_registry_source()
    missing_in_reg = sorted(fs - reg)
    extra_in_reg = sorted(reg - fs)

    ok = True
    if missing_in_reg:
        ok = False
        print("[FAIL] app/models 中存在但未列入 app/db/model_registry.py 的模块:")
        for m in missing_in_reg:
            print(f"  - {m}")
    if extra_in_reg:
        ok = False
        print("[FAIL] model_registry 中列出但 app/models 无对应文件的模块:")
        for m in extra_in_reg:
            print(f"  - {m}")
    if ok:
        print(f"[OK] model_registry 与 app/models 一致（共 {len(fs)} 个模型模块）。")

    # 轻量检查：关键入口是否引用 registry
    schema_path = PROJECT_ROOT / "app" / "services" / "schema_upgrade.py"
    init_path = PROJECT_ROOT / "app" / "initial_data.py"
    for label, path in (
        ("schema_upgrade", schema_path),
        ("initial_data", init_path),
    ):
        text = path.read_text(encoding="utf-8")
        if "ensure_model_registry_loaded" not in text:
            print(f"[WARN] {label} 未调用 ensure_model_registry_loaded，可能导致 Base.metadata 不完整。")
            ok = False

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
