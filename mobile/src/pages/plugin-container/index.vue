<script setup lang="ts">
import { onLoad } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import { fetchMobileEntries } from "@/api/plugin";

const pluginId = ref("");
const loading = ref(false);
const title = ref("插件页面");
const entryType = ref<"h5" | "webview" | "plugin" | "native" | "none">("none");
const entryUrl = ref("");
const entryUrlTemplate = ref("");
const message = ref("");
const loadStatusMessage = ref("未拉取入口");
const lastLoadedAt = ref("");

const pluginAccessSummary = computed(() => {
  return [
    "插件接入诊断摘要",
    `插件ID：${pluginId.value || "-"}`,
    `插件名称：${title.value || "-"}`,
    `入口类型：${entryType.value}`,
    `入口地址：${entryUrl.value || "-"}`,
    `诊断信息：${message.value || "入口可用"}`
  ].join("；");
});

const pluginAccessNextStepAdvice = computed(() => {
  if (entryType.value === "h5" || entryType.value === "webview") {
    if (!entryUrl.value) return "下一步建议：检查插件入口 URL 模板与发布配置。";
    return "下一步建议：验证页面加载与关键操作链路是否正常。";
  }
  if (entryType.value === "native") return "下一步建议：在原生 App 容器中验证该插件能力。";
  if (entryType.value === "plugin") return "下一步建议：确认插件运行容器已启用并具备对应权限。";
  return "下一步建议：检查账号权限、插件发布状态与移动端入口配置。";
});

const pluginTemplateParamSummary = computed(() => {
  const template = entryUrlTemplate.value || entryUrl.value || "";
  const placeholders = Array.from(new Set(template.match(/\{[a-zA-Z0-9_]+\}/g) || []));
  const required = ["{base_url}", "{token}", "{tenant_id}"];
  const missing = required.filter((x) => !placeholders.includes(x));
  return `参数完整性：模板占位=${placeholders.length || 0}；关键参数缺失=${missing.length || 0}；缺失项=${missing.join("/") || "-"}`;
});

const pluginTemplateParamAdvice = computed(() => {
  if (!(entryType.value === "h5" || entryType.value === "webview")) return "下一步建议：当前入口非 H5，可跳过 URL 占位参数核验。";
  if (!entryUrlTemplate.value && !entryUrl.value) return "下一步建议：补齐入口模板，再进行占位参数核验。";
  if (pluginTemplateParamSummary.value.includes("关键参数缺失=0")) return "下一步建议：参数完整，可继续验证跳转与鉴权链路。";
  return "下一步建议：补齐缺失占位参数后重新发布插件入口配置。";
});

const pluginEntryAdaptationSummary = computed(() => {
  const targetContainer = entryType.value === "native" ? "原生容器" : entryType.value === "plugin" ? "插件容器" : "WebView";
  const hasEntry = !!String(entryUrl.value || "").trim();
  const templateState = entryUrlTemplate.value ? "有模板" : "无模板";
  return `入口适配性：入口类型=${entryType.value}; 目标容器=${targetContainer}; 地址可用=${hasEntry ? "是" : "否"}; 模板状态=${templateState}`;
});

const pluginEntryAdaptationAdvice = computed(() => {
  if (entryType.value === "none") return "下一步建议：先补齐移动端入口类型与地址配置。";
  if ((entryType.value === "h5" || entryType.value === "webview") && !entryUrl.value) {
    return "下一步建议：补齐 H5/WebView 入口地址后再验证容器适配。";
  }
  if (entryType.value === "native") return "下一步建议：在原生容器中验证权限与页面跳转链路。";
  if (entryType.value === "plugin") return "下一步建议：在插件容器中验证运行时依赖与权限。";
  return "下一步建议：继续执行关键路径操作回归，确认容器适配稳定。";
});

const pluginEntryUrlRiskSummary = computed(() => {
  const raw = String(entryUrl.value || "").trim();
  const hasUrl = !!raw;
  const isHttps = /^https:\/\//i.test(raw);
  const hasTokenInQuery = /[?&](token|access_token|auth|sign)=/i.test(raw);
  const hasIpHost = /^https?:\/\/\d{1,3}(\.\d{1,3}){3}(:\d+)?\//i.test(raw);
  return `入口地址风险：地址可用=${hasUrl ? "是" : "否"}；HTTPS=${isHttps ? "是" : "否"}；疑似敏感参数=${hasTokenInQuery ? "是" : "否"}；IP主机=${hasIpHost ? "是" : "否"}`;
});

