﻿export interface DeviceChannelData { channels?: unknown[]; total?: number; [k: string]: unknown }

/**
 * 解析设备通道 API 响应。
 *
 * 后端 /api/v1/devices/{gb_id}/channels 直接返回通道数组（非 {channels: [...]} 包装），
 * 而 /api/v1/devices/{gb_id}/channels/paged 返回 {items: [...], total: ...}。
 * 本函数兼容两种格式，统一返回通道数组。
 */
export async function parseDeviceChannelsResponse(res: unknown): Promise<unknown[]> {
  if (res == null) return []
  // 直接返回数组
  if (Array.isArray(res)) return res
  // {channels: [...]} 或 {items: [...]} 格式
  if (typeof res === 'object') {
    const obj = res as Record<string, unknown>
    // 嵌套 data 属性（某些 API 包装器格式）
    const inner = 'data' in obj ? obj.data : obj
    if (inner == null) return []
    if (Array.isArray(inner)) return inner
    if (typeof inner === 'object') {
      const innerObj = inner as Record<string, unknown>
      if (Array.isArray(innerObj.channels)) return innerObj.channels
      if (Array.isArray(innerObj.items)) return innerObj.items
    }
  }
  return []
}
