/**
 * Safe storage wrappers — encapsulate sessionStorage/localStorage with
 * exception handling for quota-exceeded, privacy mode, and serialization errors.
 *
 * Security policy:
 * - safeSS* → sessionStorage (cleared on tab close; used for tokens and other sensitive data)
 * - safeLS* → localStorage  (persisted across sessions; used ONLY for non-sensitive UI preferences)
 */

function _safeGet(storage: Storage, key: string): string | null {
  try {
    return storage.getItem(key)
  } catch {
    return null
  }
}

function _safeSet(storage: Storage, key: string, value: string): void {
  try {
    storage.setItem(key, value)
  } catch {
    /* quota exceeded or privacy mode — silently ignore */
  }
}

function _safeRemove(storage: Storage, key: string): void {
  try {
    storage.removeItem(key)
  } catch {
    /* ignore */
  }
}

// ── sessionStorage wrappers (for sensitive data like tokens) ───────────────
export function safeSSGet(key: string): string | null {
  return _safeGet(sessionStorage, key)
}

export function safeSSSet(key: string, value: string): void {
  _safeSet(sessionStorage, key, value)
}

export function safeSSRemove(key: string): void {
  _safeRemove(sessionStorage, key)
}

// ── localStorage wrappers (for non-sensitive UI preferences only) ──────────
export function safeLSGet(key: string): string | null {
  return _safeGet(localStorage, key)
}

export function safeLSSet(key: string, value: string): void {
  _safeSet(localStorage, key, value)
}

export function safeLSRemove(key: string): void {
  _safeRemove(localStorage, key)
}
