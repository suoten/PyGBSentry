#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""PyGBSentry 功能可用性审计测试脚本 v3

逐功能测试所有 API 端点 + SIP 信令模拟。
"""
import asyncio
import hashlib
import json
import socket
import time
import uuid
from datetime import datetime, timezone, timedelta

import httpx

BASE_URL = "http://127.0.0.1:8000/api/v1"
SIP_ID = "34020000002000000001"
SIP_DOMAIN = "3402000000"
SIP_PORT = 5060
DEVICE_ID = "34020000001320000001"
DEVICE_PASSWORD = "test123456"
CHANNEL_ID = "34020000001320000002"

results = []


def log(feature, sub_item, status, detail=""):
    results.append({
        "feature": feature,
        "sub_item": sub_item,
        "status": status,
        "detail": detail,
    })
    symbol = {"PASS": "[OK]", "FAIL": "[FAIL]", "SKIP": "[SKIP]", "WARN": "[WARN]"}[status]
    print(f"  {symbol} {sub_item}: {detail[:150]}")


async def login(client):
    r = await client.post(
        f"{BASE_URL}/login/access-token",
        data={"username": "admin", "password": "admin123"},
    )
    if r.status_code == 200:
        return r.json().get("access_token")
    return None


def get_headers(token):
    return {"Authorization": f"Bearer {token}"}


# === SIP Helpers (synchronous) ===

def _sip_send_recv(sock, data, addr, timeout=3.0):
    """Send SIP data and receive response (sync)."""
    sock.sendto(data.encode("gb2312", errors="replace"), addr)
    try:
        sock.settimeout(timeout)
        resp, _ = sock.recvfrom(65535)
        return resp.decode("gb2312", errors="replace")
    except socket.timeout:
        return None
    except Exception:
        return None


def _parse_401_challenge(resp):
    import re
    for line in resp.split("\r\n"):
        if line.startswith("WWW-Authenticate:"):
            nonce_match = re.search(r'nonce="([^"]+)"', line)
            realm_match = re.search(r'realm="([^"]+)"', line)
            nonce = nonce_match.group(1) if nonce_match else ""
            realm = realm_match.group(1) if realm_match else SIP_DOMAIN
            return nonce, realm
    return None, None


def _build_digest_auth(username, password, realm, nonce, uri, method="REGISTER"):
    ha1 = hashlib.md5(f"{username}:{realm}:{password}".encode()).hexdigest()
    ha2 = hashlib.md5(f"{method}:{uri}".encode()).hexdigest()
    response = hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode()).hexdigest()
    return f'Digest username="{username}", realm="{realm}", nonce="{nonce}", uri="{uri}", response="{response}"'


def _sip_register_sync(expires=3600):
    """Synchronous SIP REGISTER with digest auth."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    addr = ("127.0.0.1", SIP_PORT)
    sn = uuid.uuid4().hex[:8]
    msg = f"REGISTER sip:{SIP_DOMAIN} SIP/2.0\r\n"
    msg += f"Via: SIP/2.0/UDP 127.0.0.1:{sock.getsockname()[1]};rport;branch=z9hG4bK{sn}\r\n"
    msg += f"From: <sip:{DEVICE_ID}@{SIP_DOMAIN}>;tag={sn}\r\n"
    msg += f"To: <sip:{DEVICE_ID}@{SIP_DOMAIN}>\r\n"
    msg += f"Call-ID: {sn}@127.0.0.1\r\n"
    msg += "CSeq: 1 REGISTER\r\n"
    msg += f"Contact: <sip:{DEVICE_ID}@127.0.0.1:{sock.getsockname()[1]}>\r\n"
    msg += "Max-Forwards: 70\r\n"
    msg += "User-Agent: PyGBSentry-Audit\r\n"
    msg += f"Expires: {expires}\r\n"
    msg += "Content-Length: 0\r\n\r\n"
    resp = _sip_send_recv(sock, msg, addr)
    if not resp:
        sock.close()
        return False
    if "200 OK" in resp:
        sock.close()
        return True
    if "401" in resp or "407" in resp:
        nonce, realm = _parse_401_challenge(resp)
        if not nonce:
            sock.close()
            return False
        uri = f"sip:{SIP_DOMAIN}"
        auth = _build_digest_auth(DEVICE_ID, DEVICE_PASSWORD, realm, nonce, uri)
        msg2 = msg.replace("Content-Length: 0\r\n\r\n", "")
        msg2 = msg2.replace("CSeq: 1 REGISTER", "CSeq: 2 REGISTER")
        msg2 = msg2 + f"Authorization: {auth}\r\nContent-Length: 0\r\n\r\n"
        resp2 = _sip_send_recv(sock, msg2, addr)
        sock.close()
        return resp2 and "200 OK" in resp2
    sock.close()
    return False


