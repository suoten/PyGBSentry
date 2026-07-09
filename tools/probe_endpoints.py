#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Probe API endpoints to find correct paths."""
import httpx

BASE = "http://127.0.0.1:8000"

r = httpx.post(f"{BASE}/api/v1/login/access-token", data={"username": "admin", "password": "admin123"})
token = r.json()["access_token"]
h = {"Authorization": f"Bearer {token}"}

endpoints = [
    ("GET", "/api/v1/devices"),
    ("GET", "/api/v1/devices/"),
    ("GET", "/api/v1/users"),
    ("GET", "/api/v1/users/"),
    ("GET", "/api/v1/alarms"),
    ("GET", "/api/v1/alarms/"),
    ("GET", "/api/v1/platforms"),
    ("GET", "/api/v1/platforms/"),
    ("GET", "/api/v1/platforms/server_config"),
    ("GET", "/api/v1/platforms/server-config"),
    ("GET", "/api/v1/audit-center/logs"),
    ("GET", "/api/v1/audit-center/"),
    ("GET", "/api/v1/gb-record/"),
    ("GET", "/api/v1/gb-record"),
    ("GET", "/api/v1/record/"),
    ("GET", "/api/v1/record"),
    ("GET", "/api/v1/record-schedule/"),
    ("GET", "/api/v1/record-schedule"),
    ("GET", "/api/v1/stream/list"),
    ("GET", "/api/v1/stream/"),
    ("GET", "/api/v1/stream"),
    ("GET", "/api/v1/health/overview"),
    ("GET", "/api/v1/ops/status"),
    ("GET", "/api/v1/ops/db-check"),
    ("GET", "/api/v1/health/liveness"),
    ("GET", "/api/v1/health/readiness"),
    ("GET", "/api/v1/control/"),
    ("GET", "/api/v1/talk/"),
    ("GET", "/api/v1/map/config"),
    ("GET", "/api/v1/map/devices"),
]

for method, path in endpoints:
    try:
        r = httpx.request(method, f"{BASE}{path}", headers=h, timeout=10.0)
        print(f"  {r.status_code} {method} {path}")
    except Exception as e:
        print(f"  ERR {method} {path}: {e}")
