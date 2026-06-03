<template>
  <div v-if="showLayout" class="common-layout">
    <el-container class="h-screen flex-col">
      <el-dialog
        v-model="showGuideDialog"
        title="首次使用引导"
        width="520px"
        :close-on-click-modal="false"
        :show-close="true"
        center
        class="guide-dialog"
      >
        <!-- 服务器版引导：插件市场 + 购买授权 -->
        <el-steps v-if="isServerEdition" direction="vertical" :active="guideStep" finish-status="success">
          <el-step title="浏览插件市场">
            <template #description>
              <span>在插件中心查看并安装所需插件。</span>
              <el-button size="small" type="primary" class="ml-2" @click="goGuide('/plugins')">前往</el-button>
            </template>
          </el-step>
          <el-step title="购买与授权">
            <template #description>
              <span>在插件购买页完成支付后自动发放授权。</span>
              <el-button size="small" type="primary" class="ml-2" @click="goGuide('/billing')">前往</el-button>
            </template>
          </el-step>
        </el-steps>
        <!-- 开源版引导：设备接入 + 监控预览 + 录像告警 + 插件扩展 -->
        <el-steps v-else direction="vertical" :active="guideStep" finish-status="success">
          <el-step title="添加第一台设备">
            <template #description>
              <span>在设备列表或多协议接入中添加国标/RTSP 等设备。</span>
              <el-button size="small" type="primary" class="ml-2" @click="goGuide('/devices')">前往</el-button>
            </template>
          </el-step>
          <el-step title="监控中心预览">
            <template #description>
              <span>在监控中心分屏预览实时视频。</span>
              <el-button size="small" type="primary" class="ml-2" @click="goGuide('/monitor')">前往</el-button>
            </template>
          </el-step>
          <el-step title="配置录像与告警">
            <template #description>
              <span>在录像计划中配置录制策略，在告警中心查看告警。</span>
              <el-button size="small" type="primary" class="ml-2" @click="goGuide('/record-schedule')">前往</el-button>
            </template>
          </el-step>
          <el-step title="可选：安装插件">
            <template #description>
              <span>在插件中心安装电视墙、智能分析等扩展插件。</span>
              <el-button size="small" type="primary" class="ml-2" @click="goGuide('/plugins')">前往</el-button>
            </template>
          </el-step>
        </el-steps>
        <template #footer>
          <el-button @click="showGuideDialog = false">跳过</el-button>
          <el-button type="primary" @click="dismissFirstVisit(); showGuideDialog = false">我知道了，不再提示</el-button>
        </template>
      </el-dialog>

      <div v-if="licenseExpiryList.length && !licenseExpiryDismissed" class="license-expiry-banner">
        <span>以下插件授权即将到期（30 天内）：{{ licenseExpiryList.join('、') }}。请前往服务器版完成续费，续费后开源端会继续识别已购状态。</span>
        <div class="flex items-center gap-2">
          <el-button v-if="isServerEdition" size="small" type="primary" @click="goGuide('/billing')">前往续费</el-button>
          <el-button v-else size="small" type="primary" @click="openMarketplaceShop">前往服务器版续费</el-button>
          <el-button size="small" text @click="dismissLicenseExpiry">不再提示</el-button>
        </div>
      </div>

      <el-container class="flex-1 min-h-0">
        <el-aside :width="collapsed ? '64px' : '210px'" class="app-sidebar">
          <div class="app-logo" :class="{ 'app-logo--collapsed': collapsed }">
            <div class="app-logo__img">
              <svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
                <defs>
                  <radialGradient id="deepSpace" cx="30%" cy="30%" r="70%">
                    <stop offset="0%" stop-color="#2a3f5f"/>
                    <stop offset="40%" stop-color="#1a2542"/>
                    <stop offset="100%" stop-color="#0a0f1a"/>
                  </radialGradient>
                  <linearGradient id="neonGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#00ffff"/>
                    <stop offset="50%" stop-color="#00d4ff"/>
                    <stop offset="100%" stop-color="#0080ff"/>
                  </linearGradient>
                  <filter id="multiGlow" x="-100%" y="-100%" width="300%" height="300%">
                    <feGaussianBlur stdDeviation="2" result="blur1"/>
                    <feGaussianBlur stdDeviation="4" result="blur2"/>
                    <feGaussianBlur stdDeviation="8" result="blur3"/>
                    <feMerge>
                      <feMergeNode in="blur3"/>
                      <feMergeNode in="blur2"/>
                      <feMergeNode in="blur1"/>
                      <feMergeNode in="SourceGraphic"/>
                    </feMerge>
                  </filter>
                </defs>
                <rect width="32" height="32" rx="10" fill="url(#deepSpace)"/>
                <circle cx="16" cy="16" r="14" fill="none" stroke="rgba(0,255,255,0.08)" stroke-width="0.5" stroke-dasharray="6 3"/>
                <circle cx="16" cy="16" r="12" fill="none" stroke="rgba(0,255,255,0.15)" stroke-width="0.8" stroke-dasharray="12 6"/>
                <circle cx="16" cy="16" r="9" fill="none" stroke="url(#neonGrad)" stroke-width="1.5" filter="url(#multiGlow)" opacity="0.9"/>
                <circle cx="16" cy="16" r="6" fill="none" stroke="rgba(0,255,255,0.4)" stroke-width="1"/>
                <path d="M10 7L26 16L10 25Z" fill="none" stroke="url(#neonGrad)" stroke-width="2" filter="url(#multiGlow)"/>
                <path d="M11 8L24 16L11 24Z" fill="url(#neonGrad)" filter="url(#multiGlow)" opacity="0.9"/>
                <path d="M13 10L21 16L13 22Z" fill="#0a0f1a"/>
                <path d="M14 11.5L19 16L14 20.5Z" fill="#00ffff" filter="url(#multiGlow)"/>
                <circle cx="16" cy="16" r="1" fill="#ffffff" filter="url(#multiGlow)"/>
              </svg>
            </div>
            <span class="app-logo__title">{{ branding.product_name }}</span>
          </div>

          <el-scrollbar class="sidebar-scrollbar">
            <el-menu
              class="sidebar-menu"
              :default-active="activeRoute"
              router
              :collapse="collapsed"
              :collapse-transition="false"
            >
              <template v-for="group in menuGroups" :key="group.title">
                <el-sub-menu v-if="group.children.length > 1" :index="group.base">
                  <template #title>
                    <el-icon><component :is="group.icon" /></el-icon>
                    <span>{{ $t(group.title) }}</span>
                  </template>
                  <el-menu-item v-for="item in group.children" :key="item.path" :index="item.path">
                    <el-icon><component :is="item.icon" /></el-icon>
                    <span>{{ $t(item.title) }}</span>
                  </el-menu-item>
                </el-sub-menu>
                <el-menu-item v-else :index="group.children[0].path">
                  <el-icon><component :is="group.children[0].icon" /></el-icon>
                  <span>{{ $t(group.children[0].title) }}</span>
                </el-menu-item>
              </template>
            </el-menu>
          </el-scrollbar>
        </el-aside>

        <el-container class="flex-1 min-w-0" direction="vertical">
          <div class="header-wrapper">
            <TopBar :collapsed="collapsed" @toggle-collapse="collapsed = !collapsed" />
            <TagsView />
          </div>
          <el-main class="main-content thin-scrollbar">
            <AppErrorBoundary>
            <router-view v-slot="{ Component }">
              <keep-alive>
                <component v-if="route.meta && (route.meta as Record<string, unknown>).keepAlive" :is="Component" />
              </keep-alive>
              <component v-if="!(route.meta && (route.meta as Record<string, unknown>).keepAlive)" :is="Component" />
            </router-view>
            </AppErrorBoundary>
          </el-main>
        </el-container>
      </el-container>
    </el-container>
  </div>
  <AppErrorBoundary v-if="!showLayout"><router-view></router-view></AppErrorBoundary>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'  // FIXED: 国际化
