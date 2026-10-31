import { clsx } from "clsx";
import { AlertTriangle, MapPin, Plus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Stagger, StaggerItem } from "@/components/motion";
import { EventIcon } from "@/components/trips/EventIcon";
import { Button, EmptyState, ErrorNote, Field, LoadError, PageHeader, PageLoader } from "@/components/ui";
import { Dialog } from "@/components/ui/Dialog";
import { api, errorMessage } from "@/lib/api";
import { daysUntil, fmtRange } from "@/lib/format";
import { useInvalidateTripData, useTrips } from "@/lib/queries";
import type { Trip } from "@/lib/types";

const groups: { key: string; label: string; phases: string[] }[] = [
  { key: "current", label: "Happening now", phases: ["current"] },
  { key: "upcoming", label: "Upcoming", phases: ["upcoming", "planning"] },
  { key: "past", label: "Past", phases: ["past", "cancelled"] },
];

export default function TripsPage() {
  const trips = useTrips();
  const [open, setOpen] = useState(false);
  if (trips.isLoading) return <PageLoader />;
  if (trips.isError && !trips.data) return <LoadError what="trips" onRetry={() => trips.refetch()} retrying={trips.isFetching} />;
  const list = trips.data ?? [];
  return (
    <div>
      <PageHeader title="Trips" subtitle="Everything grouped by journey. Records stay movable between trips."
        actions={<Button onClick={() => setOpen(true)} icon={<Plus className="h-4 w-4" />}>New trip</Button>} />
      {list.length === 0 ? (
        <EmptyState icon={<MapPin className="h-8 w-8" />} title="No trips yet" body="Trips are created automatically when you add bookings to the Inbox, or you can start one by hand."
          action={<Button onClick={() => setOpen(true)}>Create a trip</Button>} />
      ) : (
        <div className="space-y-10">
          {groups.map((g) => {
            const items = list.filter((t) => g.phases.includes(t.stats.phase ?? "planning"));
            if (!items.length) return null;
            return (
              <section key={g.key}>
                <h2 className="display mb-3 text-[21px]">{g.label}</h2>
                <Stagger className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">{items.map((t) => <StaggerItem key={t.id}><TripCard trip={t} /></StaggerItem>)}</Stagger>
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
  const d = daysUntil(trip.start_date);
  const types = Object.keys(trip.stats.reservation_types ?? {});
  const past = trip.stats.phase === "past";
  const stub = trip.stats.phase === "current" ? { big: "Now", small: "travelling" }
    : d !== null && d >= 0 ? { big: d === 0 ? "Today" : String(d), small: d === 0 ? "" : d === 1 ? "day to go" : "days to go" }
      : { big: trip.start_date ? new Date(trip.start_date + "T00:00:00").toLocaleDateString("en-GB", { month: "short" }) : "—", small: trip.start_date?.slice(0, 4) ?? "" };
  return (
    <Link to={`/trips/${trip.id}`} className={clsx("group flex overflow-hidden rounded-[22px] border border-sand-200/80 bg-white shadow-[var(--shadow-card)] transition active:scale-[0.985] hover:-translate-y-0.5 hover:shadow-[var(--shadow-lift)]", past && "opacity-75")}>
      <div className="min-w-0 flex-1 p-5">
        <h3 className="display text-[22px] leading-snug text-ink-900">{trip.name}</h3>
        <p className="mt-1 text-[13.5px] text-ink-500">{fmtRange(trip.start_date, trip.end_date)}</p>
        <p className="mt-3 flex items-center gap-1.5 text-[13.5px] text-ink-600"><MapPin className="h-3.5 w-3.5 shrink-0 text-clay-500" /><span className="truncate">{trip.destinations.map((x) => x.name).join(" → ") || trip.primary_destination || "Destination not set"}</span></p>
        <div className="mt-5 flex items-center justify-between gap-2">
          <div className="flex -space-x-1.5">{types.slice(0, 5).map((t) => <EventIcon key={t} type={t} size="sm" className="ring-2 ring-white" />)}</div>
          <span className="text-[12.5px] text-ink-400">{trip.stats.reservations ?? 0} booking{trip.stats.reservations === 1 ? "" : "s"}</span>
        </div>
        {(trip.stats.conflict_count ?? 0) > 0 && (
          <p className="mt-3 flex items-center gap-1.5 text-[12.5px] font-medium text-amber-ink"><AlertTriangle className="h-3.5 w-3.5" /> {trip.stats.conflict_count} thing{trip.stats.conflict_count === 1 ? "" : "s"} to check</p>
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

function NewTripDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const [name, setName] = useState("");
  const [dest, setDest] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const invalidate = useInvalidateTripData();
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const t = await api.post<Trip>("/trips", { name, primary_destination: dest || null, start_date: start || null, end_date: end || null });
      invalidate();
      onOpenChange(false);
      navigate(`/trips/${t.id}`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="New trip" description="You can also let Tandem create trips from your bookings.">
      <form onSubmit={submit} className="space-y-4">
        <Field label="Trip name" htmlFor="tn"><input id="tn" required className="field" value={name} onChange={(e) => setName(e.target.value)} placeholder="Lisbon in spring" /></Field>
        <Field label="Main destination" htmlFor="td"><input id="td" className="field" value={dest} onChange={(e) => setDest(e.target.value)} placeholder="Lisbon" /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Start" htmlFor="ts"><input id="ts" type="date" className="field" value={start} onChange={(e) => setStart(e.target.value)} /></Field>
          <Field label="End" htmlFor="te"><input id="te" type="date" className="field" value={end} min={start} onChange={(e) => setEnd(e.target.value)} /></Field>
        </div>
        {error && <ErrorNote>{error}</ErrorNote>}
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button type="submit" loading={busy}>Create trip</Button>
        </div>
      </form>
    </Dialog>
  );
}
