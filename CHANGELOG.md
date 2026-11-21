# CHANGELOG

所有重要变更均记录在此文件中。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [Unreleased]

### 新增

- **API 契约稳定承诺**（路线图 Phase2 收官）：新增 `tests/test_api_contract.py` + 基线 `tests/api_contract_baseline.json`（/api/v1 全部 533 路径/605 端点的 path→method 快照），CI 强制"**只增不减**"——删除已发布端点或移除 HTTP 方法会使 CI 失败（守卫自身带负向单测）；破坏性变更须经弃用周期后用 `scripts/update_api_contract_baseline.py` 刷新基线并在 CHANGELOG 公告。配套 `docs/API_CONTRACT.md` 面向集成者的兼容性口径说明
- **分享/嵌入一键生成**（路线图 Phase2，解决 wvp #2033/#1846 类 iframe 痛点）：新增 `POST /api/v1/embed/links`（登录用户为通道签发长周期 HMAC 嵌入令牌，默认 24h、上限 `STREAM_EMBED_MAX_TTL_HOURS`=7 天，返回嵌入页 URL + iframe 代码）与 `POST /api/v1/embed/resolve`（嵌入页用令牌按需触发点播、等流就绪后换发 300s 短周期 playToken 的 flv/hls 地址——长周期凭证不进入媒体路径）；新增无框嵌入播放页 `GET /embed/play`（flv.js→hls.js→原生 HLS 降级，CDN 可自托管替换），安全头中间件对该路径豁免 X-Frame-Options（页面无敏感数据，令牌把关）。play_token 引入 scope 隔离（embed/play 互不可用，旧载荷兼容）；前端播放对话框工具栏新增「分享/嵌入」按钮（输入有效时长→生成并自动复制 iframe 代码）
- **对讲厂商模式自动探测**（路线图 Phase2）：`BROADCAST_PRE_MESSAGE_ENABLED` 开启后不再需要按厂商手工区分——平台对每台设备自动学习其对标准 Broadcast MESSAGE 流程的支持：200 确认→继续前置；4xx/6xx 拒绝→记忆 24h 后续直接 INVITE；超时→记忆 1h 避免每次喊话干等（周期性重探测）。行为测试覆盖三场景。配套 `docs/TENANCY.md` 多租户使用指南（租户模型/角色体系/典型场景/FAQ）
- **部署体检**（路线图 Phase1）：新增 `GET /api/v1/network-diagnostics/deployment-check`（admin），一键全面检查部署环境——SIP 信令服务、数据库/Redis 连通与延迟、设备概况（总数/在线）、流媒体节点逐个探测（含 secret 匹配失败识别）、对外播放地址（内网地址告警 + 可选公网出口 IP 对比）、收流模式与防火墙提示、安全基线（SECRET_KEY/OpenAPI 文档暴露/CORS，只报状态不泄露密钥）、关键后台任务启用状态、CPU/内存快照；每项 ok/warn/fail + 双语结论与修复指引。前端运维中心新增「部署体检」标签页与报告面板
- **兼容性文档：厂商特性开关**（`docs/COMPATIBILITY.md`）：整理大华喊话 MESSAGE 前置、可信内网心跳地址回写、NVR 目录 OFF 状态忽略、协议版本、设备级 TCP/UDP 收流策略等兼容开关的适用场景与默认值
- **播放失败一键自诊断**（路线图 Phase1，源自 wvp 456 个 issue 分析——"收流超时/播放失败"占 1/4 且用户难以描述根因）：新增 `POST /api/v1/network-diagnostics/diagnose-play`，把播放链路拆成六道关卡逐项检查（设备注册与租户归属、信令地址、平台 SIP 传输/设备 TCP 可达、流媒体节点可达+secret 匹配、对外播放地址是否内网、SSRC 余量），每项返回 ok/warn/fail + 中英双语结论与修复指引，汇总为 ok/warning/blocked 判定；前端 `AdvancedVideoPlayerDialog` 播放失败界面新增「运行播放诊断」按钮与检查面板（覆盖 ChannelManager/ChannelList/DeviceDetailDrawer 三处播放入口）。配套公开产品路线图 `docs/ROADMAP.md`
- **产品路线图**：新增 `docs/ROADMAP.md`，基于对同类项目 456 个公开 issue 的用户画像/痛点分析制定 Phase1-3 计划并公开进展

