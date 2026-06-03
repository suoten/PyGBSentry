import { request } from "@/utils/request";

export interface AlarmItem {
  id: string;
  device_id?: string;
  channel_id?: string;
  priority?: number;
  alarm_type?: string;
  level?: string;
  description?: string;
  created_at?: string;
  time?: string;
  status?: string | number;
  escalation_state?: "open" | "acknowledged";
  escalation_level?: number;
  ack_at?: string;
}

export interface SlaOverview {
  total_open: number;
  escalated_open: number;
  overdue_open: number;
  acknowledged_today: number;
  avg_ack_minutes_today: number;
}

export interface SlaCompareOverview {
  days: number;
  period_current: number;
  period_previous: number;
  period_change_pct: number;
  day_current: number;
  day_previous: number;
  day_change_pct: number;
}

export interface SlaQualityOverview {
  days: number;
  p50_ack_minutes: number;
  p90_ack_minutes: number;
  samples: number;
  level_distribution: Record<string, number>;
  alarm_type_distribution: Record<string, number>;
  organization_distribution: Record<string, number>;
  slow_samples?: SlaQualitySlowSample[];
}

export interface SlaQualitySlowSample {
  alarm_id: string;
  device_id?: string;
  alarm_type: string;
  level: string;
  organization_id: string;
  ack_minutes: number;
  alarm_time?: string;
  ack_at?: string;
}

export interface AlarmDashboardPresetItem {
  name: string;
  config: Record<string, unknown>;
}

export interface AlarmDashboardPresetAuditItem {
  audit_id: string;
  action: string;
  operator: string;
  result: string;
  created_at: string;
  summary: string;
  preset_count: number;
}

export interface AlarmNotificationItem {
  id: string;
  tenant_id?: string;
  alarm_id?: string;
  device_id?: string;
  channel_id?: string;
  channel: string;
  status: "success" | "fail";
  error_message?: string;
  description?: string;
  sent_at?: string;
}

export interface AlarmLinkRuleItem {
  id: string;
  name: string;
  enabled?: boolean;
  min_priority?: number | null;
  max_priority?: number | null;
  start_time?: string | null;
  end_time?: string | null;
  days?: string | null;
  organization_id?: string | null;
  link_record?: boolean;
  link_wall?: boolean;
  link_notify?: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface FetchAlarmsParams {
  skip?: number;
  limit?: number;
  start_time?: string;
  end_time?: string;
  escalation_state?: "open" | "acknowledged";
  min_escalation_level?: number;
}

export function fetchAlarms(params: FetchAlarmsParams = {}) {
  const query = new URLSearchParams();
  query.set("skip", String(params.skip ?? 0));
  query.set("limit", String(params.limit ?? 100));
  if (params.start_time) query.set("start_time", params.start_time);
  if (params.end_time) query.set("end_time", params.end_time);
  if (params.escalation_state) query.set("escalation_state", params.escalation_state);
  if (typeof params.min_escalation_level === "number") {
    query.set("min_escalation_level", String(params.min_escalation_level));
  }
  return request<{ items: AlarmItem[] }>({
    url: `/api/v1/alarms?${query.toString()}`
  });
}

export function fetchSlaOverview() {
  return request<SlaOverview>({
    url: "/api/v1/alarms/sla/overview"
  });
}

export function fetchSlaCompare(days = 7, alarmType = "", organizationId = "") {
  const query = new URLSearchParams();
  query.set("days", String(days));
  if (alarmType) query.set("alarm_type", alarmType);
  if (organizationId) query.set("organization_id", organizationId);
  return request<SlaCompareOverview>({
    url: `/api/v1/alarms/sla/compare?${query.toString()}`
  });
}

export function fetchSlaQuality(days = 7, alarmType = "", organizationId = "") {
  const query = new URLSearchParams();
  query.set("days", String(days));
  if (alarmType) query.set("alarm_type", alarmType);
  if (organizationId) query.set("organization_id", organizationId);
  return request<SlaQualityOverview>({
    url: `/api/v1/alarms/sla/quality?${query.toString()}`
  });
}

export function fetchSlaPresets() {
  return request<{ items: AlarmDashboardPresetItem[]; writable?: boolean }>({
    url: "/api/v1/alarms/sla/presets"
  });
}

export function saveSlaPresets(items: AlarmDashboardPresetItem[]) {
  return request<{ items: AlarmDashboardPresetItem[] }>({
    url: "/api/v1/alarms/sla/presets",
    method: "PUT",
    data: { items }
  });
}

export function fetchSlaPresetAudits(limit = 10) {
  const query = new URLSearchParams();
  query.set("limit", String(limit));
  return request<AlarmDashboardPresetAuditItem[]>({
    url: `/api/v1/alarms/sla/presets/audits?${query.toString()}`
  });
}

export interface FetchAlarmNotificationsParams {
  skip?: number;
  limit?: number;
  channel?: "" | "sms" | "wecom" | "feishu";
  status?: "" | "success" | "fail";
  start_time?: string;
  end_time?: string;
}

export function fetchAlarmNotifications(params: FetchAlarmNotificationsParams = {}) {
  const query = new URLSearchParams();
  query.set("skip", String(params.skip ?? 0));
  query.set("limit", String(params.limit ?? 20));
  if (params.channel) query.set("channel", params.channel);
  if (params.status) query.set("status", params.status);
  if (params.start_time) query.set("start_time", params.start_time);
  if (params.end_time) query.set("end_time", params.end_time);
  return request<{ items: AlarmNotificationItem[]; total: number; skip: number; limit: number }>({
    url: `/api/v1/alarms/notifications?${query.toString()}`
  });
}

export function triggerAlertChannelTest(channelPluginId: string) {
  return request<{ ok?: boolean; message?: string }>({
    url: "/api/v1/plugins/alert-test",
    method: "POST",
    data: { channel: channelPluginId }
  });
}

export interface AlarmLinkRulePayload {
  name: string;
  enabled: boolean;
  min_priority?: number | null;
  max_priority?: number | null;
  start_time?: string | null;
  end_time?: string | null;
  days?: string | null;
  organization_id?: string | null;
  link_record: boolean;
  link_wall: boolean;
  link_notify: boolean;
}

export function fetchAlarmLinkRules() {
  return request<AlarmLinkRuleItem[]>({
    url: "/api/v1/alarms/link-rules"
  });
}

export function createAlarmLinkRule(payload: AlarmLinkRulePayload) {
  return request<{ id: string }>({
    url: "/api/v1/alarms/link-rules",
    method: "POST",
    data: payload
  });
}

export function updateAlarmLinkRule(ruleId: string, payload: AlarmLinkRulePayload) {
  return request<{ id: string }>({
    url: `/api/v1/alarms/link-rules/${encodeURIComponent(ruleId)}`,
    method: "PUT",
    data: payload
  });
}

export function deleteAlarmLinkRule(ruleId: string) {
  return request<{ ok: boolean }>({
    url: `/api/v1/alarms/link-rules/${encodeURIComponent(ruleId)}`,
    method: "DELETE"
  });
}

export function acknowledgeAlarm(alarmId: string, note = "") {
  return request<{ ok: boolean; alarm_id: string; state: string }>({
    url: `/api/v1/alarms/${encodeURIComponent(alarmId)}/ack`,
    method: "POST",
    data: { note }
  });
}

export function escalateAlarm(alarmId: string, note = "") {
  return request<{ ok: boolean; alarm_id: string; escalation_level: number }>({
    url: `/api/v1/alarms/${encodeURIComponent(alarmId)}/escalate`,
    method: "POST",
    data: { note }
  });
}
