export function channelTypeTag(type: string | number | undefined): string {
  const t = String(type ?? '').toLowerCase()
  const map: Record<string, string> = { '0': 'info', '1': 'success', '2': 'warning', civil: 'success', police: 'danger', traffic: 'warning' }
  return map[t] || 'info'
}
