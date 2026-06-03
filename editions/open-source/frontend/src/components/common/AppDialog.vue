<template>
  <el-dialog
    v-model="visible"
    :width="width"
    :title="title"
    :close-on-click-modal="closeOnClickModal"
    class="app-dialog"
    :class="[`app-dialog--${size}`]"
    append-to-body
    destroy-on-close
    @closed="emit('closed')"
  >
    <template #header>
      <div class="app-dialog__header">
        <el-icon v-if="icon" class="app-dialog__icon" :class="`app-dialog__icon--${iconColor}`">
          <component :is="icon" />
        </el-icon>
        <span class="app-dialog__title">{{ title }}</span>
      </div>
    </template>

    <div class="app-dialog__body">
      <slot />
    </div>

    <template #footer v-if="$slots.footer">
      <div class="app-dialog__footer">
        <slot name="footer" />
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  modelValue: boolean
  title: string
  width?: string | number
  size?: 'small' | 'medium' | 'large' | 'xlarge'
  icon?: string | { component: unknown }
  iconColor?: 'primary' | 'success' | 'warning' | 'danger'
  closeOnClickModal?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  width: '560px',
  size: 'medium',
  iconColor: 'primary',
  closeOnClickModal: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'closed': []
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})
</script>

<style scoped>
.app-dialog__header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.app-dialog__icon {
  font-size: 18px;
}

.app-dialog__icon--primary { color: var(--el-color-primary); }
.app-dialog__icon--success { color: var(--el-color-success); }
.app-dialog__icon--warning { color: var(--el-color-warning); }
.app-dialog__icon--danger  { color: var(--el-color-danger); }

.app-dialog__body {
  padding: var(--el-dialog-body-padding);
}

.app-dialog__footer {
  padding: var(--el-dialog-footer-padding);
  background: var(--el-fill-color-extra-light);
  border-top: 1px solid var(--el-border-color-lighter);
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.app-dialog--small { --el-dialog-width: 420px; }
.app-dialog--medium { --el-dialog-width: 560px; }
.app-dialog--large { --el-dialog-width: 800px; }
.app-dialog--xlarge { --el-dialog-width: 90%; max-width: 1200px; }
</style>
