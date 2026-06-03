<script setup lang="ts">
import { onLoad, onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import {
  fetchInstalledPlugins,
  fetchPluginMenus,
  fetchPluginRuntimeConfig,
  fetchPluginRuntimeRows,
  fetchPluginShopUrl,
  fetchPurchasedPlugins,
  savePluginRuntimeConfig,
  type PluginInstalledItem,
  type PluginRuntimeField
} from "@/api/plugin-runtime";
import AppEmpty from "@/components/AppEmpty.vue";
import AppStatusTag from "@/components/AppStatusTag.vue";

const loading = ref(false);
const actionLoading = ref(false);
const installed = ref<PluginInstalledItem[]>([]);
const purchasedIds = ref<string[]>([]);
const menus = ref<Array<{ plugin_id: string; title?: string; frontend_url?: string | null }>>([]);
const shopUrl = ref("");
const selectedPluginId = ref("");
const runtimeSchema = ref<{ fields?: PluginRuntimeField[] } | null>(null);
const runtimeConfig = ref<Record<string, unknown>>({});
const runtimeRows = ref<any[]>([]);
const runtimeMeta = ref<Record<string, unknown> | null>(null);
const runtimeKind = ref<"events" | "logs" | "health">("events");
const keyword = ref("");
const page = ref(1);
const pageSize = ref(50);
const startAt = ref("");
const endAt = ref("");
const activeTab = ref<"plugins" | "config" | "runtime">("plugins");
const loadMessage = ref("未刷新");
const loadAt = ref("");
const pendingPluginId = ref("");
const pendingFocusField = ref("");

const runtimeKindByPluginId: Record<string, "events" | "logs" | "health"> = {
  stream_health: "health",
  sip_logger: "logs",
  network_watchdog: "events",
  stream_idle: "events",
  timelapse: "events",
  webhook_pusher: "events",
  s3_sync: "events",
  ptz_tour: "events",
  auto_record: "events",
  record_schedule_executor: "events",
  record_index_verifier: "events",
  snapshot_refresh: "events",
  rtmp_push_channel_monitor: "events",
  pull_proxy_monitor: "events",
  mqtt_bridge: "events",
  feishu_alert: "events",
  wecom_alert: "events",
  sms_alert: "events"
};

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

const selectedInstalled = computed(() => installed.value.find((x) => x.id === selectedPluginId.value) || null);

const summaryText = computed(() => {
  const boughtInstalled = installed.value.filter((x) => purchasedIds.value.includes(x.id)).length;
  return `插件运行：已安装=${installed.value.length}；已购买=${purchasedIds.value.length}；已购已装=${boughtInstalled}；当前插件=${selectedPluginId.value || "-"}`;
});

const nextStepAdvice = computed(() => {
  if (!selectedPluginId.value) return "下一步建议：先选择已安装插件，再查看配置与运行数据。";
  if (runtimeRows.value.length === 0) return "下一步建议：先保存运行配置并触发业务事件后，再刷新运行数据。";
  return "下一步建议：按关键字段筛选运行记录，验证插件是否稳定生效。";
});

const runtimeRowsText = computed(() => {
  if (!runtimeRows.value.length) return "暂无运行数据";
  const first = runtimeRows.value[0];
  const keys = Object.keys(first || {}).slice(0, 8);
  return `记录数=${runtimeRows.value.length}；示例字段=${keys.join(",") || "-"}`;
});

const runtimeFields = computed(() => {
  const fields = runtimeSchema.value?.fields;
  return Array.isArray(fields) ? fields : [];
});

function isPurchased(pluginId: string) {
  return purchasedIds.value.includes(pluginId);
}

function hasMenu(pluginId: string) {
  return menus.value.some((x) => x.plugin_id === pluginId);
}

function normalizeRuntimeKind(pluginId: string) {
  runtimeKind.value = runtimeKindByPluginId[pluginId] || "events";
}

async function loadBaseData() {
  loading.value = true;
  try {
    const [installedRes, purchasedRes, menusRes, shopRes] = await Promise.allSettled([
      fetchInstalledPlugins(),
      fetchPurchasedPlugins(),
      fetchPluginMenus(),
      fetchPluginShopUrl()
    ]);
    installed.value = installedRes.status === "fulfilled" && Array.isArray(installedRes.value) ? installedRes.value : [];
    purchasedIds.value = purchasedRes.status === "fulfilled" && Array.isArray(purchasedRes.value.plugin_ids) ? purchasedRes.value.plugin_ids : [];
    menus.value = menusRes.status === "fulfilled" && Array.isArray(menusRes.value) ? menusRes.value : [];
    shopUrl.value = shopRes.status === "fulfilled" ? String(shopRes.value.url || "") : "";
    const expectedPlugin = String(pendingPluginId.value || "").trim();
    if (expectedPlugin && installed.value.some((x) => x.id === expectedPlugin)) {
      selectedPluginId.value = expectedPlugin;
    } else if (!selectedPluginId.value && installed.value.length) {
      selectedPluginId.value = installed.value[0].id;
    }
    if (selectedPluginId.value && !installed.value.find((x) => x.id === selectedPluginId.value)) {
      selectedPluginId.value = installed.value[0]?.id || "";
    }
    if (selectedPluginId.value) normalizeRuntimeKind(selectedPluginId.value);
    const failedCount = [installedRes, purchasedRes, menusRes, shopRes].filter((x) => x.status === "rejected").length;
    if (failedCount > 0) {
      setLoadStatus(`部分刷新成功：失败 ${failedCount} 项`);
      uni.showToast({ title: `部分接口失败(${failedCount})`, icon: "none" });
    } else {
      setLoadStatus("刷新成功");
    }
  } catch (err: any) {
    installed.value = [];
    purchasedIds.value = [];
    menus.value = [];
    shopUrl.value = "";
    setLoadStatus(err?.message ? `刷新失败：${err.message}` : "刷新失败");
    uni.showToast({ title: "插件运行页加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

async function loadRuntimeConfig() {
  if (!selectedPluginId.value) {
    uni.showToast({ title: "请先选择插件", icon: "none" });
    return;
  }
  actionLoading.value = true;
  try {
    const res = await fetchPluginRuntimeConfig(selectedPluginId.value);
    runtimeSchema.value = res.schema || { fields: [] };
    runtimeConfig.value = res.config && typeof res.config === "object" ? { ...res.config } : {};
    uni.showToast({ title: "配置已加载", icon: "none" });
  } catch (err: any) {
    runtimeSchema.value = null;
    runtimeConfig.value = {};
    uni.showToast({ title: err?.message ? `加载失败：${err.message}` : "加载失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function saveRuntimeConfigAction() {
  if (!selectedPluginId.value) {
    uni.showToast({ title: "请先选择插件", icon: "none" });
    return;
  }
  actionLoading.value = true;
  try {
    await savePluginRuntimeConfig(selectedPluginId.value, runtimeConfig.value);
    uni.showToast({ title: "配置已保存", icon: "none" });
    await loadRuntimeConfig();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `保存失败：${err.message}` : "保存失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function loadRuntimeData() {
  if (!selectedPluginId.value) {
    uni.showToast({ title: "请先选择插件", icon: "none" });
    return;
  }
  actionLoading.value = true;
  try {
    const res = await fetchPluginRuntimeRows(selectedPluginId.value, runtimeKind.value, {
      page: page.value,
      page_size: pageSize.value,
      keyword: keyword.value || undefined,
      start_at: startAt.value || undefined,
      end_at: endAt.value || undefined,
      only_low_bitrate: runtimeKind.value === "health" ? true : undefined
    });
    const rows = Array.isArray(res.rows) ? res.rows : Array.isArray(res.items) ? res.items : Array.isArray(res.data) ? res.data : [];
    runtimeRows.value = rows;
    runtimeMeta.value = res.meta || null;
    uni.showToast({ title: `运行数据 ${rows.length} 条`, icon: "none" });
  } catch (err: any) {
    runtimeRows.value = [];
    runtimeMeta.value = null;
    uni.showToast({ title: err?.message ? `加载失败：${err.message}` : "加载失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

function selectPlugin(pluginId: string) {
  selectedPluginId.value = pluginId;
  normalizeRuntimeKind(pluginId);
  runtimeRows.value = [];
  runtimeSchema.value = null;
  runtimeConfig.value = {};
}

function openShop() {
  if (!shopUrl.value) {
    uni.showToast({ title: "未配置商城地址", icon: "none" });
    return;
  }
  uni.setClipboardData({
    data: shopUrl.value,
    success: () => uni.showToast({ title: "商城地址已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copySummary() {
  const text = [
    summaryText.value,
    `运行数据=${runtimeRows.value.length}；kind=${runtimeKind.value}`,
    nextStepAdvice.value,
    `刷新状态=${loadMessage.value || "-"}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "运行摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

onLoad((query) => {
  pendingPluginId.value = String(query?.pluginId || "");
  pendingFocusField.value = String(query?.focus_field || "");
});

onShow(async () => {
  await loadBaseData();
  if (pendingPluginId.value) {
    activeTab.value = "config";
    await loadRuntimeConfig();
    if (pendingFocusField.value) {
      uni.showToast({ title: `请关注字段：${pendingFocusField.value}`, icon: "none" });
    }
  }
});
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">插件运行中心</view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-subtext">{{ summaryText }}</text>
        <button size="mini" :loading="loading" @click="loadBaseData">刷新</button>
      </view>
      <text class="app-subtext">{{ nextStepAdvice }}</text>
      <text class="app-subtext">刷新状态：{{ loadMessage || "-" }}</text>
      <text class="app-subtext">状态时间：{{ loadAt || "-" }}</text>
      <view class="app-row">
        <button size="mini" @click="copySummary">复制摘要</button>
        <button size="mini" @click="openShop">复制商城地址</button>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <button size="mini" :type="activeTab === 'plugins' ? 'primary' : 'default'" @click="activeTab = 'plugins'">插件列表</button>
        <button size="mini" :type="activeTab === 'config' ? 'primary' : 'default'" @click="activeTab = 'config'">运行配置</button>
        <button size="mini" :type="activeTab === 'runtime' ? 'primary' : 'default'" @click="activeTab = 'runtime'">运行数据</button>
      </view>
    </view>

    <view v-if="activeTab === 'plugins'" class="app-card app-gap-12">
      <text class="app-subtext">已安装插件（{{ installed.length }}）</text>
      <view v-if="installed.length" class="app-gap-12">
        <view v-for="row in installed" :key="row.id" class="app-card">
          <view class="app-row">
            <text class="app-subtext">{{ row.name || row.id }}（{{ row.id }}）</text>
            <button size="mini" :type="selectedPluginId === row.id ? 'primary' : 'default'" @click="selectPlugin(row.id)">选择</button>
          </view>
          <view class="app-row">
            <AppStatusTag :text="isPurchased(row.id) ? '已购买' : '未购买'" :type="isPurchased(row.id) ? 'success' : 'warning'" />
            <AppStatusTag :text="hasMenu(row.id) ? '有运行入口' : '无菜单入口'" :type="hasMenu(row.id) ? 'info' : 'warning'" />
            <text class="app-subtext">版本：{{ row.version || "-" }}</text>
            <text class="app-subtext">类型：{{ row.type || "-" }}</text>
          </view>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '插件加载中...' : '暂无已安装插件'" />
    </view>

    <view v-else-if="activeTab === 'config'" class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-subtext">当前插件：{{ selectedPluginId || "-" }}</text>
        <button size="mini" :loading="actionLoading" :disabled="!selectedPluginId" @click="loadRuntimeConfig">加载配置</button>
      </view>
      <view v-if="runtimeFields.length" class="app-gap-12">
        <view v-for="f in runtimeFields" :key="f.key" class="app-gap-12">
          <text class="app-subtext">{{ f.label || f.key }}（{{ f.type || "string" }}）</text>
          <switch
            v-if="String(f.type || '').toLowerCase() === 'bool'"
            :checked="Boolean(runtimeConfig[f.key])"
            @change="(e:any) => (runtimeConfig[f.key] = Boolean(e?.detail?.value))"
          />
          <input
            v-else
            v-model="(runtimeConfig[f.key] as any)"
            class="app-input"
            :placeholder="`请输入 ${f.label || f.key}`"
          />
        </view>
      </view>
      <AppEmpty v-else :text="selectedPluginId ? '暂无可配置字段，请先加载配置' : '请先在插件列表选择插件'" />
      <view class="app-row">
        <button size="mini" type="primary" :loading="actionLoading" :disabled="!selectedPluginId" @click="saveRuntimeConfigAction">保存配置</button>
      </view>
    </view>

    <view v-else class="app-gap-12">
      <view class="app-card app-gap-12">
        <text class="app-subtext">运行数据筛选</text>
        <picker mode="selector" :range="['events', 'logs', 'health']" :value="runtimeKind === 'events' ? 0 : runtimeKind === 'logs' ? 1 : 2" @change="(e:any) => { const i=Number(e?.detail?.value || 0); runtimeKind = i === 1 ? 'logs' : i === 2 ? 'health' : 'events'; }">
          <view class="app-subtext">数据类型：{{ runtimeKind }}</view>
        </picker>
        <input v-model="keyword" class="app-input" placeholder="关键字（可空）" />
        <input v-model="startAt" class="app-input" placeholder="开始时间（ISO，可空）" />
        <input v-model="endAt" class="app-input" placeholder="结束时间（ISO，可空）" />
        <view class="app-row">
          <input v-model.number="page" type="number" class="app-input" placeholder="页码" />
          <input v-model.number="pageSize" type="number" class="app-input" placeholder="每页条数" />
        </view>
        <view class="app-row">
          <button size="mini" :loading="actionLoading" :disabled="!selectedPluginId" @click="loadRuntimeData">查询运行数据</button>
        </view>
      </view>

      <view class="app-card app-gap-12">
        <text class="app-subtext">运行结果：{{ runtimeRowsText }}</text>
        <text class="app-subtext">meta：{{ runtimeMeta ? JSON.stringify(runtimeMeta) : "-" }}</text>
        <view v-if="runtimeRows.length" class="app-gap-12">
          <view v-for="(row, idx) in runtimeRows.slice(0, 50)" :key="`runtime-${idx}`" class="app-card">
            <textarea :value="JSON.stringify(row, null, 2)" class="app-input" :maxlength="-1" disabled auto-height />
          </view>
        </view>
        <AppEmpty v-else :text="actionLoading ? '运行数据加载中...' : '暂无运行数据'" />
      </view>
    </view>
  </view>
</template>
