import { registerNativePlayerBridge, type NativePlayerBridge, type NativePlayerOpenPayload } from "@/utils/nativePlayerBridge";

function isLikelyNativePlatform() {
  try {
    const info = uni.getSystemInfoSync();
    const p = String(info.platform || "").toLowerCase();
    return p.includes("android") || p.includes("ios");
  } catch {
    return false;
  }
}

const mockBridge: NativePlayerBridge & { __source: "mock" } = {
  __source: "mock",
  isSupported: () => true,
  open: (payload: NativePlayerOpenPayload) => {
    const title = payload.title || `原生播放器(${String(payload.protocol || "").toUpperCase()})`;
    const url = String(payload.url || "");
    if (!url) {
      uni.showToast({ title: "mock_bridge: empty url", icon: "none" });
      return;
    }
    uni.showModal({
      title,
      content: `Mock Bridge 已接收播放请求\n协议: ${payload.protocol}\n地址: ${url.slice(0, 140)}${url.length > 140 ? "..." : ""}`,
      showCancel: false
    });
  }
};

export function installMockNativePlayerBridge() {
  // Native runtime should prefer real bridge from Android/iOS plugin.
  if (isLikelyNativePlatform()) return false;
  return registerNativePlayerBridge(mockBridge, { force: false });
}
