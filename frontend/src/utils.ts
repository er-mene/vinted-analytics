function parseUtcDate(iso: string): Date | null {
  let s = iso.trim().replace(" ", "T");
  if (!s.endsWith("Z") && !s.includes("+") && !s.includes("-", 10)) {
    s += "Z";
  }
  const d = new Date(s);
  return isNaN(d.getTime()) ? null : d;
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  if (iso.length === 10 && /^\d{4}-\d{2}-\d{2}$/.test(iso)) {
    const [y, m, day] = iso.split("-");
    return `${day}-${m}-${y}`;
  }
  const d = parseUtcDate(iso);
  if (!d) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  const day = pad(d.getDate());
  const m = pad(d.getMonth() + 1);
  const y = d.getFullYear();
  return `${day}-${m}-${y}`;
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  if (iso.length === 10 && /^\d{4}-\d{2}-\d{2}$/.test(iso)) {
    return fmtDate(iso);
  }
  const d = parseUtcDate(iso);
  if (!d) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  const day = pad(d.getDate());
  const m = pad(d.getMonth() + 1);
  const y = d.getFullYear();
  const h = pad(d.getHours());
  const min = pad(d.getMinutes());
  const sec = pad(d.getSeconds());
  return `${day}-${m}-${y} ${h}:${min}:${sec}`;
}
