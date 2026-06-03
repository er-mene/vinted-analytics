import { useCallback } from "react";
import { fetchQueue } from "../api";
import { usePolling } from "../hooks/usePolling";
import SummaryCards from "../components/SummaryCards";
import QueueItemRow from "../components/QueueItemRow";

export default function Queue() {
  const fetcher = useCallback(() => fetchQueue(), []);
  const { data, error, isLoading } = usePolling(fetcher, 2000);

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
      <SummaryCards
        cards={[
          { label: "Queue Size", value: data.total },
          {
            label: "Oldest Queued",
            value: data.oldest_queued
              ? data.oldest_queued.slice(0, 10)
              : "—",
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
