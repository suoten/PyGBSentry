<template>
  <div class="flex items-center justify-between gap-3">
    <div class="toolbar-title min-w-0">
      <div class="font-semibold tracking-wide truncate" style="color: var(--el-text-color-primary)">{{ title }}</div>
      <div v-if="subtitle" class="text-xs truncate" style="color: var(--el-text-color-secondary)">{{ subtitle }}</div>
    </div>
    <div v-if="$slots.actions" class="shrink-0">
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  subtitle?: string
}>()
</script>

<style scoped>
.toolbar-title {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.toolbar-title::before {
  content: '';
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: linear-gradient(135deg, #1677ff 0%, #409eff 100%);
  box-shadow: 0 0 0 6px rgba(64, 158, 255, 0.12);
  flex: none;
}
</style>
