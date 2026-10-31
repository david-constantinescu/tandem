import { clsx } from "clsx";
import { AlertTriangle, MapPin, Plus } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Stagger, StaggerItem } from "@/components/motion";
import { EventIcon } from "@/components/trips/EventIcon";
import { NewTripDialog } from "@/components/trips/NewTripDialog";
import { Button, EmptyState, LoadError, PageHeader, PageLoader } from "@/components/ui";
import { useAdd } from "@/components/AddSheet";
import { daysUntil, fmtMonth, fmtRange } from "@/lib/format";
import { useT, type Key } from "@/lib/i18n";
import { useTrips } from "@/lib/queries";
import type { Trip } from "@/lib/types";

const groups: { key: string; label: Key; phases: string[] }[] = [
  { key: "current", label: "trips.now", phases: ["current"] },
  { key: "upcoming", label: "trips.upcoming", phases: ["upcoming", "planning"] },
  { key: "past", label: "trips.past", phases: ["past", "cancelled"] },
];

export default function TripsPage() {
  const trips = useTrips();
  const [open, setOpen] = useState(false);
  const { openAdd } = useAdd();
  const { t } = useT();
  if (trips.isLoading) return <PageLoader />;
  if (trips.isError && !trips.data) return <LoadError title={t("load.trips")} onRetry={() => trips.refetch()} retrying={trips.isFetching} />;
  const list = trips.data ?? [];
  return (
    <div>
      <PageHeader title={t("trips.title")} subtitle={t("trips.subtitle")}
        actions={<Button variant="secondary" onClick={() => setOpen(true)} icon={<Plus className="h-4 w-4" />}>{t("trips.new")}</Button>} />
      {list.length === 0 ? (
        <EmptyState icon={<MapPin className="h-8 w-8" />} title={t("trips.emptyTitle")} body={t("trips.emptyBody")}
          action={<div className="flex flex-wrap justify-center gap-2"><Button onClick={openAdd}>{t("trips.addBooking")}</Button><Button variant="secondary" onClick={() => setOpen(true)}>{t("trips.new")}</Button></div>} />
      ) : (
        <div className="space-y-10">
          {groups.map((g) => {
            const items = list.filter((x) => g.phases.includes(x.stats.phase ?? "planning"));
            if (!items.length) return null;
            return (
              <section key={g.key}>
                <h2 className="display mb-3 text-[21px]">{t(g.label)}</h2>
                <Stagger className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">{items.map((x) => <StaggerItem key={x.id}><TripCard trip={x} /></StaggerItem>)}</Stagger>
              </section>
            );
          })}
        </div>
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
    <Link to={`/trips/${trip.id}`} className={clsx("group flex overflow-hidden rounded-[22px] border border-sand-200/80 bg-white shadow-[var(--shadow-card)] transition active:scale-[0.985] hover:-translate-y-0.5 hover:shadow-[var(--shadow-lift)]", past && "opacity-75")}>
      <div className="min-w-0 flex-1 p-5">
        <h3 className="display text-[22px] leading-snug text-ink-900">{trip.name}</h3>
        <p className="mt-1 text-[13.5px] text-ink-500">{fmtRange(trip.start_date, trip.end_date)}</p>
        <p className="mt-3 flex items-center gap-1.5 text-[13.5px] text-ink-600"><MapPin className="h-3.5 w-3.5 shrink-0 text-clay-500" /><span className="truncate">{trip.destinations.map((x) => x.name).join(" → ") || trip.primary_destination || t("trips.noDestination")}</span></p>
        <div className="mt-5 flex items-center justify-between gap-2">
          <div className="flex -space-x-1.5">{types.slice(0, 5).map((x) => <EventIcon key={x} type={x} size="sm" className="ring-2 ring-white" />)}</div>
          <span className="text-[12.5px] text-ink-400">{tp("trips.bookings", trip.stats.reservations ?? 0)}</span>
        </div>
        {(trip.stats.conflict_count ?? 0) > 0 && (
          <p className="mt-3 flex items-center gap-1.5 text-[12.5px] font-medium text-amber-ink"><AlertTriangle className="h-3.5 w-3.5" /> {tp("trips.toCheck", trip.stats.conflict_count ?? 0)}</p>
        )}
      </div>
      <div className="relative flex w-[92px] shrink-0 flex-col items-center justify-center border-l-2 border-dashed border-sand-200 bg-apricot-soft/60 px-2 text-center">
        <span className="absolute -left-[11px] -top-[11px] h-5 w-5 rounded-full border border-sand-200 bg-paper" aria-hidden />
        <span className="absolute -bottom-[11px] -left-[11px] h-5 w-5 rounded-full border border-sand-200 bg-paper" aria-hidden />
        <span className="display text-[28px] leading-none text-clay-600">{stub.big}</span>
        {stub.small && <span className="mt-1 text-[11px] font-medium text-ink-500">{stub.small}</span>}
      </div>
    </Link>
  );
}
