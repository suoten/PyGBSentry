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

describe('useUserStore', () => {
  beforeEach(() => {
    localStorageMock.clear()
    setActivePinia(createPinia())
  })

  it('initial state reflects localStorage', async () => {
    localStorageMock.setItem('token', 'test-token')
    localStorageMock.setItem('username', 'admin')
    const { useUserStore } = await import('@/stores/user')
    const store = useUserStore()
    expect(store.isLoggedIn).toBe(true)
    expect(store.username).toBe('admin')
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
    expect(localStorageMock.setItem).toHaveBeenCalledWith('token', 'new-token')
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

describe('useAlarmStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('initial state is empty', async () => {
    const { useAlarmStore } = await import('@/stores/alarm')
    const store = useAlarmStore()
    expect(store.alarms).toEqual([])
    expect(store.unreadCount).toBe(0)
  })

  it('addAlarm prepends and increments unread', async () => {
    const { useAlarmStore } = await import('@/stores/alarm')
    const store = useAlarmStore()
    store.addAlarm({ id: '1', alarm_type: 'motion' })
    expect(store.alarms).toHaveLength(1)
    expect(store.unreadCount).toBe(1)
    expect(store.alarms[0].id).toBe('1')
  })

  it('recentAlarms returns first 20', async () => {
    const { useAlarmStore } = await import('@/stores/alarm')
    const store = useAlarmStore()
    for (let i = 0; i < 25; i++) {
      store.addAlarm({ id: String(i) })
    }
    expect(store.recentAlarms).toHaveLength(20)
  })
})

describe('usePluginStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('canUse checks both purchased and installed', async () => {
    const { usePluginStore } = await import('@/stores/plugin')
    const store = usePluginStore()
    store.purchasedIds = ['plugin_a', 'plugin_b']
    store.installedMenus = [{ plugin_id: 'plugin_a', name: 'A', path: '/a' }]
    expect(store.canUse('plugin_a')).toBe(true)
    expect(store.canUse('plugin_b')).toBe(false)
    expect(store.canUse('plugin_c')).toBe(false)
  })

  it('isPurchased and isInstalled work independently', async () => {
    const { usePluginStore } = await import('@/stores/plugin')
    const store = usePluginStore()
    store.purchasedIds = ['p1']
    store.installedMenus = [{ plugin_id: 'p2', name: 'P2', path: '/p2' }]
    expect(store.isPurchased('p1')).toBe(true)
    expect(store.isPurchased('p2')).toBe(false)
    expect(store.isInstalled('p2')).toBe(true)
    expect(store.isInstalled('p1')).toBe(false)
  })
})
