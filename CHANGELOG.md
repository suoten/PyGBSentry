# CHANGELOG

所有重要变更均记录在此文件中。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [1.1.0] — 2026-07-04

v1.0.0 发布候选后，经 5 轮全量代码审计和 9 轮 BUG 修复，修复 12 项功能 BUG 和 5 项稳定性缺陷。

### 修复

#### 功能 BUG 修复（12 项）

##### P0 级（阻塞性）

| 编号 | 问题 | 修复文件 |
|------|------|----------|
| BUG-01 | 倍速播放缺少 MANSRTSP Scale 头，设备不响应倍速指令 | `playback.py` |
| BUG-06 | NPT 时间语义错误（使用绝对 Unix 秒而非相对偏移） | `playback.py` |
| BUG-09 | 巡航/扫描控制 SIP 层已实现但 API 层无端点 | `ptz.py`、`frontend` |

##### P1 级（重要功能缺陷）

| 编号 | 问题 | 修复文件 |
|------|------|----------|
| BUG-02 | 时间轴拖动 NPT 使用绝对 Unix 秒，设备跳转位置错误 | `playback.py` |
| BUG-03 | WebRTC 播放地址无条件构建，无 ZLM 时前端报错 | `frontend` |
| BUG-04 | H.265 播放器选择缺少 codec 信息，默认选错播放器 | `frontend` |
| BUG-05 | 语音广播 SDP 使用后端 IP 导致 NAT 环境不可达 | `talk.py` |
| BUG-07 | 双向对讲 INVITE URI 使用 channel_id 而非设备 ID | `talk.py` |
| BUG-08 | RTP 端口耗尽无重试机制，高并发点播失败 | `invite.py` |
| BUG-10 | 双向对讲缺少 start_rtp_pusher，设备无法回传音频 | `talk.py` |
| BUG-11 | talk send_bye ZLM 流关闭参数错误导致资源泄漏 | `talk.py` |

##### P0 级（并发稳定性）

| 编号 | 问题 | 修复文件 |
|------|------|----------|
| BUG-12 | 并发登录 Internal Server Error — `get_async_session` 每次创建新 engine 导致连接池耗尽 | `session.py`、`auth.py`、`deps.py` |

#### 稳定性缺陷修复（5 项）

| 编号 | 级别 | 问题 | 修复文件 |
|------|------|------|----------|
| STAB-01 | P1 | `_PLAY_TRACES`/`_PLAY_STATUS_RECENT_FAILURE`/`_INVITE_ENDPOINT_HINTS` 无界字典增长 | `_shared.py` |
| STAB-02 | P1 | `audit_center_service._push_to_external_siem` 每次调用创建新 `httpx.AsyncClient` | `audit_center_service.py` |
| STAB-03 | P0 | `_probe_zlm_stream` 缺少 `await get_http_client()`，流探测始终失败 | `_shared.py` |
| STAB-04 | P0 | `_wait_zlm_stream_ready` 2-tuple 解包 vs 3-tuple 返回值不匹配 | `_shared.py` |
| STAB-05 | P2 | `_node_clients` 字典无定期清理，媒体节点移除后客户端残留 | `zlm_rtp_server_service.py` |

### 变更

- 全局字典改用 `OrderedDict` + 容量上限 + TTL 过期（`_shared.py`）
- 审计 Webhook 改用共享 `httpx.AsyncClient`（`audit_center_service.py`）
- 媒体节点客户端定期清理失效连接（`zlm_rtp_server_service.py`）
- `get_async_session` 修复为复用全局 engine，不再每次创建新引擎（`session.py`）

### 文档

- 更新《功能可用性审计报告》至第五轮（30 项功能逐一验证，BUG-01~11 全量回归）
- 更新《压力测试报告》至 v1.1（含 IP 防护说明、畸形 SIP 探活修复）
- 新增《稳定性加固报告》（5 项稳定性缺陷修复详情）
- 新增《修复日志》（12 项 BUG 修复全过程记录）

---

## [1.0.0] — 2026-07-03

PyGBSentry 开源版首个正式发布版本。

### 新增

#### 稳定性加固（15 项）
- 系统设置缓存 LRU 驱逐机制（`settings_cache.py`，上限 500 条）
- SIP Keepalive 缓存 LRU 驱逐机制（`storm_handler.py`，上限 15000 条）
- 进程内存增长监控与自动缓存清理（`health_service.py`，每 30s 采样 RSS，增长超 500MB 触发清理）
- 日志 WebSocket 死连接自动清理 + 心跳检测（`logs.py`）
- SIP 追踪 WebSocket 死连接自动清理 + 心跳检测（`sip_trace_ws.py`）
- 数据库连接健康检查与指数退避重连（`session.py`，1s→2s→4s→8s→16s，最多 5 次）
- SIP TCP 客户端 stale 连接定期清理（`server.py`，每 5s）
- RTP 流超时通过 WebSocket 实时通知前端（`hook.py`）
- 磁盘空间监控与录像保护（`health_service.py`，95% 停止录像，85% 警告，80% 恢复）
- 全局并发 INVITE 信号量限制（`invite.py`，默认上限 200）
- 统一异常响应格式，生产环境不暴露堆栈（`main.py`、`exceptions.py`）

