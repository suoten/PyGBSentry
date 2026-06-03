import { request } from "@/utils/request";

export interface TvWallChannelNode {
  id: string;
  label: string;
  nodeType: "channel" | "source_stream";
  status?: number;
  deviceId?: string;
  sourceId?: string;
  protocol?: string;
}

export interface TvWallScreenState {
  screenIndex: number;
  name: string;
  nodeType: "channel" | "source_stream";
  deviceId?: string;
  channelId?: string;
  sourceId?: string;
  app?: string;
  stream?: string;
  url?: string;
  hls?: string;
  mode?: string;
  loading?: boolean;
  error?: string;
}

export async function fetchTvWallDeviceTree(placement: "business" | "region" = "business") {
  return request<any[]>({
    url: placement === "business" ? "/api/v1/devices/tree/business" : "/api/v1/devices/tree"
  });
}

export async function fetchTvWallSources() {
  return request<
    Array<{
      id: string;
      name?: string;
      protocol?: string;
      enabled?: boolean;
    }>
  >({
    url: "/api/v1/integrations/sources"
  });
}

export async function previewTvWallSource(sourceId: string) {
  return request<{
    app?: string;
    stream?: string;
    webrtc?: string;
    flv?: string;
    hls?: string;
    ws_flv?: string;
    wss_flv?: string;
    ws_hls?: string;
    wss_hls?: string;
  }>({
    url: `/api/v1/integrations/sources/${encodeURIComponent(sourceId)}/play`,
    method: "POST"
  });
}

export async function stopTvWallStream(app: string, stream: string, channelId = "") {
  return request<{ ok?: boolean }>({
    url: "/api/v1/stream/stop",
    method: "POST",
    data: {
      app,
      stream,
      channel_id: channelId || undefined
    }
  });
}
