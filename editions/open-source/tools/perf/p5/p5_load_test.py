import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

import requests


def _p(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    arr = sorted(float(x) for x in values)
    if len(arr) == 1:
        return arr[0]
    q = max(0.0, min(1.0, float(q)))
    idx = int(round((len(arr) - 1) * q))
    idx = max(0, min(len(arr) - 1, idx))
    return arr[idx]


def _call_snapshot_batch(
    base_url: str,
    token: str,
    channel_ids: list[str],
    timeout_seconds: float,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/v1/devices/channels/snap-batch"
    params = {"profile": "true"}
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"channel_ids": channel_ids}
    t0 = time.perf_counter()
    try:
        resp = requests.post(url, params=params, headers=headers, json=payload, timeout=timeout_seconds)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return {
            "ok": resp.status_code < 400,
            "status_code": int(resp.status_code),
            "elapsed_ms": round(elapsed_ms, 2),
            "response": resp.json() if "application/json" in str(resp.headers.get("Content-Type", "")).lower() else {},
        }
    except Exception as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return {"ok": False, "status_code": 0, "elapsed_ms": round(elapsed_ms, 2), "error": str(e)}


def run_snapshot_batch_test(
    base_url: str,
    token: str,
    channel_ids: list[str],
    concurrency: int,
    rounds: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    tasks = []
    with ThreadPoolExecutor(max_workers=max(1, int(concurrency))) as ex:
        for _ in range(max(1, int(rounds))):
            tasks.append(ex.submit(_call_snapshot_batch, base_url, token, channel_ids, timeout_seconds))
        results = [f.result() for f in as_completed(tasks)]
    latencies = [float(x.get("elapsed_ms") or 0.0) for x in results]
    ok_count = sum(1 for x in results if bool(x.get("ok")))
    fail_count = len(results) - ok_count
    return {
        "scenario": "snapshot_batch",
        "concurrency": int(concurrency),
        "rounds": int(rounds),
        "count": len(results),
        "ok": ok_count,
        "failed": fail_count,
        "success_rate": round((ok_count / len(results)) if results else 0.0, 4),
        "latency_ms": {
            "avg": round((sum(latencies) / len(latencies)) if latencies else 0.0, 2),
            "p50": round(_p(latencies, 0.50), 2),
            "p95": round(_p(latencies, 0.95), 2),
            "max": round(max(latencies) if latencies else 0.0, 2),
        },
        "samples": results[:20],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--channel-ids", required=True, help="逗号分隔")
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    channel_ids = [x.strip() for x in str(args.channel_ids).split(",") if x.strip()]
    if not channel_ids:
        raise SystemExit("channel_ids empty")

    started_at = datetime.now(timezone.utc).isoformat()
    report = {
        "started_at": started_at,
        "base_url": str(args.base_url),
        "concurrency": int(args.concurrency),
        "rounds": int(args.rounds),
        "channel_count": len(channel_ids),
        "result": run_snapshot_batch_test(
            base_url=str(args.base_url),
            token=str(args.token),
            channel_ids=channel_ids,
            concurrency=int(args.concurrency),
            rounds=int(args.rounds),
            timeout_seconds=float(args.timeout_seconds),
        ),
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if str(args.output or "").strip():
        with open(str(args.output), "w", encoding="utf-8") as f:
            f.write(text)


if __name__ == "__main__":
    main()
