export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = iso.slice(0, 10);
  const [y, m, day] = d.split("-");
  return `${day}-${m}-${y}`;
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = fmtDate(iso);
  const time = iso.length > 10 ? iso.slice(11, 19) : "";
  return time ? `${date} ${time}` : date;
}
