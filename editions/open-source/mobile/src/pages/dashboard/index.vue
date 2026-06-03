<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import {
  fetchDashboardAlarms,
  fetchDemoStatus,
  fetchDevicesOverview,
  fetchDiagnoseReport,
  fetchNetworkBandwidth,
  fetchNetworkSummary,
  fetchOpsStatus,
  fetchSystemInfo
} from "@/api/dashboard";
import AppEmpty from "@/components/AppEmpty.vue";

const loading = ref(false);
const loadingMetrics = ref(false);
const activeTab = ref<"overview" | "metrics">("overview");
const devicesOverview = ref<any>(null);
const alarms = ref<any[]>([]);
const demoEnabled = ref(false);
const systemInfo = ref<any>(null);
const opsStatus = ref<any>(null);
const diagnose = ref<any>(null);
const networkSummary = ref<any>(null);
const networkTrend = ref<Array<{ t: string; estimated: number; zlm: number; streams: number }>>([]);
const loadMessage = ref("未刷新");
const loadAt = ref("");
const metricsLoadMessage = ref("未刷新");

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

const onlineRate = computed(() => {
  const total = Number(devicesOverview.value?.device_total || 0);
  const online = Number(devicesOverview.value?.device_online || 0);
  if (total <= 0) return 0;
  return Number(((online / total) * 100).toFixed(2));
});

const alarmPriorityStats = computed(() => {
  const p1 = alarms.value.filter((x) => String(x.priority || "") === "1").length;
  const p2 = alarms.value.filter((x) => String(x.priority || "") === "2").length;
  const p3 = Math.max(alarms.value.length - p1 - p2, 0);
  return { p1, p2, p3 };
});

const summaryText = computed(() => {
  return `工作台：设备=${devicesOverview.value?.device_total ?? 0}；在线=${devicesOverview.value?.device_online ?? 0}(${onlineRate.value}%)；通道=${devicesOverview.value?.channel_online ?? 0}/${devicesOverview.value?.channel_total ?? 0}；告警=${alarms.value.length}`;
});

const metricsSummaryText = computed(() => {
  return `资源统计：CPU=${opsStatus.value?.cpu ?? 0}%；内存=${opsStatus.value?.memory_percent ?? 0}%；带宽=${networkSummary.value?.zlm_bandwidth_mbps ?? 0}Mbps；流数=${networkSummary.value?.stream_count_zlm ?? networkSummary.value?.stream_count ?? 0}`;
});

const nextStepAdvice = computed(() => {
  if (onlineRate.value < 80) return "下一步建议：先处理离线设备，再排查通道可用性。";
  if (alarms.value.length > 0) return "下一步建议：优先进入告警中心确认高优先级告警。";
  return "下一步建议：保持巡检频率，重点关注资源统计波动。";
});

function formatTime(value: string) {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString();
}

