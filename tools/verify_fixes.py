"""验证所有修复的端点是否正常工作（带正确登录凭据）。"""
import urllib.request
import urllib.error
import urllib.parse
import json

BASE = "http://127.0.0.1:8000/api/v1"

def _get(path, token=None):
    url = f"{BASE}{path}"
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        r = urllib.request.urlopen(req, timeout=5)
        return r.status, r.read().decode()[:300]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300] if e.fp else ""
    except Exception as e:
        return -1, str(e)[:200]

def _post(path, data=None, token=None, is_form=False):
    url = f"{BASE}{path}"
    if is_form:
        body = urllib.parse.urlencode(data or {}).encode()
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    else:
        body = json.dumps(data or {}).encode()
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        r = urllib.request.urlopen(req, timeout=5)
        return r.status, r.read().decode()[:300]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300] if e.fp else ""
    except Exception as e:
        return -1, str(e)[:200]

def login():
    url = f"{BASE}/login/access-token"
    body = urllib.parse.urlencode({"username": "admin", "password": "admin123"}).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        r = urllib.request.urlopen(req, timeout=5)
        data = json.loads(r.read().decode())
        return data.get("access_token") or ""
    except Exception as e:
        print(f"  Login error: {e}")
        return ""

results = []

def check(name, path, expected_codes, token=None, method="GET"):
    if method == "GET":
        code, resp = _get(path, token)
    else:
        code, resp = _post(path, token=token)
    status = "PASS" if code in expected_codes else f"FAIL({code})"
    results.append((name, path, status, code))
    print(f"  [{status}] {name}: {method} {path} -> {code}")
    if code not in expected_codes:
        print(f"         Response: {resp[:200]}")
    return code

print("=" * 70)
print("PyGBSentry BUG 修复验证 (带 Token)")
print("=" * 70)

# 先登录获取 token
print("\n[1] 登录获取 Token...")
token = login()
if token:
    print(f"  [PASS] Token 获取成功: {token[:30]}...")
else:
    print("  [FAIL] 登录失败，尝试无 Token 测试")

# ─── BUG-A1: 设备管理 API ─────────────────────────────────────────────────────
print("\n[2] BUG-A1: 设备管理 API (之前 404)")
check("设备列表", "/devices", {200}, token)

# ─── BUG-A2: 实时预览 API ─────────────────────────────────────────────────────
print("\n[3] BUG-A2: 实时预览 API (之前 404)")
check("流错误目录", "/stream/errors/catalog", {200}, token)

# ─── BUG-A3: 系统配置 API ─────────────────────────────────────────────────────
print("\n[4] BUG-A3: 系统配置 API (之前 404)")
check("SIP追踪事件", "/system-config/sip-trace-events", {200}, token)

# ─── BUG-U1: 用户管理 API ─────────────────────────────────────────────────────
print("\n[5] BUG-U1: 用户管理 API (之前 404)")
check("用户列表", "/users", {200}, token)
check("当前用户", "/users/me", {200}, token)

# ─── BUG-C1: 级联平台 API ─────────────────────────────────────────────────────
print("\n[6] BUG-C1: 级联平台 API (之前 404)")
check("平台列表", "/platforms", {200}, token)
check("服务器配置", "/platforms/server_config", {200}, token)

# ─── BUG-U2: 操作日志 API ─────────────────────────────────────────────────────
print("\n[7] BUG-U2: 操作日志 API (之前 404)")
check("日志根路由", "/logs", {200}, token)
check("日志文件列表", "/logs/files", {200}, token)

# ─── BUG-AL1: SLA 概览 API ────────────────────────────────────────────────────
print("\n[8] BUG-AL1: SLA 概览 API (之前 500)")
check("SLA概览", "/alarms/sla/overview", {200}, token)

# ─── 回归测试 ─────────────────────────────────────────────────────────────────
print("\n[9] 回归测试: 原有正常功能")
check("存活探针", "/health/liveness", {200})
check("运维概览", "/health/overview", {200}, token)
check("报警列表", "/alarms", {200}, token)
check("报警联动规则", "/alarms/link-rules", {200}, token)
check("Token校验", f"/login/verify-token?token={token}", {200})

# ─── 汇总 ─────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
pass_count = sum(1 for r in results if "PASS" in r[2])
fail_count = sum(1 for r in results if "FAIL" in r[2])
print(f"总计: {len(results)} 项 | PASS: {pass_count} | FAIL: {fail_count}")
print("=" * 70)
