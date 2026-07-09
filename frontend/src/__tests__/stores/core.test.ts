import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {}
  return {
    getItem: vi.fn((key: string) => store[key] ?? null),
    setItem: vi.fn((key: string, value: string) => { store[key] = value }),
    removeItem: vi.fn((key: string) => { delete store[key] }),
    clear: vi.fn(() => { store = {} }),
  }
})()
Object.defineProperty(window, 'localStorage', { value: localStorageMock })

// Mock api
vi.mock('@/utils/http', () => ({
  default: {
    get: vi.fn(() => Promise.resolve({ data: { items: [] } })),
    post: vi.fn(() => Promise.resolve({ data: {} })),
  },
}))

// Provide a no-op i18n so stores that call useI18n() outside a component work.
vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

// Avoid async verify-token side effects from refreshRoleFromBackend.
vi.mock('@/utils/auth', () => ({
  getVerifiedRoleInfo: vi.fn(() => Promise.resolve(null)),
}))

// Mock element-plus to avoid loading the full library in jsdom (very slow).
vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), success: vi.fn(), warning: vi.fn(), info: vi.fn() },
}))

// Mock logger to keep the test lightweight (alarm store imports it).
vi.mock('@/utils/logger', () => ({
  logger: { warn: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

describe('useUserStore', () => {
  beforeEach(() => {
    localStorageMock.clear()
    sessionStorage.clear()
    setActivePinia(createPinia())
  })

  it('initial state reflects sessionStorage', async () => {
    // token lives in sessionStorage; username is NOT persisted — fetched from API via fetchUserInfo()
    sessionStorage.setItem('token', 'test-token')
    const { useUserStore } = await import('@/stores/user')
    const store = useUserStore()
    expect(store.isLoggedIn).toBe(true)
    expect(store.username).toBe('')
  })

  it('setAuth updates state and localStorage', async () => {
    const { useUserStore } = await import('@/stores/user')
    const store = useUserStore()
    store.setAuth({ token: 'new-token', username: 'user1', role: 'admin', is_superuser: true, tenant_id: 't1' })
    expect(store.token).toBe('new-token')
    expect(store.username).toBe('user1')
    expect(store.role).toBe('admin')
    expect(store.isSuperuser).toBe(true)
    expect(store.tenantId).toBe('t1')
    expect(sessionStorage.getItem('token')).toBe('new-token')
  })

  it('clearAuth resets all state', async () => {
    const { useUserStore } = await import('@/stores/user')
    const store = useUserStore()
    store.setAuth({ token: 't', username: 'u' })
    store.clearAuth()
    expect(store.token).toBe('')
    expect(store.username).toBe('')
    expect(store.isLoggedIn).toBe(false)
  })
})

// NOTE: useAlarmStore / usePluginStore 测试已移除 — 对应的 @/stores/alarm、@/stores/plugin
// 在开源版中已删除（参见 git status），保留会导致整个 core.test.ts 因 import 解析失败而 0 测试通过。
// useUserStore 测试与 localStorage 安全策略直接相关（token 存于 sessionStorage），保留并确保可运行。

