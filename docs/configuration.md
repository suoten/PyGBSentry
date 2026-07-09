# 配置参考

所有配置均通过 `backend/.env` 文件中的环境变量完成。启动时后端会自动读取该文件，无需额外操作。

---

## 📋 项目设置

| 变量名 | 说明 | 默认值 | 生产建议 |
|--------|------|--------|----------|
| `PROJECT_NAME` | 项目名称 | `PyGBSentry` | 按需修改 |
| `API_V1_STR` | API 路由前缀 | `/api/v1` | 一般无需修改 |
| `APP_ENV` | 运行环境：`dev` / `prod` | `dev` | **必须设为 `prod`** |
| `APP_EDITION` | 版本标识 | `oss` | 开源版保持 `oss` |
| `APP_LANGUAGE` | 界面语言：`zh` / `en` | `zh` | 按需选择 |

---

## 🔐 安全

| 变量名 | 说明 | 默认值 | 生产建议 |
|--------|------|--------|----------|
| `SECRET_KEY` | 应用密钥，用于签名与加密 | — | **必填**，使用强随机字符串 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 访问令牌过期时间（分钟） | `120` | 按安全策略调整 |
| `ENABLE_AUTO_DISCOVERY` | 自动注册未知设备 | `false` | 生产环境建议 `false` |
| `ENABLE_OPENAPI_DOCS` | 启用 Swagger / ReDoc 文档 | `false` | 生产环境**务必 `false`** |
| `ENABLE_SECURITY_HEADERS` | 启用安全响应头 | `true` | 保持 `true` |
| `ENABLE_CSP` | 启用 Content Security Policy | `true` | 保持 `true` |
| `ADMIN_INITIAL_PASSWORD` | 管理员初始密码 | — | **必须设置强密码** |
| `ADMIN_FORCE_RESET_PASSWORD` | 强制管理员重置密码 | — | 首次部署建议启用 |

---

## 🗄️ 数据库

| 变量名 | 说明 | 默认值 | 生产建议 |
|--------|------|--------|----------|
| `DATABASE_TYPE` | 数据库类型：`postgresql` / `mysql` / `sqlite` | `postgresql` | 生产推荐 `postgresql` |
| `DATABASE_HOST` | 数据库主机地址 | — | 按实际填写 |
| `DATABASE_PORT` | 数据库端口 | — | PostgreSQL: `5432`，MySQL: `3306` |
| `DATABASE_NAME` | 数据库名称 | — | 按实际填写 |
| `DATABASE_USER` | 数据库用户名 | — | 使用专用账户 |
| `DATABASE_PASSWORD` | 数据库密码 | — | **使用强密码** |
| `DATABASE_SQLITE_PATH` | SQLite 数据库文件路径（仅 `sqlite` 模式） | — | 仅开发/测试使用 |
| `USE_ALEMBIC` | 启用 Alembic 数据库迁移 | `true` | 保持 `true` |

---

## 🔴 Redis

| 变量名 | 说明 | 默认值 | 生产建议 |
|--------|------|--------|----------|
| `REDIS_HOST` | Redis 主机地址 | — | 按实际填写 |
| `REDIS_PORT` | Redis 端口 | — | 默认 `6379` |
| `REDIS_PASSWORD` | Redis 密码 | — | **生产必须设置** |
| `REDIS_DB` | Redis 数据库编号 | — | 默认 `0` |
| `INIT_REDIS_ON_STARTUP` | 启动时连接 Redis | `false` | 使用 Redis 状态后端时设为 `true` |

---

## 📡 SIP 服务

