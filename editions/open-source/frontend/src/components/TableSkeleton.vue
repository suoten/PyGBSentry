<template>
  <div class="table-skeleton p-4">
    <el-skeleton :rows="rows" animated />
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    rows?: number
  }>(),
  { rows: 6 }
)
</script>

<style scoped>
.table-skeleton {
  min-height: 200px;
}
</style>
