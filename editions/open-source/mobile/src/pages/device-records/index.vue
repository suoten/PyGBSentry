<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import { fetchDeviceChannels, fetchDevices, type DeviceChannelItem, type DeviceItem } from "@/api/device";
import {
  fetchDeviceRecordDownloadProgress,
  fetchDeviceRecordQueryStatus,
  startDeviceRecordDownload,
  startDeviceRecordQuery,
  stopDeviceRecordDownload,
  type DeviceRecordRawItem
} from "@/api/record";
import AppEmpty from "@/components/AppEmpty.vue";

interface RecordRow {
  start_time: string;
  end_time: string;
  name: string;
  type: string;
  record_id: string;
}

const loadingDevice = ref(false);
const loadingChannel = ref(false);
const querying = ref(false);
const actionLoading = ref(false);
const devices = ref<DeviceItem[]>([]);
const channels = ref<DeviceChannelItem[]>([]);
const records = ref<RecordRow[]>([]);

const selectedDeviceId = ref("");
const selectedChannelId = ref("");
const startTimeInput = ref("");
const endTimeInput = ref("");
const queryId = ref("");
const queryStatus = ref("idle");
const completionRate = ref(0);
const queryProgressText = ref("未查询");
const queryAt = ref("");

const page = ref(1);
const pageSize = ref(20);
const downloadTaskId = ref("");
const downloadStatus = ref("");
const downloadPercent = ref(0);
const downloadMessage = ref("未发起下载");
const downloadReadyRows = ref<Array<{ record_id: string; download_url: string }>>([]);

function setQueryStatus(text: string) {
  queryProgressText.value = text;
  queryAt.value = new Date().toISOString();
}

function nowISO() {
  return new Date().toISOString();
}

function initWindow() {
  const end = new Date();
  const start = new Date(end.getTime() - 24 * 60 * 60 * 1000);
  startTimeInput.value = start.toISOString();
  endTimeInput.value = end.toISOString();
}

function normalizeDateInput(raw: string) {
  const text = String(raw || "").trim();
  if (!text) return "";
  const normalized = text.includes("T") ? text : text.replace(" ", "T");
  const d = new Date(normalized);
  if (Number.isNaN(d.getTime())) return "";
  return d.toISOString();
}

function normalizeRecordRow(item: DeviceRecordRawItem, index: number): RecordRow {
  const start =
    String(item.start_time || item.startTime || item.time_start || item.beginTime || item.begin_time || "").trim() || "-";
  const end =
    String(item.end_time || item.endTime || item.time_end || item.endTime || item.finish_time || "").trim() || "-";
  return {
    start_time: start,
    end_time: end,
    name: String(item.name || item.file_name || item.record_name || `录像片段${index + 1}`).trim(),
    type: String(item.type || item.record_type || "all").trim(),
    record_id: String(item.record_id || item.id || `${start}_${end}_${index}`).trim()
  };
}

const selectedDevice = computed(() => devices.value.find((x) => x.gb_id === selectedDeviceId.value));
const selectedChannel = computed(() => channels.value.find((x) => x.gb_id === selectedChannelId.value));

const pagedRecords = computed(() => {
  const start = (page.value - 1) * pageSize.value;
  return records.value.slice(start, start + pageSize.value);
});

const summaryText = computed(() => {
  const device = selectedDevice.value?.name || selectedDeviceId.value || "未选择";
  const channel = selectedChannel.value?.name || selectedChannelId.value || "未选择";
  return [
    `设备录像摘要：设备=${device}`,
    `通道=${channel}`,
    `时间窗=${startTimeInput.value || "-"} ~ ${endTimeInput.value || "-"}`,
    `总数=${records.value.length}`,
    `状态=${queryStatus.value || "idle"}`,
    `完成率=${Math.round(completionRate.value * 100)}%`
  ].join("；");
});

const nextStepAdvice = computed(() => {
  if (!selectedDeviceId.value || !selectedChannelId.value) return "下一步建议：先选择设备与通道，再执行录像查询。";
  if (records.value.length <= 0) return "下一步建议：放宽时间窗口或检查设备录像存储策略。";
  if (downloadReadyRows.value.length > 0) return "下一步建议：优先下载已就绪片段并抽样回放核验。";
  return "下一步建议：按时间顺序抽样检查录像片段，必要时发起下载固化证据。";
});

