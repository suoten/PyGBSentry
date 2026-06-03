<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import {
  createPushChannel,
  deletePushChannel,
  fetchPushChannels,
  fetchPushUrl,
  fetchStreamSessions,
  previewSource,
  rotatePushChannelKey,
  setSourceDesiredState,
  stopStream,
  updatePushChannel,
  type PushChannelItem,
  type StreamSessionItem
} from "@/api/integration";
import AppEmpty from "@/components/AppEmpty.vue";
import AppStatusTag from "@/components/AppStatusTag.vue";

const loading = ref(false);
const saving = ref(false);
const actionLoading = ref(false);
const channels = ref<PushChannelItem[]>([]);
const streams = ref<StreamSessionItem[]>([]);
const keyword = ref("");
const activeTab = ref<"channels" | "streams">("channels");
const loadMessage = ref("未刷新");
const loadAt = ref("");

const editingId = ref("");
const formName = ref("");
const formStreamName = ref("");
const formEnabled = ref(true);
const formPushKeyEnabled = ref(true);
const formGbEnabled = ref(false);
const formGbId = ref("");
const formGbName = ref("");

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

function normalizeStreamName(row: PushChannelItem) {
  const raw = String(row.stream_name || row.name || row.id || "").replace(/\s+/g, "_");
  const normalized = raw
    .split("")
    .filter((ch) => /[0-9a-zA-Z_-]/.test(ch))
    .join("")
    .toLowerCase();
  return normalized || String(row.id || "");
}

const runningStreamSet = computed(() => {
  const set = new Set<string>();
  for (const row of streams.value) {
    if (!row) continue;
    if (String(row.app || "") !== "live") continue;
    if (String(row.is_proxy || false) === "true") continue;
    const stream = String(row.stream || "").trim();
    if (stream) set.add(stream);
  }
  return set;
});

function isRunning(row: PushChannelItem) {
  return runningStreamSet.value.has(normalizeStreamName(row));
}

function isRunningEffective(row: PushChannelItem) {
  const value = row?.extra?.["runtime.rtmp.is_running"];
  if (typeof value === "boolean") return value;
  if (String(value || "").toLowerCase() === "true") return true;
  if (String(value || "").toLowerCase() === "false") return false;
  return isRunning(row);
}

const filteredChannels = computed(() => {
  const q = keyword.value.trim().toLowerCase();
  if (!q) return channels.value;
  return channels.value.filter((row) => {
    const name = String(row.name || "").toLowerCase();
    const stream = String(row.stream_name || "").toLowerCase();
    return name.includes(q) || stream.includes(q);
  });
});

const filteredStreams = computed(() => {
  const q = keyword.value.trim().toLowerCase();
  const rows = streams.value.filter((x) => !x.is_proxy);
  if (!q) return rows;
  return rows.filter((row) => {
    const app = String(row.app || "").toLowerCase();
    const stream = String(row.stream || "").toLowerCase();
    const origin = String(row.origin_url || "").toLowerCase();
    return app.includes(q) || stream.includes(q) || origin.includes(q);
  });
});

const summaryText = computed(() => {
  return `推流管理：通道=${channels.value.length}；会话=${filteredStreams.value.length}；当前视图=${activeTab.value === "channels" ? "通道" : "会话"}；关键词=${keyword.value.trim() || "无"}`;
});

const nextStepAdviceText = computed(() => {
  const runningCount = channels.value.filter((x) => isRunningEffective(x)).length;
  if (channels.value.length <= 0) return "下一步建议：先创建推流通道，再分批验证推流地址可用性。";
  if (runningCount <= 0) return "下一步建议：当前无运行中通道，优先发起推流并检查流会话。";
  return "下一步建议：优先检查异常或未运行通道，保持会话稳定性。";
});

function resetForm() {
  editingId.value = "";
  formName.value = "";
  formStreamName.value = "";
  formEnabled.value = true;
  formPushKeyEnabled.value = true;
  formGbEnabled.value = false;
  formGbId.value = "";
  formGbName.value = "";
}

function editRow(row: PushChannelItem) {
  editingId.value = String(row.id || "");
  formName.value = String(row.name || "");
  formStreamName.value = String(row.stream_name || "");
  formEnabled.value = row.enabled !== false;
  formPushKeyEnabled.value = row.push_key_enabled !== false;
  formGbEnabled.value = row.gb_enabled === true;
  formGbId.value = String(row.gb_id || "");
  formGbName.value = String(row.gb_name || "");
}

