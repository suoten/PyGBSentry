# PyGBSentry 快速安装指南

本文档提供快速上手指南，帮助你在最短时间内启动系统。详细部署请参考 [INSTALL_DEPLOY.md](./INSTALL_DEPLOY.md)。

---

## 环境要求

| 软件 | 最低版本 | 推荐版本 |
|------|---------|---------|
| Python | 3.10 | 3.10+ |
| Node.js | 16 | 18+ |
| Docker | 20.10 | 最新版 |
| Docker Compose | 2.0 | 最新版 |

---

## 方式一：Docker 一键部署（推荐）

### 步骤 1：获取代码

```bash
git clone <你的仓库地址>
cd PyGBSentry/editions/open-source
```

### 步骤 2：配置环境变量

```bash
cd backend
cp .env.example .env
```

编辑 `.env` 文件，至少修改以下项：

```env
SECRET_KEY=你的随机密钥
MEDIA_SERVER_SECRET=你的流媒体密钥
# 数据库配置（根据需要修改）
```

### 步骤 3：启动服务

```bash
cd ..
docker compose --profile prod up -d
```

### 步骤 4：验证

| 检查项 | 地址 | 预期结果 |
|--------|------|----------|
| Web 控制台 | `http://<服务器IP>/` | 打开登录页 |
| 登录测试 | - | admin / Aa332211 |
| API 健康 | `http://<服务器IP>:8000/api/v1/ops/db-check` | `{"status": "ok"}` |

---

## 方式二：宝塔面板部署

### 步骤 1：安装环境

在宝塔「软件商店」安装：
- PostgreSQL（或 MySQL）
- Redis
- Python 管理器
- Nginx

### 步骤 2：创建数据库

在宝塔数据库管理中创建 `pygbsentry` 数据库。

### 步骤 3：部署后端

1. 将 `backend` 目录上传至 `/www/wwwroot/pygbsentry_backend`
2. 在 Python 管理器中添加项目：
   - 路径：`/www/wwwroot/pygbsentry_backend`
   - 启动文件：`app/main.py`
   - 端口：`8000`
3. 修改 `.env` 配置数据库连接

### 步骤 4：部署前端

```bash
cd frontend
npm install
npm run build
```

将 `dist` 目录上传至 `/www/wwwroot/pygbsentry_web`，在宝塔添加纯静态站点。

### 步骤 5：配置 Nginx 反代

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

### 步骤 1：安装依赖

```bash
sudo apt update
sudo apt install -y python3-pip python3-venv postgresql redis-server libgl1-mesa-glx
```

### 步骤 2：后端部署

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 修改 .env 配置
python app/initial_data.py
python -m app.main
```

### 步骤 3：前端部署

```bash
cd frontend
npm install
npm run build
# 将 dist 目录交给 Nginx 托管
```

---

## 方式四：Windows 开发测试

### 步骤 1：安装依赖

- Python 3.10+（从 python.org 下载）
- Node.js 18+
- Docker Desktop（用于运行 PostgreSQL/Redis）

### 步骤 2：后端部署

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
python app\initial_data.py
python -m app.main
```

### 步骤 3：前端部署

```powershell
cd frontend
npm install
npm run dev
```

---

## 常见问题速查

| 问题 | 快速解决方案 |
|------|-------------|
| 端口冲突 | 确保 5060、8000、80、1935、554 未被占用 |
| 视频黑屏 | 检查防火墙，开放 UDP 10000-40000 端口段 |
| 数据库连接失败 | 检查 `.env` 数据库配置，确认服务已启动 |
| 页面跳转到 /setup | 打开 `/#/setup` 查看检测项提示，按提示修复 |

---

## 下一步

- **详细部署**：[INSTALL_DEPLOY.md](./INSTALL_DEPLOY.md)
- **流媒体配置**：[MEDIA_SERVER.md](./MEDIA_SERVER.md)
- **产品能力**：[PRODUCT_OSS.md](./PRODUCT_OSS.md)
