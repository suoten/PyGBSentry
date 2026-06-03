<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import { login, getProfile } from "@/api/auth";
import { fetchMobileEntries } from "@/api/plugin";
import { useAuthStore } from "@/store/auth";
import { useAppStore } from "@/store/app";

const authStore = useAuthStore();
const appStore = useAppStore();

const username = ref("");
const password = ref("");
const loggingIn = ref(false);
const pluginLoading = ref(false);
const pluginLoadMessage = ref("");

const mineAccessSummaryText = computed(() => {
  return `账户状态：${authStore.isLoggedIn ? "已登录" : "未登录"}；插件数：${appStore.mobilePlugins.length}`;
});

const mineAccessNextStepAdvice = computed(() => {
  if (!authStore.isLoggedIn) {
    return "下一步建议：先完成登录再拉取移动插件入口。";
  }
  if (appStore.mobilePlugins.length <= 0) {
    return "下一步建议：检查插件发布状态与当前账号权限。";
  }
  return "下一步建议：优先验证高频插件入口可用性。";
});

const pluginOpenReadyCount = computed(
  () => appStore.mobilePlugins.filter((x) => !!String(x.plugin_id || "").trim()).length
);
const pluginNamedCount = computed(() => appStore.mobilePlugins.filter((x) => !!String(x.name || "").trim()).length);
const pluginHandoverTop1 = computed(() => {
  const first = appStore.mobilePlugins.find((x) => !!String(x.plugin_id || "").trim());
  if (!first) return "-";
  return `${first.name || first.plugin_id}(${first.plugin_id})`;
});
const minePluginHandoverSummaryText = computed(() => {
  const total = appStore.mobilePlugins.length;
  const namingRate = total <= 0 ? 0 : Number(((pluginNamedCount.value / total) * 100).toFixed(2));
  return [
    "插件可用性交接",
    `总插件=${total}`,
    `可打开=${pluginOpenReadyCount.value}`,
    `命名完整率=${namingRate}%`,
    `优先验证=${pluginHandoverTop1.value}`
  ].join("；");
});
const minePluginHandoverAdvice = computed(() => {
  if (!authStore.isLoggedIn) return "下一步建议：先登录后重新拉取插件列表。";
  if (appStore.mobilePlugins.length <= 0) return "下一步建议：确认插件发布与授权后再做可用性验证。";
  if (pluginOpenReadyCount.value < appStore.mobilePlugins.length) return "下一步建议：补齐缺失 plugin_id 的插件入口配置。";
  if (pluginNamedCount.value < appStore.mobilePlugins.length) return "下一步建议：完善插件命名，降低值班识别成本。";
  return "下一步建议：按优先验证插件执行端到端打开与关键操作检查。";
});
const accountProfileReadyCount = computed(() => {
  const usernameReady = !!String(authStore.profile?.username || "").trim();
  const tenantReady = !!String(authStore.profile?.tenant_id || "").trim();
  return (usernameReady ? 1 : 0) + (tenantReady ? 1 : 0);
});
const mineAccountPluginReadySummaryText = computed(() => {
  const total = appStore.mobilePlugins.length;
  const openReadyRate = total <= 0 ? 0 : Number(((pluginOpenReadyCount.value / total) * 100).toFixed(2));
  return [
    "账号与插件就绪摘要",
    `登录状态=${authStore.isLoggedIn ? "已登录" : "未登录"}`,
    `账号信息完整=${accountProfileReadyCount.value}/2`,
    `插件加载=${total}`,
    `可打开率=${openReadyRate}%`
  ].join("；");
});
const mineAccountPluginReadyAdvice = computed(() => {
  if (!authStore.isLoggedIn) return "下一步建议：先完成登录并拉取账号信息。";
  if (accountProfileReadyCount.value < 2) return "下一步建议：补齐账号资料中的租户与用户名信息。";
  if (appStore.mobilePlugins.length <= 0) return "下一步建议：检查账号授权范围并重新拉取移动插件列表。";
  if (pluginOpenReadyCount.value < appStore.mobilePlugins.length) return "下一步建议：优先补齐不可打开插件的入口标识。";
  return "下一步建议：优先验证首个高频插件并记录打开结果。";
});
const pluginEntryTypeDistributionSummary = computed(() => {
  const counters = {
    h5: 0,
    webview: 0,
    native: 0,
    plugin: 0,
    other: 0
  };
  appStore.mobilePlugins.forEach((x) => {
    const key = String((x as any).entry_type || "").toLowerCase();
    if (key === "h5") counters.h5 += 1;
    else if (key === "webview") counters.webview += 1;
    else if (key === "native") counters.native += 1;
    else if (key === "plugin") counters.plugin += 1;
    else counters.other += 1;
  });
  return `插件入口分布：h5=${counters.h5}；webview=${counters.webview}；native=${counters.native}；plugin=${counters.plugin}；other=${counters.other}`;
});
const pluginEntryTypeDistributionAdvice = computed(() => {
  if (!authStore.isLoggedIn) return "下一步建议：先登录后拉取插件列表，再进行入口类型分布核验。";
  if (appStore.mobilePlugins.length <= 0) return "下一步建议：当前无插件，先确认发布与授权范围。";
  if (pluginEntryTypeDistributionSummary.value.includes("other=0")) {
    return "下一步建议：入口类型规范，优先对高频类型执行抽样验证。";
  }
  return "下一步建议：清理 other 类型配置，统一入口类型枚举。";
});
const pluginIdMissingCount = computed(
  () => appStore.mobilePlugins.filter((x) => !String(x.plugin_id || "").trim()).length
);
const pluginIdDuplicateCount = computed(() => {
  const map = new Map<string, number>();
  appStore.mobilePlugins.forEach((x) => {
    const id = String(x.plugin_id || "").trim();
    if (!id) return;
    map.set(id, Number(map.get(id) || 0) + 1);
  });
  let duplicate = 0;
  map.forEach((count) => {
    if (count > 1) duplicate += count - 1;
  });
  return duplicate;
});
const pluginIdSpecSummaryText = computed(() => {
  const total = appStore.mobilePlugins.length;
  const valid = Math.max(0, total - pluginIdMissingCount.value - pluginIdDuplicateCount.value);
  return `插件标识规范性：总量=${total}；有效=${valid}；缺失ID=${pluginIdMissingCount.value}；重复ID=${pluginIdDuplicateCount.value}`;
});
const pluginIdSpecAdvice = computed(() => {
  if (!authStore.isLoggedIn) return "下一步建议：先登录并拉取插件列表，再核验标识规范性。";
  if (appStore.mobilePlugins.length <= 0) return "下一步建议：当前无插件数据，先确认授权与发布。";
  if (pluginIdMissingCount.value > 0) return "下一步建议：优先补齐缺失 plugin_id 的插件配置。";
  if (pluginIdDuplicateCount.value > 0) return "下一步建议：清理重复 plugin_id，确保标识唯一。";
  return "下一步建议：标识规范良好，继续执行入口可用性抽检。";
});
const pluginNameMissingCount = computed(
  () => appStore.mobilePlugins.filter((x) => !String(x.name || "").trim()).length
);
const pluginNameDuplicateCount = computed(() => {
  const map = new Map<string, number>();
  appStore.mobilePlugins.forEach((x) => {
    const name = String(x.name || "").trim();
    if (!name) return;
    map.set(name, Number(map.get(name) || 0) + 1);
  });
  let duplicate = 0;
  map.forEach((count) => {
    if (count > 1) duplicate += count - 1;
  });
  return duplicate;
});
const pluginNameSpecSummaryText = computed(() => {
  const total = appStore.mobilePlugins.length;
  const valid = Math.max(0, total - pluginNameMissingCount.value - pluginNameDuplicateCount.value);
  return `插件命名规范性：总量=${total}；命名有效=${valid}；缺失命名=${pluginNameMissingCount.value}；重复命名=${pluginNameDuplicateCount.value}`;
});
const pluginNameSpecAdvice = computed(() => {
  if (!authStore.isLoggedIn) return "下一步建议：先登录并拉取插件列表，再核验命名规范性。";
  if (appStore.mobilePlugins.length <= 0) return "下一步建议：当前无插件数据，先确认授权与发布。";
  if (pluginNameMissingCount.value > 0) return "下一步建议：优先补齐缺失插件名称，提升值班识别效率。";
  if (pluginNameDuplicateCount.value > 0) return "下一步建议：清理重复命名，避免交接歧义。";
  return "下一步建议：命名规范良好，继续推进入口抽检与治理。";
});

