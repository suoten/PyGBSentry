const BEIJING_TIMEZONE = 'Asia/Shanghai'

type LocaleMethod = (locales?: string | string[], options?: Intl.DateTimeFormatOptions) => string

const patchLocaleMethod = (method: 'toLocaleString' | 'toLocaleDateString' | 'toLocaleTimeString') => {
  const original = Date.prototype[method] as LocaleMethod
  Date.prototype[method] = function (this: Date, locales?: string | string[], options?: Intl.DateTimeFormatOptions) {
    const nextOptions: Intl.DateTimeFormatOptions = { ...(options || {}) }
    if (!nextOptions.timeZone) {
      nextOptions.timeZone = BEIJING_TIMEZONE
    }
    return original.call(this, locales, nextOptions)
  } as LocaleMethod
}

export const applyBeijingTimezone = () => {
  const key = '__pygbsentry_beijing_tz_patched__'
  const g = window as unknown as Record<string, unknown>
  if (g[key]) return
  patchLocaleMethod('toLocaleString')
  patchLocaleMethod('toLocaleDateString')
  patchLocaleMethod('toLocaleTimeString')
  g[key] = true
}

export const BEIJING_TIMEZONE_NAME = BEIJING_TIMEZONE
