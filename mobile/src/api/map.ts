import { request } from "@/utils/request";

export interface DeviceLatestPosition {
  gb_id: string;
  name?: string;
  status?: number;
  longitude?: number | null;
  latitude?: number | null;
  time?: string | null;
  speed?: number | null;
}

export interface TrajectoryPoint {
  lng: number;
  lat: number;
  time?: string;
  speed?: number;
  direction?: number;
  altitude?: number;
}

export interface MapProviderItem {
  id: string;
  name: string;
  provider: string;
  api_key?: string;
  vector_tile_url?: string | null;
  center_lng: number;
  center_lat: number;
  zoom_level: number;
  min_zoom: number;
  max_zoom: number;
  is_default: boolean;
}

export interface SaveMapProviderPayload {
  name: string;
  provider: string;
  api_key?: string;
  vector_tile_url?: string;
  center_lng: number;
  center_lat: number;
  zoom_level: number;
  min_zoom: number;
  max_zoom: number;
}

export interface VisualCommandConfig {
  enabled: boolean;
  alarm_blink_seconds: number;
  trajectory_max_points: number;
  message?: string;
}

export interface MapConfigPayload {
  id?: string;
  name?: string;
  provider: string;
  api_key: string;
  vector_tile_url?: string | null;
  center_lng: number;
  center_lat: number;
  zoom_level: number;
  min_zoom: number;
  max_zoom: number;
  profile_id?: string;
}

export function fetchLatestPositions(limit = 200) {
  return request<DeviceLatestPosition[]>({
    url: `/api/v1/map/devices-latest-positions?limit=${encodeURIComponent(String(limit))}`
  });
}

export function fetchTrajectory(deviceId: string, limit = 200, startTime?: string, endTime?: string) {
  const query = new URLSearchParams();
  query.set("device_id", deviceId);
  query.set("limit", String(limit));
  if (startTime) query.set("start_time", startTime);
  if (endTime) query.set("end_time", endTime);
  return request<TrajectoryPoint[]>({
    url: `/api/v1/map/trajectory?${query.toString()}`
  });
}

export function fetchDeviceLatestPosition(deviceId: string) {
  return request<DeviceLatestPosition>({
    url: `/api/v1/map/device-latest-position?device_id=${encodeURIComponent(deviceId)}`
  });
}

export function subscribeMobilePosition(deviceId: string, interval = 60) {
  return request<{ ok: boolean }>({
    url: "/api/v1/map/mobile-position/subscribe",
    method: "POST",
    data: {
      device_id: deviceId,
      interval
    }
  });
}

export function fetchMapConfig() {
  return request<MapConfigPayload>({
    url: "/api/v1/map"
  });
}

export function saveMapConfig(payload: MapConfigPayload) {
  return request<MapConfigPayload>({
    url: "/api/v1/map",
    method: "POST",
    data: payload
  });
}

export function fetchMapProviders() {
  return request<{ items: MapProviderItem[] }>({
    url: "/api/v1/map/providers"
  });
}

export function createMapProvider(payload: SaveMapProviderPayload) {
  return request<MapProviderItem>({
    url: "/api/v1/map/providers",
    method: "POST",
    data: payload
  });
}

export function updateMapProvider(profileId: string, payload: Partial<SaveMapProviderPayload>) {
  return request<MapProviderItem>({
    url: `/api/v1/map/providers/${encodeURIComponent(profileId)}`,
    method: "PUT",
    data: payload
  });
}

export function activateMapProvider(profileId: string) {
  return request<MapProviderItem>({
    url: `/api/v1/map/providers/${encodeURIComponent(profileId)}/activate`,
    method: "POST"
  });
}

export function deleteMapProvider(profileId: string) {
  return request<{ status: string }>({
    url: `/api/v1/map/providers/${encodeURIComponent(profileId)}`,
    method: "DELETE"
  });
}

export function fetchVisualCommandConfig() {
  return request<VisualCommandConfig>({
    url: "/api/v1/map/command-config"
  });
}
