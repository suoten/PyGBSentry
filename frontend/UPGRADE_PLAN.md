# PyGBSentry Frontend 升级方案（商业化视觉与体验）

> 说明：本文是**升级/迁移计划**，其中的 `- [ ]` 表示“尚未迁移/尚未落地”的 backlog 条目，**不是**文档缺内容或占位未写完。  
> 回填规则：每完成一个页面迁移或一个波次，请在条目旁补“完成日期 + 证据（截图/录屏/PR/commit）+ 关键路径（成功/失败各 1 条）”，并将条目改为 `[x]`。

## 目标

- 统一视觉语言与交互规范，使新页面“自然长相一致”
- 提升关键路径效率与稳定性（登录→设备→预览→告警）
- 降低维护成本：减少页面级样式与重复逻辑，增强可复用能力

## 当前问题概览（代码现状对应）

- 视觉体系不收口：Element Plus + Tailwind + 大量全局覆写并行，导致页面间密度、间距、字号层级不一致
- UI 框架策略不明确：依赖中存在未使用/不明确使用边界的 UI 组件库，放大风格漂移风险
- 全局体验能力薄弱：用户/权限/主题/布局偏好分散在 localStorage 与页面内状态中，缺少统一规范（加载、空、错、无权限）
- 路由/菜单/能力源多处维护：插件/付费能力在路由与壳层逻辑双维护，存在长期一致性风险
- 工程卫生问题：`src/` 存在 `.vue.js` 镜像文件风险，影响构建稳定性

## 升级原则

- 单一数据源：路由/菜单/能力控制统一由 capability 定义驱动
- 组件化收口：以通用页面骨架组件承载规范（标题/筛选/工具栏/表格/状态页）
- 令牌化（Design Tokens）：颜色、间距、字号、圆角、阴影等基础能力统一管理
- 先止血后优化：P0 先保证可构建、可发布与可回归，再做视觉与体验升级

## 实施步骤（分步执行与打勾）

- [x] S0：工程卫生止血（`.vue.js` 镜像清理 + 忽略规则）（已完成 2026-03-31）
- [x] S1：建立 views 全量清单与波次归类（本文档维护唯一版本）（已完成 2026-03-31）
- [x] S2：落地 Design Tokens（spacing/typography/radius/shadow）并接入全局样式（已完成 2026-03-31）
- [x] S3：升级通用页面骨架组件并固化规范（PageContainer/PageHeader/TableCard/QueryFormSection/TableToolbar/State）（已完成 2026-03-31）
- [ ] S4：波次 A 迁移（管理/列表/配置类页面）
- [ ] S5：波次 B 迁移（仪表盘/详情/综合中心类页面）
- [ ] S6：波次 C 迁移（监控预览/录像/电视墙等视频重页面）
- [ ] S7：波次 D 迁移（地图/可视化指挥/移动端页面）
- [ ] S8：全局体验统一（auth/user/permission/uiPrefs/pluginCapabilities + 状态页/权限态/错误态）
- [ ] S9：主题/可访问性/性能收尾（明暗主题、焦点与键盘、资源释放与性能）

### 如何给页面/波次打勾（统一口径）

单个页面可被标记为 `[x]` 的最低条件（Definition of Done）：

- [ ] 页面已切到统一页面骨架组件（`PageContainer/PageHeader/TableCard/QueryFormSection/TableToolbar/State`）之一或组合
- [ ] 页面级样式不再“自造密度/字号层级”，只使用 design tokens / 统一类名（允许少量业务特例，但需能解释为什么不能复用通用组件）
- [ ] 页面加载/空/错/无权限态使用统一组件或统一规范（不得各页面自造一套）
- [ ] 页面路由入口与菜单可见性受同一 capability / permission 口径控制（避免“菜单看得到但点进来 403/白屏”）
- [ ] 关键交互路径可回归：至少包含 1 条“成功链路” + 1 条“失败链路”（失败提示口径统一，不直读后端 raw detail）

波次 S4~S7 可被标记为 `[x]` 的最低条件：

- [ ] 该波次清单中 **所有**页面均达到“页面打勾条件”
- [ ] 该波次挑选的 2~3 个最高频页面补齐回归用例（手工或脚本均可，要求可复现）

## 页面波次清单（src/views 全量覆盖）

### 波次 A：管理/列表/配置（高覆盖、低风险）

- [ ] AccountSecurity.vue
- [ ] AlarmLinkRules.vue
- [x] AlarmNotifications.vue（已完成 2026-04-06）
- [ ] ApiKeyManager.vue
- [ ] AppLogs.vue
- [ ] AssetManagement.vue
- [ ] AuditCenter.vue
- [ ] BillingCenter.vue
- [ ] CascadePlatforms.vue
- [ ] ChannelGroup.vue
- [x] ChannelList.vue（已完成 2026-03-31）
- [x] ChannelManager.vue（已完成 2026-03-31）
- [ ] ChannelRegion.vue
- [ ] ConfigCenter.vue
- [x] DeviceList.vue（已完成 2026-03-31）
- [ ] Organizations.vue
- [ ] PullProxyList.vue
- [ ] PushStreamList.vue
- [ ] RecordSchedule.vue
- [ ] ReleaseCenter.vue
- [ ] UserManager.vue