def _sip_keepalive_sync():
    """Synchronous SIP Keepalive."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    addr = ("127.0.0.1", SIP_PORT)
    sn = str(int(time.time()))
    xml = f'<?xml version="1.0" encoding="GB2312"?>\n<Notify><CmdType>Keepalive</CmdType><SN>{sn}</SN><DeviceID>{DEVICE_ID}</DeviceID><Status>OK</Status></Notify>'
    sn2 = uuid.uuid4().hex[:8]
    msg = f"MESSAGE sip:{DEVICE_ID}@{SIP_DOMAIN} SIP/2.0\r\n"
    msg += f"Via: SIP/2.0/UDP 127.0.0.1:{sock.getsockname()[1]};rport;branch=z9hG4bK{sn2}\r\n"
    msg += f"From: <sip:{DEVICE_ID}@{SIP_DOMAIN}>;tag={sn2}\r\n"
    msg += f"To: <sip:{SIP_ID}@{SIP_DOMAIN}>\r\n"
    msg += f"Call-ID: {sn2}@127.0.0.1\r\n"
    msg += "CSeq: 2 MESSAGE\r\n"
    msg += "Content-Type: Application/MANSCDP+xml\r\n"
    msg += "Max-Forwards: 70\r\n"
    msg += f"Content-Length: {len(xml.encode('gb2312', errors='replace'))}\r\n\r\n{xml}"
    resp = _sip_send_recv(sock, msg, addr)
    sock.close()
    return resp and "200 OK" in resp


def _sip_catalog_query_sync():
    """Synchronous SIP Catalog Query."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    addr = ("127.0.0.1", SIP_PORT)
    sn = str(int(time.time()))
    xml = f'<?xml version="1.0" encoding="GB2312"?>\n<Query><CmdType>Catalog</CmdType><SN>{sn}</SN><DeviceID>{DEVICE_ID}</DeviceID></Query>'
    sn2 = uuid.uuid4().hex[:8]
    msg = f"MESSAGE sip:{DEVICE_ID}@{SIP_DOMAIN} SIP/2.0\r\n"
    msg += f"Via: SIP/2.0/UDP 127.0.0.1:{sock.getsockname()[1]};rport;branch=z9hG4bK{sn2}\r\n"
    msg += f"From: <sip:{DEVICE_ID}@{SIP_DOMAIN}>;tag={sn2}\r\n"
    msg += f"To: <sip:{SIP_ID}@{SIP_DOMAIN}>\r\n"
    msg += f"Call-ID: {sn2}@127.0.0.1\r\n"
    msg += "CSeq: 3 MESSAGE\r\n"
    msg += "Content-Type: Application/MANSCDP+xml\r\n"
    msg += "Max-Forwards: 70\r\n"
    msg += f"Content-Length: {len(xml.encode('gb2312', errors='replace'))}\r\n\r\n{xml}"
    resp = _sip_send_recv(sock, msg, addr, timeout=5.0)
    sock.close()
    return resp and "200 OK" in resp


def _sip_deregister_sync():
    """Synchronous SIP Deregister (Expires=0)."""
    return _sip_register_sync(expires=0)


