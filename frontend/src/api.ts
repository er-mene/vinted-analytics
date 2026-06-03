import type {
  OverviewResponse,
  QueueResponse,
  RecentItem,
  MonitorAnalytics,
} from "./types";

const BASE = "/api";

export async function fetchOverview(): Promise<OverviewResponse> {
  const res = await fetch(`${BASE}/overview?_=${Date.now()}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function fetchQueue(): Promise<QueueResponse> {
  const res = await fetch(`${BASE}/queue?_=${Date.now()}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function fetchRecentItems(monitorId: number): Promise<RecentItem[]> {
  const res = await fetch(`${BASE}/monitor/${monitorId}/top?_=${Date.now()}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function fetchMonitorAnalytics(monitorId: number): Promise<MonitorAnalytics> {
  const res = await fetch(`${BASE}/monitor/${monitorId}/analytics?_=${Date.now()}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
