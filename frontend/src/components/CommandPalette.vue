<template>
  <Teleport to="body">
    <Transition name="cp-fade">
      <div v-if="visible" class="cp-overlay" @click.self="close">
        <div class="cp-panel" :style="panelStyle">
          <div class="cp-input-row">
            <el-icon class="cp-search-icon"><Search /></el-icon>
            <input
              ref="inputRef"
              v-model="query"
              class="cp-input"
              :placeholder="t('cmdPalette.placeholder')"
              @keydown.down.prevent="move(1)"
              @keydown.up.prevent="move(-1)"
              @keydown.enter.prevent="execute(activeIndex)"
              @keydown.esc.prevent="close"
            />
            <span class="cp-esc">ESC</span>
          </div>
          <div class="cp-list" ref="listRef">
            <template v-if="filtered.length">
              <div
                v-for="(item, idx) in filtered"
                :key="item.key"
                class="cp-item"
                :class="{ 'is-active': idx === activeIndex }"
                :data-idx="idx"
                @mouseenter="activeIndex = idx"
                @click="execute(idx)"
              >
                <el-icon class="cp-item-icon"><component :is="item.icon" /></el-icon>
                <span class="cp-item-title">{{ item.title }}</span>
                <span v-if="item.hint" class="cp-item-hint">{{ item.hint }}</span>
              </div>
            </template>
            <div v-else class="cp-empty">{{ t('cmdPalette.noResult') }}</div>
          </div>
          <div class="cp-footer">
            <span><b>↑↓</b> {{ t('cmdPalette.navigate') }}</span>
            <span><b>↵</b> {{ t('cmdPalette.open') }}</span>
            <span><b>ESC</b> {{ t('cmdPalette.close') }}</span>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
// FIX [2026-09-21 UX]: 全局命令面板 —— Ctrl+K 原来只是跳帮助页。
// 现提供：菜单路由直达 + 快捷动作（主题/退出/刷新）+ 设备搜索（防抖 API）。
import { ref, computed, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Search, Odometer, Monitor, VideoCamera, Bell, Setting, User, Lock, Moon, Sunny, SwitchButton, Refresh, Coin, DataLine, MapLocation, Shop, Box, Promotion, Connection, Folder, Calendar, Document, Tools, TrendCharts, Grid } from '@element-plus/icons-vue'
import api from '@/utils/http'
import { ElMessage } from 'element-plus'

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{ (e: 'update:visible', v: boolean): void }>()

const router = useRouter()
const { t, locale } = useI18n()

const query = ref('')
const activeIndex = ref(0)
const inputRef = ref<HTMLInputElement | null>(null)
const listRef = ref<HTMLElement | null>(null)
const deviceHits = ref<CmdItem[]>([])
let searchTimer: ReturnType<typeof setTimeout> | null = null

const panelStyle = computed(() => ({}))

interface CmdItem {
  key: string
  title: string
  hint?: string
  icon: any
  run: () => void
}

const routeItems = computed<CmdItem[]>(() => {
  const defs: Array<[string, string, any]> = [
    ['/dashboard', 'route.dashboard', Odometer],
    ['/monitor', 'route.monitor', Monitor],
    ['/devices', 'route.devices', VideoCamera],
    ['/channels', 'route.channels', Connection],
    ['/channels/legacy', 'route.channelTree', Grid],
    ['/device-records', 'route.deviceRecords', Folder],
    ['/cloud-records', 'route.cloudRecord', Folder],
    ['/record-schedule', 'route.recordSchedule', Calendar],
    ['/alarms', 'route.alarms', Bell],
    ['/alarm-notifications', 'route.alarmNotifications', Document],
    ['/work-orders', 'route.workOrders', Document],
    ['/map', 'route.map', MapLocation],
    ['/health', 'route.health', DataLine],
    ['/sla', 'route.sla', TrendCharts],
    ['/asset-management', 'route.assetManagement', Coin],
    ['/network', 'route.network', Connection],
    ['/stream-optimization', 'route.streamOptimization', Tools],
    ['/ops', 'route.ops', Tools],
    ['/platforms', 'route.platforms', Promotion],
    ['/push-streams', 'route.pushStream', Promotion],
    ['/pull-proxies', 'route.pullProxy', Connection],
    ['/legacy-gateway', 'route.legacyGateway', Box],
    ['/users', 'route.users', User],
    ['/roles', 'route.roles', User],
    ['#/organizations', 'route.organizations', Document],
    ['/api-keys', 'route.apiKeys', Lock],
    ['/map-providers', 'route.mapProviders', MapLocation],
    ['/config-center', 'route.configCenter', Setting],
    ['/release-center', 'route.releaseCenter', Shop],
    ['/audit-center', 'route.auditCenter', Document],
    ['/account-security', 'route.accountSecurity', Lock],
    ['/profile', 'route.profile', User],
    ['/plugins', 'route.pluginCenter', Shop],
    ['/help', 'route.help', Document],
  ]
  const out: CmdItem[] = []
  for (const [path, titleKey, icon] of defs) {
    let title = ''
    try { title = t(titleKey) } catch { title = path }
    if (!title || title === titleKey) title = path
    // 跳过当前用户无权限进入概率极高的付费门控页在 OSS 下已由路由守卫兜底
    out.push({
      key: 'route:' + path,
      title,
      hint: path,
      icon,
      run: () => router.push(path),
    })
  }
  return out
})

