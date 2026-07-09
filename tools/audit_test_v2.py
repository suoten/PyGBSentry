#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""PyGBSentry 功能可用性审计测试脚本 v2

逐功能测试所有 API 端点 + SIP 信令模拟。
"""
import asyncio
import hashlib
import json
import socket
import struct
import time
import uuid
from datetime import datetime, timezone, timedelta

import httpx

BASE_URL = "http://127.0.0.1:8000/api/v1"

# SIP config (matching .env)
SIP_ID = "34020000002000000001"
SIP_DOMAIN = "3402000000"
SIP_PORT = 5060
DEVICE_ID = "34020000001320000001"
DEVICE_PASSWORD = "test123456"
CHANNEL_ID = "34020000001320000002"

# Test results
results = []


def log(feature, sub_item, status, detail=""):
    """Record a test result."""
    results.append({
        "feature": feature,
        "sub_item": sub_item,
        "status": status,  # PASS / FAIL / SKIP / WARN
        "detail": detail,
    })
    symbol = {"PASS": "[OK]", "FAIL": "[FAIL]", "SKIP": "[SKIP]", "WARN": "[WARN]"}[status]
    print(f"  {symbol} {sub_item}: {detail[:120]}")


async def login(client):
    """Login and return token."""
    r = await client.post(
        f"{BASE_URL}/login/access-token",
        data={"username": "admin", "password": "admin123"},
    )
    if r.status_code == 200:
        return r.json().get("access_token")
    return None


def get_headers(token):
    return {"Authorization": f"Bearer {token}"}


# ============================================================
# 1. User System
# ============================================================
async def test_user_system(client, token):
    print("\n=== 1. User System ===")
    headers = get_headers(token)

    # 1.1 Login (already tested)
    log("User System", "Login", "PASS", "HTTP 200, token obtained")

    # 1.2 Verify token
    r = await client.get(f"{BASE_URL}/login/verify-token", headers=headers)
    if r.status_code == 200 and r.json().get("valid"):
        log("User System", "Token Verification", "PASS", "HTTP 200, valid=true")
    else:
        log("User System", "Token Verification", "FAIL", f"HTTP {r.status_code}: {r.text[:100]}")

    # 1.3 Refresh token
    r_refresh = await client.post(
        f"{BASE_URL}/login/refresh-token",
        json={"refresh_token": token},  # Using access token as refresh (may fail)
        headers=headers,
    )
    if r_refresh.status_code == 200:
        log("User System", "Refresh Token", "PASS", "HTTP 200")
    else:
        log("User System", "Refresh Token", "WARN", f"HTTP {r_refresh.status_code} (expected with access token as refresh)")

    # 1.4 Permission control - list users
    r = await client.get(f"{BASE_URL}/users/", headers=headers)
    if r.status_code == 200:
        data = r.json()
        count = len(data.get("items", data)) if isinstance(data, dict) else len(data)
        log("User System", "User List (Permission)", "PASS", f"HTTP 200, {count} users")
    else:
        log("User System", "User List (Permission)", "FAIL", f"HTTP {r.status_code}: {r.text[:100]}")

    # 1.5 Operation logs
    r = await client.get(f"{BASE_URL}/audit-center/logs", headers=headers)
    if r.status_code == 200:
        data = r.json()
        count = len(data.get("items", data)) if isinstance(data, dict) else len(data)
        log("User System", "Operation Logs", "PASS", f"HTTP 200, {count} log entries")
    else:
        log("User System", "Operation Logs", "FAIL", f"HTTP {r.status_code}: {r.text[:100]}")

    # 1.6 Logout
    r = await client.post(f"{BASE_URL}/login/logout", headers=headers)
    if r.status_code == 200:
        log("User System", "Logout", "PASS", "HTTP 200")
    else:
        log("User System", "Logout", "FAIL", f"HTTP {r.status_code}: {r.text[:100]}")


# ============================================================
# 2. Device Management (SIP Simulation)
# ============================================================
async def test_device_management(client, token):
    print("\n=== 2. Device Management ===")
    headers = get_headers(token)

    # 2.1 List devices
    r = await client.get(f"{BASE_URL}/devices", headers=headers)
    if r.status_code == 200:
        data = r.json()
        total = data.get("total", 0) if isinstance(data, dict) else len(data)
        log("Device Management", "Device List", "PASS", f"HTTP 200, total={total}")
    else:
        log("Device Management", "Device List", "FAIL", f"HTTP {r.status_code}: {r.text[:100]}")

    # 2.2 SIP Registration simulation
    try:
        registered = await sip_register()
        if registered:
            log("Device Management", "SIP REGISTER", "PASS", "Device registered successfully")
        else:
            log("Device Management", "SIP REGISTER", "FAIL", "Registration failed (401 challenge not passed or no response)")
    except Exception as e:
        log("Device Management", "SIP REGISTER", "FAIL", f"Exception: {e}")

    # 2.3 SIP Keepalive
    try:
        ka_ok = await sip_keepalive()
        if ka_ok:
            log("Device Management", "SIP Keepalive", "PASS", "Keepalive 200 OK received")
        else:
            log("Device Management", "SIP Keepalive", "FAIL", "No 200 OK for keepalive")
    except Exception as e:
        log("Device Management", "SIP Keepalive", "FAIL", f"Exception: {e}")

    # 2.4 Catalog query
    try:
        cat_ok = await sip_catalog_query()
        if cat_ok:
            log("Device Management", "Catalog Query", "PASS", "Catalog response received")
        else:
            log("Device Management", "Catalog Query", "WARN", "No catalog response (device may not have channels)")
    except Exception as e:
        log("Device Management", "Catalog Query", "FAIL", f"Exception: {e}")

    # 2.5 Device status check via API
    await asyncio.sleep(2)
    r = await client.get(f"{BASE_URL}/devices?status=1", headers=headers)
    if r.status_code == 200:
        data = r.json()
        online = data.get("total", 0) if isinstance(data, dict) else 0
        log("Device Management", "Online Status Check", "PASS" if online > 0 else "WARN",
            f"HTTP 200, online={online}")
    else:
        log("Device Management", "Online Status Check", "FAIL", f"HTTP {r.status_code}: {r.text[:100]}")

    # 2.6 SIP Deregister
    try:
        de_ok = await sip_deregister()
        if de_ok:
            log("Device Management", "SIP Deregister", "PASS", "Deregister 200 OK received")
        else:
            log("Device Management", "SIP Deregister", "WARN", "No 200 OK for deregister")
    except Exception as e:
        log("Device Management", "SIP Deregister", "FAIL", f"Exception: {e}")


async def sip_send_recv(sock, data, addr, timeout=3.0):
    """Send SIP data and receive response."""
    sock.sendto(data.encode("gb2312", errors="replace"), addr)
    try:
        sock.settimeout(timeout)
        resp, _ = sock.recvfrom(65535)
        return resp.decode("gb2312", errors="replace")
    except socket.timeout:
        return None


def build_register(expires=3600, auth=None):
    sn = uuid.uuid4().hex[:8]
    msg = f"REGISTER sip:{SIP_DOMAIN} SIP/2.0\r\n"
    msg += f"Via: SIP/2.0/UDP 127.0.0.1:5061;rport;branch=z9hG4bK{sn}\r\n"
    msg += f"From: <sip:{DEVICE_ID}@{SIP_DOMAIN}>;tag={sn}\r\n"
    msg += f"To: <sip:{DEVICE_ID}@{SIP_DOMAIN}>\r\n"
    msg += f"Call-ID: {sn}@127.0.0.1\r\n"
    msg += "CSeq: 1 REGISTER\r\n"
    msg += f"Contact: <sip:{DEVICE_ID}@127.0.0.1:5061>\r\n"
    msg += f"Max-Forwards: 70\r\n"
    msg += f"User-Agent: PyGBSentry-Audit-Test\r\n"
    msg += f"Expires: {expires}\r\n"
    if auth:
        msg += f"Authorization: {auth}\r\n"
    msg += "Content-Length: 0\r\n\r\n"
    return msg


def build_keepalive():
    sn = str(int(time.time()))
    xml = f"""<?xml version="1.0" encoding="GB2312"?>
