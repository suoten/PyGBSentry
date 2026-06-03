import { request } from "@/utils/request";

export interface DeviceItem {
  id: string;
  gb_id: string;
  name: string;
  status: number;
  organization_id?: string | null;
}

export interface DeviceChannelItem {
  id: string;
  gb_id: string;
  name?: string;
  status?: number;
}

export interface ChannelFlatItem {
  id: string;
  gb_id: string;
  name?: string;
  status?: number;
  online?: boolean;
  device_id?: string;
  device_name?: string;
  parent_gb_id?: string;
  region_parent_gb_id?: string;
  civil_code?: string;
  resource_type?: number | null;
  has_audio?: boolean;
  default_stream_type?: string;
  node_type?: string;
  // FIXED: 移除重复的 region_parent_gb_id 定义（L27已定义，L33重复覆盖）
  asset_id?: string;
  business_group_id?: string | null;
  manufacturer?: string;
  model?: string;
  owner?: string;
  ptz_type?: number | null;
  longitude?: number | null;
  latitude?: number | null;
}

export interface DeviceTreeNode {
  id: string;
  label: string;
  nodeType?: string;
  children?: DeviceTreeNode[];
}

export function fetchDevices(keyword = "") {
  const q = keyword ? `&keyword=${encodeURIComponent(keyword)}` : "";
  return request<{ items: DeviceItem[] }>({
    url: `/api/v1/devices?skip=0&limit=300${q}`
  });
}

export function fetchDeviceChannels(deviceId: string, limit = 50) {
  return request<DeviceChannelItem[]>({
    url: `/api/v1/devices/${encodeURIComponent(deviceId)}/channels?limit=${encodeURIComponent(String(limit))}`
  });
}

export interface FetchChannelsFlatParams {
  keyword?: string;
  status?: number;
  resource_type?: number;
  skip?: number;
  limit?: number;
  placement?: "business" | "region";
  parent_gb_id?: string;
  not_parent_gb_id?: string;
  added_status?: "added" | "unadded";
  civil_code_prefix?: string;
  camera_only?: boolean;
  node_type?: string;
  device_id?: string;
}

export function fetchChannelsFlat(params: FetchChannelsFlatParams = {}) {
  const query = new URLSearchParams();
  query.set("node_type", params.node_type || "channel");
  query.set("skip", String(params.skip ?? 0));
  query.set("limit", String(params.limit ?? 20));
  query.set("placement", params.placement || "business");
  if (params.keyword) query.set("keyword", params.keyword);
  if (typeof params.status === "number") query.set("status", String(params.status));
  if (typeof params.resource_type === "number") query.set("resource_type", String(params.resource_type));
  if (params.parent_gb_id) query.set("parent_gb_id", params.parent_gb_id);
  if (params.not_parent_gb_id) query.set("not_parent_gb_id", params.not_parent_gb_id);
  if (params.added_status) query.set("added_status", params.added_status);
  if (params.civil_code_prefix) query.set("civil_code_prefix", params.civil_code_prefix);
  if (params.camera_only) query.set("camera_only", "true");
  if (params.device_id) query.set("device_id", params.device_id);
  return request<{ items: ChannelFlatItem[]; total: number; skip: number; limit: number }>({
    url: `/api/v1/devices/channels/flat?${query.toString()}`
  });
}

export function fetchDeviceTree(placement: "business" | "region" = "business") {
  return request<DeviceTreeNode[]>({
    url: placement === "business" ? "/api/v1/devices/tree/business" : "/api/v1/devices/tree"
  });
}

export function batchPlaceChannels(payload: {
  resource_ids: string[];
  placement: "business" | "region";
  target_id?: string;
  civil_code?: string;
}) {
  return request<{ updated: number; requested: number }>({
    url: "/api/v1/devices/channels/batch-placement",
    method: "POST",
    data: payload
  });
}
