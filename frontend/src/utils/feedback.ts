/**
 * User feedback helpers — thin wrappers around ElMessage / ElMessageBox
 * with friendly error extraction.
 */
import { ElMessage, ElMessageBox } from 'element-plus'
import { getFriendlyError } from './errorMessage'

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
 * Show a dangerous confirmation dialog.  Resolves if the user confirms,
 * rejects if the user cancels.
 */
export async function confirmDangerous(message: string, title?: string): Promise<void> {
  await ElMessageBox.confirm(message, title || message, {
    confirmButtonText: 'OK',
    cancelButtonText: 'Cancel',
    type: 'warning',
  })
}