import { useRoute, useRouter } from 'vue-router'
import AppErrorBoundary from './components/AppErrorBoundary.vue'
import api from '@/utils/http'
import { ElMessage } from 'element-plus'
import { Odometer, VideoCamera, Monitor, User, Setting, MapLocation, DataLine, TrendCharts, Shop, Box, Promotion, Connection, Bell, Folder, Calendar, Document, Lock, InfoFilled } from '@element-plus/icons-vue'
import TopBar from './components/TopBar.vue'
import TagsView from './components/TagsView.vue'
import { useTagsViewStore } from './stores/tagsView'
import { useAppPrefsStore } from './stores/appPrefs'
import appRouter from './router'
import { getRoleInfo, hasPermission } from './utils/auth'
import { logger } from '@/utils/logger'

const route = useRoute()
const { t } = useI18n()  // FIXED: 国际化
const router = useRouter()
const activeRoute = computed(() => route.path)
const isServerEdition = (import.meta.env.VITE_APP_EDITION || 'oss') === 'server'
const showLayout = computed(() => {
  if (['/login', '/register', '/setup'].includes(route.path)) return false
  if (route.path.startsWith('/m/')) return false
  return true
})
const branding = ref({
  product_name: 'PyGBSentry'
})
const pluginMenus = ref<{ plugin_id: string; title: string; path: string }[]>([])
const purchasedPluginIds = ref<string[]>([])
const showGuideDialog = ref(false)
const guideStep = ref(0)
const licenseExpiryList = ref<string[]>([])
const licenseExpiryDismissed = ref(false)
const marketplaceShopUrl = ref('')
const collapsed = ref(false)
const tagsStore = useTagsViewStore()
const prefsStore = useAppPrefsStore()
const APP_LOGS_PAID_PLUGIN_IDS = ['mobile_app_suite', 'mini_program_suite'] as const

