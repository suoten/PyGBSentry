import { request } from "@/utils/request";

export interface AppLogItem {
  id: string;
  tenant_id: string;
  plugin_id: string;
  app_version: string;
  platform: string;
  log_type: string;
  message?: string | null;
  extra?: string | null;
  created_at?: string | null;
}

export interface AppLogsQuery {
  plugin_id?: string;
  platform?: string;
  log_type?: string;
  start_time?: string;
  end_time?: string;
  skip?: number;
  limit?: number;
}

export interface AppLogsResult {
  items: AppLogItem[];
  total: number;
  skip: number;
  limit: number;
}

export function fetchAppLogs(query: AppLogsQuery = {}) {
  const params = new URLSearchParams();
  if (query.plugin_id) params.set("plugin_id", query.plugin_id);
  if (query.platform) params.set("platform", query.platform);
  if (query.log_type) params.set("log_type", query.log_type);
  if (query.start_time) params.set("start_time", query.start_time);
  if (query.end_time) params.set("end_time", query.end_time);
  params.set("skip", String(Math.max(0, Number(query.skip || 0))));
  params.set("limit", String(Math.min(200, Math.max(1, Number(query.limit || 20)))));
  return request<AppLogsResult>({
    url: `/api/v1/apps/logs?${params.toString()}`
  });
}
