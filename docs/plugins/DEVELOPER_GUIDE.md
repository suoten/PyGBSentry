# PyGBSentry 插件开发指南

## 📖 概述

PyGBSentry 采用插件化架构，允许开发者扩展系统功能而无需修改核心代码。本指南将帮助你快速开发、测试和发布插件。

## 🏗️ 插件架构

### 插件类型

| 类型 | 用途 | 示例 |
|------|------|------|
| **AI Model** | AI 检测/识别算法 | 人形检测、烟火识别 |
| **Analytics** | 数据分析与可视化 | 客流统计、热力图 |
| **Integration** | 第三方系统集成 | 飞书告警、MQTT 桥接 |
| **Storage** | 存储后端 | S3 云存储、NAS 备份 |
| **Notification** | 通知渠道 | 短信、邮件、Webhook |

### 插件结构

```
my_plugin.zip
├── plugin.json           # 插件元数据（必需）
├── __init__.py           # 入口文件（必需）
├── main.py               # 主逻辑
├── requirements.txt      # Python 依赖（可选）
├── assets/               # 静态资源（可选）
│   ├── icon.png          # 插件图标
│   └── config_schema.json # 配置表单定义
└── tests/                # 测试文件（推荐）
    └── test_plugin.py
```

## 🔧 快速开始

### 步骤 1: 创建插件骨架

使用模板快速开始：

```bash
# 复制模板
cp -r plugins/templates/basic_plugin plugins/my_first_plugin

# 进入目录
cd plugins/my_first_plugin
```

### 步骤 2: 编辑 plugin.json

```json
{
  "id": "com.example.hello_world",
  "name": "Hello World Plugin",
  "version": "1.0.0",
  "description": "我的第一个 PyGBSentry 插件",
  "author": "Your Name",
  "email": "you@example.com",
  "type": "free",
  "category": "integration",
  "min_version": "1.0.0",
  "max_version": "*",
  "license": "MIT",
  "homepage": "https://github.com/your/repo",
  "icon": "assets/icon.png"
}
```

### 步骤 3: 编写插件代码

```python
# __init__.py
"""
Hello World Plugin for PyGBSentry
"""

from .main import HelloWorldPlugin


def register(plugin_manager):
    """
    插件注册函数（必需）
    
    Args:
        plugin_manager: PyGBSentry 插件管理器实例
    """
    plugin = HelloWorldPlugin()
    plugin_manager.register_plugin(plugin)
    
    return plugin
```

```python
# main.py
from pygbsentry.plugins import BasePlugin
from pygbsentry.events import EventHook


class HelloWorldPlugin(BasePlugin):
    """Hello World 插件示例"""
    
    name = "Hello World"
    version = "1.0.0"
    
    def on_load(self):
        """插件加载时调用"""
        self.logger.info("Hello World Plugin loaded!")
        
        # 注册事件钩子
        self.hook_manager.register(
            EventHook.ON_DEVICE_REGISTER,
            self.handle_device_register
        )
    
    def handle_device_register(self, device):
        """处理设备注册事件"""
        self.logger.info(f"新设备注册: {device.name} ({device.id})")
        
        # 发送通知
        self.notification_manager.send(
            title="新设备上线",
            message=f"设备 {device.name} 已成功注册",
            level="info"
        )
    
    def on_unload(self):
        """插件卸载时调用"""
        self.logger.info("Hello World Plugin unloaded")
```

### 步骤 4: 打包插件

```bash
# 安装打包工具
pip install pygbsentry-cli

# 打包插件
pygbsentry plugin pack my_first_plugin

# 输出: my_first_plugin-1.0.0.zip
```

### 步骤 5: 安装测试

```bash
# 本地安装
pygbsentry plugin install ./my_first_plugin-1.0.0.zip

# 启用插件
pygbsentry plugin enable com.example.hello_world

# 重启服务
pygbsentry restart
```

## 📚 插件 API 参考

### BasePlugin 基类

所有插件必须继承 `BasePlugin`：

```python
from pygbsentry.plugins import BasePlugin

class MyPlugin(BasePlugin):
    # 必需属性
    name = "My Plugin"
    version = "1.0.0"
    
    def on_load(self):
        """插件加载时调用"""
        pass
    
    def on_unload(self):
        """插件卸载时调用"""
        pass
    
    def on_config_update(self, config):
        """配置更新时调用"""
        pass
```

### 可用的管理器

