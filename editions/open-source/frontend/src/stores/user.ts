import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/utils/http'

function safeGetItem(key: string, fallback: string = ''): string {
  try { return localStorage.getItem(key) || fallback } catch { return fallback }
}

function safeSetItem(key: string, value: string): void {
  try { localStorage.setItem(key, value) } catch { /* quota exceeded or privacy mode */ }
}

function safeRemoveItem(key: string): void {
  try { localStorage.removeItem(key) } catch { /* privacy mode */ }
}

export const useUserStore = defineStore('user', () => {
  const token = ref(safeGetItem('token'))
  const username = ref(safeGetItem('username'))
  const role = ref(safeGetItem('role'))
  const isSuperuser = ref(safeGetItem('is_superuser') === 'true')
  const tenantId = ref(safeGetItem('tenant_id', 'default'))

  const isLoggedIn = computed(() => !!token.value)

  function setAuth(data: { token: string; username: string; role?: string; is_superuser?: boolean; tenant_id?: string }) {
    if (!data || typeof data.token !== 'string' || !data.token) {
      console.error('setAuth: invalid token, skipping auth storage')  // FIXED: token类型校验
      return
    }
    token.value = data.token
    username.value = data.username
    role.value = data.role || ''
    isSuperuser.value = data.is_superuser || false
    tenantId.value = data.tenant_id || 'default'

    safeSetItem('token', data.token)
    safeSetItem('username', data.username)
    if (data.role) safeSetItem('role', data.role)
    safeSetItem('is_superuser', String(data.is_superuser || false))
    safeSetItem('tenant_id', data.tenant_id || 'default')
  }

  function clearAuth() {
    token.value = ''
    username.value = ''
    role.value = ''
    isSuperuser.value = false
    tenantId.value = 'default'

    safeRemoveItem('token')
    safeRemoveItem('refresh_token')
    safeRemoveItem('username')
    safeRemoveItem('role')
    safeRemoveItem('is_superuser')
    safeRemoveItem('tenant_id')
  }

  async function logout() {
    try {
      await api.post('/api/v1/login/logout')
    } catch (e) {
      console.warn('logout API call failed:', e)
    }
    clearAuth()
  }

  return { token, username, role, isSuperuser, tenantId, isLoggedIn, setAuth, clearAuth, logout }
})
