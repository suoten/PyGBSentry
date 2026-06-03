<template>
  <div class="topbar">
    <div class="topbar-left">
      <el-button
        class="collapse-btn"
        @click="$emit('toggle-collapse')"
        :aria-label="collapsed ? '展开侧边栏' : '收起侧边栏'"
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
        <div class="theme-dropdown mr-4 cursor-pointer" role="button" aria-label="切换主题模式" tabindex="0">
          <el-icon :size="18">
            <Sunny v-if="prefsStore.themeMode === 'light'" />
            <Moon v-else-if="prefsStore.themeMode === 'dark'" />
            <Monitor v-else />
          </el-icon>
        </div>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="light" :class="{ 'is-active': prefsStore.themeMode === 'light' }">浅色模式</el-dropdown-item>
            <el-dropdown-item command="dark" :class="{ 'is-active': prefsStore.themeMode === 'dark' }">深色模式</el-dropdown-item>
            <el-dropdown-item command="auto" :class="{ 'is-active': prefsStore.themeMode === 'auto' }">跟随系统</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>

      <el-dropdown trigger="click" @command="handleLocaleCommand">
        <div class="locale-dropdown mr-4 cursor-pointer" role="button" aria-label="切换语言" tabindex="0">
          <el-icon :size="18"><Promotion /></el-icon>
        </div>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="zh-CN" :class="{ 'is-active': locale === 'zh-CN' }">中文</el-dropdown-item>
            <el-dropdown-item command="en-US" :class="{ 'is-active': locale === 'en-US' }">English</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>

      <el-dropdown trigger="click" @command="handleCommand">
        <div class="user-dropdown" role="button" aria-label="用户菜单" tabindex="0">
          <el-avatar :size="30" class="user-avatar">{{ initials }}</el-avatar>
          <span class="user-name">{{ username }}</span>
          <el-icon class="dropdown-icon"><ArrowDown /></el-icon>
        </div>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="user-profile">
              <el-icon><User /></el-icon>
              <span>个人资料</span>
            </el-dropdown-item>
            <el-dropdown-item command="account-security">
              <el-icon><Lock /></el-icon>
              <span>账号安全</span>
            </el-dropdown-item>
            <el-dropdown-item divided command="logout">
              <el-icon><SwitchButton /></el-icon>
              <span>退出登录</span>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowDown, Fold, Expand, User, Lock, SwitchButton, Sunny, Moon, Monitor, Promotion } from '@element-plus/icons-vue'
import { useAppPrefsStore } from '../stores/appPrefs'
import api from '@/utils/http'
import { showError, confirmDangerous } from '../utils/feedback'

defineEmits<{ (e: 'toggle-collapse'): void }>()

const props = defineProps<{ collapsed: boolean }>()
const route = useRoute()
const router = useRouter()
const prefsStore = useAppPrefsStore()
const { locale } = useI18n()

function handleLocaleCommand(command: string) {
  locale.value = command as 'zh-CN' | 'en-US'
  localStorage.setItem('locale', command)
}

function handleThemeCommand(command: 'light' | 'dark' | 'auto') {
  prefsStore.setThemeMode(command)
}

const username = computed(() => String(localStorage.getItem('username') || ''))
const initials = computed(() => username.value.slice(0, 1).toUpperCase())

const crumbs = computed(() => {
  const matched = route.matched || []
  const list = matched
    .filter(r => r.meta && r.meta.title && !r.meta.hidden)
    .map(r => ({ path: r.path, title: String(r.meta.title) }))
  return list.length ? list : [{ path: route.path, title: String(route.meta?.title || '首页') }]
})

async function handleCommand(command: string) {
  if (command === 'user-profile') {
    router.push('/profile')
  } else if (command === 'account-security') {
    router.push('/account-security')
  } else if (command === 'logout') {
    try {
      await confirmDangerous('退出登录')
    } catch { return }
    try {
      await api.post('/api/v1/login/logout')
    } catch (e) { showError('退出登录', e) }
    localStorage.removeItem('token')
    localStorage.removeItem('refresh_token')
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
  background: #f8fafc;
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
  background: #f8fafc;
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
  background: #f8fafc;
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
