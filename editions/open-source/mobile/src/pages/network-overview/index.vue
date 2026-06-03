<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import {
  fetchNetworkBandwidth,
  fetchNetworkSummary,
  fetchNetworkTopology,
  type NetworkRange
} from "@/api/network";
import AppEmpty from "@/components/AppEmpty.vue";

const loading = ref(false);
const range = ref<NetworkRange>("1h");
const summary = ref({
  device_total: 0,
  device_online: 0,
  stream_count: 0,
  stream_count_zlm: 0,
  zlm_bandwidth_mbps: 0,
  description: ""
});
const topologyNodes = ref<any[]>([]);
const topologyEdges = ref<any[]>([]);
const streamSeries = ref<Array<{ t: string; value: number }>>([]);
const zlmSeries = ref<Array<{ t: string; value: number }>>([]);
const loadMessage = ref("未刷新");
const loadAt = ref("");

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

const deviceOnlineRate = computed(() => {
  const total = Number(summary.value.device_total || 0);
  const online = Number(summary.value.device_online || 0);
  if (total <= 0) return 0;
  return Number(((online / total) * 100).toFixed(2));
});

const summaryText = computed(() => {
  return `网络概况：设备总数=${summary.value.device_total}；在线=${summary.value.device_online}(${deviceOnlineRate.value}%)；实时流=${summary.value.stream_count}；ZLM流=${summary.value.stream_count_zlm}；ZLM带宽=${summary.value.zlm_bandwidth_mbps}Mbps`;
});

const nextStepAdvice = computed(() => {
  if (deviceOnlineRate.value < 80) return "下一步建议：先排查离线设备与链路连通性，再观察带宽回稳情况。";
  if (Number(summary.value.zlm_bandwidth_mbps || 0) > 300) return "下一步建议：当前带宽偏高，建议进入运维中心做活跃流抽样诊断。";
  return "下一步建议：保持趋势观察，并结合拓扑状态进行例行巡检。";
});

const topologySummaryText = computed(() => {
  const online = topologyNodes.value.filter((x) => x?.status !== "offline").length;
  return `拓扑摘要：节点=${topologyNodes.value.length}；边=${topologyEdges.value.length}；在线节点=${online}`;
});

const bandwidthSummaryText = computed(() => {
  const latestStreams = streamSeries.value[streamSeries.value.length - 1]?.value ?? 0;
  const latestMpbs = zlmSeries.value[zlmSeries.value.length - 1]?.value ?? 0;
  return `趋势摘要：窗口=${range.value}；流序列点=${streamSeries.value.length}；带宽序列点=${zlmSeries.value.length}；最新流=${latestStreams}；最新带宽=${latestMpbs}Mbps`;
});

async function loadData() {
  loading.value = true;
  try {
    const [summaryRes, topoRes, bandwidthRes] = await Promise.allSettled([
      fetchNetworkSummary(),
      fetchNetworkTopology(),
      fetchNetworkBandwidth(range.value)
    ]);

    if (summaryRes.status === "fulfilled") {
      summary.value = {
        device_total: Number(summaryRes.value.device_total || 0),
        device_online: Number(summaryRes.value.device_online || 0),
        stream_count: Number(summaryRes.value.stream_count || 0),
        stream_count_zlm: Number(summaryRes.value.stream_count_zlm || 0),
        zlm_bandwidth_mbps: Number(summaryRes.value.zlm_bandwidth_mbps || 0),
        description: String(summaryRes.value.description || "")
      };
    }

    if (topoRes.status === "fulfilled") {
      topologyNodes.value = Array.isArray(topoRes.value.nodes) ? topoRes.value.nodes : [];
      topologyEdges.value = Array.isArray(topoRes.value.edges) ? topoRes.value.edges : [];
    } else {
      topologyNodes.value = [];
      topologyEdges.value = [];
    }

    if (bandwidthRes.status === "fulfilled") {
      const series = Array.isArray(bandwidthRes.value.series) ? bandwidthRes.value.series : [];
      const streams = series.find((x) => x?.name === "active_streams");
      const zlm = series.find((x) => x?.name === "zlm_bandwidth");
      streamSeries.value = Array.isArray(streams?.points) ? streams.points : [];
      zlmSeries.value = Array.isArray(zlm?.points) ? zlm.points : [];
    } else {
      streamSeries.value = [];
      zlmSeries.value = [];
    }

    const failedCount = [summaryRes, topoRes, bandwidthRes].filter((x) => x.status === "rejected").length;
    if (failedCount > 0) {
      setLoadStatus(`部分刷新成功：失败 ${failedCount} 项`);
      uni.showToast({ title: `部分接口失败(${failedCount})`, icon: "none" });
    } else {
      setLoadStatus("刷新成功");
    }
  } catch (err: any) {
    setLoadStatus(err?.message ? `刷新失败：${err.message}` : "刷新失败");
    uni.showToast({ title: "网络概况加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

function changeRange(e: any) {
  const value = Number(e?.detail?.value ?? 0);
  range.value = value === 1 ? "24h" : "1h";
  loadData();
}

function copySummary() {
  const text = [
    summaryText.value,
    topologySummaryText.value,
    bandwidthSummaryText.value,
    nextStepAdvice.value,
    `刷新状态=${loadMessage.value || "-"}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "网络概况摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

onShow(loadData);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">网络概况</view>

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
      <view class="app-row">
        <text class="app-subtext">流量趋势</text>
        <picker mode="selector" :range="['1 小时', '24 小时']" :value="range === '24h' ? 1 : 0" @change="changeRange">
          <view class="app-subtext">窗口：{{ range }}</view>
        </picker>
      </view>
      <text class="app-subtext">{{ bandwidthSummaryText }}</text>
      <view v-if="streamSeries.length" class="app-gap-12">
        <view v-for="(row, idx) in streamSeries.slice(-8)" :key="`stream-${idx}`" class="app-row">
          <text class="app-subtext">流数 {{ row.t }} => {{ row.value }}</text>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '趋势加载中...' : '暂无流数趋势'" />
      <view v-if="zlmSeries.length" class="app-gap-12">
        <view v-for="(row, idx) in zlmSeries.slice(-8)" :key="`zlm-${idx}`" class="app-row">
          <text class="app-subtext">带宽 {{ row.t }} => {{ row.value }} Mbps</text>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '趋势加载中...' : '暂无带宽趋势'" />
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">网络拓扑</text>
      <text class="app-subtext">{{ topologySummaryText }}</text>
      <view v-if="topologyNodes.length" class="app-gap-12">
        <view v-for="(node, idx) in topologyNodes" :key="`node-${idx}`" class="app-row">
          <text class="app-subtext">
            节点 {{ node.label || node.id }}（{{ node.type || "-" }}）状态={{ node.status || "unknown" }}
            <text v-if="node.metrics">；设备={{ node.metrics.device_online || 0 }}/{{ node.metrics.device_total || 0 }}</text>
          </text>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '拓扑加载中...' : '暂无拓扑节点'" />
      <view v-if="topologyEdges.length" class="app-gap-12">
        <view v-for="(edge, idx) in topologyEdges.slice(0, 20)" :key="`edge-${idx}`" class="app-row">
          <text class="app-subtext">链路 {{ edge.source }} -> {{ edge.target }}（{{ edge.type }}）</text>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '拓扑加载中...' : '暂无拓扑链路'" />
    </view>
  </view>
</template>
