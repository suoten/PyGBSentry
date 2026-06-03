<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import {
  applyHealthRecommendations,
  fetchCapacityBaseline,
  fetchCapacityThresholdTemplate,
  fetchHealthDailyReport,
  fetchHealthDevices,
  fetchTuningRecommendations,
  type DeviceHealthItem
} from "@/api/health";
import { getToken } from "@/utils/storage";
import AppEmpty from "@/components/AppEmpty.vue";
import AppStatusTag from "@/components/AppStatusTag.vue";

const loading = ref(false);
const actionLoading = ref(false);
const loadMessage = ref("未刷新");
const loadAt = ref("");
const devices = ref<DeviceHealthItem[]>([]);
const riskFilter = ref<"" | "low" | "medium" | "high">("");
const onlyDiff = ref(true);
const minFailureRate = ref(0);
const baseline = ref<any>(null);
const tuning = ref<any>(null);
const threshold = ref<any>(null);
const daily = ref<any>(null);
const applySummary = ref("");

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

const summaryText = computed(() => {
  return `健康看板：设备=${baseline.value?.total_devices ?? 0}；高风险=${baseline.value?.high_risk_devices ?? 0}；不稳定=${baseline.value?.unstable_devices ?? 0}；筛选结果=${devices.value.length}`;
});

const nextStepAdvice = computed(() => {
  const healthLevel = String(baseline.value?.health_level || "green");
  if (healthLevel === "red") return "下一步建议：先按高风险设备批量应用推荐策略，再复核失败率回落。";
  if (healthLevel === "yellow") return "下一步建议：关注中高风险设备，优先处理连续失败通道。";
  return "下一步建议：保持日常巡检并定期导出健康报表复盘。";
});

