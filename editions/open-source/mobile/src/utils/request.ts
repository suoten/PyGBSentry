import { getToken, setToken, clearToken, getRefreshToken, setRefreshToken, clearRefreshToken, clearProfile } from "./storage";
import { refreshToken as refreshTokenApi } from "@/api/auth";  // FIXED: W-31补充 引入refreshToken API

const API_BASE = (import.meta.env.VITE_API_BASE || "").replace(/\/$/, "");

let _isRefreshing = false;  // FIXED-P1: C-06 防止refreshToken递归调用

type HttpMethod = "GET" | "POST" | "PUT" | "DELETE";

interface RequestOptions<T> {
  url: string;
  method?: HttpMethod;
  data?: Record<string, unknown> | string;
  params?: Record<string, string | number | boolean>;  // FIXED-P1: S-08 添加params支持，之前传入params被静默忽略
  header?: Record<string, string>;
  withAuth?: boolean;
  formUrlEncoded?: boolean;
}

function buildUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  return `${API_BASE}${path}`;
}

// FIXED-P1: S-08 将params对象拼接到URL查询字符串
function appendParams(url: string, params: Record<string, string | number | boolean> | undefined): string {
  if (!params || Object.keys(params).length === 0) return url;
  const qs = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
    .join("&");
  return qs ? `${url}${url.includes("?") ? "&" : "?"}${qs}` : url;
}

function showFriendlyError(message: string) {
  uni.showToast({
    title: message || "Request failed, please try again later", // FIXED: 硬编码中文→英文
    icon: "none",
    duration: 2200
  });
}

export async function request<T = unknown>(options: RequestOptions<T>): Promise<T> {
  const token = getToken();
  const method = options.method || "GET";
  const headers: Record<string, string> = {
    ...(options.header || {})
  };

  if (options.withAuth !== false && token) {
    headers.Authorization = `Bearer ${token}`;
  }
  if (options.formUrlEncoded) {
    headers["Content-Type"] = "application/x-www-form-urlencoded";
  }

  const [err, res] = await uni.request({
    url: appendParams(buildUrl(options.url), options.params),  // FIXED-P1: S-08 支持params查询参数
    method,
    data: options.data as any,
    header: headers
  });

  if (err) {
    showFriendlyError("Network error, please check connection"); // FIXED: 硬编码中文→英文
    throw err;
  }

  const statusCode = res.statusCode || 500;
  if (statusCode >= 200 && statusCode < 300) {
    return res.data as T;
  }

  const detail = (res.data as any)?.detail;
  if (statusCode === 401) {
    // FIXED: W-31补充 401时先尝试refreshToken，失败后再跳转登录页
    const rt = getRefreshToken();
    if (rt && !_isRefreshing) {  // FIXED-P1: C-06 增加_isRefreshing守卫，防止递归
      _isRefreshing = true;
      try {
        const refreshRes = await refreshTokenApi(rt);
        if (refreshRes.access_token) {
          setToken(refreshRes.access_token);
          if (refreshRes.refresh_token) {
            setRefreshToken(refreshRes.refresh_token);
          }
          // 用新token重试原始请求
          const retryHeaders: Record<string, string> = {
            ...(options.header || {}),
            Authorization: `Bearer ${refreshRes.access_token}`
          };
          const [retryErr, retryRes] = await uni.request({
            url: appendParams(buildUrl(options.url), options.params),  // FIXED-P1: S-08 重试时也拼接params
            method: options.method || "GET",
            data: options.data as any,
            header: retryHeaders
          });
          if (!retryErr && retryRes.statusCode && retryRes.statusCode >= 200 && retryRes.statusCode < 300) {
            return retryRes.data as T;
          }
        }
      } catch {
        // refreshToken失败，继续走清除逻辑
      } finally {
        _isRefreshing = false;
      }
    }
    // FIXED: W-31 401跳转登录页(mine)而非首页(home)
    clearToken();
    clearRefreshToken();
    clearProfile();
    showFriendlyError("Login expired, please log in again");
    uni.reLaunch({ url: "/pages/mine/index" });
  } else {
    showFriendlyError(typeof detail === "string" ? detail : "Request failed"); // FIXED: 硬编码中文→英文
  }
  throw new Error(typeof detail === "string" ? detail : `HTTP ${statusCode}`);
}

export function toFormUrlEncoded(payload: Record<string, string>) {
  return Object.keys(payload)
    .map((k) => `${encodeURIComponent(k)}=${encodeURIComponent(payload[k])}`)
    .join("&");
}
