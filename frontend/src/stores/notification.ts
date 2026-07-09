import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/utils/http'
import { buildWsUrlWithTicket } from '@/utils/wsTicket'  // P0-6: ws-ticket 认证
import { logger } from '@/utils/logger'

const WS_RECONNECT_DELAY = 3000
const WS_MAX_RETRIES = 5

export const useNotificationStore = defineStore('notification', () => {
  const notifications = ref<any[]>([])
  const unreadCount = ref(0)
  const wsConnected = ref(false)

  let ws: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let reconnectAttempts = 0

  async function connectWebSocket() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return
    // P0-6: 通过 ws-ticket 认证，消除 URL 暴露 JWT token
    let wsUrl: string
    try {
      wsUrl = await buildWsUrlWithTicket('/api/v1/alarms/ws')
    } catch (e) {
      logger.warn('WebSocket connect: failed to fetch ws-ticket', e)
      scheduleReconnect()
      return
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
          logger.warn('WebSocket: invalid notification format, missing id')  // FIXED: WebSocket消息结构校验
          return
        }
        addNotification(data)
      } catch { logger.warn('WebSocket received non-JSON message, ignored') }
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

  function resetReconnectCount() {
    reconnectAttempts = 0
  }

  async function fetchUnreadCount() {
    try {
      const res = await api.get('/api/v1/alarms/unread-count')
      unreadCount.value = res.data?.unread_count ?? res.data?.count ?? 0  // FIXED-P0: S-06-02 后端返回unread_count而非count
    } catch {
      logger.warn('获取未读报警计数失败')
      unreadCount.value = 0
    }
  }

  function addNotification(notification: Record<string, unknown>) {
    const exists = notifications.value.some(n => n.id === notification.id)
    if (!exists) {
      notifications.value.unshift(notification)
      if (notifications.value.length > 100) {
        notifications.value.splice(100)
      }
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
    resetReconnectCount,
  }
})

if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      import('@/stores/notification').then(({ useNotificationStore }) => {
        const store = useNotificationStore()
        store.resetReconnectCount()
        if (!store.wsConnected) {
          store.connectWebSocket()
        }
      })
    }
  })
  window.addEventListener('online', () => {
    import('@/stores/notification').then(({ useNotificationStore }) => {
      useNotificationStore().resetReconnectCount()
    })
  })
}
