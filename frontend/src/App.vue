<template>
  <div v-if="showLayout" class="common-layout">
    <el-container class="h-screen flex-col">
      <el-dialog
        v-model="showGuideDialog"
        :title="$t('app.guideTitle')"
        width="520px"
        :close-on-click-modal="false"
        :show-close="true"
        center
        class="guide-dialog"
      >
        <!-- 服务器版引导：插件市场 + 购买授权 -->
        <el-steps v-if="isServerEdition" direction="vertical" :active="guideStep" finish-status="success">
          <el-step :title="$t('app.browsePluginMarket')">
            <template #description>
              <span>{{ $t('app.browsePluginMarketDesc') }}</span>
              <el-button size="small" type="primary" class="ml-2" @click="goGuide('/plugins')">{{ $t('app.goto') }}</el-button>
            </template>
          </el-step>
          <el-step :title="$t('app.purchaseAndAuth')">
            <template #description>
              <span>{{ $t('app.purchaseAndAuthDesc') }}</span>
              <el-button size="small" type="primary" class="ml-2" @click="goGuide('/billing')">{{ $t('app.goto') }}</el-button>
            </template>
          </el-step>
        </el-steps>
        <!-- 开源版引导：设备接入 + 监控预览 + 录像告警 + 插件扩展 -->
        <el-steps v-else direction="vertical" :active="guideStep" finish-status="success">
          <el-step :title="$t('app.addFirstDevice')">
            <template #description>
              <span>{{ $t('app.addFirstDeviceDesc') }}</span>
              <el-button size="small" type="primary" class="ml-2" @click="goGuide('/devices')">{{ $t('app.goto') }}</el-button>
            </template>
          </el-step>
          <el-step :title="$t('app.monitorPreview')">
            <template #description>
              <span>{{ $t('app.monitorPreviewDesc') }}</span>
              <el-button size="small" type="primary" class="ml-2" @click="goGuide('/monitor')">{{ $t('app.goto') }}</el-button>
            </template>
          </el-step>
          <el-step :title="$t('app.configRecordAlarm')">
            <template #description>
              <span>{{ $t('app.configRecordAlarmDesc') }}</span>
              <el-button size="small" type="primary" class="ml-2" @click="goGuide('/record-schedule')">{{ $t('app.goto') }}</el-button>
            </template>
          </el-step>
          <el-step :title="$t('app.optionalInstallPlugin')">
            <template #description>
              <span>{{ $t('app.optionalInstallPluginDesc') }}</span>
              <el-button size="small" type="primary" class="ml-2" @click="goGuide('/plugins')">{{ $t('app.goto') }}</el-button>
            </template>
          </el-step>
        </el-steps>
        <template #footer>
          <el-button @click="showGuideDialog = false">{{ $t('app.skip') }}</el-button>
          <el-button type="primary" @click="dismissFirstVisit(); showGuideDialog = false">{{ $t('app.gotIt') }}</el-button>
        </template>
      </el-dialog>

      <div v-if="licenseExpiryList.length && !licenseExpiryDismissed" class="license-expiry-banner">
        <span>{{ $t('app.licenseExpiryBanner', { list: licenseExpiryList.join('、') }) }}</span>
        <div class="flex items-center gap-2">
          <el-button v-if="isServerEdition" size="small" type="primary" @click="goGuide('/billing')">{{ $t('app.renewNow') }}</el-button>
          <el-button v-else size="small" type="primary" @click="openMarketplaceShop">{{ $t('app.renewOnServer') }}</el-button>
          <el-button size="small" text @click="dismissLicenseExpiry">{{ $t('app.doNotRemind') }}</el-button>
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
import { getCachedRoleInfo, getVerifiedRoleInfo, hasPermission, roleInfoVersion } from './utils/auth' // FIX C-3: 改用后端验证角色
import { logger } from '@/utils/logger'
import { getBrandingCache, setBrandingCache } from '@/utils/brandingCache'  // FIX: [2026-07-04] 缺失品牌缓存导入 [全栈工程师]
import { startSessionTimeout, stopSessionTimeout } from '@/utils/sessionTimeout'  // P0-5: 会话超时
import { useUserStore } from './stores/user'  // FIX: [build warning] 改静态导入消除 dynamic/static 导入冲突警告（TopBar/Login 已静态导入，user store 必然在主 chunk，动态导入优化失效）

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
const tagsStore = useTagsViewStore()
const prefsStore = useAppPrefsStore()
// 侧边栏折叠状态从 store 读取（持久化到 localStorage，非敏感 UI 偏好）
const collapsed = computed({
  get: () => prefsStore.sidebarCollapsed,
  set: (val: boolean) => { prefsStore.sidebarCollapsed = val }
})
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
  // FIX: [2026-07-10] 异步组件导入 `() => import(...)` 不可赋值给 `Record<string, unknown>`
  // (TS2322)。改用 any 接受异步组件工厂函数 [全栈工程师]
  component: any
}

