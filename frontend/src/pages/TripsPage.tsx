import { clsx } from "clsx";
import { AlertTriangle, ChevronLeft, ChevronRight, MapPin, Plus } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useAdd } from "@/components/AddSheet";
import { EventIcon } from "@/components/trips/EventIcon";
import { NewTripDialog } from "@/components/trips/NewTripDialog";
import { Button, EmptyState, LoadError, PageLoader } from "@/components/ui";
import { daysUntil, fmtMonth, fmtRange } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { useTrips } from "@/lib/queries";
import type { Trip } from "@/lib/types";

const ORDER: Record<string, number> = { current: 0, upcoming: 1, planning: 1, past: 2, cancelled: 3 };

/** Trips: one card at a time, swipe or tap through them. Nothing here scrolls the page. */
export default function TripsPage() {
  const trips = useTrips();
  const [open, setOpen] = useState(false);
  const [index, setIndex] = useState(0);
  const rail = useRef<HTMLDivElement>(null);
  const { openAdd } = useAdd();
  const { t, tp } = useT();
  const list = useMemo(() => [...(trips.data ?? [])].sort((a, b) => (ORDER[a.stats.phase ?? "planning"] ?? 1) - (ORDER[b.stats.phase ?? "planning"] ?? 1)
    || (a.start_date ?? "").localeCompare(b.start_date ?? "")), [trips.data]);

  const go = (i: number) => {
    const el = rail.current;
    if (!el) return;
    const n = Math.max(0, Math.min(list.length, i)); // list.length is the "new trip" card
    el.scrollTo({ left: n * el.clientWidth, behavior: "smooth" });
    setIndex(n);
  };
  useEffect(() => {
    const el = rail.current;
    if (!el) return;
    const onScroll = () => setIndex(Math.round(el.scrollLeft / Math.max(1, el.clientWidth)));
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [list.length]);

  if (trips.isLoading) return <PageLoader />;
  if (trips.isError && !trips.data) return <LoadError title={t("load.trips")} onRetry={() => trips.refetch()} retrying={trips.isFetching} />;

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-3 pb-8">
      <div className="flex shrink-0 items-end justify-between gap-3">
        <div>
          <p className="kicker">{tp("trips.count", list.length)}</p>
          <h1 className="display text-[28px] leading-[1.05] tracking-[-0.02em] sm:text-[34px]">{t("trips.title")}</h1>
        </div>
      </div>
      {list.length === 0 ? (
        <EmptyState icon={<MapPin className="h-8 w-8" />} title={t("trips.emptyTitle")} body={t("trips.emptyBody")}
          action={<div className="flex flex-wrap justify-center gap-2"><Button onClick={openAdd}>{t("trips.addBooking")}</Button><Button variant="secondary" onClick={() => setOpen(true)}>{t("trips.new")}</Button></div>} />
      ) : (
        <>
          <div ref={rail} className="-mx-4 flex h-[min(58dvh,400px)] snap-x snap-mandatory overflow-x-auto overflow-y-hidden [scrollbar-width:none] sm:mx-0 sm:rounded-3xl" role="list" aria-label={t("trips.title")}>
            {list.map((x) => (
              <div key={x.id} role="listitem" className="flex w-full shrink-0 snap-center px-4 pb-1 sm:px-0"><TripCard trip={x} /></div>
            ))}
            <div role="listitem" className="flex w-full shrink-0 snap-center px-4 pb-1 sm:px-0">
              <button onClick={() => setOpen(true)} className="flex w-full flex-col items-center justify-center gap-2 rounded-[28px] border-2 border-dashed border-sand-300 text-ink-500 transition active:scale-[0.99] hover:border-clay-500/50 hover:text-clay-600">
                <Plus className="h-7 w-7" /><span className="text-[15px] font-medium">{t("trips.new")}</span>
              </button>
            </div>
          </div>
          <div className="flex shrink-0 items-center justify-center gap-3 pb-1">
            <button onClick={() => go(index - 1)} disabled={index === 0} aria-label={t("common.back")} className="flex h-9 w-9 items-center justify-center rounded-full text-ink-500 hover:bg-sand-100 disabled:opacity-25"><ChevronLeft className="h-5 w-5" /></button>
            <div className="flex gap-1.5" aria-hidden>{[...list, null].map((_, i) => <span key={i} className={clsx("h-1.5 rounded-full transition-all", i === index ? "w-5 bg-clay-500" : "w-1.5 bg-sand-300")} />)}</div>
            <button onClick={() => go(index + 1)} disabled={index >= list.length} aria-label={t("common.next")} className="flex h-9 w-9 items-center justify-center rounded-full text-ink-500 hover:bg-sand-100 disabled:opacity-25"><ChevronRight className="h-5 w-5" /></button>
          </div>
        </>
      )}
      <NewTripDialog open={open} onOpenChange={setOpen} />
    </div>
  );
}

function TripCard({ trip }: { trip: Trip }) {
  const { t, tp } = useT();
  const d = daysUntil(trip.start_date);
  const types = Object.keys(trip.stats.reservation_types ?? {});
  const past = trip.stats.phase === "past";
  const stub = trip.stats.phase === "current" ? { big: t("trips.stubNow"), small: t("trips.stubTravelling") }
    : d !== null && d >= 0 ? { big: d === 0 ? t("fmt.today") : String(d), small: d === 0 ? "" : tp("trips.daysLeft", d) }
      : { big: trip.start_date ? fmtMonth(trip.start_date) : "—", small: trip.start_date?.slice(0, 4) ?? "" };
  return (
    <Link to={`/trips/${trip.id}`} className={clsx("group flex w-full flex-col overflow-hidden rounded-[28px] border border-sand-200/80 bg-white shadow-[var(--shadow-float)] transition active:scale-[0.99]", past && "opacity-75")}>
      <div className="relative flex items-center justify-between bg-apricot-soft/70 px-6 py-5">
        <div>
          <span className="display block text-[56px] leading-none text-clay-600">{stub.big}</span>
          {stub.small && <span className="mt-1 block text-[13px] font-medium text-ink-500">{stub.small}</span>}
        </div>
        <div className="flex -space-x-1.5">{types.slice(0, 5).map((x) => <EventIcon key={x} type={x} size="sm" className="ring-2 ring-white" />)}</div>
      </div>
      <div className="perforated" />
      <div className="flex min-h-0 flex-1 flex-col p-6">
        <h2 className="display text-[28px] leading-[1.08] tracking-[-0.01em] text-ink-900">{trip.name}</h2>
        <p className="mt-1.5 text-[14.5px] text-ink-500">{fmtRange(trip.start_date, trip.end_date)}</p>
        <p className="mt-4 flex items-center gap-1.5 text-[14.5px] text-ink-700"><MapPin className="h-4 w-4 shrink-0 text-clay-500" /><span className="truncate">{trip.destinations.map((x) => x.name).join(" → ") || trip.primary_destination || t("trips.noDestination")}</span></p>
        <div className="mt-auto flex items-center justify-between pt-4 text-[13px] text-ink-400">
          <span>{tp("trips.bookings", trip.stats.reservations ?? 0)}</span>
          {(trip.stats.conflict_count ?? 0) > 0 && <span className="flex items-center gap-1.5 font-medium text-amber-ink"><AlertTriangle className="h-4 w-4" /> {tp("trips.toCheck", trip.stats.conflict_count ?? 0)}</span>}
        </div>
      </div>
    </Link>
  );
}
