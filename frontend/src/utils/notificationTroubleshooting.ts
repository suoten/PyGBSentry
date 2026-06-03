import i18n from '@/locales'

export interface NotificationTroubleshooting {
  title: string
  summary: string
  steps: string[]
  basedOn?: string
  pluginId?: string
  fieldKeys?: string[]
  showConfigCenter: boolean
}

const t = i18n.global.t

export const getNotificationChannelLabel = (value?: string) => {
  if (value === 'sms') return t('notification.sms')
  if (value === 'wecom') return t('notification.wecom')
  if (value === 'feishu') return t('notification.feishu')
  return value || '-'
} // FIXED: i18n

export const getNotificationPluginIdByChannel = (value?: string) => {
  if (value === 'sms') return 'sms_alert'
  if (value === 'wecom') return 'wecom_alert'
  if (value === 'feishu') return 'feishu_alert'
  return ''
}

export const getNotificationChannelByPluginId = (pluginId?: string) => {
  if (pluginId === 'sms_alert') return 'sms'
  if (pluginId === 'wecom_alert') return 'wecom'
  if (pluginId === 'feishu_alert') return 'feishu'
  return ''
}

export const getNotificationFieldLabel = (channel: string | undefined, fieldKey: string | undefined) => {
  const normalizedChannel = String(channel || '').trim()
  const normalizedFieldKey = String(fieldKey || '').trim()
  const byChannel: Record<string, Record<string, string>> = {
    sms: {
      api_url: t('notification.smsGatewayUrl'),
      api_key: t('notification.smsApiKey'),
      phone_numbers: t('notification.smsPhoneNumbers'),
      message_template: t('notification.smsTemplate')
    },
    wecom: {
      webhook_url: t('notification.wecomWebhook'),
      secret: t('notification.wecomSecret'),
      msg_type: t('notification.wecomMsgType')
    },
    feishu: {
      webhook_url: t('notification.feishuWebhook'),
      secret: t('notification.feishuSecret')
    }
  }
  return byChannel[normalizedChannel]?.[normalizedFieldKey] || normalizedFieldKey || t('notification.relatedConfig')
} // FIXED: i18n

const normalizeErrorText = (value?: string) => String(value || '').trim().toLowerCase()

const includesAny = (source: string, keywords: string[]) => {
  return keywords.some((keyword) => source.includes(keyword))
}

