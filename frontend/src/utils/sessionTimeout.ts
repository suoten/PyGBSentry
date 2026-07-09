/**
 * Session timeout manager — monitors user activity and JWT token expiration,
 * triggering callbacks when the session is about to expire or has expired.
 *
 * Features:
 * - 30-minute inactivity timeout (configurable)
 * - 5-minute warning before timeout
 * - JWT exp claim detection
 * - Activity events: mousemove, keydown, click, scroll, touchstart
 */
import { safeSSGet } from '@/utils/storage'

const DEFAULT_TIMEOUT_MS = 30 * 60 * 1000  // 30 minutes
const WARNING_BEFORE_MS = 5 * 60 * 1000    // 5 minutes before timeout
const TOKEN_CHECK_INTERVAL_MS = 60 * 1000  // Check token exp every 60s

interface SessionTimeoutCallbacks {
  onTimeout?: () => void
  onWarning?: () => void
  onTokenExpired?: () => void
}

let _timeoutMs = DEFAULT_TIMEOUT_MS
let _callbacks: SessionTimeoutCallbacks = {}
let _activityTimer: ReturnType<typeof setTimeout> | null = null
let _warningTimer: ReturnType<typeof setTimeout> | null = null
let _tokenCheckTimer: ReturnType<typeof setInterval> | null = null
let _warningFired = false

const _ACTIVITY_EVENTS = ['mousemove', 'keydown', 'click', 'scroll', 'touchstart']

function _clearTimers(): void {
  if (_activityTimer) { clearTimeout(_activityTimer); _activityTimer = null }
  if (_warningTimer) { clearTimeout(_warningTimer); _warningTimer = null }
  if (_tokenCheckTimer) { clearInterval(_tokenCheckTimer); _tokenCheckTimer = null }
}

function _onActivity(): void {
  _warningFired = false
  _resetTimers()
}

function _resetTimers(): void {
  if (_activityTimer) clearTimeout(_activityTimer)
  if (_warningTimer) clearTimeout(_warningTimer)

  _warningTimer = setTimeout(() => {
    if (!_warningFired) {
      _warningFired = true
      _callbacks.onWarning?.()
    }
  }, _timeoutMs - WARNING_BEFORE_MS)

  _activityTimer = setTimeout(() => {
    _callbacks.onTimeout?.()
    stopSessionTimeout()
  }, _timeoutMs)
}

function _checkTokenExp(): void {
  const token = safeSSGet('token')
  if (!token) return

  try {
    const parts = token.split('.')
    if (parts.length !== 3) return
    // JWT payload is base64url-encoded JSON
    const payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')))
    const exp = payload.exp
    if (!exp) return

    const nowSec = Math.floor(Date.now() / 1000)
    if (exp <= nowSec) {
      _callbacks.onTokenExpired?.()
      stopSessionTimeout()
    }
  } catch {
    // Invalid token format — ignore
  }
}

/**
 * Start session timeout monitoring.
 * @param callbacks - Callbacks for timeout, warning, and token expiration
 * @param timeoutMs - Session timeout in milliseconds (default: 30 minutes)
 */
export function startSessionTimeout(
  callbacks: SessionTimeoutCallbacks,
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
): void {
  stopSessionTimeout()
  _callbacks = callbacks
  _timeoutMs = timeoutMs
  _warningFired = false

  // Start activity monitoring
  _ACTIVITY_EVENTS.forEach((evt) => {
    window.addEventListener(evt, _onActivity, { passive: true })
  })

  // Start timers
  _resetTimers()

  // Start token expiration check
  _checkTokenExp()
  _tokenCheckTimer = setInterval(_checkTokenExp, TOKEN_CHECK_INTERVAL_MS)
}

/**
 * Stop session timeout monitoring and clean up all listeners and timers.
 */
export function stopSessionTimeout(): void {
  _ACTIVITY_EVENTS.forEach((evt) => {
    window.removeEventListener(evt, _onActivity)
  })
  _clearTimers()
  _callbacks = {}
  _warningFired = false
}
