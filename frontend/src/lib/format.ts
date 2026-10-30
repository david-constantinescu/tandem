/**
 * Date/time display. The API sends each event time already in its own timezone (e.g.
 * "2026-11-12T11:40:00+01:00"), so we format the wall-clock part directly instead of converting
 * to the browser's zone — a 09:30 museum entry in Rome must read 09:30 for a user in London.
 */

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const LONG_DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

type Parts = { y: number; m: number; d: number; hh: number; mm: number };

export function parts(local: string | null | undefined): Parts | null {
  if (!local) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/.exec(local);
  if (!m) return null;
  return { y: +m[1], m: +m[2], d: +m[3], hh: +(m[4] ?? 0), mm: +(m[5] ?? 0) };
}

function weekday(p: Parts) {
  return new Date(Date.UTC(p.y, p.m - 1, p.d)).getUTCDay();
}

export function fmtTime(local: string | null | undefined): string {
  const p = parts(local);
  return p ? `${String(p.hh).padStart(2, "0")}:${String(p.mm).padStart(2, "0")}` : "";
}

export function fmtDate(local: string | null | undefined, opts: { weekday?: boolean; year?: boolean } = {}): string {
  const p = parts(local);
  if (!p) return "";
  const wd = opts.weekday === false ? "" : `${DAYS[weekday(p)]} `;
  return `${wd}${p.d} ${MONTHS[p.m - 1]}${opts.year ? ` ${p.y}` : ""}`;
}

export function fmtDayHeading(dayKey: string): { weekday: string; date: string } {
  const p = parts(dayKey)!;
  return { weekday: LONG_DAYS[weekday(p)], date: `${p.d} ${MONTHS[p.m - 1]}` };
}

export function fmtDateTime(local: string | null | undefined): string {
  if (!local) return "";
  return `${fmtDate(local)}, ${fmtTime(local)}`;
}

export function dayKey(local: string | null | undefined): string {
  return local ? local.slice(0, 10) : "";
}

export function fmtRange(start: string | null, end: string | null): string {
  if (!start) return "Dates not set";
  const a = parts(start)!;
  if (!end) return fmtDate(start, { year: true });
  const b = parts(end)!;
  if (a.y === b.y && a.m === b.m) return `${a.d}–${b.d} ${MONTHS[a.m - 1]} ${a.y}`;
  if (a.y === b.y) return `${a.d} ${MONTHS[a.m - 1]} – ${b.d} ${MONTHS[b.m - 1]} ${a.y}`;
  return `${fmtDate(start, { weekday: false, year: true })} – ${fmtDate(end, { weekday: false, year: true })}`;
}

export function tzCity(tz: string | null | undefined): string {
  if (!tz) return "";
  return tz.split("/").pop()!.replace(/_/g, " ");
}

/** Offset label from an ISO string with offset, e.g. "+01:00" → "UTC+1". */
export function offsetLabel(local: string | null | undefined): string {
  if (!local) return "";
  const m = /([+-])(\d{2}):(\d{2})$/.exec(local);
  if (!m) return local.endsWith("Z") ? "UTC" : "";
  const h = +m[2];
  const mins = +m[3];
  if (!h && !mins) return "UTC";
  return `UTC${m[1]}${h}${mins ? `:${m[3]}` : ""}`;
}

export function money(amount: number | null | undefined, currency: string | null | undefined): string {
  if (amount === null || amount === undefined) return "";
  try {
    return new Intl.NumberFormat("en-GB", { style: "currency", currency: currency || "EUR", maximumFractionDigits: amount % 1 ? 2 : 0 }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${currency ?? ""}`;
  }
}

export function duration(minutes: number | null | undefined): string {
  if (!minutes) return "";
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return h ? `${h} h${m ? ` ${m} min` : ""}` : `${m} min`;
}

export function relativeTime(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`;
  return `${Math.floor(diff / 86400)} d ago`;
}

export function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function daysUntil(dateStr: string | null): number | null {
  if (!dateStr) return null;
  const p = parts(dateStr)!;
  const target = Date.UTC(p.y, p.m - 1, p.d);
  const now = new Date();
  const today = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((target - today) / 86400000);
}

export const label = (s: string) => s.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
