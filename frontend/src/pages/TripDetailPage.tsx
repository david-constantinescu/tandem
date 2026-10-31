import * as Tabs from "@radix-ui/react-tabs";
import { clsx } from "clsx";
import { CalendarPlus, ChevronLeft, Compass, FileText, MessageCircle, MoreHorizontal, Plus, Trash2, Users } from "lucide-react";
import * as Menu from "@radix-ui/react-dropdown-menu";
import { motion } from "motion/react";
import { useEffect, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { spring } from "@/components/motion";
import { ConflictList } from "@/components/trips/ConflictList";
import { EventDialog, ReservationDialog } from "@/components/trips/EditDialogs";
import { ReservationCard } from "@/components/trips/ReservationCard";
import { Timeline, TimelineLegend } from "@/components/trips/Timeline";
import { TripMap } from "@/components/trips/TripMap";
import { Badge, Button, EmptyState, LinkButton, PageLoader, StatusPill } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { api, errorMessage } from "@/lib/api";
import { fmtRange, relativeTime } from "@/lib/format";
import { useConflicts, useInvalidateTripData, useItinerary, useReservations, useTrip, useTripDocuments } from "@/lib/queries";
import type { Conversation, ItineraryEvent, Reservation } from "@/lib/types";

function Tab({ value, current, children }: { value: string; current: string; children: ReactNode }) {
  const active = value === current;
  return (
    <Tabs.Trigger value={value} className={clsx("relative flex h-10 shrink-0 snap-start items-center gap-1.5 rounded-full px-4 text-[14px] font-medium transition-colors pointer-coarse:h-11", active ? "text-white" : "text-ink-500 hover:text-ink-800")}>
      {active && <motion.span layoutId="trip-tab" transition={spring} className="absolute inset-0 rounded-full bg-ink-900" />}
      <span className="relative z-10 flex items-center gap-1.5">{children}</span>
    </Tabs.Trigger>
  );
}

export default function TripDetailPage() {
  const { id = "" } = useParams();
  const trip = useTrip(id);
  const itinerary = useItinerary(id);
  const reservations = useReservations(id);
  const conflicts = useConflicts(id);
  const documents = useTripDocuments(id);
  const invalidate = useInvalidateTripData();
  const toast = useToast();
  const navigate = useNavigate();
  const [editing, setEditing] = useState<ItineraryEvent | null | "new">(null);
  const [editingRes, setEditingRes] = useState<Reservation | null | "new">(null);
  const [notes, setNotes] = useState<string | null>(null);
  const [tab, setTab] = useState("itinerary");

  useEffect(() => { if (trip.data && notes === null) setNotes(trip.data.notes); }, [trip.data, notes]);

  if (trip.isLoading) return <PageLoader />;
  if (!trip.data) return <EmptyState title="Trip not found" action={<Link to="/trips" className="text-lagoon-600">Back to trips</Link>} />;
  const t = trip.data;
  const tz = t.destinations.find((d) => d.timezone)?.timezone ?? null;
  const allConflicts = conflicts.data ?? [];
  const serious = allConflicts.filter((c) => c.severity !== "info");

  const askAssistant = async () => {
    const conv = await api.post<Conversation>("/assistant/conversations", { trip_id: t.id, title: `About ${t.name}` });
    navigate(`/assistant/${conv.id}`);
  };
  const setStatus = async (e: ItineraryEvent, status: string) => {
    try { await api.patch(`/itinerary/events/${e.id}`, { status }); invalidate(); } catch (err) { toast(errorMessage(err), "error"); }
  };
  const remove = async (e: ItineraryEvent) => {
    try { await api.del(`/itinerary/events/${e.id}`); invalidate(); } catch (err) { toast(errorMessage(err), "error"); }
  };
  const saveNotes = async () => {
    if (notes === t.notes) return;
    await api.patch(`/trips/${t.id}`, { notes });
    invalidate();
    toast("Notes saved", "success");
  };
  const deleteTrip = async () => {
    if (!confirm("Delete this trip? Reservations are kept and become unassigned.")) return;
    await api.del(`/trips/${t.id}`);
    invalidate();
    navigate("/trips");
  };

  return (
    <div>
      <header className="mb-6">
        <Link to="/trips" className="-ml-1 inline-flex min-h-11 items-center gap-1 pr-3 text-[15px] text-lagoon-600 hover:text-lagoon-700"><ChevronLeft className="h-5 w-5" />Trips</Link>
        <div className="mt-1 flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <h1 className="display text-[34px] leading-[1.06] tracking-[-0.02em] sm:text-[40px]">{t.name}</h1>
            <p className="mt-1.5 text-[15px] text-ink-500">{fmtRange(t.start_date, t.end_date)} · {t.destinations.map((d) => d.name).join(" → ") || t.primary_destination || "No destination yet"}</p>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-[12.5px] text-ink-400">
              {t.travellers.length > 0 && <span className="inline-flex items-center gap-1"><Users className="h-3.5 w-3.5" />{t.travellers.map((x) => x.full_name).join(", ")}</span>}
              {t.created_via === "auto" && <Badge tone="neutral">Created from your documents</Badge>}
              {t.created_via === "demo" && <Badge tone="violet">Demo trip</Badge>}
            </div>
          </div>
          <div className="-mx-4 flex gap-2 overflow-x-auto px-4 [scrollbar-width:none] sm:mx-0 sm:flex-wrap sm:px-0">
            <Button variant="secondary" onClick={askAssistant} className="shrink-0" icon={<MessageCircle className="h-4 w-4" />}>Ask about this trip</Button>
            <LinkButton href={`/api/v1/calendar/trips/${t.id}.ics`} className="shrink-0" icon={<CalendarPlus className="h-4 w-4" />}>Add to Calendar</LinkButton>
            <LinkButton to={`/discover?trip=${t.id}`} className="shrink-0" icon={<Compass className="h-4 w-4" />}>Find activities</LinkButton>
            <Menu.Root>
              <Menu.Trigger className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-sand-200 bg-white text-ink-500 hover:bg-sand-50 active:scale-90 pointer-coarse:h-11 pointer-coarse:w-11" aria-label="More trip actions"><MoreHorizontal className="h-4 w-4" /></Menu.Trigger>
              <Menu.Portal>
                <Menu.Content align="end" className="z-50 min-w-[180px] rounded-xl border border-sand-200 bg-white p-1 text-[13.5px] shadow-[var(--shadow-lift)]">
                  <Menu.Item onSelect={deleteTrip} className="flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-2 text-rose-ink outline-none data-[highlighted]:bg-rose-soft"><Trash2 className="h-4 w-4" /> Delete trip</Menu.Item>
                </Menu.Content>
              </Menu.Portal>
            </Menu.Root>
          </div>
        </div>
      </header>

      <Tabs.Root value={tab} onValueChange={setTab}>
        <Tabs.List className="-mx-4 mb-6 flex snap-x gap-1 overflow-x-auto px-4 [scrollbar-width:none] sm:mx-0 sm:px-0" aria-label="Trip sections">
          <Tab value="itinerary" current={tab}>Itinerary</Tab>
          <Tab value="reservations" current={tab}>Bookings <span className="opacity-50">{reservations.data?.length ?? ""}</span></Tab>
          <Tab value="alerts" current={tab}>Alerts {serious.length > 0 && <span className="rounded-full bg-clay-500 px-1.5 text-[11px] leading-[18px] text-white">{serious.length}</span>}</Tab>
          <Tab value="map" current={tab}>Map</Tab>
          <Tab value="documents" current={tab}>Documents</Tab>
          <Tab value="notes" current={tab}>Notes</Tab>
        </Tabs.List>

        <Tabs.Content value="itinerary">
          <div className="grid grid-cols-1 gap-8 xl:grid-cols-[minmax(0,1fr)_300px]">
            <div>
              <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
                <TimelineLegend />
                <Button size="sm" variant="secondary" onClick={() => setEditing("new")} icon={<Plus className="h-3.5 w-3.5" />}>Add event</Button>
              </div>
              {itinerary.isLoading ? <PageLoader /> : (itinerary.data?.length ?? 0) === 0 ? (
                <EmptyState title="No plans yet" body="Add bookings from the Inbox, or add events yourself." />
              ) : (
                <Timeline events={itinerary.data!} conflicts={allConflicts} tripTz={tz} onEdit={(e) => setEditing(e)} onDelete={remove} onStatus={setStatus} />
              )}
            </div>
            <aside className="order-first space-y-4 xl:order-none xl:sticky xl:top-20 xl:self-start">
              <div className="card p-4">
                <p className="eyebrow mb-3">Needs attention</p>
                <ConflictList conflicts={serious} tripId={t.id} compact />
              </div>
              {tz && <p className="px-1 text-[12.5px] text-ink-400">Times are shown in each event's local time. Trip timezone: {tz.replace("_", " ")}.</p>}
            </aside>
          </div>
        </Tabs.Content>

        <Tabs.Content value="reservations">
          <div className="mb-4 flex justify-end"><Button size="sm" variant="secondary" onClick={() => setEditingRes("new")} icon={<Plus className="h-3.5 w-3.5" />}>Add reservation</Button></div>
          {(reservations.data?.length ?? 0) === 0 ? <EmptyState title="No reservations" body="Upload confirmations in the Inbox and accept them into this trip." /> : (
            <div className="space-y-3">{reservations.data!.map((r) => <ReservationCard key={r.id} r={r} onEdit={(x) => setEditingRes(x)} />)}</div>
          )}
        </Tabs.Content>

        <Tabs.Content value="alerts">
          <div className="max-w-3xl"><ConflictList conflicts={allConflicts} tripId={t.id} /></div>
          <p className="mt-4 max-w-3xl text-[12.5px] text-ink-400">Checks are rule-based: overlaps, physically impossible sequences, time after arrival, departures, missing transport or accommodation, unconfirmed bookings and cancellation deadlines. Travel times are only used when a routing provider is configured.</p>
        </Tabs.Content>

        <Tabs.Content value="map"><TripMap events={itinerary.data ?? []} /></Tabs.Content>

        <Tabs.Content value="documents">
          {(documents.data?.length ?? 0) === 0 ? <EmptyState icon={<FileText className="h-7 w-7" />} title="No documents" body="Documents you upload and accept are linked here." /> : (
            <ul className="card divide-y divide-sand-100">
              {documents.data!.map((d) => (
                <li key={d.id} className="flex items-center justify-between gap-3 px-4 py-3">
                  <Link to={`/inbox/${d.id}`} className="flex min-w-0 items-center gap-3 hover:text-lagoon-700">
                    <FileText className="h-4 w-4 shrink-0 text-ink-400" /><span className="truncate text-[14px]">{d.filename}</span>
                  </Link>
                  <span className="flex shrink-0 items-center gap-3 text-[12px] text-ink-400"><StatusPill status={d.status} /><span className="hidden sm:inline">{relativeTime(d.created_at)}</span></span>
                </li>
              ))}
            </ul>
          )}
        </Tabs.Content>

        <Tabs.Content value="notes">
          <div className="max-w-3xl">
            <textarea className={clsx("field min-h-[240px] leading-relaxed")} value={notes ?? ""} onChange={(e) => setNotes(e.target.value)} onBlur={saveNotes}
              placeholder="Packing list, ideas, things to remember…" aria-label="Trip notes" />
            <p className="mt-2 text-[12px] text-ink-400">Saved when you click away.</p>
          </div>
        </Tabs.Content>
      </Tabs.Root>

      {editing && <EventDialog tripId={t.id} event={editing === "new" ? null : editing} defaultTz={tz} onClose={() => setEditing(null)} />}
      {editingRes && <ReservationDialog tripId={t.id} reservation={editingRes === "new" ? null : editingRes} defaultTz={tz} onClose={() => setEditingRes(null)} />}
    </div>
  );
}
