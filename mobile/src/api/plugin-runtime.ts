import { request } from "@/utils/request";

export interface PluginInstalledItem {
  id: string;
  name: string;
  version?: string;
  type?: string;
  has_menu?: boolean;
}

export interface PluginPurchasedResult {
  plugin_ids: string[];
  plugins?: Array<{ id: string; name?: string; type?: string }>;
  plugin_id_to_name?: Record<string, string>;
}

export interface PluginMenuItem {
  plugin_id: string;
  title?: string;
  path?: string;
  frontend_url?: string | null;
}

export interface PluginRuntimeField {
  key: string;
  label?: string;
  type?: string;
  min?: number;
  max?: number;
}

export interface PluginRuntimeConfigResult {
  plugin_id: string;
  config: Record<string, unknown>;
  schema?: {
    fields?: PluginRuntimeField[];
  };
}

export function fetchInstalledPlugins() {
  return request<PluginInstalledItem[]>({
    url: "/api/v1/plugins/installed"
  });
}

export function fetchPurchasedPlugins() {
  return request<PluginPurchasedResult>({
    url: "/api/v1/plugins/purchased"
  });
}

export function fetchPluginMenus() {
  return request<PluginMenuItem[]>({
    url: "/api/v1/plugins/menus"
  });
}

export function fetchPluginRuntimeConfig(pluginId: string) {
  return request<PluginRuntimeConfigResult>({
    url: `/api/v1/plugins/runtime/${encodeURIComponent(pluginId)}/config`
  });
}

export function savePluginRuntimeConfig(pluginId: string, config: Record<string, unknown>) {
  return request<{ ok: boolean }>({
    url: `/api/v1/plugins/runtime/${encodeURIComponent(pluginId)}/config`,
    method: "PUT",
    data: {
      config
    }
  });
}

export function fetchPluginRuntimeRows(
  pluginId: string,
  kind: "events" | "logs" | "health" = "events",
  params: Record<string, string | number | boolean | undefined> = {}
) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v === undefined || v === null || v === "") return;
    query.set(k, String(v));
  });
  const qs = query.toString();
  return request<{
    rows?: unknown[];
    items?: unknown[];
    data?: unknown[];
    meta?: Record<string, unknown>;
  }>({
    url: `/api/v1/plugins/runtime/${encodeURIComponent(pluginId)}/${kind}${qs ? `?${qs}` : ""}`
  });
}

export function fetchPluginShopUrl() {
  return request<{ url: string }>({
    url: "/api/v1/plugins/marketplace-shop-url"
  });
}
