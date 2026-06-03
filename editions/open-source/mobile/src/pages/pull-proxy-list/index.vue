<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import {
  deleteProxySource,
  fetchAccessSources,
  fetchStreamSessions,
  previewSource,
  saveProxySource,
  setSourceDesiredState,
  setSourceEnabled,
  stopStream,
  testSource,
  type AccessSourceItem
} from "@/api/integration";
import AppEmpty from "@/components/AppEmpty.vue";
import AppStatusTag from "@/components/AppStatusTag.vue";

const loading = ref(false);
const saving = ref(false);
const actionLoading = ref(false);
const sources = ref<AccessSourceItem[]>([]);
const streams = ref<any[]>([]);
const keyword = ref("");
const protocolFilter = ref("");
const loadMessage = ref("未刷新");
const loadAt = ref("");

const editingId = ref("");
const formName = ref("");
const formProtocol = ref<"RTSP" | "ONVIF" | "SDK" | "RTMP" | "GB28181">("RTSP");
const formHost = ref("");
const formPort = ref(554);
const formUsername = ref("");
const formPassword = ref("");
const formPath = ref("");
const formStreamName = ref("");
const formEnabled = ref(true);

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

function normalizeStreamName(row: AccessSourceItem) {
  const raw = String(row.stream_name || row.name || row.id || "").replace(/\s+/g, "_");
  const normalized = raw
    .split("")
    .filter((ch) => /[0-9a-zA-Z_-]/.test(ch))
    .join("")
    .toLowerCase();
  return normalized || String(row.id || "");
}

const proxyStreamSet = computed(() => {
  const set = new Set<string>();
  for (const row of streams.value) {
    if (!row || !row.is_proxy || String(row.app || "") !== "live") continue;
    const stream = String(row.stream || "").trim();
    if (stream) set.add(stream);
  }
  return set;
});

function isRunning(row: AccessSourceItem) {
  return proxyStreamSet.value.has(normalizeStreamName(row));
}

function isRunningEffective(row: AccessSourceItem) {
  const value = row?.extra?.["runtime.proxy.is_running"];
  if (typeof value === "boolean") return value;
  if (String(value || "").toLowerCase() === "true") return true;
  if (String(value || "").toLowerCase() === "false") return false;
  return isRunning(row);
}

const protocolOptions = ["", "RTSP", "ONVIF", "SDK", "RTMP", "GB28181"];

const filteredSources = computed(() => {
  const q = keyword.value.trim().toLowerCase();
  const p = protocolFilter.value.trim().toUpperCase();
  return sources.value.filter((row) => {
    const protocol = String(row.protocol || "").toUpperCase();
    if (p && protocol !== p) return false;
    if (!q) return true;
    const text = `${row.name || ""} ${row.host || ""} ${row.path || ""} ${row.stream_name || ""}`.toLowerCase();
    return text.includes(q);
  });
});

const summaryText = computed(() => {
  return `拉流代理：总数=${sources.value.length}；筛选后=${filteredSources.value.length}；协议=${protocolFilter.value || "全部"}；关键词=${keyword.value.trim() || "无"}`;
});

const nextStepAdviceText = computed(() => {
  const running = sources.value.filter((x) => isRunningEffective(x)).length;
  if (sources.value.length <= 0) return "下一步建议：先新增接入源并验证连通性。";
  if (running <= 0) return "下一步建议：优先启动至少一路接入源，验证拉流链路。";
  return "下一步建议：持续关注异常接入源并检查期望状态是否生效。";
});

function resetForm() {
  editingId.value = "";
  formName.value = "";
  formProtocol.value = "RTSP";
  formHost.value = "";
  formPort.value = 554;
  formUsername.value = "";
  formPassword.value = "";
  formPath.value = "";
  formStreamName.value = "";
  formEnabled.value = true;
}

function editRow(row: AccessSourceItem) {
  editingId.value = String(row.id || "");
  formName.value = String(row.name || "");
  formProtocol.value = (String(row.protocol || "RTSP").toUpperCase() as any) || "RTSP";
  formHost.value = String(row.host || "");
  formPort.value = Number(row.port || 554);
  formUsername.value = String(row.username || "");
  formPassword.value = "";
  formPath.value = String(row.path || "");
  formStreamName.value = String(row.stream_name || "");
  formEnabled.value = row.enabled !== false;
}

