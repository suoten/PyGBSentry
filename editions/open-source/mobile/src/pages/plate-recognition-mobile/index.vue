<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import {
  fetchRecognitionEvents,
  fetchRecognitionRuntimeConfig,
  saveRecognitionRuntimeConfig,
  type RecognitionEventItem,
  type RecognitionRuntimeConfig
} from "@/api/ai-recognition";
import AppEmpty from "@/components/AppEmpty.vue";
import AppStatusTag from "@/components/AppStatusTag.vue";

const pluginId = "plate_recognition_suite";

const loading = ref(false);
const saving = ref(false);
const eventsLoading = ref(false);
const enabled = ref(false);
const config = ref<RecognitionRuntimeConfig>({});
const events = ref<RecognitionEventItem[]>([]);
const total = ref(0);
const loadMessage = ref("未刷新");
const loadAt = ref("");

const editAiCallbackUrl = ref("");
const editSyncUrls = ref("");
const editSendSnapshot = ref(false);
const editTimeoutSeconds = ref(10);

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

function normalizeSyncUrls(v: unknown): string {
  if (v == null) return "";
  if (Array.isArray(v)) return v.filter(Boolean).map((x) => String(x)).join(", ");
  return String(v);
}

const summaryText = computed(() => {
  return `车牌识别：状态=${enabled.value ? "启用" : "停用"}；事件=${events.value.length}/${total.value}；回调=${String(config.value.ai_callback_url || "未配置")}`;
});

const nextStepAdvice = computed(() => {
  if (enabled.value && !String(config.value.ai_callback_url || "").trim()) return "下一步建议：启用状态下请先配置回调地址。";
  if (!events.value.length) return "下一步建议：先触发车牌识别样本，再刷新事件列表验证回传链路。";
  return "下一步建议：抽检最新识别记录与车牌字段，确认回调结果完整。";
});

function openEdit() {
  editAiCallbackUrl.value = String(config.value.ai_callback_url || "");
  editSyncUrls.value = normalizeSyncUrls(config.value.sync_urls);
  editSendSnapshot.value = Boolean(config.value.send_snapshot_url);
  editTimeoutSeconds.value = Number(config.value.timeout_seconds || 10);
}

async function loadConfig() {
  try {
    const res = await fetchRecognitionRuntimeConfig(pluginId);
    const cfg = res?.config && typeof res.config === "object" ? res.config : {};
    config.value = cfg;
    enabled.value = Boolean(cfg.enabled);
    openEdit();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `配置加载失败：${err.message}` : "配置加载失败", icon: "none" });
  }
}

async function loadEvents() {
  eventsLoading.value = true;
  try {
    const res = await fetchRecognitionEvents("plate", 50);
    events.value = Array.isArray(res.items) ? res.items : [];
    total.value = Number(res.total || events.value.length || 0);
  } catch (err: any) {
    events.value = [];
    total.value = 0;
    uni.showToast({ title: err?.message ? `事件加载失败：${err.message}` : "事件加载失败", icon: "none" });
  } finally {
    eventsLoading.value = false;
  }
}

async function loadAll() {
  loading.value = true;
  try {
    await Promise.allSettled([loadConfig(), loadEvents()]);
    setLoadStatus("刷新成功");
  } catch (err: any) {
    setLoadStatus(err?.message ? `刷新失败：${err.message}` : "刷新失败");
  } finally {
    loading.value = false;
  }
}

async function toggleEnabled() {
  const nextValue = !enabled.value;
  try {
    await saveRecognitionRuntimeConfig(pluginId, { enabled: nextValue });
    enabled.value = nextValue;
    config.value = { ...config.value, enabled: nextValue };
    uni.showToast({ title: nextValue ? "已启用" : "已停用", icon: "none" });
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `操作失败：${err.message}` : "操作失败", icon: "none" });
  }
}

