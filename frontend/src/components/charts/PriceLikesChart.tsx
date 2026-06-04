import { useMemo } from "react";
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import type { ListingPoint } from "../../types";
import { fmtDate } from "../../utils";

interface Props {
  data: ListingPoint[];
}

function jitter(val: number | null, id: number, spread: number): number {
  if (val === null || val === 0) return 0;
  const seed = ((id * 2654435761) % 1000) / 1000;
  return val + (seed - 0.5) * spread * 2;
}

function CustomTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  const listed = fmtDate(d.listed_at);
  return (
    <div
      style={{
        background: "#fffaf3",
        border: "1px solid #e5dccf",
        borderRadius: 12,
        padding: "8px 12px",
        fontSize: 13,
        fontFamily: '"Helvetica Neue", Arial, sans-serif',
        maxWidth: 260,
      }}
    >
      <div style={{ fontWeight: 700, marginBottom: 4, color: "#1f2937" }}>{d.originalTitle || d.title}</div>
      <div style={{ color: "#6b7280" }}>
        Price: <strong>€{Number(d.originalPrice ?? d.price).toFixed(2)}</strong>
      </div>
      <div style={{ color: "#6b7280" }}>
        Likes: <strong>{d.originalLikes ?? d.likes}</strong>
      </div>
      <div style={{ color: "#6b7280" }}>
        Listed: <strong>{listed}</strong>
      </div>
    </div>
  );
}

export default function PriceLikesChart({ data }: Props) {
  if (!data.length) {
    return (
      <div className="h-[280px] flex items-center justify-center text-muted font-sans text-sm">
        Not enough data yet.
      </div>
    );
  }

  const jittered = useMemo(
    () =>
      data.map((d) => {
        const jp = jitter(d.price, d.id, 0.5);
        const jl = jitter(d.likes, d.id + 1, 0.5);
        return {
          ...d,
          price: jp,
          likes: jl,
          originalPrice: d.price,
          originalLikes: d.likes,
          originalTitle: d.title,
        };
      }),
    [data],
  );

  const active = jittered.filter((d: any) => d.is_active);
  const sold = jittered.filter((d: any) => !d.is_active);

  return (
    <ResponsiveContainer width="100%" height={280}>
      <ScatterChart>
        <CartesianGrid strokeDasharray="3 3" stroke="#e5dccf" />
        <XAxis
          dataKey="price"
          name="Price"
          type="number"
          domain={['dataMin - 5', 'dataMax + 5']}
          tickCount={8}
          tickFormatter={(v: number) => "€" + Math.round(v)}
          tick={{ fontSize: 11, fill: "#6b7280" }}
          stroke="#cdbda9"
        />
        <YAxis
          dataKey="likes"
          name="Likes"
          type="number"
          domain={['dataMin - 2', 'dataMax + 2']}
          tickCount={8}
          tickFormatter={(v: number) => String(Math.round(v))}
          tick={{ fontSize: 11, fill: "#6b7280" }}
          stroke="#cdbda9"
        />
        <Tooltip content={<CustomTooltip />} cursor={{ fill: "rgba(229,220,207,0.3)" }} />
        <Legend
          formatter={(value: string) => (
            <span style={{ color: "#6b7280", fontSize: 12 }}>{value}</span>
          )}
        />
        <Scatter
          name="Active"
          data={active}
          fill="#0f766e"
          fillOpacity={0.5}
        />
        <Scatter
          name="Sold"
          data={sold}
          fill="#b45309"
          fillOpacity={0.5}
        />
      </ScatterChart>
    </ResponsiveContainer>
  );
}
