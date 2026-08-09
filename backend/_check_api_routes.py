#!/usr/bin/env python
"""
准确验证前端 API 调用是否在后端有对应的路由注册。
通过比对 OpenAPI spec 的 path + method，而非实际调用端点。

这样可以避免"资源不存在"导致的 404 误报。
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

BACKEND_URL = "http://127.0.0.1:8000"
FRONTEND_DIR = Path(r"e:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\frontend")
SRC_DIR = FRONTEND_DIR / "src"


def fetch_openapi():
    """获取后端 OpenAPI spec"""
    url = f"{BACKEND_URL}/api/v1/openapi.json"
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def scan_frontend_apis():
    """扫描前端代码中所有 API 调用"""
    api_calls = []  # list of (method, path, file)

    def walk(directory):
        for dirpath, _, filenames in Path(directory).walk if hasattr(Path(directory), 'walk') else [(d, _, f) for d, _, f in os.walk(directory)]:
            for filename in filenames:
                if not re.match(r"\.(ts|vue|js)$", Path(filename).suffix):
                    continue
                filepath = Path(dirpath) / filename
                try:
                    content = filepath.read_text(encoding="utf-8")
                except Exception:
                    continue
                pattern = r"(?:http|api)\.(get|post|put|delete|patch)\(\s*(['\"`])([^'\"`]+)\2"
                for match in re.finditer(pattern, content):
                    method = match.group(1).upper()
                    api_path = match.group(3)
                    if not api_path.startswith("/api/"):
                        continue
                    # 处理动态路径：将 ${xxx} 替换为 {xxx}
                    normalized = re.sub(r"\$\{[^}]+\}", "{id}", api_path)
                    api_calls.append((method, normalized, str(filepath.relative_to(SRC_DIR))))

    import os
    for dirpath, _, filenames in os.walk(str(SRC_DIR)):
        for filename in filenames:
            if not re.match(r"\.(ts|vue|js)$", Path(filename).suffix):
                continue
            filepath = Path(dirpath) / filename
            try:
                content = filepath.read_text(encoding="utf-8")
            except Exception:
                continue
            pattern = r"(?:http|api)\.(get|post|put|delete|patch)\(\s*(['\"`])([^'\"`]+)\2"
            for match in re.finditer(pattern, content):
                method = match.group(1).upper()
                api_path = match.group(3)
                if not api_path.startswith("/api/"):
                    continue
                # 处理动态路径：将 ${xxx} 替换为 {id}
                normalized = re.sub(r"\$\{[^}]+\}", "{id}", api_path)
                api_calls.append((method, normalized, str(filepath.relative_to(SRC_DIR))))

    return api_calls


def main():
    print("=" * 70)
    print("前端 API 调用 vs 后端 OpenAPI 路由对照验证")
    print("=" * 70)

    # 获取 OpenAPI spec
    print("\n[1/2] 获取后端 OpenAPI spec...")
    spec = fetch_openapi()
    paths = spec.get("paths", {})
    print(f"  ✓ 后端注册路由数: {len(paths)}")

    # 扫描前端 API
    print("\n[2/2] 扫描前端 API 调用...")
    api_calls = scan_frontend_apis()
    unique_calls = set((m, p) for m, p, _ in api_calls)
    print(f"  ✓ 前端 API 调用数: {len(api_calls)} (唯一 method+path: {len(unique_calls)})")

    # 验证
    print("\n=== 验证结果 ===\n")
    missing = []
    found = []
    method_mismatch = []

    for method, path in sorted(unique_calls):
        if path in paths:
            # 路径存在，检查方法
            path_item = paths[path]
            method_lower = method.lower()
            if method_lower in path_item:
                found.append((method, path))
            else:
                supported = [m.upper() for m in path_item.keys() if m in ('get', 'post', 'put', 'delete', 'patch')]
                method_mismatch.append((method, path, supported))
        else:
            # 路径不存在
            # 检查是否有类似路径（可能是路径参数命名不同）
            similar = []
            for ep in paths:
                # 将 {xxx} 统一为 {id} 进行比较
                ep_normalized = re.sub(r"\{[^}]+\}", "{id}", ep)
                if ep_normalized == path:
                    similar.append(ep)
            if similar:
                method_mismatch.append((method, path, f"路径参数不同: {similar}"))
            else:
                missing.append((method, path))

    print(f"  ✓ 完全匹配: {len(found)}")
    print(f"  ⚠️ 方法不匹配: {len(method_mismatch)}")
    print(f"  ✗ 路径不存在: {len(missing)}")

    if method_mismatch:
        print("\n=== ⚠️ 方法不匹配（端点存在但方法不同）===")
        for method, path, info in method_mismatch:
            print(f"  {method:6s} {path}")
            print(f"         {info}")

    if missing:
        print("\n=== ✗ 路径不存在（真正的 404）===")
        for method, path in missing:
            # 找出调用这个路径的文件
            files = [f for m, p, f in api_calls if m == method and p == path]
            print(f"  {method:6s} {path}")
            for f in files[:3]:
                print(f"         在: {f}")
    else:
        print("\n✅ 所有前端 API 调用都有对应的后端路由！")

    # 写入报告
    report_path = FRONTEND_DIR / "_api_route_check_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# 前端 API 调用 vs 后端路由对照报告\n\n")
        f.write(f"- 后端注册路由数: {len(paths)}\n")
        f.write(f"- 前端唯一 API 调用数: {len(unique_calls)}\n")
        f.write(f"- ✓ 完全匹配: {len(found)}\n")
        f.write(f"- ⚠️ 方法不匹配: {len(method_mismatch)}\n")
        f.write(f"- ✗ 路径不存在: {len(missing)}\n\n")

        if method_mismatch:
            f.write("## ⚠️ 方法不匹配\n\n")
            f.write("| 方法 | 路径 | 说明 |\n")
            f.write("|------|------|------|\n")
            for method, path, info in method_mismatch:
                f.write(f"| {method} | `{path}` | {info} |\n")

        if missing:
            f.write("\n## ✗ 路径不存在（真正的 404）\n\n")
            f.write("| 方法 | 路径 | 调用文件 |\n")
            f.write("|------|------|----------|\n")
            for method, path in missing:
                files = [f for m, p, f in api_calls if m == method and p == path]
                f.write(f"| {method} | `{path}` | {', '.join(files[:3])} |\n")
        else:
            f.write("\n## ✅ 所有前端 API 调用都有对应的后端路由\n\n")

        f.write("\n## 完全匹配的 API 列表\n\n")
        for method, path in found:
            f.write(f"- ✓ {method} `{path}`\n")

    print(f"\n报告已写入: {report_path}")


if __name__ == "__main__":
    main()
