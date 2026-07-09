import i18n from '@/locales'
import type { FieldSchema } from '../types/center-fields'

const isEmpty = (value: unknown) => {
  if (value === null || value === undefined) return true
  if (typeof value === 'string') return value.trim() === ''
  if (Array.isArray(value)) return value.length === 0
  return false
}

export const validateFieldValue = <K extends string>(
  field: FieldSchema<K>,
  value: unknown
): string | null => {
  const t = i18n.global.t
  const label = t(field.label)
  if (field.required && isEmpty(value)) {
    return t('validation.required', { label })
  }
  if (isEmpty(value)) {
    return null
  }
  if (field.component === 'number' && typeof value === 'number') {
    if (typeof field.min === 'number' && value < field.min) {
      return t('validation.min', { label, min: field.min })
    }
    if (typeof field.max === 'number' && value > field.max) {
      return t('validation.max', { label, max: field.max })
    }
  }
  if (typeof value === 'string') {
    if (typeof field.minLength === 'number' && value.length < field.minLength) {
      return t('validation.minLength', { label, min: field.minLength })
    }
    if (typeof field.maxLength === 'number' && value.length > field.maxLength) {
      return t('validation.maxLength', { label, max: field.maxLength })
    }
  }
  if (field.component === 'daterange' && Array.isArray(value)) {
    if (value.length !== 2) {
      return t('validation.dateRangeRequired', { label })
    }
    const start = new Date(String(value[0]))
    const end = new Date(String(value[1]))
    if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
      return t('validation.invalidFormat', { label })
    }
    if (start.getTime() > end.getTime()) {
      return t('validation.dateRangeOrder', { label })
    }
  }
  if (field.pattern && typeof value === 'string') {
    const matched = new RegExp(field.pattern).test(value)
    if (!matched) {
      return field.patternMessage ? t(field.patternMessage) : t('validation.invalidFormat', { label })
    }
  }
  return null
}

export const validateFields = <K extends string>(
  fields: FieldSchema<K>[],
  values: Record<string, unknown>
): string | null => {
  for (const field of fields) {
    const message = validateFieldValue(field, values[field.key])
    if (message) return message
  }
  return null
}