### 修复
- **P0 定时录制无看门狗静默丢录像**（对照 wvp-GB28181-pro #2145）：`record_schedule_executor` / `auto_record` 此前只维护本地 `is_recording` 标志，ZLM 重启或流闪断重连后录制已死但标志仍为 True，任务期内不会重发 `startRecord`。新增周期性 ZLM `isRecording` 校验（`RECORD_SCHEDULE_VERIFY_INTERVAL_SECONDS`，默认 60s，下限 30s），发现录制中断立即重启录制自愈；重启失败翻转标志交由标准 start 路径记账重试
- **P0 级联目录变更通知体系未接通**（对照 wvp #2246/#1779/#2138/#1725）：
  - `push_catalog_incremental` 此前为死代码（零调用方），设备上下线走全量重推。现已重写并接线：Event 取值扩展为 Add/Del/Update/ON/OFF（GB28181-2016 §A.2.5）；按 `PlatformCatalogResource` 应用虚拟目录重映射（不向上级泄漏真实 gb_id）；ON/OFF 未携带完整字段时按平台租户回查 Resource 补齐；按 `PLATFORM_CATALOG_BATCH_SIZE`（默认 100）分批发送
  - 新增 `_CatalogChangeDebouncer`（`CATALOG_NOTIFY_DEBOUNCE_SECONDS`，默认 15s）：设备注册不再触发全量重推，改为防抖聚合的增量 ON 通知；设备离线从"完全不通知"改为增量 OFF 通知（修复上级侧状态滞留 ON）；`catalog.py` 同步入库时收集 Add/Update/Del 变更（Update 做内容比对去噪，周期刷新未变化的通道不产生通知），提交后交防抖器增量 NOTIFY；接收端 `handle_catalog_notify_items` 原生支持上述全部 Event 取值，双端互操作闭环
  - 上级主动推送目录默认不再把全目录塞单条报文（原先 `catalog_batch_size<=0` → 单条，数千通道超 MTU 上级收不到），与入站路径对齐默认 100 条/批
  - 入站目录查询的分批推送加单批异常保护：单批发送失败记录告警并继续后续批次，不再整目录中断
- **P1 安全**：`GET /api/v1/apps/remote-config` 补登录鉴权（原匿名可读插件套件远程配置 JSON）

