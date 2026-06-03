import { getToken, setToken, clearToken, getRefreshToken, setRefreshToken, clearRefreshToken, clearProfile } from "./storage";
import { refreshToken as refreshTokenApi } from "@/api/auth";

const API_BASE = (import.meta.env.VITE_API_BASE || "").replace(/\/$/, "");

let _isRefreshing = false;
let _refreshSubscribers: Array<{ resolve: (token: string) => void; reject: (err: unknown) => void }> = [];

function onTokenRefreshed(token: string) {
  _refreshSubscribers.forEach(({ resolve }) => {
    try {
      resolve(token);
    } catch { /* ignore subscriber error */ }
  });
  _refreshSubscribers = [];
}

function onRefreshFailed(err: unknown) {
  _refreshSubscribers.forEach(({ reject: rej }) => {
    try {
      rej(err);
    } catch { /* ignore */ }
  });
  _refreshSubscribers = [];
}

function addRefreshSubscriber(resolve: (token: string) => void, reject: (err: unknown) => void) {
  _refreshSubscribers.push({ resolve, reject });
}

type HttpMethod = "GET" | "POST" | "PUT" | "DELETE";

interface RequestOptions<T> {
  url: string;
  method?: HttpMethod;
  data?: Record<string, unknown> | string;
  params?: Record<string, string | number | boolean>;
  header?: Record<string, string>;
  withAuth?: boolean;
  formUrlEncoded?: boolean;
}

function buildUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  return `${API_BASE}${path}`;
}

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
    title: message || "Request failed, please try again later",
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
    url: appendParams(buildUrl(options.url), options.params),
    method,
    data: options.data as any,
    header: headers,
    timeout: 30000
  });

  if (err) {
    showFriendlyError("Network error, please check connection");
    throw err;
  }

  const statusCode = res.statusCode || 500;
  if (statusCode >= 200 && statusCode < 300) {
    return res.data as T;
  }

  const detail = (res.data as any)?.detail;
  if (statusCode === 401) {
    const isRefreshRequest = options.url.includes("/login/refresh-token");
    const rt = getRefreshToken();
    if (rt && !_isRefreshing && !isRefreshRequest) {
      _isRefreshing = true;
      try {
        const refreshRes = await refreshTokenApi(rt);
        if (refreshRes.access_token) {
          setToken(refreshRes.access_token);
          if (refreshRes.refresh_token) {
            setRefreshToken(refreshRes.refresh_token);
          }
          onTokenRefreshed(refreshRes.access_token);
          const retryHeaders: Record<string, string> = {
            ...(options.header || {}),
            Authorization: `Bearer ${refreshRes.access_token}`
          };
          const [retryErr, retryRes] = await uni.request({
            url: appendParams(buildUrl(options.url), options.params),
            method: options.method || "GET",
            data: options.data as any,
            header: retryHeaders,
            timeout: 30000
          });
          if (!retryErr && retryRes.statusCode && retryRes.statusCode >= 200 && retryRes.statusCode < 300) {
            return retryRes.data as T;
          }
        }
      } catch (err) {
        onRefreshFailed(err);
      } finally {
        _isRefreshing = false;
      }
    } else if (rt && _isRefreshing && !isRefreshRequest) {
      return new Promise<T>((resolve, reject) => {
        addRefreshSubscriber((newToken: string) => {
          const retryHeaders: Record<string, string> = {
            ...(options.header || {}),
            Authorization: `Bearer ${newToken}`
          };
          uni.request({
            url: appendParams(buildUrl(options.url), options.params),
            method: options.method || "GET",
            data: options.data as any,
            header: retryHeaders,
            timeout: 30000
          }).then(([retryErr, retryRes]) => {
            if (!retryErr && retryRes.statusCode && retryRes.statusCode >= 200 && retryRes.statusCode < 300) {
              resolve(retryRes.data as T);
            } else {
              reject(new Error(typeof detail === "string" ? detail : `HTTP ${statusCode}`));
            }
          }).catch(reject);
        }, (err: unknown) => {
          reject(err);
        });
      });
    }
    clearToken();
    clearRefreshToken();
    clearProfile();
    showFriendlyError("Login expired, please log in again");
    uni.reLaunch({ url: "/pages/mine/index" });
  } else {
    showFriendlyError(typeof detail === "string" ? detail : "Request failed");
  }
  throw new Error(typeof detail === "string" ? detail : `HTTP ${statusCode}`);
}

export function toFormUrlEncoded(payload: Record<string, string>) {
  return Object.keys(payload)
    .map((k) => `${encodeURIComponent(k)}=${encodeURIComponent(payload[k])}`)
    .join("&");
}
