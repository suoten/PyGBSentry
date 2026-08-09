<template>
  <div class="empty-state py-8 px-4 text-center">
    <el-empty :description="description" />
    <div v-if="$slots.action" class="mt-4 flex justify-center flex-wrap gap-2">
      <slot name="action"></slot>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  description: string
}>()
</script>