async function saveConfig() {
  if (enabled.value && !editAiCallbackUrl.value.trim()) {
    uni.showToast({ title: "启用状态需配置回调地址", icon: "none" });
    return;
  }
  saving.value = true;
  try {
    const payload: RecognitionRuntimeConfig = {
      enabled: enabled.value,
      ai_callback_url: editAiCallbackUrl.value.trim(),
      sync_urls: editSyncUrls.value.trim(),
      send_snapshot_url: editSendSnapshot.value,
      timeout_seconds: Math.max(1, Math.min(60, Number(editTimeoutSeconds.value || 10)))
    };
    await saveRecognitionRuntimeConfig(pluginId, payload);
    await loadConfig();
    uni.showToast({ title: "配置已保存", icon: "none" });
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `保存失败：${err.message}` : "保存失败", icon: "none" });
  } finally {
    saving.value = false;
  }
}

function eventTimeText(row: RecognitionEventItem) {
  return String(row.event_time || row.created_at || "-");
}

function eventSummary(row: RecognitionEventItem) {
  const payload = String(row.payload || "");
  if (payload.length <= 100) return payload || "-";
  return `${payload.slice(0, 100)}...`;
}

function copySummary() {
  const text = [summaryText.value, nextStepAdvice.value, `刷新状态=${loadMessage.value || "-"}`].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "车牌识别摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

onShow(loadAll);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">车牌识别</view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <view>
          <text class="app-subtext">当前状态：{{ enabled ? "已启用" : "未启用" }}</text>
          <text class="app-subtext">{{ summaryText }}</text>
        </view>
        <view class="app-row">
          <AppStatusTag :text="enabled ? '启用' : '停用'" :type="enabled ? 'success' : 'warning'" />
          <button size="mini" :loading="loading" @click="toggleEnabled">{{ enabled ? "停用" : "启用" }}</button>
        </view>
      </view>
      <text class="app-subtext">{{ nextStepAdvice }}</text>
      <text class="app-subtext">刷新状态：{{ loadMessage || "-" }}</text>
      <text class="app-subtext">状态时间：{{ loadAt || "-" }}</text>
      <view class="app-row">
        <button size="mini" :loading="loading" @click="loadAll">刷新</button>
        <button size="mini" @click="copySummary">复制摘要</button>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">回调配置</text>
      <input v-model="editAiCallbackUrl" class="app-input" placeholder="http(s)://车牌识别分析服务API地址" />
      <input v-model="editSyncUrls" class="app-input" placeholder="同步通知地址（逗号分隔，可空）" />
      <view class="app-row">
        <text class="app-subtext">推送截图 URL</text>
        <switch :checked="editSendSnapshot" @change="(e:any) => (editSendSnapshot = Boolean(e?.detail?.value))" />
      </view>
      <view class="app-row">
        <text class="app-subtext">请求超时（秒）</text>
        <input v-model.number="editTimeoutSeconds" type="number" class="app-input" placeholder="1-60" />
      </view>
      <view class="app-row">
        <button size="mini" type="primary" :loading="saving" @click="saveConfig">保存配置</button>
      </view>
      <text class="app-subtext">当前回调：{{ String(config.ai_callback_url || "未配置") }}</text>
      <text class="app-subtext">当前同步地址：{{ normalizeSyncUrls(config.sync_urls) || "未配置" }}</text>
      <text class="app-subtext">当前超时：{{ Number(config.timeout_seconds || 10) }} 秒</text>
    </view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-subtext">最近推送记录（{{ events.length }} / {{ total }}）</text>
        <button size="mini" :loading="eventsLoading" @click="loadEvents">刷新记录</button>
      </view>
      <view v-if="events.length" class="app-gap-12">
        <view v-for="row in events" :key="row.id" class="app-card">
          <text class="app-subtext">时间：{{ eventTimeText(row) }}</text>
          <text class="app-subtext">设备：{{ row.device_id || "-" }}；通道：{{ row.channel_id || "-" }}</text>
          <text class="app-subtext">来源：{{ row.source_plugin || "-" }}</text>
          <textarea :value="eventSummary(row)" class="app-input" auto-height :maxlength="-1" disabled />
        </view>
      </view>
      <AppEmpty v-else :text="eventsLoading ? '事件加载中...' : '暂无推送记录'" />
    </view>
  </view>
</template>
