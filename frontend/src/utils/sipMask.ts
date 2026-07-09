// SECURITY: SIP IP masking for non-superadmin users
export function maskSipIp(ip: string | undefined | null): string {
  if (!ip) return ''
  const parts = ip.split('.')
  if (parts.length === 4) return `${parts[0]}.${parts[1]}.*.*`
  const idx = ip.lastIndexOf(':')
  if (idx >= 0) return ip.substring(0, idx + 1) + '****'
  return ip.substring(0, Math.max(0, ip.length - 4)) + '****'
}
