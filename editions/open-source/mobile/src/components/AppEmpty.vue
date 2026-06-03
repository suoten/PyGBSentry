<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    text?: string;
  }>(),
  {
    text: "暂无数据"
  }
);
</script>

<template>
  <view class="app-card" style="text-align:center; padding: 40rpx 20rpx">
    <text class="app-subtext">{{ props.text }}</text>
  </view>
</template>
