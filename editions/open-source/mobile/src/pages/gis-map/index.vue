<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import {
  activateMapProvider,
  fetchDeviceLatestPosition,
  fetchLatestPositions,
  fetchMapConfig,
  fetchMapProviders,
  fetchTrajectory,
  saveMapConfig,
  subscribeMobilePosition,
  type DeviceLatestPosition,
  type MapProviderItem,
  type TrajectoryPoint
} from "@/api/map";
import { fetchDeviceChannels, type DeviceChannelItem } from "@/api/device";
import AppEmpty from "@/components/AppEmpty.vue";

const loading = ref(false);
const actionLoading = ref(false);
const positions = ref<DeviceLatestPosition[]>([]);
const providers = ref<MapProviderItem[]>([]);
const config = ref({
  profile_id: "",
  provider: "tianditu",
  api_key: "",
  center_lng: 116.404,
  center_lat: 39.915,
  zoom_level: 12,
  min_zoom: 1,
  max_zoom: 20,
  vector_tile_url: ""
});
const keyword = ref("");
const selectedDeviceId = ref("");
const selectedChannelId = ref("");
const channels = ref<DeviceChannelItem[]>([]);
const latestPosition = ref<DeviceLatestPosition | null>(null);
const trajectory = ref<TrajectoryPoint[]>([]);
const startTime = ref("");
const endTime = ref("");
const subscribeInterval = ref(60);
const loadMessage = ref("未刷新");
const loadAt = ref("");

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

const filteredPositions = computed(() => {
  if (!keyword.value) return positions.value;
  return positions.value.filter((x) => {
    const text = `${x.name || ""} ${x.gb_id || ""}`.toLowerCase();
    return text.includes(keyword.value.toLowerCase());
  });
});

const selectedProvider = computed(() => providers.value.find((x) => x.id === config.value.profile_id) || null);

const summaryText = computed(() => {
  return `GIS地图：点位=${filteredPositions.value.length}；地图方案=${providers.value.length}；当前方案=${selectedProvider.value?.name || config.value.provider || "-"}`;
});

const nextStepAdvice = computed(() => {
  if (filteredPositions.value.length <= 0) return "下一步建议：先确认设备已上报点位，再执行轨迹与订阅巡检。";
  if (!selectedDeviceId.value) return "下一步建议：先选择设备并刷新最新点位，再进行轨迹查询。";
  return "下一步建议：优先核对最新点位时间与轨迹跨度，必要时执行定位订阅。";
});

