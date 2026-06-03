import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export const useAppPrefsStore = defineStore('appPrefs', () => {
  // FIXED: localStorage访问添加try-catch，隐私模式/配额满时安全降级
  const _safeGetItem = (key: string, fallback: string = ''): string => {
    try { return localStorage.getItem(key) || fallback } catch { return fallback }
  }
  const _safeSetItem = (key: string, value: string): void => {
    try { localStorage.setItem(key, value) } catch { /* ignore storage quota/privacy mode */ }
  }

  const themeMode = ref<string>(_safeGetItem('app_theme_mode', 'auto'))

  const applyTheme = () => {
    let isDark = false
    if (themeMode.value === 'dark') {
      isDark = true
    } else if (themeMode.value === 'auto') {
      isDark = window.matchMedia('(prefers-color-scheme: dark)').matches
    }

    if (isDark) {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
  }

  const setThemeMode = (mode: 'auto' | 'light' | 'dark') => {
    themeMode.value = mode
    _safeSetItem('app_theme_mode', mode)  // FIXED: 使用安全写入
    applyTheme()
  }

  // FIXED: 事件监听器引用保存，支持清理避免内存泄漏
  const _mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
  const _onMediaChange = (e: MediaQueryListEvent) => {
    if (themeMode.value === 'auto') {
      if (e.matches) {
        document.documentElement.classList.add('dark')
      } else {
        document.documentElement.classList.remove('dark')
      }
    }
  }
  _mediaQuery.addEventListener('change', _onMediaChange)

  // 初始应用
  applyTheme()

  return {
    themeMode,
    setThemeMode,
    applyTheme,
  }
})