async function loadAll() {
  loading.value = true;
  try {
    const [channelRows, streamRows] = await Promise.all([fetchPushChannels(), fetchStreamSessions()]);
    channels.value = Array.isArray(channelRows) ? channelRows : [];
    streams.value = Array.isArray(streamRows) ? streamRows : [];
    setLoadStatus(`刷新成功：通道 ${channels.value.length} 条，会话 ${streams.value.length} 条`);
  } catch (err: any) {
    channels.value = [];
    streams.value = [];
    setLoadStatus(err?.message ? `刷新失败：${err.message}` : "刷新失败");
    uni.showToast({ title: "推流列表加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

async function saveChannel() {
  const name = String(formName.value || "").trim();
  if (!name) {
    uni.showToast({ title: "请先填写名称", icon: "none" });
    return;
  }
  saving.value = true;
  try {
    const payload = {
      name,
      stream_name: String(formStreamName.value || "").trim() || undefined,
      enabled: !!formEnabled.value,
      push_key_enabled: !!formPushKeyEnabled.value,
      gb_enabled: !!formGbEnabled.value,
      gb_id: formGbEnabled.value ? String(formGbId.value || "").trim() || undefined : undefined,
      gb_name: formGbEnabled.value ? String(formGbName.value || "").trim() || undefined : undefined
    };
    if (editingId.value) {
      await updatePushChannel(editingId.value, payload);
      uni.showToast({ title: "通道已更新", icon: "none" });
    } else {
      const res = await createPushChannel(payload);
      const key = String(res?.push_key || "").trim();
      if (key) {
        uni.setClipboardData({
          data: key,
          success: () => uni.showToast({ title: "创建成功，新密钥已复制", icon: "none" }),
          fail: () => uni.showToast({ title: "创建成功，请手动记录密钥", icon: "none" })
        });
      } else {
        uni.showToast({ title: "通道已创建", icon: "none" });
      }
    }
    resetForm();
    await loadAll();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `保存失败：${err.message}` : "保存失败", icon: "none" });
  } finally {
    saving.value = false;
  }
}

async function removeChannel(row: PushChannelItem) {
  const id = String(row.id || "").trim();
  if (!id) return;
  uni.showModal({
    title: "确认删除",
    content: `确认删除通道「${row.name || id}」？`,
    success: async (res) => {
      if (!res.confirm) return;
      actionLoading.value = true;
      try {
        await deletePushChannel(id);
        uni.showToast({ title: "通道已删除", icon: "none" });
        await loadAll();
      } catch (err: any) {
        uni.showToast({ title: err?.message ? `删除失败：${err.message}` : "删除失败", icon: "none" });
      } finally {
        actionLoading.value = false;
      }
    }
  });
}

async function copyPushUrl(row: PushChannelItem) {
  const id = String(row.id || "").trim();
  if (!id) return;
  actionLoading.value = true;
  try {
    const res = await fetchPushUrl(id);
    const url = String(res?.push_url || "").trim();
    if (!url) {
      uni.showToast({ title: "未获取到推流地址", icon: "none" });
      return;
    }
    uni.setClipboardData({
      data: url,
      success: () => uni.showToast({ title: "推流地址已复制", icon: "none" }),
      fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
    });
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `获取失败：${err.message}` : "获取失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function rotateKey(row: PushChannelItem) {
  const id = String(row.id || "").trim();
  if (!id) return;
  actionLoading.value = true;
  try {
    const res = await rotatePushChannelKey(id);
    const key = String(res?.push_key || "").trim();
    if (key) {
      uni.setClipboardData({
        data: key,
        success: () => uni.showToast({ title: "新密钥已复制", icon: "none" }),
        fail: () => uni.showToast({ title: "已重置，请手动记录", icon: "none" })
      });
    } else {
      uni.showToast({ title: "密钥已重置", icon: "none" });
    }
    await loadAll();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `重置失败：${err.message}` : "重置失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

function pickPreviewUrl(res: { webrtc?: string; flv?: string; hls?: string }) {
  return String(res.webrtc || res.flv || res.hls || "").trim();
}

async function previewRow(row: PushChannelItem) {
  const id = String(row.id || "").trim();
  if (!id) return;
  actionLoading.value = true;
  try {
    const res = await previewSource(id);
    const url = pickPreviewUrl(res);
    if (!url) {
      uni.showToast({ title: "未获取到预览地址", icon: "none" });
      return;
    }
    uni.setClipboardData({
      data: url,
      success: () => uni.showToast({ title: "预览地址已复制", icon: "none" }),
      fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
    });
    await loadAll();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `预览失败：${err.message}` : "预览失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function setDesiredState(row: PushChannelItem, state: "running" | "stopped", enforce = false) {
  const id = String(row.id || "").trim();
  if (!id) return;
  actionLoading.value = true;
  try {
    await setSourceDesiredState(id, state, enforce);
    uni.showToast({ title: state === "running" ? "已设为运行" : "已设为停止", icon: "none" });
    await loadAll();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `操作失败：${err.message}` : "操作失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function stopByStream(row: PushChannelItem) {
  const stream = normalizeStreamName(row);
  if (!stream) return;
  actionLoading.value = true;
  try {
    await stopStream("live", stream);
    uni.showToast({ title: "已发送停流", icon: "none" });
    await loadAll();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `停流失败：${err.message}` : "停流失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

function copySummary() {
  const text = [summaryText.value, nextStepAdviceText.value, `刷新状态：${loadMessage.value || "-"}`].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "推流摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function switchTab(index: number) {
  activeTab.value = index === 1 ? "streams" : "channels";
}

onShow(loadAll);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">推流列表</view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-subtext">{{ summaryText }}</text>
        <button size="mini" :loading="loading" @click="loadAll">刷新</button>
      </view>
      <input v-model="keyword" placeholder="搜索名称/流名/会话" />
      <picker mode="selector" :range="['推流通道', '流会话']" :value="activeTab === 'channels' ? 0 : 1" @change="(e:any)=>switchTab(Number(e?.detail?.value || 0))">
        <view class="app-subtext">当前视图：{{ activeTab === "channels" ? "推流通道" : "流会话" }}</view>
      </picker>
      <text class="app-subtext">{{ nextStepAdviceText }}</text>
      <text class="app-subtext">刷新状态：{{ loadMessage || "-" }}</text>
      <text class="app-subtext">状态时间：{{ loadAt || "-" }}</text>
      <view class="app-row">
        <button size="mini" @click="copySummary">复制推流摘要</button>
      </view>
    </view>

    <view v-if="activeTab === 'channels'" class="app-card app-gap-12">
      <text class="app-subtext">{{ editingId ? "编辑通道" : "新增通道" }}</text>
      <input v-model="formName" placeholder="通道名称" />
      <input v-model="formStreamName" placeholder="流名（可空，自动推导）" />
      <view class="app-row">
        <label class="app-subtext"><checkbox :checked="formEnabled" @click="formEnabled=!formEnabled" /> 启用</label>
        <label class="app-subtext"><checkbox :checked="formPushKeyEnabled" @click="formPushKeyEnabled=!formPushKeyEnabled" /> 推流密钥</label>
        <label class="app-subtext"><checkbox :checked="formGbEnabled" @click="formGbEnabled=!formGbEnabled" /> 入国标</label>
      </view>
      <input v-if="formGbEnabled" v-model="formGbId" placeholder="国标ID（20位）" />
      <input v-if="formGbEnabled" v-model="formGbName" placeholder="国标名称（可空）" />
      <view class="app-row">
        <button size="mini" type="primary" :loading="saving" @click="saveChannel">{{ editingId ? "更新通道" : "创建通道" }}</button>
        <button size="mini" @click="resetForm">清空表单</button>
      </view>
    </view>

    <view v-if="activeTab === 'channels'" class="app-card app-gap-12">
      <view v-if="filteredChannels.length" class="app-gap-12">
        <view v-for="row in filteredChannels" :key="row.id" class="app-row">
          <view style="flex:1">
            <text class="app-subtext">{{ row.name || row.id }}</text>
            <text class="app-subtext">流名：{{ row.stream_name || normalizeStreamName(row) }}</text>
            <text class="app-subtext">密钥：{{ row.push_key_enabled ? (row.push_key_hint || "已启用") : "未启用" }}</text>
            <text class="app-subtext">入国标：{{ row.gb_enabled ? `已启用(${row.gb_id || "-"})` : "未启用" }}</text>
          </view>
          <view class="app-gap-12">
            <AppStatusTag :text="isRunningEffective(row) ? '运行中' : '未运行'" :type="isRunningEffective(row) ? 'success' : 'info'" />
            <button size="mini" :loading="actionLoading" @click="editRow(row)">编辑</button>
            <button size="mini" :loading="actionLoading" @click="copyPushUrl(row)">推流地址</button>
            <button size="mini" :loading="actionLoading" @click="previewRow(row)">预览地址</button>
            <button size="mini" :loading="actionLoading" @click="rotateKey(row)">重置密钥</button>
            <button size="mini" :loading="actionLoading" @click="setDesiredState(row, 'running', false)">设为运行</button>
            <button size="mini" :loading="actionLoading" @click="setDesiredState(row, 'stopped', true)">设为停止</button>
            <button size="mini" :loading="actionLoading" @click="stopByStream(row)">停流</button>
            <button size="mini" :loading="actionLoading" @click="removeChannel(row)">删除</button>
          </view>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '推流通道加载中...' : '暂无推流通道'" />
    </view>

    <view v-if="activeTab === 'streams'" class="app-card app-gap-12">
      <view v-if="filteredStreams.length" class="app-gap-12">
        <view v-for="row in filteredStreams" :key="`${row.app}-${row.stream}`" class="app-row">
          <view style="flex:1">
            <text class="app-subtext">应用：{{ row.app || "-" }} / 流ID：{{ row.stream || "-" }}</text>
            <text class="app-subtext">观看数：{{ row.reader_count || 0 }} / 存活：{{ row.alive_second || 0 }}s / 速率：{{ row.bytes_speed || 0 }}B/s</text>
            <text class="app-subtext">源地址：{{ row.origin_url || "-" }}</text>
          </view>
          <button size="mini" :loading="actionLoading" @click="stopStream(String(row.app || 'live'), String(row.stream || ''))">停流</button>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '流会话加载中...' : '暂无流会话'" />
    </view>
  </view>
</template>
