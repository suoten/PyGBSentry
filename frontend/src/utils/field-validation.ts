import type { FieldSchema } from '../types/center-fields'
import { useI18n } from 'vue-i18n'  // FIXED: 引入i18n

const { t } = useI18n()

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
  if (field.required && isEmpty(value)) {
    return t('validation.required', { label: field.label })  // FIXED: 硬编码中文→i18n
  }
  if (isEmpty(value)) {
    return null
  }
  if (field.component === 'number' && typeof value === 'number') {
    if (typeof field.min === 'number' && value < field.min) {
      return t('validation.min', { label: field.label, min: field.min })  // FIXED: 硬编码中文→i18n
    }
    if (typeof field.max === 'number' && value > field.max) {
      return t('validation.max', { label: field.label, max: field.max })  // FIXED: 硬编码中文→i18n
    }
  }
  if (typeof value === 'string') {
    if (typeof field.minLength === 'number' && value.length < field.minLength) {
      return t('validation.minLength', { label: field.label, min: field.minLength })  // FIXED: 硬编码中文→i18n
    }
    if (typeof field.maxLength === 'number' && value.length > field.maxLength) {
      return t('validation.maxLength', { label: field.label, max: field.maxLength })  // FIXED: 硬编码中文→i18n
    }
  }
  if (field.component === 'daterange' && Array.isArray(value)) {
    if (value.length !== 2) {
      return t('validation.dateRangeRequired', { label: field.label })  // FIXED: 硬编码中文→i18n
    }
    const start = new Date(String(value[0]))
    const end = new Date(String(value[1]))
    if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
      return t('validation.invalidFormat', { label: field.label })  // FIXED: 硬编码中文→i18n
    }
    if (start.getTime() > end.getTime()) {
      return t('validation.dateRangeOrder', { label: field.label })  // FIXED: 硬编码中文→i18n
    }
  }
  if (field.pattern && typeof value === 'string') {
    const matched = new RegExp(field.pattern).test(value)
    if (!matched) {
      return field.patternMessage || t('validation.invalidFormat', { label: field.label })  // FIXED: 硬编码中文→i18n
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
