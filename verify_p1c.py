"""验证 P1-C: 使用全新 ticket 测试 talk WS"""
import requests, socket, warnings
warnings.filterwarnings("ignore")

BASE = "http://127.0.0.1:8000"
SIP_ID = "34020000001320000001"
H = {"Authorization": f"Bearer {requests.post(f'{BASE}/api/v1/login/access-token', data={'username':'admin','password':'admin123'}, timeout=5).json()['access_token']}"}

# 每次测试都用全新 ticket
def test_ws(path, label):
    r = requests.post(f"{BASE}/api/v1/auth/ws-ticket", headers=H, timeout=5)
    if r.status_code != 200:
        print(f"  [{label}] ws-ticket 失败: {r.status_code}")
        return
    ticket = r.json().get("ticket")
    ws_path = f"{path}?ticket={ticket}"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect(("127.0.0.1", 8000))
        key = "dGhlIHNhbXBsZSBub25jZQ=="
        req = (
            f"GET {ws_path} HTTP/1.1\r\n"
            f"Host: 127.0.0.1:8000\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n"
        )
        s.sendall(req.encode())
        data = s.recv(4096)
        status_line = data.decode(errors="replace").split("\r\n")[0]
        print(f"  [{label}] {path} -> {status_line}")
        s.close()
    except Exception as e:
        print(f"  [{label}] ERROR: {e!r}")

print("=== P1-C 验证: 全新 ticket 测试 talk WS ===")
test_ws(f"/api/v1/alarms/ws", "alarms WS (对照)")
test_ws(f"/api/v1/talk/ws/talk/{SIP_ID}", "talk 广播 WS")
test_ws(f"/api/v1/talk/talk/bidirectional/{SIP_ID}/{SIP_ID}", "talk 双向 WS")

print("\n=== P0-B 验证: 报警入库状态 ===")
r = requests.get(f"{BASE}/api/v1/alarms", headers=H, params={"limit": 50}, timeout=5)
if r.status_code == 200:
    data = r.json()
    items = data.get("items", []) if isinstance(data, dict) else data
    print(f"  报警总数: {len(items)}")
    for a in items:
        # 注意字段名是 time/method，不是 alarm_time/alarm_method
        print(f"    - desc={a.get('description','')[:40]} time={a.get('time')} method={a.get('method')} lon={a.get('longitude')} lat={a.get('latitude')}")
