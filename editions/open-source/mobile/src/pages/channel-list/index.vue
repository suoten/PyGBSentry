<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import { batchPlaceChannels, fetchChannelsFlat, type ChannelFlatItem } from "@/api/device";
import AppStatusTag from "@/components/AppStatusTag.vue";
import AppEmpty from "@/components/AppEmpty.vue";

const loading = ref(false);
const actionLoading = ref(false);
const keyword = ref("");
const statusFilter = ref<"" | "online" | "offline">("");
const typeFilter = ref<"" | "1" | "2" | "3">("");
const civilCodePrefix = ref("");
const parentGbId = ref("");
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);
const onlineTotal = ref(0);
const rows = ref<ChannelFlatItem[]>([]);
const selectedIds = ref<string[]>([]);
const loadMessage = ref("未刷新");
const loadAt = ref("");
const regionTargetId = ref("");
const businessTargetId = ref("");
const regionCivilCode = ref("");

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

const maxPage = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)));

const summaryText = computed(() => {
  const statusText = statusFilter.value === "online" ? "仅在线" : statusFilter.value === "offline" ? "仅离线" : "全部";
  const typeText = typeFilter.value ? `类型${typeFilter.value}` : "全部类型";
  return `通道列表：总数=${total.value}；在线=${onlineTotal.value}；当前页=${rows.value.length}；已选=${selectedIds.value.length}；筛选=${statusText}/${typeText}`;
});

const nextStepAdvice = computed(() => {
  const offline = rows.value.filter((x) => Number(x.status || 0) !== 1).length;
  if (selectedIds.value.length > 0) return "下一步建议：可对已选通道执行批量挂载，减少目录整理成本。";
  if (offline > 0) return "下一步建议：优先排查离线通道并抽样验证预览链路。";
  return "下一步建议：状态稳定，建议按业务分组执行结构化整理。";
});

function statusText(status: number | undefined) {
  return Number(status || 0) === 1 ? "在线" : "离线";
}

function statusType(status: number | undefined): "success" | "info" {
  return Number(status || 0) === 1 ? "success" : "info";
}

function rowTypeText(row: ChannelFlatItem) {
  const raw = Number(row.resource_type ?? 0);
  if (raw === 1) return "国标设备";
  if (raw === 2) return "推流设备";
  if (raw === 3) return "拉流代理";
  return "-";
}