async function loadAll() {
  loading.value = true;
  try {
    const [sourceRows, streamRows] = await Promise.all([fetchAccessSources(), fetchStreamSessions()]);
    sources.value = (Array.isArray(sourceRows) ? sourceRows : []).filter((row) =>
      ["RTSP", "ONVIF", "SDK", "RTMP", "GB28181"].includes(String(row.protocol || "").toUpperCase())
    );
    streams.value = Array.isArray(streamRows) ? streamRows : [];
    setLoadStatus(`刷新成功：接入源 ${sources.value.length} 条`);
  } catch (err: any) {
    sources.value = [];
    streams.value = [];
    setLoadStatus(err?.message ? `刷新失败：${err.message}` : "刷新失败");
    uni.showToast({ title: "接入源加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

async function saveSource() {
  const name = String(formName.value || "").trim();
  const host = String(formHost.value || "").trim();
  if (!name || !host) {
    uni.showToast({ title: "请先填写名称和主机", icon: "none" });
    return;
  }
  saving.value = true;
  try {
    await saveProxySource({
      id: editingId.value || undefined,
      name,
      protocol: String(formProtocol.value || "RTSP"),
      host,
      port: Number(formPort.value || 554),
      username: String(formUsername.value || "").trim() || undefined,
      password: String(formPassword.value || "").trim() || undefined,
      path: String(formPath.value || "").trim() || undefined,
      stream_name: String(formStreamName.value || "").trim() || undefined,
      enabled: !!formEnabled.value
    });
    uni.showToast({ title: editingId.value ? "接入源已更新" : "接入源已创建", icon: "none" });
    resetForm();
    await loadAll();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `保存失败：${err.message}` : "保存失败", icon: "none" });
  } finally {
    saving.value = false;
  }
}

async function previewRow(row: AccessSourceItem) {
  const id = String(row.id || "").trim();
  if (!id) return;
  actionLoading.value = true;
  try {
    const res = await previewSource(id);
    const url = String(res?.webrtc || res?.flv || res?.hls || "").trim();
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

async function runTest(row: AccessSourceItem) {
  const id = String(row.id || "").trim();
  if (!id) return;
  actionLoading.value = true;
  try {
    const res = await testSource(id);
    uni.showToast({ title: String(res?.message || "测试已完成"), icon: "none" });
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `测试失败：${err.message}` : "测试失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function setDesired(row: AccessSourceItem, state: "running" | "stopped", enforce = true) {
  const id = String(row.id || "").trim();
  if (!id) return;
  actionLoading.value = true;
  try {
    await setSourceDesiredState(id, state, enforce);
    uni.showToast({ title: state === "running" ? "已启动" : "已停止", icon: "none" });
    await loadAll();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `操作失败：${err.message}` : "操作失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function toggleEnabled(row: AccessSourceItem) {
  const id = String(row.id || "").trim();
  if (!id) return;
  const next = !(row.enabled !== false);
  actionLoading.value = true;
  try {
    await setSourceEnabled(id, next);
    uni.showToast({ title: next ? "已启用" : "已禁用", icon: "none" });
    await loadAll();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `操作失败：${err.message}` : "操作失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function removeSource(row: AccessSourceItem) {
  const id = String(row.id || "").trim();
  if (!id) return;
  uni.showModal({
    title: "确认删除",
    content: `确认删除接入源「${row.name || id}」？`,
    success: async (res) => {
      if (!res.confirm) return;
      actionLoading.value = true;
      try {
        await deleteProxySource(id);
        uni.showToast({ title: "接入源已删除", icon: "none" });
        await loadAll();
      } catch (err: any) {
        uni.showToast({ title: err?.message ? `删除失败：${err.message}` : "删除失败", icon: "none" });
      } finally {
        actionLoading.value = false;
      }
    }
  });
}

async function stopByStream(row: AccessSourceItem) {
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

function onProtocolChange(index: number) {
  protocolFilter.value = protocolOptions[index] || "";
}

function copySummary() {
  const text = [summaryText.value, nextStepAdviceText.value, `刷新状态：${loadMessage.value || "-"}`].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "拉流摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

onShow(loadAll);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">拉流代理</view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-subtext">{{ summaryText }}</text>
        <button size="mini" :loading="loading" @click="loadAll">刷新</button>
      </view>
      <input v-model="keyword" placeholder="搜索名称/地址/流名" />
      <picker mode="selector" :range="['全部协议', 'RTSP', 'ONVIF', 'SDK', 'RTMP', 'GB28181']" :value="Math.max(0, protocolOptions.findIndex((x)=>x===protocolFilter))" @change="(e:any)=>onProtocolChange(Number(e?.detail?.value || 0))">
        <view class="app-subtext">协议筛选：{{ protocolFilter || "全部" }}</view>
      </picker>
      <text class="app-subtext">{{ nextStepAdviceText }}</text>
      <text class="app-subtext">刷新状态：{{ loadMessage || "-" }}</text>
      <text class="app-subtext">状态时间：{{ loadAt || "-" }}</text>
      <view class="app-row">
        <button size="mini" @click="copySummary">复制拉流摘要</button>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">{{ editingId ? "编辑接入源" : "新增接入源" }}</text>
      <input v-model="formName" placeholder="名称" />
      <picker mode="selector" :range="['RTSP', 'ONVIF', 'SDK', 'RTMP', 'GB28181']" :value="['RTSP', 'ONVIF', 'SDK', 'RTMP', 'GB28181'].indexOf(formProtocol)" @change="(e:any)=>formProtocol=(['RTSP','ONVIF','SDK','RTMP','GB28181'][Number(e?.detail?.value || 0)] as any)">
        <view class="app-subtext">协议：{{ formProtocol }}</view>
      </picker>
      <view class="app-row">
        <input v-model="formHost" placeholder="主机" style="flex:1" />
        <input v-model="formPort" type="number" placeholder="端口" style="width:200rpx" />
      </view>
      <input v-model="formPath" placeholder="路径（可空）" />
      <view class="app-row">
        <input v-model="formUsername" placeholder="用户名（可空）" style="flex:1" />
        <input v-model="formPassword" password placeholder="密码（编辑时留空不改）" style="flex:1" />
      </view>
      <input v-model="formStreamName" placeholder="流名（可空，自动推导）" />
      <view class="app-row">
        <label class="app-subtext"><checkbox :checked="formEnabled" @click="formEnabled=!formEnabled" /> 启用</label>
      </view>
      <view class="app-row">
        <button size="mini" type="primary" :loading="saving" @click="saveSource">{{ editingId ? "更新接入源" : "创建接入源" }}</button>
        <button size="mini" @click="resetForm">清空表单</button>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <view v-if="filteredSources.length" class="app-gap-12">
        <view v-for="row in filteredSources" :key="row.id" class="app-row">
          <view style="flex:1">
            <text class="app-subtext">{{ row.name || row.id }}</text>
            <text class="app-subtext">协议：{{ row.protocol || "-" }} / 地址：{{ row.host || "-" }}:{{ row.port || 0 }}/{{ row.path || "" }}</text>
            <text class="app-subtext">流名：{{ row.stream_name || normalizeStreamName(row) }}</text>
            <text class="app-subtext">启用：{{ row.enabled !== false ? "是" : "否" }}</text>
          </view>
          <view class="app-gap-12">
            <AppStatusTag :text="isRunningEffective(row) ? '运行中' : '未运行'" :type="isRunningEffective(row) ? 'success' : 'info'" />
            <button size="mini" :loading="actionLoading" @click="editRow(row)">编辑</button>
            <button size="mini" :loading="actionLoading" @click="previewRow(row)">预览地址</button>
            <button size="mini" :loading="actionLoading" @click="runTest(row)">测试</button>
            <button size="mini" :loading="actionLoading" @click="setDesired(row, 'running', true)">启动</button>
            <button size="mini" :loading="actionLoading" @click="setDesired(row, 'stopped', true)">停止</button>
            <button size="mini" :loading="actionLoading" @click="toggleEnabled(row)">{{ row.enabled !== false ? "禁用" : "启用" }}</button>
            <button size="mini" :loading="actionLoading" @click="stopByStream(row)">停流</button>
            <button size="mini" :loading="actionLoading" @click="removeSource(row)">删除</button>
          </view>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '接入源加载中...' : '暂无接入源'" />
    </view>
  </view>
</template>