const pluginEntryUrlRiskAdvice = computed(() => {
  const raw = String(entryUrl.value || "").trim();
  if (!raw) return "下一步建议：先补齐入口地址，再进行地址安全核验。";
  if (!/^https:\/\//i.test(raw)) return "下一步建议：优先切换到 HTTPS 入口，降低链路明文风险。";
  if (/[?&](token|access_token|auth|sign)=/i.test(raw)) return "下一步建议：避免在 URL 明文拼接敏感参数，改用安全鉴权头。";
  if (/^https?:\/\/\d{1,3}(\.\d{1,3}){3}(:\d+)?\//i.test(raw)) return "下一步建议：优先改为域名入口，便于证书与路由治理。";
  return "下一步建议：地址风险可控，继续做入口可达与鉴权回归。";
});

function fillTemplate(url: string) {
  return url
    .replace(/\{base_url\}/g, "")
    .replace(/\{token\}/g, "")
    .replace(/\{tenant_id\}/g, "");
}

async function loadPluginEntry() {
  if (!pluginId.value) return;
  loading.value = true;
  loadStatusMessage.value = "";
  try {
    const res = await fetchMobileEntries();
    const target = (res.items || []).find((x) => x.plugin_id === pluginId.value && x.platform === "mobile");
    if (!target) {
      entryType.value = "none";
      message.value = "未找到插件移动入口或当前账号无权限";
      loadStatusMessage.value = "入口拉取完成，但无可用入口";
      lastLoadedAt.value = new Date().toISOString();
      return;
    }
    title.value = target.name || target.plugin_id;
    entryType.value = target.entry_type;
    entryUrlTemplate.value = target.entry_url_template || target.entry_url || "";
    entryUrl.value = fillTemplate(target.entry_url || target.entry_url_template || "");
    if (!entryUrl.value && (entryType.value === "h5" || entryType.value === "webview")) {
      message.value = "插件入口地址为空，请联系管理员检查插件配置";
    }
    loadStatusMessage.value = "入口拉取成功";
    lastLoadedAt.value = new Date().toISOString();
  } catch (err: any) {
    entryType.value = "none";
    entryUrl.value = "";
    entryUrlTemplate.value = "";
    message.value = err?.message ? `入口拉取失败：${err.message}` : "入口拉取失败，请重试";
    loadStatusMessage.value = "入口拉取失败";
    uni.showToast({ title: "入口拉取失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

function copyPluginAccessSummary() {
  const text = [pluginAccessSummary.value, pluginAccessNextStepAdvice.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "诊断摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyPluginTemplateParamSummary() {
  const text = [pluginTemplateParamSummary.value, pluginTemplateParamAdvice.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "参数摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyPluginEntryAdaptationSummary() {
  const text = [pluginEntryAdaptationSummary.value, pluginEntryAdaptationAdvice.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "入口适配摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyPluginEntryUrlRiskSummary() {
  const text = [pluginEntryUrlRiskSummary.value, pluginEntryUrlRiskAdvice.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "地址风险摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

onLoad((query) => {
  if (typeof query?.pluginId === "string") pluginId.value = query.pluginId;
  loadPluginEntry();
});
</script>

<template>
  <view class="app-page">
    <view v-if="loading" class="app-subtext">加载中...</view>
    <view v-else-if="entryType === 'h5' || entryType === 'webview'">
      <web-view :src="entryUrl" />
    </view>
    <view v-else class="app-card app-gap-12">
      <view class="app-title">{{ title }}</view>
      <view class="app-row">
        <button size="mini" :loading="loading" @click="loadPluginEntry">重试拉取入口</button>
      </view>
      <text class="app-subtext">拉取状态：{{ loadStatusMessage || "-" }}</text>
      <text class="app-subtext">上次拉取：{{ lastLoadedAt || "-" }}</text>
      <text class="app-subtext">
        {{
          message ||
          (entryType === "native"
            ? "该插件需使用原生 App 功能承载"
            : entryType === "plugin"
              ? "该插件需在特定容器内运行"
              : "暂无可用入口")
        }}
      </text>
      <text class="app-subtext">{{ pluginAccessSummary }}</text>
      <text class="app-subtext">{{ pluginAccessNextStepAdvice }}</text>
      <text class="app-subtext">{{ pluginTemplateParamSummary }}</text>
      <text class="app-subtext">{{ pluginTemplateParamAdvice }}</text>
      <text class="app-subtext">{{ pluginEntryAdaptationSummary }}</text>
      <text class="app-subtext">{{ pluginEntryAdaptationAdvice }}</text>
      <text class="app-subtext">{{ pluginEntryUrlRiskSummary }}</text>
      <text class="app-subtext">{{ pluginEntryUrlRiskAdvice }}</text>
      <view class="app-row">
        <button size="mini" @click="copyPluginAccessSummary">复制诊断摘要</button>
        <button size="mini" @click="copyPluginTemplateParamSummary">复制参数摘要</button>
        <button size="mini" @click="copyPluginEntryAdaptationSummary">复制入口适配摘要</button>
        <button size="mini" @click="copyPluginEntryUrlRiskSummary">复制地址风险摘要</button>
      </view>
    </view>
  </view>
</template>
