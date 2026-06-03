import { request } from "@/utils/request";

export interface StreamSessionItem {
  app?: string;
  stream?: string;
  origin_url?: string;
  is_proxy?: boolean;
  reader_count?: number;
  alive_second?: number;
  bytes_speed?: number;
}

export interface SourcePlayResult {
  app?: string;
  stream?: string;
  webrtc?: string;
  flv?: string;
  hls?: string;
}

export interface PushChannelItem {
  id: string;
  name: string;
  protocol?: string;
  stream_name?: string;
  enabled?: boolean;
  extra?: Record<string, unknown>;
  push_key_enabled?: boolean;
  push_key_hint?: string;
  gb_enabled?: boolean;
  gb_id?: string;
  gb_name?: string;
}

export interface PushChannelPayload {
  name: string;
  stream_name?: string;
  enabled?: boolean;
  push_key_enabled?: boolean;
  gb_enabled?: boolean;
  gb_id?: string;
  gb_name?: string;
  gb_parent_gb_id?: string;
}

export interface AccessSourceItem {
  id: string;
  name: string;
  protocol: string;
  host: string;
  port: number;
  username?: string;
  path?: string;
  stream_name?: string;
  enabled?: boolean;
  gb_enabled?: boolean;
  gb_id?: string;
  gb_name?: string;
  extra?: Record<string, unknown>;
}

export interface AccessSourcePayload {
  id?: string;
  name: string;
  protocol: string;
  host: string;
  port: number;
  username?: string;
  password?: string;
  path?: string;
  stream_name?: string;
  enabled?: boolean;
  gb_enabled?: boolean;
  gb_id?: string;
  gb_name?: string;
  gb_parent_gb_id?: string;
  extra?: Record<string, unknown>;
}

export function fetchStreamSessions() {
  return request<StreamSessionItem[]>({
    url: "/api/v1/stream/list"
  });
}

export function stopStream(app: string, stream: string) {
  return request<{ ok?: boolean }>({
    url: "/api/v1/stream/stop",
    method: "POST",
    data: { app, stream }
  });
}

export function previewSource(sourceId: string) {
  return request<SourcePlayResult>({
    url: `/api/v1/integrations/sources/${encodeURIComponent(sourceId)}/play`,
    method: "POST"
  });
}

export function fetchPushChannels() {
  return request<PushChannelItem[]>({
    url: "/api/v1/push-channels"
  });
}

export function createPushChannel(payload: PushChannelPayload) {
  return request<{ id: string; stream_name?: string; push_key?: string; push_key_hint?: string }>({
    url: "/api/v1/push-channels",
    method: "POST",
    data: payload
  });
}

export function updatePushChannel(channelId: string, payload: PushChannelPayload) {
  return request<{ ok: boolean }>({
    url: `/api/v1/push-channels/${encodeURIComponent(channelId)}`,
    method: "PUT",
    data: payload
  });
}

export function deletePushChannel(channelId: string) {
  return request<{ ok: boolean }>({
    url: `/api/v1/push-channels/${encodeURIComponent(channelId)}`,
    method: "DELETE"
  });
}

export function rotatePushChannelKey(channelId: string) {
  return request<{ push_key?: string; push_key_hint?: string }>({
    url: `/api/v1/push-channels/${encodeURIComponent(channelId)}/rotate-push-key`,
    method: "POST"
  });
}

export function fetchPushUrl(sourceId: string) {
  return request<{ push_url?: string; push_key_hint?: string }>({
    url: `/api/v1/integrations/sources/${encodeURIComponent(sourceId)}/push-url`
  });
}

export function setSourceDesiredState(sourceId: string, state: "running" | "stopped", enforce = false) {
  return request<{ ok: boolean }>({
    url: `/api/v1/integrations/sources/${encodeURIComponent(sourceId)}/actions/desired-state`,
    method: "POST",
    data: { state, enforce }
  });
}

export function fetchAccessSources() {
  return request<AccessSourceItem[]>({
    url: "/api/v1/integrations/sources"
  });
}

export function saveProxySource(payload: AccessSourcePayload) {
  return request<{ id: string }>({
    url: "/api/v1/proxy/save",
    method: "POST",
    data: payload
  });
}

export function deleteProxySource(sourceId: string) {
  return request<{ ok: boolean }>({
    url: `/api/v1/integrations/sources/${encodeURIComponent(sourceId)}`,
    method: "DELETE"
  });
}

export function setSourceEnabled(sourceId: string, enabled: boolean) {
  return request<{ ok: boolean }>({
    url: `/api/v1/integrations/sources/${encodeURIComponent(sourceId)}/actions/set-enabled`,
    method: "POST",
    data: { enabled }
  });
}

export function testSource(sourceId: string) {
  return request<{ ok?: boolean; message?: string }>({
    url: `/api/v1/integrations/sources/${encodeURIComponent(sourceId)}/test`,
    method: "POST"
  });
}
