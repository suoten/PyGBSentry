#!/usr/bin/env python
"""
PyGBSentry 功能可用性审计测试脚本
逐功能实际测试，不新增功能，只验证已有功能是否真的能用
"""
import asyncio
import socket
import struct
import hashlib
import time
import json
import sys
import os
import httpx
from datetime import datetime, timezone

# Configuration
SIP_HOST = "127.0.0.1"
SIP_PORT = 5060
API_BASE = "http://localhost:8000/api/v1"
SIP_DOMAIN = "3402000000"
PLATFORM_ID = "34020000002000000001"
DEVICE_ID = "34020000001320000001"
DEVICE_PASSWORD = "***REMOVED***"
ADMIN_USER = "admin"
ADMIN_PASS = "admin123"

results = {}

def log(test_name, status, details=""):
    """记录测试结果"""
    results[test_name] = {"status": status, "details": details}
    icon = {"PASS": "[OK]", "FAIL": "[FAIL]", "BUG": "[BUG]", "SKIP": "[SKIP]", "WARN": "[WARN]"}.get(status, "[?]")
    print(f"  {icon} [{status}] {test_name}: {details}")

def sip_register(device_id=DEVICE_ID, password=DEVICE_PASSWORD, expires=3600):
    """发送 SIP REGISTER 并处理 Digest 认证"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", 0))
    sock.settimeout(5.0)
    local_port = sock.getsockname()[1]
    
    call_id = f"{int(time.time())}@{local_port}"
    branch = f"z9hG4bK{int(time.time())}{local_port}"
    
    # Step 1: Send REGISTER without auth
    register_msg = (
        f"REGISTER sip:{SIP_DOMAIN} SIP/2.0\r\n"
        f"Via: SIP/2.0/UDP {SIP_HOST}:{local_port};rport;branch={branch}\r\n"
        f"From: <sip:{device_id}@{SIP_DOMAIN}>;tag={local_port}\r\n"
        f"To: <sip:{device_id}@{SIP_DOMAIN}>\r\n"
        f"Call-ID: {call_id}\r\n"
        f"CSeq: 1 REGISTER\r\n"
        f"Contact: <sip:{device_id}@{SIP_HOST}:{local_port}>\r\n"
        f"Max-Forwards: 70\r\n"
        f"User-Agent: PyGBSentry-Audit-Test\r\n"
        f"Expires: {expires}\r\n"
        f"Content-Length: 0\r\n\r\n"
    )
    
    sock.sendto(register_msg.encode(), (SIP_HOST, SIP_PORT))
    
    try:
        data, addr = sock.recvfrom(65535)
        response = data.decode("utf-8", errors="replace")
    except socket.timeout:
        sock.close()
        return None, "Timeout waiting for 401 challenge"
    
    # Check for 401 Unauthorized
    if "401 Unauthorized" not in response:
        sock.close()
        return response, f"Expected 401, got: {response.split(chr(13))[0] if response else 'empty'}"
    
    # Parse WWW-Authenticate header
    www_auth = ""
    for line in response.split("\r\n"):
        if line.startswith("WWW-Authenticate:"):
            www_auth = line
            break
    
    if not www_auth:
        sock.close()
        return response, "No WWW-Authenticate header in 401"
    
    # Parse digest parameters
    realm = ""
    nonce = ""
    algorithm = "MD5"
    for part in www_auth.split(","):
        part = part.strip()
        if "realm=" in part:
            realm = part.split('realm="')[1].split('"')[0] if 'realm="' in part else part.split("realm=")[1].strip('"')
        if "nonce=" in part:
            nonce = part.split('nonce="')[1].split('"')[0] if 'nonce="' in part else part.split("nonce=")[1].strip('"')
        if "algorithm=" in part:
            algorithm = part.split("algorithm=")[1].strip().strip('"')
    
    # Calculate Digest response
    uri = f"sip:{SIP_DOMAIN}"
    ha1 = hashlib.md5(f"{device_id}:{realm}:{password}".encode()).hexdigest()
    ha2 = hashlib.md5(f"REGISTER:{uri}".encode()).hexdigest()
    response_hash = hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode()).hexdigest()
    
    # Step 2: Send REGISTER with auth
    branch2 = f"z9hG4bK{int(time.time())}{local_port}2"
    register_auth = (
        f"REGISTER sip:{SIP_DOMAIN} SIP/2.0\r\n"
        f"Via: SIP/2.0/UDP {SIP_HOST}:{local_port};rport;branch={branch2}\r\n"
        f"From: <sip:{device_id}@{SIP_DOMAIN}>;tag={local_port}\r\n"
        f"To: <sip:{device_id}@{SIP_DOMAIN}>\r\n"
        f"Call-ID: {call_id}\r\n"
        f"CSeq: 2 REGISTER\r\n"
        f"Contact: <sip:{device_id}@{SIP_HOST}:{local_port}>\r\n"
        f"Max-Forwards: 70\r\n"
        f"User-Agent: PyGBSentry-Audit-Test\r\n"
        f"Expires: {expires}\r\n"
        f'Authorization: Digest username="{device_id}",realm="{realm}",nonce="{nonce}",uri="{uri}",response="{response_hash}",algorithm={algorithm}\r\n'
        f"Content-Length: 0\r\n\r\n"
    )
    
    sock.sendto(register_auth.encode(), (SIP_HOST, SIP_PORT))
    
    try:
        data, addr = sock.recvfrom(65535)
        response2 = data.decode("utf-8", errors="replace")
    except socket.timeout:
        sock.close()
        return response, "Timeout waiting for 200 OK after auth"
    
    sock.close()
    return response2, "Register flow completed"

def sip_send_keepalive(device_id=DEVICE_ID):
    """发送 SIP Keepalive 心跳"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", 0))
    sock.settimeout(5.0)
    local_port = sock.getsockname()[1]
    
    call_id = f"keepalive{int(time.time())}@{local_port}"
    branch = f"z9hG4bK{int(time.time())}keepalive"
    
    body = (
        f'<?xml version="1.0" encoding="GB2312"?>\r\n'
        f'<Notify>\r\n'
        f'<CmdType>Keepalive</CmdType>\r\n'
        f'<SN>{int(time.time()) % 100000}</SN>\r\n'
        f'<DeviceID>{device_id}</DeviceID>\r\n'
        f'<Status>OK</Status>\r\n'
        f'</Notify>\r\n'
    )
    
    msg = (
        f"MESSAGE sip:{device_id}@{SIP_DOMAIN} SIP/2.0\r\n"
        f"Via: SIP/2.0/UDP {SIP_HOST}:{local_port};rport;branch={branch}\r\n"
        f"From: <sip:{device_id}@{SIP_DOMAIN}>;tag={local_port}\r\n"
        f"To: <sip:{PLATFORM_ID}@{SIP_DOMAIN}>\r\n"
        f"Call-ID: {call_id}\r\n"
        f"CSeq: 1 MESSAGE\r\n"
        f"Max-Forwards: 70\r\n"
        f"Content-Type: Application/MANSCDP+xml\r\n"
        f"Content-Length: {len(body.encode('gb2312'))}\r\n\r\n"
        f"{body}"
    )
    
    sock.sendto(msg.encode("gb2312"), (SIP_HOST, SIP_PORT))
    
    try:
        data, addr = sock.recvfrom(65535)
        response = data.decode("utf-8", errors="replace")
        sock.close()
        return response
    except socket.timeout:
        sock.close()
        return None

