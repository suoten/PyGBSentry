<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import { fetchDevices, type DeviceItem } from "@/api/device";

const keyword = ref("");
const loading = ref(false);
const devices = ref<DeviceItem[]>([]);
const deviceLoadMessage = ref("未刷新");
const deviceLastLoadedAt = ref("");
const devicePreviewActionMessage = ref("未发起预览");
const devicePreviewActionAt = ref("");

function setDevicePreviewActionStatus(message: string) {
  devicePreviewActionMessage.value = message;
  devicePreviewActionAt.value = new Date().toISOString();
}

const onlineDeviceCount = computed(() => devices.value.filter((x) => Number(x.status) === 1).length);
const offlineDeviceCount = computed(() => devices.value.filter((x) => Number(x.status) !== 1).length);
const deviceSearchSummaryText = computed(() => {
  const kw = keyword.value.trim();
  return `设备检索：关键词=${kw || "全部"}；命中=${devices.value.length}；在线=${onlineDeviceCount.value}；离线=${offlineDeviceCount.value}`;
});
const deviceSearchNextStepAdvice = computed(() => {
  if (devices.value.length <= 0) {
    return "下一步建议：放宽关键词或检查设备同步任务是否正常。";
  }
  if (onlineDeviceCount.value <= 0) {
    return "下一步建议：优先排查网络连通性与设备注册状态。";
  }
  if (offlineDeviceCount.value > onlineDeviceCount.value) {
    return "下一步建议：离线占比偏高，建议先筛查离线设备并逐台预览验证。";
  }
  return "下一步建议：优先对在线设备执行实时预览抽检。";
});
const previewReadyDeviceCount = computed(() => devices.value.filter((x) => !!String(x.gb_id || "").trim()).length);
const onlinePreviewReadyDeviceCount = computed(
  () => devices.value.filter((x) => Number(x.status) === 1 && !!String(x.gb_id || "").trim()).length
);
const offlineTop3Names = computed(() =>
  devices.value
    .filter((x) => Number(x.status) !== 1)
    .slice(0, 3)
    .map((x) => x.name || x.gb_id || x.id)
    .join(" / ")
);
const devicePatrolSummaryText = computed(() => {
  const total = devices.value.length;
  const online = onlineDeviceCount.value;
  const onlinePreviewReadyRate =
    online <= 0 ? 0 : Number(((onlinePreviewReadyDeviceCount.value / online) * 100).toFixed(2));
  return [
    "设备巡检摘要",
    `总数=${total}`,
    `在线=${online}`,
    `可预览=${previewReadyDeviceCount.value}`,
    `在线可预览覆盖率=${onlinePreviewReadyRate}%`,
    `离线Top3=${offlineTop3Names.value || "-"}`
  ].join("；");
});
const devicePatrolNextStepAdvice = computed(() => {
  if (devices.value.length <= 0) return "下一步建议：先执行设备同步，再进行巡检抽样。";
  if (onlineDeviceCount.value <= 0) return "下一步建议：当前无在线设备，优先恢复设备在线状态。";
  if (onlinePreviewReadyDeviceCount.value < onlineDeviceCount.value) {
    return "下一步建议：补齐在线设备的通道标识，提升可预览覆盖率。";
  }
  if (offlineDeviceCount.value > 0) return "下一步建议：针对离线设备逐台排障，并回归验证在线状态。";
  return "下一步建议：保持当前巡检节奏，持续进行在线预览抽检。";
});
const offlineRecoverySummaryText = computed(() => {
  const offlineDevices = devices.value.filter((x) => Number(x.status) !== 1);
  const previewReadyOffline = offlineDevices.filter((x) => !!String(x.gb_id || "").trim()).length;
  const recoveryReadyRate =
    offlineDevices.length <= 0 ? 0 : Number(((previewReadyOffline / offlineDevices.length) * 100).toFixed(2));
  const top3 = offlineDevices
    .slice(0, 3)
    .map((x) => x.name || x.gb_id || x.id)
    .join(" / ");
  return [
    "离线恢复跟进摘要",
    `离线总量=${offlineDevices.length}`,
    `可预览离线=${previewReadyOffline}`,
    `恢复就绪率=${recoveryReadyRate}%`,
    `优先跟进Top3=${top3 || "-"}`
  ].join("；");
});
const offlineRecoveryNextStepAdvice = computed(() => {
  if (offlineDeviceCount.value <= 0) return "下一步建议：当前无离线设备，维持例行巡检即可。";
  if (offlineRecoverySummaryText.value.includes("恢复就绪率=0%")) {
    return "下一步建议：先补齐离线设备通道标识，再执行恢复联调。";
  }
  return "下一步建议：按 Top3 顺序执行网络与供电排查，恢复后立即回归预览验证。";
});
const onlineNotPreviewReadyTop3 = computed(() =>
  devices.value
    .filter((x) => Number(x.status) === 1 && !String(x.gb_id || "").trim())
    .slice(0, 3)
    .map((x) => x.name || x.id)
    .join(" / ")
);
const onlineInspectionPrioritySummary = computed(() => {
  const online = onlineDeviceCount.value;
  const ready = onlinePreviewReadyDeviceCount.value;
  const gap = Math.max(0, online - ready);
  const readyRate = online <= 0 ? 0 : Number(((ready / online) * 100).toFixed(2));
  return [
    "在线抽检优先级摘要",
    `在线总量=${online}`,
    `在线可预览=${ready}`,
    `抽检缺口=${gap}`,
    `在线可预览率=${readyRate}%`,
    `优先补齐Top3=${onlineNotPreviewReadyTop3.value || "-"}`
  ].join("；");
});
const onlineInspectionPriorityAdvice = computed(() => {
  if (onlineDeviceCount.value <= 0) return "下一步建议：先恢复在线设备，再执行在线抽检。";
  if (onlineInspectionPrioritySummary.value.includes("抽检缺口=0")) {
    return "下一步建议：在线抽检条件充足，按分组轮巡执行预览验证。";
  }
  return "下一步建议：优先补齐 Top3 设备的通道标识，尽快消除抽检缺口。";
});
const deviceStatusLayerSummary = computed(() => {
  const onlineReady = devices.value.filter((x) => Number(x.status) === 1 && !!String(x.gb_id || "").trim()).length;
  const onlineNotReady = devices.value.filter((x) => Number(x.status) === 1 && !String(x.gb_id || "").trim()).length;
  const offlineReady = devices.value.filter((x) => Number(x.status) !== 1 && !!String(x.gb_id || "").trim()).length;
  const offlineNotReady = devices.value.filter((x) => Number(x.status) !== 1 && !String(x.gb_id || "").trim()).length;
  return `设备状态分层：在线可预览=${onlineReady}；在线不可预览=${onlineNotReady}；离线可预览=${offlineReady}；离线不可预览=${offlineNotReady}`;
});
const deviceStatusLayerAdvice = computed(() => {
  if (devices.value.length <= 0) return "下一步建议：先同步设备清单，再进行分层治理。";
  if (deviceStatusLayerSummary.value.includes("在线不可预览=0") && deviceStatusLayerSummary.value.includes("离线不可预览=0")) {
    return "下一步建议：分层结构较优，保持在线抽检与离线恢复节奏。";
  }
  if (!deviceStatusLayerSummary.value.includes("在线不可预览=0")) return "下一步建议：优先清理在线不可预览设备，提升即时抽检能力。";
  return "下一步建议：补齐离线不可预览设备通道标识，便于恢复后快速验收。";
});

