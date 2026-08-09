"""列出所有已注册的 API 端点，用于验证前端调用是否会 404。"""
import asyncio
import json
from app.main import app

paths = {}
for route in app.routes:
    if hasattr(route, 'methods') and hasattr(route, 'path'):
        for method in route.methods:
            if method in ('GET', 'POST', 'PUT', 'DELETE', 'PATCH'):
                paths.setdefault(route.path, []).append(method)

# 输出所有路径（按字母排序）
sorted_paths = sorted(paths.keys())
print(f"Total endpoints: {len(sorted_paths)}")
for p in sorted_paths:
    methods = ','.join(sorted(paths[p]))
    print(f"{methods:20s} {p}")

# 写入文件供后续分析
with open('_api_endpoints.json', 'w', encoding='utf-8') as f:
    json.dump({p: sorted(paths[p]) for p in sorted_paths}, f, ensure_ascii=False, indent=2)
