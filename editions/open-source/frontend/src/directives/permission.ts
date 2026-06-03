import type { Directive } from 'vue'

function getPermissions(): string[] {
  try {
    const raw = localStorage.getItem('roleInfo')
    if (!raw) return []
    const info = JSON.parse(raw)
    if (info.isSuperuser) return ['*']
    return info.permissions || []
  } catch {
    return []
  }
}

export function hasPermission(required: string | string[]): boolean {
  const perms = getPermissions()
  if (perms.includes('*')) return true
  const requiredList = Array.isArray(required) ? required : [required]
  return requiredList.every(r => perms.includes(r))
}

export const vPermission: Directive<HTMLElement, string | string[]> = {
  mounted(el, binding) {
    if (!hasPermission(binding.value)) {
      el.style.display = 'none'
    }
  },
  updated(el, binding) {
    el.style.display = hasPermission(binding.value) ? '' : 'none'
  }
}