async function handleLogin() {
  if (!username.value || !password.value) {
    uni.showToast({ title: "请输入账号密码", icon: "none" });
    return;
  }
  loggingIn.value = true;
  try {
    const tokenRes = await login({ username: username.value, password: password.value });
    const profile = await getProfile();
    authStore.setAuth(tokenRes.access_token, profile);
    uni.showToast({ title: "登录成功", icon: "success" });
    await loadPlugins();
  } finally {
    loggingIn.value = false;
  }
}

async function loadPlugins() {
  if (!authStore.isLoggedIn) {
    appStore.setMobilePlugins([]);
    pluginLoadMessage.value = "未登录，插件列表未加载";
    return;
  }
  pluginLoading.value = true;
  pluginLoadMessage.value = "";
  try {
    const res = await fetchMobileEntries();
    appStore.setMobilePlugins((res.items || []).filter((x) => x.platform === "mobile"));
    pluginLoadMessage.value = "插件列表已刷新";
  } catch (err: any) {
    appStore.setMobilePlugins([]);
    pluginLoadMessage.value = err?.message ? `插件加载失败：${err.message}` : "插件加载失败，请稍后重试";
    uni.showToast({ title: "插件加载失败", icon: "none" });
  } finally {
    pluginLoading.value = false;
  }
}

