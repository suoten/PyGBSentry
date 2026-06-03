<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import { searchStructuredEvents, type StructuredEventItem } from "@/api/structured";
import AppEmpty from "@/components/AppEmpty.vue";
import AppStatusTag from "@/components/AppStatusTag.vue";

const loading = ref(false);
const eventType = ref("");
const deviceId = ref("");
const channelId = ref("");
const startTime = ref("");
const endTime = ref("");
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);
const items = ref<StructuredEventItem[]>([]);
const selected = ref<StructuredEventItem | null>(null);
const loadMessage = ref("未刷新");
const loadAt = ref("");
const selectedPreset = ref("");
const PRESET_KEY = "pgbsentry_mobile_structured_search_presets_v1";
const presets = ref<Array<{ name: string; event_type: string; device_id: string; channel_id: string }>>([]);

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

const pageCount = computed(() => {
  if (pageSize.value <= 0) return 1;
  return Math.max(1, Math.ceil(Number(total.value || 0) / pageSize.value));
});

const summaryText = computed(() => {
  return `结构化事件：总数=${total.value}；当前页=${page.value}/${pageCount.value}；当前页条数=${items.value.length}；筛选类型=${eventType.value || "all"}`;
});

const nextStepAdvice = computed(() => {
  if (items.value.length <= 0) return "下一步建议：放宽筛选条件或切换到近7天重试检索。";
  const behavior = items.value.filter((x) => String(x.event_type || "") === "behavior").length;
  if (behavior > 0) return "下一步建议：优先复核行为事件并联动地图或录像回放。";
  return "下一步建议：按设备与通道聚类复盘事件高发点位。";
});

function formatTime(value?: string) {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString();
}

function payloadText(row: StructuredEventItem) {
  if (typeof row.payload === "string") return row.payload;
  try {
    return JSON.stringify(row.payload ?? {}, null, 2);
  } catch {
    return String(row.payload ?? "");
  }
}

