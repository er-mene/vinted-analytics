import { useState, useCallback } from "react";
import { fetchOverview } from "../api";
import { usePolling } from "../hooks/usePolling";
import { fmtDate } from "../utils";
import SummaryCards from "../components/SummaryCards";
import MonitorCard from "../components/MonitorCard";
import CreateMonitorModal from "../components/CreateMonitorModal";
import type { Monitor } from "../types";

export default function Dashboard() {
  const [showCreate, setShowCreate] = useState(false);
  const [editingMonitor, setEditingMonitor] = useState<Monitor | null>(null);
  const fetcher = useCallback(() => fetchOverview(), []);
  const { data, error, isLoading } = usePolling(fetcher, 2000);

  if (isLoading) {
    return (
      <div className="shell text-center text-muted font-sans py-16">
        Loading…
      </div>
    );
  }

  if (error) {
    return (
      <div className="shell text-center text-red font-sans py-16">
        {error}
      </div>
    );
  }

  if (!data) return null;

  const totalActiveListings = data.monitors.reduce(
    (s, m) => s + (m.active_listings || 0),
    0,
  );

  return (
    <div className="max-w-7xl mx-auto px-5 py-6">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold font-serif">Dashboard</h1>
        <button
          onClick={() => setShowCreate(true)}
          className="font-sans text-sm font-semibold text-white bg-accent hover:bg-accent/90 px-4 py-2 rounded-xl transition-colors"
        >
          + New Monitor
        </button>
      </div>

      {(showCreate || editingMonitor) && (
        <CreateMonitorModal
          editMonitor={editingMonitor}
          onClose={() => { setShowCreate(false); setEditingMonitor(null); }}
        />
      )}

      <SummaryCards
        cards={[
          { label: "Monitors", value: data.monitors.length },
          { label: "Active Listings", value: totalActiveListings },
          { label: "Queue Size", value: data.queue.total },
          {
            label: "Oldest Queued",
            value: fmtDate(data.queue.oldest_queued),
          },
        ]}
      />

      {data.monitors.length === 0 ? (
        <p className="font-sans text-muted text-center py-16">
          No monitors yet.
        </p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {data.monitors.map((m) => (
            <MonitorCard key={m.id} monitor={m} onEdit={setEditingMonitor} />
          ))}
        </div>
      )}
    </div>
  );
}