async function loadChannels() {
  loading.value = true;
  try {
    const status = statusFilter.value === "online" ? 1 : statusFilter.value === "offline" ? 0 : undefined;
    const resourceType = typeFilter.value ? Number(typeFilter.value) : undefined;
    const res = await fetchChannelsFlat({
      keyword: keyword.value.trim(),
      status,
      resource_type: resourceType,
      civil_code_prefix: civilCodePrefix.value.trim() || undefined,
      parent_gb_id: parentGbId.value.trim() || undefined,
      skip: (page.value - 1) * pageSize.value,
      limit: pageSize.value,
      placement: "business"
    });
    rows.value = Array.isArray(res?.items) ? res.items : [];
    total.value = Number((res as any)?.total || 0);
    onlineTotal.value = Number((res as any)?.online_total || 0);
    selectedIds.value = selectedIds.value.filter((id) => rows.value.some((x) => x.id === id));
    setLoadStatus(`刷新成功：${rows.value.length} 条`);
  } catch (err: any) {
    rows.value = [];
    total.value = 0;
    onlineTotal.value = 0;
    selectedIds.value = [];
    setLoadStatus(err?.message ? `刷新失败：${err.message}` : "刷新失败");
    uni.showToast({ title: "通道列表加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

function toggleSelect(rowId: string) {
  if (!rowId) return;
  if (selectedIds.value.includes(rowId)) {
    selectedIds.value = selectedIds.value.filter((x) => x !== rowId);
  } else {
    selectedIds.value = [...selectedIds.value, rowId];
  }
}

function selectAllCurrent() {
  const ids = rows.value.map((x) => x.id).filter(Boolean);
  selectedIds.value = Array.from(new Set([...selectedIds.value, ...ids]));
}

function clearSelection() {
  selectedIds.value = [];
}

async function batchMoveToBusiness() {
  if (!selectedIds.value.length) {
    uni.showToast({ title: "请先选择通道", icon: "none" });
    return;
  }
  if (!businessTargetId.value.trim()) {
    uni.showToast({ title: "请输入业务目录ID", icon: "none" });
    return;
  }
  actionLoading.value = true;
  try {
    const res = await batchPlaceChannels({
      resource_ids: selectedIds.value,
      placement: "business",
      target_id: businessTargetId.value.trim()
    });
    uni.showToast({ title: `业务挂载成功(${res.updated || 0})`, icon: "none" });
    clearSelection();
    await loadChannels();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `挂载失败：${err.message}` : "挂载失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function batchMoveToRegion() {
  if (!selectedIds.value.length) {
    uni.showToast({ title: "请先选择通道", icon: "none" });
    return;
  }
  actionLoading.value = true;
  try {
    const res = await batchPlaceChannels({
      resource_ids: selectedIds.value,
      placement: "region",
      target_id: regionTargetId.value.trim() || undefined,
      civil_code: regionCivilCode.value.trim() || undefined
    });
    uni.showToast({ title: `行政区划挂载成功(${res.updated || 0})`, icon: "none" });
    clearSelection();
    await loadChannels();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `挂载失败：${err.message}` : "挂载失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

function copySummary() {
  const text = [
    summaryText.value,
    `关键词=${keyword.value.trim() || "-"}；区划前缀=${civilCodePrefix.value.trim() || "-"}；业务父节点=${parentGbId.value.trim() || "-"}`,
    nextStepAdvice.value,
    `刷新状态=${loadMessage.value || "-"}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "通道摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

async function search() {
  page.value = 1;
  await loadChannels();
}

async function prevPage() {
  if (page.value <= 1) return;
  page.value -= 1;
  await loadChannels();
}

async function nextPage() {
  if (page.value >= maxPage.value) return;
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

function openDeviceRecord(row: ChannelFlatItem) {
  const deviceId = String(row.device_id || "").trim();
  const channelId = String(row.gb_id || "").trim();
  uni.navigateTo({
    url: `/pages/device-records/index?device_id=${encodeURIComponent(deviceId)}&channel_id=${encodeURIComponent(channelId)}`
  });
}

function openCloudRecord(row: ChannelFlatItem) {
  const deviceId = String(row.device_id || "").trim();
  const channelId = String(row.gb_id || "").trim();
  uni.navigateTo({
    url: `/pages/cloud-records/index?device_id=${encodeURIComponent(deviceId)}&channel_id=${encodeURIComponent(channelId)}`
  });
}

onShow(loadChannels);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">通道列表</view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <input v-model="keyword" class="app-input" placeholder="名称/编号关键字" @confirm="search" />
        <button size="mini" :loading="loading" @click="search">查询</button>
      </view>
      <view class="app-row">
        <picker
          mode="selector"
          :range="['全部状态', '在线', '离线']"
          :value="statusFilter === '' ? 0 : statusFilter === 'online' ? 1 : 2"
          @change="
            (e:any) => {
              const i = Number(e?.detail?.value || 0);
              statusFilter = i === 1 ? 'online' : i === 2 ? 'offline' : '';
              search();
            }
          "
        >
          <view class="app-subtext">状态：{{ statusFilter === "online" ? "在线" : statusFilter === "offline" ? "离线" : "全部" }}</view>
        </picker>
        <picker
          mode="selector"
          :range="['全部类型', '国标设备', '推流设备', '拉流代理']"
          :value="typeFilter === '' ? 0 : Number(typeFilter)"
          @change="
            (e:any) => {
              const i = Number(e?.detail?.value || 0);
              typeFilter = i > 0 ? String(i) as any : '';
              search();
            }
          "
        >
          <view class="app-subtext">类型：{{ typeFilter ? rowTypeText({ resource_type: Number(typeFilter), id:'', gb_id:'' }) : '全部' }}</view>
        </picker>
      </view>
      <input v-model="civilCodePrefix" class="app-input" placeholder="行政区划前缀（可空）" @confirm="search" />
      <input v-model="parentGbId" class="app-input" placeholder="业务父目录ID（可空）" @confirm="search" />
      <text class="app-subtext">{{ summaryText }}</text>
      <text class="app-subtext">{{ nextStepAdvice }}</text>
      <text class="app-subtext">刷新状态：{{ loadMessage || "-" }}</text>
      <text class="app-subtext">状态时间：{{ loadAt || "-" }}</text>
      <view class="app-row">
        <button size="mini" @click="copySummary">复制摘要</button>
        <button size="mini" @click="selectAllCurrent">全选当前页</button>
        <button size="mini" @click="clearSelection">清空选择</button>
      </view>
      <view class="app-row">
        <button size="mini" :disabled="page <= 1" @click="prevPage">上一页</button>
        <button size="mini" :disabled="page >= maxPage" @click="nextPage">下一页</button>
        <text class="app-subtext">第 {{ page }} / {{ maxPage }} 页</text>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">批量挂载（已选 {{ selectedIds.length }}）</text>
      <input v-model="businessTargetId" class="app-input" placeholder="业务目录目标ID（parent_gb_id）" />
      <button size="mini" :loading="actionLoading" :disabled="!selectedIds.length" @click="batchMoveToBusiness">批量挂载到业务目录</button>
      <input v-model="regionTargetId" class="app-input" placeholder="行政区目录目标ID（可空）" />
      <input v-model="regionCivilCode" class="app-input" placeholder="行政区划码（可空）" />
      <button size="mini" :loading="actionLoading" :disabled="!selectedIds.length" @click="batchMoveToRegion">批量挂载到行政区</button>
    </view>

    <view class="app-card app-gap-12">
      <view v-if="rows.length" class="app-gap-12">
        <view v-for="row in rows" :key="row.id" class="app-card">
          <view class="app-row">
            <label class="app-subtext">
              <checkbox :checked="selectedIds.includes(row.id)" @click="toggleSelect(row.id)" />
              已选
            </label>
            <AppStatusTag :text="statusText(row.status)" :type="statusType(row.status)" />
          </view>
          <text class="app-subtext">{{ row.name || row.gb_id || row.id }}</text>
          <text class="app-subtext">通道ID：{{ row.gb_id || "-" }}</text>
          <text class="app-subtext">设备：{{ row.device_name || row.device_id || "-" }}</text>
          <text class="app-subtext">类型：{{ rowTypeText(row) }}；默认码流：{{ row.default_stream_type || "-" }}</text>
          <text class="app-subtext">行政区：{{ row.civil_code || "-" }}；业务父节点：{{ row.parent_gb_id || "-" }}</text>
          <text class="app-subtext">坐标：{{ row.longitude ?? "-" }}, {{ row.latitude ?? "-" }}</text>
          <view class="app-row">
            <button size="mini" :disabled="Number(row.status || 0) !== 1" @click="openPreview(row)">播放</button>
            <button size="mini" @click="openDeviceRecord(row)">设备录像</button>
            <button size="mini" @click="openCloudRecord(row)">云端录像</button>
          </view>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '通道加载中...' : '当前筛选下暂无通道'" />
    </view>
  </view>
</template>
