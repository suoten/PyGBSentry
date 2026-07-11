import { computed, type Ref } from 'vue'

export interface ChannelTreeStatsOptions {
  countableNodeTypes?: string[]
  statsVisibleNodeTypes?: string[]
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  isPlayableChannel?: (node: any) => boolean
}

export interface ChannelTreeStats {
  totalChannels: Ref<number>
  onlineChannels: Ref<number>
  offlineChannels: Ref<number>
  rebuildTreeNodeStats: () => void
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  shouldShowNodeStats: (node: any) => boolean
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  getNodeStats: (node: any) => string
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  getNodeStatsTone: (node: any) => string
}

export function useChannelTreeStats(
  _tree: Ref<unknown>,
  _options?: ChannelTreeStatsOptions
): ChannelTreeStats {
  const zero = computed(() => 0)
  return {
    totalChannels: zero,
    onlineChannels: zero,
    offlineChannels: zero,
    rebuildTreeNodeStats: () => {},
    shouldShowNodeStats: () => false,
    getNodeStats: () => '',
    getNodeStatsTone: () => '',
  }
}
