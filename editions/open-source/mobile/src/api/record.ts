import { request } from "@/utils/request";

export interface DeviceRecordQueryPayload {
  device_id: string;
  channel_id: string;
  start_time: string;
  end_time: string;
  timeout_seconds?: number;
}

export interface DeviceRecordQueryStartResult {
  query_id: string;
  sn: string;
  status: "pending" | "running" | "partial" | "done" | "timeout";
  timeout_seconds: number;
  reused?: boolean;
  received?: number;
  sum_num?: number;
  completion_rate?: number;
}

export interface DeviceRecordRawItem {
  [key: string]: unknown;
}

export interface DeviceRecordQueryStatusResult {
  query_id: string;
  sn: string;
  device_id: string;
  channel_id: string;
  start_time: string;
  end_time: string;
  status: "pending" | "running" | "partial" | "done" | "timeout";
  sum_num: number;
  received: number;
  completion_rate: number;
  age_seconds: number;
  timeout_seconds: number;
  offset: number;
  limit: number;
  total_items: number;
  items: DeviceRecordRawItem[];
}

export interface DeviceRecordDownloadPayload {
  device_id: string;
  channel_id: string;
  start_time: string;
  end_time: string;
  download_speed?: number;
}

export interface DeviceRecordDownloadStartResult {
  task_id: string;
  status: "pending" | "running" | "done" | "failed" | "cancelled";
  app: string;
  stream: string;
  total_seconds: number;
}

export interface DeviceRecordDownloadProgressResult {
  task_id: string;
  status: "pending" | "running" | "done" | "failed" | "cancelled";
  app: string;
  stream: string;
  total_seconds: number;
  recorded_seconds: number;
  percent: number;
  records: Array<{ record_id: string; download_url: string }>;
  last_error: string;
}

export interface CloudRecordItem {
  id: string;
  device_id?: string;
  device_name?: string;
  channel_id?: string;
  channel_name?: string;
  resource_id?: string;
  start_time?: string;
  end_time?: string;
  duration?: number;
  file_size?: number;
  file_path?: string;
  record_app?: string;
  media_node_id?: string;
  url_ok?: boolean;
  url_checked_at?: string;
  url_status_code?: number | null;
  url_error?: string;
}

export interface SearchCloudRecordsParams {
  start_time?: string;
  end_time?: string;
  channel_id?: string;
  channel_ids?: string;
  device_id?: string;
  skip?: number;
  limit?: number;
}

