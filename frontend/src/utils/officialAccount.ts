/**
 * officialAccount — 官网账户（双版账户打通）前端凭证管理。
 *
 * 开源版插件中心连接商业版插件商城：用户需登录自己的 PyGBSentry 官网账户
 * （由服务器版 /api/v1/oss/login 签发、经开源版后端 /api/v1/plugins/official-account/*
 * 代理转发）才能下载/购买商城插件。官方 token 由前端保管（localStorage），
 * 后续插件中心请求通过 X-Official-Token 请求头携带（见 utils/http.ts 请求拦截器），
 * 服务端转发服务器版时优先用它验证官网身份与购买权益。
 *
 * SECURITY：官网账户 token 属于跨版凭证，按后端设计「由前端保管」，与平台会话
 * （sessionStorage）分开存放；统一走 safeLS* 包装，避免隐私模式/配额异常抛错。
 */
import axios from 'axios'
import { safeLSGet, safeLSSet, safeLSRemove } from './storage'

export const OFFICIAL_TOKEN_STORAGE_KEY = 'pygb_official_token'
export const OFFICIAL_USER_STORAGE_KEY = 'pygb_official_user'

/** 插件中心（含官网账户代理）接口前缀 — http.ts 请求拦截器据此附加 X-Official-Token */
export const PLUGINS_API_PREFIX = '/api/v1/plugins/'

export type OfficialUser = {
  id: string | number
  username: string
  site_role?: string
  email?: string
}

export type OfficialAccountStatus = {
  marketplace_configured: boolean
  marketplace_enabled: boolean
  marketplace_host: string
}

export type OfficialAuthResult = {
  token: string
  user: OfficialUser
}

export function getOfficialToken(): string | null {
  const token = (safeLSGet(OFFICIAL_TOKEN_STORAGE_KEY) || '').trim()
  return token || null
}

export function getOfficialUser(): OfficialUser | null {
  const raw = safeLSGet(OFFICIAL_USER_STORAGE_KEY)
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as Partial<OfficialUser> | null
    if (parsed && typeof parsed === 'object' && parsed.username) {
      return {
        id: parsed.id ?? '',
        username: String(parsed.username),
        site_role: typeof parsed.site_role === 'string' ? parsed.site_role : undefined,
        email: typeof parsed.email === 'string' ? parsed.email : undefined,
      }
    }
  } catch {
    /* 用户 JSON 损坏则视为未登录 */
  }
  return null
}

export function setOfficialAccount(token: string, user: OfficialUser): void {
  safeLSSet(OFFICIAL_TOKEN_STORAGE_KEY, token)
  safeLSSet(OFFICIAL_USER_STORAGE_KEY, JSON.stringify(user))
}

export function clearOfficialAccount(): void {
  safeLSRemove(OFFICIAL_TOKEN_STORAGE_KEY)
  safeLSRemove(OFFICIAL_USER_STORAGE_KEY)
}

const OFFICIAL_API_TIMEOUT_MS = 15000

/**
 * 官网账户代理端点统一走裸 axios（与 http.ts 内 refresh-token 同一模式）：
 * 这些端点不属于平台会话体系，若走共享 api 实例，其 401 会触发平台 token
 * 刷新/登出/跳登录页流程，语义完全不符且会误清平台会话。
 */
async function postOfficialApi<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const base = String(import.meta.env.VITE_API_BASE_URL || '/')
  const url = `${base.replace(/\/+$/, '')}${path}`
  const res = await axios.post<T>(url, body, { timeout: OFFICIAL_API_TIMEOUT_MS, withCredentials: true })
  return res.data
}

function normalizeOfficialUser(payload: unknown, fallbackUsername = ''): OfficialUser {
  const data = (payload && typeof payload === 'object' ? payload : {}) as Record<string, unknown>
  const userRaw = (data.user && typeof data.user === 'object' ? data.user : {}) as Record<string, unknown>
  return {
    id: (userRaw.id as string | number) ?? '',
    username: String(userRaw.username || fallbackUsername),
    site_role: typeof userRaw.site_role === 'string' ? userRaw.site_role : undefined,
    email: typeof userRaw.email === 'string' ? userRaw.email : undefined,
  }
}

