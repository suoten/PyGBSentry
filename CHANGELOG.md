# CHANGELOG

所有重要变更均记录在此文件中。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [1.2.0] — 2026-08-22

两轮独立复审驱动的工业级质量加固：审计基线清零、前后端契约类型化、前端类型检查从 655 错误清零。

### 修复

#### 功能缺陷（复审发现）

| 编号 | 级别 | 问题 | 修复文件 |
|------|------|------|----------|
| FIX-A | P1 | SIP 3xx 重定向分支 UnboundLocalError（函数内局部导入遮蔽模块级导入），重定向功能静默失效 | `sip/response_handler.py` |
| FIX-B | P1 | `frontend-static-checks.yml` 使用 `npm ci` 但仓库无 package-lock.json，前端 CI 必然失败（统一为 pnpm） | `.github/workflows/frontend-static-checks.yml` |
| FIX-C | P2 | 通道类型标签读取 `.name` 但映射定义为 `nameKey`，ChannelGroup/ChannelList/ChannelRegion 类型列空白 | `ChannelGroup.vue`、`ChannelList.vue`、`ChannelRegion.vue` |
| FIX-D | P2 | DeviceList 组织下拉读取 `.name` 但 flattenOrgTree 返回 `{id,label}`，下拉空白 | `DeviceList.vue` |
| FIX-E | P2 | `parseDeviceChannelsResponse` 已异步化但 4 处调用未 await，运行时把 Promise 当数组 | `DeviceBatchOps.vue`、`DeviceRecords.vue` |
| FIX-F | P2 | 依赖双源漂移：uv.lock（无 pyproject 支撑）与 Dockerfile 使用的 requirements.txt 跨约 20 个 minor 版本，删除孤立 lockfile | `backend/uv.lock` |
| FIX-G | P3 | `ensure_embedded_media_node.py` 脚本引用未导入的 settings，手动运行必崩 | `scripts/ensure_embedded_media_node.py` |
| FIX-H | P3 | SmartVideoPlayer 向 H265Player 传未声明的 `video-url` prop，H265 分支收不到地址 | `SmartVideoPlayer.vue` |
| FIX-I | P3 | NativeHlsPlayer 调用未导入的 `t()`（运行时 ReferenceError）；Dashboard 读取不存在的 `is_superuser`（store 导出为 `isSuperuser`）；alarm store 调用不存在的 `logger.warning` | `NativeHlsPlayer.vue`、`Dashboard.vue`、`stores/alarm.ts` |
| FIX-J | P3 | 过时测试断言：catalog 重试间隔已从 [1,5,15] 优化为 [2,3,5]（2026-07-29 P0 变更），测试仍校验旧值 | `tests/test_security_hardening.py` |
| FIX-K | P0 | **监控端点并发雪崩**：`/ops/status` 每请求执行 `psutil.cpu_percent(interval=1)` 阻塞 1 秒 + 每请求独立探测 ZLM（不可达时 2s 超时），20 并发压测 91.5% 失败、P95 30s。改为非阻塞 CPU 采样 + 5s TTL 单飞缓存 + stale-while-revalidate。压测复验：QPS 0.6→510.7，P95 29861ms→368ms，成功率 17/200→200/200 | `api/v1/endpoints/ops.py` |
| FIX-L | P0 | **`/network/summary`、`/network/bandwidth` 并发放大**：每请求独立探测 ZLM，P95 19.2s。改为 5s TTL 单飞缓存 + stale-while-revalidate。压测复验：P95 19227ms→412ms，QPS 9.6→404 | `api/v1/endpoints/network.py` |

### 测试覆盖率工程（23.25% → ~50%，548 → 3700+ 测试）

三波并行测试补充（SIP 协议栈 / services 层 / API 端点 / core 工具 / 插件系统 / 流媒体端点 / main.py 中间件），
新增 52 个测试文件、约 3200 个测试。测试驱动发现并修复 **28 个真实缺陷**（摘要）：

**P0（功能完全不可用）**
- `POST /api/v1/devices` 必 500：Asset 无 domain 列但 kwarg 无条件传入
- 插件静态资源 404：`BACKEND_ROOT_DIR` 取 `parents[4]`（指向 app/ 而非 backend/）
- 许可证过期校验崩溃：naive/aware datetime 比较抛 TypeError（Python 验证路径）
- 流自愈探测从未生效：`should_probe_back_to_tcp_passive` 同类时区 bug 致循环整体失败被吞

