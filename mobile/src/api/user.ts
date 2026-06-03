import { request } from "@/utils/request";

export interface UserItem {
  id: string;
  username: string;
  full_name?: string | null;
}

export function listUsers(limit = 200) {
  return request<UserItem[]>({
    url: `/api/v1/users?skip=0&limit=${encodeURIComponent(String(limit))}`
  });
}
