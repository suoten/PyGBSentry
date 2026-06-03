import type { MobilePluginEntry } from "@/types/api";
import { request } from "@/utils/request";

export function fetchMobileEntries() {
  return request<{ items: MobilePluginEntry[] }>({
    url: "/api/v1/plugins/mobile-entries"
  });
}

export interface InstalledPluginItem {
  id: string;
  name?: string;
  version?: string;
  type?: string;
  has_menu?: boolean;
}

export interface PurchasedPluginResult {
  plugin_ids: string[];
  plugins?: Array<{ id: string; name?: string; type?: string }>;
}

export interface PluginMenuItem {
  plugin_id: string;
  title?: string;
  path?: string;
  frontend_url?: string | null;
}

export interface MarketplacePluginItem {
  id: string;
  name?: string;
  title?: string;
  version?: string;
  type?: string;
  description?: string;
  detail?: string;
  doc_url?: string;
  price_monthly?: number;
  package_url?: string;
  status?: string;
  deprecated_message?: string;
  is_official?: boolean;
  min_oss_version?: string;
}

export interface MarketplaceInstallPayload {
  plugin_id: string;
  package_url?: string | null;
}

export interface MarketplaceInstallResult {
  plugin_id?: string;
  operation?: string;
  version?: string;
  previous_version?: string;
}

export interface PluginUninstallPreview {
  risk_level?: string;
  impact_summary?: string;
  table_count?: number;
  runtime_config_rows?: number;
  ack_phrase?: string;
}

export function fetchInstalledPlugins() {
  return request<InstalledPluginItem[]>({
    url: "/api/v1/plugins/installed"
  });
}

export function fetchPurchasedPlugins() {
  return request<PurchasedPluginResult>({
    url: "/api/v1/plugins/purchased"
  });
}

export function fetchPluginMenus() {
  return request<PluginMenuItem[]>({
    url: "/api/v1/plugins/menus"
  });
}

export function fetchPluginShopUrl() {
  return request<{ url: string }>({
    url: "/api/v1/plugins/marketplace-shop-url"
  });
}

export function fetchPluginMarketplace() {
  return request<MarketplacePluginItem[]>({
    url: "/api/v1/plugins/marketplace"
  });
}

export function fetchSystemInfo() {
  return request<{ version?: string }>({
    url: "/api/v1/system-config/info"  // FIXED: 使用正式路径替代deprecated /system/info
  });
}

export function installPluginFromMarketplace(payload: MarketplaceInstallPayload) {
  return request<MarketplaceInstallResult>({
    url: "/api/v1/plugins/marketplace/install",
    method: "POST",
    data: payload
  });
}

export function fetchPluginUninstallPreview(pluginId: string) {
  return request<PluginUninstallPreview>({
    url: `/api/v1/plugins/${encodeURIComponent(pluginId)}/uninstall-preview`
  });
}

export function uninstallPlugin(
  pluginId: string,
  payload: {
    confirm: boolean;
    confirm_phrase: string;
    preserve_data?: boolean;
  }
) {
  const preserveQuery =
    payload.preserve_data === undefined ? "" : `?preserve_data=${payload.preserve_data ? "true" : "false"}`;
  return request<{ status?: string; message?: string }>({
    url: `/api/v1/plugins/${encodeURIComponent(pluginId)}${preserveQuery}`,
    method: "DELETE",
    data: {
      confirm: payload.confirm,
      confirm_phrase: payload.confirm_phrase
    }
  });
}
