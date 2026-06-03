import { createRouter, createWebHistory } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '@/utils/http'
import i18n from '@/locales' // FIXED: 国际化

const t = i18n.global.t // FIXED: 国际化

const isServerEdition = (import.meta.env.VITE_APP_EDITION || 'oss') === 'server'
const allowPublicRegistration = String(import.meta.env.VITE_ALLOW_PUBLIC_REGISTRATION || '') === 'true'

const OSS_DYNAMIC_PAID_PATH_TO_ROUTE: Record<string, string> = {
  '/mobile-app': 'MobileApp',
  '/mini-program': 'MiniProgram',
  '/app-logs': 'AppLogs',
  '/tv-wall': 'TvWall',
  '/m/tv-wall': 'MobileTvWall',
  '/visual-command': 'VisualCommand',
  '/m/visual-command': 'MobileVisualCommand',
  '/m/face-recognition': 'MobileFaceRecognition',
  '/m/plate-recognition': 'MobilePlateRecognition',
  '/m/behavior-recognition': 'MobileBehaviorRecognition',
  '/mobile-command': 'MobileCommand',
}
const OSS_PAID_GATE_TOAST_PREFIX = 'oss_paid_route_gate_'
const serverRoutes = [
  { path: '/', redirect: '/plugins', meta: { requiresAuth: true, titleKey: 'route.home' } }, // FIXED: 国际化
  { path: '/plugins', name: 'PluginCenter', component: () => import('../views/PluginCenter.vue'), meta: { requiresAuth: true, titleKey: 'route.pluginCenter', affix: true, keepAlive: true } }, // FIXED: 国际化
  { path: '/plugins/detail/:pluginId', name: 'PluginDetail', component: () => import('../views/PluginDetail.vue'), meta: { requiresAuth: true, titleKey: 'route.pluginDetail', hiddenInMenu: true, keepAlive: true } }, // FIXED: 国际化
  { path: '/plugins/runtime/:pluginId', name: 'PluginRuntime', component: () => import('../views/PluginRuntime.vue'), meta: { requiresAuth: true, titleKey: 'route.plugin', hiddenInMenu: true, keepAlive: true } }, // FIXED: 国际化
  { path: '/profile', name: 'ProfileCenter', component: () => import('../views/ProfileCenter.vue'), meta: { requiresAuth: true, titleKey: 'route.profile' } }, // FIXED: 国际化
  { path: '/account-security', name: 'AccountSecurity', component: () => import('../views/AccountSecurity.vue'), meta: { requiresAuth: true, titleKey: 'route.accountSecurity' } }, // FIXED: 国际化
  { path: '/help', name: 'Help', component: () => import('../views/Help.vue'), meta: { requiresAuth: true, titleKey: 'route.help' } }, // FIXED: 国际化
  { path: '/billing', name: 'Billing', component: () => import('../views/BillingCenter.vue'), meta: { requiresAuth: true, titleKey: 'route.billing' } }, // FIXED: 国际化
  { path: '/tv-wall', name: 'TvWall', component: () => import('../views/TvWall.vue'), meta: { requiresAuth: true, titleKey: 'route.tvWall' } }, // FIXED: 国际化
  { path: '/legacy-gateway', name: 'LegacyGateway', component: () => import('../views/LegacyGateway.vue'), meta: { requiresAuth: true, titleKey: 'route.legacyGateway' } }, // FIXED: 国际化
  { path: '/platforms', name: 'CascadePlatforms', component: () => import('../views/CascadePlatforms.vue'), meta: { requiresAuth: true, titleKey: 'route.platforms' } }, // FIXED: 国际化
  { path: '/ai-vision', name: 'StructuredEventCenter', component: () => import('../views/StructuredEventCenter.vue'), meta: { requiresAuth: true, titleKey: 'route.aiVision' } }, // FIXED: 路由名称与组件名对齐
  { path: '/mobile-app', name: 'MobileApp', component: () => import('../views/MobileAppCenter.vue'), meta: { requiresAuth: true, titleKey: 'route.mobileApp' } }, // FIXED: 国际化
  { path: '/mini-program', name: 'MiniProgram', component: () => import('../views/MiniProgramCenter.vue'), meta: { requiresAuth: true, titleKey: 'route.miniProgram' } }, // FIXED: 国际化
  { path: '/api-keys', name: 'ApiKeys', component: () => import('../views/ApiKeyManager.vue'), meta: { requiresAuth: true, titleKey: 'route.apiKeys' } } // FIXED: 国际化
]

