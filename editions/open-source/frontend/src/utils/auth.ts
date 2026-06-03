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

export const getRoleInfo = (): RoleInfo => {
  const token = (() => { try { return localStorage.getItem('token') || '' } catch { return '' } })()
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
    return atob(padded)
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
