import { computed, type Ref } from 'vue'

export interface ChannelTreeStats { totalChannels: Ref<number>; onlineChannels: Ref<number>; offlineChannels: Ref<number> }

export function useChannelTreeStats(_tree: Ref<unknown>): ChannelTreeStats {
  const zero = computed(() => 0)
  return { totalChannels: zero, onlineChannels: zero, offlineChannels: zero }
}
