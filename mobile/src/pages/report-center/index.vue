<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import {
  fetchAlarmStats,
  fetchCloseoutDrilldown,
  fetchCloseoutSummary,
  fetchReportList,
  fetchReportSummary,
  fetchTrafficStats,
  type AlarmStatsItem,
  type CloseoutDrilldownItem,
  type CloseoutSummaryResult,
  type ReportListItem,
  type ReportSummaryItem,
  type TrafficResult
} from "@/api/report";
import { getToken } from "@/utils/storage";
import AppEmpty from "@/components/AppEmpty.vue";

const loading = ref(false);
const exportLoading = ref(false);
const reportKeyword = ref("");
const detailSourceFilter = ref<"all" | "builtin" | "external">("all");
const selectedReportIds = ref<string[]>([]);
const exportTasks = ref<Array<{ id: string; name: string; statusText: string }>>([]);
const summaryItems = ref<ReportSummaryItem[]>([]);
const reportItems = ref<ReportListItem[]>([]);
const alarmItems = ref<AlarmStatsItem[]>([]);
const traffic = ref<TrafficResult | null>(null);
const closeoutSummary = ref<CloseoutSummaryResult | null>(null);
const closeoutRows = ref<CloseoutDrilldownItem[]>([]);
const closeoutTotal = ref(0);
const closeoutPageSize = ref(20);
const closeoutLoadingMore = ref(false);
const closeoutEnv = ref("");
const closeoutDays = ref(14);
const closeoutReasonCode = ref("");
const closeoutReasonCodeOut = ref("");
const closeoutSelectedDay = ref("");
const closeoutIncludeDashboard = ref(false);
const closeoutExportTemplate = ref<"default" | "minimal" | "full" | "custom">("default");
const closeoutExportCustomFieldsText = ref("");
const closeoutExportSchemeName = ref("");
const closeoutExportSchemeNote = ref("");
const closeoutActiveExportSchemeName = ref("");
const closeoutExportSchemeKeyword = ref("");
const closeoutExportSchemePinnedOnly = ref(false);
const closeoutUndoAuditKeyword = ref("");
const closeoutUndoAuditChangedOnly = ref(false);
const closeoutSnapshotHistoryVersion = ref(0);
const closeoutExportSchemeVersion = ref(0);
const loadMessage = ref("未刷新");
const loadAt = ref("");
const REPORT_FILTER_PREF_KEY = "pgbsentry_mobile_report_filter_prefs_v1";
const CLOSEOUT_FILTER_PREF_KEY = "pgbsentry_mobile_closeout_filter_prefs_v1";
const CLOSEOUT_FILTER_SNAPSHOT_KEY = "pgbsentry_mobile_closeout_filter_snapshot_v1";
const CLOSEOUT_FILTER_SNAPSHOT_HISTORY_KEY = "pgbsentry_mobile_closeout_filter_snapshot_history_v1";
const CLOSEOUT_EXPORT_SCHEME_HISTORY_KEY = "pgbsentry_mobile_closeout_export_scheme_history_v1";
const CLOSEOUT_ACTIVE_EXPORT_SCHEME_KEY = "pgbsentry_mobile_closeout_active_export_scheme_v1";
const CLOSEOUT_EXPORT_SCHEME_BACKUP_KEY = "pgbsentry_mobile_closeout_export_scheme_backup_v1";
const CLOSEOUT_REPAIRED_UNDO_AUDIT_HISTORY_KEY = "pgbsentry_mobile_closeout_repaired_undo_audit_history_v1";

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

const topAlarm = computed(() => {
  if (!alarmItems.value.length) return null;
  return [...alarmItems.value].sort((a, b) => Number(b.value || 0) - Number(a.value || 0))[0];
});

const summaryText = computed(() => {
  const device = summaryItems.value.find((x) => x.name.includes("设备"))?.value ?? 0;
  const alarm = summaryItems.value.find((x) => x.name.includes("报警"))?.value ?? 0;
  const stream = summaryItems.value.find((x) => x.name.includes("流"))?.value ?? 0;
  return `报表中心：内置报表=${reportItems.value.filter((x) => x.source === "builtin").length}；扩展报表=${reportItems.value.filter((x) => x.source !== "builtin").length}；明细命中=${filteredReportItems.value.length}；设备=${device}；今日报警=${alarm}；当前流数=${stream}`;
});

const nextStepAdvice = computed(() => {
  if ((topAlarm.value?.value || 0) > 0) return `下一步建议：优先排查高频报警类型「${topAlarm.value?.name || "-"}」。`;
  return "下一步建议：优先核对流量趋势与 closeout 原因分布，提前发现回归风险。";
});

const filteredReportItems = computed(() => {
  const keyword = reportKeyword.value.trim().toLowerCase();
  return reportItems.value.filter((row) => {
    if (detailSourceFilter.value === "builtin" && row.source !== "builtin") return false;
    if (detailSourceFilter.value === "external" && row.source === "builtin") return false;
    if (!keyword) return true;
    return String(row.id || "").toLowerCase().includes(keyword) || String(row.name || "").toLowerCase().includes(keyword);
  });
});

const hasAllVisibleSelected = computed(() => {
  if (!filteredReportItems.value.length) return false;
  return filteredReportItems.value.every((x) => selectedReportIds.value.includes(String(x.id || "")));
});

function buildApiUrl(path: string) {
  const apiBase = String(import.meta.env.VITE_API_BASE || "").replace(/\/$/, "");
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  return `${apiBase}${path}`;
}

