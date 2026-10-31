import * as Tabs from "@radix-ui/react-tabs";
import * as Menu from "@radix-ui/react-dropdown-menu";
import { clsx } from "clsx";
import { CalendarPlus, ChevronLeft, Compass, FilePlus, FileText, MessageCircle, MoreHorizontal, Plus, Ticket, Trash2, Users } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useAdd } from "@/components/AddSheet";
import { spring } from "@/components/motion";
import { ConflictList } from "@/components/trips/ConflictList";
import { EventDialog, ReservationDialog } from "@/components/trips/EditDialogs";
import { ReservationCard } from "@/components/trips/ReservationCard";
import { Timeline, TimelineLegend } from "@/components/trips/Timeline";
import { TripMap } from "@/components/trips/TripMap";
import { Badge, Button, EmptyState, LoadError, PageLoader, StatusPill } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { ApiError, api, errorMessage } from "@/lib/api";
import { fmtRange, relativeTime } from "@/lib/format";
import { useT } from "@/lib/i18n";
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

/** One big, labelled action. On phones they sit in a row of four like iOS's contact actions. */
function ActionTile({ icon, label, onClick, to, href }: { icon: ReactNode; label: string; onClick?: () => void; to?: string; href?: string }) {
  const cls = "flex min-h-[64px] flex-col items-center justify-center gap-1 rounded-2xl border border-sand-200 bg-white px-2 py-2.5 text-[12.5px] font-medium text-ink-800 shadow-[var(--shadow-card)] transition active:scale-[0.96] hover:border-sand-300 sm:min-h-0 sm:flex-row sm:gap-2 sm:rounded-xl sm:px-4 sm:py-2.5 sm:text-[14px] [&>svg]:h-5 [&>svg]:w-5 [&>svg]:text-clay-600 sm:[&>svg]:h-4 sm:[&>svg]:w-4";
  if (href) return <a href={href} className={cls}>{icon}<span className="text-center leading-tight">{label}</span></a>;
  if (to) return <Link to={to} className={cls}>{icon}<span className="text-center leading-tight">{label}</span></Link>;
  return <button type="button" onClick={onClick} className={cls}>{icon}<span className="text-center leading-tight">{label}</span></button>;
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
  const { openAdd } = useAdd();
  const { t, tp } = useT();
  const [editing, setEditing] = useState<ItineraryEvent | null | "new">(null);
  const [editingRes, setEditingRes] = useState<Reservation | null | "new">(null);
  const [notes, setNotes] = useState<string | null>(null);
  const [tab, setTab] = useState("plan");

  useEffect(() => { if (trip.data && notes === null) setNotes(trip.data.notes); }, [trip.data, notes]);

  if (trip.isLoading) return <PageLoader />;
  if (trip.isError && !trip.data && !(trip.error instanceof ApiError && trip.error.status === 404))
    return <LoadError title={t("load.trip")} onRetry={() => trip.refetch()} retrying={trip.isFetching} />;
  if (!trip.data) return <EmptyState title={t("trip.notFound")} action={<Link to="/trips" className="text-lagoon-600">{t("trip.backToTrips")}</Link>} />;
  const tr = trip.data;
  const tz = tr.destinations.find((d) => d.timezone)?.timezone ?? null;
  const allConflicts = conflicts.data ?? [];
  const serious = allConflicts.filter((c) => c.severity !== "info");
  const minor = allConflicts.filter((c) => c.severity === "info");

  const askAssistant = async () => {
    try {
      const conv = await api.post<Conversation>("/assistant/conversations", { trip_id: tr.id, title: t("trip.askTitle", { name: tr.name }) });
      navigate(`/assistant/${conv.id}`);
    } catch (err) {
      toast(errorMessage(err), "error");
    }
  };
  const setStatus = async (e: ItineraryEvent, status: string) => {
    try { await api.patch(`/itinerary/events/${e.id}`, { status }); invalidate(); } catch (err) { toast(errorMessage(err), "error"); }
  };
  const remove = async (e: ItineraryEvent) => {
    try { await api.del(`/itinerary/events/${e.id}`); invalidate(); } catch (err) { toast(errorMessage(err), "error"); }
  };
  const saveNotes = async () => {
    if (notes === tr.notes) return;
    try {
      await api.patch(`/trips/${tr.id}`, { notes });
      invalidate();
      toast(t("trip.notesSaved"), "success");
    } catch (err) {
      toast(errorMessage(err), "error");
    }
  };
  const deleteTrip = async () => {
    if (!confirm(t("trip.deleteConfirm"))) return;
    await api.del(`/trips/${tr.id}`);
    invalidate();
    navigate("/trips");
  };

  return (
    <div>
      <header className="mb-6">
        <Link to="/trips" className="-ml-1 inline-flex min-h-11 items-center gap-1 pr-3 text-[15px] text-lagoon-600 hover:text-lagoon-700"><ChevronLeft className="h-5 w-5" />{t("nav.trips")}</Link>
        <div className="mt-1 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="display text-[34px] leading-[1.06] tracking-[-0.02em] sm:text-[40px]">{tr.name}</h1>
            <p className="mt-1.5 text-[15px] text-ink-500">{fmtRange(tr.start_date, tr.end_date)} · {tr.destinations.map((d) => d.name).join(" → ") || tr.primary_destination || t("trip.noDestination")}</p>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-[12.5px] text-ink-400">
              {tr.travellers.length > 0 && <span className="inline-flex items-center gap-1"><Users className="h-3.5 w-3.5" />{tr.travellers.map((x) => x.full_name).join(", ")}</span>}
              {tr.created_via === "auto" && <Badge tone="neutral">{t("trip.fromDocuments")}</Badge>}
              {tr.created_via === "demo" && <Badge tone="violet">{t("trip.demo")}</Badge>}
            </div>
          </div>
          <Menu.Root>
            <Menu.Trigger className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-sand-200 bg-white text-ink-500 hover:bg-sand-50 active:scale-90" aria-label={t("trip.more")}><MoreHorizontal className="h-4 w-4" /></Menu.Trigger>
            <Menu.Portal>
              <Menu.Content align="end" className="z-50 min-w-[210px] rounded-xl border border-sand-200 bg-white p-1 text-[14px] shadow-[var(--shadow-lift)]">
                <Menu.Item onSelect={() => setEditing("new")} className="flex min-h-11 cursor-pointer items-center gap-2 rounded-lg px-2.5 outline-none data-[highlighted]:bg-sand-50"><Plus className="h-4 w-4" /> {t("trip.addEvent")}</Menu.Item>
                <Menu.Item onSelect={() => setEditingRes("new")} className="flex min-h-11 cursor-pointer items-center gap-2 rounded-lg px-2.5 outline-none data-[highlighted]:bg-sand-50"><FilePlus className="h-4 w-4" /> {t("trip.addReservation")}</Menu.Item>
                <Menu.Separator className="my-1 h-px bg-sand-100" />
                <Menu.Item onSelect={deleteTrip} className="flex min-h-11 cursor-pointer items-center gap-2 rounded-lg px-2.5 text-rose-ink outline-none data-[highlighted]:bg-rose-soft"><Trash2 className="h-4 w-4" /> {t("trip.delete")}</Menu.Item>
              </Menu.Content>
            </Menu.Portal>
          </Menu.Root>
        </div>
        <div className="mt-5 grid grid-cols-4 gap-2 sm:flex sm:flex-wrap">
          <ActionTile icon={<MessageCircle />} label={t("trip.ask")} onClick={askAssistant} />
          <ActionTile icon={<Compass />} label={t("trip.activities")} to={`/explore?trip=${tr.id}`} />
          <ActionTile icon={<Ticket />} label={t("trip.tickets")} to={`/explore?tab=tickets&trip=${tr.id}`} />
          <ActionTile icon={<CalendarPlus />} label={t("trip.calendar")} href={`/api/v1/calendar/trips/${tr.id}.ics`} />
        </div>
      </header>

      <Tabs.Root value={tab} onValueChange={setTab}>
        <Tabs.List className="-mx-4 mb-6 flex snap-x gap-1 overflow-x-auto scroll-px-4 px-4 [scrollbar-width:none] sm:mx-0 sm:px-0" aria-label={t("trip.sections")}>
          <Tab value="plan" current={tab}>{t("trip.tabPlan")} {serious.length > 0 && <span className="rounded-full bg-clay-500 px-1.5 text-[11px] leading-[18px] text-white">{serious.length}</span>}</Tab>
          <Tab value="reservations" current={tab}>{t("trip.tabBookings")} <span className="opacity-50">{reservations.data?.length || ""}</span></Tab>
          <Tab value="map" current={tab}>{t("trip.tabMap")}</Tab>
          <Tab value="documents" current={tab}>{t("trip.tabDocuments")} <span className="opacity-50">{documents.data?.length || ""}</span></Tab>
          <Tab value="notes" current={tab}>{t("trip.tabNotes")}</Tab>
        </Tabs.List>

        <Tabs.Content value="plan">
          <div className="grid grid-cols-1 gap-8 xl:grid-cols-[minmax(0,1fr)_340px]">
            <div>
              <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
                <TimelineLegend />
                <Button size="sm" variant="secondary" onClick={() => setEditing("new")} icon={<Plus className="h-3.5 w-3.5" />}>{t("trip.addEvent")}</Button>
              </div>
              {itinerary.isLoading ? <PageLoader /> : (itinerary.data?.length ?? 0) === 0 ? (
                <EmptyState title={t("trip.emptyPlan")} body={t("trip.emptyPlanBody")}
                  action={<Button onClick={openAdd} icon={<FilePlus className="h-4 w-4" />}>{t("trip.addBooking")}</Button>} />
              ) : (
                <Timeline events={itinerary.data!} conflicts={allConflicts} tripTz={tz} onEdit={(e) => setEditing(e)} onDelete={remove} onStatus={setStatus} />
              )}
            </div>
            <aside className="order-first space-y-3 xl:order-none xl:sticky xl:top-20 xl:self-start">
              <div className="card p-4">
                <p className="eyebrow mb-3">{serious.length ? tp("trip.toCheck", serious.length) : t("trip.checks")}</p>
                <ConflictList conflicts={serious} tripId={tr.id} />
                {minor.length > 0 && (
                  <details className="group mt-3">
                    <summary className="flex min-h-10 cursor-pointer list-none items-center text-[13px] font-medium text-ink-500 [&::-webkit-details-marker]:hidden">{tp("trip.minorNotes", minor.length)}</summary>
                    <ConflictList conflicts={minor} tripId={tr.id} compact showInfo />
                  </details>
                )}
              </div>
              {tz && <p className="px-1 text-[12.5px] text-ink-400">{t("trip.timesNote", { tz: tz.replace(/_/g, " ") })}</p>}
            </aside>
          </div>
        </Tabs.Content>

        <Tabs.Content value="reservations">
          <div className="mb-4 flex flex-wrap justify-end gap-2">
            <Button size="sm" variant="secondary" onClick={openAdd} icon={<FilePlus className="h-3.5 w-3.5" />}>{t("trip.uploadConfirmation")}</Button>
            <Button size="sm" variant="secondary" onClick={() => setEditingRes("new")} icon={<Plus className="h-3.5 w-3.5" />}>{t("trip.addManually")}</Button>
          </div>
          {(reservations.data?.length ?? 0) === 0 ? <EmptyState title={t("trip.noReservations")} body={t("trip.noReservationsBody")} /> : (
            <div className="space-y-3">{reservations.data!.map((r) => <ReservationCard key={r.id} r={r} onEdit={(x) => setEditingRes(x)} />)}</div>
          )}
        </Tabs.Content>

        <Tabs.Content value="map"><TripMap events={itinerary.data ?? []} /></Tabs.Content>

        <Tabs.Content value="documents">
          <div className="mb-4 flex justify-end"><Button size="sm" variant="secondary" onClick={openAdd} icon={<FilePlus className="h-3.5 w-3.5" />}>{t("trip.uploadConfirmation")}</Button></div>
          {(documents.data?.length ?? 0) === 0 ? <EmptyState icon={<FileText className="h-7 w-7" />} title={t("trip.noDocuments")} body={t("trip.noDocumentsBody")} /> : (
            <ul className="card divide-y divide-sand-100">
              {documents.data!.map((d) => (
                <li key={d.id}>
                  <Link to={`/inbox/${d.id}`} className="flex min-h-[56px] items-center justify-between gap-3 px-4 py-3 hover:bg-sand-50/70">
                    <span className="flex min-w-0 items-center gap-3"><FileText className="h-4 w-4 shrink-0 text-ink-400" /><span className="truncate text-[14px]">{d.filename}</span></span>
                    <span className="flex shrink-0 items-center gap-3 text-[12px] text-ink-400"><StatusPill status={d.status} /><span className="hidden sm:inline">{relativeTime(d.created_at)}</span></span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Tabs.Content>

        <Tabs.Content value="notes">
          <div className="max-w-3xl">
            <textarea className="field min-h-[240px] leading-relaxed" value={notes ?? ""} onChange={(e) => setNotes(e.target.value)} onBlur={saveNotes}
              placeholder={t("trip.notesPlaceholder")} aria-label={t("trip.tabNotes")} />
            <p className="mt-2 text-[12px] text-ink-400">{t("trip.notesHint")}</p>
          </div>
        </Tabs.Content>
      </Tabs.Root>

      {editing && <EventDialog tripId={tr.id} event={editing === "new" ? null : editing} defaultTz={tz} onClose={() => setEditing(null)} />}
      {editingRes && <ReservationDialog tripId={tr.id} reservation={editingRes === "new" ? null : editingRes} defaultTz={tz} onClose={() => setEditingRes(null)} />}
    </div>
  );
}