```python
class MyPlugin(BasePlugin):
    def on_load(self):
        # 日志管理器
        self.logger.info("Log message")
        
        # 事件钩子管理器
        self.hook_manager.register(event, callback)
        
        # 通知管理器
        self.notification_manager.send(title, message, level)
        
        # 数据库管理器
        self.db.execute("SELECT * FROM devices")
        
        # 配置管理器
        config = self.config.get("api_key")
        
        # 任务调度器
        self.scheduler.add_job(self.my_task, "interval", minutes=5)
        
        # HTTP 客户端
        response = self.http.get("https://api.example.com")
```

### 事件钩子列表

```python
from pygbsentry.events import EventHook

# 设备相关
EventHook.ON_DEVICE_REGISTER      # 设备注册
EventHook.ON_DEVICE_OFFLINE       # 设备离线
EventHook.ON_DEVICE_ALARM         # 设备告警

# 视频流相关
EventHook.ON_STREAM_START         # 流开始
EventHook.ON_STREAM_STOP          # 流停止
EventHook.ON_STREAM_ERROR         # 流错误

# 告警相关
EventHook.ON_ALARM_TRIGGERED      # 告警触发
EventHook.ON_ALARM_RESOLVED       # 告警解除

# 用户相关
EventHook.ON_USER_LOGIN           # 用户登录
EventHook.ON_USER_LOGOUT          # 用户登出
```

## 🎯 插件类型详解

### 1. AI 模型插件

```python
# ai_detector/__init__.py
from .detector import AIDetectorPlugin

def register(pm):
    return pm.register_plugin(AIDetectorPlugin())
```

```python
# ai_detector/detector.py
from pygbsentry.plugins import BasePlugin
from pygbsentry.ai import AIModel


class AIDetectorPlugin(BasePlugin):
    name = "YOLOv8 Person Detector"
    version = "1.0.0"
    type = "ai_model"
    
    def on_load(self):
        # 注册 AI 模型
        model = AIModel(
            id="yolov8_person",
            name="YOLOv8 人形检测",
            description="基于 YOLOv8 的人形检测模型",
            input_type="video_frame",
            output_type="detections"
        )
        
        self.ai_manager.register_model(model)
        
        # 注册推理回调
        model.set_inference_fn(self.detect)
    
    def detect(self, frame):
        """
        执行检测
        
        Args:
            frame: numpy array (H, W, C)
            
        Returns:
            list of Detection objects
        """
        # 你的检测逻辑
        results = self.model.predict(frame)
        
        detections = []
        for result in results:
            detections.append({
                "class": "person",
                "confidence": result.confidence,
                "bbox": result.bbox,  # [x1, y1, x2, y2]
            })
        
        return detections
```

**requirements.txt**:
```
ultralytics>=8.0.0
opencv-python>=4.8.0
```

---

### 2. 数据分析插件

```python
# people_counter/__init__.py
from .counter import PeopleCounterPlugin

def register(pm):
    return pm.register_plugin(PeopleCounterPlugin())
```

```python
# people_counter/counter.py
from pygbsentry.plugins import BasePlugin
from datetime import datetime


class PeopleCounterPlugin(BasePlugin):
    name = "People Counter"
    version = "1.0.0"
    type = "analytics"
    
    def on_load(self):
        # 创建数据表
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS people_count (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_id TEXT,
                count INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 注册定时任务
        self.scheduler.add_job(
            self.generate_report,
            "cron",
            hour=9,
            minute=0
        )
        
        # 注册 Dashboard 面板
        self.dashboard.register_panel(
            id="people_count_chart",
            title="客流统计",
            component="LineChart",
            data_source=self.get_count_data
        )
    
    def on_detection(self, event):
        """处理检测事件"""
        if event.object_type == "person":
            camera_id = event.camera_id
            
            # 更新计数
            today = datetime.now().date()
            self.db.execute("""
                INSERT INTO people_count (camera_id, count, timestamp)
                VALUES (?, 1, ?)
            """, (camera_id, today))
    
    def get_count_data(self, params):
        """获取图表数据"""
        camera_id = params.get("camera_id")
        days = params.get("days", 7)
        
        rows = self.db.execute("""
            SELECT DATE(timestamp) as date, SUM(count) as total
            FROM people_count
            WHERE camera_id = ?
              AND timestamp >= DATE('now', ? || ' days')
            GROUP BY DATE(timestamp)
            ORDER BY date
        """, (camera_id, f"-{days}"))
        
        return {
            "labels": [row["date"] for row in rows],
            "datasets": [{
                "label": "客流量",
                "data": [row["total"] for row in rows]
            }]
        }
    
    def generate_report(self):
        """生成日报"""
        # 实现报告生成逻辑
        pass
```