const dynamicPaidRoutes: DynRoute[] = [
  { pluginId: 'mobile_app_suite', routeName: 'MobileApp', path: '/mobile-app', title: t('menu.mobileApp'), component: () => import('./views/MobileAppCenter.vue') },
  { pluginId: 'mini_program_suite', routeName: 'MiniProgram', path: '/mini-program', title: t('menu.miniProgram'), component: () => import('./views/MiniProgramCenter.vue') },
  { pluginId: 'mobile_app_suite', routeName: 'AppLogs', path: '/app-logs', title: t('menu.appLogs'), component: () => import('./views/AppLogs.vue') },
  { pluginId: 'tv_wall_suite', routeName: 'TvWall', path: '/tv-wall', title: t('menu.tvWall'), component: () => import('./views/TvWall.vue') },
  { pluginId: 'tv_wall_suite', routeName: 'MobileTvWall', path: '/m/tv-wall', title: t('app.tvWallMobile'), component: () => import('./views/TvWall.vue') },
  { pluginId: 'visual_command_suite', routeName: 'VisualCommand', path: '/visual-command', title: t('menu.visualCommand'), component: () => import('./views/VisualCommand.vue') },
  { pluginId: 'visual_command_suite', routeName: 'MobileVisualCommand', path: '/m/visual-command', title: t('app.visualCommandMobile'), component: () => import('./views/VisualCommand.vue') },
  { pluginId: 'visual_command_suite', routeName: 'MobileCommand', path: '/mobile-command', title: t('menu.mobileCommand'), component: () => import('./views/MobileCommand.vue') },
  { pluginId: 'face_recognition_suite', routeName: 'MobileFaceRecognition', path: '/m/face-recognition', title: t('app.faceRecognitionMobile'), component: () => import('./views/FaceRecognitionMobile.vue') },
  { pluginId: 'plate_recognition_suite', routeName: 'MobilePlateRecognition', path: '/m/plate-recognition', title: t('app.plateRecognitionMobile'), component: () => import('./views/PlateRecognitionMobile.vue') },
  { pluginId: 'behavior_recognition_suite', routeName: 'MobileBehaviorRecognition', path: '/m/behavior-recognition', title: t('app.behaviorRecognitionMobile'), component: () => import('./views/BehaviorRecognitionMobile.vue') },
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
  // SECURITY: 非敏感 UI 标记（引导已阅）— 仅存 '1'，无敏感信息，可安全存入 localStorage
  localStorage.setItem('first_visit_done', '1')
  showGuideDialog.value = false
}
function goGuide(path: string) {
  showGuideDialog.value = false
  router.push(path)
}
function dismissLicenseExpiry() {
  // SECURITY: 非敏感 UI 标记（本月授权到期提示已忽略）— key 含月份后缀，值仅 '1'，可安全存入 localStorage
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
      licenseExpiryList.value = [...expiring.slice(0, 5), t('app.etcCount', { count: expiring.length })]
    } else {
      licenseExpiryList.value = expiring
    }
    // SECURITY: 读取非敏感 UI 标记（见 dismissLicenseExpiry 注释）
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
// FIX: [2026-07-10] Element Plus 图标组件为 DefineComponent，不可赋值给
// `string | { component: unknown }` (TS2322)。改用 any 接受图标组件 [全栈工程师]
type MenuGroup = { title: string; icon: any; base: string; children: MenuItem[] }

