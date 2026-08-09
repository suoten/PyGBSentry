import { ref } from 'vue'
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
let _staleRoleInfo: RoleInfo | null = null  // FIX: [2026-07-16] 保存上一次有效缓存，过期时返回 stale 而非 null
let _cacheExpiry = 0
const CACHE_TTL_MS = 60_000

// FIX: [2026-07-13] 响应式版本号 — 每次 roleInfo 缓存变更时递增，
// 让依赖 getCachedRoleInfo() 的 computed（如 App.vue 的 menuGroups）
// 能在缓存更新后自动重新求值。模块级 let 变量不是 Vue 响应式依赖，
// 必须通过 ref 触发。[全栈工程师]
export const roleInfoVersion = ref(0)

// FIX C-3: 空角色信息常量，供未验证时兜底使用
export const EMPTY_ROLE_INFO: RoleInfo = {
  role: '',
  isSuperuser: false,
  permissions: [],
  canManageConfig: false,
  canQueryAudit: false
}

// FIX C-3: 同步读取已缓存的后端权威角色信息（用于无法 await 的场景，如模板内 IP 脱敏）
// FIX: [2026-07-16] stale-while-revalidate — 缓存过期时返回上一次有效缓存（stale），
// 而非 null。避免 menuGroups computed 在缓存过期瞬间用 EMPTY_ROLE_INFO 过滤掉大部分菜单，
// 导致左侧菜单闪烁/缺失。异步刷新由 getVerifiedRoleInfo() 在路由守卫中完成。
//
// FIX: [2026-07-21 P0] 彻底修复"菜单突然消失只剩 4 个 bypass 路径"的 Bug。
// 原实现：缓存过期时优先返回 _staleRoleInfo，但 _staleRoleInfo 只在第二次成功
// verify-token 后才被设置（verifyTokenWithBackend 中 `if (_cachedRoleInfo)` 才备份）。
// 首次登录后 60 秒缓存过期时 _staleRoleInfo 仍为 null → getCachedRoleInfo 返回 null
// → menuGroups computed 用 EMPTY_ROLE_INFO 过滤 → 只剩 /help /account-security
// /plugins /dashboard 这 4 个 bypass 路径。等 verify-token 重新返回时菜单才恢复，
// 这就是用户看到的"菜单突然消失，过一会儿又全部出现"现象。
// 修复：缓存过期时，按 _staleRoleInfo → _cachedRoleInfo 顺序降级返回，
// 确保 menuGroups 始终能拿到上一次有效的角色信息，避免菜单闪烁。
export const getCachedRoleInfo = (): RoleInfo | null => {
  if (_cachedRoleInfo && Date.now() < _cacheExpiry) return _cachedRoleInfo
  // 缓存过期：按 stale → cached 顺序降级返回，避免菜单瞬间消失
  if (_staleRoleInfo) return _staleRoleInfo
  if (_cachedRoleInfo) return _cachedRoleInfo
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
      // FIX: [2026-07-16] 保存上一次有效缓存为 stale，用于过期时的降级读取
      if (_cachedRoleInfo) {
        _staleRoleInfo = _cachedRoleInfo
      }
      _cachedRoleInfo = info
      _cacheExpiry = Date.now() + CACHE_TTL_MS
      roleInfoVersion.value++  // FIX: [2026-07-13] 通知依赖 computed 重新求值
      return info
    }
    return null
  } catch {
    return null
  }
}

export const clearRoleCache = () => {
  _cachedRoleInfo = null
  _staleRoleInfo = null  // FIX: [2026-07-16] 清空 stale 缓存（用户登出）
  _cacheExpiry = 0
  roleInfoVersion.value++  // FIX: [2026-07-13] 通知依赖 computed 重新求值
}
