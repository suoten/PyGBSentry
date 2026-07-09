#!/usr/bin/env python
"""P2-33: 导出 FastAPI OpenAPI 规范到 docs/openapi.json。

用法：
    python tools/export_openapi.py [--output docs/openapi.json]

此脚本从 app.main:app 提取 OpenAPI 3.0 规范，用于：
1. 文档版本与代码版本绑定（openapi.json 的 info.version 与 PROJECT_VERSION 一致）
2. docs/api.md 可基于 openapi.json 自动生成
3. 前端可基于 openapi.json 生成 TypeScript 客户端
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def export_openapi(output_path: str) -> int:
    """导出 OpenAPI 规范到指定路径。

    Returns:
        0 成功，1 失败。
    """
    # 确保能导入 app 模块
    backend_dir = Path(__file__).resolve().parent.parent / "backend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    try:
        from app.main import app
        from app.core.config import settings
    except Exception as e:
        print(f"ERROR: 无法导入 app: {e}", file=sys.stderr)
        return 1

    # 提取 OpenAPI 规范
    openapi_spec = app.openapi()

    # P2-33: 绑定代码版本到文档版本
    project_version = getattr(settings, "PROJECT_VERSION", "1.0.0")
    if "info" not in openapi_spec:
        openapi_spec["info"] = {}
    openapi_spec["info"]["version"] = project_version

    # 写入文件
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(openapi_spec, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"OpenAPI spec exported to {output} (version={project_version})")
    print(f"  Paths: {len(openapi_spec.get('paths', {}))}")
    print(f"  Schemas: {len(openapi_spec.get('components', {}).get('schemas', {}))}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="导出 FastAPI OpenAPI 规范")
    parser.add_argument(
        "--output", "-o",
        default="docs/openapi.json",
        help="输出文件路径（默认: docs/openapi.json）",
    )
    args = parser.parse_args()
    return export_openapi(args.output)


if __name__ == "__main__":
    sys.exit(main())
