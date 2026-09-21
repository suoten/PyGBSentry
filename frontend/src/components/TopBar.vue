<template>
  <div class="topbar">
    <div class="topbar-left">
      <el-button
        class="collapse-btn"
        @click="$emit('toggle-collapse')"
        :aria-label="collapsed ? t('topbar.expandSidebar') : t('topbar.collapseSidebar')"
        :aria-expanded="!collapsed"
        aria-controls="app-sidebar"
      >
        <el-icon :size="18">
          <Fold v-if="!collapsed" />
          <Expand v-else />
        </el-icon>
      </el-button>
      <el-breadcrumb separator="/" class="breadcrumb">
        <el-breadcrumb-item v-for="m in crumbs" :key="m.path">
          {{ m.title }}
        </el-breadcrumb-item>
      </el-breadcrumb>
    </div>
    <div class="topbar-right">
      <el-dropdown trigger="click" @command="handleThemeCommand">
        <div class="theme-dropdown mr-4 cursor-pointer" role="button" :aria-label="t('topbar.toggleTheme')" tabindex="0">
          <el-icon :size="18">
            <Sunny v-if="prefsStore.themeMode === 'light'" />
            <Moon v-else-if="prefsStore.themeMode === 'dark'" />
            <Monitor v-else />
          </el-icon>
        </div>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="light" :class="{ 'is-active': prefsStore.themeMode === 'light' }">{{ t('topbar.lightMode') }}</el-dropdown-item>
            <el-dropdown-item command="dark" :class="{ 'is-active': prefsStore.themeMode === 'dark' }">{{ t('topbar.darkMode') }}</el-dropdown-item>
            <el-dropdown-item command="auto" :class="{ 'is-active': prefsStore.themeMode === 'auto' }">{{ t('topbar.autoMode') }}</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>

      <!-- FIX [2026-09-21 UX]: 通知中心入口 —— notification store 已有 WS 实时推送与未读数，
           但此前没有任何 UI 消费它。铃铛 + 未读徽标 + 最近通知下拉面板。 -->
      <el-popover trigger="click" placement="bottom-end" :width="340" popper-class="notif-popover">
        <template #reference>
          <div class="notif-bell mr-2 cursor-pointer" role="button" :aria-label="t('topbar.notifications')" tabindex="0">
            <el-badge :value="unreadCount" :hidden="unreadCount === 0" :max="99">
              <el-icon :size="18"><Bell /></el-icon>
            </el-badge>
          </div>
        </template>
        <div class="notif-panel">
          <div class="notif-panel-head">
            <span class="font-medium">{{ t('topbar.notifTitle') }}</span>
            <el-button v-if="notifications.length" link size="small" @click="clearNotifs">{{ t('topbar.notifClearAll') }}</el-button>
          </div>
          <div class="notif-panel-body">
            <template v-if="notifications.length">
              <div
                v-for="n in notifications.slice(0, 8)"
                :key="n.id"
                class="notif-item"
                @click="openNotification(n)"
              >
                <div class="notif-item-title">
                  <span class="notif-dot" :class="'p' + (n.priority || '3')"></span>
                  {{ n.description || t('topbar.notifUntitled') }}
                </div>
                <div class="notif-item-time">{{ formatNotifTime(n.time) }}</div>
              </div>
            </template>
            <div v-else class="notif-empty">{{ t('topbar.notifEmpty') }}</div>
          </div>
          <div class="notif-panel-foot" @click="goAlarms">{{ t('topbar.notifViewAll') }}</div>
        </div>
      </el-popover>

      <el-dropdown trigger="click" @command="handleLocaleCommand">
        <div class="locale-dropdown mr-4 cursor-pointer" role="button" :aria-label="t('topbar.toggleLanguage')" tabindex="0">
          <el-icon :size="18"><Promotion /></el-icon>
        </div>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="zh-CN" :class="{ 'is-active': locale === 'zh-CN' }">{{ t('topbar.chinese') }}</el-dropdown-item>
            <el-dropdown-item command="en-US" :class="{ 'is-active': locale === 'en-US' }">{{ t('topbar.english') }}</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>

      <el-dropdown trigger="click" @command="handleCommand">
        <div class="user-dropdown" role="button" :aria-label="t('topbar.userMenu')" tabindex="0">
          <el-avatar :size="30" class="user-avatar">{{ initials }}</el-avatar>
          <span class="user-name">{{ username }}</span>
          <el-icon class="dropdown-icon"><ArrowDown /></el-icon>
        </div>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="user-profile">
              <el-icon><User /></el-icon>
              <span>{{ t('topbar.userProfile') }}</span>
            </el-dropdown-item>
            <el-dropdown-item command="account-security">
              <el-icon><Lock /></el-icon>
              <span>{{ t('topbar.accountSecurity') }}</span>
            </el-dropdown-item>
            <el-dropdown-item divided command="logout">
              <el-icon><SwitchButton /></el-icon>
              <span>{{ t('topbar.logout') }}</span>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowDown, Fold, Expand, User, Lock, SwitchButton, Sunny, Moon, Monitor, Promotion, Bell } from '@element-plus/icons-vue'
