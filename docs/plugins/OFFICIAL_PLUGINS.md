# PyGBSentry 官方插件列表

本文档列出了 PyGBSentry 官方维护和推荐的插件。

## 📦 安装插件

```bash
# 从市场安装
pygbsentry plugin install <plugin-id>

# 从文件安装
pygbsentry plugin install ./plugin-file.zip

# 列出已安装插件
pygbsentry plugin list

# 更新插件
pygbsentry plugin update <plugin-id>

# 卸载插件
pygbsentry plugin uninstall <plugin-id>
```

---

## 🤖 AI 模型插件

### yolov8-detector

**ID**: `com.pygbsentry.yolov8-detector`  
**版本**: 1.2.0  
**类型**: AI Model  
**价格**: 免费

基于 YOLOv8 的通用目标检测插件。

**功能**:
- 支持 80 种 COCO 类别检测
- 可自定义检测类别
- GPU 加速支持
- 置信度阈值可调

**配置**:
```json
{
  "model_size": "n",  // n | s | m | l | x
  "confidence_threshold": 0.5,
  "device": "auto",   // auto | cpu | cuda
  "classes": ["person", "car", "truck"]  // 可选，只检测指定类别
}
```

**安装**:
```bash
pygbsentry plugin install yolov8-detector
```

---

### fire-smoke-detector

**ID**: `com.pygbsentry.fire-smoke-detector`  
**版本**: 1.0.0  
**类型**: AI Model  
**价格**: ¥199/年

烟火检测专用模型，适用于安防场景。

**功能**:
- 火焰检测（准确率 > 95%）
- 烟雾检测（准确率 > 90%）
- 低误报率优化
- 支持夜间模式

**配置**:
```json
{
  "detection_mode": "both",  // fire | smoke | both
  "sensitivity": "medium",   // low | medium | high
  "min_detection_area": 100  // 最小检测面积（像素）
}
```

**安装**:
```bash
pygbsentry plugin install fire-smoke-detector
```

---

### license-plate-ocr

**ID**: `com.pygbsentry.license-plate-ocr`  
**版本**: 1.1.0  
**类型**: AI Model  
**价格**: ¥149/年

车牌识别插件，支持中国大陆车牌。

**功能**:
- 蓝牌、绿牌、黄牌识别
- 字符识别准确率 > 98%
- 支持倾斜校正
- 输出车牌颜色和类型

**配置**:
```json
{
  "province_filter": [],  // 可选，限定省份 ["京", "沪", "粤"]
  "save_plate_image": true,
  "min_confidence": 0.85
}
```

**安装**:
```bash
pygbsentry plugin install license-plate-ocr
```

---

### face-recognition

**ID**: `com.pygbsentry.face-recognition`  
**版本**: 2.0.0  
**类型**: AI Model  
**价格**: ¥299/年

人脸识别插件，支持人员库管理。

**功能**:
- 人脸检测与对齐
- 特征提取与比对
- 人员库管理（增删改查）
- 活体检测（防照片攻击）

**配置**:
```json
{
  "face_database": "faces.db",
  "similarity_threshold": 0.7,
  "enable_liveness_check": true,
  "max_faces_per_frame": 10
}
```

**安装**:
```bash
pygbsentry plugin install face-recognition
```

---

## 📊 数据分析插件

### people-counter

**ID**: `com.pygbsentry.people-counter`  
**版本**: 1.0.0  
**类型**: Analytics  
**价格**: 免费

客流统计插件，提供进出人数统计。

**功能**:
- 双向计数（进入/离开）
- 实时人数统计
- 小时/日/周报表
- Dashboard 可视化

**配置**:
```json
{
  "counting_line": [[100, 300], [500, 300]],  // 计数线坐标
  "direction": "both",  // in | out | both
  "report_schedule": "0 * * * *"  // 每小时生成报告
}
```

**安装**:
```bash
pygbsentry plugin install people-counter
```

---

### heatmap-analytics

**ID**: `com.pygbsentry.heatmap-analytics`  
**版本**: 1.0.0  
**类型**: Analytics  
**价格**: ¥99/年

热力图分析插件，可视化人员活动热点。

**功能**:
- 区域热度统计
- 停留时长分析
- 动线轨迹追踪
- 导出热力图图片

**配置**:
```json
{
  "grid_size": 50,  // 网格大小（像素）
  "update_interval": 60,  // 更新间隔（秒）
  "zones": [
    {
      "id": "zone_a",
      "name": "入口区",
      "polygon": [[0, 0], [200, 0], [200, 200], [0, 200]]
    }
  ]
}
```

**安装**:
```bash
pygbsentry plugin install heatmap-analytics
```

---

### conversion-funnel

**ID**: `com.pygbsentry.conversion-funnel`  
**版本**: 1.0.0  
**类型**: Analytics  
**价格**: ¥199/年

