import { ElMessage, ElMessageBox, ElLoading } from 'element-plus'
import type { LoadingInstance } from 'element-plus/es/components/loading/src/loading'
import { getApiErrorMessage } from './errorMessage'
import i18n from '@/locales'  // FIXED: 国际化

export function showSuccess(message: string, duration = 2000) {
  ElMessage.success({ message, duration })
}

export function showError(operationName: string, error: any, fallback?: string) {
  const detail = getApiErrorMessage(error, fallback || i18n.global.t('common.failed'))  // FIXED: 国际化
  ElMessage.error({ message: `${operationName}${i18n.global.t('common.failed')}：${detail}`, duration: 4000 })  // FIXED: 国际化
}

export async function confirmDangerous(title: string, targetName?: string) {
  const message = targetName ? i18n.global.t('common.deleteConfirm') + `「${targetName}」` : i18n.global.t('common.deleteConfirm')  // FIXED: 国际化
  await ElMessageBox.confirm(message, i18n.global.t('common.tips'), { confirmButtonText: i18n.global.t('common.confirm'), cancelButtonText: i18n.global.t('common.cancel'), type: 'warning' })  // FIXED: 国际化
}

export function showLoading(text?: string) {  // FIXED: 国际化 — 默认值改为i18n
  return ElLoading.service({ text: text || i18n.global.t('common.loading'), lock: true })
}

export function showBatchProgress(current: number, total: number, operationName: string) {
  const percent = Math.round((current / total) * 100)
  ElMessage.info({ message: `${operationName}: ${current}/${total} (${percent}%)`, duration: 1500 })
}

export function showBatchResult(successCount: number, failCount: number, operationName: string) {
  if (failCount === 0) {
    ElMessage.success({ message: `${operationName}: ${successCount} ${i18n.global.t('common.success')}`, duration: 3000 })  // FIXED: 国际化
  } else {
    ElMessage.warning({ message: `${operationName}: ${successCount} ok, ${failCount} ${i18n.global.t('common.failed')}`, duration: 5000 })  // FIXED: 国际化
  }
}
