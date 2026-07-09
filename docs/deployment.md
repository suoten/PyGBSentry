# 部署指南

> **适用目录**：`editions/open-source`
> **目标读者**：运维工程师、系统管理员、首次部署用户

---

## 目录

- [1. 部署完成后你将得到什么](#1-部署完成后你将得到什么)
- [2. 系统要求](#2-系统要求)
- [3. 端口规划](#3-端口规划)
- [4. Docker 部署（推荐）](#4-docker-部署推荐)
- [5. 手工部署 — Linux](#5-手工部署--linux)
- [6. 手工部署 — Windows](#6-手工部署--windows)
- [7. 数据库配置](#7-数据库配置)
- [8. Nginx 反向代理](#8-nginx-反向代理)
- [9. ZLMediaKit 重点配置](#9-zlmediakit-重点配置)
- [10. 验收清单](#10-验收清单)
- [11. 常见报错与处理](#11-常见报错与处理)
- [12. 升级、备份与回滚](#12-升级备份与回滚)
- [13. 健康检查接口](#13-健康检查接口)

---

## 1. 部署完成后你将得到什么

| 组件 | 说明 |
|------|------|
| **Web 控制台** | 浏览器访问，提供完整 UI — 设备管理、实时预览、告警中心、运维监控等 |
| **后端 API 服务** | FastAPI 驱动，提供全部业务接口（RESTful + WebSocket） |
| **数据库** | PostgreSQL / MySQL / SQLite，存储设备、用户、配置与日志 |
| **流媒体服务** | ZLMediaKit，负责视频收流、转协议（RTSP/RTMP/HLS/FLV）与分发 |

<p align="center">
  <img src="images/1.png" width="90%" alt="部署成功后的工作台" />
</p>

<p align="center"><em>部署成功后打开浏览器即可看到的工作台界面</em></p>

---

## 2. 系统要求

| 资源 | 最低配置 | 推荐配置 |
|------|----------|----------|
| CPU | 2 核 | 4 核及以上 |
| 内存 | 4 GB | 8 GB 及以上（推荐 16 GB） |
| 磁盘 | 20 GB | 至少 50 GB，可按录像存储需求扩容 |
| 操作系统 | Linux（Ubuntu 20.04+ / CentOS 7+）/ Windows Server 2019+ | Linux 优先（Ubuntu 22.04 LTS） |

**软件依赖**：

| 软件 | 最低版本 | 推荐版本 | 备注 |
|------|----------|----------|------|
| Python | 3.10 | 3.10+ | 手工部署时需要 |
| Node.js | 16 | 18+ | 手工部署时需要 |
| Docker | 20.10 | 最新版 | Docker 部署时需要 |
| Docker Compose | 2.0 | 最新版 | Docker 部署时需要 |
| PostgreSQL | 12 | 14+ | 推荐生产环境使用 |
| Redis | 5 | 6+ | 可选，用于缓存与会话共享 |

---

## 3. 端口规划

| 端口 | 协议 | 用途 | 是否必须 |
|------|------|------|----------|
| 80 / 443 | TCP | Web 前端访问（Nginx） | ✅ |
| 8000 | TCP | 后端 API 服务 | ✅ |
| 5060 | UDP / TCP | SIP 信令端口 | ✅ |
| 5061 | TCP | SIP TLS 信令端口 | 可选 |
| 30000–39000 | UDP | RTP 收流端口段 | ✅ |
| 8880 | TCP | ZLM HTTP API / FLV 播放 | ✅ |
| 554 | TCP | ZLM RTSP 端口 | 推荐 |
| 1935 | TCP | ZLM RTMP 端口 | 可选 |
| 8083 | TCP | ZLM HLS 端口 | 可选 |

> **⚠️ 防火墙注意**：必须放行 **UDP 30000–39000** 端口段（RTP 收流），否则设备无法推流，视频将黑屏。

---

## 4. Docker 部署（推荐）

Docker 部署是最简单、成功率最高的方式，适合大部分用户。

### 4.1 克隆代码

```bash
cd /opt
git clone <你的仓库地址> PyGBSentry
cd PyGBSentry/editions/open-source
```

### 4.2 创建环境变量文件

```bash
cd backend
cp .env.example .env
```

编辑 `.env` 文件，**必须修改**以下配置项：

```env
# 安全密钥（生产环境必填，空值将拒绝启动）
SECRET_KEY=使用随机字符串替换，例如：openssl rand -hex 32
MEDIA_SERVER_SECRET=使用随机字符串替换
SIP_DEFAULT_PASSWORD=设置设备接入密码

# Docker 部署时必须设为容器网络可达的 IP（如宿主机 IP）
BACKEND_PUBLIC_HOST=192.168.1.100

# 数据库密码
POSTGRES_PASSWORD=你的强密码

# Redis 密码
REDIS_PASSWORD=你的强密码
```

**生产环境建议额外配置**：

| 配置项 | 建议值 | 说明 |
|--------|--------|------|
| `APP_ENV` | `prod` | 生产环境标识 |
| `ENABLE_OPENAPI_DOCS` | `false` | 关闭 API 文档公开访问 |
| `ENABLE_SECURITY_HEADERS` | `true` | 启用安全响应头 |
| `ENABLE_CSP` | `true` | 启用内容安全策略 |

### 4.3 启动服务

```bash
# 回到 editions/open-source 目录
cd ..

# 启动所有服务（后台运行）
docker compose --profile prod up -d
```

### 4.4 验证部署

**查看服务状态**：

```bash
# 检查所有容器是否正常运行
docker compose --profile prod ps
```

预期输出（所有服务状态为 `Up`）：

```
NAME                STATUS              PORTS
pygbsentry-backend  Up (healthy)        0.0.0.0:8000->8000/tcp, 0.0.0.0:5060->5060/tcp, ...
pygbsentry-frontend Up (healthy)        0.0.0.0:80->80/tcp
pygbsentry-db       Up (healthy)        5432/tcp
pygbsentry-redis    Up (healthy)        6379/tcp
```

**查看后端日志**：

```bash
# 实时查看后端日志（无持续报错即为正常）
docker compose --profile prod logs -f backend
```

**页面访问验证**：

| 检查项 | 地址 | 预期结果 |
|--------|------|----------|
| Web 控制台 | `http://<服务器IP>/` | 打开登录页 |
| API 健康检查 | `http://<服务器IP>:8000/api/v1/health/` | 返回 `{"status":"ok"}` |
| 安装向导 | `http://<服务器IP>/#/setup` | 显示系统检测项 |

**默认管理员账号**：

- 用户名：`admin`
- 密码：`Aa332211`

> ⚠️ 首次登录后请立即修改密码，建议进入「账号安全」开启 2FA / TOTP。

---

## 5. 手工部署 — Linux

### 5.1 安装系统依赖

**Ubuntu / Debian**：

```bash
sudo apt update
sudo apt install -y python3-pip python3-venv postgresql redis-server libgl1-mesa-glx ffmpeg
```

**CentOS / RHEL**：

```bash
sudo yum install -y python3-pip postgresql redis-server
```

### 5.2 配置 PostgreSQL

```bash
# 切换到 postgres 用户
sudo -u postgres psql

# 执行以下 SQL
CREATE DATABASE pygbsentry;
CREATE USER pygbsentry WITH PASSWORD '你的强密码';
GRANT ALL PRIVILEGES ON DATABASE pygbsentry TO pygbsentry;
\q
```

### 5.3 后端部署

```bash
cd /opt/PyGBSentry/editions/open-source/backend

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 修改数据库连接等配置
# 至少修改：DATABASE_TYPE, DATABASE_HOST, DATABASE_PORT, DATABASE_NAME, DATABASE_USER, DATABASE_PASSWORD
#           SECRET_KEY, MEDIA_SERVER_SECRET, SIP_DEFAULT_PASSWORD

# 初始化数据库（创建表结构和管理员账号）
python app/initial_data.py

# 启动后端服务
python -m app.main
```

**生产环境建议使用 systemd 管理**：

```bash
# 复制 service 文件
sudo cp deploy/pygbsentry.service /etc/systemd/system/

# 按需修改 WorkingDirectory、ExecStart 等路径
sudo systemctl daemon-reload
sudo systemctl enable pygbsentry
sudo systemctl start pygbsentry

# 查看状态
sudo systemctl status pygbsentry
```

### 5.4 前端构建

```bash
cd /opt/PyGBSentry/editions/open-source/frontend

# 安装依赖
npm install

# 编译生产版本
npm run build
```

构建完成后，将生成的 `dist` 目录交给 Nginx 托管（见第 8 章）。

---

## 6. 手工部署 — Windows

### 6.1 安装依赖

- **Python**：3.10+（从 [python.org](https://www.python.org) 下载安装，勾选 "Add to PATH"）
- **Node.js**：18+（从 [nodejs.org](https://nodejs.org) 下载安装）
- **PostgreSQL**：从 [postgresql.org](https://www.postgresql.org) 下载 Windows 版并安装
- **Redis**：可选，Windows 版可从 [GitHub](https://github.com/tporadowski/redis/releases) 获取

### 6.2 后端部署

```powershell
# 打开 PowerShell，进入后端目录
cd editions\open-source\backend

# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境
.\.venv\Scripts\Activate.ps1

# 若提示执行策略限制，先执行：
# Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
Copy-Item .env.example .env
# 用记事本或其他编辑器修改 .env 配置
# notepad .env

# 初始化数据库
python app\initial_data.py

# 启动后端
python -m app.main
```

### 6.3 前端构建

```powershell
cd editions\open-source\frontend

# 安装依赖
npm install

# 编译生产版本
npm run build
```

构建完成后，将 `dist` 目录部署到 IIS 或 Nginx for Windows。

> **提示**：Windows 部署主要用于开发测试，生产环境推荐使用 Linux + Docker。

---

## 7. 数据库配置

### 7.1 选型建议

| 场景 | 推荐数据库 | 说明 |
|------|-----------|------|
| 体验 / 测试 | SQLite | 零配置，开箱即用 |
| 正式生产 | PostgreSQL | 性能最优，功能最全 |
| 已有 MySQL 基础 | MySQL | 兼容可用 |

### 7.2 PostgreSQL 配置示例

```env
DATABASE_TYPE=postgresql
DATABASE_HOST=127.0.0.1
DATABASE_PORT=5432
DATABASE_NAME=pygbsentry
DATABASE_USER=postgres
DATABASE_PASSWORD=你的强密码
```

### 7.3 MySQL 配置示例

```env
DATABASE_TYPE=mysql
DATABASE_HOST=127.0.0.1
DATABASE_PORT=3306
DATABASE_NAME=pygbsentry
DATABASE_USER=root
DATABASE_PASSWORD=你的强密码
```

### 7.4 SQLite 配置示例

```env
DATABASE_TYPE=sqlite
DATABASE_SQLITE_PATH=./pygbsentry.db
SQLITE_CONNECT_TIMEOUT_SECONDS=15
```

> **注意**：SQLite 仅适用于体验和单机测试，不支持并发写入，生产环境请使用 PostgreSQL。

---

## 8. Nginx 反向代理

生产环境建议浏览器仅访问单一域名，将 `/api` 请求转发给后端。

### 8.1 完整配置示例

```nginx
server {
    listen 80;
    server_name your.domain.com;

    # 前端静态文件
    root /var/www/pygbsentry/dist;
    index index.html;

    # 前端路由（Vue Router history 模式）
    location / {
        try_files $uri $uri/ /index.html;
    }

    # 后端 API 反向代理（含 WebSocket 支持）
    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket 升级（关键配置，实时告警、运维日志、语音对讲依赖此项）
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600;
    }
}
```

### 8.2 HTTPS 配置（推荐）

```nginx
server {
    listen 443 ssl http2;
    server_name your.domain.com;

    ssl_certificate     /etc/nginx/ssl/your.domain.com.pem;
    ssl_certificate_key /etc/nginx/ssl/your.domain.com.key;

    # ... 其余配置同上 ...
}

# HTTP 自动跳转 HTTPS
server {
    listen 80;
    server_name your.domain.com;
    return 301 https://$host$request_uri;
}
```

> **⚠️ WebSocket 必须开启**：实时报警、运维日志、语音对讲等功能依赖 WebSocket 升级。如果未配置 `Upgrade` 和 `Connection` 头，告警将不会实时更新。

---

## 9. ZLMediaKit 重点配置

上线前必须逐项检查以下配置：

| 序号 | 检查项 | 说明 |
|------|--------|------|
| 1 | 播放端口可达 | 确认 8880（HTTP/FLV）、554（RTSP）、1935（RTMP）端口可从客户端访问 |
| 2 | RTP 端口段已放通 | 防火墙放行 UDP 30000–39000，且范围与 `.env` 中 `MEDIA_SERVER_RTP_PROXY_PORT_RANGE` 一致 |
| 3 | Hook 地址可达 | ZLM 能访问后端的 Hook 回调地址（`BACKEND_PUBLIC_HOST` 配置正确） |
| 4 | Secret 一致 | `.env` 中 `MEDIA_SERVER_SECRET` 与 ZLM `config.ini` 中 `[api] secret` 一致 |
| 5 | NAT 场景 | 公网部署时优先使用 `TCP_PASSIVE` 模式（`MEDIA_SERVER_RTP_STREAM_MODE=TCP_PASSIVE`） |
| 6 | ZLM 日志级别 | 生产环境建议设为 `2`（Info），避免日志过多影响性能 |

> 详细说明见：[MEDIA_SERVER.md](./MEDIA_SERVER.md)

---

## 10. 验收清单

部署完成后，按以下顺序逐项验证：

| 步骤 | 验证方法 | 预期结果 |
|------|----------|----------|
| 1 | 浏览器打开 `http://<服务器IP>/` | 能打开登录页 |
| 2 | 使用 `admin` / `Aa332211` 登录 | 正常进入系统 |
| 3 | 添加一台 GB28181 设备 | 设备显示在线状态 |
| 4 | 点击通道进行实时预览 | 视频正常播放 |
| 5 | 查看历史录像回放 | 回放正常播放 |
| 6 | 触发设备告警 | 告警可接收并展示 |
| 7 | 访问 `GET /api/v1/ops/db-check` | 返回数据库连接正常 |
| 8 | 访问 `GET /api/v1/ops/diagnose-report` | 能返回诊断信息 |
| 9 | 查看工作台 / 可视化指挥 / 电视墙 | 右上角显示「报警流：已连接」 |

---

## 11. 常见报错与处理

### 问题 1：页面能打开，但接口报 404

- **原因**：Nginx 反向代理未配置正确
- **处理**：检查 Nginx `/api` 代理地址是否指向 `http://127.0.0.1:8000/`（注意末尾斜杠）

### 问题 2：登录后看不到视频（黑屏）

- **原因**：多见于端口或 RTP 段未放开
- **处理**：
  1. 检查防火墙是否放行 UDP 30000–39000
  2. 检查 ZLM 端口（8880、554、1935）是否可达
  3. NAT 环境下尝试切换为 `TCP_PASSIVE` 模式

### 问题 3：页面正常，但告警不实时更新

- **原因**：Nginx 未开启 WebSocket 升级
- **处理**：
  1. 检查工作台右上角状态：「报警流：已连接 / 重连中 / 未连接」
  2. 确认 Nginx 配置中包含 `proxy_set_header Upgrade` 和 `proxy_set_header Connection "upgrade"`（见第 8 章）
  3. 运维中心的实时日志也会显示 WebSocket 连接状态

### 问题 4：启动时报数据库连接失败

- **原因**：数据库地址、账号、密码错误，或数据库服务未启动
- **处理**：
  1. 先在本机验证数据库连通性：`psql -h 127.0.0.1 -U postgres -d pygbsentry`
  2. 检查 `.env` 中 `DATABASE_*` 配置是否正确
  3. 确认数据库服务已启动：`sudo systemctl status postgresql`

### 问题 5：访问后自动跳转到 /setup

- **原因**：系统检测到数据库或 ZLM 连通性异常，或尚未点击「完成配置」
- **处理**：
  1. 打开 `/#/setup` 查看检测项提示
  2. 逐项修复红色标记的异常
  3. 全部通过后点击「完成配置，进入系统」

---

## 12. 升级、备份与回滚

### 12.1 升级前

```bash
# 1. 备份数据库
pg_dump -U postgres pygbsentry > pygbsentry_backup_$(date +%Y%m%d%H%M).sql

# 2. 备份环境变量和关键目录
cp backend/.env backend/.env.backup.$(date +%Y%m%d%H%M)

# 3. 记录当前版本号
git log --oneline -1
```

### 12.2 Docker 升级

```bash
cd /opt/PyGBSentry/editions/open-source

# 拉取最新代码
git pull origin main

# 重新构建并启动
docker compose --profile prod up -d --build
```

### 12.3 手工升级

```bash
cd /opt/PyGBSentry/editions/open-source

# 拉取最新代码
git pull origin main

# 后端：更新依赖并重启
cd backend
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart pygbsentry

# 前端：重新构建
cd ../frontend
npm install
npm run build
```

### 12.4 升级后验证

- 先验证登录、预览、回放、告警功能
- 确认正常后再进行业务切换

### 12.5 回滚

```bash
# Docker 回滚
docker compose --profile prod down
# 使用上一版本镜像或代码重新启动

# 手工回滚
git checkout <上一版本commit>
# 恢复数据库备份
psql -U postgres pygbsentry < pygbsentry_backup_XXXXXXXXXX.sql
```

---

## 13. 健康检查接口

部署后建议调用以下接口确认系统状态，均可用于监控告警和负载均衡探针：

| 接口 | 方法 | 说明 | 鉴权 |
|------|------|------|------|
| `/api/v1/health/` | GET | 综合健康检查（DB + Redis），正常返回 200，异常返回 503 | 无需 |
| `/api/v1/health/readiness` | GET | 就绪探针，DB + Redis 均正常才返回 200 | 无需 |
| `/api/v1/health/liveness` | GET | 存活探针，进程存活即返回 200（轻量级，不检查外部依赖） | 无需 |
| `/api/v1/ops/db-check` | GET | 数据库连通性检查 | 需登录 |
| `/api/v1/ops/diagnose-report` | GET | 完整诊断报告（含 DB、Redis、ZLM、SIP 状态） | 需登录 |
| `/api/v1/ops/status` | GET | 系统运行状态概览 | 需登录 |
| `/api/v1/ops/stream-diagnose` | GET | 流媒体诊断（5 步串行探测） | 需登录 |

**快速巡检示例**：

```bash
# 综合健康检查（无需登录）
curl http://localhost:8000/api/v1/health/

# 存活探针（K8s livenessProbe）
curl http://localhost:8000/api/v1/health/liveness

# 就绪探针（K8s readinessProbe）
curl http://localhost:8000/api/v1/health/readiness

# 数据库连通性检查（需登录后携带 Token）
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/v1/ops/db-check

# 完整诊断报告（需登录后携带 Token）
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/v1/ops/diagnose-report
```

**Docker 健康检查配置参考**：

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health/"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 30s
```

---

## 相关文档

| 文档 | 说明 |
|------|------|
| [INSTALL.md](./INSTALL.md) | 快速安装指南 |
| [MEDIA_SERVER.md](./MEDIA_SERVER.md) | 流媒体专项配置 |
| [DEVELOPER.md](./DEVELOPER.md) | 开发指南 |
| [PRODUCT_OSS.md](./PRODUCT_OSS.md) | 产品能力说明 |
| [PLUGIN_SPEC.md](./PLUGIN_SPEC.md) | 插件规范 |
