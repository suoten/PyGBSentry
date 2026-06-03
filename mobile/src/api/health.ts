import { request } from "@/utils/request";

export interface DeviceHealthItem {
  device_id: string;
  device_name: string;
  last_mode?: string | null;
  last_status_code?: number | null;
  success_total: number;
  fail_total: number;
  consecutive_failures: number;
  auto_switch_count: number;
  failure_rate: number;
  current_policy_mode: string;
  recommended_mode: string;
  recommend_reason: string;
  risk_level: "low" | "medium" | "high";
  updated_at?: string | null;
  signal_quality?: string | null;
  storage_status?: string | null;
}

export interface CapacityBaseline {
  tenant_scope: string;
  total_devices: number;
  high_risk_devices: number;
  unstable_devices: number;
  avg_failure_rate_pct: number;
  p95_failure_rate_pct: number;
  high_risk_ratio: number;
  unstable_ratio: number;
  health_level: string;
}

export interface TuningRecommendations {
  profile: string;
  reason: string;
  changed_count: number;
  recommendations: Array<{
    key: string;
    current: string | number;
    suggested: string | number;
  }>;
}

export interface ThresholdTemplate {
  profile: string;
  fleet_size: number;
  alert_template: Record<string, number>;
  performance_target: Record<string, number>;
  recommended_concurrency: number;
}

export interface DailyReportSummary {
  generated_at: string;
  total_devices: number;
  high_risk: number;
  medium_risk: number;
  low_risk: number;
  would_apply: number;
  top_risky: DeviceHealthItem[];
}

export interface ApplyRecommendationsPayload {
  device_ids?: string[];
  risk_level?: "low" | "medium" | "high";
  min_failure_rate?: number;
  only_diff?: boolean;
  dry_run?: boolean;
}

export function fetchHealthDevices(params: {
  risk_level?: "low" | "medium" | "high";
  min_failure_rate?: number;
  current_policy_mode?: string;
  only_diff?: boolean;
} = {}) {
  const query = new URLSearchParams();
  if (params.risk_level) query.set("risk_level", params.risk_level);
  if (typeof params.min_failure_rate === "number") query.set("min_failure_rate", String(params.min_failure_rate));
  if (params.current_policy_mode) query.set("current_policy_mode", params.current_policy_mode);
  if (typeof params.only_diff === "boolean") query.set("only_diff", String(params.only_diff));
  return request<DeviceHealthItem[]>({
    url: `/api/v1/health/devices${query.toString() ? `?${query.toString()}` : ""}`
  });
}

export function fetchCapacityBaseline() {
  return request<CapacityBaseline>({
    url: "/api/v1/health/capacity-baseline"
  });
}

export function fetchTuningRecommendations() {
  return request<TuningRecommendations>({
    url: "/api/v1/health/tuning-recommendations"
  });
}

export function fetchCapacityThresholdTemplate() {
  return request<ThresholdTemplate>({
    url: "/api/v1/health/capacity-threshold-template"
  });
}

export function fetchHealthDailyReport(topLimit = 10) {
  return request<DailyReportSummary>({
    url: `/api/v1/health/report/daily?top_limit=${encodeURIComponent(String(topLimit))}`
  });
}

export function applyHealthRecommendations(payload: ApplyRecommendationsPayload) {
  return request<{
    total: number;
    matched: number;
    would_apply: number;
    applied: number;
    results: Array<{
      device_id: string;
      previous_mode: string;
      recommended_mode: string;
      would_apply: boolean;
      applied: boolean;
      reason: string;
    }>;
  }>({
    url: "/api/v1/health/apply-recommendations",
    method: "POST",
    data: payload
  });
}
