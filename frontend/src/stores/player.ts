import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const usePlayerStore = defineStore('player', () => {
  const activePlayers = ref<Map<string, { app: string; stream: string; channelId: string }>>(new Map())

  function registerPlayer(id: string, info: { app: string; stream: string; channelId: string }) {
    activePlayers.value.set(id, info)
  }

  function unregisterPlayer(id: string) {
    activePlayers.value.delete(id)
  }

  function getPlayer(id: string) {
    return activePlayers.value.get(id)
  }

  function clearAll() {
    activePlayers.value.clear()
  }

  const playerCount = computed(() => activePlayers.value.size)

  return {
    activePlayers,
    playerCount,
    registerPlayer,
    unregisterPlayer,
    getPlayer,
    clearAll,
  }
})
