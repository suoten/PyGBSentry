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
      const placeholder = document.createComment('v-permission')
      el.parentNode?.replaceChild(placeholder, el)
      ;(el as any)._vPermissionPlaceholder = placeholder
    }
  },
  updated(el, binding) {
    const placeholder = (el as any)._vPermissionPlaceholder as Comment | undefined
    if (hasPermission(binding.value)) {
      if (placeholder && placeholder.parentNode) {
        placeholder.parentNode.replaceChild(el, placeholder)
        delete (el as any)._vPermissionPlaceholder
      }
    } else {
      if (el.parentNode) {
        const newPlaceholder = document.createComment('v-permission')
        el.parentNode.replaceChild(newPlaceholder, el)
        ;(el as any)._vPermissionPlaceholder = newPlaceholder
      }
    }
  },
  unmounted(el: HTMLElement) {
    const placeholder = (el as any)._vPermissionPlaceholder
    if (placeholder && placeholder.parentNode) {
      placeholder.parentNode.removeChild(placeholder)
    }
    delete (el as any)._vPermissionPlaceholder
  }
}
