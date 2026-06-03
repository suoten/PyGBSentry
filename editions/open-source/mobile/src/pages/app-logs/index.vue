<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import { fetchAppLogs, type AppLogItem } from "@/api/app-logs";
import AppEmpty from "@/components/AppEmpty.vue";

const loading = ref(false);
const items = ref<AppLogItem[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const pluginId = ref("");
const platform = ref("");
const logType = ref("");
const startTime = ref("");
const endTime = ref("");
const loadMessage = ref("未刷新");
const loadAt = ref("");

const pluginOptions = ["全部应用", "手机版", "小程序"];
const pluginValues = ["", "mobile_app_suite", "mini_program_suite"];
const platformOptions = ["全部平台", "android", "ios", "miniprogram"];
const platformValues = ["", "android", "ios", "miniprogram"];
const logTypeOptions = ["全部类型", "crash", "behavior"];
const logTypeValues = ["", "crash", "behavior"];
const pageSizeOptions = ["10", "20", "50", "100"];

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

const pageCount = computed(() => {
  if (pageSize.value <= 0) return 1;
  return Math.max(1, Math.ceil(Number(total.value || 0) / pageSize.value));
});

const summaryText = computed(() => {
  const crashCount = items.value.filter((x) => x.log_type === "crash").length;
  return `应用日志：总数=${total.value}；当前页=${page.value}/${pageCount.value}；页大小=${pageSize.value}；当前崩溃数=${crashCount}`;
});

const nextStepAdvice = computed(() => {
  const crashCount = items.value.filter((x) => x.log_type === "crash").length;
  if (crashCount > 0) return "下一步建议：优先处理崩溃日志，按版本与平台聚合定位高频问题。";
  return "下一步建议：保持行为日志抽样巡检，关注异常峰值与时间窗口变化。";
});

function pluginLabel(value: string) {
  if (value === "mini_program_suite") return "小程序";
  if (value === "mobile_app_suite") return "手机版";
  return "未知";
}

function logTypeLabel(value: string) {
  return value === "crash" ? "崩溃" : value === "behavior" ? "行为" : value || "-";
}

async function loadData() {
  loading.value = true;
  try {
    const result = await fetchAppLogs({
      plugin_id: pluginId.value || undefined,
      platform: platform.value || undefined,
      log_type: logType.value || undefined,
      start_time: startTime.value || undefined,
      end_time: endTime.value || undefined,
      skip: (page.value - 1) * pageSize.value,
      limit: pageSize.value
    });
    items.value = Array.isArray(result.items) ? result.items : [];
    total.value = Number(result.total || 0);
    setLoadStatus("刷新成功");
  } catch (err: any) {
    items.value = [];
    total.value = 0;
    setLoadStatus(err?.message ? `刷新失败：${err.message}` : "刷新失败");
    uni.showToast({ title: "应用日志加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

function refreshWithReset() {
  page.value = 1;
  loadData();
}

function changePlugin(e: any) {
  const i = Number(e?.detail?.value || 0);
  pluginId.value = pluginValues[i] || "";
  refreshWithReset();
}

function changePlatform(e: any) {
  const i = Number(e?.detail?.value || 0);
  platform.value = platformValues[i] || "";
  refreshWithReset();
}

function changeLogType(e: any) {
  const i = Number(e?.detail?.value || 0);
  logType.value = logTypeValues[i] || "";
  refreshWithReset();
}

function changePageSize(e: any) {
  const i = Number(e?.detail?.value || 1);
  pageSize.value = Number(pageSizeOptions[i] || "20");
  refreshWithReset();
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

function copySummary() {
  const text = [
    summaryText.value,
    `筛选=plugin:${pluginId.value || "all"},platform:${platform.value || "all"},type:${logType.value || "all"}`,
    `时间窗=${startTime.value || "-"}~${endTime.value || "-"}`,
    nextStepAdvice.value,
    `刷新状态=${loadMessage.value || "-"}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "应用日志摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

onShow(loadData);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">应用日志</view>

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
      <view class="app-row">
        <picker mode="selector" :range="pluginOptions" :value="pluginValues.indexOf(pluginId)" @change="changePlugin">
          <view class="app-subtext">应用：{{ pluginId || "全部" }}</view>
        </picker>
        <picker mode="selector" :range="platformOptions" :value="platformValues.indexOf(platform)" @change="changePlatform">
          <view class="app-subtext">平台：{{ platform || "全部" }}</view>
        </picker>
      </view>
      <view class="app-row">
        <picker mode="selector" :range="logTypeOptions" :value="logTypeValues.indexOf(logType)" @change="changeLogType">
          <view class="app-subtext">类型：{{ logType || "全部" }}</view>
        </picker>
        <picker mode="selector" :range="pageSizeOptions" :value="pageSizeOptions.indexOf(String(pageSize))" @change="changePageSize">
          <view class="app-subtext">每页：{{ pageSize }}</view>
        </picker>
      </view>
      <input v-model="startTime" class="app-input" placeholder="开始时间（ISO，例如 2026-04-22T00:00:00）" />
      <input v-model="endTime" class="app-input" placeholder="结束时间（ISO，例如 2026-04-22T23:59:59）" />
      <view class="app-row">
        <button size="mini" :loading="loading" @click="refreshWithReset">应用筛选</button>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-subtext">日志列表（{{ total }}）</text>
        <view class="app-row">
          <button size="mini" :disabled="page <= 1 || loading" @click="prevPage">上一页</button>
          <button size="mini" :disabled="page >= pageCount || loading" @click="nextPage">下一页</button>
        </view>
      </view>
      <view v-if="items.length" class="app-gap-12">
        <view v-for="row in items" :key="row.id" class="app-card">
          <text class="app-subtext">{{ row.created_at || "-" }}</text>
          <text class="app-subtext">应用：{{ pluginLabel(row.plugin_id) }}；平台：{{ row.platform || "-" }}；版本：{{ row.app_version || "-" }}</text>
          <text class="app-subtext">类型：{{ logTypeLabel(row.log_type) }}</text>
          <text class="app-subtext">内容：{{ row.message || "-" }}</text>
          <text class="app-subtext">扩展：{{ row.extra || "-" }}</text>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '日志加载中...' : '暂无日志'" />
    </view>
  </view>
</template>
