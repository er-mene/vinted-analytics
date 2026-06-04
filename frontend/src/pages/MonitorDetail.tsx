import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { fetchMonitorAnalytics } from "../api";
import type { MonitorAnalytics } from "../types";
import PriceHistoryChart from "../components/charts/PriceHistoryChart";
import PriceLikesChart from "../components/charts/PriceLikesChart";
import SellSpeedChart from "../components/charts/SellSpeedChart";

export default function MonitorDetail() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<MonitorAnalytics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    let mounted = true;
    const load = async () => {
      try {
        const result = await fetchMonitorAnalytics(Number(id));
        if (mounted) setData(result);
      } catch {
        if (mounted) setError("Failed to load analytics");
      }
    };
    load();
    const interval = setInterval(load, 10000);
    return () => { mounted = false; clearInterval(interval); };
  }, [id]);

  if (error) {
    return (
      <div className="max-w-7xl mx-auto px-5 py-6 text-center text-red font-sans">
        {error}
      </div>
    );
  }

  if (!data) {
    return (
      <div className="max-w-7xl mx-auto px-5 py-6 text-center text-muted font-sans">
        Loading…
      </div>
    );
  }

  const s = data.summary;
  const avgPrice = s.avg_price !== null ? "€" + s.avg_price.toFixed(2) : "—";
  const avgLikes = s.avg_likes !== null ? s.avg_likes.toFixed(1) : "—";
  const rPL = data.correlations.price_likes !== null ? data.correlations.price_likes.toFixed(4) : "—";
  const rST = data.correlations.price_sell_time !== null ? data.correlations.price_sell_time.toFixed(4) : "—";

  return (
    <div className="max-w-7xl mx-auto px-5 py-6">
      {/* Header */}
      <div className="flex items-center gap-4 mb-6">
        <Link
          to="/"
          className="text-accent-2 font-sans text-sm hover:underline"
        >
          &larr; Dashboard
        </Link>
        <h1 className="text-2xl font-bold font-serif">{s.name}</h1>
        <Link
          to={`/monitor/${id}/listings`}
          className="ml-auto text-accent-2 font-sans text-sm hover:underline"
        >
          Browse Listings &rarr;
        </Link>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-[repeat(auto-fit,minmax(160px,1fr))] gap-3 mb-6">
        {[
          ["Total listings", s.total_listings],
          ["Active", s.active_listings],
          ["Sold", s.sold_listings],
          ["Avg price", avgPrice],
          ["Avg likes", avgLikes],
          ["Price/likes r", rPL],
          ["Price/sell-time r", rST],
        ].map(([label, value]) => (
          <div
            key={String(label)}
            className="bg-panel/92 border border-line rounded-2xl shadow-[0_10px_30px_rgba(31,41,55,0.05)] backdrop-blur-sm px-4 py-3"
          >
            <div className="font-sans text-xs text-muted uppercase tracking-wider">
              {label}
            </div>
            <div className="mt-1 text-xl font-bold">{value}</div>
          </div>
        ))}
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="bg-panel/92 border border-line rounded-2xl shadow-[0_10px_30px_rgba(31,41,55,0.05)] backdrop-blur-sm p-4 lg:col-span-2">
          <h2 className="font-serif text-base font-bold mb-1">Price Distribution Over Time</h2>
          <p className="font-sans text-xs text-muted mb-3">Daily average price, with min/max range.</p>
          <PriceHistoryChart data={data.price_history} />
        </div>

        <div className="bg-panel/92 border border-line rounded-2xl shadow-[0_10px_30px_rgba(31,41,55,0.05)] backdrop-blur-sm p-4">
          <h2 className="font-serif text-base font-bold mb-1">Price / Likes Correlation</h2>
          <p className="font-sans text-xs text-muted mb-3">Each point is a listing. Teal = active, amber = sold.</p>
          <PriceLikesChart data={data.price_likes} />
        </div>

        <div className="bg-panel/92 border border-line rounded-2xl shadow-[0_10px_30px_rgba(31,41,55,0.05)] backdrop-blur-sm p-4">
          <h2 className="font-serif text-base font-bold mb-1">Price / Time To Sell</h2>
          <p className="font-sans text-xs text-muted mb-3">Sold items only. Rightward means longer to sell.</p>
          <SellSpeedChart data={data.sell_speed} />
        </div>
      </div>
    </div>
  );
}