async function loadOverview() {
  loading.value = true;
  try {
    const [statsRes, alarmsRes, demoRes, infoRes] = await Promise.allSettled([
      fetchDevicesOverview(),
      fetchDashboardAlarms(50),
      fetchDemoStatus(),
      fetchSystemInfo()
    ]);
    devicesOverview.value = statsRes.status === "fulfilled" ? statsRes.value : null;
    alarms.value = alarmsRes.status === "fulfilled" && Array.isArray(alarmsRes.value.items) ? alarmsRes.value.items : [];
    demoEnabled.value = demoRes.status === "fulfilled" ? !!demoRes.value.enabled : false;
    systemInfo.value = infoRes.status === "fulfilled" ? infoRes.value : null;
    const failedCount = [statsRes, alarmsRes, demoRes, infoRes].filter((x) => x.status === "rejected").length;
    if (failedCount > 0) {
      setLoadStatus(`部分刷新成功：失败 ${failedCount} 项`);
      uni.showToast({ title: `部分接口失败(${failedCount})`, icon: "none" });
    } else {
      setLoadStatus("刷新成功");
    }
  } catch (err: any) {
    devicesOverview.value = null;
    alarms.value = [];
    demoEnabled.value = false;
    systemInfo.value = null;
    setLoadStatus(err?.message ? `刷新失败：${err.message}` : "刷新失败");
    uni.showToast({ title: "工作台加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

async function loadMetrics() {
  loadingMetrics.value = true;
  try {
    const [opsRes, networkRes, bandwidthRes, diagnoseRes] = await Promise.allSettled([
      fetchOpsStatus(),
      fetchNetworkSummary(),
      fetchNetworkBandwidth("1h"),
      fetchDiagnoseReport()
    ]);
    opsStatus.value = opsRes.status === "fulfilled" ? opsRes.value : null;
    networkSummary.value = networkRes.status === "fulfilled" ? networkRes.value : null;
    diagnose.value = diagnoseRes.status === "fulfilled" ? diagnoseRes.value : null;

    if (bandwidthRes.status === "fulfilled") {
      const series = Array.isArray(bandwidthRes.value.series) ? bandwidthRes.value.series : [];
      const streamSeries = series.find((x) => x?.name === "active_streams");
      const estimatedSeries = series.find((x) => x?.name === "estimated_bandwidth");
      const zlmSeries = series.find((x) => x?.name === "zlm_bandwidth");
      const map = new Map<string, { estimated: number; zlm: number; streams: number }>();
      for (const p of streamSeries?.points || []) {
        map.set(String(p?.t || ""), { estimated: 0, zlm: 0, streams: Number(p?.value || 0) });
      }
      for (const p of estimatedSeries?.points || []) {
        const key = String(p?.t || "");
        const prev = map.get(key) || { estimated: 0, zlm: 0, streams: 0 };
        prev.estimated = Number(p?.value || 0);
        map.set(key, prev);
      }
      for (const p of zlmSeries?.points || []) {
        const key = String(p?.t || "");
        const prev = map.get(key) || { estimated: 0, zlm: 0, streams: 0 };
        prev.zlm = Number(p?.value || 0);
        map.set(key, prev);
      }
      networkTrend.value = Array.from(map.entries())
        .sort((a, b) => String(a[0]).localeCompare(String(b[0])))
        .map(([t, x]) => ({ t, estimated: x.estimated, zlm: x.zlm, streams: x.streams }))
        .slice(-30);
    } else {
      networkTrend.value = [];
    }

    const failedCount = [opsRes, networkRes, bandwidthRes, diagnoseRes].filter((x) => x.status === "rejected").length;
    metricsLoadMessage.value = failedCount > 0 ? `部分刷新成功：失败 ${failedCount} 项` : "刷新成功";
    if (failedCount > 0) {
      uni.showToast({ title: `统计接口失败(${failedCount})`, icon: "none" });
    }
  } catch (err: any) {
    opsStatus.value = null;
    networkSummary.value = null;
    diagnose.value = null;
    networkTrend.value = [];
    metricsLoadMessage.value = err?.message ? `刷新失败：${err.message}` : "刷新失败";
    uni.showToast({ title: "资源统计加载失败", icon: "none" });
  } finally {
    loadingMetrics.value = false;
  }
}

async function loadData() {
  await Promise.all([loadOverview(), loadMetrics()]);
}

function copySystemInfo() {
  const text = [
    `编号=${systemInfo.value?.sip_id || "-"}`,
    `域=${systemInfo.value?.sip_domain || "-"}`,
    `IP=${systemInfo.value?.sip_ip || "-"}`,
    `端口=${systemInfo.value?.sip_port || "-"}`,
    `密码=${systemInfo.value?.sip_password || "-"}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "平台信息已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copySummary() {
  const text = [
    summaryText.value,
    metricsSummaryText.value,
    `告警级别=紧急:${alarmPriorityStats.value.p1},重要:${alarmPriorityStats.value.p2},一般:${alarmPriorityStats.value.p3}`,
    nextStepAdvice.value,
    `刷新状态=${loadMessage.value}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "工作台摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

onShow(loadData);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">工作台</view>

    <view class="app-card app-gap-12">
      <view v-if="demoEnabled" class="app-subtext">演示模式已开启：将展示示例设备用于体验。</view>
      <view class="app-row">
        <button size="mini" :type="activeTab === 'overview' ? 'primary' : 'default'" @click="activeTab = 'overview'">工作台概览</button>
        <button size="mini" :type="activeTab === 'metrics' ? 'primary' : 'default'" @click="activeTab = 'metrics'">资源统计</button>
      </view>
      <view class="app-row">
        <text class="app-subtext">{{ activeTab === "overview" ? summaryText : metricsSummaryText }}</text>
        <button size="mini" :loading="loading || loadingMetrics" @click="loadData">刷新</button>
      </view>
      <text class="app-subtext">{{ nextStepAdvice }}</text>
      <text class="app-subtext">刷新状态：{{ loadMessage || "-" }}</text>
      <text class="app-subtext">统计状态：{{ metricsLoadMessage || "-" }}</text>
      <text class="app-subtext">状态时间：{{ loadAt || "-" }}</text>
      <view class="app-row">
        <button size="mini" @click="copySummary">复制摘要</button>
      </view>
    </view>

    <view v-if="activeTab === 'overview'" class="app-gap-12">
      <view class="app-card app-gap-12">
        <text class="app-subtext">关键指标</text>
        <text class="app-subtext">设备总数：{{ devicesOverview?.device_total ?? 0 }}</text>
        <text class="app-subtext">在线设备：{{ devicesOverview?.device_online ?? 0 }}</text>
        <text class="app-subtext">设备在线率：{{ onlineRate }}%</text>
        <text class="app-subtext">通道在线：{{ devicesOverview?.channel_online ?? 0 }}/{{ devicesOverview?.channel_total ?? 0 }}</text>
      </view>

      <view class="app-card app-gap-12">
        <text class="app-subtext">告警级别分布</text>
        <text class="app-subtext">紧急：{{ alarmPriorityStats.p1 }}；重要：{{ alarmPriorityStats.p2 }}；一般：{{ alarmPriorityStats.p3 }}</text>
      </view>

      <view class="app-card app-gap-12">
        <text class="app-subtext">实时告警（{{ alarms.length }}）</text>
        <view v-if="alarms.length" class="app-gap-12">
          <view v-for="row in alarms.slice(0, 40)" :key="row.id" class="app-card">
            <text class="app-subtext">{{ formatTime(row.time) }}</text>
            <text class="app-subtext">设备：{{ row.device_id || "-" }}；级别：{{ row.priority || "-" }}</text>
            <text class="app-subtext">描述：{{ row.description || "-" }}</text>
          </view>
        </view>
        <AppEmpty v-else :text="loading ? '告警加载中...' : '暂无告警'" />
      </view>

      <view class="app-card app-gap-12">
        <text class="app-subtext">平台信息</text>
        <text class="app-subtext">编号：{{ systemInfo?.sip_id || "-" }}</text>
        <text class="app-subtext">域：{{ systemInfo?.sip_domain || "-" }}</text>
        <text class="app-subtext">IP：{{ systemInfo?.sip_ip || "-" }}；端口：{{ systemInfo?.sip_port || "-" }}</text>
        <text class="app-subtext">版本：{{ systemInfo?.version || "-" }}；项目：{{ systemInfo?.project_name || "-" }}</text>
        <view class="app-row">
          <button size="mini" @click="copySystemInfo">复制平台信息</button>
        </view>
      </view>
    </view>

    <view v-else class="app-gap-12">
      <view class="app-card app-gap-12">
        <text class="app-subtext">资源 KPI</text>
        <text class="app-subtext">CPU：{{ opsStatus?.cpu ?? 0 }}%；内存：{{ opsStatus?.memory_percent ?? 0 }}%</text>
        <text class="app-subtext">带宽：{{ networkSummary?.zlm_bandwidth_mbps ?? 0 }} Mbps</text>
        <text class="app-subtext">流数量：{{ networkSummary?.stream_count_zlm ?? networkSummary?.stream_count ?? 0 }}</text>
      </view>

      <view class="app-card app-gap-12">
        <text class="app-subtext">1小时趋势（最近 {{ networkTrend.length }} 点）</text>
        <view v-if="networkTrend.length" class="app-gap-12">
          <view v-for="(row, idx) in networkTrend.slice(-20)" :key="`trend-${idx}`" class="app-row">
            <text class="app-subtext">{{ row.t }}：估算={{ row.estimated }}Mbps；节点={{ row.zlm }}Mbps；流={{ row.streams }}</text>
          </view>
        </view>
        <AppEmpty v-else :text="loadingMetrics ? '趋势加载中...' : '暂无趋势数据'" />
      </view>

      <view class="app-card app-gap-12">
        <text class="app-subtext">诊断摘要</text>
        <text class="app-subtext">总结：{{ diagnose?.summary || "-" }}</text>
        <text class="app-subtext">生成时间：{{ diagnose?.generated_at || "-" }}</text>
        <view v-if="(diagnose?.items || []).length" class="app-gap-12">
          <view v-for="(row, idx) in diagnose.items.slice(0, 20)" :key="`diag-${idx}`" class="app-row">
            <text class="app-subtext">{{ row.ok ? "✓" : "✗" }} {{ row.name || "-" }}：{{ row.text || "-" }}</text>
          </view>
        </view>
        <AppEmpty v-else :text="loadingMetrics ? '诊断加载中...' : '暂无诊断项'" />
      </view>
    </view>
  </view>
</template>
