<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import { fetchDeviceTree, type DeviceTreeNode } from "@/api/device";
import { fetchAccessSources, previewSource, type AccessSourceItem } from "@/api/integration";
import AppEmpty from "@/components/AppEmpty.vue";

type MonitorChannel = {
  id: string;
  label: string;
  nodeType: "channel" | "source_stream";
  status: number;
  deviceId?: string;
  sourceId?: string;
};

const loading = ref(false);
const treeMode = ref<"business" | "region">("business");
const keyword = ref("");
const onlineOnly = ref(false);
const channels = ref<MonitorChannel[]>([]);
const sources = ref<AccessSourceItem[]>([]);
const loadMessage = ref("未刷新");
const loadAt = ref("");
const actionLoading = ref(false);

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

function flattenChannels(nodes: DeviceTreeNode[], out: MonitorChannel[] = []) {
  for (const n of nodes || []) {
    const nodeType = String((n as any)?.nodeType || "").toLowerCase();
    if (nodeType === "channel") {
      out.push({
        id: String((n as any)?.id || ""),
        label: String((n as any)?.label || ""),
        nodeType: "channel",
        status: Number((n as any)?.status || 0),
        deviceId: String((n as any)?.deviceId || "")
      });
    }
    if (Array.isArray((n as any)?.children) && (n as any).children.length > 0) {
      flattenChannels((n as any).children, out);
    }
  }
  return out;
}

const sourceStreamChannels = computed<MonitorChannel[]>(() => {
  return (sources.value || []).map((x) => ({
    id: String(x.id || ""),
    label: `${x.name || x.id}（${x.protocol || "-"}）`,
    nodeType: "source_stream",
    status: x.enabled ? 1 : 0,
    sourceId: String(x.id || "")
  }));
});

const mergedChannels = computed<MonitorChannel[]>(() => {
  return [...channels.value, ...sourceStreamChannels.value];
});

const filteredChannels = computed<MonitorChannel[]>(() => {
  return mergedChannels.value.filter((x) => {
    if (onlineOnly.value && Number(x.status) !== 1) return false;
    if (!keyword.value) return true;
    const text = `${x.label} ${x.id} ${x.deviceId || ""}`.toLowerCase();
    return text.includes(keyword.value.toLowerCase());
  });
});

const summaryText = computed(() => {
  const online = filteredChannels.value.filter((x) => Number(x.status) === 1).length;
  const sourceCount = filteredChannels.value.filter((x) => x.nodeType === "source_stream").length;
  return `监控中心：通道总数=${filteredChannels.value.length}；在线=${online}；接入源流=${sourceCount}；树模式=${treeMode.value}`;
});

const nextStepAdvice = computed(() => {
  if (filteredChannels.value.length <= 0) return "下一步建议：先同步设备目录或新增多协议接入源。";
  if (filteredChannels.value.filter((x) => Number(x.status) === 1).length <= 0) return "下一步建议：当前无在线通道，建议优先恢复设备在线状态。";
  return "下一步建议：优先抽检在线通道并在预览页执行弱网门禁巡检。";
});