- **P1 设备录像查询自动翻页**（对照 wvp #2232 补强）：`sip_record.query_device_record` 支持 RecNum/PageNum 但两个查询端点写死 `page_num=1`，设备按 50 条/页返回时只会标 partial 永远不取第 2 页。新增后台自动翻页：首页收满且静止（4s 无新增）后逐页续查合并回首个 SN 缓存（内存+Redis），轮询方无感知；防死循环三重护栏（去重后无新增即停、单查询最多 100 页、整体 120s 预算）；异步查询进度改用 `last_activity_at` 计算，翻页推进中不再误判 partial
- **P1 级联预置位查询转发**（对照 wvp #1549）：上级的 PresetQuery/HomePosition 查询（`<Query>` 根）此前只回 200 存库不转发，上级永远查不到下级通道预置位。新增 `forward_cascade_preset_query` 转发真实设备 + `forward_cascade_preset_response` 按 SN 映射回传（SN/DeviceID 字符串级替换，保留厂商响应全部其他元素，虚拟通道 ID 反向映射防止泄漏真实 gb_id）；映射表随既有 prune 清理
- **P1 级联注册独立鉴权账号**（对照 wvp #1507）：`ParentPlatform` 新增 `auth_username` 列（schema_upgrade 自动迁移），Digest 鉴权用户名支持独立配置，空=沿用 client_gb_id 与旧行为一致；API create/update/list/runtime 全链路 + 前端级联平台表单（中英文案）支持
- **P1 喊话标准 MESSAGE 前置流程**（对照 wvp #2268/#2265 大华兼容）：新增 `Broadcast.send_broadcast_message`（GB28181 §9.2.1 Broadcast MESSAGE + 事务层响应等待），`BROADCAST_PRE_MESSAGE_ENABLED`（默认关闭）开启后 `/stream/broadcast/start` 先发 MESSAGE 等设备确认再走既有 INVITE；MESSAGE 结果不影响 INVITE 继续（兼容前置而非硬性握手）。对讲（talk, s=Play）流程不受影响
- **P2 TCP 设备 BYE 等待响应**（对照 wvp #2216 弱化版）：`send_bye` 的响应等待原先仅 UDP，TCP 设备 BYE 走 fire-and-forget，设备未确认就清理会话，残留旧对话可致新 INVITE 被 486 Busy 拒绝。响应匹配按 Call-ID/CSeq 与传输无关，去掉 UDP-only 限制（TCP 下事务层只发一次不重传，条目由 prune 兜底）
- **P2 心跳地址可选回写**（对照 wvp #2160 同源补强）：新增 `SIP_KEEPALIVE_ADDR_UPDATE_ENABLED`（默认关闭，保持"心跳不改地址"的防劫持语义）。可信内网/NAT 重映射且设备不重注册的场景开启后，心跳地址与注册地址不同才回写设备表，点播 INVITE 首发即命中新地址（多目标重试+成功回写仍保留为第二道兜底）
- **P2 幽灵流周期对账**（对照 wvp #2135 部分）：新增 `stream_ghost_reconcile` 后台任务（默认开启，300s 周期）。聚合 ENV+DB 两个节点源的 getMediaList，仅取 GB RTP 推流（`originTypeStr=rtp_push`，RTMP 推送通道等排除），与 StreamSession 按 (app, stream) 对账；无会话的流持续超过宽限期（`STREAM_GHOST_RECONCILE_GRACE_SECONDS`，默认 90s，容忍 INVITE 建会话与首包到达的竞态）后强制 `close_stream` 回收端口与带宽；行为测试覆盖宽限门控/有主流保留/非 RTP 排除/候选清理
- **P0（closed-issue 审计新发现）17 个后台任务模块未接线，整体从未运行**：`migrate_plugins.py` 把任务从 plugins/ 迁入 services/tasks/ 时剥掉了 HOOK_ON_STARTUP/register() 启动接线且未补——`record_schedule_executor`（录制计划执行器）、`auto_record`、`stream_idle`（空闲流回收）、`snapshot_refresh`（定时截图）、`pull_proxy_monitor`（拉流代理自愈）、`stream_health`、`ptz_tour`、`event_bridge` 等 17 个模块的 `start()` 全仓零调用方，此前两轮修复的录制看门狗/断流兜底也因此从未生效。已在 `task_manager` 统一接线（各模块自带 settings / plugin_runtime_config 开关仍生效，hook 型模块走 `register(pm)`）；真实启动烟雾测试 22 个任务全部启动并优雅停止。`ssl_certbot_renewer.py` 为 0 字节空文件未接线
- **P1（wvp #2097/#1907 同款）SSRC 三处泄漏修复**：①`_cleanup_once` 清理本地过期条目时同步 SREM Redis 集合（原先只清本地，Redis 残留蚕食 1 万序号空间后分配必 503）；②新增 Redis 周期对账——清除"本地桶与 DB StreamSession（含其他节点）均不存在"的孤儿 SSRC，多节点安全；③回放切片预取复用路径释放旧 SSRC（原先 BYE 旧会话+关流+释放端口租约但旧 SSRC 永不释放，每小时预取泄漏一个）
- **P1（自研缺陷）录制流名全链路不匹配**：GB 点播流在 ZLM 的名字是 `{channel_id}_{ssrc}`（invite.py:2320-2323），而录制计划执行器、自动录制、force-start/force-stop 端点一律用 `Resource.gb_id` 匹配 getMediaList 与调用 startRecord/stopRecord/isRecording——永远打不到真实流，录制计划即使接线后也不会生效。新增 `services/recording_guard.py`（`channel_stream_matches` 严格规则：全等或 `{gb_id}_{纯数字SSRC}` 后缀，避免下划线命名误匹配），执行器建立全名+通道前缀双索引并全链路改用真实流名
- **P1（wvp #1943/#1744 同款）录制中的流豁免无人观看断流/空闲回收**：`on_stream_none_reader` 与 `stream_idle` 对录制计划执行中的流（`recording_guard.is_stream_recording`）豁免断流，避免观众退出导致 MP4 提前收尾产生大量短文件；配套在执行器"计划结束"路径主动 stopRecord+释放会话（关流+BYE），防止被豁免的流在计划结束后滞留
- **P1（wvp #1892 同款）预置位响应多包聚合（双路径）**：①本地查询——`catalog_data_manager` 对 PresetQuery/HomePosition 启用多包聚合（分包追加、静止窗口 1.5s 无新分包即收完），`/preset/query?remote=true` 此前发出命令立即返回 SN 且结果无人消费，现等待聚合结果解析为 preset_list 返回；②级联转发——`forward_cascade_preset_response` 原先首包即 pop 映射回传、后续分包全部丢弃（上级只能收到不完整列表），现按 SN 保留映射逐包聚合（PresetID 去重、真实通道 ID 反向替换），收满 SumNum 或静止窗口后一次性回传合并结果，prune 时取消挂起任务。行为测试覆盖：分包合并去重、占位条目竞态、静止窗口等待、SSRC 清理、流名匹配边界
- **P1（wvp #1417 同款）显式注销/离线注册联动通道离线**：`storm_handler` register 分支原先仅上线恢复通道，离线（expires=0）只置设备状态——而两条离线巡检只扫 `Asset.status==1` 的设备，注销设备的通道将永久滞留 ON。补齐离线分支按 asset_id 批量置通道离线
- **P1（wvp #1782 同款）级联目录 Item 补经纬度/真实地址**：三条推送路径（`_push_catalog` 全量、`_push_catalog_to_platform` 入站、`push_catalog_incremental` 增量）此前缺 `Longitude/Latitude`（上级地图全为 0）且 `Address` 是写死的占位符。新增 `_resource_geo_xml` 辅助：有坐标带 6 位小数经纬度、无坐标省略元素（不写 0），Address 用真实值，增量 Item 同时补 CivilCode
- **P1（wvp #2081 同款）音频端口通道识别与默认列表过滤**：依据 wvp 源码口径（GbCode 类型码 138=音频/广播能力，132=视频摄像机——绝不能当音频过滤），目录入库时类型码 138 通道在 capabilities 标记 `has_audio/enable_broadcast`；`AudioOut1/AudioIn` 等纯音频端口按名称识别标 `type=3`，默认通道列表（`api/common/channel.py` 两处，NULL 兼容）排除
- **P1（wvp #1940 同源）MobilePosition 时间容错解析**：原先仅支持严格 `%Y-%m-%dT%H:%M:%S`，带毫秒/时区/空格分隔的时间全部静默丢弃真实值换成当前时间。改为 `fromisoformat` + 多格式逐级解析，带时区的统一转 naive UTC 落库
- **P1（wvp #1902 同类）看门狗心跳阈值字段统一**：`device_watchdog` 原先读 `keepalive_interval`（全仓无写入点的建表默认列），运维经 API 修改 `heartbeat_interval` 后该路径仍按 60s 判定，长心跳周期设备被误判离线。改为优先 `heartbeat_interval`、回退 `keepalive_interval`
- **P1（wvp #1852 同款防护）回放重新点播前释放同通道旧会话**：`/playback/{device}/{channel}` 原先直接发新 INVITE 不清理旧回放会话，频繁拖动若走重新点播，设备侧会话数累积至上限（"Session number has reached the upper limit '10'"）。INVITE 前按通道前缀查询并释放旧 playback 会话；`/stream/stop` 停止回放时取消跨小时切片预取任务（`cancel_prefetch_task` 此前无调用方，任务最长滞留 3590s）
- **P1（wvp #2148/#2150 同类）nginx 反代补 ZLM 媒体路径**：`deploy/nginx/nginx-lb.conf` 新增 `pygbsentry_media` 上游与 `/(record|live|rtp|index/api)/` 反代（含 WS upgrade、关闭缓冲），缺这些 location 时按模板部署的用户云端录像播放/下载 404；`docs/deployment.md` 的 nginx 样例同步补充说明
- **P2 GB28181_VERSION 默认值对齐 README**：`2016` → `2022`（README 宣称「基于 GB/T 28181-2022 构建向下兼容 2016」，原先默认 2016 导致 SDP 缺 `a=track`；a=track 为附加属性行，2016 设备按 SDP 规范忽略未知 a= 行）

