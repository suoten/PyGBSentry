<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import {
  fetchInstalledPlugins,
  fetchMobileEntries,
  fetchPluginMarketplace,
  fetchPluginMenus,
  fetchPurchasedPlugins,
  fetchSystemInfo
} from "@/api/plugin";
import AppEmpty from "@/components/AppEmpty.vue";
import AppStatusTag from "@/components/AppStatusTag.vue";

type MatrixRow = {
  plugin_id: string;
  name: string;
  platforms: string[];
  entries: Array<{ entry_url?: string; entry_url_template?: string; platform?: string }>;
  purchased: boolean;
  installed: boolean;
  canOpen: boolean;
  statusText: string;
  statusType: "success" | "warning" | "danger";
  dependencyText: string;
  compatible: boolean;
  compatibilityText: string;
};

const loading = ref(false);
const entries = ref<any[]>([]);
const purchasedIds = ref<string[]>([]);
const installedIds = ref<string[]>([]);
const menuPluginIds = ref<string[]>([]);
const ossVersion = ref("1.0.0");
const pluginMeta = ref<Record<string, { min_oss_version?: string }>>({});
const platformFilter = ref<"" | "mobile" | "miniprogram">("");
const statusFilter = ref<"" | "usable" | "need_install" | "need_purchase">("");
const keyword = ref("");
const loadMessage = ref("未刷新");
const loadAt = ref("");

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

function parseVersion(v: string) {
  return String(v || "")
    .trim()
    .replace(/^[^0-9]*/, "")
    .split(".")
    .map((part) => {
      const n = Number.parseInt(String(part).replace(/[^0-9].*$/, ""), 10);
      return Number.isFinite(n) ? n : 0;
    });
}

function gteVersion(current: string, required: string) {
  const cv = parseVersion(current);
  const rv = parseVersion(required);
  const len = Math.max(cv.length, rv.length);
  for (let i = 0; i < len; i += 1) {
    const a = cv[i] || 0;
    const b = rv[i] || 0;
    if (a > b) return true;
    if (a < b) return false;
  }
  return true;
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
    if (!current) {
      grouped.set(pid, {
        plugin_id: pid,
        name: String(item?.name || pid),
        platforms: [String(item?.platform || "mobile")],
        entries: [{ entry_url: item?.entry_url, entry_url_template: item?.entry_url_template, platform: item?.platform }],
        purchased: purchasedIds.value.includes(pid),
        installed: installedIds.value.includes(pid),
        canOpen: !!resolveEntryUrl(item),
        statusText: "",
        statusType: "danger",
        dependencyText: "",
        compatible: true,
        compatibilityText: ""
      });
      continue;
    }
    const platform = String(item?.platform || "mobile");
    if (!current.platforms.includes(platform)) current.platforms.push(platform);
    current.entries.push({ entry_url: item?.entry_url, entry_url_template: item?.entry_url_template, platform: item?.platform });
    current.purchased = current.purchased || purchasedIds.value.includes(pid);
    current.installed = current.installed || installedIds.value.includes(pid);
    current.canOpen = current.canOpen || !!resolveEntryUrl(item);
  }

  return Array.from(grouped.values())
    .sort((a, b) => a.name.localeCompare(b.name, "zh-Hans-CN"))
    .map((row) => {
      const required = String(pluginMeta.value[row.plugin_id]?.min_oss_version || "");
      const compatible = required ? gteVersion(ossVersion.value, required) : true;
      const dependencyText = row.purchased ? (row.installed ? "购买与安装均满足" : "已购买，待安装") : "未购买，需先购买";
      let statusText = "待购买";
      let statusType: "success" | "warning" | "danger" = "danger";
      if (row.purchased && !row.installed) {
        statusText = "待安装";
        statusType = "warning";
      }
      if (row.purchased && row.installed) {
        statusText = row.canOpen ? "可用" : "已安装未配置入口";
        statusType = row.canOpen ? "success" : "warning";
      }
      const compatibilityText = compatible
        ? required
          ? `兼容（要求 >= ${required}）`
          : "无版本门槛"
        : `当前版本 ${ossVersion.value}，要求 >= ${required}`;
      return {
        ...row,
        statusText,
        statusType,
        dependencyText,
        compatible,
        compatibilityText
      };
    });
});

const filteredRows = computed(() => {
  const kw = keyword.value.trim().toLowerCase();
  return matrixRows.value.filter((row) => {
    if (platformFilter.value && !row.platforms.includes(platformFilter.value)) return false;
    if (statusFilter.value === "usable" && !(row.purchased && row.installed && row.canOpen)) return false;
    if (statusFilter.value === "need_install" && !(row.purchased && !row.installed)) return false;
    if (statusFilter.value === "need_purchase" && row.purchased) return false;
    if (!kw) return true;
    return row.name.toLowerCase().includes(kw) || row.plugin_id.toLowerCase().includes(kw);
  });
});

const summaryText = computed(() => {
  const total = matrixRows.value.length;
  const usable = matrixRows.value.filter((x) => x.purchased && x.installed && x.canOpen).length;
  const needInstall = matrixRows.value.filter((x) => x.purchased && !x.installed).length;
  const needPurchase = matrixRows.value.filter((x) => !x.purchased).length;
  const incompatible = matrixRows.value.filter((x) => !x.compatible).length;
  return `能力中心：总数=${total}；可用=${usable}；待安装=${needInstall}；待购买=${needPurchase}；兼容性提醒=${incompatible}`;
});

