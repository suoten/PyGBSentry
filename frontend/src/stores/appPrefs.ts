import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { safeLSGet, safeLSSet } from '@/utils/storage'

// SECURITY: 此 store 仅持久化非敏感 UI 偏好（主题模式、侧边栏折叠状态）到 localStorage。
// 敏感信息（token、refresh_token、用户名、租户配置）使用 sessionStorage 或内存，
// 绝不存入 localStorage。详见 utils/storage.ts 安全策略。
const THEME_KEY = 'app_theme_mode'
const SIDEBAR_KEY = 'app_sidebar_collapsed'

export const useAppPrefsStore = defineStore('appPrefs', () => {
  // 非敏感 UI 偏好 — 从 localStorage 恢复，刷新后保持用户选择
  const themeMode = ref<'light' | 'dark' | 'auto'>(
    (safeLSGet(THEME_KEY) as 'light' | 'dark' | 'auto') || 'auto'
  )
  const sidebarCollapsed = ref<boolean>(safeLSGet(SIDEBAR_KEY) === 'true')

  // 持久化到 localStorage（非敏感 UI 偏好，可安全存储）
  watch(themeMode, (val) => safeLSSet(THEME_KEY, val))
  watch(sidebarCollapsed, (val) => safeLSSet(SIDEBAR_KEY, String(val)))

  // FIXED: [2026-07-13] 恢复 applyTheme 逻辑（2ad636a）。
  // ConvergeLoop 删除了此函数导致深色模式切换完全失效——themeMode ref 存在但永不应用到 DOM。
  function applyTheme() {
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

  function setThemeMode(mode: 'light' | 'dark' | 'auto') {
    themeMode.value = mode
    applyTheme()
  }

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  // FIXED: [2026-07-13] 恢复系统深色模式监听器（2ad636a）。
  // auto 模式下跟随操作系统切换深/浅色主题。
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

  // 初始应用主题
  applyTheme()

  return { themeMode, sidebarCollapsed, setThemeMode, toggleSidebar, applyTheme }
})
