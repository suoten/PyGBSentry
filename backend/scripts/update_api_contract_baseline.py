"""更新 API 契约基线(ROADMAP Phase2:API 契约稳定承诺)。

用法(在 backend/ 目录):
    python scripts/update_api_contract_baseline.py

生成 ``tests/api_contract_baseline.json``:记录 /api/v1 下全部 path → method 集合。
test_api_contract.py 以"只增不减"口径校验——已发布端点被删除或方法变更会使 CI 失败,
新增端点不受影响。**有意做破坏性变更时**(大版本、已公告弃用),运行本脚本刷新基线,
并在 CHANGELOG 中记录破坏性变更清单。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

# 与 tests/conftest.py 相同的环境兜底,保证 app 可导入
os.environ.setdefault("DATABASE_TYPE", "sqlite")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-not-for-production")

import app.main  # noqa: E402

BASELINE_PATH = BACKEND_DIR / "tests" / "api_contract_baseline.json"
PREFIX = "/api/v1"


def extract_contract() -> dict[str, list[str]]:
    """从 OpenAPI schema 提取 /api/v1 下 path → 排序后的 method 列表。"""
    schema = app.main.app.openapi()
    contract: dict[str, list[str]] = {}
    for path, methods in schema.get("paths", {}).items():
        if not path.startswith(PREFIX):
            continue
        allowed = {m for m in methods.keys() if m.lower() in {"get", "post", "put", "delete", "patch"}}
        if allowed:
            contract[path] = sorted(allowed)
    return dict(sorted(contract.items()))


def main() -> None:
    contract = extract_contract()
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(contract, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    endpoints = sum(len(v) for v in contract.values())
    print(f"baseline updated: {BASELINE_PATH}")
    print(f"paths={len(contract)} endpoints={endpoints} (scope: {PREFIX})")


if __name__ == "__main__":
    main()
