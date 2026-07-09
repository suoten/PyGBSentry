import { getToken, setToken, clearToken, getRefreshToken, setRefreshToken, clearRefreshToken, clearProfile } from "./storage";
import { refreshToken as refreshTokenApi } from "@/api/auth";

const API_BASE = (import.meta.env.VITE_API_BASE || "").replace(/\/$/, "");

// ── Constants ──────────────────────────────────────────────
const TOAST_DURATION = 2200;
const REQUEST_TIMEOUT = 30000;
const HTTP_OK_MIN = 200;
const HTTP_OK_MAX = 300;
const HTTP_UNAUTHORIZED = 401;

// ── Token refresh queue ────────────────────────────────────
let _isRefreshing = false;
let _refreshSubscribers: Array<{ resolve: (token: string) => void; reject: (err: unknown) => void }> = [];

function onTokenRefreshed(token: string) {
  _refreshSubscribers.forEach(({ resolve }) => {
    try { resolve(token); } catch { /* ignore subscriber error */ }
  });
  _refreshSubscribers = [];
}

function onRefreshFailed(err: unknown) {
  _refreshSubscribers.forEach(({ reject: rej }) => {
    try { rej(err); } catch { /* ignore */ }
  });
  _refreshSubscribers = [];
}

function addRefreshSubscriber(resolve: (token: string) => void, reject: (err: unknown) => void) {
  _refreshSubscribers.push({ resolve, reject });
}

// ── Types ──────────────────────────────────────────────────
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

interface ApiErrorBody {
  detail?: string;
  message?: string;
}

const ERROR_MESSAGES = {
  networkError: "Network error, please check connection",
  requestFailed: "Request failed, please try again later",
  loginExpired: "Login expired, please log in again",
  requestFailedShort: "Request failed",
} as const;

// ── Helpers ────────────────────────────────────────────────
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
    title: message || ERROR_MESSAGES.requestFailed,
    icon: "none",
    duration: TOAST_DURATION,
  });
}

function isSuccess(statusCode: number): boolean {
  return statusCode >= HTTP_OK_MIN && statusCode < HTTP_OK_MAX;
}

/** Build auth headers, merging custom headers with a bearer token. */
function buildAuthHeaders(
  customHeaders: Record<string, string> | undefined,
  token: string,
): Record<string, string> {
  return { ...(customHeaders || {}), Authorization: `Bearer ${token}` };
}

/** Execute a uni.request and return [err, res]. */
function execRequest(
  options: RequestOptions<unknown>,
  headers: Record<string, string>,
): Promise<[unknown, UniApp.RequestSuccessCallbackResult]> {
  return uni.request({
    url: appendParams(buildUrl(options.url), options.params),
    method: options.method || "GET",
    data: options.data,
    header: headers,
    timeout: REQUEST_TIMEOUT,
  }) as unknown as Promise<[unknown, UniApp.RequestSuccessCallbackResult]>;
}

/** Attempt to refresh the token and retry the original request. Returns data or throws. */
async function tryRefreshAndRetry<T>(options: RequestOptions<T>): Promise<T> {
  const rt = getRefreshToken();
  const isRefreshRequest = options.url.includes("/login/refresh-token");

  // Case 1: No refresh token or already refreshing or this IS the refresh request → fail
  if (!rt || isRefreshRequest) {
    return failWithAuthError();
  }

  // Case 2: Another refresh is in flight → queue and wait
  if (_isRefreshing) {
    return new Promise<T>((resolve, reject) => {
      addRefreshSubscriber(
        (newToken: string) => {
          const retryHeaders = buildAuthHeaders(options.header, newToken);
          execRequest(options as RequestOptions<unknown>, retryHeaders)
            .then(([retryErr, retryRes]) => {
              if (!retryErr && retryRes.statusCode && isSuccess(retryRes.statusCode)) {
                resolve(retryRes.data as T);
              } else {
                reject(new Error(`HTTP ${HTTP_UNAUTHORIZED}`));
              }
            })
            .catch(reject);
        },
        (err: unknown) => reject(err),
      );
    });
  }

  // Case 3: We can refresh now
  _isRefreshing = true;
  try {
    const refreshRes = await refreshTokenApi(rt);
    if (refreshRes.access_token) {
      setToken(refreshRes.access_token);
      if (refreshRes.refresh_token) setRefreshToken(refreshRes.refresh_token);
      onTokenRefreshed(refreshRes.access_token);

      const retryHeaders = buildAuthHeaders(options.header, refreshRes.access_token);
      const [retryErr, retryRes] = await execRequest(options as RequestOptions<unknown>, retryHeaders);
      if (!retryErr && retryRes.statusCode && isSuccess(retryRes.statusCode)) {
        return retryRes.data as T;
      }
    }
  } catch (err) {
    onRefreshFailed(err);
  } finally {
    _isRefreshing = false;
  }

  return failWithAuthError();
}

/** Clear auth state, show login-expired toast, redirect, and throw. */
function failWithAuthError<T>(): T {
  clearToken();
  clearRefreshToken();
  clearProfile();
  showFriendlyError(ERROR_MESSAGES.loginExpired);
  uni.reLaunch({ url: "/pages/mine/index" });
  throw new Error(`HTTP ${HTTP_UNAUTHORIZED}`);
}

// ── Main request function ──────────────────────────────────
export async function request<T = unknown>(options: RequestOptions<T>): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = { ...(options.header || {}) };

  if (options.withAuth !== false && token) {
    headers.Authorization = `Bearer ${token}`;
  }
  if (options.formUrlEncoded) {
    headers["Content-Type"] = "application/x-www-form-urlencoded";
  }

  const [err, res] = await execRequest(options as RequestOptions<unknown>, headers);

  if (err) {
    showFriendlyError(ERROR_MESSAGES.networkError);
    throw err;
  }

  const statusCode = res.statusCode || 500;
  if (isSuccess(statusCode)) {
    return res.data as T;
  }

  const detail = (res.data as ApiErrorBody | undefined)?.detail;

  if (statusCode === HTTP_UNAUTHORIZED) {
    return tryRefreshAndRetry<T>(options);
  }

  showFriendlyError(typeof detail === "string" ? detail : ERROR_MESSAGES.requestFailedShort);
  throw new Error(typeof detail === "string" ? detail : `HTTP ${statusCode}`);
}

export function toFormUrlEncoded(payload: Record<string, string>) {
  return Object.keys(payload)
    .map((k) => `${encodeURIComponent(k)}=${encodeURIComponent(payload[k])}`)
    .join("&");
}
