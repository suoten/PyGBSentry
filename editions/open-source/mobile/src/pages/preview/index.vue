<script setup lang="ts">
import { onHide, onLoad, onUnload } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import { request } from "@/utils/request";
import {
  buildFallbackChain,
  getStreamHealth,
  pickPreferredPlayUrl,
  playStream,
  reportStreamQuality,
  type StreamHealthData,
  type StreamPlayData
} from "@/api/stream";
import AppStatusTag from "@/components/AppStatusTag.vue";
import AppEmpty from "@/components/AppEmpty.vue";
import AppStreamPlayer from "@/components/AppStreamPlayer.vue";

const PREVIEW_PERF_METRICS_KEY = "pgbsentry_mobile_preview_perf_metrics";
const PREVIEW_WEAK_NETWORK_MODE_KEY = "pgbsentry_mobile_preview_weak_network_mode";
const PREVIEW_QUALITY_REPORT_METRICS_KEY = "pgbsentry_mobile_preview_quality_report_metrics";
const PREVIEW_GATE_MIN_SUCCESS_RATE = 80;
const PREVIEW_GATE_MAX_AVG_STARTUP_MS = 4500;

const deviceId = ref("");
const channelId = ref("");
const loading = ref(false);
const playUrl = ref("");
const playMode = ref("raw");
const errorText = ref("");
const splitCount = ref<1 | 4>(1);
const activeSlot = ref(0);
const lineOptions = ref<Array<{ id: string; name: string; recommended?: boolean }>>([]);
const lineOptionsLoadMessage = ref("线路信息未加载");
const lineOptionsLastLoadedAt = ref("");
const fallbackChain = ref<Array<{ mode: "webrtc" | "flv" | "hls"; url: string }>>([]);
const fallbackIndex = ref(0);
const sessionId = ref("");
const health = ref<StreamHealthData | null>(null);
const healthLoadMessage = ref("健康采样未执行");
const healthLastLoadedAt = ref("");
const weakNetworkMode = ref<"auto" | "aggressive">(
  uni.getStorageSync(PREVIEW_WEAK_NETWORK_MODE_KEY) === "aggressive" ? "aggressive" : "auto"
);
const perfMetrics = ref<{
  attempts: number;
  successes: number;
  failures: number;
  totalStartupMs: number;
  lastStartupMs: number;
  lastResult: "success" | "failed" | "idle";
  lastAt: string;
}>(
  (uni.getStorageSync(PREVIEW_PERF_METRICS_KEY) || {
    attempts: 0,
    successes: 0,
    failures: 0,
    totalStartupMs: 0,
    lastStartupMs: 0,
    lastResult: "idle",
    lastAt: ""
  }) as {
    attempts: number;
    successes: number;
    failures: number;
    totalStartupMs: number;
    lastStartupMs: number;
    lastResult: "success" | "failed" | "idle";
    lastAt: string;
  }
);
const qualityReportMetrics = ref<{
  attempts: number;
  successes: number;
  failures: number;
  lastStatus: "success" | "failed" | "idle";
  lastMessage: string;
  lastAt: string;
}>(
  (uni.getStorageSync(PREVIEW_QUALITY_REPORT_METRICS_KEY) || {
    attempts: 0,
    successes: 0,
    failures: 0,
    lastStatus: "idle",
    lastMessage: "暂无质量上报记录",
    lastAt: ""
  }) as {
    attempts: number;
    successes: number;
    failures: number;
    lastStatus: "success" | "failed" | "idle";
    lastMessage: string;
    lastAt: string;
  }
);
let healthTimer: ReturnType<typeof setInterval> | null = null;

type SlotMode = "webrtc" | "flv" | "hls" | "raw";
type PreviewSlotState = {
  sessionId: string;
  url: string;
  mode: SlotMode;
  error: string;
  loading: boolean;
  fallbackChain: Array<{ mode: "webrtc" | "flv" | "hls"; url: string }>;
  fallbackIndex: number;
  health: StreamHealthData | null;
};

const slots = ref<PreviewSlotState[]>([
  { sessionId: "", url: "", mode: "raw", error: "", loading: false, fallbackChain: [], fallbackIndex: 0, health: null },
  { sessionId: "", url: "", mode: "raw", error: "", loading: false, fallbackChain: [], fallbackIndex: 0, health: null },
  { sessionId: "", url: "", mode: "raw", error: "", loading: false, fallbackChain: [], fallbackIndex: 0, health: null },
  { sessionId: "", url: "", mode: "raw", error: "", loading: false, fallbackChain: [], fallbackIndex: 0, health: null }
]);

function setSlotUrl(index: number, url: string, mode: string) {
  const prev = slots.value[index];
  if (!prev) return;
  slots.value[index] = {
    ...prev,
    url,
    mode: mode as SlotMode
  };
  if (index === activeSlot.value) {
    playUrl.value = url;
    playMode.value = mode;
  }
}

function saveWeakNetworkMode() {
  uni.setStorageSync(PREVIEW_WEAK_NETWORK_MODE_KEY, weakNetworkMode.value);
}