const actionItems = computed<CmdItem[]>(() => {
  const isDark = document.documentElement.classList.contains('dark')
  return [
    {
      key: 'action:theme',
      title: isDark ? t('cmdPalette.actionLightMode') : t('cmdPalette.actionDarkMode'),
      icon: isDark ? Sunny : Moon,
      run: () => {
        const next = document.documentElement.classList.contains('dark') ? 'light' : 'dark'
        localStorage.setItem('app_theme_mode', next)
        document.documentElement.classList.toggle('dark', next === 'dark')
        ElMessage.success(next === 'dark' ? t('cmdPalette.darkOn') : t('cmdPalette.lightOn'))
      },
    },
    {
      key: 'action:refresh',
      title: t('cmdPalette.actionRefresh'),
      icon: Refresh,
      run: () => location.reload(),
    },
    {
      key: 'action:logout',
      title: t('cmdPalette.actionLogout'),
      icon: SwitchButton,
      run: () => {
        sessionStorage.removeItem('token')
        sessionStorage.removeItem('refresh_token')
        router.push('/login')
      },
    },
  ]
})

const staticItems = computed<CmdItem[]>(() => [...routeItems.value, ...actionItems.value, ...deviceHits.value])

const filtered = computed<CmdItem[]>(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return staticItems.value.slice(0, 12)
  const all = staticItems.value
  const matched = all.filter(it => it.title.toLowerCase().includes(q) || (it.hint || '').toLowerCase().includes(q))
  // 设备搜索：防抖触发
  scheduleDeviceSearch(q)
  return matched.slice(0, 20)
})

function scheduleDeviceSearch(q: string) {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(async () => {
    if (!q || q.length < 2) { deviceHits.value = []; return }
    try {
      const res = await api.get('/api/v1/devices', { params: { keyword: q, page: 1, page_size: 5 } })
      const items: Array<Record<string, any>> = res.data?.items || []
      deviceHits.value = items.map((d: any) => ({
        key: 'device:' + d.id,
        title: d.name || d.gb_id,
        hint: t('cmdPalette.deviceHint') + (d.gb_id || ''),
        icon: VideoCamera,
        run: () => router.push({ path: '/devices', query: { deviceId: d.id } }),
      }))
    } catch { deviceHits.value = [] }
  }, 250)
}

function move(delta: number) {
  const n = filtered.value.length
  if (!n) return
  activeIndex.value = (activeIndex.value + delta + n) % n
  nextTick(() => {
    const el = listRef.value?.querySelector(`[data-idx="${activeIndex.value}"]`)
    el?.scrollIntoView({ block: 'nearest' })
  })
}

function execute(idx: number) {
  const item = filtered.value[idx]
  if (!item) return
  close()
  item.run()
}

function close() {
  emit('update:visible', false)
}

watch(() => props.visible, async (v) => {
  if (v) {
    query.value = ''
    activeIndex.value = 0
    deviceHits.value = []
    await nextTick()
    inputRef.value?.focus()
  }
})
</script>

<style scoped>
.cp-overlay {
  position: fixed;
  inset: 0;
  z-index: 3000;
  background: rgba(15, 23, 42, 0.45);
  backdrop-filter: blur(2px);
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding-top: 12vh;
}
.cp-panel {
  width: min(620px, 92vw);
  max-height: 62vh;
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color, #fff);
  border-radius: 12px;
  box-shadow: 0 18px 50px rgba(15, 23, 42, 0.28);
  overflow: hidden;
  border: 1px solid var(--el-border-color-lighter);
}
.cp-input-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.cp-search-icon { color: var(--el-text-color-secondary); }
.cp-input {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  font-size: 15px;
  color: var(--el-text-color-primary);
}
.cp-esc {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 1px 6px;
}
.cp-list { flex: 1; overflow-y: auto; padding: 6px; }
.cp-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 10px;
  border-radius: 8px;
  cursor: pointer;
  color: var(--el-text-color-primary);
}
.cp-item.is-active { background: var(--el-color-primary-light-9, #ecf5ff); }
.cp-item-icon { color: var(--el-text-color-secondary); }
.cp-item-title { flex: 1; font-size: 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cp-item-hint { font-size: 12px; color: var(--el-text-color-secondary); font-family: monospace; }
.cp-empty { padding: 28px 0; text-align: center; color: var(--el-text-color-secondary); font-size: 13px; }
.cp-footer {
  display: flex;
  gap: 16px;
  padding: 8px 14px;
  border-top: 1px solid var(--el-border-color-lighter);
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.cp-footer b { font-weight: 600; }
.cp-fade-enter-active, .cp-fade-leave-active { transition: opacity 0.15s ease; }
.cp-fade-enter-from, .cp-fade-leave-to { opacity: 0; }
</style>
