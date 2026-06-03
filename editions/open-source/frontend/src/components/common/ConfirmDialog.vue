<template>
  <el-dialog
    v-model="visible"
    :title="title"
    :width="width"
    :close-on-click-modal="false"
    class="confirm-dialog"
    append-to-body
    destroy-on-close
  >
    <div class="confirm-dialog__body">
      <div v-if="icon" class="confirm-dialog__icon" :class="`confirm-dialog__icon--${iconType}`">
        <el-icon><component :is="icon" /></el-icon>
      </div>
      <div class="confirm-dialog__message">
        <p v-if="title" class="confirm-dialog__title">{{ title }}</p>
        <p class="confirm-dialog__content">{{ content }}</p>
      </div>
    </div>

    <template #footer>
      <el-button @click="handleCancel" :disabled="loading">
        {{ cancelText }}
      </el-button>
      <el-button
        :type="confirmType"
        :loading="loading"
        @click="handleConfirm"
      >
        {{ confirmText }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  WarningFilled,
  CircleCheckFilled,
  CircleCloseFilled,
  QuestionFilled,
  DeleteFilled,
} from '@element-plus/icons-vue'

interface Props {
  modelValue: boolean
  /** 确认按钮文字 */
  confirmText?: string
  /** 取消按钮文字 */
  cancelText?: string
  /** 对话框宽度 */
  width?: string | number
  /** 确认类型 */
  confirmType?: 'primary' | 'danger' | 'warning' | 'default'
  /** 图标组件（可选） */
  icon?: string | { component: unknown }
  /** 内容文本 */
  content: string
  /** 标题文本（可选，默认显示 content） */
  title?: string
  /** 自动推断图标类型（用于自动选择图标） */
  intent?: 'warning' | 'danger' | 'success' | 'info' | 'delete'
}

const props = withDefaults(defineProps<Props>(), {
  confirmText: '确定',
  cancelText: '取消',
  width: '440px',
  confirmType: 'primary',
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'confirm': []
  'cancel': []
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

const loading = defineModel<boolean>('loading', { default: false })

/** 根据 intent 自动选择图标 */
const resolvedIcon = computed(() => {
  if (props.icon) return props.icon
  if (props.intent) {
    const iconMap: Record<string, unknown> = {
      warning: WarningFilled,
      danger: CircleCloseFilled,
      success: CircleCheckFilled,
      info: QuestionFilled,
      delete: DeleteFilled,
    }
    return iconMap[props.intent] || QuestionFilled
  }
  return null
})

/** 根据 intent 自动选择确认按钮类型 */
const resolvedConfirmType = computed(() => {
  if (props.confirmType !== 'primary') return props.confirmType
  if (props.intent) {
    const typeMap: Record<string, 'primary' | 'danger' | 'warning'> = {
      warning: 'warning',
      danger: 'danger',
      delete: 'danger',
      success: 'primary',
      info: 'primary',
    }
    return typeMap[props.intent] || 'primary'
  }
  return 'primary'
})

const iconType = computed(() => {
  if (props.intent) return props.intent
  if (props.confirmType === 'danger') return 'danger'
  if (props.confirmType === 'warning') return 'warning'
  return 'info'
})

const icon = computed(() => resolvedIcon.value)
const confirmType = computed(() => resolvedConfirmType.value)

const handleConfirm = async () => {
  emit('confirm')
}

const handleCancel = () => {
  visible.value = false
  emit('cancel')
}
</script>

<style scoped>
.confirm-dialog__body {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 4px 0;
}

.confirm-dialog__icon {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
}

.confirm-dialog__icon--warning {
  background: var(--el-color-warning-light-9);
  color: var(--el-color-warning);
}

.confirm-dialog__icon--danger {
  background: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
}

.confirm-dialog__icon--success {
  background: var(--el-color-success-light-9);
  color: var(--el-color-success);
}

.confirm-dialog__icon--info {
  background: var(--el-color-info-light-9);
  color: var(--el-color-info);
}

.confirm-dialog__icon--delete {
  background: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
}

.confirm-dialog__message {
  flex: 1;
  min-width: 0;
}

.confirm-dialog__title {
  margin: 0 0 8px;
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  line-height: 1.5;
}

.confirm-dialog__content {
  margin: 0;
  font-size: 14px;
  color: var(--el-text-color-regular);
  line-height: 1.6;
}
</style>
