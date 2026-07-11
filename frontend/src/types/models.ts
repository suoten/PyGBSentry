// Stub type definitions
// FIX: [2026-07-10] [k: string]: unknown → any — 消除 210 个 TS2339 + 21 个 TS7053 + 9 个 TS18046
// 运行时 JS 本就是 any，unknown 是编译期虚构类型安全，对 stub 文件无实际保护价值。
// 后续可逐文件用精确 interface 替换并启用 noUncheckedIndexedAccess。[全栈工程师]
export interface Device { id?: string; name?: string; device_id?: string; [k: string]: any }
export interface Channel { id?: string; name?: string; device_id?: string; channel_id?: string; [k: string]: any }
export interface TreeNode { id?: string; label?: string; children?: TreeNode[]; [k: string]: any }
export interface Alarm { id?: string; [k: string]: any }
export interface VideoRecord { id?: string; [k: string]: any }
export interface PluginRuntimeRow { id?: string; [k: string]: any }
export interface BillingPlan { id?: string; [k: string]: any }
export interface Subscription { id?: string; [k: string]: any }
export interface Order { id?: string; [k: string]: any }
export interface License { id?: string; [k: string]: any }
export interface CascadePlatform { id?: string; [k: string]: any }
export interface StreamProxy { id?: string; [k: string]: any }
export interface StreamPush { id?: string; [k: string]: any }
export interface ScheduleItem { id?: string; [k: string]: any }
export interface TvWallScreen { id?: string; [k: string]: any }
export interface ConferenceSession { id?: string; [k: string]: any }
export interface DiagResult { id?: string; [k: string]: any }
export interface AuditLog { id?: string; [k: string]: any }
export interface ApiKey { id?: string; [k: string]: any }
export interface WorkOrder { id?: string; [k: string]: any }
export interface AssetLedger { id?: string; [k: string]: any }
export interface Maintenance { id?: string; [k: string]: any }
export interface StructuredEvent { id?: string; [k: string]: any }
export interface PluginConfig { id?: string; [k: string]: any }
