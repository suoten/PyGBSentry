import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/utils/http'

const WS_RECONNECT_DELAY = 3000
const WS_MAX_RETRIES = 5

export const useNotificationStore = defineStore('notification', () => {
  const notifications = ref<any[]>([])
  const unreadCount = ref(0)
  const wsConnected = ref(false)

  let ws: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let reconnectAttempts = 0
  let wsUrl = ''

  function connectWebSocket(url?: string) {
    if (url) wsUrl = url
    if (!wsUrl) {
      const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
      wsUrl = `${protocol}://${location.host}/api/v1/alarms/ws`
    }
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return

    try {
      ws = new WebSocket(wsUrl)
    } catch {
      scheduleReconnect()
      return
    }

    ws.onopen = () => {
      wsConnected.value = true
      reconnectAttempts = 0
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (!data || typeof data !== 'object' || !data.id) {
          console.warn('WebSocket: invalid notification format, missing id')  // FIXED: WebSocket消息结构校验
          return
        }
        addNotification(data)
      } catch { console.warn('WebSocket received non-JSON message, ignored') }
    }

    ws.onclose = () => {
      wsConnected.value = false
      ws = null
      scheduleReconnect()
    }

    ws.onerror = () => {
      wsConnected.value = false
    }
  }

  function scheduleReconnect() {
    if (reconnectAttempts >= WS_MAX_RETRIES) return
    if (reconnectTimer) return
    reconnectAttempts++
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      connectWebSocket()
    }, WS_RECONNECT_DELAY)
  }

  function disconnectWebSocket() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (ws) {
      ws.onclose = null
      ws.close()
      ws = null
    }
    wsConnected.value = false
    reconnectAttempts = 0
  }

  async function fetchUnreadCount() {
    try {
      const res = await api.get('/api/v1/alarms/unread-count')
      unreadCount.value = res.data?.count ?? 0
    } catch {
      console.warn('获取未读报警计数失败')
      unreadCount.value = 0
    }
  }

  function addNotification(notification: Record<string, unknown>) {
    const exists = notifications.value.some(n => n.id === notification.id)
    if (!exists) {
      notifications.value.unshift(notification)
      unreadCount.value++
    }
  }

  function markAsRead(id: string) {
    const idx = notifications.value.findIndex(n => n.id === id)
    if (idx !== -1) {
      notifications.value.splice(idx, 1)
      unreadCount.value = Math.max(0, unreadCount.value - 1)
    }
  }

  function clearAll() {
    notifications.value = []
    unreadCount.value = 0
  }

  return {
    notifications,
    unreadCount,
    wsConnected,
    fetchUnreadCount,
    addNotification,
    markAsRead,
    clearAll,
    connectWebSocket,
    disconnectWebSocket,
  }
})
