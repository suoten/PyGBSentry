export type NativePlayerProtocol = "webrtc" | "flv" | "hls" | "mp4" | "raw";

export interface NativePlayerOpenPayload {
  url: string;
  protocol: NativePlayerProtocol;
  title?: string;
  autoplay?: boolean;
  muted?: boolean;
}

export interface NativePlayerBridge {
  isSupported: () => boolean;
  open: (payload: NativePlayerOpenPayload) => Promise<void> | void;
}

export const BRIDGE_KEY = "__PG_BSENTRY_NATIVE_PLAYER_BRIDGE__";

export interface NativePlayerBridgeStatus {
  available: boolean;
  supported: boolean;
  source: "native" | "mock" | "none";
  platform: string;
  message: string;
}

function getBridgeFromGlobal(): NativePlayerBridge | null {
  const g = globalThis as Record<string, unknown>;
  const bridge = g[BRIDGE_KEY] as Partial<NativePlayerBridge> | undefined;
  if (!bridge) return null;
  if (typeof bridge.isSupported !== "function" || typeof bridge.open !== "function") return null;
  return bridge as NativePlayerBridge;
}

function currentPlatform() {
  try {
    const info = uni.getSystemInfoSync();
    return String(info.platform || "unknown").toLowerCase();
  } catch {
    return "unknown";
  }
}

function bridgeSource(): "native" | "mock" | "none" {
  const g = globalThis as Record<string, unknown>;
  const raw = g[BRIDGE_KEY] as Record<string, unknown> | undefined;
  if (!raw) return "none";
  const source = String(raw.__source || "").toLowerCase();
  if (source === "mock") return "mock";
  return "native";
}

export function registerNativePlayerBridge(
  bridge: NativePlayerBridge & { __source?: "native" | "mock" },
  options?: { force?: boolean }
) {
  const g = globalThis as Record<string, unknown>;
  if (!options?.force && g[BRIDGE_KEY]) return false;
  g[BRIDGE_KEY] = bridge as unknown;
  return true;
}

export function isNativePlayerBridgeAvailable() {
  const bridge = getBridgeFromGlobal();
  if (!bridge) return false;
  try {
    return !!bridge.isSupported();
  } catch {
    return false;
  }
}

export function getNativePlayerBridgeStatus(): NativePlayerBridgeStatus {
  const platform = currentPlatform();
  const bridge = getBridgeFromGlobal();
  if (!bridge) {
    return {
      available: false,
      supported: false,
      source: "none",
      platform,
      message: "未检测到桥接对象，请注入 __PG_BSENTRY_NATIVE_PLAYER_BRIDGE__"
    };
  }
  try {
    const supported = !!bridge.isSupported();
    return {
      available: true,
      supported,
      source: bridgeSource(),
      platform,
      message: supported ? "桥接可用" : "桥接已注入但当前平台不支持"
    };
  } catch (err: any) {
    return {
      available: true,
      supported: false,
      source: bridgeSource(),
      platform,
      message: err?.message || "桥接检测失败"
    };
  }
}

export async function openNativePlayer(payload: NativePlayerOpenPayload) {
  const bridge = getBridgeFromGlobal();
  if (!bridge) {
    throw new Error("native_player_bridge_missing");
  }
  if (!bridge.isSupported()) {
    throw new Error("native_player_not_supported");
  }
  await bridge.open(payload);
}