export interface SearchCloudRecordsResult {
  items: CloudRecordItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface RecordScheduleItem {
  id: string;
  resource_id: string;
  plan_type: "timed" | "motion" | "alarm" | "manual" | string;
  enabled: boolean;
  time_ranges: Array<{ start?: string; end?: string; days?: number[] }>;
  priority: number;
  created_at?: string;
  updated_at?: string;
}

export interface RecordScheduleRuntimeItem {
  id: string;
  schedule_id: string;
  resource_id: string;
  forced_mode?: string;
  forced_until?: string | null;
  desired_recording?: boolean;
  is_recording?: boolean;
  last_eval_at?: string | null;
  last_stream_seen_at?: string | null;
  last_action_at?: string | null;
  last_action?: string;
  last_action_ok?: boolean;
  last_error?: string;
  last_media_node_id?: string;
  updated_at?: string | null;
}

export interface CreateRecordSchedulePayload {
  resource_id: string;
  plan_type: "timed" | "motion" | "alarm" | "manual" | string;
  enabled: boolean;
  time_ranges: Array<{ start?: string; end?: string; days?: number[] }>;
  priority: number;
}

export interface UpdateRecordSchedulePayload {
  plan_type?: "timed" | "motion" | "alarm" | "manual" | string;
  enabled?: boolean;
  time_ranges?: Array<{ start?: string; end?: string; days?: number[] }>;
  priority?: number;
}

export function startDeviceRecordQuery(payload: DeviceRecordQueryPayload) {
  return request<DeviceRecordQueryStartResult>({
    url: "/api/v1/device-record/device/queries",
    method: "POST",
    data: payload
  });
}

export function fetchDeviceRecordQueryStatus(queryId: string, offset = 0, limit = 2000) {
  const query = new URLSearchParams();
  query.set("offset", String(offset));
  query.set("limit", String(limit));
  return request<DeviceRecordQueryStatusResult>({
    url: `/api/v1/device-record/device/queries/${encodeURIComponent(queryId)}?${query.toString()}`
  });
}

export function startDeviceRecordDownload(payload: DeviceRecordDownloadPayload) {
  return request<DeviceRecordDownloadStartResult>({
    url: "/api/v1/device-record/download/start",
    method: "POST",
    data: payload
  });
}

export function fetchDeviceRecordDownloadProgress(taskId: string) {
  return request<DeviceRecordDownloadProgressResult>({
    url: `/api/v1/device-record/download/progress/${encodeURIComponent(taskId)}`
  });
}

export function stopDeviceRecordDownload(taskId: string) {
  return request<{ ok: boolean; task_id: string; status: string }>({
    url: `/api/v1/device-record/download/stop/${encodeURIComponent(taskId)}`,
    method: "POST"
  });
}

export function searchCloudRecords(params: SearchCloudRecordsParams = {}) {
  const query = new URLSearchParams();
  if (params.start_time) query.set("start_time", params.start_time);
  if (params.end_time) query.set("end_time", params.end_time);
  if (params.channel_id) query.set("channel_id", params.channel_id);
  if (params.channel_ids) query.set("channel_ids", params.channel_ids);
  if (params.device_id) query.set("device_id", params.device_id);
  query.set("skip", String(params.skip ?? 0));
  query.set("limit", String(params.limit ?? 100));
  return request<SearchCloudRecordsResult>({
    url: `/api/v1/record/search?${query.toString()}`
  });
}

export function getRecordDownloadSignedUrl(recordId: string, inline = false, ttlSeconds = 300) {
  const query = new URLSearchParams();
  query.set("inline", inline ? "true" : "false");
  query.set("ttl_seconds", String(ttlSeconds));
  return request<{ url?: string; signed_url?: string; expires_at?: number; record_id?: string }>({
    url: `/api/v1/record/download/sign/${encodeURIComponent(recordId)}?${query.toString()}`
  });
}

export function verifyCloudRecord(recordId: string) {
  return request<{ ok: boolean; status_code?: number; error?: string; checked_at?: string }>({
    url: `/api/v1/record/verify/${encodeURIComponent(recordId)}`,
    method: "POST"
  });
}

export function verifyCloudRecordBatch(ids: string[]) {
  return request<{ total: number; updated: number; ok: number; failed: number }>({
    url: "/api/v1/record/verify-batch",
    method: "POST",
    data: { ids }
  });
}

export function repairCloudRecordUrl(recordId: string) {
  return request<{ ok: boolean; old?: string; new?: string }>({
    url: `/api/v1/record/repair-url/${encodeURIComponent(recordId)}`,
    method: "POST"
  });
}

export function repairCloudRecordUrlBatch(ids: string[]) {
  return request<{ repaired: number }>({
    url: "/api/v1/record/repair-url-batch",
    method: "POST",
    data: { ids }
  });
}

export function deleteCloudRecord(recordId: string) {
  return request<{ ok: boolean }>({
    url: `/api/v1/record/${encodeURIComponent(recordId)}`,
    method: "DELETE"
  });
}

export function deleteCloudRecordBatch(ids: string[]) {
  return request<{ deleted: number }>({
    url: "/api/v1/record/delete-batch",
    method: "POST",
    data: { ids }
  });
}

export function listRecordSchedules(planType = "") {
  const query = new URLSearchParams();
  if (planType) query.set("plan_type", planType);
  return request<RecordScheduleItem[]>({
    url: `/api/v1/record-schedule${query.toString() ? `?${query.toString()}` : ""}`
  });
}

export function createRecordSchedule(payload: CreateRecordSchedulePayload) {
  return request<{ id: string; resource_id: string; plan_type: string; enabled: boolean }>({
    url: "/api/v1/record-schedule",
    method: "POST",
    data: payload
  });
}

export function updateRecordSchedule(scheduleId: string, payload: UpdateRecordSchedulePayload) {
  return request<{ status: string }>({
    url: `/api/v1/record-schedule/${encodeURIComponent(scheduleId)}`,
    method: "PUT",
    data: payload
  });
}

export function deleteRecordSchedule(scheduleId: string) {
  return request<{ status: string }>({
    url: `/api/v1/record-schedule/${encodeURIComponent(scheduleId)}`,
    method: "DELETE"
  });
}

export function listRecordScheduleRuntimes(resourceId = "") {
  const query = new URLSearchParams();
  if (resourceId) query.set("resource_id", resourceId);
  return request<RecordScheduleRuntimeItem[]>({
    url: `/api/v1/record-schedule/runtimes${query.toString() ? `?${query.toString()}` : ""}`
  });
}

export function forceStartRecordSchedule(scheduleId: string, minutes = 60) {
  return request<{ ok: boolean; forced_until?: string }>({
    url: `/api/v1/record-schedule/${encodeURIComponent(scheduleId)}/actions/force-start`,
    method: "POST",
    data: { minutes }
  });
}

export function forceStopRecordSchedule(scheduleId: string, minutes = 10) {
  return request<{ ok: boolean; forced_until?: string }>({
    url: `/api/v1/record-schedule/${encodeURIComponent(scheduleId)}/actions/force-stop`,
    method: "POST",
    data: { minutes }
  });
}