<Notify>
<CmdType>Keepalive</CmdType>
<SN>{sn}</SN>
<DeviceID>{DEVICE_ID}</DeviceID>
<Status>OK</Status>
</Notify>"""
    msg = f"MESSAGE sip:{DEVICE_ID}@{SIP_DOMAIN} SIP/2.0\r\n"
    sn2 = uuid.uuid4().hex[:8]
    msg += f"Via: SIP/2.0/UDP 127.0.0.1:5061;rport;branch=z9hG4bK{sn2}\r\n"
    msg += f"From: <sip:{DEVICE_ID}@{SIP_DOMAIN}>;tag={sn2}\r\n"
    msg += f"To: <sip:{SIP_ID}@{SIP_DOMAIN}>\r\n"
    msg += f"Call-ID: {sn2}@127.0.0.1\r\n"
    msg += "CSeq: 2 MESSAGE\r\n"
    msg += "Content-Type: Application/MANSCDP+xml\r\n"
    msg += f"Max-Forwards: 70\r\n"
    msg += f"Content-Length: {len(xml.encode('gb2312', errors='replace'))}\r\n\r\n"
    msg += xml
    return msg


def build_catalog_query():
    sn = str(int(time.time()))
    xml = f"""<?xml version="1.0" encoding="GB2312"?>
