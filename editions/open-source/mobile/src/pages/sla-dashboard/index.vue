<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import {
  acknowledgeAlarm,
  escalateAlarm,
  fetchAlarms,
  fetchSlaCompare,
  fetchSlaOverview,
  fetchSlaQuality,
  type AlarmItem,
  type SlaCompareOverview,
  type SlaOverview,
  type SlaQualityOverview
} from "@/api/alarm";
import AppEmpty from "@/components/AppEmpty.vue";
import AppStatusTag from "@/components/AppStatusTag.vue";

const loading = ref(false);
const actionLoading = ref(false);
const alarms = ref<AlarmItem[]>([]);
const overview = ref<SlaOverview>({
  total_open: 0,
  escalated_open: 0,
  overdue_open: 0,
  acknowledged_today: 0,
  avg_ack_minutes_today: 0
});
const compare = ref<SlaCompareOverview>({
  days: 7,
  period_current: 0,
  period_previous: 0,
  period_change_pct: 0,
  day_current: 0,
  day_previous: 0,
  day_change_pct: 0
});
const quality = ref<SlaQualityOverview>({
  days: 7,
  p50_ack_minutes: 0,
  p90_ack_minutes: 0,
  samples: 0,
  level_distribution: {},
  alarm_type_distribution: {},
  organization_distribution: {},
  slow_samples: []
});

const stateFilter = ref<"" | "open" | "acknowledged">("");
const minEscalationLevel = ref(0);
const page = ref(1);
const pageSize = ref(10);
const loadMessage = ref("未刷新");
const loadAt = ref("");

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

const pagedAlarms = computed(() => {
  const start = (page.value - 1) * pageSize.value;
  return alarms.value.slice(start, start + pageSize.value);
});

const summaryText = computed(() => {
  return `SLA看板：未确认=${overview.value.total_open}；升级未确认=${overview.value.escalated_open}；超时未确认=${overview.value.overdue_open}；今日确认=${overview.value.acknowledged_today}`;
});

const nextStepAdvice = computed(() => {
  if (overview.value.overdue_open > 0) return "下一步建议：优先处理已超时未确认告警，并补充确认备注。";
  if (overview.value.escalated_open > 0) return "下一步建议：优先对已升级告警执行确认，防止跨班遗留。";
  return "下一步建议：保持SLA巡检频率，重点关注确认效率趋势。";
});

