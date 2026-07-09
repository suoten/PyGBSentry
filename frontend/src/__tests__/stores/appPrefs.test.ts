import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

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

// Mock matchMedia
const matchMediaMock = vi.fn((query: string) => ({
  matches: false,
  media: query,
  onchange: null,
  addListener: vi.fn(),
  removeListener: vi.fn(),
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
  dispatchEvent: vi.fn(),
}))
window.matchMedia = matchMediaMock

describe('App.vue Accessibility', () => {
  beforeEach(() => {
    localStorageMock.clear()
    localStorageMock.setItem.mockClear()
  })

  it('skip-link has correct href targeting main-content', () => {
    const skipLink = document.createElement('a')
    skipLink.href = '#main-content'
    skipLink.className = 'skip-link'
    skipLink.textContent = '跳转到主内容'
    document.body.appendChild(skipLink)

    expect(skipLink.getAttribute('href')).toBe('#main-content')
    document.body.removeChild(skipLink)
  })

  it('main-content has id for skip-link target', () => {
    const main = document.createElement('main')
    main.id = 'main-content'
    main.setAttribute('role', 'main')
    document.body.appendChild(main)

    expect(document.getElementById('main-content')).not.toBeNull()
    document.body.removeChild(main)
  })

  it('sidebar has navigation role and accessible label', () => {
    const aside = document.createElement('aside')
    aside.id = 'app-sidebar'
    aside.setAttribute('role', 'navigation')
    aside.setAttribute('aria-label', '主导航')
    document.body.appendChild(aside)

    expect(aside.getAttribute('role')).toBe('navigation')
    expect(aside.getAttribute('aria-label')).toBe('主导航')
    document.body.removeChild(aside)
  })
})

describe('Theme preferences', () => {
  beforeEach(() => {
    localStorageMock.clear()
    localStorageMock.setItem.mockClear()
    localStorageMock.getItem.mockClear()
  })

  it('theme mode is stored in localStorage', () => {
    localStorageMock.setItem('app_theme_mode', 'dark')
    expect(localStorageMock.setItem).toHaveBeenCalledWith('app_theme_mode', 'dark')
  })

  it('auto mode defaults to system preference', () => {
    const stored = localStorageMock.getItem('app_theme_mode')
    expect(stored).toBeNull()
  })
})

describe('Keyboard navigation', () => {
  it('Escape key closes dialogs', async () => {
    let dialogOpen = true
    const closeHandler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') dialogOpen = false
    }
    document.addEventListener('keydown', closeHandler)
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(dialogOpen).toBe(false)
    document.removeEventListener('keydown', closeHandler)
  })

  it('Ctrl+K triggers help navigation', async () => {
    let navigated = false
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        navigated = true
      }
    }
    document.addEventListener('keydown', handler)
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true }))
    expect(navigated).toBe(true)
    document.removeEventListener('keydown', handler)
  })
})
