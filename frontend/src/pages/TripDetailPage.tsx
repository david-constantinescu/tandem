import * as Menu from "@radix-ui/react-dropdown-menu";
import { clsx } from "clsx";
import { AlertTriangle, CalendarPlus, Check, ChevronLeft, CloudSun, FilePlus, FileText, MessageCircle, MoreHorizontal, Pencil, Plus, StickyNote, Trash2, Users, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useAdd } from "@/components/AddSheet";
import { Segmented } from "@/components/motion";
import { ConflictList } from "@/components/trips/ConflictList";
import { EventDialog, ReservationDialog } from "@/components/trips/EditDialogs";
import { EventIcon } from "@/components/trips/EventIcon";
import { TripContextCard, WeatherChip, WeatherIcon } from "@/components/trips/TripContext";
import { TripMap } from "@/components/trips/TripMap";
import { Badge, Button, EmptyState, LoadError, PageLoader, StatusPill } from "@/components/ui";
import { Dialog } from "@/components/ui/Dialog";
import { useToast } from "@/components/ui/Toast";
import { ApiError, api, errorMessage } from "@/lib/api";
import { dayKey, eachDay, fmtDate, fmtRange, fmtTime, relativeTime } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { useConflicts, useInvalidateTripData, useItinerary, useReservations, useTrip, useTripContext, useTripDocuments } from "@/lib/queries";
import type { Conversation, ItineraryEvent, Reservation } from "@/lib/types";

