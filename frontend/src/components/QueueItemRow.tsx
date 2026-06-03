import type { QueueItem } from "../types";

const statusInfo: Record<
  string,
  { label: string; className: string }
> = {
  active: { label: "Active", className: "bg-green/10 text-green" },
  sold: { label: "Sold", className: "bg-red/10 text-red" },
  removed: { label: "Removed", className: "bg-yellow/10 text-yellow" },
  unknown: { label: "Unknown", className: "bg-gray-100 text-muted" },
};

function getStatus(item: QueueItem) {
  if (item.is_active === 0 && item.sold_at) return statusInfo.sold;
  if (item.is_active === 0) return statusInfo.removed;
  if (item.is_active === 1) return statusInfo.active;
  return statusInfo.unknown;
}

function fmtTime(iso: string | null) {
  if (!iso) return "—";
  return iso.slice(0, 19).replace("T", " ");
}

export default function QueueItemRow({ item }: { item: QueueItem }) {
  const { label, className } = getStatus(item);

  const title = item.title || "(deleted)";
  const url = item.url || "#";
  const brand = item.brand || "—";
  const price = item.price !== null ? "€" + Number(item.price).toFixed(2) : "—";
  const mon = item.monitor_name || "—";
  const queued = fmtTime(item.queued_at);
  const lastCheck = fmtTime(item.last_check);

  return (
    <tr className="border-b border-line last:border-b-0 hover:bg-panel/60 transition-colors">
      <td className="px-3.5 py-2.5 text-sm">
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-ink no-underline hover:underline"
        >
          {title}
        </a>
      </td>
      <td className="px-3.5 py-2.5 text-sm text-muted">{brand}</td>
      <td className="px-3.5 py-2.5 text-sm font-medium">{price}</td>
      <td className="px-3.5 py-2.5 text-sm text-muted">{mon}</td>
      <td className="px-3.5 py-2.5 text-sm text-muted">{queued}</td>
      <td className="px-3.5 py-2.5 text-sm text-muted">{lastCheck}</td>
      <td className="px-3.5 py-2.5 text-sm">
        <span
          className={
            "inline-block px-2.5 py-0.5 rounded-full text-xs font-semibold font-sans " +
            className
          }
        >
          {label}
        </span>
      </td>
    </tr>
  );
}
