<script setup lang="ts">
import { onHide, onLoad, onShow, onUnload } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import {
  closeSession,
  createInstruction,
  createSession,
  joinSession,
  listInstructions,
  listParticipants,
  listSessions,
  type CommandInstruction,
  type CommandParticipant,
  type CommandSession
} from "@/api/command";
import { fetchAlarms, type AlarmItem } from "@/api/alarm";
import { fetchDeviceChannels } from "@/api/device";
import { fetchLatestPositions, fetchTrajectory, type DeviceLatestPosition, type TrajectoryPoint } from "@/api/map";
import { pickPreferredPlayUrl, playStream } from "@/api/stream";
import AppStatusTag from "@/components/AppStatusTag.vue";
import AppEmpty from "@/components/AppEmpty.vue";
import AppStreamPlayer from "@/components/AppStreamPlayer.vue";

const loading = ref(false);
const markers = ref<any[]>([]);
const polyline = ref<any[]>([]);
const mapCenter = ref({ lng: 116.397428, lat: 39.90923 });

const selectedDeviceId = ref("");
const selectedDeviceName = ref("");
const trajectoryPoints = ref<TrajectoryPoint[]>([]);

const linkedPlayUrl = ref("");
const linkedPlayMode = ref("raw");
const linkedPlayError = ref("");
const linkedLoading = ref(false);

const sessionId = ref("");
const sessionStatus = ref("idle");
const sessionTitle = ref("");
const recentOpenAlarms = ref<AlarmItem[]>([]);
const recentOpenAlarmsLoading = ref(false);
const alarmTimeWindow = ref<"" | "1h" | "24h" | "7d">("24h");
const instructionText = ref("");
const instructions = ref<CommandInstruction[]>([]);
const participants = ref<CommandParticipant[]>([]);
const recentSessions = ref<CommandSession[]>([]);
const actionLoading = ref(false);
const instructionPollingEnabled = ref(false);
let instructionTimer: ReturnType<typeof setInterval> | null = null;
const fromAlarmId = ref("");
const fromAlarmDesc = ref("");
const memberLastRefreshAt = ref("");
const instructionLastRefreshAt = ref("");
const instructionDeltaCount = ref(0);
const sessionActionStatusMessage = ref("未执行会话操作");
const sessionActionStatusAt = ref("");
const sessionHistoryStatusFilter = ref<"" | "open" | "closed">("open");
const sessionHistoryKeyword = ref("");
const sessionHistoryActiveWindow = ref<"" | "1h" | "24h" | "7d">("");
const sessionHistoryLimit = ref(50);
const sessionHistorySortMode = ref<"active" | "instruction_count" | "duration">("active");
const instructionKeyword = ref("");
const instructionSinceAt = ref("");
const memberRoleFilter = ref("");
const sessionLastRelaxAction = ref("");
const sessionLastRelaxAt = ref("");
const SESSION_RELAX_HISTORY_KEY = "command_session_relax_history_v1";
const SESSION_FILTER_STATE_KEY = "command_session_filter_state_v1";
const SESSION_FILTER_KEYWORDS_KEY = "command_session_filter_keywords_v1";
const SESSION_FILTER_VIEW_KEY = "command_session_filter_view_v1";
const SESSION_VIEW_PRESET_HISTORY_KEY = "command_session_view_preset_history_v1";
const SESSION_HANDOVER_COPY_KEY = "command_session_handover_copy_v1";
const SESSION_HANDOVER_SNAPSHOT_KEY = "command_session_handover_snapshot_v1";
const SESSION_HANDOVER_CONCLUSION_COPY_KEY = "command_session_handover_conclusion_copy_v1";
const SESSION_HANDOVER_PACKAGE_COPY_KEY = "command_session_handover_package_copy_v1";
const SESSION_HANDOVER_SHIFT_KEY = "command_session_handover_shift_v1";
const SESSION_RECENT_SESSIONS_CACHE_KEY = "command_recent_sessions_cache_v1";
const SESSION_RECENT_SESSIONS_CACHE_POLICY_KEY = "command_recent_sessions_cache_policy_v1";
const SESSION_RECENT_SESSIONS_CACHE_POLICY_AUDIT_KEY = "command_recent_sessions_cache_policy_audit_v1";
const DEFAULT_RECENT_SESSIONS_CACHE_TTL_MIN = 5;
const DEFAULT_RECENT_SESSIONS_CACHE_MAX_ROWS = 100;
const SESSION_RECENT_SESSIONS_CACHE_POLICY_AUDIT_MAX = 20;
const SESSION_RECENT_SESSIONS_CACHE_POLICY_RECENT_SHOW = 5;
const sessionRecentKeywords = ref<string[]>([]);
const sessionLastViewPreset = ref("");
const sessionLastViewPresetAt = ref("");
const sessionLastHandoverCopiedAt = ref("");
const sessionLastHandoverCopyMode = ref<"" | "text" | "json">("");
const sessionLastHandoverDigest = ref("");
const sessionLastHandoverSnapshot = ref<Record<string, any> | null>(null);
const sessionLastConclusionCopiedAt = ref("");
const sessionLastConclusionCopyMode = ref<"" | "text" | "json">("");
const sessionLastPackageCopiedAt = ref("");
const sessionLastPackageCopyMode = ref<"" | "text" | "json">("");
const sessionHandoverShiftLabel = ref("值班");
const sessionRecentCacheUpdatedAt = ref("");
const sessionRecentUsingCache = ref(false);
const sessionRecentCacheExpired = ref(false);
const sessionRecentFetchTotal = ref(0);
const sessionRecentServerHitCount = ref(0);
const sessionRecentCacheHitCount = ref(0);
const sessionRecentForceRefreshFailCount = ref(0);
const sessionRecentCacheTtlMin = ref(DEFAULT_RECENT_SESSIONS_CACHE_TTL_MIN);
const sessionRecentCacheMaxRows = ref(DEFAULT_RECENT_SESSIONS_CACHE_MAX_ROWS);
const sessionRecentCachePolicyChangedAt = ref("");
const sessionRecentCachePolicyChangedBy = ref("");
const sessionRecentCachePolicyAudit = ref<
  Array<{ changed_at: string; changed_by: string; ttl_min: number; max_rows: number; preset_label: string }>
>([]);
const sessionRecentCachePolicyPresets: Array<{
  key: "stable" | "balanced" | "compact";
  label: string;
  ttlMin: number;
  maxRows: number;
}> = [
  { key: "stable", label: "稳态", ttlMin: 30, maxRows: 200 },
  { key: "balanced", label: "平衡", ttlMin: 10, maxRows: 100 },
  { key: "compact", label: "省存", ttlMin: 5, maxRows: 50 }
];
const sessionFilterPresets: Array<{
  key: "duty" | "urgent" | "review" | "all";
  label: string;
  status: "" | "open" | "closed";
  activeWindow: "" | "1h" | "24h" | "7d";
  keyword: string;
}> = [
  { key: "duty", label: "值班", status: "open", activeWindow: "", keyword: "" },
  { key: "urgent", label: "紧急", status: "open", activeWindow: "1h", keyword: "" },
  { key: "review", label: "复盘", status: "closed", activeWindow: "7d", keyword: "" },
  { key: "all", label: "全部", status: "", activeWindow: "", keyword: "" }
];

function restoreSessionRelaxHistory() {
  try {
    const raw = uni.getStorageSync(SESSION_RELAX_HISTORY_KEY) as
      | { action?: string; at?: string }
      | undefined;
    sessionLastRelaxAction.value = String(raw?.action || "");
    sessionLastRelaxAt.value = String(raw?.at || "");
  } catch {
    sessionLastRelaxAction.value = "";
    sessionLastRelaxAt.value = "";
  }
}

function persistSessionRelaxHistory() {
  try {
    uni.setStorageSync(SESSION_RELAX_HISTORY_KEY, {
      action: sessionLastRelaxAction.value,
      at: sessionLastRelaxAt.value
    });
  } catch {
    // ignore storage failures in mobile runtime
  }
}

function restoreSessionFilterState() {
  try {
    const raw = uni.getStorageSync(SESSION_FILTER_STATE_KEY) as
      | { status?: string; activeWindow?: string; keyword?: string }
      | undefined;
    const status = String(raw?.status || "") as "" | "open" | "closed";
    const activeWindow = String(raw?.activeWindow || "") as "" | "1h" | "24h" | "7d";
    sessionHistoryStatusFilter.value = status === "open" || status === "closed" ? status : "";
    sessionHistoryActiveWindow.value =
      activeWindow === "1h" || activeWindow === "24h" || activeWindow === "7d" ? activeWindow : "";
    sessionHistoryKeyword.value = String(raw?.keyword || "");
  } catch {
    sessionHistoryStatusFilter.value = "open";
    sessionHistoryActiveWindow.value = "";
    sessionHistoryKeyword.value = "";
  }
}

function persistSessionFilterState() {
  try {
    uni.setStorageSync(SESSION_FILTER_STATE_KEY, {
      status: sessionHistoryStatusFilter.value,
      activeWindow: sessionHistoryActiveWindow.value,
      keyword: sessionHistoryKeyword.value.trim()
    });
  } catch {
    // ignore storage failures in mobile runtime
  }
}

function restoreSessionRecentKeywords() {
  try {
    const raw = uni.getStorageSync(SESSION_FILTER_KEYWORDS_KEY) as string[] | undefined;
    if (!Array.isArray(raw)) {
      sessionRecentKeywords.value = [];
      return;
    }
    sessionRecentKeywords.value = raw.map((x) => String(x || "").trim()).filter(Boolean).slice(0, 8);
  } catch {
    sessionRecentKeywords.value = [];
  }
}

function persistSessionRecentKeywords() {
  try {
    uni.setStorageSync(SESSION_FILTER_KEYWORDS_KEY, sessionRecentKeywords.value.slice(0, 8));
  } catch {
    // ignore storage failures in mobile runtime
  }
}

function restoreSessionFilterViewState() {
  try {
    const raw = uni.getStorageSync(SESSION_FILTER_VIEW_KEY) as
      | { limit?: number; sortMode?: string }
      | undefined;
    const limit = Number(raw?.limit || 50);
    sessionHistoryLimit.value = limit === 20 || limit === 50 || limit === 100 ? limit : 50;
    const mode = String(raw?.sortMode || "active");
    sessionHistorySortMode.value =
      mode === "instruction_count" || mode === "duration" || mode === "active" ? mode : "active";
  } catch {
    sessionHistoryLimit.value = 50;
    sessionHistorySortMode.value = "active";
  }
}

function persistSessionFilterViewState() {
  try {
    uni.setStorageSync(SESSION_FILTER_VIEW_KEY, {
      limit: sessionHistoryLimit.value,
      sortMode: sessionHistorySortMode.value
    });
  } catch {
    // ignore storage failures in mobile runtime
  }
}

function restoreSessionViewPresetHistory() {
  try {
    const raw = uni.getStorageSync(SESSION_VIEW_PRESET_HISTORY_KEY) as
      | { preset?: string; at?: string }
      | undefined;
    sessionLastViewPreset.value = String(raw?.preset || "");
    sessionLastViewPresetAt.value = String(raw?.at || "");
  } catch {
    sessionLastViewPreset.value = "";
    sessionLastViewPresetAt.value = "";
  }
}

function persistSessionViewPresetHistory() {
  try {
    uni.setStorageSync(SESSION_VIEW_PRESET_HISTORY_KEY, {
      preset: sessionLastViewPreset.value,
      at: sessionLastViewPresetAt.value
    });
  } catch {
    // ignore storage failures in mobile runtime
  }
}

function restoreSessionHandoverCopyState() {
  try {
    const raw = uni.getStorageSync(SESSION_HANDOVER_COPY_KEY) as
      | { copied_at?: string; copy_mode?: string }
      | undefined;
    sessionLastHandoverCopiedAt.value = String(raw?.copied_at || "");
    const mode = String(raw?.copy_mode || "");
    sessionLastHandoverCopyMode.value = mode === "text" || mode === "json" ? mode : "";
  } catch {
    sessionLastHandoverCopiedAt.value = "";
    sessionLastHandoverCopyMode.value = "";
  }
}

function persistSessionHandoverCopyState() {
  try {
    uni.setStorageSync(SESSION_HANDOVER_COPY_KEY, {
      copied_at: sessionLastHandoverCopiedAt.value,
      copy_mode: sessionLastHandoverCopyMode.value
    });
  } catch {
    // ignore storage failures in mobile runtime
  }
}

function restoreSessionHandoverConclusionCopyState() {
  try {
    const raw = uni.getStorageSync(SESSION_HANDOVER_CONCLUSION_COPY_KEY) as
      | { copied_at?: string; copy_mode?: string }
      | undefined;
    sessionLastConclusionCopiedAt.value = String(raw?.copied_at || "");
    const mode = String(raw?.copy_mode || "");
    sessionLastConclusionCopyMode.value = mode === "text" || mode === "json" ? mode : "";
  } catch {
    sessionLastConclusionCopiedAt.value = "";
    sessionLastConclusionCopyMode.value = "";
  }
}

function persistSessionHandoverConclusionCopyState() {
  try {
    uni.setStorageSync(SESSION_HANDOVER_CONCLUSION_COPY_KEY, {
      copied_at: sessionLastConclusionCopiedAt.value,
      copy_mode: sessionLastConclusionCopyMode.value
    });
  } catch {
    // ignore storage failures in mobile runtime
  }
}

function restoreSessionHandoverPackageCopyState() {
  try {
    const raw = uni.getStorageSync(SESSION_HANDOVER_PACKAGE_COPY_KEY) as
      | { copied_at?: string; copy_mode?: string }
      | undefined;
    sessionLastPackageCopiedAt.value = String(raw?.copied_at || "");
    const mode = String(raw?.copy_mode || "");
    sessionLastPackageCopyMode.value = mode === "text" || mode === "json" ? mode : "";
  } catch {
    sessionLastPackageCopiedAt.value = "";
    sessionLastPackageCopyMode.value = "";
  }
}

function persistSessionHandoverPackageCopyState() {
  try {
    uni.setStorageSync(SESSION_HANDOVER_PACKAGE_COPY_KEY, {
      copied_at: sessionLastPackageCopiedAt.value,
      copy_mode: sessionLastPackageCopyMode.value
    });
  } catch {
    // ignore storage failures in mobile runtime
  }
}