async function loadData() {
  loading.value = true;
  try {
    const [treeRes, sourceRes] = await Promise.allSettled([fetchDeviceTree(treeMode.value), fetchAccessSources()]);
    channels.value = treeRes.status === "fulfilled" ? flattenChannels(Array.isArray(treeRes.value) ? treeRes.value : []) : [];
    sources.value = sourceRes.status === "fulfilled" && Array.isArray(sourceRes.value) ? sourceRes.value : [];
    const failedCount = [treeRes, sourceRes].filter((x) => x.status === "rejected").length;
    if (failedCount > 0) {
      setLoadStatus(`部分刷新成功：失败 ${failedCount} 项`);
      uni.showToast({ title: `部分接口失败(${failedCount})`, icon: "none" });
    } else {
      setLoadStatus("刷新成功");
    }
  } catch (err: any) {
    channels.value = [];
    sources.value = [];
    setLoadStatus(err?.message ? `刷新失败：${err.message}` : "刷新失败");
    uni.showToast({ title: "监控中心加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

function openPreview(channel: MonitorChannel) {
  if (channel.nodeType === "source_stream") {
    copySourcePreview(channel);
    return;
  }
  const deviceId = String(channel.deviceId || "").trim();
  const channelId = String(channel.id || "").trim();
  if (!deviceId || !channelId) {
    uni.showToast({ title: "缺少 deviceId/channelId", icon: "none" });
    return;
  }
  uni.navigateTo({
    url: `/pages/preview/index?deviceId=${encodeURIComponent(deviceId)}&channelId=${encodeURIComponent(channelId)}`
  });
}

async function copySourcePreview(channel: MonitorChannel) {
  if (!channel.sourceId) {
    uni.showToast({ title: "缺少 sourceId", icon: "none" });
    return;
  }
  actionLoading.value = true;
  try {
    const res = await previewSource(channel.sourceId);
    const text = `接入源预览：${channel.label}；webrtc=${res?.webrtc || "-"}；flv=${res?.flv || "-"}；hls=${res?.hls || "-"}`;
    uni.setClipboardData({
      data: text,
      success: () => uni.showToast({ title: "预览地址已复制", icon: "none" }),
      fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
    });
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `获取失败：${err.message}` : "获取失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

function copySummary() {
  const text = [
    summaryText.value,
    `筛选=keyword:${keyword.value || "-"},onlineOnly:${onlineOnly.value ? "true" : "false"}`,
    nextStepAdvice.value,
    `刷新状态=${loadMessage.value || "-"}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "监控摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

onShow(loadData);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">监控中心</view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-subtext">{{ summaryText }}</text>
        <button size="mini" :loading="loading" @click="loadData">刷新</button>
      </view>
      <text class="app-subtext">{{ nextStepAdvice }}</text>
      <text class="app-subtext">刷新状态：{{ loadMessage || "-" }}</text>
      <text class="app-subtext">状态时间：{{ loadAt || "-" }}</text>
      <view class="app-row">
        <button size="mini" @click="copySummary">复制摘要</button>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">筛选条件</text>
      <view class="app-row">
        <button
          size="mini"
          :type="treeMode === 'business' ? 'primary' : 'default'"
          @click="
            treeMode = 'business';
            loadData();
          "
        >
          业务分组
        </button>
        <button
          size="mini"
          :type="treeMode === 'region' ? 'primary' : 'default'"
          @click="
            treeMode = 'region';
            loadData();
          "
        >
          行政区划
        </button>
        <button
          size="mini"
          @click="
            onlineOnly = !onlineOnly;
          "
        >
          {{ onlineOnly ? "仅在线=开" : "仅在线=关" }}
        </button>
      </view>
      <input v-model="keyword" class="app-input" placeholder="搜索通道/设备/ID" />
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">可播放通道（{{ filteredChannels.length }}）</text>
      <view v-if="filteredChannels.length" class="app-gap-12">
        <view v-for="row in filteredChannels.slice(0, 120)" :key="`${row.nodeType}-${row.id}`" class="app-card">
          <text class="app-subtext">{{ row.label }}</text>
          <text class="app-subtext">类型：{{ row.nodeType }}；状态：{{ row.status === 1 ? "在线/启用" : "离线/停用" }}</text>
          <text class="app-subtext" v-if="row.nodeType === 'channel'">设备ID：{{ row.deviceId || "-" }}；通道ID：{{ row.id }}</text>
          <text class="app-subtext" v-else>接入源ID：{{ row.sourceId || "-" }}</text>
          <view class="app-row">
            <button size="mini" :loading="actionLoading" @click="openPreview(row)">
              {{ row.nodeType === "source_stream" ? "复制预览地址" : "进入预览页" }}
            </button>
          </view>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '通道加载中...' : '暂无可播放通道'" />
    </view>
  </view>
</template>
