import { request } from "@/utils/request";

export interface PlatformItem {
  id: string;
  name: string;
  server_gb_id: string;
  server_ip: string;
  server_port: number;
  transport: string;
  client_gb_id: string;
  tenant_id?: string;
  is_online?: boolean;
  register_interval?: number;
  keepalive_interval?: number;
  catalog_batch_size?: number;
  catalog_push_delay_seconds?: number;
  enable?: boolean;
  runtime?: Record<string, unknown>;
}

export interface PlatformPayload {
  name: string;
  server_gb_id: string;
  server_ip: string;
  server_port: number;
  transport?: string;
  client_gb_id: string;
  password?: string;
  register_interval?: number;
  keepalive_interval?: number;
  catalog_batch_size?: number;
  catalog_push_delay_seconds?: number;
  enable?: boolean;
}

export interface PlatformCatalogResources {
  platform_id: string;
  resource_ids: string[];
  mappings?: Array<{
    resource_id: string;
    virtual_gb_id?: string | null;
    virtual_name?: string | null;
    virtual_parent_id?: string | null;
  }>;
}

export function fetchPlatforms() {
  return request<PlatformItem[]>({
    url: "/api/v1/platforms"
  });
}

export function createPlatform(payload: PlatformPayload) {
  return request<{ id: string; name?: string }>({
    url: "/api/v1/platforms",
    method: "POST",
    data: payload
  });
}

export function updatePlatform(platformId: string, payload: Partial<PlatformPayload>) {
  return request<{ id: string }>({
    url: `/api/v1/platforms/${encodeURIComponent(platformId)}`,
    method: "PUT",
    data: payload
  });
}

export function deletePlatform(platformId: string) {
  return request<{ ok?: boolean; status?: string }>({
    url: `/api/v1/platforms/${encodeURIComponent(platformId)}`,
    method: "DELETE"
  });
}

export function triggerPlatformRegister(platformId: string) {
  return request<{ ok: boolean }>({
    url: `/api/v1/platforms/${encodeURIComponent(platformId)}/actions/register`,
    method: "POST"
  });
}

export function triggerPlatformPushCatalog(platformId: string) {
  return request<{ ok: boolean }>({
    url: `/api/v1/platforms/${encodeURIComponent(platformId)}/actions/push-catalog`,
    method: "POST"
  });
}

export function fetchPlatformDiagnosis(platformId: string) {
  return request<Record<string, unknown>>({
    url: `/api/v1/platforms/${encodeURIComponent(platformId)}/diagnosis`
  });
}

export function fetchPlatformCatalogResources(platformId: string) {
  return request<PlatformCatalogResources>({
    url: `/api/v1/platforms/${encodeURIComponent(platformId)}/catalog-resources`
  });
}

export function updatePlatformCatalogResources(platformId: string, resourceIds: string[]) {
  return request<{ ok?: boolean }>({
    url: `/api/v1/platforms/${encodeURIComponent(platformId)}/catalog-resources`,
    method: "PUT",
    data: {
      resource_ids: resourceIds
    }
  });
}

export function fetchPlatformChannelsFlat(channelType: 0 | 1 | 2, limit = 500) {
  return request<{
    items: Array<{
      id: string;
      name?: string;
      gb_id?: string;
      channel_type?: number;
      protocol?: string;
      device_name?: string;
      device_id?: string;
    }>;
    total: number;
  }>({
    url: `/api/v1/platforms/channels/flat?channel_type=${channelType}&skip=0&limit=${limit}`
  });
}
