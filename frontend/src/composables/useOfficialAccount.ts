/**
 * useOfficialAccount — 官网账户（双版账户打通）共享状态与操作。
 *
 * 插件中心 / 插件详情共用同一份官网账户登录态（模块级单例）：
 * - 页面挂载时刷新商城配置（status）并校验本地 token（verify）；
 * - 未登录时操作商城插件（安装/购买）先弹出官网账户登录弹窗，登录成功后自动继续原操作；
 * - 安装/购买过程中遇到官网账户语义的 401/403，引导重新登录或购买。
 */
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import i18n from '@/locales'
import api from '@/utils/http'
import { logger } from '@/utils/logger'
import {
  classifyOfficialAccountError,
  clearOfficialAccount,
  extractOfficialApiDetail,
  getOfficialToken,
  getOfficialUser,
  loginOfficialAccount,
  registerOfficialAccount,
  setOfficialAccount,
  verifyOfficialAccount,
  type OfficialAccountStatus,
  type OfficialUser,
} from '@/utils/officialAccount'

const t = i18n.global.t

// 模块级单例：跨页面共享官网账户登录态与弹窗状态
const officialUser = ref<OfficialUser | null>(getOfficialUser())
const officialStatus = ref<OfficialAccountStatus>({
  marketplace_configured: false,
  marketplace_enabled: false,
  marketplace_host: '',
})
const authDialogVisible = ref(false)
const authTab = ref<'login' | 'register'>('login')
const authIntentVisible = ref(false)
const authLoading = ref(false)
const authError = ref('')

// 登录成功后需要自动继续的挂起操作（安装/购买）
let pendingAction: (() => void | Promise<void>) | null = null

export type OfficialAuthFormModel = {
  username: string
  password: string
  email: string
}

export function useOfficialAccount() {
  /** 商城可用（已配置且启用）时才展示官网账户入口 */
  const accountVisible = computed(
    () => officialStatus.value.marketplace_configured && officialStatus.value.marketplace_enabled
  )

  /** 挂载时调用：刷新商城配置 + 校验本地官网 token（存在时） */
  const refreshOfficialAccount = async () => {
    try {
      const res = await api.get('/api/v1/plugins/official-account/status')
      officialStatus.value = {
        marketplace_configured: !!res.data?.marketplace_configured,
        marketplace_enabled: !!res.data?.marketplace_enabled,
        marketplace_host: String(res.data?.marketplace_host || ''),
      }
    } catch {
      logger.warn('Failed to load official account status')
    }
    if (getOfficialToken()) {
      // token 失效（verify 401）时内部会自动清理本地状态
      officialUser.value = await verifyOfficialAccount()
    } else {
      officialUser.value = null
    }
  }

  const openAuthDialog = (options?: { tab?: 'login' | 'register'; intent?: boolean }) => {
    authTab.value = options?.tab || 'login'
    authIntentVisible.value = !!options?.intent
    authError.value = ''
    authDialogVisible.value = true
  }

  const isMarketplacePlugin = (plugin: { package_url?: string; type?: string } | null | undefined): boolean =>
    Boolean(plugin && (plugin.package_url || plugin.type === 'paid'))

  /**
   * 商城插件（有 package_url 或 type=paid）需要官网账户：未登录时先弹登录弹窗，
   * 登录成功后自动继续 action；已登录或非商城插件直接执行。
   */
  const ensureOfficialAccount = async (
    plugin: { package_url?: string; type?: string } | null | undefined,
    action: () => void | Promise<void>
  ) => {
    if (!isMarketplacePlugin(plugin) || officialUser.value) {
      await action()
      return
    }
    pendingAction = action
    openAuthDialog({ tab: 'login', intent: true })
  }

  /** 登录/注册提交（由弹窗组件调用），成功后存 token+user 并继续挂起操作 */
  const submitOfficialAuth = async (model: OfficialAuthFormModel) => {
    const username = model.username.trim()
    const password = model.password
    authLoading.value = true
    authError.value = ''
    try {
      const result =
        authTab.value === 'login'
          ? await loginOfficialAccount(username, password)
          : await registerOfficialAccount(username, password, model.email.trim() || undefined)
      setOfficialAccount(result.token, result.user)
      officialUser.value = result.user
      ElMessage.success(t(authTab.value === 'login' ? 'plugin.officialLoginSuccess' : 'plugin.officialRegisterSuccess'))
      authDialogVisible.value = false
      const resume = pendingAction
      pendingAction = null
      if (resume) {
        await resume()
      } else {
        // 登录态变化后商城已购列表可能更新，通知页面刷新
        window.dispatchEvent(new Event('official-account-changed'))
      }
    } catch (error) {
      // 401 等错误直接展示后端 detail 文案
      authError.value = extractOfficialApiDetail(error) || t('plugin.officialAuthFailed')
    } finally {
      authLoading.value = false
    }
  }

  const logoutOfficialAccount = () => {
    clearOfficialAccount()
    officialUser.value = null
    pendingAction = null
    ElMessage.success(t('plugin.officialLogoutSuccess'))
    window.dispatchEvent(new Event('official-account-changed'))
  }

  /**
   * 安装/购买失败后的官网账户引导。命中官网登录语义（401）时清理失效登录态、
   * 弹出登录弹窗并挂起 retry（登录成功后自动继续）；返回是否已接管处理。
   */
  const guideOfficialAccountOnError = (error: unknown, retry: () => void | Promise<void>): boolean => {
    if (classifyOfficialAccountError(error) !== 'login') return false
    officialUser.value = null
    clearOfficialAccount()
    pendingAction = retry
    const detail = extractOfficialApiDetail(error)
    ElMessage.warning(detail || t('plugin.officialAccountRequiredShort'))
    openAuthDialog({ tab: 'login', intent: true })
    return true
  }

  return {
    officialUser,
    officialStatus,
    accountVisible,
    authDialogVisible,
    authTab,
    authIntentVisible,
    authLoading,
    authError,
    isMarketplacePlugin,
    refreshOfficialAccount,
    openAuthDialog,
    ensureOfficialAccount,
    submitOfficialAuth,
    logoutOfficialAccount,
    guideOfficialAccountOnError,
  }
}
