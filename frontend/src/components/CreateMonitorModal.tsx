import { useState, useEffect } from "react";
import { createMonitor, updateMonitor } from "../api";
import type { Monitor, MonitorCreatePayload } from "../types";

const CONDITION_OPTIONS = [
  { id: 1, label: "New" },
  { id: 6, label: "New w/o tag" },
  { id: 3, label: "Good / Acceptable" },
  { id: 5, label: "Satisfactory" },
];

const TIME_OPTIONS = [
  { value: 86400, label: "Last day" },
  { value: 604800, label: "Last week" },
  { value: 2592000, label: "Last month" },
  { value: 5184000, label: "Last 2 months" },
  { value: 7776000, label: "Last 3 months" },
  { value: 15552000, label: "Last 6 months" },
  { value: 31536000, label: "Last year" },
];

interface Props {
  onClose: () => void;
  editMonitor?: Monitor | null;
}

export default function CreateMonitorModal({ onClose, editMonitor }: Props) {
  const isEdit = !!editMonitor;

  const [name, setName] = useState("");
  const [query, setQuery] = useState("");
  const [hours, setHours] = useState(0);
  const [minutes, setMinutes] = useState(30);
  const [brandId, setBrandId] = useState("");
  const [minPrice, setMinPrice] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [maxPages, setMaxPages] = useState(5);
  const [pageDelay, setPageDelay] = useState(4);
  const [searchTime, setSearchTime] = useState(5184000);
  const [statusIds, setStatusIds] = useState<number[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (editMonitor) {
      setName(editMonitor.name);
      setQuery(editMonitor.query);
      setHours(editMonitor.interval_hours);
      setMinutes(editMonitor.interval_minutes);
      setBrandId(editMonitor.brand_id !== null ? String(editMonitor.brand_id) : "");
      setMinPrice(editMonitor.min_price !== null ? String(editMonitor.min_price) : "");
      setMaxPrice(editMonitor.max_price !== null ? String(editMonitor.max_price) : "");
      setMaxPages(editMonitor.max_pages ?? 5);
      setPageDelay(editMonitor.page_delay_seconds);
      setSearchTime(editMonitor.search_time_seconds ?? 5184000);
      setStatusIds(editMonitor.status_ids ?? []);
    }
  }, [editMonitor]);

  const toggleCondition = (id: number) => {
    setStatusIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !query.trim()) {
      setError("Name and query are required.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const payload: MonitorCreatePayload = {
        name: name.trim(),
        query: query.trim(),
        hours,
        minutes,
        max_pages: maxPages || null,
        page_delay_seconds: pageDelay,
        search_time_seconds: searchTime,
        status_ids: statusIds,
      };
      if (brandId) payload.brand_id = Number(brandId);
      if (minPrice) payload.min_price = Number(minPrice);
      if (maxPrice) payload.max_price = Number(maxPrice);
      if (isEdit && editMonitor) {
        await updateMonitor(editMonitor.id, payload);
      } else {
        await createMonitor(payload);
      }
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to save monitor");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/20 backdrop-blur-sm">
      <div className="bg-panel border border-line rounded-2xl shadow-xl w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 pt-5 pb-3 border-b border-line">
          <h2 className="text-lg font-bold font-serif">
            {isEdit ? "Edit Monitor" : "New Monitor"}
          </h2>
          <button
            onClick={onClose}
            className="text-muted hover:text-ink text-xl leading-none"
          >
            &times;
          </button>
        </div>

        <form onSubmit={handleSubmit} className="px-6 py-4 space-y-4">
          {/* Name */}
          <div>
            <label className="font-sans text-xs text-muted uppercase tracking-wider block mb-1">
              Name *
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Apple Pencil Monitor"
              className="w-full border border-line rounded-xl px-3 py-2 bg-white/60 text-sm font-sans focus:outline-none focus:border-accent-2 transition-colors"
            />
          </div>

          {/* Query */}
          <div>
            <label className="font-sans text-xs text-muted uppercase tracking-wider block mb-1">
              Search query *
            </label>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. Apple Pencil 2"
              className="w-full border border-line rounded-xl px-3 py-2 bg-white/60 text-sm font-sans focus:outline-none focus:border-accent-2 transition-colors"
            />
          </div>

          {/* Schedule */}
          <div>
            <label className="font-sans text-xs text-muted uppercase tracking-wider block mb-1">
              Schedule
            </label>
            <div className="flex gap-3">
              <div className="flex-1">
                <input
                  type="number"
                  min={0}
                  value={hours}
                  onChange={(e) => setHours(Number(e.target.value))}
                  placeholder="0"
                  className="w-full border border-line rounded-xl px-3 py-2 bg-white/60 text-sm font-sans focus:outline-none focus:border-accent-2 transition-colors"
                />
                <span className="text-xs text-muted font-sans mt-0.5 block">
                  hours
                </span>
              </div>
              <div className="flex-1">
                <input
                  type="number"
                  min={0}
                  value={minutes}
                  onChange={(e) => setMinutes(Number(e.target.value))}
                  placeholder="30"
                  className="w-full border border-line rounded-xl px-3 py-2 bg-white/60 text-sm font-sans focus:outline-none focus:border-accent-2 transition-colors"
                />
                <span className="text-xs text-muted font-sans mt-0.5 block">
                  minutes (min 30)
                </span>
              </div>
            </div>
          </div>

          {/* Filters */}
          <details className="group">
            <summary className="font-sans text-xs text-muted uppercase tracking-wider cursor-pointer select-none group-open:text-ink transition-colors">
              Filters
            </summary>
            <div className="space-y-3 mt-3">
              <div>
                <label className="font-sans text-xs text-muted block mb-1">
                  Brand ID
                </label>
                <input
                  type="number"
                  value={brandId}
                  onChange={(e) => setBrandId(e.target.value)}
                  placeholder="e.g. 123"
                  className="w-full border border-line rounded-xl px-3 py-2 bg-white/60 text-sm font-sans focus:outline-none focus:border-accent-2 transition-colors"
                />
              </div>
              <div className="flex gap-3">
                <div className="flex-1">
                  <label className="font-sans text-xs text-muted block mb-1">
                    Min price
                  </label>
                  <input
                    type="number"
                    min={0}
                    step={0.01}
                    value={minPrice}
                    onChange={(e) => setMinPrice(e.target.value)}
                    placeholder="0"
                    className="w-full border border-line rounded-xl px-3 py-2 bg-white/60 text-sm font-sans focus:outline-none focus:border-accent-2 transition-colors"
                  />
                </div>
                <div className="flex-1">
                  <label className="font-sans text-xs text-muted block mb-1">
                    Max price
                  </label>
                  <input
                    type="number"
                    min={0}
                    step={0.01}
                    value={maxPrice}
                    onChange={(e) => setMaxPrice(e.target.value)}
                    placeholder="999"
                    className="w-full border border-line rounded-xl px-3 py-2 bg-white/60 text-sm font-sans focus:outline-none focus:border-accent-2 transition-colors"
                  />
                </div>
              </div>
              <div>
                <label className="font-sans text-xs text-muted block mb-1">
                  Time range
                </label>
                <select
                  value={searchTime}
                  onChange={(e) => setSearchTime(Number(e.target.value))}
                  className="w-full border border-line rounded-xl px-3 py-2 bg-white/60 text-sm font-sans focus:outline-none focus:border-accent-2 transition-colors"
                >
                  {TIME_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </details>

          {/* Scrolling */}
          <details className="group">
            <summary className="font-sans text-xs text-muted uppercase tracking-wider cursor-pointer select-none group-open:text-ink transition-colors">
              Scrolling
            </summary>
            <div className="space-y-3 mt-3">
              <div className="flex gap-3">
                <div className="flex-1">
                  <label className="font-sans text-xs text-muted block mb-1">
                    Max pages
                  </label>
                  <input
                    type="number"
                    min={0}
                    value={maxPages}
                    onChange={(e) => setMaxPages(Number(e.target.value))}
                    placeholder="5"
                    className="w-full border border-line rounded-xl px-3 py-2 bg-white/60 text-sm font-sans focus:outline-none focus:border-accent-2 transition-colors"
                  />
                </div>
                <div className="flex-1">
                  <label className="font-sans text-xs text-muted block mb-1">
                    Delay (seconds)
                  </label>
                  <input
                    type="number"
                    min={0.5}
                    step={0.5}
                    value={pageDelay}
                    onChange={(e) => setPageDelay(Number(e.target.value))}
                    placeholder="4"
                    className="w-full border border-line rounded-xl px-3 py-2 bg-white/60 text-sm font-sans focus:outline-none focus:border-accent-2 transition-colors"
                  />
                </div>
              </div>
            </div>
          </details>

          {/* Conditions */}
          <div>
            <label className="font-sans text-xs text-muted uppercase tracking-wider block mb-2">
              Condition
            </label>
            <div className="flex flex-wrap gap-2">
              {CONDITION_OPTIONS.map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => toggleCondition(opt.id)}
                  className={
                    "text-xs font-sans rounded-full px-3 py-1 border transition-colors " +
                    (statusIds.includes(opt.id)
                      ? "bg-accent-2/10 border-accent-2 text-accent-2"
                      : "bg-white/60 border-line text-muted hover:border-muted")
                  }
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Error */}
          {error && (
            <div className="text-red text-sm font-sans bg-red/5 border border-red/20 rounded-xl px-3 py-2">
              {error}
            </div>
          )}

          {/* Footer */}
          <div className="flex justify-end gap-3 pt-2 border-t border-line">
            <button
              type="button"
              onClick={onClose}
              className="font-sans text-sm text-muted hover:text-ink px-4 py-2 rounded-xl transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving || !name.trim() || !query.trim()}
              className="font-sans text-sm font-semibold text-white bg-accent hover:bg-accent/90 disabled:opacity-50 px-5 py-2 rounded-xl transition-colors"
            >
              {saving ? "Saving…" : isEdit ? "Save" : "Create"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
