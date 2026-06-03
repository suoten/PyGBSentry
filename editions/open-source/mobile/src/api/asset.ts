import { request } from "@/utils/request";

export interface AssetLedgerItem {
  id: string;
  gb_id: string;
  name?: string;
  manufacturer?: string;
  model?: string;
  status?: number;
  maintenance_count?: number;
}

export interface AssetMaintenanceItem {
  id: string;
  asset_id: string;
  maintenance_type: string;
  maintenance_date?: string;
  note?: string;
  operator?: string;
  created_at?: string;
}

export interface AssetMaintenancePayload {
  asset_id: string;
  maintenance_type: "routine" | "repair" | "upgrade" | "replace";
  maintenance_date: string;
  note?: string;
}

export function fetchAssetLedger(keyword = "", limit = 300) {
  const query = new URLSearchParams();
  query.set("skip", "0");
  query.set("limit", String(Math.max(1, Math.min(1000, limit))));
  if (keyword) query.set("keyword", keyword);
  return request<AssetLedgerItem[]>({
    url: `/api/v1/asset-management/ledger?${query.toString()}`
  });
}

export function fetchAssetMaintenances(assetId = "", limit = 300) {
  const query = new URLSearchParams();
  query.set("skip", "0");
  query.set("limit", String(Math.max(1, Math.min(1000, limit))));
  if (assetId) query.set("asset_id", assetId);
  return request<AssetMaintenanceItem[]>({
    url: `/api/v1/asset-management/maintenances?${query.toString()}`
  });
}

export function createAssetMaintenance(payload: AssetMaintenancePayload) {
  return request<{ id: string; asset_id: string }>({
    url: "/api/v1/asset-management/maintenances",
    method: "POST",
    data: payload
  });
}

export function deleteAssetMaintenance(maintenanceId: string) {
  return request<{ status: string }>({
    url: `/api/v1/asset-management/maintenances/${encodeURIComponent(maintenanceId)}`,
    method: "DELETE"
  });
}
