import axios from 'axios'
import { ElMessage } from 'element-plus'
import { getFriendlyError } from './errorMessage'
import { HTTP_STATUS } from '@/constants/httpStatus'
import i18n from '@/locales'  // FIXED: 国际化
import { safeSSGet, safeSSSet, safeSSRemove } from '@/utils/storage'  // P0-4: token 迁移到 sessionStorage

const API_TIMEOUT = Number(import.meta.env.VITE_API_TIMEOUT) || 30000
const TOKEN_CACHE_TTL = Number(import.meta.env.VITE_TOKEN_CACHE_TTL) || 5000

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/',
  timeout: API_TIMEOUT,
  withCredentials: true,
})

let _tokenCache: string | null = null
let _tokenCacheExpiry = 0

function getCachedToken(): string | null {
  if (_tokenCache && Date.now() < _tokenCacheExpiry) {
    return _tokenCache
  }
  _tokenCache = safeSSGet('token')
  _tokenCacheExpiry = Date.now() + TOKEN_CACHE_TTL
  return _tokenCache
}

export function invalidateTokenCache() {
  _tokenCache = null
  _tokenCacheExpiry = 0
}

api.interceptors.request.use(
  (config) => {
    const token = getCachedToken()
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    if (config.url?.includes('admin') || config.url?.includes('delete')) {
      config.headers['X-Sensitive-Operation'] = 'true'
    }
    return config
  },
  (error) => Promise.reject(error)
)

let _isRefreshing = false
let _refreshSubscribers: Array<{ resolve: (token: string) => void; reject: (err: unknown) => void }> = []

function onTokenRefreshed(token: string) {
  _refreshSubscribers.forEach(({ resolve }) => {
    try {
      resolve(token)
    } catch (e) {
      // SECURITY: 不再静默忽略订阅者错误，记录日志便于排查
      console.error('[http] Token refresh subscriber resolve error:', e)
    }
  })
  _refreshSubscribers = []
}

function onRefreshFailed(err: unknown) {
  // SECURITY: 统一处理所有订阅者的刷新失败 — 不静默忽略，确保所有请求被正确拒绝
  _refreshSubscribers.forEach(({ reject: rej }) => {
    try {
      rej(err)
    } catch (e) {
      console.error('[http] Token refresh subscriber reject error:', e)
    }
  })
  _refreshSubscribers = []
}

function addRefreshSubscriber(resolve: (token: string) => void, reject: (err: unknown) => void) {
  _refreshSubscribers.push({ resolve, reject })
}

let _lastNetworkToastTs = 0
const NETWORK_TOAST_COOLDOWN_MS = 5000
const NETWORK_RETRY_MAX = 2
const NETWORK_RETRYABLE_METHODS = ['get', 'head', 'options']

