/**
 * afisarea datei si a orei. API-ul trimite fiecare ora deja in fusul ei (de ex.
 * "2026-11-12T11:40:00+01:00"), deci formatam direct ora de pe ceas, fara conversie
 * in fusul browserului — o intrare la muzeu la 09:30 in Roma trebuie sa arate 09:30 si pentru cineva din Londra.
 * Numele zilelor si lunilor vin din Intl in limba activa, aplicat pe date UTC construite din aceste parti.
 */
import { getLocale, intlLocale, translate, translatePlural, type Locale } from "./i18n";

type Parts = { y: number; m: number; d: number; hh: number; mm: number };

export function parts(local: string | null | undefined): Parts | null {
  if (!local) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/.exec(local);
  if (!m) return null;
  return { y: +m[1], m: +m[2], d: +m[3], hh: +(m[4] ?? 0), mm: +(m[5] ?? 0) };
}

const utc = (p: Parts) => new Date(Date.UTC(p.y, p.m - 1, p.d));
const fmt = (locale: Locale, opts: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat(intlLocale(locale), { timeZone: "UTC", ...opts });
const capitalise = (s: string) => s.charAt(0).toLocaleUpperCase() + s.slice(1);

export function fmtTime(local: string | null | undefined): string {
  const p = parts(local);
  return p ? `${String(p.hh).padStart(2, "0")}:${String(p.mm).padStart(2, "0")}` : "";
}

export function fmtDate(local: string | null | undefined, opts: { weekday?: boolean; year?: boolean } = {}, locale: Locale = getLocale()): string {
  const p = parts(local);
  if (!p) return "";
  return fmt(locale, { weekday: opts.weekday === false ? undefined : "short", day: "numeric", month: "short", year: opts.year ? "numeric" : undefined }).format(utc(p));
}

export function fmtDayHeading(dayKey: string, locale: Locale = getLocale()): { weekday: string; date: string } {
  const d = utc(parts(dayKey)!);
  return { weekday: capitalise(fmt(locale, { weekday: "long" }).format(d)), date: fmt(locale, { day: "numeric", month: "short" }).format(d) };
}

export function fmtDateTime(local: string | null | undefined, locale: Locale = getLocale()): string {
  if (!local) return "";
  return `${fmtDate(local, {}, locale)}, ${fmtTime(local)}`;
}

/** azi in cuvinte, de ex. "Saturday 31 October" / "Sâmbătă, 31 octombrie" */
export function fmtToday(locale: Locale = getLocale()): string {
  return capitalise(new Intl.DateTimeFormat(intlLocale(locale), { weekday: "long", day: "numeric", month: "long" }).format(new Date()));
}

export function dayKey(local: string | null | undefined): string {
  return local ? local.slice(0, 10) : "";
}

export function fmtRange(start: string | null, end: string | null, locale: Locale = getLocale()): string {
  if (!start) return translate("fmt.noDates", undefined, locale);
  const a = parts(start)!;
  const f = fmt(locale, { day: "numeric", month: "short", year: "numeric" });
  if (!end) return f.format(utc(a));
  return f.formatRange(utc(a), utc(parts(end)!));
}

/** numele scurt al lunii, de ex. "Nov" / "nov." */
export function fmtMonth(local: string, locale: Locale = getLocale()): string {
  return fmt(locale, { month: "short" }).format(utc(parts(local)!));
}

export function tzCity(tz: string | null | undefined): string {
  if (!tz) return "";
  return tz.split("/").pop()!.replace(/_/g, " ");
}

/** eticheta decalajului dintr-un ISO cu decalaj, de ex. "+01:00" → "UTC+1" */
export function offsetLabel(local: string | null | undefined): string {
  if (!local) return "";
  const m = /([+-])(\d{2}):(\d{2})$/.exec(local);
  if (!m) return local.endsWith("Z") ? "UTC" : "";
  const h = +m[2];
  const mins = +m[3];
  if (!h && !mins) return "UTC";
  return `UTC${m[1]}${h}${mins ? `:${m[3]}` : ""}`;
}

export function money(amount: number | null | undefined, currency: string | null | undefined, locale: Locale = getLocale()): string {
  if (amount === null || amount === undefined) return "";
  try {
    return new Intl.NumberFormat(intlLocale(locale), { style: "currency", currency: currency || "EUR", maximumFractionDigits: amount % 1 ? 2 : 0 }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${currency ?? ""}`;
  }
}

export function num(n: number, locale: Locale = getLocale()): string {
  return new Intl.NumberFormat(intlLocale(locale)).format(n);
}

export function duration(minutes: number | null | undefined): string {
  if (!minutes) return "";
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return h ? `${h} h${m ? ` ${m} min` : ""}` : `${m} min`;
}

export function relativeTime(iso: string, locale: Locale = getLocale()): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return translate("fmt.justNow", undefined, locale);
  const rtf = new Intl.RelativeTimeFormat(intlLocale(locale), { numeric: "auto" });
  if (diff < 3600) return rtf.format(-Math.floor(diff / 60), "minute");
  if (diff < 86400) return rtf.format(-Math.floor(diff / 3600), "hour");
  return rtf.format(-Math.floor(diff / 86400), "day");
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

/** "Azi", "Maine", "In 12 zile" in limba activa */
export function whenLabel(days: number | null, locale: Locale = getLocale()): string {
  if (days === null) return translate("fmt.soon", undefined, locale);
  if (days === 0) return translate("fmt.today", undefined, locale);
  if (days === 1) return translate("fmt.tomorrow", undefined, locale);
  return translatePlural("fmt.inDays", days, undefined, locale);
}

/** fiecare data de la `start` la `end` (inclusiv, YYYY-MM-DD). O singura data cand nu exista final; maxim 60 de zile */
export function eachDay(start: string | null, end: string | null): string[] {
  if (!start) return [];
  const out: string[] = [];
  const last = end ?? start;
  for (let d = new Date(`${start}T12:00:00Z`); d.toISOString().slice(0, 10) <= last && out.length < 60; d.setUTCDate(d.getUTCDate() + 1)) out.push(d.toISOString().slice(0, 10));
  return out;
}