const ossRoutes = [
  { path: '/', redirect: '/dashboard', meta: { requiresAuth: true, titleKey: 'route.home' } }, // FIXED: 国际化
  { path: '/live', redirect: '/monitor', meta: { requiresAuth: true, titleKey: 'route.livePreview' } }, // FIXED: 国际化
  { path: '/channel', redirect: '/channels', meta: { requiresAuth: true, titleKey: 'route.channelCenter' } }, // FIXED: 国际化
  { path: '/device', redirect: '/devices', meta: { requiresAuth: true, titleKey: 'route.gbDevice' } }, // FIXED: 国际化
  { path: '/platform', redirect: '/platforms', meta: { requiresAuth: true, titleKey: 'route.platforms' } }, // FIXED: 国际化
  { path: '/proxy', redirect: '/pull-proxies', meta: { requiresAuth: true, titleKey: 'route.pullProxy' } }, // FIXED: 国际化
  { path: '/push', redirect: '/push-streams', meta: { requiresAuth: true, titleKey: 'route.pushStream' } }, // FIXED: 国际化
  { path: '/recordPlan', redirect: '/record-schedule', meta: { requiresAuth: true, titleKey: 'route.recordSchedule' } }, // FIXED: 国际化
  { path: '/cloudRecord', redirect: '/cloud-records', meta: { requiresAuth: true, titleKey: 'route.cloudRecord' } }, // FIXED: 国际化
  { path: '/dashboard', name: 'Dashboard', component: () => import('../views/Dashboard.vue'), meta: { requiresAuth: true, titleKey: 'route.dashboard', affix: true, keepAlive: true } }, // FIXED: 国际化
  { path: '/monitor', name: 'Monitor', component: () => import('../views/MonitorCenter.vue'), meta: { requiresAuth: true, titleKey: 'route.monitor' } }, // FIXED: 国际化
  { path: '/map', name: 'Map', component: () => import('../views/GisMap.vue'), meta: { requiresAuth: true, titleKey: 'route.map' } }, // FIXED: 国际化
  { path: '/health', name: 'Health', component: () => import('../views/HealthDashboard.vue'), meta: { requiresAuth: true, titleKey: 'route.health' } }, // FIXED: 国际化
  { path: '/sla', name: 'SLA', component: () => import('../views/SlaDashboard.vue'), meta: { requiresAuth: true, titleKey: 'route.sla' } }, // FIXED: 国际化
  { path: '/alarms', name: 'Alarms', component: () => import('../views/AlarmCenter.vue'), meta: { requiresAuth: true, titleKey: 'route.alarms' } }, // FIXED: 国际化
  { path: '/alarm-notifications', name: 'AlarmNotifications', component: () => import('../views/AlarmNotifications.vue'), meta: { requiresAuth: true, titleKey: 'route.alarmNotifications' } }, // FIXED: 国际化
  { path: '/profile', name: 'ProfileCenter', component: () => import('../views/ProfileCenter.vue'), meta: { requiresAuth: true, titleKey: 'route.profile' } }, // FIXED: 国际化
  { path: '/account-security', name: 'AccountSecurity', component: () => import('../views/AccountSecurity.vue'), meta: { requiresAuth: true, titleKey: 'route.accountSecurity' } }, // FIXED: 国际化
  { path: '/alarm-link-rules', name: 'AlarmLinkRules', component: () => import('../views/AlarmLinkRules.vue'), meta: { requiresAuth: true, titleKey: 'route.alarmLinkRules' } }, // FIXED: 国际化
  { path: '/work-orders', name: 'WorkOrders', component: () => import('../views/WorkOrders.vue'), meta: { requiresAuth: true, titleKey: 'route.workOrders' } }, // FIXED: 国际化
  { path: '/devices', name: 'Devices', component: () => import('../views/DeviceList.vue'), meta: { requiresAuth: true, titleKey: 'route.devices' } }, // FIXED: 国际化
  { path: '/push-streams', name: 'PushStreams', component: () => import('../views/PushStreamList.vue'), meta: { requiresAuth: true, titleKey: 'route.pushStream' } }, // FIXED: 国际化
  { path: '/pull-proxies', name: 'PullProxies', component: () => import('../views/PullProxyList.vue'), meta: { requiresAuth: true, titleKey: 'route.pullProxy' } }, // FIXED: 国际化
  { path: '/legacy-gateway', name: 'LegacyGateway', component: () => import('../views/LegacyGateway.vue'), meta: { requiresAuth: true, titleKey: 'route.legacyGateway' } }, // FIXED: 国际化
  { path: '/platforms', name: 'CascadePlatforms', component: () => import('../views/CascadePlatforms.vue'), meta: { requiresAuth: true, titleKey: 'route.platforms' } }, // FIXED: 国际化
  { path: '/ai-vision', name: 'StructuredEventCenter', component: () => import('../views/StructuredEventCenter.vue'), meta: { requiresAuth: true, titleKey: 'route.aiVision' } }, // FIXED: 路由名称与组件名对齐
  { path: '/channels', name: 'Channels', component: () => import('../views/ChannelList.vue'), meta: { requiresAuth: true, titleKey: 'route.channels' } }, // FIXED: 国际化
  { path: '/channelmanager', redirect: '/channels/legacy', meta: { requiresAuth: true, titleKey: 'route.channelManager' } }, // FIXED: 国际化
  { path: '/channels/legacy', name: 'ChannelsLegacy', component: () => import('../views/ChannelManager.vue'), meta: { requiresAuth: true, titleKey: 'route.channelTree' } }, // FIXED: 国际化
  { path: '/channels/region', name: 'ChannelsRegion', component: () => import('../views/ChannelRegion.vue'), meta: { requiresAuth: true, titleKey: 'route.region' } }, // FIXED: 国际化
  { path: '/channels/group', name: 'ChannelsGroup', component: () => import('../views/ChannelGroup.vue'), meta: { requiresAuth: true, titleKey: 'route.group' } }, // FIXED: 国际化
  { path: '/device-records', name: 'DeviceRecords', component: () => import('../views/DeviceRecords.vue'), meta: { requiresAuth: true, titleKey: 'route.deviceRecords' } }, // FIXED: 国际化
  { path: '/cloud-records', name: 'CloudRecords', component: () => import('../views/CloudRecords.vue'), meta: { requiresAuth: true, titleKey: 'route.cloudRecord' } }, // FIXED: 国际化
  { path: '/record-schedule', name: 'RecordSchedule', component: () => import('../views/RecordSchedule.vue'), meta: { requiresAuth: true, titleKey: 'route.recordSchedule' } }, // FIXED: 国际化
  { path: '/users', name: 'Users', component: () => import('../views/UserManager.vue'), meta: { requiresAuth: true, titleKey: 'route.users' } }, // FIXED: 国际化
  { path: '/roles', name: 'Roles', component: () => import('../views/RoleManager.vue'), meta: { requiresAuth: true, titleKey: 'route.roles' } }, // FIXED: 国际化
  { path: '/api-keys', name: 'ApiKeys', component: () => import('../views/ApiKeyManager.vue'), meta: { requiresAuth: true, titleKey: 'route.apiKeys' } }, // FIXED: 国际化
  { path: '/organizations', name: 'Organizations', component: () => import('../views/Organizations.vue'), meta: { requiresAuth: true, titleKey: 'route.organizations' } }, // FIXED: 国际化
  { path: '/ops', name: 'Operations', component: () => import('../views/Operations.vue'), meta: { requiresAuth: true, titleKey: 'route.ops' } }, // FIXED: 国际化
  { path: '/asset-management', name: 'AssetManagement', component: () => import('../views/AssetManagement.vue'), meta: { requiresAuth: true, titleKey: 'route.assetManagement' } }, // FIXED: 国际化
  { path: '/network', name: 'Network', component: () => import('../views/NetworkOverview.vue'), meta: { requiresAuth: true, titleKey: 'route.network' } }, // FIXED: 国际化
  { path: '/stream-optimization', name: 'StreamOptimization', component: () => import('../views/StreamOptimization.vue'), meta: { requiresAuth: true, titleKey: 'route.streamOptimization' } }, // FIXED: 国际化
  { path: '/map-providers', name: 'MapProviders', component: () => import('../views/MapProviders.vue'), meta: { requiresAuth: true, titleKey: 'route.mapProviders' } }, // FIXED: 国际化
  { path: '/config-center', name: 'ConfigCenter', component: () => import('../views/ConfigCenter.vue'), meta: { requiresAuth: true, titleKey: 'route.configCenter' } }, // FIXED: 国际化
  { path: '/release-center', name: 'ReleaseCenter', component: () => import('../views/ReleaseCenter.vue'), meta: { requiresAuth: true, titleKey: 'route.releaseCenter' } }, // FIXED: 国际化
  { path: '/audit-center', name: 'AuditCenter', component: () => import('../views/AuditCenter.vue'), meta: { requiresAuth: true, titleKey: 'route.auditCenter' } }, // FIXED: 国际化
  { path: '/reports', name: 'Reports', component: () => import('../views/ReportCenter.vue'), meta: { requiresAuth: true, titleKey: 'route.reports' } }, // FIXED: 国际化
  { path: '/suite-center', name: 'SuiteCenter', component: () => import('../views/SuiteCenter.vue'), meta: { requiresAuth: true, titleKey: 'route.suiteCenter' } }, // FIXED: 国际化
  { path: '/m/reports', name: 'MobileReports', component: () => import('../views/ReportCenter.vue'), meta: { requiresAuth: true, titleKey: 'route.reportsMobile' } }, // FIXED: 国际化
  { path: '/help', name: 'Help', component: () => import('../views/Help.vue'), meta: { requiresAuth: true, titleKey: 'route.help' } }, // FIXED: 国际化
  { path: '/setup', name: 'SetupWizard', component: () => import('../views/SetupWizard.vue'), meta: { requiresAuth: true, titleKey: 'route.setup' } }, // FIXED: 国际化
  { path: '/plugins', name: 'PluginCenter', component: () => import('../views/PluginCenter.vue'), meta: { requiresAuth: true, titleKey: 'route.pluginCenter' } }, // FIXED: 国际化
  { path: '/plugins/detail/:pluginId', name: 'PluginDetail', component: () => import('../views/PluginDetail.vue'), meta: { requiresAuth: true, titleKey: 'route.pluginDetail', hiddenInMenu: true, keepAlive: true } }, // FIXED: 国际化
  { path: '/plugins/runtime/:pluginId', name: 'PluginRuntime', component: () => import('../views/PluginRuntime.vue'), meta: { requiresAuth: true, titleKey: 'route.plugin', hiddenInMenu: true, keepAlive: true } } // FIXED: 国际化
]

