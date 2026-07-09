# SIP链路+ZLM RTP诊断与修复 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复GB28181实时视频无法播放的问题——设备回复200 OK后ZLM始终收不到RTP媒体流

**Architecture:** 通过深入分析SIP信令链路和ZLM RTP服务器行为，发现3层问题：(1) SIP审计缺失outbound INVITE导致无法验证SDP内容；(2) ZLM RTP服务器在设备推流前超时关闭；(3) 缺少RTP端口可达性诊断。修复策略：增强可观测性→修复RTP超时竞态→添加网络诊断

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy async, ZLMediaKit, SIP/GB28181

---

## 问题根因分析

### 日志时间线（09:05:13 INVITE流程）

| 时间 | 事件 |
|------|------|
| 09:05:13.476 | SDP IP解析: `pygbsentry.jjtt.net` → `106.119.160.150` |
| 09:05:13.497 | openRtpServer → port=30000 |
| 09:05:13.535 | Sent Play INVITE (SSRC=0086503774, sdp_ip=106.119.160.150, media_port=30000) |
| 09:05:13.669 | 收到200 OK (设备修改SSRC: 0086503774→0200000012) |
| 09:05:13.687 | [Probe] getMediaList返回EMPTY |
| 09:05:13.701 | updateRtpServerSSRC成功 |
| 09:05:13.707 | Sent ACK |
| 09:05:14~17 | 设备重传200 OK (4次)，每次触发updateRtpServerSSRC |
| 09:05:19.698 | [Probe] getMediaList count=5（但无匹配流） |
| 09:05:28.500 | **RTP Server Timeout** (15秒后ZLM关闭RTP服务器) |
| 09:05:29.087 | [SSRC Recovery] 重新打开RTP服务器（但设备已停止推流） |

### 根因链

1. **SIP审计缺失outbound INVITE** — `invite.py`通过`tx_manager.send_request`发送INVITE时未调用`HOOK_ON_SIP_SEND`，导致SIP审计日志无法记录发出的INVITE SDP内容，无法验证`c=IN IP4`行是否正确
2. **ZLM 15秒RTP超时太短** — 设备从收到INVITE到开始推流可能需要>15秒（特别是NAT场景），ZLM默认15秒无数据就关闭RTP服务器
3. **RTP超时后SSRC Recovery无效** — 重新打开RTP服务器后设备不知道，设备已停止推流
4. **缺少RTP端口可达性诊断** — 无法判断UDP 30000是否可达，是网络问题还是代码问题
5. **Probe轮询过于频繁** — 每250ms调用3次getMediaList，造成ZLM API压力

---

## File Structure

| 文件 | 操作 | 职责 |
|------|------|------|
| `backend/app/sip/invite.py` | 修改 | 添加HOOK_ON_SIP_SEND调用，记录outbound INVITE |
| `backend/app/sip/response_handler.py` | 修改 | 优化SSRC Recovery逻辑 |
| `backend/app/api/v1/endpoints/hook.py` | 修改 | 增加RTP超时时间配置 |
| `backend/app/api/v1/endpoints/stream/stream_play.py` | 修改 | 降低Probe频率，添加流名匹配日志 |
| `backend/app/services/zlm_rtp_server_service.py` | 修改 | 添加RTP服务器状态诊断API |
| `backend/app/core/config.py` | 修改 | 添加RTP超时相关配置项 |
| `backend/app/sip/commander.py` | 检查 | 确认HOOK_ON_SIP_SEND调用模式 |
| `backend/tests/test_sip_outbound_audit.py` | 创建 | 测试outbound INVITE审计日志 |

---

### Task 1: 添加outbound INVITE SIP审计日志

**问题:** `invite.py`发送INVITE时未调用`HOOK_ON_SIP_SEND`，SIP审计日志无法记录发出的INVITE SDP

**Files:**
- Modify: `backend/app/sip/invite.py:2630-2642`
- Create: `backend/tests/test_sip_outbound_audit.py`

