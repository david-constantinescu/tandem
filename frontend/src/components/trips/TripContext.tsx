/** context live pentru o calatorie: prognoza pe zile si stiri locale care pot strica planurile */
import { clsx } from "clsx";
import { AlertTriangle, Cloud, CloudDrizzle, CloudFog, CloudLightning, CloudRain, CloudSnow, ExternalLink, Megaphone, Sun, TrainFront } from "lucide-react";
import { fmtDate, relativeTime } from "@/lib/format";
import { useT, type Key } from "@/lib/i18n";
import { useTripContext } from "@/lib/queries";
import type { DayWeather, NewsItem } from "@/lib/types";

const ICONS = { clear: Sun, cloudy: Cloud, fog: CloudFog, drizzle: CloudDrizzle, rain: CloudRain, snow: CloudSnow, storm: CloudLightning, unknown: Cloud };

export function WeatherIcon({ condition, className }: { condition: DayWeather["condition"]; className?: string }) {
  const Icon = ICONS[condition] ?? Cloud;
  return <Icon className={className} aria-hidden />;
}

/** vremea pe scurt pentru titlul unei zile: icoana, temperaturi, sansa de ploaie */
export function WeatherChip({ day, withDay }: { day: DayWeather; withDay?: boolean }) {
  const { t } = useT();
  return (
    <span title={t(`weather.${day.condition}` as Key)}
      className={clsx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[12px] font-medium", day.outdoor_ok ? "bg-sand-100 text-ink-600" : "bg-lagoon-50 text-lagoon-700")}>
      {withDay && <span className="opacity-75">{fmtDate(day.date, { weekday: true }).split(/[ ,]/)[0]}</span>}
      <WeatherIcon condition={day.condition} className="h-3.5 w-3.5" />
      {day.temp_max !== null && `${Math.round(day.temp_max)}°`}
      {day.precip_probability !== null && day.precip_probability >= 30 && <span className="opacity-75">· {day.precip_probability}%</span>}
    </span>
  );
}

const KIND_ICON = { strike: TrainFront, protest: Megaphone, weather: AlertTriangle, closure: AlertTriangle, news: Megaphone };

export function NewsList({ items, limit = 4 }: { items: NewsItem[]; limit?: number }) {
  const { t } = useT();
  return (
    <ul className="space-y-2">
      {items.slice(0, limit).map((n) => {
        const Icon = KIND_ICON[n.kind] ?? Megaphone;
        return (
          <li key={n.url}>
            <a href={n.url} target="_blank" rel="noopener noreferrer nofollow"
              className={clsx("flex gap-2.5 rounded-xl border px-3 py-2.5 transition hover:shadow-[var(--shadow-card)]",
                n.mentions_dates.length ? "border-amber-soft bg-amber-soft/60" : "border-sand-200 bg-white")}>
              <Icon className={clsx("mt-0.5 h-4 w-4 shrink-0", n.kind === "strike" || n.mentions_dates.length ? "text-amber-ink" : "text-ink-400")} />
              <span className="min-w-0 flex-1">
                <span className="block text-[11.5px] font-semibold uppercase tracking-wide text-ink-400">
                  {t(`news.${n.kind}` as Key)}{n.mentions_dates.length ? ` · ${t("news.onYourDates", { dates: n.mentions_dates.map((d) => fmtDate(d, { weekday: false })).join(", ") })}` : ""}
                </span>
                <span className="mt-0.5 line-clamp-2 block text-[13.5px] leading-snug text-ink-800">{n.title}</span>
                <span className="mt-1 flex items-center gap-1 text-[11.5px] text-ink-400">{n.source}{n.published ? ` · ${relativeTime(n.published)}` : ""}<ExternalLink className="h-3 w-3" /></span>
              </span>
            </a>
          </li>
        );
      })}
    </ul>
  );
}

export function TripContextCard({ tripId }: { tripId: string }) {
  const { t } = useT();
  const ctx = useTripContext(tripId);
  if (!ctx.data) return null;
  const { weather, news } = ctx.data;
  const wet = weather.days.filter((d) => !d.outdoor_ok);
  return (
    <div className="card space-y-5 p-4">
      <section>
        <p className="eyebrow mb-3">{t("context.weather", { place: weather.place ?? "" })}</p>
        {weather.available ? (
          <>
            <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1 [scrollbar-width:none]">
              {weather.days.map((d) => (
                <div key={d.date} className={clsx("flex w-[64px] shrink-0 flex-col items-center rounded-xl px-1 py-2 text-center", d.outdoor_ok ? "bg-sand-50" : "bg-lagoon-50")}>
                  <span className="text-[11.5px] font-medium text-ink-500">{fmtDate(d.date, { weekday: true }).split(/[ ,]/)[0]}</span>
                  <WeatherIcon condition={d.condition} className={clsx("my-1 h-5 w-5", d.outdoor_ok ? "text-clay-500" : "text-lagoon-600")} />
                  <span className="text-[13px] font-semibold tabular-nums text-ink-900">{d.temp_max !== null ? Math.round(d.temp_max) : "–"}°</span>
                  <span className="text-[11px] tabular-nums text-ink-400">{d.precip_probability ?? 0}%</span>
                </div>
              ))}
            </div>
            <p className="mt-2 text-[12.5px] text-ink-500">
              {wet.length ? t("context.wetDays", { days: wet.map((d) => fmtDate(d.date, { weekday: true })).join(", ") }) : t("context.dryDays")}
            </p>
          </>
        ) : (
          <p className="text-[13px] text-ink-500">{weather.reason === "too_far_ahead" && weather.forecast_from ? t("context.tooFar", { date: fmtDate(weather.forecast_from) }) : t("context.noWeather")}</p>
        )}
      </section>
      <section>
        <p className="eyebrow mb-3">{t("context.news")}</p>
        {news.available && news.items.length ? <NewsList items={news.items} /> : (
          <p className="text-[13px] text-ink-500">{news.available ? t("context.noNews") : t("context.newsUnavailable")}</p>
        )}
        {news.available && <p className="mt-2 text-[11.5px] text-ink-400">{t("context.newsSource", { source: news.source ?? "" })}</p>}
      </section>
    </div>
  );
}
