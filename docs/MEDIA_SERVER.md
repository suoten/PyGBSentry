# 开源版流媒体指南（ZLMediaKit）

[中文](#) | [English](#english-version)

> 本文档专门解决流媒体相关问题：端口规划、RTP 收发、Hook 回调、NAT 穿越、对外播放地址生成等。  
> 如果你尚未完成系统部署，请先阅读 [INSTALL_DEPLOY.md](./INSTALL_DEPLOY.md)。

---

## 1. 角色分工

| 组件 | 职责 |
|------|------|
| PyGBSentry 后端 | 业务编排、鉴权、播放地址生成、SIP 信令控制 |
| ZLMediaKit | 媒体收流、协议转换、流分发、Hook 事件回调 |

**简单理解**：后端负责"控"，ZLM 负责"搬"。

---

## 2. 部署模式

### 2.1 模式 A：同机部署（推荐入门）

- 后端与 ZLM 运行在同一台物理机或容器内。
- 网络路径最短，配置复杂度最低。
- 适合中小型项目、测试环境或单机 demonstration。

### 2.2 模式 B：独立部署（推荐生产扩展）

- ZLM 作为独立节点部署（可单节点，也可多节点集群）。
- 适合高并发、跨网段或专门划分流媒体网络的场景。

---

## 3. 关键配置项

以下环境变量（或配置文件项）直接决定流媒体链路是否可用，请务必逐项核对。

| 配置项 | 说明 | 示例 |
|--------|------|------|
| `MEDIA_SERVER_HOST` | ZLM 监听地址（内网 IP 或 0.0.0.0） | `192.168.1.10` |
| `MEDIA_SERVER_HTTP_PORT` | ZLM HTTP 播放端口 | `8083` |
| `MEDIA_SERVER_RTSP_PORT` | RTSP 端口 | `554` |
| `MEDIA_SERVER_RTMP_PORT` | RTMP 端口 | `1935` |
| `MEDIA_SERVER_SECRET` | ZLM API 鉴权密钥 | `your_secret_key` |
| `MEDIA_SERVER_RTP_PROXY_PORT_RANGE` | RTP 收流端口范围 | `30000-39000` |
| `MEDIA_SERVER_RTP_STREAM_MODE` | 国标流传输模式：`UDP` / `TCP_PASSIVE` / `TCP_ACTIVE` | `TCP_PASSIVE` |
| `STREAM_PUBLIC_HOST` | 对外播放地址（公网 IP 或域名） | `203.0.113.10` |
| `STREAM_PUBLIC_HTTP_PORT` | 对外 HTTP 播放端口 | `8083` |
| `MEDIA_SERVER_HOOK_BASE_URL` | Hook 回调基地址（ZLM 主动访问后端） | `http://192.168.1.10:8000` |

> **注意**：`MEDIA_SERVER_HOOK_BASE_URL` 必须是 ZLM 能直接访问到后端的地址，而不是浏览器侧的公网地址。

---

## 4. 端口与网络检查清单

上线前请至少完成以下 5 项确认：

| 序号 | 检查项 | 验证方法 |
|------|--------|----------|
| 1 | ZLM 各播放协议端口可达 | `telnet <host> <port>` |
| 2 | RTP 端口段与防火墙规则一致 | 核对 `MEDIA_SERVER_RTP_PROXY_PORT_RANGE` |
| 3 | Hook 回调可从 ZLM 侧访问后端 | `curl <MEDIA_SERVER_HOOK_BASE_URL>/api/v1/media/hook` |
| 4 | 对外地址与真实访问路径一致 | 浏览器直接测试播放地址 |
| 5 | NAT 场景使用 `TCP_PASSIVE` | 检查 `MEDIA_SERVER_RTP_STREAM_MODE` |

---

## 5. NAT 与公网播放建议

| 场景 | 建议 |
|------|------|
| 设备位于复杂网络（多层 NAT、防火墙） | 优先使用 `TCP_PASSIVE` 模式，降低 UDP 打孔失败概率 |
| 内外网地址分离 | 内网地址通过 `MEDIA_SERVER_HOST` 配置；外网播放地址通过 `STREAM_PUBLIC_*` 配置，切勿混淆 |
| 网关 / 反向代理 | 建议显式配置 `MEDIA_SERVER_HOOK_BASE_URL`，确保 ZLM 回调能正确到达后端 |

---

## 6. 常见故障与排查顺序

### 6.1 现象：页面能打开，但视频黑屏

**排查顺序**：

1. 确认 ZLM 播放端口（8083/554/1935）已放通。
2. 确认 RTP 端口段（默认 30000-39000）已放通。
3. 确认 Hook 回调成功（查看 ZLM 日志与后端日志是否有 `on_play`、`on_publish` 等记录）。

### 6.2 现象：内网可播放，公网不可播放

**排查顺序**：

1. 确认 `STREAM_PUBLIC_HOST` 是否为公网可达地址（或正确映射的域名）。
2. 确认网关端口映射（NAT）是否正确。
3. 确认防火墙未遗漏 RTP 端口段。

### 6.3 现象：偶发断流或回放失败

**排查顺序**：

1. 确认 ZLM 与后端服务器时间同步（建议启用 NTP）。
2. 检查网络抖动、丢包及端口冲突。
3. 确认流模式（UDP / TCP）与现场网络环境匹配。

---

## 7. 流媒体端口规划参考

| 端口 | 协议 | 用途 | 必开 |
|------|------|------|------|
| 554 | RTSP | 设备推流 / 拉流 | 是 |
| 1935 | RTMP | RTMP 推流与分发 | 是 |
| 8083 | HTTP | Web 播放（FLV / HLS） | 是 |
| 8443 | HTTPS | HTTPS 加密播放 | 可选 |
| 30000-39000 | UDP / TCP | RTP 媒体收流 | **必须按实际范围开放** |
| 9000 | HTTP | ZLM 管理 / API 接口 | 建议仅内网开放 |

---

## 8. 生产环境建议

1. **先跑通单路**：在同一套环境中先完成"单路实时预览 + 历史回放 + 报警联动拉流"的端到端验证。
2. **再逐步扩展**：确认稳定后，再扩展到多设备并发。
3. **每次改动后复测**：
   - 实时预览
   - 历史回放
   - 轨迹 / 报警联动中的视频拉流

---

## 9. 最小验收标准

满足以下四项，即可判定流媒体链路可用：

| 序号 | 验收项 | 验证方法 |
|------|--------|----------|
| 1 | 实时预览可播放 | 播放任意一路设备视频流 |
| 2 | 历史回放可播放 | 播放一段历史录像 |
| 3 | 报警联动触发后可拉流 | 触发报警后，验证视频是否正常弹出 |
| 4 | 跨网访问时播放地址与端口均可达 | 从外部网络直接测试播放地址 |

---

## 10. 相关文档

| 文档 | 说明 |
|------|------|
| [INSTALL_DEPLOY.md](./INSTALL_DEPLOY.md) | 完整部署手册 |
| [PRODUCT_OSS.md](./PRODUCT_OSS.md) | 产品能力说明 |

---

# English Version

# Streaming Media Guide for Open-Source Edition (ZLMediaKit)

> This document focuses on streaming media topics: port planning, RTP receiving/sending, Hook callbacks, NAT traversal, and public playback address generation.  
> If you have not completed system deployment yet, please read [INSTALL_DEPLOY.md](./INSTALL_DEPLOY.md) first.

---

## 1. Role Division

| Component | Responsibility |
|-----------|----------------|
| PyGBSentry Backend | Business orchestration, authentication, playback address generation, SIP signaling control |
| ZLMediaKit | Media stream receiving, protocol conversion, stream distribution, Hook event callbacks |

**Simple analogy**: the backend is the "controller", ZLM is the "mover".

---

## 2. Deployment Modes

### 2.1 Mode A: Co-Located Deployment (Recommended for Beginners)

- The backend and ZLM run on the same physical machine or inside the same container.
- Shortest network path and lowest configuration complexity.
- Suitable for small-to-medium projects, test environments, or single-machine demonstrations.

### 2.2 Mode B: Independent Deployment (Recommended for Production Scaling)

- ZLM is deployed as an independent node (single node or multi-node cluster).
- Suitable for high concurrency, cross-network-segment, or dedicated streaming network scenarios.

---

## 3. Key Configuration Items

The following environment variables (or configuration file entries) directly determine whether the streaming link works. Please verify each item carefully.

| Configuration Item | Description | Example |
|--------------------|-------------|---------|
| `MEDIA_SERVER_HOST` | ZLM listening address (internal IP or 0.0.0.0) | `192.168.1.10` |
| `MEDIA_SERVER_HTTP_PORT` | ZLM HTTP playback port | `8083` |
| `MEDIA_SERVER_RTSP_PORT` | RTSP port | `554` |
| `MEDIA_SERVER_RTMP_PORT` | RTMP port | `1935` |
| `MEDIA_SERVER_SECRET` | ZLM API authentication key | `your_secret_key` |
| `MEDIA_SERVER_RTP_PROXY_PORT_RANGE` | RTP receiving port range | `30000-39000` |
| `MEDIA_SERVER_RTP_STREAM_MODE` | GB/T stream mode: `UDP` / `TCP_PASSIVE` / `TCP_ACTIVE` | `TCP_PASSIVE` |
| `STREAM_PUBLIC_HOST` | Public playback address (public IP or domain) | `203.0.113.10` |
| `STREAM_PUBLIC_HTTP_PORT` | Public HTTP playback port | `8083` |
| `MEDIA_SERVER_HOOK_BASE_URL` | Hook callback base URL (ZLM actively calls the backend) | `http://192.168.1.10:8000` |

> **Note**: `MEDIA_SERVER_HOOK_BASE_URL` must be an address that ZLM can reach directly; it is **not** the browser-side public address.

---

## 4. Port & Network Checklist

Before going live, please complete at least the following 5 checks:

| No. | Check Item | Verification Method |
|-----|------------|---------------------|
| 1 | ZLM playback protocol ports are reachable | `telnet <host> <port>` |
| 2 | RTP port range matches firewall rules | Verify `MEDIA_SERVER_RTP_PROXY_PORT_RANGE` |
| 3 | Hook callback is reachable from ZLM side | `curl <MEDIA_SERVER_HOOK_BASE_URL>/api/v1/media/hook` |
| 4 | Public address matches the real access path | Test the playback URL directly in a browser |
| 5 | NAT scenarios use `TCP_PASSIVE` | Check `MEDIA_SERVER_RTP_STREAM_MODE` |

---

## 5. NAT & Public Playback Recommendations

| Scenario | Recommendation |
|----------|----------------|
| Device behind complex network (multi-layer NAT, firewall) | Prefer `TCP_PASSIVE` mode to reduce UDP hole-punching failures |
| Internal / external address separation | Use `MEDIA_SERVER_HOST` for internal addresses; use `STREAM_PUBLIC_*` for public playback addresses. Do not mix them up. |
| Gateway / reverse proxy | Explicitly configure `MEDIA_SERVER_HOOK_BASE_URL` to ensure ZLM callbacks reach the backend correctly |

---

## 6. Common Issues & Troubleshooting Order

### 6.1 Symptom: Page loads, but video is black

**Troubleshooting order**:

1. Confirm ZLM playback ports (8083/554/1935) are open.
2. Confirm the RTP port range (default 30000-39000) is open.
3. Confirm Hook callbacks succeed (check ZLM logs and backend logs for `on_play`, `on_publish`, etc.).

### 6.2 Symptom: Works on LAN, but not from the public network

**Troubleshooting order**:

1. Confirm `STREAM_PUBLIC_HOST` is a public-network-reachable address (or correctly mapped domain).
2. Confirm gateway port mapping (NAT) is correct.
3. Confirm the firewall does not block the RTP port range.

### 6.3 Symptom: Occasional stream interruption or playback failure

**Troubleshooting order**:

1. Confirm time synchronization between ZLM and the backend (NTP is recommended).
2. Check network jitter, packet loss, and port conflicts.
3. Confirm the stream mode (UDP / TCP) matches the on-site network environment.

---

## 7. Streaming Media Port Planning Reference

| Port | Protocol | Purpose | Required |
|------|----------|---------|----------|
| 554 | RTSP | Device streaming / pulling | Yes |
| 1935 | RTMP | RTMP streaming and distribution | Yes |
| 8083 | HTTP | Web playback (FLV / HLS) | Yes |
| 8443 | HTTPS | HTTPS encrypted playback | Optional |
| 30000-39000 | UDP / TCP | RTP media receiving | **Must be opened according to the actual range** |
| 9000 | HTTP | ZLM management / API interface | Recommended internal access only |

---

## 8. Production Environment Recommendations

1. **Single-stream verification first**: In the same environment, complete end-to-end verification of "single-channel live preview + historical playback + alarm-linked stream pulling".
2. **Scale gradually**: After confirming stability, expand to multi-device concurrency.
3. **Re-test after every change**:
   - Live preview
   - Historical playback
   - Video stream pulling in track / alarm linkage

---

## 9. Minimum Acceptance Criteria

If the following four items are satisfied, the streaming link can be considered usable:

| No. | Acceptance Item | Verification Method |
|-----|-----------------|---------------------|
| 1 | Live preview is playable | Play any device video stream |
| 2 | Historical playback is playable | Play a segment of historical recording |
| 3 | Stream can be pulled after alarm linkage triggers | Trigger an alarm and verify the video pops up normally |
| 4 | Playback address and ports are reachable when accessing across networks | Test the playback URL directly from an external network |

---

## 10. Related Documents

| Document | Description |
|----------|-------------|
| [INSTALL_DEPLOY.md](./INSTALL_DEPLOY.md) | Complete deployment manual |
| [PRODUCT_OSS.md](./PRODUCT_OSS.md) | Product capability description |
