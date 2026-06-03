<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import { fetchAuditStats, listAuditLogs, type AuditLogItem } from "@/api/security";
import AppEmpty from "@/components/AppEmpty.vue";
import AppStatusTag from "@/components/AppStatusTag.vue";

const loading = ref(false);
const rows = ref<AuditLogItem[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const filterModule = ref("");
const filterOperator = ref("");
const filterResult = ref("");
const startAt = ref("");
const endAt = ref("");
const loadMessage = ref("未刷新");
const loadAt = ref("");
const statsTotal = ref(0);
const statsFailed = ref(0);
const statsTopAction = ref("-");
const statsTopStatusCode = ref("-");

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

function initWindow() {
  const end = new Date();
  const start = new Date(end.getTime() - 15 * 60 * 1000);
  startAt.value = start.toISOString().slice(0, 19);
  endAt.value = end.toISOString().slice(0, 19);
}

const summaryText = computed(() => {
  return `审计中心：总数=${total.value}；当前页=${rows.value.length}；失败=${statsFailed.value}/${statsTotal.value}；Top动作=${statsTopAction.value}；Top状态码=${statsTopStatusCode.value}`;
});

const nextStepAdvice = computed(() => {
  if (total.value <= 0) return "下一步建议：先放宽时间窗并按模块聚焦查询。";
  if (statsFailed.value > 0) return "下一步建议：优先筛选 failed 结果，结合状态码定位失败根因。";
  return "下一步建议：当前失败量较低，可持续观察 Top 动作与状态码趋势。";
});

function normalizeDateInput(raw: string) {
  const text = String(raw || "").trim();
  if (!text) return "";
  const normalized = text.includes("T") ? text : text.replace(" ", "T");
  const d = new Date(normalized);
  if (Number.isNaN(d.getTime())) return "";
  return d.toISOString();
}

function safeString(value: unknown) {
  return String(value || "").trim();
}

function safeResultTagType(value: string) {
  const v = String(value || "").toLowerCase();
  if (v === "success") return "success";
  if (v === "failed") return "danger";
  return "info";
}

async function search() {
  loading.value = true;
  try {
    const query = {
      module: safeString(filterModule.value) || undefined,
      operator: safeString(filterOperator.value) || undefined,
      result: safeString(filterResult.value) || undefined,
      start_at: normalizeDateInput(startAt.value) || undefined,
      end_at: normalizeDateInput(endAt.value) || undefined,
      page: page.value,
      page_size: pageSize.value
    };
    const [listRes, statsRes] = await Promise.all([listAuditLogs(query), fetchAuditStats(query)]);
    rows.value = Array.isArray(listRes?.items) ? listRes.items : [];
    total.value = Number(listRes?.total || 0);
    statsTotal.value = Number(statsRes?.total || 0);
    statsFailed.value = Number(statsRes?.failed || 0);
    statsTopAction.value = statsRes?.top_actions?.[0]?.name ? `${statsRes.top_actions[0].name}(${statsRes.top_actions[0].count})` : "-";
    statsTopStatusCode.value = statsRes?.top_status_codes?.[0]?.code
      ? `${statsRes.top_status_codes[0].code}(${statsRes.top_status_codes[0].count})`
      : "-";
    setLoadStatus(`查询成功：${rows.value.length} 条`);
  } catch (err: any) {
    rows.value = [];
    total.value = 0;
    statsTotal.value = 0;
    statsFailed.value = 0;
    statsTopAction.value = "-";
    statsTopStatusCode.value = "-";
    setLoadStatus(err?.message ? `查询失败：${err.message}` : "查询失败");
    uni.showToast({ title: "审计日志查询失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

async function prevPage() {
  if (page.value <= 1) return;
  page.value -= 1;
  await search();
}

async function nextPage() {
  const maxPage = Math.max(1, Math.ceil(total.value / pageSize.value));
  if (page.value >= maxPage) return;
  page.value += 1;
  await search();
}

async function applyQuickResult(value: string) {
  filterResult.value = value;
  page.value = 1;
  await search();
}

async function applyTimeWindow(minutes: number) {
  const end = new Date();
  const start = new Date(end.getTime() - minutes * 60 * 1000);
  startAt.value = start.toISOString().slice(0, 19);
  endAt.value = end.toISOString().slice(0, 19);
  page.value = 1;
  await search();
}

function copySummary() {
  const text = [summaryText.value, nextStepAdvice.value, `刷新状态：${loadMessage.value || "-"}`].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "审计摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyRowSummary(row: AuditLogItem) {
  const text = [
    `时间=${row.created_at || "-"}`,
    `模块=${row.module || "-"}`,
    `动作=${row.action || "-"}`,
    `结果=${row.result || "-"}`,
    `状态码=${typeof row.status_code === "number" ? row.status_code : "-"}`,
    `操作人=${row.operator || "-"}`,
    `摘要=${row.summary || "-"}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "日志摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

async function initPage() {
  if (!startAt.value || !endAt.value) initWindow();
  await search();
}

onShow(initPage);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">审计中心</view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-subtext">{{ summaryText }}</text>
        <button size="mini" :loading="loading" @click="search">刷新</button>
      </view>
      <input v-model="filterModule" placeholder="模块（可空）" />
      <input v-model="filterOperator" placeholder="操作人（可空）" />
      <picker mode="selector" :range="['全部结果', 'success', 'failed']" :value="['', 'success', 'failed'].indexOf(filterResult)" @change="(e:any)=>{ const i=Number(e?.detail?.value||0); filterResult=['','success','failed'][i] || ''; page=1; search(); }">
        <view class="app-subtext">结果筛选：{{ filterResult || "全部" }}</view>
      </picker>
      <input v-model="startAt" placeholder="开始时间（ISO 或 YYYY-MM-DD HH:mm:ss）" />
      <input v-model="endAt" placeholder="结束时间（ISO 或 YYYY-MM-DD HH:mm:ss）" />
      <view class="app-row">
        <button size="mini" :loading="loading" @click="search">执行查询</button>
        <button size="mini" :loading="loading" @click="applyQuickResult('failed')">仅失败</button>
        <button size="mini" :loading="loading" @click="applyQuickResult('')">清结果</button>
      </view>
      <view class="app-row">
        <button size="mini" :loading="loading" @click="applyTimeWindow(15)">15m</button>
        <button size="mini" :loading="loading" @click="applyTimeWindow(60)">1h</button>
        <button size="mini" :loading="loading" @click="applyTimeWindow(1440)">24h</button>
        <button size="mini" @click="copySummary">复制摘要</button>
      </view>
      <text class="app-subtext">{{ nextStepAdvice }}</text>
      <text class="app-subtext">刷新状态：{{ loadMessage || "-" }}</text>
      <text class="app-subtext">状态时间：{{ loadAt || "-" }}</text>
    </view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-subtext">日志列表：{{ total }} 条</text>
        <view class="app-row">
          <button size="mini" :disabled="page<=1" @click="prevPage">上一页</button>
          <button size="mini" :disabled="page>=Math.max(1, Math.ceil(total / pageSize))" @click="nextPage">下一页</button>
        </view>
      </view>
      <text class="app-subtext">第 {{ page }} / {{ Math.max(1, Math.ceil(total / pageSize)) }} 页（每页 {{ pageSize }} 条）</text>
      <view v-if="rows.length" class="app-gap-12">
        <view v-for="row in rows" :key="row.id" class="app-row">
          <view style="flex:1">
            <text class="app-subtext">时间：{{ row.created_at || "-" }}</text>
            <text class="app-subtext">模块/动作：{{ row.module || "-" }} / {{ row.action || "-" }}</text>
            <text class="app-subtext">来源/操作人：{{ row.source || "-" }} / {{ row.operator || "-" }}</text>
            <text class="app-subtext">状态码：{{ typeof row.status_code === "number" ? row.status_code : "-" }}；插件：{{ row.plugin_id || "-" }}</text>
            <text class="app-subtext">摘要：{{ row.summary || "-" }}</text>
          </view>
          <view class="app-gap-12">
            <AppStatusTag :text="row.result || '-'" :type="safeResultTagType(row.result || '')" />
            <button size="mini" @click="copyRowSummary(row)">复制详情</button>
          </view>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '审计日志加载中...' : '暂无审计日志'" />
    </view>
  </view>
</template>
