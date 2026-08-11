#!/usr/bin/env python3
"""PyGBSentry 运行时冒烟测试 — 验证核心 API 可达性。

用法:
    python tools/smoke_test.py                    # 默认 http://localhost:8000
    python tools/smoke_test.py --host 192.168.1.100 --port 8000
"""
import argparse
import asyncio
import sys

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(2)


async def main(host: str, port: int) -> None:
    base_url = f"http://{host}:{port}"
    async with httpx.AsyncClient(base_url=base_url, timeout=5) as c:
        tests = [
            ("GET", "/api/v1/health/", None),
            ("GET", "/api/v1/docs", None),
            ("GET", "/openapi.json", None),
        ]
        passed = 0
        for method, path, body in tests:
            try:
                r = await c.request(method, path)
                if r.status_code < 500:
                    print(f"[PASS] {method} {path} -> {r.status_code}")
                    passed += 1
                else:
                    print(f"[FAIL] {method} {path} -> {r.status_code}")
            except Exception as e:
                print(f"[FAIL] {method} {path} -> {e}")

        print(f"\n{passed}/{len(tests)} passed")
        sys.exit(0 if passed == len(tests) else 1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PyGBSentry smoke test")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    asyncio.run(main(args.host, args.port))
