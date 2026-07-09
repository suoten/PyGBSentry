export function formatDateTime(value: string | number | Date | undefined | null): string {
  if (!value) return '-'
  try {
    const d = new Date(value)
    if (isNaN(d.getTime())) return '-'
    const pad = (n: number) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  } catch { return '-' }
}