function savePerfMetrics() {
  uni.setStorageSync(PREVIEW_PERF_METRICS_KEY, perfMetrics.value);
}

function saveQualityReportMetrics() {
  uni.setStorageSync(PREVIEW_QUALITY_REPORT_METRICS_KEY, qualityReportMetrics.value);
}

function markLineOptionsStatus(message: string) {
  lineOptionsLoadMessage.value = message;
  lineOptionsLastLoadedAt.value = new Date().toISOString();
}

function markHealthStatus(message: string) {
  healthLoadMessage.value = message;
  healthLastLoadedAt.value = new Date().toISOString();
}

function markPerfAttempt(result: "success" | "failed", startupMs: number) {
  const safeMs = Math.max(0, Number(startupMs || 0));
  perfMetrics.value = {
    attempts: Number(perfMetrics.value.attempts || 0) + 1,
    successes: Number(perfMetrics.value.successes || 0) + (result === "success" ? 1 : 0),
    failures: Number(perfMetrics.value.failures || 0) + (result === "failed" ? 1 : 0),
    totalStartupMs: Number(perfMetrics.value.totalStartupMs || 0) + safeMs,
    lastStartupMs: safeMs,
    lastResult: result,
    lastAt: new Date().toISOString()
  };
  savePerfMetrics();
}

function markQualityReportAttempt(result: "success" | "failed", message: string) {
  qualityReportMetrics.value = {
    attempts: Number(qualityReportMetrics.value.attempts || 0) + 1,
    successes: Number(qualityReportMetrics.value.successes || 0) + (result === "success" ? 1 : 0),
    failures: Number(qualityReportMetrics.value.failures || 0) + (result === "failed" ? 1 : 0),
    lastStatus: result,
    lastMessage: message || (result === "success" ? "质量上报成功" : "质量上报失败"),
    lastAt: new Date().toISOString()
  };
  saveQualityReportMetrics();
}

async function reportQualityByHealth(targetSessionId: string, healthData: StreamHealthData | null, scene: string) {
  if (!targetSessionId || !healthData) return;
  try {
    await reportStreamQuality({
      session_id: targetSessionId,
      fps: Number(healthData.fps || 0),
      bitrate_kbps: Number(healthData.bitrate_kbps || 0),
      packet_loss_rate: Number(healthData.packet_loss_rate || 0),
      buffer_ms: Number(healthData.buffer_ms || 0)
    });
    markQualityReportAttempt("success", `${scene} 质量上报成功`);
  } catch (err: any) {
    const msg = String(err?.message || `${scene} 质量上报失败`);
    markQualityReportAttempt("failed", msg);
  }
}

function pickWithWeakNetworkPolicy(
  picked: { url: string; mode: "webrtc" | "flv" | "hls" | "raw" },
  chain: Array<{ mode: "webrtc" | "flv" | "hls"; url: string }>
) {
  if (weakNetworkMode.value !== "aggressive") return picked;
  const candidates = chain.filter((x) => !!x.url);
  if (candidates.length <= 0) return picked;
  const hls = candidates.find((x) => x.mode === "hls");
  if (hls) return { url: hls.url, mode: "hls" as const };
  const flv = candidates.find((x) => x.mode === "flv");
  if (flv) return { url: flv.url, mode: "flv" as const };
  const webrtc = candidates.find((x) => x.mode === "webrtc");
  if (webrtc) return { url: webrtc.url, mode: "webrtc" as const };
  return picked;
}

function resetSlots() {
  slots.value = [
    { sessionId: "", url: "", mode: "raw", error: "", loading: false, fallbackChain: [], fallbackIndex: 0, health: null },
    { sessionId: "", url: "", mode: "raw", error: "", loading: false, fallbackChain: [], fallbackIndex: 0, health: null },
    { sessionId: "", url: "", mode: "raw", error: "", loading: false, fallbackChain: [], fallbackIndex: 0, health: null },
    { sessionId: "", url: "", mode: "raw", error: "", loading: false, fallbackChain: [], fallbackIndex: 0, health: null }
  ];
}

async function loadLineOptions() {
  if (!deviceId.value || !channelId.value) return;
  try {
    const res = await request<{ lines?: Array<{ id: string; name: string; recommended?: boolean }> }>({
      url: `/api/v1/stream/stream/lines/${encodeURIComponent(deviceId.value)}/${encodeURIComponent(channelId.value)}`
    });
    lineOptions.value = res.lines || [];
    markLineOptionsStatus(`线路信息加载成功：共 ${lineOptions.value.length} 条`);
  } catch {
    try {
      const fallback = await request<{ lines?: Array<{ id: string; name: string; recommended?: boolean }> }>({
        url: `/api/v1/stream/lines/${encodeURIComponent(deviceId.value)}/${encodeURIComponent(channelId.value)}`
      });
      lineOptions.value = fallback.lines || [];
      markLineOptionsStatus(`线路信息加载成功(兼容接口)：共 ${lineOptions.value.length} 条`);
    } catch {
      lineOptions.value = [];
      markLineOptionsStatus("线路信息加载失败，请稍后重试");
      uni.showToast({ title: "线路信息加载失败", icon: "none" });
    }
  }
}

