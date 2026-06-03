<script setup lang="ts">
import { onLoad, onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import {
  fetchInstalledPlugins,
  fetchPluginMarketplace,
  fetchPluginShopUrl,
  fetchPluginUninstallPreview,
  fetchPurchasedPlugins,
  installPluginFromMarketplace,
  uninstallPlugin,
  type MarketplacePluginItem,
  type PluginUninstallPreview
} from "@/api/plugin";
import AppEmpty from "@/components/AppEmpty.vue";
import AppStatusTag from "@/components/AppStatusTag.vue";

const loading = ref(false);
const actionLoading = ref(false);
const pluginId = ref("");
const marketplace = ref<MarketplacePluginItem[]>([]);
const installedIds = ref<string[]>([]);
const installedVersionMap = ref<Record<string, string>>({});
const purchasedIds = ref<string[]>([]);
const shopUrl = ref("");
const loadMessage = ref("未刷新");
const loadAt = ref("");
const uninstallPreview = ref<PluginUninstallPreview | null>(null);
const uninstallAckInput = ref("");
const preserveData = ref(false);

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

const plugin = computed(() => marketplace.value.find((x) => String(x.id || "") === pluginId.value) || null);

const summaryText = computed(() => {
  if (!plugin.value) return "插件详情：未找到目标插件";
  const id = String(plugin.value.id || "-");
  const installed = installedIds.value.includes(id) ? "是" : "否";
  const purchased = purchasedIds.value.includes(id) ? "是" : "否";
  const version = String(plugin.value.version || "-");
  const installedVersion = installedVersionMap.value[id] || "-";
  return `插件详情：ID=${id}；版本=${version}；已安装=${installed}(本地=${installedVersion})；已购买=${purchased}`;
});

const nextStepAdvice = computed(() => {
  if (!plugin.value) return "下一步建议：返回能力中心重新选择插件。";
  const id = String(plugin.value.id || "");
  const installed = installedIds.value.includes(id);
  const purchased = purchasedIds.value.includes(id);
  if (plugin.value.type === "paid" && !purchased) return "下一步建议：先购买该插件，再执行安装。";
  if (!installed) return "下一步建议：先执行安装，再进入运行中心验证配置与数据。";
  return "下一步建议：优先进入运行中心做配置回归与运行数据抽检。";
});

const pluginStatusText = computed(() => {
  if (!plugin.value) return "未找到";
  const id = String(plugin.value.id || "");
  if (!purchasedIds.value.includes(id) && plugin.value.type === "paid") return "待购买";
  if (!installedIds.value.includes(id)) return "待安装";
  return "已安装";
});

const pluginStatusType = computed<"success" | "warning" | "danger">(() => {
  if (!plugin.value) return "danger";
  const id = String(plugin.value.id || "");
  if (!purchasedIds.value.includes(id) && plugin.value.type === "paid") return "danger";
  if (!installedIds.value.includes(id)) return "warning";
  return "success";
});

async function loadData() {
  loading.value = true;
  try {
    const [marketRes, installedRes, purchasedRes, shopRes] = await Promise.allSettled([
      fetchPluginMarketplace(),
      fetchInstalledPlugins(),
      fetchPurchasedPlugins(),
      fetchPluginShopUrl()
    ]);
    marketplace.value = marketRes.status === "fulfilled" && Array.isArray(marketRes.value) ? marketRes.value : [];
    if (installedRes.status === "fulfilled" && Array.isArray(installedRes.value)) {
      installedIds.value = installedRes.value.map((x) => String(x.id || "")).filter(Boolean);
      const map: Record<string, string> = {};
      for (const row of installedRes.value) {
        const id = String(row.id || "");
        if (!id) continue;
        map[id] = String(row.version || "");
      }
      installedVersionMap.value = map;
    } else {
      installedIds.value = [];
      installedVersionMap.value = {};
    }
    purchasedIds.value = purchasedRes.status === "fulfilled" && Array.isArray(purchasedRes.value.plugin_ids) ? purchasedRes.value.plugin_ids : [];
    shopUrl.value = shopRes.status === "fulfilled" ? String(shopRes.value.url || "") : "";

    if (!pluginId.value && marketplace.value.length > 0) {
      pluginId.value = String(marketplace.value[0]?.id || "");
    }
    if (pluginId.value && !marketplace.value.find((x) => String(x.id || "") === pluginId.value)) {
      pluginId.value = String(marketplace.value[0]?.id || "");
    }

    uninstallPreview.value = null;
    uninstallAckInput.value = "";
    const failedCount = [marketRes, installedRes, purchasedRes, shopRes].filter((x) => x.status === "rejected").length;
    if (failedCount > 0) {
      setLoadStatus(`部分刷新成功：失败 ${failedCount} 项`);
      uni.showToast({ title: `部分接口失败(${failedCount})`, icon: "none" });
    } else {
      setLoadStatus("刷新成功");
    }
  } catch (err: any) {
    setLoadStatus(err?.message ? `刷新失败：${err.message}` : "刷新失败");
    uni.showToast({ title: "插件详情加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

function selectPlugin(id: string) {
  pluginId.value = id;
  uninstallPreview.value = null;
  uninstallAckInput.value = "";
}

function copyShopUrl() {
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
  const text = [summaryText.value, nextStepAdvice.value, `刷新状态=${loadMessage.value || "-"}`].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "插件摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

async function installCurrentPlugin() {
  if (!plugin.value) {
    uni.showToast({ title: "未选择插件", icon: "none" });
    return;
  }
  if (plugin.value.type === "paid" && !purchasedIds.value.includes(plugin.value.id)) {
    uni.showToast({ title: "该付费插件尚未购买", icon: "none" });
    return;
  }
  actionLoading.value = true;
  try {
    await installPluginFromMarketplace({
      plugin_id: plugin.value.id,
      package_url: plugin.value.package_url || null
    });
    uni.showToast({ title: "安装成功", icon: "none" });
    await loadData();
    uni.navigateTo({ url: `/pages/plugin-runtime/index?plugin_id=${encodeURIComponent(plugin.value.id)}` });
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `安装失败：${err.message}` : "安装失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function loadUninstallPreview() {
  if (!pluginId.value) {
    uni.showToast({ title: "请先选择插件", icon: "none" });
    return;
  }
  actionLoading.value = true;
  try {
    uninstallPreview.value = await fetchPluginUninstallPreview(pluginId.value);
    uninstallAckInput.value = "";
    uni.showToast({ title: "卸载预检已加载", icon: "none" });
  } catch (err: any) {
    uninstallPreview.value = null;
    uni.showToast({ title: err?.message ? `预检失败：${err.message}` : "预检失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function uninstallCurrentPlugin() {
  if (!pluginId.value) {
    uni.showToast({ title: "请先选择插件", icon: "none" });
    return;
  }
  if (!uninstallPreview.value?.ack_phrase) {
    uni.showToast({ title: "请先执行卸载预检", icon: "none" });
    return;
  }
  if (uninstallAckInput.value.trim() !== String(uninstallPreview.value.ack_phrase || "")) {
    uni.showToast({ title: "确认短语不匹配", icon: "none" });
    return;
  }
  const confirmRes = await uni.showModal({
    title: "确认卸载",
    content: "卸载后该插件功能将不可用，是否继续？",
    confirmText: "确认卸载",
    cancelText: "取消"
  });
  if (!confirmRes.confirm) return;

  actionLoading.value = true;
  try {
    await uninstallPlugin(pluginId.value, {
      confirm: true,
      confirm_phrase: uninstallAckInput.value.trim(),
      preserve_data: preserveData.value
    });
    uni.showToast({ title: "卸载成功", icon: "none" });
    uninstallPreview.value = null;
    uninstallAckInput.value = "";
    await loadData();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `卸载失败：${err.message}` : "卸载失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

onLoad((options) => {
  const id = String(options?.plugin_id || "").trim();
  if (id) pluginId.value = id;
});

onShow(loadData);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">插件详情</view>

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
        <button size="mini" @click="copyShopUrl">复制商城地址</button>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">插件选择（{{ marketplace.length }}）</text>
      <view class="app-row">
        <picker
          mode="selector"
          :range="marketplace.map((x) => `${x.name || x.title || x.id} (${x.id})`)"
          :value="Math.max(0, marketplace.findIndex((x) => String(x.id || '') === pluginId))"
          @change="
            (e:any) => {
              const i = Number(e?.detail?.value || 0);
              const row = marketplace[i];
              if (row?.id) selectPlugin(String(row.id));
            }
          "
        >
          <view class="app-subtext">当前插件：{{ pluginId || '-' }}</view>
        </picker>
      </view>
    </view>

    <view v-if="plugin" class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-subtext">{{ plugin.name || plugin.title || plugin.id }}</text>
        <AppStatusTag :text="pluginStatusText" :type="pluginStatusType" />
      </view>
      <view class="app-row">
        <AppStatusTag :text="plugin.type === 'paid' ? '付费插件' : '免费插件'" :type="plugin.type === 'paid' ? 'warning' : 'success'" />
        <AppStatusTag :text="plugin.status === 'deprecated' ? '已废弃' : '可用'" :type="plugin.status === 'deprecated' ? 'danger' : 'info'" />
      </view>
      <text class="app-subtext">插件ID：{{ plugin.id }}</text>
      <text class="app-subtext">版本：{{ plugin.version || "-" }}</text>
      <text class="app-subtext">已装版本：{{ installedVersionMap[plugin.id] || "-" }}</text>
      <text class="app-subtext">价格：{{ plugin.type === "paid" ? `¥${plugin.price_monthly || 0}/月` : "免费" }}</text>
      <text class="app-subtext">描述：{{ plugin.description || "-" }}</text>
      <text class="app-subtext">详情：{{ plugin.detail || "-" }}</text>
      <text class="app-subtext">文档：{{ plugin.doc_url || "-" }}</text>
      <text v-if="plugin.deprecated_message" class="app-subtext">废弃说明：{{ plugin.deprecated_message }}</text>
      <view class="app-row">
        <button
          size="mini"
          type="primary"
          :loading="actionLoading"
          :disabled="plugin.type === 'paid' && !purchasedIds.includes(plugin.id)"
          @click="installCurrentPlugin"
        >
          {{ installedIds.includes(plugin.id) ? "重新安装" : "安装插件" }}
        </button>
        <button size="mini" :disabled="!installedIds.includes(plugin.id)" @click="loadUninstallPreview">卸载预检</button>
        <button size="mini" :disabled="!installedIds.includes(plugin.id)" :loading="actionLoading" @click="uninstallCurrentPlugin">执行卸载</button>
      </view>
      <text v-if="plugin.type === 'paid' && !purchasedIds.includes(plugin.id)" class="app-subtext">提示：该插件为付费插件，请先在商城完成购买。</text>
    </view>
    <AppEmpty v-else :text="loading ? '插件详情加载中...' : '未找到插件详情'" />

    <view class="app-card app-gap-12">
      <text class="app-subtext">卸载保护</text>
      <text class="app-subtext">数据保留策略：{{ preserveData ? "保留数据表" : "按插件策略处理数据表" }}</text>
      <switch :checked="preserveData" @change="(e:any) => (preserveData = Boolean(e?.detail?.value))" />
      <text class="app-subtext">确认短语（需与预检返回一致）</text>
      <input v-model="uninstallAckInput" class="app-input" placeholder="请输入确认短语" />
      <text class="app-subtext">预检确认短语：{{ uninstallPreview?.ack_phrase || "-" }}</text>
      <text class="app-subtext">风险等级：{{ uninstallPreview?.risk_level || "-" }}</text>
      <text class="app-subtext">影响摘要：{{ uninstallPreview?.impact_summary || "-" }}</text>
      <text class="app-subtext">关联表数量：{{ uninstallPreview?.table_count ?? "-" }}</text>
      <text class="app-subtext">运行配置行数：{{ uninstallPreview?.runtime_config_rows ?? "-" }}</text>
    </view>
  </view>
</template>
