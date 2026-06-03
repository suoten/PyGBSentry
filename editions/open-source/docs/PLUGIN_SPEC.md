# PyGBSentry 插件开发规范

本文档说明如何开发、安装和发布插件。插件机制允许你在不修改核心代码的情况下扩展系统功能。

---

## 插件概述

### 什么是插件

插件是一个独立的代码包，可以：
- 添加新的 API 端点
- 响应系统事件（报警、设备上下线等）
- 提供新的前端页面或移动端能力
- 扩展数据库表结构

### 插件与核心代码的关系

| 对比项 | 插件 | 核心代码 |
|--------|------|----------|
| 修改方式 | 通过上传 zip 包安装 | 需要修改源码 |
| 更新方式 | 可热更新 | 需要重启服务 |
| 隔离性 | 独立目录、命名空间 | 共享全局状态 |
| 卸载 | 可完全卸载 | 不可逆 |

---

## 插件包结构

插件必须打包为 `.zip` 文件，解压后包含以下文件：

```
my_plugin.zip
├── plugin.json       # 元数据（必须）
├── __init__.py       # 入口文件（必须）
├── requirements.txt  # 可选，依赖列表
├── main.py           # 可选，主逻辑
└── tables.py         # 可选，数据库表
```

### plugin.json 元数据

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

**字段说明**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | 字符串 | 是 | 唯一标识符，格式为 `com.xxx.xxx` |
| `name` | 字符串 | 是 | 显示名称 |
| `version` | 字符串 | 是 | 语义化版本，如 `1.0.0` |
| `description` | 字符串 | 否 | 功能描述 |
| `author` | 字符串 | 否 | 作者信息 |
| `type` | 字符串 | 是 | `free` 或 `paid` |
| `license_key` | 字符串 | 否 | 付费插件许可证 |
| `entry_point` | 字符串 | 是 | 入口文件，通常为 `__init__.py` |
| `tables` | 数组 | 否 | 数据库表名列表（用于卸载时清理） |
| `min_oss_version` | 字符串 | 否 | 最低兼容版本 |

### 入口文件要求

入口文件必须导出 `register` 函数：

```python
def register(pm):
    """
    插件注册函数
    pm: PluginManager 实例
    """
    # 注册 Hook
    pm.register_hook(HOOK_ON_ALARM, on_alarm_handler)
    
    # 注册 API 路由（如需要）
    pm.register_router(my_router)
```

---

## Hook 点参考

系统提供以下 Hook 点供插件订阅：

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

### 订阅报警

```python
from app.core.plugin_manager import HOOK_ON_ALARM

async def on_alarm(alarm):
    # 处理报警
    print(f"收到报警：{alarm.id} - {alarm.type}")
    
    # 可以发送通知、触发录像等
    await send_notification(alarm)

def register(pm):
    pm.register_hook(HOOK_ON_ALARM, on_alarm)
```

### 订阅设备上下线

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

在 `plugin.json` 中声明表名：

```json
{
  "tables": ["my_plugin_data"]
}
```

在入口文件中建��：

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

插件卸载时会自动删除 `plugin.json` 中 `tables` 数组声明的表。

---

## 移动端插件支持

### plugin.json 移动端字段

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

详细移动端设计规范请参见：[PLUGIN_MOBILE_DESIGN.md](./PLUGIN_MOBILE_DESIGN.md)

---

## 付费插件授权

### 许可证机制

付费插件使用许可证文件控制使用权限：

```json
{
  "plugin_id": "com.example.paid_plugin",
  "license_key": "LICENSE-KEY-FROM-PLATFORM",
  "expires_at": "2025-12-31T23:59:59Z",
  "signature": "ED25519_SIGNATURE"
}
```

### 授权校验流程

1. 安装时校验 `license.json` 签名
2. 运行时定期检查许可证有效性
3. 过期后自动禁用相关 Hook

---

## 安全与依赖约束

### 安全扫描

系统对插件包进行安全扫描，检测以下风险：

| 类别 | 检测项 | 说明 |
|------|--------|------|
| 进程/命令执行 | `subprocess`, `os.system`, `eval` 等 | 防止恶意代码执行 |
| 本地资源 | `ctypes`, `multiprocessing` 等 | 防止原生代码攻击 |
| 反序列化 | `pickle.loads` 等 | 防止反序列化攻击 |
| 网络访问 | `requests`, `httpx`, `socket` 等 | 记录网络行为 |

### 依赖约束

- 不允许使用 `git+` 源
- 不允许使用自定义 index
- 建议限制依赖版本范围

---

## 插件开发流程

### 1. 创建插件骨架

```bash
mkdir my_plugin
cd my_plugin
```

### 2. 编写元数据

创建 `plugin.json` 并填写必要信息。

### 3. 实现功能

在 `__init__.py` 中实现 `register` 函数，注册所需的 Hook。

### 4. 测试插件

在开发环境中测试：
1. 打包为 zip
2. 通过插件管理界面上传安装
3. 验证功能正常

### 5. 发布插件

将插件包上传到插件市场，供其他用户安装使用。

---

## 相关文档

| 文档 | 说明 |
|------|------|
| [PLUGIN_MOBILE_DESIGN.md](./PLUGIN_MOBILE_DESIGN.md) | 移动端插件设计规范 |
| [DEVELOPER.md](./DEVELOPER.md) | 整体开发指南 |
| [PRODUCT_OSS.md](./PRODUCT_OSS.md) | 产品能力说明 |
