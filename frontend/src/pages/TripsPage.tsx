import { clsx } from "clsx";
import { AlertTriangle, MapPin, Plus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { EventIcon } from "@/components/trips/EventIcon";
import { Button, EmptyState, ErrorNote, Field, PageHeader, PageLoader } from "@/components/ui";
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
                <h2 className="eyebrow mb-3">{g.label}</h2>
                <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{items.map((t) => <TripCard key={t.id} trip={t} />)}</div>
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
  return (
    <Link to={`/trips/${trip.id}`} className={clsx("card group flex flex-col p-5 transition hover:-translate-y-0.5 hover:shadow-[var(--shadow-lift)]", trip.stats.phase === "past" && "opacity-80")}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="display text-[20px] leading-snug text-ink-900">{trip.name}</h3>
          <p className="mt-1 text-[13.5px] text-ink-500">{fmtRange(trip.start_date, trip.end_date)}</p>
        </div>
        {trip.stats.phase === "upcoming" && d !== null && d >= 0 && (
          <span className="rounded-full bg-clay-50 px-2.5 py-1 text-[12px] font-medium text-clay-600">{d === 0 ? "Today" : `${d}d`}</span>
        )}
      </div>
      <p className="mt-3 flex items-center gap-1.5 text-[13.5px] text-ink-600"><MapPin className="h-3.5 w-3.5 text-ink-400" />{trip.destinations.map((x) => x.name).join(" → ") || trip.primary_destination || "Destination not set"}</p>
      <div className="mt-5 flex items-center justify-between">
        <div className="flex -space-x-1.5">{types.slice(0, 5).map((t) => <EventIcon key={t} type={t} size="sm" className="ring-2 ring-white" />)}</div>
        <span className="text-[12.5px] text-ink-400">{trip.stats.reservations ?? 0} booking{trip.stats.reservations === 1 ? "" : "s"}</span>
      </div>
      {(trip.stats.conflict_count ?? 0) > 0 && (
        <p className="mt-3 flex items-center gap-1.5 text-[12.5px] text-amber-ink"><AlertTriangle className="h-3.5 w-3.5" /> {trip.stats.conflict_count} issue{trip.stats.conflict_count === 1 ? "" : "s"} to check</p>
      )}
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
