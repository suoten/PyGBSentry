import type { UserProfile } from "@/types/api";
import { request, toFormUrlEncoded } from "@/utils/request";

export interface LoginPayload {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  refresh_token?: string;  // FIXED: 原LoginResponse缺少refresh_token字段
  role?: string;  // FIXED: 原LoginResponse缺少role字段
  is_superuser: boolean;  // FIXED: W44 原LoginResponse缺少is_superuser字段
  tenant_id: string;  // FIXED: W44 原LoginResponse缺少tenant_id字段
}

export function login(payload: LoginPayload) {
  return request<LoginResponse>({
    url: "/api/v1/login/access-token",
    method: "POST",
    withAuth: false,
    formUrlEncoded: true,
    data: toFormUrlEncoded({
      username: payload.username,
      password: payload.password
    })
  });
}

export function getProfile() {
  return request<UserProfile>({
    url: "/api/v1/users/me"
  });
}

// FIXED: 原auth.ts缺少refreshToken调用
export function refreshToken(refreshToken: string) {
  return request<LoginResponse>({
    url: "/api/v1/login/refresh-token",
    method: "POST",
    withAuth: false,
    data: { refresh_token: refreshToken }
  });
}
