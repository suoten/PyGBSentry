from __future__ import annotations

import re
import sys
from pathlib import Path

# 本文件位于 tools/，仓库根目录为上一级
ROOT = Path(__file__).resolve().parents[1]
backend_plugins_dir = ROOT / "backend/plugins"
plugins_api_pkg = ROOT / "backend/app/api/v1/endpoints/plugins"
plugins_api_flat = ROOT / "backend/app/api/v1/endpoints/plugins.py"
plugin_runtime_vue = ROOT / "frontend/src/views/PluginRuntime.vue"

plugin_files = sorted(
    p.stem
    for p in backend_plugins_dir.glob("*.py")
    if p.name != "__init__.py"
)

excluded = {"main_path_ai_suite", "dev_main_path_ai_template"}
plugin_ids = [p for p in plugin_files if p not in excluded]

# 插件 API 可能是单文件 plugins.py 或拆分后的 plugins/ 包，两种形态都兼容
if plugins_api_pkg.is_dir():
    api_text = "\n".join(
        p.read_text(encoding="utf-8") for p in sorted(plugins_api_pkg.glob("*.py"))
    )
else:
    api_text = plugins_api_flat.read_text(encoding="utf-8")
vue_text = plugin_runtime_vue.read_text(encoding="utf-8")

route_ids = set(re.findall(r'@router\.get\("/runtime/([^"/]+)/(?:events|logs|health)"', api_text))
vue_plugin_ids = set(re.findall(r"pluginId\.value === '([^']+)'", vue_text))

missing_api = [p for p in plugin_ids if p not in route_ids]
missing_vue = [p for p in plugin_ids if p not in vue_plugin_ids]

print("=== Runtime Coverage Check ===")
print(f"plugins total: {len(plugin_ids)}")
print(f"api runtime routes: {len(route_ids)}")
print(f"frontend runtime plugin switches: {len(vue_plugin_ids)}")

print("\n[Missing API routes]")
if missing_api:
    for p in missing_api:
        print(" -", p)
else:
    print(" - none")

print("\n[Missing PluginRuntime.vue switches]")
if missing_vue:
    for p in missing_vue:
        print(" -", p)
else:
    print(" - none")

bad_iframe_guards = re.findall(r"if \(pluginId\.value === '([^']+)' && !iframeUrl\.value\)", vue_text)
print("\n[Mounted guards still requiring !iframeUrl]")
if bad_iframe_guards:
    for p in sorted(set(bad_iframe_guards)):
        print(" -", p)
else:
    print(" - none")

has_issue = bool(missing_api or missing_vue or bad_iframe_guards)
if has_issue:
    print("\nResult: FAILED (runtime coverage has gaps)")
    sys.exit(1)

print("\nResult: OK")
