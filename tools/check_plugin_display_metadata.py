from __future__ import annotations

import json
import sys
from pathlib import Path

# 本文件位于 editions/open-source/tools/，仓库根目录为上三级
ROOT = Path(__file__).resolve().parents[3]
BACKEND_PLUGINS = ROOT / "editions/open-source/backend/plugins"
SERVER_PACKAGES = ROOT / "editions/server/backend/plugin_packages"
MARKETPLACE = BACKEND_PLUGINS / "marketplace.json"


def _load_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _plugin_json_for_id(plugin_id: str) -> dict | None:
    local = BACKEND_PLUGINS / plugin_id / "plugin.json"
    meta = _load_json(local)
    if isinstance(meta, dict):
        return meta
    server = SERVER_PACKAGES / plugin_id / "plugin.json"
    meta = _load_json(server)
    return meta if isinstance(meta, dict) else None


def _collect_builtin_plugin_ids() -> list[str]:
    ids: set[str] = set()
    for p in sorted(BACKEND_PLUGINS.glob("*.py")):
        if p.name.startswith("__"):
            continue
        ids.add(p.stem)
    for sub in sorted(BACKEND_PLUGINS.iterdir()):
        if not sub.is_dir():
            continue
        pj = sub / "plugin.json"
        if not pj.exists():
            continue
        data = _load_json(pj)
        if isinstance(data, dict):
            pid = str(data.get("id") or sub.name).strip()
            if pid:
                ids.add(pid)
    return sorted(ids)


def main() -> int:
    raw = _load_json(MARKETPLACE)
    if not isinstance(raw, list):
        print("check_plugin_display_metadata: marketplace.json must be a JSON array", file=sys.stderr)
        return 1

    marketplace_by_id: dict[str, dict] = {}
    for it in raw:
        if not isinstance(it, dict):
            continue
        pid = str(it.get("id") or it.get("plugin_id") or "").strip()
        if pid:
            marketplace_by_id[pid] = it

    errors: list[str] = []

    for stem in sorted(p.stem for p in BACKEND_PLUGINS.glob("*.py") if not p.name.startswith("__")):
        if stem not in marketplace_by_id:
            errors.append(f"P0-1.1: marketplace.json 缺少与 plugins/{stem}.py 对应的条目（id={stem}）")

    for sub in sorted(BACKEND_PLUGINS.iterdir()):
        if not sub.is_dir():
            continue
        pj = sub / "plugin.json"
        if not pj.exists():
            continue
        data = _load_json(pj)
        if not isinstance(data, dict):
            continue
        pkg_id = str(data.get("id") or sub.name).strip()
        if pkg_id and pkg_id not in marketplace_by_id:
            errors.append(
                f"P0-1.1: marketplace.json 缺少与插件包 {sub.name}/plugin.json 对应的条目（id={pkg_id}）"
            )

    for pid in _collect_builtin_plugin_ids():
        meta = _plugin_json_for_id(pid) or {}
        mp = marketplace_by_id.get(pid, {})

        name = (
            (meta.get("name") if isinstance(meta.get("name"), str) else None)
            or (meta.get("title") if isinstance(meta.get("title"), str) else None)
            or (mp.get("name") if isinstance(mp.get("name"), str) else None)
            or (mp.get("title") if isinstance(mp.get("title"), str) else None)
            or ""
        ).strip()

        desc = (
            (meta.get("description") if isinstance(meta.get("description"), str) else None)
            or (mp.get("description") if isinstance(mp.get("description"), str) else None)
            or ""
        ).strip()

        if not name or name == pid:
            errors.append(
                f"P0-1.3: 插件 {pid} 缺少可读名称（plugin.json 与 marketplace 均未提供 name/title，且不能回退为 id）"
            )
        if not desc:
            errors.append(f"P0-1.3: 插件 {pid} 缺少 description（plugin.json 与 marketplace 至少一处需非空）")

    if errors:
        print("=== Plugin display metadata check ===\n")
        for e in errors:
            print(e)
        print(f"\nResult: FAILED ({len(errors)} issue(s))")
        return 1

    print("=== Plugin display metadata check ===")
    print("Result: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
