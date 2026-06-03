import { useCallback } from "react";
import { fetchOverview } from "../api";
import { usePolling } from "../hooks/usePolling";
import SummaryCards from "../components/SummaryCards";
import MonitorCard from "../components/MonitorCard";

export default function Dashboard() {
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
      <SummaryCards
        cards={[
          { label: "Monitors", value: data.monitors.length },
          { label: "Active Listings", value: totalActiveListings },
          { label: "Queue Size", value: data.queue.total },
          {
            label: "Oldest Queued",
            value: data.queue.oldest_queued
              ? data.queue.oldest_queued.slice(0, 10)
              : "—",
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
            <MonitorCard key={m.id} monitor={m} />
          ))}
        </div>
      )}
    </div>
  );
}