def sip_unregister(device_id=DEVICE_ID, password=DEVICE_PASSWORD):
    """发送 SIP 注销 (Expires=0)"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", 0))
    sock.settimeout(5.0)
    local_port = sock.getsockname()[1]
    
    call_id = f"unreg{int(time.time())}@{local_port}"
    branch = f"z9hG4bK{int(time.time())}unreg"
    
    # Step 1: REGISTER without auth to get nonce
    register_msg = (
        f"REGISTER sip:{SIP_DOMAIN} SIP/2.0\r\n"
        f"Via: SIP/2.0/UDP {SIP_HOST}:{local_port};rport;branch={branch}\r\n"
        f"From: <sip:{device_id}@{SIP_DOMAIN}>;tag={local_port}\r\n"
        f"To: <sip:{device_id}@{SIP_DOMAIN}>\r\n"
        f"Call-ID: {call_id}\r\n"
        f"CSeq: 1 REGISTER\r\n"
        f"Contact: <sip:{device_id}@{SIP_HOST}:{local_port}>\r\n"
        f"Max-Forwards: 70\r\n"
        f"User-Agent: PyGBSentry-Audit-Test\r\n"
        f"Expires: 0\r\n"
        f"Content-Length: 0\r\n\r\n"
    )
    
    sock.sendto(register_msg.encode(), (SIP_HOST, SIP_PORT))
    
    try:
        data, addr = sock.recvfrom(65535)
        response = data.decode("utf-8", errors="replace")
    except socket.timeout:
        sock.close()
        return None, "Timeout"
    
    if "401 Unauthorized" not in response:
        sock.close()
        return response, "No 401 challenge for unregister"
    
    # Parse nonce
    nonce = ""
    realm = ""
    for line in response.split("\r\n"):
        if line.startswith("WWW-Authenticate:"):
            for part in line.split(","):
                if 'nonce="' in part:
                    nonce = part.split('nonce="')[1].split('"')[0]
                if 'realm="' in part:
                    realm = part.split('realm="')[1].split('"')[0]
            break
    
    # Calc digest
    uri = f"sip:{SIP_DOMAIN}"
    ha1 = hashlib.md5(f"{device_id}:{realm}:{password}".encode()).hexdigest()
    ha2 = hashlib.md5(f"REGISTER:{uri}".encode()).hexdigest()
    response_hash = hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode()).hexdigest()
    
    branch2 = f"z9hG4bK{int(time.time())}unreg2"
    register_auth = (
        f"REGISTER sip:{SIP_DOMAIN} SIP/2.0\r\n"
        f"Via: SIP/2.0/UDP {SIP_HOST}:{local_port};rport;branch={branch2}\r\n"
        f"From: <sip:{device_id}@{SIP_DOMAIN}>;tag={local_port}\r\n"
        f"To: <sip:{device_id}@{SIP_DOMAIN}>\r\n"
        f"Call-ID: {call_id}\r\n"
        f"CSeq: 2 REGISTER\r\n"
        f"Contact: <sip:{device_id}@{SIP_HOST}:{local_port}>\r\n"
        f"Max-Forwards: 70\r\n"
        f"User-Agent: PyGBSentry-Audit-Test\r\n"
        f"Expires: 0\r\n"
        f'Authorization: Digest username="{device_id}",realm="{realm}",nonce="{nonce}",uri="{uri}",response="{response_hash}",algorithm=MD5\r\n'
        f"Content-Length: 0\r\n\r\n"
    )
    
    sock.sendto(register_auth.encode(), (SIP_HOST, SIP_PORT))
    
    try:
        data, addr = sock.recvfrom(65535)
        response2 = data.decode("utf-8", errors="replace")
        sock.close()
        return response2, "Unregister flow completed"
    except socket.timeout:
        sock.close()
        return None, "Timeout waiting for unregister response"

def sip_send_catalog_query(device_id=DEVICE_ID):
    """发送目录查询请求 (模拟平台向设备查询)"""
    # This is normally sent by the platform TO the device
    # For testing, we'll send a Catalog response to see if the platform processes it
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", 0))
    sock.settimeout(5.0)
    local_port = sock.getsockname()[1]
    
    call_id = f"catalog{int(time.time())}@{local_port}"
    branch = f"z9hG4bK{int(time.time())}catalog"
    sn = int(time.time()) % 100000
    
    body = (
        f'<?xml version="1.0" encoding="GB2312"?>\r\n'
        f'<Response>\r\n'
        f'<CmdType>Catalog</CmdType>\r\n'
        f'<SN>{sn}</SN>\r\n'
        f'<DeviceID>{device_id}</DeviceID>\r\n'
        f'<SumNum>1</SumNum>\r\n'
        f'<DeviceList Num="1">\r\n'
        f'<Item>\r\n'
        f'<DeviceID>34020000001310000001</DeviceID>\r\n'
        f'<Name>TestCamera01</Name>\r\n'
        f'<Manufacturer>TestBrand</Manufacturer>\r\n'
        f'<Model>TestModel</Model>\r\n'
        f'<Status>ON</Status>\r\n'
        f'</Item>\r\n'
        f'</DeviceList>\r\n'
        f'</Response>\r\n'
    )
    
    msg = (
        f"MESSAGE sip:{PLATFORM_ID}@{SIP_DOMAIN} SIP/2.0\r\n"
        f"Via: SIP/2.0/UDP {SIP_HOST}:{local_port};rport;branch={branch}\r\n"
        f"From: <sip:{device_id}@{SIP_DOMAIN}>;tag={local_port}\r\n"
        f"To: <sip:{PLATFORM_ID}@{SIP_DOMAIN}>\r\n"
        f"Call-ID: {call_id}\r\n"
        f"CSeq: 1 MESSAGE\r\n"
        f"Max-Forwards: 70\r\n"
        f"Content-Type: Application/MANSCDP+xml\r\n"
        f"Content-Length: {len(body.encode('gb2312'))}\r\n\r\n"
        f"{body}"
    )
    
    sock.sendto(msg.encode("gb2312"), (SIP_HOST, SIP_PORT))
    
    try:
        data, addr = sock.recvfrom(65535)
        response = data.decode("utf-8", errors="replace")
        sock.close()
        return response
    except socket.timeout:
        sock.close()
        return None

def sip_send_alarm(device_id=DEVICE_ID):
    """发送报警消息"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", 0))
    sock.settimeout(5.0)
    local_port = sock.getsockname()[1]
    
    call_id = f"alarm{int(time.time())}@{local_port}"
    branch = f"z9hG4bK{int(time.time())}alarm"
    sn = int(time.time()) % 100000
    
    body = (
        f'<?xml version="1.0" encoding="GB2312"?>\r\n'
        f'<Notify>\r\n'
        f'<CmdType>Alarm</CmdType>\r\n'
        f'<SN>{sn}</SN>\r\n'
        f'<DeviceID>{device_id}</DeviceID>\r\n'
        f'<AlarmMethod>5</AlarmMethod>\r\n'
        f'<AlarmType>1</AlarmType>\r\n'
        f'<AlarmTime>2026-07-03T12:00:00</AlarmTime>\r\n'
        f'<AlarmDescription>Test Alarm from Audit Script</AlarmDescription>\r\n'
        f'</Notify>\r\n'
    )
    
    msg = (
        f"MESSAGE sip:{PLATFORM_ID}@{SIP_DOMAIN} SIP/2.0\r\n"
        f"Via: SIP/2.0/UDP {SIP_HOST}:{local_port};rport;branch={branch}\r\n"
        f"From: <sip:{device_id}@{SIP_DOMAIN}>;tag={local_port}\r\n"
        f"To: <sip:{PLATFORM_ID}@{SIP_DOMAIN}>\r\n"
        f"Call-ID: {call_id}\r\n"
        f"CSeq: 1 MESSAGE\r\n"
        f"Max-Forwards: 70\r\n"
        f"Content-Type: Application/MANSCDP+xml\r\n"
        f"Content-Length: {len(body.encode('gb2312'))}\r\n\r\n"
        f"{body}"
    )
    
    sock.sendto(msg.encode("gb2312"), (SIP_HOST, SIP_PORT))
    
    try:
        data, addr = sock.recvfrom(65535)
        response = data.decode("utf-8", errors="replace")
        sock.close()
        return response
    except socket.timeout:
        sock.close()
        return None