转化漏斗分析，适用于零售场景。

**功能**:
- 过店→进店→购买全链路
- 转化率计算
- 流失节点分析
- 对比分析（同比/环比）

**配置**:
```json
{
  "funnel_stages": [
    {"name": "passersby", "camera": "exterior_cam"},
    {"name": "entries", "camera": "entrance_cam"},
    {"name": "purchases", "source": "pos_system"}
  ],
  "time_window": "daily"
}
```

**安装**:
```bash
pygbsentry plugin install conversion-funnel
```

---

## 🔌 集成插件

### feishu-alert

**ID**: `com.pygbsentry.feishu-alert`  
**版本**: 1.1.0  
**类型**: Integration  
**价格**: 免费

飞书告警推送插件。

**功能**:
- 告警消息推送
- 支持 @ 指定用户
- 富媒体卡片消息
- 告警确认按钮

**配置**:
```json
{
  "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/...",
  "mention_users": ["ou_xxx", "ou_yyy"],
  "alert_levels": ["warning", "critical"],
  "include_snapshot": true
}
```

**安装**:
```bash
pygbsentry plugin install feishu-alert
```

---

### mqtt-bridge

**ID**: `com.pygbsentry.mqtt-bridge`  
**版本**: 1.0.0  
**类型**: Integration  
**价格**: 免费

MQTT 桥接插件，实现与 IoT 平台对接。

**功能**:
- 设备状态同步到 MQTT
- 告警事件发布
- 订阅 MQTT 控制指令
- 支持 TLS 加密

**配置**:
```json
{
  "broker": "mqtt://broker.example.com:1883",
  "username": "mqtt_user",
  "password": "mqtt_pass",
  "client_id": "pygbsentry_001",
  "topic_prefix": "pygbsentry/",
  "qos": 1,
  "tls_enabled": false
}
```

**发布主题**:
- `pygbsentry/devices/{id}/status` - 设备状态
- `pygbsentry/alarms/{id}` - 告警事件
- `pygbsentry/events/{type}` - 系统事件

**订阅主题**:
- `pygbsentry/control/devices/{id}` - 设备控制
- `pygbsentry/control/config` - 配置更新

**安装**:
```bash
pygbsentry plugin install mqtt-bridge
```

---

### webhook-sender

**ID**: `com.pygbsentry.webhook-sender`  
**版本**: 1.0.0  
**类型**: Integration  
**价格**: 免费

Webhook 回调插件，将事件推送到外部系统。

**功能**:
- 自定义 HTTP 回调
- 重试机制（指数退避）
- 签名验证（HMAC-SHA256）
- 请求日志

**配置**:
```json
{
  "endpoints": [
    {
      "url": "https://api.example.com/webhook",
      "method": "POST",
      "headers": {
        "Authorization": "Bearer token123"
      },
      "events": ["alarm.triggered", "device.registered"],
      "retry_count": 3,
      "timeout": 10
    }
  ],
  "signing_secret": "your_secret_key"
}
```

**安装**:
```bash
pygbsentry plugin install webhook-sender
```

---

### s3-storage

**ID**: `com.pygbsentry.s3-storage`  
**版本**: 1.0.0  
**类型**: Storage  
**价格**: 免费

S3 云存储插件，用于录像备份。

**功能**:
- 自动上传录像到 S3
- 生命周期管理（自动删除过期文件）
- 支持多种 S3 兼容服务（AWS/阿里云/腾讯云）
- 加密传输

**配置**:
```json
{
  "endpoint": "https://s3.amazonaws.com",
  "access_key": "AKIAIOSFODNN7EXAMPLE",
  "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
  "bucket": "pygbsentry-recordings",
  "region": "us-east-1",
  "path_prefix": "recordings/{camera_id}/{date}/",
  "retention_days": 30,
  "storage_class": "STANDARD_IA"
}
```

**安装**:
```bash
pygbsentry plugin install s3-storage
```

---

## 🔔 通知插件

### sms-notifier

**ID**: `com.pygbsentry.sms-notifier`  
**版本**: 1.0.0  
**类型**: Notification  
**价格**: ¥99/年

短信通知插件，支持国内主流服务商。

**功能**:
- 阿里云短信
- 腾讯云短信
- 模板变量替换
- 发送频率限制

**配置**:
```json
{
  "provider": "aliyun",  // aliyun | tencent
  "access_key": "your_access_key",
  "secret_key": "your_secret_key",
  "sign_name": "PyGBSentry",
  "template_code": "SMS_123456789",
  "phone_numbers": ["13800138000", "13900139000"],
  "rate_limit": {
    "max_per_hour": 10,
    "max_per_day": 50
  }
}
```

**安装**:
```bash
pygbsentry plugin install sms-notifier
```

---

### email-notifier

**ID**: `com.pygbsentry.email-notifier`  
**版本**: 1.0.0  
**类型**: Notification  
**价格**: 免费

