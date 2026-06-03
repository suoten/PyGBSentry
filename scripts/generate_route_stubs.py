"""
路由桩自动生成脚本。
读取 check-report-r4.md 中前端缺失路由，去重后生成开源版/服务器版路由桩文件。
用法: python scripts/generate_route_stubs.py
"""
import re
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REPORT_PATH = os.path.join(PROJECT_ROOT, "check-report-r4.md")


def normalize_path(raw_path: str) -> tuple[str, str]:
    method = ""
    path = raw_path.strip().strip("`")
    js_template_re = re.compile(r"\$\{[^}]+\}")
    path = js_template_re.sub("{id}", path)
    path = re.sub(r"\?[^}]*$", "", path)
    path = re.sub(r"/+", "/", path)
    for m in ("GET", "POST", "PUT", "DELETE", "PATCH"):
        if path.startswith(m + " "):
            method = m
            path = path[len(m):].strip()
            break
    return method, path


def parse_report(report_path: str) -> list[tuple[str, str]]:
    routes = []
    if not os.path.exists(report_path):
        print(f"报告文件不存在: {report_path}")
        return routes
    with open(report_path, "r", encoding="utf-8") as f:
        for line in f:
            m = re.match(r"\|\s*\d+\s*\|\s*(GET|POST|PUT|DELETE|PATCH)\s*\|\s*`([^`]+)`", line)
            if m:
                method = m.group(1)
                raw_path = m.group(2)
                _, norm_path = normalize_path(raw_path)
                if norm_path.startswith("/api/common/"):
                    continue
                routes.append((method, norm_path))
    seen = set()
    unique = []
    for method, path in routes:
        key = (method, path)
        if key not in seen:
            seen.add(key)
            unique.append((method, path))
    return unique


def prefix_to_module(prefix: str) -> str:
    seg = prefix.strip("/").split("/")[0] if prefix else "root"
    return seg.replace("-", "_") or "root"


def generate_stub_file(routes: list[tuple[str, str]], edition: str) -> str:
    lines = [
        '"""',
        f'路由桩（{edition}版）— 自动生成，请勿手动修改。',
        '所有路由返回 501 Not Implemented + deprecated 标记。',
        '"""',
        'from fastapi import APIRouter, HTTPException',
        '',
        'router = APIRouter(tags=["stubs"])',
        '',
        '',
        'async def _stub(path: str, method: str, note: str = ""):',
        '    """路由桩工厂：统一返回 501"""',
        '    raise HTTPException(status_code=501, detail=f"此端点尚未实现: {method} {path} {note}")',
        '',
        '',
    ]
    for i, (method, path) in enumerate(routes, 1):
        func_name = re.sub(r"[^a-zA-Z0-9_]", "_", f"stub_{method.lower()}_{path.strip('/')}").strip("_")
        while "__" in func_name:
            func_name = func_name.replace("__", "_")
        if len(func_name) > 80:
            func_name = f"stub_{edition}_{i}"
        decorator_method = method.lower()
        lines.append(f'@router.{decorator_method}("{path}", deprecated=True)')
        lines.append(f"async def {func_name}():")
        lines.append(f'    """[STUB] TODO: 实现此端点 — {method} {path}"""')
        lines.append(f'    raise HTTPException(status_code=501, detail="此端点尚未实现")')
        lines.append("")
        lines.append("")
    return "\n".join(lines)


def main():
    routes = parse_report(REPORT_PATH)
    print(f"从报告解析到 {len(routes)} 个唯一缺失路由")

    oss_routes = routes
    server_routes = [(m, p) for m, p in routes if not p.startswith("/billing") and not p.startswith("/developer") and not p.startswith("/plugins/webhooks")]

    oss_content = generate_stub_file(oss_routes, "oss")
    oss_path = os.path.join(PROJECT_ROOT, "editions", "open-source", "backend", "app", "api", "v1", "endpoints", "_route_stubs_oss.py")
    with open(oss_path, "w", encoding="utf-8") as f:
        f.write(oss_content)
    print(f"已生成开源版路由桩: {oss_path} ({len(oss_routes)} 路由)")

    server_content = generate_stub_file(server_routes, "server")
    server_path = os.path.join(PROJECT_ROOT, "editions", "server", "backend", "app", "api", "v1", "endpoints", "_route_stubs_server.py")
    with open(server_path, "w", encoding="utf-8") as f:
        f.write(server_content)
    print(f"已生成服务器版路由桩: {server_path} ({len(server_routes)} 路由)")

    print("完成！请手动在对应 api.py 中添加 include_router 注册。")


if __name__ == "__main__":
    main()
