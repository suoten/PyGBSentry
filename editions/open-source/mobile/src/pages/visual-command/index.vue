<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import {
  fetchLatestPositions,
  fetchTrajectory,
  fetchVisualCommandConfig,
  type DeviceLatestPosition,
  type TrajectoryPoint,
  type VisualCommandConfig
} from "@/api/map";
import { acknowledgeAlarm, fetchAlarms, type AlarmItem } from "@/api/alarm";
import AppEmpty from "@/components/AppEmpty.vue";
import AppStatusTag from "@/components/AppStatusTag.vue";

const loading = ref(false);
const trajectoryLoading = ref(false);
const positions = ref<DeviceLatestPosition[]>([]);
const trajectory = ref<TrajectoryPoint[]>([]);
const alarms = ref<AlarmItem[]>([]);
const alarmsTotal = ref(0);
const ackingAlarmId = ref("");
const selectedDeviceId = ref("");
const keyword = ref("");
const onlineOnly = ref(false);
const loadMessage = ref("未刷新");
const loadAt = ref("");
const config = ref<VisualCommandConfig>({
  enabled: true,
  alarm_blink_seconds: 5,
  trajectory_max_points: 50,
  message: ""
});

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

const filteredPositions = computed(() => {
  const key = String(keyword.value || "").trim().toLowerCase();
  return positions.value.filter((row) => {
    if (onlineOnly.value && Number(row.status || 0) !== 1) return false;
    if (!key) return true;
    const gb = String(row.gb_id || "").toLowerCase();
    const name = String(row.name || "").toLowerCase();
    return gb.includes(key) || name.includes(key);
  });
});

const markerRows = computed(() => {
  return filteredPositions.value
    .map((row, idx) => {
      const lng = Number(row.longitude || 0);
      const lat = Number(row.latitude || 0);
      if (!lng || !lat) return null;
      return {
        id: idx + 1,
        iconPath: "/static/logo.png",
        longitude: lng,
        latitude: lat,
        width: 22,
        height: 22,
        callout: {
          content: `${row.name || row.gb_id || "-"}`,
          display: "BYCLICK",
          color: "#111827",
          bgColor: "#ffffff",
          borderRadius: 6,
          padding: 6
        }
      };
    })
    .filter(Boolean) as Array<any>;
});

const mapCenter = computed(() => {
  const first = markerRows.value[0];
  if (first) return { longitude: first.longitude, latitude: first.latitude };
  return { longitude: 116.404, latitude: 39.915 };
});

const polyline = computed(() => {
  const points = trajectory.value
    .filter((x) => Number(x.lng || 0) && Number(x.lat || 0))
    .map((x) => ({
      longitude: Number(x.lng),
      latitude: Number(x.lat)
    }));
  if (!points.length) return [];
  return [
    {
      points,
      color: "#2563EB",
      width: 4,
      dottedLine: false
    }
  ];
});

const summaryText = computed(() => {
  return `可视化指挥：待处理告警=${alarmsTotal.value}；点位总数=${positions.value.length}；可展示点位=${markerRows.value.length}；轨迹点数=${trajectory.value.length}`;
});

const nextStepAdvice = computed(() => {
  if (alarms.value.length) return "下一步建议：优先确认高优告警并联动地图轨迹处置。";
  if (!markerRows.value.length) return "下一步建议：优先补齐设备经纬度，恢复地图点位展示能力。";
  if (!selectedDeviceId.value) return "下一步建议：点击设备加载轨迹并结合告警页执行联动处置。";
  return "下一步建议：围绕当前设备轨迹执行复盘，并联动工单闭环。";
});

