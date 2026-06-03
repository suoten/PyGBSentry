import { request } from "@/utils/request";

export interface StreamPlayData {
  session_id?: string;
  app?: string;
  stream?: string;
  codec?: string;
  webrtc?: string;
  rtc?: string;
  rtcs?: string;
  webrtc_hint?: string;
  flv?: string;
  ws_flv?: string;
  wss_flv?: string;
  hls?: string;
  ws_hls?: string;
  wss_hls?: string;
  preferred_url?: string;
}

interface AsyncPlayAccepted {
  code: number;
  msg: string;
  data?: {
    session_id?: string;
    status?: string;
  };
}

interface AsyncPlayStatus {
  code?: number;
  msg?: string;
  data?: StreamPlayData & {
    status?: "waiting" | "ready" | "failed";
    session_id?: string;
  };
}

function normalizePlayData(raw: any): StreamPlayData {
  if (!raw) return {};
  if (raw?.data && typeof raw.data === "object") return raw.data as StreamPlayData;
  return raw as StreamPlayData;
}

export async function playStream(deviceId: string, channelId: string): Promise<StreamPlayData> {
  const first = await request<StreamPlayData | AsyncPlayAccepted>({
    url: `/api/v1/stream/play/${encodeURIComponent(deviceId)}/${encodeURIComponent(channelId)}?streamType=auto&isAsync=true`,  // FIXED-P1: C-10 使用FastAPI alias名称而非Python参数名
    method: "POST"
  });

  if ((first as AsyncPlayAccepted)?.code === 202 && (first as AsyncPlayAccepted)?.data?.session_id) {
    const sessionId = (first as AsyncPlayAccepted).data!.session_id!;
    for (let i = 0; i < 40; i += 1) {
      await new Promise((resolve) => setTimeout(resolve, 600));
      const poll = await request<AsyncPlayStatus>({
        url: `/api/v1/stream/play_status/${encodeURIComponent(sessionId)}`
      });
      const status = String(poll?.status || "").toLowerCase();  // FIXED-P1: C-11 normalizePlayData已解包data层，直接从poll.status取值
      if (status === "waiting") continue;
      return {
        session_id: sessionId,
        ...(normalizePlayData(poll) || {})
      };
    }
    throw new Error("Stream address timeout, please retry later"); // FIXED: 硬编码中文→英文
  }

  return normalizePlayData(first);
}

export function pickPreferredPlayUrl(data: StreamPlayData): { url: string; mode: "webrtc" | "flv" | "hls" | "raw" } {
  const trim = (v?: string) => String(v || "").trim();
  const preferred = trim(data.preferred_url);
  const webrtc = trim(data.webrtc || data.rtc || data.rtcs);
  const flv = trim(data.wss_flv || data.ws_flv || data.flv);
  const hls = trim(data.wss_hls || data.ws_hls || data.hls);

  if (preferred) {
    const low = preferred.toLowerCase();
    if (low.includes("webrtc")) return { url: preferred, mode: "webrtc" };
    if (low.includes(".flv")) return { url: preferred, mode: "flv" };
    if (low.includes(".m3u8")) return { url: preferred, mode: "hls" };
  }
  if (webrtc) return { url: webrtc, mode: "webrtc" };
  if (flv) return { url: flv, mode: "flv" };
  if (hls) return { url: hls, mode: "hls" };
  return { url: "", mode: "raw" };
}

export function buildFallbackChain(data: StreamPlayData): Array<{ mode: "webrtc" | "flv" | "hls"; url: string }> {
  const trim = (v?: string) => String(v || "").trim();
  const webrtc = trim(data.webrtc || data.rtc || data.rtcs);
  const flv = trim(data.wss_flv || data.ws_flv || data.flv);
  const hls = trim(data.wss_hls || data.ws_hls || data.hls);
  const out: Array<{ mode: "webrtc" | "flv" | "hls"; url: string }> = [];
  if (webrtc) out.push({ mode: "webrtc", url: webrtc });
  if (flv) out.push({ mode: "flv", url: flv });
  if (hls) out.push({ mode: "hls", url: hls });
  return out;
}

export interface StreamHealthData {
  health_score?: number;
  health_level?: string;
  status?: string;
  fps?: number;
  bitrate_kbps?: number;
  packet_loss_rate?: number;
  buffer_ms?: number;
}

export async function getStreamHealth(sessionId: string): Promise<StreamHealthData | null> {
  if (!sessionId) return null;
  try {
    const res = await request<{ data?: StreamHealthData } | StreamHealthData>({
      url: `/api/v1/stream-opt/health/${encodeURIComponent(sessionId)}`
    });
    return (res as any)?.data || (res as StreamHealthData);
  } catch {
    return null;
  }
}

export interface StreamQualityReportPayload {
  session_id: string;
  fps?: number;
  bitrate_kbps?: number;
  video_width?: number;
  video_height?: number;
  codec?: string;
  latency_ms?: number;
  jitter_ms?: number;
  packet_loss_rate?: number;
  buffer_ms?: number;
  dropped_frames?: number;
  error_count?: number;
}

export async function reportStreamQuality(payload: StreamQualityReportPayload) {
  return request<{ received?: boolean; health?: StreamHealthData }>({
    url: "/api/v1/stream-opt/quality-report",
    method: "POST",
    data: payload
  });
}