async function loadData() {
  loading.value = true;
  try {
    const [ovRes, cmpRes, qRes, alarmsRes] = await Promise.allSettled([
      fetchSlaOverview(),
      fetchSlaCompare(7),
      fetchSlaQuality(7),
      fetchAlarms({
        skip: 0,
        limit: 100,
        escalation_state: stateFilter.value || undefined,
        min_escalation_level: Number(minEscalationLevel.value || 0)
      })
    ]);

    if (ovRes.status === "fulfilled") overview.value = ovRes.value;
    if (cmpRes.status === "fulfilled") compare.value = cmpRes.value;
    if (qRes.status === "fulfilled") quality.value = qRes.value;
    if (alarmsRes.status === "fulfilled") alarms.value = Array.isArray(alarmsRes.value.items) ? alarmsRes.value.items : [];
    const failedCount = [ovRes, cmpRes, qRes, alarmsRes].filter((x) => x.status === "rejected").length;
    if (failedCount > 0) {
      setLoadStatus(`部分刷新成功：失败 ${failedCount} 项`);
      uni.showToast({ title: `部分接口失败(${failedCount})`, icon: "none" });
    } else {
      setLoadStatus("刷新成功");
    }
  } catch (err: any) {
    alarms.value = [];
    setLoadStatus(err?.message ? `刷新失败：${err.message}` : "刷新失败");
    uni.showToast({ title: "SLA数据加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

async function doEscalate(row: AlarmItem) {
  const id = String(row.id || "").trim();
  if (!id) return;
  actionLoading.value = true;
  try {
    await escalateAlarm(id, "mobile_sla_escalate");
    uni.showToast({ title: "告警已升级", icon: "none" });
    await loadData();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `升级失败：${err.message}` : "升级失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function doAcknowledge(row: AlarmItem) {
  const id = String(row.id || "").trim();
  if (!id) return;
  actionLoading.value = true;
  try {
    await acknowledgeAlarm(id, "mobile_sla_ack");
    uni.showToast({ title: "告警已确认", icon: "none" });
    await loadData();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `确认失败：${err.message}` : "确认失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

function prevPage() {
  if (page.value <= 1) return;
  page.value -= 1;
}

function nextPage() {
  const maxPage = Math.max(1, Math.ceil(alarms.value.length / pageSize.value));
  if (page.value >= maxPage) return;
  page.value += 1;
}

function copySummary() {
  const text = [
    summaryText.value,
    nextStepAdvice.value,
    `7天趋势=${compare.value.period_change_pct}%`,
    `P90确认时长=${quality.value.p90_ack_minutes} 分钟`,
    `刷新状态=${loadMessage.value || "-"}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "SLA摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

onShow(loadData);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">SLA 看板</view>

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
      <picker mode="selector" :range="['全部','未确认(open)','已确认(acknowledged)']" :value="stateFilter === '' ? 0 : stateFilter === 'open' ? 1 : 2" @change="(e:any)=>{ const i=Number(e?.detail?.value||0); stateFilter = i===1 ? 'open' : i===2 ? 'acknowledged' : ''; loadData(); }">
        <view class="app-subtext">状态：{{ stateFilter || "全部" }}</view>
      </picker>
      <input v-model="minEscalationLevel" type="number" placeholder="最低升级级别" />
      <button size="mini" @click="loadData">应用筛选</button>
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">趋势概览</text>
      <text class="app-subtext">7天对比：当前 {{ compare.period_current }} / 上期 {{ compare.period_previous }}（{{ compare.period_change_pct }}%）</text>
      <text class="app-subtext">日对比：当前 {{ compare.day_current }} / 上日 {{ compare.day_previous }}（{{ compare.day_change_pct }}%）</text>
      <text class="app-subtext">确认质量：P50={{ quality.p50_ack_minutes }} 分钟；P90={{ quality.p90_ack_minutes }} 分钟；样本={{ quality.samples }}</text>
    </view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-subtext">告警列表：{{ alarms.length }} 条</text>
        <view class="app-row">
          <button size="mini" :disabled="page<=1" @click="prevPage">上一页</button>
          <button size="mini" :disabled="page>=Math.max(1, Math.ceil(alarms.length / pageSize))" @click="nextPage">下一页</button>
        </view>
      </view>
      <text class="app-subtext">第 {{ page }} / {{ Math.max(1, Math.ceil(alarms.length / pageSize)) }} 页（每页 {{ pageSize }} 条）</text>
      <view v-if="pagedAlarms.length" class="app-gap-12">
        <view v-for="row in pagedAlarms" :key="row.id" class="app-row">
          <view style="flex:1">
            <text class="app-subtext">{{ row.time || "-" }} | {{ row.device_id || "-" }}</text>
            <text class="app-subtext">{{ row.description || "-" }}</text>
            <text class="app-subtext">升级级别：{{ row.escalation_level ?? 0 }}；状态：{{ row.escalation_state || "-" }}</text>
          </view>
          <view class="app-gap-12">
            <AppStatusTag :text="row.escalation_state === 'acknowledged' ? '已确认' : '未确认'" :type="row.escalation_state === 'acknowledged' ? 'success' : 'warning'" />
            <button size="mini" :loading="actionLoading" :disabled="row.escalation_state === 'acknowledged'" @click="doEscalate(row)">升级</button>
            <button size="mini" :loading="actionLoading" :disabled="row.escalation_state === 'acknowledged'" @click="doAcknowledge(row)">确认</button>
          </view>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '告警加载中...' : '暂无告警'" />
    </view>
  </view>
</template>