### 变更

- 新增配置项：`RECORD_SCHEDULE_VERIFY_INTERVAL_SECONDS`、`PLATFORM_CATALOG_BATCH_SIZE`、`CATALOG_NOTIFY_DEBOUNCE_SECONDS`、`BROADCAST_PRE_MESSAGE_ENABLED`、`BROADCAST_PRE_MESSAGE_TIMEOUT_SECONDS`、`SIP_KEEPALIVE_ADDR_UPDATE_ENABLED`、`STREAM_GHOST_RECONCILE_ENABLED`、`STREAM_GHOST_RECONCILE_INTERVAL_SECONDS`、`STREAM_GHOST_RECONCILE_GRACE_SECONDS`

### 部署与仓库清理（issue IKMFK8）

- **P0**：`backend/Dockerfile` 的 `COPY alembic.ini initial_data.py ./` 引用构建上下文中不存在的文件（`initial_data.py` 实际位于 `app/` 内，已随 `COPY app/` 复制），镜像构建必失败 → 改为 `COPY alembic.ini ./`
- **P0**：前端镜像构建报 `ERR_PNPM_IGNORED_BUILDS`：Dockerfile 用 `corepack prepare pnpm@latest` 会拉到 pnpm 12.x，其对未声明构建脚本的依赖直接报错 → 锁定 `pnpm@10.34.9`（与 `pnpm-lock.yaml` 的 lockfileVersion 9.0 兼容）；`package.json` 增加 `packageManager` 字段与 `pnpm.onlyBuiltDependencies`（放行 `@parcel/watcher`、`esbuild`、`vue-demi`）
- **P1**：README / README_EN / CONTRIBUTING / docs（INSTALL、INSTALL_DEPLOY、deployment、quickstart、DEPENDENCY_BASELINE）及 CI workflows 中残留 monorepo 路径 `editions/open-source`（本仓库根目录即平台根）→ 全部修正；`frontend-static-checks.yml` 删除引用不存在目录的 `server-frontend` / `open-source-mobile` job
- **P2**：移除 `docker-compose.yml` / `docker-compose.ha.yml` / `docker-compose.monitoring.yml` 已弃用的 `version: '3.8'` 键；`frontend/Dockerfile` 的 `from` 统一为大写 `AS` 消除 FromAsCasing 告警
- **P2**：打包与工具脚本残留路径修复：`PyGBSentrySetup.py` 解压后直接定位平台根；`check_plugin_display_metadata.py` / `check_runtime_coverage.py` 改为相对仓库根定位（后者兼容 `plugins/` 包形态）；`fix_exception_swallow.py` 移除硬编码本机盘符路径；`ops.py` 快速开始文案、`make_portable.py` / `build-green-package.*` 注释同步更新

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