export async function loginOfficialAccount(username: string, password: string): Promise<OfficialAuthResult> {
  const data = await postOfficialApi<Record<string, unknown>>('/api/v1/plugins/official-account/login', {
    username,
    password,
  })
  const token = String((data as { token?: unknown }).token || '')
  if (!token) throw new Error('No token in official account login response')
  return { token, user: normalizeOfficialUser(data, username) }
}

export async function registerOfficialAccount(
  username: string,
  password: string,
  email?: string
): Promise<OfficialAuthResult> {
  const body: Record<string, unknown> = { username, password }
  if (email) body.email = email
  const data = await postOfficialApi<Record<string, unknown>>('/api/v1/plugins/official-account/register', body)
  const token = String((data as { token?: unknown }).token || '')
  if (!token) throw new Error('No token in official account register response')
  return { token, user: normalizeOfficialUser(data, username) }
}

/**
 * 校验本地官网账户 token 是否仍有效；401（token 失效）时自动清理本地状态并返回 null。
 * 非 401 异常（网络波动、商城未配置 503/502）保守保留本地登录态。
 */
export async function verifyOfficialAccount(): Promise<OfficialUser | null> {
  const token = getOfficialToken()
  if (!token) return null
  try {
    const data = await postOfficialApi<Record<string, unknown>>('/api/v1/plugins/official-account/verify', { token })
    if (data && (data as { valid?: unknown }).valid === false) {
      clearOfficialAccount()
      return null
    }
    const user = normalizeOfficialUser(data)
    if (user.username) {
      // 后端返回了最新用户信息，刷新本地缓存
      safeLSSet(OFFICIAL_USER_STORAGE_KEY, JSON.stringify(user))
      return user
    }
    return getOfficialUser()
  } catch (error) {
    const status = (error as { response?: { status?: number } })?.response?.status
    if (status === 401) {
      clearOfficialAccount()
      return null
    }
    return getOfficialUser()
  }
}

/**
 * 提取官网账户/插件商城代理接口的后端 detail 文案
 * （401 {detail: "..."}、结构化 {detail: {reason_code, message, ...}} 等）。
 */
export function extractOfficialApiDetail(error: unknown): string {
  const data = (error as { response?: { data?: unknown } })?.response?.data
  if (typeof data === 'string' && data.trim()) return data.trim()
  if (!data || typeof data !== 'object') return ''
  const record = data as Record<string, unknown>
  const detail = record.detail
  if (typeof detail === 'string' && detail.trim()) return detail.trim()
  if (detail && typeof detail === 'object') {
    const structured = detail as Record<string, unknown>
    if (typeof structured.message === 'string' && structured.message.trim()) return structured.message.trim()
    if (typeof structured.detail === 'string' && structured.detail.trim()) return structured.detail.trim()
  }
  for (const key of ['message', 'msg'] as const) {
    const value = record[key]
    if (typeof value === 'string' && value.trim()) return value.trim()
  }
  return ''
}

/**
 * 平台会话 401 的固定文案（后端 app/api/deps.py 的 credentials_exception）。
 * 命中它说明是平台登录态失效而非官网账户问题，应继续走 http.ts 的平台刷新/登出流程。
 */
const PLATFORM_SESSION_401_DETAIL = 'Not authenticated or session expired, please login again'

/**
 * 判断插件中心接口的 401/403 是否属于官网账户语义：
 * - 'login'    → 官网 token 缺失/失效（引导弹出官网账户登录）
 * - 'purchase' → 未购买/订阅过期（引导购买）
 * - null       → 与官网账户无关（平台会话等，交回原有处理）
 */
export function classifyOfficialAccountError(error: unknown): 'login' | 'purchase' | null {
  const status = (error as { response?: { status?: number } })?.response?.status
  if (status !== 401 && status !== 403) return null
  const url = String((error as { config?: { url?: string } })?.config?.url || '')
  if (!url.startsWith(PLUGINS_API_PREFIX)) return null
  const detail = extractOfficialApiDetail(error)
  if (status === 401) {
    // 平台会话失效（固定文案）→ 保持原有平台登录流程
    if (detail === PLATFORM_SESSION_401_DETAIL) return null
    return 'login'
  }
  const normalized = detail.toLowerCase()
  if (
    normalized.includes('plugin_not_purchased') ||
    normalized.includes('subscription_expired') ||
    normalized.includes('purchase') ||
    normalized.includes('未购买') ||
    normalized.includes('购买')
  ) {
    return 'purchase'
  }
  return null
}