const hasPurchased = (pluginId: string) => purchasedPluginIds.value.includes(pluginId)
const hasInstalled = (pluginId: string) => pluginMenus.value.some((m) => m.plugin_id === pluginId)
const canUsePaidPlugin = (pluginId: string) => hasPurchased(pluginId) && hasInstalled(pluginId)

/** App 日志：任一付费能力（手机版/小程序）购买+安装即可 */
const canUseAppLogsRoute = () =>
  APP_LOGS_PAID_PLUGIN_IDS.some((id) => canUsePaidPlugin(id))

type DynRoute = {
  pluginId: string
  routeName: string
  path: string
  title: string
  component: Record<string, unknown>
}

const dynamicPaidRoutes: DynRoute[] = [
  { pluginId: 'mobile_app_suite', routeName: 'MobileApp', path: '/mobile-app', title: '手机版', component: () => import('./views/MobileAppCenter.vue') },
  { pluginId: 'mini_program_suite', routeName: 'MiniProgram', path: '/mini-program', title: '小程序', component: () => import('./views/MiniProgramCenter.vue') },
  { pluginId: 'mobile_app_suite', routeName: 'AppLogs', path: '/app-logs', title: 'App 日志', component: () => import('./views/AppLogs.vue') },
  { pluginId: 'tv_wall_suite', routeName: 'TvWall', path: '/tv-wall', title: '电视墙', component: () => import('./views/TvWall.vue') },
  { pluginId: 'tv_wall_suite', routeName: 'MobileTvWall', path: '/m/tv-wall', title: '电视墙（移动端）', component: () => import('./views/TvWall.vue') },
  { pluginId: 'visual_command_suite', routeName: 'VisualCommand', path: '/visual-command', title: '可视化指挥', component: () => import('./views/VisualCommand.vue') },
  { pluginId: 'visual_command_suite', routeName: 'MobileVisualCommand', path: '/m/visual-command', title: '可视化指挥（移动端）', component: () => import('./views/VisualCommand.vue') },
  { pluginId: 'visual_command_suite', routeName: 'MobileCommand', path: '/mobile-command', title: '移动指挥', component: () => import('./views/MobileCommand.vue') },
  { pluginId: 'face_recognition_suite', routeName: 'MobileFaceRecognition', path: '/m/face-recognition', title: '人脸识别（移动端）', component: () => import('./views/FaceRecognitionMobile.vue') },
  { pluginId: 'plate_recognition_suite', routeName: 'MobilePlateRecognition', path: '/m/plate-recognition', title: '车牌识别（移动端）', component: () => import('./views/PlateRecognitionMobile.vue') },
  { pluginId: 'behavior_recognition_suite', routeName: 'MobileBehaviorRecognition', path: '/m/behavior-recognition', title: '行为识别（移动端）', component: () => import('./views/BehaviorRecognitionMobile.vue') },
]

