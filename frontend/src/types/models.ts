/**
 * 核心业务类型定义 — 消除 ref<Record<string, unknown>>
 *
 * NOTE: 各接口中的 `[key: string]: unknown` 索引签名是为了兼容后端返回的动态/扩展字段。
 * 长期目标：逐步将动态字段显式声明到接口中，移除索引签名。
 * 当前保留以确保不破坏现有动态属性访问代码。
 */

// ── 设备与通道 ──

export interface Device {
  id: string
  gb_id: string
  name: string
  ip_addr?: string
  port?: number
  status?: number
  manufacturer?: string
  model?: string
  register_time?: string
  last_keepalive?: string
  heartbeat_interval?: number
  heartbeat_count?: number
  keepalive_interval?: number
  channel_count?: number
  tenant_id?: string
  organization_id?: string
  transport?: string
  firmware?: string
  expires?: number
  domain?: string
  charset?: string
  ssrc_check?: boolean
  geo_coord_sys?: string
  as_message_channel?: boolean
  stream_mode?: string
  created_at?: string
  updated_at?: string
  [key: string]: unknown
}

export interface Channel {
  id: string
  gb_id: string
  name: string
  device_id: string
  device_gb_id?: string
  status?: number
  stream_type?: string
  default_stream_type?: string
  manufacturer?: string
  model?: string
  longitude?: number
  latitude?: number
  ptz_type?: number
  parent_id?: string
  parent_gb_id?: string
  civil_code?: string
  node_type?: string
  has_audio?: boolean
  capabilities?: Record<string, unknown>
  [key: string]: unknown
}

// ── 树节点 ──

export interface TreeNode {
  id: string
  label: string
  nodeType?: string
  children?: TreeNode[]
  [key: string]: unknown
}

// ── 报警 ──

export interface Alarm {
  id: string
  device_id?: string
  channel_id?: string
  alarm_type?: string
  priority?: string
  description?: string
  time?: string
  status?: number
  [key: string]: unknown
}

// ── 录像 ──

export interface VideoRecord {
  id: string
  device_id?: string
  channel_id?: string
  start_time?: string
  end_time?: string
  duration?: number
  file_path?: string
  file_size?: number
  [key: string]: unknown
}

// ── 插件运行时 ──

export interface PluginRuntimeRow {
  id?: string | number
  name?: string
  status?: string
  enabled?: boolean
  [key: string]: unknown
}

// ── 计费 ──

export interface BillingPlan {
  id: string
  name: string
  price?: number
  currency?: string
  [key: string]: unknown
}

export interface Subscription {
  id: string
  plan_id?: string
  status?: string
  [key: string]: unknown
}

export interface Order {
  id: string
  order_no?: string
  status?: string
  amount?: number
  created_at?: string
  [key: string]: unknown
}

export interface License {
  id: string
  plugin_id?: string
  status?: string
  expires_at?: string
  [key: string]: unknown
}

// ── 级联 ──

export interface CascadePlatform {
  id: string
  name: string
  server_id?: string
  server_ip?: string
  server_port?: number
  status?: string
  [key: string]: unknown
}

// ── 推拉流 ──

export interface StreamProxy {
  id: string
  name?: string
  src_url?: string
  status?: string
  [key: string]: unknown
}

export interface StreamPush {
  id: string
  name?: string
  dst_url?: string
  status?: string
  [key: string]: unknown
}

// ── 录像计划 ──

export interface ScheduleItem {
  id: string
  name?: string
  [key: string]: unknown
}

// ── 电视墙 ──

export interface TvWallScreen {
  id: string
  channel_id?: string
  channel_name?: string
  [key: string]: unknown
}

// ── 会商 ──

export interface ConferenceSession {
  id: string
  status?: string
  [key: string]: unknown
}

// ── 诊断 ──

export interface DiagResult {
  step?: string
  status?: string
  message?: string
  [key: string]: unknown
}

// ── 审计日志 ──

export interface AuditLog {
  id: string
  audit_id?: string
  module?: string
  action?: string
  operator?: string
  result?: string
  summary?: string
  time?: string
  created_at?: string
  [key: string]: unknown
}

// ── API Key ──

export interface ApiKey {
  id: string
  name?: string
  key_prefix?: string
  created_at?: string
  [key: string]: unknown
}

// ── 工单 ──

export interface WorkOrder {
  id: string
  title?: string
  status?: string
  [key: string]: unknown
}

// ── 资产 ──

export interface AssetLedger {
  id: string
  name?: string
  [key: string]: unknown
}

export interface MaintenanceRecord {
  id: string
  asset_id?: string
  [key: string]: unknown
}

// ── 结构化事件 ──

export interface StructuredEvent {
  id: string
  event_type?: string
  device_id?: string
  channel_id?: string
  event_time?: string
  payload?: string
  [key: string]: unknown
}

// ── 配置 ──

export interface PluginConfig {
  [key: string]: unknown
}
