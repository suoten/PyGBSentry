import { getFriendlyError } from './errorMessage'
import i18n from '@/locales'

// FIXED: 国际化 — EMPTY_TEXT 与消息构造函数统一走 i18n
export const EMPTY_TEXT = i18n.global.t('common.noData')

export const buildSuccessMessage = (action: string, detail?: string) => {
  if (detail) {
    return i18n.global.t('common.actionSuccessDetail', { action, detail })
  }
  return i18n.global.t('common.actionSuccess', { action })
}

export const buildErrorMessage = (action: string, error: unknown, fallback?: string) => {
  const f = getFriendlyError(error)
  const detail = (f.message || '').trim() || (fallback || '').trim()
  if (detail) {
    return i18n.global.t('common.actionFailedDetail', { action, detail })
  }
  return i18n.global.t('common.actionFailed', { action })
}