const syncPaidPluginRoutes = () => {
  if (isServerEdition) return

  for (const r of dynamicPaidRoutes) {
    const enabled =
      r.routeName === 'AppLogs' ? canUseAppLogsRoute() : canUsePaidPlugin(r.pluginId)
    const exists = router.hasRoute(r.routeName)
    if (enabled && !exists) {
      router.addRoute({
        path: r.path,
        name: r.routeName,
        component: r.component,
        meta: { requiresAuth: true, title: r.title }
      })
    } else if (!enabled && exists) {
      router.removeRoute(r.routeName)
    }
  }

  const removedNow = dynamicPaidRoutes.some((r) => {
    if (r.path !== route.path) return false
    if (r.routeName === 'AppLogs') return !canUseAppLogsRoute()
    return !canUsePaidPlugin(r.pluginId)
  })
  if (removedNow) router.replace('/plugins')
}

const canViewAppLogsMenu = computed(() => {
  if (isServerEdition) return true
  return APP_LOGS_PAID_PLUGIN_IDS.some((id) => canUsePaidPlugin(id))
})

function dismissFirstVisit() {
  localStorage.setItem('first_visit_done', '1')
  showGuideDialog.value = false
}
function goGuide(path: string) {
  showGuideDialog.value = false
  router.push(path)
}
function dismissLicenseExpiry() {
  const key = 'license_expiry_dismissed_' + new Date().toISOString().slice(0, 7)
  localStorage.setItem(key, '1')
  licenseExpiryDismissed.value = true
}
function checkLicenseExpiry() {
  api.get('/api/v1/billing/licenses/me', { params: { effective_only: true, expiring_within_days: 30 } }).then((res) => {
    const list = Array.isArray(res.data) ? res.data : []
    const expiring: string[] = []
    for (const item of list) {
      if (item.plugin_name && !expiring.includes(item.plugin_name)) expiring.push(item.plugin_name)
    }
    if (expiring.length > 5) {
      licenseExpiryList.value = [...expiring.slice(0, 5), `等 ${expiring.length} 个`]
    } else {
      licenseExpiryList.value = expiring
    }
    const key = 'license_expiry_dismissed_' + new Date().toISOString().slice(0, 7)
    licenseExpiryDismissed.value = !!localStorage.getItem(key)
  }).catch(() => {})
}

const loadMarketplaceShopUrl = async () => {
  try {
    const res = await api.get('/api/v1/plugins/marketplace-shop-url')
    marketplaceShopUrl.value = String(res.data?.url || '').trim()
  } catch {
    marketplaceShopUrl.value = ''
  }
}

const openMarketplaceShop = () => {
  const url = (marketplaceShopUrl.value || '').trim()
  if (url) {
    window.open(url, '_blank', 'noopener,noreferrer')
    return
  }
  router.push('/plugins')
}

const ossMenu = [
  { path: '/dashboard', title: 'menu.dashboard', icon: Odometer },
  { path: '/plugins', title: 'menu.plugins', icon: Box },
  { path: '/monitor', title: 'menu.monitor', icon: Monitor },
  { path: '/health', title: 'menu.health', icon: DataLine },
  { path: '/sla', title: 'menu.sla', icon: TrendCharts },
  { path: '/alarms', title: 'menu.alarms', icon: Bell },
  { path: '/alarm-notifications', title: 'menu.alarmNotifications', icon: Document },
  { path: '/work-orders', title: 'menu.workOrders', icon: Setting },
  { path: '/map', title: 'menu.map', icon: MapLocation },
  { path: '/devices', title: 'menu.devices', icon: VideoCamera },
  { path: '/legacy-gateway', title: 'menu.legacyGateway', icon: Connection },
  { path: '/platforms', title: 'menu.platforms', icon: Connection },
  { path: '/push-streams', title: 'menu.pushStreams', icon: Promotion },
  { path: '/pull-proxies', title: 'menu.pullProxies', icon: Connection },
  { path: '/channelmanager', title: 'menu.channels', icon: VideoCamera },
  { path: '/device-records', title: 'menu.deviceRecords', icon: VideoCamera },
  { path: '/cloud-records', title: 'menu.cloudRecords', icon: VideoCamera },
  { path: '/record-schedule', title: 'menu.recordSchedule', icon: Calendar },
  { path: '/users', title: 'menu.users', icon: User },
  { path: '/roles', title: 'menu.roles', icon: User },
  { path: '/api-keys', title: 'menu.apiKeys', icon: Lock },
  { path: '/organizations', title: 'menu.organizations', icon: Folder },
  { path: '/ops', title: 'menu.ops', icon: Setting },
  { path: '/asset-management', title: 'menu.assetManagement', icon: Setting },
  { path: '/network', title: 'menu.network', icon: Connection },
  { path: '/map-providers', title: 'menu.mapProviders', icon: MapLocation },
  { path: '/config-center', title: 'menu.configCenter', icon: Setting },
  { path: '/release-center', title: 'menu.releaseCenter', icon: Setting },
  { path: '/audit-center', title: 'menu.auditCenter', icon: DataLine },
  { path: '/reports', title: 'menu.reports', icon: Document },
  { path: '/suite-center', title: 'menu.suiteCenter', icon: Promotion },
  { path: '/account-security', title: 'menu.accountSecurity', icon: Lock },
  { path: '/help', title: 'menu.help', icon: InfoFilled }
] // FIXED: i18n菜单title