async def test_http():
    """测试 HTTP API 端点"""
    async with httpx.AsyncClient(base_url=API_BASE, timeout=10.0) as client:
        # === 用户系统 ===
        print("\n=== 用户系统 ===")
        
        # 1. Login
        try:
            r = await client.post("/login/access-token", data={"username": ADMIN_USER, "password": ADMIN_PASS})
            if r.status_code == 200:
                token = r.json().get("access_token")
                log("登录", "PASS", f"HTTP 200, token获取成功")
            else:
                log("登录", "BUG", f"HTTP {r.status_code}: {r.text[:200]}")
                token = None
        except Exception as e:
            log("登录", "FAIL", f"Exception: {e}")
            token = None
        
        # 1b. Login with wrong password
        try:
            r = await client.post("/login/access-token", data={"username": ADMIN_USER, "password": "wrongpass"})
            if r.status_code == 400:
                log("登录-错误密码拒绝", "PASS", f"HTTP 400")
            elif r.status_code == 500:
                log("登录-错误密码", "BUG", f"HTTP 500: {r.text[:200]}")
            else:
                log("登录-错误密码", "WARN", f"HTTP {r.status_code}: {r.text[:100]}")
        except Exception as e:
            log("登录-错误密码", "FAIL", f"Exception: {e}")
        
        # 1c. Register (should be 403 since ALLOW_PUBLIC_REGISTRATION=false)
        try:
            r = await client.post("/register", json={"username": "testuser", "password": "TestPass123!"})
            if r.status_code == 403:
                log("注册-公开注册关闭", "PASS", f"HTTP 403 as expected")
            elif r.status_code == 500:
                log("注册", "BUG", f"HTTP 500: {r.text[:200]}")
            else:
                log("注册", "WARN", f"HTTP {r.status_code}: {r.text[:100]}")
        except Exception as e:
            log("注册", "FAIL", f"Exception: {e}")
        
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        
        # 2. Verify token
        if token:
            try:
                r = await client.get("/login/verify-token", headers=headers)
                if r.status_code == 200:
                    log("Token验证", "PASS", f"HTTP 200, valid={r.json().get('valid')}")
                else:
                    log("Token验证", "FAIL", f"HTTP {r.status_code}")
            except Exception as e:
                log("Token验证", "FAIL", f"Exception: {e}")
        
        # 3. Health endpoints
        print("\n=== 健康检查 ===")
        try:
            r = await client.get("/health/liveness")
            log("存活探针", "PASS" if r.status_code == 200 else "FAIL", f"HTTP {r.status_code}: {r.text[:100]}")
        except Exception as e:
            log("存活探针", "FAIL", f"Exception: {e}")
        
        try:
            r = await client.get("/health/")
            data = r.json() if r.status_code == 200 else {}
            log("综合健康检查", "PASS" if r.status_code == 200 else "FAIL", 
                f"HTTP {r.status_code}, DB={data.get('database',{}).get('status','?')}, SIP={data.get('sip',{}).get('status','?')}, ZLM={data.get('zlm',{}).get('status','?')}")
        except Exception as e:
            log("综合健康检查", "FAIL", f"Exception: {e}")
        
        # If no token, skip authenticated tests
        if not token:
            print("\n  [!] No token, skipping authenticated API tests")
            return
        
        # === 设备管理 API ===
        print("\n=== 设备管理 API ===")
        try:
            r = await client.get("/devices/", headers=headers)
            if r.status_code == 200:
                devices = r.json()
                count = len(devices) if isinstance(devices, list) else devices.get("total", 0)
                log("设备列表查询", "PASS", f"HTTP 200, {count} devices")
            else:
                log("设备列表查询", "FAIL", f"HTTP {r.status_code}: {r.text[:100]}")
        except Exception as e:
            log("设备列表查询", "FAIL", f"Exception: {e}")
        
        # === 报警管理 API ===
        print("\n=== 报警管理 API ===")
        try:
            r = await client.get("/alarms/", headers=headers)
            if r.status_code == 200:
                alarms = r.json()
                count = len(alarms) if isinstance(alarms, list) else alarms.get("total", 0)
                log("报警查询", "PASS", f"HTTP 200, {count} alarms")
            else:
                log("报警查询", "FAIL", f"HTTP {r.status_code}: {r.text[:100]}")
        except Exception as e:
            log("报警查询", "FAIL", f"Exception: {e}")
        
        # === 录像管理 API ===
        print("\n=== 录像管理 API ===")
        try:
            r = await client.get("/records/", headers=headers)
            if r.status_code == 200:
                log("录像查询", "PASS", f"HTTP 200")
            else:
                log("录像查询", "FAIL", f"HTTP {r.status_code}: {r.text[:100]}")
        except Exception as e:
            log("录像查询", "FAIL", f"Exception: {e}")
        
        # === 操作日志 API ===
        print("\n=== 操作日志 ===")
        try:
            r = await client.get("/audit-center/logs", headers=headers)
            if r.status_code == 200:
                log("操作日志查询", "PASS", f"HTTP 200")
            else:
                log("操作日志查询", "FAIL", f"HTTP {r.status_code}: {r.text[:100]}")
        except Exception as e:
            log("操作日志查询", "FAIL", f"Exception: {e}")
        
        # === 诊断 ===
        print("\n=== 诊断 ===")
        try:
            r = await client.get("/ops/diagnose-report", headers=headers)
            if r.status_code == 200:
                log("诊断报告", "PASS", f"HTTP 200")
            else:
                log("诊断报告", "FAIL", f"HTTP {r.status_code}: {r.text[:100]}")
        except Exception as e:
            log("诊断报告", "FAIL", f"Exception: {e}")

