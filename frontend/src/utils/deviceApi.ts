/** 解析 GET /api/v1/devices/{id}/channels 的响应：兼容裸数组与 { channels: [] } */
export function parseDeviceChannelsResponse(data: unknown): Record<string, unknown>[] {
  if (Array.isArray(data)) return data
  if (data && typeof data === 'object' && Array.isArray((data as { channels?: unknown }).channels)) {
    return (data as { channels: Record<string, unknown>[] }).channels
  }
  return []
}
