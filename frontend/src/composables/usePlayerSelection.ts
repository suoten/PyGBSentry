import { ref, computed } from 'vue'

type PlayerType = 'webrtc' | 'jessibuca' | 'h265' | 'hls' | 'native'

interface PlayerOption {
  value: PlayerType
  label: string
  disabled?: boolean
}

/**
 * 播放器选择与偏好持久化
 */
export function usePlayerSelection(
  deviceId: { value: string },
  channelId: { value: string },
  hasWebrtc: { value: boolean },
  hasJessibuca: { value: boolean },
  hasH265: { value: boolean },
  hasHlsUrl: { value: boolean },
  jessibucaMixedContentRisk: { value: boolean },
) {
  const activePlayerType = ref<PlayerType>('jessibuca')

  const playerPrefStorageKey = computed(() => `player_pref_${deviceId.value}_${channelId.value}`)

  function getStoredPlayerType(): PlayerType | null {
    try {
      const stored = localStorage.getItem(playerPrefStorageKey.value)
      if (stored && ['webrtc', 'jessibuca', 'h265', 'hls', 'native'].includes(stored)) {
        return stored as PlayerType
      }
    } catch { /* ignore */ }
    return null
  }

  function savePlayerType(type: PlayerType) {
    try {
      localStorage.setItem(playerPrefStorageKey.value, type)
    } catch { /* cleanup: ignore */ }
  }

  const playerTypeOptions = computed<PlayerOption[]>(() => [
    { value: 'webrtc', label: 'WebRTC', disabled: !hasWebrtc.value },
    { value: 'jessibuca', label: 'Jessibuca', disabled: !hasJessibuca.value },
    { value: 'h265', label: 'H265', disabled: !hasH265.value },
    { value: 'hls', label: 'HLS', disabled: !hasHlsUrl.value },
  ])

  const preflightDecision = computed<PlayerType | null>(() => {
    // 自动避开混合内容风险
    if (jessibucaMixedContentRisk.value && hasWebrtc.value) return 'webrtc'
    if (hasJessibuca.value) return 'jessibuca'
    if (hasWebrtc.value) return 'webrtc'
    if (hasHlsUrl.value) return 'hls'
    return null
  })

  function selectPreferredPlayer(): PlayerType {
    const stored = getStoredPlayerType()
    if (stored) {
      const opt = playerTypeOptions.value.find(o => o.value === stored)
      if (opt && !opt.disabled) return stored
    }
    if (preflightDecision.value) return preflightDecision.value
    // fallback
    const firstAvailable = playerTypeOptions.value.find(o => !o.disabled)
    return firstAvailable?.value || 'jessibuca'
  }

  const currentPlayerLabel = computed(() => {
    const opt = playerTypeOptions.value.find(o => o.value === activePlayerType.value)
    return opt?.label || activePlayerType.value
  })

  return {
    activePlayerType,
    playerTypeOptions,
    preflightDecision,
    currentPlayerLabel,
    getStoredPlayerType,
    savePlayerType,
    selectPreferredPlayer,
  }
}
