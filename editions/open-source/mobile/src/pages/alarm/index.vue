<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref, watch } from "vue";
import {
  acknowledgeAlarm,
  escalateAlarm,
  fetchAlarms,
  fetchSlaPresets,
  fetchSlaPresetAudits,
  fetchSlaCompare,
  fetchSlaOverview,
  fetchSlaQuality,
  saveSlaPresets,
  type AlarmItem,
  type AlarmDashboardPresetItem,
  type AlarmDashboardPresetAuditItem,
  type SlaQualitySlowSample,
  type SlaOverview
} from "@/api/alarm";
import { createWorkOrder, listWorkOrders, type WorkOrderItem, type WorkOrderStatus, updateWorkOrderStatus } from "@/api/workOrder";
import { fetchDevices } from "@/api/device";
import { listOrganizations } from "@/api/organization";
import { listUsers } from "@/api/user";
import AppBarChart from "@/components/AppBarChart.vue";
import AppStatusTag from "@/components/AppStatusTag.vue";
import AppEmpty from "@/components/AppEmpty.vue";

const DASHBOARD_PREF_KEY = "pgbsentry_mobile_alarm_dashboard_prefs";
const ALARM_FILTER_SNAPSHOT_KEY = "pgbsentry_mobile_alarm_filter_snapshot";
const ALARM_FILTER_SNAPSHOT_HISTORY_KEY = "pgbsentry_mobile_alarm_filter_snapshot_history";
const DASHBOARD_PRESETS_KEY = "pgbsentry_mobile_alarm_dashboard_presets";
const REVIEW_EXPORT_HISTORY_KEY = "pgbsentry_mobile_alarm_review_export_history";
const REVIEW_EXPORT_WINDOW_RELAX_KEY = "pgbsentry_mobile_alarm_review_export_window_relax";
const REVIEW_EXPORT_WINDOW_ACTION_KEY = "pgbsentry_mobile_alarm_review_export_window_action";
const REVIEW_EXPORT_WINDOW_ACTION_AUDIT_KEY = "pgbsentry_mobile_alarm_review_export_window_action_audit";
const REVIEW_EXPORT_WINDOW_ACTION_AUDIT_RELAX_KEY = "pgbsentry_mobile_alarm_review_export_window_action_audit_relax";
const REVIEW_EXPORT_WINDOW_ACTION_AUDIT_ACTION_KEY = "pgbsentry_mobile_alarm_review_export_window_action_audit_action";
const REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_KEY = "pgbsentry_mobile_alarm_review_export_window_action_audit_preset_history";
const REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_RELAX_KEY =
  "pgbsentry_mobile_alarm_review_export_window_action_audit_preset_history_relax";
const REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_RELAX_KEY =
  "pgbsentry_mobile_alarm_review_export_window_action_audit_preset_history_action_audit_relax";
const REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_KEY =
  "pgbsentry_mobile_alarm_review_export_window_action_audit_preset_history_action";
const REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_KEY =
  "pgbsentry_mobile_alarm_review_export_window_action_audit_preset_history_action_audit";
const REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_KEY =
  "pgbsentry_mobile_alarm_review_export_window_action_audit_preset_history_action_audit_preset_history";
const REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_RELAX_KEY =
  "pgbsentry_mobile_alarm_review_export_window_action_audit_preset_history_action_audit_preset_history_relax";
const REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_KEY =
  "pgbsentry_mobile_alarm_review_export_window_action_audit_preset_history_action_audit_preset_history_action";
const REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_KEY =
  "pgbsentry_mobile_alarm_review_export_window_action_audit_preset_history_action_audit_preset_history_action_audit";
const REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_RELAX_KEY =
  "pgbsentry_mobile_alarm_review_export_window_action_audit_preset_history_action_audit_preset_history_action_audit_relax";
const REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_ACTION_KEY =
  "pgbsentry_mobile_alarm_review_export_window_action_audit_preset_history_action_audit_preset_history_action_audit_action";
const REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_KEY =
  "pgbsentry_mobile_alarm_review_export_window_action_audit_preset_history_action_audit_preset_history_action_audit_preset_history";
const REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_RELAX_KEY =
  "pgbsentry_mobile_alarm_review_export_window_action_audit_preset_history_action_audit_preset_history_action_audit_preset_history_relax";
const REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_GOVERNANCE_PRESET_HISTORY_KEY =
  "pgbsentry_mobile_alarm_review_export_window_action_audit_preset_history_action_audit_preset_history_action_audit_governance_preset_history";
const REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_GOVERNANCE_PRESET_HISTORY_RELAX_KEY =
  "pgbsentry_mobile_alarm_review_export_window_action_audit_preset_history_action_audit_preset_history_action_audit_governance_preset_history_relax";
const REVIEW_EXPORT_WINDOW_ACTION_AUDIT_MAX = 20;
const REVIEW_EXPORT_WINDOW_ACTION_AUDIT_RECENT_SHOW = 5;
const REVIEW_DISPATCH_PROFILE_KEY = "pgbsentry_mobile_alarm_review_dispatch_profile";
const REVIEW_DISPATCH_STATUS_KEY = "pgbsentry_mobile_alarm_review_dispatch_status";
const REVIEW_DISPATCH_RETRY_QUEUE_KEY = "pgbsentry_mobile_alarm_review_dispatch_retry_queue";
const REVIEW_DISPATCH_ATTEMPT_LOG_KEY = "pgbsentry_mobile_alarm_review_dispatch_attempt_log";
const REVIEW_DISPATCH_ALERTS_KEY = "pgbsentry_mobile_alarm_review_dispatch_alerts";
const REVIEW_DISPATCH_RULES_KEY = "pgbsentry_mobile_alarm_review_dispatch_rules";
const REVIEW_DISPATCH_RULE_PRESETS_KEY = "pgbsentry_mobile_alarm_review_dispatch_rule_presets";
const REVIEW_DISPATCH_RULE_SYNC_META_KEY = "pgbsentry_mobile_alarm_review_dispatch_rule_sync_meta";
const REVIEW_DISPATCH_RULE_CONFLICT_KEY = "pgbsentry_mobile_alarm_review_dispatch_rule_conflict";
const REVIEW_DISPATCH_RULE_AUDITS_KEY = "pgbsentry_mobile_alarm_review_dispatch_rule_audits";
const REVIEW_DISPATCH_CHANNEL_ANALYTICS_KEY = "pgbsentry_mobile_alarm_review_dispatch_channel_analytics";
const WORK_ORDER_RETURN_AGG_KEY = "pgbsentry_mobile_alarm_work_order_return_agg";
const DISPATCH_RULE_CENTER_PRESET_NAME = "__dispatch_rule_center__";
const REVIEW_REPORT_VERSION = "alarm_review_v1";
const savedPrefs = (uni.getStorageSync(DASHBOARD_PREF_KEY) || {}) as Record<string, unknown>;
const savedExportFields = (savedPrefs.exportFields || {}) as Record<string, unknown>;
const EXPORT_FIELD_DEFAULTS: Record<string, boolean> = {
  summary: true,
  sla: true,
  duration: true,
  slow_review: true,
  cross_day: true,
  hourly: true,
  level: true,
  top_device: true,
  assignee: true,
  organization: true,
  work_order: true
};

const loading = ref(false);
const alarms = ref<AlarmItem[]>([]);
const actionLoading = ref(false);
const quickActionAlarmId = ref("");
const selectedAlarmId = ref("");
const actionNote = ref("");
const dispatchTitle = ref("");
const dispatchDesc = ref("");
const workOrders = ref<WorkOrderItem[]>([]);
const workOrderLoading = ref(false);
const slaLoading = ref(false);
const trendLoading = ref(false);
const alarmPageActionStatusMessage = ref("未刷新");
const alarmPageActionStatusAt = ref("");
const trendDays = ref<3 | 7>(savedPrefs.trendDays === 3 ? 3 : 7);
const crossDayTrend = ref<Array<{ label: string; count: number }>>([]);
const compareMetrics = ref({
  periodCurrent: 0,
  periodPrevious: 0,
  periodChangePct: 0,
  dayCurrent: 0,
  dayPrevious: 0,
  dayChangePct: 0
});
const organizationMap = ref<Record<string, string>>({});
const organizationNameMap = ref<Record<string, string>>({});
const userNameMap = ref<Record<string, string>>({});
const selectedAlarmType = ref(String(savedPrefs.selectedAlarmType || ""));
const selectedOrganization = ref(String(savedPrefs.selectedOrganization || ""));
const alarmQuickPreset = ref<"all" | "high" | "unacked">(
  savedPrefs.alarmQuickPreset === "high" || savedPrefs.alarmQuickPreset === "unacked"
    ? (savedPrefs.alarmQuickPreset as "high" | "unacked")
    : "all"
);
type AlarmFilterSnapshotRecord = {
  selectedAlarmType: string;
  selectedOrganization: string;
  selectedOrganizationLabel: string;
  alarmQuickPreset: "all" | "high" | "unacked";
  selectedSlowAlarmId: string;
  savedAt: string;
};
const alarmFilterSnapshotHistory = ref<AlarmFilterSnapshotRecord[]>(
  Array.isArray(uni.getStorageSync(ALARM_FILTER_SNAPSHOT_HISTORY_KEY))
    ? (uni.getStorageSync(ALARM_FILTER_SNAPSHOT_HISTORY_KEY) as Array<Record<string, unknown>>)
        .map((x) => ({
          selectedAlarmType: String(x.selectedAlarmType || ""),
          selectedOrganization: String(x.selectedOrganization || ""),
          selectedOrganizationLabel: String(x.selectedOrganizationLabel || ""),
          alarmQuickPreset:
            String(x.alarmQuickPreset || "") === "high" || String(x.alarmQuickPreset || "") === "unacked"
              ? (String(x.alarmQuickPreset) as "high" | "unacked")
              : "all",
          selectedSlowAlarmId: String(x.selectedSlowAlarmId || ""),
          savedAt: String(x.savedAt || "")
        }))
        .filter((x) => !!x.savedAt)
    : []
);
const importSnapshotInputVisible = ref(false);
const importSnapshotJsonText = ref("");
const alarmTypeOptions = ref<string[]>(["全部类型"]);
const organizationOptions = ref<Array<{ label: string; value: string }>>([{ label: "全部组织", value: "" }]);

function setAlarmPageActionStatus(message: string) {
  alarmPageActionStatusMessage.value = message;
  alarmPageActionStatusAt.value = new Date().toISOString();
}
const durationMetrics = ref({
  p50: 0,
  p90: 0,
  samples: 0
});
const slowSamples = ref<SlaQualitySlowSample[]>([]);
const selectedSlowAlarmId = ref("");
const dispatchProfile = ref<{
  mode: "clipboard" | "webhook" | "channel_api";
  channel: string;
  to: string;
  cc: string;
  webhookUrl: string;
  webhookToken: string;
  channelApiUrl: string;
  channelApiToken: string;
  channelApiAppId: string;
  channelApiGrayEnabled: boolean;
  channelApiGrayOrganizations: string;
  channelApiGrayShifts: string;
  channelApiSignEnabled: boolean;
  channelApiSignSecret: string;
}>(
  (uni.getStorageSync(REVIEW_DISPATCH_PROFILE_KEY) || {
    mode: "clipboard",
    channel: "值班群",
    to: "",
    cc: "",
    webhookUrl: "",
    webhookToken: "",
    channelApiUrl: "",
    channelApiToken: "",
    channelApiAppId: "mobile-alarm-review",
    channelApiGrayEnabled: false,
    channelApiGrayOrganizations: "",
    channelApiGrayShifts: "",
    channelApiSignEnabled: false,
    channelApiSignSecret: ""
  }) as {
    mode: "clipboard" | "webhook" | "channel_api";
    channel: string;
    to: string;
    cc: string;
    webhookUrl: string;
    webhookToken: string;
    channelApiUrl: string;
    channelApiToken: string;
    channelApiAppId: string;
    channelApiGrayEnabled: boolean;
    channelApiGrayOrganizations: string;
    channelApiGrayShifts: string;
    channelApiSignEnabled: boolean;
    channelApiSignSecret: string;
  }
);
const dispatchStatus = ref<{
  lastStatus: "idle" | "skipped" | "success" | "failed";
  lastMessage: string;
  lastAt: string;
  successCount: number;
  failCount: number;
}>(
  (uni.getStorageSync(REVIEW_DISPATCH_STATUS_KEY) || {
    lastStatus: "idle",
    lastMessage: "尚未分发",
    lastAt: "",
    successCount: 0,
    failCount: 0
  }) as {
    lastStatus: "idle" | "skipped" | "success" | "failed";
    lastMessage: string;
    lastAt: string;
    successCount: number;
    failCount: number;
  }
);
const dispatchChannelAnalytics = ref<{
  channelApiRequests: number;
  grayEvaluated: number;
  grayHit: number;
  graySkipped: number;
  signEnabledRequests: number;
  replayRejected: number;
  lastEval: string;
  lastMessage: string;
}>(
  (uni.getStorageSync(REVIEW_DISPATCH_CHANNEL_ANALYTICS_KEY) || {
    channelApiRequests: 0,
    grayEvaluated: 0,
    grayHit: 0,
    graySkipped: 0,
    signEnabledRequests: 0,
    replayRejected: 0,
    lastEval: "",
    lastMessage: "暂无渠道联调记录"
  }) as {
    channelApiRequests: number;
    grayEvaluated: number;
    grayHit: number;
    graySkipped: number;
    signEnabledRequests: number;
    replayRejected: number;
    lastEval: string;
    lastMessage: string;
  }
);
const dispatchRetryQueue = ref<Array<{
  id: string;
  filename: string;
  summary: string;
  webhookUrl: string;
  dispatchMode: "webhook" | "channel_api";
  channelApiAppId: string;
  createdAt: string;
  attempts: number;
  lastError: string;
  reasonType: "network" | "http4xx" | "http5xx" | "config" | "other";
}>>(
  Array.isArray(uni.getStorageSync(REVIEW_DISPATCH_RETRY_QUEUE_KEY))
    ? (uni.getStorageSync(REVIEW_DISPATCH_RETRY_QUEUE_KEY) as Array<Record<string, unknown>>)
        .map((item) => ({
          id: String(item.id || ""),
          filename: String(item.filename || ""),
          summary: String(item.summary || ""),
          webhookUrl: String(item.webhookUrl || ""),
          dispatchMode: String(item.dispatchMode || "") === "channel_api" ? "channel_api" : "webhook",
          channelApiAppId: String(item.channelApiAppId || ""),
          createdAt: String(item.createdAt || ""),
          attempts: Number(item.attempts || 1),
          lastError: String(item.lastError || ""),
          reasonType: (String(item.reasonType || "other") as "network" | "http4xx" | "http5xx" | "config" | "other")
        }))
        .filter((x) => !!x.id)
    : []
);
const dispatchAttemptLog = ref<Array<{
  at: string;
  source: "dispatch" | "retry";
  result: "success" | "failed";
  reasonType: "network" | "http4xx" | "http5xx" | "config" | "other";
  message: string;
  statusCode: number;
}>>(
  Array.isArray(uni.getStorageSync(REVIEW_DISPATCH_ATTEMPT_LOG_KEY))
    ? (uni.getStorageSync(REVIEW_DISPATCH_ATTEMPT_LOG_KEY) as Array<{
        at: string;
        source: "dispatch" | "retry";
        result: "success" | "failed";
        reasonType: "network" | "http4xx" | "http5xx" | "config" | "other";
        message: string;
        statusCode: number;
      }>)
    : []
);
const dispatchAlerts = ref<Array<{
  id: string;
  level: "warning" | "error" | "info";
  message: string;
  createdAt: string;
  resolved: boolean;
}>>(
  Array.isArray(uni.getStorageSync(REVIEW_DISPATCH_ALERTS_KEY))
    ? (uni.getStorageSync(REVIEW_DISPATCH_ALERTS_KEY) as Array<{
        id: string;
        level: "warning" | "error" | "info";
        message: string;
        createdAt: string;
        resolved: boolean;
      }>)
    : []
);
const dispatchAlertFilter = ref<"all" | "error_only">("all");
const dispatchRules = ref<{
  preset: "strict" | "balanced" | "noise_reduction" | "custom";
  muteHttp4xxAlerts: boolean;
  promoteNetworkToError: boolean;
}>(
  (uni.getStorageSync(REVIEW_DISPATCH_RULES_KEY) || {
    preset: "balanced",
    muteHttp4xxAlerts: false,
    promoteNetworkToError: false
  }) as {
    preset: "strict" | "balanced" | "noise_reduction" | "custom";
    muteHttp4xxAlerts: boolean;
    promoteNetworkToError: boolean;
  }
);
const dispatchRulePresets = ref<Array<{
  name: string;
  muteHttp4xxAlerts: boolean;
  promoteNetworkToError: boolean;
}>>(
  Array.isArray(uni.getStorageSync(REVIEW_DISPATCH_RULE_PRESETS_KEY))
    ? (uni.getStorageSync(REVIEW_DISPATCH_RULE_PRESETS_KEY) as Array<{
        name: string;
        muteHttp4xxAlerts: boolean;
        promoteNetworkToError: boolean;
      }>)
    : []
);
const dispatchRuleSyncMeta = ref<{
  source: "server" | "local";
  lastSyncAt: string;
  lastSyncStatus: "idle" | "success" | "failed";
  lastSyncMessage: string;
}>(
  (uni.getStorageSync(REVIEW_DISPATCH_RULE_SYNC_META_KEY) || {
    source: "local",
    lastSyncAt: "",
    lastSyncStatus: "idle",
    lastSyncMessage: "未同步"
  }) as {
    source: "server" | "local";
    lastSyncAt: string;
    lastSyncStatus: "idle" | "success" | "failed";
    lastSyncMessage: string;
  }
);
type DispatchRuleCenterSnapshot = {
  rules: {
    preset: "strict" | "balanced" | "noise_reduction" | "custom";
    muteHttp4xxAlerts: boolean;
    promoteNetworkToError: boolean;
  };
  presets: Array<{
    name: string;
    muteHttp4xxAlerts: boolean;
    promoteNetworkToError: boolean;
  }>;
};
type DispatchRuleAuditItem = {
  id: string;
  at: string;
  source:
    | "template"
    | "toggle"
    | "named_preset_save"
    | "named_preset_apply"
    | "named_preset_remove"
    | "conflict_resolve_server"
    | "conflict_resolve_local"
    | "rollback";
  message: string;
  snapshot: DispatchRuleCenterSnapshot;
};
type WorkOrderReturnEventItem = {
  id: string;
  at: string;
  workOrderId: string;
  alarmId: string;
  source: "work_order_detail" | "work_order_detail_full_refresh";
  fromStatus: WorkOrderStatus | "";
  toStatus: WorkOrderStatus | "";
};
const dispatchRuleConflict = ref<{
  hasConflict: boolean;
  detectedAt: string;
  message: string;
  localSnapshot: DispatchRuleCenterSnapshot | null;
  serverSnapshot: DispatchRuleCenterSnapshot | null;
}>(
  (uni.getStorageSync(REVIEW_DISPATCH_RULE_CONFLICT_KEY) || {
    hasConflict: false,
    detectedAt: "",
    message: "",
    localSnapshot: null,
    serverSnapshot: null
  }) as {
    hasConflict: boolean;
    detectedAt: string;
    message: string;
    localSnapshot: DispatchRuleCenterSnapshot | null;
    serverSnapshot: DispatchRuleCenterSnapshot | null;
  }
);
const dispatchRuleAudits = ref<DispatchRuleAuditItem[]>(
  Array.isArray(uni.getStorageSync(REVIEW_DISPATCH_RULE_AUDITS_KEY))
    ? (uni.getStorageSync(REVIEW_DISPATCH_RULE_AUDITS_KEY) as Array<Record<string, unknown>>)
        .map((item) => {
          const snapshot = normalizeDispatchRuleCenterSnapshot({
            rules: {
              preset: String(((item.snapshot as Record<string, unknown>)?.rules as Record<string, unknown>)?.preset || "custom") as
                | "strict"
                | "balanced"
                | "noise_reduction"
                | "custom",
              muteHttp4xxAlerts: Boolean(
                (((item.snapshot as Record<string, unknown>)?.rules as Record<string, unknown>)?.muteHttp4xxAlerts)
              ),
              promoteNetworkToError: Boolean(
                (((item.snapshot as Record<string, unknown>)?.rules as Record<string, unknown>)?.promoteNetworkToError)
              )
            },
            presets: Array.isArray((item.snapshot as Record<string, unknown>)?.presets)
              ? ((item.snapshot as Record<string, unknown>).presets as Array<Record<string, unknown>>).map((x) => ({
                  name: String(x.name || ""),
                  muteHttp4xxAlerts: Boolean(x.muteHttp4xxAlerts),
                  promoteNetworkToError: Boolean(x.promoteNetworkToError)
                }))
              : []
          });
          const source = String(item.source || "");
          if (
            source !== "template" &&
            source !== "toggle" &&
            source !== "named_preset_save" &&
            source !== "named_preset_apply" &&
            source !== "named_preset_remove" &&
            source !== "conflict_resolve_server" &&
            source !== "conflict_resolve_local" &&
            source !== "rollback"
          ) {
            return null;
          }
          return {
            id: String(item.id || ""),
            at: String(item.at || ""),
            source,
            message: String(item.message || ""),
            snapshot
          } as DispatchRuleAuditItem;
        })
        .filter((x): x is DispatchRuleAuditItem => !!x && !!x.id)
        .slice(0, 30)
    : []
);
const dispatchRuleRollbackingAuditId = ref("");
const workOrderReturnEvents = ref<WorkOrderReturnEventItem[]>(
  Array.isArray(uni.getStorageSync(WORK_ORDER_RETURN_AGG_KEY))
    ? (uni.getStorageSync(WORK_ORDER_RETURN_AGG_KEY) as Array<Record<string, unknown>>)
        .map((item) => {
          const source = String(item.source || "");
          const fromStatus = String(item.fromStatus || "");
          const toStatus = String(item.toStatus || "");
          if (source !== "work_order_detail" && source !== "work_order_detail_full_refresh") return null;
          if (fromStatus && fromStatus !== "open" && fromStatus !== "in_progress" && fromStatus !== "resolved" && fromStatus !== "closed") return null;
          if (toStatus && toStatus !== "open" && toStatus !== "in_progress" && toStatus !== "resolved" && toStatus !== "closed") return null;
          return {
            id: String(item.id || ""),
            at: String(item.at || ""),
            workOrderId: String(item.workOrderId || ""),
            alarmId: String(item.alarmId || ""),
            source,
            fromStatus: (fromStatus || "") as WorkOrderStatus | "",
            toStatus: (toStatus || "") as WorkOrderStatus | ""
          } as WorkOrderReturnEventItem;
        })
        .filter((x): x is WorkOrderReturnEventItem => !!x && !!x.id)
        .slice(0, 100)
    : []
);
const dispatchRulePresetName = ref("");
const dispatchRulePresetSelected = ref("");
const reviewExportHistory = ref<Array<{
  generatedAt: string;
  shiftKey: "day" | "evening" | "night";
  shiftLabel: string;
  windowLabel: string;
  alarmType: string;
  organization: string;
}>>(
  Array.isArray(uni.getStorageSync(REVIEW_EXPORT_HISTORY_KEY))
    ? (uni.getStorageSync(REVIEW_EXPORT_HISTORY_KEY) as Array<{
        generatedAt: string;
        shiftKey: "day" | "evening" | "night";
        shiftLabel: string;
        windowLabel: string;
        alarmType: string;
        organization: string;
      }>)
    : []
);
const reviewExportWindowFilter = ref<"all" | "24h" | "7d">(
  savedPrefs.reviewExportWindowFilter === "24h" || savedPrefs.reviewExportWindowFilter === "7d"
    ? (savedPrefs.reviewExportWindowFilter as "24h" | "7d")
    : "all"
);
const reviewExportWindowActionAuditFilter = ref<"all" | "24h" | "7d">(
  savedPrefs.reviewExportWindowActionAuditFilter === "24h" || savedPrefs.reviewExportWindowActionAuditFilter === "7d"
    ? (savedPrefs.reviewExportWindowActionAuditFilter as "24h" | "7d")
    : "all"
);
const reviewExportWindowActionAuditPresetHistoryFilter = ref<"all" | "24h" | "7d">(
  savedPrefs.reviewExportWindowActionAuditPresetHistoryFilter === "24h" ||
    savedPrefs.reviewExportWindowActionAuditPresetHistoryFilter === "7d"
    ? (savedPrefs.reviewExportWindowActionAuditPresetHistoryFilter as "24h" | "7d")
    : "all"
);
const reviewExportWindowActionAuditPresetHistoryActionAuditFilter = ref<"all" | "24h" | "7d">(
  savedPrefs.reviewExportWindowActionAuditPresetHistoryActionAuditFilter === "24h" ||
    savedPrefs.reviewExportWindowActionAuditPresetHistoryActionAuditFilter === "7d"
    ? (savedPrefs.reviewExportWindowActionAuditPresetHistoryActionAuditFilter as "24h" | "7d")
    : "all"
);
const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryFilter = ref<"all" | "24h" | "7d">(
  savedPrefs.reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryFilter === "24h" ||
    savedPrefs.reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryFilter === "7d"
    ? (savedPrefs.reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryFilter as "24h" | "7d")
    : "all"
);
const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter = ref<"all" | "24h" | "7d">(
  savedPrefs.reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter === "24h" ||
    savedPrefs.reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter === "7d"
    ? (savedPrefs.reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter as "24h" | "7d")
    : "all"
);
const reviewExportWindowLastAction = ref(String((uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_KEY) || {}).action || ""));
const reviewExportWindowLastActionAt = ref(String((uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_KEY) || {}).at || ""));
const reviewExportWindowLastActionSource = ref(
  String((uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_KEY) || {}).source || "")
);
const reviewExportWindowActionAudit = ref<
  Array<{ action: string; source: string; at: string; filter: "all" | "24h" | "7d"; presetLabel: string }>
>(
  (Array.isArray(uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_KEY))
    ? (uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_KEY) as Array<Record<string, unknown>>)
    : []
  )
    .map((x) => ({
      action: String(x?.action || ""),
      source: String(x?.source || ""),
      at: String(x?.at || ""),
      filter: (String(x?.filter || "all") as "all" | "24h" | "7d"),
      presetLabel: String(x?.presetLabel || "自定义")
    }))
    .slice(0, REVIEW_EXPORT_WINDOW_ACTION_AUDIT_MAX)
);
const reviewExportWindowActionAuditLastRelaxAction = ref(
  String((uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_RELAX_KEY) || {}).action || "")
);
const reviewExportWindowActionAuditLastRelaxAt = ref(
  String((uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_RELAX_KEY) || {}).at || "")
);
const reviewExportWindowActionAuditLastAction = ref(
  String((uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_ACTION_KEY) || {}).action || "")
);
const reviewExportWindowActionAuditLastActionAt = ref(
  String((uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_ACTION_KEY) || {}).at || "")
);
const reviewExportWindowActionAuditLastActionSource = ref(
  String((uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_ACTION_KEY) || {}).source || "")
);
const reviewExportWindowActionAuditPresets: Array<{
  key: "strict" | "balanced" | "full";
  label: string;
  filter: "24h" | "7d" | "all";
}> = [
  { key: "strict", label: "严筛", filter: "24h" },
  { key: "balanced", label: "平衡", filter: "7d" },
  { key: "full", label: "全量", filter: "all" }
];
const reviewExportWindowActionAuditPresetHistory = ref<
  Array<{ presetKey: string; presetLabel: string; at: string }>
>(
  (Array.isArray(uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_KEY))
    ? (uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_KEY) as Array<Record<string, unknown>>)
    : []
  )
    .map((x) => ({
      presetKey: String(x?.presetKey || ""),
      presetLabel: String(x?.presetLabel || ""),
      at: String(x?.at || "")
    }))
    .slice(0, REVIEW_EXPORT_WINDOW_ACTION_AUDIT_MAX)
);
const reviewExportWindowActionAuditPresetHistoryLastRelaxAction = ref(
  String((uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_RELAX_KEY) || {}).action || "")
);
const reviewExportWindowActionAuditPresetHistoryLastRelaxAt = ref(
  String((uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_RELAX_KEY) || {}).at || "")
);
const reviewExportWindowActionAuditPresetHistoryActionAuditLastRelaxAction = ref(
  String((uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_RELAX_KEY) || {}).action || "")
);
const reviewExportWindowActionAuditPresetHistoryActionAuditLastRelaxAt = ref(
  String((uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_RELAX_KEY) || {}).at || "")
);
const reviewExportWindowActionAuditPresetHistoryLastAction = ref(
  String((uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_KEY) || {}).action || "")
);
const reviewExportWindowActionAuditPresetHistoryLastActionAt = ref(
  String((uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_KEY) || {}).at || "")
);
const reviewExportWindowActionAuditPresetHistoryLastActionSource = ref(
  String((uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_KEY) || {}).source || "")
);
const reviewExportWindowActionAuditPresetHistoryActionAudit = ref<
  Array<{ action: string; source: string; at: string; filter: "all" | "24h" | "7d"; presetLabel: string }>
>(
  (Array.isArray(uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_KEY))
    ? (uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_KEY) as Array<Record<string, unknown>>)
    : []
  )
    .map((x) => ({
      action: String(x?.action || ""),
      source: String(x?.source || ""),
      at: String(x?.at || ""),
      filter: (String(x?.filter || "all") as "all" | "24h" | "7d"),
      presetLabel: String(x?.presetLabel || "自定义")
    }))
    .slice(0, REVIEW_EXPORT_WINDOW_ACTION_AUDIT_MAX)
);
const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistory = ref<
  Array<{ presetKey: string; presetLabel: string; at: string }>
>(
  (Array.isArray(uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_KEY))
    ? (uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_KEY) as Array<Record<string, unknown>>)
    : []
  )
    .map((x) => ({
      presetKey: String(x?.presetKey || ""),
      presetLabel: String(x?.presetLabel || ""),
      at: String(x?.at || "")
    }))
    .slice(0, REVIEW_EXPORT_WINDOW_ACTION_AUDIT_MAX)
);
const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAction = ref(
  String((uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_RELAX_KEY) || {}).action || "")
);
const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAt = ref(
  String((uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_RELAX_KEY) || {}).at || "")
);
const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryLastAction = ref(
  String((uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_KEY) || {}).action || "")
);
const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryLastActionAt = ref(
  String((uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_KEY) || {}).at || "")
);
const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryLastActionSource = ref(
  String((uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_KEY) || {}).source || "")
);
const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAudit = ref<
  Array<{ action: string; source: string; at: string; filter: "all" | "24h" | "7d"; presetLabel: string }>
>(
  (Array.isArray(uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_KEY))
    ? (uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_KEY) as Array<Record<string, unknown>>)
    : []
  )
    .map((x) => ({
      action: String(x?.action || ""),
      source: String(x?.source || ""),
      at: String(x?.at || ""),
      filter: (String(x?.filter || "all") as "all" | "24h" | "7d"),
      presetLabel: String(x?.presetLabel || "自定义")
    }))
    .slice(0, REVIEW_EXPORT_WINDOW_ACTION_AUDIT_MAX)
);
const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastRelaxAction = ref(
  String((uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_RELAX_KEY) || {}).action || "")
);
const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastRelaxAt = ref(
  String((uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_RELAX_KEY) || {}).at || "")
);
const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastAction = ref(
  String((uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_ACTION_KEY) || {}).action || "")
);
const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastActionAt = ref(
  String((uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_ACTION_KEY) || {}).at || "")
);
const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastActionSource = ref(
  String((uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_ACTION_KEY) || {}).source || "")
);
const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresets: Array<{
  key: "strict" | "balanced" | "full";
  label: string;
  filter: "24h" | "7d" | "all";
}> = [
  { key: "strict", label: "严筛", filter: "24h" },
  { key: "balanced", label: "平衡", filter: "7d" },
  { key: "full", label: "全量", filter: "all" }
];
const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistory = ref<
  Array<{ presetKey: string; presetLabel: string; at: string }>
>(
  (Array.isArray(uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_KEY))
    ? (uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_KEY) as Array<
        Record<string, unknown>
      >)
    : []
  )
    .map((x) => ({
      presetKey: String(x?.presetKey || ""),
      presetLabel: String(x?.presetLabel || ""),
      at: String(x?.at || "")
    }))
    .slice(0, REVIEW_EXPORT_WINDOW_ACTION_AUDIT_MAX)
);
const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAction = ref(
  String((uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_RELAX_KEY) || {}).action || "")
);
const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAt = ref(
  String((uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_RELAX_KEY) || {}).at || "")
);
const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistory = ref<
  Array<{ presetKey: string; presetLabel: string; at: string }>
>(
  (Array.isArray(
    uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_GOVERNANCE_PRESET_HISTORY_KEY)
  )
    ? (uni.getStorageSync(
        REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_GOVERNANCE_PRESET_HISTORY_KEY
      ) as Array<Record<string, unknown>>)
    : []
  )
    .map((x) => ({
      presetKey: String(x?.presetKey || ""),
      presetLabel: String(x?.presetLabel || ""),
      at: String(x?.at || "")
    }))
    .slice(0, REVIEW_EXPORT_WINDOW_ACTION_AUDIT_MAX)
);
const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryLastRelaxAction = ref(
  String((uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_GOVERNANCE_PRESET_HISTORY_RELAX_KEY) || {}).action || "")
);
const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryLastRelaxAt = ref(
  String((uni.getStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_GOVERNANCE_PRESET_HISTORY_RELAX_KEY) || {}).at || "")
);
const reviewExportWindowActionAuditPresetHistoryPresets: Array<{
  key: "strict" | "balanced" | "full";
  label: string;
  filter: "24h" | "7d" | "all";
}> = [
  { key: "strict", label: "严筛", filter: "24h" },
  { key: "balanced", label: "平衡", filter: "7d" },
  { key: "full", label: "全量", filter: "all" }
];
const reviewExportWindowPresets: Array<{ key: "strict" | "balanced" | "full"; label: string; filter: "24h" | "7d" | "all" }> = [
  { key: "strict", label: "严筛", filter: "24h" },
  { key: "balanced", label: "平衡", filter: "7d" },
  { key: "full", label: "全量", filter: "all" }
];
const reviewExportWindowLastRelaxAction = ref(
  String((uni.getStorageSync(REVIEW_EXPORT_WINDOW_RELAX_KEY) || {}).action || "")
);
const reviewExportWindowLastRelaxAt = ref(
  String((uni.getStorageSync(REVIEW_EXPORT_WINDOW_RELAX_KEY) || {}).at || "")
);
const compareMode = ref<"period" | "day">(savedPrefs.compareMode === "day" ? "day" : "period");
const exportTemplate = ref<"summary" | "full">(savedPrefs.exportTemplate === "summary" ? "summary" : "full");
const exportFields = ref<Record<string, boolean>>({
  summary: savedExportFields.summary !== false && EXPORT_FIELD_DEFAULTS.summary,
  sla: savedExportFields.sla !== false && EXPORT_FIELD_DEFAULTS.sla,
  duration: savedExportFields.duration !== false && EXPORT_FIELD_DEFAULTS.duration,
  slow_review: savedExportFields.slow_review !== false && EXPORT_FIELD_DEFAULTS.slow_review,
  cross_day: savedExportFields.cross_day !== false && EXPORT_FIELD_DEFAULTS.cross_day,
  hourly: savedExportFields.hourly !== false && EXPORT_FIELD_DEFAULTS.hourly,
  level: savedExportFields.level !== false && EXPORT_FIELD_DEFAULTS.level,
  top_device: savedExportFields.top_device !== false && EXPORT_FIELD_DEFAULTS.top_device,
  assignee: savedExportFields.assignee !== false && EXPORT_FIELD_DEFAULTS.assignee,
  organization: savedExportFields.organization !== false && EXPORT_FIELD_DEFAULTS.organization,
  work_order: savedExportFields.work_order !== false && EXPORT_FIELD_DEFAULTS.work_order
});
const exportPresetName = ref("");
const exportPresetSelected = ref("");
const presetWritable = ref(true);
const presetAuditLoading = ref(false);
const presetAudits = ref<AlarmDashboardPresetAuditItem[]>([]);
const exportPresets = ref<AlarmDashboardPresetItem[]>(
  Array.isArray(uni.getStorageSync(DASHBOARD_PRESETS_KEY))
    ? (uni.getStorageSync(DASHBOARD_PRESETS_KEY) as AlarmDashboardPresetItem[]).filter((x) => x.name !== DISPATCH_RULE_CENTER_PRESET_NAME)
    : []
);
const exportFieldOptions = [
  { key: "summary", label: "摘要" },
  { key: "sla", label: "SLA" },
  { key: "duration", label: "分位数" },
  { key: "slow_review", label: "复盘结果" },
  { key: "cross_day", label: "跨日趋势" },
  { key: "hourly", label: "小时趋势" },
  { key: "level", label: "等级分布" },
  { key: "top_device", label: "Top设备" },
  { key: "assignee", label: "处置人" },
  { key: "organization", label: "组织" },
  { key: "work_order", label: "工单明细" }
] as const;
const REVIEW_TEMPLATE_ENABLED_FIELDS = ["summary", "sla", "duration", "slow_review", "work_order"];
const FULL_TEMPLATE_ENABLED_FIELDS = Object.keys(EXPORT_FIELD_DEFAULTS);
const workOrderStatusFilter = ref<WorkOrderStatus | "">("");
const workOrderAssigneeFilter = ref("");
const workOrderPriorityFilter = ref<"" | "low" | "medium" | "high">("");
const workOrderAlarmKeyword = ref("");
const workOrderTimeFilter = ref<"" | "today" | "7d">("");
const slaOverview = ref<SlaOverview>({
  total_open: 0,
  escalated_open: 0,
  overdue_open: 0,
  acknowledged_today: 0,
  avg_ack_minutes_today: 0
});
const backendLevelDistribution = ref<Array<{ level: string; count: number }>>([]);
const backendTypeDistribution = ref<Array<{ type: string; count: number }>>([]);
const backendOrgDistribution = ref<Array<{ organizationId: string; count: number }>>([]);

function parseAlarmDate(item: AlarmItem) {
  const raw = item.created_at || item.time || "";
  if (!raw) return null;
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return null;
  return d;
}

const hourlyTrend = computed(() => {
  const now = new Date();
  const slots = new Array(24).fill(0).map((_, idx) => {
    const h = (now.getHours() - (23 - idx) + 24) % 24;
    return { label: `${String(h).padStart(2, "0")}h`, count: 0 };
  });
  filteredAlarms.value.forEach((item) => {
    const d = parseAlarmDate(item);
    if (!d) return;
    const diff = now.getTime() - d.getTime();
    if (diff < 0 || diff > 24 * 60 * 60 * 1000) return;
    const hourGap = Math.floor(diff / (60 * 60 * 1000));
    const index = 23 - hourGap;
    if (index >= 0 && index < 24) slots[index].count += 1;
  });
  return slots;
});

const filteredAlarms = computed(() => {
  return alarms.value.filter((item) => {
    const typeMatched = !selectedAlarmType.value || (item.alarm_type || "unknown") === selectedAlarmType.value;
    const org = organizationMap.value[String(item.device_id || "")] || "未分组";
    const orgMatched = !selectedOrganization.value || org === selectedOrganization.value;
    const slowMatched = !selectedSlowAlarmId.value || String(item.id || "") === selectedSlowAlarmId.value;
    const presetMatched =
      alarmQuickPreset.value === "all" ||
      (alarmQuickPreset.value === "high" && Number(item.priority ?? item.escalation_level ?? 0) >= 8) ||
      (alarmQuickPreset.value === "unacked" && item.escalation_state !== "acknowledged");
    return typeMatched && orgMatched && slowMatched && presetMatched;
  });
});

const alarmListSummaryText = computed(() => {
  const presetLabel = alarmQuickPreset.value === "high" ? "高优" : alarmQuickPreset.value === "unacked" ? "未确认" : "全部";
  return `告警列表：总量=${alarms.value.length}；筛选命中=${filteredAlarms.value.length}；快捷预设=${presetLabel}；下钻=${selectedSlowAlarmId.value ? "已启用" : "未启用"}`;
});

const alarmListFilterHitRateText = computed(() => {
  const totalCount = alarms.value.length;
  const hit = filteredAlarms.value.length;
  const rate = totalCount <= 0 ? 0 : Number(((hit / totalCount) * 100).toFixed(2));
  return `筛选命中率：${rate}%（${hit}/${totalCount}）`;
});

const alarmListRiskSummaryText = computed(() => {
  const totalCount = filteredAlarms.value.length;
  const unacked = filteredAlarms.value.filter((x) => x.escalation_state !== "acknowledged").length;
  const highPriority = filteredAlarms.value.filter((x) => Number(x.priority ?? x.escalation_level ?? 0) >= 8).length;
  const highRate = totalCount <= 0 ? 0 : Number(((highPriority / totalCount) * 100).toFixed(2));
  return `处置压力：未确认=${unacked}；高优=${highPriority}；高优占比=${highRate}%`;
});

const alarmListNextStepAdviceText = computed(() => {
  const unacked = filteredAlarms.value.filter((x) => x.escalation_state !== "acknowledged").length;
  const highPriority = filteredAlarms.value.filter((x) => Number(x.priority ?? x.escalation_level ?? 0) >= 8).length;
  if (highPriority > 0) return "下一步建议：优先处理高优未确认告警，再执行联动回放与指挥追踪。";
  if (unacked > 0) return "下一步建议：先完成未确认告警的快速确认，避免积压。";
  return "下一步建议：当前筛选结果压力较低，保持巡检与抽样复核。";
});

const alarmQuickPresetLabelText = computed(() => {
  if (alarmQuickPreset.value === "high") return "高优";
  if (alarmQuickPreset.value === "unacked") return "未确认";
  return "全部";
});

function alarmQuickPresetLabelByValue(preset: "all" | "high" | "unacked") {
  if (preset === "high") return "高优";
  if (preset === "unacked") return "未确认";
  return "全部";
}

const alarmSelectedOrganizationLabel = computed(() => {
  if (!selectedOrganization.value) return "全部组织";
  return organizationOptions.value.find((x) => x.value === selectedOrganization.value)?.label || selectedOrganization.value;
});

const alarmFilterSnapshotText = computed(() => {
  return [
    `筛选快照：类型=${selectedAlarmType.value || "全部类型"}`,
    `组织=${alarmSelectedOrganizationLabel.value}`,
    `快捷预设=${alarmQuickPresetLabelText.value}`,
    `下钻=${selectedSlowAlarmId.value || "未启用"}`
  ].join("；");
});

const alarmSavedSnapshotText = computed(() => {
  const latest = alarmFilterSnapshotHistory.value[0];
  if (!latest) return "已保存快照：暂无";
  const type = latest.selectedAlarmType || "全部类型";
  const org = latest.selectedOrganizationLabel || latest.selectedOrganization || "全部组织";
  const presetLabel = alarmQuickPresetLabelByValue(latest.alarmQuickPreset);
  const slowId = latest.selectedSlowAlarmId || "未启用";
  const savedAt = latest.savedAt || "";
  return `已保存快照：类型=${type}；组织=${org}；快捷预设=${presetLabel}；下钻=${slowId}${savedAt ? `；时间=${savedAt}` : ""}`;
});

function buildAlarmFilterSnapshotPayload() {
  return {
    selectedAlarmType: selectedAlarmType.value || "",
    selectedOrganization: selectedOrganization.value || "",
    selectedOrganizationLabel: alarmSelectedOrganizationLabel.value,
    alarmQuickPreset: alarmQuickPreset.value,
    selectedSlowAlarmId: selectedSlowAlarmId.value || "",
    savedAt: new Date().toISOString()
  } as AlarmFilterSnapshotRecord;
}

function saveAlarmFilterSnapshot() {
  const payload = buildAlarmFilterSnapshotPayload();
  uni.setStorageSync(ALARM_FILTER_SNAPSHOT_KEY, payload);
  const next = [
    payload,
    ...alarmFilterSnapshotHistory.value.filter(
      (x) =>
        !(
          x.selectedAlarmType === payload.selectedAlarmType &&
          x.selectedOrganization === payload.selectedOrganization &&
          x.alarmQuickPreset === payload.alarmQuickPreset &&
          x.selectedSlowAlarmId === payload.selectedSlowAlarmId
        )
    )
  ].slice(0, 3);
  alarmFilterSnapshotHistory.value = next;
  uni.setStorageSync(ALARM_FILTER_SNAPSHOT_HISTORY_KEY, next);
  uni.showToast({ title: "筛选快照已保存", icon: "none" });
}

async function restoreAlarmFilterSnapshot() {
  const latest = alarmFilterSnapshotHistory.value[0] || ((uni.getStorageSync(ALARM_FILTER_SNAPSHOT_KEY) || {}) as AlarmFilterSnapshotRecord);
  if (!latest || Object.keys(latest).length === 0) {
    uni.showToast({ title: "暂无已保存快照", icon: "none" });
    return;
  }
  selectedAlarmType.value = latest.selectedAlarmType || "";
  selectedOrganization.value = latest.selectedOrganization || "";
  alarmQuickPreset.value = latest.alarmQuickPreset || "all";
  selectedSlowAlarmId.value = latest.selectedSlowAlarmId || "";
  saveDashboardPrefs();
  await Promise.all([loadCrossDayTrend(), loadDurationMetrics(7)]);
  uni.showToast({ title: "筛选快照已还原", icon: "none" });
}

async function restoreAlarmFilterSnapshotByIndex(index: number) {
  const row = alarmFilterSnapshotHistory.value[index];
  if (!row) {
    uni.showToast({ title: "该快照不存在", icon: "none" });
    return;
  }
  selectedAlarmType.value = row.selectedAlarmType || "";
  selectedOrganization.value = row.selectedOrganization || "";
  alarmQuickPreset.value = row.alarmQuickPreset || "all";
  selectedSlowAlarmId.value = row.selectedSlowAlarmId || "";
  const reordered = [row, ...alarmFilterSnapshotHistory.value.filter((_, idx) => idx !== index)].slice(0, 3);
  alarmFilterSnapshotHistory.value = reordered;
  uni.setStorageSync(ALARM_FILTER_SNAPSHOT_HISTORY_KEY, reordered);
  uni.setStorageSync(ALARM_FILTER_SNAPSHOT_KEY, row);
  saveDashboardPrefs();
  await Promise.all([loadCrossDayTrend(), loadDurationMetrics(7)]);
  uni.showToast({ title: "已还原选中快照", icon: "none" });
}

function clearAlarmFilterSnapshotHistory() {
  alarmFilterSnapshotHistory.value = [];
  uni.removeStorageSync(ALARM_FILTER_SNAPSHOT_HISTORY_KEY);
  uni.removeStorageSync(ALARM_FILTER_SNAPSHOT_KEY);
  uni.showToast({ title: "快照历史已清空", icon: "none" });
}

function exportAlarmFilterSnapshotHistoryJson() {
  const payload = {
    version: "alarm_filter_snapshot_v1",
    exported_at: new Date().toISOString(),
    total: alarmFilterSnapshotHistory.value.length,
    items: alarmFilterSnapshotHistory.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => uni.showToast({ title: "快照历史JSON已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function toggleImportAlarmFilterSnapshotPanel() {
  importSnapshotInputVisible.value = !importSnapshotInputVisible.value;
  if (!importSnapshotInputVisible.value) importSnapshotJsonText.value = "";
}

function importAlarmFilterSnapshotHistoryJson() {
  const raw = String(importSnapshotJsonText.value || "").trim();
  if (!raw) {
    uni.showToast({ title: "请先粘贴JSON", icon: "none" });
    return;
  }
  try {
    const parsed = JSON.parse(raw) as { items?: Array<Record<string, unknown>> };
    const items = Array.isArray(parsed.items) ? parsed.items : [];
    const next = items
      .map((x) => ({
        selectedAlarmType: String(x.selectedAlarmType || ""),
        selectedOrganization: String(x.selectedOrganization || ""),
        selectedOrganizationLabel: String(x.selectedOrganizationLabel || ""),
        alarmQuickPreset:
          String(x.alarmQuickPreset || "") === "high" || String(x.alarmQuickPreset || "") === "unacked"
            ? (String(x.alarmQuickPreset) as "high" | "unacked")
            : "all",
        selectedSlowAlarmId: String(x.selectedSlowAlarmId || ""),
        savedAt: String(x.savedAt || "")
      }))
      .filter((x) => !!x.savedAt)
      .slice(0, 3);
    if (!next.length) {
      uni.showToast({ title: "JSON中无有效快照", icon: "none" });
      return;
    }
    alarmFilterSnapshotHistory.value = next;
    uni.setStorageSync(ALARM_FILTER_SNAPSHOT_HISTORY_KEY, next);
    uni.setStorageSync(ALARM_FILTER_SNAPSHOT_KEY, next[0]);
    importSnapshotInputVisible.value = false;
    importSnapshotJsonText.value = "";
    uni.showToast({ title: "快照历史已导入", icon: "none" });
  } catch {
    uni.showToast({ title: "JSON格式错误", icon: "none" });
  }
}

function copyAlarmListOverviewSummary() {
  const text = [
    alarmListSummaryText.value,
    alarmListFilterHitRateText.value,
    alarmListRiskSummaryText.value,
    alarmListNextStepAdviceText.value,
    alarmFilterSnapshotText.value
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "列表概览摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyAlarmFilterSnapshot() {
  uni.setClipboardData({
    data: alarmFilterSnapshotText.value,
    success: () => uni.showToast({ title: "筛选快照已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

const alarmScopeIdSet = computed(() => {
  return new Set(filteredAlarms.value.map((item) => String(item.id || "")).filter(Boolean));
});

const hasAlarmScope = computed(() => {
  return !!(selectedAlarmType.value || selectedOrganization.value || selectedSlowAlarmId.value || alarmQuickPreset.value !== "all");
});

const levelDistribution = computed(() => {
  if (backendLevelDistribution.value.length > 0) return backendLevelDistribution.value;
  const map: Record<string, number> = {};
  filteredAlarms.value.forEach((item) => {
    const key = (item.level || "normal").toLowerCase();
    map[key] = (map[key] || 0) + 1;
  });
  return Object.entries(map)
    .map(([level, count]) => ({ level, count }))
    .sort((a, b) => b.count - a.count);
});

const topDevices = computed(() => {
  const map: Record<string, number> = {};
  filteredAlarms.value.forEach((item) => {
    const key = String(item.device_id || "unknown");
    map[key] = (map[key] || 0) + 1;
  });
  return Object.entries(map)
    .map(([deviceId, count]) => ({ deviceId, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 5);
});

const alarmTypeDistribution = computed(() => {
  if (backendTypeDistribution.value.length > 0) return backendTypeDistribution.value;
  const map: Record<string, number> = {};
  filteredAlarms.value.forEach((item) => {
    const key = String(item.alarm_type || "unknown").toLowerCase();
    map[key] = (map[key] || 0) + 1;
  });
  return Object.entries(map)
    .map(([type, count]) => ({ type, count }))
    .sort((a, b) => b.count - a.count);
});

const assigneeDistribution = computed(() => {
  const map: Record<string, number> = {};
  workOrders.value.forEach((item) => {
    const key = item.assignee_user_id || item.created_by_user_id || "未指派";
    map[key] = (map[key] || 0) + 1;
  });
  return Object.entries(map)
    .map(([userId, count]) => ({ userId, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 8);
});

const assigneeChartData = computed(() => {
  return assigneeDistribution.value.map((row) => ({
    label: userNameMap.value[row.userId] || row.userId,
    value: row.count
  }));
});

const workOrderStatusStats = computed(() => {
  const stats: Record<WorkOrderStatus, number> = {
    open: 0,
    in_progress: 0,
    resolved: 0,
    closed: 0
  };
  workOrders.value.forEach((item) => {
    if (item.status in stats) stats[item.status as WorkOrderStatus] += 1;
  });
  return stats;
});

const workOrderStatusChartData = computed(() => [
  { label: "待处理", value: workOrderStatusStats.value.open, key: "open" },
  { label: "处理中", value: workOrderStatusStats.value.in_progress, key: "in_progress" },
  { label: "已解决", value: workOrderStatusStats.value.resolved, key: "resolved" },
  { label: "已关闭", value: workOrderStatusStats.value.closed, key: "closed" }
]);

const workOrderReturnEvents24h = computed(() => {
  const now = Date.now();
  return workOrderReturnEvents.value.filter((item) => {
    const t = new Date(item.at).getTime();
    return !Number.isNaN(t) && now - t <= 24 * 60 * 60 * 1000;
  });
});

const workOrderReturnStatusStats24h = computed(() => {
  const stats: Record<WorkOrderStatus, number> = {
    open: 0,
    in_progress: 0,
    resolved: 0,
    closed: 0
  };
  workOrderReturnEvents24h.value.forEach((item) => {
    if (item.toStatus && item.toStatus in stats) {
      stats[item.toStatus as WorkOrderStatus] += 1;
    }
  });
  return stats;
});

const workOrderReturnChangedCount24h = computed(() => {
  return workOrderReturnEvents24h.value.filter((item) => !!item.fromStatus && !!item.toStatus && item.fromStatus !== item.toStatus).length;
});

const scopedWorkOrders = computed(() => {
  return workOrders.value.filter((item) => {
    if (!hasAlarmScope.value) return true;
    const alarmId = String(item.alarm_id || "");
    return !!alarmId && alarmScopeIdSet.value.has(alarmId);
  });
});

const filteredWorkOrders = computed(() => {
  return scopedWorkOrders.value.filter((item) => {
    const statusMatched = !workOrderStatusFilter.value || item.status === workOrderStatusFilter.value;
    const assignee = item.assignee_user_id || item.created_by_user_id || "未指派";
    const assigneeMatched = !workOrderAssigneeFilter.value || assignee === workOrderAssigneeFilter.value;
    const priorityMatched = !workOrderPriorityFilter.value || (item.priority || "medium") === workOrderPriorityFilter.value;
    const alarmMatched =
      !workOrderAlarmKeyword.value ||
      String(item.alarm_id || "")
        .toLowerCase()
        .includes(workOrderAlarmKeyword.value.toLowerCase());
    const createdAt = item.created_at ? new Date(item.created_at) : null;
    const now = Date.now();
    const timeMatched =
      !workOrderTimeFilter.value ||
      (workOrderTimeFilter.value === "today" &&
        createdAt !== null &&
        now - createdAt.getTime() <= 24 * 60 * 60 * 1000) ||
      (workOrderTimeFilter.value === "7d" &&
        createdAt !== null &&
        now - createdAt.getTime() <= 7 * 24 * 60 * 60 * 1000);
    return statusMatched && assigneeMatched && priorityMatched && alarmMatched && timeMatched;
  });
});

const workOrderAssigneeOptions = computed(() => {
  const set = new Set<string>();
  scopedWorkOrders.value.forEach((item) => {
    set.add(item.assignee_user_id || item.created_by_user_id || "未指派");
  });
  return [
    { label: "全部人员", value: "" },
    ...Array.from(set)
      .sort((a, b) => (userNameMap.value[a] || a).localeCompare(userNameMap.value[b] || b))
      .map((id) => ({ label: userNameMap.value[id] || id, value: id }))
  ];
});

const workOrderPriorityOptions = [
  { label: "全部优先级", value: "" },
  { label: "高", value: "high" },
  { label: "中", value: "medium" },
  { label: "低", value: "low" }
] as const;

const organizationDistribution = computed(() => {
  if (backendOrgDistribution.value.length > 0) return backendOrgDistribution.value;
  const map: Record<string, number> = {};
  filteredAlarms.value.forEach((item) => {
    const orgId = organizationMap.value[String(item.device_id || "")] || "未分组";
    map[orgId] = (map[orgId] || 0) + 1;
  });
  return Object.entries(map)
    .map(([organizationId, count]) => ({ organizationId, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 8);
});

const organizationChartData = computed(() => {
  return organizationDistribution.value.map((row) => ({
    label: organizationDisplayName(row.organizationId),
    value: row.count,
    key: row.organizationId
  }));
});

const crossDayChartData = computed(() => crossDayTrend.value.map((x) => ({ label: x.label, value: x.count })));
const hourlyChartData = computed(() => hourlyTrend.value.map((x) => ({ label: x.label, value: x.count })));
const levelChartData = computed(() => levelDistribution.value.map((x) => ({ label: x.level, value: x.count })));
const alarmTypeChartData = computed(() => alarmTypeDistribution.value.map((x) => ({ label: x.type, value: x.count, key: x.type })));
const topDeviceChartData = computed(() => topDevices.value.map((x) => ({ label: x.deviceId, value: x.count })));

function organizationDisplayName(idOrEmpty: string) {
  if (!idOrEmpty) return "全部组织";
  if (idOrEmpty === "未分组") return "未分组";
  return organizationNameMap.value[idOrEmpty] || idOrEmpty;
}

function levelColor(level?: string) {
  const l = (level || "").toLowerCase();
  if (l.includes("high") || l.includes("critical")) return "#EF4444";
  if (l.includes("medium")) return "#F59E0B";
  return "#10B981";
}

function calcChangePct(currentValue: number, previousValue: number) {
  if (previousValue <= 0) return currentValue > 0 ? 100 : 0;
  return Number((((currentValue - previousValue) / previousValue) * 100).toFixed(2));
}

const compareSummary = computed(() => {
  if (compareMode.value === "day") {
    return {
      title: "环比（24h）",
      current: compareMetrics.value.dayCurrent,
      previous: compareMetrics.value.dayPrevious,
      pct: compareMetrics.value.dayChangePct
    };
  }
  return {
    title: `同比（${trendDays.value}天）`,
    current: compareMetrics.value.periodCurrent,
    previous: compareMetrics.value.periodPrevious,
    pct: compareMetrics.value.periodChangePct
  };
});

watch(
  [
    compareMode,
    trendDays,
    exportTemplate,
    reviewExportWindowFilter,
    reviewExportWindowActionAuditFilter,
    reviewExportWindowActionAuditPresetHistoryFilter,
    reviewExportWindowActionAuditPresetHistoryActionAuditFilter,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryFilter,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter
  ],
  () => {
    saveDashboardPrefs();
  }
);

watch(
  exportFields,
  () => {
    saveDashboardPrefs();
  },
  { deep: true }
);

function saveDashboardPrefs() {
  uni.setStorageSync(DASHBOARD_PREF_KEY, {
    compareMode: compareMode.value,
    trendDays: trendDays.value,
    selectedAlarmType: selectedAlarmType.value,
    selectedOrganization: selectedOrganization.value,
    alarmQuickPreset: alarmQuickPreset.value,
    exportTemplate: exportTemplate.value,
    exportFields: exportFields.value,
    reviewExportWindowFilter: reviewExportWindowFilter.value,
    reviewExportWindowActionAuditFilter: reviewExportWindowActionAuditFilter.value,
    reviewExportWindowActionAuditPresetHistoryFilter: reviewExportWindowActionAuditPresetHistoryFilter.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditFilter: reviewExportWindowActionAuditPresetHistoryActionAuditFilter.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryFilter:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryFilter.value
    ,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value
  });
}

function savePresets() {
  uni.setStorageSync(DASHBOARD_PRESETS_KEY, exportPresets.value);
}

function buildDispatchRuleCenterSnapshot(): DispatchRuleCenterSnapshot {
  return {
    rules: {
      preset: dispatchRules.value.preset,
      muteHttp4xxAlerts: !!dispatchRules.value.muteHttp4xxAlerts,
      promoteNetworkToError: !!dispatchRules.value.promoteNetworkToError
    },
    presets: dispatchRulePresets.value
      .filter((x) => (x.name || "").trim())
      .slice(0, 30)
      .map((x) => ({
        name: String(x.name || "").trim().slice(0, 40),
        muteHttp4xxAlerts: !!x.muteHttp4xxAlerts,
        promoteNetworkToError: !!x.promoteNetworkToError
      }))
  };
}

function normalizeDispatchRuleCenterSnapshot(snapshot: DispatchRuleCenterSnapshot): DispatchRuleCenterSnapshot {
  return {
    rules: {
      preset: snapshot.rules.preset || "custom",
      muteHttp4xxAlerts: !!snapshot.rules.muteHttp4xxAlerts,
      promoteNetworkToError: !!snapshot.rules.promoteNetworkToError
    },
    presets: [...(snapshot.presets || [])]
      .map((x) => ({
        name: String(x.name || "").trim().slice(0, 40),
        muteHttp4xxAlerts: !!x.muteHttp4xxAlerts,
        promoteNetworkToError: !!x.promoteNetworkToError
      }))
      .filter((x) => !!x.name)
      .sort((a, b) => a.name.localeCompare(b.name))
  };
}

function dispatchRuleCenterDigest(snapshot: DispatchRuleCenterSnapshot) {
  return JSON.stringify(normalizeDispatchRuleCenterSnapshot(snapshot));
}

function saveDispatchRuleAudits() {
  uni.setStorageSync(REVIEW_DISPATCH_RULE_AUDITS_KEY, dispatchRuleAudits.value.slice(0, 30));
}

function pushDispatchRuleAudit(
  source: DispatchRuleAuditItem["source"],
  message: string,
  snapshot: DispatchRuleCenterSnapshot = buildDispatchRuleCenterSnapshot()
) {
  const now = new Date().toISOString();
  dispatchRuleAudits.value = [
    {
      id: `${now}-${Math.random().toString(36).slice(2, 8)}`,
      at: now,
      source,
      message,
      snapshot: normalizeDispatchRuleCenterSnapshot(snapshot)
    },
    ...dispatchRuleAudits.value
  ].slice(0, 30);
  saveDispatchRuleAudits();
}

function dispatchRuleAuditSourceText(source: DispatchRuleAuditItem["source"]) {
  if (source === "template") return "模板切换";
  if (source === "toggle") return "规则开关";
  if (source === "named_preset_save") return "命名策略保存";
  if (source === "named_preset_apply") return "命名策略应用";
  if (source === "named_preset_remove") return "命名策略删除";
  if (source === "conflict_resolve_server") return "冲突处置(服务端)";
  if (source === "conflict_resolve_local") return "冲突处置(本地覆盖)";
  return "审计回滚";
}

function buildDispatchRuleCenterPreset(): AlarmDashboardPresetItem {
  const center = buildDispatchRuleCenterSnapshot();
  return {
    name: DISPATCH_RULE_CENTER_PRESET_NAME,
    config: {
      dispatchRules: center.rules,
      dispatchRulePresets: center.presets
    }
  };
}

function parseServerPresetItems(items: AlarmDashboardPresetItem[]) {
  const valid = (items || []).filter((x) => (x.name || "").trim());
  const center = valid.find((x) => x.name === DISPATCH_RULE_CENTER_PRESET_NAME);
  const displayItems = valid.filter((x) => x.name !== DISPATCH_RULE_CENTER_PRESET_NAME);
  return { displayItems, center };
}

function snapshotFromDispatchRuleCenterPreset(center?: AlarmDashboardPresetItem): DispatchRuleCenterSnapshot | null {
  if (!center || typeof center.config !== "object" || !center.config) return null;
  const cfg = center.config as Record<string, unknown>;
  const rules = (cfg.dispatchRules || {}) as Record<string, unknown>;
  const presets = Array.isArray(cfg.dispatchRulePresets) ? cfg.dispatchRulePresets : [];
  return {
    rules: {
      preset: String(rules.preset || "custom") as "strict" | "balanced" | "noise_reduction" | "custom",
      muteHttp4xxAlerts: Boolean(rules.muteHttp4xxAlerts),
      promoteNetworkToError: Boolean(rules.promoteNetworkToError)
    },
    presets: presets
      .map((x) => x as Record<string, unknown>)
      .filter((x) => String(x.name || "").trim())
      .slice(0, 30)
      .map((x) => ({
        name: String(x.name || "").trim().slice(0, 40),
        muteHttp4xxAlerts: Boolean(x.muteHttp4xxAlerts),
        promoteNetworkToError: Boolean(x.promoteNetworkToError)
      }))
  };
}

function applyDispatchRuleSnapshot(snapshot: DispatchRuleCenterSnapshot, source: "server" | "local", message: string) {
  const nextRules = {
    preset: String(snapshot.rules.preset || dispatchRules.value.preset || "custom") as "strict" | "balanced" | "noise_reduction" | "custom",
    muteHttp4xxAlerts: Boolean(snapshot.rules.muteHttp4xxAlerts),
    promoteNetworkToError: Boolean(snapshot.rules.promoteNetworkToError)
  };
  dispatchRules.value = nextRules;
  dispatchRulePresets.value = snapshot.presets
    .slice(0, 30)
    .map((x) => ({
      name: String(x.name || "").trim().slice(0, 40),
      muteHttp4xxAlerts: !!x.muteHttp4xxAlerts,
      promoteNetworkToError: !!x.promoteNetworkToError
    }));
  uni.setStorageSync(REVIEW_DISPATCH_RULES_KEY, {
    preset: dispatchRules.value.preset || "custom",
    muteHttp4xxAlerts: !!dispatchRules.value.muteHttp4xxAlerts,
    promoteNetworkToError: !!dispatchRules.value.promoteNetworkToError
  });
  uni.setStorageSync(REVIEW_DISPATCH_RULE_PRESETS_KEY, dispatchRulePresets.value.slice(0, 30));
  dispatchRuleSyncMeta.value = {
    source,
    lastSyncAt: new Date().toISOString(),
    lastSyncStatus: "success",
    lastSyncMessage: message
  };
  saveDispatchRuleSyncMeta();
}

function applyDispatchRuleCenterFromPreset(center?: AlarmDashboardPresetItem) {
  const snapshot = snapshotFromDispatchRuleCenterPreset(center);
  if (!snapshot) return;
  applyDispatchRuleSnapshot(snapshot, "server", "已从服务端同步通知策略");
}

function resolveDispatchRuleConflictUseServer() {
  const serverSnapshot = dispatchRuleConflict.value.serverSnapshot;
  if (!serverSnapshot) return;
  applyDispatchRuleSnapshot(serverSnapshot, "server", "冲突已按服务端策略解决");
  pushDispatchRuleAudit("conflict_resolve_server", "冲突处置：以服务端为准", serverSnapshot);
  dispatchRuleConflict.value = {
    hasConflict: false,
    detectedAt: "",
    message: "",
    localSnapshot: null,
    serverSnapshot: null
  };
  saveDispatchRuleConflict();
  uni.showToast({ title: "已按服务端策略处理冲突", icon: "none" });
}

async function resolveDispatchRuleConflictUseLocal() {
  if (!presetWritable.value) {
    uni.showToast({ title: "当前账号无策略回滚写权限", icon: "none" });
    return;
  }
  const localSnapshot = dispatchRuleConflict.value.localSnapshot;
  if (!localSnapshot) return;
  applyDispatchRuleSnapshot(localSnapshot, "local", "冲突已按本地策略覆盖");
  pushDispatchRuleAudit("conflict_resolve_local", "冲突处置：以本地覆盖服务端", localSnapshot);
  await syncPresetsToServer();
  dispatchRuleConflict.value = {
    hasConflict: false,
    detectedAt: "",
    message: "",
    localSnapshot: null,
    serverSnapshot: null
  };
  saveDispatchRuleConflict();
  uni.showToast({ title: "已按本地策略覆盖服务端", icon: "none" });
}

async function syncPresetsToServer() {
  try {
    const payloadItems = [...exportPresets.value, buildDispatchRuleCenterPreset()];
    const saved = await saveSlaPresets(payloadItems);
    const { displayItems, center } = parseServerPresetItems(saved.items || []);
    exportPresets.value = displayItems;
    applyDispatchRuleCenterFromPreset(center);
    dispatchRuleConflict.value = {
      hasConflict: false,
      detectedAt: "",
      message: "",
      localSnapshot: null,
      serverSnapshot: null
    };
    saveDispatchRuleConflict();
    dispatchRuleSyncMeta.value = {
      source: "server",
      lastSyncAt: new Date().toISOString(),
      lastSyncStatus: "success",
      lastSyncMessage: "已同步到服务端"
    };
    saveDispatchRuleSyncMeta();
    savePresets();
    loadPresetAudits().catch(() => undefined);
  } catch {
    dispatchRuleSyncMeta.value = {
      source: "local",
      lastSyncAt: new Date().toISOString(),
      lastSyncStatus: "failed",
      lastSyncMessage: "服务端同步失败，已保留本地策略"
    };
    saveDispatchRuleSyncMeta();
    // 无权限或旧后端，保持本地兜底
  }
}

async function loadPresetsFromServer() {
  try {
    const res = await fetchSlaPresets();
    presetWritable.value = res.writable !== false;
    const { displayItems, center } = parseServerPresetItems(res.items || []);
    if (displayItems.length > 0) {
      exportPresets.value = displayItems;
      savePresets();
    }
    const serverSnapshot = snapshotFromDispatchRuleCenterPreset(center);
    const localSnapshot = buildDispatchRuleCenterSnapshot();
    if (serverSnapshot) {
      const localDigest = dispatchRuleCenterDigest(localSnapshot);
      const serverDigest = dispatchRuleCenterDigest(serverSnapshot);
      if (localDigest !== serverDigest) {
        dispatchRuleConflict.value = {
          hasConflict: true,
          detectedAt: new Date().toISOString(),
          message: "检测到本地与服务端通知策略不一致，请选择处置方式",
          localSnapshot,
          serverSnapshot
        };
        saveDispatchRuleConflict();
      } else {
        dispatchRuleConflict.value = {
          hasConflict: false,
          detectedAt: "",
          message: "",
          localSnapshot: null,
          serverSnapshot: null
        };
        saveDispatchRuleConflict();
      }
    }
    applyDispatchRuleCenterFromPreset(center);
    if (!center) {
      dispatchRuleSyncMeta.value = {
        source: "local",
        lastSyncAt: new Date().toISOString(),
        lastSyncStatus: "success",
        lastSyncMessage: "服务端暂无策略中心，使用本地策略"
      };
      saveDispatchRuleSyncMeta();
    }
  } catch {
    // 旧后端不支持时保留本地预设
    presetWritable.value = true;
    dispatchRuleSyncMeta.value = {
      source: "local",
      lastSyncAt: new Date().toISOString(),
      lastSyncStatus: "failed",
      lastSyncMessage: "拉取服务端策略失败，使用本地策略"
    };
    saveDispatchRuleSyncMeta();
  }
}

async function manualSyncDispatchRuleCenter() {
  await syncPresetsToServer();
  uni.showToast({ title: "已执行策略同步", icon: "none" });
}

async function loadPresetAudits() {
  presetAuditLoading.value = true;
  try {
    presetAudits.value = await fetchSlaPresetAudits(10);
  } catch {
    // owner/admin 之外用户可能无权限读取审计记录
    presetAudits.value = [];
  } finally {
    presetAuditLoading.value = false;
  }
}

async function loadAlarms() {
  loading.value = true;
  try {
    const res = await fetchAlarms();
    alarms.value = res.items || [];
    const typeSet = new Set<string>();
    alarms.value.forEach((item) => {
      typeSet.add(item.alarm_type || "unknown");
    });
    alarmTypeOptions.value = ["全部类型", ...Array.from(typeSet).sort((a, b) => a.localeCompare(b))];
    if (selectedAlarmType.value && !alarmTypeOptions.value.includes(selectedAlarmType.value)) {
      selectedAlarmType.value = "";
    }
    setAlarmPageActionStatus(`告警加载成功：共 ${alarms.value.length} 条`);
  } catch (err: any) {
    const reason = String(err?.message || "请稍后重试");
    setAlarmPageActionStatus(`告警加载失败：${reason}`);
    uni.showToast({ title: "告警加载失败", icon: "none" });
    throw err;
  } finally {
    loading.value = false;
  }
}

async function loadWorkOrders() {
  workOrderLoading.value = true;
  try {
    workOrders.value = await listWorkOrders();
    setAlarmPageActionStatus(`工单加载成功：共 ${workOrders.value.length} 条`);
  } catch (err: any) {
    const reason = String(err?.message || "请稍后重试");
    setAlarmPageActionStatus(`工单加载失败：${reason}`);
    uni.showToast({ title: "工单加载失败", icon: "none" });
    throw err;
  } finally {
    workOrderLoading.value = false;
  }
}

function toIsoString(date: Date) {
  return date.toISOString();
}

async function loadCrossDayTrend(days = trendDays.value) {
  trendLoading.value = true;
  try {
    const end = new Date();
    const start = new Date(end.getTime() - (days * 24 - 1) * 60 * 60 * 1000);
    const currentRes = await fetchAlarms({
      skip: 0,
      limit: 200,
      start_time: toIsoString(start),
      end_time: toIsoString(end)
    });
    const dayEnd = new Date(end.getTime() - 24 * 60 * 60 * 1000);
    const source = currentRes.items || [];
    const byDay: Record<string, number> = {};
    const labels: string[] = [];
    for (let i = days - 1; i >= 0; i -= 1) {
      const day = new Date(end.getTime() - i * 24 * 60 * 60 * 1000);
      const key = `${day.getMonth() + 1}/${day.getDate()}`;
      labels.push(key);
      byDay[key] = 0;
    }
    source
      .filter((item) => {
        const typeMatched = !selectedAlarmType.value || (item.alarm_type || "unknown") === selectedAlarmType.value;
        const org = organizationMap.value[String(item.device_id || "")] || "未分组";
        const orgMatched = !selectedOrganization.value || org === selectedOrganization.value;
        return typeMatched && orgMatched;
      })
      .forEach((item) => {
      const d = parseAlarmDate(item);
      if (!d) return;
      const key = `${d.getMonth() + 1}/${d.getDate()}`;
      if (typeof byDay[key] === "number") byDay[key] += 1;
      });
    crossDayTrend.value = labels.map((label) => ({ label, count: byDay[label] || 0 }));

    try {
      const orgParam = selectedOrganization.value === "未分组" ? "__ungrouped__" : selectedOrganization.value;
      const cmp = await fetchSlaCompare(days, selectedAlarmType.value, orgParam);
      compareMetrics.value = {
        periodCurrent: cmp.period_current,
        periodPrevious: cmp.period_previous,
        periodChangePct: cmp.period_change_pct,
        dayCurrent: cmp.day_current,
        dayPrevious: cmp.day_previous,
        dayChangePct: cmp.day_change_pct
      };
    } catch {
      // 兼容旧后端：没有 compare 接口时走前端本地统计
      const previousEnd = new Date(start.getTime() - 1);
      const previousStart = new Date(previousEnd.getTime() - (days * 24 - 1) * 60 * 60 * 1000);
      const previousRes = await fetchAlarms({
        skip: 0,
        limit: 200,
        start_time: toIsoString(previousStart),
        end_time: toIsoString(previousEnd)
      });
      const dayStart = new Date(dayEnd.getTime() - 24 * 60 * 60 * 1000);
      const dayPreviousRes = await fetchAlarms({
        skip: 0,
        limit: 200,
        start_time: toIsoString(dayStart),
        end_time: toIsoString(dayEnd)
      });
      const dayCurrentRes = await fetchAlarms({
        skip: 0,
        limit: 200,
        start_time: toIsoString(dayEnd),
        end_time: toIsoString(end)
      });
      const previousCount = (previousRes.items || []).filter((item) => {
        const typeMatched = !selectedAlarmType.value || (item.alarm_type || "unknown") === selectedAlarmType.value;
        const org = organizationMap.value[String(item.device_id || "")] || "未分组";
        const orgMatched = !selectedOrganization.value || org === selectedOrganization.value;
        return typeMatched && orgMatched;
      }).length;
      const dayPreviousCount = (dayPreviousRes.items || []).filter((item) => {
        const typeMatched = !selectedAlarmType.value || (item.alarm_type || "unknown") === selectedAlarmType.value;
        const org = organizationMap.value[String(item.device_id || "")] || "未分组";
        const orgMatched = !selectedOrganization.value || org === selectedOrganization.value;
        return typeMatched && orgMatched;
      }).length;
      const currentCount = source.filter((item) => {
        const typeMatched = !selectedAlarmType.value || (item.alarm_type || "unknown") === selectedAlarmType.value;
        const org = organizationMap.value[String(item.device_id || "")] || "未分组";
        const orgMatched = !selectedOrganization.value || org === selectedOrganization.value;
        return typeMatched && orgMatched;
      }).length;
      const dayCurrentCount = (dayCurrentRes.items || []).filter((item) => {
        const typeMatched = !selectedAlarmType.value || (item.alarm_type || "unknown") === selectedAlarmType.value;
        const org = organizationMap.value[String(item.device_id || "")] || "未分组";
        const orgMatched = !selectedOrganization.value || org === selectedOrganization.value;
        return typeMatched && orgMatched;
      }).length;
      compareMetrics.value = {
        periodCurrent: currentCount,
        periodPrevious: previousCount,
        periodChangePct: calcChangePct(currentCount, previousCount),
        dayCurrent: dayCurrentCount,
        dayPrevious: dayPreviousCount,
        dayChangePct: calcChangePct(dayCurrentCount, dayPreviousCount)
      };
    }
  } finally {
    trendLoading.value = false;
  }
}

async function loadDeviceOrganizations() {
  try {
    const [deviceRes, orgRows] = await Promise.all([fetchDevices(), listOrganizations()]);
    const map: Record<string, string> = {};
    (deviceRes.items || []).forEach((item) => {
      map[item.gb_id] = item.organization_id || "未分组";
    });
    organizationMap.value = map;
    const orgName: Record<string, string> = {};
    (orgRows || []).forEach((org) => {
      orgName[org.id] = org.name || org.id;
    });
    organizationNameMap.value = orgName;
    const orgSet = new Set<string>(Object.values(map));
    organizationOptions.value = [
      { label: "全部组织", value: "" },
      ...Array.from(orgSet)
        .sort((a, b) => organizationDisplayName(a).localeCompare(organizationDisplayName(b)))
        .map((id) => ({ label: organizationDisplayName(id), value: id }))
    ];
    if (selectedOrganization.value && !organizationOptions.value.some((x) => x.value === selectedOrganization.value)) {
      selectedOrganization.value = "";
    }
  } catch {
    organizationMap.value = {};
    organizationNameMap.value = {};
    organizationOptions.value = [{ label: "全部组织", value: "" }];
  }
}

async function loadUsersMap() {
  try {
    const rows = await listUsers(200);
    const map: Record<string, string> = {};
    (rows || []).forEach((u) => {
      map[u.id] = (u.full_name || u.username || u.id).trim();
    });
    userNameMap.value = map;
  } catch {
    // 非超管场景可能没有用户列表权限，降级为 ID 展示
    userNameMap.value = {};
  }
}

function computePercentile(values: number[], p: number) {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const idx = Math.max(0, Math.min(sorted.length - 1, Math.ceil((p / 100) * sorted.length) - 1));
  return Number(sorted[idx].toFixed(2));
}

async function loadDurationMetrics(days = 7) {
  const orgParam = selectedOrganization.value === "未分组" ? "__ungrouped__" : selectedOrganization.value;
  try {
    const quality = await fetchSlaQuality(days, selectedAlarmType.value, orgParam);
    durationMetrics.value = {
      p50: quality.p50_ack_minutes,
      p90: quality.p90_ack_minutes,
      samples: quality.samples
    };
    backendLevelDistribution.value = Object.entries(quality.level_distribution || {})
      .map(([level, count]) => ({ level, count: Number(count || 0) }))
      .sort((a, b) => b.count - a.count);
    backendTypeDistribution.value = Object.entries(quality.alarm_type_distribution || {})
      .map(([type, count]) => ({ type, count: Number(count || 0) }))
      .sort((a, b) => b.count - a.count);
    backendOrgDistribution.value = Object.entries(quality.organization_distribution || {})
      .map(([organizationId, count]) => ({
        organizationId: organizationId === "__ungrouped__" ? "未分组" : organizationId,
        count: Number(count || 0)
      }))
      .sort((a, b) => b.count - a.count);
    slowSamples.value = (quality.slow_samples || []).map((item) => ({
      ...item,
      organization_id: item.organization_id === "__ungrouped__" ? "未分组" : item.organization_id
    }));
    return;
  } catch {
    backendLevelDistribution.value = [];
    backendTypeDistribution.value = [];
    backendOrgDistribution.value = [];
    slowSamples.value = [];
  }
  try {
    const end = new Date();
    const start = new Date(end.getTime() - days * 24 * 60 * 60 * 1000);
    const res = await fetchAlarms({
      skip: 0,
      limit: 200,
      start_time: toIsoString(start),
      end_time: toIsoString(end),
      escalation_state: "acknowledged"
    });
    const durations: number[] = [];
    (res.items || []).forEach((item) => {
      const typeMatched = !selectedAlarmType.value || (item.alarm_type || "unknown") === selectedAlarmType.value;
      const org = organizationMap.value[String(item.device_id || "")] || "未分组";
      const orgMatched = !selectedOrganization.value || org === selectedOrganization.value;
      if (!typeMatched || !orgMatched) return;
      const startAt = parseAlarmDate(item);
      const ackAt = item.ack_at ? new Date(item.ack_at) : null;
      if (!startAt || !ackAt || Number.isNaN(ackAt.getTime())) return;
      const minutes = (ackAt.getTime() - startAt.getTime()) / 60000;
      if (minutes >= 0) durations.push(minutes);
    });
    durationMetrics.value = {
      p50: computePercentile(durations, 50),
      p90: computePercentile(durations, 90),
      samples: durations.length
    };
    slowSamples.value = (res.items || [])
      .map((item) => {
        const startAt = parseAlarmDate(item);
        const ackAt = item.ack_at ? new Date(item.ack_at) : null;
        if (!startAt || !ackAt || Number.isNaN(ackAt.getTime())) return null;
        const minutes = (ackAt.getTime() - startAt.getTime()) / 60000;
        if (minutes < 0) return null;
        const orgId = organizationMap.value[String(item.device_id || "")] || "未分组";
        return {
          alarm_id: String(item.id || ""),
          device_id: item.device_id,
          alarm_type: String(item.alarm_type || "unknown"),
          level: String(item.level || "normal"),
          organization_id: orgId,
          ack_minutes: Number(minutes.toFixed(2)),
          alarm_time: item.created_at || item.time,
          ack_at: item.ack_at
        } as SlaQualitySlowSample;
      })
      .filter((x): x is SlaQualitySlowSample => !!x)
      .sort((a, b) => b.ack_minutes - a.ack_minutes)
      .slice(0, 10);
  } catch {
    durationMetrics.value = { p50: 0, p90: 0, samples: 0 };
    slowSamples.value = [];
  }
}

async function loadSlaOverview() {
  slaLoading.value = true;
  try {
    slaOverview.value = await fetchSlaOverview();
  } finally {
    slaLoading.value = false;
  }
}

async function refreshAll() {
  setAlarmPageActionStatus("告警页刷新中...");
  await loadPresetsFromServer();
  const baseResults = await Promise.allSettled([
    loadAlarms(),
    loadWorkOrders(),
    loadSlaOverview(),
    loadDeviceOrganizations(),
    loadUsersMap(),
    loadPresetAudits()
  ]);
  const trendResults = await Promise.allSettled([loadCrossDayTrend(), loadDurationMetrics(7)]);
  const failed = [...baseResults, ...trendResults].filter((x) => x.status === "rejected").length;
  if (failed <= 0) {
    setAlarmPageActionStatus("告警页刷新成功");
    return;
  }
  setAlarmPageActionStatus(`告警页刷新部分失败：${failed} 项，请重试`);
  uni.showToast({ title: "部分数据刷新失败", icon: "none" });
}

function formatAuditTime(value: string) {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${y}-${m}-${day} ${hh}:${mm}`;
}

async function applySlowSample(sample: SlaQualitySlowSample) {
  selectedSlowAlarmId.value = String(sample.alarm_id || "");
  selectedAlarmType.value = String(sample.alarm_type || "");
  selectedOrganization.value = String(sample.organization_id || "");
  workOrderAlarmKeyword.value = String(sample.alarm_id || "");
  await Promise.all([loadCrossDayTrend(), loadDurationMetrics(7)]);
}

function clearSlowSampleFilter() {
  selectedSlowAlarmId.value = "";
}

function openCommandByAlarmId(alarmId: string) {
  const found = alarms.value.find((x) => String(x.id || "") === alarmId);
  if (found) {
    openCommand(found);
    return;
  }
  uni.showToast({ title: "未找到告警详情，已按ID筛选", icon: "none" });
  selectedSlowAlarmId.value = alarmId;
}

function openRelatedWorkOrderFromSlowSample(sample: SlaQualitySlowSample) {
  const alarmId = String(sample.alarm_id || "");
  if (!alarmId) return;
  const related = workOrders.value.find((wo) => String(wo.alarm_id || "") === alarmId);
  if (related) {
    openWorkOrderDetail(related);
    return;
  }
  workOrderAlarmKeyword.value = alarmId;
  uni.showToast({ title: "未找到关联工单，已按告警ID筛选", icon: "none" });
}

function getRelatedWorkOrder(sample: SlaQualitySlowSample) {
  const alarmId = String(sample.alarm_id || "");
  if (!alarmId) return null;
  return workOrders.value.find((wo) => String(wo.alarm_id || "") === alarmId) || null;
}

function workOrderStatusText(status?: WorkOrderStatus) {
  if (status === "closed") return "已关闭";
  if (status === "resolved") return "已解决";
  if (status === "in_progress") return "处理中";
  if (status === "open") return "待处理";
  return "未派单";
}

function workOrderPriorityText(priority?: "low" | "medium" | "high") {
  if (priority === "high") return "高";
  if (priority === "low") return "低";
  return "中";
}

function workOrderReturnSourceText(source: WorkOrderReturnEventItem["source"]) {
  if (source === "work_order_detail") return "详情回传";
  return "详情回传(全量刷新)";
}

function toMinutesBetween(from?: string, to?: string) {
  if (!from || !to) return null;
  const start = new Date(from);
  const end = new Date(to);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return null;
  const delta = (end.getTime() - start.getTime()) / 60000;
  if (delta < 0) return null;
  return Number(delta.toFixed(2));
}

function getSlowSampleReview(sample: SlaQualitySlowSample) {
  const wo = getRelatedWorkOrder(sample);
  const assigneeId = wo?.assignee_user_id || wo?.created_by_user_id || "";
  const assignee = assigneeId ? (userNameMap.value[assigneeId] || assigneeId) : "未指派";
  const status = workOrderStatusText(wo?.status);
  const priority = wo ? workOrderPriorityText(wo.priority) : "-";
  const alarmToWorkOrderMinutes = toMinutesBetween(sample.alarm_time, wo?.created_at || "");
  return {
    status,
    priority,
    assignee,
    alarmToWorkOrderMinutes,
    hasWorkOrder: !!wo
  };
}

function pickStatus(item: AlarmItem) {
  if (item.escalation_state === "acknowledged") return { text: "已确认", type: "success" as const };
  if (Number(item.escalation_level || 0) > 0) return { text: `已升级 Lv${item.escalation_level}`, type: "warning" as const };
  return { text: "待处理", type: "danger" as const };
}

function alarmStateText(item: AlarmItem) {
  if (item.escalation_state === "acknowledged") return "已确认";
  return "未确认";
}

function alarmPriorityText(item: AlarmItem) {
  const p = Number(item.priority ?? item.escalation_level ?? 0);
  if (p >= 8) return `高优 L${p}`;
  if (p >= 4) return `中优 L${p}`;
  return `低优 L${p}`;
}

function openActions(item: AlarmItem) {
  selectedAlarmId.value = item.id;
  actionNote.value = "";
  dispatchTitle.value = `告警处置-${item.device_id || item.id}`;
  dispatchDesc.value = item.description || "";
}

function openCommand(item: AlarmItem) {
  const q = [
    `deviceId=${encodeURIComponent(String(item.device_id || ""))}`,
    `deviceName=${encodeURIComponent(String(item.device_id || "告警设备"))}`,
    `alarmId=${encodeURIComponent(String(item.id || ""))}`,
    `alarmDesc=${encodeURIComponent(String(item.description || ""))}`,
    "autoCreate=1"
  ].join("&");
  uni.navigateTo({
    url: `/pages/command/index?${q}`
  });
}

function openAlarmPlayback(item: AlarmItem, windowMinutes = 5) {
  const deviceId = String(item.device_id || "").trim();
  const channelId = String(item.channel_id || "").trim();
  if (!deviceId || !channelId) {
    uni.showToast({ title: "缺少设备或通道ID，无法回放", icon: "none" });
    return;
  }
  const alarmTime = String(item.time || item.created_at || "");
  uni.navigateTo({
    url:
      `/pages/device-records/index?device_id=${encodeURIComponent(deviceId)}` +
      `&channel_id=${encodeURIComponent(channelId)}` +
      `&alarm_time=${encodeURIComponent(alarmTime)}` +
      `&window_minutes=${encodeURIComponent(String(windowMinutes))}`
  });
}

function openAlarmTvWall(item: AlarmItem) {
  const deviceId = String(item.device_id || "").trim();
  const channelId = String(item.channel_id || "").trim();
  if (!deviceId || !channelId) {
    uni.showToast({ title: "缺少设备或通道ID，无法上墙", icon: "none" });
    return;
  }
  uni.navigateTo({
    url: `/pages/tv-wall/index?device_id=${encodeURIComponent(deviceId)}&channel_id=${encodeURIComponent(channelId)}`
  });
}

function openAlarmVisualCommand(item: AlarmItem) {
  const deviceId = String(item.device_id || "").trim();
  const channelId = String(item.channel_id || "").trim();
  if (!deviceId || !channelId) {
    uni.showToast({ title: "缺少设备或通道ID，无法定位", icon: "none" });
    return;
  }
  uni.navigateTo({
    url: `/pages/visual-command/index?device_id=${encodeURIComponent(deviceId)}&channel_id=${encodeURIComponent(channelId)}`
  });
}

async function doAck() {
  if (!selectedAlarmId.value) return;
  actionLoading.value = true;
  try {
    await acknowledgeAlarm(selectedAlarmId.value, actionNote.value);
    uni.showToast({ title: "已确认", icon: "success" });
    await Promise.all([loadAlarms(), loadSlaOverview()]);
    setAlarmPageActionStatus(`告警确认成功：${selectedAlarmId.value}`);
  } catch (err: any) {
    const reason = String(err?.message || "请稍后重试");
    setAlarmPageActionStatus(`告警确认失败：${reason}`);
    uni.showToast({ title: "告警确认失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function quickAck(item: AlarmItem) {
  const id = String(item.id || "");
  if (!id) return;
  if (item.escalation_state === "acknowledged") {
    uni.showToast({ title: "该告警已确认", icon: "none" });
    return;
  }
  quickActionAlarmId.value = `${id}:ack`;
  try {
    await acknowledgeAlarm(id, "");
    uni.showToast({ title: "已确认", icon: "success" });
    await Promise.all([loadAlarms(), loadSlaOverview()]);
    setAlarmPageActionStatus(`告警确认成功：${id}`);
  } catch (err: any) {
    const reason = String(err?.message || "请稍后重试");
    setAlarmPageActionStatus(`告警确认失败：${reason}`);
    uni.showToast({ title: "告警确认失败", icon: "none" });
  } finally {
    quickActionAlarmId.value = "";
  }
}

async function doEscalate() {
  if (!selectedAlarmId.value) return;
  actionLoading.value = true;
  try {
    await escalateAlarm(selectedAlarmId.value, actionNote.value);
    uni.showToast({ title: "已升级", icon: "success" });
    await Promise.all([loadAlarms(), loadSlaOverview()]);
    setAlarmPageActionStatus(`告警升级成功：${selectedAlarmId.value}`);
  } catch (err: any) {
    const reason = String(err?.message || "请稍后重试");
    setAlarmPageActionStatus(`告警升级失败：${reason}`);
    uni.showToast({ title: "告警升级失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

async function quickEscalate(item: AlarmItem) {
  const id = String(item.id || "");
  if (!id) return;
  if (item.escalation_state === "acknowledged") {
    uni.showToast({ title: "该告警已确认，无需升级", icon: "none" });
    return;
  }
  quickActionAlarmId.value = `${id}:escalate`;
  try {
    await escalateAlarm(id, "");
    uni.showToast({ title: "已升级", icon: "success" });
    await Promise.all([loadAlarms(), loadSlaOverview()]);
    setAlarmPageActionStatus(`告警升级成功：${id}`);
  } catch (err: any) {
    const reason = String(err?.message || "请稍后重试");
    setAlarmPageActionStatus(`告警升级失败：${reason}`);
    uni.showToast({ title: "告警升级失败", icon: "none" });
  } finally {
    quickActionAlarmId.value = "";
  }
}

async function doDispatch() {
  if (!selectedAlarmId.value) return;
  actionLoading.value = true;
  try {
    await createWorkOrder({
      alarm_id: selectedAlarmId.value,
      title: dispatchTitle.value || `告警处置-${selectedAlarmId.value}`,
      description: dispatchDesc.value || actionNote.value,
      category: "tech_support",
      priority: "high"
    });
    uni.showToast({ title: "已派单", icon: "success" });
    await Promise.all([loadAlarms(), loadWorkOrders(), loadSlaOverview()]);
    setAlarmPageActionStatus(`告警派单成功：${selectedAlarmId.value}`);
  } catch (err: any) {
    const reason = String(err?.message || "请稍后重试");
    setAlarmPageActionStatus(`告警派单失败：${reason}`);
    uni.showToast({ title: "告警派单失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

function statusTag(status: WorkOrderStatus) {
  if (status === "closed") return { text: "已关闭", type: "info" as const };
  if (status === "resolved") return { text: "已解决", type: "success" as const };
  if (status === "in_progress") return { text: "处理中", type: "warning" as const };
  return { text: "待处理", type: "danger" as const };
}

async function moveStatus(item: WorkOrderItem, next: WorkOrderStatus) {
  actionLoading.value = true;
  try {
    await updateWorkOrderStatus(item.id, next);
    uni.showToast({ title: `已更新为 ${next}`, icon: "none" });
    await loadWorkOrders();
    setAlarmPageActionStatus(`工单状态更新成功：${item.id} -> ${next}`);
  } catch (err: any) {
    const reason = String(err?.message || "请稍后重试");
    setAlarmPageActionStatus(`工单状态更新失败：${reason}`);
    uni.showToast({ title: "工单状态更新失败", icon: "none" });
  } finally {
    actionLoading.value = false;
  }
}

onShow(async () => {
  await refreshAll();
});

async function switchTrendDays(days: 3 | 7) {
  if (trendDays.value === days) return;
  trendDays.value = days;
  await loadCrossDayTrend(days);
}

function switchCompareMode(mode: "period" | "day") {
  compareMode.value = mode;
}

function switchExportTemplate(mode: "summary" | "full") {
  exportTemplate.value = mode;
}

function onToggleExportField(key: string) {
  exportFields.value[key] = !exportFields.value[key];
}

function resetExportFields() {
  exportFields.value = { ...EXPORT_FIELD_DEFAULTS };
}

function buildTemplateFields(enabledKeys: string[]) {
  const enabled = new Set(enabledKeys);
  return Object.fromEntries(
    Object.keys(EXPORT_FIELD_DEFAULTS).map((key) => [key, enabled.has(key)])
  ) as Record<string, boolean>;
}

function applyReviewTemplatePreset() {
  applyReviewTemplatePresetInternal(true);
}

function applyReviewTemplatePresetInternal(showToast: boolean) {
  exportTemplate.value = "full";
  compareMode.value = "day";
  trendDays.value = 7;
  exportFields.value = buildTemplateFields(REVIEW_TEMPLATE_ENABLED_FIELDS);
  if (showToast) {
    uni.showToast({ title: "已切换为值班复盘模板", icon: "none" });
  }
}

function applyFullTemplatePreset() {
  exportTemplate.value = "full";
  exportFields.value = buildTemplateFields(FULL_TEMPLATE_ENABLED_FIELDS);
  uni.showToast({ title: "已切换为全量分析模板", icon: "none" });
}

function saveCurrentPreset() {
  if (!presetWritable.value) {
    uni.showToast({ title: "当前账号无共享预设写权限", icon: "none" });
    return;
  }
  const name = exportPresetName.value.trim();
  if (!name) {
    uni.showToast({ title: "请输入预设名称", icon: "none" });
    return;
  }
  const config: Record<string, unknown> = {
    exportTemplate: exportTemplate.value,
    exportFields: { ...exportFields.value },
    compareMode: compareMode.value,
    trendDays: trendDays.value
  };
  const idx = exportPresets.value.findIndex((x) => x.name === name);
  if (idx >= 0) exportPresets.value[idx] = { name, config };
  else exportPresets.value.push({ name, config });
  exportPresetSelected.value = name;
  savePresets();
  syncPresetsToServer().catch(() => undefined);
  uni.showToast({ title: "预设已保存", icon: "none" });
}

function applySelectedPreset() {
  const name = exportPresetSelected.value.trim();
  if (!name) return;
  const found = exportPresets.value.find((x) => x.name === name);
  if (!found) return;
  const cfg = found.config || {};
  exportTemplate.value = cfg.exportTemplate === "summary" ? "summary" : "full";
  compareMode.value = cfg.compareMode === "day" ? "day" : "period";
  trendDays.value = cfg.trendDays === 3 ? 3 : 7;
  const fields = (cfg.exportFields || {}) as Record<string, boolean>;
  exportFields.value = {
    ...EXPORT_FIELD_DEFAULTS,
    ...Object.fromEntries(Object.keys(EXPORT_FIELD_DEFAULTS).map((k) => [k, fields[k] !== false]))
  };
  uni.showToast({ title: "预设已应用", icon: "none" });
}

function removeSelectedPreset() {
  if (!presetWritable.value) {
    uni.showToast({ title: "当前账号无共享预设写权限", icon: "none" });
    return;
  }
  const name = exportPresetSelected.value.trim();
  if (!name) return;
  exportPresets.value = exportPresets.value.filter((x) => x.name !== name);
  exportPresetSelected.value = "";
  savePresets();
  syncPresetsToServer().catch(() => undefined);
  uni.showToast({ title: "预设已删除", icon: "none" });
}

async function onAlarmTypeChange(e: { detail?: { value?: string | number } }) {
  const idx = Number(e?.detail?.value ?? 0);
  selectedAlarmType.value = idx > 0 ? alarmTypeOptions.value[idx] : "";
  saveDashboardPrefs();
  await Promise.all([loadCrossDayTrend(), loadDurationMetrics(7)]);
}

async function onOrganizationChange(e: { detail?: { value?: string | number } }) {
  const idx = Number(e?.detail?.value ?? 0);
  selectedOrganization.value = organizationOptions.value[idx]?.value || "";
  saveDashboardPrefs();
  await Promise.all([loadCrossDayTrend(), loadDurationMetrics(7)]);
}

async function applyAlarmQuickPreset(preset: "all" | "high" | "unacked") {
  alarmQuickPreset.value = preset;
  saveDashboardPrefs();
  await Promise.all([loadCrossDayTrend(), loadDurationMetrics(7)]);
}

async function resetAlarmFilters() {
  selectedAlarmType.value = "";
  selectedOrganization.value = "";
  selectedSlowAlarmId.value = "";
  alarmQuickPreset.value = "all";
  saveDashboardPrefs();
  await Promise.all([loadCrossDayTrend(), loadDurationMetrics(7)]);
}

function toCsvValue(input: string | number) {
  const text = String(input ?? "");
  if (text.includes(",") || text.includes("\"") || text.includes("\n")) {
    return `"${text.replace(/"/g, "\"\"")}"`;
  }
  return text;
}

function currentShiftLabel() {
  const hour = new Date().getHours();
  if (hour >= 8 && hour < 16) return "白班";
  if (hour >= 16 && hour < 24) return "晚班";
  return "夜班";
}

function currentShiftKey() {
  const hour = new Date().getHours();
  if (hour >= 8 && hour < 16) return "day";
  if (hour >= 16 && hour < 24) return "evening";
  return "night";
}

function exportWindowLabel() {
  return compareMode.value === "day" ? "近24小时" : `近${trendDays.value}天`;
}

function saveReviewExportHistory() {
  uni.setStorageSync(REVIEW_EXPORT_HISTORY_KEY, reviewExportHistory.value.slice(0, 10));
}

const filteredReviewExportHistory = computed(() => {
  if (reviewExportWindowFilter.value === "all") return reviewExportHistory.value;
  const now = Date.now();
  const maxAgeMs = reviewExportWindowFilter.value === "24h" ? 24 * 60 * 60 * 1000 : 7 * 24 * 60 * 60 * 1000;
  return reviewExportHistory.value.filter((item) => {
    const t = new Date(String(item.generatedAt || "")).getTime();
    if (Number.isNaN(t)) return false;
    return now - t <= maxAgeMs;
  });
});

const reviewExportShiftTop1Text = computed(() => {
  if (!filteredReviewExportHistory.value.length) return "导出班次Top1：暂无";
  const counter = new Map<string, number>();
  for (const item of filteredReviewExportHistory.value) {
    const key = String(item.shiftLabel || "未知班次");
    counter.set(key, (counter.get(key) || 0) + 1);
  }
  const top = [...counter.entries()].sort((a, b) => b[1] - a[1])[0];
  if (!top) return "导出班次Top1：暂无";
  return `导出班次Top1：${top[0]}（${top[1]} 次）`;
});

const reviewExportWindowSummaryText = computed(() => {
  const total = reviewExportHistory.value.length;
  const matched = filteredReviewExportHistory.value.length;
  const windowLabel =
    reviewExportWindowFilter.value === "24h"
      ? "近24小时"
      : reviewExportWindowFilter.value === "7d"
        ? "近7天"
        : "全部";
  return `导出窗口：${windowLabel}；命中：${matched}/${total}`;
});

const reviewExportWindowHitRateText = computed(() => {
  const total = reviewExportHistory.value.length;
  const matched = filteredReviewExportHistory.value.length;
  if (total <= 0) return "窗口命中率：0/0 (0%)";
  const pct = Math.round((matched / total) * 100);
  return `窗口命中率：${matched}/${total} (${pct}%)`;
});

const reviewExportWindowIntensityText = computed(() => {
  const total = reviewExportHistory.value.length;
  if (total <= 0) return "窗口强度：暂无数据";
  const matched = filteredReviewExportHistory.value.length;
  const pct = Math.round((matched / total) * 100);
  if (pct <= 10) return "窗口强度：过严（建议放宽）";
  if (pct <= 35) return "窗口强度：偏严（可按需放宽）";
  return "窗口强度：正常";
});

const reviewExportWindowNextRelaxStepText = computed(() => {
  if (reviewExportWindowFilter.value === "24h") return "下一步放宽：近7天";
  if (reviewExportWindowFilter.value === "7d") return "下一步放宽：全部记录";
  return "下一步放宽：无需放宽";
});

const reviewExportWindowRelaxQueueText = computed(() => {
  if (reviewExportWindowFilter.value === "24h") return "可放宽链路：近24小时 -> 近7天 -> 全部记录";
  if (reviewExportWindowFilter.value === "7d") return "可放宽链路：近7天 -> 全部记录";
  return "可放宽链路：无";
});

const reviewExportWindowRelaxRemainingStepsText = computed(() => {
  if (reviewExportWindowFilter.value === "24h") return "剩余放宽步数：2";
  if (reviewExportWindowFilter.value === "7d") return "剩余放宽步数：1";
  return "剩余放宽步数：0";
});

const reviewExportWindowModeText = computed(() => {
  return reviewExportWindowFilter.value === "all" ? "窗口模式：默认视图" : "窗口模式：已启用筛选";
});

const reviewExportWindowCurrentPresetLabel = computed(() => {
  const matched = reviewExportWindowPresets.find((x) => x.filter === reviewExportWindowFilter.value);
  return matched ? matched.label : "自定义";
});

const reviewExportWindowActionSourceText = computed(() => {
  const source = reviewExportWindowLastActionSource.value;
  if (!source) return "未记录";
  if (source === "manual_filter") return "手动切换窗口";
  if (source === "relax") return "一键放宽";
  if (source === "reset") return "重置窗口";
  if (source.startsWith("preset_")) {
    const key = source.replace("preset_", "");
    const preset = reviewExportWindowPresets.find((x) => x.key === key);
    return `预设切换(${preset?.label || key})`;
  }
  return source;
});

const filteredReviewExportWindowActionAudit = computed(() => {
  if (reviewExportWindowActionAuditFilter.value === "all") return reviewExportWindowActionAudit.value;
  const now = Date.now();
  const maxAgeMs =
    reviewExportWindowActionAuditFilter.value === "24h" ? 24 * 60 * 60 * 1000 : 7 * 24 * 60 * 60 * 1000;
  return reviewExportWindowActionAudit.value.filter((item) => {
    const t = new Date(String(item.at || "")).getTime();
    if (Number.isNaN(t)) return false;
    return now - t <= maxAgeMs;
  });
});

const reviewExportWindowActionAuditRecentText = computed(() => {
  if (!filteredReviewExportWindowActionAudit.value.length) return "窗口动作审计：暂无";
  const rows = filteredReviewExportWindowActionAudit.value
    .slice(0, REVIEW_EXPORT_WINDOW_ACTION_AUDIT_RECENT_SHOW)
    .map((x, idx) => `${idx + 1}) ${x.source || "unknown"} @ ${formatDateTime(x.at || "")}`);
  return `窗口动作审计最近${REVIEW_EXPORT_WINDOW_ACTION_AUDIT_RECENT_SHOW}条：${rows.join("；")}`;
});

const reviewExportWindowActionAuditSourceTop1Text = computed(() => {
  if (!filteredReviewExportWindowActionAudit.value.length) return "窗口动作来源Top1：暂无";
  const counter = new Map<string, number>();
  for (const item of filteredReviewExportWindowActionAudit.value) {
    const key = String(item.source || "unknown");
    counter.set(key, (counter.get(key) || 0) + 1);
  }
  const top = [...counter.entries()].sort((a, b) => b[1] - a[1])[0];
  if (!top) return "窗口动作来源Top1：暂无";
  return `窗口动作来源Top1：${top[0]}（${top[1]} 次）`;
});

const reviewExportWindowActionAuditWindowSummaryText = computed(() => {
  const total = reviewExportWindowActionAudit.value.length;
  const matched = filteredReviewExportWindowActionAudit.value.length;
  const label =
    reviewExportWindowActionAuditFilter.value === "24h"
      ? "近24小时"
      : reviewExportWindowActionAuditFilter.value === "7d"
        ? "近7天"
        : "全部";
  return `动作审计窗口：${label}；命中：${matched}/${total}`;
});

const reviewExportWindowActionAuditHitRateText = computed(() => {
  const total = reviewExportWindowActionAudit.value.length;
  const matched = filteredReviewExportWindowActionAudit.value.length;
  if (total <= 0) return "动作审计命中率：0/0 (0%)";
  const pct = Math.round((matched / total) * 100);
  return `动作审计命中率：${matched}/${total} (${pct}%)`;
});

const reviewExportWindowActionAuditIntensityText = computed(() => {
  const total = reviewExportWindowActionAudit.value.length;
  if (total <= 0) return "动作审计强度：暂无数据";
  const matched = filteredReviewExportWindowActionAudit.value.length;
  const pct = Math.round((matched / total) * 100);
  if (pct <= 10) return "动作审计强度：过严（建议放宽）";
  if (pct <= 35) return "动作审计强度：偏严（可按需放宽）";
  return "动作审计强度：正常";
});

const reviewExportWindowActionAuditModeText = computed(() => {
  return reviewExportWindowActionAuditFilter.value === "all" ? "动作审计模式：默认视图" : "动作审计模式：已启用筛选";
});

const reviewExportWindowActionAuditCurrentPresetLabel = computed(() => {
  const matched = reviewExportWindowActionAuditPresets.find((x) => x.filter === reviewExportWindowActionAuditFilter.value);
  return matched ? matched.label : "自定义";
});

const reviewExportWindowActionAuditActionSourceText = computed(() => {
  const source = String(reviewExportWindowActionAuditLastActionSource.value || "");
  if (!source) return "未记录";
  if (source === "manual_filter") return "手动切换审计窗口";
  if (source === "relax") return "放宽审计窗口";
  if (source === "reset") return "重置审计窗口";
  if (source.startsWith("preset_")) {
    const key = source.replace("preset_", "");
    const preset = reviewExportWindowActionAuditPresets.find((x) => x.key === key);
    return `审计预设切换(${preset?.label || key})`;
  }
  return source;
});

const reviewExportWindowActionAuditPresetTop1Text = computed(() => {
  if (!filteredReviewExportWindowActionAuditPresetHistory.value.length) return "审计预设Top1：暂无";
  const counter = new Map<string, number>();
  for (const item of filteredReviewExportWindowActionAuditPresetHistory.value) {
    const key = String(item.presetLabel || "未知");
    counter.set(key, (counter.get(key) || 0) + 1);
  }
  const top = [...counter.entries()].sort((a, b) => b[1] - a[1])[0];
  if (!top) return "审计预设Top1：暂无";
  return `审计预设Top1：${top[0]}（${top[1]} 次）`;
});

const reviewExportWindowActionAuditPresetRecentText = computed(() => {
  if (!filteredReviewExportWindowActionAuditPresetHistory.value.length) return "审计预设历史：暂无";
  const rows = filteredReviewExportWindowActionAuditPresetHistory.value
    .slice(0, REVIEW_EXPORT_WINDOW_ACTION_AUDIT_RECENT_SHOW)
    .map((x, idx) => `${idx + 1}) ${x.presetLabel || x.presetKey} @ ${formatDateTime(x.at || "")}`);
  return `审计预设最近${REVIEW_EXPORT_WINDOW_ACTION_AUDIT_RECENT_SHOW}条：${rows.join("；")}`;
});

const filteredReviewExportWindowActionAuditPresetHistory = computed(() => {
  if (reviewExportWindowActionAuditPresetHistoryFilter.value === "all") return reviewExportWindowActionAuditPresetHistory.value;
  const now = Date.now();
  const maxAgeMs =
    reviewExportWindowActionAuditPresetHistoryFilter.value === "24h" ? 24 * 60 * 60 * 1000 : 7 * 24 * 60 * 60 * 1000;
  return reviewExportWindowActionAuditPresetHistory.value.filter((item) => {
    const t = new Date(String(item.at || "")).getTime();
    if (Number.isNaN(t)) return false;
    return now - t <= maxAgeMs;
  });
});

const reviewExportWindowActionAuditPresetHistoryWindowSummaryText = computed(() => {
  const total = reviewExportWindowActionAuditPresetHistory.value.length;
  const matched = filteredReviewExportWindowActionAuditPresetHistory.value.length;
  const label =
    reviewExportWindowActionAuditPresetHistoryFilter.value === "24h"
      ? "近24小时"
      : reviewExportWindowActionAuditPresetHistoryFilter.value === "7d"
        ? "近7天"
        : "全部";
  return `审计预设历史窗口：${label}；命中：${matched}/${total}`;
});

const reviewExportWindowActionAuditPresetHistoryHitRateText = computed(() => {
  const total = reviewExportWindowActionAuditPresetHistory.value.length;
  const matched = filteredReviewExportWindowActionAuditPresetHistory.value.length;
  if (total <= 0) return "审计预设历史命中率：0/0 (0%)";
  const pct = Math.round((matched / total) * 100);
  return `审计预设历史命中率：${matched}/${total} (${pct}%)`;
});

const reviewExportWindowActionAuditPresetHistoryIntensityText = computed(() => {
  const total = reviewExportWindowActionAuditPresetHistory.value.length;
  if (total <= 0) return "审计预设历史强度：暂无数据";
  const matched = filteredReviewExportWindowActionAuditPresetHistory.value.length;
  const pct = Math.round((matched / total) * 100);
  if (pct <= 10) return "审计预设历史强度：过严（建议放宽）";
  if (pct <= 35) return "审计预设历史强度：偏严（可按需放宽）";
  return "审计预设历史强度：正常";
});

const reviewExportWindowActionAuditPresetHistoryModeText = computed(() => {
  return reviewExportWindowActionAuditPresetHistoryFilter.value === "all"
    ? "审计预设历史模式：默认视图"
    : "审计预设历史模式：已启用筛选";
});

const reviewExportWindowActionAuditPresetHistoryCurrentPresetLabel = computed(() => {
  const matched = reviewExportWindowActionAuditPresetHistoryPresets.find(
    (x) => x.filter === reviewExportWindowActionAuditPresetHistoryFilter.value
  );
  return matched ? matched.label : "自定义";
});

const reviewExportWindowActionAuditPresetHistoryActionSourceText = computed(() => {
  const source = String(reviewExportWindowActionAuditPresetHistoryLastActionSource.value || "");
  if (!source) return "未记录";
  if (source === "manual_filter") return "手动切换预设历史窗口";
  if (source === "relax") return "放宽预设历史窗口";
  if (source === "reset") return "重置预设历史窗口";
  if (source === "action_audit_manual_filter") return "手动切换预设历史动作审计窗口";
  if (source === "action_audit_relax") return "放宽预设历史动作审计窗口";
  if (source === "action_audit_reset") return "重置预设历史动作审计窗口";
  if (source.startsWith("action_audit_preset_")) {
    const key = source.replace("action_audit_preset_", "");
    const preset = reviewExportWindowActionAuditPresetHistoryPresets.find((x) => x.key === key);
    return `预设历史动作审计预设(${preset?.label || key})`;
  }
  if (source.startsWith("preset_")) {
    const key = source.replace("preset_", "");
    const preset = reviewExportWindowActionAuditPresetHistoryPresets.find((x) => x.key === key);
    return `预设历史窗口预设(${preset?.label || key})`;
  }
  return source;
});

const filteredReviewExportWindowActionAuditPresetHistoryActionAudit = computed(() => {
  if (reviewExportWindowActionAuditPresetHistoryActionAuditFilter.value === "all") {
    return reviewExportWindowActionAuditPresetHistoryActionAudit.value;
  }
  const now = Date.now();
  const maxAgeMs =
    reviewExportWindowActionAuditPresetHistoryActionAuditFilter.value === "24h"
      ? 24 * 60 * 60 * 1000
      : 7 * 24 * 60 * 60 * 1000;
  return reviewExportWindowActionAuditPresetHistoryActionAudit.value.filter((item) => {
    const t = new Date(String(item.at || "")).getTime();
    if (Number.isNaN(t)) return false;
    return now - t <= maxAgeMs;
  });
});

const reviewExportWindowActionAuditPresetHistoryActionAuditSourceTop1Text = computed(() => {
  if (!filteredReviewExportWindowActionAuditPresetHistoryActionAudit.value.length) return "预设历史动作来源Top1：暂无";
  const counter = new Map<string, number>();
  for (const item of filteredReviewExportWindowActionAuditPresetHistoryActionAudit.value) {
    const key = String(item.source || "unknown");
    counter.set(key, (counter.get(key) || 0) + 1);
  }
  const top = [...counter.entries()].sort((a, b) => b[1] - a[1])[0];
  if (!top) return "预设历史动作来源Top1：暂无";
  return `预设历史动作来源Top1：${top[0]}（${top[1]} 次）`;
});

const reviewExportWindowActionAuditPresetHistoryActionAuditRecentText = computed(() => {
  if (!filteredReviewExportWindowActionAuditPresetHistoryActionAudit.value.length) return "预设历史动作审计：暂无";
  const rows = filteredReviewExportWindowActionAuditPresetHistoryActionAudit.value
    .slice(0, REVIEW_EXPORT_WINDOW_ACTION_AUDIT_RECENT_SHOW)
    .map((x, idx) => `${idx + 1}) ${x.source || "unknown"} @ ${formatDateTime(x.at || "")}`);
  return `预设历史动作审计最近${REVIEW_EXPORT_WINDOW_ACTION_AUDIT_RECENT_SHOW}条：${rows.join("；")}`;
});

const reviewExportWindowActionAuditPresetHistoryActionAuditWindowSummaryText = computed(() => {
  const total = reviewExportWindowActionAuditPresetHistoryActionAudit.value.length;
  const matched = filteredReviewExportWindowActionAuditPresetHistoryActionAudit.value.length;
  const label =
    reviewExportWindowActionAuditPresetHistoryActionAuditFilter.value === "24h"
      ? "近24小时"
      : reviewExportWindowActionAuditPresetHistoryActionAuditFilter.value === "7d"
        ? "近7天"
        : "全部";
  return `预设历史动作审计窗口：${label}；命中：${matched}/${total}`;
});

const reviewExportWindowActionAuditPresetHistoryActionAuditHitRateText = computed(() => {
  const total = reviewExportWindowActionAuditPresetHistoryActionAudit.value.length;
  const matched = filteredReviewExportWindowActionAuditPresetHistoryActionAudit.value.length;
  if (total <= 0) return "预设历史动作审计命中率：0/0 (0%)";
  const pct = Math.round((matched / total) * 100);
  return `预设历史动作审计命中率：${matched}/${total} (${pct}%)`;
});

const reviewExportWindowActionAuditPresetHistoryActionAuditIntensityText = computed(() => {
  const total = reviewExportWindowActionAuditPresetHistoryActionAudit.value.length;
  if (total <= 0) return "预设历史动作审计强度：暂无数据";
  const matched = filteredReviewExportWindowActionAuditPresetHistoryActionAudit.value.length;
  const pct = Math.round((matched / total) * 100);
  if (pct <= 10) return "预设历史动作审计强度：过严（建议放宽）";
  if (pct <= 35) return "预设历史动作审计强度：偏严（可按需放宽）";
  return "预设历史动作审计强度：正常";
});

const reviewExportWindowActionAuditPresetHistoryActionAuditModeText = computed(() => {
  return reviewExportWindowActionAuditPresetHistoryActionAuditFilter.value === "all"
    ? "预设历史动作审计模式：默认视图"
    : "预设历史动作审计模式：已启用筛选";
});

const reviewExportWindowActionAuditPresetHistoryActionAuditCurrentPresetLabel = computed(() => {
  const matched = reviewExportWindowActionAuditPresetHistoryPresets.find(
    (x) => x.filter === reviewExportWindowActionAuditPresetHistoryActionAuditFilter.value
  );
  return matched ? matched.label : "自定义";
});

const filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistory = computed(() => {
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryFilter.value === "all") {
    return reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistory.value;
  }
  const now = Date.now();
  const maxAgeMs =
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryFilter.value === "24h"
      ? 24 * 60 * 60 * 1000
      : 7 * 24 * 60 * 60 * 1000;
  return reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistory.value.filter((item) => {
    const t = new Date(String(item.at || "")).getTime();
    if (Number.isNaN(t)) return false;
    return now - t <= maxAgeMs;
  });
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetTop1Text = computed(() => {
  if (!filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistory.value.length) return "预设动作预设Top1：暂无";
  const counter = new Map<string, number>();
  for (const item of filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistory.value) {
    const key = String(item.presetLabel || "未知");
    counter.set(key, (counter.get(key) || 0) + 1);
  }
  const top = [...counter.entries()].sort((a, b) => b[1] - a[1])[0];
  if (!top) return "预设动作预设Top1：暂无";
  return `预设动作预设Top1：${top[0]}（${top[1]} 次）`;
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetRecentText = computed(() => {
  if (!filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistory.value.length) return "预设动作预设历史：暂无";
  const rows = filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistory.value
    .slice(0, REVIEW_EXPORT_WINDOW_ACTION_AUDIT_RECENT_SHOW)
    .map((x, idx) => `${idx + 1}) ${x.presetLabel || x.presetKey} @ ${formatDateTime(x.at || "")}`);
  return `预设动作预设最近${REVIEW_EXPORT_WINDOW_ACTION_AUDIT_RECENT_SHOW}条：${rows.join("；")}`;
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryWindowSummaryText = computed(() => {
  const total = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistory.value.length;
  const matched = filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistory.value.length;
  const label =
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryFilter.value === "24h"
      ? "近24小时"
      : reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryFilter.value === "7d"
        ? "近7天"
        : "全部";
  return `预设动作预设历史窗口：${label}；命中：${matched}/${total}`;
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryHitRateText = computed(() => {
  const total = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistory.value.length;
  const matched = filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistory.value.length;
  if (total <= 0) return "预设动作预设历史命中率：0/0 (0%)";
  const pct = Math.round((matched / total) * 100);
  return `预设动作预设历史命中率：${matched}/${total} (${pct}%)`;
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryIntensityText = computed(() => {
  const total = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistory.value.length;
  if (total <= 0) return "预设动作预设历史强度：暂无数据";
  const matched = filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistory.value.length;
  const pct = Math.round((matched / total) * 100);
  if (pct <= 10) return "预设动作预设历史强度：过严（建议放宽）";
  if (pct <= 35) return "预设动作预设历史强度：偏严（可按需放宽）";
  return "预设动作预设历史强度：正常";
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryModeText = computed(() => {
  return reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryFilter.value === "all"
    ? "预设动作预设历史模式：默认视图"
    : "预设动作预设历史模式：已启用筛选";
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionSourceText = computed(() => {
  const source = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryLastActionSource.value || "");
  if (!source) return "未记录";
  if (source === "manual_filter") return "手动切换预设动作预设历史窗口";
  if (source === "relax") return "放宽预设动作预设历史窗口";
  if (source === "reset") return "重置预设动作预设历史窗口";
  return source;
});

const filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAudit = computed(() => {
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "all") {
    return reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAudit.value;
  }
  const now = Date.now();
  const maxAgeMs =
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "24h"
      ? 24 * 60 * 60 * 1000
      : 7 * 24 * 60 * 60 * 1000;
  return reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAudit.value.filter((item) => {
    const t = new Date(String(item.at || "")).getTime();
    if (Number.isNaN(t)) return false;
    return now - t <= maxAgeMs;
  });
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditSourceTop1Text = computed(() => {
  if (!filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAudit.value.length) {
    return "预设动作预设历史动作来源Top1：暂无";
  }
  const counter = new Map<string, number>();
  for (const item of filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAudit.value) {
    const key = formatReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditActionSource(
      String(item.source || "unknown")
    );
    counter.set(key, (counter.get(key) || 0) + 1);
  }
  const top = [...counter.entries()].sort((a, b) => b[1] - a[1])[0];
  if (!top) return "预设动作预设历史动作来源Top1：暂无";
  return `预设动作预设历史动作来源Top1：${top[0]}（${top[1]} 次）`;
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditRecentText = computed(() => {
  if (!filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAudit.value.length) {
    return "预设动作预设历史动作审计：暂无";
  }
  const rows = filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAudit.value
    .slice(0, REVIEW_EXPORT_WINDOW_ACTION_AUDIT_RECENT_SHOW)
    .map(
      (x, idx) =>
        `${idx + 1}) ${formatReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditActionSource(String(x.source || "unknown"))} @ ${formatDateTime(x.at || "")}`
    );
  return `预设动作预设历史动作审计最近${REVIEW_EXPORT_WINDOW_ACTION_AUDIT_RECENT_SHOW}条：${rows.join("；")}`;
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditWindowSummaryText = computed(() => {
  const total = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAudit.value.length;
  const matched = filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAudit.value.length;
  const label =
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "24h"
      ? "近24小时"
      : reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "7d"
        ? "近7天"
        : "全部";
  return `预设动作预设历史动作审计窗口：${label}；命中：${matched}/${total}`;
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditHitRateText = computed(() => {
  const total = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAudit.value.length;
  const matched = filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAudit.value.length;
  if (total <= 0) return "预设动作预设历史动作审计命中率：0/0 (0%)";
  const pct = Math.round((matched / total) * 100);
  return `预设动作预设历史动作审计命中率：${matched}/${total} (${pct}%)`;
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditIntensityText = computed(() => {
  const total = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAudit.value.length;
  if (total <= 0) return "预设动作预设历史动作审计强度：暂无数据";
  const matched = filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAudit.value.length;
  const pct = Math.round((matched / total) * 100);
  if (pct <= 10) return "预设动作预设历史动作审计强度：过严（建议放宽）";
  if (pct <= 35) return "预设动作预设历史动作审计强度：偏严（可按需放宽）";
  return "预设动作预设历史动作审计强度：正常";
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditModeText = computed(() => {
  return reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "all"
    ? "预设动作预设历史动作审计模式：默认视图"
    : "预设动作预设历史动作审计模式：已启用筛选";
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditCurrentPresetLabel = computed(() => {
  const matched = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresets.find(
    (x) => x.filter === reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value
  );
  return matched ? matched.label : "自定义";
});

const filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistory = computed(() => {
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "all") {
    return reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistory.value;
  }
  const now = Date.now();
  const maxAgeMs =
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "24h"
      ? 24 * 60 * 60 * 1000
      : 7 * 24 * 60 * 60 * 1000;
  return reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistory.value.filter((item) => {
    const t = new Date(String(item.at || "")).getTime();
    if (Number.isNaN(t)) return false;
    return now - t <= maxAgeMs;
  });
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetTop1Text = computed(() => {
  if (!filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistory.value.length) {
    return "预设动作历史动作审计预设Top1：暂无";
  }
  const counter = new Map<string, number>();
  for (const item of filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistory.value) {
    const key = String(item.presetLabel || item.presetKey || "未知");
    counter.set(key, (counter.get(key) || 0) + 1);
  }
  const top = [...counter.entries()].sort((a, b) => b[1] - a[1])[0];
  if (!top) return "预设动作历史动作审计预设Top1：暂无";
  return `预设动作历史动作审计预设Top1：${top[0]}（${top[1]} 次）`;
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetRecentText = computed(() => {
  if (!filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistory.value.length) {
    return "预设动作历史动作审计预设历史：暂无";
  }
  const rows = filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistory.value
    .slice(0, REVIEW_EXPORT_WINDOW_ACTION_AUDIT_RECENT_SHOW)
    .map((x, idx) => `${idx + 1}) ${x.presetLabel || x.presetKey} @ ${formatDateTime(x.at || "")}`);
  return `预设动作历史动作审计预设最近${REVIEW_EXPORT_WINDOW_ACTION_AUDIT_RECENT_SHOW}条：${rows.join("；")}`;
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetWindowSummaryText = computed(() => {
  const total = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistory.value.length;
  const matched = filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistory.value.length;
  const label =
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "24h"
      ? "近24小时"
      : reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "7d"
        ? "近7天"
        : "全部";
  return `预设动作历史动作审计预设历史窗口：${label}；命中：${matched}/${total}`;
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHitRateText = computed(() => {
  const total = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistory.value.length;
  const matched = filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistory.value.length;
  if (total <= 0) return "预设动作历史动作审计预设历史命中率：0/0 (0%)";
  const pct = Math.round((matched / total) * 100);
  return `预设动作历史动作审计预设历史命中率：${matched}/${total} (${pct}%)`;
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetIntensityText = computed(() => {
  const total = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistory.value.length;
  if (total <= 0) return "预设动作历史动作审计预设历史强度：暂无数据";
  const matched = filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistory.value.length;
  const pct = Math.round((matched / total) * 100);
  if (pct <= 10) return "预设动作历史动作审计预设历史强度：过严（建议放宽）";
  if (pct <= 35) return "预设动作历史动作审计预设历史强度：偏严（可按需放宽）";
  return "预设动作历史动作审计预设历史强度：正常";
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetModeText = computed(() => {
  return reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "all"
    ? "预设动作历史动作审计预设历史模式：默认视图"
    : "预设动作历史动作审计预设历史模式：已启用筛选";
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryNextRelaxStepText = computed(() => {
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "24h") {
    return "预设动作历史动作审计预设历史下一步放宽：近7天";
  }
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "7d") {
    return "预设动作历史动作审计预设历史下一步放宽：全部";
  }
  return "预设动作历史动作审计预设历史下一步放宽：无需放宽";
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryRelaxQueueText = computed(() => {
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "24h") {
    return "预设动作历史动作审计预设历史可放宽链路：近24小时 -> 近7天 -> 全部";
  }
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "7d") {
    return "预设动作历史动作审计预设历史可放宽链路：近7天 -> 全部";
  }
  return "预设动作历史动作审计预设历史可放宽链路：无";
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryRelaxRemainingStepsText = computed(() => {
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "24h") {
    return "预设动作历史动作审计预设历史剩余放宽步数：2";
  }
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "7d") {
    return "预设动作历史动作审计预设历史剩余放宽步数：1";
  }
  return "预设动作历史动作审计预设历史剩余放宽步数：0";
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryRelaxStateText = computed(() => {
  return `预设动作历史动作审计预设历史放宽状态：${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetModeText.value}；${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryRelaxRemainingStepsText.value}`;
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryRelaxStateSummaryText = computed(() => {
  return [
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetModeText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryRelaxQueueText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryRelaxRemainingStepsText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryNextRelaxStepText.value
  ].join("；");
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceSummaryText = computed(() => {
  return [
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetWindowSummaryText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHitRateText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetIntensityText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetModeText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryRelaxStateSummaryText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetTop1Text.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetRecentText.value
  ].join("；");
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceAudit = computed(() => {
  return filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAudit.value.filter((item) => {
    const source = String(item.source || "");
    return (
      source === "preset_history_manual_filter" ||
      source === "preset_history_relax" ||
      source === "preset_history_reset" ||
      source === "preset_history_clear" ||
      source === "preset_history_clear_relax"
    );
  });
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceSourceTop1Text = computed(() => {
  if (!reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceAudit.value.length) {
    return "预设动作历史动作审计预设历史治理来源Top1：暂无";
  }
  const counter = new Map<string, number>();
  for (const item of reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceAudit.value) {
    const key = formatReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditActionSource(String(item.source || ""));
    counter.set(key, (counter.get(key) || 0) + 1);
  }
  const top = [...counter.entries()].sort((a, b) => b[1] - a[1])[0];
  if (!top) return "预设动作历史动作审计预设历史治理来源Top1：暂无";
  return `预设动作历史动作审计预设历史治理来源Top1：${top[0]}（${top[1]} 次）`;
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceRecentText = computed(() => {
  if (!reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceAudit.value.length) {
    return "预设动作历史动作审计预设历史治理记录：暂无";
  }
  const rows = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceAudit.value
    .slice(0, REVIEW_EXPORT_WINDOW_ACTION_AUDIT_RECENT_SHOW)
    .map(
      (x, idx) =>
        `${idx + 1}) ${formatReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditActionSource(String(x.source || ""))} @ ${formatDateTime(x.at || "")}`
    );
  return `预设动作历史动作审计预设历史治理最近${REVIEW_EXPORT_WINDOW_ACTION_AUDIT_RECENT_SHOW}条：${rows.join("；")}`;
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceLastActionItem = computed(() => {
  return reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAudit.value.find((item) => {
    const source = String(item.source || "");
    return source.startsWith("governance_");
  });
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceLastActionText = computed(() => {
  const row = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceLastActionItem.value;
  if (!row) return "最近治理动作：无";
  return `最近治理动作：${row.action || "无"}`;
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceLastActionAtText = computed(() => {
  const row = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceLastActionItem.value;
  if (!row?.at) return "治理动作时间：-";
  return `治理动作时间：${formatDateTime(row.at)}`;
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceLastActionSourceText = computed(() => {
  const row = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceLastActionItem.value;
  return `治理动作来源：${formatReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditActionSource(String(row?.source || ""))}`;
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceWindowSummaryText = computed(() => {
  const total = filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAudit.value.length;
  const matched = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceAudit.value.length;
  const label =
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "24h"
      ? "近24小时"
      : reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "7d"
        ? "近7天"
        : "全部";
  return `预设动作历史动作审计预设历史治理窗口：${label}；命中：${matched}/${total}`;
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceHitRateText = computed(() => {
  const total = filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAudit.value.length;
  const matched = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceAudit.value.length;
  if (total <= 0) return "预设动作历史动作审计预设历史治理命中率：0/0 (0%)";
  const pct = Math.round((matched / total) * 100);
  return `预设动作历史动作审计预设历史治理命中率：${matched}/${total} (${pct}%)`;
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceIntensityText = computed(() => {
  const total = filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAudit.value.length;
  if (total <= 0) return "预设动作历史动作审计预设历史治理强度：暂无数据";
  const matched = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceAudit.value.length;
  const pct = Math.round((matched / total) * 100);
  if (pct <= 10) return "预设动作历史动作审计预设历史治理强度：过严（建议放宽）";
  if (pct <= 35) return "预设动作历史动作审计预设历史治理强度：偏严（可按需放宽）";
  return "预设动作历史动作审计预设历史治理强度：正常";
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceModeText = computed(() => {
  return reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "all"
    ? "预设动作历史动作审计预设历史治理模式：默认视图"
    : "预设动作历史动作审计预设历史治理模式：已启用筛选";
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel = computed(() => {
  const matched = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresets.find(
    (x) => x.filter === reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value
  );
  return matched ? matched.label : "自定义";
});

const filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistory = computed(() => {
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "all") {
    return reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistory.value;
  }
  const now = Date.now();
  const maxAgeMs =
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "24h"
      ? 24 * 60 * 60 * 1000
      : 7 * 24 * 60 * 60 * 1000;
  return reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistory.value.filter((item) => {
    const t = new Date(String(item.at || "")).getTime();
    if (Number.isNaN(t)) return false;
    return now - t <= maxAgeMs;
  });
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetTop1Text = computed(() => {
  if (!filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistory.value.length) {
    return "预设动作历史动作审计预设历史治理预设Top1：暂无";
  }
  const counter = new Map<string, number>();
  for (const item of filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistory.value) {
    const key = String(item.presetLabel || item.presetKey || "未知");
    counter.set(key, (counter.get(key) || 0) + 1);
  }
  const top = [...counter.entries()].sort((a, b) => b[1] - a[1])[0];
  if (!top) return "预设动作历史动作审计预设历史治理预设Top1：暂无";
  return `预设动作历史动作审计预设历史治理预设Top1：${top[0]}（${top[1]} 次）`;
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetRecentText = computed(() => {
  if (!filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistory.value.length) {
    return "预设动作历史动作审计预设历史治理预设历史：暂无";
  }
  const rows = filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistory.value
    .slice(0, REVIEW_EXPORT_WINDOW_ACTION_AUDIT_RECENT_SHOW)
    .map((x, idx) => `${idx + 1}) ${x.presetLabel || x.presetKey} @ ${formatDateTime(x.at || "")}`);
  return `预设动作历史动作审计预设历史治理预设最近${REVIEW_EXPORT_WINDOW_ACTION_AUDIT_RECENT_SHOW}条：${rows.join("；")}`;
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAudit = computed(() => {
  return filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAudit.value.filter((item) =>
    String(item.source || "").startsWith("governance_preset_history_")
  );
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditTop1Text = computed(() => {
  if (!reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAudit.value.length) {
    return "治理预设历史审计来源Top1：暂无";
  }
  const counter = new Map<string, number>();
  for (const item of reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAudit.value) {
    const key = formatReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditActionSource(
      String(item.source || "")
    );
    counter.set(key, (counter.get(key) || 0) + 1);
  }
  const top = [...counter.entries()].sort((a, b) => b[1] - a[1])[0];
  if (!top) return "治理预设历史审计来源Top1：暂无";
  return `治理预设历史审计来源Top1：${top[0]}（${top[1]} 次）`;
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditRecentText = computed(() => {
  if (!reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAudit.value.length) {
    return "治理预设历史审计记录：暂无";
  }
  const rows = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAudit.value
    .slice(0, REVIEW_EXPORT_WINDOW_ACTION_AUDIT_RECENT_SHOW)
    .map(
      (x, idx) =>
        `${idx + 1}) ${formatReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditActionSource(String(x.source || ""))} @ ${formatDateTime(x.at || "")}`
    );
  return `治理预设历史审计最近${REVIEW_EXPORT_WINDOW_ACTION_AUDIT_RECENT_SHOW}条：${rows.join("；")}`;
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditSummaryText = computed(() => {
  return [
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetWindowSummaryText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHitRateText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetIntensityText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetModeText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditTop1Text.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditRecentText.value
  ].join("；");
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditLastActionItem = computed(() => {
  return reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAudit.value[0];
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditLastActionText = computed(() => {
  const row = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditLastActionItem.value;
  if (!row) return "治理预设历史审计最近动作：无";
  return `治理预设历史审计最近动作：${row.action || "无"}`;
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditLastActionSourceText = computed(() => {
  const row = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditLastActionItem.value;
  return `治理预设历史审计动作来源：${formatReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditActionSource(String(row?.source || ""))}`;
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditLastActionAtText = computed(() => {
  const row = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditLastActionItem.value;
  if (!row?.at) return "治理预设历史审计动作时间：-";
  return `治理预设历史审计动作时间：${formatDateTime(row.at)}`;
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionSummaryText = computed(
  () => {
    return [
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditLastActionText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditLastActionSourceText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditLastActionAtText.value
    ].join("；");
  }
);

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageText = computed(
  () => {
    return [
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionSummaryText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditSummaryText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditWindowStateSummaryText.value
    ].join("；");
  }
);

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageStateText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包状态摘要",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionSummaryText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditWindowStateSummaryText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditRelaxStateText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照",
      `当前筛选=${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value}`,
      `当前预设=${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value}`,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditTop1Text.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditRecentText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestText =
  computed(() => {
    const raw = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotText.value;
    let checksum = 0;
    for (let i = 0; i < raw.length; i += 1) checksum = (checksum + raw.charCodeAt(i) * (i + 1)) % 1000000007;
    return `治理预设历史审计动作组合包快照指纹：len=${raw.length}；checksum=${checksum}`;
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotHandoverText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照交接摘要",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestStateText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹状态",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditWindowStateSummaryText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditRelaxStateText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestStateText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotHandoverText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStateText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditWindowStateSummaryText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditRelaxStateText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStateText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStateText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStateText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditWindowStateSummaryText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStateText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStateText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStateText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditWindowStateSummaryText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStateText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStateText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditWindowStateSummaryText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditWindowStateSummaryText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditWindowStateSummaryText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditWindowStateSummaryText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditWindowStateSummaryText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditWindowStateSummaryText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditWindowStateSummaryText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditWindowStateSummaryText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStateText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditWindowStateSummaryText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStateText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStateText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStateText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditWindowStateSummaryText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStateText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageConclusionText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStateText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageConclusionStateText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论状态",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageConclusionText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditWindowStateSummaryText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageText =
  computed(() => {
    return [
      "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论状态交接包",
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageConclusionStateText.value,
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageConclusionText.value
    ].join("；");
  });

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditNextRelaxStepText = computed(() => {
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "24h") {
    return "治理预设历史审计下一步放宽：近7天";
  }
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "7d") {
    return "治理预设历史审计下一步放宽：全部";
  }
  return "治理预设历史审计下一步放宽：无需放宽";
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditRelaxQueueText = computed(() => {
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "24h") {
    return "治理预设历史审计可放宽链路：近24小时 -> 近7天 -> 全部";
  }
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "7d") {
    return "治理预设历史审计可放宽链路：近7天 -> 全部";
  }
  return "治理预设历史审计可放宽链路：无";
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditRelaxRemainingStepsText = computed(() => {
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "24h") {
    return "治理预设历史审计剩余放宽步数：2";
  }
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "7d") {
    return "治理预设历史审计剩余放宽步数：1";
  }
  return "治理预设历史审计剩余放宽步数：0";
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditRelaxStateText = computed(() => {
  return `治理预设历史审计放宽状态：${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetModeText.value}；${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditRelaxRemainingStepsText.value}`;
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditWindowStateSummaryText = computed(() => {
  const at = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastActionAt.value
    ? formatDateTime(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastActionAt.value)
    : "-";
  return [
    "治理预设历史审计窗口状态摘要",
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetWindowSummaryText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHitRateText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetIntensityText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetModeText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditTop1Text.value,
    `最近动作=${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastAction.value || "无"}`,
    `来源=${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditActionSourceText.value}`,
    `时间=${at}`
  ].join("；");
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetWindowSummaryText = computed(() => {
  const total = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistory.value.length;
  const matched = filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistory.value.length;
  const label =
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "24h"
      ? "近24小时"
      : reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "7d"
        ? "近7天"
        : "全部";
  return `预设动作历史动作审计预设历史治理预设历史窗口：${label}；命中：${matched}/${total}`;
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHitRateText = computed(() => {
  const total = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistory.value.length;
  const matched = filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistory.value.length;
  if (total <= 0) return "预设动作历史动作审计预设历史治理预设历史命中率：0/0 (0%)";
  const pct = Math.round((matched / total) * 100);
  return `预设动作历史动作审计预设历史治理预设历史命中率：${matched}/${total} (${pct}%)`;
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetIntensityText = computed(() => {
  const total = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistory.value.length;
  if (total <= 0) return "预设动作历史动作审计预设历史治理预设历史强度：暂无数据";
  const matched = filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistory.value.length;
  const pct = Math.round((matched / total) * 100);
  if (pct <= 10) return "预设动作历史动作审计预设历史治理预设历史强度：过严（建议放宽）";
  if (pct <= 35) return "预设动作历史动作审计预设历史治理预设历史强度：偏严（可按需放宽）";
  return "预设动作历史动作审计预设历史治理预设历史强度：正常";
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetModeText = computed(() => {
  return reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "all"
    ? "预设动作历史动作审计预设历史治理预设历史模式：默认视图"
    : "预设动作历史动作审计预设历史治理预设历史模式：已启用筛选";
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryNextRelaxStepText = computed(() => {
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "24h") {
    return "预设动作历史动作审计预设历史治理预设历史下一步放宽：近7天";
  }
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "7d") {
    return "预设动作历史动作审计预设历史治理预设历史下一步放宽：全部";
  }
  return "预设动作历史动作审计预设历史治理预设历史下一步放宽：无需放宽";
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryRelaxQueueText = computed(() => {
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "24h") {
    return "预设动作历史动作审计预设历史治理预设历史可放宽链路：近24小时 -> 近7天 -> 全部";
  }
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "7d") {
    return "预设动作历史动作审计预设历史治理预设历史可放宽链路：近7天 -> 全部";
  }
  return "预设动作历史动作审计预设历史治理预设历史可放宽链路：无";
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryRelaxRemainingStepsText = computed(() => {
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "24h") {
    return "预设动作历史动作审计预设历史治理预设历史剩余放宽步数：2";
  }
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "7d") {
    return "预设动作历史动作审计预设历史治理预设历史剩余放宽步数：1";
  }
  return "预设动作历史动作审计预设历史治理预设历史剩余放宽步数：0";
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryRelaxStateText = computed(() => {
  return `预设动作历史动作审计预设历史治理预设历史放宽状态：${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetModeText.value}；${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryRelaxRemainingStepsText.value}`;
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceNextRelaxStepText = computed(() => {
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "24h") {
    return "预设动作历史动作审计预设历史治理下一步放宽：近7天";
  }
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "7d") {
    return "预设动作历史动作审计预设历史治理下一步放宽：全部";
  }
  return "预设动作历史动作审计预设历史治理下一步放宽：无需放宽";
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceRelaxQueueText = computed(() => {
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "24h") {
    return "预设动作历史动作审计预设历史治理可放宽链路：近24小时 -> 近7天 -> 全部";
  }
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "7d") {
    return "预设动作历史动作审计预设历史治理可放宽链路：近7天 -> 全部";
  }
  return "预设动作历史动作审计预设历史治理可放宽链路：无";
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceRelaxRemainingStepsText = computed(() => {
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "24h") {
    return "预设动作历史动作审计预设历史治理剩余放宽步数：2";
  }
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "7d") {
    return "预设动作历史动作审计预设历史治理剩余放宽步数：1";
  }
  return "预设动作历史动作审计预设历史治理剩余放宽步数：0";
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceRelaxStateText = computed(() => {
  return `预设动作历史动作审计预设历史治理放宽状态：${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceModeText.value}；${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceRelaxRemainingStepsText.value}`;
});

function formatReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditActionSource(source: string) {
  if (!source) return "未记录";
  if (source === "manual_filter") return "手动切换预设动作历史动作审计窗口";
  if (source === "relax") return "放宽预设动作历史动作审计窗口";
  if (source === "reset") return "重置预设动作历史动作审计窗口";
  if (source === "preset_history_manual_filter") return "手动切换预设动作历史动作审计预设历史窗口";
  if (source === "preset_history_relax") return "放宽预设动作历史动作审计预设历史窗口";
  if (source === "preset_history_reset") return "重置预设动作历史动作审计预设历史窗口";
  if (source === "governance_manual_filter") return "手动切换预设动作历史动作审计预设历史治理窗口";
  if (source === "governance_relax") return "放宽预设动作历史动作审计预设历史治理窗口";
  if (source === "governance_reset") return "重置预设动作历史动作审计预设历史治理窗口";
  if (source === "governance_clear") return "清空预设动作历史动作审计预设历史治理审计";
  if (source.startsWith("governance_preset_")) {
    const key = source.replace("governance_preset_", "");
    const preset = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresets.find((x) => x.key === key);
    return `预设动作历史动作审计预设历史治理预设(${preset?.label || key})`;
  }
  if (source === "governance_export_summary") return "复制预设动作历史动作审计预设历史治理审计摘要";
  if (source === "governance_export_json") return "复制预设动作历史动作审计预设历史治理审计JSON";
  if (source === "governance_export_csv") return "复制预设动作历史动作审计预设历史治理审计CSV";
  if (source === "governance_export_window_state") return "复制预设动作历史动作审计预设历史治理窗口状态";
  if (source === "governance_preset_history_relax") return "放宽预设动作历史动作审计预设历史治理预设历史窗口";
  if (source === "governance_preset_history_reset") return "重置预设动作历史动作审计预设历史治理预设历史窗口";
  if (source === "governance_preset_history_export_state") return "复制预设动作历史动作审计预设历史治理预设历史窗口状态";
  if (source === "governance_preset_history_clear_relax") return "清空预设动作历史动作审计预设历史治理预设历史放宽记录";
  if (source === "governance_preset_history_export_summary") return "复制预设动作历史动作审计预设历史治理预设历史摘要";
  if (source === "governance_preset_history_export_json") return "复制预设动作历史动作审计预设历史治理预设历史JSON";
  if (source === "governance_preset_history_export_csv") return "复制预设动作历史动作审计预设历史治理预设历史CSV";
  if (source === "governance_preset_history_export_relax_state") return "复制预设动作历史动作审计预设历史治理预设历史放宽状态";
  if (source === "governance_preset_history_audit_export_summary") return "复制治理预设历史审计摘要";
  if (source === "governance_preset_history_audit_export_json") return "复制治理预设历史审计JSON";
  if (source === "governance_preset_history_audit_export_csv") return "复制治理预设历史审计CSV";
  if (source === "governance_preset_history_audit_export_relax_state") return "复制治理预设历史审计放宽状态";
  if (source === "governance_preset_history_audit_export_state") return "复制治理预设历史审计窗口状态";
  if (source === "governance_preset_history_audit_export_action") return "复制治理预设历史审计动作摘要";
  if (source === "governance_preset_history_audit_export_action_json") return "复制治理预设历史审计动作JSON";
  if (source === "governance_preset_history_audit_export_action_csv") return "复制治理预设历史审计动作CSV";
  if (source === "governance_preset_history_audit_export_action_package") return "复制治理预设历史审计动作组合包";
  if (source === "governance_preset_history_audit_export_action_package_state") return "复制治理预设历史审计动作组合包状态";
  if (source === "governance_preset_history_audit_export_action_package_json") return "复制治理预设历史审计动作组合包JSON";
  if (source === "governance_preset_history_audit_export_action_package_csv") return "复制治理预设历史审计动作组合包CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot") return "复制治理预设历史审计动作组合包快照";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_json") return "复制治理预设历史审计动作组合包快照JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_csv") return "复制治理预设历史审计动作组合包快照CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest")
    return "复制治理预设历史审计动作组合包快照指纹";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_json")
    return "复制治理预设历史审计动作组合包快照指纹JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_csv")
    return "复制治理预设历史审计动作组合包快照指纹CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_state")
    return "复制治理预设历史审计动作组合包快照指纹状态";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_package_json")
    return "复制治理预设历史审计动作组合包快照指纹交接包JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_package_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接包CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion")
    return "复制治理预设历史审计动作组合包快照指纹交接结论";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package_conclusion")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package_conclusion_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package_conclusion_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package_conclusion_state")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论状态";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论状态JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论状态CSV";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论状态交接包";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package_json")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论状态交接包JSON";
  if (source === "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package_csv")
    return "复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论状态交接包CSV";
  if (source === "governance_preset_history_audit_reset") return "重置治理预设历史审计窗口";
  if (source === "governance_preset_history_audit_clear") return "清空治理预设历史审计记录";
  if (source === "governance_preset_history_clear") return "清空预设动作历史动作审计预设历史治理预设历史";
  if (source === "preset_history_clear") return "清空预设动作历史动作审计预设历史";
  if (source === "preset_history_clear_relax") return "清空预设动作历史动作审计预设历史放宽记录";
  if (source.startsWith("preset_")) {
    const key = source.replace("preset_", "");
    const preset = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresets.find((x) => x.key === key);
    return `预设动作历史动作审计预设(${preset?.label || key})`;
  }
  return source;
}

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditActionSourceText = computed(() => {
  return formatReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditActionSource(
    String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastActionSource.value || "")
  );
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditNextRelaxStepText = computed(() => {
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "24h") {
    return "预设动作历史动作审计下一步放宽：近7天";
  }
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "7d") {
    return "预设动作历史动作审计下一步放宽：全部";
  }
  return "预设动作历史动作审计下一步放宽：无需放宽";
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditRelaxQueueText = computed(() => {
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "24h") {
    return "预设动作历史动作审计可放宽链路：近24小时 -> 近7天 -> 全部";
  }
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "7d") {
    return "预设动作历史动作审计可放宽链路：近7天 -> 全部";
  }
  return "预设动作历史动作审计可放宽链路：无";
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditRelaxRemainingStepsText = computed(() => {
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "24h") {
    return "预设动作历史动作审计剩余放宽步数：2";
  }
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "7d") {
    return "预设动作历史动作审计剩余放宽步数：1";
  }
  return "预设动作历史动作审计剩余放宽步数：0";
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditRelaxStateText = computed(() => {
  return `预设动作历史动作审计放宽状态：${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditModeText.value}；${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditRelaxRemainingStepsText.value}`;
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditRelaxStateSummaryText = computed(() => {
  return [
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditModeText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditRelaxQueueText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditRelaxRemainingStepsText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditNextRelaxStepText.value
  ].join("；");
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryNextRelaxStepText = computed(() => {
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryFilter.value === "24h") return "预设动作预设历史下一步放宽：近7天";
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryFilter.value === "7d") return "预设动作预设历史下一步放宽：全部";
  return "预设动作预设历史下一步放宽：无需放宽";
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryRelaxQueueText = computed(() => {
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryFilter.value === "24h") {
    return "预设动作预设历史可放宽链路：近24小时 -> 近7天 -> 全部";
  }
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryFilter.value === "7d") {
    return "预设动作预设历史可放宽链路：近7天 -> 全部";
  }
  return "预设动作预设历史可放宽链路：无";
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryRelaxRemainingStepsText = computed(() => {
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryFilter.value === "24h") return "预设动作预设历史剩余放宽步数：2";
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryFilter.value === "7d") return "预设动作预设历史剩余放宽步数：1";
  return "预设动作预设历史剩余放宽步数：0";
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryRelaxStateText = computed(() => {
  return `预设动作预设历史放宽状态：${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryModeText.value}；${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryRelaxRemainingStepsText.value}`;
});

const reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryRelaxStateSummaryText = computed(() => {
  return [
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryModeText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryRelaxQueueText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryRelaxRemainingStepsText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryNextRelaxStepText.value
  ].join("；");
});

const reviewExportWindowActionAuditPresetHistoryActionAuditNextRelaxStepText = computed(() => {
  if (reviewExportWindowActionAuditPresetHistoryActionAuditFilter.value === "24h") return "预设历史动作审计下一步放宽：近7天";
  if (reviewExportWindowActionAuditPresetHistoryActionAuditFilter.value === "7d") return "预设历史动作审计下一步放宽：全部";
  return "预设历史动作审计下一步放宽：无需放宽";
});

const reviewExportWindowActionAuditPresetHistoryActionAuditRelaxQueueText = computed(() => {
  if (reviewExportWindowActionAuditPresetHistoryActionAuditFilter.value === "24h") return "预设历史动作审计可放宽链路：近24小时 -> 近7天 -> 全部";
  if (reviewExportWindowActionAuditPresetHistoryActionAuditFilter.value === "7d") return "预设历史动作审计可放宽链路：近7天 -> 全部";
  return "预设历史动作审计可放宽链路：无";
});

const reviewExportWindowActionAuditPresetHistoryActionAuditRelaxRemainingStepsText = computed(() => {
  if (reviewExportWindowActionAuditPresetHistoryActionAuditFilter.value === "24h") return "预设历史动作审计剩余放宽步数：2";
  if (reviewExportWindowActionAuditPresetHistoryActionAuditFilter.value === "7d") return "预设历史动作审计剩余放宽步数：1";
  return "预设历史动作审计剩余放宽步数：0";
});

const reviewExportWindowActionAuditPresetHistoryActionAuditRelaxStateText = computed(() => {
  return `预设历史动作审计放宽状态：${reviewExportWindowActionAuditPresetHistoryActionAuditModeText.value}；${reviewExportWindowActionAuditPresetHistoryActionAuditRelaxRemainingStepsText.value}`;
});

const reviewExportWindowActionAuditPresetHistoryNextRelaxStepText = computed(() => {
  if (reviewExportWindowActionAuditPresetHistoryFilter.value === "24h") return "预设历史下一步放宽：近7天";
  if (reviewExportWindowActionAuditPresetHistoryFilter.value === "7d") return "预设历史下一步放宽：全部";
  return "预设历史下一步放宽：无需放宽";
});

const reviewExportWindowActionAuditPresetHistoryRelaxQueueText = computed(() => {
  if (reviewExportWindowActionAuditPresetHistoryFilter.value === "24h") return "预设历史可放宽链路：近24小时 -> 近7天 -> 全部";
  if (reviewExportWindowActionAuditPresetHistoryFilter.value === "7d") return "预设历史可放宽链路：近7天 -> 全部";
  return "预设历史可放宽链路：无";
});

const reviewExportWindowActionAuditPresetHistoryRelaxRemainingStepsText = computed(() => {
  if (reviewExportWindowActionAuditPresetHistoryFilter.value === "24h") return "预设历史剩余放宽步数：2";
  if (reviewExportWindowActionAuditPresetHistoryFilter.value === "7d") return "预设历史剩余放宽步数：1";
  return "预设历史剩余放宽步数：0";
});

const reviewExportWindowActionAuditPresetHistoryRelaxStateText = computed(() => {
  return `预设历史放宽状态：${reviewExportWindowActionAuditPresetHistoryModeText.value}；${reviewExportWindowActionAuditPresetHistoryRelaxRemainingStepsText.value}`;
});

const reviewExportWindowActionAuditNextRelaxStepText = computed(() => {
  if (reviewExportWindowActionAuditFilter.value === "24h") return "审计下一步放宽：近7天";
  if (reviewExportWindowActionAuditFilter.value === "7d") return "审计下一步放宽：全部";
  return "审计下一步放宽：无需放宽";
});

const reviewExportWindowActionAuditRelaxQueueText = computed(() => {
  if (reviewExportWindowActionAuditFilter.value === "24h") return "审计可放宽链路：近24小时 -> 近7天 -> 全部";
  if (reviewExportWindowActionAuditFilter.value === "7d") return "审计可放宽链路：近7天 -> 全部";
  return "审计可放宽链路：无";
});

const reviewExportWindowActionAuditRelaxRemainingStepsText = computed(() => {
  if (reviewExportWindowActionAuditFilter.value === "24h") return "审计剩余放宽步数：2";
  if (reviewExportWindowActionAuditFilter.value === "7d") return "审计剩余放宽步数：1";
  return "审计剩余放宽步数：0";
});

const reviewExportShiftStatsText = computed(() => {
  if (!filteredReviewExportHistory.value.length) return "班次统计：暂无";
  const counter = new Map<string, number>();
  for (const item of filteredReviewExportHistory.value) {
    const key = String(item.shiftLabel || "未知班次");
    counter.set(key, (counter.get(key) || 0) + 1);
  }
  const text = [...counter.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([k, v]) => `${k}=${v}`)
    .join("；");
  return `班次统计：${text}`;
});

const reviewExportOrganizationTop1Text = computed(() => {
  if (!filteredReviewExportHistory.value.length) return "组织Top1：暂无";
  const counter = new Map<string, number>();
  for (const item of filteredReviewExportHistory.value) {
    const key = String(item.organization || "all");
    counter.set(key, (counter.get(key) || 0) + 1);
  }
  const top = [...counter.entries()].sort((a, b) => b[1] - a[1])[0];
  if (!top) return "组织Top1：暂无";
  return `组织Top1：${top[0]}（${top[1]} 次）`;
});

function copyReviewExportHistoryCsv() {
  const header = "generated_at,shift_key,shift_label,window_label,alarm_type,organization";
  const rows = filteredReviewExportHistory.value.map((item) => {
    const generatedAt = String(item.generatedAt || "").replace(/"/g, '""');
    const shiftKey = String(item.shiftKey || "").replace(/"/g, '""');
    const shiftLabel = String(item.shiftLabel || "").replace(/"/g, '""');
    const windowLabel = String(item.windowLabel || "").replace(/"/g, '""');
    const alarmType = String(item.alarmType || "").replace(/"/g, '""');
    const organization = String(item.organization || "").replace(/"/g, '""');
    return `"${generatedAt}","${shiftKey}","${shiftLabel}","${windowLabel}","${alarmType}","${organization}"`;
  });
  const csv = [header, ...rows].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => uni.showToast({ title: "导出历史CSV已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowSummary() {
  const text = [
    "复盘导出窗口摘要",
    reviewExportWindowSummaryText.value,
    reviewExportWindowHitRateText.value,
    reviewExportWindowIntensityText.value,
    reviewExportWindowModeText.value,
    reviewExportShiftTop1Text.value,
    reviewExportOrganizationTop1Text.value
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "窗口摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function persistReviewExportWindowRelaxHistory() {
  uni.setStorageSync(REVIEW_EXPORT_WINDOW_RELAX_KEY, {
    action: reviewExportWindowLastRelaxAction.value,
    at: reviewExportWindowLastRelaxAt.value
  });
}

function copyReviewExportWindowCsv() {
  const header = "generated_at,shift_key,shift_label,window_label,alarm_type,organization";
  const rows = filteredReviewExportHistory.value.map((item) => {
    const generatedAt = String(item.generatedAt || "").replace(/"/g, '""');
    const shiftKey = String(item.shiftKey || "").replace(/"/g, '""');
    const shiftLabel = String(item.shiftLabel || "").replace(/"/g, '""');
    const windowLabel = String(item.windowLabel || "").replace(/"/g, '""');
    const alarmType = String(item.alarmType || "").replace(/"/g, '""');
    const organization = String(item.organization || "").replace(/"/g, '""');
    return `"${generatedAt}","${shiftKey}","${shiftLabel}","${windowLabel}","${alarmType}","${organization}"`;
  });
  const csv = [header, ...rows].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => uni.showToast({ title: "窗口CSV已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function onReviewExportWindowFilterChange(index: number) {
  reviewExportWindowFilter.value = index === 1 ? "24h" : index === 2 ? "7d" : "all";
  persistReviewExportWindowAction("已手动切换窗口", "manual_filter");
}

function resetReviewExportWindowFilter() {
  reviewExportWindowFilter.value = "all";
  persistReviewExportWindowAction("已重置窗口：全部记录", "reset");
  uni.showToast({ title: "已恢复全部窗口", icon: "none" });
}

function relaxReviewExportWindowFilter() {
  let hint = "当前已是最宽窗口";
  if (reviewExportWindowFilter.value === "24h") {
    reviewExportWindowFilter.value = "7d";
    hint = "已放宽窗口：近24小时 -> 近7天";
  } else if (reviewExportWindowFilter.value === "7d") {
    reviewExportWindowFilter.value = "all";
    hint = "已放宽窗口：近7天 -> 全部记录";
  }
  reviewExportWindowLastRelaxAction.value = hint;
  reviewExportWindowLastRelaxAt.value = new Date().toISOString();
  persistReviewExportWindowRelaxHistory();
  persistReviewExportWindowAction(hint, "relax");
  uni.showToast({ title: hint, icon: "none" });
}

function copyReviewExportWindowRelaxSummary() {
  const at = reviewExportWindowLastRelaxAt.value
    ? formatDateTime(reviewExportWindowLastRelaxAt.value)
    : "-";
  const text = [
    "窗口放宽摘要",
    reviewExportWindowModeText.value,
    reviewExportWindowRelaxQueueText.value,
    reviewExportWindowRelaxRemainingStepsText.value,
    reviewExportWindowNextRelaxStepText.value,
    `上次放宽：${reviewExportWindowLastRelaxAction.value || "无"} @ ${at}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "放宽记录已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowRelaxStateSummary() {
  const text = [
    "窗口放宽状态摘要",
    reviewExportWindowModeText.value,
    reviewExportWindowRelaxQueueText.value,
    reviewExportWindowRelaxRemainingStepsText.value,
    reviewExportWindowNextRelaxStepText.value
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "放宽状态已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function persistReviewExportWindowAction(action: string, source: string) {
  reviewExportWindowLastAction.value = action;
  reviewExportWindowLastActionSource.value = source;
  reviewExportWindowLastActionAt.value = new Date().toISOString();
  uni.setStorageSync(REVIEW_EXPORT_WINDOW_ACTION_KEY, {
    action: reviewExportWindowLastAction.value,
    source: reviewExportWindowLastActionSource.value,
    at: reviewExportWindowLastActionAt.value
  });
  const nextAudit = [
    {
      action: reviewExportWindowLastAction.value,
      source: reviewExportWindowLastActionSource.value,
      at: reviewExportWindowLastActionAt.value,
      filter: reviewExportWindowFilter.value,
      presetLabel: reviewExportWindowCurrentPresetLabel.value
    },
    ...reviewExportWindowActionAudit.value
  ].slice(0, REVIEW_EXPORT_WINDOW_ACTION_AUDIT_MAX);
  reviewExportWindowActionAudit.value = nextAudit;
  uni.setStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_KEY, nextAudit);
}

function applyReviewExportWindowPreset(presetKey: "strict" | "balanced" | "full") {
  const preset = reviewExportWindowPresets.find((x) => x.key === presetKey);
  if (!preset) return;
  reviewExportWindowFilter.value = preset.filter;
  persistReviewExportWindowAction(`已切换窗口预设：${preset.label}`, `preset_${preset.key}`);
  uni.showToast({ title: `已切换预设：${preset.label}`, icon: "none" });
}

function copyReviewExportWindowPresetSummary() {
  const at = reviewExportWindowLastActionAt.value ? formatDateTime(reviewExportWindowLastActionAt.value) : "-";
  const text = [
    "窗口预设摘要",
    `当前预设=${reviewExportWindowCurrentPresetLabel.value}`,
    reviewExportWindowSummaryText.value,
    reviewExportWindowHitRateText.value,
    reviewExportWindowIntensityText.value,
    reviewExportWindowModeText.value,
    `最近动作=${reviewExportWindowLastAction.value || "无"}`,
    `来源=${reviewExportWindowActionSourceText.value}`,
    `时间=${at}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "预设摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function clearReviewExportWindowRelaxHistory() {
  uni.showModal({
    title: "确认清理",
    content: "将清空窗口放宽记录，是否继续？",
    confirmText: "清理",
    cancelText: "取消",
    success: (res) => {
      if (!res.confirm) return;
      reviewExportWindowLastRelaxAction.value = "";
      reviewExportWindowLastRelaxAt.value = "";
      uni.removeStorageSync(REVIEW_EXPORT_WINDOW_RELAX_KEY);
      uni.showToast({ title: "已清空放宽记录", icon: "none" });
    }
  });
}

function copyReviewExportWindowActionAuditJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowFilter.value,
    current_preset: reviewExportWindowCurrentPresetLabel.value,
    audit_window_filter: reviewExportWindowActionAuditFilter.value,
    audit_window_summary: reviewExportWindowActionAuditWindowSummaryText.value,
    audit_hit_rate: reviewExportWindowActionAuditHitRateText.value,
    audit_intensity: reviewExportWindowActionAuditIntensityText.value,
    audit_mode: reviewExportWindowActionAuditModeText.value,
    audit_source_top1: reviewExportWindowActionAuditSourceTop1Text.value,
    audit_recent: reviewExportWindowActionAuditRecentText.value,
    action_audit: filteredReviewExportWindowActionAudit.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => uni.showToast({ title: "窗口动作审计JSON已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditCsv() {
  const header = "at,source,action,filter,preset_label";
  const rows = filteredReviewExportWindowActionAudit.value.map((x) => {
    const at = String(x.at || "").replace(/"/g, '""');
    const source = String(x.source || "").replace(/"/g, '""');
    const action = String(x.action || "").replace(/"/g, '""');
    const filter = String(x.filter || "").replace(/"/g, '""');
    const preset = String(x.presetLabel || "").replace(/"/g, '""');
    return `"${at}","${source}","${action}","${filter}","${preset}"`;
  });
  const csv = [header, ...rows].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => uni.showToast({ title: "窗口动作审计CSV已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditSummary() {
  const text = [
    "窗口动作审计摘要",
    reviewExportWindowActionAuditWindowSummaryText.value,
    reviewExportWindowActionAuditHitRateText.value,
    reviewExportWindowActionAuditIntensityText.value,
    reviewExportWindowActionAuditModeText.value,
    reviewExportWindowActionAuditRecentText.value,
    reviewExportWindowActionAuditSourceTop1Text.value
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "窗口动作审计摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function onReviewExportWindowActionAuditFilterChange(index: number) {
  reviewExportWindowActionAuditFilter.value = index === 1 ? "24h" : index === 2 ? "7d" : "all";
  persistReviewExportWindowActionAuditAction("已手动切换审计窗口", "manual_filter");
}

function resetReviewExportWindowActionAuditFilter() {
  reviewExportWindowActionAuditFilter.value = "all";
  persistReviewExportWindowActionAuditAction("已重置审计窗口：全部", "reset");
  uni.showToast({ title: "已恢复动作审计窗口", icon: "none" });
}

function persistReviewExportWindowActionAuditRelaxHistory() {
  uni.setStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_RELAX_KEY, {
    action: reviewExportWindowActionAuditLastRelaxAction.value,
    at: reviewExportWindowActionAuditLastRelaxAt.value
  });
}

function relaxReviewExportWindowActionAuditFilter() {
  let hint = "当前审计窗口已是最宽";
  if (reviewExportWindowActionAuditFilter.value === "24h") {
    reviewExportWindowActionAuditFilter.value = "7d";
    hint = "已放宽审计窗口：近24小时 -> 近7天";
  } else if (reviewExportWindowActionAuditFilter.value === "7d") {
    reviewExportWindowActionAuditFilter.value = "all";
    hint = "已放宽审计窗口：近7天 -> 全部";
  }
  reviewExportWindowActionAuditLastRelaxAction.value = hint;
  reviewExportWindowActionAuditLastRelaxAt.value = new Date().toISOString();
  persistReviewExportWindowActionAuditRelaxHistory();
  persistReviewExportWindowActionAuditAction(hint, "relax");
  uni.showToast({ title: hint, icon: "none" });
}

function copyReviewExportWindowActionAuditRelaxSummary() {
  const at = reviewExportWindowActionAuditLastRelaxAt.value
    ? formatDateTime(reviewExportWindowActionAuditLastRelaxAt.value)
    : "-";
  const text = [
    "动作审计窗口放宽摘要",
    reviewExportWindowActionAuditModeText.value,
    reviewExportWindowActionAuditRelaxQueueText.value,
    reviewExportWindowActionAuditRelaxRemainingStepsText.value,
    reviewExportWindowActionAuditNextRelaxStepText.value,
    `上次放宽：${reviewExportWindowActionAuditLastRelaxAction.value || "无"} @ ${at}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "审计放宽摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function clearReviewExportWindowActionAuditRelaxHistory() {
  uni.showModal({
    title: "确认清理",
    content: "将清空审计窗口放宽记录，是否继续？",
    confirmText: "清理",
    cancelText: "取消",
    success: (res) => {
      if (!res.confirm) return;
      reviewExportWindowActionAuditLastRelaxAction.value = "";
      reviewExportWindowActionAuditLastRelaxAt.value = "";
      uni.removeStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_RELAX_KEY);
      uni.showToast({ title: "已清空审计放宽记录", icon: "none" });
    }
  });
}

function persistReviewExportWindowActionAuditAction(action: string, source: string) {
  reviewExportWindowActionAuditLastAction.value = action;
  reviewExportWindowActionAuditLastActionSource.value = source;
  reviewExportWindowActionAuditLastActionAt.value = new Date().toISOString();
  uni.setStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_ACTION_KEY, {
    action: reviewExportWindowActionAuditLastAction.value,
    source: reviewExportWindowActionAuditLastActionSource.value,
    at: reviewExportWindowActionAuditLastActionAt.value
  });
}

function applyReviewExportWindowActionAuditPreset(presetKey: "strict" | "balanced" | "full") {
  const preset = reviewExportWindowActionAuditPresets.find((x) => x.key === presetKey);
  if (!preset) return;
  reviewExportWindowActionAuditFilter.value = preset.filter;
  const nextHistory = [
    { presetKey: preset.key, presetLabel: preset.label, at: new Date().toISOString() },
    ...reviewExportWindowActionAuditPresetHistory.value
  ].slice(0, REVIEW_EXPORT_WINDOW_ACTION_AUDIT_MAX);
  reviewExportWindowActionAuditPresetHistory.value = nextHistory;
  uni.setStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_KEY, nextHistory);
  persistReviewExportWindowActionAuditAction(`已切换审计预设：${preset.label}`, `preset_${preset.key}`);
  uni.showToast({ title: `已切换审计预设：${preset.label}`, icon: "none" });
}

function copyReviewExportWindowActionAuditPresetSummary() {
  const at = reviewExportWindowActionAuditLastActionAt.value
    ? formatDateTime(reviewExportWindowActionAuditLastActionAt.value)
    : "-";
  const text = [
    "动作审计预设摘要",
    `当前预设=${reviewExportWindowActionAuditCurrentPresetLabel.value}`,
    reviewExportWindowActionAuditWindowSummaryText.value,
    reviewExportWindowActionAuditHitRateText.value,
    reviewExportWindowActionAuditIntensityText.value,
    reviewExportWindowActionAuditModeText.value,
    `最近动作=${reviewExportWindowActionAuditLastAction.value || "无"}`,
    `来源=${reviewExportWindowActionAuditActionSourceText.value}`,
    `时间=${at}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "审计预设摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistorySummary() {
  const text = [
    "审计预设历史摘要",
    reviewExportWindowActionAuditPresetHistoryWindowSummaryText.value,
    reviewExportWindowActionAuditPresetHistoryHitRateText.value,
    reviewExportWindowActionAuditPresetHistoryIntensityText.value,
    reviewExportWindowActionAuditPresetHistoryModeText.value,
    reviewExportWindowActionAuditPresetTop1Text.value,
    reviewExportWindowActionAuditPresetRecentText.value
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "审计预设历史已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryCsv() {
  const header = "at,preset_key,preset_label";
  const rows = filteredReviewExportWindowActionAuditPresetHistory.value.map((x) => {
    const at = String(x.at || "").replace(/"/g, '""');
    const presetKey = String(x.presetKey || "").replace(/"/g, '""');
    const presetLabel = String(x.presetLabel || "").replace(/"/g, '""');
    return `"${at}","${presetKey}","${presetLabel}"`;
  });
  const csv = [header, ...rows].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => uni.showToast({ title: "审计预设历史CSV已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function onReviewExportWindowActionAuditPresetHistoryFilterChange(index: number) {
  reviewExportWindowActionAuditPresetHistoryFilter.value = index === 1 ? "24h" : index === 2 ? "7d" : "all";
  persistReviewExportWindowActionAuditPresetHistoryAction("已手动切换预设历史窗口", "manual_filter");
}

function resetReviewExportWindowActionAuditPresetHistoryFilter() {
  reviewExportWindowActionAuditPresetHistoryFilter.value = "all";
  persistReviewExportWindowActionAuditPresetHistoryAction("已重置预设历史窗口：全部", "reset");
  uni.showToast({ title: "已恢复审计预设历史窗口", icon: "none" });
}

function persistReviewExportWindowActionAuditPresetHistoryRelaxHistory() {
  uni.setStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_RELAX_KEY, {
    action: reviewExportWindowActionAuditPresetHistoryLastRelaxAction.value,
    at: reviewExportWindowActionAuditPresetHistoryLastRelaxAt.value
  });
}

function relaxReviewExportWindowActionAuditPresetHistoryFilter() {
  let hint = "当前预设历史窗口已是最宽";
  if (reviewExportWindowActionAuditPresetHistoryFilter.value === "24h") {
    reviewExportWindowActionAuditPresetHistoryFilter.value = "7d";
    hint = "已放宽预设历史窗口：近24小时 -> 近7天";
  } else if (reviewExportWindowActionAuditPresetHistoryFilter.value === "7d") {
    reviewExportWindowActionAuditPresetHistoryFilter.value = "all";
    hint = "已放宽预设历史窗口：近7天 -> 全部";
  }
  reviewExportWindowActionAuditPresetHistoryLastRelaxAction.value = hint;
  reviewExportWindowActionAuditPresetHistoryLastRelaxAt.value = new Date().toISOString();
  persistReviewExportWindowActionAuditPresetHistoryRelaxHistory();
  persistReviewExportWindowActionAuditPresetHistoryAction(hint, "relax");
  uni.showToast({ title: hint, icon: "none" });
}

function copyReviewExportWindowActionAuditPresetHistoryRelaxSummary() {
  const at = reviewExportWindowActionAuditPresetHistoryLastRelaxAt.value
    ? formatDateTime(reviewExportWindowActionAuditPresetHistoryLastRelaxAt.value)
    : "-";
  const text = [
    "审计预设历史放宽摘要",
    reviewExportWindowActionAuditPresetHistoryModeText.value,
    reviewExportWindowActionAuditPresetHistoryHitRateText.value,
    reviewExportWindowActionAuditPresetHistoryIntensityText.value,
    reviewExportWindowActionAuditPresetHistoryRelaxQueueText.value,
    reviewExportWindowActionAuditPresetHistoryRelaxRemainingStepsText.value,
    reviewExportWindowActionAuditPresetHistoryNextRelaxStepText.value,
    `上次放宽：${reviewExportWindowActionAuditPresetHistoryLastRelaxAction.value || "无"} @ ${at}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "预设历史放宽摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function persistReviewExportWindowActionAuditPresetHistoryAction(action: string, source: string) {
  const at = new Date().toISOString();
  reviewExportWindowActionAuditPresetHistoryLastAction.value = action;
  reviewExportWindowActionAuditPresetHistoryLastActionSource.value = source;
  reviewExportWindowActionAuditPresetHistoryLastActionAt.value = at;
  uni.setStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_KEY, {
    action: reviewExportWindowActionAuditPresetHistoryLastAction.value,
    source: reviewExportWindowActionAuditPresetHistoryLastActionSource.value,
    at: reviewExportWindowActionAuditPresetHistoryLastActionAt.value
  });
  const nextAudit = [
    {
      action,
      source,
      at,
      filter: reviewExportWindowActionAuditPresetHistoryFilter.value,
      presetLabel: reviewExportWindowActionAuditPresetHistoryCurrentPresetLabel.value
    },
    ...reviewExportWindowActionAuditPresetHistoryActionAudit.value
  ].slice(0, REVIEW_EXPORT_WINDOW_ACTION_AUDIT_MAX);
  reviewExportWindowActionAuditPresetHistoryActionAudit.value = nextAudit;
  uni.setStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_KEY, nextAudit);
}

function applyReviewExportWindowActionAuditPresetHistoryPreset(presetKey: "strict" | "balanced" | "full") {
  const preset = reviewExportWindowActionAuditPresetHistoryPresets.find((x) => x.key === presetKey);
  if (!preset) return;
  reviewExportWindowActionAuditPresetHistoryFilter.value = preset.filter;
  persistReviewExportWindowActionAuditPresetHistoryAction(`已切换预设历史窗口预设：${preset.label}`, `preset_${preset.key}`);
  uni.showToast({ title: `已切换预设历史预设：${preset.label}`, icon: "none" });
}

function copyReviewExportWindowActionAuditPresetHistoryPresetSummary() {
  const at = reviewExportWindowActionAuditPresetHistoryLastActionAt.value
    ? formatDateTime(reviewExportWindowActionAuditPresetHistoryLastActionAt.value)
    : "-";
  const text = [
    "审计预设历史窗口预设摘要",
    `当前预设=${reviewExportWindowActionAuditPresetHistoryCurrentPresetLabel.value}`,
    reviewExportWindowActionAuditPresetHistoryWindowSummaryText.value,
    reviewExportWindowActionAuditPresetHistoryHitRateText.value,
    reviewExportWindowActionAuditPresetHistoryIntensityText.value,
    reviewExportWindowActionAuditPresetHistoryModeText.value,
    `最近动作=${reviewExportWindowActionAuditPresetHistoryLastAction.value || "无"}`,
    `来源=${reviewExportWindowActionAuditPresetHistoryActionSourceText.value}`,
    `时间=${at}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "预设历史预设摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditFilter.value,
    audit_window_filter: reviewExportWindowActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditCurrentPresetLabel.value,
    audit_window_summary: reviewExportWindowActionAuditPresetHistoryActionAuditWindowSummaryText.value,
    audit_hit_rate: reviewExportWindowActionAuditPresetHistoryActionAuditHitRateText.value,
    audit_intensity: reviewExportWindowActionAuditPresetHistoryActionAuditIntensityText.value,
    audit_mode: reviewExportWindowActionAuditPresetHistoryActionAuditModeText.value,
    audit_source_top1: reviewExportWindowActionAuditPresetHistoryActionAuditSourceTop1Text.value,
    audit_recent: reviewExportWindowActionAuditPresetHistoryActionAuditRecentText.value,
    action_audit: filteredReviewExportWindowActionAuditPresetHistoryActionAudit.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => uni.showToast({ title: "预设历史动作审计JSON已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditCsv() {
  const header = "at,source,action,filter,preset_label";
  const rows = filteredReviewExportWindowActionAuditPresetHistoryActionAudit.value.map((x) => {
    const at = String(x.at || "").replace(/"/g, '""');
    const source = String(x.source || "").replace(/"/g, '""');
    const action = String(x.action || "").replace(/"/g, '""');
    const filter = String(x.filter || "").replace(/"/g, '""');
    const preset = String(x.presetLabel || "").replace(/"/g, '""');
    return `"${at}","${source}","${action}","${filter}","${preset}"`;
  });
  const csv = [header, ...rows].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => uni.showToast({ title: "预设历史动作审计CSV已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditSummary() {
  const text = [
    "预设历史动作审计摘要",
    reviewExportWindowActionAuditPresetHistoryActionAuditWindowSummaryText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditHitRateText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditIntensityText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditModeText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditSourceTop1Text.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditRecentText.value
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "预设历史动作审计摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function applyReviewExportWindowActionAuditPresetHistoryActionAuditPreset(presetKey: "strict" | "balanced" | "full") {
  const preset = reviewExportWindowActionAuditPresetHistoryPresets.find((x) => x.key === presetKey);
  if (!preset) return;
  reviewExportWindowActionAuditPresetHistoryActionAuditFilter.value = preset.filter;
  const nextHistory = [
    { presetKey: preset.key, presetLabel: preset.label, at: new Date().toISOString() },
    ...reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistory.value
  ].slice(0, REVIEW_EXPORT_WINDOW_ACTION_AUDIT_MAX);
  reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistory.value = nextHistory;
  uni.setStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_KEY, nextHistory);
  persistReviewExportWindowActionAuditPresetHistoryAction(
    `已切换预设历史动作审计预设：${preset.label}`,
    `action_audit_preset_${preset.key}`
  );
  uni.showToast({ title: `已切换预设动作预设：${preset.label}`, icon: "none" });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetSummary() {
  const at = reviewExportWindowActionAuditPresetHistoryLastActionAt.value
    ? formatDateTime(reviewExportWindowActionAuditPresetHistoryLastActionAt.value)
    : "-";
  const text = [
    "预设历史动作审计预设摘要",
    `当前预设=${reviewExportWindowActionAuditPresetHistoryActionAuditCurrentPresetLabel.value}`,
    reviewExportWindowActionAuditPresetHistoryActionAuditWindowSummaryText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditHitRateText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditIntensityText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditModeText.value,
    `最近动作=${reviewExportWindowActionAuditPresetHistoryLastAction.value || "无"}`,
    `来源=${reviewExportWindowActionAuditPresetHistoryActionSourceText.value}`,
    `时间=${at}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "预设动作预设摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistorySummary() {
  const text = [
    "预设动作预设历史摘要",
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryWindowSummaryText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryHitRateText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryIntensityText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryModeText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetTop1Text.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetRecentText.value
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "预设动作预设历史已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryCsv() {
  const header = "at,preset_key,preset_label";
  const rows = filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistory.value.map((x) => {
    const at = String(x.at || "").replace(/"/g, '""');
    const presetKey = String(x.presetKey || "").replace(/"/g, '""');
    const presetLabel = String(x.presetLabel || "").replace(/"/g, '""');
    return `"${at}","${presetKey}","${presetLabel}"`;
  });
  const csv = [header, ...rows].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => uni.showToast({ title: "预设动作预设历史CSV已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function resetReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryFilter() {
  reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryFilter.value = "all";
  persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryAction("已重置预设动作预设历史窗口：全部", "reset");
  uni.showToast({ title: "已恢复预设动作预设历史窗口", icon: "none" });
}

function persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryRelaxHistory() {
  uni.setStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_RELAX_KEY, {
    action: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAction.value,
    at: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAt.value
  });
}

function relaxReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryFilter() {
  let hint = "当前预设动作预设历史窗口已是最宽";
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryFilter.value === "24h") {
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryFilter.value = "7d";
    hint = "已放宽预设动作预设历史窗口：近24小时 -> 近7天";
  } else if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryFilter.value === "7d") {
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryFilter.value = "all";
    hint = "已放宽预设动作预设历史窗口：近7天 -> 全部";
  }
  reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAction.value = hint;
  reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAt.value = new Date().toISOString();
  persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryRelaxHistory();
  persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryAction(hint, "relax");
  uni.showToast({ title: hint, icon: "none" });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryRelaxSummary() {
  const at = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAt.value
    ? formatDateTime(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAt.value)
    : "-";
  const text = [
    "预设动作预设历史放宽摘要",
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryHitRateText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryIntensityText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryModeText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryRelaxQueueText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryRelaxRemainingStepsText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryNextRelaxStepText.value,
    `上次放宽：${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAction.value || "无"} @ ${at}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "预设动作历史放宽已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryRelaxStateSummary() {
  const at = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAt.value
    ? formatDateTime(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAt.value)
    : "-";
  const text = [
    "预设动作预设历史放宽状态摘要",
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryRelaxStateSummaryText.value,
    `上次放宽：${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAction.value || "无"} @ ${at}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "预设动作历史放宽状态已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function clearReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryRelaxHistory() {
  uni.showModal({
    title: "确认清理",
    content: "将清空预设动作预设历史放宽记录，是否继续？",
    confirmText: "清理",
    cancelText: "取消",
    success: (res) => {
      if (!res.confirm) return;
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAction.value = "";
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAt.value = "";
      uni.removeStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_RELAX_KEY);
      uni.showToast({ title: "已清空预设动作历史放宽记录", icon: "none" });
    }
  });
}

function persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryAction(action: string, source: string) {
  const at = new Date().toISOString();
  reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryLastAction.value = action;
  reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryLastActionSource.value = source;
  reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryLastActionAt.value = at;
  uni.setStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_KEY, {
    action: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryLastAction.value,
    source: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryLastActionSource.value,
    at: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryLastActionAt.value
  });
  const nextAudit = [
    {
      action,
      source,
      at,
      filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryFilter.value
    },
    ...reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAudit.value
  ].slice(0, REVIEW_EXPORT_WINDOW_ACTION_AUDIT_MAX);
  reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAudit.value = nextAudit;
  uni.setStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_KEY, nextAudit);
}

function onReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryFilterChange(index: number) {
  reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryFilter.value = index === 1 ? "24h" : index === 2 ? "7d" : "all";
  persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryAction("已手动切换预设动作预设历史窗口", "manual_filter");
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionSummary() {
  const at = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryLastActionAt.value
    ? formatDateTime(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryLastActionAt.value)
    : "-";
  const text = [
    "预设动作预设历史动作摘要",
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryModeText.value,
    `最近动作=${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryLastAction.value || "无"}`,
    `来源=${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionSourceText.value}`,
    `时间=${at}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "预设动作历史动作摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditSummary() {
  const text = [
    "预设动作预设历史动作审计摘要",
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditWindowSummaryText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditHitRateText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditIntensityText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditModeText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditSourceTop1Text.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditRecentText.value
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "预设动作历史动作审计摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditRelaxSummary() {
  const at = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastRelaxAt.value
    ? formatDateTime(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastRelaxAt.value)
    : "-";
  const text = [
    "预设动作历史动作审计放宽摘要",
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditHitRateText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditIntensityText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditModeText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditRelaxQueueText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditRelaxRemainingStepsText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditNextRelaxStepText.value,
    `上次放宽：${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastRelaxAction.value || "无"} @ ${at}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "预设动作历史动作审计放宽已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditRelaxStateSummary() {
  const at = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastRelaxAt.value
    ? formatDateTime(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastRelaxAt.value)
    : "-";
  const text = [
    "预设动作历史动作审计放宽状态摘要",
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditRelaxStateSummaryText.value,
    `上次放宽：${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastRelaxAction.value || "无"} @ ${at}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "预设动作历史动作审计放宽状态已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function clearReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditRelaxHistory() {
  uni.showModal({
    title: "确认清理",
    content: "将清空预设动作历史动作审计放宽记录，是否继续？",
    confirmText: "清理",
    cancelText: "取消",
    success: (res) => {
      if (!res.confirm) return;
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastRelaxAction.value = "";
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastRelaxAt.value = "";
      uni.removeStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_RELAX_KEY);
      uni.showToast({ title: "已清空预设动作历史动作审计放宽", icon: "none" });
    }
  });
}

function resetReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter() {
  reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value = "all";
  persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
    "已重置预设动作历史动作审计窗口：全部",
    "reset"
  );
  uni.showToast({ title: "已恢复预设动作历史动作审计窗口", icon: "none" });
}

function persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditRelaxHistory() {
  uni.setStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_RELAX_KEY, {
    action: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastRelaxAction.value,
    at: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastRelaxAt.value
  });
}

function onReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilterChange(index: number) {
  reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value =
    index === 1 ? "24h" : index === 2 ? "7d" : "all";
  persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
    "已手动切换预设动作历史动作审计窗口",
    "preset_history_manual_filter"
  );
}

function relaxReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter() {
  let hint = "当前预设动作历史动作审计窗口已是最宽";
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "24h") {
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value = "7d";
    hint = "已放宽预设动作历史动作审计窗口：近24小时 -> 近7天";
  } else if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "7d") {
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value = "all";
    hint = "已放宽预设动作历史动作审计窗口：近7天 -> 全部";
  }
  reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastRelaxAction.value = hint;
  reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastRelaxAt.value = new Date().toISOString();
  persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditRelaxHistory();
  persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(hint, "relax");
  uni.showToast({ title: hint, icon: "none" });
}

function persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(action: string, source: string) {
  const at = new Date().toISOString();
  reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastAction.value = action;
  reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastActionSource.value = source;
  reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastActionAt.value = at;
  uni.setStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_ACTION_KEY, {
    action: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastAction.value,
    source: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastActionSource.value,
    at: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastActionAt.value
  });
  const nextAudit = [
    {
      action,
      source,
      at,
      filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
      presetLabel: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditCurrentPresetLabel.value
    },
    ...reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAudit.value
  ].slice(0, REVIEW_EXPORT_WINDOW_ACTION_AUDIT_MAX);
  reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAudit.value = nextAudit;
  uni.setStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_KEY, nextAudit);
}

function applyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPreset(
  presetKey: "strict" | "balanced" | "full"
) {
  const preset = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresets.find((x) => x.key === presetKey);
  if (!preset) return;
  reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value = preset.filter;
  const nextHistory = [
    { presetKey: preset.key, presetLabel: preset.label, at: new Date().toISOString() },
    ...reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistory.value
  ].slice(0, REVIEW_EXPORT_WINDOW_ACTION_AUDIT_MAX);
  reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistory.value = nextHistory;
  uni.setStorageSync(
    REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_KEY,
    nextHistory
  );
  persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
    `已切换预设动作历史动作审计预设：${preset.label}`,
    `preset_${preset.key}`
  );
  uni.showToast({ title: `已切换预设动作历史动作审计预设：${preset.label}`, icon: "none" });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetSummary() {
  const at = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastActionAt.value
    ? formatDateTime(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastActionAt.value)
    : "-";
  const text = [
    "预设动作历史动作审计预设摘要",
    `当前预设=${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditCurrentPresetLabel.value}`,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetWindowSummaryText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHitRateText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetIntensityText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetModeText.value,
    `最近动作=${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastAction.value || "无"}`,
    `来源=${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditActionSourceText.value}`,
    `时间=${at}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "预设动作历史动作审计预设已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistorySummary() {
  const text = [
    "预设动作历史动作审计预设历史摘要",
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetWindowSummaryText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHitRateText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetIntensityText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetModeText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetTop1Text.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetRecentText.value
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "预设动作历史动作审计预设历史已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryCsv() {
  const header = "at,preset_key,preset_label";
  const rows = filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistory.value.map((x) => {
    const at = String(x.at || "").replace(/"/g, '""');
    const presetKey = String(x.presetKey || "").replace(/"/g, '""');
    const presetLabel = String(x.presetLabel || "").replace(/"/g, '""');
    return `"${at}","${presetKey}","${presetLabel}"`;
  });
  const csv = [header, ...rows].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => uni.showToast({ title: "预设动作历史动作审计预设CSV已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    preset_window_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditCurrentPresetLabel.value,
    preset_window_summary: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetWindowSummaryText.value,
    preset_hit_rate: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHitRateText.value,
    preset_intensity: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetIntensityText.value,
    preset_mode: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetModeText.value,
    preset_top1: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetTop1Text.value,
    preset_recent: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetRecentText.value,
    preset_history: filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistory.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => uni.showToast({ title: "预设动作历史动作审计预设JSON已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryRelaxHistory() {
  uni.setStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_RELAX_KEY, {
    action: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAction.value,
    at: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAt.value
  });
}

function relaxReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistory() {
  let hint = "当前预设动作历史动作审计预设历史窗口已是最宽";
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "24h") {
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value = "7d";
    hint = "已放宽预设动作历史动作审计预设历史窗口：近24小时 -> 近7天";
  } else if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "7d") {
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value = "all";
    hint = "已放宽预设动作历史动作审计预设历史窗口：近7天 -> 全部";
  }
  reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAction.value = hint;
  reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAt.value = new Date().toISOString();
  persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryRelaxHistory();
  persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(hint, "preset_history_relax");
  uni.showToast({ title: hint, icon: "none" });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryRelaxSummary() {
  const at = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAt.value
    ? formatDateTime(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAt.value)
    : "-";
  const text = [
    "预设动作历史动作审计预设历史放宽摘要",
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetModeText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryRelaxQueueText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryRelaxRemainingStepsText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryNextRelaxStepText.value,
    `上次放宽：${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAction.value || "无"} @ ${at}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "预设动作历史动作审计预设历史放宽已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryRelaxStateSummary() {
  const at = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAt.value
    ? formatDateTime(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAt.value)
    : "-";
  const text = [
    "预设动作历史动作审计预设历史放宽状态摘要",
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryRelaxStateSummaryText.value,
    `上次放宽：${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAction.value || "无"} @ ${at}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "预设动作历史动作审计预设历史放宽状态已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceSummary() {
  uni.setClipboardData({
    data: `预设动作历史动作审计预设历史治理摘要：${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceSummaryText.value}`,
    success: () => uni.showToast({ title: "预设动作历史动作审计预设历史治理摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceAuditSummary() {
  const text = [
    "预设动作历史动作审计预设历史治理审计摘要",
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceWindowSummaryText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceHitRateText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceIntensityText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceModeText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceSourceTop1Text.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceRecentText.value
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制预设动作历史动作审计预设历史治理审计摘要",
        "governance_export_summary"
      );
      uni.showToast({ title: "预设动作历史动作审计预设历史治理审计已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceAuditJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    governance_window_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    governance_window_summary: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceWindowSummaryText.value,
    governance_hit_rate: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceHitRateText.value,
    governance_intensity: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceIntensityText.value,
    governance_mode: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceModeText.value,
    governance_source_top1: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceSourceTop1Text.value,
    governance_recent: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceRecentText.value,
    governance_audit: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceAudit.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制预设动作历史动作审计预设历史治理JSON",
        "governance_export_json"
      );
      uni.showToast({ title: "预设动作历史动作审计预设历史治理JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceAuditCsv() {
  const header = "generated_at,current_filter,governance_window_filter,at,source,source_text,action,filter,preset_label";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(/"/g, '""');
  const governanceWindowFilter = currentFilter;
  const rows = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceAudit.value.map((x) => {
    const at = String(x.at || "").replace(/"/g, '""');
    const source = String(x.source || "").replace(/"/g, '""');
    const sourceText = formatReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditActionSource(String(x.source || "")).replace(/"/g, '""');
    const action = String(x.action || "").replace(/"/g, '""');
    const filter = String(x.filter || "").replace(/"/g, '""');
    const preset = String(x.presetLabel || "").replace(/"/g, '""');
    return `"${generatedAt}","${currentFilter}","${governanceWindowFilter}","${at}","${source}","${sourceText}","${action}","${filter}","${preset}"`;
  });
  const csv = [header, ...rows].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制预设动作历史动作审计预设历史治理CSV",
        "governance_export_csv"
      );
      uni.showToast({ title: "预设动作历史动作审计预设历史治理CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function onReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceFilterChange(index: number) {
  reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value =
    index === 1 ? "24h" : index === 2 ? "7d" : "all";
  persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
    "已手动切换预设动作历史动作审计预设历史治理窗口",
    "governance_manual_filter"
  );
}

function applyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePreset(
  presetKey: "strict" | "balanced" | "full"
) {
  const preset = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresets.find((x) => x.key === presetKey);
  if (!preset) return;
  reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value = preset.filter;
  const nextHistory = [
    { presetKey: preset.key, presetLabel: preset.label, at: new Date().toISOString() },
    ...reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistory.value
  ].slice(0, REVIEW_EXPORT_WINDOW_ACTION_AUDIT_MAX);
  reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistory.value = nextHistory;
  uni.setStorageSync(
    REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_GOVERNANCE_PRESET_HISTORY_KEY,
    nextHistory
  );
  persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
    `已切换预设动作历史动作审计预设历史治理预设：${preset.label}`,
    `governance_preset_${preset.key}`
  );
  uni.showToast({ title: `已切换治理预设：${preset.label}`, icon: "none" });
}

function relaxReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceWindow() {
  let hint = "当前预设动作历史动作审计预设历史治理窗口已是最宽";
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "24h") {
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value = "7d";
    hint = "已放宽预设动作历史动作审计预设历史治理窗口：近24小时 -> 近7天";
  } else if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "7d") {
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value = "all";
    hint = "已放宽预设动作历史动作审计预设历史治理窗口：近7天 -> 全部";
  }
  reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastRelaxAction.value = hint;
  reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastRelaxAt.value = new Date().toISOString();
  persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditRelaxHistory();
  persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(hint, "governance_relax");
  uni.showToast({ title: hint, icon: "none" });
}

function resetReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceWindow() {
  reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value = "all";
  persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
    "已重置预设动作历史动作审计预设历史治理窗口：全部",
    "governance_reset"
  );
  uni.showToast({ title: "已重置预设动作历史动作审计预设历史治理窗口", icon: "none" });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceRelaxStateSummary() {
  const at = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastRelaxAt.value
    ? formatDateTime(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastRelaxAt.value)
    : "-";
  const text = [
    "预设动作历史动作审计预设历史治理放宽状态摘要",
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceRelaxStateText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceRelaxQueueText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceRelaxRemainingStepsText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceNextRelaxStepText.value,
    `上次放宽：${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastRelaxAction.value || "无"} @ ${at}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "预设动作历史动作审计预设历史治理放宽状态已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetSummary() {
  const at = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastActionAt.value
    ? formatDateTime(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastActionAt.value)
    : "-";
  const text = [
    "预设动作历史动作审计预设历史治理预设摘要",
    `当前预设=${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value}`,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceWindowSummaryText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceHitRateText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceIntensityText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceModeText.value,
    `最近动作=${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastAction.value || "无"}`,
    `来源=${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditActionSourceText.value}`,
    `时间=${at}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "预设动作历史动作审计预设历史治理预设已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistorySummary() {
  const text = [
    "预设动作历史动作审计预设历史治理预设历史摘要",
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetWindowSummaryText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHitRateText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetIntensityText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetModeText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetTop1Text.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetRecentText.value
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制预设动作历史动作审计预设历史治理预设历史摘要",
        "governance_preset_history_export_summary"
      );
      uni.showToast({ title: "预设动作历史动作审计预设历史治理预设历史已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    preset_window_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    preset_window_summary: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetWindowSummaryText.value,
    preset_hit_rate: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHitRateText.value,
    preset_intensity: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetIntensityText.value,
    preset_mode: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetModeText.value,
    preset_top1: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetTop1Text.value,
    preset_recent: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetRecentText.value,
    preset_history: filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistory.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制预设动作历史动作审计预设历史治理预设历史JSON",
        "governance_preset_history_export_json"
      );
      uni.showToast({ title: "预设动作历史动作审计预设历史治理预设JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryRelaxHistory() {
  uni.setStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_GOVERNANCE_PRESET_HISTORY_RELAX_KEY, {
    action: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryLastRelaxAction.value,
    at: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryLastRelaxAt.value
  });
}

function relaxReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistory() {
  let hint = "当前预设动作历史动作审计预设历史治理预设历史窗口已是最宽";
  if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "24h") {
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value = "7d";
    hint = "已放宽预设动作历史动作审计预设历史治理预设历史窗口：近24小时 -> 近7天";
  } else if (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value === "7d") {
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value = "all";
    hint = "已放宽预设动作历史动作审计预设历史治理预设历史窗口：近7天 -> 全部";
  }
  reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryLastRelaxAction.value = hint;
  reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryLastRelaxAt.value = new Date().toISOString();
  persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryRelaxHistory();
  persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(hint, "governance_preset_history_relax");
  uni.showToast({ title: hint, icon: "none" });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryRelaxStateSummary() {
  const at = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryLastRelaxAt.value
    ? formatDateTime(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryLastRelaxAt.value)
    : "-";
  const text = [
    "预设动作历史动作审计预设历史治理预设历史放宽状态摘要",
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryRelaxStateText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryRelaxQueueText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryRelaxRemainingStepsText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryNextRelaxStepText.value,
    `上次放宽：${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryLastRelaxAction.value || "无"} @ ${at}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制预设动作历史动作审计预设历史治理预设历史放宽状态",
        "governance_preset_history_export_relax_state"
      );
      uni.showToast({ title: "预设动作历史动作审计预设历史治理预设历史放宽状态已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryWindowStateSummary() {
  const at = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastActionAt.value
    ? formatDateTime(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastActionAt.value)
    : "-";
  const text = [
    "预设动作历史动作审计预设历史治理预设历史窗口状态摘要",
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetWindowSummaryText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHitRateText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetIntensityText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetModeText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetTop1Text.value,
    `最近动作=${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastAction.value || "无"}`,
    `来源=${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditActionSourceText.value}`,
    `时间=${at}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制预设动作历史动作审计预设历史治理预设历史窗口状态",
        "governance_preset_history_export_state"
      );
      uni.showToast({ title: "预设动作历史动作审计预设历史治理预设历史窗口状态已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function resetReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryWindow() {
  reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value = "all";
  reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryLastRelaxAction.value = "";
  reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryLastRelaxAt.value = "";
  uni.removeStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_GOVERNANCE_PRESET_HISTORY_RELAX_KEY);
  persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
    "已重置预设动作历史动作审计预设历史治理预设历史窗口：全部",
    "governance_preset_history_reset"
  );
  uni.showToast({ title: "已重置预设动作历史动作审计预设历史治理预设历史窗口", icon: "none" });
}

function clearReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryRelaxHistory() {
  uni.showModal({
    title: "确认清理",
    content: "将清空预设动作历史动作审计预设历史治理预设历史放宽记录，是否继续？",
    confirmText: "清理",
    cancelText: "取消",
    success: (res) => {
      if (!res.confirm) return;
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryLastRelaxAction.value = "";
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryLastRelaxAt.value = "";
      uni.removeStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_GOVERNANCE_PRESET_HISTORY_RELAX_KEY);
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已清空预设动作历史动作审计预设历史治理预设历史放宽记录",
        "governance_preset_history_clear_relax"
      );
      uni.showToast({ title: "已清空预设动作历史动作审计预设历史治理预设历史放宽", icon: "none" });
    }
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryCsv() {
  const header = "generated_at,current_filter,current_preset,at,preset_key,preset_label";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(/"/g, '""');
  const currentPreset = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || "").replace(/"/g, '""');
  const rows = filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistory.value.map((x) => {
    const at = String(x.at || "").replace(/"/g, '""');
    const presetKey = String(x.presetKey || "").replace(/"/g, '""');
    const presetLabel = String(x.presetLabel || "").replace(/"/g, '""');
    return `"${generatedAt}","${currentFilter}","${currentPreset}","${at}","${presetKey}","${presetLabel}"`;
  });
  const csv = [header, ...rows].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制预设动作历史动作审计预设历史治理预设历史CSV",
        "governance_preset_history_export_csv"
      );
      uni.showToast({ title: "预设动作历史动作审计预设历史治理预设CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditSummary() {
  uni.setClipboardData({
    data: `治理预设历史审计摘要：${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditSummaryText.value}`,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计摘要",
        "governance_preset_history_audit_export_summary"
      );
      uni.showToast({ title: "治理预设历史审计摘要已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionSummary() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionSummaryText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作摘要",
        "governance_preset_history_audit_export_action"
      );
      uni.showToast({ title: "治理预设历史审计动作摘要已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionJson() {
  const row = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditLastActionItem.value;
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    action_summary: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionSummaryText.value,
    action_latest: row || null
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作JSON",
        "governance_preset_history_audit_export_action_json"
      );
      uni.showToast({ title: "治理预设历史审计动作JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionCsv() {
  const header = "generated_at,current_filter,at,source,source_text,action,filter,preset_label";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const row = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditLastActionItem.value;
  const rows = row
    ? [
        `"${generatedAt}","${currentFilter}","${String(row.at || "").replace(/"/g, '""')}","${String(row.source || "").replace(/"/g, '""')}","${formatReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditActionSource(String(row.source || "")).replace(/"/g, '""')}","${String(row.action || "").replace(/"/g, '""')}","${String(row.filter || "").replace(/"/g, '""')}","${String(row.presetLabel || "").replace(/"/g, '""')}"`
      ]
    : [];
  const csv = [header, ...rows].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作CSV",
        "governance_preset_history_audit_export_action_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackage() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包",
        "governance_preset_history_audit_export_action_package"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageState() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageStateText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包状态",
        "governance_preset_history_audit_export_action_package_state"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包状态已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    package_state: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageStateText.value,
    package_text: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageText.value,
    action_latest: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditLastActionItem.value || null
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包JSON",
        "governance_preset_history_audit_export_action_package_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageCsv() {
  const header = "generated_at,current_filter,package_state,package_text";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const packageState = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageStateText.value || ""
  ).replace(/"/g, '""');
  const packageText = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${packageState}","${packageText}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包CSV",
        "governance_preset_history_audit_export_action_package_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshot() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照",
        "governance_preset_history_audit_export_action_package_snapshot"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    snapshot_text: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照JSON",
        "governance_preset_history_audit_export_action_package_snapshot_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotCsv() {
  const header = "generated_at,current_filter,current_preset,snapshot_text";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const snapshotText = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${snapshotText}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照CSV",
        "governance_preset_history_audit_export_action_package_snapshot_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigest() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotHandoverText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹",
        "governance_preset_history_audit_export_action_package_snapshot_digest"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    snapshot_digest: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestText.value,
    handover_text: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotHandoverText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestCsv() {
  const header = "generated_at,current_filter,current_preset,snapshot_digest,handover_text";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const snapshotDigest = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestText.value || ""
  ).replace(/"/g, '""');
  const handoverText = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotHandoverText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${snapshotDigest}","${handoverText}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestState() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestStateText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹状态",
        "governance_preset_history_audit_export_action_package_snapshot_digest_state"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹状态已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestPackageJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_state: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestStateText.value,
    digest_handover: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotHandoverText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接包JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_package_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接包JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestPackageCsv() {
  const header = "generated_at,current_filter,current_preset,digest_state,digest_handover";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const digestState = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestStateText.value || ""
  ).replace(/"/g, '""');
  const digestHandover = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotHandoverText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${digestState}","${digestHandover}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接包CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_package_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接包CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusion() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionCsv() {
  const header = "generated_at,current_filter,current_preset,digest_conclusion";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const digestConclusion = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${digestConclusion}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionState() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStateText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStateJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStateText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStateCsv() {
  const header = "generated_at,current_filter,current_preset,digest_conclusion_state";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const digestConclusionState = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStateText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${digestConclusionState}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackage() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageCsv() {
  const header = "generated_at,current_filter,current_preset,digest_conclusion_state_package";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const statePackage = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${statePackage}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandover() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverCsv() {
  const header = "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const handover = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${handover}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverState() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStateText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStateJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover_state:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStateText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStateCsv() {
  const header = "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover_state";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const handoverState = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStateText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${handoverState}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackage() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover_state_package:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageCsv() {
  const header = "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover_state_package";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const statePackage = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${statePackage}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusion() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover_state_package_conclusion:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionCsv() {
  const header =
    "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover_state_package_conclusion";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const conclusion = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${conclusion}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionState() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStateText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStateJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover_state_package_conclusion_state:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStateText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStateCsv() {
  const header =
    "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover_state_package_conclusion_state";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const conclusionState = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStateText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${conclusionState}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackage() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover_state_package_conclusion_state_package:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageCsv() {
  const header =
    "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover_state_package_conclusion_state_package";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const statePackage = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${statePackage}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandover() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverCsv() {
  const header =
    "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const handover = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${handover}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverState() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateCsv() {
  const header =
    "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const handoverState = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${handoverState}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackage() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageCsv() {
  const header =
    "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const handoverStatePackage = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${handoverStatePackage}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusion() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionCsv() {
  const header =
    "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const conclusion = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${conclusion}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionState() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateCsv() {
  const header =
    "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const conclusionState = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${conclusionState}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackage() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageCsv() {
  const header =
    "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const conclusionStatePackage = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${conclusionStatePackage}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandover() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverCsv() {
  const header =
    "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const conclusionStatePackageHandover = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${conclusionStatePackageHandover}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverState() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateCsv() {
  const header =
    "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const conclusionStatePackageHandoverState = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${conclusionStatePackageHandoverState}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackage() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageCsv() {
  const header =
    "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const conclusionStatePackage = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${conclusionStatePackage}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusion() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionCsv() {
  const header =
    "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const conclusion = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${conclusion}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionState() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateCsv() {
  const header =
    "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const conclusionState = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${conclusionState}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackage() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageCsv() {
  const header =
    "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const conclusionStatePackage = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${conclusionStatePackage}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandover() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverCsv() {
  const header =
    "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const conclusionStatePackageHandover = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${conclusionStatePackageHandover}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverState() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateCsv() {
  const header =
    "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const conclusionStatePackageHandoverState = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${conclusionStatePackageHandoverState}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackage() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageCsv() {
  const header =
    "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const conclusionStatePackage = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${conclusionStatePackage}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusion() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionCsv() {
  const header =
    "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const conclusion = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${conclusion}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionState() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateCsv() {
  const header =
    "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const conclusionState = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${conclusionState}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandover() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverCsv() {
  const header =
    "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const conclusionStatePackageHandover = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${conclusionStatePackageHandover}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverState() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateCsv() {
  const header =
    "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const conclusionStatePackageHandoverState = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${conclusionStatePackageHandoverState}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackage() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageCsv() {
  const header =
    "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const conclusionStatePackage = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${conclusionStatePackage}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusion() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionCsv() {
  const header =
    "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const conclusionStatePackageConclusion = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${conclusionStatePackageConclusion}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionState() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateCsv() {
  const header =
    "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const conclusionStatePackageConclusionState = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${conclusionStatePackageConclusionState}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackage() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageCsv() {
  const header =
    "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const conclusionStatePackage = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${conclusionStatePackage}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusion() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionCsv() {
  const header =
    "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const conclusionStatePackageConclusion = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${conclusionStatePackageConclusion}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionState() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStateText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStateJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStateText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStateCsv() {
  const header =
    "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const conclusionStatePackageConclusionState = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStateText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${conclusionStatePackageConclusionState}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackage() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageCsv() {
  const header =
    "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const conclusionStatePackage = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${conclusionStatePackage}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusion() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionCsv() {
  const header =
    "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const conclusionStatePackageConclusion = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${conclusionStatePackageConclusion}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionState() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStateText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStateJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStateText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStateCsv() {
  const header =
    "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const conclusionStatePackageConclusionState = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStateText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${conclusionStatePackageConclusionState}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackage() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageCsv() {
  const header =
    "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const conclusionStatePackage = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${conclusionStatePackage}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageConclusion() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageConclusionText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package_conclusion"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageConclusionJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package_conclusion:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageConclusionText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package_conclusion_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageConclusionCsv() {
  const header =
    "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package_conclusion";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const conclusionStatePackageConclusion = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageConclusionText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${conclusionStatePackageConclusion}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package_conclusion_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageConclusionState() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageConclusionStateText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论状态",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package_conclusion_state"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论状态已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageConclusionStateJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package_conclusion_state:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageConclusionStateText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论状态JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论状态JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageConclusionStateCsv() {
  const header =
    "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package_conclusion_state";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const conclusionStatePackageConclusionState = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageConclusionStateText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${conclusionStatePackageConclusionState}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论状态CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论状态CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackage() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论状态交接包",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论状态交接包已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value,
    digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package:
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageText.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论状态交接包JSON",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package_json"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论状态交接包JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageCsv() {
  const header =
    "generated_at,current_filter,current_preset,digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const currentPreset = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel.value || ""
  ).replace(/"/g, '""');
  const conclusionStatePackage = String(
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageText.value || ""
  ).replace(/"/g, '""');
  const csv = [header, `"${generatedAt}","${currentFilter}","${currentPreset}","${conclusionStatePackage}"`].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论状态交接包CSV",
        "governance_preset_history_audit_export_action_package_snapshot_digest_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_handover_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package_conclusion_state_package_csv"
      );
      uni.showToast({ title: "治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论状态交接包CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    audit_summary: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditSummaryText.value,
    audit_top1: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditTop1Text.value,
    audit_recent: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditRecentText.value,
    audit_items: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAudit.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计JSON",
        "governance_preset_history_audit_export_json"
      );
      uni.showToast({ title: "治理预设历史审计JSON已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditCsv() {
  const header = "generated_at,current_filter,at,source,source_text,action,filter,preset_label";
  const generatedAt = new Date().toISOString().replace(/"/g, '""');
  const currentFilter = String(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value || "").replace(
    /"/g,
    '""'
  );
  const rows = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAudit.value.map(
    (x) => {
      const at = String(x.at || "").replace(/"/g, '""');
      const source = String(x.source || "").replace(/"/g, '""');
      const sourceText = formatReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditActionSource(
        String(x.source || "")
      ).replace(/"/g, '""');
      const action = String(x.action || "").replace(/"/g, '""');
      const filter = String(x.filter || "").replace(/"/g, '""');
      const preset = String(x.presetLabel || "").replace(/"/g, '""');
      return `"${generatedAt}","${currentFilter}","${at}","${source}","${sourceText}","${action}","${filter}","${preset}"`;
    }
  );
  const csv = [header, ...rows].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计CSV",
        "governance_preset_history_audit_export_csv"
      );
      uni.showToast({ title: "治理预设历史审计CSV已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditRelaxStateSummary() {
  const text = [
    "治理预设历史审计放宽状态摘要",
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditRelaxStateText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditRelaxQueueText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditRelaxRemainingStepsText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditNextRelaxStepText.value
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计放宽状态",
        "governance_preset_history_audit_export_relax_state"
      );
      uni.showToast({ title: "治理预设历史审计放宽状态已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditWindowStateSummary() {
  uni.setClipboardData({
    data: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditWindowStateSummaryText.value,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制治理预设历史审计窗口状态",
        "governance_preset_history_audit_export_state"
      );
      uni.showToast({ title: "治理预设历史审计窗口状态已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function resetReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditWindow() {
  reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value = "all";
  persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
    "已重置治理预设历史审计窗口：全部",
    "governance_preset_history_audit_reset"
  );
  uni.showToast({ title: "已重置治理预设历史审计窗口", icon: "none" });
}

function clearReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAudit() {
  uni.showModal({
    title: "确认清理",
    content: "将清空治理预设历史审计记录，是否继续？",
    confirmText: "清理",
    cancelText: "取消",
    success: (res) => {
      if (!res.confirm) return;
      const nextAudit = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAudit.value.filter((item) => {
        const source = String(item.source || "");
        return !source.startsWith("governance_preset_history_");
      });
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAudit.value = nextAudit;
      uni.setStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_KEY, nextAudit);
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已清空治理预设历史审计记录",
        "governance_preset_history_audit_clear"
      );
      uni.showToast({ title: "已清空治理预设历史审计记录", icon: "none" });
    }
  });
}

function clearReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistory() {
  uni.showModal({
    title: "确认清理",
    content: "将清空预设动作历史动作审计预设历史治理预设历史，是否继续？",
    confirmText: "清理",
    cancelText: "取消",
    success: (res) => {
      if (!res.confirm) return;
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistory.value = [];
      uni.removeStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_GOVERNANCE_PRESET_HISTORY_KEY);
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已清空预设动作历史动作审计预设历史治理预设历史",
        "governance_preset_history_clear"
      );
      uni.showToast({ title: "已清空预设动作历史动作审计预设历史治理预设历史", icon: "none" });
    }
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceWindowStateSummary() {
  const at = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastActionAt.value
    ? formatDateTime(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastActionAt.value)
    : "-";
  const text = [
    "预设动作历史动作审计预设历史治理窗口状态摘要",
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceWindowSummaryText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceHitRateText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceIntensityText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceModeText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceSourceTop1Text.value,
    `最近动作=${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastAction.value || "无"}`,
    `来源=${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditActionSourceText.value}`,
    `时间=${at}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => {
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已复制预设动作历史动作审计预设历史治理窗口状态",
        "governance_export_window_state"
      );
      uni.showToast({ title: "预设动作历史动作审计预设历史治理窗口状态已复制", icon: "none" });
    },
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function clearReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceAudit() {
  uni.showModal({
    title: "确认清理",
    content: "将清空预设动作历史动作审计预设历史治理审计记录，是否继续？",
    confirmText: "清理",
    cancelText: "取消",
    success: (res) => {
      if (!res.confirm) return;
      const nextAudit = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAudit.value.filter((item) => {
        const source = String(item.source || "");
        return !(
          source === "governance_manual_filter" ||
          source === "governance_relax" ||
          source === "governance_reset" ||
          source === "governance_clear" ||
          source === "preset_history_manual_filter" ||
          source === "preset_history_relax" ||
          source === "preset_history_reset" ||
          source === "preset_history_clear" ||
          source === "preset_history_clear_relax"
        );
      });
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAudit.value = nextAudit;
      uni.setStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_KEY, nextAudit);
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已清空预设动作历史动作审计预设历史治理审计",
        "governance_clear"
      );
      uni.showToast({ title: "已清空预设动作历史动作审计预设历史治理审计", icon: "none" });
    }
  });
}

function resetReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryWindow() {
  reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value = "all";
  reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAction.value = "";
  reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAt.value = "";
  uni.removeStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_RELAX_KEY);
  persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
    "已重置预设动作历史动作审计预设历史窗口：全部",
    "preset_history_reset"
  );
  uni.showToast({ title: "已重置预设动作历史动作审计预设历史窗口", icon: "none" });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryResetStateSummary() {
  const at = reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastActionAt.value
    ? formatDateTime(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastActionAt.value)
    : "-";
  const text = [
    "预设动作历史动作审计预设历史重置状态摘要",
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetWindowSummaryText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetModeText.value,
    `最近动作=${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastAction.value || "无"}`,
    `来源=${reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditActionSourceText.value}`,
    `时间=${at}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "预设动作历史动作审计预设历史重置状态已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function clearReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryRelaxHistory() {
  uni.showModal({
    title: "确认清理",
    content: "将清空预设动作历史动作审计预设历史放宽记录，是否继续？",
    confirmText: "清理",
    cancelText: "取消",
    success: (res) => {
      if (!res.confirm) return;
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAction.value = "";
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAt.value = "";
      uni.removeStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_RELAX_KEY);
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已清空预设动作历史动作审计预设历史放宽记录",
        "preset_history_clear_relax"
      );
      uni.showToast({ title: "已清空预设动作历史动作审计预设历史放宽", icon: "none" });
    }
  });
}

function clearReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistory() {
  uni.showModal({
    title: "确认清理",
    content: "将清空预设动作历史动作审计预设历史，是否继续？",
    confirmText: "清理",
    cancelText: "取消",
    success: (res) => {
      if (!res.confirm) return;
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistory.value = [];
      uni.removeStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_KEY);
      persistReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditAction(
        "已清空预设动作历史动作审计预设历史",
        "preset_history_clear"
      );
      uni.showToast({ title: "已清空预设动作历史动作审计预设历史", icon: "none" });
    }
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditJson() {
  const payload = {
    schema_version: "v1",
    generated_at: new Date().toISOString(),
    current_filter: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter.value,
    current_preset: reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditCurrentPresetLabel.value,
    action_audit: filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAudit.value
  };
  uni.setClipboardData({
    data: JSON.stringify(payload, null, 2),
    success: () => uni.showToast({ title: "预设动作历史动作审计JSON已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditCsv() {
  const header = "at,source,action,filter,preset_label";
  const rows = filteredReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAudit.value.map((x) => {
    const at = String(x.at || "").replace(/"/g, '""');
    const source = String(x.source || "").replace(/"/g, '""');
    const action = String(x.action || "").replace(/"/g, '""');
    const filter = String(x.filter || "").replace(/"/g, '""');
    const preset = String(x.presetLabel || "").replace(/"/g, '""');
    return `"${at}","${source}","${action}","${filter}","${preset}"`;
  });
  const csv = [header, ...rows].join("\n");
  uni.setClipboardData({
    data: csv,
    success: () => uni.showToast({ title: "预设动作历史动作审计CSV已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function clearReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAudit() {
  uni.showModal({
    title: "确认清理",
    content: "将清空预设动作预设历史动作审计，是否继续？",
    confirmText: "清理",
    cancelText: "取消",
    success: (res) => {
      if (!res.confirm) return;
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAudit.value = [];
      uni.removeStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_KEY);
      uni.showToast({ title: "已清空预设动作历史动作审计", icon: "none" });
    }
  });
}

function clearReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistory() {
  uni.showModal({
    title: "确认清理",
    content: "将清空预设动作预设历史，是否继续？",
    confirmText: "清理",
    cancelText: "取消",
    success: (res) => {
      if (!res.confirm) return;
      reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistory.value = [];
      uni.removeStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_PRESET_HISTORY_KEY);
      uni.showToast({ title: "已清空预设动作预设历史", icon: "none" });
    }
  });
}

function resetReviewExportWindowActionAuditPresetHistoryActionAuditWindow() {
  reviewExportWindowActionAuditPresetHistoryActionAuditFilter.value = "all";
  persistReviewExportWindowActionAuditPresetHistoryAction("已重置预设历史动作审计窗口：全部", "action_audit_reset");
  uni.showToast({ title: "已恢复预设历史动作审计窗口", icon: "none" });
}

function persistReviewExportWindowActionAuditPresetHistoryActionAuditRelaxHistory() {
  uni.setStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_RELAX_KEY, {
    action: reviewExportWindowActionAuditPresetHistoryActionAuditLastRelaxAction.value,
    at: reviewExportWindowActionAuditPresetHistoryActionAuditLastRelaxAt.value
  });
}

function relaxReviewExportWindowActionAuditPresetHistoryActionAuditWindow() {
  let hint = "当前预设历史动作审计窗口已是最宽";
  if (reviewExportWindowActionAuditPresetHistoryActionAuditFilter.value === "24h") {
    reviewExportWindowActionAuditPresetHistoryActionAuditFilter.value = "7d";
    hint = "已放宽预设历史动作审计窗口：近24小时 -> 近7天";
  } else if (reviewExportWindowActionAuditPresetHistoryActionAuditFilter.value === "7d") {
    reviewExportWindowActionAuditPresetHistoryActionAuditFilter.value = "all";
    hint = "已放宽预设历史动作审计窗口：近7天 -> 全部";
  }
  reviewExportWindowActionAuditPresetHistoryActionAuditLastRelaxAction.value = hint;
  reviewExportWindowActionAuditPresetHistoryActionAuditLastRelaxAt.value = new Date().toISOString();
  persistReviewExportWindowActionAuditPresetHistoryActionAuditRelaxHistory();
  persistReviewExportWindowActionAuditPresetHistoryAction(hint, "action_audit_relax");
  uni.showToast({ title: hint, icon: "none" });
}

function onReviewExportWindowActionAuditPresetHistoryActionAuditFilterChange(index: number) {
  reviewExportWindowActionAuditPresetHistoryActionAuditFilter.value = index === 1 ? "24h" : index === 2 ? "7d" : "all";
  persistReviewExportWindowActionAuditPresetHistoryAction("已手动切换预设历史动作审计窗口", "action_audit_manual_filter");
}

function copyReviewExportWindowActionAuditPresetHistoryActionAuditRelaxSummary() {
  const at = reviewExportWindowActionAuditPresetHistoryActionAuditLastRelaxAt.value
    ? formatDateTime(reviewExportWindowActionAuditPresetHistoryActionAuditLastRelaxAt.value)
    : "-";
  const text = [
    "预设历史动作审计放宽摘要",
    reviewExportWindowActionAuditPresetHistoryActionAuditModeText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditRelaxQueueText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditRelaxRemainingStepsText.value,
    reviewExportWindowActionAuditPresetHistoryActionAuditNextRelaxStepText.value,
    `上次放宽：${reviewExportWindowActionAuditPresetHistoryActionAuditLastRelaxAction.value || "无"} @ ${at}`
  ].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "预设动作放宽摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function clearReviewExportWindowActionAuditPresetHistoryActionAuditRelaxHistory() {
  uni.showModal({
    title: "确认清理",
    content: "将清空预设动作审计放宽记录，是否继续？",
    confirmText: "清理",
    cancelText: "取消",
    success: (res) => {
      if (!res.confirm) return;
      reviewExportWindowActionAuditPresetHistoryActionAuditLastRelaxAction.value = "";
      reviewExportWindowActionAuditPresetHistoryActionAuditLastRelaxAt.value = "";
      uni.removeStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_RELAX_KEY);
      uni.showToast({ title: "已清空预设动作放宽记录", icon: "none" });
    }
  });
}

function clearReviewExportWindowActionAuditPresetHistoryActionAudit() {
  uni.showModal({
    title: "确认清理",
    content: "将清空预设历史窗口动作审计，是否继续？",
    confirmText: "清理",
    cancelText: "取消",
    success: (res) => {
      if (!res.confirm) return;
      reviewExportWindowActionAuditPresetHistoryActionAudit.value = [];
      uni.removeStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_ACTION_AUDIT_KEY);
      uni.showToast({ title: "已清空预设历史动作审计", icon: "none" });
    }
  });
}

function clearReviewExportWindowActionAuditPresetHistoryRelaxHistory() {
  uni.showModal({
    title: "确认清理",
    content: "将清空预设历史窗口放宽记录，是否继续？",
    confirmText: "清理",
    cancelText: "取消",
    success: (res) => {
      if (!res.confirm) return;
      reviewExportWindowActionAuditPresetHistoryLastRelaxAction.value = "";
      reviewExportWindowActionAuditPresetHistoryLastRelaxAt.value = "";
      uni.removeStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_RELAX_KEY);
      uni.showToast({ title: "已清空预设历史放宽记录", icon: "none" });
    }
  });
}

function clearReviewExportWindowActionAuditPresetHistory() {
  uni.showModal({
    title: "确认清理",
    content: "将清空审计预设历史，是否继续？",
    confirmText: "清理",
    cancelText: "取消",
    success: (res) => {
      if (!res.confirm) return;
      reviewExportWindowActionAuditPresetHistory.value = [];
      uni.removeStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_PRESET_HISTORY_KEY);
      uni.showToast({ title: "已清空审计预设历史", icon: "none" });
    }
  });
}

function clearReviewExportWindowActionAudit() {
  uni.showModal({
    title: "确认清理",
    content: "将清空窗口动作审计记录，是否继续？",
    confirmText: "清理",
    cancelText: "取消",
    success: (res) => {
      if (!res.confirm) return;
      reviewExportWindowActionAudit.value = [];
      uni.removeStorageSync(REVIEW_EXPORT_WINDOW_ACTION_AUDIT_KEY);
      uni.showToast({ title: "已清空窗口动作审计", icon: "none" });
    }
  });
}

function clearReviewExportHistory() {
  uni.showModal({
    title: "确认清理",
    content: "将清空最近复盘导出记录，是否继续？",
    confirmText: "清理",
    cancelText: "取消",
    success: (res) => {
      if (!res.confirm) return;
      reviewExportHistory.value = [];
      saveReviewExportHistory();
      uni.showToast({ title: "已清空导出记录", icon: "none" });
    }
  });
}

function saveDispatchProfile() {
  uni.setStorageSync(REVIEW_DISPATCH_PROFILE_KEY, {
    mode:
      dispatchProfile.value.mode === "webhook"
        ? "webhook"
        : dispatchProfile.value.mode === "channel_api"
          ? "channel_api"
          : "clipboard",
    channel: String(dispatchProfile.value.channel || "").trim(),
    to: String(dispatchProfile.value.to || "").trim(),
    cc: String(dispatchProfile.value.cc || "").trim(),
    webhookUrl: String(dispatchProfile.value.webhookUrl || "").trim(),
    webhookToken: String(dispatchProfile.value.webhookToken || "").trim(),
    channelApiUrl: String(dispatchProfile.value.channelApiUrl || "").trim(),
    channelApiToken: String(dispatchProfile.value.channelApiToken || "").trim(),
    channelApiAppId: String(dispatchProfile.value.channelApiAppId || "").trim(),
    channelApiGrayEnabled: !!dispatchProfile.value.channelApiGrayEnabled,
    channelApiGrayOrganizations: String(dispatchProfile.value.channelApiGrayOrganizations || "").trim(),
    channelApiGrayShifts: String(dispatchProfile.value.channelApiGrayShifts || "").trim(),
    channelApiSignEnabled: !!dispatchProfile.value.channelApiSignEnabled,
    channelApiSignSecret: String(dispatchProfile.value.channelApiSignSecret || "").trim()
  });
}

function saveDispatchStatus() {
  uni.setStorageSync(REVIEW_DISPATCH_STATUS_KEY, dispatchStatus.value);
}

function saveDispatchChannelAnalytics() {
  uni.setStorageSync(REVIEW_DISPATCH_CHANNEL_ANALYTICS_KEY, dispatchChannelAnalytics.value);
}

function markDispatchChannelAnalytics(payload: {
  isChannelApi: boolean;
  grayEvaluated?: boolean;
  grayHit?: boolean;
  signEnabled?: boolean;
  replayRejected?: boolean;
  message?: string;
}) {
  if (!payload.isChannelApi) return;
  const next = { ...dispatchChannelAnalytics.value };
  next.channelApiRequests += 1;
  if (payload.grayEvaluated) {
    next.grayEvaluated += 1;
    if (payload.grayHit) next.grayHit += 1;
    else next.graySkipped += 1;
  }
  if (payload.signEnabled) next.signEnabledRequests += 1;
  if (payload.replayRejected) next.replayRejected += 1;
  next.lastEval = new Date().toISOString();
  if (payload.message) next.lastMessage = payload.message;
  dispatchChannelAnalytics.value = next;
  saveDispatchChannelAnalytics();
}

function saveDispatchRetryQueue() {
  uni.setStorageSync(REVIEW_DISPATCH_RETRY_QUEUE_KEY, dispatchRetryQueue.value.slice(0, 20));
}

function saveDispatchAttemptLog() {
  uni.setStorageSync(REVIEW_DISPATCH_ATTEMPT_LOG_KEY, dispatchAttemptLog.value.slice(0, 200));
}

function saveDispatchAlerts() {
  uni.setStorageSync(REVIEW_DISPATCH_ALERTS_KEY, dispatchAlerts.value.slice(0, 50));
}

function saveDispatchRules() {
  uni.setStorageSync(REVIEW_DISPATCH_RULES_KEY, {
    preset: dispatchRules.value.preset || "custom",
    muteHttp4xxAlerts: !!dispatchRules.value.muteHttp4xxAlerts,
    promoteNetworkToError: !!dispatchRules.value.promoteNetworkToError
  });
  syncPresetsToServer().catch(() => undefined);
}

function saveDispatchRulePresets() {
  uni.setStorageSync(REVIEW_DISPATCH_RULE_PRESETS_KEY, dispatchRulePresets.value.slice(0, 30));
  syncPresetsToServer().catch(() => undefined);
}

function saveDispatchRuleSyncMeta() {
  uni.setStorageSync(REVIEW_DISPATCH_RULE_SYNC_META_KEY, dispatchRuleSyncMeta.value);
}

function saveDispatchRuleConflict() {
  uni.setStorageSync(REVIEW_DISPATCH_RULE_CONFLICT_KEY, dispatchRuleConflict.value);
}

function saveWorkOrderReturnEvents() {
  uni.setStorageSync(WORK_ORDER_RETURN_AGG_KEY, workOrderReturnEvents.value.slice(0, 100));
}

function pushWorkOrderReturnEvent(event: Omit<WorkOrderReturnEventItem, "id" | "at">) {
  const now = new Date().toISOString();
  workOrderReturnEvents.value = [
    {
      id: `${now}-${Math.random().toString(36).slice(2, 8)}`,
      at: now,
      ...event
    },
    ...workOrderReturnEvents.value
  ].slice(0, 100);
  saveWorkOrderReturnEvents();
}

async function rollbackDispatchRuleAudit(item: DispatchRuleAuditItem) {
  if (!item || !item.snapshot) return;
  if (!presetWritable.value) {
    uni.showToast({ title: "当前账号无策略回滚写权限", icon: "none" });
    return;
  }
  dispatchRuleRollbackingAuditId.value = item.id;
  try {
    applyDispatchRuleSnapshot(item.snapshot, "local", "已从审计记录回滚通知策略");
    pushDispatchRuleAudit("rollback", `回滚到 ${formatAuditTime(item.at)} 的策略快照`, item.snapshot);
    await syncPresetsToServer();
    uni.showToast({ title: "策略已回滚并同步", icon: "none" });
  } finally {
    dispatchRuleRollbackingAuditId.value = "";
  }
}

function applyDispatchRulePreset(preset: "strict" | "balanced" | "noise_reduction", showToast = true) {
  if (preset === "strict") {
    dispatchRules.value = {
      preset,
      muteHttp4xxAlerts: false,
      promoteNetworkToError: true
    };
  } else if (preset === "noise_reduction") {
    dispatchRules.value = {
      preset,
      muteHttp4xxAlerts: true,
      promoteNetworkToError: false
    };
  } else {
    dispatchRules.value = {
      preset: "balanced",
      muteHttp4xxAlerts: false,
      promoteNetworkToError: false
    };
  }
  saveDispatchRules();
  pushDispatchRuleAudit("template", `应用策略模板：${preset}`, buildDispatchRuleCenterSnapshot());
  if (showToast) {
    uni.showToast({ title: "通知策略模板已切换", icon: "none" });
  }
}

function syncDispatchRulePresetFromValues() {
  const mute = !!dispatchRules.value.muteHttp4xxAlerts;
  const promote = !!dispatchRules.value.promoteNetworkToError;
  if (!mute && promote) {
    dispatchRules.value.preset = "strict";
  } else if (mute && !promote) {
    dispatchRules.value.preset = "noise_reduction";
  } else if (!mute && !promote) {
    dispatchRules.value.preset = "balanced";
  } else {
    dispatchRules.value.preset = "custom";
  }
}
syncDispatchRulePresetFromValues();

function saveCurrentDispatchRulePreset() {
  const name = dispatchRulePresetName.value.trim();
  if (!name) {
    uni.showToast({ title: "请输入策略名称", icon: "none" });
    return;
  }
  const row = {
    name: name.slice(0, 40),
    muteHttp4xxAlerts: !!dispatchRules.value.muteHttp4xxAlerts,
    promoteNetworkToError: !!dispatchRules.value.promoteNetworkToError
  };
  const idx = dispatchRulePresets.value.findIndex((x) => x.name === row.name);
  if (idx >= 0) dispatchRulePresets.value[idx] = row;
  else dispatchRulePresets.value.push(row);
  dispatchRulePresetSelected.value = row.name;
  saveDispatchRulePresets();
  pushDispatchRuleAudit("named_preset_save", `保存命名策略：${row.name}`, buildDispatchRuleCenterSnapshot());
  uni.showToast({ title: "策略已保存", icon: "none" });
}

function applySelectedDispatchRulePreset() {
  const name = dispatchRulePresetSelected.value.trim();
  if (!name) return;
  const found = dispatchRulePresets.value.find((x) => x.name === name);
  if (!found) return;
  dispatchRules.value = {
    preset: "custom",
    muteHttp4xxAlerts: !!found.muteHttp4xxAlerts,
    promoteNetworkToError: !!found.promoteNetworkToError
  };
  syncDispatchRulePresetFromValues();
  saveDispatchRules();
  pushDispatchRuleAudit("named_preset_apply", `应用命名策略：${found.name}`, buildDispatchRuleCenterSnapshot());
  uni.showToast({ title: "策略已应用", icon: "none" });
}

function removeSelectedDispatchRulePreset() {
  const name = dispatchRulePresetSelected.value.trim();
  if (!name) return;
  dispatchRulePresets.value = dispatchRulePresets.value.filter((x) => x.name !== name);
  dispatchRulePresetSelected.value = "";
  saveDispatchRulePresets();
  pushDispatchRuleAudit("named_preset_remove", `删除命名策略：${name}`, buildDispatchRuleCenterSnapshot());
  uni.showToast({ title: "策略已删除", icon: "none" });
}

function toggleDispatchMuteHttp4xxAlerts() {
  dispatchRules.value.muteHttp4xxAlerts = !dispatchRules.value.muteHttp4xxAlerts;
  syncDispatchRulePresetFromValues();
  saveDispatchRules();
  pushDispatchRuleAudit(
    "toggle",
    `切换 4xx降噪：${dispatchRules.value.muteHttp4xxAlerts ? "开启" : "关闭"}`,
    buildDispatchRuleCenterSnapshot()
  );
}

function toggleDispatchPromoteNetworkToError() {
  dispatchRules.value.promoteNetworkToError = !dispatchRules.value.promoteNetworkToError;
  syncDispatchRulePresetFromValues();
  saveDispatchRules();
  pushDispatchRuleAudit(
    "toggle",
    `切换 网络升级错误：${dispatchRules.value.promoteNetworkToError ? "开启" : "关闭"}`,
    buildDispatchRuleCenterSnapshot()
  );
}

function pushDispatchAlert(level: "warning" | "error" | "info", message: string) {
  const now = new Date().toISOString();
  dispatchAlerts.value = [
    {
      id: `${now}-${Math.random().toString(36).slice(2, 8)}`,
      level,
      message,
      createdAt: now,
      resolved: false
    },
    ...dispatchAlerts.value
  ].slice(0, 50);
  saveDispatchAlerts();
}

function alertLevelByReasonType(reasonType: "network" | "http4xx" | "http5xx" | "config" | "other") {
  if (reasonType === "network" && dispatchRules.value.promoteNetworkToError) return "error" as const;
  if (reasonType === "config" || reasonType === "http5xx") return "error" as const;
  if (reasonType === "network" || reasonType === "http4xx") return "warning" as const;
  return "info" as const;
}

function shouldNotifyByReasonType(reasonType: "network" | "http4xx" | "http5xx" | "config" | "other") {
  if (reasonType === "http4xx" && dispatchRules.value.muteHttp4xxAlerts) return false;
  return true;
}

const filteredDispatchAlerts = computed(() => {
  if (dispatchAlertFilter.value === "error_only") {
    return dispatchAlerts.value.filter((x) => x.level === "error");
  }
  return dispatchAlerts.value;
});

function markDispatchAlertResolved(id: string) {
  dispatchAlerts.value = dispatchAlerts.value.map((item) => (item.id === id ? { ...item, resolved: true } : item));
  saveDispatchAlerts();
}

function clearResolvedDispatchAlerts() {
  dispatchAlerts.value = dispatchAlerts.value.filter((item) => !item.resolved);
  saveDispatchAlerts();
}

function unresolvedDispatchAlertCount() {
  return dispatchAlerts.value.filter((x) => !x.resolved).length;
}

function appendDispatchAttempt(
  source: "dispatch" | "retry",
  result: "success" | "failed",
  reasonType: "network" | "http4xx" | "http5xx" | "config" | "other",
  message: string,
  statusCode = 0
) {
  dispatchAttemptLog.value = [
    {
      at: new Date().toISOString(),
      source,
      result,
      reasonType,
      message,
      statusCode: Number(statusCode || 0)
    },
    ...dispatchAttemptLog.value
  ].slice(0, 200);
  saveDispatchAttemptLog();
}

function classifyReasonTypeByStatusCode(statusCode: number) {
  if (statusCode >= 400 && statusCode < 500) return "http4xx" as const;
  if (statusCode >= 500) return "http5xx" as const;
  return "other" as const;
}

function enqueueDispatchRetry(
  filename: string,
  summary: string,
  webhookUrl: string,
  errorMessage: string,
  reasonType: "network" | "http4xx" | "http5xx" | "config" | "other",
  dispatchMode: "webhook" | "channel_api" = "webhook",
  channelApiAppId = ""
) {
  const now = new Date().toISOString();
  dispatchRetryQueue.value = [
    {
      id: `${now}-${Math.random().toString(36).slice(2, 8)}`,
      filename,
      summary,
      webhookUrl,
      dispatchMode,
      channelApiAppId,
      createdAt: now,
      attempts: 1,
      lastError: errorMessage,
      reasonType
    },
    ...dispatchRetryQueue.value
  ].slice(0, 20);
  saveDispatchRetryQueue();
}

function getQueueReasonStatsText() {
  const stats: Record<"network" | "http4xx" | "http5xx" | "config" | "other", number> = {
    network: 0,
    http4xx: 0,
    http5xx: 0,
    config: 0,
    other: 0
  };
  dispatchRetryQueue.value.forEach((item) => {
    stats[item.reasonType] += 1;
  });
  return `失败分类：网络 ${stats.network} / 4xx ${stats.http4xx} / 5xx ${stats.http5xx} / 配置 ${stats.config} / 其他 ${stats.other}`;
}

function getRecent24hRetrySuccessRateText() {
  const now = Date.now();
  const in24h = dispatchAttemptLog.value.filter((item) => {
    if (item.source !== "retry") return false;
    const t = new Date(item.at).getTime();
    return !Number.isNaN(t) && now - t <= 24 * 60 * 60 * 1000;
  });
  const total = in24h.length;
  if (total <= 0) return "24h 重试成功率：-";
  const success = in24h.filter((x) => x.result === "success").length;
  const rate = Number(((success / total) * 100).toFixed(2));
  return `24h 重试成功率：${rate}%（${success}/${total}）`;
}

function getRecent24hRetryStats() {
  const now = Date.now();
  const in24h = dispatchAttemptLog.value.filter((item) => {
    if (item.source !== "retry") return false;
    const t = new Date(item.at).getTime();
    return !Number.isNaN(t) && now - t <= 24 * 60 * 60 * 1000;
  });
  const total = in24h.length;
  const success = in24h.filter((x) => x.result === "success").length;
  const rate = total <= 0 ? null : Number(((success / total) * 100).toFixed(2));
  return { total, success, rate };
}

function getDispatchHealthSummaryText() {
  const retry = getRecent24hRetryStats();
  const retryRateText = retry.rate === null ? "-" : `${retry.rate}%（${retry.success}/${retry.total}）`;
  return [
    "分发健康摘要",
    `状态=${dispatchStatus.value.lastStatus}`,
    `成功=${dispatchStatus.value.successCount}`,
    `失败=${dispatchStatus.value.failCount}`,
    `失败队列=${dispatchRetryQueue.value.length}`,
    `未读通知=${unresolvedDispatchAlertCount()}`,
    `24h重试成功率=${retryRateText}`,
    `最近结果=${dispatchStatus.value.lastMessage || "-"}`
  ].join("；");
}

function getDispatchHealthNextStepAdviceText() {
  if (dispatchStatus.value.lastStatus === "failed" || dispatchRetryQueue.value.length >= 5) {
    return "下一步建议：优先处理失败队列并核对 Webhook/渠道 API 配置。";
  }
  if (unresolvedDispatchAlertCount() > 0) {
    return "下一步建议：先清理未读分发通知，再回看重试效果。";
  }
  const retry = getRecent24hRetryStats();
  if (retry.rate !== null && retry.rate < 80) {
    return "下一步建议：排查网络与签名配置，提升重试成功率。";
  }
  return "下一步建议：保持当前分发策略，持续监控联调指标。";
}

function copyDispatchHealthSummary() {
  const text = [getDispatchHealthSummaryText(), getDispatchHealthNextStepAdviceText()].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "分发健康摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function isAlarmUnresolved(status?: string) {
  const s = String(status || "open").toLowerCase();
  return !(s.includes("closed") || s.includes("resolved") || s.includes("done"));
}

function getAlarmTriageSummaryText() {
  const rows = alarms.value || [];
  const unresolved = rows.filter((x) => isAlarmUnresolved(String((x as any).status || "")));
  const highOrCritical = unresolved.filter((x) => {
    const level = String((x as any).level || "").toLowerCase();
    return level.includes("high") || level.includes("critical");
  });
  const top3 = highOrCritical
    .slice(0, 3)
    .map((x) => String((x as any).device_id || (x as any).id || "-"))
    .join("/");
  return [
    "告警处置优先级摘要",
    `告警总量=${rows.length}`,
    `未处理=${unresolved.length}`,
    `高优未处理=${highOrCritical.length}`,
    `高优Top3=${top3 || "-"}`
  ].join("；");
}

function getAlarmTriageNextStepAdviceText() {
  const rows = alarms.value || [];
  const unresolved = rows.filter((x) => isAlarmUnresolved(String((x as any).status || "")));
  const highOrCritical = unresolved.filter((x) => {
    const level = String((x as any).level || "").toLowerCase();
    return level.includes("high") || level.includes("critical");
  });
  if (highOrCritical.length > 0) return "下一步建议：优先处理高优未闭环告警，并同步创建高优工单。";
  if (unresolved.length > 0) return "下一步建议：按时间顺序清理未处理告警，避免持续积压。";
  return "下一步建议：当前无未处理积压，保持告警巡检节奏。";
}

function copyAlarmTriageSummary() {
  const text = [getAlarmTriageSummaryText(), getAlarmTriageNextStepAdviceText()].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "处置优先级摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function getDispatchAlertGovernanceSummaryText() {
  const all = dispatchAlerts.value.length;
  const unresolved = dispatchAlerts.value.filter((x) => !x.resolved);
  const unresolvedCount = unresolved.length;
  const unresolvedErrorCount = unresolved.filter((x) => x.level === "error").length;
  const latestUnresolved = unresolved[0];
  const latestText = latestUnresolved
    ? `${latestUnresolved.message || "-"}${latestUnresolved.createdAt ? `@${formatAuditTime(latestUnresolved.createdAt)}` : ""}`
    : "-";
  return [
    "分发通知处置摘要",
    `通知总量=${all}`,
    `未读=${unresolvedCount}`,
    `未读错误=${unresolvedErrorCount}`,
    `最新未读=${latestText}`
  ].join("；");
}

function getDispatchAlertGovernanceAdviceText() {
  const unresolved = dispatchAlerts.value.filter((x) => !x.resolved);
  const unresolvedErrorCount = unresolved.filter((x) => x.level === "error").length;
  if (unresolvedErrorCount > 0) return "下一步建议：优先处理错误级未读通知，并复核对应分发链路。";
  if (unresolved.length > 0) return "下一步建议：按时间顺序清理未读通知，避免告警噪声堆积。";
  return "下一步建议：通知已清空，保持分发巡检与策略回看节奏。";
}

function copyDispatchAlertGovernanceSummary() {
  const text = [getDispatchAlertGovernanceSummaryText(), getDispatchAlertGovernanceAdviceText()].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "通知处置摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function getDispatchFailureCategorySummaryText() {
  const stats: Record<"network" | "http4xx" | "http5xx" | "config" | "other", number> = {
    network: 0,
    http4xx: 0,
    http5xx: 0,
    config: 0,
    other: 0
  };
  dispatchRetryQueue.value.forEach((item) => {
    stats[item.reasonType] += 1;
  });
  return [
    "分发失败分类摘要",
    `网络=${stats.network}`,
    `4xx=${stats.http4xx}`,
    `5xx=${stats.http5xx}`,
    `配置=${stats.config}`,
    `其他=${stats.other}`,
    `失败队列=${dispatchRetryQueue.value.length}`
  ].join("；");
}

function getDispatchFailureCategoryAdviceText() {
  const stats: Record<"network" | "http4xx" | "http5xx" | "config" | "other", number> = {
    network: 0,
    http4xx: 0,
    http5xx: 0,
    config: 0,
    other: 0
  };
  dispatchRetryQueue.value.forEach((item) => {
    stats[item.reasonType] += 1;
  });
  if (stats.config > 0) return "下一步建议：优先修复配置类失败（URL/Token/签名）后再批量重试。";
  if (stats.http5xx > 0) return "下一步建议：优先联系服务端排查 5xx，再执行队列重试。";
  if (stats.network > 0) return "下一步建议：优先排查网络连通性并观察重试成功率。";
  if (stats.http4xx > 0) return "下一步建议：核对请求参数与权限范围，降低 4xx 失败。";
  return "下一步建议：失败分类压力较低，保持分发巡检与抽样重试。";
}

function copyDispatchFailureCategorySummary() {
  const text = [getDispatchFailureCategorySummaryText(), getDispatchFailureCategoryAdviceText()].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "失败分类摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

function dispatchRetryModeText(mode?: "webhook" | "channel_api") {
  return mode === "channel_api" ? "渠道API" : "Webhook";
}

function pushReviewExportHistory(shiftKey: "day" | "evening" | "night") {
  reviewExportHistory.value = [
    {
      generatedAt: new Date().toISOString(),
      shiftKey,
      shiftLabel: currentShiftLabel(),
      windowLabel: exportWindowLabel(),
      alarmType: selectedAlarmType.value || "all",
      organization: selectedOrganization.value || "all"
    },
    ...reviewExportHistory.value
  ].slice(0, 10);
  saveReviewExportHistory();
}

function buildDashboardCsv() {
  const rows: Array<Array<string | number>> = [];
  rows.push(["meta", "report_version", REVIEW_REPORT_VERSION]);
  rows.push(["meta", "generated_at", new Date().toISOString()]);
  rows.push(["meta", "shift", currentShiftLabel()]);
  rows.push(["meta", "window", exportWindowLabel()]);
  rows.push(["meta", "alarm_type", selectedAlarmType.value || "all"]);
  rows.push(["meta", "organization", selectedOrganization.value || "all"]);
  rows.push(["meta", "template", exportTemplate.value]);
  rows.push(["meta", "compare_mode", compareMode.value]);
  rows.push(["meta", "trend_days", trendDays.value]);
  rows.push(["section", "label", "value"]);
  rows.push(["filter", "alarm_type", selectedAlarmType.value || "all"]);
  rows.push(["filter", "organization", selectedOrganization.value || "all"]);
  rows.push(["filter", "template", exportTemplate.value]);
  rows.push(["filter", "compare_mode", compareMode.value]);
  rows.push(["filter", "trend_days", trendDays.value]);
  if (exportFields.value.summary) {
    rows.push(["summary", "period_current", compareMetrics.value.periodCurrent]);
    rows.push(["summary", "period_previous", compareMetrics.value.periodPrevious]);
    rows.push(["summary", "period_change_pct", compareMetrics.value.periodChangePct]);
    rows.push(["summary", "day_current", compareMetrics.value.dayCurrent]);
    rows.push(["summary", "day_previous", compareMetrics.value.dayPrevious]);
    rows.push(["summary", "day_change_pct", compareMetrics.value.dayChangePct]);
  }
  if (exportFields.value.sla) {
    rows.push(["sla", "total_open", slaOverview.value.total_open]);
    rows.push(["sla", "escalated_open", slaOverview.value.escalated_open]);
    rows.push(["sla", "overdue_open", slaOverview.value.overdue_open]);
    rows.push(["sla", "acknowledged_today", slaOverview.value.acknowledged_today]);
    rows.push(["sla", "avg_ack_minutes_today", slaOverview.value.avg_ack_minutes_today]);
  }
  if (exportFields.value.duration) {
    rows.push(["duration", "p50", durationMetrics.value.p50]);
    rows.push(["duration", "p90", durationMetrics.value.p90]);
    rows.push(["duration", "samples", durationMetrics.value.samples]);
  }
  if (exportFields.value.cross_day) {
    crossDayChartData.value.forEach((x) => rows.push(["cross_day", x.label, x.value]));
  }
  if (exportTemplate.value === "full") {
    if (exportFields.value.slow_review) {
      slowSamples.value.forEach((sample) => {
        const review = getSlowSampleReview(sample);
        rows.push([
          "slow_review",
          sample.alarm_id,
          [
            `ack_minutes=${sample.ack_minutes}`,
            `status=${review.status}`,
            `priority=${review.priority}`,
            `assignee=${review.assignee}`,
            `alarm_to_wo_minutes=${review.alarmToWorkOrderMinutes === null ? "-" : review.alarmToWorkOrderMinutes}`
          ].join("|")
        ]);
      });
    }
    if (exportFields.value.hourly) hourlyChartData.value.forEach((x) => rows.push(["hourly", x.label, x.value]));
    if (exportFields.value.level) levelChartData.value.forEach((x) => rows.push(["level", x.label, x.value]));
    if (exportFields.value.top_device) topDeviceChartData.value.forEach((x) => rows.push(["top_device", x.label, x.value]));
    if (exportFields.value.assignee) assigneeChartData.value.forEach((x) => rows.push(["assignee", x.label, x.value]));
    if (exportFields.value.organization) organizationChartData.value.forEach((x) => rows.push(["organization", x.label, x.value]));
    if (exportFields.value.work_order) {
      filteredWorkOrders.value.forEach((wo) => {
        rows.push([
          "work_order",
          `${wo.id}:${wo.title}`,
          `${wo.status}|${wo.priority || "medium"}|${wo.assignee_user_id || wo.created_by_user_id || "unassigned"}`
        ]);
      });
    }
  }
  return rows.map((line) => line.map((x) => toCsvValue(x)).join(",")).join("\n");
}

function exportDashboardCsv() {
  const csv = buildDashboardCsv();
  uni.setClipboardData({
    data: csv,
    success: () => uni.showToast({ title: "已复制 CSV 到剪贴板", icon: "none" })
  });
}

function buildCsvFilename(prefix: string) {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  const hh = String(now.getHours()).padStart(2, "0");
  const mm = String(now.getMinutes()).padStart(2, "0");
  return `${prefix}-${y}${m}${d}-${hh}${mm}.csv`;
}

function downloadDashboardCsv(csvContent?: string, filenamePrefix = "alarm-dashboard") {
  const csv = csvContent || buildDashboardCsv();
  const filename = buildCsvFilename(filenamePrefix);
  try {
    if (typeof document !== "undefined" && typeof URL !== "undefined" && typeof Blob !== "undefined") {
      const blob = new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.style.display = "none";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      uni.showToast({ title: "CSV 已开始下载", icon: "none" });
      return filename;
    }
  } catch {
    // ignore and fallback
  }
  exportDashboardCsv();
  return filename;
}

function buildReviewDispatchSummary(filename: string) {
  const mode =
    dispatchProfile.value.mode === "webhook"
      ? "复制+Webhook"
      : dispatchProfile.value.mode === "channel_api"
        ? "渠道 API"
        : "仅复制";
  const channel = String(dispatchProfile.value.channel || "").trim() || "值班群";
  const to = String(dispatchProfile.value.to || "").trim() || "-";
  const cc = String(dispatchProfile.value.cc || "").trim() || "-";
  return [
    "【值班复盘包】",
    `文件：${filename}`,
    `分发模式：${mode}`,
    `分发渠道：${channel}`,
    `主送：${to}`,
    `抄送：${cc}`,
    `班次：${currentShiftLabel()}`,
    `时间窗：${exportWindowLabel()}`,
    `筛选：类型=${selectedAlarmType.value || "all"} / 组织=${selectedOrganization.value || "all"}`,
    `SLA：待处理=${slaOverview.value.total_open} / 超时=${slaOverview.value.overdue_open} / 今日确认=${slaOverview.value.acknowledged_today}`,
    `时长：P50=${durationMetrics.value.p50}分钟 / P90=${durationMetrics.value.p90}分钟 / 样本=${durationMetrics.value.samples}`,
    `生成时间：${new Date().toLocaleString()}`
  ].join("\n");
}

function copyReviewDispatchSummary(filename: string) {
  const summary = buildReviewDispatchSummary(filename);
  uni.setClipboardData({
    data: summary,
    success: () => {
      uni.showToast({ title: "复盘分发摘要已复制", icon: "none" });
    }
  });
}

async function sendReviewDispatchWebhook(filename: string) {
  if (dispatchProfile.value.mode !== "webhook") {
    dispatchStatus.value = {
      ...dispatchStatus.value,
      lastStatus: "skipped",
      lastMessage: "当前为仅复制模式，未调用 Webhook",
      lastAt: new Date().toISOString()
    };
    saveDispatchStatus();
    return "skipped";
  }
  const url = String(dispatchProfile.value.webhookUrl || "").trim();
  if (!url) {
    dispatchStatus.value = {
      ...dispatchStatus.value,
      lastStatus: "failed",
      lastMessage: "Webhook URL 为空，分发失败",
      lastAt: new Date().toISOString()
    };
    saveDispatchStatus();
    appendDispatchAttempt("dispatch", "failed", "config", "webhook_url_missing", 0);
    pushDispatchAlert("error", "分发失败：Webhook 模式未配置 URL");
    return "failed";
  }
  const summary = buildReviewDispatchSummary(filename);
  const token = String(dispatchProfile.value.webhookToken || "").trim();
  const requestResult = await new Promise<{
    result: "success" | "failed";
    message: string;
    reasonType: "network" | "http4xx" | "http5xx" | "config" | "other";
    statusCode: number;
  }>((resolve) => {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;
    uni.request({
      url,
      method: "POST",
      header: headers,
      data: {
        filename,
        summary,
        channel: dispatchProfile.value.channel || "",
        to: dispatchProfile.value.to || "",
        cc: dispatchProfile.value.cc || "",
        generated_at: new Date().toISOString()
      },
      success: (res) => {
        const code = Number(res?.statusCode || 0);
        if (code >= 200 && code < 300) {
          resolve({ result: "success", message: "Webhook 分发成功", reasonType: "other", statusCode: code });
          return;
        }
        resolve({
          result: "failed",
          message: `HTTP ${code || 0}`,
          reasonType: classifyReasonTypeByStatusCode(code),
          statusCode: code
        });
      },
      fail: () => resolve({ result: "failed", message: "network_error", reasonType: "network", statusCode: 0 })
    });
  });
  const result = requestResult.result;
  const next = {
    ...dispatchStatus.value,
    lastStatus: result,
    lastMessage: requestResult.message,
    lastAt: new Date().toISOString(),
    successCount: dispatchStatus.value.successCount + (result === "success" ? 1 : 0),
    failCount: dispatchStatus.value.failCount + (result === "failed" ? 1 : 0)
  };
  dispatchStatus.value = next;
  saveDispatchStatus();
  appendDispatchAttempt("dispatch", result, requestResult.reasonType, requestResult.message, requestResult.statusCode);
  if (result === "failed") {
    enqueueDispatchRetry(filename, summary, url, requestResult.message, requestResult.reasonType, "webhook", "");
    if (shouldNotifyByReasonType(requestResult.reasonType)) {
      pushDispatchAlert(
        alertLevelByReasonType(requestResult.reasonType),
        `分发失败（${requestResult.reasonType}）：${requestResult.message || "unknown_error"}，已加入失败队列`
      );
    }
  } else {
    pushDispatchAlert("info", "分发成功：Webhook 已返回成功状态");
  }
  return result;
}

function parseChannelApiResult(data: unknown) {
  const body = (data || {}) as Record<string, unknown>;
  const successByFlag = body.success === true;
  const successByCode = Number(body.code) === 0;
  const successByStatus = String(body.status || "").toLowerCase() === "ok";
  const success = successByFlag || successByCode || successByStatus;
  const message = String(body.message || body.msg || "");
  return {
    success,
    message: message || (success ? "channel_api_ok" : "channel_api_response_invalid")
  };
}

function parseDispatchCsvList(value: string) {
  return String(value || "")
    .replace(/，/g, ",")
    .split(",")
    .map((x) => x.trim())
    .filter((x) => !!x);
}

function shouldSendChannelApiByGrayPolicy() {
  if (!dispatchProfile.value.channelApiGrayEnabled) {
    return { allow: true, message: "", grayEvaluated: false, grayHit: true };
  }
  const orgRules = parseDispatchCsvList(dispatchProfile.value.channelApiGrayOrganizations || "");
  const shiftRules = parseDispatchCsvList(dispatchProfile.value.channelApiGrayShifts || "").map((x) => x.toLowerCase());
  const selectedOrg = String(selectedOrganization.value || "all").trim() || "all";
  const shift = currentShiftKey();
  const orgMatch = orgRules.length === 0 || orgRules.includes(selectedOrg) || orgRules.includes("all");
  const shiftMatch = shiftRules.length === 0 || shiftRules.includes(shift) || shiftRules.includes("all");
  if (orgMatch && shiftMatch) {
    return { allow: true, message: "", grayEvaluated: true, grayHit: true };
  }
  return {
    allow: false,
    message: `灰度策略未命中（org=${selectedOrg}, shift=${shift}）`,
    grayEvaluated: true,
    grayHit: false
  };
}

function isReplayRejected(statusCode: number, message: string) {
  if (statusCode === 409) return true;
  const text = String(message || "").toLowerCase();
  return text.includes("replay") || text.includes("nonce") || text.includes("duplicate");
}

async function buildChannelApiSignature(
  signSecret: string,
  timestamp: string,
  nonce: string,
  payloadText: string
) {
  const secret = String(signSecret || "").trim();
  if (!secret) return "";
  try {
    const cryptoObj = (globalThis as { crypto?: Crypto }).crypto;
    if (cryptoObj?.subtle && typeof TextEncoder !== "undefined") {
      const enc = new TextEncoder();
      const key = await cryptoObj.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
      const raw = await cryptoObj.subtle.sign("HMAC", key, enc.encode(`${timestamp}\n${nonce}\n${payloadText}`));
      const bytes = new Uint8Array(raw);
      return Array.from(bytes)
        .map((b) => b.toString(16).padStart(2, "0"))
        .join("");
    }
  } catch {
    // fallback below
  }
  return `${timestamp}.${nonce}.${secret.length}.${payloadText.length}`;
}

async function sendReviewDispatchChannelApi(filename: string) {
  if (dispatchProfile.value.mode !== "channel_api") {
    dispatchStatus.value = {
      ...dispatchStatus.value,
      lastStatus: "skipped",
      lastMessage: "当前未启用渠道 API 模式",
      lastAt: new Date().toISOString()
    };
    saveDispatchStatus();
    return "skipped";
  }
  const url = String(dispatchProfile.value.channelApiUrl || "").trim();
  if (!url) {
    dispatchStatus.value = {
      ...dispatchStatus.value,
      lastStatus: "failed",
      lastMessage: "渠道 API URL 为空，分发失败",
      lastAt: new Date().toISOString()
    };
    saveDispatchStatus();
    appendDispatchAttempt("dispatch", "failed", "config", "channel_api_url_missing", 0);
    pushDispatchAlert("error", "分发失败：渠道 API 模式未配置 URL");
    return "failed";
  }
  const gray = shouldSendChannelApiByGrayPolicy();
  if (!gray.allow) {
    markDispatchChannelAnalytics({
      isChannelApi: true,
      grayEvaluated: gray.grayEvaluated,
      grayHit: gray.grayHit,
      signEnabled: !!dispatchProfile.value.channelApiSignEnabled,
      replayRejected: false,
      message: gray.message
    });
    dispatchStatus.value = {
      ...dispatchStatus.value,
      lastStatus: "skipped",
      lastMessage: gray.message,
      lastAt: new Date().toISOString()
    };
    saveDispatchStatus();
    pushDispatchAlert("info", `渠道 API 已跳过：${gray.message}`);
    return "skipped";
  }
  const summary = buildReviewDispatchSummary(filename);
  const token = String(dispatchProfile.value.channelApiToken || "").trim();
  const appId = String(dispatchProfile.value.channelApiAppId || "").trim() || "mobile-alarm-review";
  if (dispatchProfile.value.channelApiSignEnabled && !String(dispatchProfile.value.channelApiSignSecret || "").trim()) {
    dispatchStatus.value = {
      ...dispatchStatus.value,
      lastStatus: "failed",
      lastMessage: "签名模式已开启但签名密钥为空",
      lastAt: new Date().toISOString()
    };
    saveDispatchStatus();
    appendDispatchAttempt("dispatch", "failed", "config", "channel_api_sign_secret_missing", 0);
    pushDispatchAlert("error", "分发失败：渠道 API 签名密钥未配置");
    return "failed";
  }
  const timestamp = String(Math.floor(Date.now() / 1000));
  const nonce = Math.random().toString(36).slice(2, 12);
  const signPayload = JSON.stringify({
    app_id: appId,
    report_type: "alarm_review",
    filename,
    summary
  });
  const signature =
    dispatchProfile.value.channelApiSignEnabled && dispatchProfile.value.channelApiSignSecret
      ? await buildChannelApiSignature(dispatchProfile.value.channelApiSignSecret, timestamp, nonce, signPayload)
      : "";
  const requestResult = await new Promise<{
    result: "success" | "failed";
    message: string;
    reasonType: "network" | "http4xx" | "http5xx" | "config" | "other";
    statusCode: number;
    replayRejected: boolean;
  }>((resolve) => {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      "X-Client-App": appId,
      "X-Sign-Timestamp": timestamp,
      "X-Sign-Nonce": nonce
    };
    if (token) headers.Authorization = `Bearer ${token}`;
    if (signature) {
      headers["X-Signature"] = signature;
      headers["X-Sign-Alg"] = "HMAC-SHA256";
    }
    uni.request({
      url,
      method: "POST",
      header: headers,
      data: {
        app_id: appId,
        report_type: "alarm_review",
        filename,
        summary,
        profile: {
          channel: dispatchProfile.value.channel || "",
          to: dispatchProfile.value.to || "",
          cc: dispatchProfile.value.cc || ""
        },
        sign_meta: {
          timestamp,
          nonce,
          alg: signature ? "HMAC-SHA256" : "none"
        },
        generated_at: new Date().toISOString()
      },
      success: (res) => {
        const code = Number(res?.statusCode || 0);
        if (code >= 200 && code < 300) {
          const parsed = parseChannelApiResult(res?.data);
          if (parsed.success) {
            resolve({
              result: "success",
              message: "渠道 API 分发成功",
              reasonType: "other",
              statusCode: code,
              replayRejected: false
            });
            return;
          }
          resolve({
            result: "failed",
            message: parsed.message,
            reasonType: "other",
            statusCode: code,
            replayRejected: isReplayRejected(code, parsed.message)
          });
          return;
        }
        resolve({
          result: "failed",
          message: `HTTP ${code || 0}`,
          reasonType: classifyReasonTypeByStatusCode(code),
          statusCode: code,
          replayRejected: isReplayRejected(code, `HTTP ${code || 0}`)
        });
      },
      fail: () => resolve({ result: "failed", message: "network_error", reasonType: "network", statusCode: 0, replayRejected: false })
    });
  });
  markDispatchChannelAnalytics({
    isChannelApi: true,
    grayEvaluated: gray.grayEvaluated,
    grayHit: gray.grayHit,
    signEnabled: !!dispatchProfile.value.channelApiSignEnabled,
    replayRejected: !!requestResult.replayRejected,
    message: requestResult.message
  });
  const result = requestResult.result;
  dispatchStatus.value = {
    ...dispatchStatus.value,
    lastStatus: result,
    lastMessage: requestResult.message,
    lastAt: new Date().toISOString(),
    successCount: dispatchStatus.value.successCount + (result === "success" ? 1 : 0),
    failCount: dispatchStatus.value.failCount + (result === "failed" ? 1 : 0)
  };
  saveDispatchStatus();
  appendDispatchAttempt("dispatch", result, requestResult.reasonType, requestResult.message, requestResult.statusCode);
  if (result === "failed") {
    enqueueDispatchRetry(filename, summary, url, requestResult.message, requestResult.reasonType, "channel_api", appId);
    if (shouldNotifyByReasonType(requestResult.reasonType)) {
      pushDispatchAlert(
        alertLevelByReasonType(requestResult.reasonType),
        `渠道 API 分发失败（${requestResult.reasonType}）：${requestResult.message || "unknown_error"}，已加入失败队列`
      );
    }
    if (requestResult.replayRejected) {
      pushDispatchAlert("warning", "检测到渠道 API 可能触发防重放拒绝（nonce/replay），请检查服务端时间窗与 nonce TTL 配置");
    }
  } else {
    pushDispatchAlert("info", "分发成功：渠道 API 已返回成功状态");
  }
  return result;
}

async function sendReviewDispatch(filename: string) {
  if (dispatchProfile.value.mode === "channel_api") {
    return sendReviewDispatchChannelApi(filename);
  }
  return sendReviewDispatchWebhook(filename);
}

async function retryDispatchQueueItem(id: string) {
  const idx = dispatchRetryQueue.value.findIndex((x) => x.id === id);
  if (idx < 0) return;
  const row = dispatchRetryQueue.value[idx];
  const mode = row.dispatchMode || "webhook";
  const url =
    mode === "channel_api"
      ? String(dispatchProfile.value.channelApiUrl || row.webhookUrl || "").trim()
      : String(dispatchProfile.value.webhookUrl || row.webhookUrl || "").trim();
  if (!url) {
    uni.showToast({ title: mode === "channel_api" ? "缺少渠道 API URL" : "缺少 Webhook URL", icon: "none" });
    return;
  }
  const tokenForMode =
    mode === "channel_api"
      ? String(dispatchProfile.value.channelApiToken || "").trim()
      : String(dispatchProfile.value.webhookToken || "").trim();
  const appIdForMode = String(dispatchProfile.value.channelApiAppId || row.channelApiAppId || "").trim() || "mobile-alarm-review";
  const timestamp = String(Math.floor(Date.now() / 1000));
  const nonce = Math.random().toString(36).slice(2, 12);
  const signature =
    mode === "channel_api" && dispatchProfile.value.channelApiSignEnabled && dispatchProfile.value.channelApiSignSecret
      ? await buildChannelApiSignature(
          dispatchProfile.value.channelApiSignSecret,
          timestamp,
          nonce,
          JSON.stringify({
            app_id: appIdForMode,
            report_type: "alarm_review",
            filename: row.filename,
            summary: row.summary
          })
        )
      : "";
  const requestResult = await new Promise<{
    result: "success" | "failed";
    message: string;
    reasonType: "network" | "http4xx" | "http5xx" | "config" | "other";
    statusCode: number;
    replayRejected: boolean;
  }>((resolve) => {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (tokenForMode) headers.Authorization = `Bearer ${tokenForMode}`;
    if (mode === "channel_api") {
      headers["X-Client-App"] = appIdForMode;
      headers["X-Sign-Timestamp"] = timestamp;
      headers["X-Sign-Nonce"] = nonce;
      if (signature) {
        headers["X-Signature"] = signature;
        headers["X-Sign-Alg"] = "HMAC-SHA256";
      }
    }
    uni.request({
      url,
      method: "POST",
      header: headers,
      data:
        mode === "channel_api"
          ? {
              app_id: appIdForMode,
              report_type: "alarm_review",
              filename: row.filename,
              summary: row.summary,
              sign_meta: {
                timestamp,
                nonce,
                alg: signature ? "HMAC-SHA256" : "none"
              },
              generated_at: new Date().toISOString()
            }
          : {
              filename: row.filename,
              summary: row.summary,
              generated_at: new Date().toISOString()
            },
      success: (res) => {
        const code = Number(res?.statusCode || 0);
        if (code >= 200 && code < 300) {
          if (mode === "channel_api") {
            const parsed = parseChannelApiResult(res?.data);
            if (parsed.success) {
              resolve({
                result: "success",
                message: "失败队列重试成功",
                reasonType: "other",
                statusCode: code,
                replayRejected: false
              });
              return;
            }
            resolve({
              result: "failed",
              message: parsed.message,
              reasonType: "other",
              statusCode: code,
              replayRejected: isReplayRejected(code, parsed.message)
            });
            return;
          }
          resolve({
            result: "success",
            message: "失败队列重试成功",
            reasonType: "other",
            statusCode: code,
            replayRejected: false
          });
          return;
        }
        resolve({
          result: "failed",
          message: `HTTP ${code || 0}`,
          reasonType: classifyReasonTypeByStatusCode(code),
          statusCode: code,
          replayRejected: isReplayRejected(code, `HTTP ${code || 0}`)
        });
      },
      fail: () => resolve({ result: "failed", message: "network_error", reasonType: "network", statusCode: 0, replayRejected: false })
    });
  });
  markDispatchChannelAnalytics({
    isChannelApi: mode === "channel_api",
    grayEvaluated: false,
    grayHit: true,
    signEnabled: mode === "channel_api" && !!dispatchProfile.value.channelApiSignEnabled,
    replayRejected: !!requestResult.replayRejected,
    message: `${mode === "channel_api" ? "渠道API重试" : "Webhook重试"}: ${requestResult.message}`
  });
  const result = requestResult.result;
  appendDispatchAttempt("retry", result, requestResult.reasonType, requestResult.message, requestResult.statusCode);
  if (result === "success") {
    dispatchRetryQueue.value.splice(idx, 1);
    saveDispatchRetryQueue();
    dispatchStatus.value = {
      ...dispatchStatus.value,
      lastStatus: "success",
      lastMessage: "失败队列重试成功",
      lastAt: new Date().toISOString(),
      successCount: dispatchStatus.value.successCount + 1
    };
    saveDispatchStatus();
    pushDispatchAlert("info", "失败队列重试成功");
    uni.showToast({ title: "重试成功", icon: "none" });
    return;
  }
  dispatchRetryQueue.value[idx] = {
    ...row,
    attempts: Number(row.attempts || 1) + 1,
    lastError: requestResult.message,
    webhookUrl: url,
    reasonType: requestResult.reasonType,
    dispatchMode: mode,
    channelApiAppId: appIdForMode
  };
  saveDispatchRetryQueue();
  dispatchStatus.value = {
    ...dispatchStatus.value,
    lastStatus: "failed",
    lastMessage: "失败队列重试失败",
    lastAt: new Date().toISOString(),
    failCount: dispatchStatus.value.failCount + 1
  };
  saveDispatchStatus();
  if (shouldNotifyByReasonType(requestResult.reasonType)) {
    pushDispatchAlert(
      alertLevelByReasonType(requestResult.reasonType),
      `失败队列重试失败（${requestResult.reasonType}）：${requestResult.message || "unknown_error"}`
    );
  }
  if (requestResult.replayRejected) {
    pushDispatchAlert("warning", "失败队列重试命中防重放拒绝，请检查 nonce/timestamp 配置");
  }
  uni.showToast({ title: "重试失败", icon: "none" });
}

async function retryAllDispatchQueue() {
  const ids = dispatchRetryQueue.value.map((x) => x.id);
  for (const id of ids) {
    await retryDispatchQueueItem(id);
  }
}

function clearDispatchRetryQueue() {
  dispatchRetryQueue.value = [];
  saveDispatchRetryQueue();
}

async function exportReviewPackage() {
  applyReviewTemplatePresetInternal(false);
  const csv = buildDashboardCsv();
  const shiftKey = currentShiftKey();
  const filename = downloadDashboardCsv(csv, `alarm-review-pack-${shiftKey}`);
  pushReviewExportHistory(shiftKey);
  await sendReviewDispatch(filename);
  copyReviewDispatchSummary(filename);
}

async function quickReExportReviewPackage(item: {
  generatedAt: string;
  shiftKey: "day" | "evening" | "night";
  alarmType: string;
  organization: string;
}) {
  applyReviewTemplatePresetInternal(false);
  selectedAlarmType.value = item.alarmType === "all" ? "" : item.alarmType;
  selectedOrganization.value = item.organization === "all" ? "" : item.organization;
  await Promise.all([loadCrossDayTrend(), loadDurationMetrics(7)]);
  const csv = buildDashboardCsv();
  const filename = downloadDashboardCsv(csv, `alarm-review-pack-${item.shiftKey}-redo`);
  pushReviewExportHistory(item.shiftKey);
  await sendReviewDispatch(filename);
  copyReviewDispatchSummary(filename);
}

function onWorkOrderAssigneeChange(e: { detail?: { value?: string | number } }) {
  const idx = Number(e?.detail?.value ?? 0);
  workOrderAssigneeFilter.value = workOrderAssigneeOptions.value[idx]?.value || "";
}

function onWorkOrderPriorityChange(e: { detail?: { value?: string | number } }) {
  const idx = Number(e?.detail?.value ?? 0);
  const item = workOrderPriorityOptions[idx];
  workOrderPriorityFilter.value = (item?.value || "") as "" | "low" | "medium" | "high";
}

function onWorkOrderStatusChartClick(item: { key?: string }) {
  const key = String(item?.key || "") as WorkOrderStatus;
  if (key === "open" || key === "in_progress" || key === "resolved" || key === "closed") {
    workOrderStatusFilter.value = key;
  }
}

async function onAlarmTypeChartClick(item: { key?: string }) {
  selectedAlarmType.value = String(item?.key || "");
  await Promise.all([loadCrossDayTrend(), loadDurationMetrics(7)]);
}

async function onOrganizationChartClick(item: { key?: string }) {
  const raw = String(item?.key || "");
  selectedOrganization.value = raw === "__ungrouped__" ? "未分组" : raw;
  await Promise.all([loadCrossDayTrend(), loadDurationMetrics(7)]);
}

function openWorkOrderDetail(wo: WorkOrderItem) {
  const assigneeId = wo.assignee_user_id || wo.created_by_user_id || "未指派";
  const q = [
    `id=${encodeURIComponent(wo.id)}`,
    `title=${encodeURIComponent(wo.title || "")}`,
    `status=${encodeURIComponent(wo.status || "open")}`,
    `priority=${encodeURIComponent(wo.priority || "medium")}`,
    `assignee=${encodeURIComponent(userNameMap.value[assigneeId] || assigneeId)}`,
    `alarmId=${encodeURIComponent(wo.alarm_id || "")}`,
    `createdAt=${encodeURIComponent(wo.created_at || "")}`,
    `description=${encodeURIComponent(wo.description || "")}`
  ].join("&");
  uni.navigateTo({
    url: `/pages/work-order-detail/index?${q}`,
    success: (res) => {
      res.eventChannel.on("workOrderUpdated", async (payload?: { id?: string; status?: WorkOrderStatus }) => {
        const id = String(payload?.id || "");
        const status = payload?.status;
        if (id && status) {
          const prev = workOrders.value.find((x) => x.id === id);
          workOrders.value = workOrders.value.map((x) => (x.id === id ? { ...x, status } : x));
          pushWorkOrderReturnEvent({
            workOrderId: id,
            alarmId: String(prev?.alarm_id || ""),
            source: "work_order_detail",
            fromStatus: (prev?.status || "") as WorkOrderStatus | "",
            toStatus: status
          });
          return;
        }
        pushWorkOrderReturnEvent({
          workOrderId: String(wo.id || ""),
          alarmId: String(wo.alarm_id || ""),
          source: "work_order_detail_full_refresh",
          fromStatus: "",
          toStatus: ""
        });
        await loadWorkOrders();
      });
    }
  });
}
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">告警中心</view>
    <button type="primary" :loading="loading || workOrderLoading || slaLoading || trendLoading" @click="refreshAll">刷新告警</button>
    <text class="app-subtext">操作状态：{{ alarmPageActionStatusMessage || "-" }}</text>
    <text v-if="alarmPageActionStatusAt" class="app-subtext">状态时间：{{ formatAuditTime(alarmPageActionStatusAt) }}</text>

    <view class="app-card app-gap-12">
      <text class="app-title" style="font-size:30rpx">联动筛选</text>
      <view class="app-row">
        <text class="app-subtext">告警类型</text>
        <picker mode="selector" :range="alarmTypeOptions" @change="onAlarmTypeChange">
          <view class="app-subtext">{{ selectedAlarmType || "全部类型" }}</view>
        </picker>
      </view>
      <view class="app-row">
        <text class="app-subtext">组织维度</text>
        <picker mode="selector" :range="organizationOptions" range-key="label" @change="onOrganizationChange">
          <view class="app-subtext">{{ organizationDisplayName(selectedOrganization) }}</view>
        </picker>
      </view>
      <view class="app-row">
        <text class="app-subtext">快捷预设</text>
        <button size="mini" :type="alarmQuickPreset === 'all' ? 'primary' : 'default'" @click="applyAlarmQuickPreset('all')">全部</button>
        <button size="mini" :type="alarmQuickPreset === 'high' ? 'primary' : 'default'" @click="applyAlarmQuickPreset('high')">高优</button>
        <button size="mini" :type="alarmQuickPreset === 'unacked' ? 'primary' : 'default'" @click="applyAlarmQuickPreset('unacked')">未确认</button>
        <button size="mini" @click="resetAlarmFilters">重置筛选</button>
      </view>
      <view class="app-row">
        <button size="mini" @click="downloadDashboardCsv">下载 CSV</button>
        <button size="mini" @click="exportDashboardCsv">复制 CSV</button>
      </view>
      <view class="app-row">
        <input v-model="exportPresetName" placeholder="导出预设名称（如：值班日报）" />
        <button size="mini" :disabled="!presetWritable" @click="saveCurrentPreset">保存预设</button>
        <AppStatusTag :text="presetWritable ? '可写' : '只读'" :type="presetWritable ? 'success' : 'warning'" />
      </view>
      <view class="app-row">
        <picker mode="selector" :range="exportPresets.map((x) => x.name)" @change="(e) => { exportPresetSelected = exportPresets[Number(e?.detail?.value || 0)]?.name || '' }">
          <view class="app-subtext">当前预设：{{ exportPresetSelected || "未选择" }}</view>
        </picker>
        <button size="mini" @click="applySelectedPreset">应用</button>
        <button size="mini" :disabled="!presetWritable" @click="removeSelectedPreset">删除</button>
      </view>
      <view class="app-row" style="flex-wrap: wrap; gap: 8rpx">
        <button
          v-for="field in exportFieldOptions"
          :key="field.key"
          size="mini"
          :type="exportFields[field.key] ? 'primary' : 'default'"
          @click="onToggleExportField(field.key)"
        >
          {{ field.label }}
        </button>
        <button size="mini" @click="resetExportFields">恢复默认</button>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-title" style="font-size:30rpx">共享预设审计</text>
        <AppStatusTag :text="presetAuditLoading ? '加载中' : '最近10条'" :type="presetAuditLoading ? 'warning' : 'info'" />
      </view>
      <view v-for="item in presetAudits" :key="item.audit_id" class="app-gap-12" style="border:1rpx solid #E2E8F0;border-radius:10rpx;padding:12rpx;">
        <view class="app-row">
          <text class="app-subtext">{{ formatAuditTime(item.created_at) }}</text>
          <AppStatusTag :text="item.result === 'success' ? '成功' : '失败'" :type="item.result === 'success' ? 'success' : 'danger'" />
        </view>
        <text class="app-subtext">操作人：{{ item.operator || "-" }}</text>
        <text class="app-subtext">预设数量：{{ item.preset_count }}</text>
      </view>
      <AppEmpty v-if="!presetAuditLoading && presetAudits.length === 0" text="暂无共享预设审计记录（仅 owner/admin 可见）" />
    </view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-title" style="font-size:30rpx">处置时长分位数（7 天）</text>
        <AppStatusTag :text="`样本 ${durationMetrics.samples}`" :type="durationMetrics.samples > 0 ? 'success' : 'info'" />
      </view>
      <view class="app-row">
        <text class="app-subtext">P50：{{ durationMetrics.p50 }} 分钟</text>
        <text class="app-subtext">P90：{{ durationMetrics.p90 }} 分钟</text>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-title" style="font-size:30rpx">质量口径下钻（TOP 慢告警）</text>
        <button size="mini" :type="selectedSlowAlarmId ? 'primary' : 'default'" @click="clearSlowSampleFilter">清除下钻</button>
      </view>
      <view v-for="item in slowSamples" :key="`${item.alarm_id}-${item.ack_at || ''}`" class="app-gap-12" style="border:1rpx solid #E2E8F0;border-radius:10rpx;padding:12rpx;">
        <view class="app-row">
          <text class="app-subtext">告警ID：{{ item.alarm_id }}</text>
          <AppStatusTag :text="`${item.ack_minutes} 分钟`" :type="item.ack_minutes >= durationMetrics.p90 && durationMetrics.p90 > 0 ? 'danger' : 'warning'" />
        </view>
        <text class="app-subtext">类型：{{ item.alarm_type }} / 等级：{{ item.level }}</text>
        <text class="app-subtext">组织：{{ organizationDisplayName(item.organization_id) }}</text>
        <text class="app-subtext">
          处置结果：{{ getSlowSampleReview(item).status }} / 优先级：{{ getSlowSampleReview(item).priority }} / 处置人：{{ getSlowSampleReview(item).assignee }}
        </text>
        <text class="app-subtext">
          告警到派单耗时：{{ getSlowSampleReview(item).alarmToWorkOrderMinutes === null ? "-" : `${getSlowSampleReview(item).alarmToWorkOrderMinutes} 分钟` }}
        </text>
        <view class="app-row">
          <button size="mini" @click="applySlowSample(item)">按该告警下钻</button>
          <button size="mini" @click="openRelatedWorkOrderFromSlowSample(item)">{{ getSlowSampleReview(item).hasWorkOrder ? "工单详情" : "去工单筛选" }}</button>
          <button size="mini" @click="openCommandByAlarmId(item.alarm_id)">会商联动</button>
        </view>
      </view>
      <AppEmpty v-if="slowSamples.length === 0" text="暂无慢告警样本" />
    </view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-title" style="font-size:30rpx">SLA 概览</text>
        <AppStatusTag :text="slaLoading ? '更新中' : '实时'" :type="slaLoading ? 'warning' : 'success'" />
      </view>
      <view class="app-row">
        <text class="app-subtext">待处理总量：{{ slaOverview.total_open }}</text>
        <text class="app-subtext">升级中：{{ slaOverview.escalated_open }}</text>
      </view>
      <view class="app-row">
        <text class="app-subtext">超时待处理：{{ slaOverview.overdue_open }}</text>
        <text class="app-subtext">今日已确认：{{ slaOverview.acknowledged_today }}</text>
      </view>
      <view class="app-row">
        <text class="app-subtext">今日平均确认时长：{{ Number(slaOverview.avg_ack_minutes_today || 0).toFixed(2) }} 分钟</text>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-title" style="font-size:30rpx">跨日告警趋势</text>
        <view class="app-row">
          <button size="mini" :type="trendDays === 3 ? 'primary' : 'default'" @click="switchTrendDays(3)">3 天</button>
          <button size="mini" :type="trendDays === 7 ? 'primary' : 'default'" @click="switchTrendDays(7)">7 天</button>
        </view>
      </view>
      <view class="app-row">
        <button size="mini" :type="compareMode === 'period' ? 'primary' : 'default'" @click="switchCompareMode('period')">周期口径</button>
        <button size="mini" :type="compareMode === 'day' ? 'primary' : 'default'" @click="switchCompareMode('day')">24h口径</button>
        <button size="mini" :type="exportTemplate === 'summary' ? 'primary' : 'default'" @click="switchExportTemplate('summary')">简版导出</button>
        <button size="mini" :type="exportTemplate === 'full' ? 'primary' : 'default'" @click="switchExportTemplate('full')">完整导出</button>
      </view>
      <view class="app-row">
        <button size="mini" @click="applyReviewTemplatePreset">值班复盘模板</button>
        <button size="mini" @click="applyFullTemplatePreset">全量分析模板</button>
        <button size="mini" type="primary" @click="exportReviewPackage">导出复盘包</button>
      </view>
      <view class="app-gap-12" style="border:1rpx solid #E2E8F0;border-radius:10rpx;padding:10rpx;">
        <text class="app-subtext">分发模板配置</text>
        <view class="app-row">
          <button size="mini" :type="dispatchProfile.mode === 'clipboard' ? 'primary' : 'default'" @click="() => { dispatchProfile.mode = 'clipboard'; saveDispatchProfile(); }">仅复制</button>
          <button size="mini" :type="dispatchProfile.mode === 'webhook' ? 'primary' : 'default'" @click="() => { dispatchProfile.mode = 'webhook'; saveDispatchProfile(); }">复制+Webhook</button>
          <button size="mini" :type="dispatchProfile.mode === 'channel_api' ? 'primary' : 'default'" @click="() => { dispatchProfile.mode = 'channel_api'; saveDispatchProfile(); }">渠道 API</button>
        </view>
        <input v-model="dispatchProfile.channel" placeholder="分发渠道（如：值班群）" @blur="saveDispatchProfile" />
        <input v-model="dispatchProfile.to" placeholder="主送（逗号分隔）" @blur="saveDispatchProfile" />
        <input v-model="dispatchProfile.cc" placeholder="抄送（逗号分隔）" @blur="saveDispatchProfile" />
        <input v-model="dispatchProfile.webhookUrl" placeholder="Webhook URL（可选）" @blur="saveDispatchProfile" />
        <input v-model="dispatchProfile.webhookToken" placeholder="Webhook Token（可选）" :password="true" @blur="saveDispatchProfile" />
        <input v-model="dispatchProfile.channelApiUrl" placeholder="渠道 API URL（可选）" @blur="saveDispatchProfile" />
        <input v-model="dispatchProfile.channelApiToken" placeholder="渠道 API Token（可选）" :password="true" @blur="saveDispatchProfile" />
        <input v-model="dispatchProfile.channelApiAppId" placeholder="渠道 API AppId（默认 mobile-alarm-review）" @blur="saveDispatchProfile" />
        <view class="app-row">
          <button size="mini" :type="dispatchProfile.channelApiGrayEnabled ? 'primary' : 'default'" @click="() => { dispatchProfile.channelApiGrayEnabled = !dispatchProfile.channelApiGrayEnabled; saveDispatchProfile(); }">
            渠道灰度
          </button>
          <button size="mini" :type="dispatchProfile.channelApiSignEnabled ? 'primary' : 'default'" @click="() => { dispatchProfile.channelApiSignEnabled = !dispatchProfile.channelApiSignEnabled; saveDispatchProfile(); }">
            签名校验
          </button>
        </view>
        <input v-model="dispatchProfile.channelApiGrayOrganizations" placeholder="灰度组织（逗号分隔，空=全部，all=通配）" @blur="saveDispatchProfile" />
        <input v-model="dispatchProfile.channelApiGrayShifts" placeholder="灰度班次（day/evening/night/all）" @blur="saveDispatchProfile" />
        <input v-model="dispatchProfile.channelApiSignSecret" placeholder="签名密钥（开启签名时必填）" :password="true" @blur="saveDispatchProfile" />
        <view class="app-row">
          <button size="mini" :type="dispatchRules.preset === 'strict' ? 'primary' : 'default'" @click="applyDispatchRulePreset('strict')">
            严格
          </button>
          <button size="mini" :type="dispatchRules.preset === 'balanced' ? 'primary' : 'default'" @click="applyDispatchRulePreset('balanced')">
            均衡
          </button>
          <button size="mini" :type="dispatchRules.preset === 'noise_reduction' ? 'primary' : 'default'" @click="applyDispatchRulePreset('noise_reduction')">
            降噪
          </button>
        </view>
        <view class="app-row">
          <button size="mini" :type="dispatchRules.muteHttp4xxAlerts ? 'primary' : 'default'" @click="toggleDispatchMuteHttp4xxAlerts">
            4xx降噪
          </button>
          <button size="mini" :type="dispatchRules.promoteNetworkToError ? 'primary' : 'default'" @click="toggleDispatchPromoteNetworkToError">
            网络升级错误
          </button>
        </view>
        <view class="app-row">
          <input v-model="dispatchRulePresetName" placeholder="通知策略名称（如：夜班降噪）" />
          <button size="mini" @click="saveCurrentDispatchRulePreset">保存策略</button>
          <button size="mini" @click="manualSyncDispatchRuleCenter">手动同步</button>
        </view>
        <view v-if="dispatchRuleConflict.hasConflict" class="app-gap-12" style="border:1rpx solid #F59E0B;border-radius:10rpx;padding:8rpx;">
          <text class="app-subtext">策略冲突：{{ dispatchRuleConflict.message }}</text>
          <view class="app-row">
            <button size="mini" @click="resolveDispatchRuleConflictUseServer">以服务端为准</button>
            <button size="mini" type="primary" @click="resolveDispatchRuleConflictUseLocal">以本地覆盖服务端</button>
          </view>
        </view>
        <view class="app-row">
          <picker mode="selector" :range="dispatchRulePresets.map((x) => x.name)" @change="(e) => { dispatchRulePresetSelected = dispatchRulePresets[Number(e?.detail?.value || 0)]?.name || '' }">
            <view class="app-subtext">当前命名策略：{{ dispatchRulePresetSelected || "未选择" }}</view>
          </picker>
          <button size="mini" @click="applySelectedDispatchRulePreset">应用策略</button>
          <button size="mini" @click="removeSelectedDispatchRulePreset">删除策略</button>
        </view>
        <text class="app-subtext">当前策略模板：{{ dispatchRules.preset }}</text>
        <text class="app-subtext">
          共享状态：{{ dispatchRuleSyncMeta.source }} / {{ dispatchRuleSyncMeta.lastSyncStatus }}
          {{ dispatchRuleSyncMeta.lastSyncAt ? `(${formatAuditTime(dispatchRuleSyncMeta.lastSyncAt)})` : "" }}
        </text>
        <text class="app-subtext">共享详情：{{ dispatchRuleSyncMeta.lastSyncMessage }}</text>
        <view class="app-gap-12" style="border:1rpx solid #E2E8F0;border-radius:10rpx;padding:8rpx;">
          <view class="app-row">
            <text class="app-subtext">通知策略审计（最近 {{ Math.min(dispatchRuleAudits.length, 8) }} 条）</text>
          </view>
          <view
            v-for="item in dispatchRuleAudits.slice(0, 8)"
            :key="item.id"
            class="app-gap-12"
            style="border:1rpx solid #E2E8F0;border-radius:10rpx;padding:8rpx;"
          >
            <text class="app-subtext">
              {{ dispatchRuleAuditSourceText(item.source) }} / {{ item.message }} {{ item.at ? `(${formatAuditTime(item.at)})` : "" }}
            </text>
            <view class="app-row">
              <text class="app-subtext">
                快照：模板={{ item.snapshot.rules.preset }} / 4xx降噪={{ item.snapshot.rules.muteHttp4xxAlerts ? "开" : "关" }} / 网络升级={{ item.snapshot.rules.promoteNetworkToError ? "开" : "关" }}
              </text>
              <button
                size="mini"
                :disabled="!presetWritable"
                :loading="dispatchRuleRollbackingAuditId === item.id"
                @click="rollbackDispatchRuleAudit(item)"
              >
                回滚到此
              </button>
            </view>
          </view>
          <AppEmpty v-if="dispatchRuleAudits.length === 0" text="暂无通知策略审计记录" />
        </view>
        <text class="app-subtext">
          分发状态：{{ dispatchStatus.lastStatus }} / 成功 {{ dispatchStatus.successCount }} / 失败 {{ dispatchStatus.failCount }}
        </text>
        <text class="app-subtext">最近结果：{{ dispatchStatus.lastMessage }} {{ dispatchStatus.lastAt ? `(${formatAuditTime(dispatchStatus.lastAt)})` : "" }}</text>
        <text class="app-subtext">
          渠道联调：请求 {{ dispatchChannelAnalytics.channelApiRequests }} / 灰度命中 {{ dispatchChannelAnalytics.grayHit }}/{{ dispatchChannelAnalytics.grayEvaluated }} / 灰度跳过 {{ dispatchChannelAnalytics.graySkipped }}
        </text>
        <text class="app-subtext">
          签名开启请求 {{ dispatchChannelAnalytics.signEnabledRequests }} / 防重放拒绝 {{ dispatchChannelAnalytics.replayRejected }} {{ dispatchChannelAnalytics.lastEval ? `(${formatAuditTime(dispatchChannelAnalytics.lastEval)})` : "" }}
        </text>
        <text class="app-subtext">联调最近消息：{{ dispatchChannelAnalytics.lastMessage }}</text>
        <text class="app-subtext">{{ getQueueReasonStatsText() }}</text>
        <text class="app-subtext">{{ getRecent24hRetrySuccessRateText() }}</text>
        <text class="app-subtext">{{ getDispatchHealthSummaryText() }}</text>
        <text class="app-subtext">{{ getDispatchHealthNextStepAdviceText() }}</text>
        <text class="app-subtext">{{ getAlarmTriageSummaryText() }}</text>
        <text class="app-subtext">{{ getAlarmTriageNextStepAdviceText() }}</text>
        <text class="app-subtext">{{ getDispatchAlertGovernanceSummaryText() }}</text>
        <text class="app-subtext">{{ getDispatchAlertGovernanceAdviceText() }}</text>
        <text class="app-subtext">{{ getDispatchFailureCategorySummaryText() }}</text>
        <text class="app-subtext">{{ getDispatchFailureCategoryAdviceText() }}</text>
        <view class="app-row">
          <button size="mini" @click="copyDispatchHealthSummary">复制分发健康摘要</button>
          <button size="mini" @click="copyAlarmTriageSummary">复制处置优先级摘要</button>
          <button size="mini" @click="copyDispatchAlertGovernanceSummary">复制通知处置摘要</button>
          <button size="mini" @click="copyDispatchFailureCategorySummary">复制失败分类摘要</button>
        </view>
        <text class="app-subtext">未读通知：{{ unresolvedDispatchAlertCount() }}</text>
        <view class="app-row">
          <button size="mini" :type="dispatchAlertFilter === 'all' ? 'primary' : 'default'" @click="dispatchAlertFilter = 'all'">全部通知</button>
          <button size="mini" :type="dispatchAlertFilter === 'error_only' ? 'primary' : 'default'" @click="dispatchAlertFilter = 'error_only'">仅错误</button>
          <button size="mini" @click="retryAllDispatchQueue">全部重试</button>
          <button size="mini" @click="clearDispatchRetryQueue">清空队列</button>
          <button size="mini" @click="clearResolvedDispatchAlerts">清理已读</button>
        </view>
        <view
          v-for="alert in filteredDispatchAlerts"
          :key="alert.id"
          class="app-row"
          style="border:1rpx solid #E2E8F0;border-radius:10rpx;padding:8rpx;"
        >
          <text class="app-subtext">
            [{{ alert.level }}] {{ alert.message }} {{ alert.createdAt ? `(${formatAuditTime(alert.createdAt)})` : "" }} {{ alert.resolved ? "（已读）" : "" }}
          </text>
          <button size="mini" :disabled="alert.resolved" @click="markDispatchAlertResolved(alert.id)">标记已读</button>
        </view>
        <AppEmpty v-if="filteredDispatchAlerts.length === 0" text="当前过滤条件下暂无分发通知" />
        <view
          v-for="item in dispatchRetryQueue"
          :key="item.id"
          class="app-row"
          style="border:1rpx solid #E2E8F0;border-radius:10rpx;padding:8rpx;"
        >
          <text class="app-subtext">
            {{ dispatchRetryModeText(item.dispatchMode) }} / {{ item.filename }} / 次数={{ item.attempts }} / {{ item.reasonType }} / {{ item.lastError || "-" }}
          </text>
          <button size="mini" @click="retryDispatchQueueItem(item.id)">重试</button>
        </view>
        <AppEmpty v-if="dispatchRetryQueue.length === 0" text="暂无分发失败队列" />
      </view>
      <view class="app-gap-12">
        <text class="app-subtext">最近复盘导出</text>
        <picker
          mode="selector"
          :range="['全部记录', '近24小时', '近7天']"
          :value="reviewExportWindowFilter === 'all' ? 0 : reviewExportWindowFilter === '24h' ? 1 : 2"
          @change="(e:any) => onReviewExportWindowFilterChange(Number(e?.detail?.value || 0))"
        >
          <view class="app-subtext">窗口筛选：{{ reviewExportWindowFilter === 'all' ? '全部记录' : (reviewExportWindowFilter === '24h' ? '近24小时' : '近7天') }}</view>
        </picker>
        <view class="app-row">
          <text class="app-subtext">窗口预设</text>
          <button size="mini" @click="applyReviewExportWindowPreset('strict')">严筛</button>
          <button size="mini" @click="applyReviewExportWindowPreset('balanced')">平衡</button>
          <button size="mini" @click="applyReviewExportWindowPreset('full')">全量</button>
        </view>
        <text class="app-subtext">当前窗口预设：{{ reviewExportWindowCurrentPresetLabel }}</text>
        <text class="app-subtext">{{ reviewExportWindowSummaryText }}</text>
        <text class="app-subtext">{{ reviewExportWindowHitRateText }}</text>
        <text class="app-subtext">{{ reviewExportWindowIntensityText }}</text>
        <text class="app-subtext">{{ reviewExportWindowModeText }}</text>
        <text class="app-subtext">窗口动作来源：{{ reviewExportWindowActionSourceText }}</text>
        <picker
          mode="selector"
          :range="['审计全部', '审计近24小时', '审计近7天']"
          :value="reviewExportWindowActionAuditFilter === 'all' ? 0 : reviewExportWindowActionAuditFilter === '24h' ? 1 : 2"
          @change="(e:any) => onReviewExportWindowActionAuditFilterChange(Number(e?.detail?.value || 0))"
        >
          <view class="app-subtext">动作审计窗口：{{ reviewExportWindowActionAuditFilter === 'all' ? '全部' : (reviewExportWindowActionAuditFilter === '24h' ? '近24小时' : '近7天') }}</view>
        </picker>
        <view class="app-row">
          <text class="app-subtext">审计预设</text>
          <button size="mini" @click="applyReviewExportWindowActionAuditPreset('strict')">严筛</button>
          <button size="mini" @click="applyReviewExportWindowActionAuditPreset('balanced')">平衡</button>
          <button size="mini" @click="applyReviewExportWindowActionAuditPreset('full')">全量</button>
        </view>
        <text class="app-subtext">当前审计预设：{{ reviewExportWindowActionAuditCurrentPresetLabel }}</text>
        <picker
          mode="selector"
          :range="['预设历史全部', '预设历史近24小时', '预设历史近7天']"
          :value="reviewExportWindowActionAuditPresetHistoryFilter === 'all' ? 0 : reviewExportWindowActionAuditPresetHistoryFilter === '24h' ? 1 : 2"
          @change="(e:any) => onReviewExportWindowActionAuditPresetHistoryFilterChange(Number(e?.detail?.value || 0))"
        >
          <view class="app-subtext">预设历史窗口：{{ reviewExportWindowActionAuditPresetHistoryFilter === 'all' ? '全部' : (reviewExportWindowActionAuditPresetHistoryFilter === '24h' ? '近24小时' : '近7天') }}</view>
        </picker>
        <view class="app-row">
          <text class="app-subtext">预设历史预设</text>
          <button size="mini" @click="applyReviewExportWindowActionAuditPresetHistoryPreset('strict')">严筛</button>
          <button size="mini" @click="applyReviewExportWindowActionAuditPresetHistoryPreset('balanced')">平衡</button>
          <button size="mini" @click="applyReviewExportWindowActionAuditPresetHistoryPreset('full')">全量</button>
        </view>
        <text class="app-subtext">当前预设历史预设：{{ reviewExportWindowActionAuditPresetHistoryCurrentPresetLabel }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryWindowSummaryText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryHitRateText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryIntensityText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryModeText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryNextRelaxStepText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryRelaxQueueText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryRelaxRemainingStepsText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryRelaxStateText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetTop1Text }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetRecentText }}</text>
        <text class="app-subtext">预设历史动作来源：{{ reviewExportWindowActionAuditPresetHistoryActionSourceText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditSourceTop1Text }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditRecentText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditWindowSummaryText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditHitRateText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditIntensityText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditModeText }}</text>
        <picker
          mode="selector"
          :range="['预设动作审计全部', '预设动作审计近24小时', '预设动作审计近7天']"
          :value="reviewExportWindowActionAuditPresetHistoryActionAuditFilter === 'all' ? 0 : reviewExportWindowActionAuditPresetHistoryActionAuditFilter === '24h' ? 1 : 2"
          @change="(e:any) => onReviewExportWindowActionAuditPresetHistoryActionAuditFilterChange(Number(e?.detail?.value || 0))"
        >
          <view class="app-subtext">预设动作审计窗口：{{ reviewExportWindowActionAuditPresetHistoryActionAuditFilter === 'all' ? '全部' : (reviewExportWindowActionAuditPresetHistoryActionAuditFilter === '24h' ? '近24小时' : '近7天') }}</view>
        </picker>
        <view class="app-row">
          <text class="app-subtext">预设动作预设</text>
          <button size="mini" @click="applyReviewExportWindowActionAuditPresetHistoryActionAuditPreset('strict')">严筛</button>
          <button size="mini" @click="applyReviewExportWindowActionAuditPresetHistoryActionAuditPreset('balanced')">平衡</button>
          <button size="mini" @click="applyReviewExportWindowActionAuditPresetHistoryActionAuditPreset('full')">全量</button>
        </view>
        <text class="app-subtext">当前预设动作预设：{{ reviewExportWindowActionAuditPresetHistoryActionAuditCurrentPresetLabel }}</text>
        <picker
          mode="selector"
          :range="['预设动作历史全部', '预设动作历史近24小时', '预设动作历史近7天']"
          :value="reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryFilter === 'all' ? 0 : reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryFilter === '24h' ? 1 : 2"
          @change="(e:any) => onReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryFilterChange(Number(e?.detail?.value || 0))"
        >
          <view class="app-subtext">预设动作预设历史窗口：{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryFilter === 'all' ? '全部' : (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryFilter === '24h' ? '近24小时' : '近7天') }}</view>
        </picker>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryWindowSummaryText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryHitRateText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryIntensityText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryModeText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryNextRelaxStepText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryRelaxQueueText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryRelaxRemainingStepsText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryRelaxStateText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryRelaxStateSummaryText }}</text>
        <text v-if="reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAction" class="app-subtext">上次预设动作历史放宽：{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAction }}</text>
        <text v-if="reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAt" class="app-subtext">预设动作历史放宽时间：{{ formatDateTime(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAt) }}</text>
        <text class="app-subtext">预设动作历史来源：{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionSourceText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditSourceTop1Text }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditRecentText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditWindowSummaryText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditHitRateText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditIntensityText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditModeText }}</text>
        <view class="app-row">
          <text class="app-subtext">预设动作历史动作审计预设</text>
          <button size="mini" @click="applyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPreset('strict')">严筛</button>
          <button size="mini" @click="applyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPreset('balanced')">平衡</button>
          <button size="mini" @click="applyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPreset('full')">全量</button>
        </view>
        <text class="app-subtext">当前预设动作历史动作审计预设：{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditCurrentPresetLabel }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetWindowSummaryText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHitRateText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetIntensityText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetModeText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryNextRelaxStepText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryRelaxQueueText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryRelaxRemainingStepsText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryRelaxStateText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryRelaxStateSummaryText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceSummaryText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceWindowSummaryText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceHitRateText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceIntensityText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceModeText }}</text>
        <view class="app-row">
          <text class="app-subtext">预设动作历史动作审计预设历史治理预设</text>
          <button size="mini" @click="applyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePreset('strict')">严筛</button>
          <button size="mini" @click="applyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePreset('balanced')">平衡</button>
          <button size="mini" @click="applyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePreset('full')">全量</button>
        </view>
        <text class="app-subtext">当前治理预设：{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceCurrentPresetLabel }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceNextRelaxStepText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceRelaxQueueText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceRelaxRemainingStepsText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceRelaxStateText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceSourceTop1Text }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceRecentText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceLastActionText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceLastActionSourceText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceLastActionAtText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetTop1Text }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetRecentText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditTop1Text }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditRecentText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditSummaryText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditLastActionText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditLastActionSourceText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditLastActionAtText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionSummaryText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageStateText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotHandoverText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestStateText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStateText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStateText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStateText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStateText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStateText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageConclusionText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageConclusionStateText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditNextRelaxStepText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditRelaxQueueText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditRelaxRemainingStepsText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditRelaxStateText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditWindowStateSummaryText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetWindowSummaryText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHitRateText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetIntensityText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetModeText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryNextRelaxStepText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryRelaxQueueText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryRelaxRemainingStepsText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryRelaxStateText }}</text>
        <text v-if="reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryLastRelaxAction" class="app-subtext">上次治理预设历史放宽：{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryLastRelaxAction }}</text>
        <text v-if="reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryLastRelaxAt" class="app-subtext">治理预设历史放宽时间：{{ formatDateTime(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryLastRelaxAt) }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetTop1Text }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetRecentText }}</text>
        <text v-if="reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAction" class="app-subtext">上次预设动作历史动作审计预设历史放宽：{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAction }}</text>
        <text v-if="reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAt" class="app-subtext">预设动作历史动作审计预设历史放宽时间：{{ formatDateTime(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryLastRelaxAt) }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditNextRelaxStepText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditRelaxQueueText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditRelaxRemainingStepsText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditRelaxStateText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditRelaxStateSummaryText }}</text>
        <text v-if="reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastRelaxAction" class="app-subtext">上次预设动作历史动作审计放宽：{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastRelaxAction }}</text>
        <text v-if="reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastRelaxAt" class="app-subtext">预设动作历史动作审计放宽时间：{{ formatDateTime(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastRelaxAt) }}</text>
        <text class="app-subtext">预设动作历史动作审计来源：{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditActionSourceText }}</text>
        <text v-if="reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastAction" class="app-subtext">最近预设动作历史动作审计动作：{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastAction }}</text>
        <text v-if="reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastActionAt" class="app-subtext">预设动作历史动作审计时间：{{ formatDateTime(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditLastActionAt) }}</text>
        <picker
          mode="selector"
          :range="['预设动作历史动作审计全部', '预设动作历史动作审计近24小时', '预设动作历史动作审计近7天']"
          :value="reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter === 'all' ? 0 : reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter === '24h' ? 1 : 2"
          @change="(e:any) => onReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceFilterChange(Number(e?.detail?.value || 0))"
        >
          <view class="app-subtext">预设动作历史动作审计窗口：{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter === 'all' ? '全部' : (reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter === '24h' ? '近24小时' : '近7天') }}</view>
        </picker>
        <text v-if="reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryLastAction" class="app-subtext">最近预设动作历史动作：{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryLastAction }}</text>
        <text v-if="reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryLastActionAt" class="app-subtext">预设动作历史动作时间：{{ formatDateTime(reviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryLastActionAt) }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetTop1Text }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditPresetRecentText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditNextRelaxStepText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditRelaxQueueText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditRelaxRemainingStepsText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditPresetHistoryActionAuditRelaxStateText }}</text>
        <text v-if="reviewExportWindowActionAuditPresetHistoryActionAuditLastRelaxAction" class="app-subtext">上次预设动作放宽：{{ reviewExportWindowActionAuditPresetHistoryActionAuditLastRelaxAction }}</text>
        <text v-if="reviewExportWindowActionAuditPresetHistoryActionAuditLastRelaxAt" class="app-subtext">预设动作放宽时间：{{ formatDateTime(reviewExportWindowActionAuditPresetHistoryActionAuditLastRelaxAt) }}</text>
        <text v-if="reviewExportWindowActionAuditPresetHistoryLastAction" class="app-subtext">最近预设历史动作：{{ reviewExportWindowActionAuditPresetHistoryLastAction }}</text>
        <text v-if="reviewExportWindowActionAuditPresetHistoryLastActionAt" class="app-subtext">预设历史动作时间：{{ formatDateTime(reviewExportWindowActionAuditPresetHistoryLastActionAt) }}</text>
        <text v-if="reviewExportWindowActionAuditPresetHistoryLastRelaxAction" class="app-subtext">上次预设历史放宽：{{ reviewExportWindowActionAuditPresetHistoryLastRelaxAction }}</text>
        <text v-if="reviewExportWindowActionAuditPresetHistoryLastRelaxAt" class="app-subtext">预设历史放宽时间：{{ formatDateTime(reviewExportWindowActionAuditPresetHistoryLastRelaxAt) }}</text>
        <text class="app-subtext">审计动作来源：{{ reviewExportWindowActionAuditActionSourceText }}</text>
        <text v-if="reviewExportWindowActionAuditLastAction" class="app-subtext">最近审计动作：{{ reviewExportWindowActionAuditLastAction }}</text>
        <text v-if="reviewExportWindowActionAuditLastActionAt" class="app-subtext">审计动作时间：{{ formatDateTime(reviewExportWindowActionAuditLastActionAt) }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditWindowSummaryText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditHitRateText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditIntensityText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditModeText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditSourceTop1Text }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditRecentText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditNextRelaxStepText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditRelaxQueueText }}</text>
        <text class="app-subtext">{{ reviewExportWindowActionAuditRelaxRemainingStepsText }}</text>
        <text v-if="reviewExportWindowActionAuditLastRelaxAction" class="app-subtext">上次审计放宽：{{ reviewExportWindowActionAuditLastRelaxAction }}</text>
        <text v-if="reviewExportWindowActionAuditLastRelaxAt" class="app-subtext">审计放宽时间：{{ formatDateTime(reviewExportWindowActionAuditLastRelaxAt) }}</text>
        <text class="app-subtext">{{ reviewExportWindowNextRelaxStepText }}</text>
        <text class="app-subtext">{{ reviewExportWindowRelaxQueueText }}</text>
        <text class="app-subtext">{{ reviewExportWindowRelaxRemainingStepsText }}</text>
        <text class="app-subtext">{{ reviewExportShiftTop1Text }}</text>
        <text class="app-subtext">{{ reviewExportShiftStatsText }}</text>
        <text class="app-subtext">{{ reviewExportOrganizationTop1Text }}</text>
        <text v-if="reviewExportWindowLastRelaxAction" class="app-subtext">上次放宽：{{ reviewExportWindowLastRelaxAction }}</text>
        <text v-if="reviewExportWindowLastRelaxAt" class="app-subtext">放宽时间：{{ formatDateTime(reviewExportWindowLastRelaxAt) }}</text>
        <text v-if="reviewExportWindowLastAction" class="app-subtext">最近窗口动作：{{ reviewExportWindowLastAction }}</text>
        <text v-if="reviewExportWindowLastActionAt" class="app-subtext">窗口动作时间：{{ formatDateTime(reviewExportWindowLastActionAt) }}</text>
        <view class="app-row">
          <button size="mini" @click="copyReviewExportHistoryCsv">复制导出CSV</button>
          <button size="mini" @click="copyReviewExportWindowCsv">复制窗口CSV</button>
          <button size="mini" @click="copyReviewExportWindowSummary">复制窗口摘要</button>
          <button size="mini" @click="copyReviewExportWindowPresetSummary">复制预设摘要</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetSummary">复制审计预设摘要</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryPresetSummary">复制预设历史预设</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistorySummary">复制审计预设历史</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryCsv">复制审计预设CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditJson">复制预设动作JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditCsv">复制预设动作CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetSummary">复制预设动作预设</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistorySummary">复制预设动作历史</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryCsv">复制预设动作历史CSV</button>
          <button size="mini" @click="resetReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryFilter">重置预设动作历史窗口</button>
          <button size="mini" @click="relaxReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryFilter">放宽预设动作历史</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryRelaxSummary">复制预设动作历史放宽</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryRelaxStateSummary">复制预设动作历史放宽状态</button>
          <button size="mini" @click="clearReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryRelaxHistory">清空预设动作历史放宽</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionSummary">复制预设动作历史动作</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditJson">复制预设动作历史动作JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditCsv">复制预设动作历史动作CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditSummary">复制预设动作历史动作摘要</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetSummary">复制预设动作历史动作预设</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistorySummary">复制预设动作历史动作预设历史</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryCsv">复制预设动作历史动作预设CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryJson">复制预设动作历史动作预设JSON</button>
          <button size="mini" @click="relaxReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistory">放宽预设动作历史动作预设历史</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryRelaxSummary">复制预设动作历史动作预设放宽</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryRelaxStateSummary">复制预设动作历史动作预设放宽状态</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceSummary">复制预设动作历史动作预设治理摘要</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceAuditSummary">复制预设动作历史动作预设治理审计</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceAuditJson">复制预设动作历史动作预设治理JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryGovernanceAuditCsv">复制预设动作历史动作预设治理CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetSummary">复制预设动作历史动作预设治理预设</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistorySummary">复制预设动作历史动作预设治理预设历史</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryCsv">复制预设动作历史动作预设治理预设CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryJson">复制预设动作历史动作预设治理预设JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditSummary">复制治理预设历史审计摘要</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionSummary">复制治理预设历史审计动作摘要</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionJson">复制治理预设历史审计动作JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionCsv">复制治理预设历史审计动作CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackage">复制治理预设历史审计动作组合包</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageState">复制治理预设历史审计动作组合包状态</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageJson">复制治理预设历史审计动作组合包JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageCsv">复制治理预设历史审计动作组合包CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshot">复制治理预设历史审计动作组合包快照</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotJson">复制治理预设历史审计动作组合包快照JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotCsv">复制治理预设历史审计动作组合包快照CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigest">复制治理预设历史审计动作组合包快照指纹</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestJson">复制治理预设历史审计动作组合包快照指纹JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestCsv">复制治理预设历史审计动作组合包快照指纹CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestState">复制治理预设历史审计动作组合包快照指纹状态</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestPackageJson">复制治理预设历史审计动作组合包快照指纹交接包JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestPackageCsv">复制治理预设历史审计动作组合包快照指纹交接包CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusion">复制治理预设历史审计动作组合包快照指纹交接结论</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionJson">复制治理预设历史审计动作组合包快照指纹交接结论JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionCsv">复制治理预设历史审计动作组合包快照指纹交接结论CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionState">复制治理预设历史审计动作组合包快照指纹交接结论状态</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStateJson">复制治理预设历史审计动作组合包快照指纹交接结论状态JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStateCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackage">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandover">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverState">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStateJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStateCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackage">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusion">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionState">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStateJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStateCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackage">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandover">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverState">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackage">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusion">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionState">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackage">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandover">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverState">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackage">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusion">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionState">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackage">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandover">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverState">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackage">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusion">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionState">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandover">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverState">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStateCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackage">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusion">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionState">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStateCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackage">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusion">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionState">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStateJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStateCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackage">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusion">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionState">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStateJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStateCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackage">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageConclusion">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageConclusionJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageConclusionCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageConclusionState">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论状态</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageConclusionStateJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论状态JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageConclusionStateCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论状态CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackage">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论状态交接包</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageJson">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论状态交接包JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditActionPackageSnapshotDigestConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageHandoverStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageConclusionStatePackageCsv">复制治理预设历史审计动作组合包快照指纹交接结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包交接摘要状态总包结论状态交接包结论状态交接包结论状态交接包结论状态交接包CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditJson">复制治理预设历史审计JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditCsv">复制治理预设历史审计CSV</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditRelaxStateSummary">复制治理预设历史审计放宽状态</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditWindowStateSummary">复制治理预设历史审计窗口状态</button>
          <button size="mini" @click="resetReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAuditWindow">重置治理预设历史审计窗口</button>
          <button size="mini" @click="clearReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryAudit">清空治理预设历史审计记录</button>
          <button size="mini" @click="relaxReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistory">放宽预设动作历史动作预设治理预设历史</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryRelaxStateSummary">复制预设动作历史动作预设治理预设历史放宽状态</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryWindowStateSummary">复制预设动作历史动作预设治理预设历史窗口状态</button>
          <button size="mini" @click="resetReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryWindow">重置预设动作历史动作预设治理预设历史</button>
          <button size="mini" @click="clearReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistoryRelaxHistory">清空预设动作历史动作预设治理预设历史放宽</button>
          <button size="mini" @click="clearReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernancePresetHistory">清空预设动作历史动作预设治理预设历史</button>
          <button size="mini" @click="relaxReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceWindow">放宽预设动作历史动作预设治理窗口</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceRelaxStateSummary">复制预设动作历史动作预设治理放宽状态</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceWindowStateSummary">复制预设动作历史动作预设治理窗口状态</button>
          <button size="mini" @click="resetReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceWindow">重置预设动作历史动作预设治理窗口</button>
          <button size="mini" @click="clearReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditGovernanceAudit">清空预设动作历史动作预设治理审计</button>
          <button size="mini" @click="resetReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryWindow">重置预设动作历史动作预设历史</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryResetStateSummary">复制预设动作历史动作预设重置状态</button>
          <button size="mini" @click="clearReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistoryRelaxHistory">清空预设动作历史动作预设放宽</button>
          <button size="mini" @click="resetReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter">重置预设动作历史动作审计窗口</button>
          <button size="mini" @click="relaxReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditFilter">放宽预设动作历史动作审计</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditRelaxSummary">复制预设动作历史动作放宽</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditRelaxStateSummary">复制预设动作历史动作放宽状态</button>
          <button size="mini" @click="clearReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditRelaxHistory">清空预设动作历史动作放宽</button>
          <button size="mini" @click="clearReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAuditPresetHistory">清空预设动作历史动作预设历史</button>
          <button size="mini" @click="clearReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistoryActionAudit">清空预设动作历史动作审计</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditSummary">复制预设动作摘要</button>
          <button size="mini" @click="clearReviewExportWindowActionAuditPresetHistoryActionAuditPresetHistory">清空预设动作历史</button>
          <button size="mini" @click="clearReviewExportWindowActionAuditPresetHistoryActionAudit">清空预设动作审计</button>
          <button size="mini" @click="resetReviewExportWindowActionAuditPresetHistoryActionAuditWindow">重置预设动作窗口</button>
          <button size="mini" @click="relaxReviewExportWindowActionAuditPresetHistoryActionAuditWindow">放宽预设动作窗口</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryActionAuditRelaxSummary">复制预设动作放宽</button>
          <button size="mini" @click="clearReviewExportWindowActionAuditPresetHistoryActionAuditRelaxHistory">清空预设动作放宽</button>
          <button size="mini" @click="relaxReviewExportWindowActionAuditPresetHistoryFilter">放宽审计预设窗口</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditPresetHistoryRelaxSummary">复制预设放宽</button>
          <button size="mini" @click="clearReviewExportWindowActionAuditPresetHistoryRelaxHistory">清空预设放宽记录</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditSummary">复制动作审计摘要</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditJson">复制动作审计JSON</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditCsv">复制动作审计CSV</button>
          <button size="mini" @click="relaxReviewExportWindowActionAuditFilter">放宽审计窗口</button>
          <button size="mini" @click="copyReviewExportWindowActionAuditRelaxSummary">复制审计放宽</button>
          <button size="mini" @click="clearReviewExportWindowActionAuditRelaxHistory">清空审计放宽记录</button>
          <button size="mini" @click="resetReviewExportWindowActionAuditFilter">重置审计窗口</button>
          <button size="mini" @click="resetReviewExportWindowActionAuditPresetHistoryFilter">重置审计预设窗口</button>
          <button size="mini" @click="clearReviewExportWindowActionAuditPresetHistory">清空审计预设历史</button>
          <button size="mini" @click="clearReviewExportWindowActionAudit">清空动作审计</button>
          <button size="mini" @click="relaxReviewExportWindowFilter">放宽窗口</button>
          <button size="mini" @click="copyReviewExportWindowRelaxStateSummary">复制放宽状态</button>
          <button size="mini" @click="copyReviewExportWindowRelaxSummary">复制放宽记录</button>
          <button size="mini" @click="clearReviewExportWindowRelaxHistory">清空放宽记录</button>
          <button size="mini" @click="resetReviewExportWindowFilter">重置窗口</button>
          <button size="mini" @click="clearReviewExportHistory">清空导出记录</button>
        </view>
        <view
          v-for="(item, idx) in filteredReviewExportHistory"
          :key="`${item.generatedAt}-${idx}`"
          class="app-row"
          style="border:1rpx solid #E2E8F0;border-radius:10rpx;padding:8rpx;"
        >
          <text class="app-subtext">
            {{ item.shiftLabel }} / {{ item.windowLabel }} / 类型={{ item.alarmType }} / 组织={{ item.organization }}
          </text>
          <button size="mini" @click="quickReExportReviewPackage(item)">复导</button>
        </view>
        <AppEmpty v-if="filteredReviewExportHistory.length === 0" text="当前窗口下暂无复盘包导出记录" />
      </view>
      <view class="app-row">
        <text class="app-subtext">{{ compareSummary.title }} 当前：{{ compareSummary.current }}</text>
        <text class="app-subtext">上一周期：{{ compareSummary.previous }}</text>
      </view>
      <view class="app-row">
        <text class="app-subtext">变化：{{ compareSummary.pct }}%</text>
      </view>
      <AppBarChart :items="crossDayChartData" color="#0EA5E9" :min-width-rpx="900" empty-text="暂无跨日趋势数据" />
      <AppStatusTag :text="trendLoading ? '计算中' : '已更新'" :type="trendLoading ? 'warning' : 'success'" />
    </view>

    <view class="app-card app-gap-12">
      <text class="app-title" style="font-size:30rpx">近 24 小时告警趋势</text>
      <AppBarChart :items="hourlyChartData" color="#2563EB" :min-width-rpx="1300" empty-text="暂无小时趋势数据" />
    </view>

    <view class="app-card app-gap-12">
      <text class="app-title" style="font-size:30rpx">按等级分布</text>
      <AppBarChart :items="levelChartData" color="#F59E0B" :min-width-rpx="900" empty-text="暂无等级分布数据" />
    </view>

    <view class="app-card app-gap-12">
      <text class="app-title" style="font-size:30rpx">告警类型分布</text>
      <AppBarChart
        :items="alarmTypeChartData"
        color="#0D9488"
        :min-width-rpx="900"
        empty-text="暂无告警类型分布数据"
        @item-click="onAlarmTypeChartClick"
      />
    </view>

    <view class="app-card app-gap-12">
      <text class="app-title" style="font-size:30rpx">Top 告警设备</text>
      <AppBarChart :items="topDeviceChartData" color="#14B8A6" :min-width-rpx="900" empty-text="暂无设备分布数据" />
    </view>

    <view class="app-card app-gap-12">
      <text class="app-title" style="font-size:30rpx">处置人维度</text>
      <AppBarChart :items="assigneeChartData" color="#8B5CF6" :min-width-rpx="900" empty-text="暂无处置人维度数据" />
    </view>

    <view class="app-card app-gap-12">
      <text class="app-title" style="font-size:30rpx">组织维度</text>
      <AppBarChart
        :items="organizationChartData"
        color="#06B6D4"
        :min-width-rpx="900"
        empty-text="暂无组织维度数据"
        @item-click="onOrganizationChartClick"
      />
    </view>

    <view class="app-card app-gap-12">
      <text class="app-title" style="font-size:30rpx">告警列表概览</text>
      <text class="app-subtext">{{ alarmListSummaryText }}</text>
      <text class="app-subtext">{{ alarmListFilterHitRateText }}</text>
      <text class="app-subtext">{{ alarmListRiskSummaryText }}</text>
      <text class="app-subtext">{{ alarmListNextStepAdviceText }}</text>
      <text class="app-subtext">{{ alarmFilterSnapshotText }}</text>
      <text class="app-subtext">{{ alarmSavedSnapshotText }}</text>
      <view class="app-row">
        <button size="mini" @click="copyAlarmListOverviewSummary">复制概览摘要</button>
        <button size="mini" @click="copyAlarmFilterSnapshot">复制筛选快照</button>
        <button size="mini" @click="saveAlarmFilterSnapshot">保存快照</button>
        <button size="mini" @click="restoreAlarmFilterSnapshot">还原快照</button>
      </view>
      <view v-if="alarmFilterSnapshotHistory.length" class="app-gap-12" style="border:1rpx solid #E2E8F0;border-radius:10rpx;padding:10rpx;">
        <text class="app-subtext">最近快照（最多3条）</text>
        <view class="app-row">
          <button size="mini" @click="exportAlarmFilterSnapshotHistoryJson">导出JSON</button>
          <button size="mini" @click="toggleImportAlarmFilterSnapshotPanel">{{ importSnapshotInputVisible ? "取消导入" : "导入JSON" }}</button>
          <button size="mini" @click="clearAlarmFilterSnapshotHistory">清空历史</button>
        </view>
        <view v-if="importSnapshotInputVisible" class="app-gap-12" style="border:1rpx solid #E2E8F0;border-radius:10rpx;padding:8rpx;">
          <textarea
            v-model="importSnapshotJsonText"
            class="app-input"
            auto-height
            :maxlength="-1"
            placeholder="粘贴由“导出JSON”复制的快照历史内容"
          />
          <view class="app-row">
            <button size="mini" type="primary" @click="importAlarmFilterSnapshotHistoryJson">确认导入</button>
          </view>
        </view>
        <view v-for="(snap, idx) in alarmFilterSnapshotHistory" :key="`alarm-snap-${idx}-${snap.savedAt}`" class="app-row">
          <text class="app-subtext">
            #{{ idx + 1 }} 类型={{ snap.selectedAlarmType || "全部类型" }}；组织={{ snap.selectedOrganizationLabel || snap.selectedOrganization || "全部组织" }}；
            预设={{ alarmQuickPresetLabelByValue(snap.alarmQuickPreset) }}；下钻={{ snap.selectedSlowAlarmId || "未启用" }}{{ snap.savedAt ? `；${snap.savedAt}` : "" }}
          </text>
          <button size="mini" @click="restoreAlarmFilterSnapshotByIndex(idx)">还原该条</button>
        </view>
      </view>
    </view>

    <view v-for="item in filteredAlarms" :key="item.id" class="app-card app-gap-12">
      <view class="app-row">
        <text>{{ item.description || "未命名告警" }}</text>
        <AppStatusTag :text="item.level || 'normal'" :type="levelColor(item.level) === '#EF4444' ? 'danger' : levelColor(item.level) === '#F59E0B' ? 'warning' : 'success'" />
      </view>
      <text class="app-subtext">设备：{{ item.device_id || "-" }}</text>
      <text class="app-subtext">时间：{{ item.created_at || item.time || "-" }}</text>
      <view class="app-row">
        <text class="app-subtext">状态：{{ alarmStateText(item) }}</text>
        <text class="app-subtext">优先级：{{ alarmPriorityText(item) }}</text>
        <AppStatusTag :text="pickStatus(item).text" :type="pickStatus(item).type" />
      </view>
      <view class="app-row">
        <text class="app-subtext">处置动作</text>
        <button size="mini" type="primary" @click="openActions(item)">展开处置</button>
        <button
          size="mini"
          :disabled="item.escalation_state === 'acknowledged'"
          :loading="quickActionAlarmId === `${item.id}:ack`"
          @click="quickAck(item)"
        >
          快速确认
        </button>
        <button
          size="mini"
          :disabled="item.escalation_state === 'acknowledged'"
          :loading="quickActionAlarmId === `${item.id}:escalate`"
          @click="quickEscalate(item)"
        >
          快速升级
        </button>
      </view>
      <view class="app-row">
        <text class="app-subtext">联动动作</text>
        <button size="mini" @click="openAlarmPlayback(item, 5)">回放5分钟</button>
        <button size="mini" @click="openAlarmTvWall(item)">上墙</button>
        <button size="mini" @click="openAlarmVisualCommand(item)">可视指挥</button>
        <button size="mini" @click="openCommand(item)">会商联动</button>
      </view>

      <view v-if="selectedAlarmId === item.id" class="app-gap-12" style="margin-top: 8rpx">
        <input v-model="actionNote" placeholder="处置备注（可选）" />
        <input v-model="dispatchTitle" placeholder="派单标题" />
        <input v-model="dispatchDesc" placeholder="派单描述（可选）" />
        <view class="app-row">
          <button size="mini" :loading="actionLoading" @click="doAck">确认</button>
          <button size="mini" :loading="actionLoading" @click="doEscalate">升级</button>
          <button size="mini" type="primary" :loading="actionLoading" @click="doDispatch">派单</button>
        </view>
      </view>
    </view>

    <AppEmpty v-if="!loading && filteredAlarms.length === 0" text="当前筛选条件下无告警" />

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-title" style="font-size:30rpx">处置工单</text>
        <button size="mini" :loading="workOrderLoading" @click="loadWorkOrders">刷新</button>
      </view>
      <view class="app-gap-12" style="border:1rpx solid #E2E8F0;border-radius:10rpx;padding:10rpx;">
        <text class="app-subtext">跨页回传聚合（24h）</text>
        <text class="app-subtext">回传次数：{{ workOrderReturnEvents24h.length }} / 状态变更：{{ workOrderReturnChangedCount24h }}</text>
        <text class="app-subtext">
          状态分布：待处理 {{ workOrderReturnStatusStats24h.open }} / 处理中 {{ workOrderReturnStatusStats24h.in_progress }} / 已解决 {{ workOrderReturnStatusStats24h.resolved }} / 已关闭 {{ workOrderReturnStatusStats24h.closed }}
        </text>
        <view
          v-for="item in workOrderReturnEvents.slice(0, 5)"
          :key="item.id"
          class="app-row"
          style="border:1rpx solid #E2E8F0;border-radius:10rpx;padding:8rpx;"
        >
          <text class="app-subtext">
            {{ workOrderReturnSourceText(item.source) }} / 工单 {{ item.workOrderId || "-" }} / {{ item.fromStatus || "-" }} -> {{ item.toStatus || "-" }} {{ item.at ? `(${formatAuditTime(item.at)})` : "" }}
          </text>
        </view>
        <AppEmpty v-if="workOrderReturnEvents.length === 0" text="暂无跨页回传记录" />
      </view>
      <AppBarChart
        :items="workOrderStatusChartData"
        color="#7C3AED"
        :min-width-rpx="900"
        empty-text="暂无工单状态分布"
        @item-click="onWorkOrderStatusChartClick"
      />
      <view class="app-row">
        <button size="mini" :type="workOrderStatusFilter === '' ? 'primary' : 'default'" @click="workOrderStatusFilter = ''">全部({{ workOrders.length }})</button>
        <button size="mini" :type="workOrderStatusFilter === 'open' ? 'primary' : 'default'" @click="workOrderStatusFilter = 'open'">待处理({{ workOrderStatusStats.open }})</button>
        <button size="mini" :type="workOrderStatusFilter === 'in_progress' ? 'primary' : 'default'" @click="workOrderStatusFilter = 'in_progress'">处理中({{ workOrderStatusStats.in_progress }})</button>
        <button size="mini" :type="workOrderStatusFilter === 'resolved' ? 'primary' : 'default'" @click="workOrderStatusFilter = 'resolved'">已解决({{ workOrderStatusStats.resolved }})</button>
        <button size="mini" :type="workOrderStatusFilter === 'closed' ? 'primary' : 'default'" @click="workOrderStatusFilter = 'closed'">已关闭({{ workOrderStatusStats.closed }})</button>
      </view>
      <view class="app-row">
        <picker mode="selector" :range="workOrderAssigneeOptions" range-key="label" @change="onWorkOrderAssigneeChange">
          <view class="app-subtext">处置人：{{ workOrderAssigneeOptions.find((x) => x.value === workOrderAssigneeFilter)?.label || "全部人员" }}</view>
        </picker>
        <picker mode="selector" :range="workOrderPriorityOptions" range-key="label" @change="onWorkOrderPriorityChange">
          <view class="app-subtext">优先级：{{ workOrderPriorityOptions.find((x) => x.value === workOrderPriorityFilter)?.label || "全部优先级" }}</view>
        </picker>
      </view>
      <view class="app-row">
        <input v-model="workOrderAlarmKeyword" placeholder="按关联告警ID关键字筛选" />
        <button size="mini" :type="workOrderTimeFilter === '' ? 'primary' : 'default'" @click="workOrderTimeFilter = ''">全部时间</button>
        <button size="mini" :type="workOrderTimeFilter === 'today' ? 'primary' : 'default'" @click="workOrderTimeFilter = 'today'">24h</button>
        <button size="mini" :type="workOrderTimeFilter === '7d' ? 'primary' : 'default'" @click="workOrderTimeFilter = '7d'">7天</button>
      </view>
      <view v-for="wo in filteredWorkOrders" :key="wo.id" class="app-gap-12" style="border:1rpx solid #E2E8F0;border-radius:10rpx;padding:12rpx;">
        <view class="app-row">
          <text>{{ wo.title }}</text>
          <AppStatusTag :text="statusTag(wo.status).text" :type="statusTag(wo.status).type" />
        </view>
        <text class="app-subtext">关联告警：{{ wo.alarm_id || "-" }}</text>
        <view class="app-row">
          <button size="mini" @click="openWorkOrderDetail(wo)">详情</button>
          <button size="mini" :disabled="wo.status !== 'open'" :loading="actionLoading" @click="moveStatus(wo, 'in_progress')">接单</button>
          <button size="mini" :disabled="wo.status !== 'in_progress'" :loading="actionLoading" @click="moveStatus(wo, 'resolved')">解决</button>
          <button size="mini" :disabled="wo.status === 'closed'" :loading="actionLoading" @click="moveStatus(wo, 'closed')">关闭</button>
        </view>
      </view>
      <AppEmpty v-if="!workOrderLoading && filteredWorkOrders.length === 0" text="当前筛选下暂无处置工单" />
    </view>
  </view>
</template>
