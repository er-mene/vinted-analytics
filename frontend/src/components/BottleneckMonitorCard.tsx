import { useState } from "react";
import { usePolling } from "../hooks/usePolling";
import { fetchPerformance, resetPerformance } from "../api";

export default function BottleneckMonitorCard() {
  const { data: perf, refetch } = usePolling(fetchPerformance, 3000);
  const [isResetting, setIsResetting] = useState(false);

  if (!perf) return null;

  const s = perf.summary;
  const bottleneckName = perf.primary_bottleneck.replace("_", " ").toUpperCase();

  const handleReset = async () => {
    if (!window.confirm("Reset all performance and bottleneck counters?")) return;
    setIsResetting(true);
    try {
      await resetPerformance();
      refetch();
    } finally {
      setIsResetting(false);
    }
  };

  const categories = [
    { key: "time_sleep", label: "time.sleep() / delays", stat: s.time_sleep, color: "bg-amber-500", hex: "#d97706" },
    { key: "web_scraping", label: "Web Scraping", stat: s.web_scraping, color: "bg-teal-600", hex: "#0f766e" },
    { key: "db_write", label: "DB Write", stat: s.db_write, color: "bg-purple-600", hex: "#7c3aed" },
    { key: "db_read", label: "DB Read", stat: s.db_read, color: "bg-blue-600", hex: "#2563eb" },
    { key: "other", label: "Other / CPU", stat: s.other, color: "bg-stone-400", hex: "#9ca3af" },
  ];

  return (
    <div className="bg-panel border border-line rounded-2xl p-5 mb-6 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
        <div>
          <span className="text-xs uppercase tracking-wider text-muted font-sans font-semibold">
            Runtime Bottleneck Monitor
          </span>
          <div className="text-lg font-bold font-serif text-ink mt-0.5">
            Primary Bottleneck:{" "}
            <span className="text-accent">{bottleneckName}</span>{" "}
            <span className="text-sm font-sans font-normal text-muted">
              ({perf.primary_bottleneck_pct}% of runtime)
            </span>
          </div>
          {perf.insights && perf.insights.length > 0 && (
            <p className="text-xs text-muted font-sans mt-1 max-w-3xl">
              {perf.insights[0]}
            </p>
          )}
        </div>
        <div className="flex items-center gap-3">
          <a
            href="/api/performance/report"
            target="_blank"
            rel="noreferrer"
            className="text-xs font-semibold text-accent hover:underline font-sans"
          >
            Full Report ↗
          </a>
          <button
            onClick={handleReset}
            disabled={isResetting}
            className="text-xs font-semibold px-2.5 py-1 bg-white hover:bg-stone-50 text-ink border border-line rounded-lg font-sans transition-colors disabled:opacity-50"
          >
            {isResetting ? "Resetting…" : "Reset Metrics"}
          </button>
        </div>
      </div>

      {/* Visual Percentage Distribution Bar */}
      <div className="w-full h-4 bg-stone-200 rounded-full overflow-hidden flex my-3">
        {categories.map((c) => (
          <div
            key={c.key}
            className={`h-full ${c.color} transition-all duration-300`}
            style={{ width: `${c.stat.percentage || 0}%` }}
            title={`${c.label}: ${c.stat.percentage}% (${c.stat.total_seconds}s)`}
          />
        ))}
      </div>

      {/* Legend & Key Metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 mt-3 pt-3 border-t border-line/60">
        {categories.map((c) => (
          <div key={c.key} className="font-sans">
            <div className="flex items-center gap-1.5 text-xs text-muted">
              <span
                className="w-2.5 h-2.5 rounded-full inline-block"
                style={{ backgroundColor: c.hex }}
              />
              <span className="font-medium truncate">{c.label}</span>
            </div>
            <div className="text-base font-bold text-ink mt-0.5">
              {c.stat.total_seconds}s{" "}
              <span className="text-xs font-normal text-muted">
                ({c.stat.percentage}%)
              </span>
            </div>
            <div className="text-[11px] text-muted">
              {c.stat.count} calls · avg {c.stat.avg_ms}ms
            </div>
          </div>
        ))}
      </div>

      {/* Last Completed Scrape Profile */}
      {perf.last_scrape && (
        <div className="mt-3 pt-3 border-t border-line/60 text-xs text-muted font-sans flex flex-wrap items-center justify-between gap-2">
          <div>
            <span className="font-semibold text-ink">Last Scrape:</span> Monitor #{perf.last_scrape.monitor_id} ({perf.last_scrape.monitor_name}) finished in{" "}
            <strong className="text-ink">{perf.last_scrape.duration_seconds}s</strong> ({perf.last_scrape.items_found} items found, {perf.last_scrape.new_items} new)
          </div>
          <div className="text-[11px]">
            Delays: {perf.last_scrape.breakdown_percentages.time_sleep || 0}% · Web: {perf.last_scrape.breakdown_percentages.web_scraping || 0}% · DB Write: {perf.last_scrape.breakdown_percentages.db_write || 0}% · DB Read: {perf.last_scrape.breakdown_percentages.db_read || 0}%
          </div>
        </div>
      )}
    </div>
  );
}