const routes = [
  { path: '/login', name: 'Login', component: () => import('../views/Login.vue'), meta: { titleKey: 'route.login' } }, // FIXED: 国际化
  { path: '/register', name: 'Register', component: () => import('../views/Register.vue'), meta: { titleKey: 'route.register' } }, // FIXED: 国际化
  ...(isServerEdition ? serverRoutes : ossRoutes),
  { path: '/:pathMatch(.*)*', name: 'NotFound', component: () => import('../views/NotFound.vue'), meta: { titleKey: 'route.notFound' } } // FIXED: 国际化
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

const APP_TITLE = 'PyGBSentry'

router.beforeEach(async (to, from, next) => {
  try {
    const { clearStalePendingRequests } = await import('@/utils/httpDedupe')
    clearStalePendingRequests()
  } catch { /* ignore */ }
  const token = localStorage.getItem('token')
  if (to.meta.requiresAuth && token) {
    const lastVerify = Number(localStorage.getItem('_tokenVerifyTs') || 0)
    if (Date.now() - lastVerify > 5 * 60 * 1000) {
      try {
        await api.get('/api/v1/login/verify-token')
        localStorage.setItem('_tokenVerifyTs', String(Date.now()))
      } catch {
        localStorage.removeItem('token')
        localStorage.removeItem('refresh_token')
        localStorage.removeItem('_tokenVerifyTs')
        next('/login')
        return
      }
    }
  }
  if (to.path === '/register' && !allowPublicRegistration) {
    next('/login')
    return
  }
  if (to.meta.requiresAuth && !token) {
    next('/login')
  } else if ((to.path === '/login' || to.path === '/register') && token) {
    next(isServerEdition ? '/plugins' : '/dashboard')
  } else {
    if (!isServerEdition) {
      const dynName = OSS_DYNAMIC_PAID_PATH_TO_ROUTE[to.path]
      const isPaidFeature = to.meta?.paidFeature === true
      if ((dynName && !router.hasRoute(dynName)) || isPaidFeature) {
        if (!token) {
          next('/login')
          return
        }
        const toastKey = OSS_PAID_GATE_TOAST_PREFIX + to.path
        if (!sessionStorage.getItem(toastKey)) {
          sessionStorage.setItem(toastKey, '1')
          ElMessage.warning(t('error.paidFeatureRequired')) // FIXED: 国际化
        }
        next('/plugins')
        return
      }
    }
    next()
  }
})

router.afterEach((to) => {
  const titleKey = to.meta?.titleKey as string
  const title = titleKey ? t(titleKey) : (String(to.name || '') || 'PyGBSentry') // FIXED: 国际化
  document.title = title ? `${title} - ${APP_TITLE}` : APP_TITLE
})

export default router
