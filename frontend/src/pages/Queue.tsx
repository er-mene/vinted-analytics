import { useCallback, useState } from "react";
import { fetchQueue, clearVerificationQueue } from "../api";
import { usePolling } from "../hooks/usePolling";
import { fmtDate } from "../utils";
import SummaryCards from "../components/SummaryCards";
import QueueItemRow from "../components/QueueItemRow";

export default function Queue() {
  const fetcher = useCallback(() => fetchQueue(), []);
  const { data, error, isLoading, refetch, mutate } = usePolling(fetcher, 2000);
  const [clearing, setClearing] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const handleClearQueue = async () => {
    setClearing(true);
    setActionError(null);
    try {
      await clearVerificationQueue();
      mutate((prev) => (prev ? { ...prev, total: 0, oldest_queued: null, items: [] } : null));
      refetch();
      setConfirmClear(false);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to clear queue");
    } finally {
      setClearing(false);
    }
  };

  if (isLoading) {
    return (
      <div className="max-w-7xl mx-auto px-5 py-6 text-center text-muted font-sans">
        Loading…
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-7xl mx-auto px-5 py-6 text-center text-red font-sans">
        {error}
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="max-w-7xl mx-auto px-5 py-6">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold font-serif">Verification Queue</h1>
        {confirmClear ? (
          <div className="flex items-center gap-2">
            <span className="font-sans text-sm text-red font-medium">
              Clear entire queue?
            </span>
            <button
              type="button"
              onClick={handleClearQueue}
              disabled={clearing}
              className="font-sans text-xs font-semibold text-white bg-red hover:bg-red/90 disabled:opacity-50 px-3 py-1.5 rounded-xl transition-colors cursor-pointer"
            >
              {clearing ? "Clearing…" : "Yes, Clear"}
            </button>
            <button
              type="button"
              onClick={() => setConfirmClear(false)}
              disabled={clearing}
              className="font-sans text-xs text-muted hover:text-ink px-3 py-1.5 rounded-xl transition-colors cursor-pointer"
            >
              Cancel
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setConfirmClear(true)}
            disabled={clearing || data.total === 0}
            className="font-sans text-sm font-semibold text-white bg-red hover:bg-red/90 disabled:opacity-50 disabled:cursor-not-allowed px-4 py-2 rounded-xl transition-colors cursor-pointer"
          >
            Clear Queue
          </button>
        )}
      </div>

      {actionError && (
        <div className="mb-4 p-3 bg-red/10 border border-red/20 text-red text-sm font-sans rounded-xl flex items-center justify-between">
          <span>{actionError}</span>
          <button
            type="button"
            onClick={() => setActionError(null)}
            className="text-red font-bold hover:opacity-80 ml-2"
          >
            &times;
          </button>
        </div>
      )}

      <SummaryCards
        cards={[
          { label: "Queue Size", value: data.total },
          {
            label: "Oldest Queued",
            value: fmtDate(data.oldest_queued),
          },
          {
            label: "By last check",
            value: data.items.length,
          },
        ]}
      />

      <div className="bg-panel/92 border border-line rounded-2xl shadow-[0_10px_30px_rgba(31,41,55,0.05)] backdrop-blur-sm overflow-hidden">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-line bg-line/20">
              {[
                "Item",
                "Brand",
                "Price",
                "Monitor",
                "Queued",
                "Last Check",
                "Status",
              ].map((h) => (
                <th
                  key={h}
                  className="text-left px-3.5 py-3 font-sans text-xs text-muted uppercase tracking-wider"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.items.length === 0 ? (
              <tr>
                <td
                  colSpan={7}
                  className="text-center text-muted font-sans py-16"
                >
                  Queue is empty.
                </td>
              </tr>
            ) : (
              data.items.map((item) => (
                <QueueItemRow key={item.id} item={item} />
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
