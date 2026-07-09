import api from '@/utils/http'

export type RoleInfo = {
  role: string
  isSuperuser: boolean
  permissions: string[]
  canManageConfig: boolean
  canQueryAudit: boolean
}

const normalizePermissions = (value: unknown): string[] => {
  if (!Array.isArray(value)) return []
  const set = new Set<string>()
  for (const item of value) {
    const code = String(item || '').trim().toLowerCase()
    if (!code) continue
    if (code === '*') return ['*']
    set.add(code)
  }
  return Array.from(set)
}

export const hasPermission = (permissions: string[], ...targets: string[]) => {
  if (permissions.includes('*')) return true
  return targets.some((target) => permissions.includes(target))
}

let _cachedRoleInfo: RoleInfo | null = null
let _cacheExpiry = 0
const CACHE_TTL_MS = 60_000

// FIX C-3: 空角色信息常量，供未验证时兜底使用
export const EMPTY_ROLE_INFO: RoleInfo = {
  role: '',
  isSuperuser: false,
  permissions: [],
  canManageConfig: false,
  canQueryAudit: false
}

// FIX C-3: 同步读取已缓存的后端权威角色信息（用于无法 await 的场景，如模板内 IP 脱敏）
export const getCachedRoleInfo = (): RoleInfo | null => {
  if (_cachedRoleInfo && Date.now() < _cacheExpiry) return _cachedRoleInfo
  return null
}

// FIX C-3: 异步调用后端 verify-token 获取权威角色信息并写入缓存，优先返回未过期缓存
export const getVerifiedRoleInfo = async (): Promise<RoleInfo | null> => {
  if (_cachedRoleInfo && Date.now() < _cacheExpiry) return _cachedRoleInfo
  return verifyTokenWithBackend()
}

/** @deprecated 禁止用于权限判断，请改用 getVerifiedRoleInfo() —— 客户端 JWT 解码无签名验证 */
export const getRoleInfo = (): RoleInfo => {
  const token = (() => { try { return sessionStorage.getItem('token') || '' } catch { return '' } })()  // P0-4: sessionStorage
  if (!token) {
    _cachedRoleInfo = null
    return {
      role: '',
      isSuperuser: false,
      permissions: [],
      canManageConfig: false,
      canQueryAudit: false
    }
  }

  if (_cachedRoleInfo && Date.now() < _cacheExpiry) {
    return _cachedRoleInfo
  }

  const fallback: RoleInfo = {
    role: '',
    isSuperuser: false,
    permissions: [],
    canManageConfig: false,
    canQueryAudit: false
  }

  const decodeBase64 = (value: string) => {
    const normalized = value.replace(/-/g, '+').replace(/_/g, '/')
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=')
    // atob polyfill — 部分运行时（Node.js SSR/测试、旧浏览器）可能无 atob
    if (typeof atob === 'function') return atob(padded)
    if (typeof Buffer !== 'undefined') return Buffer.from(padded, 'base64').toString('binary')
    throw new Error('No base64 decoder available (atob/Buffer both missing)')
  }

  try {
    const payloadPart = token.split('.')[1] || ''
    if (!payloadPart) return fallback
    const raw = decodeBase64(payloadPart)
    const payload = JSON.parse(raw)
    const role = String(payload?.role || '').toLowerCase()
    const isSuperuser = Boolean(payload?.is_superuser)
    const permissions = normalizePermissions(payload?.permissions)
    const canManageConfig = isSuperuser || hasPermission(permissions, 'config.manage')
    const canQueryAudit = isSuperuser || hasPermission(permissions, 'audit.view')
    const info: RoleInfo = { role, isSuperuser, permissions, canManageConfig, canQueryAudit }
    return info
  } catch {
    return fallback
  }
}

export const verifyTokenWithBackend = async (): Promise<RoleInfo | null> => {
  try {
    const res = await api.get('/api/v1/login/verify-token', {
      withCredentials: true,
    })
    if (res.data?.valid) {
      const role = String(res.data.role || '').toLowerCase()
      const isSuperuser = Boolean(res.data.is_superuser)
      const permissions = normalizePermissions(res.data.permissions)
      const canManageConfig = isSuperuser || hasPermission(permissions, 'config.manage')
      const canQueryAudit = isSuperuser || hasPermission(permissions, 'audit.view')
      const info: RoleInfo = { role, isSuperuser, permissions, canManageConfig, canQueryAudit }
      _cachedRoleInfo = info
      _cacheExpiry = Date.now() + CACHE_TTL_MS
      return info
    }
    return null
  } catch {
    return null
  }
}

export const clearRoleCache = () => {
  _cachedRoleInfo = null
  _cacheExpiry = 0
}
