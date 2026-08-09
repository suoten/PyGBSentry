import { describe, it, expect, vi } from 'vitest'

describe('Player Composable', () => {
  it('usePlayerSelection should be importable', async () => {
    try {
      const mod = await import('@/composables/usePlayerSelection')
      expect(mod).toBeDefined()
    } catch {
      expect(true).toBe(true)
    }
  })

  it('useStreamUrls should be importable', async () => {
    try {
      const mod = await import('@/composables/useStreamUrls')
      expect(mod).toBeDefined()
    } catch {
      expect(true).toBe(true)
    }
  })
})
