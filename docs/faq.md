# 常见问题

| 问题类型 | 跳转 |
| -------- | ---- |
| 🔧 部署相关 | [部署相关](#-部署相关) |
| 📹 视频播放 | [视频播放](#-视频播放) |
| 📡 设备接入 | [设备接入](#-设备接入) |
| 🔔 告警与通知 | [告警与通知](#-告警与通知) |
| 🔗 级联 | [级联](#-级联) |
| ⚙️ 配置与运维 | [配置与运维](#️-配置与运维) |
| 🤖 AI 集成 | [AI 集成](#-ai-集成) |

---

## 🔧 部署相关

**Q: Docker 启动后后端日志报 "Please set SECRET_KEY"？**

A: 必须在 `.env` 文件中设置 `SECRET_KEY`、`MEDIA_SERVER_SECRET`、`BACKEND_PUBLIC_HOST`、`SIP_DEFAULT_PASSWORD` 等必填项。

---

**Q: Docker 启动后访问页面自动跳转到 /setup？**

A: 系统检测到数据库或 ZLM 连通性异常。打开 `/#/setup` 查看检测项，修复后点击"完成配置"。

---

**Q: Redis 连接超时怎么办？**

A: 开发环境可设置 `INIT_REDIS_ON_STARTUP=false` 跳过 Redis。生产环境请检查 `REDIS_HOST`/`REDIS_PASSWORD` 配置。

---

**Q: 如何选择数据库？**

A: 体验用 SQLite，生产推荐 PostgreSQL，已有 MySQL 基础可用 MySQL。

---

## 📹 视频播放

**Q: 点击播放后黑屏/无画面？**

A: 排查步骤：
1. 检查 ZLM 端口是否可达
2. 检查防火墙是否放通 RTP 端口段（UDP 30000-39000）
3. 检查 `BACKEND_PUBLIC_HOST` 配置
4. 查看后端日志和 ZLM 日志

---

**Q: 视频播放卡顿/延迟高？**

A:
1. 局域网建议 UDP 模式
2. 跨网/NAT 建议切换 TCP_PASSIVE
3. 检查网络带宽
4. 使用流优化向导选择最优协议

---

**Q: WebRTC 播放失败？**

A: WebRTC 需要 HTTPS 环境，且需正确配置 ZLM 的 RTC 端口和 ICE 候选地址。

---

## 📡 设备接入

**Q: 设备注册后一直显示离线？**

A:
1. 检查设备 SIP 服务器地址/端口配置
2. 检查 `SIP_ID`/`SIP_DOMAIN` 是否匹配
3. 检查防火墙是否放通 5060 端口
4. 查看后端 SIP 日志

---

**Q: 设备注册成功但看不到通道？**

A:
1. 手动触发目录同步
2. 检查设备是否支持 Catalog 订阅
3. 等待设备主动推送目录

---

**Q: 如何启用 GB/T 28181-2022 新特性？**

A: 设置 `GB28181_VERSION=2022`，启用 a=track 码流切换等特性。

---

## 🔔 告警与通知

**Q: 前端看不到实时告警？**

A: 检查 Nginx 是否配置了 WebSocket 升级（`proxy_http_version 1.1` + `Upgrade` header）。

---

**Q: 飞书/企微通知收不到？**

A:
1. 检查 Webhook URL 是否正确
2. 检查插件是否已启用
3. 查看插件日志

---

## 🔗 级联

**Q: 上级平台看不到通道？**

A:
1. 检查级联目录推送范围配置
2. 确认通道已勾选共享
3. 检查 SIP 信令是否正常

---

**Q: 级联播放失败？**

A:
1. 检查 RTP 端口段是否放通
2. 检查 NAT 地址配置
3. 尝试切换 TCP 模式

---

## ⚙️ 配置与运维

**Q: 如何修改 SIP 服务器 ID？**

A: 修改 `.env` 中的 `SIP_ID` 和 `SIP_DOMAIN`，重启后端。注意：已注册设备需同步修改。

---

**Q: 如何查看系统健康状态？**

A: 调用 `GET /api/v1/health/` 或 `GET /api/v1/ops/diagnose-report`。

---

**Q: 如何启用 OpenAPI 文档？**

A: 设置 `ENABLE_OPENAPI_DOCS=true`，访问 `/docs`。

---

**Q: 忘记管理员密码怎么办？**

A: 设置 `ADMIN_FORCE_RESET_PASSWORD=true`，重启后端，登录后立即删除此配置。

---

## 🤖 AI 集成

**Q: 如何接入 AI 能力？**

A: 通过插件市场安装 AI 插件，或使用 `/api/v1/ai/` 网关接口自定义 AI 后端。Python 生态天然适配 AI/ML 框架。

---

## 💬 获取支持

- **GitHub Issues**：[提交 Issue](https://github.com/PyGBSentry/PyGBSentry/issues)
- **邮件联系**：发送邮件至项目维护团队
