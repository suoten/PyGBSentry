import { request } from "@/utils/request";

export type NetworkRange = "1h" | "24h";

export interface NetworkSummary {
  device_total: number;
  device_online: number;
  stream_count: number;
  stream_count_zlm: number;
  zlm_bandwidth_mbps: number;
  description?: string;
}

export interface NetworkTopologyNode {
  id: string;
  type: string;
  label: string;
  status?: string;
  metrics?: {
    device_total?: number;
    device_online?: number;
  };
}

export interface NetworkTopologyEdge {
  source: string;
  target: string;
  type: string;
}

export interface NetworkTopology {
  nodes: NetworkTopologyNode[];
  edges: NetworkTopologyEdge[];
  generated_at?: string;
}

export interface NetworkSeriesPoint {
  t: string;
  value: number;
}

export interface NetworkBandwidthSeries {
  name: string;
  unit: string;
  points: NetworkSeriesPoint[];
}

export interface NetworkBandwidth {
  series: NetworkBandwidthSeries[];
  generated_at?: string;
}

export function fetchNetworkSummary() {
  return request<NetworkSummary>({
    url: "/api/v1/network/summary"
  });
}

export function fetchNetworkTopology() {
  return request<NetworkTopology>({
    url: "/api/v1/network/topology"
  });
}

export function fetchNetworkBandwidth(range: NetworkRange = "1h") {
  return request<NetworkBandwidth>({
    url: `/api/v1/network/bandwidth?range=${encodeURIComponent(range)}`
  });
}