function restoreSessionHandoverShiftLabel() {
  try {
    const raw = uni.getStorageSync(SESSION_HANDOVER_SHIFT_KEY);
    const v = String(raw || "").trim();
    sessionHandoverShiftLabel.value = v || "值班";
  } catch {
    sessionHandoverShiftLabel.value = "值班";
  }
}

function persistSessionHandoverShiftLabel() {
  try {
    uni.setStorageSync(SESSION_HANDOVER_SHIFT_KEY, sessionHandoverShiftLabel.value.trim() || "值班");
  } catch {
    // ignore storage failures in mobile runtime
  }
}

function restoreSessionHandoverSnapshot() {
  try {
    const raw = uni.getStorageSync(SESSION_HANDOVER_SNAPSHOT_KEY) as
      | { digest?: string; payload?: Record<string, any> }
      | undefined;
    sessionLastHandoverDigest.value = String(raw?.digest || "");
    sessionLastHandoverSnapshot.value = raw?.payload && typeof raw.payload === "object" ? raw.payload : null;
  } catch {
    sessionLastHandoverDigest.value = "";
    sessionLastHandoverSnapshot.value = null;
  }
}

function persistSessionHandoverSnapshot() {
  try {
    uni.setStorageSync(SESSION_HANDOVER_SNAPSHOT_KEY, {
      digest: sessionHandoverDigest.value,
      payload: sessionHandoverPayload.value
    });
    sessionLastHandoverDigest.value = sessionHandoverDigest.value;
    sessionLastHandoverSnapshot.value = sessionHandoverPayload.value;
  } catch {
    // ignore storage failures in mobile runtime
  }
}

function clearSessionHandoverSnapshot() {
  sessionLastHandoverDigest.value = "";
  sessionLastHandoverSnapshot.value = null;
  try {
    uni.removeStorageSync(SESSION_HANDOVER_SNAPSHOT_KEY);
  } catch {
    // ignore storage failures in mobile runtime
  }
}

function normalizeNum(v: unknown) {
  const n = Number(v);
  return Number.isFinite(n) ? n : NaN;
}

function normalizeRecentCachePolicy(ttlMin: number, maxRows: number) {
  const ttl = Number(ttlMin);
  const rows = Number(maxRows);
  return {
    ttlMin: ttl === 5 || ttl === 10 || ttl === 15 || ttl === 30 ? ttl : DEFAULT_RECENT_SESSIONS_CACHE_TTL_MIN,
    maxRows: rows === 50 || rows === 100 || rows === 200 ? rows : DEFAULT_RECENT_SESSIONS_CACHE_MAX_ROWS
  };
}

function restoreRecentSessionsCachePolicy() {
  try {
    const raw = uni.getStorageSync(SESSION_RECENT_SESSIONS_CACHE_POLICY_KEY) as
      | { ttl_min?: number; max_rows?: number; changed_at?: string; changed_by?: string }
      | undefined;
    const normalized = normalizeRecentCachePolicy(Number(raw?.ttl_min), Number(raw?.max_rows));
    sessionRecentCacheTtlMin.value = normalized.ttlMin;
    sessionRecentCacheMaxRows.value = normalized.maxRows;
    sessionRecentCachePolicyChangedAt.value = String(raw?.changed_at || "");
    sessionRecentCachePolicyChangedBy.value = String(raw?.changed_by || "");
    const auditRaw = uni.getStorageSync(SESSION_RECENT_SESSIONS_CACHE_POLICY_AUDIT_KEY) as
      | Array<{ changed_at?: string; changed_by?: string; ttl_min?: number; max_rows?: number; preset_label?: string }>
      | undefined;
    sessionRecentCachePolicyAudit.value = Array.isArray(auditRaw)
      ? auditRaw
          .map((x) => ({
            changed_at: String(x?.changed_at || ""),
            changed_by: String(x?.changed_by || ""),
            ttl_min: Number(x?.ttl_min || DEFAULT_RECENT_SESSIONS_CACHE_TTL_MIN),
            max_rows: Number(x?.max_rows || DEFAULT_RECENT_SESSIONS_CACHE_MAX_ROWS),
            preset_label: String(x?.preset_label || "自定义")
          }))
          .slice(0, SESSION_RECENT_SESSIONS_CACHE_POLICY_AUDIT_MAX)
      : [];
  } catch {
    sessionRecentCacheTtlMin.value = DEFAULT_RECENT_SESSIONS_CACHE_TTL_MIN;
    sessionRecentCacheMaxRows.value = DEFAULT_RECENT_SESSIONS_CACHE_MAX_ROWS;
    sessionRecentCachePolicyChangedAt.value = "";
    sessionRecentCachePolicyChangedBy.value = "";
    sessionRecentCachePolicyAudit.value = [];
  }
}

function persistRecentSessionsCachePolicy(changedBy: string) {
  try {
    const changedAt = new Date().toISOString();
    sessionRecentCachePolicyChangedAt.value = changedAt;
    sessionRecentCachePolicyChangedBy.value = changedBy;
    const presetLabel = sessionRecentCacheCurrentPresetLabel.value;
    uni.setStorageSync(SESSION_RECENT_SESSIONS_CACHE_POLICY_KEY, {
      ttl_min: sessionRecentCacheTtlMin.value,
      max_rows: sessionRecentCacheMaxRows.value,
      changed_at: changedAt,
      changed_by: changedBy
    });
    const nextAudit = [
      {
        changed_at: changedAt,
        changed_by: changedBy,
        ttl_min: sessionRecentCacheTtlMin.value,
        max_rows: sessionRecentCacheMaxRows.value,
        preset_label: presetLabel
      },
      ...sessionRecentCachePolicyAudit.value
    ].slice(0, SESSION_RECENT_SESSIONS_CACHE_POLICY_AUDIT_MAX);
    sessionRecentCachePolicyAudit.value = nextAudit;
    uni.setStorageSync(SESSION_RECENT_SESSIONS_CACHE_POLICY_AUDIT_KEY, nextAudit);
  } catch {
    // ignore storage failures in mobile runtime
  }
}

function isRecentSessionsCacheExpired(updatedAt: string) {
  const ts = String(updatedAt || "").trim();
  if (!ts) return true;
  const ms = new Date(ts).getTime();
  if (Number.isNaN(ms)) return true;
  return Date.now() - ms > sessionRecentCacheTtlMin.value * 60 * 1000;
}

function refreshRecentCacheExpiryState() {
  sessionRecentCacheExpired.value =
    !!sessionRecentCacheUpdatedAt.value && isRecentSessionsCacheExpired(sessionRecentCacheUpdatedAt.value);
}

function persistRecentSessionsCache(rows: CommandSession[]) {
  try {
    const nowIso = new Date().toISOString();
    const cappedRows = [...rows].slice(0, sessionRecentCacheMaxRows.value);
    uni.setStorageSync(SESSION_RECENT_SESSIONS_CACHE_KEY, {
      updated_at: nowIso,
      rows: cappedRows
    });
    sessionRecentCacheUpdatedAt.value = nowIso;
    sessionRecentCacheExpired.value = false;
  } catch {
    // ignore storage failures in mobile runtime
  }
}

function restoreRecentSessionsCache() {
  try {
    const raw = uni.getStorageSync(SESSION_RECENT_SESSIONS_CACHE_KEY) as
      | { updated_at?: string; rows?: CommandSession[] }
      | undefined;
    const rows = Array.isArray(raw?.rows) ? raw?.rows || [] : [];
    const updatedAt = String(raw?.updated_at || "");
    return { rows, updatedAt };
  } catch {
    return { rows: [] as CommandSession[], updatedAt: "" };
  }
}

function clearRecentSessionsCache() {
  try {
    uni.removeStorageSync(SESSION_RECENT_SESSIONS_CACHE_KEY);
  } catch {
    // ignore storage failures in mobile runtime
  }
  sessionRecentCacheUpdatedAt.value = "";
  sessionRecentUsingCache.value = false;
  sessionRecentCacheExpired.value = false;
  uni.showToast({ title: "已清理会话缓存", icon: "none" });
}

function buildMarkers(items: DeviceLatestPosition[]) {
  // 性能兜底：地图最多渲染 120 个点位
  return items
    .filter((x) => Number.isFinite(normalizeNum(x.longitude)) && Number.isFinite(normalizeNum(x.latitude)))
    .slice(0, 120)
    .map((x, idx) => ({
      id: idx + 1,
      longitude: Number(x.longitude),
      latitude: Number(x.latitude),
      title: x.name || x.gb_id,
      width: 22,
      height: 22,
      alpha: 0.95,
      callout: {
        content: x.name || x.gb_id,
        fontSize: 11,
        borderRadius: 6,
        padding: 4,
        display: "BYCLICK"
      },
      extra: {
        gb_id: x.gb_id,
        name: x.name || x.gb_id
      }
    }));
}

async function loadMapData() {
  loading.value = true;
  try {
    const list = await fetchLatestPositions(300);
    markers.value = buildMarkers(list || []);
    const first = markers.value[0];
    if (first) mapCenter.value = { lng: Number(first.longitude), lat: Number(first.latitude) };
  } finally {
    loading.value = false;
  }
}

async function loadRecentSessions(options?: { force?: boolean }) {
  sessionRecentFetchTotal.value += 1;
  try {
    const rows =
      (await listSessions(sessionHistoryStatusFilter.value, sessionHistoryLimit.value, sessionHistoryKeyword.value)) || [];
    recentSessions.value = [...rows].sort((a, b) => {
      if (sessionHistorySortMode.value === "active" && !sessionHistoryStatusFilter.value) {
        const aOpen = String(a.status || "").toLowerCase() === "open";
        const bOpen = String(b.status || "").toLowerCase() === "open";
        if (aOpen !== bOpen) return aOpen ? -1 : 1;
      }
      if (sessionHistorySortMode.value === "instruction_count") {
        const ac = Number(a.instruction_count || 0);
        const bc = Number(b.instruction_count || 0);
        if (ac !== bc) return bc - ac;
      }
      if (sessionHistorySortMode.value === "duration") {
        const ad = Number(a.duration_sec || 0);
        const bd = Number(b.duration_sec || 0);
        if (ad !== bd) return bd - ad;
      }
      const aKey = String(a.last_instruction_at || a.started_at || "");
      const bKey = String(b.last_instruction_at || b.started_at || "");
      return bKey.localeCompare(aKey);
    });
    persistRecentSessionsCache(recentSessions.value);
    sessionRecentUsingCache.value = false;
    sessionRecentCacheExpired.value = false;
    sessionRecentServerHitCount.value += 1;
  } catch {
    if (options?.force) {
      sessionRecentUsingCache.value = false;
      sessionRecentCacheExpired.value = false;
      sessionRecentForceRefreshFailCount.value += 1;
      uni.showToast({ title: "强制刷新失败，请稍后重试", icon: "none" });
      return;
    }
    const cache = restoreRecentSessionsCache();
    recentSessions.value = cache.rows;
    sessionRecentCacheUpdatedAt.value = cache.updatedAt;
    sessionRecentUsingCache.value = cache.rows.length > 0;
    sessionRecentCacheExpired.value = cache.rows.length > 0 && isRecentSessionsCacheExpired(cache.updatedAt);
    if (cache.rows.length > 0) {
      sessionRecentCacheHitCount.value += 1;
    }
  }
}

async function forceRefreshRecentSessions() {
  await loadRecentSessions({ force: true });
}

function onRecentCacheTtlPolicyChange(index: number) {
  const options = [5, 10, 15, 30];
  const value = options[index] || DEFAULT_RECENT_SESSIONS_CACHE_TTL_MIN;
  sessionRecentCacheTtlMin.value = value;
  persistRecentSessionsCachePolicy("manual_ttl");
  refreshRecentCacheExpiryState();
}

function onRecentCacheMaxRowsPolicyChange(index: number) {
  const options = [50, 100, 200];
  const value = options[index] || DEFAULT_RECENT_SESSIONS_CACHE_MAX_ROWS;
  sessionRecentCacheMaxRows.value = value;
  persistRecentSessionsCachePolicy("manual_capacity");
}

function resetRecentSessionsCachePolicy() {
  sessionRecentCacheTtlMin.value = DEFAULT_RECENT_SESSIONS_CACHE_TTL_MIN;
  sessionRecentCacheMaxRows.value = DEFAULT_RECENT_SESSIONS_CACHE_MAX_ROWS;
  persistRecentSessionsCachePolicy("reset_default");
  refreshRecentCacheExpiryState();
  uni.showToast({ title: "已恢复默认缓存策略", icon: "none" });
}

function applyRecentSessionsCachePolicyPreset(presetKey: "stable" | "balanced" | "compact") {
  const preset = sessionRecentCachePolicyPresets.find((x) => x.key === presetKey);
  if (!preset) return;
  sessionRecentCacheTtlMin.value = preset.ttlMin;
  sessionRecentCacheMaxRows.value = preset.maxRows;
  persistRecentSessionsCachePolicy(`preset_${preset.key}`);
  refreshRecentCacheExpiryState();
  uni.showToast({ title: `已切换缓存预设：${preset.label}`, icon: "none" });
}

function formatRecentCachePolicyChangeSource(source: string) {
  if (!source) return "未记录";
  if (source === "manual_ttl") return "手动调整TTL";
  if (source === "manual_capacity") return "手动调整容量";
  if (source === "reset_default") return "恢复默认策略";
  if (source.startsWith("preset_")) {
    const key = source.replace("preset_", "");
    const preset = sessionRecentCachePolicyPresets.find((x) => x.key === key);
    return `预设切换(${preset?.label || key})`;
  }
  return source;
}

const sessionRecentCacheCurrentPresetLabel = computed(() => {
  const matched = sessionRecentCachePolicyPresets.find(
    (x) => x.ttlMin === sessionRecentCacheTtlMin.value && x.maxRows === sessionRecentCacheMaxRows.value
  );
  return matched ? matched.label : "自定义";
});

const sessionRecentCacheHitRateText = computed(() => {
  const total = sessionRecentFetchTotal.value;
  if (total <= 0) return "缓存命中率：0/0 (0%)";
  const hit = sessionRecentCacheHitCount.value;
  const pct = Math.round((hit / total) * 100);
  return `缓存命中率：${hit}/${total} (${pct}%)`;
});

const sessionRecentCachePolicyText = computed(() => {
  return `缓存策略：TTL=${sessionRecentCacheTtlMin.value} 分钟；容量上限=${sessionRecentCacheMaxRows.value} 条；预设=${sessionRecentCacheCurrentPresetLabel.value}`;
});

