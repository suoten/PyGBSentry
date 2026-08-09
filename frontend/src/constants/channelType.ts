/** 通道类型标签映射（用于通道管理页面展示）。 */
// FIXED: 硬编码中文→i18n key
export const CHANNEL_TYPE_MAP: Record<
  number,
  { id: number; nameKey: string; style: Record<string, string> }
> = {
  1: { id: 1, nameKey: 'channelType.gbDevice', style: { color: '#409eff', borderColor: '#b3d8ff' } },
  2: { id: 2, nameKey: 'channelType.pushDevice', style: { color: '#67c23a', borderColor: '#c2e7b0' } },
  3: { id: 3, nameKey: 'channelType.pullProxy', style: { color: '#e6a23c', borderColor: '#f5dab1' } },
  200: { id: 200, nameKey: 'channelType.ministryDevice', style: { color: '#fa6436', borderColor: '#f4997c' } }
}

export const channelTypeTag = (dataType: number) =>
  CHANNEL_TYPE_MAP[dataType] || CHANNEL_TYPE_MAP[1]