async function loadData() {
  loading.value = true;
  try {
    const [posRes, providerRes, cfgRes] = await Promise.allSettled([fetchLatestPositions(2000), fetchMapProviders(), fetchMapConfig()]);
    positions.value = posRes.status === "fulfilled" && Array.isArray(posRes.value) ? posRes.value : [];
    providers.value = providerRes.status === "fulfilled" && Array.isArray(providerRes.value?.items) ? providerRes.value.items : [];
    if (cfgRes.status === "fulfilled" && cfgRes.value) {
      config.value = {
        profile_id: String((cfgRes.value as any).id || ""),
        provider: String(cfgRes.value.provider || "tianditu"),
        api_key: String(cfgRes.value.api_key || ""),
        center_lng: Number(cfgRes.value.center_lng || 116.404),
        center_lat: Number(cfgRes.value.center_lat || 39.915),
        zoom_level: Number(cfgRes.value.zoom_level || 12),
        min_zoom: Number(cfgRes.value.min_zoom || 1),
        max_zoom: Number(cfgRes.value.max_zoom || 20),
        vector_tile_url: String(cfgRes.value.vector_tile_url || "")
      };
    }
    const failedCount = [posRes, providerRes, cfgRes].filter((x) => x.status === "rejected").length;
    if (failedCount > 0) {
      setLoadStatus(`部分刷新成功：失败 ${failedCount} 项`);
      uni.showToast({ title: `部分接口失败(${failedCount})`, icon: "none" });
    } else {
      setLoadStatus("刷新成功");
    }
  } catch (err: any) {
    positions.value = [];
    providers.value = [];
    setLoadStatus(err?.message ? `刷新失败：${err.message}` : "刷新失败");
    uni.showToast({ title: "GIS数据加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

async function chooseDevice(deviceId: string) {
  selectedDeviceId.value = deviceId;
  selectedChannelId.value = "";
  latestPosition.value = null;
  trajectory.value = [];
  actionLoading.value = true;
  try {
    const [latest, chRes] = await Promise.all([fetchDeviceLatestPosition(deviceId), fetchDeviceChannels(deviceId, 200)]);
    latestPosition.value = latest || null;
    channels.value = Array.isArray(chRes) ? chRes : [];
    if (channels.value.length) {
      selectedChannelId.value = channels.value[0].gb_id || channels.value[0].id || "";
    }
  } catch (err: any) {
    latestPosition.value = null;
    channels.value = [];
    uni.showToast({ title: err?.message ? `设备加载失败：${err.message}` : "设备加载失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function loadTrajectoryData() {
  if (!selectedDeviceId.value) {
    uni.showToast({ title: "请先选择设备", icon: "none" });
    return;
  }
  actionLoading.value = true;
  try {
    trajectory.value = await fetchTrajectory(selectedDeviceId.value, 1000, startTime.value || undefined, endTime.value || undefined);
    uni.showToast({ title: `轨迹点 ${trajectory.value.length} 条`, icon: "none" });
  } catch (err: any) {
    trajectory.value = [];
    uni.showToast({ title: err?.message ? `轨迹查询失败：${err.message}` : "轨迹查询失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function subscribePositionData() {
  if (!selectedDeviceId.value) {
    uni.showToast({ title: "请先选择设备", icon: "none" });
    return;
  }
  actionLoading.value = true;
  try {
    await subscribeMobilePosition(selectedDeviceId.value, Number(subscribeInterval.value || 60));
    uni.showToast({ title: "订阅已发送", icon: "none" });
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `订阅失败：${err.message}` : "订阅失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function applyProvider(providerId: string) {
  if (!providerId) return;
  actionLoading.value = true;
  try {
    await activateMapProvider(providerId);
    await loadData();
    uni.showToast({ title: "地图方案已激活", icon: "none" });
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `激活失败：${err.message}` : "激活失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function saveCurrentConfig() {
  actionLoading.value = true;
  try {
    await saveMapConfig({
      profile_id: config.value.profile_id || undefined,
      provider: config.value.provider,
      api_key: config.value.api_key,
      center_lng: Number(config.value.center_lng),
      center_lat: Number(config.value.center_lat),
      zoom_level: Number(config.value.zoom_level),
      min_zoom: Number(config.value.min_zoom),
      max_zoom: Number(config.value.max_zoom),
      vector_tile_url: config.value.vector_tile_url || undefined
    });
    await loadData();
    uni.showToast({ title: "配置已保存", icon: "none" });
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `保存失败：${err.message}` : "保存失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

function openPreview() {
  if (!selectedDeviceId.value || !selectedChannelId.value) {
    uni.showToast({ title: "请先选择设备与通道", icon: "none" });
    return;
  }
  uni.navigateTo({
    url: `/pages/preview/index?deviceId=${encodeURIComponent(selectedDeviceId.value)}&channelId=${encodeURIComponent(selectedChannelId.value)}`
  });
}

function copySummary() {
  const latestTime = latestPosition.value?.time || "-";
  const text = [
    summaryText.value,
    `设备=${selectedDeviceId.value || "-"}；通道=${selectedChannelId.value || "-"}；最新点位时间=${latestTime}`,
    `轨迹点=${trajectory.value.length}；订阅间隔=${subscribeInterval.value}s`,
    nextStepAdvice.value,
    `刷新状态=${loadMessage.value || "-"}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "GIS摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

onShow(loadData);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">GIS 地图</view>

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
      <text class="app-subtext">地图配置</text>
      <view class="app-row">
        <picker
          mode="selector"
          :range="providers.map((x) => `${x.name}${x.is_default ? '（默认）' : ''}`)"
          :value="Math.max(0, providers.findIndex((x) => x.id === config.profile_id))"
          @change="
            (e:any)=>{
              const i = Number(e?.detail?.value || 0);
              const row = providers[i];
              if (!row) return;
              config.profile_id = row.id;
              config.provider = row.provider;
              config.api_key = row.api_key || '';
              config.center_lng = Number(row.center_lng || 116.404);
              config.center_lat = Number(row.center_lat || 39.915);
              config.zoom_level = Number(row.zoom_level || 12);
              config.min_zoom = Number(row.min_zoom || 1);
              config.max_zoom = Number(row.max_zoom || 20);
              config.vector_tile_url = String(row.vector_tile_url || '');
            }
          "
        >
          <view class="app-subtext">方案：{{ selectedProvider?.name || "未选择" }}</view>
        </picker>
      </view>
      <input v-model="config.provider" class="app-input" placeholder="provider（tianditu/gaode/osm/vector）" />
      <input v-model="config.api_key" class="app-input" placeholder="api_key（可空）" />
      <input v-model.number="config.center_lng" type="number" class="app-input" placeholder="center_lng" />
      <input v-model.number="config.center_lat" type="number" class="app-input" placeholder="center_lat" />
      <input v-model.number="config.zoom_level" type="number" class="app-input" placeholder="zoom_level" />
      <view class="app-row">
        <button size="mini" :loading="actionLoading" :disabled="!config.profile_id" @click="applyProvider(config.profile_id)">设为默认</button>
        <button size="mini" :loading="actionLoading" @click="saveCurrentConfig">保存配置</button>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">设备点位</text>
      <input v-model="keyword" class="app-input" placeholder="搜索设备名称/国标ID" />
      <view v-if="filteredPositions.length" class="app-gap-12">
        <view v-for="row in filteredPositions.slice(0, 120)" :key="row.gb_id" class="app-card">
          <text class="app-subtext">{{ row.name || row.gb_id }}</text>
          <text class="app-subtext">ID：{{ row.gb_id }}；状态：{{ row.status === 1 ? "在线" : "离线" }}</text>
          <text class="app-subtext">坐标：{{ row.longitude ?? "-" }}, {{ row.latitude ?? "-" }}；时间：{{ row.time || "-" }}</text>
          <view class="app-row">
            <button size="mini" :loading="actionLoading" @click="chooseDevice(row.gb_id)">选中设备</button>
          </view>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '点位加载中...' : '暂无点位数据'" />
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">轨迹与联动（设备：{{ selectedDeviceId || "-" }}）</text>
      <text class="app-subtext">最新点位：{{ latestPosition?.longitude ?? "-" }}, {{ latestPosition?.latitude ?? "-" }} / {{ latestPosition?.time || "-" }}</text>
      <input v-model="startTime" class="app-input" placeholder="开始时间（ISO，可空）" />
      <input v-model="endTime" class="app-input" placeholder="结束时间（ISO，可空）" />
      <input v-model.number="subscribeInterval" type="number" class="app-input" placeholder="订阅间隔秒（默认60）" />
      <view class="app-row">
        <button size="mini" :loading="actionLoading" :disabled="!selectedDeviceId" @click="loadTrajectoryData">查询轨迹</button>
        <button size="mini" :loading="actionLoading" :disabled="!selectedDeviceId" @click="subscribePositionData">订阅定位</button>
      </view>
      <view class="app-row">
        <picker
          mode="selector"
          :range="channels.map((x) => `${x.name || x.gb_id || x.id}`)"
          :value="Math.max(0, channels.findIndex((x) => (x.gb_id || x.id) === selectedChannelId))"
          @change="
            (e:any)=>{
              const i = Number(e?.detail?.value || 0);
              const row = channels[i];
              if (!row) return;
              selectedChannelId = String(row.gb_id || row.id || '');
            }
          "
        >
          <view class="app-subtext">通道：{{ selectedChannelId || "未选择" }}</view>
        </picker>
        <button size="mini" :disabled="!selectedDeviceId || !selectedChannelId" @click="openPreview">进入预览页</button>
      </view>
      <text class="app-subtext">轨迹点：{{ trajectory.length }}</text>
      <view v-if="trajectory.length" class="app-gap-12">
        <view v-for="(row, idx) in trajectory.slice(0, 60)" :key="`traj-${idx}`" class="app-row">
          <text class="app-subtext">{{ row.time || "-" }} => {{ row.lng }}, {{ row.lat }}；速度={{ row.speed ?? "-" }}</text>
        </view>
      </view>
      <AppEmpty v-else :text="actionLoading ? '轨迹加载中...' : '暂无轨迹点'" />
    </view>
  </view>
</template>
