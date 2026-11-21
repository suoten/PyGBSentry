"""API 契约稳定性测试(ROADMAP Phase2:API 契约稳定承诺)。

契约口径(**只增不减**):``tests/api_contract_baseline.json`` 记录的每个 /api/v1
端点(path + method)必须仍然存在——删除端点或变更 HTTP 方法会使本测试失败;
新增端点不受影响(向后兼容的演进)。

有意做破坏性变更时:运行 ``python scripts/update_api_contract_baseline.py`` 刷新基线,
并在 CHANGELOG 的破坏性变更清单中公告。

PyGBSentry 通过登录鉴权与 HMAC 播放令牌对调用方承诺:基线内的端点在 minor 版本内
保持路径、方法与语义不变;字段级演进遵循"只加不改不删"。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
BASELINE_PATH = BACKEND_DIR / "tests" / "api_contract_baseline.json"
PREFIX = "/api/v1"


def _extract_contract(app) -> dict[str, list[str]]:
    schema = app.openapi()
    contract: dict[str, list[str]] = {}
    for path, methods in schema.get("paths", {}).items():
        if not path.startswith(PREFIX):
            continue
        allowed = {m for m in methods.keys() if m.lower() in {"get", "post", "put", "delete", "patch"}}
        if allowed:
            contract[path] = sorted(allowed)
    return contract


def _check_no_removals(baseline: dict[str, list[str]], current: dict[str, list[str]]) -> list[str]:
    """返回破坏性变更清单(端点删除 / 方法移除);空列表=契约完好。

    抽成纯函数以便在 CI 中对守卫本身做负向单测(不必真实移除应用路由)。
    """
    regressions: list[str] = []
    for path in sorted(baseline):
        methods = baseline[path]
        if path not in current:
            regressions.append(f"{path}: 端点已删除")
            continue
        missing = sorted(set(methods) - set(current[path]))
        if missing:
            regressions.append(f"{path}: 方法被移除 -{','.join(m.upper() for m in missing)}")
    return regressions


def test_removal_detection_logic() -> None:
    """负向单测:守卫必须能抓住"端点删除"与"方法移除"两类破坏。"""
    baseline = {
        "/api/v1/alpha": ["get"],
        "/api/v1/beta": ["get", "post"],
    }
    # 完好 → 空
    assert _check_no_removals(baseline, {**baseline}) == []
    # 端点删除 → 必须检出
    current = {k: v for k, v in baseline.items() if k != "/api/v1/alpha"}
    assert _check_no_removals(baseline, current) == ["/api/v1/alpha: 端点已删除"]
    # 方法移除 → 必须检出
    current2 = {"/api/v1/alpha": ["get"], "/api/v1/beta": ["get"]}
    assert _check_no_removals(baseline, current2) == ["/api/v1/beta: 方法被移除 -POST"]
    # 新增端点 → 不算破坏(只增不减口径)
    current3 = {**baseline, "/api/v1/gamma": ["get"]}
    assert _check_no_removals(baseline, current3) == []


def test_api_contract_no_removals(app) -> None:
    """基线中的每个端点必须仍然存在,且 HTTP 方法不被移除。"""
    if not BASELINE_PATH.exists():
        pytest.fail(
            "API 契约基线缺失:请运行 `python scripts/update_api_contract_baseline.py` 生成 "
            "tests/api_contract_baseline.json"
        )
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    current = _extract_contract(app)

    regressions = _check_no_removals(baseline, current)
    assert not regressions, (
        "检测到破坏性变更(已发布端点被删除或方法被移除,禁止): "
        f"{regressions}\n"
        "如确属有意废弃,请先公告弃用周期,再运行 "
        "`python scripts/update_api_contract_baseline.py` 刷新基线并在 CHANGELOG 记录。"
    )


def test_api_contract_baseline_wellformed() -> None:
    """基线文件本身可解析、路径均在 /api/v1 下、方法合法。"""
    if not BASELINE_PATH.exists():
        pytest.skip("baseline missing (regenerate first)")
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    assert isinstance(baseline, dict) and baseline, "baseline must be a non-empty dict"
    legal = {"get", "post", "put", "delete", "patch"}
    for path, methods in baseline.items():
        assert path.startswith(PREFIX), f"non /api/v1 path in baseline: {path}"
        assert methods and set(methods) <= legal, f"illegal methods for {path}: {methods}"