---

### 3. 集成插件

```python
# feishu_alert/__init__.py
from .alert import FeishuAlertPlugin

def register(pm):
    return pm.register_plugin(FeishuAlertPlugin())
```

```python
# feishu_alert/alert.py
import requests
from pygbsentry.plugins import BasePlugin


class FeishuAlertPlugin(BasePlugin):
    name = "Feishu Alert"
    version = "1.0.0"
    type = "integration"
    
    # 配置 schema
    config_schema = {
        "webhook_url": {
            "type": "string",
            "required": True,
            "label": "飞书 Webhook URL",
            "help": "从飞书群机器人设置中获取"
        },
        "mention_users": {
            "type": "array",
            "required": False,
            "label": "@ 用户",
            "help": "需要 @ 的用户 ID 列表"
        }
    }
    
    def on_load(self):
        # 注册告警处理器
        self.alert_manager.register_handler(
            "feishu",
            self.send_alert
        )
    
    def send_alert(self, alert):
        """发送飞书告警"""
        webhook_url = self.config.get("webhook_url")
        mention_users = self.config.get("mention_users", [])
        
        # 构建消息
        message = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": f"⚠️ {alert.title}"
                    },
                    "template": "red" if alert.level == "critical" else "blue"
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": alert.message
                        }
                    },
                    {
                        "tag": "action",
                        "actions": [
                            {
                                "tag": "button",
                                "text": {
                                    "tag": "plain_text",
                                    "content": "查看详情"
                                },
                                "url": alert.detail_url,
                                "type": "primary"
                            }
                        ]
                    }
                ]
            }
        }
        
        # 添加 @ 用户
        if mention_users:
            message["card"]["elements"].append({
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": f"@{' @'.join(mention_users)}"
                    }
                ]
            })
        
        # 发送请求
        response = requests.post(webhook_url, json=message)
        response.raise_for_status()
        
        self.logger.info(f"飞书告警已发送: {alert.id}")
```

**assets/config_schema.json**:
```json
{
  "webhook_url": {
    "type": "string",
    "required": true,
    "label": "飞书 Webhook URL",
    "placeholder": "https://open.feishu.cn/open-apis/bot/v2/hook/..."
  },
  "mention_users": {
    "type": "array",
    "required": false,
    "label": "@ 用户",
    "items": {
      "type": "string",
      "label": "用户 ID"
    }
  }
}
```

## 🧪 测试插件

### 单元测试

```python
# tests/test_plugin.py
import pytest
from pygbsentry.testing import PluginTestCase
from my_plugin.main import MyPlugin


class TestMyPlugin(PluginTestCase):
    def setUp(self):
        self.plugin = MyPlugin()
        self.plugin.on_load()
    
    def test_on_device_register(self):
        """测试设备注册事件"""
        mock_device = MockDevice(id="test_001", name="Test Camera")
        
        # 触发事件
        self.plugin.handle_device_register(mock_device)
        
        # 验证通知已发送
        self.assert_notification_sent(
            title="新设备上线",
            level="info"
        )
    
    def tearDown(self):
        self.plugin.on_unload()
```

运行测试：

```bash
pytest tests/
```

### 集成测试

```python
# tests/test_integration.py
from pygbsentry.testing import IntegrationTest


class TestPluginIntegration(IntegrationTest):
    def test_full_workflow(self):
        """测试完整工作流程"""
        # 1. 安装插件
        self.install_plugin("my_plugin-1.0.0.zip")
        
        # 2. 配置插件
        self.configure_plugin("com.example.my_plugin", {
            "api_key": "test_key"
        })
        
        # 3. 模拟设备注册
        device = self.create_device("test_camera")
        
        # 4. 验证插件响应
        self.assert_event_triggered("ON_DEVICE_REGISTER")
        self.assert_notification_sent()
```

## 📦 发布插件

### 1. 准备发布

确保 `plugin.json` 包含所有必需字段：

```json
{
  "id": "com.example.my_plugin",
  "name": "My Plugin",
  "version": "1.0.0",
  "description": "详细的插件描述",
  "author": "Your Name",
  "email": "you@example.com",
  "type": "free",
  "category": "integration",
  "min_version": "1.0.0",
  "license": "MIT",
  "homepage": "https://github.com/your/repo",
  "repository": "https://github.com/your/repo.git",
  "documentation": "https://docs.example.com/my-plugin",
  "changelog": "https://github.com/your/repo/releases/tag/v1.0.0",
  "screenshots": [
    "assets/screenshot1.png",
    "assets/screenshot2.png"
  ],
  "tags": ["feishu", "alert", "notification"]
}
```