**P1（关键功能失效）**
- 路由遮蔽 ×5：`PUT/DELETE /devices/directories`、`PUT /users/me`、`PUT /record-schedule/storage-config`、
  `POST /play/{sid}/switch` 与 `/playback/{cid}/pause|resume|seek|speed` 均被通配路由抢先匹配 → 修复方式：
  静态路径先注册/通配路由移至路由表末尾（devices/__init__.py、users.py、record_schedule.py、stream/__init__.py）
- 目录订阅 PUT 无成功路径：模型字段（enabled/expiry）与端点读取（cycle_seconds）及前端发送均不匹配
- 通道编辑必 500：`safe_auth_audit` 不存在的 `summary` 形参（正确名 `extra_summary`）
- 通道分页必 500：序列化读取 Resource 不存在的 manufacturer/model/owner 列
- 2FA 三端点必 500：`safe_auth_audit` 缺必填 `module` 参数（8 处）
- `GET /command/sessions` 必 500：open 会话 duration 计算混用 aware/naive
- `POST /ops/backup` 必 500：`normalize_db_type()` 缺必填参数
- `/media/cluster-status` 必 500（有节点时）：RuntimeMediaNode 缺 `is_online` 字段
- CSeq 持久化失效：导入不存在的 `redis_state.get_redis_state`，ImportError 被吞
- 广播看门狗资源泄漏：访问不存在的 `invite_state._invite_pending`，AttributeError 被吞（SSRC/会话泄漏）
- `send_session_refresh_reinvite` 回退分支参数顺序颠倒（proto/transport 错位）
- 422 处理器崩溃：pydantic v2 ValueError 对象直接进 JSONResponse → 500（新增递归清洗）
- SIP 行为缺陷：3xx 无 Contact 时双重 ACK；对讲 INVITE 4xx 不发 ACK（RFC 3261 §13.2.2.4）
- 流端点：download 缺 retryable 参数（TypeError）、`STREAM_PUBLIC_RTSP_PORT` 配置项不存在（3 处）、
  `/plugins/runtime/stream_health/health` UnboundLocalError、integrations 运行时状态永不落库（SQLAlchemy 变更检测失效）、
  `channel_play` 缺 background_tasks 参数、`channel_preset_query` 参数错位、rtp.py 局部导入遮蔽、vod.py 双前缀

**P2/P3**
- 非 SIP 事件分页 `has_more` 恒 False（14 处）、plugins upload 临时 zip 泄漏、CSV operator 未转义、
  日志行数 off-by-one、CORS 尾斜杠配置失效（Origin 规范化）、黑名单删除不存在 IP 返回 200、
  `_auto_blacklist_ip` 缓存不更新（每包重复查库）、`_resend_final` 不支持 sync sender、
  config_center validate hints 类型不符、health_service 空 key 未过滤

#### 质量加固

- **L1 审计落地**：实现缺失的 `app/core/audit_l1_schema_consistency.py`（Pydantic ↔ ORM 一致性检查，L101-L104 规则），`audit_run_all.py` 的 L1 调用不再崩溃且崩溃可被正确上报
- **L2 审计纠偏**：修复索引签名 `[key: string]` 误解析为 `key` 字段、SKIP hack 制造假阳性、`export type` 语法不识别三个缺陷；配对表从"展示接口↔请求载荷"的错误语义改为"展示接口↔响应模型"；配对未命中时输出 WARN 防止检测静默失效
- **L3 清零**：28 个 ERROR 级异常吞没全部修复（22 处收窄异常类型 + 6 处补日志）
- **响应契约类型化**：GET /devices、GET /alarms、GET /platforms 挂载 `response_model`（DeviceItem/AlarmItem/PlatformItem），含 NULL 列兜底（stream_mode/escalation 字段）防脏数据 500
- **前端类型清零**：655 个 vue-tsc 错误（strict 模式）全部修复，涉及 64 个文件；`npm run typecheck:ci` 通过
- **models.ts 契约修正**：TS 接口与后端实际响应对齐（BillingPlan `price`→`price_monthly`、Subscription `plan_id`→`plan_code`、CascadePlatform `server_id`→`server_gb_id`/`status`→`is_online` 等），移除全部死字段
- **ruff 清零**：74 个 lint 错误（含 F821/F811/F841）全部修复
- **工程卫生**：删除 frontend 根目录 19 个临时审计产物（`_*.log`/`_*.txt`/`_*.md`/`_check_*.js`）；`.env.example` 注释示例与默认值对齐

### 变更

- `frontend-static-checks.yml` open-source 前端任务统一使用 pnpm（与 ci.yml/CONTRIBUTING.md 一致）
- L2 审计新增 `PAIR_TS_NOT_FOUND`/`PAIR_PYDANTIC_NOT_FOUND` 警告类型

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
