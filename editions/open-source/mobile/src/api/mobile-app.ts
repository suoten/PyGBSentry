import { request } from "@/utils/request";

export interface AppVersionCheckParams {
  plugin_id: "mobile_app_suite" | "mini_program_suite";
  platform: "android" | "ios" | "miniprogram";
  current_version?: string;
  release_channel?: string;
  device_id?: string;
}

export interface AppVersionCheckResult {
  has_update?: boolean;
  latest_version?: string;
  download_url?: string;
  force_update?: boolean;
  release_notes?: string;
  rollout_ratio?: number;
  release_channel?: string;
}

export interface AppStatsResult {
  days: number;
  total: number;
  crash_total: number;
  grouped?: Array<{
    plugin_id: string;
    platform: string;
    log_type: string;
    count: number;
  }>;
}

export interface AppRemoteConfigResult {
  plugin_id: string;
  app_version?: string;
  config: Record<string, unknown>;
  fetched_at?: string;
}

export function fetchAppVersionCheck(params: AppVersionCheckParams) {
  return request<AppVersionCheckResult>({
    url: "/api/v1/plugins/app-version-check",
    params: {
      plugin_id: params.plugin_id,
      platform: params.platform,
      current_version: params.current_version || "0.0.0",
      release_channel: params.release_channel || "stable",
      device_id: params.device_id || "mobile-client"
    }
  });
}

export function fetchAppStats(pluginId: "mobile_app_suite" | "mini_program_suite", days = 1) {
  return request<AppStatsResult>({
    url: "/api/v1/apps/stats",
    params: {
      plugin_id: pluginId,
      days
    }
  });
}

export function fetchAppRemoteConfig(pluginId: "mobile_app_suite" | "mini_program_suite", appVersion = "0.0.0") {
  return request<AppRemoteConfigResult>({
    url: "/api/v1/apps/remote-config",
    params: {
      plugin_id: pluginId,
      app_version: appVersion
    }
  });
}