const nextStepAdvice = computed(() => {
  const incompatible = matrixRows.value.filter((x) => !x.compatible).length;
  const needPurchase = matrixRows.value.filter((x) => !x.purchased).length;
  const needInstall = matrixRows.value.filter((x) => x.purchased && !x.installed).length;
  if (incompatible > 0) return "下一步建议：先处理版本兼容性提醒，再推进安装。";
  if (needPurchase > 0) return "下一步建议：先完成待购买插件，再回到能力页验证。";
  if (needInstall > 0) return "下一步建议：先安装已购买插件，再检查入口可达性。";
  return "下一步建议：优先抽检可用能力，联动运行中心确认数据回传。";
});

function rowMenuText(pluginId: string) {
  return menuPluginIds.value.includes(pluginId) ? "是" : "否";
}

async function loadData() {
  loading.value = true;
  try {
    const [entriesRes, purchasedRes, installedRes, menusRes, marketRes, sysRes] = await Promise.allSettled([
      fetchMobileEntries(),
      fetchPurchasedPlugins(),
      fetchInstalledPlugins(),
      fetchPluginMenus(),
      fetchPluginMarketplace(),
      fetchSystemInfo()
    ]);
    entries.value = entriesRes.status === "fulfilled" && Array.isArray(entriesRes.value.items) ? entriesRes.value.items : [];
    purchasedIds.value = purchasedRes.status === "fulfilled" && Array.isArray(purchasedRes.value.plugin_ids) ? purchasedRes.value.plugin_ids : [];
    installedIds.value = installedRes.status === "fulfilled" && Array.isArray(installedRes.value) ? installedRes.value.map((x) => String(x.id || "")).filter(Boolean) : [];
    menuPluginIds.value = menusRes.status === "fulfilled" && Array.isArray(menusRes.value) ? menusRes.value.map((x) => String(x.plugin_id || "")).filter(Boolean) : [];
    if (marketRes.status === "fulfilled" && Array.isArray(marketRes.value)) {
      const map: Record<string, { min_oss_version?: string }> = {};
      for (const row of marketRes.value) {
        const id = String(row?.id || "");
        if (!id) continue;
        map[id] = { min_oss_version: String(row?.min_oss_version || "") || undefined };
      }
      pluginMeta.value = map;
    } else {
      pluginMeta.value = {};
    }
    ossVersion.value = sysRes.status === "fulfilled" ? String(sysRes.value?.version || "1.0.0") : "1.0.0";
    const failedCount = [entriesRes, purchasedRes, installedRes, menusRes, marketRes, sysRes].filter((x) => x.status === "rejected").length;
    if (failedCount > 0) {
      setLoadStatus(`部分刷新成功：失败 ${failedCount} 项`);
      uni.showToast({ title: `部分接口失败(${failedCount})`, icon: "none" });
    } else {
      setLoadStatus("刷新成功");
    }
  } catch (err: any) {
    setLoadStatus(err?.message ? `刷新失败：${err.message}` : "刷新失败");
    uni.showToast({ title: "能力中心加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

function openPlugin(row: MatrixRow) {
  if (!row.canOpen) {
    uni.showToast({ title: "该能力未配置可用入口", icon: "none" });
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

function openDetail(row: MatrixRow) {
  uni.navigateTo({
    url: `/pages/plugin-detail/index?plugin_id=${encodeURIComponent(row.plugin_id)}`
  });
}

function copySummary() {
  const text = [
    summaryText.value,
    `筛选=platform:${platformFilter.value || "all"},status:${statusFilter.value || "all"},keyword:${keyword.value || "-"}`,
    `系统版本=${ossVersion.value}`,
    nextStepAdvice.value,
    `刷新状态=${loadMessage.value || "-"}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "能力摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

onShow(loadData);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">移动能力中心</view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-subtext">{{ summaryText }}</text>
        <button size="mini" :loading="loading" @click="loadData">刷新</button>
      </view>
      <text class="app-subtext">系统版本：{{ ossVersion }}</text>
      <text class="app-subtext">{{ nextStepAdvice }}</text>
      <text class="app-subtext">刷新状态：{{ loadMessage || "-" }}</text>
      <text class="app-subtext">状态时间：{{ loadAt || "-" }}</text>
      <view class="app-row">
        <button size="mini" @click="copySummary">复制摘要</button>
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
          <view class="app-subtext">状态：{{ statusFilter || '全部' }}</view>
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
            <AppStatusTag :text="row.statusText" :type="row.statusType" />
          </view>
          <text class="app-subtext">插件ID：{{ row.plugin_id }}</text>
          <text class="app-subtext">平台：{{ row.platforms.join("/") }}</text>
          <text class="app-subtext">依赖：{{ row.dependencyText }}</text>
          <text class="app-subtext">兼容性：{{ row.compatibilityText }}</text>
          <text class="app-subtext">菜单可见：{{ rowMenuText(row.plugin_id) }}</text>
          <view class="app-row">
            <button size="mini" :disabled="!row.canOpen" @click="openPlugin(row)">打开入口</button>
            <button size="mini" :disabled="!row.installed" @click="openRuntime(row)">运行页</button>
            <button size="mini" @click="openDetail(row)">插件详情</button>
          </view>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '能力矩阵加载中...' : '当前筛选下暂无能力项'" />
    </view>
  </view>
</template>
