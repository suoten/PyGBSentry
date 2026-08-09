<template>
  <div class="page-container" :class="{ 'page-container--flex': isFlex }">
    <div v-if="$slots.header" class="page-container__header">
      <slot name="header" />
    </div>
    <div class="page-container__content">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, useAttrs } from 'vue'

defineProps<{
  padded?: boolean
}>()

const attrs = useAttrs()

const isFlex = computed(() => {
  const c: Record<string, unknown> = attrs.class
  if (!c) return false
  if (typeof c === 'string') return c.includes('flex')
  if (Array.isArray(c)) {
    return c.some((item) => {
      if (typeof item === 'string') return item.includes('flex')
      if (item && typeof item === 'object') return !!(item as Record<string, unknown>).flex
      return false
    })
  }
  if (c && typeof c === 'object') return !!(c as Record<string, unknown>).flex
  return false
})
</script>

<style scoped>
.page-container {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--el-border-radius-md);
  overflow: hidden;
  box-shadow: var(--el-box-shadow-xs);
}

.page-container--flex {
  display: flex;
  flex-direction: column;
}

.page-container--flex .page-container__content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: var(--el-content-padding-sm);
}

.page-container__header {
  background: var(--el-bg-color);
}

.page-container__content {
  padding: var(--el-content-padding-sm);
}
</style>
