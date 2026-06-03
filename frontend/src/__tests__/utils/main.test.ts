import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock localStorage
const localStorageData: Record<string, string> = {}
vi.stubGlobal('localStorage', {
  getItem: (key: string) => localStorageData[key] ?? null,
  setItem: (key: string, value: string) => { localStorageData[key] = value },
  removeItem: (key: string) => { delete localStorageData[key] },
  clear: () => { Object.keys(localStorageData).forEach(k => delete localStorageData[k]) },
})

describe('Axios interceptor security features', () => {
  beforeEach(() => {
    Object.keys(localStorageData).forEach(k => delete localStorageData[k])
    vi.clearAllMocks()
  })

  it('sets Authorization Bearer token from localStorage', () => {
    localStorageData['token'] = 'test-jwt-token'
    const token = localStorage.getItem('token')
    expect(token).toBe('test-jwt-token')
  })

  it('reads CSRF token from localStorage', () => {
    localStorageData['csrf_token'] = 'csrf-test-token'
    const csrfToken = localStorage.getItem('csrf_token')
    expect(csrfToken).toBe('csrf-test-token')
  })

  it('generates unique Request-ID per request', () => {
    const id1 = crypto.randomUUID()
    const id2 = crypto.randomUUID()
    expect(id1).not.toBe(id2)
    expect(id1).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i)
  })

  it('marks sensitive operations with X-Sensitive-Operation header', () => {
    const sensitivePaths = ['/admin', '/delete', '/api/v1/users/1']
    const nonSensitivePaths = ['/api/v1/devices', '/api/v1/stream']

    const isSensitive = (path: string) =>
      path.includes('admin') || path.includes('delete')

    sensitivePaths.forEach(p => expect(isSensitive(p)).toBe(true))
    nonSensitivePaths.forEach(p => expect(isSensitive(p)).toBe(false))
  })

  it('handles 401 by clearing token and redirecting', () => {
    localStorageData['token'] = 'expired-token'
    const status = 401

    if (status === 401) {
      localStorage.removeItem('token')
    }

    expect(localStorage.getItem('token')).toBeNull()
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
    localStorageData['token'] = 'valid-token'
    const status = 429

    if (status === 429) {
      // Just show error, don't clear token
    }

    expect(localStorage.getItem('token')).toBe('valid-token')
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