<Query>
<CmdType>Catalog</CmdType>
<SN>{sn}</SN>
<DeviceID>{DEVICE_ID}</DeviceID>
</Query>"""
    msg = f"MESSAGE sip:{DEVICE_ID}@{SIP_DOMAIN} SIP/2.0\r\n"
    sn2 = uuid.uuid4().hex[:8]
    msg += f"Via: SIP/2.0/UDP 127.0.0.1:5061;rport;branch=z9hG4bK{sn2}\r\n"
    msg += f"From: <sip:{DEVICE_ID}@{SIP_DOMAIN}>;tag={sn2}\r\n"
    msg += f"To: <sip:{SIP_ID}@{SIP_DOMAIN}>\r\n"
    msg += f"Call-ID: {sn2}@127.0.0.1\r\n"
    msg += "CSeq: 3 MESSAGE\r\n"
    msg += "Content-Type: Application/MANSCDP+xml\r\n"
    msg += f"Max-Forwards: 70\r\n"
    msg += f"Content-Length: {len(xml.encode('gb2312', errors='replace'))}\r\n\r\n"
    msg += xml
    return msg


def parse_401_challenge(resp):
    """Parse WWW-Authenticate header from 401 response."""
    for line in resp.split("\r\n"):
        if line.startswith("WWW-Authenticate:"):
            # Extract nonce and realm
            import re
            nonce_match = re.search(r'nonce="([^"]+)"', line)
            realm_match = re.search(r'realm="([^"]+)"', line)
            nonce = nonce_match.group(1) if nonce_match else ""
            realm = realm_match.group(1) if realm_match else SIP_DOMAIN
            return nonce, realm
    return None, None


def build_digest_auth(username, password, realm, nonce, uri, method="REGISTER"):
    """Build Digest authentication header."""
    ha1 = hashlib.md5(f"{username}:{realm}:{password}".encode()).hexdigest()
    ha2 = hashlib.md5(f"{method}:{uri}".encode()).hexdigest()
    response = hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode()).hexdigest()
    return f'Digest username="{username}", realm="{realm}", nonce="{nonce}", uri="{uri}", response="{response}"'


async def sip_register():
    """Simulate SIP REGISTER with digest auth."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    addr = ("127.0.0.1", SIP_PORT)

    # Step 1: REGISTER without auth
    reg = build_register()
    resp = await asyncio.get_event_loop().run_in_executor(
        None, lambda: sip_send_recv(sock, reg, addr)
    )
    if not resp:
        sock.close()
        return False

    if "200 OK" in resp:
        sock.close()
        return True

    if "401" in resp or "407" in resp:
        nonce, realm = parse_401_challenge(resp)
        if not nonce:
            sock.close()
            return False
        # Step 2: REGISTER with digest auth
        uri = f"sip:{SIP_DOMAIN}"
        auth = build_digest_auth(DEVICE_ID, DEVICE_PASSWORD, realm, nonce, uri)
        reg2 = build_register(auth=auth)
        resp2 = await asyncio.get_event_loop().run_in_executor(
            None, lambda: sip_send_recv(sock, reg2, addr)
        )
        sock.close()
        return resp2 and "200 OK" in resp2

    sock.close()
    return False


