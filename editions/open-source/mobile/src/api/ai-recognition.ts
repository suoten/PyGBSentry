import { request } from "@/utils/request";

export interface RecognitionRuntimeConfig {
  enabled?: boolean;
  ai_callback_url?: string;
  sync_urls?: string | string[];
  send_snapshot_url?: boolean;
  timeout_seconds?: number;
  [key: string]: unknown;
}

export interface RecognitionEventItem {
  id: string;
  source_plugin?: string;
  event_type?: "face" | "behavior" | "plate" | string;
  device_id?: string;
  channel_id?: string;
  event_time?: string;
  payload?: string;
  created_at?: string;
}

export interface FaceDbMetaResult {
  exists?: boolean;
  path?: string;
  count?: number;
}

export interface FaceDbItem {
  person_id?: string;
  name?: string;
  embedding_dim?: number;
}

export function fetchRecognitionRuntimeConfig(pluginId: string) {
  return request<{
    plugin_id: string;
    config: RecognitionRuntimeConfig;
    schema?: { fields?: Array<{ key: string; label?: string; type?: string }> };
  }>({
    url: `/api/v1/plugins/runtime/${encodeURIComponent(pluginId)}/config`
  });
}

export function saveRecognitionRuntimeConfig(pluginId: string, config: RecognitionRuntimeConfig) {
  return request<{ ok: boolean; plugin_id: string }>({
    url: `/api/v1/plugins/runtime/${encodeURIComponent(pluginId)}/config`,
    method: "PUT",
    data: { config }
  });
}

export function fetchRecognitionEvents(eventType: "face" | "behavior" | "plate", limit = 50) {
  const query = new URLSearchParams();
  query.set("event_type", eventType);
  query.set("skip", "0");
  query.set("limit", String(Math.max(1, Math.min(200, limit))));
  return request<{ items: RecognitionEventItem[]; total: number; skip: number; limit: number }>({
    url: `/api/v1/structured/search?${query.toString()}`
  });
}

export function fetchFaceDbMeta() {
  return request<FaceDbMetaResult>({
    url: "/api/v1/plugins/runtime/face_recognition_suite/face-db/meta"
  });
}

export function fetchFaceDbList() {
  return request<{ exists?: boolean; items?: FaceDbItem[] }>({
    url: "/api/v1/plugins/runtime/face_recognition_suite/face-db/list"
  });
}

export function deleteFaceDbPerson(personId: string) {
  return request<{ ok: boolean; removed: number }>({
    url: "/api/v1/plugins/runtime/face_recognition_suite/face-db/delete",
    method: "POST",
    data: { person_id: personId }
  });
}

export function clearFaceDb() {
  return request<{ ok: boolean; before: number; after: number }>({
    url: "/api/v1/plugins/runtime/face_recognition_suite/face-db/clear",
    method: "POST"
  });
}