const sessionRecentCachePolicyChangeSourceText = computed(() => {
  const source = String(sessionRecentCachePolicyChangedBy.value || "");
  return formatRecentCachePolicyChangeSource(source);
});

const sessionRecentCachePolicyChangeText = computed(() => {
  const changedAt = sessionRecentCachePolicyChangedAt.value
    ? formatSessionTime(sessionRecentCachePolicyChangedAt.value)
    : "-";
  return `策略变更：${sessionRecentCachePolicyChangeSourceText.value} @ ${changedAt}`;
});

const sessionRecentCachePolicyLastSnapshotText = computed(() => {
  const last = sessionRecentCachePolicyAudit.value[0];
  if (!last) return "策略快照：暂无";
  return `策略快照：TTL=${last.ttl_min} 分钟 / 容量=${last.max_rows} 条 / 预设=${last.preset_label} @ ${formatSessionTime(last.changed_at)}`;
});

const sessionRecentCachePolicyRecentItemsText = computed(() => {
  if (!sessionRecentCachePolicyAudit.value.length) return "最近策略变更：暂无";
  const rows = sessionRecentCachePolicyAudit.value
    .slice(0, SESSION_RECENT_SESSIONS_CACHE_POLICY_RECENT_SHOW)
    .map((x, idx) => {
      const at = x.changed_at ? formatSessionTime(x.changed_at) : "-";
      const source = formatRecentCachePolicyChangeSource(String(x.changed_by || ""));
      return `${idx + 1}) ${source} @ ${at}`;
    });
  return `最近策略变更(${SESSION_RECENT_SESSIONS_CACHE_POLICY_RECENT_SHOW}条)：${rows.join("；")}`;
});

const sessionRecentCachePolicySourceStatsText = computed(() => {
  if (!sessionRecentCachePolicyAudit.value.length) return "来源统计：暂无";
  const counter = new Map<string, number>();
  for (const row of sessionRecentCachePolicyAudit.value) {
    const key = formatRecentCachePolicyChangeSource(String(row.changed_by || ""));
    counter.set(key, (counter.get(key) || 0) + 1);
  }
  const text = [...counter.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([k, v]) => `${k}=${v}`)
    .join("；");
  return `来源统计：${text}`;
});

const sessionRecentCachePolicySourceTop1Text = computed(() => {
  if (!sessionRecentCachePolicyAudit.value.length) return "来源Top1：暂无";
  const counter = new Map<string, number>();
  for (const row of sessionRecentCachePolicyAudit.value) {
    const key = formatRecentCachePolicyChangeSource(String(row.changed_by || ""));
    counter.set(key, (counter.get(key) || 0) + 1);
  }
  const top = [...counter.entries()].sort((a, b) => b[1] - a[1])[0];
  if (!top) return "来源Top1：暂无";
  return `来源Top1：${top[0]}（${top[1]} 次）`;
});

const sessionRecentCacheMissCount = computed(() => {
  const total = sessionRecentFetchTotal.value;
  const sum = sessionRecentServerHitCount.value + sessionRecentCacheHitCount.value + sessionRecentForceRefreshFailCount.value;
  return Math.max(0, total - sum);
});

const sessionRecentCacheCountersText = computed(() => {
  return `请求统计：总=${sessionRecentFetchTotal.value}；服务端=${sessionRecentServerHitCount.value}；缓存=${sessionRecentCacheHitCount.value}；强制失败=${sessionRecentForceRefreshFailCount.value}；未命中=${sessionRecentCacheMissCount.value}`;
});

const sessionRecentCacheSelfCheckText = computed(() => {
  const total = sessionRecentFetchTotal.value;
  if (total <= 0) return "一致性自检：暂无数据";
  const server = sessionRecentServerHitCount.value;
  const cache = sessionRecentCacheHitCount.value;
  const fail = sessionRecentForceRefreshFailCount.value;
  const miss = sessionRecentCacheMissCount.value;
  const sum = server + cache + fail + miss;
  const ok = sum === total;
  const hint = sessionRecentUsingCache.value && sessionRecentCacheExpired.value ? "当前使用缓存且已过期" : "状态正常";
  return ok ? `一致性自检：通过（sum=${sum} 等于 total=${total}，${hint}）` : `一致性自检：异常（sum=${sum} 不等于 total=${total}）`;
});

function resetRecentCacheStats() {
  sessionRecentFetchTotal.value = 0;
  sessionRecentServerHitCount.value = 0;
  sessionRecentCacheHitCount.value = 0;
  sessionRecentForceRefreshFailCount.value = 0;
  uni.showToast({ title: "已重置命中统计", icon: "none" });
}

function copyRecentCacheStatsJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    totals: {
      fetch_total: sessionRecentFetchTotal.value,
      server_hit: sessionRecentServerHitCount.value,
      cache_hit: sessionRecentCacheHitCount.value,
      force_refresh_fail: sessionRecentForceRefreshFailCount.value,
      miss: sessionRecentCacheMissCount.value
    },
    hit_rate_text: sessionRecentCacheHitRateText.value,
    source: sessionRecentUsingCache.value ? "cache" : "server",
    cache_expired: sessionRecentCacheExpired.value,
    ttl_min: sessionRecentCacheTtlMin.value,
    max_rows: sessionRecentCacheMaxRows.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => uni.showToast({ title: "命中统计JSON已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyRecentCacheStatsText() {
  const text = [
    "缓存命中统计",
    sessionRecentCacheHitRateText.value,
    sessionRecentCacheCountersText.value,
    sessionRecentCacheSelfCheckText.value
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "命中统计已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyRecentCachePolicySummary() {
  const updatedAt = sessionRecentCacheUpdatedAt.value
    ? formatSessionTime(sessionRecentCacheUpdatedAt.value)
    : "-";
  const source = sessionRecentUsingCache.value ? "本地缓存兜底" : "服务端实时";
  const status = sessionRecentCacheExpired.value ? "已过期" : "有效";
  const text = [
    "会话缓存摘要",
    sessionRecentCachePolicyText.value,
    `当前来源：${source}`,
    `缓存状态：${status}`,
    `缓存更新时间：${updatedAt}`,
    sessionRecentCacheHitRateText.value,
    `服务端命中：${sessionRecentServerHitCount.value}`,
    `缓存命中：${sessionRecentCacheHitCount.value}`,
    `强制刷新失败：${sessionRecentForceRefreshFailCount.value}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "缓存摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyRecentCachePresetSummary() {
  const text = `缓存预设摘要：当前预设=${sessionRecentCacheCurrentPresetLabel.value}；TTL=${sessionRecentCacheTtlMin.value} 分钟；容量=${sessionRecentCacheMaxRows.value} 条`;
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "缓存预设摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyRecentCachePolicyChangeSummary() {
  const text = [
    "缓存策略变更记录",
    sessionRecentCachePolicyText.value,
    sessionRecentCachePolicyChangeText.value
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "策略变更记录已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyRecentCachePolicyAuditJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_policy: {
      ttl_min: sessionRecentCacheTtlMin.value,
      max_rows: sessionRecentCacheMaxRows.value,
      preset_label: sessionRecentCacheCurrentPresetLabel.value
    },
    change_source_text: sessionRecentCachePolicyChangeSourceText.value,
    changed_at: sessionRecentCachePolicyChangedAt.value || "",
    changed_by: sessionRecentCachePolicyChangedBy.value || "",
    audit_history: sessionRecentCachePolicyAudit.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => uni.showToast({ title: "策略审计JSON已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyRecentCachePolicyAuditCsv() {
  const header = "changed_at,changed_by,ttl_min,max_rows,preset_label";
  const rows = sessionRecentCachePolicyAudit.value.map((x) => {
    const at = String(x.changed_at || "").replace(/"/g, '""');
    const by = String(x.changed_by || "").replace(/"/g, '""');
    const ttl = Number(x.ttl_min || 0);
    const cap = Number(x.max_rows || 0);
    const preset = String(x.preset_label || "").replace(/"/g, '""');
    return `"${at}","${by}",${ttl},${cap},"${preset}"`;
  });
  const csv = [header, ...rows].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => uni.showToast({ title: "策略审计CSV已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyRecentCachePolicyLastSnapshot() {
  uni.setClipboardData({
    data: sessionRecentCachePolicyLastSnapshotText.value,
    success: () => uni.showToast({ title: "策略快照已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyRecentCachePolicySourceTop1() {
  const text = [
    "缓存策略来源Top1",
    sessionRecentCachePolicyText.value,
    sessionRecentCachePolicySourceTop1Text.value,
    sessionRecentCachePolicySourceStatsText.value
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "来源Top1已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyRecentCachePolicyRecentItems() {
  const text = [
    "最近策略变更明细",
    sessionRecentCachePolicyText.value,
    sessionRecentCachePolicyRecentItemsText.value
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "最近策略变更已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyRecentCachePolicySourceStats() {
  const text = [
    "缓存策略来源统计",
    sessionRecentCachePolicyText.value,
    sessionRecentCachePolicySourceStatsText.value,
    sessionRecentCachePolicySourceTop1Text.value
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "来源统计已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyRecentCachePolicyOverview() {
  const text = [
    "缓存策略审计总览",
    sessionRecentCachePolicyText.value,
    sessionRecentCachePolicyChangeText.value,
    sessionRecentCachePolicyRecentItemsText.value,
    sessionRecentCachePolicySourceStatsText.value,
    sessionRecentCachePolicySourceTop1Text.value
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "策略总览已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function clearRecentCachePolicyAudit() {
  uni.showModal({
    title: "确认清理",
    content: "将清空本地策略审计记录，是否继续？",
    confirmText: "清理",
    cancelText: "取消",
    success: (res) => {
      if (!res.confirm) return;
      sessionRecentCachePolicyAudit.value = [];
      try {
        uni.removeStorageSync(SESSION_RECENT_SESSIONS_CACHE_POLICY_AUDIT_KEY);
      } catch {
        // ignore storage failures in mobile runtime
      }
      uni.showToast({ title: "已清理策略审计", icon: "none" });
    }
  });
}

async function resetSessionHistoryFilters() {
  sessionHistoryStatusFilter.value = "open";
  sessionHistoryActiveWindow.value = "";
  sessionHistoryKeyword.value = "";
  try {
    uni.removeStorageSync(SESSION_FILTER_STATE_KEY);
  } catch {
    // ignore storage failures in mobile runtime
  }
  await loadRecentSessions();
}

async function applySessionFilterPreset(presetKey: "duty" | "urgent" | "review" | "all") {
  const preset = sessionFilterPresets.find((x) => x.key === presetKey);
  if (!preset) return;
  sessionHistoryStatusFilter.value = preset.status;
  sessionHistoryActiveWindow.value = preset.activeWindow;
  sessionHistoryKeyword.value = preset.keyword;
  persistSessionFilterState();
  await loadRecentSessions();
  uni.showToast({ title: `已切换预设：${preset.label}`, icon: "none" });
}

function copySessionFilterSummary() {
  const text = `会话筛选摘要：${sessionFilterSummary.value}；命中率：${sessionFilterHitRateText.value}；${sessionFilterModeText.value}`;
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "筛选摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

async function applySessionViewPreset(preset: "fast" | "balanced" | "dense") {
  if (preset === "fast") {
    sessionHistoryLimit.value = 20;
    sessionHistorySortMode.value = "active";
  } else if (preset === "dense") {
    sessionHistoryLimit.value = 100;
    sessionHistorySortMode.value = "instruction_count";
  } else {
    sessionHistoryLimit.value = 50;
    sessionHistorySortMode.value = "active";
  }
  persistSessionFilterViewState();
  sessionLastViewPreset.value = preset === "fast" ? "快速" : preset === "dense" ? "高密度" : "平衡";
  sessionLastViewPresetAt.value = new Date().toISOString();
  persistSessionViewPresetHistory();
  await loadRecentSessions();
  uni.showToast({
    title: preset === "fast" ? "已切换快速视图" : preset === "dense" ? "已切换高密度视图" : "已切换平衡视图",
    icon: "none"
  });
}

async function resetSessionViewConfig() {
  sessionHistoryLimit.value = 50;
  sessionHistorySortMode.value = "active";
  try {
    uni.removeStorageSync(SESSION_FILTER_VIEW_KEY);
  } catch {
    // ignore storage failures in mobile runtime
  }
  await loadRecentSessions();
  uni.showToast({ title: "已重置视图配置", icon: "none" });
}

function copySessionViewSummary() {
  const text = `会话视图：排序=${sessionHistorySortMode.value}; 条数=${sessionHistoryLimit.value}; 预设=${sessionCurrentPresetLabel.value}; 筛选=${sessionFilterSummary.value}`;
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "视图摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

const sessionExecutionHealthSummaryText = computed(() => {
  const status = sessionStatus.value || "idle";
  const memberCount = participants.value.length;
  const instructionCount = instructions.value.length;
  const deltaCount = instructionDeltaCount.value;
  const polling = instructionPollingEnabled.value ? "开启" : "关闭";
  const lastInstructionAt = instructionLastRefreshAt.value ? formatSessionTime(instructionLastRefreshAt.value) : "-";
  return `会话执行健康：状态=${status}；成员=${memberCount}；指令总数=${instructionCount}；本轮新增=${deltaCount}；轮询=${polling}；最近指令刷新=${lastInstructionAt}`;
});

const sessionExecutionHealthNextStepAdvice = computed(() => {
  if (!sessionId.value) return "下一步建议：先创建或加入会话，再进行会商执行监控。";
  if (sessionStatus.value === "closed") return "下一步建议：当前会话已结束，建议创建新会话延续处置。";
  if (participants.value.length <= 1) return "下一步建议：补充参会成员，避免单人会商导致信息遗漏。";
  if (instructionDeltaCount.value <= 0) return "下一步建议：尝试刷新或发布指令，确认会话仍在持续推进。";
  return "下一步建议：保持当前会商节奏，持续观察新增指令与成员反馈。";
});

const sessionRoleCoverageSummaryText = computed(() => {
  const roleSet = new Set(
    participants.value
      .map((x) => String((x as any).role || "").trim().toLowerCase())
      .filter((x) => !!x)
      .map((x) => (x === "owner" || x === "coordinator" || x === "observer" ? x : "participant"))
  );
  const required: Array<"owner" | "coordinator" | "participant"> = ["owner", "coordinator", "participant"];
  const missing = required.filter((x) => !roleSet.has(x));
  return `参会角色覆盖：成员=${participants.value.length}；已覆盖=${Array.from(roleSet).join("/") || "-"}；缺口=${missing.join("/") || "无"}`;
});

const sessionRoleCoverageAdvice = computed(() => {
  if (!sessionId.value) return "下一步建议：先创建或加入会话，再校验角色覆盖。";
  if (participants.value.length <= 0) return "下一步建议：先邀请成员入会，避免空会话。";
  if (sessionRoleCoverageSummaryText.value.includes("缺口=无")) return "下一步建议：角色覆盖完整，保持当前协同分工。";
  if (sessionRoleCoverageSummaryText.value.includes("owner")) return "下一步建议：优先补充 Owner，明确会商责任人。";
  if (sessionRoleCoverageSummaryText.value.includes("coordinator")) return "下一步建议：补充协调员，保障跨组协同推进。";
  return "下一步建议：补充 participant 角色，提升一线执行覆盖。";
});

const sessionInstructionActivitySummaryText = computed(() => {
  const total = instructions.value.length;
  const filtered = filteredInstructions.value.length;
  const delta = instructionDeltaCount.value;
  const refreshAt = instructionLastRefreshAt.value ? formatSessionTime(instructionLastRefreshAt.value) : "-";
  const intensity = delta >= 5 ? "高" : delta >= 1 ? "中" : "低";
  return `指令活跃摘要：总指令=${total}；当前视图=${filtered}；本轮新增=${delta}；活跃强度=${intensity}；最近刷新=${refreshAt}`;
});

const sessionInstructionActivityAdvice = computed(() => {
  if (!sessionId.value) return "下一步建议：先创建或加入会话，再观察指令活跃度。";
  if (instructionDeltaCount.value <= 0) return "下一步建议：尝试发布一条确认指令并刷新记录。";
  if (instructionDeltaCount.value >= 5) return "下一步建议：指令活跃较高，建议同步分工并跟踪执行反馈。";
  return "下一步建议：保持当前指令节奏，持续观察新增与回执。";
});

const sessionRefreshTimelinessSummaryText = computed(() => {
  const nowMs = Date.now();
  const memberMs = memberLastRefreshAt.value ? new Date(memberLastRefreshAt.value).getTime() : NaN;
  const instructionMs = instructionLastRefreshAt.value ? new Date(instructionLastRefreshAt.value).getTime() : NaN;
  const memberLagSec = Number.isNaN(memberMs) ? -1 : Math.max(0, Math.round((nowMs - memberMs) / 1000));
  const instructionLagSec = Number.isNaN(instructionMs) ? -1 : Math.max(0, Math.round((nowMs - instructionMs) / 1000));
  const stale =
    (memberLagSec >= 0 && memberLagSec > 120) || (instructionLagSec >= 0 && instructionLagSec > 120) ? "是" : "否";
  return `会话刷新时效：成员刷新滞后=${memberLagSec >= 0 ? `${memberLagSec}s` : "-"}；指令刷新滞后=${instructionLagSec >= 0 ? `${instructionLagSec}s` : "-"}；本轮新增=${instructionDeltaCount.value}；刷新异常=${stale}`;
});

const sessionRefreshTimelinessAdvice = computed(() => {
  if (!sessionId.value) return "下一步建议：先创建或加入会话，再建立刷新基线。";
  if (sessionRefreshTimelinessSummaryText.value.includes("刷新异常=是")) {
    return "下一步建议：优先手动刷新会话数据并检查网络连通性。";
  }
  if (instructionDeltaCount.value <= 0) return "下一步建议：可发布心跳指令验证刷新链路持续有效。";
  return "下一步建议：刷新时效正常，保持当前会商节奏。";
});

const sessionInstructionKeywordHitSummaryText = computed(() => {
  const keyword = String(instructionKeyword.value || "").trim();
  const total = instructions.value.length;
  const matched = filteredInstructions.value.length;
  const rate = total <= 0 ? 0 : Number(((matched / total) * 100).toFixed(2));
  return `指令关键词命中：关键词=${keyword || "全部"}；命中=${matched}/${total}；命中率=${rate}%`;
});

const sessionInstructionKeywordHitAdvice = computed(() => {
  if (!sessionId.value) return "下一步建议：先创建或加入会话，再进行关键词命中分析。";
  const keyword = String(instructionKeyword.value || "").trim();
  const total = instructions.value.length;
  const matched = filteredInstructions.value.length;
  if (!keyword) return "下一步建议：当前未设置关键词，可输入关键词进行定向筛查。";
  if (total > 0 && matched <= 0) return "下一步建议：关键词未命中，建议放宽关键词或清空筛选。";
  if (total > 0 && matched < total / 5) return "下一步建议：命中偏低，建议改用更宽泛关键词复核指令轨迹。";
  return "下一步建议：命中结果可用，继续结合新增指令推进会商处置。";
});

const sessionMemberRefreshCoverageSummaryText = computed(() => {
  const role = memberRoleFilter.value || "全部";
  const memberCount = participants.value.length;
  const refreshAt = memberLastRefreshAt.value ? formatSessionTime(memberLastRefreshAt.value) : "-";
  const lagSec = memberLastRefreshAt.value
    ? Math.max(0, Math.round((Date.now() - new Date(memberLastRefreshAt.value).getTime()) / 1000))
    : -1;
  const stale = lagSec >= 0 && lagSec > 120 ? "是" : "否";
  return `成员刷新覆盖：筛选角色=${role}；成员数=${memberCount}；最近刷新=${refreshAt}；刷新滞后=${lagSec >= 0 ? `${lagSec}s` : "-"}；覆盖异常=${stale}`;
});

const sessionMemberRefreshCoverageAdvice = computed(() => {
  if (!sessionId.value) return "下一步建议：先创建或加入会话，再建立成员刷新覆盖基线。";
  if (sessionMemberRefreshCoverageSummaryText.value.includes("覆盖异常=是")) {
    return "下一步建议：优先手动刷新成员列表并检查会话连通性。";
  }
  if (participants.value.length <= 0) return "下一步建议：先邀请成员入会，确保会商覆盖。";
  return "下一步建议：成员刷新覆盖正常，保持当前协同节奏。";
});

function copySessionExecutionHealthSummary() {
  const text = [sessionExecutionHealthSummaryText.value, sessionExecutionHealthNextStepAdvice.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "执行健康摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copySessionRoleCoverageSummary() {
  const text = [sessionRoleCoverageSummaryText.value, sessionRoleCoverageAdvice.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "角色覆盖摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copySessionInstructionActivitySummary() {
  const text = [sessionInstructionActivitySummaryText.value, sessionInstructionActivityAdvice.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "指令活跃摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copySessionRefreshTimelinessSummary() {
  const text = [sessionRefreshTimelinessSummaryText.value, sessionRefreshTimelinessAdvice.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "刷新时效摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copySessionInstructionKeywordHitSummary() {
  const text = [sessionInstructionKeywordHitSummaryText.value, sessionInstructionKeywordHitAdvice.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "关键词命中摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copySessionMemberRefreshCoverageSummary() {
  const text = [sessionMemberRefreshCoverageSummaryText.value, sessionMemberRefreshCoverageAdvice.value].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "成员覆盖摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function buildHandoverDigest(input: string) {
  const text = String(input || "");
  let hash = 5381;
  for (let i = 0; i < text.length; i += 1) {
    hash = (hash * 33) ^ text.charCodeAt(i);
  }
  return `hs-${(hash >>> 0).toString(16).padStart(8, "0")}`;
}

const sessionHandoverDigest = computed(() => {
  const base = [
    sessionFilterSummary.value,
    sessionFilterHitRateText.value,
    sessionViewSummaryText.value,
    sessionCurrentPresetLabel.value,
    sessionLastViewPreset.value || "",
    sessionLastViewPresetAt.value || "",
    sessionLastRelaxAction.value || "",
    sessionLastRelaxAt.value || ""
  ].join("|");
  return buildHandoverDigest(base);
});

const sessionHandoverSummaryText = computed(() => {
  const relaxAction = sessionLastRelaxAction.value || "无";
  const relaxAt = formatSessionTime(sessionLastRelaxAt.value);
  const viewPreset = sessionLastViewPreset.value || "无";
  const viewPresetAt = formatSessionTime(sessionLastViewPresetAt.value);
  const handoverTime = formatSessionTime(new Date().toISOString());
  return [
    `会话交接摘要`,
    `生成时间：${handoverTime}`,
    `筛选：${sessionFilterSummary.value}`,
    `命中率：${sessionFilterHitRateText.value}`,
    `视图：${sessionViewSummaryText.value}`,
    `当前筛选预设：${sessionCurrentPresetLabel.value}`,
    `上次视图预设：${viewPreset} @ ${viewPresetAt}`,
    `上次放宽：${relaxAction} @ ${relaxAt}`,
    `摘要指纹：${sessionHandoverDigest.value}`
  ].join("；");
});

const sessionHandoverPayload = computed(() => ({
  schema_version: "v2",
  generated_at: new Date().toISOString(),
  filter_summary: sessionFilterSummary.value,
  hit_rate: sessionFilterHitRateText.value,
  view_summary: sessionViewSummaryText.value,
  filter_preset: sessionCurrentPresetLabel.value,
  last_view_preset: sessionLastViewPreset.value || "",
  last_view_preset_at: sessionLastViewPresetAt.value || "",
  last_relax_action: sessionLastRelaxAction.value || "",
  last_relax_at: sessionLastRelaxAt.value || "",
  handover_digest: sessionHandoverDigest.value
}));

const sessionHandoverDiffItems = computed(() => {
  const prev = sessionLastHandoverSnapshot.value || {};
  const curr = sessionHandoverPayload.value;
  const fields: Array<{ key: string; label: string }> = [
    { key: "filter_summary", label: "筛选摘要" },
    { key: "hit_rate", label: "命中率" },
    { key: "view_summary", label: "视图摘要" },
    { key: "filter_preset", label: "筛选预设" },
    { key: "last_view_preset", label: "上次视图预设" },
    { key: "last_relax_action", label: "上次放宽动作" }
  ];
  const changed: string[] = [];
  for (const field of fields) {
    const before = String(prev[field.key] || "");
    const after = String((curr as any)[field.key] || "");
    if (before !== after) changed.push(field.label);
  }
  return changed;
});

const sessionHandoverDiffDetails = computed(() => {
  const prev = sessionLastHandoverSnapshot.value || {};
  const curr = sessionHandoverPayload.value;
  const fields: Array<{ key: string; label: string }> = [
    { key: "filter_summary", label: "筛选摘要" },
    { key: "hit_rate", label: "命中率" },
    { key: "view_summary", label: "视图摘要" },
    { key: "filter_preset", label: "筛选预设" },
    { key: "last_view_preset", label: "上次视图预设" },
    { key: "last_relax_action", label: "上次放宽动作" }
  ];
  return fields
    .map((field) => {
      const before = String(prev[field.key] || "");
      const after = String((curr as any)[field.key] || "");
      return {
        key: field.key,
        label: field.label,
        before,
        after,
        changed: before !== after
      };
    })
    .filter((x) => x.changed);
});

const sessionHandoverDiffText = computed(() => {
  if (!sessionLastHandoverDigest.value || !sessionLastHandoverSnapshot.value) return "与上次交接差异：暂无基线";
  if (!sessionHandoverDiffItems.value.length) return "与上次交接差异：无变化";
  return `与上次交接差异：${sessionHandoverDiffItems.value.join("、")}`;
});

const sessionHandoverBaselineAtText = computed(() => {
  const ts = String(sessionLastHandoverSnapshot.value?.generated_at || "").trim();
  if (!ts) return "交接基线时间：-";
  return `交接基线时间：${formatSessionTime(ts)}`;
});

const sessionHandoverDiffCountText = computed(() => {
  if (!sessionLastHandoverDigest.value || !sessionLastHandoverSnapshot.value) return "差异字段数：-";
  return `差异字段数：${sessionHandoverDiffDetails.value.length}`;
});

const sessionHandoverDiffLevel = computed(() => {
  const count = sessionHandoverDiffDetails.value.length;
  if (!sessionLastHandoverDigest.value || !sessionLastHandoverSnapshot.value) {
    return { code: "none", label: "基线未建立" };
  }
  if (count <= 0) return { code: "low", label: "低变更" };
  if (count <= 2) return { code: "medium", label: "中变更" };
  return { code: "high", label: "高变更" };
});

const sessionHandoverConclusionText = computed(() => {
  const now = formatSessionTime(new Date().toISOString());
  const baseline = String(sessionLastHandoverSnapshot.value?.generated_at || "").trim();
  const baselineText = baseline ? formatSessionTime(baseline) : "-";
  const diffFields = sessionHandoverDiffItems.value.length ? sessionHandoverDiffItems.value.join("、") : "无";
  return [
    `会话交接结论`,
    `生成时间：${now}`,
    `基线时间：${baselineText}`,
    `变更等级：${sessionHandoverDiffLevel.value.label}`,
    `差异字段数：${sessionHandoverDiffDetails.value.length}`,
    `差异字段：${diffFields}`,
    `当前指纹：${sessionHandoverDigest.value}`,
    `上次指纹：${sessionLastHandoverDigest.value || "-"}`
  ].join("；");
});

const sessionHandoverConclusionPayload = computed(() => ({
  schema_version: "v1",
  generated_at: new Date().toISOString(),
  baseline_generated_at: String(sessionLastHandoverSnapshot.value?.generated_at || ""),
  diff_level: sessionHandoverDiffLevel.value.label,
  diff_count: sessionHandoverDiffDetails.value.length,
  diff_fields: sessionHandoverDiffDetails.value.map((item) => ({
    key: item.key,
    label: item.label,
    before: item.before,
    after: item.after
  })),
  current_digest: sessionHandoverDigest.value,
  previous_digest: sessionLastHandoverDigest.value || "",
  filter_summary: sessionFilterSummary.value,
  view_summary: sessionViewSummaryText.value,
  hit_rate: sessionFilterHitRateText.value,
  conclusion_text: sessionHandoverConclusionText.value
}));

function buildSessionHandoverDiffPayload() {
  return {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    baseline_generated_at: String(sessionLastHandoverSnapshot.value?.generated_at || ""),
    current_digest: sessionHandoverDigest.value,
    previous_digest: sessionLastHandoverDigest.value || "",
    has_baseline: !!sessionLastHandoverDigest.value && !!sessionLastHandoverSnapshot.value,
    diff_count: sessionHandoverDiffDetails.value.length,
    diff_fields: sessionHandoverDiffDetails.value.map((item) => ({
      key: item.key,
      label: item.label,
      before: item.before,
      after: item.after
    }))
  };
}

function buildCopyAuditItem(label: string, at: string, mode: "" | "text" | "json") {
  const timeText = at ? formatSessionTime(at) : "-";
  const modeText = mode ? (mode === "json" ? "JSON" : "文本") : "-";
  return `${label}=${timeText}/${modeText}`;
}

function normalizeFilenamePart(input: string) {
  return String(input || "")
    .trim()
    .replace(/[\\/:*?"<>|\s]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}

const sessionHandoverSuggestedFileName = computed(() => {
  const dt = new Date();
  const yyyy = dt.getFullYear();
  const mm = String(dt.getMonth() + 1).padStart(2, "0");
  const dd = String(dt.getDate()).padStart(2, "0");
  const hh = String(dt.getHours()).padStart(2, "0");
  const mi = String(dt.getMinutes()).padStart(2, "0");
  const ss = String(dt.getSeconds()).padStart(2, "0");
  const shift = normalizeFilenamePart(sessionHandoverShiftLabel.value || "值班");
  const digest = normalizeFilenamePart(sessionHandoverDigest.value || "no-digest");
  return `command-handover-${shift}-${yyyy}${mm}${dd}-${hh}${mi}${ss}-${digest}.json`;
});

const sessionCopyAuditSummaryText = computed(() => {
  return [
    "复制审计",
    buildCopyAuditItem("交接摘要", sessionLastHandoverCopiedAt.value, sessionLastHandoverCopyMode.value),
    buildCopyAuditItem("交接结论", sessionLastConclusionCopiedAt.value, sessionLastConclusionCopyMode.value),
    buildCopyAuditItem("交接组合包", sessionLastPackageCopiedAt.value, sessionLastPackageCopyMode.value)
  ].join("；");
});

const sessionHandoverRequiredChecks = computed(() => {
  const checks: Array<{ label: string; ok: boolean; hint: string }> = [
    {
      label: "班次标签",
      ok: !!sessionHandoverShiftLabel.value.trim(),
      hint: "请先设置班次标签"
    },
    {
      label: "交接基线",
      ok: !!sessionLastHandoverDigest.value && !!sessionLastHandoverSnapshot.value,
      hint: "请先复制交接摘要或手动设为当前基线"
    },
    {
      label: "交接结论",
      ok: !!sessionLastConclusionCopiedAt.value,
      hint: "请先复制交接结论（文本或JSON）"
    }
  ];
  return checks;
});

const sessionHandoverReady = computed(() => sessionHandoverRequiredChecks.value.every((x) => x.ok));

const sessionHandoverReadyText = computed(() => {
  if (sessionHandoverReady.value) return "交接校验：已就绪";
  const missing = sessionHandoverRequiredChecks.value.filter((x) => !x.ok).map((x) => x.label);
  return `交接校验：缺少 ${missing.join("、")}`;
});

const sessionHandoverReadyHintText = computed(() => {
  if (sessionHandoverReady.value) return "交接提示：可直接复制组合包进行分发";
  const next = sessionHandoverRequiredChecks.value.find((x) => !x.ok);
  return `交接提示：${next?.hint || "请补齐必要字段"}`;
});

const sessionHandoverBundleText = computed(() => {
  return [
    "【会话交接组合包】",
    `生成时间：${formatSessionTime(new Date().toISOString())}`,
    `班次标签：${sessionHandoverShiftLabel.value || "值班"}`,
    `建议文件名：${sessionHandoverSuggestedFileName.value}`,
    "",
    `1) 交接摘要：${sessionHandoverSummaryText.value}`,
    "",
    `2) 交接差异：${sessionHandoverDiffText.value}`,
    "",
    `3) 交接结论：${sessionHandoverConclusionText.value}`,
    "",
    `4) 审计信息：${sessionCopyAuditSummaryText.value}`
  ].join("\n");
});

const sessionHandoverBundlePayload = computed(() => ({
  schema_version: "v1",
  generated_at: new Date().toISOString(),
  shift_label: sessionHandoverShiftLabel.value || "值班",
  suggested_filename: sessionHandoverSuggestedFileName.value,
  handover_digest: sessionHandoverDigest.value,
  summary: {
    text: sessionHandoverSummaryText.value,
    payload: sessionHandoverPayload.value
  },
  diff: {
    text: sessionHandoverDiffText.value,
    payload: buildSessionHandoverDiffPayload()
  },
  conclusion: {
    text: sessionHandoverConclusionText.value,
    payload: sessionHandoverConclusionPayload.value
  },
  copy_audit: sessionCopyAuditSummaryText.value
}));

const sessionCopyAuditPayload = computed(() => ({
  schema_version: "v1",
  generated_at: new Date().toISOString(),
  shift_label: sessionHandoverShiftLabel.value || "值班",
  handover_digest: sessionHandoverDigest.value,
  suggested_filename: sessionHandoverSuggestedFileName.value,
  records: [
    {
      type: "handover_summary",
      copied_at: sessionLastHandoverCopiedAt.value || "",
      copy_mode: sessionLastHandoverCopyMode.value || ""
    },
    {
      type: "handover_conclusion",
      copied_at: sessionLastConclusionCopiedAt.value || "",
      copy_mode: sessionLastConclusionCopyMode.value || ""
    },
    {
      type: "handover_bundle",
      copied_at: sessionLastPackageCopiedAt.value || "",
      copy_mode: sessionLastPackageCopyMode.value || ""
    }
  ],
  summary_text: sessionCopyAuditSummaryText.value
}));

function copySessionHandoverSummary() {
  const text = sessionHandoverSummaryText.value;
  uni.setClipboardData({
    data: text,
    success: () => {
      sessionLastHandoverCopiedAt.value = new Date().toISOString();
      sessionLastHandoverCopyMode.value = "text";
      persistSessionHandoverCopyState();
      persistSessionHandoverSnapshot();
      uni.showToast({ title: "交接摘要已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copySessionHandoverSummaryJson() {
  const jsonText = JSON.stringify(sessionHandoverPayload.value, null, 2);
  uni.setClipboardData({
    data: jsonText,
    success: () => {
      sessionLastHandoverCopiedAt.value = new Date().toISOString();
      sessionLastHandoverCopyMode.value = "json";
      persistSessionHandoverCopyState();
      persistSessionHandoverSnapshot();
      uni.showToast({ title: "交接JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copySessionHandoverDiffSummary() {
  const text = `会话交接差异摘要：${sessionHandoverDiffText.value}；当前指纹：${sessionHandoverDigest.value}；上次指纹：${sessionLastHandoverDigest.value || "-"}`;
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "交接差异已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copySessionHandoverDiffSummaryJson() {
  uni.setClipboardData({
    data: JSON.stringify(buildSessionHandoverDiffPayload(), null, 2),
    success: () => uni.showToast({ title: "交接差异JSON已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function resetSessionHandoverBaseline() {
  clearSessionHandoverSnapshot();
  uni.showToast({ title: "已重置交接基线", icon: "none" });
}

function markSessionHandoverBaseline() {
  persistSessionHandoverSnapshot();
  uni.showToast({ title: "已设为当前交接基线", icon: "none" });
}

function copySessionHandoverConclusion() {
  uni.setClipboardData({
    data: sessionHandoverConclusionText.value,
    success: () => {
      sessionLastConclusionCopiedAt.value = new Date().toISOString();
      sessionLastConclusionCopyMode.value = "text";
      persistSessionHandoverConclusionCopyState();
      uni.showToast({ title: "交接结论已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copySessionHandoverConclusionJson() {
  uni.setClipboardData({
    data: JSON.stringify(sessionHandoverConclusionPayload.value, null, 2),
    success: () => {
      sessionLastConclusionCopiedAt.value = new Date().toISOString();
      sessionLastConclusionCopyMode.value = "json";
      persistSessionHandoverConclusionCopyState();
      uni.showToast({ title: "交接结论JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copySessionHandoverBundle() {
  uni.setClipboardData({
    data: sessionHandoverBundleText.value,
    success: () => {
      sessionLastPackageCopiedAt.value = new Date().toISOString();
      sessionLastPackageCopyMode.value = "text";
      persistSessionHandoverPackageCopyState();
      uni.showToast({ title: "交接组合包已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copySessionHandoverBundleJson() {
  uni.setClipboardData({
    data: JSON.stringify(sessionHandoverBundlePayload.value, null, 2),
    success: () => {
      sessionLastPackageCopiedAt.value = new Date().toISOString();
      sessionLastPackageCopyMode.value = "json";
      persistSessionHandoverPackageCopyState();
      uni.showToast({ title: "交接组合包JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copySessionCopyAuditSummary() {
  uni.setClipboardData({
    data: sessionCopyAuditSummaryText.value,
    success: () => uni.showToast({ title: "复制审计摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copySessionCopyAuditJson() {
  uni.setClipboardData({
    data: JSON.stringify(sessionCopyAuditPayload.value, null, 2),
    success: () => uni.showToast({ title: "审计JSON已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function applySessionShiftPreset(value: "值班" | "夜班" | "复盘") {
  sessionHandoverShiftLabel.value = value;
  persistSessionHandoverShiftLabel();
  uni.showToast({ title: `已切换班次：${value}`, icon: "none" });
}

function onSessionShiftLabelBlur() {
  sessionHandoverShiftLabel.value = sessionHandoverShiftLabel.value.trim() || "值班";
  persistSessionHandoverShiftLabel();
}

async function resetSessionHandoverStandardConfig() {
  sessionHistoryStatusFilter.value = "open";
  sessionHistoryActiveWindow.value = "";
  sessionHistoryKeyword.value = "";
  sessionHistorySortMode.value = "active";
  sessionHistoryLimit.value = 50;
  sessionHandoverShiftLabel.value = "值班";
  sessionLastRelaxAction.value = "";
  sessionLastRelaxAt.value = "";
  clearSessionHandoverSnapshot();
  persistSessionFilterState();
  persistSessionFilterViewState();
  persistSessionHandoverShiftLabel();
  try {
    uni.removeStorageSync(SESSION_RELAX_HISTORY_KEY);
  } catch {
    // ignore storage failures in mobile runtime
  }
  await loadRecentSessions();
  uni.showToast({ title: "已恢复标准交接配置", icon: "none" });
}

function upsertSessionKeywordHistory(keyword: string) {
  const v = String(keyword || "").trim();
  if (!v) return;
  const merged = [v, ...sessionRecentKeywords.value.filter((x) => x !== v)];
  sessionRecentKeywords.value = merged.slice(0, 8);
  persistSessionRecentKeywords();
}

async function applyRecentKeyword(keyword: string) {
  sessionHistoryKeyword.value = String(keyword || "").trim();
  persistSessionFilterState();
  await loadRecentSessions();
}

function clearRecentKeywords() {
  sessionRecentKeywords.value = [];
  try {
    uni.removeStorageSync(SESSION_FILTER_KEYWORDS_KEY);
  } catch {
    // ignore storage failures in mobile runtime
  }
  uni.showToast({ title: "已清空关键词历史", icon: "none" });
}

async function onSessionSortModeChange(index: number) {
  sessionHistorySortMode.value = index === 1 ? "instruction_count" : index === 2 ? "duration" : "active";
  persistSessionFilterViewState();
  await loadRecentSessions();
}

async function onSessionLimitChange(index: number) {
  sessionHistoryLimit.value = index === 1 ? 50 : index === 2 ? 100 : 20;
  persistSessionFilterViewState();
  await loadRecentSessions();
}

async function onSessionStatusFilterChange(index: number) {
  sessionHistoryStatusFilter.value = index === 1 ? "open" : index === 2 ? "closed" : "";
  persistSessionFilterState();
  await loadRecentSessions();
}

function onSessionActiveWindowChange(index: number) {
  sessionHistoryActiveWindow.value = index === 1 ? "1h" : index === 2 ? "24h" : index === 3 ? "7d" : "";
  persistSessionFilterState();
}

async function onSessionKeywordQuery() {
  upsertSessionKeywordHistory(sessionHistoryKeyword.value);
  persistSessionFilterState();
  await loadRecentSessions();
}

const sessionCurrentPresetLabel = computed(() => {
  const status = sessionHistoryStatusFilter.value;
  const activeWindow = sessionHistoryActiveWindow.value;
  const keyword = sessionHistoryKeyword.value.trim();
  const matched = sessionFilterPresets.find(
    (x) => x.status === status && x.activeWindow === activeWindow && x.keyword.trim() === keyword
  );
  return matched ? matched.label : "自定义";
});

const sessionViewSummaryText = computed(() => {
  const sortLabel =
    sessionHistorySortMode.value === "active"
      ? "最近活跃"
      : sessionHistorySortMode.value === "instruction_count"
        ? "指令数"
        : "会话时长";
  return `视图配置：${sortLabel} / ${sessionHistoryLimit.value} 条`;
});

const filteredRecentSessions = computed(() => {
  const now = Date.now();
  const maxAgeMs =
    sessionHistoryActiveWindow.value === "1h"
      ? 60 * 60 * 1000
      : sessionHistoryActiveWindow.value === "24h"
        ? 24 * 60 * 60 * 1000
        : sessionHistoryActiveWindow.value === "7d"
          ? 7 * 24 * 60 * 60 * 1000
          : 0;
  if (!maxAgeMs) return recentSessions.value;
  return recentSessions.value.filter((s) => {
    const ts = String(s.last_instruction_at || s.started_at || "").trim();
    if (!ts) return false;
    const ms = new Date(ts).getTime();
    if (Number.isNaN(ms)) return false;
    return now - ms <= maxAgeMs;
  });
});

const sessionFilterSummary = computed(() => {
  const parts: string[] = [];
  if (sessionHistoryStatusFilter.value) {
    parts.push(sessionHistoryStatusFilter.value === "open" ? "状态=进行中" : "状态=已结束");
  } else {
    parts.push("状态=全部");
  }
  if (sessionHistoryActiveWindow.value) {
    parts.push(
      sessionHistoryActiveWindow.value === "1h"
        ? "活跃=1小时内"
        : sessionHistoryActiveWindow.value === "24h"
          ? "活跃=24小时内"
          : "活跃=7天内"
    );
  } else {
    parts.push("活跃=全部");
  }
  if (sessionHistoryKeyword.value.trim()) {
    parts.push(`关键词=${sessionHistoryKeyword.value.trim()}`);
  }
  return parts.join(" | ");
});

const sessionFilterHitRateText = computed(() => {
  const total = recentSessions.value.length;
  const matched = filteredRecentSessions.value.length;
  if (total <= 0) return "0/0 (0%)";
  const pct = Math.round((matched / total) * 100);
  return `${matched}/${total} (${pct}%)`;
});

const sessionFilterModeText = computed(() => {
  const hasKeyword = !!sessionHistoryKeyword.value.trim();
  const hasStatus = sessionHistoryStatusFilter.value !== "open";
  const hasWindow = !!sessionHistoryActiveWindow.value;
  const enabled = hasKeyword || hasStatus || hasWindow;
  return enabled ? "筛选状态：已启用" : "筛选状态：默认视图";
});

const sessionFilterHintText = computed(() => {
  const total = recentSessions.value.length;
  if (total <= 0) return "筛选强度：暂无数据";
  const matched = filteredRecentSessions.value.length;
  const pct = Math.round((matched / total) * 100);
  if (pct <= 10) return "筛选强度：过严（建议放宽条件）";
  if (pct <= 35) return "筛选强度：偏严（可按需放宽）";
  return "筛选强度：正常";
});

const sessionFilterEnabledCountText = computed(() => {
  let count = 0;
  if (sessionHistoryStatusFilter.value !== "open") count += 1;
  if (sessionHistoryActiveWindow.value) count += 1;
  if (sessionHistoryKeyword.value.trim()) count += 1;
  return `已启用筛选：${count} 项`;
});

const sessionFilterNeedsRelax = computed(() => {
  const total = recentSessions.value.length;
  if (total <= 0) return false;
  const matched = filteredRecentSessions.value.length;
  const pct = Math.round((matched / total) * 100);
  return pct <= 35;
});

const sessionNextRelaxStepText = computed(() => {
  if (sessionHistoryKeyword.value.trim()) return "下一步：清空关键词";
  if (sessionHistoryActiveWindow.value) return "下一步：清空活跃时间";
  if (sessionHistoryStatusFilter.value !== "open") return "下一步：恢复进行中状态";
  return "下一步：无需放宽";
});

const sessionRelaxQueueText = computed(() => {
  const queue: string[] = [];
  if (sessionHistoryKeyword.value.trim()) queue.push("关键词");
  if (sessionHistoryActiveWindow.value) queue.push("活跃时间");
  if (sessionHistoryStatusFilter.value !== "open") queue.push("状态");
  return queue.length ? `可放宽项：${queue.join(" -> ")}` : "可放宽项：无";
});

const sessionRelaxRemainingStepsText = computed(() => {
  let count = 0;
  if (sessionHistoryKeyword.value.trim()) count += 1;
  if (sessionHistoryActiveWindow.value) count += 1;
  if (sessionHistoryStatusFilter.value !== "open") count += 1;
  return `剩余放宽步数：${count}`;
});

async function relaxSessionFilters() {
  let hint = "当前筛选已是默认";
  if (sessionHistoryKeyword.value.trim()) {
    sessionHistoryKeyword.value = "";
    hint = "已放宽：清空关键词";
  } else if (sessionHistoryActiveWindow.value) {
    sessionHistoryActiveWindow.value = "";
    hint = "已放宽：清空活跃时间";
  } else if (sessionHistoryStatusFilter.value !== "open") {
    sessionHistoryStatusFilter.value = "open";
    hint = "已放宽：状态恢复进行中";
  }
  sessionLastRelaxAction.value = hint;
  sessionLastRelaxAt.value = new Date().toISOString();
  persistSessionFilterState();
  persistSessionRelaxHistory();
  await loadRecentSessions();
  uni.showToast({ title: hint, icon: "none" });
}

function clearSessionRelaxHistory() {
  sessionLastRelaxAction.value = "";
  sessionLastRelaxAt.value = "";
  try {
    uni.removeStorageSync(SESSION_RELAX_HISTORY_KEY);
  } catch {
    // ignore storage failures in mobile runtime
  }
  uni.showToast({ title: "已清空放宽记录", icon: "none" });
}

const filteredInstructions = computed(() => instructions.value);

function participantRoleLabel(role: string) {
  const key = String(role || "").toLowerCase();
  if (key === "owner") return "Owner";
  if (key === "coordinator") return "协调员";
  if (key === "observer") return "观察员";
  return key || "participant";
}

function participantRoleType(role: string): "success" | "warning" | "info" {
  const key = String(role || "").toLowerCase();
  if (key === "owner" || key === "coordinator") return "success";
  if (key === "observer") return "warning";
  return "info";
}

function formatSessionDuration(durationSec: number | undefined) {
  const total = Math.max(0, Number(durationSec || 0));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = Math.floor(total % 60);
  if (h > 0) return `${h}h ${m}m ${s}s`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function formatSessionTime(value: string | undefined) {
  const raw = String(value || "").trim();
  if (!raw) return "-";
  const dt = new Date(raw);
  if (Number.isNaN(dt.getTime())) return raw;
  const yyyy = dt.getFullYear();
  const mm = String(dt.getMonth() + 1).padStart(2, "0");
  const dd = String(dt.getDate()).padStart(2, "0");
  const hh = String(dt.getHours()).padStart(2, "0");
  const mi = String(dt.getMinutes()).padStart(2, "0");
  const ss = String(dt.getSeconds()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd} ${hh}:${mi}:${ss}`;
}

