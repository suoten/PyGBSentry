import { request } from "@/utils/request";

export interface OpsStatus {
  cpu: number;
  memory_percent: number;
  memory_used?: number;  // FIXED: 原OpsStatus缺少memory_used字段
  memory_total?: number;  // FIXED: 原OpsStatus缺少memory_total字段
  uptime?: string;  // FIXED: 原OpsStatus缺少uptime字段
  zlm_status: string;
  zlm_streams: number;
  zlm_node_id?: string;
  zlm_select_reason?: string;
  zlm_select_reason_label?: string;
  zlm_target?: string;
  zlm_error?: string | null;
  uptime_seconds?: number;
}

export interface DiagnoseItem {
  name: string;
  ok: boolean;
  text: string;
}

export interface DiagnoseReport {
  items: DiagnoseItem[];
  summary: "ok" | "warn" | "error";
  generated_at: string;
}

export interface StreamDiagItem {
  step: string;
  key: string;
  ok: boolean;
  title: string;
  detail?: string;
  suggestion?: string;
}

export function fetchOpsStatus() {
  return request<OpsStatus>({
    url: "/api/v1/ops/status"
  });
}

export function fetchDbCheck() {
  return request<{
    status: string;
    connected: boolean;
    database?: string;
    detail?: string;
    vendor_hint?: string;
  }>({
    url: "/api/v1/ops/db-check"
  });
}

export function fetchDbCompatReport() {
  return request<{
    database?: string;
    connected?: boolean;
    summary?: string;
    checks?: Array<{ name: string; ok: boolean; detail: string }>;
    vendor_hint?: string;
  }>({
    url: "/api/v1/ops/db-compat-report"
  });
}

export function fetchDiagnoseReport() {
  return request<DiagnoseReport>({
    url: "/api/v1/ops/diagnose-report"
  });
}

export function fetchActiveStreams(nodeId?: string) {
  const query = nodeId ? `?node_id=${encodeURIComponent(nodeId)}` : "";
  return request<{
    streams: Array<{
      stream: string;
      name: string;
      app?: string;
      schema?: string;
      aliveSecond?: number;
      readerCount?: number;
      totalReaderCount?: number;
      bytesSpeed?: number;
    }>;
    total: number;
  }>({
    url: `/api/v1/ops/active-streams${query}`
  });
}

export function runStreamDiagnose(params: { node_id?: string; channel_id?: string } = {}) {
  const query = new URLSearchParams();
  if (params.node_id) query.set("node_id", params.node_id);
  if (params.channel_id) query.set("channel_id", params.channel_id);
  return request<{
    items: StreamDiagItem[];
    channel_name?: string;
    channel_id?: string;
  }>({
    url: `/api/v1/ops/stream-diagnose${query.toString() ? `?${query.toString()}` : ""}`
  });
}

export function shutdownService() {
  return request<{ ok: boolean; pid?: number }>({
    url: "/api/v1/ops/shutdown",
    method: "POST"
  });
}
