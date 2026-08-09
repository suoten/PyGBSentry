<template>
  <el-card class="table-card" shadow="never">
    <template v-if="$slots.header" #header>
      <slot name="header" />
    </template>
    <slot />
  </el-card>
</template>

<script setup lang="ts">
</script>

<style scoped>
.table-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--el-border-radius-md);
  box-shadow: var(--el-box-shadow-sm);
  background: var(--el-bg-color);
  transition: transform var(--transition-time-02), box-shadow var(--transition-time-02), border-color var(--transition-time-02);
}

.table-card:hover {
  border-color: var(--el-border-color-hover);
  box-shadow: var(--el-box-shadow-base);
}

.table-card :deep(.el-card__body) {
  padding: var(--el-content-padding-sm) var(--el-content-padding-base);
}

.table-card :deep(.el-card__header) {
  padding: 10px var(--el-content-padding-base);
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-extra-light);
}
</style>