async function loadStreamHealth() {
  if (!sessionId.value) {
    health.value = null;
    markHealthStatus("健康采样跳过：当前无会话");
    return;
  }
  try {
    health.value = await getStreamHealth(sessionId.value);
    await reportQualityByHealth(sessionId.value, health.value, "主窗口");
    const score = Number(health.value?.health_score || 0);
    markHealthStatus(`健康采样成功：主窗口健康分 ${score || "-"}`);
  } catch (err: any) {
    const reason = String(err?.message || "请稍后重试");
    markHealthStatus(`健康采样失败：${reason}`);
    uni.showToast({ title: "健康采样失败", icon: "none" });
  }
}

async function loadSlotStreamHealth(slotIndex: number) {
  const slot = slots.value[slotIndex];
  if (!slot || !slot.sessionId) {
    if (slot) slot.health = null;
    markHealthStatus(`健康采样跳过：窗口${slotIndex + 1}无会话`);
    return;
  }
  try {
    slot.health = await getStreamHealth(slot.sessionId);
    await reportQualityByHealth(slot.sessionId, slot.health, `四分屏窗口${slotIndex + 1}`);
    const score = Number(slot.health?.health_score || 0);
    markHealthStatus(`健康采样成功：窗口${slotIndex + 1} 健康分 ${score || "-"}`);
  } catch (err: any) {
    const reason = String(err?.message || "请稍后重试");
    markHealthStatus(`健康采样失败：窗口${slotIndex + 1}，${reason}`);
  }
}

function stopHealthPolling() {
  if (healthTimer) {
    clearInterval(healthTimer);
    healthTimer = null;
  }
}

function startHealthPolling() {
  stopHealthPolling();
  if (!sessionId.value && splitCount.value !== 4) return;
  healthTimer = setInterval(() => {
    if (splitCount.value === 4) {
      [0, 1, 2, 3].forEach((idx) => {
        loadSlotStreamHealth(idx).catch(() => undefined);
      });
    } else {
      loadStreamHealth().catch(() => undefined);
    }
  }, 10000);
}

async function startPreviewForSlot(slotIndex: number) {
  const slot = slots.value[slotIndex];
  if (!slot) return;
  slot.loading = true;
  slot.error = "";
  slot.url = "";
  slot.mode = "raw";
  slot.sessionId = "";
  slot.fallbackChain = [];
  slot.fallbackIndex = 0;
  slot.health = null;
  const startedAt = Date.now();
  try {
    const data: StreamPlayData = await playStream(deviceId.value, channelId.value);
    slot.sessionId = String(data.session_id || "");
    slot.fallbackChain = buildFallbackChain(data);
    const picked = pickPreferredPlayUrl(data);
    const selected = pickWithWeakNetworkPolicy(picked, slot.fallbackChain);
    slot.url = selected.url;
    slot.mode = selected.mode;
    if (!selected.url) {
      slot.error = "未拿到可播放地址";
      markPerfAttempt("failed", Date.now() - startedAt);
    } else {
      markPerfAttempt("success", Date.now() - startedAt);
    }
    if (slotIndex === activeSlot.value) {
      playUrl.value = slot.url;
      playMode.value = slot.mode;
      sessionId.value = slot.sessionId;
      fallbackChain.value = slot.fallbackChain;
      fallbackIndex.value = slot.fallbackIndex;
    }
    await loadSlotStreamHealth(slotIndex);
  } catch (err: any) {
    slot.error = err?.message || "拉流失败";
    markPerfAttempt("failed", Date.now() - startedAt);
  } finally {
    slot.loading = false;
  }
}

async function startPreview() {
  if (!deviceId.value || !channelId.value) {
    uni.showToast({ title: "请先输入设备ID与通道ID", icon: "none" });
    return;
  }
  loading.value = true;
  errorText.value = "";
  playUrl.value = "";
  playMode.value = "raw";
  sessionId.value = "";
  health.value = null;
  fallbackIndex.value = 0;
  resetSlots();
  try {
    if (splitCount.value === 4) {
      await Promise.all([0, 1, 2, 3].map((idx) => startPreviewForSlot(idx)));
      const active = slots.value[activeSlot.value];
      playUrl.value = active?.url || "";
      playMode.value = active?.mode || "raw";
      sessionId.value = active?.sessionId || "";
      fallbackChain.value = active?.fallbackChain || [];
      fallbackIndex.value = active?.fallbackIndex || 0;
      if (!playUrl.value) {
        errorText.value = "四分屏未拿到可播放地址，请检查设备在线状态和流媒体配置";
      }
    } else {
      const startedAt = Date.now();
      const data: StreamPlayData = await playStream(deviceId.value, channelId.value);
      sessionId.value = String(data.session_id || "");
      fallbackChain.value = buildFallbackChain(data);
      const picked = pickPreferredPlayUrl(data);
      const selected = pickWithWeakNetworkPolicy(picked, fallbackChain.value);
      playUrl.value = selected.url;
      playMode.value = selected.mode;
      setSlotUrl(activeSlot.value, selected.url, selected.mode);
      if (!selected.url) {
        errorText.value = "未拿到可播放地址，请检查设备在线状态和流媒体配置";
        markPerfAttempt("failed", Date.now() - startedAt);
      } else if (fallbackChain.value.length > 1) {
        markPerfAttempt("success", Date.now() - startedAt);
        uni.showToast({
          title: `当前线路 ${selected.mode.toUpperCase()}，已启用自动回退`,
          icon: "none",
          duration: 1600
        });
      } else {
        markPerfAttempt("success", Date.now() - startedAt);
      }
      await loadStreamHealth();
    }
    await loadLineOptions();
    startHealthPolling();
  } catch (err: any) {
    errorText.value = err?.message || "拉流失败，请稍后重试";
    markPerfAttempt("failed", 0);
  } finally {
    loading.value = false;
  }
}

