export interface DeviceChannelData { channels?: unknown[]; total?: number; [k: string]: unknown }

export async function parseDeviceChannelsResponse(res: unknown): Promise<DeviceChannelData> {
  if (res && typeof res === 'object' && 'data' in res) {
    const data = (res as Record<string, unknown>).data
    if (data && typeof data === 'object') return data as DeviceChannelData
  }
  return { channels: [], total: 0 }
}
