import { getFriendlyError } from './errorMessage'
import i18n from '@/locales'

export const EMPTY_TEXT = i18n.global.t('common.noData') // FIXED: i18n

export const buildSuccessMessage = (action: string, detail?: string) => {
  return detail ? `${action}${i18n.global.t('common.success')}：${detail}` : `${action}${i18n.global.t('common.success')}` // FIXED: i18n
}

export const buildErrorMessage = (action: string, error: unknown, fallback?: string) => {
  const f = getFriendlyError(error)
  const detail = (f.message || '').trim() || (fallback || '').trim()
  if (detail) {
    return `${action}${i18n.global.t('common.failed')}：${detail}` // FIXED: i18n
  }
  return `${action}${i18n.global.t('common.failed')}` // FIXED: i18n
}
