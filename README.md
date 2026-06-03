<div align="center">

# PyGBSentry

**让每一台服务器，都成为符合国标的智能视频中枢**

[![License](https://img.shields.io/badge/License-AGPL--v3-blue)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Vue](https://img.shields.io/badge/Vue-3.x-4FC08D?logo=vue.js&logoColor=white)](https://vuejs.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)

[中文](#) | [English](#english-readme)

</div>

---

## 为什么选择 PyGBSentry？

PyGBSentry 是一款**基于最新 GB/T 28181-2022 标准构建的开源国标视频管理平台**（向下兼容 GB/T 28181-2016 设备）。不同于依赖第三方 C 库或商业 SIP 中间件的方案，我们从零实现了纯 Python 的 SIP/GB28181 协议栈，让你真正拥有从信令到流媒体的全链路可控能力。

| 优势 | 说明 |
|:---|:---|
| **纯 Python 原生 SIP 栈** | 自研异步 SIP 协议实现（UDP/TCP 双栈），非封装调用，调试与二改零门槛 |
| **符合最新 GB/T 28181-2022 国标** | 基于现行国家标准开发，向下兼容 2016 版设备；通过配置化方式按需启用 2022 增强特性 |
| **GB28181 全链路覆盖** | 设备接入 / 平台级联 / 实时预览 / 录像回放 / 云台控制 / 语音对讲 / 报警联动 |
| **插件化架构** | 核心代码零侵入，飞书/企微告警、MQTT、S3 云存、AI 识别等能力即插即用 |
| **三端统一** | Web 管理后台（Vue 3）+ 移动端（uni-app）+ REST API，体验一致 |
| **生产级部署** | Docker Compose 一键启动，同时提供 Helm Chart、K8s、Nginx 负载均衡完整方案 |
| **多协议流媒体** | 集成 ZLMediaKit，支持 WebRTC / HTTP-FLV / HLS / RTSP / RTMP 任意切换 |
| **GIS 可视化指挥** | 地图落图、轨迹回放、电视墙拼屏、可视化会商，满足应急调度场景 |
| **企业级治理** | 审计中心全留痕、配置草稿发布、RBAC 权限、JWT+2FA、速率限制、防 DDoS |

---

## 功能全景

```
国标接入          视频业务          智能运维          数据集成          可视化
─────────────    ─────────────    ─────────────    ─────────────    ─────────────
设备注册          实时预览          网络看门狗        MQTT 对接        GIS 地图
平台级联          多分屏播放         流健康监测        Webhook 回调     电视墙拼屏
目录推送          录像检索回放        SLA 质量看板      级联上报         轨迹回放
GPS 订阅          云台 PTZ          容量基线预警      飞书/企微告警     可视化指挥
语音对讲          预置位轮巡         SIP 信令审计      S3 云存储       告警联动
```

---

## GB/T 28181-2022 增强特性

平台基于 **GB/T 28181-2022** 标准实现，在保障向下兼容 2016 版设备的同时，通过配置化方式按需启用 **2022 版核心增强特性**：

| 2022 新特性 | 说明 | 配置方式 |
|:---|:---|:---|
| **SDP a=track 轨道标识** | 精准区分主/子码流与多路轨道，解决 2016 版码流切换模糊问题 | `GB28181_STREAM_SWITCH_USE_TRACK_SUBJECT=true` |
| **绝对云台控制** | 支持地理坐标级精准定位，满足高空瞭望、应急指挥场景 | API 自动识别 2022 指令 |
| **3D 放大/定位 (DragZoom)** | 框选即放大，操作体验对标主流 GIS 平台 | 前端 PTZ 面板直接调用 |
| **文件目录检索** | 按时间、类型、通道精准检索设备端录像文件 | `/api/v1/devices/{id}/file-catalog` |
| **报警细化分类** | 支持入侵、徘徊、聚集等 20+ 细分报警类型订阅与联动 | 报警中心自动解析 |
| **远程配置下载/设置** | 批量下发编码、网络、OSD 参数，千级设备集中运维 | ConfigDownload / ConfigSet API |

> **如何切换版本**：修改 `backend/.env` 中的 `GB28181_VERSION=2022`，重启后端即可。系统会自动适配 SDP、信令 XML 与交互流程。

---

## 快速开始

### Docker 一键部署（Linux 推荐，含流媒体服务）

```bash
git clone https://github.com/suoten/PyGBSentry.git
cd PyGBSentry/editions/open-source

# 创建环境配置
cat > .env << 'EOF'
POSTGRES_PASSWORD=YourStrongDbPass!
REDIS_PASSWORD=YourStrongRedisPass!
SECRET_KEY=change-me-to-32-char-random-string
MEDIA_SERVER_SECRET=zlm-secret-key
BACKEND_PUBLIC_HOST=192.168.1.100
EOF

# 启动全部服务
docker compose up -d
```

访问 `http://<BACKEND_PUBLIC_HOST>` 进入安装向导，首次使用创建管理员账号即可。

> **注意**：内置 ZLMediaKit 仅提供 Linux 二进制，Windows / macOS Docker 桌面版无法运行流媒体容器。Windows/macOS 开发者请使用下方「本地开发模式」。

### 本地开发模式（Windows / Linux / macOS）

```bash
cd backend
cp .env.example .env
python -m venv venv
# Windows: venv\Scripts\activate
# Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
python app/initial_data.py
python -m app.main          # → http://localhost:8000

cd ../frontend
npm install
npm run dev                 # → http://localhost:5173
```

本地模式使用 SQLite，无需 PostgreSQL/Redis，适合二次开发与轻量体验。

---

## 项目目录结构

```
PyGBSentry/
├── backend/                    # Python FastAPI 后端
│   ├── app/
│   │   ├── api/               # REST API 路由（v1 业务端点 + common 通用组件）
│   │   ├── core/              # 配置中心、安全、插件管理、全局单例
│   │   ├── db/                # 数据库会话、模型基类、注册表
│   │   ├── models/            # SQLAlchemy ORM 模型
│   │   ├── schemas/           # Pydantic 数据校验与序列化
│   │   ├── services/          # 业务逻辑、定时任务、健康检查
│   │   ├── sip/               # 自研 SIP/GB28181 协议栈核心
│   │   │   ├── server.py      # SIP 服务器（UDP/TCP 双栈）
│   │   │   ├── handlers.py    # 信令处理器
│   │   │   ├── invite.py      # 点播/回放 INVITE 会话
│   │   │   ├── ptz.py         # 云台控制指令
│   │   │   ├── cascade.py     # 上下级平台级联
│   │   │   └── ...
│   │   └── utils/             # 工具函数（防火墙、流名称生成、SSL 等）
│   ├── alembic/               # 数据库迁移脚本
│   ├── plugins/               # 插件目录与插件市场配置
│   ├── scripts/               # 运维脚本（FFmpeg 安装、数据迁移等）
│   └── tests/                 # 单元测试与集成测试
├── frontend/                   # Vue 3 管理后台
│   └── dist/                  # 生产构建产物
├── mobile/                     # uni-app 移动端（H5 / 小程序 / App）
│   └── src/
│       ├── api/               # 接口封装
│       ├── components/        # 公共组件（播放器、图表、状态标签等）
│       ├── pages/             # 业务页面（设备、告警、地图、工单、SLA 看板等）
│       ├── store/             # Pinia 状态管理
│       └── locales/           # 国际化（zh-CN / en-US）
├── deploy/                     # 生产部署与运维
│   ├── helm/                  # Kubernetes Helm Chart
│   ├── monitoring/            # Prometheus + Grafana + Loki 监控栈
│   ├── nginx/                 # Nginx 负载均衡与 SSL 配置
│   └── scripts/               # 备份、恢复、升级、容量检查、SIP 压测脚本
├── docs/                       # 文档中心
│   ├── INSTALL.md             # 完整部署手册
│   ├── INSTALL_DEPLOY.md      # 生产环境部署指南
│   ├── DEVELOPER.md           # 架构与二次开发指南
│   ├── PLUGIN_SPEC.md         # 插件开发规范
│   ├── COMPATIBILITY.md       # 浏览器与设备兼容性说明
│   ├── MEDIA_SERVER.md        # 流媒体专项配置
│   └── ...
├── docker-compose.yml          # Docker Compose 一键部署
├── docker-compose.ha.yml       # 高可用部署编排
├── docker-compose.monitoring.yml # 监控栈独立编排
├── Dockerfile
├── Makefile
└── LICENSE
```

---

## 技术架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        终端层（多端覆盖）                              │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│   │   Web 后台    │  │  Mobile App  │  │    第三方平台 / 设备      │  │
│   │  Vue 3 + TS  │  │  uni-app     │  │    GB28181 级联对接       │  │
│   └──────┬───────┘  └──────┬───────┘  └────────────┬─────────────┘  │
└──────────┼─────────────────┼───────────────────────┼────────────────┘
           │                 │                       │
┌──────────▼─────────────────▼───────────────────────▼────────────────┐
│                        接入网关层                                     │
│              Nginx 负载均衡 / HTTPS 终结 / 静态资源分发                  │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│                        业务服务层（FastAPI）                           │
│   REST API · WebSocket 推送 · 插件运行时 · 审计日志 · 配置治理            │
├──────────────────────────┬──────────────────────────────────────────┤
│       SIP 信令引擎        │           流媒体网关                      │
│   自研 Python SIP 栈      │      ZLMediaKit Hook 对接                 │
│   GB28181 注册/点播/回放   │   WebRTC / FLV / HLS / RTSP / RTMP       │
│   级联/PTZ/报警/语音      │   RTP 接收 / 录像回调 / 云端录制            │
├──────────────────────────┴──────────────────────────────────────────┤
│                        数据与缓存层                                    │
│         PostgreSQL / MySQL / SQLite        │         Redis            │
│         （持久化数据、审计日志、级联关系）        │    （会话、状态、限流）      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 系统要求

| 部署形态 | 操作系统 | 内存 | 说明 |
|:---|:---|:---|:---|
| Docker 完整部署 | Linux（Ubuntu 20.04+ / Debian 11+ / CentOS 8+） | 4GB+ | 含 ZLMediaKit 流媒体服务，推荐生产环境 |
| 本地开发模式 | Linux / Windows 10+ / macOS 12+ | 2GB+ | SQLite 开箱即用，需外置 ZLM 才能播放 |
| 高可用集群 | Kubernetes 1.25+ | 8GB+ | 使用 `deploy/helm/` 部署 |

详细环境要求与端口说明请参考 [docs/INSTALL.md](docs/INSTALL.md)。

---

## 文档导航

| 文档 | 适合谁 | 内容 |
|:---|:---|:---|
| [INSTALL.md](docs/INSTALL.md) | 运维/实施 | 完整部署手册，含 Docker、手工、高可用方案 |
| [INSTALL_DEPLOY.md](docs/INSTALL_DEPLOY.md) | 运维/实施 | 生产环境 checklist、NAT、端口、SSL 配置 |
| [DEVELOPER.md](docs/DEVELOPER.md) | 开发者 | 架构详解、目录说明、添加 API、扩展 SIP 逻辑 |
| [PLUGIN_SPEC.md](docs/PLUGIN_SPEC.md) | 开发者 | 插件开发规范、生命周期、API、上架流程 |
| [MEDIA_SERVER.md](docs/MEDIA_SERVER.md) | 运维/开发者 | ZLMediaKit 配置、Hook 说明、排错指南 |
| [COMPATIBILITY.md](docs/COMPATIBILITY.md) | 实施/用户 | 浏览器与设备兼容性矩阵 |
| [QA_TROUBLESHOOT.md](docs/QA_TROUBLESHOOT.md) | 所有人 | 常见问题与排查步骤 |

---

## 开源协议

本项目采用 [GNU Affero General Public License v3.0](LICENSE) 开源协议。

> 对于网络交互软件，AGPL v3 确保任何在公网提供服务的修改版本，也必须向用户公开源代码。这保护了开源社区的利益，也保证了项目的长期健康发展。

---

## 社区与支持

- 问题反馈：[GitHub Issues](https://github.com/suoten/PyGBSentry/issues)
- 作者邮箱：[suoten@163.com](mailto:suoten@163.com)

如果你觉得项目有帮助，欢迎点亮 Star，这是对开源作者最好的鼓励。

---
---

<div align="center">

# English README

**Turn any server into a GB/T 28181-compliant intelligent video hub**

</div>

## Why PyGBSentry?

PyGBSentry is an **open-source national standard video management platform built on the latest GB/T 28181-2022** (backward compatible with GB/T 28181-2016 devices). Unlike solutions that rely on third-party C libraries or commercial SIP middleware, we built a pure Python SIP/GB28181 protocol stack from the ground up, giving you full control over the entire pipeline—from signaling to streaming.

| Advantage | Description |
|:---|:---|
| **Native Python SIP Stack** | Self-implemented async SIP protocol (UDP/TCP dual-stack), not a wrapper—easy to debug and customize |
| **Compliant with Latest GB/T 28181-2022** | Built on the current national standard, backward compatible with 2016 devices; 2022 enhancements available on demand via configuration |
| **Full GB28181 Coverage** | Device access / platform cascade / live preview / playback / PTZ control / two-way audio / alarm linkage |
| **Plugin Architecture** | Extend without touching core code: Feishing/WeCom alerts, MQTT, S3 cloud storage, AI recognition, etc. |
| **Triple-Screen Unified** | Web admin (Vue 3) + mobile (uni-app) + REST API, consistent experience across all endpoints |
| **Production-Ready Deployment** | One-command Docker Compose, plus Helm Chart, K8s, and Nginx load balancing recipes |
| **Multi-Protocol Streaming** | Integrated ZLMediaKit supporting WebRTC / HTTP-FLV / HLS / RTSP / RTMP |
| **GIS Visual Command** | Map plotting, trajectory playback, TV wall splicing, and visual conferencing for emergency dispatch |
| **Enterprise Governance** | Full audit trail, config draft publishing, RBAC, JWT+2FA, rate limiting, anti-DDoS |

---

## Feature Overview

```
GB28181 Access     Video Services     Smart Ops        Data Integration     Visualization
───────────────    ──────────────    ────────────    ─────────────────    ──────────────
Device Register    Live Preview       Network Watchdog   MQTT Bridge         GIS Map
Platform Cascade   Multi-Screen       Stream Health      Webhook Callback    TV Wall
Catalog Push       Playback Search    SLA Dashboard      Cascade Uplink      Trajectory
GPS Subscribe      PTZ Control        Capacity Baseline  Feishu/WeCom Alert  Visual Command
Two-Way Audio      Preset Tour        SIP Audit          S3 Cloud Storage    Alarm Linkage
```

---

## GB/T 28181-2022 Enhanced Features

Built on the **GB/T 28181-2022** standard, the platform ensures backward compatibility with 2016 devices while enabling **core 2022 enhancements** on demand through configuration:

| 2022 Feature | Description | How to Use |
|:---|:---|:---|
| **SDP a=track Media Track ID** | Precisely distinguish main/sub streams and multiple tracks, solving the stream-switching ambiguity of the 2016 edition | `GB28181_STREAM_SWITCH_USE_TRACK_SUBJECT=true` |
| **Absolute PTZ Control** | Geo-coordinate-level precise positioning for high-altitude surveillance and emergency command scenarios | API auto-detects 2022 commands |
| **3D Zoom/Positioning (DragZoom)** | Drag-to-zoom interaction matching mainstream GIS platforms | PTZ panel invokes directly |
| **File Directory Retrieval** | Retrieve device-side recordings by time, type, and channel | `/api/v1/devices/{id}/file-catalog` |
| **Alarm Sub-classification** | Supports 20+ refined alarm types (intrusion, loitering, gathering, etc.) | Alarm center auto-parses |
| **Remote Config Download/Set** | Batch-deploy encoding, network, and OSD parameters across thousands of devices | ConfigDownload / ConfigSet API |

> **How to switch versions**: Update `GB28181_VERSION=2022` in `backend/.env` and restart. The system automatically adapts SDP, signaling XML, and interaction flows.

---

## Quick Start

### Docker One-Command Deploy (Linux recommended, includes streaming)

```bash
git clone https://github.com/suoten/PyGBSentry.git
cd PyGBSentry/editions/open-source

# Create environment config
cat > .env << 'EOF'
POSTGRES_PASSWORD=YourStrongDbPass!
REDIS_PASSWORD=YourStrongRedisPass!
SECRET_KEY=change-me-to-32-char-random-string
MEDIA_SERVER_SECRET=zlm-secret-key
BACKEND_PUBLIC_HOST=192.168.1.100
EOF

# Start all services
docker compose up -d
```

Visit `http://<BACKEND_PUBLIC_HOST>` to enter the setup wizard and create your admin account.

> **Note**: The bundled ZLMediaKit only provides Linux binaries; Windows/macOS Docker Desktop cannot run the streaming container. Windows/macOS developers should use "Local Dev Mode" below.

### Local Dev Mode (Windows / Linux / macOS)

```bash
cd backend
cp .env.example .env
python -m venv venv
# Windows: venv\Scripts\activate
# Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
python app/initial_data.py
python -m app.main          # → http://localhost:8000

cd ../frontend
npm install
npm run dev                 # → http://localhost:5173
```

Local mode uses SQLite out of the box; no PostgreSQL/Redis required. Great for development and light evaluation.

---

## Project Structure

```
PyGBSentry/
├── backend/                    # Python FastAPI backend
│   ├── app/
│   │   ├── api/               # REST API routes (v1 endpoints + common components)
│   │   ├── core/              # Config, security, plugin manager, global singletons
│   │   ├── db/                # DB sessions, base classes, registry
│   │   ├── models/            # SQLAlchemy ORM models
│   │   ├── schemas/           # Pydantic validation & serialization
│   │   ├── services/          # Business logic, scheduled tasks, health checks
│   │   ├── sip/               # Self-built SIP/GB28181 protocol stack
│   │   │   ├── server.py      # SIP server (UDP/TCP dual-stack)
│   │   │   ├── handlers.py    # Signaling handlers
│   │   │   ├── invite.py      # Play/playback INVITE sessions
│   │   │   ├── ptz.py         # PTZ control commands
│   │   │   ├── cascade.py     # Upper/lower platform cascading
│   │   │   └── ...
│   │   └── utils/             # Utilities (firewall, stream naming, SSL, etc.)
│   ├── alembic/               # Database migration scripts
│   ├── plugins/               # Plugin directory & marketplace config
│   ├── scripts/               # Ops scripts (FFmpeg install, data migration, etc.)
│   └── tests/                 # Unit & integration tests
├── frontend/                   # Vue 3 admin dashboard
│   └── dist/                  # Production build artifacts
├── mobile/                     # uni-app mobile client (H5 / mini-program / App)
│   └── src/
│       ├── api/               # API wrappers
│       ├── components/        # Shared components (player, charts, status tags)
│       ├── pages/             # Business pages (devices, alarms, map, work orders, SLA)
│       ├── store/             # Pinia state management
│       └── locales/           # i18n (zh-CN / en-US)
├── deploy/                     # Production deployment & operations
│   ├── helm/                  # Kubernetes Helm Chart
│   ├── monitoring/            # Prometheus + Grafana + Loki stack
│   ├── nginx/                 # Nginx load balancing & SSL config
│   └── scripts/               # Backup, restore, upgrade, capacity check, SIP load test
├── docs/                       # Documentation center
│   ├── INSTALL.md             # Full deployment guide
│   ├── INSTALL_DEPLOY.md      # Production environment guide
│   ├── DEVELOPER.md           # Architecture & development guide
│   ├── PLUGIN_SPEC.md         # Plugin development specification
│   ├── MEDIA_SERVER.md        # Streaming server configuration
│   └── ...
├── docker-compose.yml
├── docker-compose.ha.yml
├── docker-compose.monitoring.yml
├── Dockerfile
├── Makefile
└── LICENSE
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Client Layer (Multi-Screen)                   │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│   │   Web Admin   │  │  Mobile App  │  │    3rd Party / Devices   │  │
│   │  Vue 3 + TS  │  │  uni-app     │  │    GB28181 Cascade       │  │
│   └──────┬───────┘  └──────┬───────┘  └────────────┬─────────────┘  │
└──────────┼─────────────────┼───────────────────────┼────────────────┘
           │                 │                       │
┌──────────▼─────────────────▼───────────────────────▼────────────────┐
│                        Gateway Layer                                  │
│              Nginx Load Balancer / HTTPS / Static Assets              │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│                        Service Layer (FastAPI)                        │
│   REST API · WebSocket Push · Plugin Runtime · Audit Log · Config     │
├──────────────────────────┬──────────────────────────────────────────┤
│       SIP Signaling       │           Streaming Gateway               │
│   Native Python SIP Stack │      ZLMediaKit Hook Integration          │
│   GB28181 Register/Play/  │   WebRTC / FLV / HLS / RTSP / RTMP        │
│   Playback/Cascade/PTZ    │   RTP Receiver / Record Callback          │
├──────────────────────────┴──────────────────────────────────────────┤
│                        Data & Cache Layer                             │
│         PostgreSQL / MySQL / SQLite        │         Redis             │
│         (Persistent data, audit, cascade)  │    (Sessions, state, rate)│
└─────────────────────────────────────────────────────────────────────┘
```

---

## System Requirements

| Deployment Form | OS | RAM | Notes |
|:---|:---|:---|:---|
| Docker Full Deploy | Linux (Ubuntu 20.04+ / Debian 11+ / CentOS 8+) | 4GB+ | Includes ZLMediaKit streaming; recommended for production |
| Local Dev Mode | Linux / Windows 10+ / macOS 12+ | 2GB+ | SQLite out-of-the-box; external ZLM needed for playback |
| HA Cluster | Kubernetes 1.25+ | 8GB+ | Use `deploy/helm/` |

For detailed environment requirements and port list, see [docs/INSTALL.md](docs/INSTALL.md).

---

## Documentation

| Document | Audience | Content |
|:---|:---|:---|
| [INSTALL.md](docs/INSTALL.md) | DevOps/Integrator | Full deployment guide: Docker, manual, HA |
| [INSTALL_DEPLOY.md](docs/INSTALL_DEPLOY.md) | DevOps | Production checklist, NAT, ports, SSL |
| [DEVELOPER.md](docs/DEVELOPER.md) | Developers | Architecture deep dive, adding APIs, extending SIP |
| [PLUGIN_SPEC.md](docs/PLUGIN_SPEC.md) | Developers | Plugin spec, lifecycle, APIs, publishing |
| [MEDIA_SERVER.md](docs/MEDIA_SERVER.md) | DevOps/Developers | ZLMediaKit config, hooks, troubleshooting |
| [COMPATIBILITY.md](docs/COMPATIBILITY.md) | Integrator/Users | Browser & device compatibility matrix |
| [QA_TROUBLESHOOT.md](docs/QA_TROUBLESHOOT.md) | Everyone | FAQ & troubleshooting steps |

---

## License

This project is licensed under the [GNU Affero General Public License v3.0](LICENSE).

> AGPL v3 ensures that any modified version of the software offered as a network service must also provide its source code to users. This protects the interests of the open-source community and ensures the long-term healthy development of the project.

---

## Community & Support

- Issues: [GitHub Issues](https://github.com/suoten/PyGBSentry/issues)
- Author: [suoten@163.com](mailto:suoten@163.com)

If you find this project helpful, a Star is the best encouragement for open-source authors.
