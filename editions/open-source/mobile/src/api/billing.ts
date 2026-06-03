import { request } from "@/utils/request";

export interface BillingPlanItem {
  id: string;
  code: string;
  name: string;
  price_monthly: number;
  max_devices: number;
  plugin_entitlements?: string;
}

export interface BillingSubscription {
  tenant_id: string;
  plan_code: string;
  status: string;
  trial_ends_at?: string | null;
  ends_at?: string | null;
}

export interface BillingPluginItem {
  id: string;
  name: string;
  price_monthly: number;
  version?: string;
  type?: string;
}

export interface BillingOrderItem {
  order_no: string;
  plugin_id: string;
  plugin_name?: string;
  amount: number;
  status: string;
  pay_channel?: string;
  paid_at?: string | null;
}

export interface BillingLicenseItem {
  order_no: string;
  plugin_id: string;
  plugin_name?: string;
  paid_at?: string | null;
  expires_at?: string | null;
}

export interface BillingBranding {
  product_name: string;
  logo_url?: string;
  primary_color: string;
  welcome_text: string;
}

export interface BillingCreateOrderPayload {
  plugin_id: string;
  months: number;
  pay_channel: string;
}

export interface BillingCreateOrderResult {
  order_no: string;
  status: string;
  amount: number;
  currency: string;
  pay_channel: string;
  callback_sign_example: string;
  return_url?: string;
}

export interface BillingPaymentCallbackPayload {
  order_no: string;
  status: "paid" | "failed";
  paid_amount: number;
  provider_trade_no?: string;
  signature: string;
}

export function fetchBillingPlans() {
  return request<BillingPlanItem[]>({
    url: "/api/v1/billing/plans"
  });
}

export function fetchMySubscription() {
  return request<BillingSubscription>({
    url: "/api/v1/billing/subscription/me"
  });
}

export function fetchMyBranding() {
  return request<BillingBranding>({
    url: "/api/v1/billing/branding/me"
  });
}

export function saveMyBranding(payload: BillingBranding) {
  return request<BillingBranding>({
    url: "/api/v1/billing/branding/me",
    method: "PUT",
    data: payload
  });
}

export function fetchBillingPlugins() {
  return request<BillingPluginItem[]>({
    url: "/api/v1/billing/plugins"
  });
}

export function fetchMyOrders() {
  return request<BillingOrderItem[]>({
    url: "/api/v1/billing/orders/me"
  });
}

export function fetchMyLicenses() {
  return request<BillingLicenseItem[]>({
    url: "/api/v1/billing/licenses/me"
  });
}

export function createBillingOrder(payload: BillingCreateOrderPayload) {
  return request<BillingCreateOrderResult>({
    url: "/api/v1/billing/orders",
    method: "POST",
    data: payload
  });
}

export function simulateBillingPaymentCallback(payload: BillingPaymentCallbackPayload) {
  return request<{ status: string; order_no: string; order_status: string }>({
    url: `/api/v1/billing/payment/callback`,
    method: "POST",
    data: payload
  });
}
