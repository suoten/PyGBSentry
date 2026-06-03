import { request } from "@/utils/request";

export interface DevicesOverview {
  device_total: number;
  device_online: number;
  channel_total: number;
  channel_online: number;
  device_online_rate_pct: number;
  channel_online_rate_pct: number;
}

export interface DashboardAlarmItem {
  id: string;
  device_id?: string;
  description?: string;
  priority?: string;
  time?: string;
  status?: number;
  escalation_level?: number;
}

export interface OpsStatus {
  cpu?: number;
  memory_percent?: number;
  zlm_status?: string;
  zlm_streams?: number;
  zlm_bandwidth_mbps?: number;
}

export interface DiagnoseReport {
  summary?: string;
  generated_at?: string;
  items?: Array<{
    name?: string;
    text?: string;
    ok?: boolean;
  }>;
}

export interface NetworkSummary {
  stream_count?: number;
  stream_count_zlm?: number;
  zlm_bandwidth_mbps?: number;
}

export interface NetworkSeriesPoint {
  t: string;
  value: number;
}

export interface NetworkBandwidth {
  series: Array<{
    name: string;
    unit?: string;
    points: NetworkSeriesPoint[];
  }>;
}

export interface DemoStatus {
  enabled: boolean;
}

export interface SystemInfo {
  sip_id: string;
  sip_domain: string;
  sip_ip: string;
  sip_port: number;
  sip_password?: string;
  version?: string;
  project_name?: string;
}

export function fetchDevicesOverview() {
  return request<DevicesOverview>({
    url: "/api/v1/metrics/devices-overview"
  });
}

export function fetchDashboardAlarms(limit = 50) {
  const query = new URLSearchParams();
  query.set("skip", "0");
  query.set("limit", String(Math.max(1, Math.min(200, limit))));
  return request<{ items: DashboardAlarmItem[]; total: number }>({
    url: `/api/v1/alarms?${query.toString()}`
  });
}

export function fetchOpsStatus() {
  return request<OpsStatus>({
    url: "/api/v1/ops/status"
  });
}

export function fetchDiagnoseReport() {
  return request<DiagnoseReport>({
    url: "/api/v1/ops/diagnose-report"
  });
}

export function fetchNetworkSummary() {
  return request<NetworkSummary>({
    url: "/api/v1/network/summary"
  });
}

export function fetchNetworkBandwidth(range: "1h" | "24h" = "1h") {
  return request<NetworkBandwidth>({
    url: `/api/v1/network/bandwidth?range=${encodeURIComponent(range)}`
  });
}

export function fetchDemoStatus() {
  return request<DemoStatus>({
    url: "/api/v1/demo/status"
  });
}

export function fetchSystemInfo() {
  return request<SystemInfo>({
    url: "/api/v1/system-config/system-info"
  });
}