邮件通知插件。

**功能**:
- SMTP 发送邮件
- HTML 格式支持
- 附件支持（截图/录像片段）
- 收件人分组

**配置**:
```json
{
  "smtp_host": "smtp.example.com",
  "smtp_port": 587,
  "username": "noreply@example.com",
  "password": "your_password",
  "from_address": "PyGBSentry <noreply@example.com>",
  "to_addresses": ["admin@example.com"],
  "cc_addresses": [],
  "include_snapshot": true,
  "alert_levels": ["critical"]
}
```

**安装**:
```bash
pygbsentry plugin install email-notifier
```

---

## 🛡️ 企业级插件

### audit-log

**ID**: `com.pygbsentry.audit-log`  
**版本**: 1.0.0  
**类型**: Enterprise  
**价格**: 包含在 Enterprise 版

审计日志插件，满足合规要求。

**功能**:
- 完整操作日志记录
- 防篡改存储
- 日志导出（CSV/PDF）
- SOC2/ISO27001 报告模板

**配置**:
```json
{
  "log_level": "INFO",
  "storage_backend": "database",  // database | file | elasticsearch
  "retention_days": 365,
  "export_format": "pdf",
  "compliance_mode": "soc2"  // soc2 | iso27001 | gdpr
}
```

**安装**:
```bash
# 仅 Enterprise 版可用
pygbsentry plugin install audit-log
```

---

### sso-integration

**ID**: `com.pygbsentry.sso-integration`  
**版本**: 1.0.0  
**类型**: Enterprise  
**价格**: 包含在 Enterprise 版

单点登录插件，支持多种认证协议。

**功能**:
- OAuth 2.0 / OIDC
- SAML 2.0
- LDAP / AD
- 角色映射

**配置**:
```json
{
  "provider": "oidc",  // oidc | saml | ldap
  "oidc": {
    "issuer": "https://auth.example.com",
    "client_id": "pygbsentry",
    "client_secret": "secret",
    "redirect_uri": "https://pygbsentry.example.com/auth/callback"
  },
  "role_mapping": {
    "admin_group": "administrator",
    "operator_group": "operator",
    "viewer_group": "viewer"
  }
}
```

**安装**:
```bash
pygbsentry plugin install sso-integration
```

---

## 📦 插件包（Bundle）

### retail-bundle

**ID**: `com.pygbsentry.retail-bundle`  
**版本**: 1.0.0  
**价格**: ¥999/年（节省 40%）

零售业插件包，包含：

- ✅ people-counter
- ✅ heatmap-analytics
- ✅ conversion-funnel
- ✅ license-plate-ocr
- ✅ feishu-alert

**安装**:
```bash
pygbsentry plugin install retail-bundle
```

---

### security-bundle

**ID**: `com.pygbsentry.security-bundle`  
**版本**: 1.0.0  
**价格**: ¥799/年（节省 35%）

安防监控插件包，包含：

- ✅ yolov8-detector
- ✅ fire-smoke-detector
- ✅ face-recognition
- ✅ sms-notifier
- ✅ email-notifier

**安装**:
```bash
pygbsentry plugin install security-bundle
```

---

## 🔧 开发中插件

以下插件正在开发中，欢迎参与贡献：

| 插件名称 | 预计发布 | 状态 |
|---------|---------|------|
| traffic-analyzer | 2026 Q2 | Alpha |
| crowd-density | 2026 Q2 | Beta |
| pos-integration | 2026 Q3 | Planning |
| shelf-monitor | 2026 Q3 | Planning |
| action-recognition | 2026 Q4 | Research |

---

## 📝 提交你的插件

开发了有趣的插件？欢迎提交到官方市场！

1. Fork [plugin-marketplace](https://github.com/pygbsentry/plugin-marketplace)
2. 添加你的插件信息到 `plugins.json`
3. 提交 Pull Request
4. 审核通过后上线

**审核标准**:
- ✅ 功能完整，无明显 Bug
- ✅ 文档清晰，有使用示例
- ✅ 代码规范，通过安全检查
- ✅ 有单元测试覆盖

---

## ❓ 常见问题

### Q1: 如何查看插件的详细文档？

```bash
pygbsentry plugin info <plugin-id>
```

### Q2: 插件冲突怎么办？

如果两个插件监听同一事件，它们都会收到通知。确保插件之间没有状态依赖。

### Q3: 如何禁用某个插件？

```bash
pygbsentry plugin disable <plugin-id>
pygbsentry restart
```

### Q4: 插件更新会丢失配置吗？

不会。配置存储在独立的数据库中，升级时会保留。

---

## 📞 技术支持

- 📧 邮箱: plugins@pygbsentry.com
- 💬 Discord: https://discord.gg/pygbsentry
- 🐛 Issue: https://github.com/pygbsentry/pygbsentry/issues
