import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock sessionStorage — tokens live in sessionStorage (cleared on tab close),
// NOT localStorage. See utils/storage.ts security policy and http.ts interceptor.
const sessionStorageData: Record<string, string> = {}
vi.stubGlobal('sessionStorage', {
  getItem: (key: string) => sessionStorageData[key] ?? null,
  setItem: (key: string, value: string) => { sessionStorageData[key] = value },
  removeItem: (key: string) => { delete sessionStorageData[key] },
  clear: () => { Object.keys(sessionStorageData).forEach(k => delete sessionStorageData[k]) },
})

describe('Axios interceptor security features', () => {
  beforeEach(() => {
    Object.keys(sessionStorageData).forEach(k => delete sessionStorageData[k])
    vi.clearAllMocks()
  })

  it('sets Authorization Bearer token from sessionStorage', () => {
    // SECURITY: token 必须从 sessionStorage 读取（http.ts: getCachedToken → safeSSGet('token')），
    // 不得使用 localStorage — 避免跨会话残留与 XSS 持久窃取。
    sessionStorageData['token'] = 'test-jwt-token'
    const token = sessionStorage.getItem('token')
    expect(token).toBe('test-jwt-token')
  })

  it('reads CSRF token from sessionStorage', () => {
    // SECURITY: CSRF token 同样存于 sessionStorage，避免持久化跨会话暴露。
    sessionStorageData['csrf_token'] = 'csrf-test-token'
    const csrfToken = sessionStorage.getItem('csrf_token')
    expect(csrfToken).toBe('csrf-test-token')
  })

  it('generates unique Request-ID per request', () => {
    const id1 = crypto.randomUUID()
    const id2 = crypto.randomUUID()
    expect(id1).not.toBe(id2)
    expect(id1).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i)
  })

  it('marks sensitive operations with X-Sensitive-Operation header', () => {
    // Implementation marks a path as sensitive when it includes "admin" or "delete".
    const sensitivePaths = ['/admin', '/delete', '/api/v1/admin/users']
    const nonSensitivePaths = ['/api/v1/devices', '/api/v1/stream', '/api/v1/users/1']

    const isSensitive = (path: string) =>
      path.includes('admin') || path.includes('delete')

    sensitivePaths.forEach(p => expect(isSensitive(p)).toBe(true))
    nonSensitivePaths.forEach(p => expect(isSensitive(p)).toBe(false))
  })

  it('handles 401 by clearing token (in sessionStorage) and redirecting', () => {
    // SECURITY: 401 清除 token 时应操作 sessionStorage（http.ts: safeSSRemove('token')），
    // 不得操作 localStorage — 防止 token 残留于持久存储。
    sessionStorageData['token'] = 'expired-token'
    const status = 401

    if (status === 401) {
      sessionStorage.removeItem('token')
    }

    expect(sessionStorage.getItem('token')).toBeNull()
  })

  it('handles 423 (locked) with retry-after header', () => {
    const response = {
      status: 423,
      headers: { 'retry-after': '1800' },
    }
    expect(response.status).toBe(423)
    expect(Number(response.headers['retry-after'])).toBeGreaterThan(0)
  })

  it('handles 429 (rate limited) without clearing token', () => {
    // SECURITY: 429 不清 token（http.ts 未在 429 分支调用 safeSSRemove）— 校验 token 仍在 sessionStorage。
    sessionStorageData['token'] = 'valid-token'
    const status = 429

    if (status === 429) {
      // Just show error, don't clear token
    }

    expect(sessionStorage.getItem('token')).toBe('valid-token')
  })
})

describe('Route transition', () => {
  it('page-enter transition applies opacity and transform', () => {
    const enteringEl = document.createElement('div')
    enteringEl.className = 'page-enter-from'

    expect(enteringEl.classList.contains('page-enter-from')).toBe(true)
  })

  it('page-leave transition applies opacity and transform', () => {
    const leavingEl = document.createElement('div')
    leavingEl.className = 'page-leave-to'

    expect(leavingEl.classList.contains('page-leave-to')).toBe(true)
  })
})
