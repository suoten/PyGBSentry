# PyGBSentry 快速安装指南

[中文](#) | [English](#english-version)

本文档提供快速上手指南，帮助你在最短时间内完成系统部署并启动运行。如需了解详细部署方案，请参考 [INSTALL_DEPLOY.md](./INSTALL_DEPLOY.md)。

---

## 目录

- [环境要求](#环境要求)
- [方式一：Docker 一键部署（推荐）](#方式一docker-一键部署推荐)
- [方式二：宝塔面板部署](#方式二宝塔面板部署)
- [方式三：Linux 源码部署](#方式三linux-源码部署)
- [方式四：Windows 开发测试](#方式四windows-开发测试)
- [常见问题速查](#常见问题速查)
- [下一步](#下一步)

---

## 环境要求

| 软件 | 最低版本 | 推荐版本 |
| :--- | :--- | :--- |
| Python | 3.10 | 3.10+ |
| Node.js | 16 | 18+ |
| Docker | 20.10 | 最新版 |
| Docker Compose | 2.0 | 最新版 |

---

## 方式一：Docker 一键部署（推荐）

### 1. 获取代码

```bash
git clone <你的仓库地址>
cd PyGBSentry/editions/open-source
```

### 2. 配置环境变量

```bash
cd backend
cp .env.example .env
```

编辑 `.env` 文件，至少修改以下配置项：

```env
SECRET_KEY=你的随机密钥
MEDIA_SERVER_SECRET=你的流媒体密钥
# 数据库配置（根据需要修改）
```

### 3. 启动服务

返回项目根目录并启动：

```bash
cd ..
docker compose --profile prod up -d
```

### 4. 验证部署

| 检查项 | 地址 | 预期结果 |
| :--- | :--- | :--- |
| Web 控制台 | `http://<服务器IP>/` | 打开登录页 |
| 登录测试 | — | 账号：`admin` / 密码：`Aa332211` |
| API 健康检查 | `http://<服务器IP>:8000/api/v1/ops/db-check` | 返回 `{"status": "ok"}` |

---

## 方式二：宝塔面板部署

### 1. 安装环境

在宝塔「软件商店」中安装以下软件：
- PostgreSQL（或 MySQL）
- Redis
- Python 管理器
- Nginx

### 2. 创建数据库

在宝塔「数据库」管理中创建名为 `pygbsentry` 的数据库。

### 3. 部署后端

1. 将 `backend` 目录上传至服务器 `/www/wwwroot/pygbsentry_backend`。
2. 在「Python 管理器」中添加项目：
   - **项目路径**：`/www/wwwroot/pygbsentry_backend`
   - **启动文件**：`app/main.py`
   - **端口**：`8000`
3. 修改 `.env` 文件，配置数据库连接信息。

### 4. 部署前端

```bash
cd frontend
npm install
npm run build
```

将构建生成的 `dist` 目录上传至 `/www/wwwroot/pygbsentry_web`，然后在宝塔中添加「纯静态」站点。

### 5. 配置 Nginx 反向代理

在站点配置中添加：

```nginx
location /api/ {
  proxy_pass http://127.0.0.1:8000;
}

location /ws/ {
  proxy_pass http://127.0.0.1:8000;
  proxy_http_version 1.1;
  proxy_set_header Upgrade $http_upgrade;
  proxy_set_header Connection "Upgrade";
}
```

---

## 方式三：Linux 源码部署

### 1. 安装系统依赖

```bash
sudo apt update
sudo apt install -y python3-pip python3-venv postgresql redis-server libgl1-mesa-glx
```

### 2. 部署后端

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 根据需要修改 .env 配置
python app/initial_data.py
python -m app.main
```

### 3. 部署前端

```bash
cd frontend
npm install
npm run build
```

构建完成后，将 `dist` 目录交给 Nginx 托管。

---

## 方式四：Windows 开发测试

### 1. 安装依赖软件

- **Python**：3.10+（从 [python.org](https://www.python.org) 下载安装）
- **Node.js**：18+
- **Docker Desktop**：用于运行 PostgreSQL / Redis

### 2. 部署后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
python app\initial_data.py
python -m app.main
```

### 3. 部署前端

```powershell
cd frontend
npm install
npm run dev
```

---

## 常见问题速查

| 问题 | 快速解决方案 |
| :--- | :--- |
| 端口冲突 | 确保 **5060**、**8000**、**80**、**1935**、**554** 未被占用 |
| 视频黑屏 | 检查防火墙规则，开放 **UDP 10000–40000** 端口段 |
| 数据库连接失败 | 检查 `.env` 中的数据库配置，确认数据库服务已启动 |
| 页面跳转到 `/setup` | 打开 `/#/setup` 查看检测项提示，按提示修复问题 |

---

## 下一步

- **详细部署文档**：[INSTALL_DEPLOY.md](./INSTALL_DEPLOY.md)
- **流媒体配置**：[MEDIA_SERVER.md](./MEDIA_SERVER.md)
- **产品能力说明**：[PRODUCT_OSS.md](./PRODUCT_OSS.md)

---

# English Version

# PyGBSentry Quick Installation Guide

This document provides a quick start guide to help you deploy and launch the system in the shortest possible time. For detailed deployment instructions, please refer to [INSTALL_DEPLOY.md](./INSTALL_DEPLOY.md).

---

## Table of Contents

- [Requirements](#requirements)
- [Method 1: One-Click Docker Deployment (Recommended)](#method-1-one-click-docker-deployment-recommended)
- [Method 2: aaPanel Deployment](#method-2-aapanel-deployment)
- [Method 3: Linux Source Deployment](#method-3-linux-source-deployment)
- [Method 4: Windows Development & Testing](#method-4-windows-development--testing)
- [Quick Troubleshooting](#quick-troubleshooting)
- [Next Steps](#next-steps)

---

## Requirements

| Software | Minimum Version | Recommended Version |
| :--- | :--- | :--- |
| Python | 3.10 | 3.10+ |
| Node.js | 16 | 18+ |
| Docker | 20.10 | Latest |
| Docker Compose | 2.0 | Latest |

---

## Method 1: One-Click Docker Deployment (Recommended)

### 1. Get the Code

```bash
git clone <你的仓库地址>
cd PyGBSentry/editions/open-source
```

### 2. Configure Environment Variables

```bash
cd backend
cp .env.example .env
```

Edit the `.env` file and modify at least the following items:

```env
SECRET_KEY=你的随机密钥
MEDIA_SERVER_SECRET=你的流媒体密钥
# 数据库配置（根据需要修改）
```

### 3. Start Services

Return to the project root and start:

```bash
cd ..
docker compose --profile prod up -d
```

### 4. Verify Deployment

| Check Item | URL | Expected Result |
| :--- | :--- | :--- |
| Web Console | `http://<服务器IP>/` | Login page opens |
| Login Test | — | Username: `admin` / Password: `Aa332211` |
| API Health Check | `http://<服务器IP>:8000/api/v1/ops/db-check` | Returns `{"status": "ok"}` |

---

## Method 2: aaPanel Deployment

### 1. Install Environment

Install the following software in aaPanel "App Store":
- PostgreSQL (or MySQL)
- Redis
- Python Manager
- Nginx

### 2. Create Database

Create a database named `pygbsentry` in aaPanel "Database" management.

### 3. Deploy Backend

1. Upload the `backend` directory to `/www/wwwroot/pygbsentry_backend`.
2. Add a project in "Python Manager":
   - **Project Path**: `/www/wwwroot/pygbsentry_backend`
   - **Startup File**: `app/main.py`
   - **Port**: `8000`
3. Modify `.env` to configure database connection.

### 4. Deploy Frontend

```bash
cd frontend
npm install
npm run build
```

Upload the generated `dist` directory to `/www/wwwroot/pygbsentry_web`, then add a "Static" site in aaPanel.

### 5. Configure Nginx Reverse Proxy

Add the following to site configuration:

```nginx
location /api/ {
  proxy_pass http://127.0.0.1:8000;
}

location /ws/ {
  proxy_pass http://127.0.0.1:8000;
  proxy_http_version 1.1;
  proxy_set_header Upgrade $http_upgrade;
  proxy_set_header Connection "Upgrade";
}
```

---

## Method 3: Linux Source Deployment

### 1. Install System Dependencies

```bash
sudo apt update
sudo apt install -y python3-pip python3-venv postgresql redis-server libgl1-mesa-glx
```

### 2. Deploy Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 根据需要修改 .env 配置
python app/initial_data.py
python -m app.main
```

### 3. Deploy Frontend

```bash
cd frontend
npm install
npm run build
```

After build, let Nginx serve the `dist` directory.

---

## Method 4: Windows Development & Testing

### 1. Install Required Software

- **Python**: 3.10+ (download from [python.org](https://www.python.org))
- **Node.js**: 18+
- **Docker Desktop**: for running PostgreSQL / Redis

### 2. Deploy Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
python app\initial_data.py
python -m app.main
```

### 3. Deploy Frontend

```powershell
cd frontend
npm install
npm run dev
```

---

## Quick Troubleshooting

| Issue | Quick Solution |
| :--- | :--- |
| Port Conflict | Ensure **5060**, **8000**, **80**, **1935**, **554** are not occupied |
| Black Screen Video | Check firewall rules and open **UDP 10000–40000** port range |
| Database Connection Failed | Check `.env` database configuration and confirm service is running |
| Page Redirects to `/setup` | Open `/#/setup` to view check items and fix according to prompts |

---

## Next Steps

- **Detailed Deployment**: [INSTALL_DEPLOY.md](./INSTALL_DEPLOY.md)
- **Media Server Configuration**: [MEDIA_SERVER.md](./MEDIA_SERVER.md)
- **Product Capabilities**: [PRODUCT_OSS.md](./PRODUCT_OSS.md)