import { useAppPrefsStore } from '../stores/appPrefs'
import { useNotificationStore } from '../stores/notification'
import { formatDateTime } from '../utils/time'
import { useUserStore } from '../stores/user'
import api from '@/utils/http'
import { showError, confirmDangerous } from '../utils/feedback'
import { safeLSSet } from '@/utils/storage'

defineEmits<{ (e: 'toggle-collapse'): void }>()

const props = defineProps<{ collapsed: boolean }>()
const route = useRoute()
const router = useRouter()
const prefsStore = useAppPrefsStore()
const userStore = useUserStore()
const { t, locale } = useI18n()

// SECURITY: username 不持久化到任何 storage，组件挂载时从 API 实时获取
onMounted(() => {
  notificationStore.connectWebSocket()
  notificationStore.fetchUnreadCount()
  if (userStore.isLoggedIn && !userStore.username) {
    void userStore.fetchUserInfo()
  }
})

function handleLocaleCommand(command: string) {
  locale.value = command as 'zh-CN' | 'en-US'
  safeLSSet('locale', command)  // locale is a non-sensitive UI preference
}

function handleThemeCommand(command: 'light' | 'dark' | 'auto') {
  prefsStore.setThemeMode(command)
}

const username = computed(() => userStore.username)
// FIX [2026-09-21 UX]: 通知中心 —— WS 实时推送 + 未读徽标 + 最近通知
const notificationStore = useNotificationStore()
const notifications = computed(() => notificationStore.notifications)
const unreadCount = computed(() => notificationStore.unreadCount)
function openNotification(n: Record<string, unknown>) {
  notificationStore.markAsRead(String(n.id))
  router.push('/alarms')
}
function clearNotifs() { notificationStore.clearAll() }
function goAlarms() { router.push('/alarms') }
function formatNotifTime(tm: unknown) {
  if (!tm) return ''
  try { return formatDateTime(String(tm)) } catch { return String(tm) }
}
const initials = computed(() => username.value.slice(0, 1).toUpperCase())

const crumbs = computed(() => {
  const matched = route.matched || []
  // FIX: [2026-07-13] 路由配置已改用 `meta.titleKey`（i18n 翻译键）而非硬编码 `meta.title`。
  // 旧代码仅过滤 `meta.title`，导致所有面包屑项都被过滤掉，回退到默认 "首页"。
  // 现在优先使用 titleKey + i18n 翻译，其次回退到 meta.title（向后兼容）。
  const list = matched
    .filter(r => r.meta && (r.meta.titleKey || r.meta.title) && !r.meta.hidden)
    .map(r => ({
      path: r.path,
      title: r.meta.titleKey
        ? t(String(r.meta.titleKey))
        : String(r.meta.title || '')
    }))
  return list.length ? list : [{
    path: route.path,
    title: route.meta?.titleKey
      ? t(String(route.meta.titleKey))
      : String(route.meta?.title || t('topbar.home'))
  }]
})

async function handleCommand(command: string) {
  if (command === 'user-profile') {
    router.push('/profile')
  } else if (command === 'account-security') {
    router.push('/account-security')
  } else if (command === 'logout') {
    try {
      await confirmDangerous(t('topbar.logout'))
    } catch { return }
    try {
      await api.post('/api/v1/login/logout')
    } catch (e) { showError(t('topbar.logout'), e) }
    sessionStorage.removeItem('token')  // P0-4: sessionStorage
    sessionStorage.removeItem('refresh_token')
    document.cookie = 'access_token=; path=/; max-age=0; secure; samesite=lax'
    router.push('/login')
  }
}
</script>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: var(--top-tool-height);
  padding: 0 var(--top-tool-p-x);
  background: var(--top-header-bg-color);
  border-bottom: 1px solid var(--el-border-color-lighter);
  box-shadow: none;
}

.topbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.collapse-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  border: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-light, #f8fafc);
  color: var(--el-text-color-primary);
  cursor: pointer;
  border-radius: 6px;
  transition: all var(--transition-time-02);
}

.collapse-btn:hover {
  border-color: rgba(64, 158, 255, 0.22);
  background: rgba(64, 158, 255, 0.08);
  color: var(--el-color-primary);
}

.breadcrumb {
  min-width: 0;
  flex: 1;
}

.breadcrumb :deep(.el-breadcrumb__item) {
  display: inline-flex;
  align-items: center;
}

.breadcrumb :deep(.el-breadcrumb__inner) {
  display: inline-flex;
  align-items: center;
  font-weight: 500;
  color: var(--el-text-color-secondary);
  transition: color var(--transition-time-02);
  font-size: 13px;
}

.breadcrumb :deep(.el-breadcrumb__separator) {
  margin: 0 8px;
  color: var(--el-text-color-placeholder);
}

.breadcrumb :deep(.el-breadcrumb__item:last-child .el-breadcrumb__inner) {
  color: var(--el-text-color-primary);
  font-weight: 500;
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.locale-dropdown {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  border: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-light, #f8fafc);
  color: var(--el-text-color-primary);
  cursor: pointer;
  border-radius: 6px;
  transition: all var(--transition-time-02);
}

.locale-dropdown:hover {
  border-color: rgba(64, 158, 255, 0.22);
  background: rgba(64, 158, 255, 0.08);
  color: var(--el-color-primary);
}

.user-dropdown {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 10px;
  cursor: pointer;
  border-radius: 16px;
  border: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-light, #f8fafc);
  transition: all var(--transition-time-02);
}

.user-dropdown:hover {
  border-color: rgba(64, 158, 255, 0.22);
  background: rgba(64, 158, 255, 0.08);
}

.user-avatar {
  background: linear-gradient(135deg, var(--el-color-primary) 0%, var(--el-color-primary-dark-2) 100%);
  color: #fff;
  font-size: 13px;
  font-weight: 500;
}

.user-name {
  font-size: 13px;
  color: var(--top-header-text-color);
  font-weight: 500;
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dropdown-icon {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  transition: transform var(--transition-time-02);
}

.user-dropdown:hover .dropdown-icon {
  color: var(--el-color-primary);
}

:deep(.el-dropdown-menu__item) {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  font-size: 13px;
  color: var(--el-text-color-regular);
  transition: all var(--transition-time-02);
}

:deep(.el-dropdown-menu__item:hover) {
  background: var(--el-fill-color-light);
  color: var(--el-color-primary);
}

:deep(.el-dropdown-menu__item .el-icon) {
  font-size: 14px;
}
</style>

.notif-bell {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  background: var(--el-fill-color-light, #f8fafc);
  color: var(--el-text-color-primary);
  transition: all 0.2s;
}
.notif-bell:hover { border-color: rgba(64, 158, 255, 0.22); color: var(--el-color-primary); }
.notif-panel-head { display: flex; align-items: center; justify-content: space-between; padding: 4px 4px 10px; border-bottom: 1px solid var(--el-border-color-lighter); }
.notif-panel-body { max-height: 300px; overflow-y: auto; }
.notif-item { padding: 8px 4px; border-bottom: 1px solid var(--el-border-color-extra-light, #f0f0f0); cursor: pointer; }
.notif-item:hover { background: var(--el-fill-color-light, #f5f7fa); }
.notif-item-title { font-size: 13px; color: var(--el-text-color-primary); display: flex; align-items: center; gap: 6px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.notif-item-time { font-size: 11px; color: var(--el-text-color-secondary); margin-top: 3px; }
.notif-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; display: inline-block; }
.notif-dot.p1 { background: var(--el-color-danger); }
.notif-dot.p2 { background: var(--el-color-warning); }
.notif-dot.p3 { background: var(--el-color-info); }
.notif-empty { padding: 26px 0; text-align: center; color: var(--el-text-color-secondary); font-size: 13px; }
.notif-panel-foot { padding: 8px 0 2px; text-align: center; font-size: 12px; color: var(--el-color-primary); cursor: pointer; }