async function loadDevices() {
  loadingDevice.value = true;
  try {
    const res = await fetchDevices("");
    devices.value = Array.isArray(res?.items) ? res.items : [];
    if (!selectedDeviceId.value && devices.value.length > 0) {
      selectedDeviceId.value = String(devices.value[0].gb_id || "");
    }
    setQueryStatus(`设备加载成功：${devices.value.length} 台`);
  } catch (err: any) {
    devices.value = [];
    setQueryStatus(err?.message ? `设备加载失败：${err.message}` : "设备加载失败");
    uni.showToast({ title: "设备加载失败", icon: "none" });
  } finally {
    loadingDevice.value = false;
  }
}

async function loadChannels() {
  const deviceId = String(selectedDeviceId.value || "").trim();
  if (!deviceId) {
    channels.value = [];
    selectedChannelId.value = "";
    return;
  }
  loadingChannel.value = true;
  try {
    const rows = await fetchDeviceChannels(deviceId, 300);
    channels.value = Array.isArray(rows) ? rows : [];
    if (!channels.value.some((x) => x.gb_id === selectedChannelId.value)) {
      selectedChannelId.value = String(channels.value[0]?.gb_id || "");
    }
    setQueryStatus(`通道加载成功：${channels.value.length} 路`);
  } catch (err: any) {
    channels.value = [];
    selectedChannelId.value = "";
    setQueryStatus(err?.message ? `通道加载失败：${err.message}` : "通道加载失败");
    uni.showToast({ title: "通道加载失败", icon: "none" });
  } finally {
    loadingChannel.value = false;
  }
}

async function onDeviceChange(index: number) {
  selectedDeviceId.value = String(devices.value[index]?.gb_id || "");
  selectedChannelId.value = "";
  await loadChannels();
}

function onChannelChange(index: number) {
  selectedChannelId.value = String(channels.value[index]?.gb_id || "");
}

async function refreshQueryStatus() {
  const id = String(queryId.value || "").trim();
  if (!id) return;
  try {
    const res = await fetchDeviceRecordQueryStatus(id, 0, 2000);
    queryStatus.value = String(res?.status || "idle");
    completionRate.value = Number(res?.completion_rate || 0);
    const rows = Array.isArray(res?.items) ? res.items : [];
    records.value = rows.map((item, index) => normalizeRecordRow(item, index));
    setQueryStatus(
      `查询状态=${queryStatus.value}；回传=${Number(res?.received || 0)}/${Number(res?.sum_num || 0)}；片段=${records.value.length}`
    );
    if (queryStatus.value === "done" || queryStatus.value === "partial" || queryStatus.value === "timeout") {
      querying.value = false;
    }
  } catch (err: any) {
    setQueryStatus(err?.message ? `状态刷新失败：${err.message}` : "状态刷新失败");
    uni.showToast({ title: "查询状态刷新失败", icon: "none" });
  }
}

async function autoPollQuery(maxRound = 10) {
  for (let i = 0; i < maxRound; i += 1) {
    await refreshQueryStatus();
    if (!querying.value) return;
    await new Promise((resolve) => setTimeout(resolve, 1200));
  }
}

async function startQuery() {
  const deviceId = String(selectedDeviceId.value || "").trim();
  const channelId = String(selectedChannelId.value || "").trim();
  const start = normalizeDateInput(startTimeInput.value);
  const end = normalizeDateInput(endTimeInput.value);
  if (!deviceId || !channelId) {
    uni.showToast({ title: "请先选择设备与通道", icon: "none" });
    return;
  }
  if (!start || !end) {
    uni.showToast({ title: "请输入合法时间", icon: "none" });
    return;
  }
  querying.value = true;
  queryStatus.value = "pending";
  records.value = [];
  queryId.value = "";
  setQueryStatus("正在下发录像查询...");
  try {
    const res = await startDeviceRecordQuery({
      device_id: deviceId,
      channel_id: channelId,
      start_time: start,
      end_time: end,
      timeout_seconds: 20
    });
    queryId.value = String(res?.query_id || "");
    queryStatus.value = String(res?.status || "pending");
    completionRate.value = Number(res?.completion_rate || 0);
    setQueryStatus(`查询已下发：query_id=${queryId.value || "-"}；状态=${queryStatus.value}`);
    await autoPollQuery(12);
  } catch (err: any) {
    querying.value = false;
    queryStatus.value = "failed";
    setQueryStatus(err?.message ? `查询失败：${err.message}` : "查询失败");
    uni.showToast({ title: "录像查询失败", icon: "none" });
  }
}

