<template>
  <div class="flex items-center gap-2">
    <el-button
      :type="primaryType"
      :loading="primaryLoading"
      :disabled="primaryDisabled"
      @click="$emit('primary')"
    >
      {{ primaryText }}
    </el-button>
    <el-button
      :type="secondaryType"
      :loading="secondaryLoading"
      :disabled="secondaryDisabled"
      @click="$emit('secondary')"
    >
      {{ secondaryText }}
    </el-button>
    <slot />
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    primaryText: string
    secondaryText: string
    primaryType?: '' | 'primary' | 'success' | 'warning' | 'danger' | 'info'
    secondaryType?: '' | 'primary' | 'success' | 'warning' | 'danger' | 'info'
    primaryLoading?: boolean
    secondaryLoading?: boolean
    primaryDisabled?: boolean
    secondaryDisabled?: boolean
  }>(),
  {
    primaryType: 'primary',
    secondaryType: '',
    primaryLoading: false,
    secondaryLoading: false,
    primaryDisabled: false,
    secondaryDisabled: false
  }
)

defineEmits<{
  (e: 'primary'): void
  (e: 'secondary'): void
}>()
</script>