- [ ] **Step 1: 在invite.py的INVITE发送处添加HOOK_ON_SIP_SEND调用**

在 `_send_invite_common_inner` 函数中，`tx_manager.send_request` 调用之前，添加SIP审计日志记录：

```python
# 在 line ~2633 (result["original_sdp"] = sdp ...) 之后添加:
try:
    from app.core.plugin_manager import plugin_manager, HOOK_ON_SIP_SEND
    _bg_create_task(plugin_manager.emit(HOOK_ON_SIP_SEND, req, addr, proto))
except Exception as _audit_err:
    logger.debug(f"SIP audit hook failed (non-critical): {_audit_err}")
```

同样在 fallback `send_sip_bytes` 路径中也添加审计日志：

```python
# 在 line ~2640 (await send_sip_bytes(proto, transport, addr, data)) 之后添加:
try:
    from app.core.plugin_manager import plugin_manager, HOOK_ON_SIP_SEND
    _bg_create_task(plugin_manager.emit(HOOK_ON_SIP_SEND, req, addr, proto))
except Exception as _audit_err:
    logger.debug(f"SIP audit hook failed (non-critical): {_audit_err}")
```

- [ ] **Step 2: 在Re-INVITE发送处也添加HOOK_ON_SIP_SEND**

在 `_send_invite_common_inner` 的 stream switch 路径（line ~1069）和 HA failover 路径（line ~1280）中，`tx_manager.send_request` 调用之前，同样添加 `HOOK_ON_SIP_SEND` 调用。

- [ ] **Step 3: 编写测试**

创建 `backend/tests/test_sip_outbound_audit.py`:

```python
"""测试outbound INVITE是否触发SIP审计日志hook"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.mark.asyncio
async def test_invite_emits_sip_send_hook():
    """验证_send_invite_common_inner发送INVITE时调用HOOK_ON_SIP_SEND"""
    with patch("app.sip.invite._get_client_tx_manager") as mock_txm, \
         patch("app.core.plugin_manager.plugin_manager.emit", new_callable=AsyncMock) as mock_emit:
        mock_txm.return_value = MagicMock(send_request=AsyncMock())
        # ... 构造调用参数并调用 _send_invite_common_inner ...
        # 验证 mock_emit 被调用且参数包含 HOOK_ON_SIP_SEND
        assert any("on_sip_send" in str(call) for call in mock_emit.call_args_list)
```

- [ ] **Step 4: 运行测试验证**

Run: `cd backend && python -m pytest tests/test_sip_outbound_audit.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/sip/invite.py backend/tests/test_sip_outbound_audit.py
git commit -m "fix: add HOOK_ON_SIP_SEND for outbound INVITE audit logging"
```

---

### Task 2: 增加ZLM RTP超时时间并添加配置项

**问题:** ZLM默认15秒RTP超时太短，NAT场景下设备推流延迟可能超过15秒

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/api/v1/endpoints/hook.py`

- [ ] **Step 1: 在config.py中添加RTP超时配置项**

```python
# 在 config.py 的 Settings 类中添加:
RTP_SERVER_TIMEOUT_SECONDS: int = int(os.getenv("RTP_SERVER_TIMEOUT_SECONDS", "30") or "30")
"""ZLM RTP Server超时秒数，NAT场景建议>=30秒"""
```

- [ ] **Step 2: 在hook.py的on_rtp_server_timeout中使用配置的超时值**

修改 `on_rtp_server_timeout` 函数，在调用 `_cleanup_sessions` 之前检查距离INVITE发送的时间，如果未超过配置的超时时间，则跳过清理并重新打开RTP服务器：

```python
# 在 on_rtp_server_timeout 中，_cleanup_sessions 调用之前添加:
_rtp_timeout_config = int(getattr(settings, "RTP_SERVER_TIMEOUT_SECONDS", 30) or 30)
# 检查stream_session的创建时间，如果距离现在不到_rtp_timeout_config秒，跳过清理
if stream_session and hasattr(stream_session, "created_at"):
    from datetime import datetime, timezone
    _elapsed = (datetime.now(timezone.utc) - stream_session.created_at).total_seconds()
    if _elapsed < _rtp_timeout_config:
        logger.info(f"[RTP Timeout] Grace period active: elapsed={_elapsed:.1f}s < config={_rtp_timeout_config}s, "
                    f"skipping cleanup for {app_name}/{stream_id}")
        return