function setSessionActionStatus(message: string) {
  sessionActionStatusMessage.value = message;
  sessionActionStatusAt.value = new Date().toISOString();
}

async function loadLinkedVideo(deviceGbId: string) {
  linkedLoading.value = true;
  linkedPlayError.value = "";
  linkedPlayUrl.value = "";
  linkedPlayMode.value = "raw";
  try {
    const channels = await fetchDeviceChannels(deviceGbId, 20);
    const online = (channels || []).find((c) => Number(c.status || 0) === 1) || channels?.[0];
    if (!online?.gb_id) {
      linkedPlayError.value = "该设备暂无可用通道，无法联动视频";
      return;
    }
    const data = await playStream(deviceGbId, online.gb_id);
    const picked = pickPreferredPlayUrl(data);
    if (!picked.url) {
      linkedPlayError.value = "未拿到联动播放地址，请稍后重试";
      return;
    }
    linkedPlayUrl.value = picked.url;
    linkedPlayMode.value = picked.mode;
  } catch (e: any) {
    linkedPlayError.value = e?.message || "视频联动失败";
  } finally {
    linkedLoading.value = false;
  }
}

async function selectDevice(deviceId: string, name?: string) {
  selectedDeviceId.value = deviceId;
  selectedDeviceName.value = name || deviceId;
  const list = await fetchTrajectory(deviceId, 200);
  trajectoryPoints.value = list || [];
  polyline.value = [
    {
      points: trajectoryPoints.value.map((p) => ({ longitude: Number(p.lng), latitude: Number(p.lat) })),
      color: "#2563EB",
      width: 4,
      dottedLine: false
    }
  ];
  const first = trajectoryPoints.value[0];
  if (first) mapCenter.value = { lng: Number(first.lng), lat: Number(first.lat) };
  await loadLinkedVideo(deviceId);
}