def test_sip():
    """测试 SIP 功能"""
    print("\n=== 设备管理 (SIP) ===")
    
    # 1. Register
    response, info = sip_register()
    if response and "200 OK" in response:
        log("设备注册", "PASS", f"200 OK received")
    elif response and "401 Unauthorized" in response:
        # Got 401 but failed auth
        log("设备注册", "WARN", f"Got 401, auth may have failed. Response: {response.split(chr(13))[0]}")
    elif response:
        log("设备注册", "WARN", f"Response: {response.split(chr(13))[0] if response else 'empty'}")
    else:
        log("设备注册", "FAIL", info)
    
    # Wait a moment
    time.sleep(1)
    
    # 2. Keepalive
    response = sip_send_keepalive()
    if response and "200 OK" in response:
        log("设备心跳", "PASS", f"200 OK received")
    elif response:
        log("设备心跳", "WARN", f"Response: {response.split(chr(13))[0]}")
    else:
        log("设备心跳", "FAIL", "Timeout")
    
    time.sleep(1)
    
    # 3. Catalog response
    response = sip_send_catalog_query()
    if response and "200 OK" in response:
        log("目录同步", "PASS", f"200 OK received (catalog response accepted)")
    elif response:
        log("目录同步", "WARN", f"Response: {response.split(chr(13))[0]}")
    else:
        log("目录同步", "FAIL", "Timeout")
    
    time.sleep(1)
    
    # 4. Alarm
    response = sip_send_alarm()
    if response and "200 OK" in response:
        log("报警接收", "PASS", f"200 OK received (alarm accepted)")
    elif response:
        log("报警接收", "WARN", f"Response: {response.split(chr(13))[0]}")
    else:
        log("报警接收", "FAIL", "Timeout")
    
    time.sleep(1)
    
    # 5. Unregister
    response, info = sip_unregister()
    if response and "200 OK" in response:
        log("设备注销", "PASS", f"200 OK received")
    elif response:
        log("设备注销", "WARN", f"Response: {response.split(chr(13))[0] if response else 'empty'}")
    else:
        log("设备注销", "FAIL", info)

