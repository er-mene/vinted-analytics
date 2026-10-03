import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { SellSpeedPoint } from "../../types";

interface Props {
  data: SellSpeedPoint[];
}

interface TooltipPayloadItem {
  payload: SellSpeedPoint;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: TooltipPayloadItem[];
}

function CustomTooltip({ active, payload }: CustomTooltipProps) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
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
        pointerEvents: "none",
      }}
    >
      <div style={{ fontWeight: 700, marginBottom: 4, color: "#1f2937" }}>{d.title}</div>
      <div style={{ color: "#6b7280" }}>
        Price: <strong>€{Number(d.price).toFixed(2)}</strong>
      </div>
      <div style={{ color: "#6b7280" }}>
        Time to sell: <strong>{Number(d.hours_to_sell).toFixed(1)}h</strong>
      </div>
      {d.url && (
        <div style={{ marginTop: 6, fontSize: 11, color: "#0f766e", fontWeight: 600 }}>
          Click dot to open listing &rarr;
        </div>
      )}
    </div>
  );
}

export default function SellSpeedChart({ data }: Props) {
  const handleClick = (entry: unknown) => {
    const item = entry as { url?: string; payload?: { url?: string } } | null;
    const url = item?.payload?.url || item?.url;
    if (url) {
      window.open(url, "_blank", "noopener,noreferrer");
    }
  };

  if (!data.length) {
    return (
      <div className="h-[280px] flex items-center justify-center text-muted font-sans text-sm">
        Not enough sold listings yet.
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={280}>
      <ScatterChart>
        <CartesianGrid strokeDasharray="3 3" stroke="#e5dccf" />
        <XAxis
          dataKey="hours_to_sell"
          name="Hours to sell"
          type="number"
          domain={['dataMin - 5', 'dataMax + 5']}
          tickCount={8}
          tickFormatter={(v: number) => v.toFixed(0) + "h"}
          tick={{ fontSize: 11, fill: "#6b7280" }}
          stroke="#cdbda9"
        />
        <YAxis
          dataKey="price"
          name="Price"
          type="number"
          domain={['dataMin - 5', 'dataMax + 5']}
          tickCount={8}
          tickFormatter={(v: number) => "€" + v}
          tick={{ fontSize: 11, fill: "#6b7280" }}
          stroke="#cdbda9"
        />
        <Tooltip content={<CustomTooltip />} cursor={{ fill: "rgba(229,220,207,0.3)" }} />
        <Scatter
          name="Sold"
          data={data}
          fill="#b45309"
          fillOpacity={0.6}
          cursor="pointer"
          className="cursor-pointer"
          onClick={handleClick}
        />
      </ScatterChart>
    </ResponsiveContainer>
  );
}
