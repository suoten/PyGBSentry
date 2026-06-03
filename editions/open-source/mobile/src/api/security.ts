import { request } from "@/utils/request";

export interface UserApiKeyItem {
  id: string;
  name: string;
  tenant_id?: string;
  user_id?: string;
  key_prefix?: string;
  scopes?: string[];
  expires_at?: string | null;
  is_active?: boolean;
  revoked_at?: string | null;
  last_used_at?: string | null;
  created_at?: string | null;
}

export interface CreateUserApiKeyPayload {
  name: string;
  scopes?: string[];
}

export interface CreateUserApiKeyResult {
  id: string;
  name: string;
  key_prefix?: string;
  scopes?: string[];
  api_key?: string;
  header_name?: string;
  created_at?: string;
}

export interface SecurityUserProfile {
  id: string;
  username: string;
  email?: string | null;
  full_name?: string | null;
  is_active: boolean;
  is_superuser: boolean;
  tenant_id: string;
  role: string;
  totp_enabled?: boolean;
}

export interface ChangePasswordPayload {
  current_password: string;
  new_password: string;
}

export interface TotpSetupResult {
  secret: string;
  otpauth_uri: string;
}

export interface AuditLogItem {
  audit_id: string;
  created_at?: string;
  module?: string;
  action?: string;
  source?: string;
  operator?: string;
  result?: string;
  summary?: string;
  status_code?: number | null;
  plugin_id?: string;
  tenant_id?: string;
}

export interface AuditLogListResult {
  items: AuditLogItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface AuditStatsItem {
  name: string;
  count: number;
}

export interface AuditStatsCodeItem {
  code: string;
  count: number;
}

export interface AuditStatsResult {
  total: number;
  failed: number;
  top_actions: AuditStatsItem[];
  top_status_codes: AuditStatsCodeItem[];
  status_buckets?: Record<string, number>;
}

export interface AuditQueryParams {
  module?: string;
  action?: string;
  action_prefix?: string;
  operator?: string;
  result?: string;
  plugin_id?: string;
  source?: string;
  tenant_id?: string;
  status_code?: number;
  status_family?: number;
  start_at?: string;
  end_at?: string;
  page?: number;
  page_size?: number;
}

function buildAuditQuery(params: AuditQueryParams = {}) {
  const query = new URLSearchParams();
  if (params.module) query.set("module", params.module);
  if (params.action) query.set("action", params.action);
  if (params.action_prefix) query.set("action_prefix", params.action_prefix);
  if (params.operator) query.set("operator", params.operator);
  if (params.result) query.set("result", params.result);
  if (params.plugin_id) query.set("plugin_id", params.plugin_id);
  if (params.source) query.set("source", params.source);
  if (params.tenant_id) query.set("tenant_id", params.tenant_id);
  if (typeof params.status_code === "number") query.set("status_code", String(params.status_code));
  if (typeof params.status_family === "number") query.set("status_family", String(params.status_family));
  if (params.start_at) query.set("start_at", params.start_at);
  if (params.end_at) query.set("end_at", params.end_at);
  if (typeof params.page === "number") query.set("page", String(params.page));
  if (typeof params.page_size === "number") query.set("page_size", String(params.page_size));
  return query.toString();
}

export function listMyApiKeys() {
  return request<UserApiKeyItem[]>({
    url: "/api/v1/user-api-keys/me"
  });
}

export function createUserApiKey(payload: CreateUserApiKeyPayload) {
  const { scopes, ...rest } = payload;
  return request<CreateUserApiKeyResult>({
    url: "/api/v1/user-api-keys",
    method: "POST",
    data: { ...rest, allowed_scopes: scopes }
  });  // FIXED: scopes→allowed_scopes匹配后端ApiKeyCreateRequest字段名
}

export function revokeUserApiKey(keyId: string) {
  return request<{ ok: boolean }>({
    url: `/api/v1/user-api-keys/${encodeURIComponent(keyId)}/revoke`,
    method: "POST"
  });
}

export function listAuditLogs(params: AuditQueryParams = {}) {
  const query = buildAuditQuery(params);
  return request<AuditLogListResult>({
    url: `/api/v1/audit-center/logs${query ? `?${query}` : ""}`
  });
}

export function fetchAuditStats(params: AuditQueryParams = {}) {
  const query = buildAuditQuery(params);
  return request<AuditStatsResult>({
    url: `/api/v1/audit-center/stats${query ? `?${query}` : ""}`
  });
}

export function fetchMySecurityProfile() {
  return request<SecurityUserProfile>({
    url: "/api/v1/users/me"
  });
}

export function changeMyPassword(payload: ChangePasswordPayload) {
  return request<{ ok: boolean }>({
    url: "/api/v1/users/me/change-password",
    method: "POST",
    data: payload
  });
}

export function setupMyTotp() {
  return request<TotpSetupResult>({
    url: "/api/v1/users/me/2fa/setup",
    method: "POST"
  });
}

export function enableMyTotp(code: string) {
  return request<{ ok: boolean; totp_enabled: boolean }>({
    url: "/api/v1/users/me/2fa/enable",
    method: "POST",
    data: { code }
  });
}

export function disableMyTotp(code: string) {
  return request<{ ok: boolean; totp_enabled: boolean }>({
    url: "/api/v1/users/me/2fa/disable",
    method: "POST",
    data: { code }
  });
}
