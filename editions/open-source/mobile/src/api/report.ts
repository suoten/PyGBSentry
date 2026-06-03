import { request } from "@/utils/request";

export interface ReportSummaryItem {
  name: string;
  value?: number;
  updated_at?: string;
}

export interface ReportSummaryResult {
  items: ReportSummaryItem[];
  stats?: {
    device_count?: number;
    alarm_today?: number;
    active_streams?: number;
  };
  message?: string;
}

export interface ReportListItem {
  id: string;
  name: string;
  source: string;
  export_formats?: string[];
}

export interface ReportListResult {
  reports: ReportListItem[];
  total: number;
}

export interface AlarmStatsItem {
  name: string;
  value: number;
}

export interface TrafficPoint {
  t: string;
  value?: number;
  value_kbps?: number;
}

export interface TrafficResult {
  start_time?: string;
  end_time?: string;
  summary?: {
    avg_streams?: number;
    max_streams?: number;
    avg_bandwidth_kbps?: number;
    max_bandwidth_kbps?: number;
    sample_count?: number;
  };
  streams?: TrafficPoint[];
  bandwidth?: TrafficPoint[];
}

export interface CloseoutSummaryResult {
  window_days: number;
  policy_env_filter?: string | null;
  total: number;
  by_env?: Record<string, number>;
  by_reason_code?: Record<string, number>;
  by_closeout_reason_code?: Record<string, number>;
  trend_by_day?: Record<string, number>;
  latest?: Record<string, any> | null;
}

export interface CloseoutDrilldownItem {
  event_id: string;
  received_at?: string;
  policy_env?: string;
  reason_code?: string;
  closeout_reason_code?: string;
  run_id?: string;
}

export interface CloseoutDrilldownResult {
  total: number;
  limit: number;
  offset: number;
  items: CloseoutDrilldownItem[];
}

export function fetchReportSummary() {
  return request<ReportSummaryResult>({
    url: "/api/v1/reports/summary"
  });
}

export function fetchReportList() {
  return request<ReportListResult>({
    url: "/api/v1/reports/list"
  });
}

export function fetchAlarmStats() {
  return request<AlarmStatsItem[]>({
    url: "/api/v1/reports/data/alarms"
  });
}

export function fetchTrafficStats() {
  return request<TrafficResult>({
    url: "/api/v1/reports/data/traffic"
  });
}

export function fetchCloseoutSummary(days = 14, policyEnv?: string) {
  const query = new URLSearchParams();
  query.set("days", String(days));
  if (policyEnv) query.set("policy_env", policyEnv);
  return request<CloseoutSummaryResult>({
    url: `/api/v1/reports/mobile-regression/closeout-governance-dashboard/summary?${query.toString()}`
  });
}

export function fetchCloseoutDrilldown(params: {
  limit?: number;
  offset?: number;
  policy_env?: string;
  reason_code?: string;
  closeout_reason_code?: string;
  received_day?: string;
  include_dashboard?: boolean;
}) {
  const query = new URLSearchParams();
  query.set("limit", String(params.limit ?? 20));
  query.set("offset", String(params.offset ?? 0));
  if (params.policy_env) query.set("policy_env", params.policy_env);
  if (params.reason_code) query.set("reason_code", params.reason_code);
  if (params.closeout_reason_code) query.set("closeout_reason_code", params.closeout_reason_code);
  if (params.received_day) query.set("received_day", params.received_day);
  if (params.include_dashboard) query.set("include_dashboard", "true");
  return request<CloseoutDrilldownResult>({
    url: `/api/v1/reports/mobile-regression/closeout-governance-dashboard/drilldown?${query.toString()}`
  });
}