type MenuItem = { path: string; title: string; icon: Record<string, unknown> }
type MenuGroup = { title: string; icon: string | { component: unknown }; base: string; children: MenuItem[] }

const menuGroups = computed<MenuGroup[]>(() => {
  let base = [...ossMenu] as MenuItem[]

  if (canViewAppLogsMenu.value) base.push({ path: '/app-logs', title: 'menu.appLogs', icon: Document })
  if (canUsePaidPlugin('tv_wall_suite')) base.push({ path: '/tv-wall', title: 'menu.tvWall', icon: Monitor })
  if (canUsePaidPlugin('visual_command_suite')) base.push({ path: '/visual-command', title: 'menu.visualCommand', icon: Monitor })
  if (canUsePaidPlugin('visual_command_suite')) base.push({ path: '/mobile-command', title: 'menu.mobileCommand', icon: Promotion }) // FIXED: i18n菜单title

  const runtime = pluginMenus.value.map(item => ({ path: item.path, title: item.title, icon: Box }))
  const all = [...base, ...runtime]

  const roleInfo = getRoleInfo()
  const filterPerms = (items: MenuItem[]) => {
    if (roleInfo.isSuperuser || roleInfo.permissions.includes('*')) return items
    return items.filter(item => {
      if (['/help', '/account-security', '/plugins', '/dashboard'].includes(item.path)) return true

      if (item.path.startsWith('/plugins/runtime/')) {
        const pluginId = item.path.split('/').pop()
        return hasPermission(roleInfo.permissions, `plugin_${pluginId}.view`)
      }

      const r = router.getRoutes().find(route => route.path === item.path)
      if (!r || !r.name) return true

      const routeName = String(r.name)
      const legacyMap: Record<string, string> = {
        'Devices': 'devices.manage',
        'Alarms': 'alarms.handle',
        'ConfigCenter': 'config.manage',
        'Users': 'users.manage',
        'Roles': 'roles.manage',
        'AuditCenter': 'audit.view',
        'RecordSchedule': 'records.view',
        'DeviceRecords': 'records.view',
        'CloudRecords': 'records.view'
      }

      const code = `${routeName.charAt(0).toLowerCase() + routeName.slice(1)}.view`
      const codeLower = `${routeName.toLowerCase()}.view`
      const legacyCode = legacyMap[routeName]

      return hasPermission(roleInfo.permissions, code, codeLower) || (legacyCode && hasPermission(roleInfo.permissions, legacyCode))
    })
  }

  const groups: MenuGroup[] = [
    { title: '概览', icon: Odometer, base: '/_g1', children: filterPerms(all.filter(i => ['/dashboard', '/plugins'].includes(i.path))) },
    { title: '业务', icon: Monitor, base: '/_g2', children: filterPerms(all.filter(i => ['/monitor','/tv-wall','/devices','/push-streams','/pull-proxies','/channelmanager','/device-records','/cloud-records','/record-schedule','/legacy-gateway','/platforms'].includes(i.path))) },
    { title: '告警', icon: Bell, base: '/_g3', children: filterPerms(all.filter(i => ['/alarms','/alarm-notifications','/work-orders'].includes(i.path))) },
    { title: '可视化', icon: MapLocation, base: '/_g4', children: filterPerms(all.filter(i => ['/map','/visual-command','/mobile-command'].includes(i.path))) },
    { title: '运维', icon: Setting, base: '/_g5', children: filterPerms(all.filter(i => ['/health','/sla','/ops','/app-logs','/network','/asset-management'].includes(i.path))) },
    { title: '系统', icon: User, base: '/_g6', children: filterPerms(all.filter(i => ['/users','/roles','/organizations','/api-keys','/map-providers','/config-center','/release-center','/audit-center','/reports','/suite-center','/account-security','/help'].includes(i.path))) }
  ]

  return groups.filter(g => g.children.length > 0)
})

