import { request } from "@/utils/request";

export interface StructuredEventItem {
  id: string;
  source_plugin?: string;
  event_type?: "face" | "plate" | "behavior" | string;
  device_id?: string;
  channel_id?: string;
  event_time?: string;
  payload?: unknown;
  created_at?: string;
}

export interface StructuredSearchQuery {
  event_type?: string;
  device_id?: string;
  channel_id?: string;
  start_time?: string;
  end_time?: string;
  skip?: number;
  limit?: number;
}

export interface StructuredSearchResult {
  items: StructuredEventItem[];
  total: number;
  skip: number;
  limit: number;
}

export function searchStructuredEvents(query: StructuredSearchQuery = {}) {
  const params = new URLSearchParams();
  params.set("skip", String(Math.max(0, Number(query.skip || 0))));
  params.set("limit", String(Math.min(200, Math.max(1, Number(query.limit || 20)))));
  if (query.event_type) params.set("event_type", query.event_type);
  if (query.device_id) params.set("device_id", query.device_id);
  if (query.channel_id) params.set("channel_id", query.channel_id);
  if (query.start_time) params.set("start_time", query.start_time);
  if (query.end_time) params.set("end_time", query.end_time);
  return request<StructuredSearchResult>({
    url: `/api/v1/structured/search?${params.toString()}`
  });
}
