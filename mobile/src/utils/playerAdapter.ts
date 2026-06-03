export type StreamProtocol = "webrtc" | "flv" | "hls" | "mp4" | "raw";

export type PlaybackStrategy = "native-video" | "native-adapter" | "external-debug";

export interface PlaybackPlan {
  protocol: StreamProtocol;
  strategy: PlaybackStrategy;
  canInlineVideo: boolean;
  reason: string;
  suggestedFallback: "hls" | "flv" | "none";
}

export function detectStreamProtocol(url: string, mode?: string): StreamProtocol {
  const lowMode = String(mode || "").toLowerCase();
  const lowUrl = String(url || "").toLowerCase();
  if (lowMode.includes("webrtc") || lowUrl.includes("webrtc")) return "webrtc";
  if (lowMode.includes("hls") || lowUrl.includes(".m3u8")) return "hls";
  if (lowMode.includes("flv") || lowUrl.includes(".flv")) return "flv";
  if (lowUrl.includes(".mp4")) return "mp4";
  return "raw";
}

function isHttpUrl(url: string) {
  const low = String(url || "").toLowerCase();
  return low.startsWith("http://") || low.startsWith("https://");
}

function runtimePlatform() {
  try {
    const info = uni.getSystemInfoSync();
    return String(info.platform || "").toLowerCase();
  } catch {
    return "";
  }
}

export function buildPlaybackPlan(url: string, mode?: string): PlaybackPlan {
  const protocol = detectStreamProtocol(url, mode);
  if (!isHttpUrl(url)) {
    return {
      protocol,
      strategy: "external-debug",
      canInlineVideo: false,
      reason: "播放地址不是标准 HTTP/HTTPS 链路",
      suggestedFallback: "none"
    };
  }

  const platform = runtimePlatform();
  const isNativeLike = platform.includes("android") || platform.includes("ios");

  if (protocol === "hls" || protocol === "mp4") {
    return {
      protocol,
      strategy: "native-video",
      canInlineVideo: true,
      reason: "当前协议可由内置 video 组件稳定承载",
      suggestedFallback: "none"
    };
  }

  if (protocol === "flv") {
    if (isNativeLike) {
      return {
        protocol,
        strategy: "native-adapter",
        canInlineVideo: false,
        reason: "移动端建议接入原生 FLV 解码适配器以提升稳定性",
        suggestedFallback: "hls"
      };
    }
    return {
      protocol,
      strategy: "external-debug",
      canInlineVideo: false,
      reason: "当前运行环境对 FLV 内嵌能力有限，建议切换 HLS 或接入适配层",
      suggestedFallback: "hls"
    };
  }

  if (protocol === "webrtc") {
    return {
      protocol,
      strategy: "native-adapter",
      canInlineVideo: false,
      reason: "WebRTC 建议接入原生播放器适配层（低延时）",
      suggestedFallback: "flv"
    };
  }

  return {
    protocol,
    strategy: "external-debug",
    canInlineVideo: false,
    reason: "无法识别协议，建议回退到 HLS/FLV 并做外部调试",
    suggestedFallback: "hls"
  };
}