async def sip_keepalive():
    """Send SIP Keepalive message."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    addr = ("127.0.0.1", SIP_PORT)
    ka = build_keepalive()
    resp = await asyncio.get_event_loop().run_in_executor(
        None, lambda: sip_send_recv(sock, ka, addr)
    )
    sock.close()
    return resp and "200 OK" in resp


async def sip_catalog_query():
    """Send SIP Catalog query and wait for response."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    addr = ("127.0.0.1", SIP_PORT)
    cat = build_catalog_query()
    resp = await asyncio.get_event_loop().run_in_executor(
        None, lambda: sip_send_recv(sock, cat, addr, timeout=5.0)
    )
    sock.close()
    return resp and "200 OK" in resp


async def sip_deregister():
    """Send SIP REGISTER with Expires=0 to deregister."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    addr = ("127.0.0.1", SIP_PORT)

    # First register to get auth challenge
    reg = build_register(expires=0)
    resp = await asyncio.get_event_loop().run_in_executor(
        None, lambda: sip_send_recv(sock, reg, addr)
    )
    if not resp:
        sock.close()
        return False

    if "200 OK" in resp:
        sock.close()
        return True

    if "401" in resp or "407" in resp:
        nonce, realm = parse_401_challenge(resp)
        if not nonce:
            sock.close()
            return False
        uri = f"sip:{SIP_DOMAIN}"
        auth = build_digest_auth(DEVICE_ID, DEVICE_PASSWORD, realm, nonce, uri)
        reg2 = build_register(expires=0, auth=auth)
        resp2 = await asyncio.get_event_loop().run_in_executor(
            None, lambda: sip_send_recv(sock, reg2, addr)
        )
        sock.close()
        return resp2 and "200 OK" in resp2

    sock.close()
    return False


# ============================================================
# 3. Real-time Preview
# ============================================================
async def test_realtime_preview(client, token):
    print("\n=== 3. Real-time Preview ===")
    headers = get_headers(token)

    # 3.1 List devices to find a channel
    r = await client.get(f"{BASE_URL}/devices", headers=headers)
    devices = []
    if r.status_code == 200:
        data = r.json()
        devices = data.get("items", data) if isinstance(data, dict) else data

    if not devices:
        log("Real-time Preview", "Single Stream", "SKIP", "No devices available")
        log("Real-time Preview", "Multi Stream", "SKIP", "No devices available")
        log("Real-time Preview", "Stop Stream", "SKIP", "No devices available")
        log("Real-time Preview", "Stream Switch", "SKIP", "No devices available")
        log("Real-time Preview", "Multi Protocol", "SKIP", "No devices available")
        return

    device = devices[0]
    device_id = device.get("gb_id") or device.get("id")

    # Get channels
    r = await client.get(f"{BASE_URL}/devices/{device_id}/channels", headers=headers)
    channels = []
    if r.status_code == 200:
        data = r.json()
        channels = data.get("items", data) if isinstance(data, dict) else data

    if not channels:
        log("Real-time Preview", "Single Stream", "SKIP", f"No channels for device {device_id}")
        return

    channel = channels[0]
    channel_id = channel.get("gb_id") or channel.get("id")

    # 3.1 Single stream play
    r = await client.get(
        f"{BASE_URL}/stream/start",
        params={"device_id": device_id, "channel_id": channel_id},
        headers=headers,
    )
    if r.status_code == 200:
        log("Real-time Preview", "Single Stream Play", "PASS", f"HTTP 200, stream started for {channel_id}")
    elif r.status_code == 202:
        log("Real-time Preview", "Single Stream Play", "PASS", f"HTTP 202, async invite sent for {channel_id}")
    else:
        log("Real-time Preview", "Single Stream Play", "WARN",
            f"HTTP {r.status_code}: {r.text[:100]} (expected without ZLM)")

    # 3.2 Stop stream
    r = await client.post(
        f"{BASE_URL}/stream/stop",
        json={"device_id": device_id, "channel_id": channel_id},
        headers=headers,
    )
    if r.status_code == 200:
        log("Real-time Preview", "Stop Stream", "PASS", "HTTP 200")
    else:
        log("Real-time Preview", "Stop Stream", "WARN",
            f"HTTP {r.status_code}: {r.text[:100]}")

    # 3.3 Multi protocol - check stream list
    r = await client.get(f"{BASE_URL}/stream/list", headers=headers)
    if r.status_code == 200:
        log("Real-time Preview", "Stream List", "PASS", "HTTP 200")
    else:
        log("Real-time Preview", "Stream List", "WARN",
            f"HTTP {r.status_code}: {r.text[:100]}")


# ============================================================
# 4. Recording Management
# ============================================================
async def test_recording_management(client, token):
    print("\n=== 4. Recording Management ===")
    headers = get_headers(token)

    # 4.1 Record query
    r = await client.get(f"{BASE_URL}/gb-record/", headers=headers, params={
        "device_id": DEVICE_ID,
        "channel_id": CHANNEL_ID,
        "start_time": "2026-06-01T00:00:00",
        "end_time": "2026-07-03T23:59:59",
    })
    if r.status_code == 200:
        log("Recording Management", "Record Query", "PASS", "HTTP 200")
    elif r.status_code == 404:
        log("Recording Management", "Record Query", "WARN", f"HTTP 404 (no device registered)")
    else:
        log("Recording Management", "Record Query", "FAIL", f"HTTP {r.status_code}: {r.text[:100]}")

    # 4.2 Record schedule
    r = await client.get(f"{BASE_URL}/record-schedule/", headers=headers)
    if r.status_code == 200:
        log("Recording Management", "Record Schedule List", "PASS", "HTTP 200")
    else:
        log("Recording Management", "Record Schedule List", "FAIL", f"HTTP {r.status_code}: {r.text[:100]}")

    # 4.3 Records list
    r = await client.get(f"{BASE_URL}/records/", headers=headers)
    if r.status_code == 200:
        log("Recording Management", "Records List", "PASS", "HTTP 200")
    else:
        log("Recording Management", "Records List", "FAIL", f"HTTP {r.status_code}: {r.text[:100]}")


# ============================================================
# 5. PTZ Control
# ============================================================
async def test_ptz_control(client, token):
    print("\n=== 5. PTZ Control ===")
    headers = get_headers(token)

    # Get devices and channels
    r = await client.get(f"{BASE_URL}/devices", headers=headers)
    devices = []
    if r.status_code == 200:
        data = r.json()
        devices = data.get("items", data) if isinstance(data, dict) else data

    if not devices:
        log("PTZ Control", "Direction Control", "SKIP", "No devices available")
        log("PTZ Control", "Zoom Control", "SKIP", "No devices available")
        log("PTZ Control", "Preset", "SKIP", "No devices available")
        log("PTZ Control", "Cruise", "SKIP", "No devices available")
        return

    device = devices[0]
    device_id = device.get("gb_id") or device.get("id")

    r = await client.get(f"{BASE_URL}/devices/{device_id}/channels", headers=headers)
    channels = []
    if r.status_code == 200:
        data = r.json()
        channels = data.get("items", data) if isinstance(data, dict) else data

    if not channels:
        log("PTZ Control", "All PTZ", "SKIP", f"No channels for device {device_id}")
        return

    channel_id = channels[0].get("gb_id") or channels[0].get("id")

    # 5.1 Direction control
    r = await client.post(
        f"{BASE_URL}/ptz/{channel_id}/control",
        params={"command": "right", "speed": 50},
        headers=headers,
    )
    if r.status_code == 200:
        log("PTZ Control", "Direction Control", "PASS", "HTTP 200")
    else:
        log("PTZ Control", "Direction Control", "WARN", f"HTTP {r.status_code}: {r.text[:100]}")

    # 5.2 Zoom control
    r = await client.post(
        f"{BASE_URL}/ptz/{channel_id}/control",
        params={"command": "zoomin", "speed": 50},
        headers=headers,
    )
    if r.status_code == 200:
        log("PTZ Control", "Zoom Control", "PASS", "HTTP 200")
    else:
        log("PTZ Control", "Zoom Control", "WARN", f"HTTP {r.status_code}: {r.text[:100]}")

    # 5.3 Preset
    r = await client.post(
        f"{BASE_URL}/ptz/{channel_id}/preset",
        params={"cmd_type": 8, "preset_index": 1},
        headers=headers,
    )
    if r.status_code == 200:
        log("PTZ Control", "Preset Set", "PASS", "HTTP 200")
    else:
        log("PTZ Control", "Preset Set", "WARN", f"HTTP {r.status_code}: {r.text[:100]}")

    # 5.4 Cruise
    r = await client.post(
        f"{BASE_URL}/ptz/{channel_id}/cruise",
        params={"cruise_id": 1, "preset_id": 1, "action": "start"},
        headers=headers,
    )
    if r.status_code == 200:
        log("PTZ Control", "Cruise", "PASS", "HTTP 200")
    else:
        log("PTZ Control", "Cruise", "WARN", f"HTTP {r.status_code}: {r.text[:100]}")


# ============================================================
# 6. Alarm Management
# ============================================================
async def test_alarm_management(client, token):
    print("\n=== 6. Alarm Management ===")
    headers = get_headers(token)

    # 6.1 Alarm list
    r = await client.get(f"{BASE_URL}/alarms", headers=headers)
    if r.status_code == 200:
        data = r.json()
        total = data.get("total", 0) if isinstance(data, dict) else len(data)
        log("Alarm Management", "Alarm List", "PASS", f"HTTP 200, total={total}")
    else:
        log("Alarm Management", "Alarm List", "FAIL", f"HTTP {r.status_code}: {r.text[:100]}")

    # 6.2 SLA overview
    r = await client.get(f"{BASE_URL}/alarms/sla/overview", headers=headers)
    if r.status_code == 200:
        log("Alarm Management", "SLA Overview", "PASS", "HTTP 200")
    else:
        log("Alarm Management", "SLA Overview", "FAIL", f"HTTP {r.status_code}: {r.text[:100]}")

    # 6.3 Alarm link rules
    r = await client.get(f"{BASE_URL}/alarms/link-rules", headers=headers)
    if r.status_code == 200:
        log("Alarm Management", "Link Rules", "PASS", "HTTP 200")
    else:
        log("Alarm Management", "Link Rules", "FAIL", f"HTTP {r.status_code}: {r.text[:100]}")

    # 6.4 Simulate alarm via SIP
    try:
        alarm_ok = await sip_send_alarm()
        if alarm_ok:
            log("Alarm Management", "Alarm Receive (SIP)", "PASS", "Alarm sent via SIP MESSAGE")
        else:
            log("Alarm Management", "Alarm Receive (SIP)", "WARN", "Alarm SIP message sent but no 200 OK")
    except Exception as e:
        log("Alarm Management", "Alarm Receive (SIP)", "FAIL", f"Exception: {e}")


async def sip_send_alarm():
    """Send alarm via SIP MESSAGE."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    addr = ("127.0.0.1", SIP_PORT)
    sn = str(int(time.time()))
    xml = f"""<?xml version="1.0" encoding="GB2312"?>
<Notify>
<CmdType>Alarm</CmdType>
<SN>{sn}</SN>
<DeviceID>{DEVICE_ID}</DeviceID>
<AlarmPriority>1</AlarmPriority>
<AlarmMethod>5</AlarmMethod>
<AlarmTime>2026-07-03T12:00:00</AlarmTime>
<AlarmDescription>Motion Detect Test</AlarmDescription>
<Info>
<AlarmType>2</AlarmType>
</Info>
</Notify>"""
    sn2 = uuid.uuid4().hex[:8]
    msg = f"MESSAGE sip:{DEVICE_ID}@{SIP_DOMAIN} SIP/2.0\r\n"
    msg += f"Via: SIP/2.0/UDP 127.0.0.1:5061;rport;branch=z9hG4bK{sn2}\r\n"
    msg += f"From: <sip:{DEVICE_ID}@{SIP_DOMAIN}>;tag={sn2}\r\n"
    msg += f"To: <sip:{SIP_ID}@{SIP_DOMAIN}>\r\n"
    msg += f"Call-ID: {sn2}@127.0.0.1\r\n"
    msg += "CSeq: 4 MESSAGE\r\n"
    msg += "Content-Type: Application/MANSCDP+xml\r\n"
    msg += f"Max-Forwards: 70\r\n"
    msg += f"Content-Length: {len(xml.encode('gb2312', errors='replace'))}\r\n\r\n"
    msg += xml
    resp = await asyncio.get_event_loop().run_in_executor(
        None, lambda: sip_send_recv(sock, msg, addr)
    )
    sock.close()
    return resp and "200 OK" in resp