function switchSplit(count: 1 | 4) {
  splitCount.value = count;
  if (count === 1) {
    activeSlot.value = 0;
    const first = slots.value[0];
    playUrl.value = first?.url || "";
    playMode.value = first?.mode || "raw";
    sessionId.value = first?.sessionId || "";
    fallbackChain.value = first?.fallbackChain || [];
    fallbackIndex.value = first?.fallbackIndex || 0;
    health.value = first?.health || null;
  } else {
    const cur = slots.value[activeSlot.value];
    playUrl.value = cur?.url || "";
    playMode.value = cur?.mode || "raw";
    sessionId.value = cur?.sessionId || "";
    fallbackChain.value = cur?.fallbackChain || [];
    fallbackIndex.value = cur?.fallbackIndex || 0;
    health.value = cur?.health || null;
  }
}

function switchSlot(index: number) {
  activeSlot.value = index;
  const slot = slots.value[index];
  playUrl.value = slot?.url || "";
  playMode.value = slot?.mode || "raw";
  sessionId.value = slot?.sessionId || "";
  fallbackChain.value = slot?.fallbackChain || [];
  fallbackIndex.value = slot?.fallbackIndex || 0;
  health.value = slot?.health || null;
}

function fallbackNext() {
  if (splitCount.value === 4) {
    const slot = slots.value[activeSlot.value];
    if (!slot || !slot.fallbackChain.length) {
      uni.showToast({ title: "当前窗口无可回退线路", icon: "none" });
      return;
    }
    slot.fallbackIndex = (slot.fallbackIndex + 1) % slot.fallbackChain.length;
    const next = slot.fallbackChain[slot.fallbackIndex];
    slot.url = next.url;
    slot.mode = next.mode;
    playUrl.value = slot.url;
    playMode.value = slot.mode;
    uni.showToast({ title: `窗口${activeSlot.value + 1}切换到 ${next.mode.toUpperCase()}`, icon: "none" });
    return;
  }
  if (!fallbackChain.value.length) {
    uni.showToast({ title: "当前无可回退线路", icon: "none" });
    return;
  }
  fallbackIndex.value = (fallbackIndex.value + 1) % fallbackChain.value.length;
  const next = fallbackChain.value[fallbackIndex.value];
  setSlotUrl(activeSlot.value, next.url, next.mode);
  uni.showToast({ title: `已切换到 ${next.mode.toUpperCase()}`, icon: "none" });
}

async function refreshSingleSlot(index: number) {
  if (!deviceId.value || !channelId.value) {
    uni.showToast({ title: "请先输入设备ID与通道ID", icon: "none" });
    return;
  }
  await startPreviewForSlot(index);
  if (index === activeSlot.value) {
    const slot = slots.value[index];
    playUrl.value = slot?.url || "";
    playMode.value = slot?.mode || "raw";
    sessionId.value = slot?.sessionId || "";
    fallbackChain.value = slot?.fallbackChain || [];
    fallbackIndex.value = slot?.fallbackIndex || 0;
    health.value = slot?.health || null;
  }
}

async function refreshHealthSample() {
  if (splitCount.value === 4) {
    await loadSlotStreamHealth(activeSlot.value);
    return;
  }
  await loadStreamHealth();
}

const splitLoadedCount = computed(() => slots.value.filter((x) => !!x.url).length);
const previewAvgStartupMs = computed(() => {
  const attempts = Number(perfMetrics.value.attempts || 0);
  if (attempts <= 0) return 0;
  return Number((Number(perfMetrics.value.totalStartupMs || 0) / attempts).toFixed(2));
});
const previewSuccessRate = computed(() => {
  const attempts = Number(perfMetrics.value.attempts || 0);
  if (attempts <= 0) return 0;
  return Number(((Number(perfMetrics.value.successes || 0) / attempts) * 100).toFixed(2));
});
const previewPerfGate = computed(() => {
  const ratePass = previewSuccessRate.value >= PREVIEW_GATE_MIN_SUCCESS_RATE;
  const startupPass = previewAvgStartupMs.value > 0 && previewAvgStartupMs.value <= PREVIEW_GATE_MAX_AVG_STARTUP_MS;
  return {
    pass: ratePass && startupPass,
    message: `成功率阈值(>=${PREVIEW_GATE_MIN_SUCCESS_RATE}%) ${ratePass ? "通过" : "未通过"} / 启动耗时阈值(<=${PREVIEW_GATE_MAX_AVG_STARTUP_MS}ms) ${startupPass ? "通过" : "未通过"}`
  };
});