async function startDownload(row: RecordRow) {
  const deviceId = String(selectedDeviceId.value || "").trim();
  const channelId = String(selectedChannelId.value || "").trim();
  const start = normalizeDateInput(row.start_time);
  const end = normalizeDateInput(row.end_time);
  if (!deviceId || !channelId || !start || !end) {
    uni.showToast({ title: "片段时间异常，无法下载", icon: "none" });
    return;
  }
  actionLoading.value = true;
  downloadReadyRows.value = [];
  try {
    const res = await startDeviceRecordDownload({
      device_id: deviceId,
      channel_id: channelId,
      start_time: start,
      end_time: end,
      download_speed: 4
    });
    downloadTaskId.value = String(res?.task_id || "");
    downloadStatus.value = String(res?.status || "pending");
    downloadPercent.value = 0;
    downloadMessage.value = `下载任务已创建：${downloadTaskId.value || "-"} (${downloadStatus.value})`;
    await refreshDownloadProgress();
  } catch (err: any) {
    downloadMessage.value = err?.message ? `下载创建失败：${err.message}` : "下载创建失败";
    uni.showToast({ title: "下载创建失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function refreshDownloadProgress() {
  const taskId = String(downloadTaskId.value || "").trim();
  if (!taskId) return;
  try {
    const res = await fetchDeviceRecordDownloadProgress(taskId);
    downloadStatus.value = String(res?.status || "");
    downloadPercent.value = Number(res?.percent || 0);
    downloadReadyRows.value = Array.isArray(res?.records) ? res.records : [];
    downloadMessage.value = `下载进度：${downloadStatus.value || "-"} ${downloadPercent.value}%（就绪=${downloadReadyRows.value.length}）`;
  } catch (err: any) {
    downloadMessage.value = err?.message ? `进度刷新失败：${err.message}` : "进度刷新失败";
    uni.showToast({ title: "下载进度刷新失败", icon: "none" });
  }
}

async function stopDownloadTask() {
  const taskId = String(downloadTaskId.value || "").trim();
  if (!taskId) return;
  actionLoading.value = true;
  try {
    await stopDeviceRecordDownload(taskId);
    await refreshDownloadProgress();
    uni.showToast({ title: "下载任务已停止", icon: "none" });
  } catch (err: any) {
    downloadMessage.value = err?.message ? `停止失败：${err.message}` : "停止失败";
    uni.showToast({ title: "停止下载失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

function copySummary() {
  const text = [summaryText.value, nextStepAdvice.value, `查询状态：${queryProgressText.value}`, `下载状态：${downloadMessage.value}`].join(
    "；"
  );
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "录像摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyDownloadUrl(row: { record_id: string; download_url: string }) {
  const url = String(row.download_url || "").trim();
  if (!url) return;
  const fullUrl = url.startsWith("http://") || url.startsWith("https://") ? url : url;
  uni.setClipboardData({
    data: fullUrl,
    success: () => uni.showToast({ title: "下载链接已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

async function prevPage() {
  if (page.value <= 1) return;
  page.value -= 1;
}

async function nextPage() {
  const maxPage = Math.max(1, Math.ceil(records.value.length / pageSize.value));
  if (page.value >= maxPage) return;
  page.value += 1;
}

async function resetWindow() {
  initWindow();
  setQueryStatus(`时间窗已重置：${nowISO()}`);
}

async function initPage() {
  if (!startTimeInput.value || !endTimeInput.value) initWindow();
  await loadDevices();
  await loadChannels();
}

onShow(initPage);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">设备录像</view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-subtext">{{ summaryText }}</text>
        <button size="mini" :loading="loadingDevice || loadingChannel" @click="initPage">刷新设备</button>
      </view>
      <picker
        mode="selector"
        :range="devices.map((x) => `${x.name || x.gb_id} (${x.gb_id})`)"
        :value="Math.max(0, devices.findIndex((x) => x.gb_id === selectedDeviceId))"
        @change="(e:any)=>onDeviceChange(Number(e?.detail?.value || 0))"
      >
        <view class="app-subtext">设备：{{ selectedDevice?.name || selectedDeviceId || "请选择设备" }}</view>
      </picker>
      <picker
        mode="selector"
        :range="channels.map((x) => `${x.name || x.gb_id} (${x.gb_id})`)"
        :value="Math.max(0, channels.findIndex((x) => x.gb_id === selectedChannelId))"
        @change="(e:any)=>onChannelChange(Number(e?.detail?.value || 0))"
      >
        <view class="app-subtext">通道：{{ selectedChannel?.name || selectedChannelId || "请选择通道" }}</view>
      </picker>
      <input v-model="startTimeInput" placeholder="开始时间（ISO 或 YYYY-MM-DD HH:mm:ss）" />
      <input v-model="endTimeInput" placeholder="结束时间（ISO 或 YYYY-MM-DD HH:mm:ss）" />
      <view class="app-row">
        <button size="mini" type="primary" :loading="querying" @click="startQuery">查询录像</button>
        <button size="mini" :loading="querying" @click="refreshQueryStatus">刷新查询状态</button>
        <button size="mini" @click="resetWindow">重置时间窗</button>
      </view>
      <text class="app-subtext">查询状态：{{ queryProgressText }}</text>
      <text class="app-subtext">状态时间：{{ queryAt || "-" }}</text>
      <text class="app-subtext">{{ nextStepAdvice }}</text>
      <view class="app-row">
        <button size="mini" @click="copySummary">复制录像摘要</button>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-subtext">下载状态：{{ downloadMessage }}</text>
        <button size="mini" :loading="actionLoading" @click="refreshDownloadProgress">刷新下载进度</button>
      </view>
      <view class="app-row">
        <button
          size="mini"
          :loading="actionLoading"
          :disabled="!downloadTaskId || downloadStatus === 'done' || downloadStatus === 'failed' || downloadStatus === 'cancelled'"
          @click="stopDownloadTask"
        >
          停止下载任务
        </button>
        <text class="app-subtext">任务ID：{{ downloadTaskId || "-" }} / 进度：{{ downloadPercent }}%</text>
      </view>
      <view v-if="downloadReadyRows.length" class="app-gap-12">
        <view v-for="row in downloadReadyRows" :key="row.record_id" class="app-row">
          <text class="app-subtext" style="flex:1">可下载片段：{{ row.record_id }}</text>
          <button size="mini" @click="copyDownloadUrl(row)">复制下载链接</button>
        </view>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-subtext">录像片段：{{ records.length }} 条</text>
        <view class="app-row">
          <button size="mini" :disabled="page <= 1" @click="prevPage">上一页</button>
          <button size="mini" :disabled="page >= Math.max(1, Math.ceil(records.length / pageSize))" @click="nextPage">下一页</button>
        </view>
      </view>
      <text class="app-subtext">第 {{ page }} / {{ Math.max(1, Math.ceil(records.length / pageSize)) }} 页（每页 {{ pageSize }} 条）</text>
      <view v-if="pagedRecords.length" class="app-gap-12">
        <view v-for="row in pagedRecords" :key="row.record_id" class="app-row">
          <view style="flex:1">
            <text class="app-subtext">{{ row.name || row.record_id }}</text>
            <text class="app-subtext">开始：{{ row.start_time || "-" }}</text>
            <text class="app-subtext">结束：{{ row.end_time || "-" }}</text>
            <text class="app-subtext">类型：{{ row.type || "-" }}</text>
          </view>
          <button size="mini" type="primary" :loading="actionLoading" @click="startDownload(row)">下载片段</button>
        </view>
      </view>
      <AppEmpty v-else :text="querying ? '录像查询中...' : '当前条件下暂无录像片段'" />
    </view>
  </view>
</template>
