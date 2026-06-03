# PyGBSentry 架构与二次开发指南

[中文](#) | [English](#english-version)

本文档面向希望基于 PyGBSentry 进行功能扩展、插件开发或代码贡献的开发者。内容涵盖系统整体架构、前后端开发规范、插件机制以及代码提交标准，帮助开发者快速理解代码结构并高效地进行二次开发。

---

## 目录

- [系统架构](#系统架构)
- [后端开发](#后端开发)
- [前端开发](#前端开发)
- [插件开发](#插件开发)
- [代码规范](#代码规范)
- [测试](#测试)
- [贡献代码](#贡献代码)
- [相关文档](#相关文档)
- [English Version](#english-version)

---

## 系统架构

### 核心分层

PyGBSentry 采用经典的分层架构设计，各层职责如下：

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
| 协议 | GB/T 28181-2022 SIP（向下兼容 2016） |

### 后端目录结构

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

### 新增 API 接口

扩展 RESTful API 的标准流程如下：

1. 在 `app/api/v1/endpoints/` 下创建新文件（如 `myapp.py`）。
2. 定义 `APIRouter` 和具体的处理函数。
3. 在 `app/api/v1/api.py` 中注册路由。

**示例代码**：

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

如需处理新的 SIP 消息类型或自定义 XML 指令，请按以下步骤操作：

1. 打开 `app/sip/handlers.py`，定位到 `handle_message_request` 函数。
2. 增加新的 XML `CmdType` 判断分支。
3. 编写对应的处理函数并完成业务逻辑。

### 数据库操作示例

项目使用 SQLAlchemy 作为 ORM，推荐通过异步会话执行数据库操作：

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

### 新增页面

1. 在 `src/views/` 目录下创建新的 Vue 组件。
2. 在 `src/router/index.ts` 中添加对应的路由配置。
3. 在侧边栏配置中添加菜单项。

### API 调用规范

前端统一封装了请求实例，业务模块通过独立文件管理接口：

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

我们强烈建议通过**插件**来扩展功能，而不是修改核心代码。插件机制能够在保证系统稳定性的同时，实现灵活的功能扩展。

### 插件包结构

插件必须以 `.zip` 格式分发，解压后需包含以下文件：

| 文件 | 说明 |
|------|------|
| `plugin.json` | 元数据（ID、版本、依赖） |
| `__init__.py` | 入口文件，必须包含 `register(pm)` 函数 |
| `requirements.txt` | 可选，依赖列表 |

### 系统 Hook 点

插件管理器在系统关键生命周期和事件节点预留了 Hook，开发者可通过注册回调函数介入：

| Hook 点 | 触发时机 |
|---------|----------|
| `HOOK_ON_STARTUP` | 系统启动时 |
| `HOOK_ON_SHUTDOWN` | 系统关闭时 |
| `HOOK_ON_DEVICE_REGISTER` | 设备注册/上线时 |
| `HOOK_ON_ALARM` | 收到报警时 |
| `HOOK_ON_SIP_RECEIVE` | 收到任意 SIP 消息时 |
| `HOOK_ON_STREAM_START` | 视频流开始播放时 |
| `HOOK_ON_UPGRADE` | 插件升级时 |

### 插件代码示例

以下示例展示了如何注册一个报警处理插件：

```python
from app.core.plugin_manager import HOOK_ON_ALARM
import logging

logger = logging.getLogger(__name__)

async def on_alarm(alarm):
    logger.info(f"Plugin received alarm: {alarm.description}")

def register(pm):
    pm.register_hook(HOOK_ON_ALARM, on_alarm)
```

> 详细插件规范请参见：[PLUGIN_SPEC.md](./PLUGIN_SPEC.md)

---

## 代码规范

### 后端代码规范

- 遵循 [PEP 8](https://peps.python.org/pep-0008/) 编码规范。
- 使用类型注解（[PEP 484](https://peps.python.org/pep-0484/)）。
- 涉及 I/O 或数据库操作的函数统一使用 `async/await`。
- 数据库访问统一使用 SQLAlchemy ORM。
- 全局配置项从 `app/core/config.py` 获取，禁止在业务代码中硬编码配置。

### 前端代码规范

- 使用 Vue 3 Composition API（`<script setup>` 语法）。
- 组件名使用 PascalCase。
- CSS 类名使用 kebab-case。
- API 错误处理统一使用 `getFriendlyError` 工具函数。

### Git Commit 规范

提交信息请遵循 [Conventional Commits](https://www.conventionalcommits.org/) 格式：

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

1. Fork 仓库并创建功能分支。
2. 遵循上述代码规范进行开发。
3. 确保本地通过所有测试。
4. 提交清晰且符合规范的 Commit 信息。

---

## 相关文档

| 文档 | 说明 |
|------|------|
| [PLUGIN_SPEC.md](./PLUGIN_SPEC.md) | 插件完整规范 |
| [PLUGIN_MOBILE_DESIGN.md](./PLUGIN_MOBILE_DESIGN.md) | 移动端插件设计 |
| [PRODUCT_OSS.md](./PRODUCT_OSS.md) | 产品能力说明 |

---

# English Version

# PyGBSentry Architecture & Developer Guide

This document is intended for developers who wish to extend PyGBSentry, develop plugins, or contribute code. It covers the overall system architecture, frontend and backend development standards, the plugin mechanism, and code submission guidelines to help developers quickly understand the codebase and efficiently perform secondary development.

---

## Table of Contents

- [System Architecture](#system-architecture)
- [Backend Development](#backend-development)
- [Frontend Development](#frontend-development)
- [Plugin Development](#plugin-development)
- [Code Standards](#code-standards)
- [Testing](#testing)
- [Contributing](#contributing)
- [Related Documents](#related-documents)

---

## System Architecture

### Core Layers

PyGBSentry adopts a classic layered architecture. The responsibilities of each layer are as follows:

| Layer | Description |
|------|------|
| **API Layer** | FastAPI provides RESTful APIs, handling frontend requests, authentication, and WebSocket push |
| **Business Layer** | Includes SIP command dispatch (INVITE, PTZ, QUERY), cascade services, AI analysis, etc. |
| **Protocol Layer** | Pure Python SIP protocol stack, supporting UDP/TCP dual stack, asyncio high-concurrency I/O |
| **Media Layer** | Built-in / external ZLMediaKit, monitoring stream status via Hook mechanism |
| **Data Layer** | PostgreSQL for persistent data, Redis for session and state caching |

### Technology Stack

| Component | Technology |
|------|---------|
| Backend Framework | FastAPI + uvicorn |
| Database | PostgreSQL / MySQL / SQLite |
| Cache | Redis |
| Media Streaming | ZLMediaKit |
| Frontend | Vue 3 + Element Plus |
| Protocol | GB/T 28181-2022 SIP (backward compatible with 2016) |

### Backend Directory Structure

```
backend/
├── app/
│   ├── api/                    # API routes
│   │   ├── v1/
│   │   │   └── endpoints/     # Business endpoints
│   │   └── common/            # Common components
│   ├── core/                  # Configuration, plugin management, global singletons
│   ├── db/                    # Database models (SQLAlchemy)
│   ├── models/                # ORM models
│   ├── services/              # Business logic
│   ├── sip/                   # SIP protocol stack core
│   └── main.py                # Entry file
├── plugins/                   # Plugin directory
└── binaries/                  # ZLM binaries
```

---

## Backend Development

### Adding a New API Endpoint

The standard process for extending RESTful APIs is as follows:

1. Create a new file under `app/api/v1/endpoints/` (e.g., `myapp.py`).
2. Define the `APIRouter` and specific handler functions.
3. Register the route in `app/api/v1/api.py`.

**Code Example**:

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

### Extending SIP Processing Logic

To handle new SIP message types or custom XML commands, follow these steps:

1. Open `app/sip/handlers.py` and locate the `handle_message_request` function.
2. Add a new XML `CmdType` branch.
3. Write the corresponding handler function and complete the business logic.

### Database Operation Example

The project uses SQLAlchemy as the ORM. It is recommended to execute database operations via asynchronous sessions:

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

## Frontend Development

### Project Structure

```
frontend/
├── src/
│   ├── api/                   # API calls
│   ├── components/            # Common components
│   ├── views/                 # Page views
│   ├── stores/                # Pinia state management
│   ├── router/                # Route configuration
│   └── utils/                 # Utility functions
├── public/                    # Static assets
└── package.json
```

### Adding a New Page

1. Create a new Vue component under `src/views/`.
2. Add the corresponding route configuration in `src/router/index.ts`.
3. Add a menu item in the sidebar configuration.

### API Call Standards

The frontend uses a unified request instance. Business modules manage interfaces through independent files:

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

## Plugin Development

We strongly recommend extending functionality through **plugins** rather than modifying core code. The plugin mechanism enables flexible feature expansion while ensuring system stability.

### Plugin Package Structure

Plugins must be distributed as `.zip` archives and must contain the following files after extraction:

| File | Description |
|------|------|
| `plugin.json` | Metadata (ID, version, dependencies) |
| `__init__.py` | Entry file, must contain the `register(pm)` function |
| `requirements.txt` | Optional, dependency list |

### System Hook Points

The plugin manager reserves hooks at key system lifecycle and event nodes. Developers can intervene by registering callback functions:

| Hook Point | Trigger Timing |
|---------|----------|
| `HOOK_ON_STARTUP` | When the system starts |
| `HOOK_ON_SHUTDOWN` | When the system shuts down |
| `HOOK_ON_DEVICE_REGISTER` | When a device registers / comes online |
| `HOOK_ON_ALARM` | When an alarm is received |
| `HOOK_ON_SIP_RECEIVE` | When any SIP message is received |
| `HOOK_ON_STREAM_START` | When video stream playback starts |
| `HOOK_ON_UPGRADE` | When the plugin is upgraded |

### Plugin Code Example

The following example shows how to register an alarm handling plugin:

```python
from app.core.plugin_manager import HOOK_ON_ALARM
import logging

logger = logging.getLogger(__name__)

async def on_alarm(alarm):
    logger.info(f"Plugin received alarm: {alarm.description}")

def register(pm):
    pm.register_hook(HOOK_ON_ALARM, on_alarm)
```

> For detailed plugin specifications, see: [PLUGIN_SPEC.md](./PLUGIN_SPEC.md)

---

## Code Standards

### Backend Code Standards

- Follow the [PEP 8](https://peps.python.org/pep-0008/) style guide.
- Use type annotations ([PEP 484](https://peps.python.org/pep-0484/)).
- Functions involving I/O or database operations must use `async/await` consistently.
- Database access must use SQLAlchemy ORM uniformly.
- Global configuration items must be retrieved from `app/core/config.py`. Hard-coding configurations in business code is prohibited.

### Frontend Code Standards

- Use Vue 3 Composition API (`<script setup>` syntax).
- Component names use PascalCase.
- CSS class names use kebab-case.
- API error handling must uniformly use the `getFriendlyError` utility function.

### Git Commit Standards

Commit messages should follow the [Conventional Commits](https://www.conventionalcommits.org/) format:

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

## Testing

### Backend Testing

```bash
cd backend
pytest tests/ -v
```

### Frontend Testing

```bash
cd frontend
npm run test
```

---

## Contributing

Pull Requests are welcome!

1. Fork the repository and create a feature branch.
2. Develop following the code standards above.
3. Ensure all tests pass locally.
4. Submit clear and standard-compliant commit messages.

---

## Related Documents

| Document | Description |
|------|------|
| [PLUGIN_SPEC.md](./PLUGIN_SPEC.md) | Full plugin specifications |
| [PLUGIN_MOBILE_DESIGN.md](./PLUGIN_MOBILE_DESIGN.md) | Mobile plugin design |
| [PRODUCT_OSS.md](./PRODUCT_OSS.md) | Product capability description |