### 2. 打包

```bash
pygbsentry plugin pack my_plugin --output dist/
```

### 3. 提交到官方市场

```bash
# 登录
pygbsentry login

# 提交插件
pygbsentry plugin publish dist/my_plugin-1.0.0.zip

# 查看状态
pygbsentry plugin status com.example.my_plugin
```

### 4. 付费插件

对于付费插件，需要额外步骤：

```json
{
  "type": "paid",
  "price": 99.00,
  "currency": "CNY",
  "billing_period": "yearly",
  "trial_days": 14
}
```

```bash
# 加密源代码
pygbsentry plugin encrypt my_plugin

# 签名插件
pygbsentry plugin sign my_plugin --key-path ~/.pygbsentry/private_key.pem
```

## 🔐 安全最佳实践

### 1. 输入验证

```python
def handle_request(self, data):
    # 验证输入
    if not isinstance(data, dict):
        raise ValueError("Invalid input type")
    
    if "api_key" not in data:
        raise ValueError("Missing required field: api_key")
    
    # 清理输入
    api_key = sanitize_string(data["api_key"])
```

### 2. 敏感信息保护

```python
# ❌ 不要硬编码密钥
API_KEY = "sk-1234567890"

# ✅ 使用配置
API_KEY = self.config.get("api_key")

# ✅ 或使用环境变量
import os
API_KEY = os.getenv("MY_PLUGIN_API_KEY")
```

### 3. 权限最小化

```python
# 只请求必需的权限
permissions = [
    "devices:read",      # 读取设备信息
    "events:subscribe",  # 订阅事件
    "notifications:send" # 发送通知
]
```

## 📊 插件性能优化

### 1. 异步处理

```python
import asyncio

class MyPlugin(BasePlugin):
    async def handle_event(self, event):
        """异步处理事件"""
        # 非阻塞操作
        await self.http.post_async(url, data)
```

### 2. 缓存

```python
from functools import lru_cache

class MyPlugin(BasePlugin):
    @lru_cache(maxsize=128)
    def get_device_info(self, device_id):
        """缓存设备信息"""
        return self.db.query_one(
            "SELECT * FROM devices WHERE id = ?",
            (device_id,)
        )
```

### 3. 批量处理

```python
class MyPlugin(BasePlugin):
    def __init__(self):
        self.event_buffer = []
        self.buffer_size = 100
    
    def on_event(self, event):
        self.event_buffer.append(event)
        
        if len(self.event_buffer) >= self.buffer_size:
            self.process_batch()
    
    def process_batch(self):
        """批量处理事件"""
        events = self.event_buffer.copy()
        self.event_buffer.clear()
        
        # 批量写入数据库
        self.db.executemany(
            "INSERT INTO events (...) VALUES (...)",
            [(e.data,) for e in events]
        )
```

## ❓ 常见问题

### Q1: 如何调试插件？

```python
# 启用调试日志
import logging
logging.basicConfig(level=logging.DEBUG)

# 在插件中
self.logger.debug(f"Debug info: {variable}")
```

### Q2: 插件之间如何通信？

```python
# 方法 1: 通过事件总线
self.event_bus.emit("custom_event", data={"key": "value"})

# 方法 2: 共享数据库
self.db.execute("INSERT INTO shared_table ...")

# 方法 3: Redis  pub/sub
self.redis.publish("channel", message)
```

### Q3: 如何处理插件升级？

```python
def on_upgrade(self, old_version, new_version):
    """插件升级时调用"""
    if old_version < "1.2.0":
        # 执行数据库迁移
        self.db.execute("ALTER TABLE my_table ADD COLUMN new_field TEXT")
    
    if old_version < "1.3.0":
        # 更新配置
        self.config.set("new_option", "default_value")
```

## 📚 更多资源

- [插件 API 完整文档](../api/plugins.md)
- [官方插件示例](../plugins/official/)
- [插件市场](https://marketplace.pygbsentry.com)
- [社区论坛](https://community.pygbsentry.com)

## 💬 获取帮助

遇到问题？

1. 查看 [FAQ](FAQ.md)
2. 搜索 [GitHub Issues](https://github.com/pygbsentry/pygbsentry/issues)
3. 加入 [Discord 社区](https://discord.gg/pygbsentry)
4. 发送邮件至 plugins@pygbsentry.com