function onMarkerTap(e: any) {
  const markerId = Number(e?.detail?.markerId);
  const marker = markers.value.find((m) => Number(m.id) === markerId);
  if (!marker) return;
  selectDevice(marker.extra?.gb_id || "", marker.extra?.name || "");
}

function buildDeviceContextInstruction() {
  if (!selectedDeviceId.value) return "";
  const lines = [
    `设备：${selectedDeviceName.value || selectedDeviceId.value}`,
    `设备编号：${selectedDeviceId.value}`,
    `轨迹点：${trajectoryPoints.value.length}`,
    `联动线路：${linkedPlayMode.value.toUpperCase()}`,
    `联动地址：${linkedPlayUrl.value || "未获取"}`
  ];
  return lines.join("\n");
}

function buildAlarmContextInstruction(alarm: AlarmItem) {
  return [
    "【告警上下文】",
    `告警ID：${alarm.id}`,
    `设备ID：${alarm.device_id || "-"}`,
    `通道ID：${alarm.channel_id || "-"}`,
    `告警级别：${alarm.priority ?? "-"}`,
    `告警描述：${alarm.description || "-"}`,
    `告警时间：${alarm.time || alarm.created_at || "-"}`
  ].join("\n");
}

async function loadRecentOpenAlarms() {
  recentOpenAlarmsLoading.value = true;
  try {
    const now = new Date();
    const start = new Date(now);
    if (alarmTimeWindow.value === "1h") start.setHours(start.getHours() - 1);
    else if (alarmTimeWindow.value === "24h") start.setDate(start.getDate() - 1);
    else if (alarmTimeWindow.value === "7d") start.setDate(start.getDate() - 7);
    const params: any = {
      skip: 0,
      limit: 20,
      escalation_state: "open"
    };
    if (alarmTimeWindow.value) {
      params.start_time = start.toISOString();
      params.end_time = now.toISOString();
    }
    const res = await fetchAlarms(params);
    recentOpenAlarms.value = (res.items || []).slice(0, 20);
  } catch (err: any) {
    recentOpenAlarms.value = [];
    uni.showToast({ title: err?.message ? `告警加载失败：${err.message}` : "告警加载失败", icon: "none" });
  } finally {
    recentOpenAlarmsLoading.value = false;
  }
}

async function createConference(withDeviceContext = false) {
  actionLoading.value = true;
  try {
    const title =
      sessionTitle.value.trim() ||
      (withDeviceContext && selectedDeviceName.value
        ? `移动会商-${selectedDeviceName.value}`
        : `移动会商-${Date.now()}`);
    const created = await createSession(fromAlarmId.value || undefined, title);
    sessionId.value = created.id;
    sessionStatus.value = "open";
    await joinSession(sessionId.value, "participant");
    if (withDeviceContext && selectedDeviceId.value) {
      const contextText = buildDeviceContextInstruction();
      if (contextText) {
        await createInstruction(sessionId.value, `【设备上下文】\n${contextText}`);
      }
    }
    if (fromAlarmId.value) {
      const alarmText = [
        "【告警上下文】",
        `告警ID：${fromAlarmId.value}`,
        `告警描述：${fromAlarmDesc.value || "-"}`
      ].join("\n");
      await createInstruction(sessionId.value, alarmText);
    }
    await refreshSessionData();
    await loadRecentSessions();
    startInstructionPolling();
    uni.showToast({ title: "会商已创建", icon: "success" });
  } finally {
    actionLoading.value = false;
  }
}