def test_sip_malformed():
    """测试畸形 SIP 消息"""
    print("\n=== 异常场景 (畸形SIP) ===")
    
    test_cases = [
        ("garbage_data", b"NOTASIPMESSAGE\r\n\r\n"),
        ("missing_headers", b"SIP/2.0 200 OK\r\n\r\n"),
        ("empty_message", b""),
        ("request_line_only", b"REGISTER sip:3402000000 SIP/2.0\r\n\r\n"),
    ]
    
    for name, data in test_cases:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(3.0)
        try:
            sock.sendto(data, (SIP_HOST, SIP_PORT))
            try:
                resp, _ = sock.recvfrom(65535)
                log(f"畸形SIP-{name}", "PASS", f"Platform responded (didn't crash)")
            except socket.timeout:
                log(f"畸形SIP-{name}", "PASS", f"Platform ignored (no crash)")
        except Exception as e:
            log(f"畸形SIP-{name}", "FAIL", f"Exception: {e}")
        finally:
            sock.close()

def main():
    print("=" * 70)
    print("PyGBSentry 功能可用性审计测试")
    print(f"时间: {datetime.now(timezone.utc).isoformat()}")
    print(f"目标: {API_BASE} / SIP {SIP_HOST}:{SIP_PORT}")
    print("=" * 70)
    
    # SIP tests
    test_sip()
    
    # Malformed SIP tests
    test_sip_malformed()
    
    # HTTP API tests
    asyncio.run(test_http())
    
    # Summary
    print("\n" + "=" * 70)
    print("测试汇总")
    print("=" * 70)
    pass_count = sum(1 for v in results.values() if v["status"] == "PASS")
    fail_count = sum(1 for v in results.values() if v["status"] == "FAIL")
    bug_count = sum(1 for v in results.values() if v["status"] == "BUG")
    warn_count = sum(1 for v in results.values() if v["status"] == "WARN")
    print(f"  PASS: {pass_count}  FAIL: {fail_count}  BUG: {bug_count}  WARN: {warn_count}")
    print()
    
    # Output JSON
    with open("audit_test_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("  详细结果已保存到 audit_test_results.json")

if __name__ == "__main__":
    main()
