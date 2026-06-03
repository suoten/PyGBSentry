const TOKEN_KEY = "pgbsentry_mobile_token";
const REFRESH_TOKEN_KEY = "pgbsentry_mobile_refresh_token";  // FIXED: W-31补充 添加refresh_token存储
const PROFILE_KEY = "pgbsentry_mobile_profile";

export function setToken(token: string) {
  uni.setStorageSync(TOKEN_KEY, token);
}

export function getToken(): string {
  return uni.getStorageSync(TOKEN_KEY) || "";
}

export function clearToken() {
  uni.removeStorageSync(TOKEN_KEY);
}

export function setRefreshToken(token: string) {  // FIXED: W-31补充 添加refresh_token存取
  uni.setStorageSync(REFRESH_TOKEN_KEY, token);
}

export function getRefreshToken(): string {  // FIXED: W-31补充 添加refresh_token存取
  return uni.getStorageSync(REFRESH_TOKEN_KEY) || "";
}

export function clearRefreshToken() {  // FIXED: W-31补充 添加refresh_token存取
  uni.removeStorageSync(REFRESH_TOKEN_KEY);
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
