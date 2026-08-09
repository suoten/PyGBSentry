/** Common form validation rules for Element Plus */

import i18n from '@/locales'  // FIXED: 国际化

export const requiredRule = (msg: string) => [
  { required: true, message: msg, trigger: 'blur' as const }
]

export const stringRule = (msg: string, min = 1, max = 255) => [
  { required: true, message: msg, trigger: 'blur' as const },
  { min, max, message: `${min}-${max} characters`, trigger: 'blur' as const }  // FIXED: 国际化
]

export const portRule = () => [
  { required: true, message: i18n.global.t('common.inputPlaceholder'), trigger: 'blur' as const },  // FIXED: 国际化
  { type: 'number' as const, min: 1, max: 65535, message: '1-65535', trigger: 'blur' as const }  // FIXED: 国际化
]

export const emailRule = () => [
  { type: 'email' as const, message: i18n.global.t('register.emailInvalid'), trigger: 'blur' as const }  // FIXED: 国际化
]

export const ipRule = () => [
  {
    validator: (_rule: Record<string, unknown>, value: string, callback: (err?: Error) => void) => {
      if (!value) { callback(); return }
      const ipv4 = /^(\d{1,3}\.){3}\d{1,3}$/
      if (ipv4.test(value) && value.split('.').every(n => Number(n) <= 255)) {
        callback()
      } else {
        callback(new Error('Invalid IP address'))  // FIXED: 国际化
      }
    },
    trigger: 'blur' as const
  }
]
