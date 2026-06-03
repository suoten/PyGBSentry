# 开源版安装部署指南（超详细）

[中文](#) | [English](#english-version)

> **适用目录**：`editions/open-source`  
> **目标读者**：首次接触服务器部署的用户，无需编程经验也可按步骤完成。

---

## 快速导读

1. **只要会复制命令，就能先把系统跑起来。**
2. **建议优先选择 Docker 路线，成功率最高。**
3. **每一步都附带验证方法，确认结果后再继续下一步。**

> **重要提示**：开源版提供「安装向导」页面（`/#/setup` 或 `/setup`）。  
> 首次部署时，若数据库或流媒体服务（ZLM）未连通，或未点击「完成配置」，系统会引导你先修复基础连通性问题。可随时通过浏览器访问 `/#/setup` 查看检测结果。

---

## 1. 部署完成后你将得到什么

| 组件 | 说明 |
|------|------|
| Web 控制台 | 浏览器访问，提供完整 UI |
| 后端 API 服务 | FastAPI，提供全部业务接口 |
| 数据库 | PostgreSQL / MySQL / SQLite，存储设备、用户、配置与日志 |
| 流媒体服务 | ZLMediaKit，负责视频收流、转协议与分发 |

---

## 2. 部署方式选择

### 方式 A：Docker（推荐，最简单）

- **适用场景**：大部分用户，尤其是首次部署
- **优点**：依赖少、回滚方便、出问题更易排查
- **补充说明**：Windows / macOS 建议使用 Docker Desktop；Linux 直接安装 Docker Engine

### 方式 B：手工部署（进阶）

- **适用场景**：内网受限、需要自定义进程管理或打包策略

---

## 3. 部署前准备

### 3.1 服务器建议配置

| 资源 | 建议配置 |
|------|----------|
| CPU | 4 核及以上 |
| 内存 | 8GB 及以上（推荐 16GB） |
| 磁盘 | 至少 50GB，可按录像存储需求扩容 |
| 操作系统 | Linux 优先（Ubuntu / CentOS 均可），Windows 也可用于测试 |

### 3.2 网络与端口规划

至少预留以下端口：

| 端口 | 用途 |
|------|------|
| 80 / 443 | Web 前端访问 |
| 8000 | 后端 API（若使用反向代理可不直接暴露） |
| 5060 | SIP 信令（可自定义） |
| 30000–39000 | RTP 收流端口段（UDP） |
| ZLM 相关端口 | 按配置启用（HLS：8083、RTSP：554、RTMP：1935 等） |

> **防火墙注意**：必须放行 UDP 10000–40000 端口段（RTP 收流），否则设备无法推流。

### 3.3 获取代码

```bash
cd /opt
git clone <你的仓库地址> PyGBSentry
cd PyGBSentry
```

---

## 4. Docker 部署（推荐）

### 4.1 进入目录

```bash
cd editions/open-source
```

### 4.2 准备环境变量

```bash
cd backend
cp .env.example .env
```

**必须修改的配置项**：

| 配置项 | 说明 |
|--------|------|
| `SECRET_KEY` | 应用密钥，建议使用随机字符串 |
| `MEDIA_SERVER_SECRET` | 流媒体服务密钥 |
| 数据库相关配置 | 根据所选数据库修改密码等 |

**生产环境建议配置**：

| 配置项 | 建议值 |
|--------|--------|
| `APP_ENV` | `prod` |
| `ENABLE_OPENAPI_DOCS` | `false` |
| `ALLOW_PUBLIC_REGISTRATION` | `false` |

### 4.3 启动服务

```bash
# 回到 editions/open-source 目录
cd ..

# 启动生产环境服务
docker compose --profile prod up -d
```

### 4.4 验证启动状态

```bash
# 查看服务状态
docker compose --profile prod ps

# 查看后端日志（无持续报错即为正常）
docker compose --profile prod logs -f backend
```

### 4.5 页面访问验证

| 页面 | 访问地址 |
|------|----------|
| 控制台 | `http://<服务器IP>/` |
| API | `http://<服务器IP>:8000/` |
| 安装向导 | `http://<服务器IP>/#/setup`（或 `/setup`） |

**默认管理员账号**：

- 用户名：`admin`
- 密码：`Aa332211`

> 首次登录后请立即修改密码，建议进入「账号安全」开启 2FA / TOTP。

---

## 5. 手工部署：Linux

### 5.1 安装系统依赖

```bash
# Ubuntu / Debian
sudo apt update
sudo apt install -y python3-pip python3-venv postgresql redis-server libgl1-mesa-glx

# CentOS / RHEL
sudo yum install -y python3-pip postgresql redis-server
```

### 5.2 配置数据库

```bash
# 创建 PostgreSQL 数据库
sudo -u postgres psql
CREATE DATABASE pygbsentry;
CREATE USER your_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE pygbsentry TO your_user;
\q
```

### 5.3 后端部署

```bash
cd editions/open-source/backend

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 修改数据库连接等配置

# 初始化数据库（创建表结构和管理员账号）
python app/initial_data.py

# 启动后端服务
python -m app.main
```

### 5.4 前端部署

```bash
cd editions/open-source/frontend

# 安装依赖
npm install

# 编译
npm run build
```

将生成的 `dist` 目录交给 Nginx 托管。

---

## 6. 手工部署：Windows

### 6.1 安装依赖

- Python 3.10+（建议从 [python.org](https://www.python.org) 官网下载）
- Node.js 18+
- PostgreSQL（可从 [postgresql.org](https://www.postgresql.org) 下载 Windows 版）
- Redis（可选，Windows 版可从 GitHub 获取）

### 6.2 后端部署

```powershell
# 打开 PowerShell
cd editions\open-source\backend

# 创建虚拟环境
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
Copy-Item .env.example .env
# 编辑 .env 修改配置

# 初始化数据库
python app\initial_data.py

# 启动后端
python -m app.main
```

> 若提示执行策略限制，执行：`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`

### 6.3 前端部署

```powershell
cd editions\open-source\frontend
npm install
npm run build
```

---

## 7. 数据库配置

### 7.1 选型建议

| 场景 | 推荐数据库 |
|------|-----------|
| 体验 / 测试 | SQLite |
| 正式生产 | PostgreSQL（推荐） |
| 已有 MySQL 基础 | MySQL |

### 7.2 配置示例

**PostgreSQL**：

```env
DATABASE_TYPE=postgresql
DATABASE_HOST=127.0.0.1
DATABASE_PORT=5432
DATABASE_NAME=pygbsentry
DATABASE_USER=postgres
DATABASE_PASSWORD=你的强密码
```

**MySQL**：

```env
DATABASE_TYPE=mysql
DATABASE_HOST=127.0.0.1
DATABASE_PORT=3306
DATABASE_NAME=pygbsentry
DATABASE_USER=root
DATABASE_PASSWORD=你的强密码
```

**SQLite**：

```env
DATABASE_TYPE=sqlite
DATABASE_SQLITE_PATH=./pygbsentry.db
```

---

## 8. Nginx 反向代理（生产环境推荐）

建议浏览器仅访问单一域名，将 `/api` 请求转发给后端。

```nginx
server {
  listen 80;
  server_name your.domain.com;

  root /var/www/pygbsentry/dist;
  index index.html;

  location / {
    try_files $uri $uri/ /index.html;
  }

  location /api/ {
    proxy_pass http://127.0.0.1:8000/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }
}
```

### WebSocket 支持（必须开启）

实时报警、运维日志、语音对讲等功能依赖 WebSocket 升级：

```nginx
location /api/ {
  proxy_pass http://127.0.0.1:8000/;
  proxy_set_header Host $host;
  proxy_set_header X-Real-IP $remote_addr;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  proxy_set_header X-Forwarded-Proto $scheme;

  # WebSocket 升级（关键配置）
  proxy_http_version 1.1;
  proxy_set_header Upgrade $http_upgrade;
  proxy_set_header Connection "upgrade";
  proxy_read_timeout 3600;
}
```

---

## 9. ZLMediaKit（流媒体）重点配置

上线前必查项：

1. 播放端口可达
2. RTP 端口段已放通
3. Hook 地址可达（ZLM 能访问后端）
4. NAT 场景优先使用 `TCP_PASSIVE` 模式

详细说明见：[MEDIA_SERVER.md](./MEDIA_SERVER.md)

---

## 10. 验收清单（按顺序检查）

| 步骤 | 验证方法 |
|------|----------|
| 1 | 能打开登录页 |
| 2 | `admin` 能正常登录 |
| 3 | 添加设备后能看到在线状态 |
| 4 | 实时预览可正常播放 |
| 5 | 回放可正常播放 |
| 6 | 告警可接收并展示 |
| 7 | `GET /api/v1/ops/db-check` 返回连接正常 |
| 8 | `GET /api/v1/ops/diagnose-report` 能返回诊断信息 |
| 9 | 工作台 / 可视化指挥 / 电视墙显示「报警流：已连接」 |

---

## 11. 常见报错与处理

### 问题 1：页面能打开，但接口报 404

- **原因**：Nginx 反向代理未配置正确
- **处理**：检查 Nginx `/api` 代理地址是否准确

### 问题 2：登录后看不到视频

- **原因**：多见于端口或 RTP 段未放开
- **处理**：检查 ZLM 端口、防火墙、NAT 地址配置

### 问题 2.1：页面正常，但报警不更新

- **原因**：Nginx 未开启 WebSocket 升级
- **处理**：
  - 检查「工作台 / 可视化指挥 / 电视墙」右上角状态："报警流：已连接 / 重连中 / 未连接"
  - 运维中心的实时日志也会显示连接状态
  - 确认 Nginx 配置中包含 WebSocket 升级相关配置（见第 8 章）

### 问题 3：启动时报数据库连接失败

- **原因**：数据库地址、账号、密码错误，或服务未启动
- **处理**：先在本机连通数据库，再检查 `.env` 配置

### 问题 4：访问后自动跳转到 /setup

- **原因**：系统检测到数据库或 ZLM 连通性异常，或尚未点击「完成配置」
- **处理**：打开 `/#/setup` 查看检测项提示；修复后点击「完成配置，进入系统」

---

## 12. 升级、备份与回滚

### 升级前

- 备份数据库
- 备份 `.env` 和关键目录
- 记录当前版本号

### 升级后

- 先验证登录、预览、回放、告警功能
- 确认正常后再进行业务切换

### 回滚

- 使用上一版本镜像 / 代码
- 恢复升级前的数据库备份

---

## 13. 一键巡检接口

部署后建议调用以下接口确认系统状态：

```bash
curl http://localhost:8000/api/v1/ops/db-check
curl http://localhost:8000/api/v1/ops/diagnose
```

---

## 14. 给非技术同学的建议

- 每次只改一个配置项，改完就验证
- 保留每次改动记录（时间、改了什么、结果如何）
- 遇到问题先看日志，不要盲目重装
- 先在本地跑通，再上公网

---

## 15. 相关文档

| 文档 | 说明 |
|------|------|
| [PRODUCT_OSS.md](./PRODUCT_OSS.md) | 产品说明 |
| [DEVELOPER.md](./DEVELOPER.md) | 开发指南 |
| [MEDIA_SERVER.md](./MEDIA_SERVER.md) | 流媒体专项 |
| [PLUGIN_SPEC.md](./PLUGIN_SPEC.md) | 插件规范 |

---

# English Version

# Open Source Edition Installation & Deployment Guide (Ultra-Detailed)

> **Applicable Directory**: `editions/open-source`  
> **Target Audience**: Users deploying a server for the first time; no programming experience required.

---

## Quick Start

1. **If you can copy and paste commands, you can get the system running.**
2. **Docker is the recommended route and has the highest success rate.**
3. **Every step includes a verification method; confirm the result before moving on.**

> **Important Notice**: The open-source edition provides a "Setup Wizard" page (`/#/setup` or `/setup`).  
> During first deployment, if the database or streaming server (ZLM) is unreachable, or if you have not clicked "Finish Configuration", the system will guide you to fix basic connectivity issues first. You can visit `/#/setup` in your browser at any time to view the detection results.

---

## 1. What You Will Get After Deployment

| Component | Description |
|-----------|-------------|
| Web Console | Browser-based access with full UI |
| Backend API Service | FastAPI, provides all business APIs |
| Database | PostgreSQL / MySQL / SQLite, stores devices, users, configs, and logs |
| Streaming Server | ZLMediaKit, handles video ingestion, protocol conversion, and distribution |

---

## 2. Choose a Deployment Method

### Method A: Docker (Recommended, Easiest)

- **Best For**: Most users, especially first-time deployments
- **Advantages**: Fewer dependencies, easy rollback, simpler troubleshooting
- **Note**: On Windows / macOS, use Docker Desktop; on Linux, install Docker Engine directly

### Method B: Manual Deployment (Advanced)

- **Best For**: Restricted intranets, custom process management, or custom packaging strategies

---

## 3. Pre-Deployment Preparation

### 3.1 Recommended Server Specifications

| Resource | Recommendation |
|----------|----------------|
| CPU | 4 cores or more |
| Memory | 8GB or more (16GB recommended) |
| Disk | At least 50GB; expand according to recording storage needs |
| OS | Linux preferred (Ubuntu / CentOS both supported); Windows also acceptable for testing |

### 3.2 Network and Port Planning

Reserve at least the following ports:

| Port | Purpose |
|------|---------|
| 80 / 443 | Web frontend access |
| 8000 | Backend API (can be hidden if using a reverse proxy) |
| 5060 | SIP signaling (customizable) |
| 30000–39000 | RTP ingress port range (UDP) |
| ZLM ports | Enabled as needed (HLS: 8083, RTSP: 554, RTMP: 1935, etc.) |

> **Firewall Note**: You **must** allow UDP port range 10000–40000 (RTP ingress); otherwise devices cannot push streams.

### 3.3 Get the Code

```bash
cd /opt
git clone <your-repository-url> PyGBSentry
cd PyGBSentry
```

---

## 4. Docker Deployment (Recommended)

### 4.1 Enter the Directory

```bash
cd editions/open-source
```

### 4.2 Prepare Environment Variables

```bash
cd backend
cp .env.example .env
```

**Required Configuration Changes**:

| Config Item | Description |
|-------------|-------------|
| `SECRET_KEY` | Application secret; use a random string |
| `MEDIA_SERVER_SECRET` | Streaming server secret |
| Database-related configs | Update password, etc., according to your chosen database |

**Production Environment Recommendations**:

| Config Item | Recommended Value |
|-------------|-------------------|
| `APP_ENV` | `prod` |
| `ENABLE_OPENAPI_DOCS` | `false` |
| `ALLOW_PUBLIC_REGISTRATION` | `false` |

### 4.3 Start Services

```bash
# Return to editions/open-source directory
cd ..

# Start production services
docker compose --profile prod up -d
```

### 4.4 Verify Startup Status

```bash
# View service status
docker compose --profile prod ps

# View backend logs (no continuous errors means OK)
docker compose --profile prod logs -f backend
```

### 4.5 Verify via Web Pages

| Page | URL |
|------|-----|
| Console | `http://<server-ip>/` |
| API | `http://<server-ip>:8000/` |
| Setup Wizard | `http://<server-ip>/#/setup` (or `/setup`) |

**Default Admin Account**:

- Username: `admin`
- Password: `Aa332211`

> Change the password immediately after first login. It is recommended to enable 2FA / TOTP in "Account Security".

---

## 5. Manual Deployment: Linux

### 5.1 Install System Dependencies

```bash
# Ubuntu / Debian
sudo apt update
sudo apt install -y python3-pip python3-venv postgresql redis-server libgl1-mesa-glx

# CentOS / RHEL
sudo yum install -y python3-pip postgresql redis-server
```

### 5.2 Configure the Database

```bash
# Create PostgreSQL database
sudo -u postgres psql
CREATE DATABASE pygbsentry;
CREATE USER your_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE pygbsentry TO your_user;
\q
```

### 5.3 Backend Deployment

```bash
cd editions/open-source/backend

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env to update database connection, etc.

# Initialize database (create schema and admin account)
python app/initial_data.py

# Start backend service
python -m app.main
```

### 5.4 Frontend Deployment

```bash
cd editions/open-source/frontend

# Install dependencies
npm install

# Build
npm run build
```

Serve the generated `dist` directory with Nginx.

---

## 6. Manual Deployment: Windows

### 6.1 Install Dependencies

- Python 3.10+ (download from [python.org](https://www.python.org))
- Node.js 18+
- PostgreSQL (download Windows version from [postgresql.org](https://www.postgresql.org))
- Redis (optional; Windows version available on GitHub)

### 6.2 Backend Deployment

```powershell
# Open PowerShell
cd editions\open-source\backend

# Create virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
Copy-Item .env.example .env
# Edit .env to update configuration

# Initialize database
python app\initial_data.py

# Start backend
python -m app.main
```

> If you see an execution policy restriction, run: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`

### 6.3 Frontend Deployment

```powershell
cd editions\open-source\frontend
npm install
npm run build
```

---

## 7. Database Configuration

### 7.1 Selection Guide

| Scenario | Recommended Database |
|----------|----------------------|
| Trial / Testing | SQLite |
| Production | PostgreSQL (recommended) |
| Existing MySQL infrastructure | MySQL |

### 7.2 Configuration Examples

**PostgreSQL**:

```env
DATABASE_TYPE=postgresql
DATABASE_HOST=127.0.0.1
DATABASE_PORT=5432
DATABASE_NAME=pygbsentry
DATABASE_USER=postgres
DATABASE_PASSWORD=your_strong_password
```

**MySQL**:

```env
DATABASE_TYPE=mysql
DATABASE_HOST=127.0.0.1
DATABASE_PORT=3306
DATABASE_NAME=pygbsentry
DATABASE_USER=root
DATABASE_PASSWORD=your_strong_password
```

**SQLite**:

```env
DATABASE_TYPE=sqlite
DATABASE_SQLITE_PATH=./pygbsentry.db
```

---

## 8. Nginx Reverse Proxy (Recommended for Production)

It is recommended that browsers access only a single domain, with `/api` forwarded to the backend.

```nginx
server {
  listen 80;
  server_name your.domain.com;

  root /var/www/pygbsentry/dist;
  index index.html;

  location / {
    try_files $uri $uri/ /index.html;
  }

  location /api/ {
    proxy_pass http://127.0.0.1:8000/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }
}
```

### WebSocket Support (Must Enable)

Real-time alarms, operation logs, and two-way audio depend on WebSocket upgrades:

```nginx
location /api/ {
  proxy_pass http://127.0.0.1:8000/;
  proxy_set_header Host $host;
  proxy_set_header X-Real-IP $remote_addr;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  proxy_set_header X-Forwarded-Proto $scheme;

  # WebSocket upgrade (critical config)
  proxy_http_version 1.1;
  proxy_set_header Upgrade $http_upgrade;
  proxy_set_header Connection "upgrade";
  proxy_read_timeout 3600;
}
```

---

## 9. ZLMediaKit (Streaming Server) Key Configurations

Before going live, verify:

1. Playback ports are reachable
2. RTP port range is open
3. Hook addresses are reachable (ZLM can access the backend)
4. In NAT scenarios, prefer `TCP_PASSIVE` mode

For details, see: [MEDIA_SERVER.md](./MEDIA_SERVER.md)

---

## 10. Acceptance Checklist (Check in Order)

| Step | Verification Method |
|------|---------------------|
| 1 | Login page loads |
| 2 | `admin` can log in |
| 3 | After adding a device, its online status is visible |
| 4 | Live preview plays correctly |
| 5 | Playback plays correctly |
| 6 | Alarms are received and displayed |
| 7 | `GET /api/v1/ops/db-check` returns normal connection status |
| 8 | `GET /api/v1/ops/diagnose-report` returns diagnostic information |
| 9 | Workbench / Visual Command / TV Wall shows "Alarm Stream: Connected" |

---

## 11. Common Errors and Fixes

### Issue 1: Page Loads but APIs Return 404

- **Cause**: Nginx reverse proxy is misconfigured
- **Fix**: Check whether the Nginx `/api` proxy address is correct

### Issue 2: No Video After Login

- **Cause**: Usually caused by ports or RTP range not being open
- **Fix**: Check ZLM ports, firewall rules, and NAT address configuration

### Issue 2.1: Page Normal but Alarms Not Updating

- **Cause**: Nginx WebSocket upgrade is not enabled
- **Fix**:
  - Check the top-right status on "Workbench / Visual Command / TV Wall": "Alarm Stream: Connected / Reconnecting / Not Connected"
  - Real-time logs in the Operations Center also show connection status
  - Confirm that the Nginx config includes WebSocket upgrade settings (see Chapter 8)

### Issue 3: Database Connection Failure on Startup

- **Cause**: Wrong database address, account, or password; or the service is not running
- **Fix**: First verify local database connectivity, then check `.env` configuration

### Issue 4: Automatic Redirect to /setup

- **Cause**: The system detects database or ZLM connectivity issues, or you have not clicked "Finish Configuration"
- **Fix**: Open `/#/setup` to view detection hints; after fixing, click "Finish Configuration and Enter System"

---

## 12. Upgrade, Backup, and Rollback

### Before Upgrading

- Back up the database
- Back up `.env` and key directories
- Record the current version number

### After Upgrading

- First verify login, preview, playback, and alarm functions
- Only switch business traffic after confirming normality

### Rollback

- Use the previous version image / code
- Restore the pre-upgrade database backup

---

## 13. One-Click Health Check APIs

After deployment, it is recommended to call the following APIs to confirm system status:

```bash
curl http://localhost:8000/api/v1/ops/db-check
curl http://localhost:8000/api/v1/ops/diagnose
```

---

## 14. Advice for Non-Technical Users

- Change only one configuration item at a time, then verify
- Keep a record of every change (time, what was changed, result)
- When encountering issues, check logs first; do not blindly reinstall
- Get it running locally before deploying to the public internet

---

## 15. Related Documentation

| Document | Description |
|----------|-------------|
| [PRODUCT_OSS.md](./PRODUCT_OSS.md) | Product Description |
| [DEVELOPER.md](./DEVELOPER.md) | Developer Guide |
| [MEDIA_SERVER.md](./MEDIA_SERVER.md) | Streaming Server Guide |
| [PLUGIN_SPEC.md](./PLUGIN_SPEC.md) | Plugin Specification |
