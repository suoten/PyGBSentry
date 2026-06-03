<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import { fetchAlarmNotifications, triggerAlertChannelTest, type AlarmNotificationItem } from "@/api/alarm";
import AppStatusTag from "@/components/AppStatusTag.vue";
import AppEmpty from "@/components/AppEmpty.vue";

const loading = ref(false);
const channelFilter = ref<"" | "sms" | "wecom" | "feishu">("");
const statusFilter = ref<"" | "success" | "fail">("");
const timeWindow = ref<"24h" | "7d">("24h");
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);
const rows = ref<AlarmNotificationItem[]>([]);
const loadMessage = ref("未刷新");
const loadAt = ref("");
const selectedNotificationId = ref("");
const retryLoading = ref(false);

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

function channelLabel(channel: string) {
  if (channel === "sms") return "短信";
  if (channel === "wecom") return "企业微信";
  if (channel === "feishu") return "飞书";
  return channel || "-";
}

function statusLabel(status: string) {
  return status === "success" ? "成功" : "失败";
}

function statusTagType(status: string): "success" | "danger" {
  return status === "success" ? "success" : "danger";
}

function buildTimeRange() {
  const end = new Date();
  const start = new Date(end.getTime() - (timeWindow.value === "24h" ? 24 : 24 * 7) * 60 * 60 * 1000);
  return { startISO: start.toISOString(), endISO: end.toISOString() };
}

const summaryText = computed(() => {
  const channel = channelFilter.value ? channelLabel(channelFilter.value) : "全部";
  const status = statusFilter.value ? statusLabel(statusFilter.value) : "全部";
  const windowText = timeWindow.value === "24h" ? "近24小时" : "近7天";
  return `通知记录：总数=${total.value}；当前页=${rows.value.length}；渠道=${channel}；状态=${status}；窗口=${windowText}`;
});

const statusStatsText = computed(() => {
  let ok = 0;
  let fail = 0;
  for (const row of rows.value) {
    if (String(row.status) === "success") ok += 1;
    else fail += 1;
  }
  const totalNow = rows.value.length;
  const failRate = totalNow <= 0 ? 0 : Math.round((fail / totalNow) * 100);
  return `当前页状态：成功=${ok}；失败=${fail}；失败率=${failRate}%`;
});

const nextStepAdviceText = computed(() => {
  const failCount = rows.value.filter((x) => String(x.status) !== "success").length;
  if (failCount > 0) return "下一步建议：优先查看失败记录，核对错误信息并回查渠道配置。";
  return "下一步建议：当前页通知发送正常，保持抽样巡检。";
});

const selectedNotification = computed(() => {
  if (!rows.value.length) return null;
  const found = rows.value.find((x) => x.id === selectedNotificationId.value);
  return found || rows.value[0];
});

const selectedTroubleshooting = computed(() => {
  const row = selectedNotification.value;
  if (!row || row.status === "success") return null;
  const channel = String(row.channel || "");
  const err = String(row.error_message || "").toLowerCase();
  const steps: string[] = [];
  let title = `${channelLabel(channel)} 通知排障建议`;
  let summary = "建议核对插件运行配置与网络连通性，再执行一次通道测试。";
  let fieldKey = "default";
  if (err.includes("timeout") || err.includes("timed out")) {
    summary = "检测到超时错误，通常与目标地址不可达或回包过慢有关。";
    steps.push("检查目标平台地址是否可达，确认 DNS 与防火墙策略。");
    steps.push("在插件运行配置中适当提高超时时间并重试。");
    fieldKey = "timeout_seconds";
  } else if (err.includes("auth") || err.includes("401") || err.includes("403")) {
    summary = "检测到认证失败，通常与密钥、Token 或签名配置不一致有关。";
    steps.push("核对对应渠道的密钥、Token、签名字段是否为最新值。");
    steps.push("确认发送账号权限与应用可见范围。");
    fieldKey = "auth";
  } else if (err.includes("url") || err.includes("host") || err.includes("dns") || err.includes("connect")) {
    summary = "检测到地址/连接异常，建议优先核对回调地址与网络出口策略。";
    steps.push("检查渠道 API 地址、端口与协议是否正确。");
    steps.push("确认网关或代理策略未拦截目标域名。");
    fieldKey = "endpoint";
  } else {
    steps.push("核对渠道基础配置（地址、密钥、超时）并保存。");
    steps.push("执行重发测试并观察最新通知记录是否恢复成功。");
  }
  return { title, summary, steps, fieldKey };
});

