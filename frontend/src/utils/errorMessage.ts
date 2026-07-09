/**
 * Friendly error message generator — converts axios/FastAPI errors into
 * user-friendly messages with optional suggestions and retry hints.
 */
import i18n from '@/locales'

export interface FriendlyError {
  message: string
  suggestion: string
  status: number | null
  reasonCode: string
  retryable: boolean
  diagnostics: string
  upgradeHookReport: unknown
}

/** Extract a human-readable detail string from an axios error response. */
function _extractDetail(data: unknown): string {
  if (!data || typeof data !== 'object') return ''
  const obj = data as Record<string, unknown>
  // FastAPI HTTPException detail
  if (typeof obj.detail === 'string') return obj.detail
  // Pydantic validation error array
  if (Array.isArray(obj.detail)) {
    const first = obj.detail[0] as Record<string, unknown> | undefined
    if (first) {
      const loc = Array.isArray(first.loc) ? first.loc.join('.') : ''
      const msg = typeof first.msg === 'string' ? first.msg : ''
      return loc ? `${loc}: ${msg}` : msg
    }
  }
  if (typeof obj.message === 'string') return obj.message
  return ''
}

/** Status-code → handler descriptor for HTTP errors. */
interface StatusHandler {
  msgKey: string
  reasonCode: string
  retryable?: boolean
  useDetail?: boolean
}

const NETWORK_ERROR_CODES = new Set(['ECONNREFUSED', 'ECONNRESET', 'ETIMEDOUT', 'ERR_NETWORK'])

const STATUS_HANDLERS: Record<number, StatusHandler> = {
  400: { msgKey: 'common.badRequest', reasonCode: '', useDetail: true },
  401: { msgKey: 'common.sessionExpired', reasonCode: 'auth', useDetail: true },
  403: { msgKey: 'common.forbidden', reasonCode: 'forbidden', useDetail: true },
  404: { msgKey: 'common.notFound', reasonCode: 'not_found', useDetail: true },
  422: { msgKey: 'common.validationFailed', reasonCode: 'validation', useDetail: true },
  423: { msgKey: 'common.locked', reasonCode: 'locked', useDetail: true },
  429: { msgKey: 'common.tooManyRequests', reasonCode: 'rate_limit', retryable: true, useDetail: true },
  500: { msgKey: 'common.serverError', reasonCode: 'server', retryable: true },
  501: { msgKey: 'common.notImplemented', reasonCode: 'not_implemented' },
  502: { msgKey: 'common.serviceUnavailable', reasonCode: 'unavailable', retryable: true },
  503: { msgKey: 'common.serviceUnavailable', reasonCode: 'unavailable', retryable: true },
  504: { msgKey: 'common.gatewayTimeout', reasonCode: 'timeout', retryable: true },
}

/** Build the default FriendlyError template. */
function _emptyError(): FriendlyError {
  return {
    message: i18n.global.t('common.unknownError'),
    suggestion: '',
    status: null,
    reasonCode: '',
    retryable: false,
    diagnostics: '',
    upgradeHookReport: null,
  }
}

/** Handle network-level errors (no HTTP response received). */
function _handleNetworkError(code: string): FriendlyError {
  const retryable = NETWORK_ERROR_CODES.has(code)
  return {
    ..._emptyError(),
    message: i18n.global.t('common.networkError'),
    retryable,
    reasonCode: 'network',
  }
}

/** Handle an HTTP error by status code using a lookup table. */
function _handleHttpError(status: number, detail: string): FriendlyError {
  const handler = STATUS_HANDLERS[status]
  if (!handler) {
    return { ..._emptyError(), message: detail || i18n.global.t('common.unknownError'), status }
  }
  const message = handler.useDetail
    ? (detail || i18n.global.t(handler.msgKey))
    : i18n.global.t(handler.msgKey)
  return {
    ..._emptyError(),
    message,
    status,
    reasonCode: handler.reasonCode,
    retryable: handler.retryable ?? false,
  }
}

/**
 * Convert an axios error into a FriendlyError with i18n messages.
 */
export function getFriendlyError(error: unknown): FriendlyError {
  if (!error || typeof error !== 'object') return _emptyError()

  const axiosErr = error as {
    response?: { status?: number; data?: unknown }
    code?: string
    message?: string
  }

  // Network-level errors (no response from server)
  if (!axiosErr.response) {
    return _handleNetworkError(axiosErr.code || '')
  }

  const status = axiosErr.response.status ?? 0
  const detail = _extractDetail(axiosErr.response.data)
  return _handleHttpError(status, detail)
}

/**
 * Extract a plain error message string from an axios/FastAPI error.
 * Returns `fallback` if no detail can be extracted.
 */
export function getApiErrorMessage(error: unknown, fallback: string): string {
  const f = getFriendlyError(error)
  return (f.message || '').trim() || fallback
}

/**
 * If an error response contains an upgrade-hook report (plugin marketplace
 * upgrade flow), prompt the user with the details.  Currently a safe no-op
 * when no report is present.
 */
export function promptUpgradeHookReportIfPresent(error: unknown): void {
  if (!error || typeof error !== 'object') return
  const axiosErr = error as { response?: { data?: unknown } }
  const data = axiosErr.response?.data as Record<string, unknown> | undefined
  if (!data || typeof data !== 'object') return
  const report = data.upgrade_hook_report
  if (!report) return
  // Log the report for debugging; a full UI prompt can be added per-product
  console.info('[upgrade-hook-report]', report)
}

export default getFriendlyError
