export type OptionItem = {
  label: string
  value: string
}

export type FieldComponent = 'input' | 'select' | 'switch' | 'number' | 'daterange'

export type FieldSchema<Key extends string> = {
  key: Key
  label: string
  component: FieldComponent
  placeholder?: string
  hint?: string
  min?: number
  max?: number
  minLength?: number
  maxLength?: number
  options?: OptionItem[]
  required?: boolean
  pattern?: string
  patternMessage?: string
}