async function loadData() {
  loading.value = true;
  try {
    const [devicesRes, baselineRes, tuningRes, thresholdRes, dailyRes] = await Promise.allSettled([
      fetchHealthDevices({
        risk_level: riskFilter.value || undefined,
        min_failure_rate: Number(minFailureRate.value || 0),
        only_diff: !!onlyDiff.value
      }),
      fetchCapacityBaseline(),
      fetchTuningRecommendations(),
      fetchCapacityThresholdTemplate(),
      fetchHealthDailyReport(5)
    ]);

    devices.value = devicesRes.status === "fulfilled" && Array.isArray(devicesRes.value) ? devicesRes.value : [];
    baseline.value = baselineRes.status === "fulfilled" ? baselineRes.value : null;
    tuning.value = tuningRes.status === "fulfilled" ? tuningRes.value : null;
    threshold.value = thresholdRes.status === "fulfilled" ? thresholdRes.value : null;
    daily.value = dailyRes.status === "fulfilled" ? dailyRes.value : null;

    const failedCount = [devicesRes, baselineRes, tuningRes, thresholdRes, dailyRes].filter((x) => x.status === "rejected").length;
    if (failedCount > 0) {
      setLoadStatus(`部分刷新成功：失败 ${failedCount} 项`);
      uni.showToast({ title: `部分接口失败(${failedCount})`, icon: "none" });
    } else {
      setLoadStatus("刷新成功");
    }
  } catch (err: any) {
    devices.value = [];
    setLoadStatus(err?.message ? `刷新失败：${err.message}` : "刷新失败");
    uni.showToast({ title: "健康数据加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

async function dryRunApply() {
  actionLoading.value = true;
  try {
    const res = await applyHealthRecommendations({
      risk_level: riskFilter.value || undefined,
      min_failure_rate: Number(minFailureRate.value || 0),
      only_diff: !!onlyDiff.value,
      dry_run: true
    });
    applySummary.value = `预演完成：匹配=${res.matched}；建议变更=${res.would_apply}`;
    uni.showToast({ title: "预演完成", icon: "none" });
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `预演失败：${err.message}` : "预演失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function applyNow() {
  uni.showModal({
    title: "确认应用",
    content: "确认批量应用健康推荐策略吗？",
    success: async (res) => {
      if (!res.confirm) return;
      actionLoading.value = true;
      try {
        const ret = await applyHealthRecommendations({
          risk_level: riskFilter.value || undefined,
          min_failure_rate: Number(minFailureRate.value || 0),
          only_diff: !!onlyDiff.value,
          dry_run: false
        });
        applySummary.value = `应用完成：匹配=${ret.matched}；建议变更=${ret.would_apply}；实际应用=${ret.applied}`;
        uni.showToast({ title: "策略应用完成", icon: "none" });
        await loadData();
      } catch (err: any) {
        uni.showToast({ title: err?.message ? `应用失败：${err.message}` : "应用失败", icon: "none" });
      } finally {
        actionLoading.value = false;
      }
    }
  });
}

function buildApiUrl(path: string) {
  const apiBase = String(import.meta.env.VITE_API_BASE || "").replace(/\/$/, "");
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  return `${apiBase}${path}`;
}

async function exportDailyCsv() {
  const token = getToken();
  if (!token) {
    uni.showToast({ title: "请先登录后导出", icon: "none" });
    return;
  }
  try {
    const url = buildApiUrl("/api/v1/health/report/daily.csv");
    const [err, res] = await uni.downloadFile({
      url,
      header: { Authorization: `Bearer ${token}` }
    });
    if (err || !res || res.statusCode < 200 || res.statusCode >= 300) {
      throw new Error(`导出失败(${res?.statusCode || "network"})`);
    }
    uni.showToast({ title: "报表导出成功", icon: "none" });
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `导出失败：${err.message}` : "导出失败", icon: "none" });
  }
}

function copySummary() {
  const text = [
    summaryText.value,
    nextStepAdvice.value,
    `推荐档位=${tuning.value?.profile || "-"}`,
    `刷新状态=${loadMessage.value || "-"}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "健康摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

onShow(loadData);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">健康看板</view>

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
      <text class="app-subtext">筛选与动作</text>
      <picker mode="selector" :range="['全部','低风险','中风险','高风险']" :value="riskFilter === '' ? 0 : riskFilter === 'low' ? 1 : riskFilter === 'medium' ? 2 : 3" @change="(e:any)=>{ const i=Number(e?.detail?.value||0); riskFilter = i===1?'low':i===2?'medium':i===3?'high':''; }">
        <view class="app-subtext">风险筛选：{{ riskFilter || "全部" }}</view>
      </picker>
      <input v-model="minFailureRate" type="digit" placeholder="最低失败率（0-1）" />
      <label class="app-subtext"><checkbox :checked="onlyDiff" @click="onlyDiff = !onlyDiff" /> 仅看策略差异</label>
      <view class="app-row">
        <button size="mini" @click="loadData">应用筛选</button>
        <button size="mini" :loading="actionLoading" @click="dryRunApply">推荐预演</button>
        <button size="mini" type="primary" :loading="actionLoading" @click="applyNow">应用推荐</button>
        <button size="mini" @click="exportDailyCsv">导出日报CSV</button>
      </view>
      <text class="app-subtext">执行结果：{{ applySummary || "-" }}</text>
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">容量与调优建议</text>
      <text class="app-subtext">健康等级：{{ baseline?.health_level || "-" }}；P95失败率：{{ baseline?.p95_failure_rate_pct ?? 0 }}%</text>
      <text class="app-subtext">推荐档位：{{ tuning?.profile || "-" }}；建议项：{{ tuning?.changed_count ?? 0 }}</text>
      <text class="app-subtext">推荐并发：{{ threshold?.recommended_concurrency ?? "-" }}；设备规模：{{ threshold?.fleet_size ?? 0 }}</text>
      <text class="app-subtext">日报：高={{ daily?.high_risk ?? 0 }}；中={{ daily?.medium_risk ?? 0 }}；低={{ daily?.low_risk ?? 0 }}</text>
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">设备健康列表：{{ devices.length }} 条</text>
      <view v-if="devices.length" class="app-gap-12">
        <view v-for="row in devices.slice(0, 120)" :key="row.device_id" class="app-row">
          <view style="flex:1">
            <text class="app-subtext">{{ row.device_name || row.device_id }}（{{ row.device_id }}）</text>
            <text class="app-subtext">失败率={{ row.failure_rate }}；连续失败={{ row.consecutive_failures }}；当前={{ row.current_policy_mode }}；建议={{ row.recommended_mode }}</text>
            <text class="app-subtext">{{ row.recommend_reason || "-" }}</text>
          </view>
          <AppStatusTag :text="row.risk_level || '-'" :type="row.risk_level === 'high' ? 'danger' : row.risk_level === 'medium' ? 'warning' : 'success'" />
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '健康数据加载中...' : '暂无健康数据'" />
    </view>
  </view>
</template>