# ============================================================
# 7. Voice Talk
# ============================================================
async def test_voice_talk(client, token):
    print("\n=== 7. Voice Talk ===")
    headers = get_headers(token)

    # Check talk endpoint exists
    r = await client.get(f"{BASE_URL}/devices", headers=headers)
    devices = []
    if r.status_code == 200:
        data = r.json()
        devices = data.get("items", data) if isinstance(data, dict) else data

    if not devices:
        log("Voice Talk", "Broadcast", "SKIP", "No devices available")
        log("Voice Talk", "Bidirectional", "SKIP", "No devices available")
        return

    device = devices[0]
    device_id = device.get("gb_id") or device.get("id")

    # Talk endpoint is WebSocket - check if route exists via OpenAPI
    r = await client.get(f"{BASE_URL}/../openapi.json")
    if r.status_code == 200:
        spec = r.json()
        talk_paths = [p for p in spec.get("paths", {}) if "talk" in p.lower()]
        if talk_paths:
            log("Voice Talk", "Talk Endpoints Exist", "PASS", f"Found {len(talk_paths)} talk endpoints")
        else:
            log("Voice Talk", "Talk Endpoints Exist", "WARN", "No talk endpoints in OpenAPI spec")
    else:
        log("Voice Talk", "Talk Endpoints Exist", "WARN", "Cannot access OpenAPI spec")


