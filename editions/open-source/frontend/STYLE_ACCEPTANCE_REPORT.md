# 开源版前端样式重构验收单（Naive UI Admin 风格）

更新时间：2026-03-26

## 1. 目标与结论

- 目标：将开源版前端视觉统一到更现代、克制、语义化的风格（参考 Naive UI Admin），消除大面积历史硬编码色值与渐变。
- 结论：已完成主页面与核心交互页面的统一收口；`src/views` 中显著样式残留已大幅清理。
- 验证：多轮 `ReadLints` 与 `npm run build` 均通过。

## 2. 已完成统一（核心页面）

- `Dashboard.vue`
- `AlarmCenter.vue`
- `DeviceList.vue`
- `TvWall.vue`
- `MonitorCenter.vue`
- `ChannelManager.vue`
- `ChannelList.vue`
- `UserManager.vue`
- `Organizations.vue`
- `LegacyGateway.vue`
- `NetworkOverview.vue`
- `Operations.vue`
- `RecordSchedule.vue`
- `QueryFormSection.vue`
- `TableCard.vue`
- `PageContainer.vue`
- `AdvancedPtzControl.vue` 及 `ptz/*` 子组件

## 3. 统一原则（本次已执行）

- 颜色语义化：优先 `var(--el-color-*)`、`var(--el-text-color-*)`、`var(--el-border-color-*)`、`var(--el-fill-color-*)`。
- 卡片/容器统一：主卡片圆角与阴影层级趋于一致，减少夸张渐变。
- 表格统一：`n-data-table` 与旧表格共存场景下，表头、hover、fixed 列背景统一。
- 状态表达统一：success/warning/danger/info 使用语义色，不再散落 magic color。
- 交互统一：focus/hover 阴影与边框反馈使用主色体系。

## 4. 白名单保留项（非问题）

以下保留为业务或场景必需，不建议强行替换为通用变量：

- 深色视频/画布底色（如 `#0f172a`、`#111827`、`#0b1220`）：
  - 用于监控宫格、视频承载区、地图深色画布，属于功能型视觉约束。
- 半透明白色蒙层/面板（如 `rgba(255,255,255,0.92/.94)`）：
  - 用于地图/可视化浮层可读性控制，透明度本身有业务意义。
- 地图引擎绘制色（OpenLayers `Fill/Stroke`）：
  - 位于 `GisMap.vue`、`MobileCommand.vue`、`VisualCommand.vue`，用于图元区分与告警闪烁。
- 业务默认配置值：
  - `BillingCenter.vue` 的 `primary_color: '#1f2937'` 为品牌默认值（数据默认），非页面样式残留。

## 5. 后续可选优化（不影响当前交付）

- 将地图/可视化页中的绘制色抽象为“可视化主题常量”，集中管理（便于后续暗黑主题）。
- 对 `Login.vue` 的 SVG 渐变进行品牌化参数透出（可配置，而非写死）。
- 在 `style.css` 增补一组“可视化场景 tokens”（overlay/viewport/grid-border），减少页面内联样式重复。

## 6. 验收建议

- 功能回归优先页：
  - 设备管理、告警中心、电视墙、监控中心、通道管理、运维中心。
- 视觉回归重点：
  - 表格 fixed 列遮罩与 hover 一致性；
  - 弹窗头部/工具条背景层级；
  - 状态点与状态标签语义色一致性；
  - 暗色视频区域与浅色控制区对比度。

## 7. 交付状态

- 样式统一：已完成。
- 语义变量替换：已完成主要路径。
- 编译与静态检查：通过。

