/**
 * WebSocket ticket helper — obtains a short-lived one-time ws-ticket from the
 * backend and appends it as a query parameter to the WebSocket URL.
 *
 * This eliminates the need to pass JWT tokens via WebSocket URL query
 * parameters, preventing token leakage in logs and browser history.
 */
import api from '@/utils/http'

/**
 * Build a WebSocket URL with a ws-ticket parameter.
 *
 * @param path - The API WebSocket path (e.g. '/api/v1/alarms/ws')
 * @returns A ws:// or wss:// URL with `?ticket=xxx` appended
 */
export async function buildWsUrlWithTicket(path: string): Promise<string> {
  const res = await api.post('/api/v1/auth/ws-ticket')
  const ticket = res.data?.ticket
  if (!ticket || typeof ticket !== 'string') {
    throw new Error('Failed to obtain ws-ticket')
  }

  const baseURL = import.meta.env.VITE_API_BASE_URL || '/'
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host

  // If baseURL is an absolute URL, extract its host; otherwise use current host
  let wsBase: string
  if (baseURL.startsWith('http://') || baseURL.startsWith('https://')) {
    const url = new URL(baseURL)
    wsBase = `${protocol}//${url.host}`
  } else {
    wsBase = `${protocol}//${host}`
  }

  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${wsBase}${normalizedPath}?ticket=${encodeURIComponent(ticket)}`
}

export default buildWsUrlWithTicket
