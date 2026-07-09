"""耐久测试监控脚本 — 连续监控 72 小时系统资源与错误日志。

测试目标:
  - 连续运行 72 小时，监控:
    - 内存占用变化（要求：波动 < 20%，无持续增长）
    - CPU 占用变化（要求：平均 < 50%）
    - 错误日志数量（要求：ERROR=0，WARN < 10 条/天）

使用方式:
  python tools/stress_test/endurance_monitor.py \
      --base-url http://localhost:8000 \
      --log-path ./backend/logs/app.log \
      --duration-hours 72 \
      --output endurance_report.json

依赖: pip install httpx psutil
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Any

try:
    import psutil
except ImportError:
    psutil = None

try:
    import httpx
except ImportError:
    httpx = None


# ─── 资源采样 ──────────────────────────────────────────────

async def sample_local_resources() -> dict[str, Any]:
    """采集本机进程资源。"""
    if psutil is None:
        return {}
    try:
        proc = psutil.Process(os.getpid())
        return {
            "timestamp": time.time(),
            "rss_mb": round(proc.memory_info().rss / 1024 / 1024, 1),
            "cpu_percent": proc.cpu_percent(interval=0.5),
            "threads": proc.num_threads(),
        }
    except Exception:
        return {}


async def sample_remote_resources(base_url: str) -> dict[str, Any]:
    """通过 API 采集远端系统资源。"""
    if httpx is None:
        return {}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{base_url}/api/v1/ops/status")
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "timestamp": time.time(),
                    "remote_cpu": data.get("cpu", 0),
                    "remote_memory_percent": data.get("memory_percent", 0),
                    "remote_process_memory_mb": data.get("process_memory_mb", 0),
                    "remote_threads": data.get("process_threads", 0),
                    "remote_uptime_s": data.get("uptime_seconds", 0),
                    "zlm_streams": data.get("zlm_streams", 0),
                }
    except Exception:
        pass
    return {}


async def check_health(base_url: str) -> dict[str, Any]:
    """检查健康端点状态。"""
    if httpx is None:
        return {}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{base_url}/health/live")
            alive = resp.status_code == 200
            resp2 = await client.get(f"{base_url}/health/ready")
            ready = resp2.status_code == 200
            return {
                "timestamp": time.time(),
                "liveness": "alive" if alive else "dead",
                "readiness": "ready" if ready else "not_ready",
            }
    except Exception:
        return {"timestamp": time.time(), "liveness": "error", "readiness": "error"}


# ─── 日志分析 ──────────────────────────────────────────────

_ERROR_PATTERN = re.compile(r"\b(ERROR|CRITICAL)\b", re.IGNORECASE)
_WARN_PATTERN = re.compile(r"\b(WARNING|WARN)\b", re.IGNORECASE)
_LOG_TIMESTAMP_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})"
)


def analyze_log_file(log_path: str, since_ts: float) -> dict[str, Any]:
    """分析日志文件中的 ERROR/WARN 数量。

    Args:
        log_path: 日志文件路径
        since_ts: 只统计此时间戳之后的日志（Unix epoch）

    Returns:
        {"error_count": int, "warn_count": int, "samples": [...]}
    """
    if not os.path.exists(log_path):
        return {"error_count": 0, "warn_count": 0, "samples": [], "note": "log file not found"}

    error_count = 0
    warn_count = 0
    samples: list[str] = []
    since_str = datetime.fromtimestamp(since_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                # 简单的时间戳过滤
                m = _LOG_TIMESTAMP_RE.search(line)
                if m:
                    try:
                        line_ts = datetime.strptime(m.group(1).replace("T", " "), "%Y-%m-%d %H:%M:%S")
                        if line_ts.timestamp() < since_ts:
                            continue
                    except Exception:
                        pass

                if _ERROR_PATTERN.search(line):
                    error_count += 1
                    if len(samples) < 50:
                        samples.append(line.strip()[:200])
                elif _WARN_PATTERN.search(line):
                    warn_count += 1
    except Exception as e:
        return {"error_count": 0, "warn_count": 0, "samples": [], "error": str(e)}

    return {"error_count": error_count, "warn_count": warn_count, "samples": samples[:20]}


# ─── 主监控循环 ────────────────────────────────────────────

async def run_endurance_monitor(
    base_url: str,
    log_path: str,
    duration_hours: float,
    output_file: str,
) -> dict[str, Any]:
    """运行耐久测试监控。"""
    duration_seconds = duration_hours * 3600
    sample_interval = 60  # 1 分钟采样一次
    log_check_interval = 300  # 5 分钟检查一次日志

    print(f"\n{'='*70}")
    print(f"耐久测试监控: {duration_hours} 小时")
    print(f"Base URL: {base_url}")
    print(f"Log path: {log_path}")
    print(f"Sample interval: {sample_interval}s | Log check: {log_check_interval}s")
    print(f"{'='*70}\n")

    start_ts = time.time()
    resource_samples: list[dict[str, Any]] = []
    health_samples: list[dict[str, Any]] = []
    log_snapshots: list[dict[str, Any]] = []
    last_log_check = start_ts

    # 初始日志分析基线
    baseline_log = analyze_log_file(log_path, 0)
    baseline_error_count = baseline_log.get("error_count", 0)
    baseline_warn_count = baseline_log.get("warn_count", 0)
    print(f"  [Baseline] Errors: {baseline_error_count}, Warnings: {baseline_warn_count}")

    elapsed = 0
    while elapsed < duration_seconds:
        elapsed = time.time() - start_ts
        hours_elapsed = elapsed / 3600

        # 采集资源
        local = await sample_local_resources()
        remote = await sample_remote_resources(base_url)
        sample = {**local, **remote}
        if sample:
            resource_samples.append(sample)

        # 健康检查
        health = await check_health(base_url)
        health_samples.append(health)

        # 定期日志检查
        if elapsed - last_log_check >= log_check_interval:
            log_analysis = analyze_log_file(log_path, start_ts)
            log_snapshots.append({
                "timestamp": time.time(),
                "elapsed_hours": round(hours_elapsed, 2),
                **log_analysis,
            })
            last_log_check = elapsed
            print(f"  [{hours_elapsed:.1f}h] "
                  f"CPU={sample.get('remote_cpu', 0)}% "
                  f"Mem={sample.get('remote_process_memory_mb', 0)}MB "
                  f"Errors={log_analysis.get('error_count', 0)} "
                  f"Warns={log_analysis.get('warn_count', 0)} "
                  f"Health={health.get('liveness', '?')}")

        await asyncio.sleep(sample_interval)

    # 最终日志分析
    final_log = analyze_log_file(log_path, start_ts)

    # 计算统计数据
    remote_mem = [s.get("remote_process_memory_mb", 0) for s in resource_samples if s.get("remote_process_memory_mb")]
    remote_cpu = [s.get("remote_cpu", 0) for s in resource_samples if s.get("remote_cpu") is not None]
    health_alive_count = sum(1 for h in health_samples if h.get("liveness") == "alive")

    memory_stats = {}
    if remote_mem:
        mem_avg = sum(remote_mem) / len(remote_mem)
        memory_stats = {
            "min_mb": round(min(remote_mem), 1),
            "max_mb": round(max(remote_mem), 1),
            "avg_mb": round(mem_avg, 1),
            "first_mb": remote_mem[0],
            "last_mb": remote_mem[-1],
            "fluctuation_pct": round(((max(remote_mem) - min(remote_mem)) / mem_avg) * 100, 1) if mem_avg else 0,
            "trend": "increasing" if remote_mem[-1] > remote_mem[0] * 1.2 else
                     "decreasing" if remote_mem[-1] < remote_mem[0] * 0.8 else "stable",
        }

    cpu_stats = {}
    if remote_cpu:
        cpu_stats = {
            "min_pct": round(min(remote_cpu), 1),
            "max_pct": round(max(remote_cpu), 1),
            "avg_pct": round(sum(remote_cpu) / len(remote_cpu), 1),
        }

    # 每日错误统计
    daily_errors: list[dict[str, Any]] = []
    total_errors = final_log.get("error_count", 0)
    total_warns = final_log.get("warn_count", 0)
    days = max(1, int(duration_hours / 24))
    errors_per_day = total_errors / days
    warns_per_day = total_warns / days

    summary = {
        "scenario": "endurance_monitor",
        "duration_hours": duration_hours,
        "start_time": datetime.fromtimestamp(start_ts, tz=timezone.utc).isoformat(),
        "end_time": datetime.fromtimestamp(time.time(), tz=timezone.utc).isoformat(),
        "resource_sample_count": len(resource_samples),
        "health_check_count": len(health_samples),
        "health_alive_rate": round(health_alive_count / len(health_samples), 4) if health_samples else 0,
        "memory_stats": memory_stats,
        "cpu_stats": cpu_stats,
        "log_stats": {
            "total_errors": total_errors,
            "total_warns": total_warns,
            "errors_per_day": round(errors_per_day, 1),
            "warns_per_day": round(warns_per_day, 1),
            "error_samples": final_log.get("samples", []),
        },
        "pass_criteria": {
            "memory_fluctuation_lt_20pct": memory_stats.get("fluctuation_pct", 0) < 20,
            "memory_no_continuous_growth": memory_stats.get("trend") != "increasing",
            "cpu_avg_lt_50pct": cpu_stats.get("avg_pct", 0) < 50,
            "error_count_zero": total_errors == 0,
            "warn_lt_10_per_day": warns_per_day < 10,
            "health_alive_rate_gt_99pct": (health_alive_count / len(health_samples)) > 0.99 if health_samples else False,
        },
    }

    all_pass = all(summary["pass_criteria"].values())
    summary["overall_pass"] = all_pass

    print(f"\n{'='*70}")
    print(f"耐久测试结果 ({duration_hours}h)")
    print(f"{'='*70}")
    print(f"  内存波动: {memory_stats.get('fluctuation_pct', 'N/A')}% "
          f"({'PASS' if summary['pass_criteria']['memory_fluctuation_lt_20pct'] else 'FAIL'})")
    print(f"  内存趋势: {memory_stats.get('trend', 'N/A')} "
          f"({'PASS' if summary['pass_criteria']['memory_no_continuous_growth'] else 'FAIL'})")
    print(f"  CPU平均: {cpu_stats.get('avg_pct', 'N/A')}% "
          f"({'PASS' if summary['pass_criteria']['cpu_avg_lt_50pct'] else 'FAIL'})")
    print(f"  ERROR数: {total_errors} "
          f"({'PASS' if summary['pass_criteria']['error_count_zero'] else 'FAIL'})")
    print(f"  WARN/天: {warns_per_day:.1f} "
          f"({'PASS' if summary['pass_criteria']['warn_lt_10_per_day'] else 'FAIL'})")
    print(f"  存活率: {summary['health_alive_rate']*100:.1f}% "
          f"({'PASS' if summary['pass_criteria']['health_alive_rate_gt_99pct'] else 'FAIL'})")
    print(f"\n  总体: {'PASS' if all_pass else 'FAIL'}")
    print(f"{'='*70}\n")

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print(f"结果已保存到 {output_file}")

    return summary


def main():
    parser = argparse.ArgumentParser(description="PyGBSentry 耐久测试监控")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--log-path", default="./logs/app.log", help="应用日志路径")
    parser.add_argument("--duration-hours", type=float, default=72, help="持续时间(小时)")
    parser.add_argument("--output", default="endurance_report.json", help="结果输出文件")
    args = parser.parse_args()

    asyncio.run(run_endurance_monitor(
        base_url=args.base_url,
        log_path=args.log_path,
        duration_hours=args.duration_hours,
        output_file=args.output,
    ))


if __name__ == "__main__":
    main()
