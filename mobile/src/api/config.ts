import { request } from "@/utils/request";

export interface BasicConfigPayload {
  streamPullTimeout?: number;
  alarmDefaultLevel?: string;
  deviceHeartbeatInterval?: number;
  recordAutoCleanDays?: number;
  logRetentionDays?: number;
}

export interface DatabaseConfigPayload {
  database_type: string;
  host?: string;
  port?: number;
  name?: string;
  username?: string;
  password?: string;
  sqlite_path?: string;
  sqlalchemy_database_uri?: string;
}

export interface CurrentDraftResult {
  draft_id: string;
  base_revision: number;
  status: string;
  modules: Record<string, any>;
  updated_at: string;
}

export interface ValidateIssue {
  field: string;
  message: string;
}

export interface ValidateDraftResult {
  valid: boolean;
  errors: ValidateIssue[];
  warnings: ValidateIssue[];
  hints: string[];
}

export function fetchBasicConfig() {
  return request<Required<BasicConfigPayload>>({
    url: "/api/v1/config-center/basic"
  });
}

export function saveBasicConfig(payload: BasicConfigPayload) {
  return request<Required<BasicConfigPayload>>({
    url: "/api/v1/config-center/basic",
    method: "PUT",
    data: payload
  });
}

export function fetchDatabaseConfig() {
  return request<DatabaseConfigPayload>({
    url: "/api/v1/system-config/database"
  });
}

export function testDatabaseConfig(payload: DatabaseConfigPayload) {
  return request<{
    ok: boolean;
    dialect?: string;
    database?: string;
    compatibility?: Record<string, any>;
    vendor_hint?: string;
  }>({
    url: "/api/v1/system-config/database/test",
    method: "POST",
    data: payload
  });
}

export function saveDatabaseConfig(payload: DatabaseConfigPayload) {
  return request<{ status: string; message?: string }>({
    url: "/api/v1/system-config/database",
    method: "PUT",
    data: payload
  });
}

export function fetchCurrentDraft() {
  return request<CurrentDraftResult>({
    url: "/api/v1/config-center/drafts/current"
  });
}

export function validateDraft(draftId: string) {
  return request<ValidateDraftResult>({
    url: `/api/v1/config-center/drafts/${encodeURIComponent(draftId)}/validate`,
    method: "POST"
  });
}
