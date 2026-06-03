#!/usr/bin/env python3
"""
PyGBSentry Capacity Baseline Verification Tool.

Checks RTP port availability, SSRC capacity, concurrent stream limits,
and system resource adequacy for production deployment.

Usage:
    python capacity_check.py
    python capacity_check.py --port-range 30000-30999 --max-ssrc 1000
"""

import argparse
import os
import socket
import sys
import subprocess
from typing import Tuple


def check_port_range(start: int, end: int) -> Tuple[int, int, list[int]]:
    """Check how many ports in the range are available."""
    total = end - start + 1
    unavailable = []
    for port in range(start, min(end + 1, start + 200)):  # Sample first 200 ports
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.bind(("0.0.0.0", port))
        except OSError:
            unavailable.append(port)
    available = total - len(unavailable) * (total / min(200, total))
    return total, int(available), unavailable[:10]


def check_concurrent_streams(port_count: int, avg_stream_duration_hours: float = 2.0) -> dict:
    """Estimate max concurrent streams based on port availability."""
    # Each stream uses 1-2 RTP ports (audio + video)
    max_streams_conservative = port_count // 2
    max_streams_optimistic = port_count
    # With turnover: streams per day = port_count * (24 / avg_duration)
    daily_capacity = int(port_count * (24 / avg_stream_duration_hours))
    return {
        "max_concurrent_conservative": max_streams_conservative,
        "max_concurrent_optimistic": max_streams_optimistic,
        "daily_stream_capacity": daily_capacity,
        "avg_duration_hours": avg_stream_duration_hours,
    }


def check_ssrc_capacity(max_ssrc: int) -> dict:
    """Check SSRC allocation capacity."""
    # SSRC is 32-bit, but practical limit is configured
    ssrc_warning_threshold = int(max_ssrc * 0.8)
    ssrc_critical_threshold = int(max_ssrc * 0.95)
    return {
        "max_ssrc": max_ssrc,
        "warning_at": ssrc_warning_threshold,
        "critical_at": ssrc_critical_threshold,
        "recommended_max_devices": max_ssrc // 2,  # 2 SSRC per device (audio+video)
    }


def check_system_resources() -> dict:
    """Check system CPU, memory, and disk."""
    result = {"cpu_cores": 0, "memory_gb": 0.0, "disk_gb": 0.0}

    try:
        result["cpu_cores"] = os.cpu_count() or 0
    except Exception:
        pass

    try:
        import psutil
        result["memory_gb"] = round(psutil.virtual_memory().total / (1024**3), 1)
        result["disk_gb"] = round(psutil.disk_usage("/").total / (1024**3), 1)
    except ImportError:
        # Fallback without psutil
        if sys.platform == "linux":
            try:
                with open("/proc/meminfo") as f:
                    for line in f:
                        if line.startswith("MemTotal:"):
                            result["memory_gb"] = round(int(line.split()[1]) / (1024**2), 1)
                            break
            except Exception:
                pass

    return result


def check_sip_capacity() -> dict:
    """Estimate SIP signaling capacity."""
    return {
        "max_inflight_default": 200,
        "recommended_device_limit_single_instance": 2000,
        "recommended_device_limit_ha": 5000,
        "keepalive_interval_seconds": 60,
        "catalog_sync_interval_seconds": 300,
        "note": "SIP UDP is single-endpoint; use HA proxy or DNS round-robin for multi-instance",
    }


def generate_recommendations(port_total: int, port_available: int, max_ssrc: int,
                              system: dict, streams: dict) -> list[str]:
    """Generate capacity recommendations."""
    recs = []

    if port_available < 100:
        recs.append("CRITICAL: Less than 100 RTP ports available. Increase port range or reduce concurrent streams.")

    if port_available < 500:
        recs.append("WARNING: Less than 500 RTP ports available. Consider 30000-31999 for 2000 ports.")

    port_utilization = (port_total - port_available) / port_total * 100 if port_total > 0 else 0
    if port_utilization > 50:
        recs.append(f"WARNING: {port_utilization:.0f}% ports already in use. Free ports before deployment.")

    if system.get("cpu_cores", 0) < 2:
        recs.append("WARNING: Less than 2 CPU cores. Minimum 4 cores recommended for 500+ devices.")

    if system.get("memory_gb", 0) < 4:
        recs.append("WARNING: Less than 4GB RAM. Minimum 8GB recommended for production.")

    if system.get("disk_gb", 0) < 50:
        recs.append("WARNING: Less than 50GB disk. Recording storage requires separate volume.")

    if max_ssrc < 500:
        recs.append("WARNING: SSRC capacity below 500. Increase for 250+ devices.")

    return recs


def main():
    parser = argparse.ArgumentParser(description="PyGBSentry Capacity Baseline Check")
    parser.add_argument("--port-start", type=int, default=30000, help="RTP port range start")
    parser.add_argument("--port-end", type=int, default=30999, help="RTP port range end")
    parser.add_argument("--max-ssrc", type=int, default=1000, help="Max SSRC allocations")
    parser.add_argument("--avg-stream-hours", type=float, default=2.0, help="Average stream duration in hours")
    args = parser.parse_args()

    print("=" * 60)
    print("  PyGBSentry Capacity Baseline Verification")
    print("=" * 60)

    # Port check
    print(f"\n--- RTP Port Range: {args.port_start}-{args.port_end} ---")
    port_total, port_available, sample_unavailable = check_port_range(args.port_start, args.port_end)
    print(f"  Total ports:       {port_total}")
    print(f"  Available (est.):  {port_available}")
    if sample_unavailable:
        print(f"  Sample unavailable: {sample_unavailable}...")

    # Stream capacity
    print("\n--- Concurrent Stream Capacity ---")
    streams = check_concurrent_streams(port_total, args.avg_stream_hours)
    for k, v in streams.items():
        print(f"  {k}: {v}")

    # SSRC capacity
    print(f"\n--- SSRC Capacity (max: {args.max_ssrc}) ---")
    ssrc = check_ssrc_capacity(args.max_ssrc)
    for k, v in ssrc.items():
        print(f"  {k}: {v}")

    # System resources
    print("\n--- System Resources ---")
    system = check_system_resources()
    for k, v in system.items():
        print(f"  {k}: {v}")

    # SIP capacity
    print("\n--- SIP Signaling Capacity ---")
    sip = check_sip_capacity()
    for k, v in sip.items():
        print(f"  {k}: {v}")

    # Recommendations
    print("\n--- Recommendations ---")
    recs = generate_recommendations(port_total, port_available, args.max_ssrc, system, streams)
    if recs:
        for r in recs:
            print(f"  {r}")
    else:
        print("  All capacity checks passed.")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
