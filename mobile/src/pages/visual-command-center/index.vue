<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import { acknowledgeAlarm, fetchAlarms, type AlarmItem } from "@/api/alarm";
import { fetchVisualCommandConfig, type VisualCommandConfig } from "@/api/map";
import AppEmpty from "@/components/AppEmpty.vue";
import AppStatusTag from "@/components/AppStatusTag.vue";

const loading = ref(false);
const ackingId = ref("");
const alarms = ref<AlarmItem[]>([]);
const alarmsTotal = ref(0);
const config = ref<VisualCommandConfig>({
  enabled: true,
  alarm_blink_seconds: 5,
  trajectory_max_points: 50,
  message: ""
});
const loadMessage = ref("未刷新");
const loadAt = ref("");

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

const summaryText = computed(() => {
  return `联动总览：待处理告警=${alarmsTotal.value}；当前列表=${alarms.value.length}；轨迹点上限=${config.value.trajectory_max_points}；闪烁秒数=${config.value.alarm_blink_seconds}`;
});

const nextStepAdvice = computed(() => {
  if (!config.value.enabled) return "下一步建议：先启用可视化指挥配置，再执行联动处置。";
  if (!alarms.value.length) return "下一步建议：当前无待处理告警，可按班次刷新观察。";
  return "下一步建议：优先对高优告警执行地图定位与确认处置。";
});

function formatAlarmTime(alarm: AlarmItem) {
  return String(alarm.time || alarm.created_at || "-");
}

function alarmStatusText(alarm: AlarmItem) {
  if (alarm.escalation_state === "acknowledged") return "已确认";
  return "待处理";
}

function alarmStatusType(alarm: AlarmItem): "success" | "warning" {
  if (alarm.escalation_state === "acknowledged") return "success";
  return "warning";
}

async function loadData() {
  loading.value = true;
  try {
    const [cfgRes, alarmRes] = await Promise.allSettled([
      fetchVisualCommandConfig(),
      fetchAlarms({ skip: 0, limit: 20, escalation_state: "open" })
    ]);
    if (cfgRes.status === "fulfilled") config.value = cfgRes.value;
    alarms.value = alarmRes.status === "fulfilled" && Array.isArray(alarmRes.value.items) ? alarmRes.value.items : [];
    alarmsTotal.value = alarmRes.status === "fulfilled" ? Number(alarmRes.value.total || alarms.value.length || 0) : alarms.value.length;
    const failedCount = [cfgRes, alarmRes].filter((x) => x.status === "rejected").length;
    if (failedCount > 0) {
      setLoadStatus(`部分刷新成功：失败 ${failedCount} 项`);
      uni.showToast({ title: `部分接口失败(${failedCount})`, icon: "none" });
    } else {
      setLoadStatus("刷新成功");
    }
  } catch (err: any) {
    alarms.value = [];
    alarmsTotal.value = 0;
    setLoadStatus(err?.message ? `刷新失败：${err.message}` : "刷新失败");
    uni.showToast({ title: "可视化指挥中心加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

function openMap(alarm: AlarmItem) {
  const deviceId = String(alarm.device_id || "").trim();
  const channelId = String(alarm.channel_id || "").trim();
  uni.navigateTo({
    url: `/pages/gis-map/index?device_id=${encodeURIComponent(deviceId)}&channel_id=${encodeURIComponent(channelId)}`
  });
}

function openVisualCommand(alarm: AlarmItem) {
  const deviceId = String(alarm.device_id || "").trim();
  const channelId = String(alarm.channel_id || "").trim();
  uni.navigateTo({
    url: `/pages/visual-command/index?device_id=${encodeURIComponent(deviceId)}&channel_id=${encodeURIComponent(channelId)}`
  });
}

function openAlarmCenter() {
  uni.navigateTo({ url: "/pages/alarm/index" });
}

function openGisMap() {
  uni.navigateTo({ url: "/pages/gis-map/index" });
}

function openMobileCommand() {
  uni.navigateTo({ url: "/pages/command/index" });
}

async function ackAlarm(alarm: AlarmItem) {
  const id = String(alarm.id || "").trim();
  if (!id) return;
  ackingId.value = id;
  try {
    await acknowledgeAlarm(id);
    uni.showToast({ title: "已确认", icon: "none" });
    await loadData();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `确认失败：${err.message}` : "确认失败", icon: "none" });
  } finally {
    ackingId.value = "";
  }
}

function copyAlarmsCsv() {
  if (!alarms.value.length) {
    uni.showToast({ title: "当前无告警可导出", icon: "none" });
    return;
  }
  const header = ["id", "time", "device_id", "channel_id", "description"];
  const rows = alarms.value.map((row) => [
    String(row.id || ""),
    formatAlarmTime(row),
    String(row.device_id || ""),
    String(row.channel_id || ""),
    String(row.description || "")
  ]);
  const escapeCell = (value: string) => {
    if (value.includes("\"") || value.includes(",") || value.includes("\n")) return `"${value.replace(/"/g, "\"\"")}"`;
    return value;
  };
  const csv = [header.join(","), ...rows.map((line) => line.map((x) => escapeCell(String(x))).join(","))].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => uni.showToast({ title: "告警CSV已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copySummary() {
  const text = [summaryText.value, nextStepAdvice.value, `刷新状态=${loadMessage.value || "-"}`].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "联动摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

onShow(loadData);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">可视化指挥中心</view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-subtext">{{ summaryText }}</text>
        <button size="mini" :loading="loading" @click="loadData">刷新</button>
      </view>
      <text class="app-subtext">{{ config.message || "报警联动、轨迹追踪与快速处置入口" }}</text>
      <text class="app-subtext">状态：{{ config.enabled ? "已启用" : "未启用" }}</text>
      <text class="app-subtext">{{ nextStepAdvice }}</text>
      <text class="app-subtext">刷新状态：{{ loadMessage || "-" }}</text>
      <text class="app-subtext">状态时间：{{ loadAt || "-" }}</text>
      <view class="app-row">
        <button size="mini" @click="copySummary">复制摘要</button>
        <button size="mini" :disabled="!alarms.length" @click="copyAlarmsCsv">导出当前报警</button>
      </view>
      <view class="app-row">
        <button size="mini" type="primary" @click="openAlarmCenter">告警中心</button>
        <button size="mini" @click="openGisMap">电子地图</button>
        <button size="mini" @click="openMobileCommand">移动指挥</button>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">最近报警快速处置（{{ alarms.length }}）</text>
      <view v-if="alarms.length" class="app-gap-12">
        <view v-for="row in alarms" :key="row.id" class="app-card">
          <view class="app-row">
            <text class="app-subtext">{{ row.description || "-" }}</text>
            <AppStatusTag :text="alarmStatusText(row)" :type="alarmStatusType(row)" />
          </view>
          <text class="app-subtext">告警ID：{{ row.id }}</text>
          <text class="app-subtext">时间：{{ formatAlarmTime(row) }}</text>
          <text class="app-subtext">设备：{{ row.device_id || "-" }}</text>
          <text class="app-subtext">通道：{{ row.channel_id || "-" }}</text>
          <text class="app-subtext">等级：{{ row.priority ?? "-" }}</text>
          <view class="app-row">
            <button size="mini" @click="openMap(row)">地图定位</button>
            <button size="mini" @click="openVisualCommand(row)">指挥追踪</button>
            <button size="mini" type="primary" :loading="ackingId === row.id" @click="ackAlarm(row)">确认</button>
          </view>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '报警加载中...' : '当前无待处理报警'" />
    </view>
  </view>
</template>
