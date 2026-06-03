<template>
  <div class="page-header">
    <div class="page-header__left">
      <h3 class="page-header__title">{{ title }}</h3>
      <p v-if="description" class="page-header__desc">{{ description }}</p>
    </div>
    <div v-if="$slots.actions" class="page-header__right">
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  description?: string
}>()
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: #ffffff;
}

.page-header__left {
  min-width: 0;
  flex: 1;
}

.page-header__title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  line-height: 1.3;
  letter-spacing: 0.2px;
}

.page-header__desc {
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}

.page-header__right {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}
</style>
