import { useEffect, useState } from "react";
import type { Monitor, RecentItem } from "../types";
import { fetchRecentItems, stopMonitor, resumeMonitor, runMonitor, deleteMonitorFromApi, fetchMonitorProgress } from "../api";
import { fmtDate, fmtDateTime } from "../utils";

function formatCountdown(seconds: number): string {
  if (seconds <= 0) return "Running…";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

export default function MonitorCard({ monitor, onEdit }: { monitor: Monitor; onEdit?: (m: Monitor) => void }) {
  const [countdown, setCountdown] = useState("");
  const [recent, setRecent] = useState<RecentItem[]>([]);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<{ current: number; total: number } | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [isPaused, setIsPaused] = useState(monitor.paused);

  useEffect(() => {
    setIsPaused(monitor.paused);
  }, [monitor.paused]);

  useEffect(() => {
    const tick = () => {
      if (!monitor.next_run_time) {
        setCountdown(isPaused ? "Paused" : "—");
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
  }, [monitor.next_run_time, isPaused]);

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

  useEffect(() => {
    if (!running) {
      setProgress(null);
      return;
    }
    const poll = async () => {
      try {
        const p = await fetchMonitorProgress(monitor.id);
        if (p.running) setProgress({ current: p.current, total: p.total });
      } catch { /* ignore */ }
    };
    poll();
    const id = setInterval(poll, 1500);
    return () => clearInterval(id);
  }, [monitor.id, running]);

  const statusBadge = isPaused
    ? "bg-yellow/10 text-yellow"
    : "bg-green/10 text-green";

  const statusLabel = isPaused ? "Paused" : "Active";

  const avgPrice =
    monitor.avg_price !== null
      ? "€" + monitor.avg_price.toFixed(2)
      : "—";

  const lastScrape = fmtDateTime(monitor.last_scrape);

  const handleRun = async () => {
    setRunning(true);
    setActionMsg(null);
    try {
      const res = await runMonitor(monitor.id);
      setActionMsg(`${res.new_items_found} new · avg €${res.current_avg_price}`);
    } catch {
      setActionMsg("Run failed");
    }
    setRunning(false);
  };

  const handleTogglePause = async () => {
    setActionMsg(null);
    const next = !isPaused;
    setIsPaused(next);
    try {
      if (next) {
        await stopMonitor(monitor.id);
      } else {
        await resumeMonitor(monitor.id);
      }
    } catch {
      setIsPaused(!next);
      setActionMsg("Failed");
    }
  };

  const handleDelete = async () => {
    setActionMsg(null);
    try {
      await deleteMonitorFromApi(monitor.id);
      setActionMsg("Deleted");
      setConfirmDelete(false);
    } catch {
      setActionMsg("Delete failed");
    }
  };

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

      {/* Actions */}
      <div className="flex flex-wrap gap-2 mb-3">
        <button
          onClick={() => onEdit?.(monitor)}
          className="font-sans text-xs font-semibold text-accent-2 border border-accent-2/40 hover:bg-accent-2/10 px-3 py-1.5 rounded-xl transition-colors"
        >
          Edit
        </button>
        <button
          onClick={handleRun}
          disabled={running}
          className="font-sans text-xs font-semibold text-white bg-accent/80 hover:bg-accent disabled:opacity-50 px-3 py-1.5 rounded-xl transition-colors"
        >
          {running
            ? progress
              ? `Page ${progress.current}/${progress.total}`
              : "Running…"
            : "Run"}
        </button>
        <button
          onClick={handleTogglePause}
          className="font-sans text-xs font-semibold text-accent-2 border border-accent-2/40 hover:bg-accent-2/10 px-3 py-1.5 rounded-xl transition-colors"
        >
          {isPaused ? "Resume" : "Pause"}
        </button>
        {confirmDelete ? (
          <span className="flex items-center gap-1.5">
            <span className="font-sans text-xs text-red">Delete?</span>
            <button
              onClick={handleDelete}
              className="font-sans text-xs font-semibold text-white bg-red hover:bg-red/80 px-2.5 py-1.5 rounded-xl transition-colors"
            >
              Yes
            </button>
            <button
              onClick={() => setConfirmDelete(false)}
              className="font-sans text-xs text-muted hover:text-ink px-2.5 py-1.5 rounded-xl transition-colors"
            >
              No
            </button>
          </span>
        ) : (
          <button
            onClick={() => setConfirmDelete(true)}
            className="font-sans text-xs text-red/60 hover:text-red px-3 py-1.5 rounded-xl transition-colors"
          >
            Delete
          </button>
        )}
        <a
          href={`/monitor/${monitor.id}`}
          className="font-sans text-xs text-accent-2 hover:underline self-center ml-auto"
        >
          Charts
        </a>
      </div>

      {/* Action feedback */}
      {actionMsg && (
        <div className="font-sans text-xs text-muted mb-2 italic">
          {actionMsg}
        </div>
      )}

      {recent.length > 0 && (
        <div className="mb-1">
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
                  {fmtDate(item.listed_at)}
                </span>
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