#### 新增配置项
- `MEMORY_GROWTH_ALERT_THRESHOLD_MB`（默认 500）
- `MEMORY_ABSOLUTE_ALERT_THRESHOLD_MB`（默认 2048）
- `DISK_SPACE_MONITOR_ENABLED`（默认 True）
- `DISK_SPACE_CRITICAL_THRESHOLD`（默认 95）
- `DISK_SPACE_WARNING_THRESHOLD`（默认 85）
- `DISK_SPACE_RECOVERY_THRESHOLD`（默认 80）
- `SIP_INVITE_MAX_CONCURRENT`（默认 200）

#### 压力测试工具
- 并发设备注册测试脚本（`concurrent_register_test.py`）
- 并发用户登录测试脚本（`concurrent_login_test.py`）
- 并发预览压力测试脚本（`concurrent_preview_test.py`）
- 72 小时耐久监控脚本（`endurance_monitor.py`）
- 异常场景测试脚本（`exception_scenario_test.py`）
- 总运行脚本（`run_all_tests.py`）

### 修复

#### P0 级修复（阻塞性 BUG）
- **报警 WebSocket 推送参数缺失**：`broadcast_alarm()` 调用缺少 `tenant_id` 参数导致 `TypeError`，所有 WebSocket 客户端无法收到报警实时推送（`handlers.py`、`vision_hub.py`）
- **语音广播音频编码不匹配**：前端发送 PCM 16bit LE，后端直接封装 RTP 但 SDP 协商为 G.711A(PCMA)，设备无法解码。新增 `pcm16le_to_alaw()` 编码转换函数（`talk.py`）

#### P1 级修复（重要功能缺陷）
- **双向对讲前端缺少接收方向**：`TalkButton.vue` 新增 WHEP 拉流播放逻辑，通过 `RTCPeerConnection` 接收设备回传音频
- **RTP 端口租约泄漏**：孤儿租约清理延迟从 5 分钟降至 2 分钟（`health_service.py`、`invite.py`）
- **ZLM 与 DB 状态不同步导致端口泄漏**：`MediaPortLease` 新增 `stream_id`/`app_name` 字段；修正 `cleanup_stale_leases` 中列名错误 `media_node_id` → `media_server_id`；使用 `stream_id` 精确关闭 ZLM RTP Server（`media_nodes_db.py`、`media_port_lease.py`）

#### P2 级修复（功能完善）
- **16x 倍速播放前端选项缺失**：`playbackSpeedOptions` 数组添加 16（`DeviceDetailDrawer.vue`）
- **H.265 码流 WebRTC 协议兼容性**：用户选择 WebRTC 播放 H.265 码流时显示兼容性警告（`AdvancedVideoPlayerDialog.vue`）
- **INVITE 并发无全局限制**：新增 `global_invite_semaphore` 全局信号量（`invite.py`、`config.py`）

#### P3 级修复（体验优化）
- **seek 操作无后端频率限制**：`PlaybackControl` 新增 per-call_id 的 seek 频率限制（1 秒间隔）（`playback_control.py`）
- **长 expires 设备离线检测延迟过长**：`DEVICE_OFFLINE_MAX_GRACE_SECONDS` 的 `getattr` 默认值从 1800 修正为 300，与 `config.py` 一致（`server.py`）

#### 数据库迁移
- 新增 Alembic 迁移：`g1a2b3c4d5e6_add_stream_id_to_media_port_leases.py`（为 `media_port_leases` 表添加 `stream_id` 和 `app_name` 列）
- 修复 `billing_plans` 表 schema 与模型不一致（补全 `price_yearly`、`description`、`sort_order` 列）

### 文档
- 新增《功能可用性审计报告》（30 项子功能逐一验证）
- 新增《修复日志》（11 项 BUG 修复详情）
- 新增《稳定性加固报告》（15 项加固措施）
- 新增《压力测试报告》（并发测试 + 耐久测试 + 异常场景测试）
- 已有《部署指南》（`docs/deployment.md`，629 行，覆盖 Docker/手工部署/Linux/Windows）

---

## [1.0.0-rc.1] — 2026-06-15

初始发布候选版本。
