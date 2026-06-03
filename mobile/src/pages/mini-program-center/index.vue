<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import { fetchAppRemoteConfig, fetchAppStats, fetchAppVersionCheck } from "@/api/mobile-app";

const loading = ref(false);
const loadMessage = ref("未刷新");
const loadAt = ref("");
const latestVersion = ref("");
const forceUpdate = ref(false);
const rolloutRatio = ref(100);
const miniprogramUrl = ref("");
const releaseNotes = ref("");
const stats = ref({ total: 0, crash_total: 0 });
const remoteConfigText = ref("{}");

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

const summaryText = computed(() => {
  return `小程序：版本=${latestVersion.value || "-"}；强更=${forceUpdate.value ? "是" : "否"}；灰度=${rolloutRatio.value}%；24h日志=${stats.value.total}；24h崩溃=${stats.value.crash_total}`;
});

const nextStepAdvice = computed(() => {
  if (forceUpdate.value) return "下一步建议：优先验证强制更新提示与入口跳转。";
  if (stats.value.crash_total > 0) return "下一步建议：优先定位崩溃来源并回归关键页面。";
  return "下一步建议：维持灰度观测，持续抽检远程配置命中情况。";
});

async function loadData() {
  loading.value = true;
  try {
    const current = latestVersion.value || "0.0.0";
    const [versionRes, statsRes, configRes] = await Promise.allSettled([
      fetchAppVersionCheck({
        plugin_id: "mini_program_suite",
        platform: "miniprogram",
        current_version: current,
        release_channel: "stable",
        device_id: "mobile-console"
      }),
      fetchAppStats("mini_program_suite", 1),
      fetchAppRemoteConfig("mini_program_suite", current)
    ]);

    if (versionRes.status === "fulfilled") {
      latestVersion.value = String(versionRes.value.latest_version || "");
      forceUpdate.value = Boolean(versionRes.value.force_update);
      rolloutRatio.value = Number(versionRes.value.rollout_ratio ?? 100);
      miniprogramUrl.value = String(versionRes.value.download_url || "");
      releaseNotes.value = String(versionRes.value.release_notes || "");
    } else {
      latestVersion.value = "";
      forceUpdate.value = false;
      rolloutRatio.value = 100;
      miniprogramUrl.value = "";
      releaseNotes.value = "";
    }

    if (statsRes.status === "fulfilled") {
      stats.value = {
        total: Number(statsRes.value.total || 0),
        crash_total: Number(statsRes.value.crash_total || 0)
      };
    } else {
      stats.value = { total: 0, crash_total: 0 };
    }

    if (configRes.status === "fulfilled") {
      remoteConfigText.value = JSON.stringify(configRes.value.config || {}, null, 2);
    } else {
      remoteConfigText.value = "{}";
    }

    const failedCount = [versionRes, statsRes, configRes].filter((x) => x.status === "rejected").length;
    if (failedCount > 0) {
      setLoadStatus(`部分刷新成功：失败 ${failedCount} 项`);
      uni.showToast({ title: `部分接口失败(${failedCount})`, icon: "none" });
    } else {
      setLoadStatus("刷新成功");
    }
  } catch (err: any) {
    setLoadStatus(err?.message ? `刷新失败：${err.message}` : "刷新失败");
    uni.showToast({ title: "小程序中心加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

function copyText(text: string, title: string) {
  if (!text) {
    uni.showToast({ title: "暂无可复制内容", icon: "none" });
    return;
  }
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title, icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copySummary() {
  const text = [summaryText.value, nextStepAdvice.value, `刷新状态=${loadMessage.value || "-"}`].join("；");
  copyText(text, "小程序摘要已复制");
}

onShow(loadData);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">小程序中心</view>

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
      <text class="app-subtext">版本概览</text>
      <text class="app-subtext">最新版本：{{ latestVersion || "-" }}</text>
      <text class="app-subtext">强制更新：{{ forceUpdate ? "是" : "否" }}</text>
      <text class="app-subtext">灰度比例：{{ rolloutRatio }}%</text>
      <text class="app-subtext">更新说明：{{ releaseNotes || "-" }}</text>
      <view class="app-row">
        <button size="mini" :disabled="!miniprogramUrl" @click="copyText(miniprogramUrl, '小程序链接已复制')">复制访问链接</button>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">运行概览（最近24h）</text>
      <text class="app-subtext">日志总量：{{ stats.total }}</text>
      <text class="app-subtext">崩溃总量：{{ stats.crash_total }}</text>
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">远程配置</text>
      <textarea :value="remoteConfigText" class="app-input" auto-height :maxlength="-1" disabled />
      <view class="app-row">
        <button size="mini" @click="copyText(remoteConfigText, '远程配置已复制')">复制远程配置</button>
      </view>
    </view>
  </view>
</template>
