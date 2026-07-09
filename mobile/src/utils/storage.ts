const TOKEN_KEY = "pgbsentry_mobile_token";
const REFRESH_TOKEN_KEY = "pgbsentry_mobile_refresh_token";  // FIXED: W-31补充 添加refresh_token存储
const PROFILE_KEY = "pgbsentry_mobile_profile";

// P0-10: H5 端使用 sessionStorage（关闭标签即失效），App/小程序端保持原生持久存储
// #ifdef H5
function _h5Set(key: string, value: string) {
  try { sessionStorage.setItem(key, value) } catch { /* privacy */ }
}
function _h5Get(key: string): string {
  try { return sessionStorage.getItem(key) || '' } catch { return '' }
}
function _h5Remove(key: string) {
  try { sessionStorage.removeItem(key) } catch { /* privacy */ }
}
// #endif

/** 解码 JWT payload 检查 exp（秒级时间戳），过期返回 true */
function _isTokenExpired(token: string): boolean {
  if (!token) return true
  try {
    const parts = token.split('.')
    if (parts.length < 2) return false  // 非 JWT 格式，不拦截
    const payloadB64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    const padded = payloadB64.padEnd(Math.ceil(payloadB64.length / 4) * 4, '=')
    const payload = JSON.parse(atob(padded))
    const exp = Number(payload?.exp)
    if (!Number.isFinite(exp) || exp <= 0) return false  // 无 exp 字段，视为不过期
    return Math.floor(Date.now() / 1000) >= exp
  } catch {
    return false  // 解析失败不拦截，由后端验证
  }
}

export function setToken(token: string) {
  // #ifdef H5
  _h5Set(TOKEN_KEY, token);
  // #endif
  // #ifndef H5
  uni.setStorageSync(TOKEN_KEY, token);
  // #endif
}

export function getToken(): string {
  let token: string;
  // #ifdef H5
  token = _h5Get(TOKEN_KEY);
  // #endif
  // #ifndef H5
  token = uni.getStorageSync(TOKEN_KEY) || "";
  // #endif
  // P0-10: App/小程序端也检查 exp，过期则清除
  if (token && _isTokenExpired(token)) {
    clearToken();
    clearRefreshToken();
    return "";
  }
  return token;
}

export function clearToken() {
  // #ifdef H5
  _h5Remove(TOKEN_KEY);
  // #endif
  // #ifndef H5
  uni.removeStorageSync(TOKEN_KEY);
  // #endif
}

export function setRefreshToken(token: string) {  // FIXED: W-31补充 添加refresh_token存取
  // #ifdef H5
  _h5Set(REFRESH_TOKEN_KEY, token);
  // #endif
  // #ifndef H5
  uni.setStorageSync(REFRESH_TOKEN_KEY, token);
  // #endif
}

export function getRefreshToken(): string {  // FIXED: W-31补充 添加refresh_token存取
  // #ifdef H5
  return _h5Get(REFRESH_TOKEN_KEY);
  // #endif
  // #ifndef H5
  return uni.getStorageSync(REFRESH_TOKEN_KEY) || "";
  // #endif
}

export function clearRefreshToken() {  // FIXED: W-31补充 添加refresh_token存取
  // #ifdef H5
  _h5Remove(REFRESH_TOKEN_KEY);
  // #endif
  // #ifndef H5
  uni.removeStorageSync(REFRESH_TOKEN_KEY);
  // #endif
}

export function setProfile(profile: Record<string, unknown>) {
  uni.setStorageSync(PROFILE_KEY, profile);
}

export function getProfile<T = Record<string, unknown>>(): T | null {
  return uni.getStorageSync(PROFILE_KEY) || null;
}

export function clearProfile() {
  uni.removeStorageSync(PROFILE_KEY);
}
