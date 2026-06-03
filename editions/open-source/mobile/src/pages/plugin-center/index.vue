<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import {
  fetchInstalledPlugins,
  fetchMobileEntries,
  fetchPluginMenus,
  fetchPluginShopUrl,
  fetchPurchasedPlugins
} from "@/api/plugin";
import AppEmpty from "@/components/AppEmpty.vue";
import AppStatusTag from "@/components/AppStatusTag.vue";

type MatrixRow = {
  plugin_id: string;
  name: string;
  platforms: string[];
  entry_url: string;
  purchased: boolean;
  installed: boolean;
  hasMenu: boolean;
};

const loading = ref(false);
const entries = ref<any[]>([]);
const purchasedIds = ref<string[]>([]);
const installedIds = ref<string[]>([]);
const menuPluginIds = ref<string[]>([]);
const shopUrl = ref("");
const keyword = ref("");
const platformFilter = ref<"" | "mobile" | "miniprogram">("");
const statusFilter = ref<"" | "usable" | "need_install" | "need_purchase">("");
const loadMessage = ref("未刷新");
const loadAt = ref("");

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

function resolveEntryUrl(row: any) {
  const raw = String(row?.entry_url || row?.entry_url_template || "").trim();
  if (!raw) return "";
  return raw
    .replace(/\{plugin_id\}/g, encodeURIComponent(String(row?.plugin_id || "")))
    .replace(/\{platform\}/g, encodeURIComponent(String(row?.platform || "")))
    .replace(/\{base_url\}/g, "")
    .replace(/\{token\}/g, "")
    .replace(/\{tenant_id\}/g, "");
}

const matrixRows = computed<MatrixRow[]>(() => {
  const grouped = new Map<string, MatrixRow>();
  for (const item of entries.value) {
    const pid = String(item?.plugin_id || "");
    if (!pid) continue;
    const current = grouped.get(pid);
    const nextUrl = resolveEntryUrl(item);
    if (!current) {
      grouped.set(pid, {
        plugin_id: pid,
        name: String(item?.name || pid),
        platforms: [String(item?.platform || "mobile")],
        entry_url: nextUrl,
        purchased: purchasedIds.value.includes(pid),
        installed: installedIds.value.includes(pid),
        hasMenu: menuPluginIds.value.includes(pid)
      });
      continue;
    }
    if (!current.platforms.includes(String(item?.platform || "mobile"))) {
      current.platforms.push(String(item?.platform || "mobile"));
    }
    if (!current.entry_url && nextUrl) current.entry_url = nextUrl;
    current.purchased = current.purchased || purchasedIds.value.includes(pid);
    current.installed = current.installed || installedIds.value.includes(pid);
    current.hasMenu = current.hasMenu || menuPluginIds.value.includes(pid);
  }
  return Array.from(grouped.values()).sort((a, b) => a.name.localeCompare(b.name, "zh-Hans-CN"));
});

const filteredRows = computed(() => {
  const kw = keyword.value.trim().toLowerCase();
  return matrixRows.value.filter((row) => {
    if (platformFilter.value && !row.platforms.includes(platformFilter.value)) return false;
    const usable = row.purchased && row.installed && !!row.entry_url;
    const needInstall = row.purchased && !row.installed;
    const needPurchase = !row.purchased;
    if (statusFilter.value === "usable" && !usable) return false;
    if (statusFilter.value === "need_install" && !needInstall) return false;
    if (statusFilter.value === "need_purchase" && !needPurchase) return false;
    if (!kw) return true;
    return row.name.toLowerCase().includes(kw) || row.plugin_id.toLowerCase().includes(kw);
  });
});

const summaryText = computed(() => {
  const total = matrixRows.value.length;
  const usable = matrixRows.value.filter((x) => x.purchased && x.installed && !!x.entry_url).length;
  const needInstall = matrixRows.value.filter((x) => x.purchased && !x.installed).length;
  const needPurchase = matrixRows.value.filter((x) => !x.purchased).length;
  return `插件中心：能力=${total}；可用=${usable}；待安装=${needInstall}；待购买=${needPurchase}`;
});

const nextStepAdvice = computed(() => {
  const needInstall = matrixRows.value.filter((x) => x.purchased && !x.installed).length;
  const needPurchase = matrixRows.value.filter((x) => !x.purchased).length;
  if (needPurchase > 0) return "下一步建议：先在计费中心完成插件购买，再返回安装与验证入口。";
  if (needInstall > 0) return "下一步建议：先安装已购买插件，再检查入口可达性与运行数据。";
  return "下一步建议：优先抽检有菜单入口的插件，验证运行配置与数据回传。";
});

function rowStatusText(row: MatrixRow) {
  if (!row.purchased) return "待购买";
  if (!row.installed) return "待安装";
  if (!row.entry_url) return "已安装未配置入口";
  return "可用";
}

function rowStatusType(row: MatrixRow): "success" | "warning" | "danger" | "info" {
  if (!row.purchased) return "danger";
  if (!row.installed) return "warning";
  if (!row.entry_url) return "warning";
  return "success";
}

