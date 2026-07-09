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

  function setThemeMode(mode: 'light' | 'dark' | 'auto') {
    themeMode.value = mode
  }

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  return { themeMode, sidebarCollapsed, setThemeMode, toggleSidebar }
})