const loadPluginMenus = async () => {
  const token = localStorage.getItem('token')
  if (!token) {
    pluginMenus.value = []
    return
  }
  try {
    const res = await api.get('/api/v1/plugins/menus')
    pluginMenus.value = Array.isArray(res.data) ? res.data : []
  } catch {
    pluginMenus.value = []
  }
}

const loadPurchasedPluginIds = async () => {
  if (isServerEdition) return
  try {
    const purchasedRes = await api.get('/api/v1/plugins/purchased')
    const list = Array.isArray(purchasedRes?.data?.plugin_ids) ? purchasedRes.data.plugin_ids : []
    purchasedPluginIds.value = list.map((x: unknown) => String(x))
  } catch {
    purchasedPluginIds.value = []
  }
}

let lastPurchaseSyncAt = 0
const LAST_PURCHASED_PLUGIN_ID_KEY = 'last_purchased_plugin_id'

const emitPurchasedPluginSyncEvent = (focusPluginId?: string) => {
  window.dispatchEvent(new CustomEvent('plugin-purchases-updated', {
    detail: {
      pluginIds: [...purchasedPluginIds.value],
      focusPluginId: focusPluginId ? String(focusPluginId) : ''
    }
  }))
}

const syncPurchasedPluginIds = async (options?: { announce?: boolean; forceEvent?: boolean; pluginId?: string }) => {
  if (isServerEdition) return
  const focusPluginId = String(options?.pluginId || '').trim()
  const previous = purchasedPluginIds.value.join(',')
  await loadPurchasedPluginIds()
  const current = purchasedPluginIds.value.join(',')
  const changed = previous !== current
  if (focusPluginId && purchasedPluginIds.value.includes(focusPluginId)) {
    sessionStorage.setItem(LAST_PURCHASED_PLUGIN_ID_KEY, focusPluginId)
  }
  if (changed || options?.forceEvent) emitPurchasedPluginSyncEvent(focusPluginId)
  if (options?.announce && changed) {
    if (focusPluginId && purchasedPluginIds.value.includes(focusPluginId)) {
      ElMessage.success(`已同步 ${focusPluginId} 的购买状态，可回到插件中心继续安装`)
    } else {
      ElMessage.success(t('plugin.syncedServerPurchase'))
    }
  }
}

const syncPurchasedPluginIdsOnReturn = async () => {
  if (isServerEdition) return
  if (document.visibilityState === 'hidden') return
  const now = Date.now()
  if (now - lastPurchaseSyncAt < 1500) return
  lastPurchaseSyncAt = now
  await syncPurchasedPluginIds()
}

const onWindowFocus = () => {
  void syncPurchasedPluginIdsOnReturn()
}

const onVisibilityReturn = () => {
  if (document.visibilityState === 'visible') {
    void syncPurchasedPluginIdsOnReturn()
  }
}

const onMarketplacePurchaseMessage = (event: MessageEvent) => {
  if (isServerEdition) return
  const data = event.data
  if (!data || typeof data !== 'object') return
  if ((data as { type?: string }).type !== 'plugin-marketplace-purchase-completed') return
  const pluginId = String((data as { pluginId?: unknown }).pluginId || '').trim()
  void syncPurchasedPluginIds({ announce: true, forceEvent: true, pluginId })
}