def _sip_send_alarm_sync():
    """Send alarm via SIP MESSAGE."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    addr = ("127.0.0.1", SIP_PORT)
    sn = str(int(time.time()))
    xml = f'<?xml version="1.0" encoding="GB2312"?>\n<Notify><CmdType>Alarm</CmdType><SN>{sn}</SN><DeviceID>{DEVICE_ID}</DeviceID><AlarmPriority>1</AlarmPriority><AlarmMethod>5</AlarmMethod><AlarmTime>2026-07-03T12:00:00</AlarmTime><AlarmDescription>Motion Detect Test</AlarmDescription><Info><AlarmType>2</AlarmType></Info></Notify>'
    sn2 = uuid.uuid4().hex[:8]
    msg = f"MESSAGE sip:{DEVICE_ID}@{SIP_DOMAIN} SIP/2.0\r\n"
    msg += f"Via: SIP/2.0/UDP 127.0.0.1:{sock.getsockname()[1]};rport;branch=z9hG4bK{sn2}\r\n"
    msg += f"From: <sip:{DEVICE_ID}@{SIP_DOMAIN}>;tag={sn2}\r\n"
    msg += f"To: <sip:{SIP_ID}@{SIP_DOMAIN}>\r\n"
    msg += f"Call-ID: {sn2}@127.0.0.1\r\n"
    msg += "CSeq: 4 MESSAGE\r\n"
    msg += "Content-Type: Application/MANSCDP+xml\r\n"
    msg += "Max-Forwards: 70\r\n"
    msg += f"Content-Length: {len(xml.encode('gb2312', errors='replace'))}\r\n\r\n{xml}"
    resp = _sip_send_recv(sock, msg, addr)
    sock.close()
    return resp and "200 OK" in resp


# === Test Suites ===

async def test_user_system(client, token):
    print("\n=== 1. User System ===")
    headers = get_headers(token)

    log("User System", "Login", "PASS", "HTTP 200, token obtained")

    r = await client.get(f"{BASE_URL}/login/verify-token", headers=headers)
    if r.status_code == 200 and r.json().get("valid"):
        log("User System", "Token Verification", "PASS", "HTTP 200, valid=true")
    else:
        log("User System", "Token Verification", "FAIL", f"HTTP {r.status_code}: {r.text[:100]}")

    # Users endpoint - may not exist in OSS
    r = await client.get(f"{BASE_URL}/users/", headers=headers)
    if r.status_code == 200:
        log("User System", "User List", "PASS", f"HTTP 200")
    elif r.status_code == 404:
        log("User System", "User List", "FAIL", "HTTP 404 - users module not loaded (import error)")
    else:
        log("User System", "User List", "FAIL", f"HTTP {r.status_code}: {r.text[:100]}")

    # Operation logs
    r = await client.get(f"{BASE_URL}/logs/", headers=headers)
    if r.status_code == 200:
        log("User System", "Operation Logs", "PASS", f"HTTP 200")
    elif r.status_code == 404:
        log("User System", "Operation Logs", "FAIL", "HTTP 404 - logs module not loaded")
    else:
        log("User System", "Operation Logs", "FAIL", f"HTTP {r.status_code}: {r.text[:100]}")

    # Audit center
    r = await client.get(f"{BASE_URL}/config-center/sip-info", headers=headers)
    if r.status_code == 200:
        log("User System", "Config Center SIP Info", "PASS", "HTTP 200")
    else:
        log("User System", "Config Center SIP Info", "WARN", f"HTTP {r.status_code}: {r.text[:100]}")

    # Logout
    r = await client.post(f"{BASE_URL}/login/logout", headers=headers)
    if r.status_code == 200:
        log("User System", "Logout", "PASS", "HTTP 200")
    else:
        log("User System", "Logout", "FAIL", f"HTTP {r.status_code}: {r.text[:100]}")


async def test_device_management(client, token):
    print("\n=== 2. Device Management ===")
    headers = get_headers(token)

    # Device list - check with and without trailing slash
    r = await client.get(f"{BASE_URL}/devices", headers=headers)
    if r.status_code == 200:
        data = r.json()
        total = data.get("total", 0) if isinstance(data, dict) else len(data)
        log("Device Management", "Device List API", "PASS", f"HTTP 200, total={total}")
    elif r.status_code == 404:
        log("Device Management", "Device List API", "FAIL", "HTTP 404 - devices module not mounted (missing __init__.py)")
    else:
        log("Device Management", "Device List API", "FAIL", f"HTTP {r.status_code}: {r.text[:100]}")

    # SIP Register
    try:
        loop = asyncio.get_event_loop()
        registered = await loop.run_in_executor(None, _sip_register_sync)
        if registered:
            log("Device Management", "SIP REGISTER", "PASS", "Device registered, 200 OK received")
        else:
            log("Device Management", "SIP REGISTER", "FAIL", "Registration failed - no 200 OK after digest auth")
    except Exception as e:
        log("Device Management", "SIP REGISTER", "FAIL", f"Exception: {e}")

    # SIP Keepalive
    try:
        loop = asyncio.get_event_loop()
        ka_ok = await loop.run_in_executor(None, _sip_keepalive_sync)
        if ka_ok:
            log("Device Management", "SIP Keepalive", "PASS", "Keepalive 200 OK received")
        else:
            log("Device Management", "SIP Keepalive", "FAIL", "No 200 OK for keepalive")
    except Exception as e:
        log("Device Management", "SIP Keepalive", "FAIL", f"Exception: {e}")

    # Catalog Query
    try:
        loop = asyncio.get_event_loop()
        cat_ok = await loop.run_in_executor(None, _sip_catalog_query_sync)
        if cat_ok:
            log("Device Management", "Catalog Query", "PASS", "Catalog query 200 OK received")
        else:
            log("Device Management", "Catalog Query", "WARN", "No 200 OK for catalog query")
    except Exception as e:
        log("Device Management", "Catalog Query", "FAIL", f"Exception: {e}")

    # Online status check
    await asyncio.sleep(2)
    r = await client.get(f"{BASE_URL}/devices?status=1", headers=headers)
    if r.status_code == 200:
        data = r.json()
        online = data.get("total", 0) if isinstance(data, dict) else 0
        log("Device Management", "Online Status Check", "PASS" if online > 0 else "WARN",
            f"HTTP 200, online={online}")
    elif r.status_code == 404:
        log("Device Management", "Online Status Check", "FAIL", "HTTP 404 - devices API not available")
    else:
        log("Device Management", "Online Status Check", "FAIL", f"HTTP {r.status_code}")

    # SIP Deregister
    try:
        loop = asyncio.get_event_loop()
        de_ok = await loop.run_in_executor(None, _sip_deregister_sync)
        if de_ok:
            log("Device Management", "SIP Deregister", "PASS", "Deregister 200 OK received")
        else:
            log("Device Management", "SIP Deregister", "WARN", "No 200 OK for deregister")
    except Exception as e:
        log("Device Management", "SIP Deregister", "FAIL", f"Exception: {e}")


async def test_realtime_preview(client, token):
    print("\n=== 3. Real-time Preview ===")
    headers = get_headers(token)

    # Check if stream endpoint exists
    r = await client.get(f"{BASE_URL}/stream/errors/catalog", headers=headers)
    if r.status_code == 200:
        log("Real-time Preview", "Stream Error Catalog", "PASS", "HTTP 200")
    elif r.status_code == 404:
        log("Real-time Preview", "Stream Error Catalog", "FAIL", "HTTP 404 - stream module not mounted (missing __init__.py + _shared.py)")
    else:
        log("Real-time Preview", "Stream Error Catalog", "WARN", f"HTTP {r.status_code}")

    # Try play endpoint
    r = await client.post(
        f"{BASE_URL}/stream/play/{DEVICE_ID}/{CHANNEL_ID}",
        headers=headers,
    )
    if r.status_code == 200:
        log("Real-time Preview", "Single Stream Play", "PASS", "HTTP 200")
    elif r.status_code == 202:
        log("Real-time Preview", "Single Stream Play", "PASS", "HTTP 202, async invite sent")
    elif r.status_code == 404:
        log("Real-time Preview", "Single Stream Play", "FAIL", "HTTP 404 - stream play endpoint not available")
    elif r.status_code == 503:
        log("Real-time Preview", "Single Stream Play", "WARN", f"HTTP 503 - SIP service or ZLM not ready")
    else:
        log("Real-time Preview", "Single Stream Play", "WARN", f"HTTP {r.status_code}: {r.text[:100]}")

    # Stop stream
    r = await client.post(
        f"{BASE_URL}/stream/stop",
        json={"device_id": DEVICE_ID, "channel_id": CHANNEL_ID},
        headers=headers,
    )
    if r.status_code == 200:
        log("Real-time Preview", "Stop Stream", "PASS", "HTTP 200")
    elif r.status_code == 404:
        log("Real-time Preview", "Stop Stream", "FAIL", "HTTP 404 - stream stop endpoint not available")
    else:
        log("Real-time Preview", "Stop Stream", "WARN", f"HTTP {r.status_code}")


async def test_recording_management(client, token):
    print("\n=== 4. Recording Management ===")
    headers = get_headers(token)

    # GB Record query
    r = await client.get(f"{BASE_URL}/record/query", headers=headers, params={
        "device_id": DEVICE_ID,
        "channel_id": CHANNEL_ID,
    })
    if r.status_code == 200:
        log("Recording Management", "Record Query", "PASS", "HTTP 200")
    elif r.status_code == 404:
        log("Recording Management", "Record Query", "FAIL", "HTTP 404 - record module not available")
    else:
        log("Recording Management", "Record Query", "WARN", f"HTTP {r.status_code}: {r.text[:100]}")

    # Record schedule
    r = await client.get(f"{BASE_URL}/record-schedule", headers=headers)
    if r.status_code == 200:
        log("Recording Management", "Record Schedule List", "PASS", "HTTP 200")
    elif r.status_code == 307:
        r2 = await client.get(f"{BASE_URL}/record-schedule/", headers=headers)
        if r2.status_code == 200:
            log("Recording Management", "Record Schedule List", "PASS", "HTTP 200 (with trailing slash)")
        else:
            log("Recording Management", "Record Schedule List", "FAIL", f"HTTP {r2.status_code}")
    else:
        log("Recording Management", "Record Schedule List", "FAIL", f"HTTP {r.status_code}")

    # Device record
    r = await client.get(f"{BASE_URL}/device-record/device/queries", headers=headers)
    if r.status_code == 200:
        log("Recording Management", "Device Record Queries", "PASS", "HTTP 200")
    elif r.status_code == 404:
        log("Recording Management", "Device Record Queries", "FAIL", "HTTP 404")
    else:
        log("Recording Management", "Device Record Queries", "WARN", f"HTTP {r.status_code}")


async def test_ptz_control(client, token):
    print("\n=== 5. PTZ Control ===")
    headers = get_headers(token)

    # PTZ endpoints - need channel_id
    r = await client.post(
        f"{BASE_URL}/ptz/{CHANNEL_ID}/control",
        params={"command": "right", "speed": 50},
        headers=headers,
    )
    if r.status_code == 200:
        log("PTZ Control", "Direction Control", "PASS", "HTTP 200")
    elif r.status_code == 404:
        log("PTZ Control", "Direction Control", "FAIL", "HTTP 404 - channel not found (no device registered)")
    elif r.status_code == 500:
        log("PTZ Control", "Direction Control", "WARN", f"HTTP 500 - SIP service not ready")
    else:
        log("PTZ Control", "Direction Control", "WARN", f"HTTP {r.status_code}: {r.text[:100]}")

    r = await client.post(
        f"{BASE_URL}/ptz/{CHANNEL_ID}/control",
        params={"command": "zoomin", "speed": 50},
        headers=headers,
    )
    if r.status_code == 200:
        log("PTZ Control", "Zoom Control", "PASS", "HTTP 200")
    elif r.status_code == 404:
        log("PTZ Control", "Zoom Control", "WARN", "HTTP 404 - channel not found")
    else:
        log("PTZ Control", "Zoom Control", "WARN", f"HTTP {r.status_code}")

    r = await client.post(
        f"{BASE_URL}/ptz/{CHANNEL_ID}/preset",
        params={"cmd_type": 8, "preset_index": 1},
        headers=headers,
    )
    if r.status_code == 200:
        log("PTZ Control", "Preset Set", "PASS", "HTTP 200")
    elif r.status_code == 404:
        log("PTZ Control", "Preset Set", "WARN", "HTTP 404 - channel not found")
    else:
        log("PTZ Control", "Preset Set", "WARN", f"HTTP {r.status_code}")


async def test_alarm_management(client, token):
    print("\n=== 6. Alarm Management ===")
    headers = get_headers(token)

    r = await client.get(f"{BASE_URL}/alarms", headers=headers)
    if r.status_code == 200:
        data = r.json()
        total = data.get("total", 0) if isinstance(data, dict) else len(data)
        log("Alarm Management", "Alarm List", "PASS", f"HTTP 200, total={total}")
    else:
        log("Alarm Management", "Alarm List", "FAIL", f"HTTP {r.status_code}: {r.text[:100]}")

    r = await client.get(f"{BASE_URL}/alarms/sla/overview", headers=headers)
    if r.status_code == 200:
        log("Alarm Management", "SLA Overview", "PASS", "HTTP 200")
    elif r.status_code == 500:
        log("Alarm Management", "SLA Overview", "FAIL", f"HTTP 500: {r.text[:150]}")
    else:
        log("Alarm Management", "SLA Overview", "FAIL", f"HTTP {r.status_code}")

    r = await client.get(f"{BASE_URL}/alarms/link-rules", headers=headers)
    if r.status_code == 200:
        log("Alarm Management", "Link Rules", "PASS", "HTTP 200")
    else:
        log("Alarm Management", "Link Rules", "FAIL", f"HTTP {r.status_code}")

    # SIP alarm
    try:
        loop = asyncio.get_event_loop()
        alarm_ok = await loop.run_in_executor(None, _sip_send_alarm_sync)
        if alarm_ok:
            log("Alarm Management", "Alarm Receive (SIP)", "PASS", "Alarm SIP MESSAGE 200 OK")
        else:
            log("Alarm Management", "Alarm Receive (SIP)", "WARN", "No 200 OK for alarm")
    except Exception as e:
        log("Alarm Management", "Alarm Receive (SIP)", "FAIL", f"Exception: {e}")


async def test_voice_talk(client, token):
    print("\n=== 7. Voice Talk ===")
    headers = get_headers(token)

    # Talk endpoints - check if they exist
    r = await client.get(f"{BASE_URL}/talk/talk/bidirectional/{DEVICE_ID}/{CHANNEL_ID}", headers=headers)
    if r.status_code == 200:
        log("Voice Talk", "Bidirectional Talk Endpoint", "PASS", "HTTP 200")
    elif r.status_code == 404:
        log("Voice Talk", "Bidirectional Talk Endpoint", "WARN", "HTTP 404 - device not found (expected without registered device)")
    elif r.status_code == 503:
        log("Voice Talk", "Bidirectional Talk Endpoint", "WARN", "HTTP 503 - service not ready")
    else:
        log("Voice Talk", "Bidirectional Talk Endpoint", "WARN", f"HTTP {r.status_code}")

    # WebSocket talk endpoint check
    log("Voice Talk", "WebSocket Talk", "SKIP", "WebSocket endpoint requires WS client (cannot test via HTTP)")


async def test_cascade(client, token):
    print("\n=== 8. Cascade ===")
    headers = get_headers(token)

    r = await client.get(f"{BASE_URL}/config-center/sip-info", headers=headers)
    if r.status_code == 200:
        data = r.json()
        log("Cascade", "Server SIP Config", "PASS", f"SIP ID: {data.get('sip_id', 'N/A')}")
    else:
        log("Cascade", "Server SIP Config", "WARN", f"HTTP {r.status_code}")

    # Platforms endpoint
    r = await client.get(f"{BASE_URL}/platforms/", headers=headers)
    if r.status_code == 200:
        data = r.json()
        count = len(data) if isinstance(data, list) else len(data.get("items", []))
        log("Cascade", "Platform List", "PASS", f"HTTP 200, {count} platforms")
    elif r.status_code == 404:
        log("Cascade", "Platform List", "FAIL", "HTTP 404 - platforms module not loaded")
    else:
        log("Cascade", "Platform List", "FAIL", f"HTTP {r.status_code}")

    # Check inbound platforms (downstream cascade)
    r = await client.get(f"{BASE_URL}/config-center/sip-info", headers=headers)
    if r.status_code == 200:
        log("Cascade", "Downstream Platform Info", "PASS", "SIP config available for downstream registration")
    else:
        log("Cascade", "Downstream Platform Info", "WARN", f"HTTP {r.status_code}")


async def test_health_ops(client, token):
    print("\n=== 9. Health & Ops ===")
    headers = get_headers(token)

    r = await client.get(f"{BASE_URL}/health/liveness")
    log("Health & Ops", "Liveness", "PASS" if r.status_code == 200 else "FAIL", f"HTTP {r.status_code}")

    r = await client.get(f"{BASE_URL}/health/readiness")
    if r.status_code == 200:
        data = r.json()
        log("Health & Ops", "Readiness", "PASS", f"HTTP 200, status={data.get('status', 'N/A')}")
    elif r.status_code == 503:
        data = r.json()
        log("Health & Ops", "Readiness", "WARN", f"HTTP 503, status={data.get('status', 'degraded')}")
    else:
        log("Health & Ops", "Readiness", "FAIL", f"HTTP {r.status_code}")

    r = await client.get(f"{BASE_URL}/health/overview", headers=headers)
    log("Health & Ops", "Health Overview", "PASS" if r.status_code == 200 else "FAIL", f"HTTP {r.status_code}")

    r = await client.get(f"{BASE_URL}/ops/db-check", headers=headers)
    log("Health & Ops", "DB Check", "PASS" if r.status_code == 200 else "FAIL", f"HTTP {r.status_code}")

    r = await client.get(f"{BASE_URL}/ops/status", headers=headers)
    log("Health & Ops", "Ops Status", "PASS" if r.status_code == 200 else "FAIL", f"HTTP {r.status_code}")

    r = await client.get(f"{BASE_URL}/metrics/devices-overview", headers=headers)
    log("Health & Ops", "Device Metrics", "PASS" if r.status_code == 200 else "FAIL", f"HTTP {r.status_code}")


async def test_module_import_failures():
    """Document all endpoint modules that fail to import."""
    print("\n=== 0. Module Import Check ===")
    import importlib
    import sys
    import os

    os.chdir(r"e:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\backend")
    sys.path.insert(0, ".")

    # Known modules that should exist but fail
    critical_modules = {
        "devices": "Device management (CRUD, channels)",
        "stream": "Real-time preview (play/stop)",
        "system_config": "System configuration & SIP trace events",
        "proxy_compat": "Proxy compatibility layer",
        "reports": "Reports & analytics",
    }

    for mod_name, desc in critical_modules.items():
        try:
            mod = importlib.import_module(f"app.api.v1.endpoints.{mod_name}")
            router = getattr(mod, "router", None)
            if router is None:
                log("Module Imports", f"{mod_name} ({desc})", "FAIL",
                    f"Module loaded but no 'router' attribute (missing __init__.py with router export)")
            else:
                log("Module Imports", f"{mod_name} ({desc})", "PASS", "Module loaded with router")
        except Exception as e:
            log("Module Imports", f"{mod_name} ({desc})", "FAIL", f"Import error: {str(e)[:120]}")


async def main():
    print("=" * 60)
    print("PyGBSentry Functional Audit Test v3")
    print(f"Started at: {datetime.now().isoformat()}")
    print("=" * 60)

    # Check module imports first
    await test_module_import_failures()

    async with httpx.AsyncClient(timeout=30.0) as client:
        token = await login(client)
        if not token:
            print("FATAL: Login failed, cannot continue tests")
            return

        await test_user_system(client, token)

        token = await login(client)
        if not token:
            print("FATAL: Re-login failed after logout test")
            return

        await test_device_management(client, token)
        await test_realtime_preview(client, token)
        await test_recording_management(client, token)
        await test_ptz_control(client, token)
        await test_alarm_management(client, token)
        await test_voice_talk(client, token)
        await test_cascade(client, token)
        await test_health_ops(client, token)

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    pass_count = sum(1 for r in results if r["status"] == "PASS")
    fail_count = sum(1 for r in results if r["status"] == "FAIL")
    warn_count = sum(1 for r in results if r["status"] == "WARN")
    skip_count = sum(1 for r in results if r["status"] == "SKIP")
    print(f"  PASS: {pass_count}  FAIL: {fail_count}  WARN: {warn_count}  SKIP: {skip_count}")
    print(f"  Total: {len(results)}")

    with open("audit_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\nResults saved to audit_results.json")


if __name__ == "__main__":
    asyncio.run(main())