```

- [ ] **Step 3: 在.env中添加配置**

在 `.env` 文件中添加:
```
# ZLM RTP Server超时秒数（默认30，NAT场景建议60）
RTP_SERVER_TIMEOUT_SECONDS=60
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/config.py backend/app/api/v1/endpoints/hook.py backend/.env
git commit -m "fix: increase RTP server timeout for NAT scenarios, add configurable timeout"
```

---

### Task 3: 添加RTP端口可达性诊断

**问题:** 无法判断UDP 30000端口是否可达，无法区分网络问题与代码问题

**Files:**
- Modify: `backend/app/api/v1/endpoints/network_diagnostics.py`
- Modify: `backend/app/services/zlm_rtp_server_service.py`

- [ ] **Step 1: 在zlm_rtp_server_service.py中添加RTP服务器状态查询函数**

```python
async def get_rtp_server_status(
    host: str, http_port: int, secret: str, stream_id: str | None = None
) -> dict:
    """查询ZLM RTP Server状态，用于诊断"""
    try:
        params = {"secret": secret}
        if stream_id:
            params["stream_id"] = stream_id
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"http://{host}:{http_port}/index/api/getRtpServerStatus",
                params=params
            )
            return resp.json()
    except Exception as e:
        return {"code": -1, "msg": str(e)}
