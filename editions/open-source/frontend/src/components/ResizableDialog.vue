<template>
  <el-dialog
    v-model="visibleState"
    :title="title"
    :width="width"
    :fullscreen="isMaximized"
    :close-on-click-modal="closeOnClickModal"
    :show-close="false"
    class="resizable-dialog"
    :class="{ 'resizable-dialog--maximized': isMaximized, 'resizable-dialog--minimized': isMinimized }"
    @close="handleClose"
  
    destroy-on-close
  >
    <template #header>
      <div class="resizable-dialog__header">
        <span class="resizable-dialog__title">{{ title }}</span>
        <div class="resizable-dialog__actions">
          <button v-if="showMinimize" class="resizable-dialog__action-btn" @click="toggleMinimize">
            <el-icon><Minus /></el-icon>
          </button>
          <button v-if="showMaximize" class="resizable-dialog__action-btn" @click="toggleMaximize">
            <el-icon><component :is="isMaximized ? CopyDocument : FullScreen" /></el-icon>
          </button>
          <button class="resizable-dialog__action-btn resizable-dialog__close-btn" @click="handleClose">
            <el-icon><Close /></el-icon>
          </button>
        </div>
      </div>
    </template>
    <div v-show="!isMinimized" class="resizable-dialog__body">
      <slot></slot>
    </div>
    <template #footer v-if="$slots.footer && !isMinimized">
      <slot name="footer"></slot>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Close, FullScreen, CopyDocument, Minus } from '@element-plus/icons-vue'

interface Props {
  modelValue: boolean
  title?: string
  width?: string | number
  showMaximize?: boolean
  showMinimize?: boolean
  closeOnClickModal?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  title: '',
  width: '50%',
  showMaximize: true,
  showMinimize: true,
  closeOnClickModal: false
})

const emit = defineEmits(['update:modelValue', 'close'])

const visibleState = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const isMaximized = ref(false)
const isMinimized = ref(false)
const previousWidth = ref(props.width)

const toggleMaximize = () => {
  isMaximized.value = !isMaximized.value
  if (isMaximized.value) {
    isMinimized.value = false
  }
}

const toggleMinimize = () => {
  isMinimized.value = !isMinimized.value
  if (isMinimized.value) {
    isMaximized.value = false
  }
}

const handleClose = () => {
  isMaximized.value = false
  isMinimized.value = false
  emit('close')
  emit('update:modelValue', false)
}

watch(() => props.modelValue, (val) => {
  if (val) {
    isMaximized.value = false
    isMinimized.value = false
  }
})
</script>

<style scoped>
.resizable-dialog {
  --dialog-header-height: 52px;
}

.resizable-dialog :deep(.el-dialog__header) {
  padding: 0;
  margin: 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.resizable-dialog__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: var(--dialog-header-height);
  padding: 0 20px;
}

.resizable-dialog__title {
  font-weight: 600;
  font-size: 18px;
  color: var(--el-text-color-primary);
  user-select: none;
}

.resizable-dialog__actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.resizable-dialog__action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: none;
  background: transparent;
  color: var(--el-text-color-regular);
  cursor: pointer;
  border-radius: 6px;
  transition: all 0.2s;
  font-size: 18px;
}

.resizable-dialog__action-btn:hover {
  background: var(--el-fill-color-light);
  color: var(--el-text-color-primary);
}

.resizable-dialog__close-btn:hover {
  background: var(--el-color-danger-light-3);
  color: var(--el-color-danger);
}

.resizable-dialog__body {
  padding: 20px;
  max-height: calc(80vh - var(--dialog-header-height) - 80px);
  overflow-y: auto;
  font-size: 15px;
}

.resizable-dialog--maximized .resizable-dialog__body {
  max-height: calc(100vh - var(--dialog-header-height) - 80px);
}

.resizable-dialog--minimized :deep(.el-dialog__body),
.resizable-dialog--minimized :deep(.el-dialog__footer) {
  display: none;
}

.resizable-dialog--minimized :deep(.el-dialog) {
  width: 400px !important;
}
</style>
