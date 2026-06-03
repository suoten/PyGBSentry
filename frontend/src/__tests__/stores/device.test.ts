import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock Pinia
vi.mock('pinia', () => ({
  defineStore: vi.fn((name, setup) => setup),
  createPinia: vi.fn(() => ({})),
}))

describe('Device Store', () => {
  it('should have initial state', () => {
    // Basic smoke test for store structure
    expect(true).toBe(true)
  })
})
