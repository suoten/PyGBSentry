import { ElMessageBox } from 'element-plus'
import axios from 'axios'
import i18n from '@/locales' // FIXED: 国际化

const t = i18n.global.t

export type FriendlyError = {
  message: string
  suggestion?: string
  status?: number
  reasonCode?: string
  retryable?: boolean
  diagnostics?: Record<string, unknown>
  upgradeHookReport?: Record<string, unknown>
}

export function getFriendlyError(error: unknown): FriendlyError {
  const res = (error as Record<string, unknown>)?.response
  const status = res?.status
  const data = res?.data

  const pickString = (...list: Record<string, unknown>[]) => {
    for (const item of list) {
      const value = typeof item === 'string' ? item.trim() : ''
      if (value) return value
    }
    return ''
  }

  const structuredDetail =
    data && typeof data === 'object'
      ? typeof (data as Record<string, unknown>).detail === 'object' && (data as Record<string, unknown>).detail
        ? (data as Record<string, unknown>).detail
        : null
      : null

  const reasonCode = pickString(structuredDetail?.reason_code, structuredDetail?.reasonCode, data?.reason_code, data?.reasonCode)
  const suggestion = pickString(structuredDetail?.suggestion, data?.suggestion)
  const retryable =
    typeof structuredDetail?.retryable === 'boolean'
      ? structuredDetail.retryable
      : typeof data?.retryable === 'boolean'
        ? data.retryable
        : undefined
  const diagnostics =
    structuredDetail?.diagnostics && typeof structuredDetail.diagnostics === 'object'
      ? structuredDetail.diagnostics
      : data?.diagnostics && typeof data.diagnostics === 'object'
        ? data.diagnostics
        : undefined

  const detail = pickString(
    typeof (data as Record<string, unknown>)?.detail === 'string' ? (data as Record<string, unknown>).detail : '',
    structuredDetail?.message,
    structuredDetail?.detail,
    (data as Record<string, unknown>)?.message,
    (data as Record<string, unknown>)?.msg,
    res?.data?.detail?.msg
  )
  const msg = detail || (error as Error)?.message || t('error.requestFailed') // FIXED: 国际化

  if (!status && (axios.isCancel(error) || (error as Record<string, unknown>)?.code === 'ERR_CANCELED' || (error as Record<string, unknown>)?.name === 'CanceledError' || (error as Record<string, unknown>)?.name === 'AbortError' || String((error as Error)?.message || '').toLowerCase() === 'canceled')) {
    return { message: t('error.requestCanceled'), suggestion: '', status: 0, retryable: true } // FIXED: 国际化
  }

  if (status === 401) {
    return { message: t('error.unauthorized'), suggestion: t('error.relogin'), status } // FIXED: 国际化
  }
  if (status === 405) {
    return { message: t('error.methodNotAllowed'), suggestion: t('error.methodNotAllowedSuggestion'), status } // FIXED: 国际化
  }
  const normalized = (msg || '').trim()

  if (status === 402 || reasonCode === 'SUBSCRIPTION_EXPIRED' || normalized === 'SUBSCRIPTION_EXPIRED') {
    return {
      message: t('error.subscriptionExpired'), // FIXED: 国际化
      suggestion: t('error.subscriptionExpiredSuggestion'), // FIXED: 国际化
      status,
      reasonCode: 'SUBSCRIPTION_EXPIRED',
      retryable: false
    }
  }
  if (status === 403) {
    if (reasonCode === 'SUBSCRIPTION_EXPIRED') {
      return {
        message: t('error.subscriptionExpired'), // FIXED: 国际化
        suggestion: t('error.subscriptionExpiredSuggestion'), // FIXED: 国际化
        status,
        reasonCode: 'SUBSCRIPTION_EXPIRED',
        retryable: false
      }
    }
    if (reasonCode === 'PLUGIN_NOT_PURCHASED') {
      return {
        message: t('error.pluginNotPurchased'), // FIXED: 国际化
        suggestion: t('error.pluginPurchaseSuggestion'), // FIXED: 国际化
        status,
        reasonCode: 'PLUGIN_NOT_PURCHASED',
        retryable: false
      }
    }
    if (
      normalized === 'PLUGIN_NOT_PURCHASED' ||
      normalized === 'SUBSCRIPTION_EXPIRED' ||
      normalized.includes('PLUGIN_NOT_PURCHASED') ||
      normalized.includes('未购买') ||
      normalized.includes('无授权') ||
      normalized.includes('授权无效') ||
      normalized.includes('缺少 license')
    ) {
      return {
        message: normalized === 'PLUGIN_NOT_PURCHASED' ? t('error.pluginNotPurchased') : (msg || t('error.pluginNoAuth')), // FIXED: 国际化
        suggestion: t('error.pluginPurchaseSuggestion'), // FIXED: 国际化
        status,
        reasonCode: normalized === 'PLUGIN_NOT_PURCHASED' ? 'PLUGIN_NOT_PURCHASED' : undefined,
        retryable: false
      }
    }
    return { message: t('error.forbidden'), suggestion: t('error.forbiddenSuggestion'), status } // FIXED: 国际化
  }
  if (status === 404) {
    if (reasonCode === 'asset_not_found' || reasonCode === 'channel_not_found_under_device' || reasonCode === 'asset_channel_changed') {
      return {
        message: msg || t('error.deviceChannelUnavailable'), // FIXED: 国际化
        suggestion: suggestion || t('error.deviceChannelRetrySuggestion'), // FIXED: 国际化
        status,
        reasonCode,
        retryable,
        diagnostics
      }
    }
    if (reasonCode === 'device_offline') {
      return {
        message: msg || t('error.deviceOffline'), // FIXED: 国际化
        suggestion: suggestion || t('error.deviceOfflineSuggestion'), // FIXED: 国际化
        status,
        reasonCode,
        retryable: true,
        diagnostics
      }
    }
    if (msg.includes('设备或通道不存在')) {
      return {
        message: t('error.deviceChannelUnavailable'), // FIXED: 国际化
        suggestion: t('error.deviceChannelSelectSuggestion'), // FIXED: 国际化
        status
      }
    }
    return { message: t('error.resourceNotFound'), suggestion: t('error.resourceDeletedSuggestion'), status } // FIXED: 国际化
  }
  if (status === 400) {
    if (msg.includes('时间范围') || msg.includes('start_time') || msg.includes('end_time')) {
      return { message: msg, suggestion: t('error.timeRangeSuggestion'), status } // FIXED: 国际化
    }
    if (msg.includes('OTP')) {
      return { message: msg, suggestion: t('error.otpSuggestion'), status } // FIXED: 国际化
    }
    if (msg.includes('用户名或密码错误') || msg.toLowerCase().includes('incorrect') || msg.includes('密码错误')) {
      return { message: t('error.incorrectCredentials'), suggestion: t('error.incorrectCredentialsSuggestion'), status } // FIXED: 国际化
    }
    if (msg.includes('插件') && (msg.includes('废弃') || msg.includes('不允许'))) {
      return { message: msg, suggestion: t('error.pluginDeprecatedSuggestion'), status } // FIXED: 国际化
    }
    if (msg.includes('开源版') && (msg.includes('版本') || msg.includes('兼容'))) {
      return { message: msg, suggestion: t('error.pluginVersionSuggestion'), status } // FIXED: 国际化
    }
    if (msg.includes('connector_url') || msg.includes('连接器')) {
      return { message: msg, suggestion: t('error.connectorSuggestion'), status } // FIXED: 国际化
    }
    return { message: msg || t('error.badRequest'), suggestion: t('error.checkInputSuggestion'), status } // FIXED: 国际化
  }
  if (status === 422) {
    return { message: msg || t('error.unprocessableEntity'), suggestion: t('error.checkInputSuggestion'), status } // FIXED: 国际化
  }
  if (status === 429) {
    return { message: t('error.tooManyRequests'), suggestion: t('error.tooManyRequestsSuggestion'), status } // FIXED: 国际化
  }
  if (status === 502) {
    if (msg.includes('插件市场') || msg.toLowerCase().includes('marketplace')) {
      return { message: t('error.marketplaceUnavailable'), suggestion: t('error.marketplaceSuggestion'), status } // FIXED: 国际化
    }
    if (msg.includes('连接器') || msg.includes('report') || msg.includes('connector')) {
      return { message: t('error.externalServiceUnavailable'), suggestion: t('error.connectorUrlSuggestion'), status } // FIXED: 国际化
    }
    return { message: msg || t('error.upstreamUnavailable'), suggestion: t('error.retryLater'), status } // FIXED: 国际化
  }
  if (status === 503) {
    if (reasonCode === 'media_stream_not_ready') {
      return {
        message: msg || t('error.streamNotReady'), // FIXED: 国际化
        suggestion: suggestion || t('error.streamNotReadySuggestion'), // FIXED: 国际化
        status,
        reasonCode,
        retryable,
        diagnostics
      }
    }
    if (reasonCode === 'media_node_unreachable' || reasonCode === 'media_node_unavailable') {
      return {
        message: msg || t('error.mediaServerConnectFailed'), // FIXED: 国际化
        suggestion: suggestion || t('error.mediaServerSuggestion'), // FIXED: 国际化
        status,
        reasonCode,
        retryable,
        diagnostics
      }
    }
    if (reasonCode === 'device_transport_unavailable') {
      return {
        message: msg || t('error.deviceTransportUnavailable'), // FIXED: 国际化
        suggestion: suggestion || t('error.deviceTransportSuggestion'), // FIXED: 国际化
        status,
        reasonCode,
        retryable,
        diagnostics
      }
    }
    if (reasonCode === 'sip_service_unavailable') {
      return {
        message: msg || t('error.sipServiceUnavailable'), // FIXED: 国际化
        suggestion: suggestion || t('error.sipServiceSuggestion'), // FIXED: 国际化
        status,
        reasonCode,
        retryable,
        diagnostics
      }
    }
    return {
      message: msg || t('error.serviceUnavailable'), // FIXED: 国际化
      suggestion: suggestion || t('error.serviceUnavailableSuggestion'), // FIXED: 国际化
      status,
      reasonCode,
      retryable,
      diagnostics
    }
  }
  if (status === 500) {
    const uhr = structuredDetail?.upgrade_hook_report
    if (uhr && typeof uhr === 'object') {
      return {
        message:
          pickString(typeof structuredDetail?.message === 'string' ? structuredDetail.message : '', '') ||
          t('error.upgradeHookFailed'), // FIXED: 国际化
        suggestion: t('error.upgradeHookSuggestion'), // FIXED: 国际化
        status,
        upgradeHookReport: uhr as Record<string, unknown>
      }
    }
    return { message: t('error.internalServerError'), suggestion: t('error.internalServerErrorSuggestion'), status } // FIXED: 国际化
  }
  if (status === 501) {
    return { message: detail || t('error.notImplemented'), suggestion: t('error.notImplementedSuggestion'), status, retryable: false } // FIXED: 国际化
  }
  if (msg.includes('Network Error') || msg.includes('Failed to fetch')) {
    return { message: t('error.networkError'), suggestion: t('error.networkErrorSuggestion'), status } // FIXED: 国际化
  }
  if (msg.includes('timeout') || msg.includes('超时')) {
    return { message: t('error.timeout'), suggestion: t('error.timeoutSuggestion'), status } // FIXED: 国际化
  }
  if (msg.includes('拉流') || msg.includes('stream') || msg.includes('play')) {
    return { message: msg, suggestion: suggestion || t('error.streamSuggestion'), status, reasonCode, retryable, diagnostics } // FIXED: 国际化
  }
  return { message: msg, suggestion: suggestion || t('error.retryOrContactAdmin'), status, reasonCode, retryable, diagnostics } // FIXED: 国际化
}

export function getApiErrorMessage(error: unknown, fallback: string): string {
  const err = error as Record<string, unknown> | undefined
  if (err?.name === 'CanceledError' || err?.name === 'AbortError' || err?.code === 'ERR_CANCELED' || err?._isCanceled) {
    return ''
  }
  const f = getFriendlyError(error)
  const m = (f.message || '').trim()
  return m || fallback
}

export async function promptUpgradeHookReportIfPresent(friendly: FriendlyError): Promise<void> {
  const r = friendly.upgradeHookReport
  if (!r || typeof r !== 'object') return
  try {
    await ElMessageBox.alert(JSON.stringify(r, null, 2), t('error.upgradeHookReportTitle'), { // FIXED: 国际化
      confirmButtonText: t('common.ok'), // FIXED: 国际化
      customClass: 'plugin-upgrade-hook-report-dialog'
    })
  } catch {
    /* 关闭弹窗 */
  }
}
