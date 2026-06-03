export interface ApiResult<T> {
  data: T;
  statusCode: number;
}

export interface PagedResult<T> {
  items: T[];
  total?: number;
}

export interface UserProfile {
  id: string;
  username: string;
  full_name?: string;
  role?: string;
  tenant_id?: string;
  is_superuser?: boolean;
}

export interface MobilePluginEntry {
  plugin_id: string;
  name: string;
  platform: "mobile" | "miniprogram";
  entry_type: "h5" | "webview" | "plugin" | "native" | "none";
  entry_url?: string | null;
  entry_url_template?: string | null;
}
