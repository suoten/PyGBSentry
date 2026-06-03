import { request } from "@/utils/request";

export interface OrgNode {
  id: string;
  name: string;
  parent_id?: string | null;
  tenant_id?: string;
  sort_order?: number;
  children?: OrgNode[];
}

export interface CreateOrganizationPayload {
  name: string;
  parent_id?: string;
  sort_order?: number;
}

export interface UpdateOrganizationPayload {
  name?: string;
  parent_id?: string;
  sort_order?: number;
}

export interface UserItem {
  id: string;
  username: string;
  email?: string | null;
  full_name?: string | null;
  is_active: boolean;
  is_superuser: boolean;
  tenant_id: string;
  role: string;
}

export interface UserRoleItem {
  code: string;
  name: string;
}

export interface RoleItem {
  id: string;
  tenant_id: string;
  code: string;
  name: string;
  description?: string | null;
  permission_codes?: string[];
  is_system?: boolean;
}

export interface RolePayload {
  code: string;
  name: string;
  description?: string;
  permission_codes?: string[];
}

export interface CreateUserPayload {
  username: string;
  password: string;
  email?: string;
  full_name?: string;
  is_superuser?: boolean;
  tenant_id?: string;
  role?: string;
}

export interface UpdateUserPayload {
  email?: string | null;
  full_name?: string | null;
  is_active?: boolean;
  is_superuser?: boolean;
  tenant_id?: string;
  role?: string;
}

export function fetchOrganizationTree() {
  return request<OrgNode[]>({
    url: "/api/v1/organizations/tree"
  });
}

export function createOrganization(payload: CreateOrganizationPayload) {
  return request<{ id: string; name: string; parent_id?: string }>({
    url: "/api/v1/organizations",
    method: "POST",
    data: payload
  });
}

export function updateOrganization(organizationId: string, payload: UpdateOrganizationPayload) {
  return request<{ status: string }>({
    url: `/api/v1/organizations/${encodeURIComponent(organizationId)}`,
    method: "PUT",
    data: payload
  });
}

export function deleteOrganization(organizationId: string) {
  return request<{ status: string }>({
    url: `/api/v1/organizations/${encodeURIComponent(organizationId)}`,
    method: "DELETE"
  });
}

export function fetchUsers(skip = 0, limit = 100) {
  return request<UserItem[]>({
    url: `/api/v1/users?skip=${encodeURIComponent(String(skip))}&limit=${encodeURIComponent(String(limit))}`
  });
}

export function fetchMe() {
  return request<UserItem>({
    url: "/api/v1/users/me"
  });
}

export function fetchRoles() {
  return request<UserRoleItem[]>({
    url: "/api/v1/roles"
  });
}

export function createRole(payload: RolePayload) {
  return request<RoleItem>({
    url: "/api/v1/roles",
    method: "POST",
    data: payload
  });
}

export function updateRole(roleId: string, payload: RolePayload) {
  return request<RoleItem>({
    url: `/api/v1/roles/${encodeURIComponent(roleId)}`,
    method: "PUT",
    data: payload
  });
}

export function deleteRole(roleId: string) {
  return request<{ ok: boolean }>({
    url: `/api/v1/roles/${encodeURIComponent(roleId)}`,
    method: "DELETE"
  });
}

export function createUser(payload: CreateUserPayload) {
  return request<UserItem>({
    url: "/api/v1/users",
    method: "POST",
    data: payload
  });
}

export function updateUser(userId: string, payload: UpdateUserPayload) {
  return request<UserItem>({
    url: `/api/v1/users/${encodeURIComponent(userId)}`,
    method: "PUT",
    data: payload
  });
}

export function deleteUser(userId: string) {
  return request<{ ok: boolean }>({
    url: `/api/v1/users/${encodeURIComponent(userId)}`,
    method: "DELETE"
  });
}
