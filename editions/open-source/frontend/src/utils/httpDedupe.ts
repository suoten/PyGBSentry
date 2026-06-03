import api, { invalidateTokenCache } from '@/utils/http'
import type { AxiosRequestConfig } from 'axios'

const pendingRequests = new Map<string, AbortController>()

function getRequestKey(config: AxiosRequestConfig): string {
  return `${config.method || 'get'}:${config.url}:${JSON.stringify(config.params || '')}`
}

api.interceptors.request.use((config) => {
  const key = getRequestKey(config)
  // Only abort previous request on navigation (explicit cancelAll),
  // not on duplicate requests within the same page.
  // If a duplicate is already in-flight, let it coexist — the response
  // will be delivered to both callers, which is acceptable for GET requests.
  // For POST/PUT/DELETE, duplicates should never happen from UI.
  const controller = new AbortController()
  config.signal = controller.signal
  pendingRequests.set(key, controller)
  return config
})

api.interceptors.response.use(
  (response) => {
    const key = getRequestKey(response.config)
    pendingRequests.delete(key)
    return response
  },
  (error) => {
    if (error.config) {
      const key = getRequestKey(error.config)
      pendingRequests.delete(key)
    }
    return Promise.reject(error)
  }
)

export function cancelAllPendingRequests() {
  pendingRequests.forEach((controller) => controller.abort())
  pendingRequests.clear()
}

export function clearStalePendingRequests() {
  pendingRequests.clear()
}

export { api, invalidateTokenCache }
