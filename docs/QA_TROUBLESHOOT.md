# PyGBSentry 常见问题排查手册

[中文](#) | [English](#english-version)

> 本手册系统整理了 PyGBSentry 使用过程中最常见的几类问题，提供结构化的排查思路与解决路径。  
> 建议按目录顺序阅读，按问题类型对号入座。  
> **更新时间：** 2026-04-13

---

## 目录

- [快速索引](#快速索引)
- [1. 排查前置准备](#1-排查前置准备)
  - [1.1 获取关键信息](#11-获取关键信息)
  - [1.2 查看日志](#12-查看日志)
- [2. 设备无法注册](#2-设备无法注册)
  - [2.1 典型错误表现](#21-典型错误表现)
  - [2.2 排查路径图](#22-排查路径图)
  - [2.3 常见错误码解析](#23-常见错误码解析)
  - [2.4 实战案例](#24-实战案例)
- [3. 视频播放失败](#3-视频播放失败)
  - [3.1 问题分类](#31-问题分类)
  - [3.2 排查路径图](#32-排查路径图)
  - [3.3 快速诊断命令](#33-快速诊断命令)
  - [3.4 常见问题详解](#34-常见问题详解)
- [4. 视频卡顿与延迟](#4-视频卡顿与延迟)
  - [4.1 延迟来源分析](#41-延迟来源分析)
  - [4.2 优化建议](#42-优化建议)
  - [4.3 查看 ZLM 流媒体状态](#43-查看-zlm-流媒体状态)
- [5. 报警推送异常](#5-报警推送异常)
  - [5.1 报警未收到](#51-报警未收到)
  - [5.2 报警录像联动未触发](#52-报警录像联动未触发)
- [6. 级联赛道问题](#6-级联赛道问题)
  - [6.1 上级平台看不到通道](#61-上级平台看不到通道)
  - [6.2 级联播放失败](#62-级联播放失败)
- [7. 前端访问异常](#7-前端访问异常)
  - [7.1 页面空白或加载失败](#71-页面空白或加载失败)
  - [7.2 登录页样式异常](#72-登录页样式异常)
- [8. 环境检测工具](#8-环境检测工具)
  - [8.1 一键诊断脚本](#81-一键诊断脚本)
- [9. 获取技术支持](#9-获取技术支持)

---

## 快速索引

| 问题类型 | 典型表现 | 参考章节 |
| :------- | :------- | :------- |
| 设备无法注册 | 设备一直离线，平台无响应 | [第 2 节](#2-设备无法注册) |
| 视频无法播放 | 点击播放后黑屏或报错 | [第 3 节](#3-视频播放失败) |
| 播放卡顿 / 延迟高 | 视频加载慢，延时大 | [第 4 节](#4-视频卡顿与延迟) |
| 报警未收到 | Web 端无报警推送 | [第 5 节](#5-报警推送异常) |
| 级联平台异常 | 上级平台看不到通道 | [第 6 节](#6-级联赛道问题) |
| 页面打不开 | 前端无法加载 | [第 7 节](#7-前端访问异常) |

---

## 1. 排查前置准备

### 1.1 获取关键信息

遇到问题时，请先收集以下信息：

1. 操作系统及版本（Windows Server / Ubuntu / CentOS）
2. Python 版本：`python --version`
3. PyGBSentry 版本：`git log --oneline -1` 或查看版本文件
4. 数据库类型（PostgreSQL / MySQL / SQLite）
5. 是否使用 Docker 部署
6. 出现问题的时间点与操作步骤
7. 相关错误日志（见 [1.2 查看日志](#12-查看日志)）

### 1.2 查看日志

日志是排查问题的第一手资料，务必优先查看。

#### 本地开发环境

```bash
# 实时查看日志（后端）
cd backend
python -m app.main

# 或使用 uvicorn
uvicorn app.main:app --reload --log-level debug
```

#### Docker 部署

```bash
# 查看后端容器日志
docker logs -f pygbsentry-backend

# 查看所有容器日志
docker compose logs -f

# 查看最近 200 行
docker logs --tail 200 pygbsentry-backend
```

#### 日志级别说明

| 级别 | 含义 | 使用场景 |
| :--- | :--- | :--- |
| `ERROR` | 严重错误，请求处理失败 | 必看，找错误根因 |
| `WARNING` | 警告，不影响主流程 | 参考性信息 |
| `INFO` | 常规操作记录 | 确认流程是否执行 |
| `DEBUG` | 详细调试信息 | 深入排查时启用 |

#### 开启 DEBUG 模式

```bash
# 修改 backend/.env
LOG_LEVEL=DEBUG

# 重启服务
docker compose restart backend

# 或本地（自动读取 .env）
python -m app.main
```

---

## 2. 设备无法注册

### 2.1 典型错误表现

- 设备状态显示「离线」
- 日志中出现 `401 Unauthorized`、`403 Forbidden`、`404 Not Found`
- 设备侧提示注册失败

### 2.2 排查路径图

```text
设备无法注册
├── 网络不通？
│   └── telnet 平台IP 5060 → 失败 → 检查防火墙/安全组/网络
├── 参数不匹配？
│   ├── SIP 地址/端口错误 → 核对平台侧配置
│   ├── SIP ID（横号）错误 → 确认20位编码
│   └── 认证密码错误 → 与平台侧密码一致
├── 设备横号冲突？
│   └── 同一横号被其他设备占用 → 修改设备横号
├── 心跳超时？
│   └── NAT 环境下心跳周期过长 → 缩短至30秒
└── 平台侧问题？
    ├── SIP 服务未启动 → 重启后端
    └── 数据库连接失败 → 检查数据库状态
```

### 2.3 常见错误码解析

| HTTP/SIP 错误码 | 含义 | 常见原因 |
| :-------------- | :--- | :--- |
| `401 Unauthorized` | 认证失败 | 密码错误 |
| `403 Forbidden` | 禁止访问 | IP 未授权、设备被禁用 |
| `404 Not Found` | 设备不存在 | 设备横号未在平台登记 |
| `408 Request Timeout` | 请求超时 | 设备无法到达平台、网络中断 |
| `480 Temporarily Unavailable` | 临时不可用 | 设备横号格式错误 |

### 2.4 实战案例

#### 案例一：海康摄像头注册返回 401

**现象：** 海康摄像头始终无法注册，日志显示 `401 Unauthorized`。

**排查步骤：**

1. 确认平台侧设备横号正确（20 位）。
2. 确认设备侧密码与平台一致。
3. 检查设备固件版本，部分老版本存在 Digest 认证兼容性问题。
4. 尝试将设备密码改为纯数字，重试注册。

**解决：** 将设备认证密码改为纯数字 `12345678`，重新注册成功。

#### 案例二：NVR 下挂摄像头通道全部丢失

**现象：** NVR 在线，但下挂的摄像头通道全部消失。

**排查步骤：**

1. 确认 NVR 已开启「通道自动上报」。
2. 在平台侧点击设备「刷新」按钮，等待通道同步。
3. 检查 NVR 侧网络设置，确认通道未被禁用。

---

## 3. 视频播放失败

### 3.1 问题分类

视频播放失败可分为三类：

1. **点播信令失败** —— 设备未响应平台发起的播放请求。
2. **收流超时** —— 设备已响应，但视频流未送达。
3. **流解析失败** —— 视频流已到达，但播放器无法解码。

### 3.2 排查路径图

```text
视频播放失败
├── 点击播放后立即报错（< 1 秒）
│   ├── 400 错误 → 设备认为请求格式错误 → 抓包分析
│   ├── 500 错误 → 设备内部故障 → 联系厂商
│   └── 408 超时 → 设备未响应 → 检查网络/心跳
├── 点击播放后等待（> 5 秒）报错
│   ├── 点播超时 → 设备未回复 INVITE
│   │   ├── 检查防火墙是否放行了 UDP 10000-40000
│   │   ├── 检查 NAT 环境下收流地址配置
│   │   └── 尝试 TCP 模式点播
│   └── 收流超时 → 流未到达 ZLM
│       ├── 检查 ZLM 的 hook 配置是否可达
│       ├── 查看 ZLM 日志是否有流注册记录
│       └── 抓包查看设备是否在发流
└── 播放窗口黑屏无报错
    ├── 音频编码不支持 → 设备改为 H.264 + AAC
    ├── 视频编码不支持 → 确认 H.264 / H.265
    └── SSRC 校验冲突 → 关闭 SSRC 校验
```

### 3.3 快速诊断命令

#### 诊断点播信令是否正常

```bash
# 查看平台日志中的点播请求
grep -E "INVITE|200 OK|BYE" logs/app.log | tail -50

# 查看是否有设备响应超时
grep "timeout" logs/app.log
```

#### 诊断流媒体是否收到流

```bash
# 查看 ZLM 日志（Docker 环境）
docker exec pygbsentry-media cat /opt/zlmediakit/log/log.txt | grep "rtp"

# 或查看 ZLM 的流列表 API
curl "http://localhost:9092/api/getMediaList"
```

### 3.4 常见问题详解

#### 问题 1：播放器加载成功但黑屏

**原因：** 视频流未到达播放器。

**排查：**

1. 打开浏览器开发者工具（F12），切换到 **Network** 标签。
2. 过滤 `ws://` 或 `flv` / `hls` 请求。
3. 查看 WebSocket 连接状态是否为 `Open`。
4. 查看是否有流地址返回。

**解决：**

- 如果没有流地址返回 → 设备未发流，检查收流配置。
- 如果有地址但播放失败 → 播放器无法解码，尝试切换流协议（FLV / WebRTC）。

#### 问题 2：设备发流但 ZLM 未收到

**原因：** 设备的发流地址配置错误。

**排查：**

1. 确认平台给设备发送的 SDP 中 `c=` 行的 IP 地址。
2. 如果是公网部署，IP 必须是公网可路由地址。
3. 如果在内网，IP 必须是设备能到达的地址。

**解决：**

- 在平台侧「编辑设备」中配置「收流 IP」为服务器实际监听地址。
- 关闭 NAT 穿透时使用 `local_ip` 配置。

#### 问题 3：H.265 视频无法播放

**原因：** 浏览器默认不支持 H.265（HEVC）。

**解决：**

- **方案一：** 联系设备厂商，将编码改为 H.264。
- **方案二：** 使用支持 H.265 的播放器（如 h265web.js 或 Jessibuca）。
- **方案三：** ZLM 开启 H.265 → H.264 转码（性能开销较大，不推荐）。

---

## 4. 视频卡顿与延迟

### 4.1 延迟来源分析

视频延迟由以下几部分组成：

```text
总延迟 = 信令延迟 + 流传输延迟 + 解码延迟 + 缓冲延迟 + 网络往返延迟

典型值：
- 局域网：100 ms ~ 500 ms
- 跨地域：500 ms ~ 2000 ms
- 公网弱网：2 s ~ 10 s
```

### 4.2 优化建议

| 优化项 | 操作方法 | 预期效果 |
| :----- | :------- | :------- |
| 降低缓冲延迟 | 播放器设置低缓冲模式 | 延迟减少 0.5 s ~ 2 s |
| 关闭音频 | 部分设备音频干扰解码 | 改善卡顿 |
| 使用 TCP 模式 | 在设备侧开启 TCP 发流 | 抗丢包，适合公网 |
| 升级带宽 | 带宽不足时必须升级 | 根本解决 |
| 降低码率 | 设备降低码率 / 分辨率 | 改善卡顿 |

### 4.3 查看 ZLM 流媒体状态

```bash
# 获取 ZLM 流列表（验证是否有流在传输）
curl -s "http://localhost:9092/api/getMediaList" | python -m json.tool

# 查看 ZLM 当前连接数
curl -s "http://localhost:9092/api/getNetSelection" | python -m json.tool
```

---

## 5. 报警推送异常

### 5.1 报警未收到

**排查步骤：**

1. **确认设备是否支持报警功能**
   - 并非所有摄像头都支持报警输入。
   - 部分设备需要额外配置报警输入端口。

2. **确认报警配置**
   - 平台侧：是否开启了报警接收。
   - 设备侧：是否配置了报警联动。

3. **查看 WebSocket 连接**
   - 浏览器 F12 → Network → 过滤 `ws://`。
   - 查看 WebSocket 连接是否建立。

4. **查看日志**

   ```bash
   grep -E "ALARM|报警" logs/app.log | tail -50
   ```

### 5.2 报警录像联动未触发

**排查：**

1. 确认录像计划已配置。
2. 确认报警规则中的联动动作包含「录像」。
3. 查看触发时间是否在计划范围内。

---

## 6. 级联赛道问题

### 6.1 上级平台看不到通道

**排查步骤：**

1. 确认本平台作为下级平台已正确配置。
2. 确认上级平台的 IP、端口、横号、密码正确。
3. 查看「通道推送」配置，确认要推送的通道已勾选。
4. 确认上级平台是否开启了「目录订阅」。

### 6.2 级联播放失败

与普通点播失败排查相同，额外检查：

- 上级平台是否支持 TCP 发流。
- 级联的心跳是否正常。

---

## 7. 前端访问异常

### 7.1 页面空白或加载失败

**排查：**

```bash
# 1. 确认前端服务运行正常
curl -I http://localhost:3000

# 2. 确认后端 API 可访问
curl http://localhost:8000/api/v1/ops/health

# 3. 查看浏览器控制台错误（F12 → Console）
```

### 7.2 登录页样式异常

**原因：** 静态资源未正确加载（Nginx 配置问题）。

**解决：**

检查 Nginx 配置：

```nginx
server {
    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
    }
}
```

---

## 8. 环境检测工具

### 8.1 一键诊断脚本

在服务器上执行以下命令，快速诊断环境问题：

```bash
# 网络连通性检测
echo "=== 端口检测 ==="
for port in 5060 8000 3000 1935 554 10000; do
    nc -zvw 2 localhost $port && echo "  $port: OK" || echo "  $port: FAIL"
done

# 数据库连接检测
echo "=== 数据库检测 ==="
python -c "import asyncio; from app.db.session import get_db; asyncio.run(get_db())" \
    && echo "  DB: OK" || echo "  DB: FAIL"

# 流媒体检测
echo "=== ZLM 检测 ==="
curl -s http://localhost:9092/api/getServerConfig \
    && echo "  ZLM: OK" || echo "  ZLM: FAIL"
```

---

## 9. 获取技术支持

如果以上方法均无法解决问题，请按以下格式整理问题：

```text
【问题描述】
[简洁描述遇到的问题]

【环境信息】
- 操作系统：
- Python 版本：
- 部署方式（Docker / 源码）：
- 数据库：

【复现步骤】
1.
2.
3.

【错误日志】
[粘贴相关日志，重要部分高亮]

【已尝试的解决措施】
1.
2.
```

> **相关文档：**
> - [视频点播与播放问题排查](./QA_PLAY_ERROR.md)
> - [国标设备配置指南](./GUIDE_DEVICE_CONFIG.md)
> - [流媒体配置指南](./MEDIA_SERVER.md)

---

# English Version

# PyGBSentry Troubleshooting Guide

> This guide systematically organizes the most common issues encountered when using PyGBSentry, providing structured diagnostic approaches and resolution paths.  
> It is recommended to read in order and match your issue to the relevant section.  
> **Last Updated:** 2026-04-13

---

## Table of Contents

- [Quick Index](#quick-index)
- [1. Preliminary Preparation](#1-preliminary-preparation)
  - [1.1 Gather Key Information](#11-gather-key-information)
  - [1.2 Check Logs](#12-check-logs)
- [2. Device Registration Failure](#2-device-registration-failure)
  - [2.1 Typical Symptoms](#21-typical-symptoms)
  - [2.2 Diagnostic Flowchart](#22-diagnostic-flowchart)
  - [2.3 Common Error Codes](#23-common-error-codes)
  - [2.4 Real-World Cases](#24-real-world-cases)
- [3. Video Playback Failure](#3-video-playback-failure)
  - [3.1 Problem Categories](#31-problem-categories)
  - [3.2 Diagnostic Flowchart](#32-diagnostic-flowchart)
  - [3.3 Quick Diagnostic Commands](#33-quick-diagnostic-commands)
  - [3.4 Common Issues in Detail](#34-common-issues-in-detail)
- [4. Video Stuttering and Latency](#4-video-stuttering-and-latency)
  - [4.1 Latency Source Analysis](#41-latency-source-analysis)
  - [4.2 Optimization Suggestions](#42-optimization-suggestions)
  - [4.3 Check ZLM Media Server Status](#43-check-zlm-media-server-status)
- [5. Alarm Push Abnormalities](#5-alarm-push-abnormalities)
  - [5.1 Alarm Not Received](#51-alarm-not-received)
  - [5.2 Alarm-Triggered Recording Not Working](#52-alarm-triggered-recording-not-working)
- [6. Cascade Channel Issues](#6-cascade-channel-issues)
  - [6.1 Superior Platform Cannot See Channels](#61-superior-platform-cannot-see-channels)
  - [6.2 Cascade Playback Failure](#62-cascade-playback-failure)
- [7. Frontend Access Abnormalities](#7-frontend-access-abnormalities)
  - [7.1 Blank or Failed Page Load](#71-blank-or-failed-page-load)
  - [7.2 Login Page Style Abnormalities](#72-login-page-style-abnormalities)
- [8. Environment Detection Tools](#8-environment-detection-tools)
  - [8.1 One-Click Diagnostic Script](#81-one-click-diagnostic-script)
- [9. Getting Technical Support](#9-getting-technical-support)

---

## Quick Index

| Issue Type | Typical Symptom | Reference Section |
| :--------- | :-------------- | :---------------- |
| Device registration failure | Device always offline, no platform response | [Section 2](#2-device-registration-failure) |
| Video cannot play | Black screen or error after clicking play | [Section 3](#3-video-playback-failure) |
| Playback stuttering / high latency | Slow video loading, large delay | [Section 4](#4-video-stuttering-and-latency) |
| Alarm not received | No alarm push on Web端 | [Section 5](#5-alarm-push-abnormalities) |
| Cascade platform abnormal | Superior platform cannot see channels | [Section 6](#6-cascade-channel-issues) |
| Page cannot open | Frontend fails to load | [Section 7](#7-frontend-access-abnormalities) |

---

## 1. Preliminary Preparation

### 1.1 Gather Key Information

When encountering an issue, please collect the following information first:

1. Operating system and version (Windows Server / Ubuntu / CentOS)
2. Python version: `python --version`
3. PyGBSentry version: `git log --oneline -1` or check the version file
4. Database type (PostgreSQL / MySQL / SQLite)
5. Whether deployed using Docker
6. Time of issue and operation steps
7. Relevant error logs (see [1.2 Check Logs](#12-check-logs))

### 1.2 Check Logs

Logs are the primary source for troubleshooting; always check them first.

#### Local Development Environment

```bash
# View logs in real time (backend)
cd backend
python -m app.main

# Or use uvicorn
uvicorn app.main:app --reload --log-level debug
```

#### Docker Deployment

```bash
# View backend container logs
docker logs -f pygbsentry-backend

# View all container logs
docker compose logs -f

# View the last 200 lines
docker logs --tail 200 pygbsentry-backend
```

#### Log Level Reference

| Level | Meaning | Usage Scenario |
| :---- | :------ | :------------- |
| `ERROR` | Severe error, request processing failed | Must-check, find root cause |
| `WARNING` | Warning, does not affect main flow | Reference information |
| `INFO` | Routine operation records | Confirm whether the process executed |
| `DEBUG` | Detailed debug information | Enable for in-depth troubleshooting |

#### Enable DEBUG Mode

```bash
# Modify backend/.env
LOG_LEVEL=DEBUG

# Restart the service
docker compose restart backend

# Or for local (automatically reads .env)
python -m app.main
```

---

## 2. Device Registration Failure

### 2.1 Typical Symptoms

- Device status shows "Offline"
- Logs show `401 Unauthorized`, `403 Forbidden`, `404 Not Found`
- Device side reports registration failure

### 2.2 Diagnostic Flowchart

```text
Device Registration Failure
├── Network unreachable?
│   └── telnet <platform_ip> 5060 → fails → check firewall / security group / network
├── Parameters mismatch?
│   ├── SIP address / port incorrect → verify platform-side config
│   ├── SIP ID (device ID) incorrect → confirm 20-digit encoding
│   └── Authentication password incorrect → match platform-side password
├── Device ID conflict?
│   └── Same ID occupied by another device → change device ID
├── Heartbeat timeout?
│   └── NAT environment with overly long heartbeat interval → shorten to 30s
└── Platform-side issue?
    ├── SIP service not started → restart backend
    └── Database connection failed → check database status
```

### 2.3 Common Error Codes

| HTTP/SIP Error Code | Meaning | Common Cause |
| :------------------ | :------ | :----------- |
| `401 Unauthorized` | Authentication failed | Wrong password |
| `403 Forbidden` | Access denied | IP not authorized, device disabled |
| `404 Not Found` | Device does not exist | Device ID not registered on platform |
| `408 Request Timeout` | Request timed out | Device cannot reach platform, network interrupted |
| `480 Temporarily Unavailable` | Temporarily unavailable | Device ID format incorrect |

### 2.4 Real-World Cases

#### Case 1: Hikvision Camera Returns 401 on Registration

**Symptom:** Hikvision camera cannot register, logs show `401 Unauthorized`.

**Diagnostic Steps:**

1. Confirm the platform-side device ID is correct (20 digits).
2. Confirm the device-side password matches the platform.
3. Check the device firmware version; some older versions have Digest authentication compatibility issues.
4. Try changing the device password to pure numeric and retry registration.

**Resolution:** Change the device authentication password to pure numeric `12345678`; registration succeeds.

#### Case 2: All Camera Channels Under NVR Disappear

**Symptom:** NVR is online, but all attached camera channels disappear.

**Diagnostic Steps:**

1. Confirm NVR has "channel auto-report" enabled.
2. On the platform side, click the device "Refresh" button and wait for channel synchronization.
3. Check NVR-side network settings to confirm channels are not disabled.

---

## 3. Video Playback Failure

### 3.1 Problem Categories

Video playback failure can be divided into three categories:

1. **VOD Signaling Failure** — Device did not respond to the platform's play request.
2. **Stream Reception Timeout** — Device responded, but the video stream was not delivered.
3. **Stream Parsing Failure** — Video stream arrived, but the player cannot decode it.

### 3.2 Diagnostic Flowchart

```text
Video Playback Failure
├── Immediate error after clicking play (< 1s)
│   ├── 400 error → device thinks request format is wrong → packet capture analysis
│   ├── 500 error → device internal fault → contact vendor
│   └── 408 timeout → device did not respond → check network / heartbeat
├── Error after waiting (> 5s)
│   ├── VOD timeout → device did not reply to INVITE
│   │   ├── check whether firewall allows UDP 10000-40000
│   │   ├── check stream-reception address config in NAT environment
│   │   └── try TCP mode VOD
│   └── Stream reception timeout → stream did not reach ZLM
│       ├── check whether ZLM hook config is reachable
│       ├── check ZLM logs for stream registration records
│       └── packet capture to see if device is sending stream
└── Black screen in player window with no error
    ├── Audio encoding not supported → change device to H.264 + AAC
    ├── Video encoding not supported → confirm H.264 / H.265
    └── SSRC validation conflict → disable SSRC validation
```

### 3.3 Quick Diagnostic Commands

#### Diagnose Whether VOD Signaling Is Normal

```bash
# Check VOD requests in platform logs
grep -E "INVITE|200 OK|BYE" logs/app.log | tail -50

# Check for device response timeouts
grep "timeout" logs/app.log
```

#### Diagnose Whether the Media Server Received the Stream

```bash
# Check ZLM logs (Docker environment)
docker exec pygbsentry-media cat /opt/zlmediakit/log/log.txt | grep "rtp"

# Or query ZLM stream list API
curl "http://localhost:9092/api/getMediaList"
```

### 3.4 Common Issues in Detail

#### Issue 1: Player Loads Successfully but Black Screen

**Cause:** Video stream did not reach the player.

**Diagnosis:**

1. Open browser developer tools (F12), switch to the **Network** tab.
2. Filter `ws://` or `flv` / `hls` requests.
3. Check whether the WebSocket connection status is `Open`.
4. Check whether a stream address is returned.

**Resolution:**

- If no stream address is returned → device did not send stream; check stream-reception config.
- If address exists but playback fails → player cannot decode; try switching stream protocol (FLV / WebRTC).

#### Issue 2: Device Sends Stream but ZLM Did Not Receive

**Cause:** The stream destination address configured on the device is wrong.

**Diagnosis:**

1. Confirm the IP address in the `c=` line of the SDP sent by the platform to the device.
2. If deployed on the public internet, the IP must be a publicly routable address.
3. If on an internal network, the IP must be reachable by the device.

**Resolution:**

- In the platform side "Edit Device", configure "Stream Reception IP" to the server's actual listening address.
- Use `local_ip` config when NAT traversal is disabled.

#### Issue 3: H.265 Video Cannot Play

**Cause:** Browsers do not support H.265 (HEVC) by default.

**Resolution:**

- **Option 1:** Contact the device vendor to change encoding to H.264.
- **Option 2:** Use an H.265-capable player (e.g., h265web.js or Jessibuca).
- **Option 3:** Enable H.265 → H.264 transcoding on ZLM (high performance cost, not recommended).

---

## 4. Video Stuttering and Latency

### 4.1 Latency Source Analysis

Video latency is composed of the following parts:

```text
Total Latency = Signaling Latency + Stream Transmission Latency + Decoding Latency + Buffering Latency + Network Round-Trip Latency

Typical Values:
- LAN: 100 ms ~ 500 ms
- Cross-region: 500 ms ~ 2000 ms
- Public network / weak network: 2 s ~ 10 s
```

### 4.2 Optimization Suggestions

| Optimization Item | Operation Method | Expected Effect |
| :---------------- | :--------------- | :-------------- |
| Reduce buffering latency | Set player to low-buffer mode | Latency reduced by 0.5 s ~ 2 s |
| Disable audio | Some device audio interferes with decoding | Improves stuttering |
| Use TCP mode | Enable TCP streaming on device side | Packet-loss resistant, suitable for public network |
| Upgrade bandwidth | Must upgrade when bandwidth is insufficient | Fundamental solution |
| Lower bitrate | Reduce bitrate / resolution on device | Improves stuttering |

### 4.3 Check ZLM Media Server Status

```bash
# Get ZLM stream list (verify whether streams are transmitting)
curl -s "http://localhost:9092/api/getMediaList" | python -m json.tool

# Check ZLM current connection count
curl -s "http://localhost:9092/api/getNetSelection" | python -m json.tool
```

---

## 5. Alarm Push Abnormalities

### 5.1 Alarm Not Received

**Diagnostic Steps:**

1. **Confirm whether the device supports alarm functionality**
   - Not all cameras support alarm input.
   - Some devices require additional alarm input port configuration.

2. **Confirm alarm configuration**
   - Platform side: whether alarm reception is enabled.
   - Device side: whether alarm linkage is configured.

3. **Check WebSocket connection**
   - Browser F12 → Network → filter `ws://`.
   - Check whether the WebSocket connection is established.

4. **Check logs**

   ```bash
   grep -E "ALARM|报警" logs/app.log | tail -50
   ```

### 5.2 Alarm-Triggered Recording Not Working

**Diagnosis:**

1. Confirm the recording schedule is configured.
2. Confirm the alarm rule's联动 action includes "Recording".
3. Check whether the trigger time falls within the scheduled range.

---

## 6. Cascade Channel Issues

### 6.1 Superior Platform Cannot See Channels

**Diagnostic Steps:**

1. Confirm this platform is correctly configured as a subordinate platform.
2. Confirm the superior platform's IP, port, device ID, and password are correct.
3. Check "Channel Push" config and confirm the channels to be pushed are checked.
4. Confirm whether the superior platform has enabled "Catalog Subscription".

### 6.2 Cascade Playback Failure

Same as ordinary VOD failure diagnosis, with additional checks:

- Whether the superior platform supports TCP streaming.
- Whether cascade heartbeats are normal.

---

## 7. Frontend Access Abnormalities

### 7.1 Blank or Failed Page Load

**Diagnosis:**

```bash
# 1. Confirm frontend service is running normally
curl -I http://localhost:3000

# 2. Confirm backend API is accessible
curl http://localhost:8000/api/v1/ops/health

# 3. Check browser console errors (F12 → Console)
```

### 7.2 Login Page Style Abnormalities

**Cause:** Static resources failed to load correctly (Nginx configuration issue).

**Resolution:**

Check Nginx configuration:

```nginx
server {
    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
    }
}
```

---

## 8. Environment Detection Tools

### 8.1 One-Click Diagnostic Script

Run the following command on the server for a quick environment diagnosis:

```bash
# Network connectivity detection
echo "=== Port Check ==="
for port in 5060 8000 3000 1935 554 10000; do
    nc -zvw 2 localhost $port && echo "  $port: OK" || echo "  $port: FAIL"
done

# Database connection detection
echo "=== Database Check ==="
python -c "import asyncio; from app.db.session import get_db; asyncio.run(get_db())" \
    && echo "  DB: OK" || echo "  DB: FAIL"

# Media server detection
echo "=== ZLM Check ==="
curl -s http://localhost:9092/api/getServerConfig \
    && echo "  ZLM: OK" || echo "  ZLM: FAIL"
```

---

## 9. Getting Technical Support

If none of the above methods resolve your issue, please organize your problem in the following format:

```text
[Problem Description]
[Brief description of the issue encountered]

[Environment Information]
- Operating System:
- Python Version:
- Deployment Method (Docker / Source):
- Database:

[Reproduction Steps]
1.
2.
3.

[Error Logs]
[Paste relevant logs, highlight important parts]

[Troubleshooting Attempted]
1.
2.
```

> **Related Documentation:**
> - [Video VOD and Playback Troubleshooting](./QA_PLAY_ERROR.md)
> - [GB/T Device Configuration Guide](./GUIDE_DEVICE_CONFIG.md)
> - [Media Server Configuration Guide](./MEDIA_SERVER.md)