| 变量名 | 说明 | 默认值 | 生产建议 |
|--------|------|--------|----------|
| `SIP_IP` | SIP 监听地址 | `0.0.0.0` | Docker 环境按需调整 |
| `SIP_PORT` | SIP 端口 | `5060` | 确保防火墙放行 |
| `SIP_ID` | SIP 服务器 ID（20 位编码） | `34020000002000000001` | 按国标编码规则填写 |
| `SIP_DOMAIN` | SIP 域编码（10 位） | `3402000000` | 与 SIP_ID 前 10 位一致 |
| `SIP_DEFAULT_PASSWORD` | SIP 设备注册密码 | — | **生产必填**，使用强密码 |
| `SIP_WORKER_CONCURRENCY` | SIP Worker 并发数 | `200` | 按设备规模调整 |
| `SIP_STATE_BACKEND` | 状态存储方式：`local` / `redis` | `local` | 多实例部署时使用 `redis` |

---

## 🎬 ZLMediaKit

| 变量名 | 说明 | 默认值 | 生产建议 |
|--------|------|--------|----------|
| `MEDIA_SERVER_SECRET` | ZLM API 访问密钥 | — | **生产必填** |
| `MEDIA_SERVER_HOST` | ZLM 主机地址 | `127.0.0.1` | 按实际填写 |
| `MEDIA_SERVER_HTTP_PORT` | ZLM HTTP 端口 | `8880` | 与 ZLM 配置一致 |
| `MEDIA_SERVER_RTSP_PORT` | ZLM RTSP 端口 | `554` | 与 ZLM 配置一致 |
| `MEDIA_SERVER_RTMP_PORT` | ZLM RTMP 端口 | `1935` | 与 ZLM 配置一致 |
| `MEDIA_SERVER_RTP_PROXY_PORT` | RTP 代理端口 | `30000` | 与 ZLM 配置一致 |
| `MEDIA_SERVER_RTP_PROXY_PORT_RANGE` | RTP 端口范围 | `30000-39000` | 确保范围足够 |
| `MEDIA_SERVER_RTP_STREAM_MODE` | 流传输模式：`UDP` / `TCP_PASSIVE` | `UDP` | 网络不稳定时用 `TCP_PASSIVE` |
| `MEDIA_NODES` | 多节点集群配置（JSON 数组） | — | 见下方多节点配置说明 |

---

## 📜 GB/T 28181

| 变量名 | 说明 | 默认值 | 生产建议 |
|--------|------|--------|----------|
| `GB28181_VERSION` | 协议版本：`2016` / `2022` | `2016` | 按设备兼容性选择 |
| `GB28181_STREAM_SWITCH_USE_TRACK_SUBJECT` | 使用 2022 版 TrackID 切流 | `false` | 仅 `2022` 版本时考虑开启 |

---

## 🎥 流与健康

| 变量名 | 说明 | 默认值 | 生产建议 |
|--------|------|--------|----------|
| `STREAM_SELF_HEAL_PROBE_ENABLED` | 启用流自愈探测 | `true` | 生产建议 `true` |
| `AUTO_PLAY_ENABLED` | 启用自动播放 | `true` | 按需设置 |
| `PLAY_ALLOW_NO_TOKEN` | 允许无 Token 播放 | `false` | 生产环境**务必 `false`** |

---

## 🐳 Docker

| 变量名 | 说明 | 默认值 | 生产建议 |
|--------|------|--------|----------|
| `RUNNING_IN_DOCKER` | Docker 环境检测标识 | `false` | Docker 部署时设为 `true` |
| `RTP_PORT_RANGE_START` | RTP 端口映射起始 | — | 与 ZLM 端口范围对应 |
| `RTP_PORT_RANGE_END` | RTP 端口映射结束 | — | 与 ZLM 端口范围对应 |
| `BACKEND_PUBLIC_HOST` | 后端公网地址（供 ZLM 回调） | — | **Docker 部署必填** |
| `BACKEND_PUBLIC_PORT` | 后端公网端口 | `8000` | 按实际映射端口填写 |

---

## 🌐 CORS

| 变量名 | 说明 | 默认值 | 生产建议 |
|--------|------|--------|----------|
| `BACKEND_CORS_ORIGINS` | 允许的跨域来源（JSON 数组） | — | 严格限制为前端域名 |

