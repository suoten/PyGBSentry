<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    text: string;
    type?: "success" | "warning" | "danger" | "info";
  }>(),
  {
    type: "info"
  }
);

const styleText = computed(() => {
  if (props.type === "success") return "background:#ecfdf5;color:#047857;";
  if (props.type === "warning") return "background:#fffbeb;color:#b45309;";
  if (props.type === "danger") return "background:#fef2f2;color:#b91c1c;";
  return "background:#eff6ff;color:#1d4ed8;";
});
</script>

<template>
  <text :style="`padding:6rpx 12rpx;border-radius:999rpx;font-size:22rpx;${styleText}`">{{ props.text }}</text>
</template>