async function createConferenceByAlarm(alarm: AlarmItem) {
  if (!alarm?.id) {
    uni.showToast({ title: "告警信息不完整", icon: "none" });
    return;
  }
  actionLoading.value = true;
  try {
    fromAlarmId.value = String(alarm.id);
    fromAlarmDesc.value = String(alarm.description || "");
    if (alarm.device_id) {
      selectedDeviceId.value = String(alarm.device_id);
      selectedDeviceName.value = String(alarm.device_id);
      await loadLinkedVideo(selectedDeviceId.value);
    }
    const title = `告警会商-${alarm.id}`;
    const created = await createSession(fromAlarmId.value, title);
    sessionId.value = created.id;
    sessionStatus.value = "open";
    sessionTitle.value = title;
    await joinSession(sessionId.value, "participant");
    await createInstruction(sessionId.value, buildAlarmContextInstruction(alarm));
    if (selectedDeviceId.value) {
      const contextText = buildDeviceContextInstruction();
      if (contextText) await createInstruction(sessionId.value, `【设备上下文】\n${contextText}`);
    }
    await refreshSessionData(false);
    await loadRecentSessions();
    startInstructionPolling();
    setSessionActionStatus(`告警会商已创建：${alarm.id}`);
    uni.showToast({ title: "告警会商已创建", icon: "success" });
  } catch (err: any) {
    const reason = err?.message ? String(err.message) : "请稍后重试";
    setSessionActionStatus(`告警会商创建失败：${reason}`);
    uni.showToast({ title: "告警会商创建失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

function newestInstructionAt(list: CommandInstruction[]) {
  const sorted = [...list].sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
  return String(sorted[0]?.created_at || "");
}

async function refreshSessionData(incremental = false) {
  if (!sessionId.value) return;
  const prevTopId = instructions.value[0]?.id || "";
  const prevIdSet = new Set(instructions.value.map((x) => x.id));
  const sinceAt = incremental ? instructionSinceAt.value : "";
  try {
    const [inst, parts] = await Promise.all([
      listInstructions(sessionId.value, 80, instructionKeyword.value, sinceAt),
      listParticipants(sessionId.value, memberRoleFilter.value)
    ]);
    const incoming = (inst || []) as CommandInstruction[];
    if (incremental) {
      const merged = [...instructions.value, ...incoming];
      const map = new Map<string, CommandInstruction>();
      merged.forEach((x) => map.set(String(x.id), x));
      instructions.value = [...map.values()]
        .sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")))
        .slice(0, 40);
      instructionDeltaCount.value = incoming.filter((x) => !prevIdSet.has(String(x.id))).length;
    } else {
      instructions.value = [...incoming]
        .sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")))
        .slice(0, 40);
      const newTopId = instructions.value[0]?.id || "";
      if (prevTopId && newTopId && prevTopId !== newTopId) {
        const prevIndex = instructions.value.findIndex((x) => x.id === prevTopId);
        instructionDeltaCount.value = prevIndex > 0 ? prevIndex : 1;
      } else {
        instructionDeltaCount.value = 0;
      }
    }
    participants.value = parts || [];
    const nowIso = new Date().toISOString();
    memberLastRefreshAt.value = nowIso;
    instructionLastRefreshAt.value = nowIso;
    instructionSinceAt.value = newestInstructionAt(instructions.value) || instructionSinceAt.value;
    const modeText = incremental ? "增量刷新成功" : "刷新成功";
    const deltaText = instructionDeltaCount.value > 0 ? `，新增${instructionDeltaCount.value}条` : "";
    setSessionActionStatus(`${modeText}：成员${participants.value.length}人，指令${instructions.value.length}条${deltaText}`);
  } catch (err: any) {
    const reason = err?.message ? String(err.message) : "请稍后重试";
    setSessionActionStatus(incremental ? `增量刷新失败：${reason}` : `刷新失败：${reason}`);
    if (!incremental) {
      uni.showToast({ title: "会话刷新失败", icon: "none" });
    }
    throw err;
  }
}

function startInstructionPolling() {
  stopInstructionPolling();
  instructionTimer = setInterval(() => {
    refreshSessionData(true).catch(() => undefined);
  }, 5000);
  instructionPollingEnabled.value = true;
}

function stopInstructionPolling() {
  if (instructionTimer) {
    clearInterval(instructionTimer);
    instructionTimer = null;
  }
  instructionPollingEnabled.value = false;
}

async function createConferenceBySelectedDevice() {
  if (!selectedDeviceId.value) {
    uni.showToast({ title: "请先在地图中选择设备", icon: "none" });
    return;
  }
  await createConference(true);
}

async function sendInstruction() {
  const content = instructionText.value.trim();
  if (!sessionId.value || !content) {
    uni.showToast({ title: "请先创建会商并输入指令", icon: "none" });
    return;
  }
  actionLoading.value = true;
  try {
    await createInstruction(sessionId.value, content);
    instructionText.value = "";
    setSessionActionStatus("指令已发布，正在刷新会话数据...");
    try {
      await refreshSessionData(false);
      const preview = content.length > 18 ? `${content.slice(0, 18)}...` : content;
      setSessionActionStatus(`指令发布成功：${preview}`);
    } catch (err: any) {
      const reason = err?.message ? String(err.message) : "请稍后重试";
      setSessionActionStatus(`指令已发布，但刷新失败：${reason}`);
      uni.showToast({ title: "发布成功但刷新失败", icon: "none" });
    }
  } catch (err: any) {
    const reason = err?.message ? String(err.message) : "请稍后重试";
    setSessionActionStatus(`指令发布失败：${reason}`);
    uni.showToast({ title: "指令发布失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function endConference() {
  if (!sessionId.value) return;
  actionLoading.value = true;
  try {
    await closeSession(sessionId.value, "移动端结束会商");
    sessionStatus.value = "closed";
    stopInstructionPolling();
    await loadRecentSessions();
    uni.showToast({ title: "会商已结束", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function joinExistingSession(targetSessionId: string) {
  const sid = String(targetSessionId || "").trim();
  if (!sid) return;
  const session = recentSessions.value.find((x) => String(x.id) === sid);
  if (session?.status === "closed") {
    uni.showToast({ title: "该会话已结束，无法加入", icon: "none" });
    return;
  }
  actionLoading.value = true;
  try {
    await joinSession(sid, "participant");
    sessionId.value = sid;
    sessionStatus.value = "open";
    await refreshSessionData(false);
    startInstructionPolling();
    uni.showToast({ title: "已加入会商", icon: "success" });
  } finally {
    actionLoading.value = false;
  }
}

onShow(async () => {
  await Promise.all([loadMapData(), loadRecentSessions(), loadRecentOpenAlarms()]);
});
onLoad(async (query) => {
  restoreSessionRelaxHistory();
  restoreSessionFilterState();
  restoreSessionRecentKeywords();
  restoreSessionFilterViewState();
  restoreSessionViewPresetHistory();
  restoreRecentSessionsCachePolicy();
  restoreSessionHandoverCopyState();
  restoreSessionHandoverConclusionCopyState();
  restoreSessionHandoverPackageCopyState();
  restoreSessionHandoverShiftLabel();
  const recentCache = restoreRecentSessionsCache();
  sessionRecentCacheUpdatedAt.value = recentCache.updatedAt;
  refreshRecentCacheExpiryState();
  restoreSessionHandoverSnapshot();
  const deviceId = String(query?.deviceId || "").trim();
  const deviceName = String(query?.deviceName || "").trim();
  fromAlarmId.value = String(query?.alarmId || "").trim();
  fromAlarmDesc.value = String(query?.alarmDesc || "").trim();
  const autoCreate = String(query?.autoCreate || "") === "1";
  if (deviceId) {
    await selectDevice(deviceId, deviceName || deviceId);
  }
  if (autoCreate) {
    await createConference(true);
  }
});
onHide(stopInstructionPolling);
onUnload(stopInstructionPolling);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">移动指挥</view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text>设备态势地图</text>
        <button size="mini" :loading="loading" @click="loadMapData">刷新</button>
      </view>
      <map
        style="width: 100%; height: 420rpx; border-radius: 12rpx"
        :longitude="mapCenter.lng"
        :latitude="mapCenter.lat"
        :markers="markers"
        :polyline="polyline"
        :scale="12"
        @markertap="onMarkerTap"
      />
      <view class="app-subtext">在线定位设备：{{ markers.length }} 台（地图最多显示 120 台）</view>
      <view v-if="selectedDeviceId" class="app-row">
        <text class="app-subtext">当前轨迹：{{ selectedDeviceName }}（{{ trajectoryPoints.length }} 点）</text>
        <AppStatusTag text="轨迹已加载" type="success" />
      </view>
    </view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text>视频联动</text>
        <AppStatusTag :text="selectedDeviceId ? selectedDeviceName : '未选择设备'" :type="selectedDeviceId ? 'success' : 'info'" />
      </view>
      <view class="app-row">
        <text class="app-subtext">联动线路</text>
        <AppStatusTag :text="linkedPlayMode.toUpperCase()" :type="linkedPlayUrl ? 'success' : 'warning'" />
      </view>
      <view v-if="linkedLoading" class="app-subtext">联动视频加载中...</view>
      <AppStreamPlayer v-else-if="linkedPlayUrl" :url="linkedPlayUrl" :mode="linkedPlayMode" />
      <AppEmpty v-else :text="linkedPlayError || '点击地图点位后自动联动视频'" />
    </view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text>会商会话</text>
        <AppStatusTag :text="sessionStatus === 'closed' ? '已结束' : sessionId ? '进行中' : '未开始'" :type="sessionStatus === 'closed' ? 'info' : sessionId ? 'success' : 'warning'" />
      </view>
      <view v-if="fromAlarmId" class="app-row">
        <text class="app-subtext">来源告警：{{ fromAlarmId }}</text>
        <AppStatusTag text="告警联动" type="warning" />
      </view>
      <view class="app-row">
        <text class="app-subtext">指令追踪</text>
        <AppStatusTag :text="instructionPollingEnabled ? '自动轮询中(5s)' : '未轮询'" :type="instructionPollingEnabled ? 'success' : 'info'" />
      </view>
      <view class="app-row">
        <text class="app-subtext">近期未确认告警：{{ recentOpenAlarms.length }} 条</text>
        <picker
          mode="selector"
          :range="['不限时间', '1小时', '24小时', '7天']"
          :value="alarmTimeWindow === '' ? 0 : alarmTimeWindow === '1h' ? 1 : alarmTimeWindow === '24h' ? 2 : 3"
          @change="
            (e:any) => {
              const i = Number(e?.detail?.value || 0);
              alarmTimeWindow = i === 1 ? '1h' : i === 2 ? '24h' : i === 3 ? '7d' : '';
              loadRecentOpenAlarms();
            }
          "
        >
          <view class="app-subtext">
            时间窗：{{ alarmTimeWindow === '' ? '不限' : alarmTimeWindow === '1h' ? '1小时' : alarmTimeWindow === '24h' ? '24小时' : '7天' }}
          </view>
        </picker>
        <button size="mini" :loading="recentOpenAlarmsLoading" @click="loadRecentOpenAlarms">刷新告警</button>
      </view>
      <view v-if="recentOpenAlarms.length" class="app-gap-12">
        <view v-for="a in recentOpenAlarms.slice(0, 10)" :key="a.id" class="app-card">
          <text class="app-subtext">告警：{{ a.description || "-" }}</text>
          <text class="app-subtext">设备：{{ a.device_id || "-" }}；通道：{{ a.channel_id || "-" }}</text>
          <text class="app-subtext">级别：{{ a.priority ?? "-" }}；时间：{{ a.time || a.created_at || "-" }}</text>
          <view class="app-row">
            <button size="mini" type="primary" :loading="actionLoading" @click="createConferenceByAlarm(a)">发起会商</button>
          </view>
        </view>
      </view>
      <AppEmpty v-else :text="recentOpenAlarmsLoading ? '告警加载中...' : '暂无未确认告警'" />
      <view class="app-row">
        <text class="app-subtext">会话历史：{{ filteredRecentSessions.length }} / {{ recentSessions.length }} 个</text>
        <button size="mini" :loading="actionLoading" @click="loadRecentSessions">刷新会话列表</button>
        <button size="mini" :loading="actionLoading" @click="forceRefreshRecentSessions">强制刷新</button>
        <button size="mini" @click="clearRecentSessionsCache">清理缓存</button>
      </view>
      <text class="app-subtext">
        数据来源：{{ sessionRecentUsingCache ? '本地缓存兜底' : '服务端实时' }}
      </text>
      <text v-if="sessionRecentCacheUpdatedAt" class="app-subtext">
        缓存更新时间：{{ formatSessionTime(sessionRecentCacheUpdatedAt) }}
      </text>
      <text v-if="sessionRecentCacheUpdatedAt" class="app-subtext">
        缓存状态：{{ sessionRecentCacheExpired ? `已过期（超出${sessionRecentCacheTtlMin}分钟TTL）` : `有效（${sessionRecentCacheTtlMin}分钟TTL内）` }}
      </text>
      <text class="app-subtext">{{ sessionRecentCachePolicyText }}</text>
      <text class="app-subtext">缓存预设：{{ sessionRecentCacheCurrentPresetLabel }}</text>
      <text class="app-subtext">{{ sessionRecentCachePolicyChangeText }}</text>
      <text class="app-subtext">{{ sessionRecentCachePolicyLastSnapshotText }}</text>
      <text class="app-subtext">{{ sessionRecentCachePolicyRecentItemsText }}</text>
      <text class="app-subtext">{{ sessionRecentCachePolicySourceStatsText }}</text>
      <text class="app-subtext">{{ sessionRecentCachePolicySourceTop1Text }}</text>
      <text class="app-subtext">{{ sessionRecentCacheHitRateText }}</text>
      <text class="app-subtext">{{ sessionRecentCacheCountersText }}</text>
      <text class="app-subtext">{{ sessionRecentCacheSelfCheckText }}</text>
      <text class="app-subtext">
        命中统计：服务端={{ sessionRecentServerHitCount }}；缓存={{ sessionRecentCacheHitCount }}；强制刷新失败={{ sessionRecentForceRefreshFailCount }}
      </text>
      <view class="app-row">
        <text class="app-subtext">缓存预设</text>
        <button size="mini" @click="applyRecentSessionsCachePolicyPreset('stable')">稳态</button>
        <button size="mini" @click="applyRecentSessionsCachePolicyPreset('balanced')">平衡</button>
        <button size="mini" @click="applyRecentSessionsCachePolicyPreset('compact')">省存</button>
      </view>
      <view class="app-row">
        <picker
          mode="selector"
          :range="['TTL 5 分钟', 'TTL 10 分钟', 'TTL 15 分钟', 'TTL 30 分钟']"
          :value="sessionRecentCacheTtlMin === 5 ? 0 : sessionRecentCacheTtlMin === 10 ? 1 : sessionRecentCacheTtlMin === 15 ? 2 : 3"
          @change="(e:any) => onRecentCacheTtlPolicyChange(Number(e?.detail?.value || 0))"
        >
          <view class="app-subtext">TTL：{{ sessionRecentCacheTtlMin }} 分钟</view>
        </picker>
        <picker
          mode="selector"
          :range="['50 条', '100 条', '200 条']"
          :value="sessionRecentCacheMaxRows === 50 ? 0 : sessionRecentCacheMaxRows === 100 ? 1 : 2"
          @change="(e:any) => onRecentCacheMaxRowsPolicyChange(Number(e?.detail?.value || 0))"
        >
          <view class="app-subtext">容量：{{ sessionRecentCacheMaxRows }} 条</view>
        </picker>
        <button size="mini" @click="resetRecentSessionsCachePolicy">恢复默认策略</button>
      </view>
      <view class="app-row">
        <button size="mini" @click="copyRecentCachePolicySummary">复制缓存摘要</button>
        <button size="mini" @click="copyRecentCachePresetSummary">复制预设摘要</button>
        <button size="mini" @click="copyRecentCachePolicyChangeSummary">复制策略变更</button>
        <button size="mini" @click="copyRecentCachePolicyLastSnapshot">复制策略快照</button>
        <button size="mini" @click="copyRecentCachePolicySourceTop1">复制来源Top1</button>
        <button size="mini" @click="copyRecentCachePolicyRecentItems">复制最近策略</button>
        <button size="mini" @click="copyRecentCachePolicySourceStats">复制来源统计</button>
        <button size="mini" @click="copyRecentCachePolicyOverview">复制策略总览</button>
        <button size="mini" @click="copyRecentCachePolicyAuditJson">复制策略审计JSON</button>
        <button size="mini" @click="copyRecentCachePolicyAuditCsv">复制策略审计CSV</button>
        <button size="mini" @click="clearRecentCachePolicyAudit">清理策略审计</button>
      </view>
      <view class="app-row">
        <button size="mini" @click="copyRecentCacheStatsText">复制命中统计</button>
        <button size="mini" @click="copyRecentCacheStatsJson">复制命中JSON</button>
        <button size="mini" @click="resetRecentCacheStats">重置命中统计</button>
      </view>
      <view class="app-row">
        <text class="app-subtext">筛选预设</text>
        <button size="mini" @click="applySessionFilterPreset('duty')">值班</button>
        <button size="mini" @click="applySessionFilterPreset('urgent')">紧急</button>
        <button size="mini" @click="applySessionFilterPreset('review')">复盘</button>
        <button size="mini" @click="applySessionFilterPreset('all')">全部</button>
      </view>
      <view class="app-row">
        <text class="app-subtext">视图预设</text>
        <button size="mini" @click="applySessionViewPreset('fast')">快速</button>
        <button size="mini" @click="applySessionViewPreset('balanced')">平衡</button>
        <button size="mini" @click="applySessionViewPreset('dense')">高密度</button>
        <button size="mini" @click="resetSessionViewConfig">重置视图</button>
      </view>
      <view class="app-row">
        <picker
          mode="selector"
          :range="['按最近活跃', '按指令数', '按会话时长']"
          :value="sessionHistorySortMode === 'active' ? 0 : sessionHistorySortMode === 'instruction_count' ? 1 : 2"
          @change="(e:any) => onSessionSortModeChange(Number(e?.detail?.value || 0))"
        >
          <view class="app-subtext">排序：{{ sessionHistorySortMode === 'active' ? '最近活跃' : (sessionHistorySortMode === 'instruction_count' ? '指令数' : '会话时长') }}</view>
        </picker>
        <picker
          mode="selector"
          :range="['20 条', '50 条', '100 条']"
          :value="sessionHistoryLimit === 20 ? 0 : sessionHistoryLimit === 50 ? 1 : 2"
          @change="(e:any) => onSessionLimitChange(Number(e?.detail?.value || 0))"
        >
          <view class="app-subtext">列表条数：{{ sessionHistoryLimit }}</view>
        </picker>
      </view>
      <text class="app-subtext">当前预设：{{ sessionCurrentPresetLabel }}</text>
      <text class="app-subtext">{{ sessionViewSummaryText }}</text>
      <text v-if="sessionLastViewPreset" class="app-subtext">上次视图预设：{{ sessionLastViewPreset }}</text>
      <text v-if="sessionLastViewPresetAt" class="app-subtext">视图切换时间：{{ formatSessionTime(sessionLastViewPresetAt) }}</text>
      <text v-if="sessionLastHandoverCopiedAt" class="app-subtext">上次交接复制：{{ formatSessionTime(sessionLastHandoverCopiedAt) }}</text>
      <text v-if="sessionLastHandoverCopyMode" class="app-subtext">交接复制方式：{{ sessionLastHandoverCopyMode === 'json' ? 'JSON' : '文本' }}</text>
      <text v-if="sessionLastConclusionCopiedAt" class="app-subtext">上次结论复制：{{ formatSessionTime(sessionLastConclusionCopiedAt) }}</text>
      <text v-if="sessionLastConclusionCopyMode" class="app-subtext">结论复制方式：{{ sessionLastConclusionCopyMode === 'json' ? 'JSON' : '文本' }}</text>
      <text v-if="sessionLastPackageCopiedAt" class="app-subtext">上次组合包复制：{{ formatSessionTime(sessionLastPackageCopiedAt) }}</text>
      <text v-if="sessionLastPackageCopyMode" class="app-subtext">组合包复制方式：{{ sessionLastPackageCopyMode === 'json' ? 'JSON' : '文本' }}</text>
      <view class="app-row">
        <text class="app-subtext">班次标签</text>
        <input v-model="sessionHandoverShiftLabel" style="flex:1" placeholder="值班/夜班/复盘" @blur="onSessionShiftLabelBlur" />
        <button size="mini" @click="applySessionShiftPreset('值班')">值班</button>
        <button size="mini" @click="applySessionShiftPreset('夜班')">夜班</button>
        <button size="mini" @click="applySessionShiftPreset('复盘')">复盘</button>
      </view>
      <text class="app-subtext">建议文件名：{{ sessionHandoverSuggestedFileName }}</text>
      <text class="app-subtext">{{ sessionHandoverReadyText }}</text>
      <text class="app-subtext">{{ sessionHandoverReadyHintText }}</text>
      <text class="app-subtext">交接摘要指纹：{{ sessionHandoverDigest }}</text>
      <text v-if="sessionLastHandoverDigest" class="app-subtext">上次交接指纹：{{ sessionLastHandoverDigest }}</text>
      <text class="app-subtext">{{ sessionCopyAuditSummaryText }}</text>
      <text class="app-subtext">{{ sessionHandoverBaselineAtText }}</text>
      <text class="app-subtext">{{ sessionHandoverDiffCountText }}</text>
      <text class="app-subtext">变更等级：{{ sessionHandoverDiffLevel.label }}</text>
      <text class="app-subtext">{{ sessionHandoverDiffText }}</text>
      <text v-if="sessionHandoverDiffDetails.length" class="app-subtext">
        差异字段：{{ sessionHandoverDiffDetails.map((x) => `${x.label}(${x.before || '-'} -> ${x.after || '-'})`).join('；') }}
      </text>
      <text class="app-subtext">交接结论预览：{{ sessionHandoverConclusionText }}</text>
      <text class="app-subtext">交接预览：{{ sessionHandoverSummaryText }}</text>
      <text class="app-subtext">筛选条件：{{ sessionFilterSummary }}</text>
      <text class="app-subtext">筛选命中率：{{ sessionFilterHitRateText }}</text>
      <text class="app-subtext">{{ sessionFilterModeText }}</text>
      <text class="app-subtext">{{ sessionFilterHintText }}</text>
      <text class="app-subtext">{{ sessionFilterEnabledCountText }}</text>
      <view v-if="sessionFilterNeedsRelax" class="app-row">
        <text class="app-subtext">{{ sessionNextRelaxStepText }}</text>
        <text class="app-subtext">{{ sessionRelaxQueueText }}</text>
        <text class="app-subtext">{{ sessionRelaxRemainingStepsText }}</text>
        <button size="mini" :loading="actionLoading" @click="relaxSessionFilters">一键放宽筛选</button>
      </view>
      <text v-if="sessionLastRelaxAction" class="app-subtext">上次放宽：{{ sessionLastRelaxAction }}</text>
      <text v-if="sessionLastRelaxAt" class="app-subtext">放宽时间：{{ formatSessionTime(sessionLastRelaxAt) }}</text>
      <view v-if="sessionLastRelaxAction || sessionLastRelaxAt" class="app-row">
        <button size="mini" @click="clearSessionRelaxHistory">清空放宽记录</button>
      </view>
      <view class="app-row">
        <button size="mini" @click="copySessionFilterSummary">复制筛选摘要</button>
        <button size="mini" @click="copySessionViewSummary">复制视图摘要</button>
        <button size="mini" @click="copySessionHandoverSummary">复制交接摘要</button>
        <button size="mini" @click="copySessionHandoverSummaryJson">复制交接JSON</button>
        <button size="mini" @click="copySessionHandoverDiffSummary">复制交接差异</button>
        <button size="mini" @click="copySessionHandoverDiffSummaryJson">复制差异JSON</button>
        <button size="mini" @click="copySessionHandoverConclusion">复制交接结论</button>
        <button size="mini" @click="copySessionHandoverConclusionJson">复制结论JSON</button>
        <button size="mini" @click="copySessionHandoverBundle">复制交接组合包</button>
        <button size="mini" @click="copySessionHandoverBundleJson">复制组合包JSON</button>
        <button size="mini" @click="copySessionCopyAuditSummary">复制审计摘要</button>
        <button size="mini" @click="copySessionCopyAuditJson">复制审计JSON</button>
        <button size="mini" @click="resetSessionHandoverStandardConfig">恢复标准交接</button>
        <button size="mini" @click="markSessionHandoverBaseline">设为当前基线</button>
        <button size="mini" @click="resetSessionHandoverBaseline">重置交接基线</button>
      </view>
      <view class="app-row">
        <picker mode="selector" :range="['全部', '进行中', '已结束']" :value="sessionHistoryStatusFilter === '' ? 0 : sessionHistoryStatusFilter === 'open' ? 1 : 2" @change="(e:any) => onSessionStatusFilterChange(Number(e?.detail?.value || 0))">
          <view class="app-subtext">状态：{{ sessionHistoryStatusFilter === '' ? '全部' : (sessionHistoryStatusFilter === 'open' ? '进行中' : '已结束') }}</view>
        </picker>
        <picker mode="selector" :range="['全部活跃', '1小时内', '24小时内', '7天内']" :value="sessionHistoryActiveWindow === '' ? 0 : sessionHistoryActiveWindow === '1h' ? 1 : sessionHistoryActiveWindow === '24h' ? 2 : 3" @change="(e:any) => onSessionActiveWindowChange(Number(e?.detail?.value || 0))">
          <view class="app-subtext">活跃：{{ sessionHistoryActiveWindow === '' ? '全部' : (sessionHistoryActiveWindow === '1h' ? '1小时内' : (sessionHistoryActiveWindow === '24h' ? '24小时内' : '7天内')) }}</view>
        </picker>
        <input v-model="sessionHistoryKeyword" placeholder="按会话ID/标题/告警ID筛选" style="flex:1" @confirm="onSessionKeywordQuery" />
        <button size="mini" :loading="actionLoading" @click="onSessionKeywordQuery">查询</button>
        <button size="mini" :loading="actionLoading" @click="resetSessionHistoryFilters">清空筛选</button>
      </view>
      <view v-if="sessionRecentKeywords.length" class="app-row">
        <text class="app-subtext">关键词历史</text>
        <button
          v-for="kw in sessionRecentKeywords"
          :key="kw"
          size="mini"
          @click="applyRecentKeyword(kw)"
        >
          {{ kw }}
        </button>
        <button size="mini" @click="clearRecentKeywords">清空历史</button>
      </view>
      <view v-if="filteredRecentSessions.length" class="app-gap-12">
        <view v-for="s in filteredRecentSessions" :key="s.id" class="app-row">
          <view style="flex:1">
            <text class="app-subtext">{{ s.title || s.id }}</text>
            <view class="app-subtext">ID：{{ s.id }} / 状态：{{ s.status || '-' }}</view>
            <view class="app-subtext">成员：{{ s.participant_count || 0 }} / 指令：{{ s.instruction_count || 0 }}</view>
            <view class="app-subtext">最近指令：{{ formatSessionTime(s.last_instruction_at) }} / 持续：{{ formatSessionDuration(s.duration_sec) }}</view>
          </view>
          <button size="mini" :disabled="s.status === 'closed'" :loading="actionLoading" @click="joinExistingSession(s.id)">加入</button>
        </view>
      </view>
      <AppEmpty
        v-else
        :text="
          recentSessions.length === 0
            ? '暂无会话记录'
            : '当前筛选条件下暂无会话，请调整状态/活跃时间/关键词后重试'
        "
      />
      <input v-model="sessionTitle" placeholder="会商标题（可选）" />
      <view class="app-row">
        <button size="mini" type="primary" :loading="actionLoading" @click="createConference">创建会商</button>
        <button
          size="mini"
          type="primary"
          :disabled="!selectedDeviceId"
          :loading="actionLoading"
          @click="createConferenceBySelectedDevice"
        >
          当前设备会商
        </button>
        <button size="mini" :disabled="!sessionId" :loading="actionLoading" @click="refreshSessionData">刷新</button>
        <button size="mini" :disabled="!sessionId || sessionStatus === 'closed'" :loading="actionLoading" @click="endConference">结束会商</button>
      </view>
      <text class="app-subtext">会话ID：{{ sessionId || "-" }}</text>
      <text class="app-subtext">操作状态：{{ sessionActionStatusMessage || "-" }}</text>
      <text v-if="sessionActionStatusAt" class="app-subtext">状态时间：{{ formatSessionTime(sessionActionStatusAt) }}</text>
      <text class="app-subtext">参会成员：{{ participants.length }} 人</text>
      <text class="app-subtext">{{ sessionExecutionHealthSummaryText }}</text>
      <text class="app-subtext">{{ sessionExecutionHealthNextStepAdvice }}</text>
      <text class="app-subtext">{{ sessionRoleCoverageSummaryText }}</text>
      <text class="app-subtext">{{ sessionRoleCoverageAdvice }}</text>
      <text class="app-subtext">{{ sessionInstructionActivitySummaryText }}</text>
      <text class="app-subtext">{{ sessionInstructionActivityAdvice }}</text>
      <text class="app-subtext">{{ sessionRefreshTimelinessSummaryText }}</text>
      <text class="app-subtext">{{ sessionRefreshTimelinessAdvice }}</text>
      <text class="app-subtext">{{ sessionInstructionKeywordHitSummaryText }}</text>
      <text class="app-subtext">{{ sessionInstructionKeywordHitAdvice }}</text>
      <text class="app-subtext">{{ sessionMemberRefreshCoverageSummaryText }}</text>
      <text class="app-subtext">{{ sessionMemberRefreshCoverageAdvice }}</text>
      <view class="app-row">
        <button size="mini" @click="copySessionExecutionHealthSummary">复制执行健康摘要</button>
        <button size="mini" @click="copySessionRoleCoverageSummary">复制角色覆盖摘要</button>
        <button size="mini" @click="copySessionInstructionActivitySummary">复制指令活跃摘要</button>
        <button size="mini" @click="copySessionRefreshTimelinessSummary">复制刷新时效摘要</button>
        <button size="mini" @click="copySessionInstructionKeywordHitSummary">复制关键词命中摘要</button>
        <button size="mini" @click="copySessionMemberRefreshCoverageSummary">复制成员覆盖摘要</button>
      </view>
      <view class="app-row">
        <picker
          mode="selector"
          :range="['全部角色', 'Owner', 'participant', 'coordinator', 'observer']"
          :value="memberRoleFilter === '' ? 0 : memberRoleFilter === 'owner' ? 1 : memberRoleFilter === 'participant' ? 2 : memberRoleFilter === 'coordinator' ? 3 : 4"
          @change="(e:any) => { const i = Number(e?.detail?.value || 0); memberRoleFilter = i === 1 ? 'owner' : i === 2 ? 'participant' : i === 3 ? 'coordinator' : i === 4 ? 'observer' : ''; refreshSessionData(false); }"
        >
          <view class="app-subtext">成员角色筛选：{{ memberRoleFilter || '全部' }}</view>
        </picker>
      </view>
      <text class="app-subtext">成员刷新：{{ memberLastRefreshAt || "-" }}</text>
      <text class="app-subtext">指令刷新：{{ instructionLastRefreshAt || "-" }} {{ instructionDeltaCount > 0 ? `(新增 ${instructionDeltaCount} 条)` : "" }}</text>
      <view v-if="participants.length" class="app-gap-12">
        <view v-for="p in participants" :key="p.id" class="app-row">
          <text>{{ p.username }}</text>
          <AppStatusTag :text="participantRoleLabel(p.role)" :type="participantRoleType(p.role)" />
        </view>
      </view>
      <input v-model="instructionText" placeholder="输入会商指令" />
      <view class="app-row">
        <input v-model="instructionKeyword" placeholder="按关键词筛选指令记录（服务端）" style="flex:1" @confirm="() => refreshSessionData(false)" />
        <button size="mini" :disabled="!sessionId" :loading="actionLoading" @click="() => refreshSessionData(false)">查询</button>
      </view>
      <button :disabled="!sessionId" :loading="actionLoading" @click="sendInstruction">发布指令</button>
      <view class="app-gap-12">
        <view v-for="item in filteredInstructions" :key="item.id" class="app-card" style="padding: 12rpx">
          <text>{{ item.content }}</text>
          <view class="app-subtext">{{ item.created_at || "-" }}</view>
        </view>
      </view>
      <AppEmpty v-if="sessionId && filteredInstructions.length === 0" :text="instructionKeyword ? '关键词下暂无匹配指令' : '暂无会商指令'" />
    </view>
  </view>
</template>
