import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { fetchMonitorListings } from "../api";
import type { MonitorListing } from "../types";
import { fmtDate } from "../utils";

type SortField = "likes" | "price" | "listed_at";

const SORT_LABELS: Record<SortField, string> = {
  likes: "Likes",
  price: "Price",
  listed_at: "Listed",
};

export default function MonitorListings() {
  const { id } = useParams<{ id: string }>();
  const [listings, setListings] = useState<MonitorListing[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<SortField>("likes");
  const [order, setOrder] = useState<"asc" | "desc">("desc");

  useEffect(() => {
    if (!id) return;
    let mounted = true;
    fetchMonitorListings(Number(id), sortBy, order)
      .then((data) => { if (mounted) setListings(data); })
      .catch(() => { if (mounted) setError("Failed to load listings"); });
    return () => { mounted = false; };
  }, [id, sortBy, order]);

  function toggleSort(field: SortField) {
    if (sortBy === field) {
      setOrder((o) => (o === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(field);
      setOrder("desc");
    }
  }

  function SortIcon(field: SortField) {
    if (sortBy !== field) return null;
    return <span className="ml-1">{order === "asc" ? "\u25B2" : "\u25BC"}</span>;
  }

  if (error) {
    return (
      <div className="max-w-7xl mx-auto px-5 py-6 text-center text-red font-sans">
        {error}
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-5 py-6">
      <div className="flex items-center gap-4 mb-6">
        <Link
          to={`/monitor/${id}`}
          className="text-accent-2 font-sans text-sm hover:underline"
        >
          &larr; Monitor Details
        </Link>
        <h1 className="text-2xl font-bold font-serif">Listings</h1>
        <span className="text-muted font-sans text-sm ml-auto">
          {listings.length} items
        </span>
      </div>

      <div className="bg-panel/92 border border-line rounded-2xl shadow-[0_10px_30px_rgba(31,41,55,0.05)] overflow-x-auto">
        <table className="w-full text-sm font-sans">
          <thead>
            <tr className="border-b border-line text-muted uppercase tracking-wider text-xs">
              <th className="text-left px-4 py-3 font-semibold">Title</th>
              <th className="text-left px-4 py-3 font-semibold">Brand</th>
              {(["likes", "price", "listed_at"] as SortField[]).map((field) => (
                <th
                  key={field}
                  onClick={() => toggleSort(field)}
                  className="text-right px-4 py-3 font-semibold cursor-pointer hover:text-ink select-none whitespace-nowrap"
                >
                  {SORT_LABELS[field]}
                  {SortIcon(field)}
                </th>
              ))}
              <th className="text-center px-4 py-3 font-semibold">Status</th>
            </tr>
          </thead>
          <tbody>
            {listings.length === 0 ? (
              <tr>
                <td colSpan={6} className="text-center py-10 text-muted">
                  No listings found.
                </td>
              </tr>
            ) : (
              listings.map((item) => (
                <tr key={item.id} className="border-b border-line/50 hover:bg-black/[0.02]">
                  <td className="px-4 py-3 max-w-xs truncate">
                    <a
                      href={item.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-accent-2 hover:underline"
                    >
                      {item.title}
                    </a>
                  </td>
                  <td className="px-4 py-3 text-muted">{item.brand || "\u2014"}</td>
                  <td className="px-4 py-3 text-right font-medium tabular-nums whitespace-nowrap">
                    {item.likes !== null ? item.likes : "\u2014"}
                  </td>
                  <td className="px-4 py-3 text-right font-medium tabular-nums whitespace-nowrap">
                    {item.price !== null ? `\u20AC${item.price.toFixed(2)}` : "\u2014"}
                  </td>
                  <td className="px-4 py-3 text-right text-muted tabular-nums whitespace-nowrap">
                    {item.listed_at ? fmtDate(item.listed_at) : "\u2014"}
                  </td>
                  <td className="px-4 py-3 text-center whitespace-nowrap">
                    <span
                      className={
                        "inline-block px-2 py-0.5 rounded-full text-xs font-medium " +
                        (item.is_active
                          ? "bg-teal-100 text-teal-800"
                          : "bg-amber-100 text-amber-800")
                      }
                    >
                      {item.is_active ? "Active" : "Sold"}
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