const menuGroups = computed<MenuGroup[]>(() => {
  // FIX: [2026-07-21 P0] 读取 roleInfoVersion.value 建立响应式依赖。
  // getCachedRoleInfo() 读取的是模块级普通变量 _cachedRoleInfo（非响应式），
  // Vue 无法追踪其变化。roleInfoVersion ref 在 verifyTokenWithBackend()
  // 成功后递增，这里读取它确保 menuGroups 在角色缓存更新后自动重新求值。
  // 否则菜单会在缓存过期/刷新后“无缘无故消失”，只剩 4 个 bypass 路径，
  // 必须手动刷新整个页面才能恢复。
  void roleInfoVersion.value

  let base = [...ossMenu] as MenuItem[]

  if (canViewAppLogsMenu.value) base.push({ path: '/app-logs', title: 'menu.appLogs', icon: Document })
  if (canUsePaidPlugin('tv_wall_suite')) base.push({ path: '/tv-wall', title: 'menu.tvWall', icon: Monitor })
  if (canUsePaidPlugin('visual_command_suite')) base.push({ path: '/visual-command', title: 'menu.visualCommand', icon: Monitor })
  if (canUsePaidPlugin('visual_command_suite')) base.push({ path: '/mobile-command', title: 'menu.mobileCommand', icon: Promotion }) // FIXED: i18n菜单title

  const runtime = pluginMenus.value.map(item => ({ path: item.path, title: item.title, icon: Box }))
  const all = [...base, ...runtime]

  // FIX: [2026-07-04] verifiedRoleInfo 从未声明为 ref，运行时 ReferenceError。
  // computed 中无法 await getVerifiedRoleInfo()，改用同步 getCachedRoleInfo()
  // 读取已由 onMounted 预热缓存的后端权威角色信息。[全栈工程师]
  //
  // FIX: [2026-07-21 P0] 不再 fallback 到 EMPTY_ROLE_INFO。
  // 原实现 `getCachedRoleInfo() ?? EMPTY_ROLE_INFO` 在缓存未填充时会得到
  // EMPTY_ROLE_INFO（isSuperuser=false, permissions=[]），filterPerms 只放行
  // /help /account-security /plugins /dashboard 这 4 个 bypass 路径，
  // 其余菜单全部被过滤掉 → 用户看到"菜单突然消失只剩几个"。
  // 修复：roleInfo 为 null 时跳过权限过滤，显示全部菜单。安全性由路由守卫的
  // verify-token 检查 + 后端 RBAC 端点校验双重保障，前端菜单可见性只是 UX。
  const roleInfo = getCachedRoleInfo()
  const filterPerms = (items: MenuItem[]) => {
    if (!roleInfo) return items
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
    { title: 'app.menuGroupOverview', icon: Odometer, base: '/_g1', children: filterPerms(all.filter(i => ['/dashboard', '/plugins'].includes(i.path))) },
    { title: 'app.menuGroupBusiness', icon: Monitor, base: '/_g2', children: filterPerms(all.filter(i => ['/monitor','/tv-wall','/devices','/push-streams','/pull-proxies','/channelmanager','/device-records','/cloud-records','/record-schedule','/legacy-gateway','/platforms'].includes(i.path))) },
    { title: 'app.menuGroupAlarm', icon: Bell, base: '/_g3', children: filterPerms(all.filter(i => ['/alarms','/alarm-notifications','/work-orders'].includes(i.path))) },
    { title: 'app.menuGroupVisualization', icon: MapLocation, base: '/_g4', children: filterPerms(all.filter(i => ['/map','/visual-command','/mobile-command'].includes(i.path))) },
    { title: 'app.menuGroupOps', icon: Setting, base: '/_g5', children: filterPerms(all.filter(i => ['/health','/sla','/ops','/app-logs','/network','/asset-management'].includes(i.path))) },
    { title: 'app.menuGroupSystem', icon: User, base: '/_g6', children: filterPerms(all.filter(i => ['/users','/roles','/organizations','/api-keys','/map-providers','/config-center','/release-center','/audit-center','/reports','/suite-center','/account-security','/help'].includes(i.path))) }
  ]

  return groups.filter(g => g.children.length > 0)
})

const loadPluginMenus = async () => {
  const token = sessionStorage.getItem('token')  // P0-4: sessionStorage
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
      ElMessage.success(t('app.syncedPurchaseStatus', { pluginId: focusPluginId }))
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
  // FIX: [2026-07-21 P0] 预热角色缓存 — 路由守卫 beforeEach 也会调用 getVerifiedRoleInfo()，
  // 但如果那次调用失败（网络波动/后端临时不可用），_cachedRoleInfo 保持 null，
  // menuGroups computed 用 EMPTY_ROLE_INFO 过滤 → 菜单只剩 4 个 bypass 项。
  // 这里再调一次提供第二次机会，成功后 roleInfoVersion++ 触发 menuGroups 重新求值。
  if (sessionStorage.getItem('token')) {
    void getVerifiedRoleInfo()
  }
  // SECURITY: 读取非敏感 UI 标记（引导已阅），仅 '1'，无敏感信息
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
  const cached = getBrandingCache()
  if (cached) {
    branding.value = { product_name: cached.product_name || 'PyGBSentry' }
  }
  if (isServerEdition) {
    try {
      const res = await api.get('/api/v1/billing/branding/me')
      branding.value = { product_name: res.data.product_name || 'PyGBSentry' }
      setBrandingCache(res.data)
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
  // P0-5: 启动 30 分钟会话超时 + 活动监听 + exp 检测
  if (sessionStorage.getItem('token')) {
    startSessionTimeout({
      onTimeout: () => {
        ElMessage.warning(t('common.sessionTimeout'))
        useUserStore()
          .logout()
          .finally(() => {
            router.push({ path: '/login', query: { redirect: route.fullPath } })
          })
      },
      onWarning: () => {
        ElMessage.warning(t('common.sessionExpiringSoon'))
      },
      onTokenExpired: () => {
        ElMessage.warning(t('common.sessionExpired'))
        useUserStore().clearAuth()
        router.push({ path: '/login', query: { redirect: route.fullPath } })
      },
    })
  }
})

onUnmounted(() => {
  window.removeEventListener('plugins-updated', onPluginUpdated)
  window.removeEventListener('focus', onWindowFocus)
  window.removeEventListener('message', onMarketplacePurchaseMessage)
  document.removeEventListener('visibilitychange', onVisibilityReturn)
  stopSessionTimeout()  // P0-5: 清理会话超时监听
})

watch(
  () => route.fullPath,
  () => {
    if (!showLayout.value) return
    // FIX: [2026-07-10] RouteLocationNormalizedLoadedGeneric 缺少 title 属性，
    // 不可赋值给 TagView (TS2322)。路由 meta.title 由 addView 内部处理，此处强转 [全栈工程师]
    tagsStore.addView(route as any)
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
  tagsStore.ensureAffix(affix as any)
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
