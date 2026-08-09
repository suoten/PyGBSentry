import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/utils/http'
import { getVerifiedRoleInfo } from '@/utils/auth' // FIX C-2: 从后端获取权威角色信息
import { safeSSGet, safeSSSet, safeSSRemove } from '@/utils/storage'  // SECURITY: 所有敏感数据统一用 sessionStorage
import { logger } from '@/utils/logger'

export const useUserStore = defineStore('user', () => {
  const token = ref(safeSSGet('token') || '')
  // SECURITY: username 仅保留在内存中，不持久化到任何 storage，通过 fetchUserInfo() 从 API 实时获取
  const username = ref('')
  // FIX C-2: role/isSuperuser/tenantId 仅保留在内存中，不再持久化（防止可篡改）
  const role = ref('')
  const isSuperuser = ref(false)
  const tenantId = ref('default')

  const isLoggedIn = computed(() => !!token.value)

  // FIX C-2: 从后端 verify-token 刷新权威角色信息到内存
  async function refreshRoleFromBackend(): Promise<void> {
    const info = await getVerifiedRoleInfo()
    if (info) {
      role.value = info.role
      isSuperuser.value = info.isSuperuser
    } else {
      role.value = ''
      isSuperuser.value = false
    }
  }

  // SECURITY: 从后端实时获取用户信息（username 等），不依赖任何本地 storage
  async function fetchUserInfo(): Promise<void> {
    if (!token.value) return
    try {
      const res = await api.get('/api/v1/login/verify-token', { withCredentials: true })
      if (res.data?.valid) {
        username.value = res.data.username || username.value
        role.value = res.data.role || ''
        isSuperuser.value = Boolean(res.data.is_superuser)
        tenantId.value = res.data.tenant_id || 'default'
      }
    } catch (e) {
      logger.warn('fetchUserInfo failed:', e)
    }
  }

  function setAuth(data: { token: string; username: string; role?: string; is_superuser?: boolean; tenant_id?: string }) {
    if (!data || typeof data.token !== 'string' || !data.token) {
      logger.error('setAuth: invalid token, skipping auth storage')  // FIXED: token类型校验
      return
    }
    token.value = data.token
    username.value = data.username
    role.value = data.role || ''
    isSuperuser.value = data.is_superuser || false
    tenantId.value = data.tenant_id || 'default'

    // SECURITY: token 存 sessionStorage（防 XSS 持久窃取）；username 不持久化到任何 storage，仅保留内存
    safeSSSet('token', data.token)
    // 异步从后端刷新权威角色信息
    void refreshRoleFromBackend()
  }

  function clearAuth() {
    token.value = ''
    username.value = ''
    role.value = ''
    isSuperuser.value = false
    tenantId.value = 'default'

    safeSSRemove('token')
    safeSSRemove('refresh_token')
    // SECURITY: username 不再持久化到任何 storage，无需移除
  }

  async function logout() {
    try {
      await api.post('/api/v1/login/logout')
    } catch (e) {
      logger.warn('logout API call failed:', e)
    }
    const { useNotificationStore } = await import('@/stores/notification')
    useNotificationStore().disconnectWebSocket()
    clearAuth()
    // FIX: [2026-07-17 P1] 重置业务 store，防止跨账号数据残留
    // 公共终端场景下 A 账号登出后 B 账号登录会看到 A 的残留数据
    try {
      const { useDeviceStore } = await import('@/stores/device')
      useDeviceStore().$reset()
    } catch { /* store 可能未加载 */ }
    try {
      const { useAlarmStore } = await import('@/stores/alarm')
      useAlarmStore().$reset()
    } catch { /* store 可能未加载 */ }
    try {
      const { usePlayerStore } = await import('@/stores/player')
      usePlayerStore().$reset()
    } catch { /* store 可能未加载 */ }
    try {
      const { usePluginStore } = await import('@/stores/plugin')
      usePluginStore().$reset()
    } catch { /* store 可能未加载 */ }
    // FIX: [2026-07-17 P1] 取消所有进行中的请求，防止旧请求响应覆盖新账号状态
    const { clearStalePendingRequests } = await import('@/utils/httpDedupe')
    clearStalePendingRequests()
  }

  return { token, username, role, isSuperuser, tenantId, isLoggedIn, setAuth, clearAuth, logout, refreshRoleFromBackend, fetchUserInfo }
})