export const getNotificationTroubleshooting = (input: {
  channel?: string
  errorMessage?: string
}): NotificationTroubleshooting => {
  const channel = String(input.channel || '').trim()
  const rawError = String(input.errorMessage || '').trim()
  const errorText = normalizeErrorText(rawError)
  const channelLabel = getNotificationChannelLabel(channel)
  const pluginId = getNotificationPluginIdByChannel(channel)
  const base: NotificationTroubleshooting = {
    title: t('notification.baseTitle', { channel: channelLabel }),
    summary: t('notification.baseSummary'),
    steps: [
      t('notification.baseStep1'),
      t('notification.baseStep2'),
      t('notification.baseStep3')
    ],
    pluginId,
    fieldKeys: [],
    showConfigCenter: true
  }

  if (channel === 'sms') {
    if (includesAny(errorText, ['phone_numbers_empty', 'phone number', 'phone_numbers', 'mobile', 'receiver', 'target'])) {
      return {
        ...base,
        title: t('notification.smsPhoneTitle'),
        summary: t('notification.smsPhoneSummary'),
        steps: [
          t('notification.smsPhoneStep1'),
          t('notification.smsPhoneStep2'),
          t('notification.smsPhoneStep3')
        ],
        fieldKeys: ['phone_numbers'],
        basedOn: rawError || 'phone_numbers_empty'
      }
    }
    if (includesAny(errorText, ['template_format', 'template', 'sign', 'signature', 'tpl'])) {
      return {
        ...base,
        title: t('notification.smsTemplateTitle'),
        summary: t('notification.smsTemplateSummary'),
        steps: [
          t('notification.smsTemplateStep1'),
          t('notification.smsTemplateStep2'),
          t('notification.smsTemplateStep3')
        ],
        fieldKeys: ['message_template'],
        basedOn: rawError || 'template/signature related'
      }
    }
    if (includesAny(errorText, ['api_url_empty'])) {
      return {
        ...base,
        title: t('notification.smsUrlEmptyTitle'),
        summary: t('notification.smsUrlEmptySummary'),
        steps: [
          t('notification.smsUrlEmptyStep1'),
          t('notification.smsUrlEmptyStep2'),
          t('notification.smsUrlEmptyStep3')
        ],
        fieldKeys: ['api_url'],
        basedOn: rawError || 'api_url_empty'
      }
    }
    if (includesAny(errorText, ['api url', '404', 'connection', 'timeout', 'name or service not known', 'max retries exceeded'])) {
      return {
        ...base,
        title: t('notification.smsUnreachableTitle'),
        summary: t('notification.smsUnreachableSummary'),
        steps: [
          t('notification.smsUnreachableStep1'),
          t('notification.smsUnreachableStep2'),
          t('notification.smsUnreachableStep3')
        ],
        fieldKeys: ['api_url'],
        basedOn: rawError
      }
    }
  }

  if (channel === 'wecom') {
    if (includesAny(errorText, ['webhook_not_configured', 'webhook', 'key', 'robot'])) {
      return {
        ...base,
        title: t('notification.wecomWebhookTitle'),
        summary: t('notification.wecomWebhookSummary'),
        steps: [
          t('notification.wecomWebhookStep1'),
          t('notification.wecomWebhookStep2'),
          t('notification.wecomWebhookStep3')
        ],
        fieldKeys: ['webhook_url'],
        basedOn: rawError || 'webhook_not_configured'
      }
    }
    if (includesAny(errorText, ['secret', 'sign'])) {
      return {
        ...base,
        title: t('notification.wecomSignTitle'),
        summary: t('notification.wecomSignSummary'),
        steps: [
          t('notification.wecomSignStep1'),
          t('notification.wecomSignStep2'),
          t('notification.wecomSignStep3')
        ],
        fieldKeys: ['webhook_url', 'secret'],
        basedOn: rawError
      }
    }
  }

  if (channel === 'feishu') {
    if (includesAny(errorText, ['webhook_not_configured', 'webhook', 'token', 'tenant_access_token'])) {
      return {
        ...base,
        title: t('notification.feishuWebhookTitle'),
        summary: t('notification.feishuWebhookSummary'),
        steps: [
          t('notification.feishuWebhookStep1'),
          t('notification.feishuWebhookStep2'),
          t('notification.feishuWebhookStep3')
        ],
        fieldKeys: ['webhook_url'],
        basedOn: rawError || 'webhook_not_configured'
      }
    }
    if (includesAny(errorText, ['secret', 'sign', 'key mismatch', 'invalid secret'])) {
      return {
        ...base,
        title: t('notification.feishuSecretTitle'),
        summary: t('notification.feishuSecretSummary'),
        steps: [
          t('notification.feishuSecretStep1'),
          t('notification.feishuSecretStep2'),
          t('notification.feishuSecretStep3')
        ],
        fieldKeys: ['secret', 'webhook_url'],
        basedOn: rawError
      }
    }
  }

  if (includesAny(errorText, ['401', '403', 'unauthorized', 'forbidden'])) {
    const authFieldKeysByChannel: Record<string, string[]> = {
      sms: ['api_key', 'api_url'],
      wecom: ['webhook_url', 'secret'],
      feishu: ['webhook_url', 'secret']
    }
    return {
      ...base,
      title: t('notification.authFailTitle', { channel: channelLabel }),
      summary: t('notification.authFailSummary', { channel: channelLabel }),
      steps: [
        t('notification.authFailStep1'),
        t('notification.authFailStep2'),
        t('notification.authFailStep3')
      ],
      fieldKeys: authFieldKeysByChannel[channel] || [],
      basedOn: rawError
    }
  }

  return base
}

export const getNotificationTroubleshootingByPluginId = (pluginId?: string, errorMessage?: string) => {
  return getNotificationTroubleshooting({
    channel: getNotificationChannelByPluginId(pluginId),
    errorMessage
  })
}
