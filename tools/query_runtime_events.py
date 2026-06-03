#!/usr/bin/env python3
"""
Runtime events/health query helper.

It is intended for ops troubleshooting:
  - Builds GET URL for:
      /api/v1/plugins/runtime/{plugin_id}/events
      /api/v1/plugins/runtime/stream_health/health
      /api/v1/plugins/runtime/sip_logger/logs
  - Accepts arbitrary query params as JSON (e.g. {"device":"3402","ok":true})
  - Optionally sends Cookie header (if your API requires login)
  - Prints meta + first rows summary

Example:
  python query_runtime_events.py --plugin wecom_alert --params '{"device":"3402","ok":false}' --page-size 20 --cookie "access_token=..."
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone


def _default_range(hours: int, use_utc: bool) -> tuple[str, str]:
    now = datetime.now(timezone.utc) if use_utc else datetime.now()
    start = now - timedelta(hours=hours)
    # Backend parses isoformat and strips tzinfo; keep it simple/consistent.
    start_s = start.replace(tzinfo=None).isoformat(timespec="seconds")
    end_s = now.replace(tzinfo=None).isoformat(timespec="seconds")
    return start_s, end_s


def _build_url(base_url: str, plugin_id: str) -> str:
    base_url = base_url.rstrip("/")
    if plugin_id == "stream_health":
        return f"{base_url}/api/v1/plugins/runtime/stream_health/health"
    if plugin_id == "sip_logger":
        return f"{base_url}/api/v1/plugins/runtime/sip_logger/logs"
    return f"{base_url}/api/v1/plugins/runtime/{plugin_id}/events"


def _http_get(url: str, headers: dict[str, str], timeout_sec: int = 20) -> dict:
    req = urllib.request.Request(url, method="GET", headers=headers)
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    try:
        return json.loads(raw)
    except Exception as e:
        raise RuntimeError(f"Response is not JSON: {e}; raw={raw[:400]}") from e


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000", help="Backend base URL")
    ap.add_argument("--plugin", required=True, help="plugin_id, e.g. network_watchdog / wecom_alert / mqtt_bridge")
    ap.add_argument("--page", type=int, default=1)
    ap.add_argument("--page-size", type=int, default=50)
    ap.add_argument("--token", default=None, help="Bearer token (if your backend requires auth)")
    ap.add_argument("--start-at", default=None, help="ISO datetime: YYYY-MM-DDTHH:mm:ss (naive)"
                   )
    ap.add_argument("--end-at", default=None, help="ISO datetime: YYYY-MM-DDTHH:mm:ss (naive)")
    ap.add_argument("--range-hours", type=int, default=24, help="Used when start/end are not provided")
    ap.add_argument("--utc", action="store_true", help="Use UTC for default range")
    ap.add_argument("--params", default="{}", help="Additional query params as JSON object")
    ap.add_argument("--cookie", default=None, help="Cookie header value (optional)")
    ap.add_argument("--timeout", type=int, default=20)
    ap.add_argument("--dry-run", action="store_true", help="Print URL and exit")
    args = ap.parse_args()

    try:
        extra_params = json.loads(args.params or "{}")
        if not isinstance(extra_params, dict):
            raise ValueError("--params must be a JSON object")
    except Exception as e:
        print(f"Invalid --params JSON: {e}", file=sys.stderr)
        return 2

    if args.start_at and args.end_at:
        start_s = args.start_at
        end_s = args.end_at
    else:
        start_s, end_s = _default_range(args.range_hours, use_utc=args.utc)

    url = _build_url(args.base_url, args.plugin)

    # Some endpoints (stream_health) don't require start/end, but accepting them is harmless
    # since server filters by dt_start/dt_end in their handler only if provided.
    query: dict[str, object] = {
        "page": args.page,
        "page_size": args.page_size,
        "start_at": start_s,
        "end_at": end_s,
    }
    # Overwrite with explicit params
    query.update(extra_params)

    # Drop None
    query = {k: v for k, v in query.items() if v is not None}
    qs = urllib.parse.urlencode(query, doseq=True)
    full_url = f"{url}?{qs}"

    if args.dry_run:
        print(full_url)
        return 0

    headers: dict[str, str] = {
        "Accept": "application/json",
    }
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"
    if args.cookie:
        headers["Cookie"] = args.cookie

    try:
        data = _http_get(full_url, headers=headers, timeout_sec=args.timeout)
    except Exception as e:
        print(f"Request failed: {e}", file=sys.stderr)
        return 1

    meta = data.get("meta") if isinstance(data, dict) else None
    rows = data.get("rows") if isinstance(data, dict) else None

    print("=== Runtime Query Result ===")
    print("URL:", full_url)
    if isinstance(meta, dict):
        print("meta:", json.dumps(meta, ensure_ascii=False, indent=2))
    if isinstance(rows, list):
        print(f"rows: {len(rows)}")
        # Print first 3 rows (without dumping entire payload)
        for i, r in enumerate(rows[:3]):
            try:
                print(f"row[{i}]:", json.dumps(r, ensure_ascii=False)[:600])
            except Exception:
                print(f"row[{i}]: {str(r)[:600]}")
    else:
        print("rows: (not a list)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

