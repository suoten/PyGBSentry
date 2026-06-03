import { request } from "@/utils/request";

export interface OrganizationItem {
  id: string;
  name: string;
  parent_id?: string | null;
  tenant_id?: string;
  sort_order?: number;
}

export function listOrganizations() {
  return request<OrganizationItem[]>({
    url: "/api/v1/organizations"
  });
}
