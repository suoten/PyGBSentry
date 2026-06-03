<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import {
  fetchAccessSources,
  fetchStreamSessions,
  previewSource,
  setSourceEnabled,
  testSource,
  type AccessSourceItem,
  type StreamSessionItem
} from "@/api/integration";
import AppEmpty from "@/components/AppEmpty.vue";

const loading = ref(false);
const sources = ref<AccessSourceItem[]>([]);
const streams = ref<StreamSessionItem[]>([]);
const protocolFilter = ref("");
const keyword = ref("");
const loadMessage = ref("未刷新");
const loadAt = ref("");
const actionLoading = ref(false);

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

const proxyStreams = computed(() => {
  return streams.value.filter((x) => Boolean(x.is_proxy));
});

const filteredSources = computed(() => {
  return sources.value.filter((x) => {
    const protocolOk = !protocolFilter.value || String(x.protocol || "").toLowerCase() === protocolFilter.value.toLowerCase();
    const text = `${x.name || ""} ${x.host || ""} ${x.stream_name || ""}`.toLowerCase();
    const keywordOk = !keyword.value || text.includes(keyword.value.toLowerCase());
    return protocolOk && keywordOk;
  });
});

const summaryText = computed(() => {
  return `多协议接入：接入源=${sources.value.length}；代理流=${proxyStreams.value.length}；总流=${streams.value.length}；筛选后接入源=${filteredSources.value.length}`;
});

const nextStepAdvice = computed(() => {
  if (filteredSources.value.length === 0) return "下一步建议：先在运维中心或拉流代理页新增接入源，再回到本页汇总巡检。";
  if (proxyStreams.value.length === 0) return "下一步建议：当前无代理流，建议先执行接入源连通性测试并触发拉流。";
  return "下一步建议：按代理流观看数与吞吐排序，优先诊断高负载流。";
});

async function loadData() {
  loading.value = true;
  try {
    const [sourceRes, streamRes] = await Promise.allSettled([fetchAccessSources(), fetchStreamSessions()]);
    sources.value = sourceRes.status === "fulfilled" && Array.isArray(sourceRes.value) ? sourceRes.value : [];
    streams.value = streamRes.status === "fulfilled" && Array.isArray(streamRes.value) ? streamRes.value : [];
    const failedCount = [sourceRes, streamRes].filter((x) => x.status === "rejected").length;
    if (failedCount > 0) {
      setLoadStatus(`部分刷新成功：失败 ${failedCount} 项`);
      uni.showToast({ title: `部分接口失败(${failedCount})`, icon: "none" });
    } else {
      setLoadStatus("刷新成功");
    }
  } catch (err: any) {
    sources.value = [];
    streams.value = [];
    setLoadStatus(err?.message ? `刷新失败：${err.message}` : "刷新失败");
    uni.showToast({ title: "多协议接入加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

async function doTestSource(sourceId: string) {
  actionLoading.value = true;
  try {
    const res = await testSource(sourceId);
    uni.showToast({ title: res?.ok ? "连通性正常" : res?.message || "连通性异常", icon: "none" });
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `测试失败：${err.message}` : "测试失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function doPreviewSource(sourceId: string) {
  actionLoading.value = true;
  try {
    const res = await previewSource(sourceId);
    const text = `预览地址：webrtc=${res?.webrtc || "-"}；flv=${res?.flv || "-"}；hls=${res?.hls || "-"}`;
    uni.setClipboardData({
      data: text,
      success: () => uni.showToast({ title: "预览地址已复制", icon: "none" }),
      fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
    });
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `获取失败：${err.message}` : "获取失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function toggleSource(source: AccessSourceItem) {
  actionLoading.value = true;
  try {
    await setSourceEnabled(source.id, !Boolean(source.enabled));
    uni.showToast({ title: "状态已更新", icon: "none" });
    await loadData();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `更新失败：${err.message}` : "更新失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

function copySummary() {
  const text = [
    summaryText.value,
    `筛选=protocol:${protocolFilter.value || "all"},keyword:${keyword.value || "-"}`,
    nextStepAdvice.value,
    `刷新状态=${loadMessage.value || "-"}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "多协议接入摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

onShow(loadData);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">多协议接入</view>

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
      <text class="app-subtext">筛选</text>
      <input v-model="protocolFilter" class="app-input" placeholder="协议过滤（rtsp/onvif/sdk）" />
      <input v-model="keyword" class="app-input" placeholder="关键词（名称/主机/流名）" />
      <view class="app-row">
        <button size="mini" :loading="loading" @click="loadData">应用筛选并刷新</button>
        <button
          size="mini"
          @click="
            protocolFilter = '';
            keyword = '';
          "
        >
          重置筛选
        </button>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">接入源（{{ filteredSources.length }}）</text>
      <view v-if="filteredSources.length" class="app-gap-12">
        <view v-for="row in filteredSources" :key="row.id" class="app-card">
          <text class="app-subtext">{{ row.name }}（{{ row.protocol }}）</text>
          <text class="app-subtext">地址：{{ row.host }}:{{ row.port }}{{ row.path ? "/" + row.path : "" }}</text>
          <text class="app-subtext">流名：{{ row.stream_name || "-" }}；启用：{{ row.enabled ? "是" : "否" }}</text>
          <view class="app-row">
            <button size="mini" :loading="actionLoading" @click="toggleSource(row)">{{ row.enabled ? "停用" : "启用" }}</button>
            <button size="mini" :loading="actionLoading" @click="doTestSource(row.id)">连通性测试</button>
            <button size="mini" :loading="actionLoading" @click="doPreviewSource(row.id)">复制预览地址</button>
          </view>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '接入源加载中...' : '暂无接入源'" />
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">代理流（{{ proxyStreams.length }}）</text>
      <view v-if="proxyStreams.length" class="app-gap-12">
        <view v-for="(row, idx) in proxyStreams.slice(0, 80)" :key="`proxy-${idx}`" class="app-row">
          <text class="app-subtext">
            {{ row.app || "-" }}/{{ row.stream || "-" }}；观看={{ row.reader_count || 0 }}；存活={{ row.alive_second || 0 }}s；吞吐={{ row.bytes_speed || 0 }}B/s
          </text>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '流会话加载中...' : '暂无代理流'" />
    </view>
  </view>
</template>