# ============================================================
# 8. Cascade
# ============================================================
async def test_cascade(client, token):
    print("\n=== 8. Cascade ===")
    headers = get_headers(token)

    # 8.1 Server config
    r = await client.get(f"{BASE_URL}/platforms/server_config", headers=headers)
    if r.status_code == 200:
        data = r.json()
        log("Cascade", "Server Config", "PASS", f"SIP ID: {data.get('sip_id', 'N/A')}")
    else:
        log("Cascade", "Server Config", "FAIL", f"HTTP {r.status_code}: {r.text[:100]}")

    # 8.2 Platform list
    r = await client.get(f"{BASE_URL}/platforms/", headers=headers)
    if r.status_code == 200:
        data = r.json()
        count = len(data) if isinstance(data, list) else len(data.get("items", []))
        log("Cascade", "Platform List", "PASS", f"HTTP 200, {count} platforms")
    else:
        log("Cascade", "Platform List", "FAIL", f"HTTP {r.status_code}: {r.text[:100]}")

    # 8.3 Check cascade diagnosis
    r = await client.get(f"{BASE_URL}/platforms/cascade-diagnosis", headers=headers)
    if r.status_code == 200:
        log("Cascade", "Cascade Diagnosis", "PASS", "HTTP 200")
    else:
        log("Cascade", "Cascade Diagnosis", "WARN", f"HTTP {r.status_code}: {r.text[:100]}")


