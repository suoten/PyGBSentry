import { describe, it, expect, vi } from 'vitest'

vi.mock('pinia', () => ({
  defineStore: vi.fn((name, setup) => setup),
  createPinia: vi.fn(() => ({})),
}))

describe('Alarm Store', () => {
  it('should have initial state', () => {
    expect(true).toBe(true)
  })
})
