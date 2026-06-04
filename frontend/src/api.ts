import type {
  OverviewResponse,
  QueueResponse,
  RecentItem,
  MonitorAnalytics,
  MonitorListing,
  MonitorCreatePayload,
  MonitorCreateResponse,
  MonitorActionResponse,
  RunMonitorResponse,
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

export async function fetchMonitorListings(
  monitorId: number,
  sortBy: string = "likes",
  order: string = "desc",
): Promise<MonitorListing[]> {
  const res = await fetch(`${BASE}/monitor/${monitorId}/listings?sort_by=${sortBy}&order=${order}&limit=500&_=${Date.now()}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function createMonitor(data: MonitorCreatePayload): Promise<MonitorCreateResponse> {
  const res = await fetch(`${BASE}/monitor`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function updateMonitor(id: number, data: MonitorCreatePayload): Promise<MonitorCreateResponse> {
  const res = await fetch(`${BASE}/monitor/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function stopMonitor(id: number): Promise<MonitorActionResponse> {
  const res = await fetch(`${BASE}/monitor/stop?monitor_id=${id}`, { method: "PATCH" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function resumeMonitor(id: number): Promise<MonitorActionResponse> {
  const res = await fetch(`${BASE}/monitor/resume?monitor_id=${id}`, { method: "PATCH" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function deleteMonitorFromApi(id: number): Promise<MonitorActionResponse> {
  const res = await fetch(`${BASE}/monitor/delete?monitor_id=${id}`, { method: "POST" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function runMonitor(id: number): Promise<RunMonitorResponse> {
  const res = await fetch(`${BASE}/monitor/${id}/run?_=${Date.now()}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function fetchMonitorProgress(id: number): Promise<{ current: number; total: number; running: boolean }> {
  const res = await fetch(`${BASE}/monitor/${id}/progress?_=${Date.now()}`);
  if (!res.ok) return { current: 0, total: 0, running: false };
  return res.json();
}
