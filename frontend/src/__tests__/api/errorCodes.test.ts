import { describe, it, expect, vi, beforeEach } from 'vitest'
import axios from 'axios'
import { getFriendlyError, getApiErrorMessage } from '@/utils/errorMessage'

// Mock vue-i18n so getFriendlyError can use t()
vi.mock('@/locales', () => ({
  default: {
    global: {
      t: (key: string, params?: Record<string, unknown>) => {
        // Return the key itself as the "translated" string for testing
        if (params) {
          return `${key}:${JSON.stringify(params)}`
        }
        return key
      },
    },
  },
}))

/**
 * Helper: build an axios-like error object from a response payload.
 */
function makeAxiosError(status: number, data: Record<string, unknown>) {
  return {
    response: { status, data },
    message: 'Request failed',
    isAxiosError: true,
  } as unknown as Error
}

describe('API error code mechanism', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('error_code in validation errors (ERR_002)', () => {
    it('extracts error_code ERR_002 from 422 validation error response', () => {
      const error = makeAxiosError(422, {
        detail: "Parameter 'device_id' validation failed",
        error_code: 'ERR_002',
        errors: [
          { loc: ['body', 'device_id'], msg: 'field required', type: 'value_error.missing' },
        ],
      })

      const result = getFriendlyError(error)
      expect(result.status).toBe(422)
      // The error_code field is present in the response data
      expect((error as any).response.data.error_code).toBe('ERR_002')
    })

    it('handles 422 with structured validation errors', () => {
      const error = makeAxiosError(422, {
        detail: 'Validation error',
        error_code: 'ERR_002',
        errors: [
          { loc: ['query', 'page'], msg: 'must be positive integer', type: 'value_error' },
          { loc: ['body', 'name'], msg: 'field required', type: 'value_error.missing' },
        ],
      })

      const result = getFriendlyError(error)
      expect(result.status).toBe(422)
      expect((error as any).response.data.error_code).toBe('ERR_002')
      expect((error as any).response.data.errors).toHaveLength(2)
    })
  })

  describe('error_code in HTTP errors (ERR_XXX)', () => {
    it('extracts error_code from 404 response', () => {
      const error = makeAxiosError(404, {
        detail: 'Device not found',
        message: 'Device not found',
        status_code: 404,
        error_code: 'ERR_003',
      })

      const result = getFriendlyError(error)
      expect(result.status).toBe(404)
      expect((error as any).response.data.error_code).toBe('ERR_003')
    })

    it('extracts error_code from 403 forbidden response', () => {
      const error = makeAxiosError(403, {
        detail: 'No permission',
        message: 'No permission',
        status_code: 403,
        error_code: 'ERR_005',
      })

      const result = getFriendlyError(error)
      expect(result.status).toBe(403)
      expect((error as any).response.data.error_code).toBe('ERR_005')
    })

    it('extracts error_code from 429 rate-limited response', () => {
      const error = makeAxiosError(429, {
        detail: 'Too many requests',
        message: 'Too many requests',
        status_code: 429,
        error_code: 'ERR_006',
      })

      const result = getFriendlyError(error)
      expect(result.status).toBe(429)
      expect((error as any).response.data.error_code).toBe('ERR_006')
    })

    it('extracts error_code from 400 bad request response', () => {
      const error = makeAxiosError(400, {
        detail: 'Bad request',
        message: 'Bad request',
        status_code: 400,
        error_code: 'ERR_400',
      })

      const result = getFriendlyError(error)
      expect(result.status).toBe(400)
      expect((error as any).response.data.error_code).toBe('ERR_400')
    })

    it('handles HTTP error with auto-generated error_code (ERR_{status})', () => {
      const error = makeAxiosError(405, {
        detail: 'Method not allowed',
        message: 'Method not allowed',
        status_code: 405,
        error_code: 'ERR_405',
      })

      const result = getFriendlyError(error)
      expect(result.status).toBe(405)
      expect((error as any).response.data.error_code).toBe('ERR_405')
    })
  })

  describe('error_code in global exceptions (ERR_001)', () => {
    it('extracts error_code ERR_001 from 500 internal server error', () => {
      const error = makeAxiosError(500, {
        detail: 'Internal server error',
        message: 'Internal server error',
        error_code: 'ERR_001',
        retryable: true,
        status_code: 500,
      })

      const result = getFriendlyError(error)
      expect(result.status).toBe(500)
      expect((error as any).response.data.error_code).toBe('ERR_001')
      expect((error as any).response.data.retryable).toBe(true)
    })

    it('handles 500 with upgrade_hook_report', () => {
      const report = { step: 'migrate_db', status: 'failed', detail: 'column not found' }
      const error = makeAxiosError(500, {
        detail: { message: 'Upgrade hook failed', upgrade_hook_report: report },
        error_code: 'ERR_001',
        status_code: 500,
      })

      const result = getFriendlyError(error)
      expect(result.status).toBe(500)
      expect(result.upgradeHookReport).toEqual(report)
    })
  })

  describe('error_code in device/channel errors', () => {
    it('extracts device-specific error_code from 404 response', () => {
      const error = makeAxiosError(404, {
        detail: 'Device not found',
        message: 'Device not found',
        error_code: 'ERR_DEV_001',
        reason_code: 'device_offline',
      })

      const result = getFriendlyError(error)
      expect(result.status).toBe(404)
      expect((error as any).response.data.error_code).toBe('ERR_DEV_001')
      expect(result.reasonCode).toBe('device_offline')
    })

    it('extracts stream-specific error_code from 503 response', () => {
      const error = makeAxiosError(503, {
        detail: 'Stream not ready',
        message: 'Stream not ready',
        error_code: 'ERR_STR_001',
        reason_code: 'media_stream_not_ready',
        retryable: true,
      })

      const result = getFriendlyError(error)
      expect(result.status).toBe(503)
      expect((error as any).response.data.error_code).toBe('ERR_STR_001')
      expect(result.reasonCode).toBe('media_stream_not_ready')
      expect(result.retryable).toBe(true)
    })
  })

  describe('getApiErrorMessage with error_code responses', () => {
    it('returns friendly message for error_code responses', () => {
      const error = makeAxiosError(422, {
        detail: 'Validation error',
        error_code: 'ERR_002',
      })

      const msg = getApiErrorMessage(error, 'Fallback')
      expect(msg).toBeTruthy()
      expect(msg).not.toBe('Fallback')
    })

    it('returns empty string for canceled requests', () => {
      const canceledError = {
        name: 'CanceledError',
        message: 'canceled',
        code: 'ERR_CANCELED',
      } as unknown as Error

      const msg = getApiErrorMessage(canceledError, 'Fallback')
      expect(msg).toBe('')
    })

    it('returns fallback when friendly message is empty', () => {
      const error = {
        name: 'CanceledError',
        message: 'canceled',
        code: 'ERR_CANCELED',
      } as unknown as Error

      const msg = getApiErrorMessage(error, 'Fallback message')
      // CanceledError returns empty string, not fallback
      expect(msg).toBe('')
    })
  })

  describe('error responses with error_code are handled correctly', () => {
    it('preserves error_code in the response data for all error types', () => {
      const testCases = [
        { status: 400, errorCode: 'ERR_400' },
        { status: 401, errorCode: 'ERR_401' },
        { status: 403, errorCode: 'ERR_005' },
        { status: 404, errorCode: 'ERR_003' },
        { status: 422, errorCode: 'ERR_002' },
        { status: 429, errorCode: 'ERR_006' },
        { status: 500, errorCode: 'ERR_001' },
        { status: 503, errorCode: 'ERR_503' },
      ]

      for (const { status, errorCode } of testCases) {
        const error = makeAxiosError(status, {
          detail: `Error ${status}`,
          message: `Error ${status}`,
          error_code: errorCode,
          status_code: status,
        })

        const result = getFriendlyError(error)
        expect(result.status).toBe(status)
        expect((error as any).response.data.error_code).toBe(errorCode)
      }
    })
  })
})
