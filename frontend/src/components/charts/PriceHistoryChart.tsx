import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { PriceHistoryPoint } from "../../types";

interface Props {
  data: PriceHistoryPoint[];
}

export default function PriceHistoryChart({ data }: Props) {
  if (!data.length) {
    return (
      <div className="h-[280px] flex items-center justify-center text-muted font-sans text-sm">
        Not enough dated listings yet.
      </div>
    );
  }

  const sorted = [...data].sort((a, b) => a.day.localeCompare(b.day));

  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart data={sorted}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e5dccf" />
        <XAxis
          dataKey="day"
          tick={{ fontSize: 11, fill: "#6b7280" }}
          tickFormatter={(v: string) => v.slice(5)}
          stroke="#cdbda9"
        />
        <YAxis
          type="number"
          domain={[0, 'auto']}
          tickFormatter={(v: number) => "€" + v}
          tick={{ fontSize: 11, fill: "#6b7280" }}
          stroke="#cdbda9"
        />
        <Tooltip
          contentStyle={{
            background: "#fffaf3",
            border: "1px solid #e5dccf",
            borderRadius: 12,
            fontSize: 13,
            fontFamily: '"Helvetica Neue", Arial, sans-serif',
          }}
          formatter={(value: any) => "€" + Number(value).toFixed(2)}
          labelFormatter={(label: any) => "Date: " + label}
        />

        {/* Price range band */}
        <Area
          type="monotone"
          dataKey="max_price"
          stroke="none"
          fill="#b45309"
          fillOpacity={0.08}
        />
        <Area
          type="monotone"
          dataKey="min_price"
          stroke="none"
          fill="#fffaf3"
          fillOpacity={1}
        />

        {/* Average price line */}
        <Area
          type="monotone"
          dataKey="avg_price"
          stroke="#b45309"
          strokeWidth={2.5}
          fill="none"
          dot={false}
          activeDot={{ r: 5, fill: "#b45309", stroke: "#fff" }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
