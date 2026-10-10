import i18n from '@/locales'

const t = i18n.global.t

export type PluginMarketplaceStateInput = {
  id: string
  type?: string
  status?: string
  deprecated_message?: string
  min_oss_version?: string
}

export type PluginMarketplaceStateContext = {
  installed: boolean
  purchased: boolean
  hasUpdate: boolean
  ossVersionIncompatible: boolean
}

export type PluginMarketplaceDisplayState = {
  key: 'installed' | 'update_available' | 'purchased_pending_install' | 'ready_to_buy' | 'ready_to_install' | 'restricted'
  label: string
  tagType: 'success' | 'warning' | 'info' | 'danger' | 'primary'
  detail: string
  primaryAction: 'none' | 'buy' | 'install' | 'update'
  primaryActionLabel: string
}

export const resolvePluginMarketplaceDisplayState = (
  plugin: PluginMarketplaceStateInput,
  context: PluginMarketplaceStateContext
): PluginMarketplaceDisplayState => {
  if ((plugin.status || '').trim() === 'deprecated') {
    return {
      key: 'restricted',
      label: t('plugin.deprecated'),
      tagType: 'danger',
      detail: plugin.deprecated_message || t('plugin.deprecatedDetail'),
      primaryAction: 'none',
      primaryActionLabel: t('plugin.deprecated')
    }
  }

  if (context.ossVersionIncompatible) {
    return {
      key: 'restricted',
      label: t('plugin.restricted'),
      tagType: 'danger',
      detail: t('plugin.restrictedDetail', { version: plugin.min_oss_version || 'required version' }),
      primaryAction: 'none',
      primaryActionLabel: t('plugin.upgradeFirst')
    }
  }

  if (context.installed && context.hasUpdate) {
    return {
      key: 'update_available',
      label: t('plugin.updateAvailable'),
      tagType: 'warning',
      detail: t('plugin.updateAvailableDetail'),
      primaryAction: 'update',
      primaryActionLabel: t('plugin.updateInstall')
    }
  }

  if (context.installed) {
    return {
      key: 'installed',
      label: t('plugin.installed'),
      tagType: 'success',
      detail: t('plugin.installedDetail'),
      primaryAction: 'none',
      primaryActionLabel: t('plugin.installed')
    }
  }

  if ((plugin.type || 'free') === 'paid' && context.purchased) {
    return {
      key: 'purchased_pending_install',
      label: t('plugin.purchasedPending'),
      tagType: 'primary',
      detail: t('plugin.purchasedPendingDetail'),
      primaryAction: 'install',
      primaryActionLabel: t('plugin.install')
    }
  }

  if ((plugin.type || 'free') === 'paid') {
    return {
      key: 'ready_to_buy',
      label: t('plugin.readyToBuy'),
      tagType: 'info',
      detail: t('plugin.readyToBuyDetail'),
      primaryAction: 'buy',
      primaryActionLabel: t('plugin.buy')
    }
  }

  return {
    key: 'ready_to_install',
    label: t('plugin.readyToInstall'),
    tagType: 'success',
    detail: t('plugin.readyToInstallDetail'),
    primaryAction: 'install',
    primaryActionLabel: t('plugin.install')
  }
} // FIXED: i18n

export const buildMarketplacePurchaseUrl = (baseUrl: string, pluginId?: string, sourceUrl?: string): string => {
  const base = (baseUrl || '').trim()
  if (!base) return ''

  try {
    const url = new URL(base)
    if (sourceUrl) url.searchParams.set('source_url', sourceUrl)
    if (!pluginId) return url.toString()

    const cleanedPath = url.pathname.replace(/\/+$/, '')
    if (cleanedPath.endsWith('/market')) {
      url.pathname = `${cleanedPath}/${pluginId}`
    } else {
      url.pathname = `${cleanedPath}/market/${pluginId}`.replace(/\/{2,}/g, '/')
    }
    return url.toString()
  } catch {
    const normalized = base.replace(/\/+$/, '')
    const encodedSource = sourceUrl ? `?source_url=${encodeURIComponent(sourceUrl)}` : ''
    if (!pluginId) return `${normalized}${encodedSource}`
    if (normalized.endsWith('/market')) return `${normalized}/${pluginId}${encodedSource}`
    return `${normalized}/market/${pluginId}${encodedSource}`
  }
}

// ── 商城插件价格/试用展示（双版账户打通 2026-10-10） ─────────────────────────

export type PluginPriceLike = {
  price_monthly?: number | null
  price_yearly?: number | null
  price_perpetual?: number | null
}

export type PluginPriceTier = {
  period: 'monthly' | 'yearly' | 'perpetual'
  cents: number
  label: string
}

// 价格字段单位为「分」，格式化为 ¥xx（最多保留两位小数）
const formatCentsToYuan = (cents: number): string =>
  `¥${(cents / 100).toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`

/**
 * 汇总插件的全部价格档位（分 → ¥ 文案），按金额升序（最低档在前）。
 * 无有效价格档位（全部缺失/为 0）时返回空数组。
 */
export const resolvePluginPriceTiers = (plugin: PluginPriceLike): PluginPriceTier[] => {
  const tiers: PluginPriceTier[] = []
  const pushTier = (period: PluginPriceTier['period'], cents: unknown, suffix: string) => {
    const value = Number(cents)
    if (!Number.isFinite(value) || value <= 0) return
    tiers.push({ period, cents: value, label: `${formatCentsToYuan(value)}${suffix}` })
  }
  pushTier('monthly', plugin.price_monthly, t('plugin.perMonth'))
  pushTier('yearly', plugin.price_yearly, t('plugin.perYear'))
  pushTier('perpetual', plugin.price_perpetual, t('plugin.perpetualSuffix'))
  return tiers.sort((a, b) => a.cents - b.cents)
}

/** trial_days > 0 视为提供试用 */
export const hasPluginTrial = (plugin: { trial_days?: number | null }): boolean =>
  Number(plugin?.trial_days || 0) > 0