function logout() {
  authStore.logout();
  appStore.setMobilePlugins([]);
  uni.showToast({ title: "已退出", icon: "none" });
}

function openPlugin(pluginId: string) {
  uni.navigateTo({
    url: `/pages/plugin-container/index?pluginId=${encodeURIComponent(pluginId)}`
  });
}

function copyMineAccessSummary() {
  const user = authStore.profile?.username || "-";
  const tenant = authStore.profile?.tenant_id || "-";
  const text = [
    "我的页接入摘要",
    mineAccessSummaryText.value,
    `用户：${user}；租户：${tenant}`,
    mineAccessNextStepAdvice.value
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "接入摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyMinePluginHandoverSummary() {
  const text = [minePluginHandoverSummaryText.value, minePluginHandoverAdvice.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "插件交接摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyMineAccountPluginReadySummary() {
  const text = [mineAccountPluginReadySummaryText.value, mineAccountPluginReadyAdvice.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "就绪摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyPluginEntryTypeDistributionSummary() {
  const text = [pluginEntryTypeDistributionSummary.value, pluginEntryTypeDistributionAdvice.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "入口分布摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyPluginIdSpecSummary() {
  const text = [pluginIdSpecSummaryText.value, pluginIdSpecAdvice.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "标识规范摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyPluginNameSpecSummary() {
  const text = [pluginNameSpecSummaryText.value, pluginNameSpecAdvice.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "命名规范摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

onShow(loadPlugins);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">我的</view>

    <view class="app-card app-gap-12" v-if="!authStore.isLoggedIn">
      <input v-model="username" placeholder="用户名" />
      <input v-model="password" password placeholder="密码" />
      <button type="primary" :loading="loggingIn" @click="handleLogin">登录</button>
      <text class="app-subtext">登录后可访问移动插件与更多能力</text>
    </view>

    <view v-else class="app-card app-gap-12">
      <text>用户：{{ authStore.profile?.username || "-" }}</text>
      <text class="app-subtext">租户：{{ authStore.profile?.tenant_id || "-" }}</text>
      <button @click="logout">退出登录</button>
    </view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text>移动插件</text>
        <text class="app-subtext">{{ appStore.mobilePlugins.length }} 个</text>
      </view>
      <view class="app-row">
        <button size="mini" :loading="pluginLoading" @click="loadPlugins">刷新插件列表</button>
      </view>
      <text class="app-subtext">{{ pluginLoadMessage || "-" }}</text>
      <text class="app-subtext">{{ mineAccessSummaryText }}</text>
      <text class="app-subtext">{{ mineAccessNextStepAdvice }}</text>
      <view class="app-row">
        <button size="mini" @click="copyMineAccessSummary">复制接入摘要</button>
        <button size="mini" @click="copyMinePluginHandoverSummary">复制插件交接摘要</button>
        <button size="mini" @click="copyMineAccountPluginReadySummary">复制就绪摘要</button>
        <button size="mini" @click="copyPluginEntryTypeDistributionSummary">复制入口分布摘要</button>
        <button size="mini" @click="copyPluginIdSpecSummary">复制标识规范摘要</button>
        <button size="mini" @click="copyPluginNameSpecSummary">复制命名规范摘要</button>
      </view>
      <text class="app-subtext">{{ minePluginHandoverSummaryText }}</text>
      <text class="app-subtext">{{ minePluginHandoverAdvice }}</text>
      <text class="app-subtext">{{ mineAccountPluginReadySummaryText }}</text>
      <text class="app-subtext">{{ mineAccountPluginReadyAdvice }}</text>
      <text class="app-subtext">{{ pluginEntryTypeDistributionSummary }}</text>
      <text class="app-subtext">{{ pluginEntryTypeDistributionAdvice }}</text>
      <text class="app-subtext">{{ pluginIdSpecSummaryText }}</text>
      <text class="app-subtext">{{ pluginIdSpecAdvice }}</text>
      <text class="app-subtext">{{ pluginNameSpecSummaryText }}</text>
      <text class="app-subtext">{{ pluginNameSpecAdvice }}</text>
      <view v-for="plugin in appStore.mobilePlugins" :key="plugin.plugin_id" class="app-row">
        <text>{{ plugin.name }}</text>
        <button size="mini" type="primary" @click="openPlugin(plugin.plugin_id)">打开</button>
      </view>
      <text v-if="appStore.mobilePlugins.length === 0" class="app-subtext">暂无可用插件</text>
    </view>
  </view>
</template>
