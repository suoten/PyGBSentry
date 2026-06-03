<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import { fetchChannelsFlat, type ChannelFlatItem } from "@/api/device";
import {
  deleteCloudRecord,
  deleteCloudRecordBatch,
  getRecordDownloadSignedUrl,
  repairCloudRecordUrl,
  repairCloudRecordUrlBatch,
  searchCloudRecords,
  verifyCloudRecord,
  verifyCloudRecordBatch,
  type CloudRecordItem
} from "@/api/record";
import AppEmpty from "@/components/AppEmpty.vue";
import AppStatusTag from "@/components/AppStatusTag.vue";

const loading = ref(false);
const actionLoading = ref(false);
const channels = ref<ChannelFlatItem[]>([]);
const rows = ref<CloudRecordItem[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(50);
const selectedChannelGbId = ref("");
const startTime = ref("");
const endTime = ref("");
const onlyBad = ref(false);
const selectedIds = ref<string[]>([]);
const loadMessage = ref("未刷新");
const loadAt = ref("");

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

function initWindow() {
  const end = new Date();
  const start = new Date(end.getTime() - 24 * 60 * 60 * 1000);
  startTime.value = start.toISOString();
  endTime.value = end.toISOString();
}

const filteredRows = computed(() => {
  if (!onlyBad.value) return rows.value;
  return rows.value.filter((x) => x.url_ok === false);
});

const selectedIdSet = computed(() => new Set(selectedIds.value));

const summaryText = computed(() => {
  return `云端录像：总数=${total.value}；当前页=${rows.value.length}；筛选后=${filteredRows.value.length}；通道=${selectedChannelGbId.value || "全部"}；仅异常=${onlyBad.value ? "是" : "否"}`;
});

const nextStepAdvice = computed(() => {
  const bad = filteredRows.value.filter((x) => x.url_ok === false).length;
  if (rows.value.length <= 0) return "下一步建议：放宽时间窗口或检查录像写入链路。";
  if (bad > 0) return "下一步建议：优先批量校验与修复异常录像链接。";
  return "下一步建议：当前页面无明显异常，可抽样下载验证可用性。";
});

function toggleSelect(id: string) {
  const value = String(id || "").trim();
  if (!value) return;
  if (selectedIdSet.value.has(value)) {
    selectedIds.value = selectedIds.value.filter((x) => x !== value);
  } else {
    selectedIds.value = [...selectedIds.value, value];
  }
}

const badSelectedIds = computed(() => {
  const set = selectedIdSet.value;
  return rows.value.filter((x) => set.has(String(x.id || "")) && x.url_ok === false).map((x) => String(x.id || ""));
});

async function loadChannels() {
  try {
    const res = await fetchChannelsFlat({ skip: 0, limit: 500, placement: "business" });
    channels.value = Array.isArray(res?.items) ? res.items : [];
  } catch {
    channels.value = [];
  }
}

async function search() {
  loading.value = true;
  try {
    const res = await searchCloudRecords({
      start_time: startTime.value || undefined,
      end_time: endTime.value || undefined,
      channel_id: selectedChannelGbId.value || undefined,
      skip: (page.value - 1) * pageSize.value,
      limit: pageSize.value
    });
    rows.value = Array.isArray(res?.items) ? res.items : [];
    total.value = Number(res?.total || 0);
    selectedIds.value = [];
    setLoadStatus(`查询成功：${rows.value.length} 条`);
  } catch (err: any) {
    rows.value = [];
    total.value = 0;
    setLoadStatus(err?.message ? `查询失败：${err.message}` : "查询失败");
    uni.showToast({ title: "云端录像查询失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

async function onChannelChange(index: number) {
  if (index <= 0) selectedChannelGbId.value = "";
  else selectedChannelGbId.value = String(channels.value[index - 1]?.gb_id || "");
  page.value = 1;
  await search();
}

async function prevPage() {
  if (page.value <= 1) return;
  page.value -= 1;
  await search();
}

async function nextPage() {
  const maxPage = Math.max(1, Math.ceil(total.value / pageSize.value));
  if (page.value >= maxPage) return;
  page.value += 1;
  await search();
}

async function copySignedDownloadUrl(recordId: string, inline = false) {
  const id = String(recordId || "").trim();
  if (!id) return;
  actionLoading.value = true;
  try {
    const res = await getRecordDownloadSignedUrl(id, inline, 300);
    const url = String(res?.signed_url || res?.url || "").trim();
    if (!url) {
      uni.showToast({ title: "未获取到下载链接", icon: "none" });
      return;
    }
    uni.setClipboardData({
      data: url,
      success: () => uni.showToast({ title: "下载链接已复制", icon: "none" }),
      fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
    });
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `获取失败：${err.message}` : "获取失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function verifyOne(recordId: string) {
  const id = String(recordId || "").trim();
  if (!id) return;
  actionLoading.value = true;
  try {
    const res = await verifyCloudRecord(id);
    uni.showToast({ title: res?.ok ? "校验通过" : "校验失败", icon: "none" });
    await search();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `校验失败：${err.message}` : "校验失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function repairOne(recordId: string) {
  const id = String(recordId || "").trim();
  if (!id) return;
  actionLoading.value = true;
  try {
    const res = await repairCloudRecordUrl(id);
    const nextUrl = String(res?.new || "").trim();
    if (nextUrl) {
      uni.setClipboardData({
        data: nextUrl,
        success: () => uni.showToast({ title: "修复成功，新链接已复制", icon: "none" }),
        fail: () => uni.showToast({ title: "修复成功", icon: "none" })
      });
    } else {
      uni.showToast({ title: "修复成功", icon: "none" });
    }
    await search();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `修复失败：${err.message}` : "修复失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function removeOne(recordId: string) {
  const id = String(recordId || "").trim();
  if (!id) return;
  uni.showModal({
    title: "确认删除",
    content: "确认删除该录像索引？不会删除实际文件。",
    success: async (res) => {
      if (!res.confirm) return;
      actionLoading.value = true;
      try {
        await deleteCloudRecord(id);
        uni.showToast({ title: "索引已删除", icon: "none" });
        await search();
      } catch (err: any) {
        uni.showToast({ title: err?.message ? `删除失败：${err.message}` : "删除失败", icon: "none" });
      } finally {
        actionLoading.value = false;
      }
    }
  });
}

async function verifyBatch() {
  const ids = selectedIds.value.slice(0, 200);
  if (!ids.length) {
    uni.showToast({ title: "请先选择记录", icon: "none" });
    return;
  }
  actionLoading.value = true;
  try {
    const res = await verifyCloudRecordBatch(ids);
    uni.showToast({ title: `校验完成：成功${res.ok} 失败${res.failed}`, icon: "none" });
    await search();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `批量校验失败：${err.message}` : "批量校验失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function repairBatch() {
  const ids = selectedIds.value.slice(0, 200);
  if (!ids.length) {
    uni.showToast({ title: "请先选择记录", icon: "none" });
    return;
  }
  actionLoading.value = true;
  try {
    const res = await repairCloudRecordUrlBatch(ids);
    uni.showToast({ title: `批量修复完成：${res.repaired}`, icon: "none" });
    await search();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `批量修复失败：${err.message}` : "批量修复失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function removeBadBatch() {
  const ids = badSelectedIds.value.slice(0, 500);
  if (!ids.length) {
    uni.showToast({ title: "未选中异常记录", icon: "none" });
    return;
  }
  uni.showModal({
    title: "确认批量删除",
    content: `确认删除 ${ids.length} 条异常索引？`,
    success: async (res) => {
      if (!res.confirm) return;
      actionLoading.value = true;
      try {
        const out = await deleteCloudRecordBatch(ids);
        uni.showToast({ title: `已删除 ${out.deleted} 条`, icon: "none" });
        await search();
      } catch (err: any) {
        uni.showToast({ title: err?.message ? `批量删除失败：${err.message}` : "批量删除失败", icon: "none" });
      } finally {
        actionLoading.value = false;
      }
    }
  });
}

function copySummary() {
  const text = [summaryText.value, nextStepAdvice.value, `刷新状态：${loadMessage.value || "-"}`].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "云端录像摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

async function initPage() {
  if (!startTime.value || !endTime.value) initWindow();
  await loadChannels();
  await search();
}

onShow(initPage);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">云端录像</view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-subtext">{{ summaryText }}</text>
        <button size="mini" :loading="loading" @click="search">刷新</button>
      </view>
      <picker mode="selector" :range="['全部通道', ...channels.map((x) => `${x.device_name || x.device_id || '-'} / ${x.name || x.gb_id || '-'}`)]" @change="(e:any)=>onChannelChange(Number(e?.detail?.value || 0))">
        <view class="app-subtext">通道：{{ selectedChannelGbId || "全部" }}</view>
      </picker>
      <input v-model="startTime" placeholder="开始时间（ISO）" />
      <input v-model="endTime" placeholder="结束时间（ISO）" />
      <view class="app-row">
        <label class="app-subtext"><checkbox :checked="onlyBad" @click="onlyBad=!onlyBad" /> 仅异常</label>
        <button size="mini" :loading="loading" @click="search">查询</button>
      </view>
      <text class="app-subtext">{{ nextStepAdvice }}</text>
      <text class="app-subtext">刷新状态：{{ loadMessage || "-" }}</text>
      <text class="app-subtext">状态时间：{{ loadAt || "-" }}</text>
      <view class="app-row">
        <button size="mini" :loading="actionLoading" @click="verifyBatch">批量校验</button>
        <button size="mini" :loading="actionLoading" @click="repairBatch">批量修复</button>
        <button size="mini" :loading="actionLoading" @click="removeBadBatch">批量删异常</button>
        <button size="mini" @click="copySummary">复制摘要</button>
      </view>
      <view class="app-row">
        <button size="mini" :disabled="page<=1" @click="prevPage">上一页</button>
        <button size="mini" :disabled="page>=Math.max(1, Math.ceil(total / pageSize))" @click="nextPage">下一页</button>
        <text class="app-subtext">第 {{ page }} / {{ Math.max(1, Math.ceil(total / pageSize)) }} 页</text>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <view v-if="filteredRows.length" class="app-gap-12">
        <view v-for="row in filteredRows" :key="row.id" class="app-row">
          <view style="flex:1">
            <label class="app-subtext">
              <checkbox :checked="selectedIdSet.has(String(row.id || ''))" @click="toggleSelect(String(row.id || ''))" />
              选择
            </label>
            <text class="app-subtext">时间：{{ row.start_time || "-" }} ~ {{ row.end_time || "-" }}</text>
            <text class="app-subtext">设备/通道：{{ row.device_name || row.device_id || "-" }} / {{ row.channel_name || row.channel_id || "-" }}</text>
            <text class="app-subtext">时长：{{ row.duration || 0 }}s；大小：{{ row.file_size || 0 }}B</text>
            <text class="app-subtext">来源：{{ row.record_app || "-" }} {{ row.media_node_id ? `@${row.media_node_id}` : "" }}</text>
            <text class="app-subtext">错误：{{ row.url_error || "-" }}</text>
          </view>
          <view class="app-gap-12">
            <AppStatusTag :text="row.url_ok === false ? '异常' : row.url_checked_at ? '已校验' : '未校验'" :type="row.url_ok === false ? 'danger' : row.url_checked_at ? 'success' : 'info'" />
            <button size="mini" :loading="actionLoading" @click="copySignedDownloadUrl(String(row.id || ''), false)">下载链接</button>
            <button size="mini" :loading="actionLoading" @click="copySignedDownloadUrl(String(row.id || ''), true)">回放链接</button>
            <button size="mini" :loading="actionLoading" @click="verifyOne(String(row.id || ''))">校验</button>
            <button size="mini" :loading="actionLoading" @click="repairOne(String(row.id || ''))">修复</button>
            <button size="mini" :loading="actionLoading" @click="removeOne(String(row.id || ''))">删索引</button>
          </view>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '云端录像加载中...' : '暂无录像数据'" />
    </view>
  </view>
</template>