function toastNetworkErrorOnce() {
  // FIX [2026-09-02 P2]: 后端重启/网络抖动时多个并发请求同时失败会刷屏，
  // 5 秒内只提示一次。
  const now = Date.now()
  if (now - _lastNetworkToastTs < NETWORK_TOAST_COOLDOWN_MS) return
  _lastNetworkToastTs = now
  ElMessage.error(i18n.global.t('common.networkError'))
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (axios.isCancel(error) || error.code === 'ERR_CANCELED' || error.name === 'CanceledError' || error.name === 'AbortError') {
      error._isCanceled = true
      return Promise.reject(error)
    }
    if (!error.response) {
      // FIX [2026-09-02 P2]: 后端重启/网络抖动的容错 ——
      // 1) 幂等请求（GET/HEAD/OPTIONS）自动重试最多 2 次（指数退避），
      //    避免后端重启窗口内页面数据请求全部失败；
      // 2) 重试仍失败才提示，且 5 秒内只提示一次，防止并发请求刷屏。
      const config = error.config || {}
      const method = String(config.method || 'get').toLowerCase()
      const retries = Number(config.__networkRetries || 0)
      if (NETWORK_RETRYABLE_METHODS.includes(method) && retries < NETWORK_RETRY_MAX) {
        config.__networkRetries = retries + 1
        await new Promise((r) => setTimeout(r, 600 * retries + 400))
        return api(config)
      }
      toastNetworkErrorOnce()
      return Promise.reject(error)
    }
    const status = error.response.status
    const originalRequest = error.config
    if (status === HTTP_STATUS.UNAUTHORIZED && !originalRequest._retry) {
      const token = safeSSGet('token')
      if (!token) {
        if (!window.location.pathname.includes('/login')) {
          ElMessage.info(i18n.global.t('common.pleaseLogin'))  // FIXED: 国际化
          import('@/router').then(({ default: router }) => {
            router.push({ path: '/login', query: { redirect: router.currentRoute.value.fullPath } })
          })
        }
        return Promise.reject(error)
      }
      if (_isRefreshing) {
        return new Promise((resolve, reject) => {
          addRefreshSubscriber((newToken: string) => {
            originalRequest.headers.Authorization = `Bearer ${newToken}`
            resolve(api(originalRequest))
          }, (err: unknown) => {
            reject(err)
          })
        })
      }
      originalRequest._retry = true
      _isRefreshing = true
      try {
        const refreshToken = safeSSGet('refresh_token')
        if (!refreshToken) throw new Error('No refresh token')
        // FIX: [2026-07-16 P1] 为 token 刷新请求添加超时，避免后端慢响应时
        // 阻塞所有排队的 401 重试请求导致前端假死
        const res = await axios.post(
          `${import.meta.env.VITE_API_BASE_URL || '/'}/api/v1/login/refresh-token`,
          { refresh_token: refreshToken },
          { withCredentials: true, timeout: 10000 }
        )
        const newToken = res.data?.access_token || res.data?.token
        if (newToken && typeof newToken === 'string') {
          safeSSSet('token', newToken)
          if (res.data?.refresh_token && typeof res.data.refresh_token === 'string') {
            safeSSSet('refresh_token', res.data.refresh_token)
          }
          invalidateTokenCache()
          onTokenRefreshed(newToken)
          originalRequest.headers.Authorization = `Bearer ${newToken}`
          return api(originalRequest)
        }
        throw new Error('No token in refresh response')
      } catch (refreshError) {
        // FIX [2026-09-02 P2]: 区分刷新失败的类型 ——
        // 后端重启/网络抖动时 refresh 请求本身发不出去（无 response），
        // 此时 access token 仍然有效（JWT 无状态），不应清除登录态强制登出；
        // 只有服务端明确拒绝刷新（有 response）才视为会话失效。
        const hasServerResponse = !!(refreshError as { response?: unknown })?.response
        if (!hasServerResponse) {
          toastNetworkErrorOnce()
          onRefreshFailed(error)
          _refreshSubscribers = []
          return Promise.reject(error)
        }
        safeSSRemove('token')
        safeSSRemove('refresh_token')
        invalidateTokenCache()
        onRefreshFailed(error)
        _refreshSubscribers = []
        ElMessage.warning(i18n.global.t('common.sessionExpired'))  // FIXED: 国际化
        import('@/router').then(({ default: router }) => {
          router.push({ path: '/login', query: { redirect: router.currentRoute.value.fullPath } })
        })
        return Promise.reject(error)
      } finally {
        _isRefreshing = false
      }
    }
    if (status === HTTP_STATUS.UNAUTHORIZED) {
      safeSSRemove('token')
      safeSSRemove('refresh_token')
      invalidateTokenCache()
      if (!window.location.pathname.includes('/login')) {
        ElMessage.warning(i18n.global.t('common.sessionExpired'))  // FIXED: 国际化
        import('@/router').then(({ default: router }) => {
          router.push({ path: '/login', query: { redirect: router.currentRoute.value.fullPath } })
        })
      }
      return Promise.reject(error)
    }
    if (status === HTTP_STATUS.FORBIDDEN) {
      ElMessage.error(i18n.global.t('common.forbidden'))  // FIXED: 国际化
      return Promise.reject(error)
    }
    if (status === HTTP_STATUS.UNPROCESSABLE_ENTITY) {
      const { message: msg422 } = getFriendlyError(error)
      ElMessage.error(i18n.global.t('common.validationFailed', { msg: msg422 || i18n.global.t('common.checkInput') }))  // FIXED: 国际化
      return Promise.reject(error)
    }
    if (status === HTTP_STATUS.TOO_MANY_REQUESTS) {
      // FIX: [2026-07-16 P1] 解析 Retry-After 头，告知用户等待时间
      const retryAfter = error.response.headers?.['retry-after']
      const retryMsg = retryAfter
        ? i18n.global.t('common.tooManyRequestsRetry', { seconds: retryAfter })
        : i18n.global.t('common.tooManyRequests')
      ElMessage.warning(retryMsg)  // FIXED: 国际化
      return Promise.reject(error)
    }
    // FIX: [2026-07-16 P1] 处理 423 账户锁定，解析 Retry-After 头
    if (status === HTTP_STATUS.LOCKED) {
      const retryAfter = error.response.headers?.['retry-after']
      const lockMsg = retryAfter
        ? i18n.global.t('common.accountLockedRetry', { minutes: Math.ceil(Number(retryAfter) / 60) })
        : i18n.global.t('common.accountLocked')
      ElMessage.error(lockMsg)
      return Promise.reject(error)
    }
    if (status === HTTP_STATUS.NOT_IMPLEMENTED) {
      const { message: msg501 } = getFriendlyError(error)
      ElMessage.warning(i18n.global.t('common.notImplemented'))  // FIXED: 国际化
      return Promise.reject(error)
    }
    if (status === HTTP_STATUS.NOT_FOUND) {
      const { message: msg404 } = getFriendlyError(error)
      ElMessage.error(msg404 || i18n.global.t('common.notFound'))  // FIXED: 国际化
      return Promise.reject(error)
    }
    if (status === HTTP_STATUS.BAD_GATEWAY || status === HTTP_STATUS.SERVICE_UNAVAILABLE) {
      ElMessage.error(i18n.global.t('common.serviceUnavailable'))  // FIXED: 国际化
      return Promise.reject(error)
    }
    const skipFriendly = (error.config as Record<string, unknown>)?.skipFriendlyMessage
    if (!skipFriendly && status !== HTTP_STATUS.UNAUTHORIZED) {
      const { message, suggestion } = getFriendlyError(error)
      ElMessage.error(suggestion ? `${message}. ${suggestion}` : message)  // FIXED: A-05 中文句号→英文句号
    }
    return Promise.reject(error)
  }
)

export { api }
export default api
