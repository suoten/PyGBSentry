# API 文档

<!-- P2-33: 文档版本与代码版本绑定 -->
> **文档版本**：与 `PROJECT_VERSION`（`app/core/config.py`）保持一致。
> 完整 OpenAPI 规范可通过 `python tools/export_openapi.py` 导出为 `docs/openapi.json`。

## 概述

PyGBSentry 提供 RESTful API，基于 [FastAPI](https://fastapi.tiangolo.com/) 构建，遵循 OpenAPI 3.0 规范。

- 基础路径：`/api/v1/`
- 数据格式：JSON
- 在线文档：启用后可访问 `/docs`（Swagger UI）和 `/redoc`（ReDoc）

---

## 🔐 认证

API 使用 JWT Bearer Token 进行身份认证。

### 登录获取令牌

```
POST /api/v1/login/access-token
```

请求体（`application/x-www-form-urlencoded`）：

| 字段       | 类型   | 必填 | 说明     |
| ---------- | ------ | ---- | -------- |
| username   | string | ✅   | 用户名   |
| password   | string | ✅   | 密码     |

响应：

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

### 使用令牌

在请求头中携带令牌：

```
Authorization: Bearer <access_token>
```

---

## 👤 认证与用户

| 方法   | 路径                        | 说明         |
| ------ | --------------------------- | ------------ |
| POST   | /api/v1/login/access-token  | 登录获取令牌 |
| GET    | /api/v1/users/me            | 当前用户信息 |
| GET    | /api/v1/users/              | 用户列表     |
| POST   | /api/v1/users/              | 创建用户     |
| PUT    | /api/v1/users/{id}          | 更新用户     |
| GET    | /api/v1/user-api-keys/      | API 密钥管理 |

---

## 📡 设备与通道

| 方法   | 路径                              | 说明           |
| ------ | --------------------------------- | -------------- |
| GET    | /api/v1/devices/                  | 设备列表       |
| GET    | /api/v1/devices/{id}              | 设备详情       |
| DELETE | /api/v1/devices/{id}              | 删除设备       |
| GET    | /api/v1/devices/{id}/channels     | 设备通道列表   |
| POST   | /api/v1/devices/{id}/sync         | 同步设备目录   |
| POST   | /api/v1/devices/channels/import   | 批量导入通道   |

---

## 🎬 流媒体与回放

| 方法 | 路径                         | 说明           |
| ---- | ---------------------------- | -------------- |
| GET  | /api/v1/stream/start         | 启动实时流     |
| GET  | /api/v1/stream/stop          | 停止流         |
| GET  | /api/v1/stream/optimize      | 流优化指南     |
| GET  | /api/v1/vod/                 | VOD 点播回放   |
| GET  | /api/v1/gb-record/           | 国标录像查询   |
| GET  | /api/v1/record/              | 录像管理       |
| GET  | /api/v1/record-schedule/     | 录像计划       |

---

## 🎮 云台控制（PTZ）

| 方法 | 路径                                | 说明                |
| ---- | ----------------------------------- | ------------------- |
| POST | /api/v1/ptz/{device_id}/control     | PTZ 方向控制        |
| POST | /api/v1/ptz/{device_id}/preset      | 预置位操作          |
| POST | /api/v1/ptz/{device_id}/cruise      | 自动巡航            |
| POST | /api/v1/ptz/{device_id}/drag-zoom   | 3D 拖拽放大（2022） |

---

## 🚨 告警

| 方法 | 路径                            | 说明     |
| ---- | ------------------------------- | -------- |
| GET  | /api/v1/alarms/                 | 告警列表 |
| GET  | /api/v1/alarms/{id}             | 告警详情 |
| PUT  | /api/v1/alarms/{id}/confirm     | 确认告警 |
| PUT  | /api/v1/alarms/{id}/escalate    | 升级告警 |

---

## 🌐 平台与级联

| 方法 | 路径                                 | 说明             |
| ---- | ------------------------------------ | ---------------- |
| GET  | /api/v1/platforms/                   | 平台列表         |
| POST | /api/v1/platforms/                   | 添加平台         |
| GET  | /api/v1/platforms/server_config      | 获取服务端 SIP 配置 |
| GET  | /api/v1/platforms/exist/{gb_id}      | 检查平台是否存在 |

---

## 🗺️ GIS 地图

| 方法 | 路径                     | 说明         |
| ---- | ------------------------ | ------------ |
| GET  | /api/v1/map/config       | 地图配置     |
| GET  | /api/v1/map/devices      | 设备位置信息 |

---

## 🏥 运维与健康

| 方法 | 路径                              | 说明           |
| ---- | --------------------------------- | -------------- |
| GET  | /api/v1/health/liveness           | 存活探针       |
| GET  | /api/v1/health/readiness          | 就绪探针       |
| GET  | /api/v1/health/overview           | 运维概览       |
| GET  | /api/v1/health/devices            | 设备健康详情   |
| GET  | /api/v1/health/report/daily       | 每日健康报告   |
| GET  | /api/v1/ops/db-check              | 数据库检查     |
| GET  | /api/v1/ops/status                | 系统状态       |
| GET  | /api/v1/ops/diagnose              | 快速诊断       |
| GET  | /api/v1/ops/diagnose-report       | 完整诊断报告   |
| GET  | /api/v1/network/summary           | 网络概况       |
| GET  | /api/v1/network/bandwidth         | 带宽统计       |
| GET  | /api/v1/network/topology          | 网络拓扑       |
| GET  | /api/v1/metrics/devices-overview  | 设备概览指标   |

---

## ⚙️ 配置

| 方法 | 路径                     | 说明                               |
| ---- | ------------------------ | ---------------------------------- |
| GET  | /api/v1/system-config/   | 获取系统配置                       |
| PUT  | /api/v1/system-config/   | 更新系统配置                       |
| GET  | /api/v1/config-center/   | 配置中心（草稿/发布/回滚）         |

---

## 🔌 插件

| 方法   | 路径                            | 说明       |
| ------ | ------------------------------- | ---------- |
| GET    | /api/v1/plugins/                | 插件列表   |
| POST   | /api/v1/plugins/{id}/install    | 安装插件   |
| POST   | /api/v1/plugins/{id}/enable     | 启用插件   |
| DELETE | /api/v1/plugins/{id}            | 卸载插件   |

---

## 🤖 AI 网关

| 方法 | 路径                   | 说明         |
| ---- | ---------------------- | ------------ |
| POST | /api/v1/ai/chat        | AI 对话接口  |
| POST | /api/v1/ai/analyze     | AI 分析接口  |

---

## 📦 其他

| 方法     | 路径                           | 说明                   |
| -------- | ------------------------------ | ---------------------- |
| GET      | /api/v1/regions/               | 区域管理               |
| GET      | /api/v1/organizations/         | 组织管理               |
| GET      | /api/v1/audit-center/          | 审计中心               |
| GET      | /api/v1/logs/                  | 系统日志               |
| GET      | /api/v1/network/               | 网络状态               |
| GET      | /api/v1/network-diagnostics/   | 网络诊断               |
| GET      | /api/v1/ssl-cert/              | SSL 证书管理           |
| WebSocket| /api/v1/sip-trace              | SIP 信令追踪 WebSocket |
| POST     | /api/v1/hook/*                 | ZLMediaKit 回调（内部）|

---

## 📋 通用响应格式

### 成功响应

```json
{
  "code": 0,
  "msg": "success",
  "data": { }
}
```

### 分页响应

```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "items": [],
    "total": 100,
    "page": 1,
    "size": 20
  }
}
```

### 错误响应

```json
{
  "code": 401,
  "msg": "Not authenticated",
  "detail": "Could not validate credentials"
}
```

---

## ❌ 错误码

| 状态码 | 说明                                       |
| ------ | ------------------------------------------ |
| 400    | 请求参数错误                               |
| 401    | 未认证或令牌无效                           |
| 403    | 权限不足，禁止访问                         |
| 404    | 资源不存在                                 |
| 422    | 请求体验证失败（字段校验错误）             |
| 429    | 请求过于频繁，触发限流                     |
| 500    | 服务器内部错误                             |
| 503    | 服务暂不可用（依赖服务异常或维护中）       |

---

## ⏱ 限流

- 默认限制：每 IP 每分钟 60 次请求
- 登录接口：每 IP 每分钟 10 次请求
- 超出限制返回 `429 Too Many Requests`，响应头包含：

```
Retry-After: 30
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1718300000
```

---

## 📖 OpenAPI 在线文档

默认关闭。通过环境变量启用：

```bash
ENABLE_OPENAPI_DOCS=true
```

启用后访问：

| 地址       | 说明         |
| ---------- | ------------ |
| /docs      | Swagger UI   |
| /redoc     | ReDoc        |
| /openapi.json | OpenAPI Schema |