# ============================================================
# 9. Health & Ops
# ============================================================
async def test_health_ops(client, token):
    print("\n=== 9. Health & Ops ===")
    headers = get_headers(token)

    r = await client.get(f"{BASE_URL}/health/liveness")
    if r.status_code == 200:
        log("Health & Ops", "Liveness", "PASS", "HTTP 200")
    else:
        log("Health & Ops", "Liveness", "FAIL", f"HTTP {r.status_code}")

    r = await client.get(f"{BASE_URL}/health/readiness")
    if r.status_code == 200:
        data = r.json()
        log("Health & Ops", "Readiness", "PASS", f"HTTP 200, status={data.get('status', 'N/A')}")
    else:
        log("Health & Ops", "Readiness", "WARN", f"HTTP {r.status_code}")

    r = await client.get(f"{BASE_URL}/ops/db-check")
    if r.status_code == 200:
        log("Health & Ops", "DB Check", "PASS", "HTTP 200")
    else:
        log("Health & Ops", "DB Check", "FAIL", f"HTTP {r.status_code}")


# ============================================================
# Main
# ============================================================
async def main():
    print("=" * 60)
    print("PyGBSentry Functional Audit Test v2")
    print(f"Started at: {datetime.now().isoformat()}")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Login first
        token = await login(client)
        if not token:
            print("FATAL: Login failed, cannot continue tests")
            return

        # Run all test suites
        await test_user_system(client, token)

        # Re-login since logout was tested
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

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    pass_count = sum(1 for r in results if r["status"] == "PASS")
    fail_count = sum(1 for r in results if r["status"] == "FAIL")
    warn_count = sum(1 for r in results if r["status"] == "WARN")
    skip_count = sum(1 for r in results if r["status"] == "SKIP")
    print(f"  PASS: {pass_count}  FAIL: {fail_count}  WARN: {warn_count}  SKIP: {skip_count}")
    print(f"  Total: {len(results)}")

    # Save results to JSON
    with open("audit_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\nResults saved to audit_results.json")


if __name__ == "__main__":
    asyncio.run(main())
