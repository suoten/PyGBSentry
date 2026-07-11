import { createRouter, createWebHistory } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getVerifiedRoleInfo } from '@/utils/auth' // FIX C-1: 依赖后端权威角色信息
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
  { path: '/billing', name: 'Billing', component: () => import('../views/BillingCenter.vue'), meta: { requiresAuth: true, titleKey: 'route.billing', requiredRoles: ['owner'] } }, // FIXED: 国际化 + RBAC
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
  { path: '/users', name: 'Users', component: () => import('../views/UserManager.vue'), meta: { requiresAuth: true, titleKey: 'route.users', requiredRoles: ['admin', 'owner'] } }, // FIXED: 国际化 + RBAC
  { path: '/roles', name: 'Roles', component: () => import('../views/RoleManager.vue'), meta: { requiresAuth: true, titleKey: 'route.roles', requiredRoles: ['admin', 'owner'] } }, // FIXED: 国际化 + RBAC
  { path: '/api-keys', name: 'ApiKeys', component: () => import('../views/ApiKeyManager.vue'), meta: { requiresAuth: true, titleKey: 'route.apiKeys', requiredRoles: ['admin', 'owner'] } }, // FIXED: RBAC
  { path: '/organizations', name: 'Organizations', component: () => import('../views/Organizations.vue'), meta: { requiresAuth: true, titleKey: 'route.organizations', requiredRoles: ['admin', 'owner'] } }, // FIXED: RBAC
  { path: '/ops', name: 'Operations', component: () => import('../views/Operations.vue'), meta: { requiresAuth: true, titleKey: 'route.ops', requiredRoles: ['admin', 'owner', 'operator'] } }, // FIXED: 国际化 + RBAC
  { path: '/asset-management', name: 'AssetManagement', component: () => import('../views/AssetManagement.vue'), meta: { requiresAuth: true, titleKey: 'route.assetManagement', requiredRoles: ['admin', 'owner', 'operator'] } }, // FIXED: RBAC
  { path: '/network', name: 'Network', component: () => import('../views/NetworkOverview.vue'), meta: { requiresAuth: true, titleKey: 'route.network', requiredRoles: ['admin', 'owner'] } }, // FIXED: RBAC
  { path: '/stream-optimization', name: 'StreamOptimization', component: () => import('../views/StreamOptimization.vue'), meta: { requiresAuth: true, titleKey: 'route.streamOptimization', requiredRoles: ['admin', 'owner'] } }, // FIXED: RBAC
  { path: '/map-providers', name: 'MapProviders', component: () => import('../views/MapProviders.vue'), meta: { requiresAuth: true, titleKey: 'route.mapProviders', requiredRoles: ['admin', 'owner'] } }, // FIXED: RBAC
  { path: '/config-center', name: 'ConfigCenter', component: () => import('../views/ConfigCenter.vue'), meta: { requiresAuth: true, titleKey: 'route.configCenter', requiredRoles: ['admin', 'owner'] } }, // FIXED: RBAC
  { path: '/release-center', name: 'ReleaseCenter', component: () => import('../views/ReleaseCenter.vue'), meta: { requiresAuth: true, titleKey: 'route.releaseCenter', requiredRoles: ['admin', 'owner'] } }, // FIXED: RBAC
  { path: '/audit-center', name: 'AuditCenter', component: () => import('../views/AuditCenter.vue'), meta: { requiresAuth: true, titleKey: 'route.auditCenter', requiredRoles: ['admin', 'owner', 'operator'] } }, // FIXED: 国际化 + RBAC
  { path: '/reports', name: 'Reports', component: () => import('../views/ReportCenter.vue'), meta: { requiresAuth: true, titleKey: 'route.reports', requiredRoles: ['admin', 'owner', 'operator'] } }, // FIXED: RBAC
  { path: '/suite-center', name: 'SuiteCenter', component: () => import('../views/SuiteCenter.vue'), meta: { requiresAuth: true, titleKey: 'route.suiteCenter', requiredRoles: ['admin', 'owner'] } }, // FIXED: RBAC
  { path: '/m/reports', name: 'MobileReports', component: () => import('../views/ReportCenter.vue'), meta: { requiresAuth: true, titleKey: 'route.reportsMobile' } }, // FIXED: 国际化
  { path: '/help', name: 'Help', component: () => import('../views/Help.vue'), meta: { requiresAuth: true, titleKey: 'route.help' } }, // FIXED: 国际化
  { path: '/setup', name: 'SetupWizard', component: () => import('../views/SetupWizard.vue'), meta: { requiresAuth: true, titleKey: 'route.setup', requiredRoles: ['owner', 'admin'] } }, // FIXED: RBAC
  { path: '/plugins', name: 'PluginCenter', component: () => import('../views/PluginCenter.vue'), meta: { requiresAuth: true, titleKey: 'route.pluginCenter' } }, // FIXED: 国际化
  { path: '/plugins/detail/:pluginId', name: 'PluginDetail', component: () => import('../views/PluginDetail.vue'), meta: { requiresAuth: true, titleKey: 'route.pluginDetail', hiddenInMenu: true, keepAlive: true } }, // FIXED: 国际化
  { path: '/plugins/runtime/:pluginId', name: 'PluginRuntime', component: () => import('../views/PluginRuntime.vue'), meta: { requiresAuth: true, titleKey: 'route.plugin', hiddenInMenu: true, keepAlive: true } } // FIXED: 国际化
]