function loadPresets() {
  try {
    const raw = uni.getStorageSync(PRESET_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    presets.value = Array.isArray(parsed) ? parsed.filter((x) => x && x.name) : [];
  } catch {
    presets.value = [];
  }
}

function savePresets() {
  uni.setStorageSync(PRESET_KEY, JSON.stringify(presets.value));
}

function applyPresetByName(name: string) {
  const hit = presets.value.find((x) => x.name === name);
  if (!hit) return;
  eventType.value = hit.event_type || "";
  deviceId.value = hit.device_id || "";
  channelId.value = hit.channel_id || "";
  page.value = 1;
  loadData();
}

function saveCurrentPreset() {
  uni.showModal({
    title: "保存预设",
    content: "是否保存当前筛选为新预设？",
    success: (res) => {
      if (!res.confirm) return;
      const name = `${eventType.value || "all"}-${deviceId.value || "device"}-${Date.now()}`;
      const entry = {
        name,
        event_type: eventType.value || "",
        device_id: deviceId.value || "",
        channel_id: channelId.value || ""
      };
      presets.value = [entry, ...presets.value.filter((x) => x.name !== name)].slice(0, 20);
      selectedPreset.value = name;
      savePresets();
      uni.showToast({ title: "预设已保存", icon: "none" });
    }
  });
}

function removePreset() {
  if (!selectedPreset.value) return;
  presets.value = presets.value.filter((x) => x.name !== selectedPreset.value);
  selectedPreset.value = "";
  savePresets();
  uni.showToast({ title: "预设已删除", icon: "none" });
}

function applyQuickPreset(kind: "24h" | "7d") {
  const end = new Date();
  const start = new Date(end);
  if (kind === "24h") start.setHours(start.getHours() - 24);
  else start.setDate(start.getDate() - 7);
  const fmt = (d: Date) => {
    const p = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
  };
  startTime.value = fmt(start);
  endTime.value = fmt(end);
  page.value = 1;
  loadData();
}

async function loadData() {
  loading.value = true;
  try {
    const res = await searchStructuredEvents({
      event_type: eventType.value || undefined,
      device_id: deviceId.value || undefined,
      channel_id: channelId.value || undefined,
      start_time: startTime.value || undefined,
      end_time: endTime.value || undefined,
      skip: (page.value - 1) * pageSize.value,
      limit: pageSize.value
    });
    items.value = Array.isArray(res.items) ? res.items : [];
    total.value = Number(res.total || 0);
    setLoadStatus("刷新成功");
  } catch (err: any) {
    items.value = [];
    total.value = 0;
    setLoadStatus(err?.message ? `刷新失败：${err.message}` : "刷新失败");
    uni.showToast({ title: "结构化事件检索失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

function doSearch() {
  page.value = 1;
  loadData();
}

function resetFilters() {
  eventType.value = "";
  deviceId.value = "";
  channelId.value = "";
  startTime.value = "";
  endTime.value = "";
  page.value = 1;
  loadData();
}

function prevPage() {
  if (page.value <= 1) return;
  page.value -= 1;
  loadData();
}

function nextPage() {
  if (page.value >= pageCount.value) return;
  page.value += 1;
  loadData();
}

function goMap(row: StructuredEventItem) {
  uni.navigateTo({
    url: `/pages/gis-map/index?device_id=${encodeURIComponent(String(row.device_id || ""))}&channel_id=${encodeURIComponent(String(row.channel_id || ""))}`
  });
}

function goAlarms(row: StructuredEventItem) {
  uni.navigateTo({
    url: `/pages/alarm/index?device_id=${encodeURIComponent(String(row.device_id || ""))}&channel_id=${encodeURIComponent(String(row.channel_id || ""))}`
  });
}

function goRecords(row: StructuredEventItem) {
  uni.navigateTo({
    url: `/pages/device-records/index?device_id=${encodeURIComponent(String(row.device_id || ""))}&channel_id=${encodeURIComponent(String(row.channel_id || ""))}&start_time=${encodeURIComponent(startTime.value || "")}&end_time=${encodeURIComponent(endTime.value || "")}`
  });
}

function exportCurrentCsv() {
  if (!items.value.length) {
    uni.showToast({ title: "当前页无可导出数据", icon: "none" });
    return;
  }
  const header = ["event_type", "source_plugin", "device_id", "channel_id", "event_time", "payload"];
  const escapeCsv = (val: string) => {
    const text = String(val || "");
    if (text.includes(",") || text.includes("\"") || text.includes("\n")) return `"${text.replace(/"/g, "\"\"")}"`;
    return text;
  };
  const body = items.value.map((row) =>
    [
      row.event_type || "",
      row.source_plugin || "",
      row.device_id || "",
      row.channel_id || "",
      row.event_time || "",
      payloadText(row)
    ]
      .map((x) => escapeCsv(String(x)))
      .join(",")
  );
  const csv = [header.join(","), ...body].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => uni.showToast({ title: "CSV已复制到剪贴板", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copySummary() {
  const text = [
    summaryText.value,
    `筛选=device:${deviceId.value || "-"},channel:${channelId.value || "-"},time:${startTime.value || "-"}~${endTime.value || "-"}`,
    nextStepAdvice.value,
    `刷新状态=${loadMessage.value || "-"}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "结构化摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

onShow(() => {
  loadPresets();
  loadData();
});
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">结构化事件中心</view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">检索条件</text>
      <picker mode="selector" :range="['全部类型', '人脸(face)', '车牌(plate)', '行为(behavior)']" :value="eventType === 'face' ? 1 : eventType === 'plate' ? 2 : eventType === 'behavior' ? 3 : 0" @change="(e:any) => { const i=Number(e?.detail?.value||0); eventType = i===1 ? 'face' : i===2 ? 'plate' : i===3 ? 'behavior' : ''; }">
        <view class="app-subtext">事件类型：{{ eventType || "全部" }}</view>
      </picker>
      <input v-model="deviceId" class="app-input" placeholder="设备ID" />
      <input v-model="channelId" class="app-input" placeholder="通道ID" />
      <input v-model="startTime" class="app-input" placeholder="开始时间（ISO）" />
      <input v-model="endTime" class="app-input" placeholder="结束时间（ISO）" />
      <view class="app-row">
        <button size="mini" :loading="loading" @click="doSearch">检索</button>
        <button size="mini" @click="resetFilters">重置</button>
        <button size="mini" @click="applyQuickPreset('24h')">近24小时</button>
        <button size="mini" @click="applyQuickPreset('7d')">近7天</button>
      </view>
      <view class="app-row">
        <picker mode="selector" :range="['未选择预设', ...presets.map((x) => x.name)]" :value="Math.max(0, presets.findIndex((x) => x.name === selectedPreset) + 1)" @change="(e:any) => { const i = Number(e?.detail?.value || 0); selectedPreset = i <= 0 ? '' : String(presets[i - 1]?.name || ''); if (selectedPreset) applyPresetByName(selectedPreset); }">
          <view class="app-subtext">查询预设：{{ selectedPreset || "未选择" }}</view>
        </picker>
      </view>
      <view class="app-row">
        <button size="mini" @click="saveCurrentPreset">保存预设</button>
        <button size="mini" :disabled="!selectedPreset" @click="removePreset">删除预设</button>
      </view>
    </view>

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
        <button size="mini" :disabled="!items.length" @click="exportCurrentCsv">导出当前页CSV</button>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">事件列表（{{ total }}）</text>
      <view v-if="items.length" class="app-gap-12">
        <view v-for="row in items" :key="row.id" class="app-card">
          <view class="app-row">
            <text class="app-subtext">{{ row.event_type || "-" }} / {{ row.source_plugin || "-" }}</text>
            <AppStatusTag :text="row.event_type || 'unknown'" :type="row.event_type === 'behavior' ? 'warning' : row.event_type === 'plate' ? 'success' : 'info'" />
          </view>
          <text class="app-subtext">设备：{{ row.device_id || "-" }}；通道：{{ row.channel_id || "-" }}</text>
          <text class="app-subtext">时间：{{ formatTime(row.event_time) }}</text>
          <text class="app-subtext">内容：{{ payloadText(row).slice(0, 160) }}</text>
          <view class="app-row">
            <button
              size="mini"
              @click="
                selected = row;
              "
            >
              详情
            </button>
            <button size="mini" @click="goMap(row)">地图联动</button>
            <button size="mini" @click="goAlarms(row)">告警中心</button>
            <button size="mini" @click="goRecords(row)">录像回放</button>
          </view>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '事件加载中...' : '暂无匹配事件'" />
      <view class="app-row">
        <button size="mini" :disabled="page <= 1 || loading" @click="prevPage">上一页</button>
        <text class="app-subtext">第 {{ page }} / {{ pageCount }} 页</text>
        <button size="mini" :disabled="page >= pageCount || loading" @click="nextPage">下一页</button>
      </view>
    </view>

    <view v-if="selected" class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-subtext">事件详情</text>
        <button
          size="mini"
          @click="
            selected = null;
          "
        >
          关闭
        </button>
      </view>
      <text class="app-subtext">ID：{{ selected.id }}</text>
      <text class="app-subtext">类型：{{ selected.event_type || "-" }}</text>
      <text class="app-subtext">来源：{{ selected.source_plugin || "-" }}</text>
      <text class="app-subtext">设备/通道：{{ selected.device_id || "-" }} / {{ selected.channel_id || "-" }}</text>
      <text class="app-subtext">时间：{{ formatTime(selected.event_time) }}</text>
      <textarea :value="payloadText(selected)" class="app-input" :maxlength="-1" disabled auto-height />
    </view>
  </view>
</template>
