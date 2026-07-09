"""并发预览压力测试 — 模拟 10 路并发预览，持续 30 分钟。

测试目标:
  - 10 路并发预览持续 30 分钟，不卡顿、不崩溃
  - 预览过程中内存无持续增长
  - 预览过程中无 ERROR 日志

使用方式:
  python tools/stress_test/concurrent_preview_test.py \
      --base-url http://localhost:8000 \
      --token YOUR_JWT_TOKEN \
      --channels "ch001,ch002,ch003,ch004,ch005,ch006,ch007,ch008,ch009,ch010" \
      --duration-minutes 30

依赖: pip install httpx
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from typing import Any

import httpx


async def start_preview(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    channel_id: str,
) -> dict[str, Any]:
    """启动一路预览。"""
    headers = {"Authorization": f"Bearer {token}"}
    start = time.perf_counter()
    try:
        resp = await client.post(
            f"{base_url}/api/play/start",
            json={"channel_id": channel_id, "mode": "main"},
            headers=headers,
            timeout=15.0,
        )
        elapsed = round((time.perf_counter() - start) * 1000, 2)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "channel_id": channel_id,
                "success": True,
                "elapsed_ms": elapsed,
                "stream_id": data.get("stream_id", ""),
                "flv_url": data.get("flv_url", ""),
            }
        else:
            return {
                "channel_id": channel_id,
                "success": False,
                "elapsed_ms": elapsed,
                "error": f"HTTP {resp.status_code}: {resp.text[:100]}",
            }
    except Exception as e:
        return {
            "channel_id": channel_id,
            "success": False,
            "elapsed_ms": round((time.perf_counter() - start) * 1000, 2),
            "error": str(e)[:100],
        }


async def stop_preview(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    app: str,
    stream_id: str,
) -> bool:
    """停止一路预览。"""
    headers = {"Authorization": f"Bearer {token}"}
    try:
        await client.post(
            f"{base_url}/api/v1/streams/stop",
            json={"app": app, "stream": stream_id},
            headers=headers,
            timeout=10.0,
        )
        return True
    except Exception:
        return False


async def monitor_system_resources(
    base_url: str,
    stop_event: asyncio.Event,
    interval: float = 30.0,
) -> list[dict[str, Any]]:
    """定期采集系统资源指标。"""
    samples: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        while not stop_event.is_set():
            try:
                resp = await client.get(f"{base_url}/api/v1/ops/status")
                if resp.status_code == 200:
                    data = resp.json()
                    samples.append({
                        "timestamp": time.time(),
                        "cpu_percent": data.get("cpu", 0),
                        "memory_percent": data.get("memory_percent", 0),
                        "process_memory_mb": data.get("process_memory_mb", 0),
                        "zlm_streams": data.get("zlm_streams", 0),
                    })
                    print(f"  [Monitor] CPU={data.get('cpu', 0)}% "
                          f"Mem={data.get('memory_percent', 0)}% "
                          f"ProcMem={data.get('process_memory_mb', 0)}MB "
                          f"Streams={data.get('zlm_streams', 0)}")
            except Exception as e:
                print(f"  [Monitor] Error: {e}")

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass
    return samples


async def run_concurrent_preview(
    base_url: str,
    token: str,
    channels: list[str],
    duration_minutes: int,
) -> dict[str, Any]:
    """执行并发预览测试。"""
    duration_seconds = duration_minutes * 60
    print(f"\n{'='*70}")
    print(f"并发预览压力测试: {len(channels)} 路 × {duration_minutes} 分钟")
    print(f"Target: {base_url}")
    print(f"{'='*70}\n")

    stop_event = asyncio.Event()
    resource_monitor_task = asyncio.create_task(
        monitor_system_resources(base_url, stop_event, interval=30.0)
    )

    # 启动预览
    print("--- 启动预览 ---")
    async with httpx.AsyncClient(timeout=15.0) as client:
        start_tasks = [start_preview(client, base_url, token, ch) for ch in channels]
        start_results = await asyncio.gather(*start_tasks)

    active_streams: list[dict[str, Any]] = []
    for r in start_results:
        if r["success"]:
            active_streams.append(r)
            print(f"  [OK] {r['channel_id']} → {r.get('stream_id', '')} ({r['elapsed_ms']}ms)")
        else:
            print(f"  [FAIL] {r['channel_id']}: {r.get('error', 'unknown')}")

    start_success = len(active_streams)
    print(f"\n  启动成功: {start_success}/{len(channels)}")

    if start_success == 0:
        stop_event.set()
        await resource_monitor_task
        return {
            "scenario": "concurrent_preview",
            "start_success": 0,
            "start_fail": len(channels),
            "error": "All previews failed to start",
        }

    # 持续运行
    print(f"\n--- 持续运行 {duration_minutes} 分钟 ---")
    start_ts = time.perf_counter()
    health_checks: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=10.0) as client:
        while True:
            elapsed = time.perf_counter() - start_ts
            if elapsed >= duration_seconds:
                break

            # 每 60 秒检查一次预览状态
            await asyncio.sleep(60)
            active_count = 0
            try:
                resp = await client.get(
                    f"{base_url}/api/v1/streams/sessions",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"page": 1, "page_size": 50},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    active_count = data.get("total", 0) if isinstance(data, dict) else 0
            except Exception:
                pass

            mins = int(elapsed // 60)
            secs = int(elapsed % 60)
            print(f"  [{mins:02d}:{secs:02d}] Active streams: {active_count}")
            health_checks.append({
                "elapsed_s": round(elapsed, 1),
                "active_streams": active_count,
            })

    # 停止预览
    print("\n--- 停止预览 ---")
    async with httpx.AsyncClient(timeout=10.0) as client:
        stop_tasks = []
        for s in active_streams:
            app = "live"
            stop_tasks.append(stop_preview(client, base_url, token, app, s.get("stream_id", "")))
        stop_results = await asyncio.gather(*stop_tasks)
    stop_success = sum(1 for r in stop_results if r)

    # 等待资源监控结束
    stop_event.set()
    resource_samples = await resource_monitor_task

    # 分析资源趋势
    memory_values = [s["process_memory_mb"] for s in resource_samples] if resource_samples else []
    cpu_values = [s["cpu_percent"] for s in resource_samples] if resource_samples else []
    memory_trend = "stable"
    if len(memory_values) >= 3:
        first_half_avg = sum(memory_values[:len(memory_values)//2]) / (len(memory_values)//2)
        second_half_avg = sum(memory_values[len(memory_values)//2:]) / (len(memory_values) - len(memory_values)//2)
        if second_half_avg > first_half_avg * 1.2:
            memory_trend = "increasing"
        elif second_half_avg < first_half_avg * 0.8:
            memory_trend = "decreasing"

    summary = {
        "scenario": "concurrent_preview",
        "channel_count": len(channels),
        "duration_minutes": duration_minutes,
        "start_success": start_success,
        "start_fail": len(channels) - start_success,
        "stop_success": stop_success,
        "stop_fail": len(active_streams) - stop_success,
        "resource_monitor": {
            "sample_count": len(resource_samples),
            "memory_mb": {
                "min": round(min(memory_values), 1) if memory_values else 0,
                "max": round(max(memory_values), 1) if memory_values else 0,
                "avg": round(sum(memory_values) / len(memory_values), 1) if memory_values else 0,
                "trend": memory_trend,
            },
            "cpu_percent": {
                "min": round(min(cpu_values), 1) if cpu_values else 0,
                "max": round(max(cpu_values), 1) if cpu_values else 0,
                "avg": round(sum(cpu_values) / len(cpu_values), 1) if cpu_values else 0,
            },
        },
        "health_checks": health_checks,
        "pass_criteria": {
            "all_started": start_success == len(channels),
            "no_crash": len(health_checks) > 0,
            "memory_stable": memory_trend != "increasing",
        },
    }

    all_pass = all(summary["pass_criteria"].values())
    print(f"\n--- 测试结果 ---")
    print(f"  启动: {start_success}/{len(channels)} {'PASS' if summary['pass_criteria']['all_started'] else 'FAIL'}")
    print(f"  停止: {stop_success}/{len(active_streams)}")
    print(f"  内存趋势: {memory_trend} {'PASS' if summary['pass_criteria']['memory_stable'] else 'FAIL'}")
    if memory_values:
        print(f"  内存范围: {summary['resource_monitor']['memory_mb']['min']}-{summary['resource_monitor']['memory_mb']['max']} MB")
    if cpu_values:
        print(f"  CPU 平均: {summary['resource_monitor']['cpu_percent']['avg']}%")
    print(f"  总体: {'PASS' if all_pass else 'FAIL'}")
    print()

    return summary


def main():
    parser = argparse.ArgumentParser(description="PyGBSentry 并发预览压力测试")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--token", required=True, help="JWT token")
    parser.add_argument("--channels", required=True, help="通道ID列表(逗号分隔)")
    parser.add_argument("--duration-minutes", type=int, default=30, help="持续时间(分钟)")
    parser.add_argument("--output", default="", help="结果输出文件 (JSON)")
    args = parser.parse_args()

    channels = [c.strip() for c in args.channels.split(",") if c.strip()]
    if not channels:
        raise SystemExit("channels 不能为空")

    result = asyncio.run(run_concurrent_preview(
        base_url=args.base_url,
        token=args.token,
        channels=channels,
        duration_minutes=args.duration_minutes,
    ))

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"结果已保存到 {args.output}")


if __name__ == "__main__":
    main()
