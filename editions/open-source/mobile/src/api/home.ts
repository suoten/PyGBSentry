import { request } from "@/utils/request";

export interface HomeOverview {
  online_devices: number;
  offline_devices: number;
  today_alarms: number;
  pending_work_orders: number;
}

export async function fetchHomeOverview(): Promise<HomeOverview> {
  const [devices, alarms, workOrders] = await Promise.all([
    request<{ items: any[] }>({ url: "/api/v1/devices?skip=0&limit=1000" }),
    request<{ items: any[] }>({ url: "/api/v1/alarms?skip=0&limit=100" }),
    request<{ items: any[] }>({ url: "/api/v1/work-orders?skip=0&limit=100" })
  ]);

  const deviceItems = devices.items || [];
  const online = deviceItems.filter((d) => Number(d.status || 0) === 1).length;
  const offline = Math.max(deviceItems.length - online, 0);
  const alarmItems = alarms.items || [];
  const pending = (workOrders.items || []).filter((x) => !["closed", "resolved"].includes(String(x.status || "").toLowerCase())).length;  // FIXED-P0: S-02 后端状态枚举为open/in_progress/resolved/closed，"done"不存在

  return {
    online_devices: online,
    offline_devices: offline,
    today_alarms: alarmItems.length,
    pending_work_orders: pending
  };
}
