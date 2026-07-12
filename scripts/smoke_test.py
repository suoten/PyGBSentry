#!/usr/bin/env python3
"""Smoke test script for PyGBSentry.

Verifies that key API endpoints respond correctly after server startup.
Designed to be run against a live server instance (local, Docker, or CI).

Usage:
    python scripts/smoke_test.py [--host localhost] [--port 8000] [--timeout 10]

Exit codes:
    0 — All smoke tests passed
    1 — One or more smoke tests failed
    2 — Could not connect to server
"""
import argparse
import sys
import time
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError


# Endpoints to test: (method, path, expected_status, description)
SMOKE_ENDPOINTS = [
    ("GET", "/api/v1/health/", 200, "Health check root"),
    ("GET", "/api/v1/health/liveness", 200, "Liveness probe"),
    ("GET", "/api/v1/health/readiness", 200, "Readiness probe"),
    ("GET", "/api/v1/ops/db-check", 200, "Database connectivity check"),
    ("GET", "/api/v1/health/overview", 200, "Health overview (may require auth)"),
    ("GET", "/api/v1/metrics/devices-overview", 200, "Device metrics overview"),
    ("GET", "/api/v1/network/summary", 200, "Network summary"),
    ("GET", "/docs", 200, "OpenAPI docs (if enabled)"),
]


def wait_for_server(base_url: str, timeout: int) -> bool:
    """Wait for the server to become reachable."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            req = Request(f"{base_url}/api/v1/health/", method="GET")
            with urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    return True
        except (URLError, ConnectionError, OSError):
            pass
        time.sleep(1)
    return False


def test_endpoint(base_url: str, method: str, path: str, expected_status: int, description: str) -> bool:
    """Test a single endpoint and return True if it passes."""
    url = f"{base_url}{path}"
    try:
        req = Request(url, method=method)
        with urlopen(req, timeout=10) as resp:
            status = resp.status
            if status == expected_status:
                print(f"  [PASS] {method} {path} → {status} ({description})")
                return True
            # Accept 401/403 as "endpoint exists but requires auth"
            if status in (401, 403) and expected_status == 200:
                print(f"  [PASS] {method} {path} → {status} ({description}, auth required)")
                return True
            print(f"  [FAIL] {method} {path} → {status}, expected {expected_status} ({description})")
            return False
    except HTTPError as e:
        if e.code in (401, 403) and expected_status == 200:
            print(f"  [PASS] {method} {path} → {e.code} ({description}, auth required)")
            return True
        if e.code == expected_status:
            print(f"  [PASS] {method} {path} → {e.code} ({description})")
            return True
        print(f"  [FAIL] {method} {path} → {e.code}, expected {expected_status} ({description})")
        return False
    except URLError as e:
        print(f"  [FAIL] {method} {path} → Connection error: {e} ({description})")
        return False
    except Exception as e:
        print(f"  [FAIL] {method} {path} → Unexpected error: {e} ({description})")
        return False


def main():
    parser = argparse.ArgumentParser(description="PyGBSentry Smoke Test")
    parser.add_argument("--host", default="localhost", help="Server host (default: localhost)")
    parser.add_argument("--port", type=int, default=8000, help="Server port (default: 8000)")
    parser.add_argument("--timeout", type=int, default=30, help="Max wait time for server (default: 30s)")
    parser.add_argument("--base-url", default=None, help="Full base URL (overrides host/port)")
    args = parser.parse_args()

    base_url = args.base_url or f"http://{args.host}:{args.port}"

    print("PyGBSentry Smoke Test")
    print(f"Target: {base_url}")
    print(f"Timeout: {args.timeout}s")
    print()

    # Wait for server to be ready
    print("Waiting for server to become reachable...")
    if not wait_for_server(base_url, args.timeout):
        print(f"[FAIL] Server at {base_url} did not become reachable within {args.timeout}s")
        sys.exit(2)

    print("Server is reachable. Running smoke tests...")
    print()

    passed = 0
    failed = 0
    for method, path, expected, desc in SMOKE_ENDPOINTS:
        if test_endpoint(base_url, method, path, expected, desc):
            passed += 1
        else:
            failed += 1

    print()
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")

    if failed > 0:
        print(f"[FAIL] {failed} smoke test(s) failed")
        sys.exit(1)
    else:
        print("[PASS] All smoke tests passed")
        sys.exit(0)


if __name__ == "__main__":
    main()
