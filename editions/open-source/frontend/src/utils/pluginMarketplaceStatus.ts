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
