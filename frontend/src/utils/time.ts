export const formatDateTime = (input: string | Date | null | undefined, emptyText = '-') => {
  if (!input) return emptyText
  const date = input instanceof Date ? input : new Date(input)
  return Number.isNaN(date.getTime()) ? String(input) : date.toLocaleString()
}