const consumePurchaseSyncQuery = async () => {
  if (isServerEdition) return
  if (String(route.query.purchase_sync || '').trim() !== '1') return
  const pluginId = String(route.query.purchased_plugin_id || '').trim()
  await syncPurchasedPluginIds({ announce: true, forceEvent: true, pluginId })
  const nextQuery = { ...route.query }
  delete nextQuery.purchase_sync
  delete nextQuery.purchased_plugin_id
  router.replace({ path: route.path, query: nextQuery })
}

const onPluginUpdated = async () => {
  await loadPluginMenus()
  await loadPurchasedPluginIds()
  syncPaidPluginRoutes()
}

onMounted(async () => {
  const isFirstVisit = !localStorage.getItem('first_visit_done')
  if (isFirstVisit) {
    showGuideDialog.value = true
  }
  if (isServerEdition) {
    checkLicenseExpiry()
  }
  loadMarketplaceShopUrl()
  if (!isServerEdition && route.path !== '/setup' && showLayout.value) {
    try {
      const res = await api.get('/api/v1/setup/status')
      if (res.data && res.data.wizard_completed === false) {
        router.replace('/setup')
        return
      }
    } catch (e) {
      logger.warn('安装向导状态检查失败:', e)
    }
  }
  const cached = localStorage.getItem('tenant_branding_cache')
  if (cached) {
    try {
      branding.value = JSON.parse(cached)
    } catch {
      // invalid cache, ignore
    }
  }
  if (isServerEdition) {
    try {
      const res = await api.get('/api/v1/billing/branding/me')
      branding.value = { product_name: res.data.product_name || 'PyGBSentry' }
      localStorage.setItem('tenant_branding_cache', JSON.stringify(res.data))
    } catch (e) {
      logger.warn('品牌信息获取失败:', e)
    }
  }
  await loadPluginMenus()
  await loadPurchasedPluginIds()
  syncPaidPluginRoutes()
  window.addEventListener('plugins-updated', onPluginUpdated)
  window.addEventListener('focus', onWindowFocus)
  window.addEventListener('message', onMarketplacePurchaseMessage)
  document.addEventListener('visibilitychange', onVisibilityReturn)
  await consumePurchaseSyncQuery()
})

onUnmounted(() => {
  window.removeEventListener('plugins-updated', onPluginUpdated)
  window.removeEventListener('focus', onWindowFocus)
  window.removeEventListener('message', onMarketplacePurchaseMessage)
  document.removeEventListener('visibilitychange', onVisibilityReturn)
})

watch(
  () => route.fullPath,
  () => {
    if (!showLayout.value) return
    tagsStore.addView(route)
  },
  { immediate: true }
)

watch(
  () => [purchasedPluginIds.value.join(','), JSON.stringify(pluginMenus.value.map((m) => m.plugin_id).sort())],
  () => syncPaidPluginRoutes()
)

watch(
  () => route.fullPath,
  () => {
    void consumePurchaseSyncQuery()
  }
)

onMounted(() => {
  const affix = appRouter
    .getRoutes()
    .filter(r => (r.meta as Record<string, unknown>)?.affix)
    .map(r => ({ path: r.path, meta: r.meta, name: r.name }))
  tagsStore.ensureAffix(affix as Record<string, unknown>)
})
</script>

<style scoped>
.license-expiry-banner {
  background: linear-gradient(90deg, #fff7e6 0%, #fff1d6 100%);
  border-bottom: 1px solid #ffd591;
  padding: 10px 18px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
  color: #d4380d;
  flex-shrink: 0;
}

.guide-dialog :deep(.el-dialog__header) {
  border-bottom: 1px solid var(--el-border-color-lighter);
  padding: 16px 20px;
  margin-right: 0;
}

.guide-dialog :deep(.el-dialog__body) {
  padding: 24px 20px;
}

.guide-dialog :deep(.el-dialog__footer) {
  border-top: 1px solid var(--el-border-color-lighter);
  padding: 12px 20px;
}

.sidebar-scrollbar {
  height: calc(100vh - var(--logo-height));
}

.sidebar-scrollbar :deep(.el-scrollbar__wrap) {
  overflow-x: hidden;
}

.sidebar-menu {
  border-right: none;
}

.header-wrapper {
  flex-shrink: 0;
  background: #ffffff;
}

.main-content {
  padding: 0;
  background: var(--app-content-bg-gradient);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
</style>
