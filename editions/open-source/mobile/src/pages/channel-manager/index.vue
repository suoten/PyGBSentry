<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import { fetchChannelsFlat, type ChannelFlatItem } from "@/api/device";
import AppStatusTag from "@/components/AppStatusTag.vue";
import AppEmpty from "@/components/AppEmpty.vue";

const loading = ref(false);
const keyword = ref("");
const statusFilter = ref<"" | "online" | "offline">("");
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);
const rows = ref<ChannelFlatItem[]>([]);
const loadMessage = ref("未刷新");
const loadAt = ref("");

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

function statusLabel(status: number | undefined) {
  return Number(status || 0) === 1 ? "在线" : "离线";
}

function statusTagType(status: number | undefined): "success" | "info" {
  return Number(status || 0) === 1 ? "success" : "info";
}

const summaryText = computed(() => {
  const filter = statusFilter.value === "online" ? "仅在线" : statusFilter.value === "offline" ? "仅离线" : "全部";
  return `通道列表：总数=${total.value}；当前页=${rows.value.length}；状态筛选=${filter}；关键词=${keyword.value.trim() || "-"}`;
});

const onlineStatsText = computed(() => {
  let online = 0;
  for (const row of rows.value) {
    if (Number(row.status || 0) === 1) online += 1;
  }
  const offline = rows.value.length - online;
  const rate = rows.value.length <= 0 ? 0 : Math.round((online / rows.value.length) * 100);
  return `当前页在线率：在线=${online}；离线=${offline}；在线率=${rate}%`;
});

const nextStepAdvice = computed(() => {
  const offline = rows.value.filter((x) => Number(x.status || 0) !== 1).length;
  if (offline > 0) return "下一步建议：优先排查离线通道，随后对在线通道做抽样预览。";
  return "下一步建议：当前页通道状态稳定，可执行抽样预览核验。";
});

function copySummary() {
  const text = [summaryText.value, onlineStatsText.value, nextStepAdvice.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "通道摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

async function loadChannels() {
  loading.value = true;
  try {
    const status = statusFilter.value === "online" ? 1 : statusFilter.value === "offline" ? 0 : undefined;
    const res = await fetchChannelsFlat({
      keyword: keyword.value.trim(),
      status,
      skip: (page.value - 1) * pageSize.value,
      limit: pageSize.value,
      placement: "business"
    });
    rows.value = Array.isArray(res?.items) ? res.items : [];
    total.value = Number(res?.total || 0);
    setLoadStatus(`刷新成功：${rows.value.length} 条`);
  } catch (err: any) {
    const reason = err?.message ? String(err.message) : "请稍后重试";
    setLoadStatus(`刷新失败：${reason}`);
    uni.showToast({ title: "通道加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

async function onStatusFilterChange(index: number) {
  statusFilter.value = index === 1 ? "online" : index === 2 ? "offline" : "";
  page.value = 1;
  await loadChannels();
}

async function onPageSizeChange(index: number) {
  pageSize.value = index === 1 ? 50 : index === 2 ? 100 : 20;
  page.value = 1;
  await loadChannels();
}

async function onSearch() {
  page.value = 1;
  await loadChannels();
}

async function prevPage() {
  if (page.value <= 1) return;
  page.value -= 1;
  await loadChannels();
}

async function nextPage() {
  const maxPage = Math.max(1, Math.ceil(total.value / pageSize.value));
  if (page.value >= maxPage) return;
  page.value += 1;
  await loadChannels();
}

function openPreview(row: ChannelFlatItem) {
  const deviceId = String(row.device_id || "").trim();
  const channelId = String(row.gb_id || "").trim();
  if (!deviceId || !channelId) {
    uni.showToast({ title: "缺少设备或通道标识", icon: "none" });
    return;
  }
  uni.navigateTo({
    url: `/pages/preview/index?deviceId=${encodeURIComponent(deviceId)}&channelId=${encodeURIComponent(channelId)}`
  });
}

onShow(loadChannels);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">通道管理</view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <input v-model="keyword" placeholder="按通道ID/通道名称检索" style="flex:1" @confirm="onSearch" />
        <button size="mini" :loading="loading" @click="onSearch">查询</button>
      </view>
      <view class="app-row">
        <picker mode="selector" :range="['全部状态', '仅在线', '仅离线']" @change="(e:any)=>onStatusFilterChange(Number(e?.detail?.value||0))">
          <view class="app-subtext">状态筛选：{{ statusFilter === "online" ? "仅在线" : statusFilter === "offline" ? "仅离线" : "全部状态" }}</view>
        </picker>
        <picker mode="selector" :range="['20条/页', '50条/页', '100条/页']" :value="pageSize === 20 ? 0 : pageSize === 50 ? 1 : 2" @change="(e:any)=>onPageSizeChange(Number(e?.detail?.value||0))">
          <view class="app-subtext">每页：{{ pageSize }}</view>
        </picker>
      </view>
      <text class="app-subtext">{{ summaryText }}</text>
      <text class="app-subtext">{{ onlineStatsText }}</text>
      <text class="app-subtext">{{ nextStepAdvice }}</text>
      <text class="app-subtext">刷新状态：{{ loadMessage || "-" }}</text>
      <text v-if="loadAt" class="app-subtext">状态时间：{{ loadAt }}</text>
      <view class="app-row">
        <button size="mini" @click="copySummary">复制通道摘要</button>
        <button size="mini" :disabled="page <= 1" @click="prevPage">上一页</button>
        <button size="mini" :disabled="page >= Math.max(1, Math.ceil(total / pageSize))" @click="nextPage">下一页</button>
        <text class="app-subtext">第 {{ page }} / {{ Math.max(1, Math.ceil(total / pageSize)) }} 页</text>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <view v-if="rows.length" class="app-gap-12">
        <view v-for="row in rows" :key="row.id" class="app-row">
          <view style="flex:1">
            <text class="app-subtext">{{ row.name || row.gb_id || row.id }}</text>
            <text class="app-subtext">通道ID：{{ row.gb_id || "-" }}</text>
            <text class="app-subtext">设备：{{ row.device_name || row.device_id || "-" }}</text>
            <text class="app-subtext">默认码流：{{ row.default_stream_type || "-" }} / 音频：{{ row.has_audio ? "开" : "关" }}</text>
          </view>
          <view class="app-gap-12">
            <AppStatusTag :text="statusLabel(row.status)" :type="statusTagType(row.status)" />
            <button size="mini" :disabled="Number(row.status || 0) !== 1" @click="openPreview(row)">预览</button>
          </view>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '通道加载中...' : '当前筛选下暂无通道'" />
    </view>
  </view>
</template>
