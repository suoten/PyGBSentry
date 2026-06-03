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
const androidUrl = ref("");
const iosUrl = ref("");
const releaseNotes = ref("");
const stats = ref({ total: 0, crash_total: 0 });
const remoteConfigText = ref("{}");

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

const summaryText = computed(() => {
  return `手机版：版本=${latestVersion.value || "-"}；强更=${forceUpdate.value ? "是" : "否"}；灰度=${rolloutRatio.value}%；24h日志=${stats.value.total}；24h崩溃=${stats.value.crash_total}`;
});

const nextStepAdvice = computed(() => {
  if (forceUpdate.value) return "下一步建议：优先验证强制更新链路与下载地址可达性。";
  if (stats.value.crash_total > 0) return "下一步建议：优先排查崩溃日志并确认回归版本。";
  return "下一步建议：保持版本抽检，重点关注灰度发布阶段反馈。";
});

async function loadData() {
  loading.value = true;
  try {
    const current = latestVersion.value || "0.0.0";
    const [androidRes, iosRes, statsRes, configRes] = await Promise.allSettled([
      fetchAppVersionCheck({
        plugin_id: "mobile_app_suite",
        platform: "android",
        current_version: current,
        release_channel: "stable",
        device_id: "mobile-console"
      }),
      fetchAppVersionCheck({
        plugin_id: "mobile_app_suite",
        platform: "ios",
        current_version: current,
        release_channel: "stable",
        device_id: "mobile-console"
      }),
      fetchAppStats("mobile_app_suite", 1),
      fetchAppRemoteConfig("mobile_app_suite", current)
    ]);

    const android = androidRes.status === "fulfilled" ? androidRes.value : {};
    const ios = iosRes.status === "fulfilled" ? iosRes.value : {};
    latestVersion.value = String(android.latest_version || ios.latest_version || "");
    forceUpdate.value = Boolean(android.force_update || ios.force_update);
    rolloutRatio.value = Number(android.rollout_ratio ?? ios.rollout_ratio ?? 100);
    androidUrl.value = String(android.download_url || "");
    iosUrl.value = String(ios.download_url || "");
    releaseNotes.value = String(android.release_notes || ios.release_notes || "");

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

    const failedCount = [androidRes, iosRes, statsRes, configRes].filter((x) => x.status === "rejected").length;
    if (failedCount > 0) {
      setLoadStatus(`部分刷新成功：失败 ${failedCount} 项`);
      uni.showToast({ title: `部分接口失败(${failedCount})`, icon: "none" });
    } else {
      setLoadStatus("刷新成功");
    }
  } catch (err: any) {
    setLoadStatus(err?.message ? `刷新失败：${err.message}` : "刷新失败");
    uni.showToast({ title: "手机版中心加载失败", icon: "none" });
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
  copyText(text, "手机版摘要已复制");
}

onShow(loadData);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">手机版中心</view>

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
        <button size="mini" :disabled="!androidUrl" @click="copyText(androidUrl, '安卓下载地址已复制')">安卓下载地址</button>
        <button size="mini" :disabled="!iosUrl" @click="copyText(iosUrl, 'iOS下载地址已复制')">iOS下载地址</button>
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