function escapeCsvCell(value: unknown) {
  const text = String(value ?? "");
  if (/[",\n]/.test(text)) return `"${text.replace(/"/g, '""')}"`;
  return text;
}

function restoreFilterPrefs() {
  try {
    const reportRaw = uni.getStorageSync(REPORT_FILTER_PREF_KEY);
    if (reportRaw && typeof reportRaw === "object") {
      const reportObj = reportRaw as Record<string, any>;
      const source = String(reportObj?.detailSourceFilter || "all");
      if (source === "all" || source === "builtin" || source === "external") {
        detailSourceFilter.value = source;
      }
      reportKeyword.value = String(reportObj?.reportKeyword || "");
    }
    const closeoutRaw = uni.getStorageSync(CLOSEOUT_FILTER_PREF_KEY);
    if (closeoutRaw && typeof closeoutRaw === "object") {
      const closeoutObj = closeoutRaw as Record<string, any>;
      closeoutEnv.value = String(closeoutObj?.closeoutEnv || "");
      closeoutDays.value = Number(closeoutObj?.closeoutDays || 14) || 14;
      closeoutReasonCode.value = String(closeoutObj?.closeoutReasonCode || "");
      closeoutReasonCodeOut.value = String(closeoutObj?.closeoutReasonCodeOut || "");
      closeoutSelectedDay.value = String(closeoutObj?.closeoutSelectedDay || "");
      closeoutIncludeDashboard.value = Boolean(closeoutObj?.closeoutIncludeDashboard);
      const exportTemplate = String(closeoutObj?.closeoutExportTemplate || "default");
      if (["default", "minimal", "full", "custom"].includes(exportTemplate)) {
        closeoutExportTemplate.value = exportTemplate as "default" | "minimal" | "full" | "custom";
      }
      closeoutExportCustomFieldsText.value = String(closeoutObj?.closeoutExportCustomFieldsText || "");
      closeoutExportSchemeName.value = String(closeoutObj?.closeoutExportSchemeName || "");
      closeoutExportSchemeNote.value = String(closeoutObj?.closeoutExportSchemeNote || "");
      closeoutExportSchemeKeyword.value = String(closeoutObj?.closeoutExportSchemeKeyword || "");
      closeoutExportSchemePinnedOnly.value = Boolean(closeoutObj?.closeoutExportSchemePinnedOnly);
      closeoutUndoAuditKeyword.value = String(closeoutObj?.closeoutUndoAuditKeyword || "");
      closeoutUndoAuditChangedOnly.value = Boolean(closeoutObj?.closeoutUndoAuditChangedOnly);
    }
    closeoutActiveExportSchemeName.value = String(uni.getStorageSync(CLOSEOUT_ACTIVE_EXPORT_SCHEME_KEY) || "");
  } catch (err) {
    console.warn("restore report filter prefs failed", err);
  }
}

function saveReportFilterPrefs() {
  uni.setStorageSync(REPORT_FILTER_PREF_KEY, {
    reportKeyword: reportKeyword.value,
    detailSourceFilter: detailSourceFilter.value
  });
}

function saveCloseoutFilterPrefs() {
  uni.setStorageSync(CLOSEOUT_FILTER_PREF_KEY, {
    closeoutEnv: closeoutEnv.value,
    closeoutDays: closeoutDays.value,
    closeoutReasonCode: closeoutReasonCode.value,
    closeoutReasonCodeOut: closeoutReasonCodeOut.value,
    closeoutSelectedDay: closeoutSelectedDay.value,
    closeoutIncludeDashboard: closeoutIncludeDashboard.value,
    closeoutExportTemplate: closeoutExportTemplate.value,
    closeoutExportCustomFieldsText: closeoutExportCustomFieldsText.value,
    closeoutExportSchemeName: closeoutExportSchemeName.value,
    closeoutExportSchemeNote: closeoutExportSchemeNote.value,
    closeoutExportSchemeKeyword: closeoutExportSchemeKeyword.value,
    closeoutExportSchemePinnedOnly: closeoutExportSchemePinnedOnly.value,
    closeoutUndoAuditKeyword: closeoutUndoAuditKeyword.value,
    closeoutUndoAuditChangedOnly: closeoutUndoAuditChangedOnly.value
  });
}

interface CloseoutFilterSnapshot {
  closeoutEnv: string;
  closeoutDays: number;
  closeoutReasonCode: string;
  closeoutReasonCodeOut: string;
  closeoutSelectedDay: string;
  closeoutIncludeDashboard: boolean;
  closeoutExportTemplate: "default" | "minimal" | "full" | "custom";
  closeoutExportCustomFieldsText: string;
  savedAt: string;
}

interface CloseoutExportScheme {
  name: string;
  note?: string;
  template: "default" | "minimal" | "full" | "custom";
  customFieldsText: string;
  resolvedFields: string[];
  pinned?: boolean;
  useCount?: number;
  lastUsedAt?: string;
  savedAt: string;
}

interface CloseoutExportSchemeBackup {
  reason: string;
  savedAt: string;
  activeName: string;
  items: CloseoutExportScheme[];
}

interface CloseoutRepairedUndoAuditItem {
  executedAt: string;
  snapshotSavedAt: string;
  snapshotReason: string;
  beforeActiveName: string;
  afterActiveName: string;
  removedNames: string[];
  restoredNames: string[];
}

function buildDefaultCloseoutExportSchemes(): CloseoutExportScheme[] {
  const now = new Date().toISOString();
  return [
    {
      name: "默认_值班交接",
      note: "交接口径：时间/环境/原因/收口/Run",
      template: "custom",
      customFieldsText: "received_at,policy_env,reason_code,closeout_reason_code,run_id",
      resolvedFields: ["received_at", "policy_env", "reason_code", "closeout_reason_code", "run_id"],
      pinned: true,
      useCount: 0,
      lastUsedAt: "",
      savedAt: now
    },
    {
      name: "默认_问题排查",
      note: "排障口径：时间/原因/收口/Run/Event",
      template: "custom",
      customFieldsText: "received_at,reason_code,closeout_reason_code,run_id,event_id",
      resolvedFields: ["received_at", "reason_code", "closeout_reason_code", "run_id", "event_id"],
      pinned: false,
      useCount: 0,
      lastUsedAt: "",
      savedAt: now
    },
    {
      name: "默认_审计留痕",
      note: "审计口径：全链路关键字段",
      template: "custom",
      customFieldsText: "event_id,received_at,policy_env,reason_code,closeout_reason_code,run_id",
      resolvedFields: ["event_id", "received_at", "policy_env", "reason_code", "closeout_reason_code", "run_id"],
      pinned: false,
      useCount: 0,
      lastUsedAt: "",
      savedAt: now
    }
  ];
}

function normalizeCloseoutFilterSnapshot(input: any): CloseoutFilterSnapshot | null {
  if (!input || typeof input !== "object") return null;
  return {
    closeoutEnv: String(input.closeoutEnv || ""),
    closeoutDays: Number(input.closeoutDays || 14) || 14,
    closeoutReasonCode: String(input.closeoutReasonCode || ""),
    closeoutReasonCodeOut: String(input.closeoutReasonCodeOut || ""),
    closeoutSelectedDay: String(input.closeoutSelectedDay || ""),
    closeoutIncludeDashboard: Boolean(input.closeoutIncludeDashboard),
    closeoutExportTemplate: ["default", "minimal", "full", "custom"].includes(String(input.closeoutExportTemplate || ""))
      ? (String(input.closeoutExportTemplate) as "default" | "minimal" | "full" | "custom")
      : "default",
    closeoutExportCustomFieldsText: String(input.closeoutExportCustomFieldsText || ""),
    savedAt: String(input.savedAt || new Date().toISOString())
  };
}

function buildCloseoutFilterSnapshot(): CloseoutFilterSnapshot {
  return {
    closeoutEnv: closeoutEnv.value || "",
    closeoutDays: Number(closeoutDays.value || 14) || 14,
    closeoutReasonCode: closeoutReasonCode.value || "",
    closeoutReasonCodeOut: closeoutReasonCodeOut.value || "",
    closeoutSelectedDay: closeoutSelectedDay.value || "",
    closeoutIncludeDashboard: closeoutIncludeDashboard.value,
    closeoutExportTemplate: closeoutExportTemplate.value,
    closeoutExportCustomFieldsText: closeoutExportCustomFieldsText.value || "",
    savedAt: new Date().toISOString()
  };
}

function applyCloseoutFilterSnapshot(snapshot: Partial<CloseoutFilterSnapshot>) {
  closeoutEnv.value = String(snapshot.closeoutEnv || "");
  closeoutDays.value = Number(snapshot.closeoutDays || 14) || 14;
  closeoutReasonCode.value = String(snapshot.closeoutReasonCode || "");
  closeoutReasonCodeOut.value = String(snapshot.closeoutReasonCodeOut || "");
  closeoutSelectedDay.value = String(snapshot.closeoutSelectedDay || "");
  closeoutIncludeDashboard.value = Boolean(snapshot.closeoutIncludeDashboard);
  const exportTemplate = String(snapshot.closeoutExportTemplate || "default");
  closeoutExportTemplate.value = ["default", "minimal", "full", "custom"].includes(exportTemplate)
    ? (exportTemplate as "default" | "minimal" | "full" | "custom")
    : "default";
  closeoutExportCustomFieldsText.value = String(snapshot.closeoutExportCustomFieldsText || "");
  saveCloseoutFilterPrefs();
}

function saveCloseoutFilterSnapshot() {
  try {
    const next = buildCloseoutFilterSnapshot();
    const raw = uni.getStorageSync(CLOSEOUT_FILTER_SNAPSHOT_HISTORY_KEY);
    const history = Array.isArray(raw) ? (raw as CloseoutFilterSnapshot[]) : [];
    const latest = [next, ...history].slice(0, 3);
    uni.setStorageSync(CLOSEOUT_FILTER_SNAPSHOT_KEY, next);
    uni.setStorageSync(CLOSEOUT_FILTER_SNAPSHOT_HISTORY_KEY, latest);
    closeoutSnapshotHistoryVersion.value += 1;
    uni.showToast({ title: "Closeout快照已保存", icon: "none" });
  } catch (err) {
    uni.showToast({ title: "保存快照失败，请重试", icon: "none" });
  }
}

function restoreLatestCloseoutFilterSnapshot() {
  try {
    const raw = uni.getStorageSync(CLOSEOUT_FILTER_SNAPSHOT_KEY);
    if (!raw || typeof raw !== "object") {
      uni.showToast({ title: "暂无可还原快照", icon: "none" });
      return;
    }
    applyCloseoutFilterSnapshot(raw as Partial<CloseoutFilterSnapshot>);
    uni.showToast({ title: "已还原最近快照", icon: "none" });
  } catch (err) {
    uni.showToast({ title: "还原快照失败，请重试", icon: "none" });
  }
}

const closeoutFilterSnapshotHistory = computed(() => {
  void closeoutSnapshotHistoryVersion.value;
  const raw = uni.getStorageSync(CLOSEOUT_FILTER_SNAPSHOT_HISTORY_KEY);
  return Array.isArray(raw) ? (raw as CloseoutFilterSnapshot[]).slice(0, 3) : [];
});

function restoreCloseoutFilterSnapshotByIndex(index: number) {
  const row = closeoutFilterSnapshotHistory.value[index];
  if (!row) {
    uni.showToast({ title: "快照不存在", icon: "none" });
    return;
  }
  applyCloseoutFilterSnapshot(row);
  const reordered = [row, ...closeoutFilterSnapshotHistory.value.filter((_, idx) => idx !== index)].slice(0, 3);
  uni.setStorageSync(CLOSEOUT_FILTER_SNAPSHOT_KEY, row);
  uni.setStorageSync(CLOSEOUT_FILTER_SNAPSHOT_HISTORY_KEY, reordered);
  closeoutSnapshotHistoryVersion.value += 1;
  uni.showToast({ title: "已还原所选快照", icon: "none" });
}

function exportCloseoutFilterSnapshotHistoryJson() {
  const text = JSON.stringify(closeoutFilterSnapshotHistory.value, null, 2);
  uni.setClipboardData({
    data: text || "[]",
    success: () => uni.showToast({ title: "快照历史JSON已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function clearCloseoutFilterSnapshotHistory() {
  uni.removeStorageSync(CLOSEOUT_FILTER_SNAPSHOT_KEY);
  uni.removeStorageSync(CLOSEOUT_FILTER_SNAPSHOT_HISTORY_KEY);
  closeoutSnapshotHistoryVersion.value += 1;
  uni.showToast({ title: "快照历史已清空", icon: "none" });
}

async function importCloseoutFilterSnapshotHistoryFromClipboard() {
  try {
    const [err, res] = await uni.getClipboardData();
    if (err || !res?.data) {
      uni.showToast({ title: "剪贴板为空，请先复制JSON", icon: "none" });
      return;
    }
    const parsed = JSON.parse(String(res.data || "[]"));
    if (!Array.isArray(parsed)) {
      uni.showToast({ title: "JSON格式不正确（需为数组）", icon: "none" });
      return;
    }
    const normalized = parsed
      .map((item) => normalizeCloseoutFilterSnapshot(item))
      .filter((item): item is CloseoutFilterSnapshot => Boolean(item))
      .slice(0, 3);
    uni.setStorageSync(CLOSEOUT_FILTER_SNAPSHOT_HISTORY_KEY, normalized);
    uni.setStorageSync(CLOSEOUT_FILTER_SNAPSHOT_KEY, normalized[0] || buildCloseoutFilterSnapshot());
    closeoutSnapshotHistoryVersion.value += 1;
    uni.showToast({ title: `已导入${normalized.length}条快照`, icon: "none" });
  } catch (err) {
    uni.showToast({ title: "导入失败，请检查JSON", icon: "none" });
  }
}

function normalizeSourceText(source: string) {
  return source === "builtin" ? "内置" : "扩展";
}

function toggleReportSelection(reportId: string) {
  const id = String(reportId || "");
  if (!id) return;
  if (selectedReportIds.value.includes(id)) {
    selectedReportIds.value = selectedReportIds.value.filter((x) => x !== id);
    return;
  }
  selectedReportIds.value = [...selectedReportIds.value, id];
}

function toggleSelectAllVisibleReports() {
  if (!filteredReportItems.value.length) {
    uni.showToast({ title: "当前筛选下无报表", icon: "none" });
    return;
  }
  if (hasAllVisibleSelected.value) {
    const visibleIds = new Set(filteredReportItems.value.map((x) => String(x.id || "")));
    selectedReportIds.value = selectedReportIds.value.filter((id) => !visibleIds.has(id));
    return;
  }
  const next = new Set(selectedReportIds.value);
  filteredReportItems.value.forEach((x) => next.add(String(x.id || "")));
  selectedReportIds.value = [...next];
}

function clearSelectedReports() {
  selectedReportIds.value = [];
}

function copyReportFilterSnapshot() {
  saveReportFilterPrefs();
  const text = [
    `关键词=${reportKeyword.value.trim() || "-"}`,
    `来源筛选=${detailSourceFilter.value === "all" ? "全部" : detailSourceFilter.value === "builtin" ? "内置" : "扩展"}`,
    `筛选命中=${filteredReportItems.value.length}`,
    `已选导出=${selectedReportIds.value.length}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "筛选快照已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function setCloseoutEnvQuick(env: "" | "prod" | "canary" | "dev") {
  closeoutEnv.value = env;
  saveCloseoutFilterPrefs();
}

function setCloseoutDaysQuick(days: number) {
  closeoutDays.value = days;
  saveCloseoutFilterPrefs();
}

function resetCloseoutFilters() {
  closeoutEnv.value = "";
  closeoutDays.value = 14;
  closeoutReasonCode.value = "";
  closeoutReasonCodeOut.value = "";
  closeoutSelectedDay.value = "";
  closeoutIncludeDashboard.value = false;
  saveCloseoutFilterPrefs();
}

function copyCloseoutFilterSnapshot() {
  const text = [
    `环境=${closeoutEnv.value || "-"}`,
    `窗口天数=${closeoutDays.value || 14}`,
    `报警原因码=${closeoutReasonCode.value.trim() || "-"}`,
    `收口原因码=${closeoutReasonCodeOut.value.trim() || "-"}`,
    `按天筛选=${closeoutSelectedDay.value || "-"}`,
    `完整看板=${closeoutIncludeDashboard.value ? "开启" : "关闭"}`,
    `导出模板=${closeoutExportTemplate.value}`,
    `自定义字段=${closeoutExportCustomFieldsText.value.trim() || "-"}`,
    `明细条数=${closeoutRows.value.length}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "Closeout快照已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

const closeoutExportFieldOptions = ["event_id", "received_at", "policy_env", "reason_code", "closeout_reason_code", "run_id"];
const DEFAULT_CLOSEOUT_EXPORT_FIELDS = ["received_at", "policy_env", "reason_code", "closeout_reason_code", "run_id"];

function parseCloseoutCustomFieldsText(text: string) {
  const raw = String(text || "")
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);
  const unique: string[] = [];
  const invalid: string[] = [];
  raw.forEach((item) => {
    if (unique.includes(item)) return;
    if (closeoutExportFieldOptions.includes(item)) {
      unique.push(item);
      return;
    }
    invalid.push(item);
  });
  return { valid: unique, invalid };
}

const closeoutCustomFieldParseResult = computed(() => {
  const source = closeoutExportCustomFieldsText.value
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);
  const duplicate: string[] = [];
  const unique: string[] = [];
  source.forEach((item) => {
    if (!unique.includes(item)) {
      unique.push(item);
    } else if (!duplicate.includes(item)) {
      duplicate.push(item);
    }
  });
  const valid = unique.filter((x) => closeoutExportFieldOptions.includes(x));
  const invalid = unique.filter((x) => !closeoutExportFieldOptions.includes(x));
  return { valid, invalid, duplicate };
});

function resolveCloseoutExportFields() {
  if (closeoutExportTemplate.value === "minimal") {
    return ["received_at", "policy_env", "reason_code"];
  }
  if (closeoutExportTemplate.value === "full") {
    return [...closeoutExportFieldOptions];
  }
  if (closeoutExportTemplate.value === "custom") {
    const selected = closeoutCustomFieldParseResult.value.valid;
    return selected.length ? selected : [...DEFAULT_CLOSEOUT_EXPORT_FIELDS];
  }
  return [...DEFAULT_CLOSEOUT_EXPORT_FIELDS];
}

const closeoutResolvedExportFields = computed(() => resolveCloseoutExportFields());
const closeoutExportSchemeHistory = computed(() => {
  void closeoutExportSchemeVersion.value;
  const raw = uni.getStorageSync(CLOSEOUT_EXPORT_SCHEME_HISTORY_KEY);
  return Array.isArray(raw) ? (raw as CloseoutExportScheme[]).slice(0, 3) : [];
});
const closeoutFilteredExportSchemeRows = computed(() => {
  const keyword = closeoutExportSchemeKeyword.value.trim().toLowerCase();
  return closeoutExportSchemeHistory.value
    .map((scheme, index) => ({ scheme, index }))
    .filter(({ scheme }) => {
      if (closeoutExportSchemePinnedOnly.value && !scheme.pinned) return false;
      if (!keyword) return true;
      const merged = `${scheme.name || ""} ${scheme.note || ""} ${scheme.template || ""} ${(scheme.resolvedFields || []).join(",")}`.toLowerCase();
      return merged.includes(keyword);
    });
});

const closeoutFilteredExportSchemeHistory = computed(() => {
  return closeoutFilteredExportSchemeRows.value.map((x) => x.scheme);
});
const closeoutExportSchemeBackupMeta = computed(() => {
  void closeoutExportSchemeVersion.value;
  const raw = uni.getStorageSync(CLOSEOUT_EXPORT_SCHEME_BACKUP_KEY);
  if (!raw || typeof raw !== "object") return null;
  const obj = raw as Partial<CloseoutExportSchemeBackup>;
  const items = Array.isArray(obj.items) ? obj.items : [];
  if (!items.length) return null;
  return {
    reason: String(obj.reason || "-"),
    savedAt: String(obj.savedAt || "-"),
    count: items.length
  };
});
const closeoutExportSchemeBackupRows = computed(() => {
  void closeoutExportSchemeVersion.value;
  const payload = getCloseoutExportSchemeBackupPayload();
  if (!payload) return [];
  const hasActive = Boolean(payload.activeName);
  return payload.items.map((scheme, index) => ({
    scheme,
    index,
    isBackupActive: hasActive ? payload.activeName === scheme.name : index === 0
  }));
});

function isUndoableRepairedSchemeReason(reason: string) {
  return String(reason || "") === "save_repaired_scheme";
}

const closeoutCanUndoRepairedSchemeSave = computed(() => {
  void closeoutExportSchemeVersion.value;
  const payload = getCloseoutExportSchemeBackupPayload();
  if (!payload) return false;
  return isUndoableRepairedSchemeReason(payload.reason) && payload.items.length > 0;
});
const closeoutUndoRepairedSchemeHint = computed(() => {
  void closeoutExportSchemeVersion.value;
  const payload = getCloseoutExportSchemeBackupPayload();
  if (!payload) return "修复沉淀回滚：无可撤销快照";
  if (!isUndoableRepairedSchemeReason(payload.reason)) {
    return `修复沉淀回滚：不可撤销（reason=${payload.reason || "-"})`;
  }
  return `修复沉淀回滚：可撤销（快照时间=${payload.savedAt || "-"})`;
});
const closeoutRepairedUndoAuditMeta = computed(() => {
  void closeoutExportSchemeVersion.value;
  const rows = readCloseoutRepairedUndoAuditHistory();
  if (!rows.length) return "回滚审计：无";
  return `回滚审计：${rows.length}条 / 最近执行=${rows[0]?.executedAt || "-"}`;
});
const closeoutFilteredRepairedUndoAuditRows = computed(() => {
  void closeoutExportSchemeVersion.value;
  const keyword = closeoutUndoAuditKeyword.value.trim().toLowerCase();
  const rows = readCloseoutRepairedUndoAuditHistory()
    .filter((x) => !closeoutUndoAuditChangedOnly.value || (x.removedNames?.length || 0) > 0 || (x.restoredNames?.length || 0) > 0);
  if (!keyword) return rows;
  return rows.filter((x) => {
    const merged = `${x.executedAt || ""} ${x.snapshotSavedAt || ""} ${x.snapshotReason || ""} ${x.beforeActiveName || ""} ${x.afterActiveName || ""} ${(x.removedNames || []).join(",")} ${(x.restoredNames || []).join(",")}`.toLowerCase();
    return merged.includes(keyword);
  });
});
const closeoutChangedRepairedUndoAuditCount = computed(() => {
  void closeoutExportSchemeVersion.value;
  return readCloseoutRepairedUndoAuditHistory().filter((x) => (x.removedNames?.length || 0) > 0 || (x.restoredNames?.length || 0) > 0).length;
});

function getSchemeDisplayText(scheme: CloseoutExportScheme) {
  return `${scheme.pinned ? "置顶/" : ""}${scheme.name}${closeoutActiveExportSchemeName.value === scheme.name ? "（当前）" : ""} / ${scheme.note || "-"} / ${scheme.template} / 使用=${scheme.useCount || 0} / 最近=${scheme.lastUsedAt || "-"} / ${(scheme.resolvedFields || []).join(",") || "-"}`;
}

function canShowSchemeNoMatch() {
  return closeoutExportSchemeHistory.value.length > 0 && closeoutFilteredExportSchemeRows.value.length === 0;
}

function resetCloseoutExportSchemeFilters() {
  closeoutExportSchemeKeyword.value = "";
  closeoutExportSchemePinnedOnly.value = false;
  saveCloseoutFilterPrefs();
}

function schemeActionIndex(rowIndex: number) {
  const row = closeoutFilteredExportSchemeRows.value[rowIndex];
  return Number(row?.index ?? -1);
}

function canOperateScheme(rowIndex: number) {
  return schemeActionIndex(rowIndex) >= 0;
}

function backupCloseoutExportSchemes(reason: string) {
  if (!closeoutExportSchemeHistory.value.length) return;
  const payload: CloseoutExportSchemeBackup = {
    reason: String(reason || "manual"),
    savedAt: new Date().toISOString(),
    activeName: String(closeoutActiveExportSchemeName.value || ""),
    items: closeoutExportSchemeHistory.value.slice(0, 3)
  };
  uni.setStorageSync(CLOSEOUT_EXPORT_SCHEME_BACKUP_KEY, payload);
}

function getCloseoutExportSchemeBackupPayload() {
  const raw = uni.getStorageSync(CLOSEOUT_EXPORT_SCHEME_BACKUP_KEY);
  if (!raw || typeof raw !== "object") return null;
  const payload = raw as Partial<CloseoutExportSchemeBackup>;
  const items = (Array.isArray(payload.items) ? payload.items : [])
    .map((x) => normalizeCloseoutExportScheme(x))
    .filter((x): x is CloseoutExportScheme => Boolean(x))
    .slice(0, 3);
  if (!items.length) return null;
  return {
    reason: String(payload.reason || "-"),
    savedAt: String(payload.savedAt || new Date().toISOString()),
    activeName: String(payload.activeName || ""),
    items
  };
}

function restoreCloseoutExportSchemeHistoryFromBackup() {
  const payload = getCloseoutExportSchemeBackupPayload();
  if (!payload) {
    uni.showToast({ title: "暂无可恢复备份", icon: "none" });
    return;
  }
  const normalized = payload.items;
  if (!normalized.length) {
    uni.showToast({ title: "备份无有效方案", icon: "none" });
    return;
  }
  uni.setStorageSync(CLOSEOUT_EXPORT_SCHEME_HISTORY_KEY, normalized);
  const activeFromBackup = String(payload.activeName || "");
  if (activeFromBackup && normalized.some((x) => x.name === activeFromBackup)) {
    setCloseoutActiveExportSchemeName(activeFromBackup);
  } else {
    setCloseoutActiveExportSchemeName(normalized[0]?.name || "");
  }
  closeoutExportSchemeVersion.value += 1;
  uni.showToast({ title: `已恢复备份方案(${normalized.length}条)`, icon: "none" });
}

function copyCloseoutExportSchemeBackupSummary() {
  const payload = getCloseoutExportSchemeBackupPayload();
  if (!payload) {
    uni.showToast({ title: "暂无可复制备份摘要", icon: "none" });
    return;
  }
  const lines = [
    `备份时间：${payload.savedAt}`,
    `备份原因：${payload.reason || "-"}`,
    `备份活动方案：${payload.activeName || "-"}`,
    `备份条数：${payload.items.length}`,
    ...payload.items.map((x, idx) => {
      const activeMark = payload.activeName && payload.activeName === x.name ? "（备份活动）" : "";
      return `${idx + 1}. ${x.name}${activeMark} | 置顶=${x.pinned ? "是" : "否"} | 备注=${x.note || "-"} | 模板=${x.template} | 使用=${x.useCount || 0} | 最近使用=${x.lastUsedAt || "-"} | 字段=${(x.resolvedFields || []).join(",") || "-"}`;
    })
  ];
  uni.setClipboardData({
    data: lines.join("\n"),
    success: () => uni.showToast({ title: "备份摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function buildCurrentCloseoutExportSchemeDraft(): CloseoutExportScheme {
  return {
    name: closeoutExportSchemeName.value.trim() || "-",
    note: closeoutExportSchemeNote.value.trim() || "",
    template: closeoutExportTemplate.value,
    customFieldsText: closeoutExportCustomFieldsText.value.trim(),
    resolvedFields: [...closeoutResolvedExportFields.value],
    pinned: false,
    useCount: 0,
    lastUsedAt: "",
    savedAt: new Date().toISOString()
  };
}

function copyCloseoutExportSchemeBackupDiffSummary() {
  const payload = getCloseoutExportSchemeBackupPayload();
  if (!payload) {
    uni.showToast({ title: "暂无可对比备份", icon: "none" });
    return;
  }
  const backupActive = payload.activeName ? payload.items.find((x) => x.name === payload.activeName) : undefined;
  const backupTarget = backupActive || payload.items[0];
  if (!backupTarget) {
    uni.showToast({ title: "备份无可对比方案", icon: "none" });
    return;
  }
  const current = buildCurrentCloseoutExportSchemeDraft();
  const currentFields = new Set(current.resolvedFields || []);
  const backupFields = new Set(backupTarget.resolvedFields || []);
  const added = [...currentFields].filter((x) => !backupFields.has(x));
  const removed = [...backupFields].filter((x) => !currentFields.has(x));
  const lines = [
    `备份时间：${payload.savedAt}`,
    `备份原因：${payload.reason || "-"}`,
    `对比对象：${backupTarget.name || "-"}${payload.activeName && payload.activeName === backupTarget.name ? "（备份活动）" : ""}`,
    `模板：当前=${current.template} / 备份=${backupTarget.template} / 一致=${current.template === backupTarget.template ? "是" : "否"}`,
    `名称：当前=${current.name || "-"} / 备份=${backupTarget.name || "-"} / 一致=${current.name === (backupTarget.name || "-") ? "是" : "否"}`,
    `备注：当前=${current.note || "-"} / 备份=${backupTarget.note || "-"} / 一致=${(current.note || "-") === (backupTarget.note || "-") ? "是" : "否"}`,
    `字段新增(当前有/备份无)：${added.join(",") || "-"}`,
    `字段缺失(备份有/当前无)：${removed.join(",") || "-"}`,
    `当前字段：${(current.resolvedFields || []).join(",") || "-"}`,
    `备份字段：${(backupTarget.resolvedFields || []).join(",") || "-"}`
  ];
  uni.setClipboardData({
    data: lines.join("\n"),
    success: () => uni.showToast({ title: "备份差异已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyCloseoutExportSchemeBackupHealthSummary() {
  const payload = getCloseoutExportSchemeBackupPayload();
  if (!payload) {
    uni.showToast({ title: "暂无可检查备份", icon: "none" });
    return;
  }
  const lines = [
    `备份时间：${payload.savedAt}`,
    `备份原因：${payload.reason || "-"}`,
    `备份活动方案：${payload.activeName || "-"}`,
    `备份条数：${payload.items.length}`
  ];
  payload.items.forEach((scheme, index) => {
    const resolved = Array.isArray(scheme.resolvedFields) ? scheme.resolvedFields.filter(Boolean) : [];
    const unknown = resolved.filter((x) => !closeoutExportFieldOptions.includes(x));
    const customParsed = parseCloseoutCustomFieldsText(scheme.customFieldsText || "");
    const isEmptyResolved = resolved.length === 0;
    const riskParts = [
      isEmptyResolved ? "空字段" : "",
      customParsed.invalid.length ? `无效字段=${customParsed.invalid.length}` : "",
      customParsed.duplicate.length ? `重复字段=${customParsed.duplicate.length}` : "",
      unknown.length ? `未知字段=${unknown.length}` : ""
    ].filter(Boolean);
    lines.push(
      `${index + 1}. ${scheme.name || "-"}${payload.activeName && payload.activeName === scheme.name ? "（备份活动）" : ""} | 模板=${scheme.template} | 风险=${riskParts.join("、") || "无"} | 字段=${resolved.join(",") || "-"}`
    );
  });
  uni.setClipboardData({
    data: lines.join("\n"),
    success: () => uni.showToast({ title: "备份健康摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function resolveCloseoutExportFieldsByTemplate(
  template: "default" | "minimal" | "full" | "custom",
  customFieldsText: string
) {
  if (template === "minimal") {
    return ["received_at", "policy_env", "reason_code"];
  }
  if (template === "full") {
    return [...closeoutExportFieldOptions];
  }
  if (template === "custom") {
    const parsed = parseCloseoutCustomFieldsText(customFieldsText || "");
    return parsed.valid.length ? parsed.valid : [...DEFAULT_CLOSEOUT_EXPORT_FIELDS];
  }
  return [...DEFAULT_CLOSEOUT_EXPORT_FIELDS];
}

function copyCloseoutExportSchemeBackupRepairPreview() {
  const payload = getCloseoutExportSchemeBackupPayload();
  if (!payload) {
    uni.showToast({ title: "暂无可预览修复备份", icon: "none" });
    return;
  }
  const lines = [
    `备份时间：${payload.savedAt}`,
    `备份原因：${payload.reason || "-"}`,
    `修复预览条数：${payload.items.length}`
  ];
  payload.items.forEach((scheme, index) => {
    const before = Array.isArray(scheme.resolvedFields) ? scheme.resolvedFields.filter(Boolean) : [];
    const after = resolveCloseoutExportFieldsByTemplate(scheme.template, scheme.customFieldsText || "");
    const added = after.filter((x) => !before.includes(x));
    const removed = before.filter((x) => !after.includes(x));
    const changed = added.length > 0 || removed.length > 0;
    lines.push(
      `${index + 1}. ${scheme.name || "-"} | 模板=${scheme.template} | 变更=${changed ? "是" : "否"} | 新增=${added.join(",") || "-"} | 移除=${removed.join(",") || "-"} | 修复后字段=${after.join(",") || "-"}`
    );
  });
  uni.setClipboardData({
    data: lines.join("\n"),
    success: () => uni.showToast({ title: "备份修复预览已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function applyRepairedCloseoutExportSchemeFromBackupActive() {
  const payload = getCloseoutExportSchemeBackupPayload();
  if (!payload) {
    uni.showToast({ title: "暂无可试用备份", icon: "none" });
    return;
  }
  const active = payload.activeName ? payload.items.find((x) => x.name === payload.activeName) : payload.items[0];
  if (!active) {
    uni.showToast({ title: "备份无可用方案", icon: "none" });
    return;
  }
  const resolvedFields = resolveCloseoutExportFieldsByTemplate(active.template, active.customFieldsText || "");
  const repairedTarget: CloseoutExportScheme = {
    ...active,
    customFieldsText: active.template === "custom" ? resolvedFields.join(",") : String(active.customFieldsText || ""),
    resolvedFields
  };
  applyCloseoutExportSchemeFromBackupTarget(repairedTarget);
}

function saveRepairedBackupActiveAsCloseoutExportScheme() {
  const payload = getCloseoutExportSchemeBackupPayload();
  if (!payload) {
    uni.showToast({ title: "暂无可保存备份", icon: "none" });
    return;
  }
  const active = payload.activeName ? payload.items.find((x) => x.name === payload.activeName) : payload.items[0];
  if (!active) {
    uni.showToast({ title: "备份无可用方案", icon: "none" });
    return;
  }
  const resolvedFields = resolveCloseoutExportFieldsByTemplate(active.template, active.customFieldsText || "");
  const existingNames = new Set(closeoutExportSchemeHistory.value.map((x) => x.name));
  const baseName = `${active.name || "backup_active"}_repaired`;
  let nextName = baseName;
  if (existingNames.has(nextName)) {
    nextName = `${baseName}_${Date.now().toString().slice(-4)}`;
  }
  const next: CloseoutExportScheme = {
    name: nextName,
    note: `${String(active.note || "")}${active.note ? " | " : ""}from_backup:${payload.savedAt}`,
    template: active.template,
    customFieldsText: active.template === "custom" ? resolvedFields.join(",") : String(active.customFieldsText || ""),
    resolvedFields,
    pinned: false,
    useCount: 0,
    lastUsedAt: "",
    savedAt: new Date().toISOString()
  };
  backupCloseoutExportSchemes("save_repaired_scheme");
  const merged = [next, ...closeoutExportSchemeHistory.value.filter((x) => x.name !== next.name)].slice(0, 3);
  uni.setStorageSync(CLOSEOUT_EXPORT_SCHEME_HISTORY_KEY, merged);
  setCloseoutActiveExportSchemeName(next.name);
  closeoutExportSchemeVersion.value += 1;
  uni.showToast({ title: `已保存修复方案：${next.name}`, icon: "none" });
}

function getUndoableRepairedSchemeBackupPayload(showToastOnError = false) {
  const payload = getCloseoutExportSchemeBackupPayload();
  if (!payload) {
    if (showToastOnError) {
      uni.showToast({ title: "暂无可撤销备份", icon: "none" });
    }
    return null;
  }
  if (!isUndoableRepairedSchemeReason(payload.reason)) {
    if (showToastOnError) {
      uni.showToast({ title: "最近备份并非修复沉淀前快照", icon: "none" });
    }
    return null;
  }
  if (!payload.items.length) {
    if (showToastOnError) {
      uni.showToast({ title: "撤销失败：备份无有效方案", icon: "none" });
    }
    return null;
  }
  return payload;
}

function normalizeCloseoutRepairedUndoAuditRows(input: unknown) {
  if (!Array.isArray(input)) return [];
  const normalized = input
    .filter((x) => x && typeof x === "object")
    .map((x) => {
      const item = x as Partial<CloseoutRepairedUndoAuditItem>;
      return {
        executedAt: String(item.executedAt || new Date().toISOString()),
        snapshotSavedAt: String(item.snapshotSavedAt || "-"),
        snapshotReason: String(item.snapshotReason || "-"),
        beforeActiveName: String(item.beforeActiveName || ""),
        afterActiveName: String(item.afterActiveName || ""),
        removedNames: Array.isArray(item.removedNames) ? item.removedNames.map((n) => String(n || "")).filter(Boolean).slice(0, 10) : [],
        restoredNames: Array.isArray(item.restoredNames) ? item.restoredNames.map((n) => String(n || "")).filter(Boolean).slice(0, 10) : []
      } as CloseoutRepairedUndoAuditItem;
    })
    .sort((a, b) => String(b.executedAt || "").localeCompare(String(a.executedAt || "")));
  const deduped: CloseoutRepairedUndoAuditItem[] = [];
  const seen = new Set<string>();
  normalized.forEach((item) => {
    const key = `${item.executedAt}|${item.snapshotSavedAt}|${item.snapshotReason}|${item.beforeActiveName}|${item.afterActiveName}`;
    if (seen.has(key)) return;
    seen.add(key);
    deduped.push(item);
  });
  return deduped.slice(0, 5);
}

function readCloseoutRepairedUndoAuditHistory() {
  const raw = uni.getStorageSync(CLOSEOUT_REPAIRED_UNDO_AUDIT_HISTORY_KEY);
  return normalizeCloseoutRepairedUndoAuditRows(raw);
}

function appendCloseoutRepairedUndoAudit(item: CloseoutRepairedUndoAuditItem) {
  const next = normalizeCloseoutRepairedUndoAuditRows([item, ...readCloseoutRepairedUndoAuditHistory()]);
  uni.setStorageSync(CLOSEOUT_REPAIRED_UNDO_AUDIT_HISTORY_KEY, next);
}

function copyCloseoutRepairedUndoAuditSummary() {
  const rows = readCloseoutRepairedUndoAuditHistory();
  if (!rows.length) {
    uni.showToast({ title: "暂无回滚审计记录", icon: "none" });
    return;
  }
  const lines = rows.map((x, idx) => {
    return `${idx + 1}. 执行=${x.executedAt} | 快照=${x.snapshotSavedAt} | reason=${x.snapshotReason} | 活动方案: ${x.beforeActiveName || "-"} -> ${x.afterActiveName || "-"} | 移除=${x.removedNames.join(",") || "-"} | 恢复=${x.restoredNames.join(",") || "-"}`;
  });
  uni.setClipboardData({
    data: lines.join("\n"),
    success: () => uni.showToast({ title: "回滚审计摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyFilteredCloseoutRepairedUndoAuditSummary() {
  const rows = closeoutFilteredRepairedUndoAuditRows.value;
  if (!rows.length) {
    uni.showToast({ title: "当前无命中审计记录", icon: "none" });
    return;
  }
  const lines = rows.map((x, idx) => {
    return `${idx + 1}. 执行=${x.executedAt} | 快照=${x.snapshotSavedAt} | reason=${x.snapshotReason} | 活动方案: ${x.beforeActiveName || "-"} -> ${x.afterActiveName || "-"} | 移除=${x.removedNames.join(",") || "-"} | 恢复=${x.restoredNames.join(",") || "-"}`;
  });
  uni.setClipboardData({
    data: lines.join("\n"),
    success: () => uni.showToast({ title: "命中回滚审计已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyChangedCloseoutRepairedUndoAuditSummary() {
  const rows = readCloseoutRepairedUndoAuditHistory()
    .filter((x) => (x.removedNames?.length || 0) > 0 || (x.restoredNames?.length || 0) > 0)
    .slice(0, 5);
  if (!rows.length) {
    uni.showToast({ title: "暂无有变更审计记录", icon: "none" });
    return;
  }
  const lines = rows.map((x, idx) => {
    return `${idx + 1}. 执行=${x.executedAt} | 快照=${x.snapshotSavedAt} | reason=${x.snapshotReason} | 活动方案: ${x.beforeActiveName || "-"} -> ${x.afterActiveName || "-"} | 移除=${x.removedNames.join(",") || "-"} | 恢复=${x.restoredNames.join(",") || "-"}`;
  });
  uni.setClipboardData({
    data: lines.join("\n"),
    success: () => uni.showToast({ title: "有变更审计已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function keepChangedCloseoutRepairedUndoAuditHistory() {
  const rows = readCloseoutRepairedUndoAuditHistory()
    .filter((x) => (x.removedNames?.length || 0) > 0 || (x.restoredNames?.length || 0) > 0)
    .slice(0, 5);
  if (!rows.length) {
    uni.showToast({ title: "暂无有变更审计可保留", icon: "none" });
    return;
  }
  uni.setStorageSync(CLOSEOUT_REPAIRED_UNDO_AUDIT_HISTORY_KEY, rows);
  closeoutExportSchemeVersion.value += 1;
  uni.showToast({ title: `已仅保留${rows.length}条有变更审计`, icon: "none" });
}

function resetCloseoutUndoAuditFilters() {
  closeoutUndoAuditKeyword.value = "";
  closeoutUndoAuditChangedOnly.value = false;
  saveCloseoutFilterPrefs();
}

function copyCloseoutUndoAuditFilterSnapshot() {
  const text = [
    `审计关键词=${closeoutUndoAuditKeyword.value.trim() || "-"}`,
    `仅看有变更=${closeoutUndoAuditChangedOnly.value ? "是" : "否"}`,
    `命中数=${closeoutFilteredRepairedUndoAuditRows.value.length}`,
    `有变更总数=${closeoutChangedRepairedUndoAuditCount.value}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "审计筛选快照已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyCloseoutUndoAuditFilterSnapshotJson() {
  const payload = {
    schemaVersion: 1,
    snapshotType: "closeout_undo_audit_filter",
    closeoutUndoAuditKeyword: closeoutUndoAuditKeyword.value.trim(),
    closeoutUndoAuditChangedOnly: closeoutUndoAuditChangedOnly.value,
    matchedCount: closeoutFilteredRepairedUndoAuditRows.value.length,
    changedCount: closeoutChangedRepairedUndoAuditCount.value,
    savedAt: new Date().toISOString()
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => uni.showToast({ title: "审计筛选快照JSON已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function parseCloseoutUndoAuditFilterSnapshotText(text: string) {
  const source = String(text || "");
  try {
    const parsed = JSON.parse(source);
    if (parsed && typeof parsed === "object") {
      const rootObj = parsed as Record<string, unknown>;
      const snapshotType = String(rootObj.snapshotType || "");
      const schemaVersion = String(rootObj.schemaVersion || "");
      const typeValid = !snapshotType || snapshotType === "closeout_undo_audit_filter";
      const schemaValid = !schemaVersion || schemaVersion === "1";
      const payloadObj = (rootObj.payload && typeof rootObj.payload === "object")
        ? (rootObj.payload as Record<string, unknown>)
        : rootObj;
      const filterObj = (payloadObj.filters && typeof payloadObj.filters === "object")
        ? (payloadObj.filters as Record<string, unknown>)
        : null;
      const readField = (key: string) => {
        if (filterObj && Object.prototype.hasOwnProperty.call(filterObj, key)) return filterObj[key];
        if (Object.prototype.hasOwnProperty.call(payloadObj, key)) return payloadObj[key];
        return undefined;
      };
      const hasKeyword = readField("closeoutUndoAuditKeyword") !== undefined
        || readField("auditKeyword") !== undefined;
      const hasChangedOnly = readField("closeoutUndoAuditChangedOnly") !== undefined
        || readField("auditChangedOnly") !== undefined;
      const keywordRaw = String(readField("closeoutUndoAuditKeyword") ?? readField("auditKeyword") ?? "").trim();
      const changedRawSource = String(readField("closeoutUndoAuditChangedOnly") ?? readField("auditChangedOnly") ?? "").trim().toLowerCase();
      return {
        hasKnownField: hasKeyword || hasChangedOnly,
        hasKeyword,
        hasChangedOnly,
        keyword: keywordRaw === "-" ? "" : keywordRaw,
        changedOnly: ["是", "true", "1", "on"].includes(changedRawSource),
        snapshotType,
        schemaVersion,
        typeValid,
        schemaValid
      };
    }
  } catch {
    // fallback to text mode
  }
  const keywordMatch = source.match(/审计关键词=([^；\n]*)/);
  const changedOnlyMatch = source.match(/仅看有变更=([^；\n]*)/);
  const hasKnownField = Boolean(keywordMatch || changedOnlyMatch);
  const keyword = String(keywordMatch?.[1] || "").trim();
  const changedRaw = String(changedOnlyMatch?.[1] || "").trim().toLowerCase();
  const changedOnly = ["是", "true", "1", "on"].includes(changedRaw);
  return {
    hasKnownField,
    hasKeyword: Boolean(keywordMatch),
    hasChangedOnly: Boolean(changedOnlyMatch),
    keyword: keyword === "-" ? "" : keyword,
    changedOnly,
    snapshotType: "text",
    schemaVersion: "",
    typeValid: true,
    schemaValid: true
  };
}

async function previewCloseoutUndoAuditFilterSnapshotFromClipboard() {
  try {
    const [err, res] = await uni.getClipboardData();
    if (err || !res?.data) {
      uni.showToast({ title: "剪贴板为空，请先复制筛选快照", icon: "none" });
      return;
    }
    const parsed = parseCloseoutUndoAuditFilterSnapshotText(String(res.data || ""));
    if (!parsed.hasKnownField) {
      uni.showToast({ title: "未识别到有效筛选快照字段", icon: "none" });
      return;
    }
    if (!parsed.typeValid) {
      uni.showToast({ title: `快照类型不匹配：${parsed.snapshotType || "-"}`, icon: "none" });
      return;
    }
    if (!parsed.schemaValid) {
      uni.showToast({ title: `快照版本不兼容：${parsed.schemaVersion || "-"}`, icon: "none" });
      return;
    }
    let schemaVersionText = "-";
    try {
      const rawObj = JSON.parse(String(res.data || "{}")) as Record<string, unknown>;
      schemaVersionText = String(rawObj?.schemaVersion || "-");
    } catch {
      schemaVersionText = "-";
    }
    const text = [
      `预览-快照格式=${String(res.data || "").trim().startsWith("{") ? "json" : "text"}`,
      `预览-快照类型=${parsed.snapshotType || "-"}`,
      `预览-schemaVersion=${schemaVersionText}`,
      `预览-审计关键词=${parsed.hasKeyword ? (parsed.keyword || "-") : "（未提供）"}`,
      `预览-仅看有变更=${parsed.hasChangedOnly ? (parsed.changedOnly ? "是" : "否") : "（未提供）"}`
    ].join("；");
    uni.setClipboardData({
      data: text,
      success: () => uni.showToast({ title: "筛选快照预览已复制", icon: "none" }),
      fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
    });
  } catch {
    uni.showToast({ title: "预览筛选快照失败", icon: "none" });
  }
}

async function copyCloseoutUndoAuditSnapshotCompatibilityReport() {
  try {
    const [err, res] = await uni.getClipboardData();
    if (err || !res?.data) {
      uni.showToast({ title: "剪贴板为空，请先复制筛选快照", icon: "none" });
      return;
    }
    const parsed = parseCloseoutUndoAuditFilterSnapshotText(String(res.data || ""));
    const blockReason = !parsed.hasKnownField
      ? "缺少可识别字段"
      : (!parsed.typeValid ? "快照类型不匹配" : (!parsed.schemaValid ? "快照版本不兼容" : "-"));
    const recommendedAction = !parsed.hasKnownField
      ? "先补齐审计关键词或仅看有变更字段"
      : (!parsed.typeValid ? "先转换为closeout_undo_audit_filter类型快照" : (!parsed.schemaValid ? "先降级或升级到schemaVersion=1" : "可直接预览或应用"));
    const lines = [
      `兼容-快照格式=${String(res.data || "").trim().startsWith("{") ? "json" : "text"}`,
      `兼容-快照类型=${parsed.snapshotType || "-"}`,
      `兼容-schemaVersion=${parsed.schemaVersion || "-"}`,
      `兼容-类型校验=${parsed.typeValid ? "通过" : "不通过"}`,
      `兼容-版本校验=${parsed.schemaValid ? "通过" : "不通过"}`,
      `兼容-字段识别=${parsed.hasKnownField ? "通过" : "不通过"}`,
      `兼容-阻断原因=${blockReason}`,
      `兼容-建议动作=${recommendedAction}`
    ];
    uni.setClipboardData({
      data: lines.join("\n"),
      success: () => uni.showToast({ title: "快照兼容报告已复制", icon: "none" }),
      fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
    });
  } catch {
    uni.showToast({ title: "生成兼容报告失败", icon: "none" });
  }
}

async function copyCloseoutUndoAuditSnapshotCompatibilityReportJson() {
  try {
    const [err, res] = await uni.getClipboardData();
    if (err || !res?.data) {
      uni.showToast({ title: "剪贴板为空，请先复制筛选快照", icon: "none" });
      return;
    }
    const parsed = parseCloseoutUndoAuditFilterSnapshotText(String(res.data || ""));
    const blockReason = !parsed.hasKnownField
      ? "missing_known_fields"
      : (!parsed.typeValid ? "snapshot_type_mismatch" : (!parsed.schemaValid ? "schema_version_mismatch" : ""));
    const recommendedAction = !parsed.hasKnownField
      ? "add_required_filter_fields"
      : (!parsed.typeValid ? "convert_snapshot_type" : (!parsed.schemaValid ? "migrate_schema_version_to_1" : "apply_or_preview_directly"));
    const payload = {
      format: String(res.data || "").trim().startsWith("{") ? "json" : "text",
      snapshotType: parsed.snapshotType || "-",
      schemaVersion: parsed.schemaVersion || "-",
      typeValid: Boolean(parsed.typeValid),
      schemaValid: Boolean(parsed.schemaValid),
      hasKnownField: Boolean(parsed.hasKnownField),
      blockReason,
      recommendedAction,
      generatedAt: new Date().toISOString()
    };
    uni.setClipboardData({
      data: JSON.stringify(payload, null, 2),
      success: () => uni.showToast({ title: "快照兼容报告JSON已复制", icon: "none" }),
      fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
    });
  } catch {
    uni.showToast({ title: "生成兼容报告失败", icon: "none" });
  }
}

async function copyCloseoutUndoAuditFilterDiffWithClipboard() {
  try {
    const [err, res] = await uni.getClipboardData();
    if (err || !res?.data) {
      uni.showToast({ title: "剪贴板为空，请先复制筛选快照", icon: "none" });
      return;
    }
    const parsed = parseCloseoutUndoAuditFilterSnapshotText(String(res.data || ""));
    if (!parsed.hasKnownField) {
      uni.showToast({ title: "未识别到有效筛选快照字段", icon: "none" });
      return;
    }
    if (!parsed.typeValid) {
      uni.showToast({ title: `快照类型不匹配：${parsed.snapshotType || "-"}`, icon: "none" });
      return;
    }
    if (!parsed.schemaValid) {
      uni.showToast({ title: `快照版本不兼容：${parsed.schemaVersion || "-"}`, icon: "none" });
      return;
    }
    const currentKeyword = closeoutUndoAuditKeyword.value.trim();
    const currentChangedOnly = closeoutUndoAuditChangedOnly.value;
    const nextKeyword = parsed.hasKeyword ? parsed.keyword : currentKeyword;
    const nextChangedOnly = parsed.hasChangedOnly ? parsed.changedOnly : currentChangedOnly;
    const keywordChanged = currentKeyword !== nextKeyword;
    const changedOnlyChanged = currentChangedOnly !== nextChangedOnly;
    const lines = [
      `差异-审计关键词：当前=${currentKeyword || "-"} / 快照=${parsed.hasKeyword ? (nextKeyword || "-") : "（未提供）"} / 变更=${keywordChanged ? "是" : "否"}`,
      `差异-仅看有变更：当前=${currentChangedOnly ? "是" : "否"} / 快照=${parsed.hasChangedOnly ? (nextChangedOnly ? "是" : "否") : "（未提供）"} / 变更=${changedOnlyChanged ? "是" : "否"}`
    ];
    uni.setClipboardData({
      data: lines.join("\n"),
      success: () => uni.showToast({ title: "筛选快照差异已复制", icon: "none" }),
      fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
    });
  } catch {
    uni.showToast({ title: "对比筛选快照失败", icon: "none" });
  }
}

async function applyCloseoutUndoAuditFilterSnapshotFromClipboard() {
  try {
    const [err, res] = await uni.getClipboardData();
    if (err || !res?.data) {
      uni.showToast({ title: "剪贴板为空，请先复制筛选快照", icon: "none" });
      return;
    }
    const parsed = parseCloseoutUndoAuditFilterSnapshotText(String(res.data || ""));
    if (!parsed.hasKnownField) {
      uni.showToast({ title: "未识别到有效筛选快照字段", icon: "none" });
      return;
    }
    if (!parsed.typeValid) {
      uni.showToast({ title: `快照类型不匹配：${parsed.snapshotType || "-"}`, icon: "none" });
      return;
    }
    if (!parsed.schemaValid) {
      uni.showToast({ title: `快照版本不兼容：${parsed.schemaVersion || "-"}`, icon: "none" });
      return;
    }
    if (parsed.hasKeyword) {
      closeoutUndoAuditKeyword.value = parsed.keyword;
    }
    if (parsed.hasChangedOnly) {
      closeoutUndoAuditChangedOnly.value = parsed.changedOnly;
    }
    saveCloseoutFilterPrefs();
    uni.showToast({ title: "已应用审计筛选快照", icon: "none" });
  } catch {
    uni.showToast({ title: "应用筛选快照失败", icon: "none" });
  }
}

function keepFilteredCloseoutRepairedUndoAuditHistory() {
  const rows = closeoutFilteredRepairedUndoAuditRows.value.slice(0, 5);
  if (!rows.length) {
    uni.showToast({ title: "当前无命中审计可保留", icon: "none" });
    return;
  }
  uni.setStorageSync(CLOSEOUT_REPAIRED_UNDO_AUDIT_HISTORY_KEY, rows);
  closeoutExportSchemeVersion.value += 1;
  uni.showToast({ title: `已仅保留${rows.length}条命中审计`, icon: "none" });
}

function sortCloseoutRepairedUndoAuditBySnapshotSavedAt() {
  const rows = readCloseoutRepairedUndoAuditHistory();
  if (!rows.length) {
    uni.showToast({ title: "暂无审计可排序", icon: "none" });
    return;
  }
  const sorted = [...rows]
    .sort((a, b) => String(b.snapshotSavedAt || "").localeCompare(String(a.snapshotSavedAt || "")))
    .slice(0, 5);
  uni.setStorageSync(CLOSEOUT_REPAIRED_UNDO_AUDIT_HISTORY_KEY, sorted);
  closeoutExportSchemeVersion.value += 1;
  uni.showToast({ title: "已按快照时间排序审计", icon: "none" });
}

function sortCloseoutRepairedUndoAuditByExecutedAt() {
  const rows = readCloseoutRepairedUndoAuditHistory();
  if (!rows.length) {
    uni.showToast({ title: "暂无审计可排序", icon: "none" });
    return;
  }
  const sorted = [...rows]
    .sort((a, b) => String(b.executedAt || "").localeCompare(String(a.executedAt || "")))
    .slice(0, 5);
  uni.setStorageSync(CLOSEOUT_REPAIRED_UNDO_AUDIT_HISTORY_KEY, sorted);
  closeoutExportSchemeVersion.value += 1;
  uni.showToast({ title: "已按执行时间排序审计", icon: "none" });
}

function copyCloseoutRepairedUndoAuditJson() {
  const rows = readCloseoutRepairedUndoAuditHistory();
  uni.setClipboardData({
    data: JSON.stringify(rows, null, 2),
    success: () => uni.showToast({ title: "回滚审计JSON已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function clearCloseoutRepairedUndoAuditHistory() {
  uni.removeStorageSync(CLOSEOUT_REPAIRED_UNDO_AUDIT_HISTORY_KEY);
  closeoutExportSchemeVersion.value += 1;
  uni.showToast({ title: "回滚审计已清空", icon: "none" });
}

async function importCloseoutRepairedUndoAuditFromClipboard() {
  try {
    const [err, res] = await uni.getClipboardData();
    if (err || !res?.data) {
      uni.showToast({ title: "剪贴板为空，请先复制审计JSON", icon: "none" });
      return;
    }
    const parsed = JSON.parse(String(res.data || "[]"));
    if (!Array.isArray(parsed)) {
      uni.showToast({ title: "JSON格式不正确（需为数组）", icon: "none" });
      return;
    }
    const normalized = normalizeCloseoutRepairedUndoAuditRows(parsed);
    uni.setStorageSync(CLOSEOUT_REPAIRED_UNDO_AUDIT_HISTORY_KEY, normalized);
    closeoutExportSchemeVersion.value += 1;
    uni.showToast({ title: `已导入回滚审计(${normalized.length}条)`, icon: "none" });
  } catch {
    uni.showToast({ title: "导入失败，请检查JSON", icon: "none" });
  }
}

function undoLastRepairedSchemeSave() {
  const payload = getUndoableRepairedSchemeBackupPayload(true);
  if (!payload) return;
  const currentItems = closeoutExportSchemeHistory.value.slice(0, 3);
  const normalized = payload.items.slice(0, 3);
  const beforeNames = currentItems.map((x) => x.name || "-");
  const afterNames = normalized.map((x) => x.name || "-");
  const removedNames = beforeNames.filter((x) => !afterNames.includes(x));
  const restoredNames = afterNames.filter((x) => !beforeNames.includes(x));
  const beforeActiveName = closeoutActiveExportSchemeName.value || "";
  uni.setStorageSync(CLOSEOUT_EXPORT_SCHEME_HISTORY_KEY, normalized);
  const activeFromBackup = String(payload.activeName || "");
  let afterActiveName = "";
  if (activeFromBackup && normalized.some((x) => x.name === activeFromBackup)) {
    setCloseoutActiveExportSchemeName(activeFromBackup);
    afterActiveName = activeFromBackup;
  } else {
    const fallbackName = normalized[0]?.name || "";
    setCloseoutActiveExportSchemeName(fallbackName);
    afterActiveName = fallbackName;
  }
  const consumedPayload: CloseoutExportSchemeBackup = {
    reason: `${String(payload.reason || "save_repaired_scheme")}_consumed`,
    savedAt: new Date().toISOString(),
    activeName: String(payload.activeName || normalized[0]?.name || ""),
    items: normalized
  };
  uni.setStorageSync(CLOSEOUT_EXPORT_SCHEME_BACKUP_KEY, consumedPayload);
  appendCloseoutRepairedUndoAudit({
    executedAt: new Date().toISOString(),
    snapshotSavedAt: String(payload.savedAt || "-"),
    snapshotReason: String(payload.reason || "-"),
    beforeActiveName,
    afterActiveName,
    removedNames,
    restoredNames
  });
  closeoutExportSchemeVersion.value += 1;
  uni.showToast({ title: `已撤销修复沉淀(${normalized.length}条)`, icon: "none" });
}

function copyUndoRepairedSchemePreview() {
  const payload = getUndoableRepairedSchemeBackupPayload(true);
  if (!payload) return;
  const backupItems = payload.items.slice(0, 3);
  const currentItems = closeoutExportSchemeHistory.value.slice(0, 3);
  const backupNames = backupItems.map((x) => x.name || "-");
  const currentNames = currentItems.map((x) => x.name || "-");
  const added = currentNames.filter((x) => !backupNames.includes(x));
  const removed = backupNames.filter((x) => !currentNames.includes(x));
  const lines = [
    `回滚预览来源：${payload.savedAt} / reason=${payload.reason}`,
    `当前活动方案：${closeoutActiveExportSchemeName.value || "-"}`,
    `回滚后活动方案：${payload.activeName || backupItems[0]?.name || "-"}`,
    `当前方案数：${currentItems.length} / 快照方案数：${backupItems.length}`,
    `将移除(当前有/快照无)：${added.join(",") || "-"}`,
    `将恢复(快照有/当前无)：${removed.join(",") || "-"}`,
    `当前方案：${currentNames.join(",") || "-"}`,
    `快照方案：${backupNames.join(",") || "-"}`
  ];
  uni.setClipboardData({
    data: lines.join("\n"),
    success: () => uni.showToast({ title: "回滚预览已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function repairCloseoutExportSchemeBackupAndSave() {
  const payload = getCloseoutExportSchemeBackupPayload();
  if (!payload) {
    uni.showToast({ title: "暂无可修复备份", icon: "none" });
    return;
  }
  const repairedItems = payload.items.map((scheme) => {
    const resolvedFields = resolveCloseoutExportFieldsByTemplate(scheme.template, scheme.customFieldsText || "");
    const nextCustomFieldsText = scheme.template === "custom" ? resolvedFields.join(",") : String(scheme.customFieldsText || "");
    return {
      ...scheme,
      customFieldsText: nextCustomFieldsText,
      resolvedFields
    };
  });
  const activeName = payload.activeName && repairedItems.some((x) => x.name === payload.activeName)
    ? payload.activeName
    : repairedItems[0]?.name || "";
  const repairedPayload: CloseoutExportSchemeBackup = {
    reason: `${payload.reason || "repair"}_repaired`,
    savedAt: new Date().toISOString(),
    activeName,
    items: repairedItems.slice(0, 3)
  };
  uni.setStorageSync(CLOSEOUT_EXPORT_SCHEME_BACKUP_KEY, repairedPayload);
  closeoutExportSchemeVersion.value += 1;
  uni.showToast({ title: `备份已修复并保存(${repairedPayload.items.length}条)`, icon: "none" });
}

function applyCloseoutExportSchemeFromBackupTarget(target: CloseoutExportScheme) {
  if (!target) {
    uni.showToast({ title: "备份无可用方案", icon: "none" });
    return;
  }
  closeoutExportTemplate.value = target.template;
  if (target.template === "custom") {
    const parsed = parseCloseoutCustomFieldsText(target.customFieldsText || "");
    if (!parsed.valid.length) {
      closeoutExportCustomFieldsText.value = DEFAULT_CLOSEOUT_EXPORT_FIELDS.join(",");
      uni.showToast({ title: "备份自定义字段无效，已回退默认字段", icon: "none" });
    } else {
      closeoutExportCustomFieldsText.value = parsed.valid.join(",");
      if (parsed.invalid.length) {
        uni.showToast({ title: `备份含${parsed.invalid.length}个无效字段，已自动纠偏`, icon: "none" });
      }
    }
  } else {
    closeoutExportCustomFieldsText.value = target.customFieldsText || "";
  }
  closeoutExportSchemeName.value = target.name || "";
  closeoutExportSchemeNote.value = String(target.note || "");
  saveCloseoutFilterPrefs();
  uni.showToast({ title: `已回填备份方案：${target.name || "-"}`, icon: "none" });
}

function applyCloseoutExportSchemeFromBackupActive() {
  const payload = getCloseoutExportSchemeBackupPayload();
  if (!payload) {
    uni.showToast({ title: "暂无可应用备份", icon: "none" });
    return;
  }
  const targetByActive = payload.activeName ? payload.items.find((x) => x.name === payload.activeName) : undefined;
  const target = targetByActive || payload.items[0];
  if (!target) {
    uni.showToast({ title: "备份无可用方案", icon: "none" });
    return;
  }
  applyCloseoutExportSchemeFromBackupTarget(target);
}

function applyCloseoutExportSchemeFromBackupByRow(rowIndex: number) {
  const row = closeoutExportSchemeBackupRows.value[rowIndex];
  if (!row) {
    uni.showToast({ title: "备份条目不存在", icon: "none" });
    return;
  }
  applyCloseoutExportSchemeFromBackupTarget(row.scheme);
}

function copyCloseoutExportSchemeBackupJson() {
  const raw = uni.getStorageSync(CLOSEOUT_EXPORT_SCHEME_BACKUP_KEY);
  if (!raw || typeof raw !== "object") {
    uni.showToast({ title: "暂无可复制备份", icon: "none" });
    return;
  }
  const text = JSON.stringify(raw, null, 2);
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "备份JSON已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function clearCloseoutExportSchemeBackup() {
  uni.removeStorageSync(CLOSEOUT_EXPORT_SCHEME_BACKUP_KEY);
  closeoutExportSchemeVersion.value += 1;
  uni.showToast({ title: "备份已清空", icon: "none" });
}

async function importCloseoutExportSchemeBackupFromClipboard() {
  try {
    const [err, res] = await uni.getClipboardData();
    if (err || !res?.data) {
      uni.showToast({ title: "剪贴板为空，请先复制备份JSON", icon: "none" });
      return;
    }
    const parsed = JSON.parse(String(res.data || "{}"));
    if (!parsed || typeof parsed !== "object") {
      uni.showToast({ title: "JSON格式不正确", icon: "none" });
      return;
    }
    const normalizedItems = (Array.isArray((parsed as any).items) ? (parsed as any).items : [])
      .map((x: any) => normalizeCloseoutExportScheme(x))
      .filter((x: CloseoutExportScheme | null): x is CloseoutExportScheme => Boolean(x))
      .slice(0, 3);
    if (!normalizedItems.length) {
      uni.showToast({ title: "备份中无有效方案", icon: "none" });
      return;
    }
    const payload: CloseoutExportSchemeBackup = {
      reason: String((parsed as any).reason || "import_backup"),
      savedAt: String((parsed as any).savedAt || new Date().toISOString()),
      activeName: String((parsed as any).activeName || ""),
      items: normalizedItems
    };
    uni.setStorageSync(CLOSEOUT_EXPORT_SCHEME_BACKUP_KEY, payload);
    closeoutExportSchemeVersion.value += 1;
    uni.showToast({ title: `已导入备份(${normalizedItems.length}条)`, icon: "none" });
  } catch {
    uni.showToast({ title: "导入备份失败，请检查JSON", icon: "none" });
  }
}

function safeApplyCloseoutExportScheme(rowIndex: number) {
  const index = schemeActionIndex(rowIndex);
  if (index < 0) {
    uni.showToast({ title: "方案索引失效，请刷新后重试", icon: "none" });
    return;
  }
  applyCloseoutExportSchemeByIndex(index);
}

function safeApplyCloseoutExportSchemeAndCopyHeader(rowIndex: number) {
  const index = schemeActionIndex(rowIndex);
  if (index < 0) {
    uni.showToast({ title: "方案索引失效，请刷新后重试", icon: "none" });
    return;
  }
  applyCloseoutExportSchemeAndCopyHeader(index);
}

function safeApplyCloseoutExportSchemeAndCopyConfig(rowIndex: number) {
  const index = schemeActionIndex(rowIndex);
  if (index < 0) {
    uni.showToast({ title: "方案索引失效，请刷新后重试", icon: "none" });
    return;
  }
  applyCloseoutExportSchemeAndCopyConfig(index);
}

function safeTogglePinCloseoutExportScheme(rowIndex: number) {
  const index = schemeActionIndex(rowIndex);
  if (index < 0) {
    uni.showToast({ title: "方案索引失效，请刷新后重试", icon: "none" });
    return;
  }
  togglePinCloseoutExportSchemeByIndex(index);
}

function safeRenameCloseoutExportScheme(rowIndex: number) {
  const index = schemeActionIndex(rowIndex);
  if (index < 0) {
    uni.showToast({ title: "方案索引失效，请刷新后重试", icon: "none" });
    return;
  }
  renameCloseoutExportSchemeByIndex(index);
}

function safeCopySingleCloseoutExportSchemeJson(rowIndex: number) {
  const index = schemeActionIndex(rowIndex);
  if (index < 0) {
    uni.showToast({ title: "方案索引失效，请刷新后重试", icon: "none" });
    return;
  }
  copySingleCloseoutExportSchemeJson(index);
}

function safeRemoveCloseoutExportScheme(rowIndex: number) {
  const index = schemeActionIndex(rowIndex);
  if (index < 0) {
    uni.showToast({ title: "方案索引失效，请刷新后重试", icon: "none" });
    return;
  }
  removeCloseoutExportSchemeByIndex(index);
}

function setCloseoutActiveExportSchemeName(name: string) {
  const next = String(name || "");
  closeoutActiveExportSchemeName.value = next;
  uni.setStorageSync(CLOSEOUT_ACTIVE_EXPORT_SCHEME_KEY, next);
}
const closeoutExportFieldCount = computed(() => closeoutResolvedExportFields.value.length);
const closeoutCustomExportWarning = computed(() => {
  if (closeoutExportTemplate.value !== "custom") return "";
  if (!closeoutCustomFieldParseResult.value.valid.length) {
    return "当前自定义字段均无效，导出将回退到默认字段组合。";
  }
  return "";
});

function setCloseoutExportTemplate(template: "default" | "minimal" | "full" | "custom") {
  closeoutExportTemplate.value = template;
  saveCloseoutFilterPrefs();
}

function saveCurrentCloseoutExportScheme() {
  const name = closeoutExportSchemeName.value.trim();
  if (!name) {
    uni.showToast({ title: "请先输入方案名", icon: "none" });
    return;
  }
  let normalizedCustomFieldsText = closeoutExportCustomFieldsText.value.trim();
  let resolvedFields = [...closeoutResolvedExportFields.value];
  if (closeoutExportTemplate.value === "custom") {
    const parsed = parseCloseoutCustomFieldsText(normalizedCustomFieldsText);
    if (!parsed.valid.length) {
      normalizedCustomFieldsText = DEFAULT_CLOSEOUT_EXPORT_FIELDS.join(",");
      resolvedFields = [...DEFAULT_CLOSEOUT_EXPORT_FIELDS];
      uni.showToast({ title: "自定义字段为空或无效，已回退默认字段保存", icon: "none" });
    } else {
      normalizedCustomFieldsText = parsed.valid.join(",");
      resolvedFields = [...parsed.valid];
      if (parsed.invalid.length) {
        uni.showToast({ title: `已忽略${parsed.invalid.length}个无效字段并保存`, icon: "none" });
      }
    }
    closeoutExportCustomFieldsText.value = normalizedCustomFieldsText;
  }
  const existed = closeoutExportSchemeHistory.value.find((x) => x.name === name);
  const next: CloseoutExportScheme = {
    name,
    note: closeoutExportSchemeNote.value.trim(),
    template: closeoutExportTemplate.value,
    customFieldsText: normalizedCustomFieldsText,
    resolvedFields,
    pinned: Boolean(existed?.pinned),
    useCount: Number(existed?.useCount || 0),
    lastUsedAt: String(existed?.lastUsedAt || ""),
    savedAt: new Date().toISOString()
  };
  const merged = [next, ...closeoutExportSchemeHistory.value.filter((x) => x.name !== name)].slice(0, 3);
  uni.setStorageSync(CLOSEOUT_EXPORT_SCHEME_HISTORY_KEY, merged);
  setCloseoutActiveExportSchemeName(name);
  closeoutExportSchemeVersion.value += 1;
  uni.showToast({ title: "导出方案已保存", icon: "none" });
}

function fillCloseoutExportSchemeNameByCurrentContext() {
  const dayPart = closeoutSelectedDay.value || "all-days";
  const envPart = closeoutEnv.value || "all-env";
  const templatePart = closeoutExportTemplate.value;
  closeoutExportSchemeName.value = `closeout_${envPart}_${dayPart}_${templatePart}`;
}

function applyCloseoutExportSchemeByIndex(index: number) {
  const row = closeoutExportSchemeHistory.value[index];
  if (!row) {
    uni.showToast({ title: "方案不存在", icon: "none" });
    return;
  }
  closeoutExportTemplate.value = row.template;
  if (row.template === "custom") {
    const parsed = parseCloseoutCustomFieldsText(row.customFieldsText || "");
    if (!parsed.valid.length) {
      closeoutExportCustomFieldsText.value = DEFAULT_CLOSEOUT_EXPORT_FIELDS.join(",");
      uni.showToast({ title: "方案自定义字段无效，已回退默认字段", icon: "none" });
    } else {
      closeoutExportCustomFieldsText.value = parsed.valid.join(",");
      if (parsed.invalid.length) {
        uni.showToast({ title: `方案含${parsed.invalid.length}个无效字段，已自动纠偏`, icon: "none" });
      }
    }
  } else {
    closeoutExportCustomFieldsText.value = row.customFieldsText || "";
  }
  closeoutExportSchemeName.value = row.name || "";
  closeoutExportSchemeNote.value = String(row.note || "");
  setCloseoutActiveExportSchemeName(row.name || "");
  saveCloseoutFilterPrefs();
  const usedRow: CloseoutExportScheme = {
    ...row,
    useCount: Number(row.useCount || 0) + 1,
    lastUsedAt: new Date().toISOString()
  };
  const reordered = [usedRow, ...closeoutExportSchemeHistory.value.filter((_, idx) => idx !== index)].slice(0, 3);
  uni.setStorageSync(CLOSEOUT_EXPORT_SCHEME_HISTORY_KEY, reordered);
  closeoutExportSchemeVersion.value += 1;
  uni.showToast({ title: "已应用导出方案", icon: "none" });
}

function applyCloseoutExportSchemeAndCopyHeader(index: number) {
  applyCloseoutExportSchemeByIndex(index);
  copyCloseoutExportHeader();
}

function applyCloseoutExportSchemeAndCopyConfig(index: number) {
  applyCloseoutExportSchemeByIndex(index);
  copyCloseoutExportTemplateConfig();
}

function renameCloseoutExportSchemeByIndex(index: number) {
  const row = closeoutExportSchemeHistory.value[index];
  if (!row) {
    uni.showToast({ title: "方案不存在", icon: "none" });
    return;
  }
  const nextName = closeoutExportSchemeName.value.trim();
  if (!nextName) {
    uni.showToast({ title: "请先输入新方案名", icon: "none" });
    return;
  }
  const nextRow: CloseoutExportScheme = {
    ...row,
    name: nextName,
    note: closeoutExportSchemeNote.value.trim(),
    pinned: Boolean(row.pinned),
    savedAt: new Date().toISOString()
  };
  const next = [nextRow, ...closeoutExportSchemeHistory.value.filter((_, idx) => idx !== index && _.name !== nextName)].slice(0, 3);
  uni.setStorageSync(CLOSEOUT_EXPORT_SCHEME_HISTORY_KEY, next);
  setCloseoutActiveExportSchemeName(nextName);
  closeoutExportSchemeVersion.value += 1;
  uni.showToast({ title: "方案名已更新", icon: "none" });
}

function removeCloseoutExportSchemeByIndex(index: number) {
  const row = closeoutExportSchemeHistory.value[index];
  if (!row) {
    uni.showToast({ title: "方案不存在", icon: "none" });
    return;
  }
  const next = closeoutExportSchemeHistory.value.filter((_, idx) => idx !== index).slice(0, 3);
  uni.setStorageSync(CLOSEOUT_EXPORT_SCHEME_HISTORY_KEY, next);
  if (closeoutActiveExportSchemeName.value && row.name === closeoutActiveExportSchemeName.value) {
    setCloseoutActiveExportSchemeName(next[0]?.name || "");
  }
  closeoutExportSchemeVersion.value += 1;
  uni.showToast({ title: "方案已删除", icon: "none" });
}

function copySingleCloseoutExportSchemeJson(index: number) {
  const row = closeoutExportSchemeHistory.value[index];
  if (!row) {
    uni.showToast({ title: "方案不存在", icon: "none" });
    return;
  }
  const text = JSON.stringify(row, null, 2);
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "单条方案JSON已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function clearCloseoutExportSchemeHistory() {
  backupCloseoutExportSchemes("clear_history");
  uni.removeStorageSync(CLOSEOUT_EXPORT_SCHEME_HISTORY_KEY);
  setCloseoutActiveExportSchemeName("");
  closeoutExportSchemeVersion.value += 1;
  uni.showToast({ title: "导出方案已清空", icon: "none" });
}

function restoreDefaultCloseoutExportSchemes() {
  backupCloseoutExportSchemes("restore_default");
  const defaults = buildDefaultCloseoutExportSchemes().slice(0, 3);
  uni.setStorageSync(CLOSEOUT_EXPORT_SCHEME_HISTORY_KEY, defaults);
  setCloseoutActiveExportSchemeName(defaults[0]?.name || "");
  closeoutExportSchemeVersion.value += 1;
  uni.showToast({ title: "已恢复默认方案池", icon: "none" });
}

function exportCloseoutExportSchemeHistoryJson() {
  const text = JSON.stringify(closeoutExportSchemeHistory.value, null, 2);
  uni.setClipboardData({
    data: text || "[]",
    success: () => uni.showToast({ title: "方案JSON已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function normalizeCloseoutExportScheme(input: any): CloseoutExportScheme | null {
  if (!input || typeof input !== "object") return null;
  const template = String(input.template || "default");
  const normalizedTemplate = ["default", "minimal", "full", "custom"].includes(template)
    ? (template as "default" | "minimal" | "full" | "custom")
    : "default";
  const resolvedFields = Array.isArray(input.resolvedFields)
    ? input.resolvedFields.map((x: any) => String(x || "")).filter(Boolean).slice(0, 20)
    : [];
  return {
    name: String(input.name || `scheme_${Date.now()}`),
    note: String(input.note || ""),
    template: normalizedTemplate,
    customFieldsText: String(input.customFieldsText || ""),
    resolvedFields,
    pinned: Boolean(input.pinned),
    useCount: Math.max(0, Number(input.useCount || 0) || 0),
    lastUsedAt: String(input.lastUsedAt || ""),
    savedAt: String(input.savedAt || new Date().toISOString())
  };
}

async function importCloseoutExportSchemeHistoryFromClipboard() {
  try {
    const [err, res] = await uni.getClipboardData();
    if (err || !res?.data) {
      uni.showToast({ title: "剪贴板为空，请先复制JSON", icon: "none" });
      return;
    }
    const parsed = JSON.parse(String(res.data || "[]"));
    if (!Array.isArray(parsed)) {
      uni.showToast({ title: "JSON格式不正确（需为数组）", icon: "none" });
      return;
    }
    const normalized = parsed
      .map((x) => normalizeCloseoutExportScheme(x))
      .filter((x): x is CloseoutExportScheme => Boolean(x))
      .slice(0, 3);
    backupCloseoutExportSchemes("import_json");
    uni.setStorageSync(CLOSEOUT_EXPORT_SCHEME_HISTORY_KEY, normalized);
    setCloseoutActiveExportSchemeName(normalized[0]?.name || "");
    closeoutExportSchemeVersion.value += 1;
    uni.showToast({ title: `已导入${normalized.length}条方案`, icon: "none" });
  } catch {
    uni.showToast({ title: "导入失败，请检查JSON", icon: "none" });
  }
}

function applyLastUsedCloseoutExportScheme() {
  const target = closeoutActiveExportSchemeName.value;
  if (!target) {
    uni.showToast({ title: "暂无最近方案", icon: "none" });
    return;
  }
  const index = closeoutExportSchemeHistory.value.findIndex((x) => x.name === target);
  if (index < 0) {
    uni.showToast({ title: "最近方案不存在", icon: "none" });
    return;
  }
  applyCloseoutExportSchemeByIndex(index);
}

function copyCloseoutExportSchemeHistorySummary() {
  const text = closeoutExportSchemeHistory.value
    .map((x, idx) => `${idx + 1}. ${x.name} | 置顶=${x.pinned ? "是" : "否"} | 备注=${x.note || "-"} | 模板=${x.template} | 使用=${x.useCount || 0} | 最近使用=${x.lastUsedAt || "-"} | 字段=${(x.resolvedFields || []).join(",") || "-"}`)
    .join("\n");
  uni.setClipboardData({
    data: text || "暂无导出方案",
    success: () => uni.showToast({ title: "方案摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyFilteredCloseoutExportSchemeSummary() {
  if (!closeoutFilteredExportSchemeRows.value.length) {
    uni.showToast({ title: "当前无命中方案可复制", icon: "none" });
    return;
  }
  const text = closeoutFilteredExportSchemeRows.value
    .map((row, idx) => `${idx + 1}. ${getSchemeDisplayText(row.scheme)}`)
    .join("\n");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "命中方案摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function keepPinnedCloseoutExportSchemesOnly() {
  const pinned = closeoutExportSchemeHistory.value.filter((x) => x.pinned).slice(0, 3);
  if (!pinned.length) {
    uni.showToast({ title: "暂无置顶方案可保留", icon: "none" });
    return;
  }
  backupCloseoutExportSchemes("keep_pinned");
  uni.setStorageSync(CLOSEOUT_EXPORT_SCHEME_HISTORY_KEY, pinned);
  if (!pinned.some((x) => x.name === closeoutActiveExportSchemeName.value)) {
    setCloseoutActiveExportSchemeName(pinned[0]?.name || "");
  }
  closeoutExportSchemeVersion.value += 1;
  uni.showToast({ title: `已仅保留${pinned.length}条置顶方案`, icon: "none" });
}

function keepFilteredCloseoutExportSchemesOnly() {
  const filtered = closeoutFilteredExportSchemeRows.value.map((x) => x.scheme).slice(0, 3);
  if (!filtered.length) {
    uni.showToast({ title: "当前无命中方案可保留", icon: "none" });
    return;
  }
  backupCloseoutExportSchemes("keep_filtered");
  uni.setStorageSync(CLOSEOUT_EXPORT_SCHEME_HISTORY_KEY, filtered);
  if (!filtered.some((x) => x.name === closeoutActiveExportSchemeName.value)) {
    setCloseoutActiveExportSchemeName(filtered[0]?.name || "");
  }
  closeoutExportSchemeVersion.value += 1;
  uni.showToast({ title: `已仅保留${filtered.length}条命中方案`, icon: "none" });
}

function togglePinCloseoutExportSchemeByIndex(index: number) {
  const row = closeoutExportSchemeHistory.value[index];
  if (!row) {
    uni.showToast({ title: "方案不存在", icon: "none" });
    return;
  }
  const updated: CloseoutExportScheme = { ...row, pinned: !row.pinned };
  const list = closeoutExportSchemeHistory.value.map((item, idx) => (idx === index ? updated : item));
  const pinned = list.filter((x) => x.pinned);
  const normal = list.filter((x) => !x.pinned);
  const merged = [...pinned, ...normal].slice(0, 3);
  uni.setStorageSync(CLOSEOUT_EXPORT_SCHEME_HISTORY_KEY, merged);
  closeoutExportSchemeVersion.value += 1;
  uni.showToast({ title: updated.pinned ? "已置顶方案" : "已取消置顶", icon: "none" });
}

function sortCloseoutExportSchemeHistoryByUseCount() {
  if (!closeoutExportSchemeHistory.value.length) {
    uni.showToast({ title: "暂无可排序方案", icon: "none" });
    return;
  }
  const sorted = [...closeoutExportSchemeHistory.value]
    .sort((a, b) => {
      if (Boolean(a.pinned) !== Boolean(b.pinned)) return a.pinned ? -1 : 1;
      const useDelta = Number(b.useCount || 0) - Number(a.useCount || 0);
      if (useDelta !== 0) return useDelta;
      return String(b.lastUsedAt || "").localeCompare(String(a.lastUsedAt || ""));
    })
    .slice(0, 3);
  uni.setStorageSync(CLOSEOUT_EXPORT_SCHEME_HISTORY_KEY, sorted);
  closeoutExportSchemeVersion.value += 1;
  uni.showToast({ title: "已按使用频次排序", icon: "none" });
}

function sortCloseoutExportSchemeHistoryByLastUsed() {
  if (!closeoutExportSchemeHistory.value.length) {
    uni.showToast({ title: "暂无可排序方案", icon: "none" });
    return;
  }
  const sorted = [...closeoutExportSchemeHistory.value]
    .sort((a, b) => {
      if (Boolean(a.pinned) !== Boolean(b.pinned)) return a.pinned ? -1 : 1;
      const lastUsedDelta = String(b.lastUsedAt || "").localeCompare(String(a.lastUsedAt || ""));
      if (lastUsedDelta !== 0) return lastUsedDelta;
      const useDelta = Number(b.useCount || 0) - Number(a.useCount || 0);
      if (useDelta !== 0) return useDelta;
      return String(b.savedAt || "").localeCompare(String(a.savedAt || ""));
    })
    .slice(0, 3);
  uni.setStorageSync(CLOSEOUT_EXPORT_SCHEME_HISTORY_KEY, sorted);
  closeoutExportSchemeVersion.value += 1;
  uni.showToast({ title: "已按最近使用排序", icon: "none" });
}

function applyCloseoutFieldPreset(preset: "handover" | "troubleshoot" | "audit") {
  const presetMap: Record<string, string[]> = {
    handover: ["received_at", "policy_env", "reason_code", "closeout_reason_code", "run_id"],
    troubleshoot: ["received_at", "reason_code", "closeout_reason_code", "run_id", "event_id"],
    audit: ["event_id", "received_at", "policy_env", "reason_code", "closeout_reason_code", "run_id"]
  };
  const next = presetMap[preset] || presetMap.handover;
  closeoutExportTemplate.value = "custom";
  closeoutExportCustomFieldsText.value = next.join(",");
  saveCloseoutFilterPrefs();
  uni.showToast({ title: "已应用字段预设", icon: "none" });
}

function fillCloseoutCustomFieldsRecommended() {
  closeoutExportCustomFieldsText.value = "received_at,policy_env,reason_code,closeout_reason_code,run_id";
  saveCloseoutFilterPrefs();
}

function clearCloseoutCustomFields() {
  closeoutExportCustomFieldsText.value = "";
  saveCloseoutFilterPrefs();
}

function normalizeCloseoutCustomFieldsInput() {
  closeoutExportCustomFieldsText.value = closeoutCustomFieldParseResult.value.valid.join(",");
  saveCloseoutFilterPrefs();
  uni.showToast({ title: "字段已规范化", icon: "none" });
}

function removeInvalidCloseoutCustomFields() {
  const { valid, invalid } = closeoutCustomFieldParseResult.value;
  if (!invalid.length) {
    uni.showToast({ title: "没有无效字段", icon: "none" });
    return;
  }
  closeoutExportCustomFieldsText.value = valid.join(",");
  saveCloseoutFilterPrefs();
  uni.showToast({ title: `已移除${invalid.length}个无效字段`, icon: "none" });
}

function removeDuplicateCloseoutCustomFields() {
  const { duplicate } = closeoutCustomFieldParseResult.value;
  if (!duplicate.length) {
    uni.showToast({ title: "没有重复字段", icon: "none" });
    return;
  }
  closeoutExportCustomFieldsText.value = closeoutCustomFieldParseResult.value.valid
    .concat(closeoutCustomFieldParseResult.value.invalid)
    .join(",");
  saveCloseoutFilterPrefs();
  uni.showToast({ title: `已移除${duplicate.length}个重复字段`, icon: "none" });
}

function toggleCloseoutCustomField(field: string) {
  const current = closeoutResolvedExportFields.value;
  let next: string[];
  if (current.includes(field)) {
    next = current.filter((x) => x !== field);
  } else {
    next = [...current, field];
  }
  closeoutExportTemplate.value = "custom";
  closeoutExportCustomFieldsText.value = next.join(",");
  saveCloseoutFilterPrefs();
}

function moveCloseoutCustomField(field: string, direction: "left" | "right") {
  const current = [...closeoutResolvedExportFields.value];
  const index = current.findIndex((x) => x === field);
  if (index < 0) return;
  if (direction === "left" && index === 0) return;
  if (direction === "right" && index === current.length - 1) return;
  const targetIndex = direction === "left" ? index - 1 : index + 1;
  const temp = current[targetIndex];
  current[targetIndex] = current[index];
  current[index] = temp;
  closeoutExportTemplate.value = "custom";
  closeoutExportCustomFieldsText.value = current.join(",");
  saveCloseoutFilterPrefs();
}

function sortCloseoutCustomFieldsByRecommendedOrder() {
  const selected = closeoutResolvedExportFields.value.filter((x) => closeoutExportFieldOptions.includes(x));
  const sorted = closeoutExportFieldOptions.filter((x) => selected.includes(x));
  closeoutExportTemplate.value = "custom";
  closeoutExportCustomFieldsText.value = sorted.join(",");
  saveCloseoutFilterPrefs();
  uni.showToast({ title: "已按推荐顺序排序", icon: "none" });
}

function reverseCloseoutCustomFieldsOrder() {
  const selected = [...closeoutResolvedExportFields.value].reverse();
  closeoutExportTemplate.value = "custom";
  closeoutExportCustomFieldsText.value = selected.join(",");
  saveCloseoutFilterPrefs();
  uni.showToast({ title: "字段顺序已反转", icon: "none" });
}

function copyCloseoutExportHeader() {
  const header = closeoutResolvedExportFields.value.join(",");
  uni.setClipboardData({
    data: header,
    success: () => uni.showToast({ title: "导出表头已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyCloseoutExportTemplateConfig() {
  const text = [
    `模板=${closeoutExportTemplate.value}`,
    `原始字段输入=${closeoutExportCustomFieldsText.value.trim() || "-"}`,
    `最终导出字段=${closeoutResolvedExportFields.value.join(",")}`,
    `无效字段=${closeoutCustomFieldParseResult.value.invalid.join(",") || "-"}`,
    `重复字段=${closeoutCustomFieldParseResult.value.duplicate.join(",") || "-"}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "导出配置已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function exportCloseoutRowsCsv() {
  if (!closeoutRows.value.length) {
    uni.showToast({ title: "暂无可导出明细", icon: "none" });
    return;
  }
  const header = closeoutResolvedExportFields.value;
  const lines = closeoutRows.value.map((row) => header.map((field) => String((row as Record<string, any>)?.[field] || "")));
  const csv = [header, ...lines].map((line) => line.map((x) => escapeCsvCell(x)).join(",")).join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => uni.showToast({ title: "Closeout CSV已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

const closeoutTrendDays = computed(() => {
  const trend = closeoutSummary.value?.trend_by_day || {};
  return Object.keys(trend)
    .sort((a, b) => String(b).localeCompare(String(a)))
    .slice(0, 7);
});

const closeoutReasonTopRows = computed(() => {
  const source = closeoutSummary.value?.by_reason_code || {};
  return Object.entries(source)
    .map(([key, count]) => ({ key, count: Number(count || 0) }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 6);
});

const closeoutReasonOutTopRows = computed(() => {
  const source = closeoutSummary.value?.by_closeout_reason_code || {};
  return Object.entries(source)
    .map(([key, count]) => ({ key, count: Number(count || 0) }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 6);
});

function buildCloseoutDrilldownParams(offset = 0) {
  return {
    limit: closeoutPageSize.value,
    offset,
    policy_env: closeoutEnv.value || undefined,
    reason_code: closeoutReasonCode.value.trim() || undefined,
    closeout_reason_code: closeoutReasonCodeOut.value.trim() || undefined,
    received_day: closeoutSelectedDay.value || undefined,
    include_dashboard: closeoutIncludeDashboard.value
  };
}

function toggleCloseoutIncludeDashboard() {
  closeoutIncludeDashboard.value = !closeoutIncludeDashboard.value;
  saveCloseoutFilterPrefs();
}

function setCloseoutSelectedDay(day: string) {
  closeoutSelectedDay.value = String(day || "");
  saveCloseoutFilterPrefs();
}

async function applyCloseoutReasonQuick(reasonCode: string) {
  closeoutReasonCode.value = String(reasonCode || "");
  saveCloseoutFilterPrefs();
  await loadData();
}

async function applyCloseoutReasonOutQuick(reasonCode: string) {
  closeoutReasonCodeOut.value = String(reasonCode || "");
  saveCloseoutFilterPrefs();
  await loadData();
}

function copyCloseoutDashboardSummary() {
  const envTop = Object.entries(closeoutSummary.value?.by_env || {})
    .map(([key, value]) => `${key}:${value}`)
    .join(" / ");
  const reasonTop = closeoutReasonTopRows.value.map((x) => `${x.key}:${x.count}`).join(" / ");
  const closeoutTop = closeoutReasonOutTopRows.value.map((x) => `${x.key}:${x.count}`).join(" / ");
  const text = [
    `窗口总记录=${closeoutSummary.value?.total ?? 0}`,
    `环境分布=${envTop || "-"}`,
    `报警原因Top=${reasonTop || "-"}`,
    `收口原因Top=${closeoutTop || "-"}`,
    `当前筛选=env:${closeoutEnv.value || "-"},day:${closeoutSelectedDay.value || "-"},reason:${closeoutReasonCode.value || "-"},closeout:${closeoutReasonCodeOut.value || "-"}`,
    `导出模板=${closeoutExportTemplate.value}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "Closeout摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

async function loadMoreCloseoutRows() {
  if (closeoutLoadingMore.value || closeoutRows.value.length >= closeoutTotal.value) return;
  closeoutLoadingMore.value = true;
  try {
    const res = await fetchCloseoutDrilldown(buildCloseoutDrilldownParams(closeoutRows.value.length));
    const incoming = Array.isArray(res?.items) ? res.items : [];
    closeoutRows.value = [...closeoutRows.value, ...incoming];
    closeoutTotal.value = Number(res?.total || closeoutTotal.value || 0);
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `加载更多失败：${err.message}` : "加载更多失败", icon: "none" });
  } finally {
    closeoutLoadingMore.value = false;
  }
}

async function loadData() {
  loading.value = true;
  try {
    saveReportFilterPrefs();
    saveCloseoutFilterPrefs();
    const [summaryRes, listRes, alarmsRes, trafficRes, closeoutSummaryRes, closeoutDrillRes] = await Promise.allSettled([
      fetchReportSummary(),
      fetchReportList(),
      fetchAlarmStats(),
      fetchTrafficStats(),
      fetchCloseoutSummary(closeoutDays.value, closeoutEnv.value || undefined),
      fetchCloseoutDrilldown(buildCloseoutDrilldownParams(0))
    ]);

    summaryItems.value = summaryRes.status === "fulfilled" && Array.isArray(summaryRes.value.items) ? summaryRes.value.items : [];
    reportItems.value = listRes.status === "fulfilled" && Array.isArray(listRes.value.reports) ? listRes.value.reports : [];
    const reportIdSet = new Set(reportItems.value.map((x) => String(x.id || "")));
    selectedReportIds.value = selectedReportIds.value.filter((id) => reportIdSet.has(id));
    alarmItems.value = alarmsRes.status === "fulfilled" && Array.isArray(alarmsRes.value) ? alarmsRes.value : [];
    traffic.value = trafficRes.status === "fulfilled" ? trafficRes.value : null;
    closeoutSummary.value = closeoutSummaryRes.status === "fulfilled" ? closeoutSummaryRes.value : null;
    closeoutRows.value = closeoutDrillRes.status === "fulfilled" && Array.isArray(closeoutDrillRes.value.items) ? closeoutDrillRes.value.items : [];
    closeoutTotal.value = closeoutDrillRes.status === "fulfilled" ? Number(closeoutDrillRes.value.total || 0) : 0;

    const failedCount = [summaryRes, listRes, alarmsRes, trafficRes, closeoutSummaryRes, closeoutDrillRes].filter((x) => x.status === "rejected").length;
    if (failedCount > 0) {
      setLoadStatus(`部分刷新成功：失败 ${failedCount} 项`);
      uni.showToast({ title: `部分接口失败(${failedCount})`, icon: "none" });
    } else {
      setLoadStatus("刷新成功");
    }
  } catch (err: any) {
    setLoadStatus(err?.message ? `刷新失败：${err.message}` : "刷新失败");
    uni.showToast({ title: "报表数据加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

async function triggerExport(type: string, silentSuccess = false) {
  const token = getToken();
  if (!token) {
    uni.showToast({ title: "请先登录后导出", icon: "none" });
    return false;
  }
  exportLoading.value = true;
  try {
    const url = buildApiUrl(`/api/v1/reports/export?type=${encodeURIComponent(type)}`);
    const [err, res] = await uni.downloadFile({
      url,
      header: {
        Authorization: `Bearer ${token}`
      }
    });
    if (err || !res || res.statusCode < 200 || res.statusCode >= 300) {
      throw new Error(`导出失败(${res?.statusCode || "network"})`);
    }
    if (!silentSuccess) {
      uni.showToast({ title: "导出成功，文件已下载", icon: "none" });
    }
    return true;
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `导出失败：${err.message}` : "导出失败", icon: "none" });
    return false;
  } finally {
    exportLoading.value = false;
  }
}

async function exportSelectedReports() {
  const ids = [...selectedReportIds.value];
  if (!ids.length) {
    uni.showToast({ title: "请先选择报表", icon: "none" });
    return;
  }
  for (const id of ids) {
    const taskId = `${Date.now()}_${id}`;
    exportTasks.value = [{ id: taskId, name: `报表 ${id}`, statusText: "执行中" }, ...exportTasks.value].slice(0, 10);
    const ok = await triggerExport(id, true);
    exportTasks.value = exportTasks.value.map((task) => {
      if (task.id !== taskId) return task;
      return { ...task, statusText: ok ? "已完成" : "失败" };
    });
  }
  uni.showToast({ title: `已触发 ${ids.length} 项导出`, icon: "none" });
}

function copySummary() {
  const text = [
    summaryText.value,
    nextStepAdvice.value,
    `刷新状态：${loadMessage.value || "-"}`,
    `筛选快照：关键词=${reportKeyword.value.trim() || "-"} / 来源=${detailSourceFilter.value}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "报表摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

restoreFilterPrefs();
closeoutSnapshotHistoryVersion.value += 1;
onShow(loadData);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">报表中心</view>

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
      </view>
    </view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-subtext">报表清单：{{ filteredReportItems.length }} / {{ reportItems.length }} 项</text>
        <view class="app-row">
          <button size="mini" :loading="exportLoading" @click="triggerExport('summary')">导出摘要CSV</button>
          <button size="mini" :loading="exportLoading" @click="triggerExport('alarms')">导出报警CSV</button>
          <button size="mini" :loading="exportLoading" @click="triggerExport('traffic')">导出流量CSV</button>
        </view>
      </view>
      <view class="app-row">
        <input v-model="reportKeyword" placeholder="按ID/名称筛选" />
        <button size="mini" :type="detailSourceFilter === 'all' ? 'primary' : 'default'" @click="detailSourceFilter = 'all'">全部</button>
        <button size="mini" :type="detailSourceFilter === 'builtin' ? 'primary' : 'default'" @click="detailSourceFilter = 'builtin'">内置</button>
        <button size="mini" :type="detailSourceFilter === 'external' ? 'primary' : 'default'" @click="detailSourceFilter = 'external'">扩展</button>
      </view>
      <view class="app-row">
        <button size="mini" @click="toggleSelectAllVisibleReports">{{ hasAllVisibleSelected ? "取消全选命中" : "全选命中" }}</button>
        <button size="mini" @click="clearSelectedReports">清空已选</button>
        <button size="mini" @click="copyReportFilterSnapshot">复制筛选快照</button>
        <button size="mini" type="primary" :loading="exportLoading" @click="exportSelectedReports">一键导出已选（{{ selectedReportIds.length }}）</button>
      </view>
      <view v-if="filteredReportItems.length" class="app-gap-12">
        <view v-for="row in filteredReportItems" :key="row.id" class="app-row">
          <view style="flex:1">
            <text class="app-subtext">{{ row.name }}（{{ row.id }}）</text>
            <text class="app-subtext">来源：{{ normalizeSourceText(row.source) }}；格式：{{ (row.export_formats || []).join("/") || "-" }}</text>
          </view>
          <button
            size="mini"
            :type="selectedReportIds.includes(row.id) ? 'primary' : 'default'"
            @click="toggleReportSelection(row.id)"
          >
            {{ selectedReportIds.includes(row.id) ? "已选" : "选择" }}
          </button>
          <button size="mini" :loading="exportLoading" @click="triggerExport(row.id)">导出</button>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '报表加载中...' : '暂无匹配报表'" />
      <view v-if="exportTasks.length" class="app-gap-12">
        <text class="app-subtext">导出任务（最近{{ exportTasks.length }}条）</text>
        <view v-for="task in exportTasks" :key="task.id" class="app-row">
          <text class="app-subtext">{{ task.name }}</text>
          <text class="app-subtext">{{ task.statusText }}</text>
        </view>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">报警统计（类型分布）</text>
      <view v-if="alarmItems.length" class="app-gap-12">
        <view v-for="row in alarmItems" :key="row.name" class="app-row">
          <text class="app-subtext">{{ row.name }}</text>
          <text class="app-subtext">{{ row.value }}</text>
        </view>
      </view>
      <AppEmpty v-else :text="loading ? '报警统计加载中...' : '暂无报警统计'" />
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">流量趋势摘要</text>
      <text class="app-subtext">采样点：{{ traffic?.summary?.sample_count ?? 0 }}</text>
      <text class="app-subtext">平均流数：{{ traffic?.summary?.avg_streams ?? 0 }}；峰值流数：{{ traffic?.summary?.max_streams ?? 0 }}</text>
      <text class="app-subtext">平均带宽(Kbps)：{{ traffic?.summary?.avg_bandwidth_kbps ?? 0 }}；峰值带宽(Kbps)：{{ traffic?.summary?.max_bandwidth_kbps ?? 0 }}</text>
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">Closeout 看板</text>
      <view class="app-row">
        <input v-model="closeoutEnv" placeholder="环境筛选（prod/canary/dev）" />
        <input v-model="closeoutDays" type="number" placeholder="窗口天数（默认14）" />
        <button size="mini" @click="loadData">应用筛选</button>
      </view>
      <view class="app-row">
        <button size="mini" :type="closeoutEnv === '' ? 'primary' : 'default'" @click="setCloseoutEnvQuick('')">全部环境</button>
        <button size="mini" :type="closeoutEnv === 'prod' ? 'primary' : 'default'" @click="setCloseoutEnvQuick('prod')">prod</button>
        <button size="mini" :type="closeoutEnv === 'canary' ? 'primary' : 'default'" @click="setCloseoutEnvQuick('canary')">canary</button>
        <button size="mini" :type="closeoutEnv === 'dev' ? 'primary' : 'default'" @click="setCloseoutEnvQuick('dev')">dev</button>
      </view>
      <view class="app-row">
        <button size="mini" :type="closeoutDays === 7 ? 'primary' : 'default'" @click="setCloseoutDaysQuick(7)">7天</button>
        <button size="mini" :type="closeoutDays === 14 ? 'primary' : 'default'" @click="setCloseoutDaysQuick(14)">14天</button>
        <button size="mini" :type="closeoutDays === 30 ? 'primary' : 'default'" @click="setCloseoutDaysQuick(30)">30天</button>
      </view>
      <view class="app-row">
        <input v-model="closeoutReasonCode" placeholder="报警原因码（reason_code）" />
        <input v-model="closeoutReasonCodeOut" placeholder="收口原因码（closeout_reason_code）" />
        <button size="mini" @click="closeoutReasonCode = ''">清空报警码</button>
        <button size="mini" @click="closeoutReasonCodeOut = ''">清空收口码</button>
      </view>
      <view class="app-row">
        <button size="mini" :type="closeoutExportTemplate === 'default' ? 'primary' : 'default'" @click="setCloseoutExportTemplate('default')">默认导出</button>
        <button size="mini" :type="closeoutExportTemplate === 'minimal' ? 'primary' : 'default'" @click="setCloseoutExportTemplate('minimal')">最小导出</button>
        <button size="mini" :type="closeoutExportTemplate === 'full' ? 'primary' : 'default'" @click="setCloseoutExportTemplate('full')">全量导出</button>
        <button size="mini" :type="closeoutExportTemplate === 'custom' ? 'primary' : 'default'" @click="setCloseoutExportTemplate('custom')">自定义导出</button>
        <button size="mini" @click="copyCloseoutExportHeader">复制表头</button>
        <button size="mini" @click="copyCloseoutExportTemplateConfig">复制导出配置</button>
      </view>
      <view class="app-row">
        <input v-model="closeoutExportSchemeName" placeholder="导出方案名（如：夜班交接）" />
        <input v-model="closeoutExportSchemeNote" placeholder="方案备注（如：夜班值守口径）" />
        <button size="mini" @click="fillCloseoutExportSchemeNameByCurrentContext">按当前筛选命名</button>
        <button size="mini" @click="saveCurrentCloseoutExportScheme">保存方案</button>
        <button size="mini" @click="applyLastUsedCloseoutExportScheme">应用最近方案</button>
        <button size="mini" @click="copyCloseoutExportSchemeHistorySummary">复制方案摘要</button>
        <button size="mini" @click="sortCloseoutExportSchemeHistoryByUseCount">按使用排序</button>
        <button size="mini" @click="sortCloseoutExportSchemeHistoryByLastUsed">按最近排序</button>
        <button size="mini" @click="exportCloseoutExportSchemeHistoryJson">导出方案JSON</button>
        <button size="mini" @click="importCloseoutExportSchemeHistoryFromClipboard">导入方案JSON</button>
        <button size="mini" @click="restoreCloseoutExportSchemeHistoryFromBackup">恢复上次方案池</button>
        <button size="mini" @click="applyCloseoutExportSchemeFromBackupActive">从备份应用当前</button>
        <button size="mini" @click="copyCloseoutExportSchemeBackupSummary">复制备份摘要</button>
        <button size="mini" @click="copyCloseoutExportSchemeBackupDiffSummary">复制备份差异</button>
        <button size="mini" @click="copyCloseoutExportSchemeBackupHealthSummary">复制备份健康</button>
        <button size="mini" @click="copyCloseoutExportSchemeBackupRepairPreview">复制修复预览</button>
        <button size="mini" @click="applyRepairedCloseoutExportSchemeFromBackupActive">按修复结果回填当前</button>
        <button size="mini" @click="saveRepairedBackupActiveAsCloseoutExportScheme">保存修复方案到方案池</button>
        <button size="mini" :disabled="!closeoutCanUndoRepairedSchemeSave" @click="copyUndoRepairedSchemePreview">复制回滚预览</button>
        <button size="mini" :disabled="!closeoutCanUndoRepairedSchemeSave" @click="undoLastRepairedSchemeSave">撤销最近修复沉淀</button>
        <button size="mini" @click="copyCloseoutRepairedUndoAuditSummary">复制回滚审计</button>
        <button size="mini" @click="copyCloseoutRepairedUndoAuditJson">复制回滚审计JSON</button>
        <button size="mini" @click="importCloseoutRepairedUndoAuditFromClipboard">导入回滚审计JSON</button>
        <button size="mini" @click="clearCloseoutRepairedUndoAuditHistory">清空回滚审计</button>
        <button size="mini" @click="repairCloseoutExportSchemeBackupAndSave">修复并保存备份</button>
        <button size="mini" @click="copyCloseoutExportSchemeBackupJson">复制备份JSON</button>
        <button size="mini" @click="importCloseoutExportSchemeBackupFromClipboard">导入备份JSON</button>
        <button size="mini" @click="clearCloseoutExportSchemeBackup">清空备份</button>
        <button size="mini" @click="restoreDefaultCloseoutExportSchemes">恢复默认方案</button>
        <button size="mini" @click="clearCloseoutExportSchemeHistory">清空方案</button>
      </view>
      <text v-if="closeoutExportSchemeBackupMeta" class="app-subtext">
        最近备份：{{ closeoutExportSchemeBackupMeta.savedAt }} / 原因={{ closeoutExportSchemeBackupMeta.reason }} / 条数={{ closeoutExportSchemeBackupMeta.count }}
      </text>
      <text v-else class="app-subtext">最近备份：无</text>
      <text class="app-subtext">{{ closeoutUndoRepairedSchemeHint }}</text>
      <text class="app-subtext">{{ closeoutRepairedUndoAuditMeta }}</text>
      <view class="app-row">
        <input v-model="closeoutUndoAuditKeyword" @blur="saveCloseoutFilterPrefs" placeholder="按时间/原因/方案名筛选回滚审计" />
        <button size="mini" @click="resetCloseoutUndoAuditFilters">重置审计筛选</button>
        <button size="mini" @click="copyCloseoutUndoAuditFilterSnapshot">复制审计筛选快照</button>
        <button size="mini" @click="copyCloseoutUndoAuditFilterSnapshotJson">复制审计筛选快照JSON</button>
        <button size="mini" @click="previewCloseoutUndoAuditFilterSnapshotFromClipboard">预览审计筛选快照</button>
        <button size="mini" @click="copyCloseoutUndoAuditSnapshotCompatibilityReport">复制快照兼容报告</button>
        <button size="mini" @click="copyCloseoutUndoAuditSnapshotCompatibilityReportJson">复制快照兼容报告JSON</button>
        <button size="mini" @click="copyCloseoutUndoAuditFilterDiffWithClipboard">复制快照差异</button>
        <button size="mini" @click="applyCloseoutUndoAuditFilterSnapshotFromClipboard">应用审计筛选快照</button>
        <button size="mini" :type="closeoutUndoAuditChangedOnly ? 'primary' : 'default'" @click="closeoutUndoAuditChangedOnly = !closeoutUndoAuditChangedOnly; saveCloseoutFilterPrefs();">
          {{ closeoutUndoAuditChangedOnly ? "仅看有变更：开" : "仅看有变更：关" }}
        </button>
        <button size="mini" @click="copyFilteredCloseoutRepairedUndoAuditSummary">复制命中审计</button>
        <button size="mini" @click="copyChangedCloseoutRepairedUndoAuditSummary">复制有变更审计</button>
        <button size="mini" @click="keepChangedCloseoutRepairedUndoAuditHistory">仅保留有变更审计</button>
        <button size="mini" @click="keepFilteredCloseoutRepairedUndoAuditHistory">仅保留命中审计</button>
        <button size="mini" @click="sortCloseoutRepairedUndoAuditBySnapshotSavedAt">按快照排序审计</button>
        <button size="mini" @click="sortCloseoutRepairedUndoAuditByExecutedAt">按执行排序审计</button>
        <text class="app-subtext">命中={{ closeoutFilteredRepairedUndoAuditRows.length }} / 有变更={{ closeoutChangedRepairedUndoAuditCount }}</text>
      </view>
      <view v-if="closeoutExportSchemeBackupRows.length" class="app-gap-12">
        <text class="app-subtext">备份条目（最近{{ closeoutExportSchemeBackupRows.length }}条）</text>
        <view v-for="(row, idx) in closeoutExportSchemeBackupRows" :key="`backup_${row.scheme.name}_${row.scheme.savedAt}_${idx}`" class="app-row">
          <text class="app-subtext">
            {{ idx + 1 }}. {{ row.isBackupActive ? "【备份活动】" : "" }}{{ row.scheme.name }} / {{ row.scheme.note || "-" }} / {{ row.scheme.template }} / 字段={{ (row.scheme.resolvedFields || []).join(",") || "-" }}
          </text>
          <button size="mini" @click="applyCloseoutExportSchemeFromBackupByRow(idx)">回填当前</button>
        </view>
      </view>
      <view class="app-row">
        <input v-model="closeoutExportSchemeKeyword" placeholder="按方案名/备注/模板/字段筛选方案" />
        <button
          size="mini"
          :type="closeoutExportSchemePinnedOnly ? 'primary' : 'default'"
          @click="closeoutExportSchemePinnedOnly = !closeoutExportSchemePinnedOnly; saveCloseoutFilterPrefs();"
        >
          {{ closeoutExportSchemePinnedOnly ? "仅看置顶：开" : "仅看置顶：关" }}
        </button>
        <button size="mini" @click="resetCloseoutExportSchemeFilters">重置方案筛选</button>
        <button size="mini" @click="copyFilteredCloseoutExportSchemeSummary">复制命中摘要</button>
        <button size="mini" @click="keepFilteredCloseoutExportSchemesOnly">仅保留命中</button>
        <button size="mini" @click="keepPinnedCloseoutExportSchemesOnly">仅保留置顶</button>
      </view>
      <view v-if="closeoutExportSchemeHistory.length" class="app-gap-12">
        <text class="app-subtext">导出方案（命中{{ closeoutFilteredExportSchemeHistory.length }} / 最近{{ closeoutExportSchemeHistory.length }}条）</text>
        <view v-for="(row, idx) in closeoutFilteredExportSchemeRows" :key="`${row.scheme.name}_${row.scheme.savedAt}_${row.index}`" class="app-row">
          <text class="app-subtext">{{ getSchemeDisplayText(row.scheme) }}</text>
          <button size="mini" :disabled="!canOperateScheme(idx)" @click="safeApplyCloseoutExportScheme(idx)">应用</button>
          <button size="mini" :disabled="!canOperateScheme(idx)" @click="safeApplyCloseoutExportSchemeAndCopyHeader(idx)">应用并复制表头</button>
          <button size="mini" :disabled="!canOperateScheme(idx)" @click="safeApplyCloseoutExportSchemeAndCopyConfig(idx)">应用并复制配置</button>
          <button size="mini" :disabled="!canOperateScheme(idx)" @click="safeTogglePinCloseoutExportScheme(idx)">{{ row.scheme.pinned ? "取消置顶" : "置顶" }}</button>
          <button size="mini" :disabled="!canOperateScheme(idx)" @click="safeRenameCloseoutExportScheme(idx)">重命名</button>
          <button size="mini" :disabled="!canOperateScheme(idx)" @click="safeCopySingleCloseoutExportSchemeJson(idx)">复制JSON</button>
          <button size="mini" :disabled="!canOperateScheme(idx)" @click="safeRemoveCloseoutExportScheme(idx)">删除</button>
        </view>
        <text v-if="canShowSchemeNoMatch()" class="app-subtext">当前筛选下无匹配方案</text>
      </view>
      <view v-if="closeoutExportTemplate === 'custom'" class="app-row">
        <input
          v-model="closeoutExportCustomFieldsText"
          @blur="saveCloseoutFilterPrefs"
          placeholder="自定义字段，逗号分隔（event_id,received_at,policy_env,reason_code,closeout_reason_code,run_id）"
        />
        <button size="mini" @click="fillCloseoutCustomFieldsRecommended">填充推荐</button>
        <button size="mini" @click="clearCloseoutCustomFields">清空字段</button>
        <button size="mini" @click="normalizeCloseoutCustomFieldsInput">规范化</button>
        <button size="mini" @click="removeInvalidCloseoutCustomFields">移除无效</button>
        <button size="mini" @click="removeDuplicateCloseoutCustomFields">移除重复</button>
        <button size="mini" @click="sortCloseoutCustomFieldsByRecommendedOrder">推荐排序</button>
        <button size="mini" @click="reverseCloseoutCustomFieldsOrder">反转顺序</button>
      </view>
      <view v-if="closeoutExportTemplate === 'custom'" class="app-row">
        <button size="mini" @click="applyCloseoutFieldPreset('handover')">交接预设</button>
        <button size="mini" @click="applyCloseoutFieldPreset('troubleshoot')">排障预设</button>
        <button size="mini" @click="applyCloseoutFieldPreset('audit')">审计预设</button>
      </view>
      <view v-if="closeoutExportTemplate === 'custom'" class="app-row">
        <button
          v-for="field in closeoutExportFieldOptions"
          :key="`field-${field}`"
          size="mini"
          :type="closeoutResolvedExportFields.includes(field) ? 'primary' : 'default'"
          @click="toggleCloseoutCustomField(field)"
        >
          {{ field }}
        </button>
      </view>
      <view v-if="closeoutExportTemplate === 'custom' && closeoutResolvedExportFields.length" class="app-gap-12">
        <text class="app-subtext">字段顺序微调：</text>
        <view v-for="(field, idx) in closeoutResolvedExportFields" :key="`order-${field}-${idx}`" class="app-row">
          <text class="app-subtext">{{ idx + 1 }}. {{ field }}</text>
          <button size="mini" @click="moveCloseoutCustomField(field, 'left')">左移</button>
          <button size="mini" @click="moveCloseoutCustomField(field, 'right')">右移</button>
        </view>
      </view>
      <text v-if="closeoutExportTemplate === 'custom'" class="app-subtext">
        自定义解析：有效={{ closeoutCustomFieldParseResult.valid.join(",") || "-" }}；无效={{ closeoutCustomFieldParseResult.invalid.join(",") || "-" }}；重复={{ closeoutCustomFieldParseResult.duplicate.join(",") || "-" }}
      </text>
      <text class="app-subtext">当前导出字段数：{{ closeoutExportFieldCount }}</text>
      <text v-if="closeoutCustomExportWarning" class="app-subtext">{{ closeoutCustomExportWarning }}</text>
      <text class="app-subtext">当前导出字段：{{ closeoutResolvedExportFields.join(",") }}</text>
      <view v-if="closeoutReasonTopRows.length" class="app-row">
        <text class="app-subtext">报警原因Top：</text>
        <button
          v-for="item in closeoutReasonTopRows"
          :key="`reason-${item.key}`"
          size="mini"
          :type="closeoutReasonCode === item.key ? 'primary' : 'default'"
          @click="applyCloseoutReasonQuick(item.key)"
        >
          {{ item.key }}({{ item.count }})
        </button>
      </view>
      <view v-if="closeoutReasonOutTopRows.length" class="app-row">
        <text class="app-subtext">收口原因Top：</text>
        <button
          v-for="item in closeoutReasonOutTopRows"
          :key="`closeout-${item.key}`"
          size="mini"
          :type="closeoutReasonCodeOut === item.key ? 'primary' : 'default'"
          @click="applyCloseoutReasonOutQuick(item.key)"
        >
          {{ item.key }}({{ item.count }})
        </button>
      </view>
      <view class="app-row">
        <button size="mini" :type="closeoutIncludeDashboard ? 'primary' : 'default'" @click="toggleCloseoutIncludeDashboard">
          {{ closeoutIncludeDashboard ? "完整看板：开" : "完整看板：关" }}
        </button>
        <button size="mini" :type="closeoutSelectedDay === '' ? 'primary' : 'default'" @click="setCloseoutSelectedDay('')">全部日期</button>
      </view>
      <view v-if="closeoutTrendDays.length" class="app-row">
        <button
          v-for="day in closeoutTrendDays"
          :key="day"
          size="mini"
          :type="closeoutSelectedDay === day ? 'primary' : 'default'"
          @click="setCloseoutSelectedDay(day)"
        >
          {{ day }}
        </button>
      </view>
      <view class="app-row">
        <button size="mini" @click="copyCloseoutDashboardSummary">复制Closeout摘要</button>
        <button size="mini" @click="copyCloseoutFilterSnapshot">复制Closeout快照</button>
        <button size="mini" @click="exportCloseoutRowsCsv">复制当前CSV</button>
        <button size="mini" @click="saveCloseoutFilterSnapshot">保存快照</button>
        <button size="mini" @click="restoreLatestCloseoutFilterSnapshot">还原最近快照</button>
        <button size="mini" @click="exportCloseoutFilterSnapshotHistoryJson">导出快照JSON</button>
        <button size="mini" @click="importCloseoutFilterSnapshotHistoryFromClipboard">导入快照JSON</button>
        <button size="mini" @click="clearCloseoutFilterSnapshotHistory">清空快照历史</button>
        <button size="mini" @click="resetCloseoutFilters">重置筛选</button>
      </view>
      <view v-if="closeoutFilterSnapshotHistory.length" class="app-gap-12">
        <text class="app-subtext">快照历史（最近{{ closeoutFilterSnapshotHistory.length }}条）</text>
        <view v-for="(item, idx) in closeoutFilterSnapshotHistory" :key="`${item.savedAt}_${idx}`" class="app-row">
          <text class="app-subtext">
            {{ item.savedAt }} / env={{ item.closeoutEnv || "-" }} / day={{ item.closeoutSelectedDay || "-" }} / reason={{ item.closeoutReasonCode || "-" }}
          </text>
          <button size="mini" @click="restoreCloseoutFilterSnapshotByIndex(idx)">还原</button>
        </view>
      </view>
      <text class="app-subtext">窗口总记录：{{ closeoutSummary?.total ?? 0 }}</text>
      <text class="app-subtext">最新环境：{{ closeoutSummary?.latest?.policy_env || "-" }}</text>
      <text class="app-subtext">明细进度：{{ closeoutRows.length }} / {{ closeoutTotal }} 条</text>
      <view v-if="closeoutRows.length" class="app-gap-12">
        <view v-for="row in closeoutRows" :key="row.event_id" class="app-row">
          <view style="flex:1">
            <text class="app-subtext">{{ row.received_at || "-" }}</text>
            <text class="app-subtext">环境：{{ row.policy_env || "-" }}；原因：{{ row.reason_code || "-" }}；收口：{{ row.closeout_reason_code || "-" }}</text>
          </view>
        </view>
        <view v-if="closeoutRows.length < closeoutTotal" class="app-row">
          <button size="mini" :loading="closeoutLoadingMore" @click="loadMoreCloseoutRows">加载更多明细</button>
        </view>
      </view>
    </view>
  </view>
</template>