const previewPerfNextStepAdvice = computed(() => {
  if (previewPerfGate.value.pass && Number(qualityReportMetrics.value.failures || 0) <= 0) {
    return "下一步建议：保持当前策略并持续观察质量上报。";
  }
  if (!previewPerfGate.value.pass && previewSuccessRate.value < PREVIEW_GATE_MIN_SUCCESS_RATE) {
    return "下一步建议：优先检查设备在线状态与网络抖动，必要时切换为激进弱网策略后重试。";
  }
  if (!previewPerfGate.value.pass && previewAvgStartupMs.value > PREVIEW_GATE_MAX_AVG_STARTUP_MS) {
    return "下一步建议：优先检查流媒体节点负载与链路时延，必要时执行线路回退。";
  }
  if (Number(qualityReportMetrics.value.failures || 0) > 0) {
    return "下一步建议：检查质量上报接口连通性与鉴权配置后重试上报。";
  }
  return "下一步建议：执行一次拉流重试并复核门禁指标。";
});

function copyPreviewPerfGateSummary() {
  const text = [
    "预览门禁摘要",
    `拉流尝试：${perfMetrics.value.attempts} / 成功：${perfMetrics.value.successes} / 失败：${perfMetrics.value.failures}`,
    `平均启动耗时：${previewAvgStartupMs.value}ms / 最近一次：${perfMetrics.value.lastStartupMs}ms`,
    `成功率：${previewSuccessRate.value}% / 当前策略：${
      weakNetworkMode.value === "aggressive" ? "激进弱网（优先 HLS/FLV）" : "自动"
    }`,
    `门禁结果：${previewPerfGate.value.message}`,
    `质量上报：${qualityReportMetrics.value.attempts} 次 / 成功 ${qualityReportMetrics.value.successes} / 失败 ${qualityReportMetrics.value.failures}`,
    previewPerfNextStepAdvice.value
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "预览门禁摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

const previewSplitPatrolStats = computed(() => {
  const loadedSlots = slots.value.filter((x) => !!x.url);
  const loadedCount = loadedSlots.length;
  const healthScores = loadedSlots
    .map((x) => Number(x.health?.health_score || 0))
    .filter((score) => score > 0);
  const avgHealthScore =
    healthScores.length > 0 ? Number((healthScores.reduce((sum, x) => sum + x, 0) / healthScores.length).toFixed(2)) : 0;
  const lowHealthCount = loadedSlots.filter((x) => Number(x.health?.health_score || 0) > 0 && Number(x.health?.health_score || 0) < 60).length;
  const noHealthCount = loadedSlots.filter((x) => Number(x.health?.health_score || 0) <= 0).length;
  return { loadedCount, avgHealthScore, lowHealthCount, noHealthCount };
});

const previewSplitPatrolNextStepAdvice = computed(() => {
  if (previewSplitPatrolStats.value.loadedCount < 4) {
    return "下一步建议：优先刷新未加载窗口，确保四分屏链路齐全。";
  }
  if (previewSplitPatrolStats.value.lowHealthCount > 0) {
    return "下一步建议：优先处理低健康窗口，必要时执行线路回退或切换弱网策略。";
  }
  if (previewSplitPatrolStats.value.noHealthCount > 0) {
    return "下一步建议：补齐健康采样后再做稳定性结论。";
  }
  return "下一步建议：保持当前四分屏巡检节奏并持续观察健康趋势。";
});

const previewPlaybackStabilityStats = computed(() => {
  if (splitCount.value === 4) {
    const loadedCount = slots.value.filter((x) => !!x.url).length;
    const failedCount = slots.value.filter((x) => !x.loading && !x.url && !!x.error).length;
    const lowHealthCount = slots.value.filter((x) => Number(x.health?.health_score || 0) > 0 && Number(x.health?.health_score || 0) < 60).length;
    const noHealthCount = slots.value.filter((x) => !!x.url && Number(x.health?.health_score || 0) <= 0).length;
    return { loadedCount, failedCount, lowHealthCount, noHealthCount };
  }
  const loadedCount = playUrl.value ? 1 : 0;
  const failedCount = !loading.value && !playUrl.value && !!errorText.value ? 1 : 0;
  const lowHealthCount = Number(health.value?.health_score || 0) > 0 && Number(health.value?.health_score || 0) < 60 ? 1 : 0;
  const noHealthCount = playUrl.value && Number(health.value?.health_score || 0) <= 0 ? 1 : 0;
  return { loadedCount, failedCount, lowHealthCount, noHealthCount };
});

const previewPlaybackStabilityNextStepAdvice = computed(() => {
  if (previewPlaybackStabilityStats.value.failedCount > 0) {
    return "下一步建议：优先刷新失败窗口并执行线路回退，确认播放链路恢复。";
  }
  if (previewPlaybackStabilityStats.value.lowHealthCount > 0) {
    return "下一步建议：优先处理低健康窗口，必要时切换到激进弱网策略。";
  }
  if (previewPlaybackStabilityStats.value.noHealthCount > 0) {
    return "下一步建议：补齐健康采样后再确认稳定性结论。";
  }
  return "下一步建议：播放稳定，保持当前巡检节奏并持续观察。";
});

const previewQualityReportSummaryText = computed(() => {
  const attempts = Number(qualityReportMetrics.value.attempts || 0);
  const successes = Number(qualityReportMetrics.value.successes || 0);
  const failures = Number(qualityReportMetrics.value.failures || 0);
  const rate = attempts <= 0 ? 0 : Number(((successes / attempts) * 100).toFixed(2));
  const lastAt = qualityReportMetrics.value.lastAt || "-";
  return `质量上报稳定性：尝试=${attempts}；成功=${successes}；失败=${failures}；成功率=${rate}%；最近状态=${qualityReportMetrics.value.lastStatus}；最近时间=${lastAt}`;
});

const previewQualityReportAdvice = computed(() => {
  const attempts = Number(qualityReportMetrics.value.attempts || 0);
  const failures = Number(qualityReportMetrics.value.failures || 0);
  if (attempts <= 0) return "下一步建议：先触发一次预览拉流并等待健康上报。";
  if (failures > 0 && qualityReportMetrics.value.lastStatus === "failed") {
    return "下一步建议：优先检查质量上报接口连通性与鉴权配置。";
  }
  if (failures > 0) return "下一步建议：复核历史失败原因并持续观察后续上报稳定性。";
  return "下一步建议：质量上报稳定，保持当前策略并持续巡检。";
});

const previewFallbackSummaryText = computed(() => {
  const currentChain =
    splitCount.value === 4 ? slots.value[activeSlot.value]?.fallbackChain || [] : fallbackChain.value || [];
  const currentIndex =
    splitCount.value === 4 ? Number(slots.value[activeSlot.value]?.fallbackIndex || 0) : Number(fallbackIndex.value || 0);
  const chainText = currentChain.length > 0 ? currentChain.map((x) => x.mode.toUpperCase()).join("/") : "-";
  const currentMode = currentChain.length > 0 ? currentChain[currentIndex % currentChain.length]?.mode?.toUpperCase() : playMode.value.toUpperCase();
  return `线路回退摘要：模式=${splitCount.value === 4 ? "四分屏" : "单屏"}；当前窗口=${activeSlot.value + 1}；当前线路=${currentMode || "-"}；可回退链路=${chainText}；链路数=${currentChain.length}`;
});

const previewFallbackAdvice = computed(() => {
  const currentChain = splitCount.value === 4 ? slots.value[activeSlot.value]?.fallbackChain || [] : fallbackChain.value || [];
  if (currentChain.length <= 0) return "下一步建议：当前无回退链路，先重试拉流并获取多线路地址。";
  if (currentChain.length === 1) return "下一步建议：仅单线路可用，建议补齐多线路能力以提升容灾性。";
  return "下一步建议：按链路顺序执行回退抽检，确认各线路可用性。";
});

const previewLoadFailureSummaryText = computed(() => {
  if (splitCount.value === 4) {
    const failed = slots.value
      .map((x, idx) => ({ idx, x }))
      .filter((row) => !row.x.loading && !row.x.url && !!row.x.error);
    const top3 = failed
      .slice(0, 3)
      .map((row) => `窗${row.idx + 1}`)
      .join("/");
    return `窗口加载失败：模式=四分屏；失败窗口=${failed.length}/4；失败Top3=${top3 || "-"}`;
  }
  const failed = !loading.value && !playUrl.value && !!errorText.value ? 1 : 0;
  return `窗口加载失败：模式=单屏；失败窗口=${failed}/1；失败Top3=${failed > 0 ? "窗1" : "-"}`;
});

const previewLoadFailureAdvice = computed(() => {
  if (previewLoadFailureSummaryText.value.includes("失败窗口=0/")) {
    return "下一步建议：当前无加载失败窗口，保持常规抽检即可。";
  }
  if (splitCount.value === 4) return "下一步建议：优先刷新失败窗口并执行线路回退，恢复四分屏完整性。";
  return "下一步建议：优先重试单屏拉流并检查设备在线状态与流媒体配置。";
});

function copyPreviewQualityReportSummary() {
  const text = [previewQualityReportSummaryText.value, previewQualityReportAdvice.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "质量上报摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyPreviewFallbackSummary() {
  const text = [previewFallbackSummaryText.value, previewFallbackAdvice.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "回退摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyPreviewLoadFailureSummary() {
  const text = [previewLoadFailureSummaryText.value, previewLoadFailureAdvice.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "加载失败摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyPreviewPlaybackStabilitySummary() {
  const text = [
    "播放稳定性摘要",
    `模式=${splitCount.value === 4 ? "四分屏" : "单屏"}`,
    `已加载窗口=${previewPlaybackStabilityStats.value.loadedCount}/${splitCount.value === 4 ? 4 : 1}`,
    `失败窗口=${previewPlaybackStabilityStats.value.failedCount}`,
    `低健康窗口=${previewPlaybackStabilityStats.value.lowHealthCount}`,
    `待补采样窗口=${previewPlaybackStabilityStats.value.noHealthCount}`,
    `当前弱网策略=${weakNetworkMode.value === "aggressive" ? "激进弱网（优先 HLS/FLV）" : "自动"}`,
    previewPlaybackStabilityNextStepAdvice.value
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "播放稳定性摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyPreviewSplitPatrolSummary() {
  const text = [
    "四分屏巡检摘要",
    `已加载窗口：${previewSplitPatrolStats.value.loadedCount}/4`,
    `主窗口：${activeSlot.value + 1}`,
    `平均健康分：${previewSplitPatrolStats.value.avgHealthScore || "-"}`,
    `低健康窗口：${previewSplitPatrolStats.value.lowHealthCount}`,
    `待补采样窗口：${previewSplitPatrolStats.value.noHealthCount}`,
    `当前弱网策略：${weakNetworkMode.value === "aggressive" ? "激进弱网（优先 HLS/FLV）" : "自动"}`,
    previewSplitPatrolNextStepAdvice.value
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "四分屏巡检摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

onLoad((query) => {
  if (typeof query?.deviceId === "string") deviceId.value = query.deviceId;
  if (typeof query?.channelId === "string") channelId.value = query.channelId;
  if (deviceId.value && channelId.value) startPreview();
});

onHide(stopHealthPolling);
onUnload(stopHealthPolling);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">实时预览</view>
    <view class="app-card app-gap-12">
      <input v-model="deviceId" placeholder="设备 ID" />
      <input v-model="channelId" placeholder="通道 ID" />
      <button type="primary" :loading="loading" @click="startPreview">开始预览</button>
      <view class="app-row">
        <button size="mini" @click="switchSplit(1)">单屏</button>
        <button size="mini" @click="switchSplit(4)">四分屏</button>
        <button size="mini" @click="fallbackNext">回退线路</button>
        <button size="mini" @click="loadLineOptions">重试线路</button>
        <button size="mini" @click="refreshHealthSample">重试健康采样</button>
      </view>
      <view class="app-subtext">线路状态：{{ lineOptionsLoadMessage }}</view>
      <view v-if="lineOptionsLastLoadedAt" class="app-subtext">线路时间：{{ lineOptionsLastLoadedAt }}</view>
      <view class="app-subtext">健康状态：{{ healthLoadMessage }}</view>
      <view v-if="healthLastLoadedAt" class="app-subtext">健康时间：{{ healthLastLoadedAt }}</view>
      <view class="app-row">
        <button
          size="mini"
          :type="weakNetworkMode === 'auto' ? 'primary' : 'default'"
          @click="() => { weakNetworkMode = 'auto'; saveWeakNetworkMode(); }"
        >
          弱网策略-自动
        </button>
        <button
          size="mini"
          :type="weakNetworkMode === 'aggressive' ? 'primary' : 'default'"
          @click="() => { weakNetworkMode = 'aggressive'; saveWeakNetworkMode(); }"
        >
          弱网策略-激进
        </button>
      </view>
      <view v-if="lineOptions.length" class="app-subtext">
        线路：{{ lineOptions.map((x) => `${x.name}${x.recommended ? "(推荐)" : ""}`).join(" / ") }}
      </view>
    </view>

    <view class="app-card app-gap-12">
      <view v-if="playUrl && splitCount === 1" class="app-gap-12">
        <view class="app-row">
          <text class="app-subtext">当前播放窗口（{{ activeSlot + 1 }}）</text>
          <AppStatusTag :text="playMode.toUpperCase()" :type="playMode === 'webrtc' ? 'success' : playMode === 'flv' ? 'warning' : 'info'" />
        </view>
        <AppStreamPlayer :url="playUrl" :mode="playMode" />
        <view v-if="health" class="app-row">
          <text class="app-subtext">健康评分：{{ health.health_score ?? "-" }}</text>
          <AppStatusTag :text="String(health.health_level || health.status || 'unknown')" :type="(health.health_score || 0) >= 85 ? 'success' : (health.health_score || 0) >= 60 ? 'warning' : 'danger'" />
        </view>
      </view>
      <text v-else class="app-subtext">暂未播放</text>
      <view v-if="errorText" style="margin-top: 12rpx; color: #ef4444">{{ errorText }}</view>
    </view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-title" style="font-size:30rpx">性能与弱网门禁</text>
        <AppStatusTag :text="previewPerfGate.pass ? '门禁通过' : '门禁未通过'" :type="previewPerfGate.pass ? 'success' : 'danger'" />
      </view>
      <text class="app-subtext">拉流尝试：{{ perfMetrics.attempts }} / 成功：{{ perfMetrics.successes }} / 失败：{{ perfMetrics.failures }}</text>
      <text class="app-subtext">平均启动耗时：{{ previewAvgStartupMs }} ms / 最近一次：{{ perfMetrics.lastStartupMs }} ms</text>
      <text class="app-subtext">成功率：{{ previewSuccessRate }}% / 当前策略：{{ weakNetworkMode === "aggressive" ? "激进弱网（优先 HLS/FLV）" : "自动" }}</text>
      <text class="app-subtext">门禁结果：{{ previewPerfGate.message }}</text>
      <text class="app-subtext">质量上报：{{ qualityReportMetrics.attempts }} 次 / 成功 {{ qualityReportMetrics.successes }} / 失败 {{ qualityReportMetrics.failures }}</text>
      <text class="app-subtext">质量上报最近：{{ qualityReportMetrics.lastMessage }} {{ qualityReportMetrics.lastAt ? `(${qualityReportMetrics.lastAt})` : "" }}</text>
      <text class="app-subtext">{{ previewPerfNextStepAdvice }}</text>
      <text class="app-subtext">{{ previewQualityReportSummaryText }}</text>
      <text class="app-subtext">{{ previewQualityReportAdvice }}</text>
      <text class="app-subtext">{{ previewFallbackSummaryText }}</text>
      <text class="app-subtext">{{ previewFallbackAdvice }}</text>
      <text class="app-subtext">{{ previewLoadFailureSummaryText }}</text>
      <text class="app-subtext">{{ previewLoadFailureAdvice }}</text>
      <text class="app-subtext">
        播放稳定：已加载 {{ previewPlaybackStabilityStats.loadedCount }}/{{ splitCount === 4 ? 4 : 1 }} / 失败 {{ previewPlaybackStabilityStats.failedCount }} / 低健康 {{ previewPlaybackStabilityStats.lowHealthCount }} / 待补采样 {{ previewPlaybackStabilityStats.noHealthCount }}
      </text>
      <text class="app-subtext">{{ previewPlaybackStabilityNextStepAdvice }}</text>
      <view class="app-row">
        <button size="mini" @click="copyPreviewPerfGateSummary">复制预览门禁摘要</button>
        <button size="mini" @click="copyPreviewQualityReportSummary">复制质量上报摘要</button>
        <button size="mini" @click="copyPreviewFallbackSummary">复制回退摘要</button>
        <button size="mini" @click="copyPreviewLoadFailureSummary">复制加载失败摘要</button>
        <button size="mini" @click="copyPreviewPlaybackStabilitySummary">复制播放稳定性摘要</button>
      </view>
    </view>

    <view v-if="splitCount === 4" class="app-card">
      <view class="app-row" style="margin-bottom: 8rpx">
        <text class="app-subtext">四分屏真实播放：已加载 {{ splitLoadedCount }}/4</text>
      </view>
      <text class="app-subtext">
        巡检统计：平均健康 {{ previewSplitPatrolStats.avgHealthScore || "-" }} / 低健康 {{ previewSplitPatrolStats.lowHealthCount }} / 待补采样 {{ previewSplitPatrolStats.noHealthCount }}
      </text>
      <text class="app-subtext">{{ previewSplitPatrolNextStepAdvice }}</text>
      <view class="app-row" style="margin-bottom: 8rpx">
        <button size="mini" @click="copyPreviewSplitPatrolSummary">复制四分屏巡检摘要</button>
      </view>
      <view style="display:grid;grid-template-columns:1fr 1fr;gap:12rpx;">
        <view
          v-for="(slot, idx) in slots"
          :key="idx"
          :style="`border:1rpx solid ${activeSlot === idx ? '#2563EB' : '#E2E8F0'};border-radius:12rpx;padding:12rpx;`"
          @click="switchSlot(idx)"
        >
          <view class="app-row">
            <text>窗口 {{ idx + 1 }}</text>
            <AppStatusTag
              :text="slot.url ? slot.mode.toUpperCase() : slot.loading ? '加载中' : '空'"
              :type="slot.url ? 'success' : slot.loading ? 'warning' : 'info'"
            />
          </view>
          <AppStreamPlayer v-if="slot.url" :url="slot.url" :mode="slot.mode" :height-rpx="220" :muted="idx !== activeSlot" />
          <text v-else class="app-subtext" selectable>{{ slot.loading ? "正在拉流..." : slot.error || "未加载流地址" }}</text>
          <view class="app-row" style="margin-top: 8rpx">
            <button size="mini" @click.stop="refreshSingleSlot(idx)">刷新本窗</button>
            <button size="mini" @click.stop="switchSlot(idx)">设为主窗</button>
          </view>
          <view v-if="slot.health" class="app-row" style="margin-top: 6rpx">
            <text class="app-subtext">健康：{{ slot.health.health_score ?? "-" }}</text>
            <AppStatusTag :text="String(slot.health.health_level || slot.health.status || 'unknown')" :type="(slot.health.health_score || 0) >= 85 ? 'success' : (slot.health.health_score || 0) >= 60 ? 'warning' : 'danger'" />
          </view>
        </view>
      </view>
    </view>

    <AppEmpty v-if="!loading && !playUrl && !errorText" text="输入设备和通道后开始实时预览" />
  </view>
</template>
