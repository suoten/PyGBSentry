# PyGBSentry 架构与二次开发指南

本文档介绍系统的技术架构与二次开发规范，帮助开发者快速理解代码结构并进行功能扩展。

---

## 系统架构

### 核心分层

| 层级 | 说明 |
|------|------|
| **接口层** | FastAPI 提供 RESTful API，处理前端请求、鉴权、WebSocket 推送 |
| **业务层** | 包含 SIP 指令下发（INVITE、PTZ、QUERY）、级联服务、AI 分析等 |
| **协议层** | 纯 Python 实现的 SIP 协议栈，支持 UDP/TCP 双协议栈，asyncio 高并发 I/O |
| **流媒体层** | 内置/外挂 ZLMediaKit，通过 Hook 机制监听流状态 |
| **数据层** | PostgreSQL 存储持久化数据，Redis 缓存会话与状态 |

### 技术栈

| 组件 | 技术选型 |
|------|---------|
| 后端框架 | FastAPI + uvicorn |
| 数据库 | PostgreSQL / MySQL / SQLite |
| 缓存 | Redis |
| 流媒体 | ZLMediaKit |
| 前端 | Vue 3 + Element Plus |
| 协议 | GB/T 28181-2016 SIP |

### 目录结构

```
backend/
├── app/
│   ├── api/                    # API 路由
│   │   ├── v1/
│   │   │   └── endpoints/     # 业务端点
│   │   └── common/            # 通用组件
│   ├── core/                  # 配置、插件管理、全局单例
│   ├── db/                    # 数据库模型 (SQLAlchemy)
│   ├── models/                # ORM 模型
│   ├── services/              # 业务逻辑
│   ├── sip/                   # SIP 协议栈核心
│   └── main.py                # 入口文件
├── plugins/                   # 插件目录
└── binaries/                  # ZLM 二进制文件
```

---

## 后端开发

### 添加新的 API 接口

1. 在 `app/api/v1/endpoints/` 下创建新文件（如 `myapp.py`）
2. 定义 `APIRouter` 和处理函数
3. 在 `app/api/v1/api.py` 中注册路由

**示例**：

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db

router = APIRouter(prefix="/myapp", tags=["我的应用"])

@router.get("/items")
async def list_items(db: AsyncSession = Depends(get_db)):
    """获取列表"""
    # 业务逻辑
    return {"items": []}
```

### 扩展 SIP 处理逻辑

1. 在 `app/sip/handlers.py` 中找到 `handle_message_request`
2. 增加新的 XML `CmdType` 判断分支
3. 编写对应的处理函数

### 数据库操作

```python
from sqlalchemy import select
from app.models.device import Device

async def get_device(db: AsyncSession, device_id: str):
    result = await db.execute(
        select(Device).where(Device.id == device_id)
    )
    return result.scalar_one_or_none()
```

---

## 前端开发

### 项目结构

```
frontend/
├── src/
│   ├── api/                   # API 调用
│   ├── components/            # 公共组件
│   ├── views/                 # 页面视图
│   ├── stores/                # Pinia 状态管理
│   ├── router/                # 路由配置
│   └── utils/                 # 工具函数
├── public/                    # 静态资源
└── package.json
```

### 添加新页面

1. 在 `src/views/` 创建 Vue 组件
2. 在 `src/router/index.ts` 添加路由配置
3. 在侧边栏配置中添加菜单项

### API 调用规范

```typescript
import api from '@/utils/request'

export const getDevices = () => {
  return api.get('/api/v1/devices')
}

export const addDevice = (data: object) => {
  return api.post('/api/v1/devices', data)
}
```

---

## 插件开发

我们强烈建议通过**插件**来扩展功能，而不是修��核心代码。

### 插件结构

插件必须是一个 `.zip` 包，解压后包含：

| 文件 | 说明 |
|------|------|
| `plugin.json` | 元数据（ID、版本、依赖） |
| `__init__.py` | 入口文件，必须包含 `register(pm)` 函数 |
| `requirements.txt` | 可选，依赖列表 |

### 支持的 Hook 点

| Hook 点 | 触发时机 |
|---------|----------|
| `HOOK_ON_STARTUP` | 系统启动时 |
| `HOOK_ON_SHUTDOWN` | 系统关闭时 |
| `HOOK_ON_DEVICE_REGISTER` | 设备注册/上线时 |
| `HOOK_ON_ALARM` | 收到报警时 |
| `HOOK_ON_SIP_RECEIVE` | 收到任意 SIP 消息时 |
| `HOOK_ON_STREAM_START` | 视频流开始播放时 |
| `HOOK_ON_UPGRADE` | 插件升级时 |

### 代码示例

```python
from app.core.plugin_manager import HOOK_ON_ALARM
import logging

logger = logging.getLogger(__name__)

async def on_alarm(alarm):
    logger.info(f"Plugin received alarm: {alarm.description}")

def register(pm):
    pm.register_hook(HOOK_ON_ALARM, on_alarm)
```

详细插件规范请参见：[PLUGIN_SPEC.md](./PLUGIN_SPEC.md)

---

## 代码规范

### 后端规范

- 遵循 PEP 8 编码规范
- 使用类型注解（PEP 484）
- 异步函数使用 `async/await`
- 数据库操作使用 SQLAlchemy ORM
- 配置项从 `app/core/config.py` 获取

### 前端规范

- 使用 Vue 3 Composition API（`<script setup>`）
- 组件名使用 PascalCase
- CSS 类名使用 kebab-case
- API 错误处理统一使用 `getFriendlyError`

### Git 提交规范

```
feat: 新功能
fix: 修复 bug
docs: 文档更新
style: 代码格式（不影响功能）
refactor: 重构
test: 测试
chore: 构建/工具更新
```

---

## 测试

### 后端测试

```bash
cd backend
pytest tests/ -v
```

### 前端测试

```bash
cd frontend
npm run test
```

---

## 贡献代码

欢迎提交 Pull Request！

1. Fork 仓库并创建新分支
2. 遵循代码规范
3. 确保通过所有测试
4. 提交清晰的 commit 信息

---

## 相关文档

| 文档 | 说明 |
|------|------|
| [PLUGIN_SPEC.md](./PLUGIN_SPEC.md) | 插件完整规范 |
| [PLUGIN_MOBILE_DESIGN.md](./PLUGIN_MOBILE_DESIGN.md) | 移动端插件设计 |
| [PRODUCT_OSS.md](./PRODUCT_OSS.md) | 产品能力说明 |