function copySummary() {
  const text = [summaryText.value, statusStatsText.value, nextStepAdviceText.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "通知摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

async function loadNotifications() {
  loading.value = true;
  try {
    const { startISO, endISO } = buildTimeRange();
    const res = await fetchAlarmNotifications({
      skip: (page.value - 1) * pageSize.value,
      limit: pageSize.value,
      channel: channelFilter.value,
      status: statusFilter.value,
      start_time: startISO,
      end_time: endISO
    });
    rows.value = Array.isArray(res?.items) ? res.items : [];
    total.value = Number(res?.total || 0);
    if (!rows.value.length) {
      selectedNotificationId.value = "";
    } else if (!rows.value.some((x) => x.id === selectedNotificationId.value)) {
      selectedNotificationId.value = rows.value[0].id;
    }
    setLoadStatus(`刷新成功：${rows.value.length} 条`);
  } catch (err: any) {
    const reason = err?.message ? String(err.message) : "请稍后重试";
    setLoadStatus(`刷新失败：${reason}`);
    uni.showToast({ title: "通知记录加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

function selectNotification(row: AlarmNotificationItem) {
  selectedNotificationId.value = row.id;
}

function channelPluginId(channel: string) {
  if (channel === "sms") return "sms_notifier";
  if (channel === "wecom") return "wecom_notifier";
  if (channel === "feishu") return "feishu_notifier";
  return "";
}

function openPluginRuntime(fieldKey = "") {
  const row = selectedNotification.value;
  if (!row) return;
  const pluginId = channelPluginId(String(row.channel || ""));
  if (!pluginId) {
    uni.showToast({ title: "当前渠道暂无插件映射", icon: "none" });
    return;
  }
  const query = fieldKey ? `?focus_field=${encodeURIComponent(fieldKey)}` : "";
  uni.navigateTo({
    url: `/pages/plugin-runtime/index?pluginId=${encodeURIComponent(pluginId)}${query}`
  });
}

async function retrySelectedChannelTest() {
  const row = selectedNotification.value;
  if (!row) return;
  const pluginId = channelPluginId(String(row.channel || ""));
  if (!pluginId) {
    uni.showToast({ title: "当前渠道不支持测试", icon: "none" });
    return;
  }
  retryLoading.value = true;
  try {
    const res = await triggerAlertChannelTest(pluginId);
    uni.showToast({ title: res?.message || "测试已触发", icon: "none" });
    await loadNotifications();
    const latest = rows.value.find((x) => x.channel === row.channel);
    if (latest?.id) selectedNotificationId.value = latest.id;
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `测试失败：${err.message}` : "测试失败", icon: "none" });
  } finally {
    retryLoading.value = false;
  }
}

function copySelectedNotification() {
  const row = selectedNotification.value;
  if (!row) return;
  const text = [
    `通知ID=${row.id}`,
    `渠道=${channelLabel(row.channel)}`,
    `状态=${statusLabel(row.status)}`,
    `发送时间=${row.sent_at || "-"}`,
    `设备=${row.device_id || "-"}`,
    `通道=${row.channel_id || "-"}`,
    `错误=${row.error_message || "无"}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "记录详情已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

async function onChannelChange(index: number) {
  channelFilter.value = index === 1 ? "sms" : index === 2 ? "wecom" : index === 3 ? "feishu" : "";
  page.value = 1;
  await loadNotifications();
}

async function onStatusChange(index: number) {
  statusFilter.value = index === 1 ? "success" : index === 2 ? "fail" : "";
  page.value = 1;
  await loadNotifications();
}

async function onWindowChange(index: number) {
  timeWindow.value = index === 1 ? "7d" : "24h";
  page.value = 1;
  await loadNotifications();
}

async function onPageSizeChange(index: number) {
  pageSize.value = index === 1 ? 50 : index === 2 ? 100 : 20;
  page.value = 1;
  await loadNotifications();
}

async function prevPage() {
  if (page.value <= 1) return;
  page.value -= 1;
  await loadNotifications();
}

async function nextPage() {
  const maxPage = Math.max(1, Math.ceil(total.value / pageSize.value));
  if (page.value >= maxPage) return;
  page.value += 1;
  await loadNotifications();
}

onShow(loadNotifications);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">告警通知记录</view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-subtext">{{ summaryText }}</text>
        <button size="mini" :loading="loading" @click="loadNotifications">刷新</button>
      </view>
      <view class="app-row">
        <picker mode="selector" :range="['全部渠道', '短信', '企业微信', '飞书']" @change="(e:any)=>onChannelChange(Number(e?.detail?.value||0))">
          <view class="app-subtext">渠道：{{ channelFilter ? channelLabel(channelFilter) : "全部" }}</view>
        </picker>
        <picker mode="selector" :range="['全部状态', '成功', '失败']" @change="(e:any)=>onStatusChange(Number(e?.detail?.value||0))">
          <view class="app-subtext">状态：{{ statusFilter ? statusLabel(statusFilter) : "全部" }}</view>
        </picker>
      </view>
      <view class="app-row">
        <picker mode="selector" :range="['近24小时', '近7天']" :value="timeWindow === '24h' ? 0 : 1" @change="(e:any)=>onWindowChange(Number(e?.detail?.value||0))">
          <view class="app-subtext">时间窗口：{{ timeWindow === "24h" ? "近24小时" : "近7天" }}</view>
        </picker>
        <picker mode="selector" :range="['20条/页', '50条/页', '100条/页']" :value="pageSize === 20 ? 0 : pageSize === 50 ? 1 : 2" @change="(e:any)=>onPageSizeChange(Number(e?.detail?.value||0))">
          <view class="app-subtext">每页：{{ pageSize }}</view>
        </picker>
      </view>
      <text class="app-subtext">{{ statusStatsText }}</text>
      <text class="app-subtext">{{ nextStepAdviceText }}</text>
      <text class="app-subtext">刷新状态：{{ loadMessage || "-" }}</text>
      <text v-if="loadAt" class="app-subtext">状态时间：{{ loadAt }}</text>
      <view class="app-row">
        <button size="mini" @click="copySummary">复制通知摘要</button>
        <button size="mini" :disabled="page <= 1" @click="prevPage">上一页</button>
        <button size="mini" :disabled="page >= Math.max(1, Math.ceil(total / pageSize))" @click="nextPage">下一页</button>
        <text class="app-subtext">第 {{ page }} / {{ Math.max(1, Math.ceil(total / pageSize)) }} 页</text>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <view v-if="rows.length" class="app-gap-12">
        <view v-for="row in rows" :key="row.id" class="app-row">
          <view style="flex:1">
            <text class="app-subtext">发送时间：{{ row.sent_at || "-" }}</text>
            <text class="app-subtext">渠道：{{ channelLabel(row.channel) }} / 状态：{{ statusLabel(row.status) }}</text>
            <text class="app-subtext">设备：{{ row.device_id || "-" }} / 通道：{{ row.channel_id || "-" }}</text>
            <text class="app-subtext">描述：{{ row.description || "-" }}</text>
            <text class="app-subtext">错误：{{ row.error_message || "无" }}</text>
          </view>
          <view class="app-gap-12">
            <AppStatusTag :text="statusLabel(row.status)" :type="statusTagType(row.status)" />
            <button size="mini" @click="selectNotification(row)">详情</button>
          </view>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '通知记录加载中...' : '当前筛选下暂无通知记录'" />
    </view>

    <view v-if="selectedNotification" class="app-card app-gap-12">
      <text class="app-subtext">记录详情</text>
      <text class="app-subtext">通知ID：{{ selectedNotification.id }}</text>
      <text class="app-subtext">发送时间：{{ selectedNotification.sent_at || "-" }}</text>
      <text class="app-subtext">渠道：{{ channelLabel(selectedNotification.channel) }}</text>
      <text class="app-subtext">状态：{{ statusLabel(selectedNotification.status) }}</text>
      <text class="app-subtext">告警ID：{{ selectedNotification.alarm_id || "-" }}</text>
      <text class="app-subtext">设备：{{ selectedNotification.device_id || "-" }} / 通道：{{ selectedNotification.channel_id || "-" }}</text>
      <text class="app-subtext">描述：{{ selectedNotification.description || "-" }}</text>
      <text class="app-subtext">错误：{{ selectedNotification.error_message || "无" }}</text>
      <view class="app-row">
        <button size="mini" @click="copySelectedNotification">复制详情</button>
        <button size="mini" @click="openPluginRuntime()">插件运行页</button>
      </view>
    </view>

    <view v-if="selectedTroubleshooting" class="app-card app-gap-12">
      <text class="app-subtext">{{ selectedTroubleshooting.title }}</text>
      <text class="app-subtext">{{ selectedTroubleshooting.summary }}</text>
      <view class="app-gap-12">
        <text v-for="(step, idx) in selectedTroubleshooting.steps" :key="`step-${idx}`" class="app-subtext">{{ idx + 1 }}. {{ step }}</text>
      </view>
      <view class="app-row">
        <button size="mini" @click="openPluginRuntime(selectedTroubleshooting.fieldKey)">定位配置项</button>
        <button size="mini" type="primary" :loading="retryLoading" @click="retrySelectedChannelTest">重新发送测试</button>
      </view>
    </view>
  </view>
</template>