/** o calatorie e un singur ecran: antet, patru taburi si un paginator de zile in plan. Listele din ea incap; se deruleaza doar o zi neobisnuit de lunga */
export default function TripDetailPage() {
  const { id = "" } = useParams();
  const trip = useTrip(id);
  const itinerary = useItinerary(id);
  const reservations = useReservations(id);
  const conflicts = useConflicts(id);
  const documents = useTripDocuments(id);
  const context = useTripContext(id);
  const invalidate = useInvalidateTripData();
  const toast = useToast();
  const navigate = useNavigate();
  const { openAdd } = useAdd();
  const { t, tp } = useT();
  const [tab, setTab] = useState<"plan" | "bookings" | "map" | "docs">("plan");
  const [day, setDay] = useState<string | null>(null);
  const [sheet, setSheet] = useState<"checks" | "notes" | "event" | null>(null);
  const [picked, setPicked] = useState<ItineraryEvent | null>(null);
  const [editing, setEditing] = useState<ItineraryEvent | null | "new">(null);
  const [editingRes, setEditingRes] = useState<Reservation | null | "new">(null);
  const [notes, setNotes] = useState<string | null>(null);
  const touch = useRef<number | null>(null);

  useEffect(() => { if (trip.data && notes === null) setNotes(trip.data.notes); }, [trip.data, notes]);

  const events = useMemo(() => itinerary.data ?? [], [itinerary.data]);
  const days = useMemo(() => {
    const fromTrip = eachDay(trip.data?.start_date ?? null, trip.data?.end_date ?? null);
    const extra = events.map((e) => dayKey(e.start_local)).filter((d) => !fromTrip.includes(d));
    return [...fromTrip, ...new Set(extra)].sort();
  }, [trip.data?.start_date, trip.data?.end_date, events]);
  const current = day && days.includes(day) ? day : (days.find((d) => d >= new Date().toISOString().slice(0, 10)) ?? days[0] ?? null);

  if (trip.isLoading) return <PageLoader />;
  if (trip.isError && !trip.data && !(trip.error instanceof ApiError && trip.error.status === 404))
    return <LoadError title={t("load.trip")} onRetry={() => trip.refetch()} retrying={trip.isFetching} />;
  if (!trip.data) return <EmptyState title={t("trip.notFound")} action={<Link to="/trips" className="text-lagoon-600">{t("trip.backToTrips")}</Link>} />;
  const tr = trip.data;
  const tz = tr.destinations.find((d) => d.timezone)?.timezone ?? null;
  const all = conflicts.data ?? [];
  const serious = all.filter((c) => c.severity !== "info");
  const weatherByDay = new Map((context.data?.weather.days ?? []).map((w) => [w.date, w]));
  const flagged = new Map<string, number>();
  for (const c of all) for (const eid of c.event_ids) flagged.set(eid, (flagged.get(eid) ?? 0) + 1);
  const dayEvents = events.filter((e) => dayKey(e.start_local) === current);
  const idx = current ? days.indexOf(current) : -1;
  const step = (n: number) => { const next = days[idx + n]; if (next) setDay(next); };
  const todaysWeather = current ? weatherByDay.get(current) : undefined;

  const askAssistant = async () => {
    try {
      const conv = await api.post<Conversation>("/assistant/conversations", { trip_id: tr.id, title: t("trip.askTitle", { name: tr.name }) });
      navigate(`/assistant/${conv.id}`);
    } catch (err) { toast(errorMessage(err), "error"); }
  };
  const setStatus = async (e: ItineraryEvent, status: string) => {
    try { await api.patch(`/itinerary/events/${e.id}`, { status }); invalidate(); setSheet(null); setPicked(null); } catch (err) { toast(errorMessage(err), "error"); }
  };
  const remove = async (e: ItineraryEvent) => {
    try { await api.del(`/itinerary/events/${e.id}`); invalidate(); setSheet(null); setPicked(null); } catch (err) { toast(errorMessage(err), "error"); }
  };
  const saveNotes = async () => {
    if (notes === tr.notes) return;
    try { await api.patch(`/trips/${tr.id}`, { notes }); invalidate(); toast(t("trip.notesSaved"), "success"); } catch (err) { toast(errorMessage(err), "error"); }
  };
  const deleteTrip = async () => {
    if (!confirm(t("trip.deleteConfirm"))) return;
    await api.del(`/trips/${tr.id}`);
    invalidate();
    navigate("/trips");
  };

  return (
    <div className="mx-auto flex min-h-full max-w-3xl flex-col gap-3 pb-8">
      <header className="shrink-0">
        <div className="flex items-center gap-1">
          <Link to="/trips" aria-label={t("trip.backToTrips")} className="-ml-2 flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-lagoon-600 active:bg-sand-100"><ChevronLeft className="h-6 w-6" /></Link>
          <h1 className="display line-clamp-2 min-w-0 flex-1 text-[23px] leading-[1.12] tracking-[-0.01em] sm:text-[30px]">{tr.name}</h1>
          <button onClick={askAssistant} aria-label={t("trip.ask")} className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-lagoon-900 text-white active:scale-90"><MessageCircle className="h-[18px] w-[18px]" /></button>
          <Menu.Root>
            <Menu.Trigger className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-sand-200 bg-white text-ink-500 active:scale-90" aria-label={t("trip.more")}><MoreHorizontal className="h-4 w-4" /></Menu.Trigger>
            <Menu.Portal>
              <Menu.Content align="end" className="z-50 min-w-[220px] rounded-xl border border-sand-200 bg-white p-1 text-[14px] shadow-[var(--shadow-lift)]">
                {[
                  { icon: <Plus className="h-4 w-4" />, label: t("trip.addEvent"), run: () => setEditing("new") },
                  { icon: <FilePlus className="h-4 w-4" />, label: t("trip.addReservation"), run: () => setEditingRes("new") },
                  { icon: <StickyNote className="h-4 w-4" />, label: t("trip.tabNotes"), run: () => setSheet("notes") },
                ].map((o) => (
                  <Menu.Item key={o.label} onSelect={o.run} className="flex min-h-11 cursor-pointer items-center gap-2 rounded-lg px-2.5 outline-none data-[highlighted]:bg-sand-50">{o.icon} {o.label}</Menu.Item>
                ))}
                <Menu.Item asChild><a href={`/api/v1/calendar/trips/${tr.id}.ics`} className="flex min-h-11 cursor-pointer items-center gap-2 rounded-lg px-2.5 outline-none data-[highlighted]:bg-sand-50"><CalendarPlus className="h-4 w-4" /> {t("trip.calendar")}</a></Menu.Item>
                <Menu.Separator className="my-1 h-px bg-sand-100" />
                <Menu.Item onSelect={deleteTrip} className="flex min-h-11 cursor-pointer items-center gap-2 rounded-lg px-2.5 text-rose-ink outline-none data-[highlighted]:bg-rose-soft"><Trash2 className="h-4 w-4" /> {t("trip.delete")}</Menu.Item>
              </Menu.Content>
            </Menu.Portal>
          </Menu.Root>
        </div>
        <p className="mt-1 pl-0.5 text-[13.5px] leading-snug text-ink-500">
          {fmtRange(tr.start_date, tr.end_date)} · {tr.destinations.map((d) => d.name).join(" → ") || tr.primary_destination || t("trip.noDestination")}
          {tr.travellers.length > 0 && <span className="text-ink-400"> · <Users className="-mt-0.5 inline h-3 w-3" /> {tr.travellers.map((x) => x.full_name.split(" ")[0]).join(", ")}</span>}
        </p>
      </header>

      <Segmented id="trip-tab" value={tab} onChange={setTab} className="shrink-0 [&_button]:gap-1 [&_button]:px-1 [&_button]:text-[13px]"
        options={[
          { value: "plan", label: <>{t("trip.tabPlan")}{serious.length > 0 && <span className="rounded-full bg-clay-500 px-1.5 text-[11px] leading-[18px] text-white">{serious.length}</span>}</> },
          { value: "bookings", label: <>{t("trip.tabBookings")}<span className="opacity-50">{reservations.data?.length || ""}</span></> },
          { value: "map", label: t("trip.tabMap") },
          { value: "docs", label: <>{t("trip.tabDocuments")}<span className="opacity-50">{documents.data?.length || ""}</span></> },
        ]} />

      {tab === "plan" && (
        <section className="flex flex-col gap-2.5">
          {days.length > 0 && (
            <div className="-mx-4 flex shrink-0 gap-1.5 overflow-x-auto px-4 [scrollbar-width:none] sm:mx-0 sm:px-0" role="tablist" aria-label={t("trip.days")}>
              {days.map((d) => {
                const w = weatherByDay.get(d);
                const on = d === current;
                const hasFlag = events.some((e) => dayKey(e.start_local) === d && flagged.has(e.id));
                return (
                  <button key={d} role="tab" aria-selected={on} onClick={() => setDay(d)}
                    className={clsx("relative flex h-[62px] min-w-[56px] flex-1 flex-col items-center justify-center rounded-2xl border text-center transition active:scale-95",
                      on ? "border-ink-900 bg-ink-900 text-white" : "border-sand-200 bg-white text-ink-600")}>
                    <span className="text-[11px] font-medium uppercase tracking-wide opacity-70">{fmtDate(d, { weekday: true }).split(/[ ,.]/)[0]}</span>
                    <span className="text-[17px] font-semibold leading-tight tabular-nums">{Number(d.slice(8))}</span>
                    {w ? <WeatherIcon condition={w.condition} className={clsx("h-3.5 w-3.5", on ? "text-white/80" : w.outdoor_ok ? "text-clay-500" : "text-lagoon-600")} /> : <span className="h-3.5" />}
                    {hasFlag && <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-rose-ink" />}
                  </button>
                );
              })}
            </div>
          )}
          <div className="flex shrink-0 items-center gap-2">
            <p className="min-w-0 flex-1 truncate text-[13.5px] text-ink-500">{current ? fmtDate(current, { weekday: true }) : ""}</p>
            {todaysWeather && <WeatherChip day={todaysWeather} />}
            <button onClick={() => setSheet("checks")} className={clsx("flex h-8 items-center gap-1 rounded-full px-2.5 text-[12.5px] font-medium active:scale-95", serious.length ? "bg-amber-soft text-amber-ink" : "bg-sand-100 text-ink-600")}>
              {serious.length ? <AlertTriangle className="h-3.5 w-3.5" /> : <CloudSun className="h-3.5 w-3.5" />}{serious.length || t("trip.context")}
            </button>
            <button onClick={() => setEditing("new")} aria-label={t("trip.addEvent")} className="flex h-8 w-8 items-center justify-center rounded-full bg-sand-100 text-ink-700 active:scale-90"><Plus className="h-4 w-4" /></button>
          </div>
          <div className="rounded-2xl"
            onTouchStart={(e) => { touch.current = e.touches[0].clientX; }}
            onTouchEnd={(e) => { if (touch.current !== null) { const dx = e.changedTouches[0].clientX - touch.current; if (Math.abs(dx) > 60) step(dx < 0 ? 1 : -1); touch.current = null; } }}>
            {itinerary.isLoading ? <PageLoader /> : dayEvents.length === 0 ? (
              <div className="flex min-h-[200px] flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-sand-300 py-8 text-center">
                <p className="px-6 text-[14px] text-ink-500">{events.length === 0 ? t("trip.emptyPlanBody") : t("trip.emptyDay")}</p>
                <Button size="sm" variant="secondary" onClick={() => (events.length === 0 ? openAdd() : setEditing("new"))} icon={<Plus className="h-3.5 w-3.5" />}>{events.length === 0 ? t("trip.addBooking") : t("trip.addEvent")}</Button>
              </div>
            ) : (
              <ol className="space-y-1.5">
                {dayEvents.map((e) => <DayRow key={e.id} e={e} flags={flagged.get(e.id) ?? 0} onOpen={() => { setPicked(e); setSheet("event"); }} />)}
              </ol>
            )}
          </div>
        </section>
      )}

      {tab === "bookings" && (
        <section className="flex flex-col gap-2">
          <div className="flex shrink-0 justify-end gap-2">
            <Button size="sm" variant="secondary" onClick={openAdd} icon={<FilePlus className="h-3.5 w-3.5" />}>{t("trip.uploadConfirmation")}</Button>
            <Button size="sm" variant="secondary" onClick={() => setEditingRes("new")} icon={<Plus className="h-3.5 w-3.5" />}>{t("trip.addManually")}</Button>
          </div>
          {(reservations.data?.length ?? 0) === 0 ? <EmptyState title={t("trip.noReservations")} body={t("trip.noReservationsBody")} /> : (
            <ul className="card divide-y divide-sand-100">
              {reservations.data!.map((r) => (
                <li key={r.id}>
                  <button onClick={() => setEditingRes(r)} className="flex min-h-[58px] w-full items-center gap-3 px-3.5 py-2 text-left active:bg-sand-50">
                    <EventIcon type={r.type} size="sm" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[14px] font-medium text-ink-900">{r.title}</span>
                      <span className="block truncate text-[12px] text-ink-400">{r.provider_name}{r.booking_reference ? ` · ${r.booking_reference}` : ""}{r.start_local ? ` · ${fmtDate(dayKey(r.start_local))} ${fmtTime(r.start_local)}` : ""}</span>
                    </span>
                    <StatusPill status={r.status} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {tab === "map" && <section className="h-[60dvh] min-h-[320px] overflow-hidden rounded-2xl"><TripMap events={events} /></section>}

      {tab === "docs" && (
        <section className="flex flex-col gap-2">
          <div className="flex shrink-0 justify-end"><Button size="sm" variant="secondary" onClick={openAdd} icon={<FilePlus className="h-3.5 w-3.5" />}>{t("trip.uploadConfirmation")}</Button></div>
          {(documents.data?.length ?? 0) === 0 ? <EmptyState icon={<FileText className="h-7 w-7" />} title={t("trip.noDocuments")} body={t("trip.noDocumentsBody")} /> : (
            <ul className="card divide-y divide-sand-100">
              {documents.data!.map((d) => (
                <li key={d.id}>
                  <Link to={`/inbox/${d.id}`} className="flex min-h-[54px] items-center justify-between gap-3 px-3.5 py-2.5 active:bg-sand-50">
                    <span className="flex min-w-0 items-center gap-3"><FileText className="h-4 w-4 shrink-0 text-ink-400" /><span className="truncate text-[14px]">{d.filename}</span></span>
                    <span className="flex shrink-0 items-center gap-2 text-[12px] text-ink-400"><StatusPill status={d.status} /><span className="hidden sm:inline">{relativeTime(d.created_at)}</span></span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      <Dialog open={sheet === "checks"} onOpenChange={(o) => !o && setSheet(null)} title={serious.length ? tp("trip.toCheck", serious.length) : t("trip.context")}>
        <div className="max-h-[68dvh] space-y-4 overflow-y-auto pb-2">
          {serious.length > 0 && <ConflictList conflicts={serious} tripId={tr.id} />}
          <TripContextCard tripId={tr.id} />
          {tz && <p className="text-[12px] text-ink-400">{t("trip.timesNote", { tz: tz.replace(/_/g, " ") })}</p>}
        </div>
      </Dialog>
      <Dialog open={sheet === "notes"} onOpenChange={(o) => !o && setSheet(null)} title={t("trip.tabNotes")} description={t("trip.notesHint")}>
        <textarea className="field min-h-[180px] leading-relaxed" value={notes ?? ""} onChange={(e) => setNotes(e.target.value)} onBlur={saveNotes} placeholder={t("trip.notesPlaceholder")} aria-label={t("trip.tabNotes")} />
      </Dialog>
      <Dialog open={sheet === "event" && !!picked} onOpenChange={(o) => { if (!o) { setSheet(null); setPicked(null); } }} title={picked?.title ?? ""}
        description={picked ? `${fmtDate(dayKey(picked.start_local), { weekday: true })} · ${fmtTime(picked.start_local)}${picked.end_local ? `–${fmtTime(picked.end_local)}` : ""}` : undefined}>
        {picked && <EventSheet e={picked} flags={all.filter((c) => c.event_ids.includes(picked.id)).map((c) => c.title)}
          onStatus={(s) => setStatus(picked, s)} onEdit={() => { setEditing(picked); setSheet(null); }} onDelete={() => remove(picked)} />}
      </Dialog>

      {editing && <EventDialog tripId={tr.id} event={editing === "new" ? null : editing} defaultTz={tz} defaultDay={current} onClose={() => setEditing(null)} />}
      {editingRes && <ReservationDialog tripId={tr.id} reservation={editingRes === "new" ? null : editingRes} defaultTz={tz} onClose={() => setEditingRes(null)} />}
    </div>
  );
}

function DayRow({ e, flags, onOpen }: { e: ItineraryEvent; flags: number; onOpen: () => void }) {
  const suggested = e.status === "suggested";
  const free = e.type === "free_time";
  return (
    <li>
      <button onClick={onOpen} className={clsx("flex min-h-[54px] w-full items-center gap-3 rounded-2xl border px-3 py-2 text-left transition active:scale-[0.99]",
        suggested ? "border-dashed border-violet-ink/35 bg-violet-soft/40" : free ? "border-dashed border-lagoon-500/30 bg-lagoon-50/40" : "border-sand-200/80 bg-white shadow-[var(--shadow-card)]",
        flags > 0 && "ring-1 ring-rose-ink/30", e.status === "cancelled" && "opacity-60")}>
        <span className="w-11 shrink-0 text-right text-[14px] font-semibold tabular-nums text-ink-900">{fmtTime(e.start_local)}</span>
        <EventIcon type={e.type} size="sm" />
        <span className="min-w-0 flex-1">
          <span className={clsx("block truncate text-[14px] font-medium text-ink-900", e.status === "cancelled" && "line-through")}>{e.title}</span>
          {(e.location_name || e.end_location_name) && <span className="block truncate text-[12px] text-ink-400">{e.location_name}{e.end_location_name ? ` → ${e.end_location_name}` : ""}</span>}
        </span>
        {flags > 0 && <AlertTriangle className="h-4 w-4 shrink-0 text-rose-ink" aria-hidden />}
        {e.status !== "confirmed" && <StatusPill status={e.status} />}
      </button>
    </li>
  );
}

function EventSheet({ e, flags, onStatus, onEdit, onDelete }: { e: ItineraryEvent; flags: string[]; onStatus: (s: string) => void; onEdit: () => void; onDelete: () => void }) {
  const { t } = useT();
  const editable = !e.reservation_id;
  return (
    <div className="space-y-3 pb-2">
      <div className="flex flex-wrap items-center gap-2"><StatusPill status={e.status} />{e.details?.booking_reference && <Badge tone="neutral">{t("timeline.ref")} {e.details.booking_reference}</Badge>}</div>
      {(e.location_name || e.end_location_name) && <p className="text-[14px] text-ink-600">{e.location_name}{e.end_location_name ? ` → ${e.end_location_name}` : ""}</p>}
      {e.notes && <p className="text-[13.5px] text-ink-500">{e.notes}</p>}
      {flags.map((f) => <p key={f} className="flex items-start gap-1.5 rounded-lg bg-amber-soft px-2.5 py-1.5 text-[13px] text-amber-ink"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />{f}</p>)}
      <div className="flex flex-wrap gap-2 pt-1">
        {e.status === "suggested" && <Button size="sm" onClick={() => onStatus("unbooked")} icon={<Check className="h-3.5 w-3.5" />}>{t("timeline.keep")}</Button>}
        {e.status !== "completed" && e.status !== "suggested" && <Button size="sm" variant="secondary" onClick={() => onStatus("completed")} icon={<Check className="h-3.5 w-3.5" />}>{t("timeline.complete")}</Button>}
        <Button size="sm" variant="secondary" onClick={onEdit} icon={<Pencil className="h-3.5 w-3.5" />}>{editable ? t("common.edit") : t("timeline.editNotes")}</Button>
        {editable && <Button size="sm" variant="ghost" onClick={onDelete} icon={e.status === "suggested" ? <X className="h-3.5 w-3.5" /> : <Trash2 className="h-3.5 w-3.5" />}>{e.status === "suggested" ? t("timeline.dismiss") : t("common.delete")}</Button>}
      </div>
    </div>
  );
}
