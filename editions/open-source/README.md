<div align="center">

# PyGBSentry

### 下一代 Python 智能视频监控平台

**让每一台普通服务器，都成为具备 AI 视力的智能哨兵**

[![License](https://img.shields.io/github/license/suoten/PyGBSentry?color=blue&label=license)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Vue](https://img.shields.io/badge/Vue-3.x-4FC08D?logo=vue.js&logoColor=white)](https://vuejs.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)

</div>

---

## 为什么选择 PyGBSentry？

| | 特性 | 说明 |
|:-:|:-----|:-----|
| :rocket: | **1 秒启动，200MB 内存** | 极致轻量，完美运行于树莓派、边缘盒子、云服务器 |
| :brain: | **原生 AI 能力** | 内置 YOLOv8 视觉中枢，人脸/车牌/行为识别开箱即用 |
| :electric_plug: | **丰富插件生态** | 飞书告警、企微告警、MQTT 桥接、S3 云存、Webhook… |
| :shield: | **企业级安全** | 速率限制、JWT+2FA、防 DDoS、操作审计 |
| :globe_with_meridians: | **标准协议** | 完整 GB28181 国标实现，SIP 信令 + RTP 流媒体 |
| :movie_camera: | **多协议流媒体** | HTTP-FLV / WebRTC / RTSP / RTMP 全支持 |
| :map: | **GIS 可视化** | 实时定位、轨迹回放、地图指挥 |
| :tv: | **多屏监控墙** | 电视墙自由拼屏，支持 1/4/9/16 宫格 |

---

## 功能全景

```
视频能力          信令控制          智能运维          数据集成          可视化
─────────────    ─────────────    ─────────────    ─────────────    ─────────────
实时预览          云台 PTZ          网络看门狗        MQTT 对接        GIS 地图
设备回放          预置位轮巡         流健康监测        Webhook 回调     多屏监控墙
云端录像          语音对讲           SIP 信令审计      级联上报         电视墙拼屏
延时摄影          设备远程控制        容量基线          S3 云存          轨迹回放
快照抓拍          辅助开关/雨刷       SLA 质量看板     飞书/企微告警     可视化指挥
```

---

## 系统要求

> :bulb: **先看这个！** 选错系统是部署失败最常见的原因。

### Docker 部署（推荐）—— 仅限 Linux

| 项目 | 要求 |
|:-----|:-----|
| **操作系统** | :penguin: **Linux**（Ubuntu 20.04+、Debian 11+、CentOS 8+ 等） |
| **Docker** | 20.10+ |
| **Docker Compose** | 1.29+ 或 Docker Compose V2 |
| **内存** | 最低 2GB，推荐 4GB+ |
| **磁盘** | 最低 10GB（录像另计） |
| **网络** | 需要公网 IP 或局域网可达 IP |

> :warning: **Windows / macOS 不能用 Docker 部署！** 内置流媒体服务器（ZLMediaKit）只编译了 Linux 二进制，Windows/macOS 的 Docker 容器无法启动流媒体服务。Windows/macOS 用户请使用下面的「本地开发模式」。

### 本地开发模式 —— Linux / Windows / macOS 均可

| 项目 | 要求 |
|:-----|:-----|
| **操作系统** | Linux / Windows 10+ / macOS 12+ |
| **Python** | 3.10 ~ 3.12 |
| **Node.js** | 18+ |
| **npm** | 8+ |
| **数据库** | SQLite（开箱即用，无需安装） |

> :bulb: 本地开发模式使用 SQLite，无需安装 PostgreSQL 和 Redis，适合体验和二次开发。**但不包含内置流媒体服务器**，需要外置 ZLMediaKit 或仅使用管理功能。

---

## 部署方式一：Docker 一键部署（Linux 推荐）

> :bulb: 以下所有命令都在 **Linux 终端** 中执行。如果你用的是 Windows，请跳到[部署方式二](#部署方式二本地开发模式-windows--linux--macos)。

### 第 1 步：安装 Docker

如果还没装 Docker，执行以下命令（Ubuntu/Debian）：

```bash
# 一键安装 Docker（官方脚本）
curl -fsSL https://get.docker.com | sudo sh

# 让当前用户可以不用 sudo 执行 docker
sudo usermod -aG docker $USER

# 重新登录终端，或者执行下面这句让权限生效
newgrp docker

# 验证安装
docker --version
docker compose version
```

> :bulb: CentOS / 其他发行版也可以用上面的脚本。如果公司网络限制，参考 [Docker 官方安装文档](https://docs.docker.com/engine/install/)。

### 第 2 步：克隆代码

```bash
git clone https://github.com/suoten/PyGBSentry.git
cd PyGBSentry/editions/open-source
```

> :bulb: 没装 git？执行 `sudo apt install git -y`（Ubuntu/Debian）或 `sudo yum install git -y`（CentOS）。

### 第 3 步：查看服务器 IP

```bash
# 查看你的服务器 IP 地址（记住这个 IP，下一步要用）
hostname -I
```

输出类似 `192.168.1.100 172.17.0.1`，取第一个就是你的 IP。

> :warning: **不要用 `127.0.0.1` 或 `localhost`！** Docker 容器之间需要通过真实 IP 通信，填 localhost 会导致流媒体服务无法连接后端。

### 第 4 步：创建配置文件

在 `editions/open-source` 目录下创建 `.env` 文件：

```bash
cat > .env << 'EOF'
# ===== 必填项（请根据你的实际情况修改）=====

# PostgreSQL 数据库密码（自己定一个强密码）
POSTGRES_PASSWORD=MyDbP@ssw0rd!2024

# Redis 密码（自己定一个强密码）
REDIS_PASSWORD=MyRedisP@ss!2024

# JWT 签名密钥（随便填一个 32 位以上的随机字符串）
SECRET_KEY=sk-a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6

# ZLMediaKit API 密钥（自己定一个，记住它）
MEDIA_SERVER_SECRET=zlm-my-secret-2024

# 你的服务器 IP（用第 3 步查到的 IP 替换下面的地址）
BACKEND_PUBLIC_HOST=192.168.1.100

# ===== 可选项（一般不用改）=====
APP_ENV=prod
EOF
```

> :warning: **必须修改的项**：
> - `BACKEND_PUBLIC_HOST` —— 改成你服务器的**真实 IP 地址**
> - `POSTGRES_PASSWORD` / `REDIS_PASSWORD` —— 改成你自己的强密码
> - `SECRET_KEY` —— 改成你自己的随机字符串
> - `MEDIA_SERVER_SECRET` —— 改成你自己的密钥
>
> 这些值**不要照抄上面的示例**，否则不安全！

### 第 5 步：启动服务

```bash
docker compose up -d
```

> :bulb: 如果你的系统用的是老版本 docker-compose（带横杠），请用 `docker-compose up -d`。

等待约 30-60 秒，所有服务启动完成。

### 第 6 步：验证启动状态

```bash
# 查看所有容器是否正常运行（Status 列应该都是 Up）
docker compose ps

# 查看后端日志（确认没有报错）
docker compose logs backend --tail 20
```

正常情况下你应该看到类似输出：

```
NAME                STATUS              PORTS
opensource-db-1     Up 2 minutes        0.0.0.0:5432->5432/tcp
opensource-redis-1  Up 2 minutes        0.0.0.0:6379->6379/tcp
opensource-backend-1 Up 2 minutes       0.0.0.0:8000->8000/tcp, ...
opensource-frontend-1 Up 2 minutes      0.0.0.0:80->80/tcp
```

### 第 7 步：打开浏览器

在浏览器中访问：

| 服务 | 地址 | 说明 |
|:-----|:-----|:-----|
| **管理界面** | `http://你的服务器IP` | 首次访问进入安装向导 |
| API 接口 | `http://你的服务器IP:8000` | 后端 REST API |
| API 文档 | `http://你的服务器IP:8000/docs` | 需在 .env 中设置 `ENABLE_OPENAPI_DOCS=true` |

> :bulb: 首次访问会进入安装向导，按提示创建管理员账号即可开始使用！

> :warning: **如果页面打不开**，请看下面的[常见问题排查](#页面打不开怎么办)。

---

## 部署方式二：本地开发模式（Windows / Linux / macOS）

> :bulb: 这个模式适合想体验、学习或二次开发的同学。**不需要 Docker**，但也没有内置流媒体服务器。

### 第 1 步：安装依赖

**Windows：**

1. 安装 Python 3.10+：[下载地址](https://www.python.org/downloads/)（安装时勾选 "Add Python to PATH"）
2. 安装 Node.js 18+：[下载地址](https://nodejs.org/)（选择 LTS 版本）
3. 打开 **PowerShell** 或 **CMD** 继续下面的步骤

**Linux（Ubuntu/Debian）：**

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv nodejs npm
```

**macOS：**

```bash
brew install python@3.12 node@20
```

### 第 2 步：克隆代码

```bash
git clone https://github.com/suoten/PyGBSentry.git
cd PyGBSentry/editions/open-source
```

### 第 3 步：启动后端

```bash
cd backend

# 复制配置模板
cp .env.example .env

# 安装 Python 依赖（建议用虚拟环境）
python -m venv venv
# Windows 激活:  venv\Scripts\activate
# Linux/macOS 激活:  source venv/bin/activate
pip install -r requirements.txt

# 初始化数据库和管理员
python app/initial_data.py

# 启动后端 → http://localhost:8000
python -m app.main
```

> :bulb: 默认使用 SQLite 数据库，无需额外安装。生产环境建议使用 PostgreSQL。

### 第 4 步：启动前端（另开一个终端）

```bash
cd frontend

# 安装前端依赖
npm install

# 启动开发服务器 → http://localhost:5173
npm run dev
```

### 第 5 步：打开浏览器

在浏览器中访问 `http://localhost:5173`，首次访问进入安装向导。

---

## 配置说明

### Docker 部署必填环境变量

| 变量 | 作用 | 怎么填 | 示例 |
|:-----|:-----|:-------|:-----|
| `POSTGRES_PASSWORD` | PostgreSQL 密码 | 自己定一个强密码 | `MyDbP@ss!2024` |
| `REDIS_PASSWORD` | Redis 密码 | 自己定一个强密码 | `MyRedisP@ss!2024` |
| `SECRET_KEY` | JWT 签名密钥 | 32 位以上随机字符串 | `sk-a1b2c3d4e5f6...` |
| `MEDIA_SERVER_SECRET` | ZLMediaKit API 密钥 | 自己定一个密钥 | `zlm-secret-2024` |
| `BACKEND_PUBLIC_HOST` | 服务器 IP | **必须填真实 IP** | `192.168.1.100` |

> :warning: `BACKEND_PUBLIC_HOST` 是 Docker 部署中**最容易填错**的项：
> - :white_check_mark: 正确：`192.168.1.100`（你的服务器真实 IP）
> - :x: 错误：`localhost`、`127.0.0.1`（Docker 容器内无法通过 localhost 访问宿主机）
> - :x: 错误：`0.0.0.0`（这不是有效地址）

### 数据库选择

| 数据库 | 适用场景 | 配置 |
|:-------|:---------|:-----|
| **PostgreSQL** | Docker 部署 / 生产环境（推荐） | `DATABASE_TYPE=postgresql` |
| **MySQL** | 已有 MySQL 环境 | `DATABASE_TYPE=mysql` |
| **SQLite** | 本地开发 / 体验 | `DATABASE_TYPE=sqlite` |

### 常用可选配置

| 变量 | 默认值 | 说明 |
|:-----|:-------|:-----|
| `APP_ENV` | `prod` | 环境：`dev` 开发 / `prod` 生产 |
| `SIP_PORT` | `5060` | SIP 信令端口 |
| `ENABLE_AUTO_DISCOVERY` | `true` | 允许未知设备自动注册 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | Token 有效期（分钟） |
| `ENABLE_OPENAPI_DOCS` | `false` | 开启 API 文档（生产建议关闭） |
| `DEMO_MODE` | `false` | 演示模式 |

完整配置参考 `backend/.env.example`

---

## 使用指南

### 设备接入（3 步完成）

1. 在摄像头/录像机中配置 SIP 服务器地址、SIP 域、设备 ID
2. 设备注册成功后自动出现在「设备列表」
3. 点击设备 → 查看通道 → 实时预览 / 回放录像

### 常用操作速查

| 操作 | 入口 |
|:-----|:-----|
| 实时预览 | 监控中心 → 通道 → 播放 |
| 云台控制 | 通道详情 → PTZ 面板 |
| 云端录像 | 录像计划 → 配置计划 → 自动录像 |
| 设备回放 | 设备录像 → 选择时间范围 |
| 告警管理 | 告警中心 → 确认/升级 |
| 系统配置 | 配置中心 → 基础/数据库/流媒体 |

---

## 常见问题排查

### 页面打不开怎么办？

> :bulb: 这是最常见的问题，按顺序排查：

**1. 检查容器是否都在运行**

```bash
docker compose ps
```

如果看到某个容器 Status 不是 `Up`，查看它的日志：

```bash
docker compose logs backend --tail 50
docker compose logs frontend --tail 50
```

**2. 检查防火墙是否放行了端口**

需要放行的端口：

| 端口 | 用途 |
|:-----|:-----|
| 80 | 管理界面（HTTP） |
| 8000 | 后端 API |
| 5060 | SIP 信令（UDP + TCP） |
| 8880 | ZLM HTTP 流媒体 |
| 30000-30199 | RTP 视频流（UDP） |

```bash
# Ubuntu/Debian 放行端口
sudo ufw allow 80/tcp
sudo ufw allow 8000/tcp
sudo ufw allow 5060/tcp
sudo ufw allow 5060/udp
sudo ufw allow 8880/tcp
sudo ufw allow 30000:30199/udp

# CentOS/RHEL 放行端口
sudo firewall-cmd --permanent --add-port=80/tcp
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --permanent --add-port=5060/tcp
sudo firewall-cmd --permanent --add-port=5060/udp
sudo firewall-cmd --permanent --add-port=8880/tcp
sudo firewall-cmd --permanent --add-port=30000-30199/udp
sudo firewall-cmd --reload
```

> :warning: **云服务器还需要在安全组中放行以上端口！** 这是最容易被忽略的一步。

**3. 检查 BACKEND_PUBLIC_HOST 是否填对了**

```bash
# 查看当前配置
grep BACKEND_PUBLIC_HOST .env
```

- 如果显示 `localhost` 或 `127.0.0.1` → **错误**，改成服务器真实 IP
- 如果显示 `0.0.0.0` → **错误**，改成服务器真实 IP

修改后重启：

```bash
docker compose down
docker compose up -d
```

**4. 检查 SSL 证书问题**

如果你用 HTTPS 访问但没配证书，浏览器会显示安全错误。Docker 部署默认使用 **HTTP（80 端口）**，请用 `http://` 而不是 `https://` 访问。

**5. 本地开发模式页面打不开**

- 确认后端已启动：浏览器访问 `http://localhost:8000/health`，应返回 `{"status":"ok"}`
- 确认前端已启动：终端显示 `Local: http://localhost:5173/`
- 如果 5173 端口被占用，前端会自动使用 5174 等端口，看终端提示

### 启动问题

**Q: 执行 `docker compose up -d` 报错 `required variable POSTGRES_PASSWORD is missing`**

A: 你没有创建 `.env` 文件，或者文件内容不对。请按[第 4 步](#第-4-步创建配置文件)创建 `.env` 文件。注意：
- `.env` 文件必须在 `docker-compose.yml` 同一目录下
- 文件名是 `.env`，不是 `env.txt` 或 `.env.example`
- 用 `ls -la` 确认文件存在

**Q: 容器启动后报 `SECRET_KEY` 为空**

A: `.env` 文件中必须设置 `SECRET_KEY`。确保格式正确——等号两边不要有空格，值不需要加引号：

```
# 正确
SECRET_KEY=sk-a1b2c3d4e5f6g7h8

# 错误（有空格）
SECRET_KEY = sk-a1b2c3d4e5f6g7h8

# 错误（加了引号）
SECRET_KEY="sk-a1b2c3d4e5f6g7h8"
```

**Q: Redis 连接超时**

A: 检查 Redis 密码是否与 `.env` 中一致。如果不需要 Redis，可以在 `.env` 中添加 `INIT_REDIS_ON_STARTUP=false`，系统可降级运行。

**Q: ZLM Hook 不可达 / 视频播放黑屏**

A: 这是 `BACKEND_PUBLIC_HOST` 填错导致的。Docker 部署时必须填**容器网络可达的 IP**（宿主机 IP 或 Docker 网关），**不能填 localhost**。查看宿主机 IP：

```bash
hostname -I
# 或
ip addr show docker0
```

**Q: 未检测到 FFmpeg**

A: 安装 FFmpeg：

```bash
# Ubuntu/Debian
sudo apt install ffmpeg -y

# CentOS/RHEL
sudo yum install ffmpeg -y
```

缺少 FFmpeg 会影响快照、AI 推理和录像处理，但不影响基本的视频预览。

### 设备问题

**Q: 设备注册不上**

A: 逐一检查：
1. SIP 端口 5060 是否放行（防火墙 + 云服务器安全组）
2. 设备端 SIP 域和 ID 是否与平台一致（默认 SIP 域：`3402000000`，SIP 服务器 ID：`34020000002000000001`）
3. 设备端 SIP 服务器地址是否填了你的服务器 IP（不是 localhost）
4. 查看后端日志：`docker compose logs backend --tail 100 | grep -i register`

**Q: 视频播放黑屏/卡顿**

A: 检查：
1. RTP 端口范围（30000-30199 UDP）是否放行（防火墙 + 云服务器安全组）
2. 设备编码格式是否支持（推荐 H.264，部分设备 H.265 需要浏览器支持）
3. 网络带宽是否足够（一路 1080P 约 4Mbps）

### 部署问题

**Q: 我用的是 Windows，能 Docker 部署吗？**

A: **不能。** 内置流媒体服务器（ZLMediaKit）只编译了 Linux 二进制，Windows Docker 容器无法运行。Windows 用户请使用[本地开发模式](#部署方式二本地开发模式-windows--linux--macos)。

**Q: 我用的是 macOS，能 Docker 部署吗？**

A: **不能。** 同上原因，ZLMediaKit 二进制仅支持 Linux。macOS 用户请使用[本地开发模式](#部署方式二本地开发模式-windows--linux--macos)。

**Q: Docker 端口冲突**

A: 修改 `docker-compose.yml` 中对应端口映射，如 `8000:8000` 改为 `8080:8000`：

```yaml
ports:
  - "8080:8000"    # 把宿主机端口从 8000 改为 8080
```

**Q: 数据会丢失吗？**

A: Docker 使用 named volumes（postgres_data、backend_data 等），容器重建不影响数据。备份：

```bash
docker compose exec db pg_dump -U postgres pygb28181 > backup.sql
```

**Q: 如何更新版本？**

```bash
git pull
docker compose build
docker compose up -d
```

**Q: 如何完全卸载？**

```bash
docker compose down -v    # -v 会删除数据卷，谨慎操作！
```

---

## 端口说明

| 端口 | 协议 | 用途 | 是否必须放行 |
|:-----|:-----|:-----|:------------|
| 80 | TCP | 管理界面（Nginx） | :white_check_mark: 是 |
| 8000 | TCP | 后端 API | :white_check_mark: 是 |
| 5060 | UDP+TCP | SIP 信令 | :white_check_mark: 是 |
| 8880 | TCP | ZLM HTTP 流媒体 | :white_check_mark: 是 |
| 554 | TCP | ZLM RTSP | 可选 |
| 1935 | TCP | ZLM RTMP | 可选 |
| 30000-30199 | UDP | RTP 视频流 | :white_check_mark: 是 |
| 5432 | TCP | PostgreSQL | :x: 仅本机访问 |
| 6379 | TCP | Redis | :x: 仅本机访问 |

> :warning: **云服务器用户**：除了 Linux 防火墙，还必须在云服务商的**安全组**中放行以上端口！这是最常见的遗漏。

---

## 技术架构

```
┌─────────────────────────────────────────────────────┐
│                    前端 (Vue 3)                      │
│   TypeScript + Vite + Element Plus + Pinia          │
├─────────────────────────────────────────────────────┤
│                    后端 (FastAPI)                     │
│   SQLAlchemy 2.0 (async) + Pydantic 2 + JWT/2FA    │
├──────────────────────┬──────────────────────────────┤
│    SIP 信令 (GB28181)  │     流媒体 (ZLMediaKit)      │
│    自研 SIP 栈         │  HTTP-FLV/WebRTC/RTSP/RTMP  │
├──────────────────────┴──────────────────────────────┤
│     PostgreSQL / MySQL / SQLite    │     Redis       │
└─────────────────────────────────────────────────────┘
```

---

## 文档

- [插件开发规范](docs/PLUGIN_SPEC.md) — 开发你自己的 PyGBSentry 插件
- [兼容性说明](docs/COMPATIBILITY.md) — 浏览器和设备兼容性

---

## 许可证

MIT License — 自由使用、修改、分发

---

## 作者

**suoten** — [suoten@163.com](mailto:suoten@163.com)

如有问题或建议，欢迎提 [Issue](https://github.com/suoten/PyGBSentry/issues)
