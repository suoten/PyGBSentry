import { describe, it, expect } from 'vitest'
import zhCN from '@/locales/zh-CN'
import enUS from '@/locales/en-US'

/**
 * Recursively flatten a nested object into dot-separated keys.
 * e.g. { auth: { login: "xxx" } } → Set(["auth.login"])
 */
function flattenKeys(obj: Record<string, unknown>, prefix = ''): Set<string> {
  const keys = new Set<string>()
  for (const [key, value] of Object.entries(obj)) {
    const fullKey = prefix ? `${prefix}.${key}` : key
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      for (const k of flattenKeys(value as Record<string, unknown>, fullKey)) {
        keys.add(k)
      }
    } else {
      keys.add(fullKey)
    }
  }
  return keys
}

describe('i18n locale completeness', () => {
  const zhKeys = flattenKeys(zhCN as unknown as Record<string, unknown>)
  const enKeys = flattenKeys(enUS as unknown as Record<string, unknown>)

  it('zh-CN and en-US should have the same top-level sections', () => {
    const zhTopLevel = new Set(Object.keys(zhCN))
    const enTopLevel = new Set(Object.keys(enUS))

    const missingInEn = [...zhTopLevel].filter(k => !enTopLevel.has(k))
    const missingInZh = [...enTopLevel].filter(k => !zhTopLevel.has(k))

    expect(missingInEn, `Sections in zh-CN but missing in en-US: ${missingInEn.join(', ')}`).toHaveLength(0)
    expect(missingInZh, `Sections in en-US but missing in zh-CN: ${missingInZh.join(', ')}`).toHaveLength(0)
  })

  it('all keys in zh-CN should exist in en-US', () => {
    const missingInEn = [...zhKeys].filter(k => !enKeys.has(k))
    expect(
      missingInEn,
      `Keys present in zh-CN but missing in en-US (${missingInEn.length}):\n${missingInEn.join('\n')}`,
    ).toHaveLength(0)
  })

  it('all keys in en-US should exist in zh-CN', () => {
    const missingInZh = [...enKeys].filter(k => !zhKeys.has(k))
    expect(
      missingInZh,
      `Keys present in en-US but missing in zh-CN (${missingInZh.length}):\n${missingInZh.join('\n')}`,
    ).toHaveLength(0)
  })

  it('both locales should have a non-empty set of keys', () => {
    expect(zhKeys.size).toBeGreaterThan(0)
    expect(enKeys.size).toBeGreaterThan(0)
  })

  it('both locales should have the same total number of keys', () => {
    expect(zhKeys.size).toBe(enKeys.size)
  })
})
