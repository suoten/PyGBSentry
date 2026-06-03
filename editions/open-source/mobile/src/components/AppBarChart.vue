<script setup lang="ts">
import { computed } from "vue";

interface ChartItem {
  label: string;
  value: number;
  key?: string;
}

const props = withDefaults(
  defineProps<{
    items: ChartItem[];
    color?: string;
    minWidthRpx?: number;
    barWidthRpx?: number;
    maxHeightRpx?: number;
    emptyText?: string;
  }>(),
  {
    color: "#2563EB",
    minWidthRpx: 900,
    barWidthRpx: 56,
    maxHeightRpx: 120,
    emptyText: "暂无图表数据"
  }
);
const emit = defineEmits<{
  (e: "item-click", item: ChartItem): void;
}>();

const maxValue = computed(() => {
  if (!props.items.length) return 0;
  return Math.max(...props.items.map((item) => Number(item.value || 0)));
});

function barHeight(value: number) {
  const v = Number(value || 0);
  if (maxValue.value <= 0) return 4;
  return Math.max(Math.round((v / maxValue.value) * props.maxHeightRpx), 4);
}

function onItemClick(item: ChartItem) {
  emit("item-click", item);
}
</script>

<template>
  <view class="app-gap-12">
    <scroll-view v-if="items.length > 0" scroll-x>
      <view class="app-row" :style="{ minWidth: `${minWidthRpx}rpx`, gap: '10rpx' }">
        <view
          v-for="item in items"
          :key="item.label"
          class="app-gap-12"
          :style="{ width: `${barWidthRpx + 18}rpx`, alignItems: 'center' }"
          @click="onItemClick(item)"
        >
          <view
            :style="{
              width: `${barWidthRpx}rpx`,
              background: color,
              borderRadius: '8rpx 8rpx 0 0',
              height: `${barHeight(item.value)}rpx`
            }"
          />
          <text style="font-size:20rpx;color:#64748B">{{ item.label }}</text>
          <text style="font-size:22rpx;color:#0F172A">{{ item.value }}</text>
        </view>
      </view>
    </scroll-view>
    <text v-else class="app-subtext">{{ emptyText }}</text>
  </view>
</template>
