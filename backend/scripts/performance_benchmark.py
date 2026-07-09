"""PyGBSentry 性能压测脚本。

测试核心 API 端点的响应时间和并发处理能力。
使用方式：python scripts/performance_benchmark.py [--base-url http://localhost:8000] [--token YOUR_TOKEN]
"""
import asyncio
import time
import argparse
import httpx
import json
from typing import Any


async def benchmark_single(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    headers: dict,
    **kwargs,
) -> dict[str, Any]:
    """执行单次请求并返回耗时。"""
    start = time.perf_counter()
    try:
        resp = await client.request(method, url, headers=headers, **kwargs)
        elapsed = (time.perf_counter() - start) * 1000  # ms
        return {
            "url": url,
            "method": method,
            "status": resp.status_code,
            "elapsed_ms": round(elapsed, 2),
            "success": 200 <= resp.status_code < 400,
        }
    except Exception as e:
        elapsed = (time.perf_counter() - start) * 1000
        return {
            "url": url,
            "method": method,
            "status": 0,
            "elapsed_ms": round(elapsed, 2),
            "success": False,
            "error": str(e)[:100],
        }


async def benchmark_concurrent(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    headers: dict,
    concurrency: int = 10,
    total: int = 100,
    **kwargs,
) -> dict[str, Any]:
    """并发压测。"""
    semaphore = asyncio.Semaphore(concurrency)
    results: list[dict[str, Any]] = []

    async def _run():
        async with semaphore:
            return await benchmark_single(client, method, url, headers, **kwargs)

    tasks = [_run() for _ in range(total)]
    results = await asyncio.gather(*tasks)

    elapsed_times = [r["elapsed_ms"] for r in results if r["success"]]
    success_count = sum(1 for r in results if r["success"])

    if not elapsed_times:
        return {
            "url": url,
            "concurrency": concurrency,
            "total": total,
            "success": 0,
            "fail": total,
            "avg_ms": 0,
            "p50_ms": 0,
            "p95_ms": 0,
            "p99_ms": 0,
            "qps": 0,
        }

    elapsed_times.sort()
    n = len(elapsed_times)
    total_time = max(elapsed_times) / 1000  # seconds

    return {
        "url": url,
        "concurrency": concurrency,
        "total": total,
        "success": success_count,
        "fail": total - success_count,
        "avg_ms": round(sum(elapsed_times) / n, 2),
        "p50_ms": round(elapsed_times[n // 2], 2),
        "p95_ms": round(elapsed_times[int(n * 0.95)], 2),
        "p99_ms": round(elapsed_times[min(int(n * 0.99), n - 1)], 2),
        "qps": round(success_count / total_time, 1) if total_time > 0 else 0,
    }


async def main():
    parser = argparse.ArgumentParser(description="PyGBSentry Performance Benchmark")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Base URL")
    parser.add_argument("--token", default="", help="Auth token")
    parser.add_argument("--concurrency", type=int, default=10, help="Concurrency level")
    parser.add_argument("--total", type=int, default=50, help="Total requests per endpoint")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {args.token}"} if args.token else {}

    endpoints = [
        ("GET", "/api/v1/health/liveness"),
        ("GET", "/api/v1/ops/db-check"),
        ("GET", "/api/v1/health/overview"),
        ("GET", "/api/v1/ops/status"),
        ("GET", "/api/v1/network/summary"),
        ("GET", "/api/v1/metrics/devices-overview"),
    ]

    print(f"\n{'='*80}")
    print(f"PyGBSentry Performance Benchmark")
    print(f"Base URL: {base_url}")
    print(f"Concurrency: {args.concurrency} | Total per endpoint: {args.total}")
    print(f"{'='*80}\n")

    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        # Single request warm-up
        print("--- Warm-up (single request) ---")
        for method, path in endpoints:
            result = await benchmark_single(client, method, path, headers)
            status = "OK" if result["success"] else "FAIL"
            print(f"  [{status}] {method} {path} → {result['status']} ({result['elapsed_ms']:.1f}ms)")

        # Concurrent benchmark
        print(f"\n--- Concurrent Benchmark (C={args.concurrency}, N={args.total}) ---")
        all_results = []
        for method, path in endpoints:
            result = await benchmark_concurrent(
                client, method, path, headers,
                concurrency=args.concurrency,
                total=args.total,
            )
            all_results.append(result)
            print(f"\n  {method} {path}")
            print(f"    Success: {result['success']}/{result['total']}")
            print(f"    Latency: avg={result['avg_ms']}ms p50={result['p50_ms']}ms p95={result['p95_ms']}ms p99={result['p99_ms']}ms")
            print(f"    QPS: {result['qps']}")

    # Summary
    print(f"\n{'='*80}")
    print("Summary:")
    print(f"{'Endpoint':<45} {'QPS':>8} {'P95(ms)':>10} {'Success':>10}")
    print(f"{'-'*80}")
    for r in all_results:
        endpoint = f"{r['url']}"
        print(f"{endpoint:<45} {r['qps']:>8.1f} {r['p95_ms']:>10} {r['success']:>5}/{r['total']}")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    asyncio.run(main())
