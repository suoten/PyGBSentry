<template>
  <el-option
    v-bind="$attrs"
    :label="label"
    :value="value"
    :title="resolvedTitle"
  >
    <slot />
  </el-option>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  label: string
  value: string | number | boolean
  title?: string
}>()

const resolvedTitle = computed(() => String(props.title || props.label || ''))
</script>
