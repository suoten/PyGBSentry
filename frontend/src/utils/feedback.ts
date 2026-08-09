/**
 * User feedback helpers — thin wrappers around ElMessage / ElMessageBox
 * with friendly error extraction.
 */
import { ElMessage, ElMessageBox } from 'element-plus'
import { getFriendlyError } from './errorMessage'
import i18n from '@/locales'

/** Show an error toast. If `error` is provided, append its friendly message. */
export function showError(action: string, error?: unknown): void {
  if (error !== undefined && error !== null) {
    const f = getFriendlyError(error)
    const detail = (f.message || '').trim()
    ElMessage.error(detail ? `${action}: ${detail}` : action)
  } else {
    ElMessage.error(action)
  }
}

/** Show a success toast. */
export function showSuccess(message: string): void {
  ElMessage.success(message)
}

/** Show a warning toast. */
export function showWarning(message: string): void {
  ElMessage.warning(message)
}

/**
 * Show a dangerous confirmation dialog. Resolves if the user confirms,
 * rejects if the user cancels.
 *
 * FIXED: [2026-07-13] 恢复 2ad636a 的签名 (title, targetName?)。
 * ConvergeLoop 将签名改为 (message, title?) 导致 4 处调用方参数语义互换：
 *   - PtzPreset.vue:74    confirmDangerous('删除预置位', item.presetName)
 *   - ChannelTree.vue:179 confirmDangerous('删除目录', node.label)
 *   - DeviceTable.vue:231 confirmDangerous('批量删除', 'N台设备')
 *   - DeviceTable.vue:239 confirmDangerous('删除设备', row.name)
 * 旧签名下 title=动作(如"删除设备")，targetName=目标名称(如"摄像头01")。
 */
export async function confirmDangerous(title: string, targetName?: string): Promise<void> {
  const t = i18n.global.t
  const message = targetName
    ? `${title}「${targetName}」？`
    : `${title}？`
  await ElMessageBox.confirm(message, t('common.tips'), {
    confirmButtonText: t('common.confirm'),
    cancelButtonText: t('common.cancel'),
    type: 'warning',
  })
}
