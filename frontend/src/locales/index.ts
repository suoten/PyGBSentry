import { createI18n } from 'vue-i18n'
import zhCN from './zh-CN'
import enUS from './en-US'

export type MessageSchema = typeof zhCN

// SECURITY: 非敏感 UI 偏好（语言选择）— 仅存语言代码（zh-CN/en-US），不含任何敏感信息，
// 可安全存入 localStorage 跨会话保留。敏感信息（token、用户名等）使用 sessionStorage，详见 utils/storage.ts。
const savedLocale = localStorage.getItem('locale') || 'zh-CN'

const i18n = createI18n({
  legacy: false,
  locale: savedLocale,
  fallbackLocale: 'zh-CN',
  messages: {
    'zh-CN': zhCN,
    'en-US': enUS
  }
})

export default i18n
