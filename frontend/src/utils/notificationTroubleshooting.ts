export function getNotificationFieldLabel(field: string): string { return field }
// FIX: [2026-07-10] 去掉 async — 原声明返回 Promise，调用方同步访问 .summary 等属性全为 undefined，
// 导致故障排查 UI 永不渲染 + 26 个 TS2339。桩函数返回 {} 无需 async。 [全栈工程师]
export function getNotificationTroubleshootingByPluginId(_pluginId: string): Record<string, unknown> { return {} }
