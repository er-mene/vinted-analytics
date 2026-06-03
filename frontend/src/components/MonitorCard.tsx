import { useEffect, useState } from "react";
import type { Monitor, RecentItem } from "../types";
import { fetchRecentItems } from "../api";

function formatCountdown(seconds: number): string {
  if (seconds <= 0) return "Running…";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

export default function MonitorCard({ monitor }: { monitor: Monitor }) {
  const [countdown, setCountdown] = useState("");
  const [recent, setRecent] = useState<RecentItem[]>([]);

  useEffect(() => {
    const tick = () => {
      if (!monitor.next_run_time) {
        setCountdown(monitor.paused ? "Paused" : "—");
        return;
      }
      const diff = Math.floor(
        (new Date(monitor.next_run_time).getTime() - Date.now()) / 1000,
      );
      setCountdown(formatCountdown(diff));
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [monitor.next_run_time, monitor.paused]);

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      try {
        const items = await fetchRecentItems(monitor.id);
        if (mounted) setRecent(items);
      } catch { /* ignore */ }
    };
    load();
    const id = setInterval(load, 4000);
    return () => { mounted = false; clearInterval(id); };
  }, [monitor.id]);

  const statusBadge = monitor.paused
    ? "bg-yellow/10 text-yellow"
    : countdown === "Running…"
      ? "bg-green/10 text-green"
      : "bg-green/10 text-green";

  const statusLabel = monitor.paused
    ? "Paused"
    : countdown === "Running…"
      ? "Running"
      : "Active";

  const avgPrice =
    monitor.avg_price !== null
      ? "€" + monitor.avg_price.toFixed(2)
      : "—";

  const lastScrape = monitor.last_scrape
    ? monitor.last_scrape.slice(0, 19).replace("T", " ")
    : "—";

  return (
    <div className="bg-panel/92 border border-line rounded-2xl shadow-[0_10px_30px_rgba(31,41,55,0.05)] backdrop-blur-sm p-5">
      <div className="flex items-start justify-between mb-3">
        <div>
          <h3 className="text-lg font-bold font-serif">{monitor.name}</h3>
          <p className="text-sm text-muted font-sans">{monitor.query}</p>
        </div>
        <span
          className={
            "inline-block px-2.5 py-0.5 rounded-full text-xs font-semibold font-sans " +
            statusBadge
          }
        >
          {statusLabel}
        </span>
      </div>

      <div className="font-sans text-sm mb-1">
        <span className="text-muted">Next run: </span>
        <span className="font-mono font-semibold text-ink">{countdown}</span>
      </div>
      <div className="font-sans text-sm mb-3">
        <span className="text-muted">Last scrape: </span>
        <span className="font-mono text-ink">{lastScrape}</span>
      </div>

      <div className="grid grid-cols-3 gap-2 text-center mb-4">
        <div>
          <div className="font-sans text-xs text-muted">Active</div>
          <div className="text-lg font-bold">{monitor.active_listings}</div>
        </div>
        <div>
          <div className="font-sans text-xs text-muted">Sold</div>
          <div className="text-lg font-bold">{monitor.sold_listings}</div>
        </div>
        <div>
          <div className="font-sans text-xs text-muted">Avg</div>
          <div className="text-lg font-bold">{avgPrice}</div>
        </div>
      </div>

      {recent.length > 0 && (
        <div className="mb-4">
          <div className="font-sans text-xs text-muted uppercase tracking-wider mb-2">
            Most liked items
          </div>
          <div className="space-y-1.5">
            {recent.slice(0, 5).map((item) => (
              <a
                key={item.id}
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 text-sm no-underline hover:bg-line/30 rounded px-1.5 py-1 transition-colors"
              >
                <span className="text-ink truncate flex-[2] min-w-0">
                  {item.title}
                </span>
                <span className="text-muted font-mono whitespace-nowrap text-right w-10">
                  {item.likes}
                </span>
                <span className="text-muted font-mono whitespace-nowrap text-right w-16">
                  €{Number(item.price ?? 0).toFixed(2)}
                </span>
                <span className="text-muted font-sans whitespace-nowrap text-right w-20 text-[0.8rem]">
                  {item.listed_at ? item.listed_at.slice(0, 10) : "—"}
                </span>
              </a>
            ))}
          </div>
        </div>
      )}

      <div className="flex gap-3 font-sans text-sm">
        <a
          href={`/api/monitor/${monitor.id}/run`}
          className="text-accent-2 hover:underline"
        >
          Run
        </a>
        <a
          href={`/api/monitor/${monitor.id}/analytics`}
          className="text-accent-2 hover:underline"
        >
          Data
        </a>
        <a
          href={`/monitor/${monitor.id}`}
          className="text-accent-2 hover:underline"
        >
          Chart
        </a>
      </div>
    </div>
  );
}