```

- [ ] **Step 2: 在network_diagnostics.py中添加RTP端口诊断端点**

添加一个诊断端点，检查：
1. ZLM进程是否运行
2. RTP端口是否监听
3. 从ZLM API查询RTP服务器状态
4. 检查防火墙规则（Linux only）

```python
@router.get("/rtp-port-check", summary="RTP端口可达性诊断")
async def rtp_port_check():
    """检查RTP端口是否可达，用于诊断视频无法播放问题"""
    from app.core.config import settings
    from app.services.zlm_rtp_server_service import get_rtp_server_status

    results = {
        "zlm_host": settings.MEDIA_SERVER_HOST,
        "rtp_port": settings.MEDIA_SERVER_RTP_PROXY_PORT,
        "checks": {}
    }

    # Check 1: ZLM HTTP API reachable
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"http://{settings.MEDIA_SERVER_HOST}:{settings.MEDIA_SERVER_HTTP_PORT}/index/api/getServerConfig",
                params={"secret": settings.MEDIA_SERVER_SECRET}
            )
            results["checks"]["zlm_api"] = {"ok": True, "status": resp.status_code}
    except Exception as e:
        results["checks"]["zlm_api"] = {"ok": False, "error": str(e)}

    # Check 2: RTP server status
    try:
        status = await get_rtp_server_status(
            host=settings.MEDIA_SERVER_HOST,
            http_port=settings.MEDIA_SERVER_HTTP_PORT,
            secret=settings.MEDIA_SERVER_SECRET,
        )
        results["checks"]["rtp_server"] = {"ok": status.get("code") == 0, "data": status}
    except Exception as e:
        results["checks"]["rtp_server"] = {"ok": False, "error": str(e)}

    # Check 3: UDP port listening (local check)
    import socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2)
        test_port = int(settings.MEDIA_SERVER_RTP_PROXY_PORT or 30000)
        # 尝试绑定到同一端口（如果ZLM已占用则失败，说明ZLM在监听）
        try:
            sock.bind(("0.0.0.0", test_port))
            results["checks"]["udp_port"] = {"ok": False, "warning": f"Port {test_port} is NOT occupied by ZLM (bind succeeded)"}
            sock.close()
        except OSError:
            results["checks"]["udp_port"] = {"ok": True, "msg": f"Port {test_port} is occupied (likely by ZLM)"}
    except Exception as e:
        results["checks"]["udp_port"] = {"ok": None, "error": str(e)}

    return results
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/v1/endpoints/network_diagnostics.py backend/app/services/zlm_rtp_server_service.py
git commit -m "feat: add RTP port reachability diagnostics endpoint"
```

---

### Task 4: 优化Probe轮询频率并添加流名匹配日志

**问题:** Probe每250ms调用3次getMediaList，过于频繁；且不记录ZLM实际返回的流名，无法诊断流名不匹配问题

**Files:**
- Modify: `backend/app/api/v1/endpoints/stream/stream_play.py`

- [ ] **Step 1: 降低Probe频率，从250ms改为500ms**

在 `_wait_zlm_stream_ready` 函数中，将轮询间隔从 0.25 秒改为 0.5 秒：

搜索 `0.25` 或 `asyncio.sleep(0.25)` 在 stream_play.py 中的 Probe 轮询逻辑，替换为：

```python
await asyncio.sleep(0.5)  # OPTIMIZED: 从0.25s降为0.5s，减少ZLM API压力
```

- [ ] **Step 2: 添加ZLM实际流名日志**

在 Probe 检查逻辑中，当 `ZLM_returned_count > 0` 但未找到匹配流时，记录ZLM实际返回的流名：

```python
# 在 [Probe] 日志后添加:
if zlm_count > 0 and not found:
    _actual_streams = []
    for _app_data in _all_media_data.values():
        if isinstance(_app_data, list):
            for _s in _app_data:
                if isinstance(_s, dict):
                    _actual_streams.append(f"{_s.get('app', '?')}/{_s.get('stream', '?')}")
    if _actual_streams:
        logger.warning(f"[Probe] Stream NOT found! ZLM actual streams: {_actual_streams[:10]}")
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/v1/endpoints/stream/stream_play.py
git commit -m "fix: reduce probe frequency and add actual stream name logging"
```

---

### Task 5: 修复SSRC Recovery后设备不知道新RTP服务器的问题

**问题:** RTP超时后SSRC Recovery重新打开RTP服务器，但设备不知道新的session，已停止推流。需要在Recovery后发送re-INVITE通知设备。

**Files:**
- Modify: `backend/app/sip/response_handler.py`

- [ ] **Step 1: 在SSRC Recovery成功后，不发送ACK（因为已经发过了），而是记录详细日志**

在 `_try_reopen_rtp_server_on_ssrc_mismatch` 成功后，添加日志说明设备可能需要重新INVITE：

```python
# 在 SSRC Recovery 成功后添加:
logger.warning(
    f"[SSRC Recovery] RTP server reopened for {stream_id}, but device may have stopped pushing. "
    f"Consider sending re-INVITE if stream doesn't appear within 5 seconds. "
    f"New RTP server port={_allocated_port}, SSRC={ssrc}"
)
```

- [ ] **Step 2: 在SSRC Recovery后添加5秒等待和重试检查**

在 `handle_invite_response` 中SSRC Recovery成功后，添加5秒等待检查流是否出现：

```python
# 在 SSRC Recovery 成功后添加:
if _recovered:
    # 等待5秒检查流是否出现
    for _retry in range(10):
        await asyncio.sleep(0.5)
        try:
            _check = await get_media_list(
                host=str(db_node.host if db_node else settings.MEDIA_SERVER_HOST),
                http_port=int((db_node.http_port if db_node else None) or settings.MEDIA_SERVER_HTTP_PORT),
                secret=str(secret),
                app=app_name,
                stream=stream_id,
            )
            if _check and isinstance(_check, list) and len(_check) > 0:
                logger.info(f"[SSRC Recovery] Stream appeared after recovery: {app_name}/{stream_id}")
                break
        except Exception:
            pass
    else:
        logger.warning(f"[SSRC Recovery] Stream still not found after 5s wait for {app_name}/{stream_id}")
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/sip/response_handler.py
git commit -m "fix: add post-SSRC-recovery stream check and diagnostic logging"
```

---

### Task 6: 添加INVITE SDP内容调试日志

**问题:** 无法看到PyGBSentry发出的INVITE SDP完整内容，无法验证`c=IN IP4`行

**Files:**
- Modify: `backend/app/sip/invite.py`

- [ ] **Step 1: 在INVITE发送前记录完整SDP内容**

在 `_send_invite_common_inner` 中 `build_sdp` 调用后，添加SDP内容日志：

```python
# 在 sdp = await build_sdp(int(media_port or 0)) 之后添加:
logger.info(
    f"[INVITE SDP] channel={channel_id} sdp_ip={sdp_ip} media_port={media_port} "
    f"ssrc={ssrc} app={app_name} stream_id={stream_id}\n{sdp}"
)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/sip/invite.py
git commit -m "feat: add INVITE SDP content debug logging"
```

---

### Task 7: 添加ZLM配置中RTP proxy extern_ip

**问题:** ZLM的`rtp_proxy`段没有配置`extern_ip`，在某些ZLM版本中可能导致SDP中的IP不正确

**Files:**
- Modify: `backend/app/services/media_manager.py`

- [ ] **Step 1: 在_generate_config中添加rtp_proxy extern_ip配置**

在 `_generate_config` 函数的 `rtp_proxy` 段配置中，添加 `extern_ip`：

```python
# 在 config.set("rtp_proxy", "port_range", str(port_range)) 之后添加:
# BUG-FIX: 设置 rtp_proxy extern_ip，确保ZLM在SDP中使用公网IP
_rtp_extern_ip = (getattr(settings, "STREAM_PUBLIC_HOST", "") or "").strip()
if _rtp_extern_ip:
    try:
        import socket
        _resolved = socket.gethostbyname(_rtp_extern_ip)
        config.set("rtp_proxy", "extern_ip", _resolved)
        logger.info(f"[ZLM Config] rtp_proxy.extern_ip = {_resolved} (resolved from {_rtp_extern_ip})")
    except Exception as e:
        logger.warning(f"[ZLM Config] Failed to resolve STREAM_PUBLIC_HOST '{_rtp_extern_ip}': {e}")
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/media_manager.py
git commit -m "fix: add rtp_proxy extern_ip to ZLM config for NAT scenarios"
```

---

## 部署后验证清单

修复部署后，按以下步骤验证：

1. **检查SIP审计日志** — 播放视频后，检查 `logs/sip_audit/sip_YYYY-MM-DD.log` 中是否有 `[outbound]` 的INVITE记录，确认SDP中 `c=IN IP4` 行是公网IP（106.119.160.150）

2. **检查RTP端口诊断** — 访问 `GET /api/v1/network/rtp-port-check`，确认：
   - ZLM API可达
   - UDP 30000端口被ZLM占用
   - RTP服务器状态正常

3. **检查Probe日志** — 播放视频后，检查app.log中是否有 `[Probe] Stream NOT found! ZLM actual streams:` 日志，确认ZLM实际注册的流名

4. **检查RTP超时** — 播放视频后，检查app.log中是否有 `[RTP Timeout] Grace period active` 日志，确认超时保护生效

5. **检查防火墙** — 如果RTP端口诊断显示端口正常但视频仍无法播放，检查服务器防火墙是否开放UDP 30000-39000端口：
   ```bash
   # Linux
   sudo iptables -L -n | grep 30000
   sudo ufw status
   # 或检查云服务器安全组规则
   ```

6. **检查NAT端口转发** — 如果服务器在NAT后面，确认路由器已将UDP 30000-39000转发到服务器内网IP