### 波次 B：仪表盘/概览/详情/综合中心

- [ ] AlarmCenter.vue
- [ ] Dashboard.vue
- [ ] HealthDashboard.vue
- [ ] Help.vue
- [ ] LicenseCenter.vue
- [ ] NetworkOverview.vue
- [ ] Operations.vue
- [ ] PluginCenter.vue
- [ ] PluginDetail.vue
- [ ] SlaDashboard.vue
- [ ] SetupWizard.vue

### 波次 C：视频与监控重页面（稳定性优先）

- [ ] CloudRecords.vue
- [ ] MonitorCenter.vue
- [ ] PluginRuntime.vue
- [ ] TvWall.vue

### 波次 D：地图/可视化/移动端与占位

- [ ] AiVisionPlaceholder.vue
- [ ] BehaviorRecognitionMobile.vue
- [ ] FaceRecognitionMobile.vue
- [ ] GisMap.vue
- [ ] LegacyGateway.vue
- [ ] MapProviders.vue
- [ ] MiniProgramPlaceholder.vue
- [ ] MobileAppPlaceholder.vue
- [ ] MobileCommand.vue
- [ ] PlateRecognitionMobile.vue
- [ ] ReportPlaceholder.vue
- [ ] SuitePlaceholder.vue
- [ ] VisualCommand.vue
- [ ] VisualCommandPlaceholder.vue
- [ ] WorkOrders.vue

### 系统页（不计入波次迁移，但同样需要统一观感）

- [ ] Login.vue
- [ ] Register.vue
- [ ] NotFound.vue

## 分阶段计划与验收

### P0：工程稳定性与卫生（交付底座）

- [x] 清理 `src/**/*.vue.js` 镜像文件，并新增忽略规则，保证 `npm run build` 稳定通过（已完成 2026-03-31）
- [ ] 明确发布产物策略：是否提交 `dist/`、如何产出与发布（建议产物不入库，走构建产出）
- [x] 清理不使用/边界不清的依赖，形成“唯一 UI 主框架”决策与执行准则（已完成 2026-04-11）

验收口径：
- `npm run build` 在干净工作区稳定通过
- 仓库中不再出现 `.vue.js` 镜像文件复现

### P1：视觉体系收口（设计系统落地）

- [x] 定义设计令牌（Design Tokens）：字号层级、间距、圆角/阴影等，并接入全局样式（对应 `S2`，已完成 2026-03-31）
- [x] 升级通用页面组件：PageContainer/PageHeader/TableCard/QueryFormSection/TableToolbar/State（对应 `S3`，已完成 2026-03-31）
- [ ] 补齐通用状态页/骨架的覆盖面：`EmptyState/Skeleton` 在高频页面落地并形成复用惯例（不要求一次性全量替换）
- [ ] 制定页面布局规范：标题区/筛选区/工具栏/表格区/分页区的默认结构与间距，并在波次 A 的页面迁移中强制执行

验收口径：
- 选取 3 个高频列表页完成规范化改造，视觉与交互一致
- 新增一个列表页无需复制大段样式即可达到统一观感

### P2：体验一致性（全局能力统一）

- [ ] 建立全局状态域：auth/user/permission/uiPrefs/pluginCapabilities
- [ ] 统一加载/空/错/无权限态组件与规范，并替换高频页面的自定义实现
- [ ] 路由与侧栏菜单由 capability 单一来源生成，避免双维护

验收口径：
- 核心路径（设备→预览→云台→录像）反馈一致，错误提示一致
- 菜单可见性、路由可达性与能力拦截一致，无“入口存在但不可用”边界问题

### P3：商业化完善（主题、可访问性、性能）

- [ ] 主题系统闭环：明/暗、品牌色、持久化、地图/视频区域对比度一致
- [ ] 可访问性基础：焦点态、键盘可达、对比度、表单可读性
- [ ] 性能与稳定性：KeepAlive 白名单、资源释放、列表性能优化、关键路径埋点与错误上报

验收口径：
- 支持主题切换与持久化，关键页面在明暗主题下可用且对比度合格
- 关键页面交互无明显卡顿，资源占用可控且可回归

## 建议的样板间页面（优先改造）

- 登录与安装向导
- 设备列表与设备详情
- 监控预览与云台控制
- 告警中心
- 录像检索/回放
- 插件中心
- 地图页面

---

## 附：页面迁移记录模板（建议复制到每个页面条目旁）

> 用法：对每个页面迁移，在条目后追加一行“记录块”，避免只打勾不留证据。
>
> 示例（写法示意，不强制格式）：
> - [x] DeviceList.vue（已完成 2026-03-31）
>   - 证据：截图/录屏/PR/commit
>   - 关键路径：成功/失败各 1 条
>   - 备注：本页特例与原因
