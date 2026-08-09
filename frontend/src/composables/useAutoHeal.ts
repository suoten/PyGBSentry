import { ref, computed } from 'vue'

/**
 * 自动修复(Auto-Heal)逻辑
 * 当播放器出错时自动尝试切换到其他可用播放器
 */
export function useAutoHeal() {
  const fallbackState = ref<Set<string>>(new Set())
  const autoHealAttempts = ref(0)
  const autoHealCooldownMs = 3000
  const autoHealLastAt = ref(0)
  const requestWaitingTimer = ref<ReturnType<typeof setTimeout> | null>(null)

  const maxAutoHealAttempts = 3

  function canAutoHeal(): boolean {
    const now = Date.now()
    if (now - autoHealLastAt.value < autoHealCooldownMs) return false
    if (autoHealAttempts.value >= maxAutoHealAttempts) return false
    return true
  }

  function recordFallback(playerType: string) {
    fallbackState.value.add(playerType)
    autoHealAttempts.value++
    autoHealLastAt.value = Date.now()
  }

  function resetAutoHeal() {
    fallbackState.value.clear()
    autoHealAttempts.value = 0
    if (requestWaitingTimer.value) {
      clearTimeout(requestWaitingTimer.value)
      requestWaitingTimer.value = null
    }
  }

  function hasTried(playerType: string): boolean {
    return fallbackState.value.has(playerType)
  }

  function scheduleWaitingHeal(callback: () => void, delayMs: number) {
    if (requestWaitingTimer.value) clearTimeout(requestWaitingTimer.value)
    requestWaitingTimer.value = setTimeout(() => {
      requestWaitingTimer.value = null
      callback()
    }, delayMs)
  }

  function clearWaitingTimer() {
    if (requestWaitingTimer.value) {
      clearTimeout(requestWaitingTimer.value)
      requestWaitingTimer.value = null
    }
  }

  return {
    fallbackState,
    autoHealAttempts,
    maxAutoHealAttempts,
    canAutoHeal,
    recordFallback,
    resetAutoHeal,
    hasTried,
    scheduleWaitingHeal,
    clearWaitingTimer,
  }
}