示例：

```env
BACKEND_CORS_ORIGINS=["https://gbsentry.example.com"]
```

---

## 🔌 插件

| 变量名 | 说明 | 默认值 | 生产建议 |
|--------|------|--------|----------|
| `PLUGIN_MARKETPLACE_BASE_URL` | 插件市场地址 | — | 按实际填写 |
| `PLUGIN_HOOK_EXEC_TIMEOUT_SECONDS` | 插件钩子执行超时（秒） | `30` | 按插件复杂度调整 |

---

## 🚨 告警与通知

| 变量名 | 说明 | 默认值 | 生产建议 |
|--------|------|--------|----------|
| `ALARM_ESCALATION_ENABLED` | 启用告警升级 | `true` | 生产建议 `true` |
| `HEALTH_ALERT_WEBHOOK_URL` | 健康告警 Webhook 地址 | — | 接入运维通知渠道 |
| `SLA_BREACH_NOTIFY_ENABLED` | 启用 SLA 违约通知 | `true` | 生产建议 `true` |

---

## ✅ 生产环境检查清单

部署到生产环境前，**必须**确认以下配置项：

- [ ] `APP_ENV` 设为 `prod`
- [ ] `SECRET_KEY` 已设置为强随机字符串
- [ ] `SIP_DEFAULT_PASSWORD` 已设置强密码
- [ ] `MEDIA_SERVER_SECRET` 已设置
- [ ] `ADMIN_INITIAL_PASSWORD` 已设置强密码
- [ ] `ENABLE_OPENAPI_DOCS` 设为 `false`
- [ ] `PLAY_ALLOW_NO_TOKEN` 设为 `false`
- [ ] `ENABLE_AUTO_DISCOVERY` 设为 `false`
- [ ] `DATABASE_PASSWORD` 使用强密码
- [ ] `REDIS_PASSWORD` 已设置（如使用 Redis）
- [ ] `BACKEND_CORS_ORIGINS` 已限制为前端域名

---

## 🐳 Docker 专项说明

Docker 部署时需额外注意：

1. **`RUNNING_IN_DOCKER`** 必须设为 `true`，系统将据此调整内部地址解析逻辑。
2. **`BACKEND_PUBLIC_HOST`** 必须填写后端的公网可达地址，ZLMediaKit 的 Hook 回调依赖此地址。
3. **`RTP_PORT_RANGE_START` / `RTP_PORT_RANGE_END`** 需与 `MEDIA_SERVER_RTP_PROXY_PORT_RANGE` 对应，并在 `docker-compose.yml` 中映射相应端口段。
4. **端口映射**：确保 SIP 端口（5060/UDP）、HTTP 端口（8000）、RTP 端口段均在防火墙和 Docker 端口映射中放行。

---

## 🖧 多节点流媒体集群配置

当部署多个 ZLMediaKit 节点时，通过 `MEDIA_NODES` 以 JSON 数组格式配置：

```env
MEDIA_NODES=[
  {
    "id": "node-1",
    "host": "192.168.1.10",
    "http_port": 8880,
    "rtsp_port": 554,
    "rtmp_port": 1935,
    "rtp_proxy_port": 30000,
    "secret": "your-node1-secret"
  },
  {
    "id": "node-2",
    "host": "192.168.1.11",
    "http_port": 8880,
    "rtsp_port": 554,
    "rtmp_port": 1935,
    "rtp_proxy_port": 30000,
    "secret": "your-node2-secret"
  }
]
```

配置多节点时需注意：

- 每个节点的 `id` 必须唯一。
- `secret` 应与各节点 ZLMediaKit 配置中的 `secret` 一致。
- 使用多节点时，`SIP_STATE_BACKEND` 建议设为 `redis`，并确保 `INIT_REDIS_ON_STARTUP` 为 `true`。
- 系统将自动在节点间进行负载均衡与故障转移。
