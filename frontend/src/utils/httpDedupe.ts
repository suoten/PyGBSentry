const _pending = new Map<string, unknown>()
export function clearStalePendingRequests(): void { _pending.clear() }
