# PyGBSentry 插件开发规范

[中文](#) | [English](#english-version)

本文档说明如何开发、安装和发布 PyGBSentry 插件。插件机制允许你在不修改核心代码的前提下扩展系统功能。

**适用版本**：开源版（OSS）  
**最后更新**：2025-06-03

---

## 目录

- [插件概述](#插件概述)
- [插件包结构](#插件包结构)
- [Hook 点参考](#hook-点参考)
- [Hook 使用示例](#hook-使用示例)
- [数据库操作](#数据库操作)
- [移动端插件支持](#移动端插件支持)
- [付费插件授权](#付费插件授权)
- [安全与依赖约束](#安全与依赖约束)
- [插件开发流程](#插件开发流程)
- [相关文档](#相关文档)

---

## 插件概述

### 什么是插件

插件是一个独立的代码包，可以在不修改核心系统的前提下完成以下扩展：

- 添加新的 API 端点
- 响应系统事件（报警、设备上下线等）
- 提供新的前端页面或移动端能力
- 扩展数据库表结构

### 插件与核心代码的对比

| 对比项 | 插件 | 核心代码 |
|--------|------|----------|
| 修改方式 | 通过上传 `.zip` 包安装 | 需要修改源码 |
| 更新方式 | 支持热更新 | 需要重启服务 |
| 隔离性 | 独立目录、独立命名空间 | 共享全局状态 |
| 卸载 | 可完全卸载 | 不可逆 |

---

## 插件包结构

插件必须打包为 `.zip` 文件，解压后应包含以下文件：

```
my_plugin.zip
├── plugin.json       # 插件元数据（必须）
├── __init__.py       # 入口文件（必须）
├── requirements.txt  # 可选，Python 依赖列表
├── main.py           # 可选，主业务逻辑
└── tables.py         # 可选，数据库模型定义
```

### plugin.json 元数据

`plugin.json` 是插件的唯一标识和配置中心，其格式如下：

```json
{
  "id": "com.example.my_plugin",
  "name": "我的插件",
  "version": "1.0.0",
  "description": "插件功能描述",
  "author": "插件作者",
  "type": "free",
  "license_key": "",
  "entry_point": "__init__.py",
  "tables": ["my_plugin_data"],
  "min_oss_version": "1.0.0"
}
```

#### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | 字符串 | 是 | 全局唯一标识符，建议使用反向域名格式，如 `com.xxx.xxx` |
| `name` | 字符串 | 是 | 插件的显示名称 |
| `version` | 字符串 | 是 | 语义化版本号，例如 `1.0.0` |
| `description` | 字符串 | 否 | 插件功能描述 |
| `author` | 字符串 | 否 | 作者或组织信息 |
| `type` | 字符串 | 是 | 插件类型：`free`（免费）或 `paid`（付费） |
| `license_key` | 字符串 | 否 | 付费插件的许可证密钥 |
| `entry_point` | 字符串 | 是 | 入口文件路径，通常为 `__init__.py` |
| `tables` | 数组 | 否 | 数据库表名列表，用于卸载时自动清理 |
| `min_oss_version` | 字符串 | 否 | 最低兼容的 OSS 版本号 |

### 入口文件要求

入口文件 **必须** 导出 `register` 函数，系统将在插件加载时调用该函数：

```python
def register(pm):
    """
    插件注册函数

    Args:
        pm: PluginManager 实例，提供注册 Hook、路由等能力
    """
    # 注册 Hook
    pm.register_hook(HOOK_ON_ALARM, on_alarm_handler)

    # 注册 API 路由（如需要）
    pm.register_router(my_router)
```

---

## Hook 点参考

系统预定义了以下 Hook 点，插件可通过 `pm.register_hook` 订阅感兴趣的事件。

### 系统生命周期

| Hook | 说明 | 回调参数 |
|------|------|----------|
| `HOOK_ON_STARTUP` | 系统启动完成 | `app` |
| `HOOK_ON_SHUTDOWN` | 系统关闭前 | `app` |
| `HOOK_ON_UPGRADE` | 插件升级时 | `plugin_id, old_version, new_version` |

### 设备相关

| Hook | 说明 | 回调参数 |
|------|------|----------|
| `HOOK_ON_DEVICE_REGISTER` | 设备注册成功 | `device` |
| `HOOK_ON_DEVICE_OFFLINE` | 设备离线 | `device` |
| `HOOK_ON_CATALOG_SYNC` | 目录同步完成 | `device, channels` |

### 报警相关

| Hook | 说明 | 回调参数 |
|------|------|----------|
| `HOOK_ON_ALARM` | 收到报警 | `alarm` |
| `HOOK_ON_ALARM_CONFIRM` | 报警被确认 | `alarm, user` |
| `HOOK_ON_ALARM_ESCALATE` | 报警升级 | `alarm, level` |

### 流媒体相关

| Hook | 说明 | 回调参数 |
|------|------|----------|
| `HOOK_ON_STREAM_START` | 流开始播放 | `device_id, channel_id, stream_url` |
| `HOOK_ON_STREAM_STOP` | 流停止播放 | `device_id, channel_id` |
| `HOOK_ON_RECORD_START` | 录像开始 | `device_id, channel_id` |
| `HOOK_ON_RECORD_STOP` | 录像结束 | `device_id, channel_id` |

### SIP 协议相关

| Hook | 说明 | 回调参数 |
|------|------|----------|
| `HOOK_ON_SIP_RECEIVE` | 收到 SIP 消息 | `message` |
| `HOOK_ON_SIP_SEND` | 发送 SIP 消息 | `message` |

---

## Hook 使用示例

### 订阅报警事件

```python
from app.core.plugin_manager import HOOK_ON_ALARM

async def on_alarm(alarm):
    # 处理报警
    print(f"收到报警：{alarm.id} - {alarm.type}")

    # 可在此发送通知、触发录像等
    await send_notification(alarm)

def register(pm):
    pm.register_hook(HOOK_ON_ALARM, on_alarm)
```

### 订阅设备上下线事件

```python
from app.core.plugin_manager import HOOK_ON_DEVICE_REGISTER, HOOK_ON_DEVICE_OFFLINE

async def on_device_online(device):
    print(f"设备上线：{device.name}")

async def on_device_offline(device):
    print(f"设备离线：{device.name}")

def register(pm):
    pm.register_hook(HOOK_ON_DEVICE_REGISTER, on_device_online)
    pm.register_hook(HOOK_ON_DEVICE_OFFLINE, on_device_offline)
```

---

## 数据库操作

### 创建表结构

首先，在 `plugin.json` 中声明插件需要的数据库表名：

```json
{
  "tables": ["my_plugin_data"]
}
```

然后在入口文件中定义模型并完成建表：

```python
from app.db.session import Base
from sqlalchemy import Column, String, Integer
from sqlalchemy.orm import declarative_base

PluginBase = declarative_base(cls=Base)

class MyPluginData(PluginBase):
    __tablename__ = "my_plugin_data"

    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    value = Column(String(1000))

async def init_plugin_db():
    from app.db.session import engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def on_startup(app):
    await init_plugin_db()

def register(pm):
    pm.register_hook(HOOK_ON_STARTUP, on_startup)
```

### 卸载时清理

插件卸载时，系统会自动删除 `plugin.json` 中 `tables` 数组声明的所有表。

---

## 移动端插件支持

插件可通过 `plugin.json` 中的 `mobile` 与 `miniprogram` 字段扩展移动端能力：

```json
{
  "id": "my_plugin",
  "name": "我的插件",
  "mobile": {
    "entry_type": "h5",
    "entry_url": "https://example.com/mobile/index.html"
  },
  "miniprogram": {
    "entry_type": "webview",
    "entry_url": "https://example.com/mini/index.html"
  }
}
```

详细的移动端设计规范请参见：[PLUGIN_MOBILE_DESIGN.md](./PLUGIN_MOBILE_DESIGN.md)

---

## 付费插件授权

### 许可证机制

付费插件使用许可证文件控制使用权限。许可证格式如下：

```json
{
  "plugin_id": "com.example.paid_plugin",
  "license_key": "LICENSE-KEY-FROM-PLATFORM",
  "expires_at": "2025-12-31T23:59:59Z",
  "signature": "ED25519_SIGNATURE"
}
```

### 授权校验流程

1. **安装时**：校验 `license.json` 的签名有效性。
2. **运行时**：定期检查许可证是否过期或吊销。
3. **过期后**：自动禁用该插件注册的所有 Hook。

---

## 安全与依赖约束

### 安全扫描

系统在上传插件包时自动进行安全扫描，检测以下风险类别：

| 类别 | 检测项 | 说明 |
|------|--------|------|
| 进程/命令执行 | `subprocess`, `os.system`, `eval` 等 | 防止恶意代码执行 |
| 本地资源 | `ctypes`, `multiprocessing` 等 | 防止原生代码攻击 |
| 反序列化 | `pickle.loads` 等 | 防止反序列化攻击 |
| 网络访问 | `requests`, `httpx`, `socket` 等 | 记录网络行为 |

### 依赖约束

- 不允许使用 `git+` 源安装依赖。
- 不允许使用自定义 PyPI index。
- 建议为依赖项指定明确的版本范围，避免意外破坏。

---

## 插件开发流程

### 1. 创建插件骨架

```bash
mkdir my_plugin
cd my_plugin
```

### 2. 编写元数据

创建 `plugin.json` 并填写必要的插件信息。

### 3. 实现功能

在 `__init__.py` 中实现 `register` 函数，注册所需的 Hook 或路由。

### 4. 测试插件

在开发环境中完成以下验证：

1. 将插件目录打包为 `.zip` 文件。
2. 通过「插件管理」界面上传并安装。
3. 验证功能按预期工作，查看日志排查问题。

### 5. 发布插件

将插件包上传到插件市场，供其他用户下载安装。

---

## 相关文档

| 文档 | 说明 |
|------|------|
| [PLUGIN_MOBILE_DESIGN.md](./PLUGIN_MOBILE_DESIGN.md) | 移动端插件设计规范 |
| [DEVELOPER.md](./DEVELOPER.md) | 整体开发指南 |
| [PRODUCT_OSS.md](./PRODUCT_OSS.md) | 产品能力说明 |

---

# English Version

# PyGBSentry Plugin Development Specification

This document explains how to develop, install, and publish PyGBSentry plugins. The plugin mechanism allows you to extend system functionality without modifying the core codebase.

**Applicable Version**: Open Source Edition (OSS)  
**Last Updated**: 2025-06-03

---

## Table of Contents

- [Plugin Overview](#plugin-overview)
- [Plugin Package Structure](#plugin-package-structure)
- [Hook Reference](#hook-reference)
- [Hook Usage Examples](#hook-usage-examples)
- [Database Operations](#database-operations)
- [Mobile Plugin Support](#mobile-plugin-support)
- [Paid Plugin Licensing](#paid-plugin-licensing)
- [Security and Dependency Constraints](#security-and-dependency-constraints)
- [Plugin Development Workflow](#plugin-development-workflow)
- [Related Documents](#related-documents)

---

## Plugin Overview

### What Is a Plugin

A plugin is an independent code package capable of extending the system without touching core code:

- Add new API endpoints
- Respond to system events (alarms, device online/offline, etc.)
- Provide new frontend pages or mobile capabilities
- Extend the database schema

### Plugin vs. Core Code

| Comparison Item | Plugin | Core Code |
|-----------------|--------|-----------|
| Modification Method | Install by uploading a `.zip` package | Requires modifying source code |
| Update Method | Supports hot update | Requires service restart |
| Isolation | Independent directory and namespace | Shares global state |
| Uninstallation | Fully uninstallable | Irreversible |

---

## Plugin Package Structure

Plugins must be packaged as `.zip` files and should contain the following files after extraction:

```
my_plugin.zip
├── plugin.json       # Plugin metadata (required)
├── __init__.py       # Entry file (required)
├── requirements.txt  # Optional, Python dependency list
├── main.py           # Optional, main business logic
└── tables.py         # Optional, database model definitions
```

### plugin.json Metadata

`plugin.json` is the identity and configuration center of a plugin. Its format is as follows:

```json
{
  "id": "com.example.my_plugin",
  "name": "我的插件",
  "version": "1.0.0",
  "description": "插件功能描述",
  "author": "插件作者",
  "type": "free",
  "license_key": "",
  "entry_point": "__init__.py",
  "tables": ["my_plugin_data"],
  "min_oss_version": "1.0.0"
}
```

#### Field Descriptions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | String | Yes | Globally unique identifier; reverse-domain format recommended, e.g. `com.xxx.xxx` |
| `name` | String | Yes | Display name of the plugin |
| `version` | String | Yes | Semantic version, e.g. `1.0.0` |
| `description` | String | No | Functional description of the plugin |
| `author` | String | No | Author or organization information |
| `type` | String | Yes | Plugin type: `free` or `paid` |
| `license_key` | String | No | License key for paid plugins |
| `entry_point` | String | Yes | Entry file path, usually `__init__.py` |
| `tables` | Array | No | Database table names, used for automatic cleanup during uninstallation |
| `min_oss_version` | String | No | Minimum compatible OSS version |

### Entry File Requirements

The entry file **must** export a `register` function, which the system will invoke when loading the plugin:

```python
def register(pm):
    """
    Plugin registration function

    Args:
        pm: PluginManager instance, providing Hook and router registration capabilities
    """
    # Register Hook
    pm.register_hook(HOOK_ON_ALARM, on_alarm_handler)

    # Register API router (if needed)
    pm.register_router(my_router)
```

---

## Hook Reference

The system predefines the following Hook points. Plugins can subscribe to events of interest via `pm.register_hook`.

### System Lifecycle

| Hook | Description | Callback Parameters |
|------|-------------|---------------------|
| `HOOK_ON_STARTUP` | System startup completed | `app` |
| `HOOK_ON_SHUTDOWN` | Before system shutdown | `app` |
| `HOOK_ON_UPGRADE` | Plugin upgrade | `plugin_id, old_version, new_version` |

### Device Related

| Hook | Description | Callback Parameters |
|------|-------------|---------------------|
| `HOOK_ON_DEVICE_REGISTER` | Device registered successfully | `device` |
| `HOOK_ON_DEVICE_OFFLINE` | Device offline | `device` |
| `HOOK_ON_CATALOG_SYNC` | Catalog sync completed | `device, channels` |

### Alarm Related

| Hook | Description | Callback Parameters |
|------|-------------|---------------------|
| `HOOK_ON_ALARM` | Alarm received | `alarm` |
| `HOOK_ON_ALARM_CONFIRM` | Alarm confirmed | `alarm, user` |
| `HOOK_ON_ALARM_ESCALATE` | Alarm escalated | `alarm, level` |

### Streaming Media Related

| Hook | Description | Callback Parameters |
|------|-------------|---------------------|
| `HOOK_ON_STREAM_START` | Stream started playing | `device_id, channel_id, stream_url` |
| `HOOK_ON_STREAM_STOP` | Stream stopped playing | `device_id, channel_id` |
| `HOOK_ON_RECORD_START` | Recording started | `device_id, channel_id` |
| `HOOK_ON_RECORD_STOP` | Recording stopped | `device_id, channel_id` |

### SIP Protocol Related

| Hook | Description | Callback Parameters |
|------|-------------|---------------------|
| `HOOK_ON_SIP_RECEIVE` | SIP message received | `message` |
| `HOOK_ON_SIP_SEND` | SIP message sent | `message` |

---

## Hook Usage Examples

### Subscribing to Alarm Events

```python
from app.core.plugin_manager import HOOK_ON_ALARM

async def on_alarm(alarm):
    # Process the alarm
    print(f"收到报警：{alarm.id} - {alarm.type}")

    # You can send notifications, trigger recordings, etc.
    await send_notification(alarm)

def register(pm):
    pm.register_hook(HOOK_ON_ALARM, on_alarm)
```

### Subscribing to Device Online/Offline Events

```python
from app.core.plugin_manager import HOOK_ON_DEVICE_REGISTER, HOOK_ON_DEVICE_OFFLINE

async def on_device_online(device):
    print(f"设备上线：{device.name}")

async def on_device_offline(device):
    print(f"设备离线：{device.name}")

def register(pm):
    pm.register_hook(HOOK_ON_DEVICE_REGISTER, on_device_online)
    pm.register_hook(HOOK_ON_DEVICE_OFFLINE, on_device_offline)
```

---

## Database Operations

### Creating Table Schema

First, declare the database tables required by the plugin in `plugin.json`:

```json
{
  "tables": ["my_plugin_data"]
}
```

Then define the models and create the tables in the entry file:

```python
from app.db.session import Base
from sqlalchemy import Column, String, Integer
from sqlalchemy.orm import declarative_base

PluginBase = declarative_base(cls=Base)

class MyPluginData(PluginBase):
    __tablename__ = "my_plugin_data"

    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    value = Column(String(1000))

async def init_plugin_db():
    from app.db.session import engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def on_startup(app):
    await init_plugin_db()

def register(pm):
    pm.register_hook(HOOK_ON_STARTUP, on_startup)
```

### Cleanup on Uninstallation

When a plugin is uninstalled, the system will automatically drop all tables listed in the `tables` array of `plugin.json`.

---

## Mobile Plugin Support

Plugins can extend mobile capabilities through the `mobile` and `miniprogram` fields in `plugin.json`:

```json
{
  "id": "my_plugin",
  "name": "我的插件",
  "mobile": {
    "entry_type": "h5",
    "entry_url": "https://example.com/mobile/index.html"
  },
  "miniprogram": {
    "entry_type": "webview",
    "entry_url": "https://example.com/mini/index.html"
  }
}
```

For detailed mobile design specifications, please refer to: [PLUGIN_MOBILE_DESIGN.md](./PLUGIN_MOBILE_DESIGN.md)

---

## Paid Plugin Licensing

### License Mechanism

Paid plugins use a license file to control usage rights. The license format is as follows:

```json
{
  "plugin_id": "com.example.paid_plugin",
  "license_key": "LICENSE-KEY-FROM-PLATFORM",
  "expires_at": "2025-12-31T23:59:59Z",
  "signature": "ED25519_SIGNATURE"
}
```

### License Validation Workflow

1. **During Installation**: Validate the signature of `license.json`.
2. **At Runtime**: Periodically check whether the license is expired or revoked.
3. **After Expiration**: Automatically disable all Hooks registered by the plugin.

---

## Security and Dependency Constraints

### Security Scanning

The system performs automatic security scanning when a plugin package is uploaded, detecting the following risk categories:

| Category | Detection Items | Description |
|----------|-----------------|-------------|
| Process / Command Execution | `subprocess`, `os.system`, `eval`, etc. | Prevent malicious code execution |
| Local Resources | `ctypes`, `multiprocessing`, etc. | Prevent native code attacks |
| Deserialization | `pickle.loads`, etc. | Prevent deserialization attacks |
| Network Access | `requests`, `httpx`, `socket`, etc. | Record network behavior |

### Dependency Constraints

- Using `git+` sources for dependencies is not allowed.
- Using custom PyPI indexes is not allowed.
- It is recommended to specify explicit version ranges for dependencies to avoid unexpected breakage.

---

## Plugin Development Workflow

### 1. Create the Plugin Skeleton

```bash
mkdir my_plugin
cd my_plugin
```

### 2. Write Metadata

Create `plugin.json` and fill in the necessary plugin information.

### 3. Implement Functionality

Implement the `register` function in `__init__.py`, registering the required Hooks or routers.

### 4. Test the Plugin

Perform the following validations in the development environment:

1. Package the plugin directory into a `.zip` file.
2. Upload and install it via the Plugin Management interface.
3. Verify that the functionality works as expected, and inspect logs for troubleshooting.

### 5. Publish the Plugin

Upload the plugin package to the plugin marketplace for other users to download and install.

---

## Related Documents

| Document | Description |
|----------|-------------|
| [PLUGIN_MOBILE_DESIGN.md](./PLUGIN_MOBILE_DESIGN.md) | Mobile plugin design specifications |
| [DEVELOPER.md](./DEVELOPER.md) | Overall development guide |
| [PRODUCT_OSS.md](./PRODUCT_OSS.md) | Product capability description |