async function loadData() {
  loading.value = true;
  try {
    const [entriesRes, purchasedRes, installedRes, menusRes, shopRes] = await Promise.allSettled([
      fetchMobileEntries(),
      fetchPurchasedPlugins(),
      fetchInstalledPlugins(),
      fetchPluginMenus(),
      fetchPluginShopUrl()
    ]);
    entries.value = entriesRes.status === "fulfilled" && Array.isArray(entriesRes.value.items) ? entriesRes.value.items : [];
    purchasedIds.value = purchasedRes.status === "fulfilled" && Array.isArray(purchasedRes.value.plugin_ids) ? purchasedRes.value.plugin_ids : [];
    installedIds.value = installedRes.status === "fulfilled" && Array.isArray(installedRes.value) ? installedRes.value.map((x) => String(x.id || "")).filter(Boolean) : [];
    menuPluginIds.value = menusRes.status === "fulfilled" && Array.isArray(menusRes.value) ? menusRes.value.map((x) => String(x.plugin_id || "")).filter(Boolean) : [];
    shopUrl.value = shopRes.status === "fulfilled" ? String(shopRes.value.url || "") : "";
    const failedCount = [entriesRes, purchasedRes, installedRes, menusRes, shopRes].filter((x) => x.status === "rejected").length;
    if (failedCount > 0) {
      setLoadStatus(`部分刷新成功：失败 ${failedCount} 项`);
      uni.showToast({ title: `部分接口失败(${failedCount})`, icon: "none" });
    } else {
      setLoadStatus("刷新成功");
    }
  } catch (err: any) {
    setLoadStatus(err?.message ? `刷新失败：${err.message}` : "刷新失败");
    uni.showToast({ title: "插件中心加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

function openPlugin(row: MatrixRow) {
  if (!row.entry_url) {
    uni.showToast({ title: "该插件未配置可打开入口", icon: "none" });
    return;
  }
  uni.navigateTo({
    url: `/pages/plugin-container/index?pluginId=${encodeURIComponent(row.plugin_id)}`
  });
}

function openRuntime(row: MatrixRow) {
  uni.navigateTo({
    url: `/pages/plugin-runtime/index?plugin_id=${encodeURIComponent(row.plugin_id)}`
  });
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
  const text = [
    summaryText.value,
    `筛选=platform:${platformFilter.value || "all"},status:${statusFilter.value || "all"},keyword:${keyword.value || "-"}`,
    nextStepAdvice.value,
    `刷新状态=${loadMessage.value || "-"}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "插件中心摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

onShow(loadData);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">插件中心</view>

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
      <text class="app-subtext">筛选</text>
      <view class="app-row">
        <picker
          mode="selector"
          :range="['全部平台', '移动端', '小程序']"
          :value="platformFilter === '' ? 0 : platformFilter === 'mobile' ? 1 : 2"
          @change="
            (e:any) => {
              const i = Number(e?.detail?.value || 0);
              platformFilter = i === 1 ? 'mobile' : i === 2 ? 'miniprogram' : '';
            }
          "
        >
          <view class="app-subtext">平台：{{ platformFilter || "全部" }}</view>
        </picker>
        <picker
          mode="selector"
          :range="['全部状态', '可用', '待安装', '待购买']"
          :value="statusFilter === '' ? 0 : statusFilter === 'usable' ? 1 : statusFilter === 'need_install' ? 2 : 3"
          @change="
            (e:any) => {
              const i = Number(e?.detail?.value || 0);
              statusFilter = i === 1 ? 'usable' : i === 2 ? 'need_install' : i === 3 ? 'need_purchase' : '';
            }
          "
        >
          <view class="app-subtext">状态：{{ statusFilter || "全部" }}</view>
        </picker>
      </view>
      <input v-model="keyword" class="app-input" placeholder="按能力名/插件ID搜索" />
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">能力矩阵（{{ filteredRows.length }}）</text>
      <view v-if="filteredRows.length" class="app-gap-12">
        <view v-for="row in filteredRows" :key="row.plugin_id" class="app-card">
          <view class="app-row">
            <text class="app-subtext">{{ row.name }}</text>
            <AppStatusTag :text="rowStatusText(row)" :type="rowStatusType(row)" />
          </view>
          <text class="app-subtext">插件ID：{{ row.plugin_id }}</text>
          <text class="app-subtext">平台：{{ row.platforms.join("/") }}</text>
          <text class="app-subtext">入口：{{ row.entry_url || "-" }}</text>
          <text class="app-subtext">菜单可见：{{ row.hasMenu ? "是" : "否" }}</text>
          <view class="app-row">
            <button size="mini" :disabled="!row.entry_url" @click="openPlugin(row)">打开入口</button>
            <button size="mini" :disabled="!row.installed" @click="openRuntime(row)">运行页</button>
          </view>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '能力矩阵加载中...' : '当前筛选下暂无能力项'" />
    </view>
  </view>
</template>