// FIXED: [2026-07-10] E-01/F-02 OSS 版隐藏企业版页面 — 后端无对应端点模块，显示会导致 404 [全栈工程师]
// 遵循"不新增功能"原则：OSS 版仅保留核心 GB28181 功能，企业版功能（组织/角色/API密钥/地图/工单/资产/流优化/发布/审计/AI视觉/配置向导）仅在 server 版可用
const OSS_ENTERPRISE_PATHS = new Set<string>([
  '/map', '/map-providers', '/work-orders', '/channels/region',
  '/roles', '/api-keys', '/organizations', '/asset-management',
  '/network', '/stream-optimization', '/release-center',
  '/audit-center', '/ai-vision', '/setup',
])
const ossVisibleRoutes = isServerEdition ? serverRoutes : ossRoutes.filter(r => !OSS_ENTERPRISE_PATHS.has(r.path))

const routes = [
  { path: '/login', name: 'Login', component: () => import('../views/Login.vue'), meta: { titleKey: 'route.login' } }, // FIXED: 国际化
  { path: '/register', name: 'Register', component: () => import('../views/Register.vue'), meta: { titleKey: 'route.register' } }, // FIXED: 国际化
  ...ossVisibleRoutes,
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
  const token = sessionStorage.getItem('token')  // P0-4: sessionStorage
  if (to.meta.requiresAuth && token) {
    const lastVerify = Number(sessionStorage.getItem('_tokenVerifyTs') || 0)
    // SECURITY: 缩短 token 验证间隔到 1 分钟，确保 token 被吊销后最多 1 分钟内生效
    if (Date.now() - lastVerify > 60 * 1000) {
      // FIX C-1: 使用后端 verify-token 权威验证，不再信任可篡改的客户端存储
      const info = await getVerifiedRoleInfo()
      if (!info) {
        sessionStorage.removeItem('token')
        sessionStorage.removeItem('refresh_token')
        sessionStorage.removeItem('_tokenVerifyTs')
        next('/login')
        return
      }
      sessionStorage.setItem('_tokenVerifyTs', String(Date.now()))
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
    // RBAC role check — FIX C-1: 使用后端验证的角色信息，不再解码 JWT 或读取可篡改的 localStorage
    if (to.meta.requiresAuth && token && to.meta.requiredRoles) {
      const verified = await getVerifiedRoleInfo()
      const userRole = (verified?.role || '').toLowerCase()
      const isSuperuser = !!verified?.isSuperuser
      const allowedRoles = (to.meta.requiredRoles as string[]).map(r => r.toLowerCase())
      if (!isSuperuser && !allowedRoles.includes(userRole)) {
        ElMessage.error(t('common.forbidden'))
        next(isServerEdition ? '/plugins' : '/dashboard')
        return
      }
    }
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
