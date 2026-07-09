# 🚀 快速上手

> 几分钟内完成 PyGBSentry 部署，开始你的国标视频监控之旅！

---

## 📋 前置条件

| 工具 | 最低版本 | 说明 |
|------|---------|------|
| **Docker** | 20.10+ | [安装 Docker](https://docs.docker.com/get-docker/) |
| **Git** | 2.30+ | [安装 Git](https://git-scm.com/downloads) |

> 确保 Docker 服务已启动：`docker info`

---

## 🛠️ 三步部署

### Step 1：克隆 & 进入目录

```bash
git clone https://github.com/suoten/PyGBSentry.git
cd PyGBSentry/editions/open-source
```

### Step 2：创建 `.env` 配置文件

```bash
cat > .env << 'EOF'
POSTGRES_PASSWORD=YourStrongDbPass!
REDIS_PASSWORD=YourStrongRedisPass!
SECRET_KEY=change-me-to-32-char-random-string
MEDIA_SERVER_SECRET=zlm-secret-key
BACKEND_PUBLIC_HOST=192.168.1.100
SIP_DEFAULT_PASSWORD=your-sip-password
EOF
```

> ⚠️ **请务必修改以下内容：**
> - `BACKEND_PUBLIC_HOST` → 改为你服务器的实际 IP 或域名
> - `SECRET_KEY` → 生成一个 32 位随机字符串（如 `openssl rand -hex 16`）
> - 所有密码请使用强密码

### Step 3：启动服务

```bash
docker compose up -d
```

首次启动需拉取镜像，请耐心等待。查看启动状态：

```bash
docker compose ps
```

所有服务状态为 `healthy` 即表示就绪 ✅

---

## ✅ 验证部署

| 服务 | 地址 | 说明 |
|------|------|------|
| 前端界面 | `http://<你的IP>:8080` | 管理后台 |
| 后端 API | `http://<你的IP>:8000/api/health/` | 健康检查 |
| 流媒体服务 | `http://<你的IP>:80` | ZLMediaKit |

```bash
# 快速检查后端健康状态
curl http://localhost:8000/api/health/
```

返回 `"status": "ok"` 即表示后端正常运行。

---

## 🔑 首次登录

| 项目 | 值 |
|------|-----|
| 地址 | `http://<你的IP>:8080` |
| 用户名 | `admin` |
| 密码 | `Aa332211` |

> 🔴 **登录后请立即修改默认密码！** 进入「系统设置 → 用户管理」修改 admin 密码。

![仪表盘](images/1.png)

---

## 📹 添加第一台设备

1. 登录管理后台，进入 **「设备管理」**
2. 点击 **「新增设备」**
3. 填写设备信息：
   - **设备编号**：国标设备 ID（20 位编码）
   - **设备名称**：自定义名称
   - **SIP 服务器**：选择默认服务器
4. 点击 **「保存」**
5. 设备上线后状态变为 🟢 在线

---

## 🎬 播放第一路视频

1. 在设备列表中找到已上线的设备
2. 点击设备进入 **「通道列表」**
3. 找到目标通道，点击 **「播放」** 按钮
4. 视频画面即可在页面中播放 🎉

> 如果无法播放，请检查流媒体服务是否正常运行，以及 `BACKEND_PUBLIC_HOST` 配置是否正确。

---

## 📚 下一步

| 文档 | 说明 |
|------|------|
| [部署指南](deployment.md) | 生产环境详细部署方案 |
| [配置说明](configuration.md) | 完整配置参数参考 |
| [API 文档](api.md) | 后端接口文档 |
| [级联对接](cascade.md) | 上下级平台级联 |
| [常见问题](faq.md) | 故障排查与 FAQ |

---

💡 **遇到问题？** 先查看 [常见问题](faq.md)，或在 [GitHub Issues](https://github.com/suoten/PyGBSentry/issues) 提交反馈。