async function loadDevices() {
  loading.value = true;
  deviceLoadMessage.value = "";
  try {
    const res = await fetchDevices(keyword.value.trim());
    devices.value = res.items || [];
    deviceLastLoadedAt.value = new Date().toISOString();
    deviceLoadMessage.value = "设备列表拉取成功";
  } catch (err: any) {
    devices.value = [];
    deviceLoadMessage.value = err?.message ? `设备列表拉取失败：${err.message}` : "设备列表拉取失败，请重试";
    uni.showToast({ title: "设备拉取失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

function openPreview(device: DeviceItem) {
  const deviceId = String(device.id || "").trim();
  const channelId = String(device.gb_id || "").trim();
  const name = String(device.name || device.gb_id || device.id || "设备");
  if (!deviceId || !channelId) {
    setDevicePreviewActionStatus(`发起预览失败：${name} 缺少通道标识`);
    uni.showToast({ title: "设备缺少通道标识", icon: "none" });
    return;
  }
  setDevicePreviewActionStatus(`发起预览成功：${name}`);
  uni.navigateTo({
    url: `/pages/preview/index?deviceId=${encodeURIComponent(deviceId)}&channelId=${encodeURIComponent(channelId)}`,
    fail: () => {
      setDevicePreviewActionStatus(`发起预览失败：${name} 跳转异常`);
      uni.showToast({ title: "跳转预览失败", icon: "none" });
    }
  });
}

function copyDeviceSearchSummary() {
  const text = [deviceSearchSummaryText.value, deviceSearchNextStepAdvice.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "设备检索摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyDevicePatrolSummary() {
  const text = [devicePatrolSummaryText.value, devicePatrolNextStepAdvice.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "设备巡检摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyOfflineRecoverySummary() {
  const text = [offlineRecoverySummaryText.value, offlineRecoveryNextStepAdvice.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "离线恢复摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyOnlineInspectionPrioritySummary() {
  const text = [onlineInspectionPrioritySummary.value, onlineInspectionPriorityAdvice.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "在线抽检摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyDeviceStatusLayerSummary() {
  const text = [deviceStatusLayerSummary.value, deviceStatusLayerAdvice.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "状态分层摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

onShow(loadDevices);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">设备中心</view>
    <view class="app-card">
      <input v-model="keyword" placeholder="输入设备名或编码" />
      <button type="primary" style="margin-top: 12rpx" :loading="loading" @click="loadDevices">搜索</button>
      <text class="app-subtext">刷新状态：{{ deviceLoadMessage || "-" }}</text>
      <text class="app-subtext">上次刷新：{{ deviceLastLoadedAt || "-" }}</text>
      <text class="app-subtext">预览状态：{{ devicePreviewActionMessage || "-" }}</text>
      <text class="app-subtext">预览时间：{{ devicePreviewActionAt || "-" }}</text>
      <text class="app-subtext" style="margin-top: 8rpx">{{ deviceSearchSummaryText }}</text>
      <text class="app-subtext">{{ deviceSearchNextStepAdvice }}</text>
      <view class="app-row">
        <button size="mini" @click="copyDeviceSearchSummary">复制检索摘要</button>
      </view>
    </view>

    <view class="app-gap-12">
      <view class="app-card app-gap-12">
        <text class="app-subtext">{{ devicePatrolSummaryText }}</text>
        <text class="app-subtext">{{ devicePatrolNextStepAdvice }}</text>
        <text class="app-subtext">{{ offlineRecoverySummaryText }}</text>
        <text class="app-subtext">{{ offlineRecoveryNextStepAdvice }}</text>
        <text class="app-subtext">{{ onlineInspectionPrioritySummary }}</text>
        <text class="app-subtext">{{ onlineInspectionPriorityAdvice }}</text>
        <text class="app-subtext">{{ deviceStatusLayerSummary }}</text>
        <text class="app-subtext">{{ deviceStatusLayerAdvice }}</text>
        <view class="app-row">
          <button size="mini" @click="copyDevicePatrolSummary">复制巡检摘要</button>
          <button size="mini" @click="copyOfflineRecoverySummary">复制离线恢复摘要</button>
          <button size="mini" @click="copyOnlineInspectionPrioritySummary">复制在线抽检摘要</button>
          <button size="mini" @click="copyDeviceStatusLayerSummary">复制状态分层摘要</button>
        </view>
      </view>
      <view v-for="item in devices" :key="item.id" class="app-card app-gap-12">
        <view class="app-row">
          <text>{{ item.name || item.gb_id }}</text>
          <text :style="{ color: Number(item.status) === 1 ? '#10B981' : '#EF4444' }">
            {{ Number(item.status) === 1 ? "在线" : "离线" }}
          </text>
        </view>
        <text class="app-subtext">{{ item.gb_id }}</text>
        <button size="mini" type="primary" :disabled="!String(item.gb_id || '').trim()" @click="openPreview(item)">实时预览</button>
      </view>
      <view v-if="!loading && devices.length === 0" class="app-subtext">暂无设备数据</view>
    </view>
  </view>
</template>