async function loadBaseData() {
  loading.value = true;
  try {
    const [cfgRes, posRes, alarmRes] = await Promise.allSettled([
      fetchVisualCommandConfig(),
      fetchLatestPositions(2000),
      fetchAlarms({ skip: 0, limit: 20, escalation_state: "open" })
    ]);
    if (cfgRes.status === "fulfilled") config.value = cfgRes.value;
    positions.value = posRes.status === "fulfilled" && Array.isArray(posRes.value) ? posRes.value : [];
    alarms.value = alarmRes.status === "fulfilled" && Array.isArray(alarmRes.value.items) ? alarmRes.value.items : [];
    alarmsTotal.value = alarmRes.status === "fulfilled" ? Number(alarmRes.value.total || alarms.value.length || 0) : alarms.value.length;
    const failedCount = [cfgRes, posRes, alarmRes].filter((x) => x.status === "rejected").length;
    if (failedCount > 0) {
      setLoadStatus(`部分刷新成功：失败 ${failedCount} 项`);
    } else {
      setLoadStatus("刷新成功");
    }
  } catch (err: any) {
    positions.value = [];
    setLoadStatus(err?.message ? `刷新失败：${err.message}` : "刷新失败");
    uni.showToast({ title: "指挥数据加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

function openAlarmCenter() {
  uni.navigateTo({ url: "/pages/alarm/index" });
}

function openGisMap(alarm?: AlarmItem) {
  const deviceId = String(alarm?.device_id || "").trim();
  const channelId = String(alarm?.channel_id || "").trim();
  uni.navigateTo({
    url: `/pages/gis-map/index?device_id=${encodeURIComponent(deviceId)}&channel_id=${encodeURIComponent(channelId)}`
  });
}

function alarmStatusText(alarm: AlarmItem) {
  if (alarm.escalation_state === "acknowledged") return "已确认";
  return "待处理";
}

function alarmStatusType(alarm: AlarmItem): "success" | "warning" {
  if (alarm.escalation_state === "acknowledged") return "success";
  return "warning";
}

function alarmTimeText(alarm: AlarmItem) {
  return String(alarm.time || alarm.created_at || "-");
}

function openAlarmVisualCommand(alarm: AlarmItem) {
  const deviceId = String(alarm.device_id || "").trim();
  const channelId = String(alarm.channel_id || "").trim();
  if (deviceId) loadTrajectoryFor(deviceId);
  if (deviceId || channelId) {
    uni.showToast({ title: "已切到目标告警设备轨迹", icon: "none" });
  }
}

async function ackAlarm(alarm: AlarmItem) {
  const id = String(alarm.id || "").trim();
  if (!id) return;
  ackingAlarmId.value = id;
  try {
    await acknowledgeAlarm(id);
    uni.showToast({ title: "告警已确认", icon: "none" });
    await loadBaseData();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `确认失败：${err.message}` : "确认失败", icon: "none" });
  } finally {
    ackingAlarmId.value = "";
  }
}

async function loadTrajectoryFor(deviceId: string) {
  const id = String(deviceId || "").trim();
  if (!id) return;
  selectedDeviceId.value = id;
  trajectoryLoading.value = true;
  try {
    const points = await fetchTrajectory(id, Math.max(20, Number(config.value.trajectory_max_points || 50)));
    trajectory.value = Array.isArray(points) ? points : [];
  } catch (err: any) {
    trajectory.value = [];
    uni.showToast({ title: err?.message ? `轨迹加载失败：${err.message}` : "轨迹加载失败", icon: "none" });
  } finally {
    trajectoryLoading.value = false;
  }
}

function onMarkerTap(e: any) {
  const markerId = Number(e?.detail?.markerId || 0);
  if (!markerId) return;
  const target = markerRows.value.find((x) => Number(x.id) === markerId);
  if (!target) return;
  const row = filteredPositions.value[markerId - 1];
  if (!row?.gb_id) return;
  loadTrajectoryFor(String(row.gb_id));
}

function copySummary() {
  const text = [summaryText.value, nextStepAdvice.value, `刷新状态：${loadMessage.value || "-"}`].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "指挥摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

onShow(loadBaseData);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">可视化指挥</view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-subtext">{{ summaryText }}</text>
        <button size="mini" :loading="loading" @click="loadBaseData">刷新</button>
      </view>
      <text class="app-subtext">{{ config.message || "报警点位闪烁、轨迹追踪与视频联动配置" }}</text>
      <text class="app-subtext">{{ nextStepAdvice }}</text>
      <text class="app-subtext">刷新状态：{{ loadMessage || "-" }}</text>
      <text class="app-subtext">状态时间：{{ loadAt || "-" }}</text>
      <view class="app-row">
        <button size="mini" @click="copySummary">复制摘要</button>
        <button size="mini" @click="openAlarmCenter">告警中心</button>
        <button size="mini" @click="openGisMap()">电子地图</button>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">待处理告警快处置（{{ alarms.length }} / {{ alarmsTotal }}）</text>
      <view v-if="alarms.length" class="app-gap-12">
        <view v-for="row in alarms" :key="row.id" class="app-card">
          <view class="app-row">
            <text class="app-subtext">{{ row.description || "-" }}</text>
            <AppStatusTag :text="alarmStatusText(row)" :type="alarmStatusType(row)" />
          </view>
          <text class="app-subtext">告警ID：{{ row.id || "-" }}</text>
          <text class="app-subtext">时间：{{ alarmTimeText(row) }}</text>
          <text class="app-subtext">设备：{{ row.device_id || "-" }}；通道：{{ row.channel_id || "-" }}</text>
          <text class="app-subtext">优先级：{{ row.priority ?? "-" }}；升级级别：{{ row.escalation_level ?? "-" }}</text>
          <view class="app-row">
            <button size="mini" @click="openGisMap(row)">地图定位</button>
            <button size="mini" @click="openAlarmVisualCommand(row)">指挥追踪</button>
            <button size="mini" type="primary" :loading="ackingAlarmId === row.id" @click="ackAlarm(row)">确认告警</button>
          </view>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '告警加载中...' : '当前无待处理告警'" />
    </view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <input v-model="keyword" placeholder="按设备ID/名称筛选" />
        <label class="app-subtext"><checkbox :checked="onlineOnly" @click="onlineOnly = !onlineOnly" /> 仅在线</label>
      </view>
      <map
        style="width: 100%; height: 420rpx; border-radius: 12rpx; overflow: hidden"
        :longitude="mapCenter.longitude"
        :latitude="mapCenter.latitude"
        :scale="12"
        :markers="markerRows"
        :polyline="polyline"
        @markertap="onMarkerTap"
      />
      <text class="app-subtext">地图点位：{{ markerRows.length }}；当前轨迹设备：{{ selectedDeviceId || "-" }}；轨迹点：{{ trajectory.length }}</text>
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">设备点位列表：{{ filteredPositions.length }} 条</text>
      <view v-if="filteredPositions.length" class="app-gap-12">
        <view v-for="row in filteredPositions.slice(0, 80)" :key="row.gb_id" class="app-row">
          <view style="flex:1">
            <text class="app-subtext">{{ row.name || "-" }}（{{ row.gb_id || "-" }}）</text>
            <text class="app-subtext">坐标：{{ row.longitude || "-" }}, {{ row.latitude || "-" }}；速度：{{ row.speed || "-" }}</text>
          </view>
          <button size="mini" :loading="trajectoryLoading && selectedDeviceId === row.gb_id" @click="loadTrajectoryFor(String(row.gb_id || ''))">
            轨迹
          </button>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '点位加载中...' : '暂无设备点位'" />
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">轨迹明细：{{ trajectory.length }} 条</text>
      <view v-if="trajectory.length" class="app-gap-12">
        <view v-for="(row, idx) in trajectory.slice(0, 30)" :key="`t-${idx}`" class="app-row">
          <text class="app-subtext">{{ row.time || "-" }}</text>
          <text class="app-subtext">{{ row.lng }}, {{ row.lat }}</text>
        </view>
      </view>
      <AppEmpty v-else :text="trajectoryLoading ? '轨迹加载中...' : '请选择设备查看轨迹'" />
    </view>
  </view>
</template>
