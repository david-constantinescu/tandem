import { clsx } from "clsx";
import { Accessibility, Bookmark, CalendarCheck, CalendarX, Clock, ExternalLink, MapPin, Star } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, Button, ErrorNote } from "@/components/ui";
import { Dialog } from "@/components/ui/Dialog";
import { useToast } from "@/components/ui/Toast";
import { api, errorMessage } from "@/lib/api";
import { duration, fmtDate, money } from "@/lib/format";
import { useInvalidateTripData } from "@/lib/queries";
import type { Action, ActivityResult } from "@/lib/types";
import { ActionCard } from "./ActionCard";

export function ActivityCard({ a, tripId, date }: { a: ActivityResult; tripId?: string; date?: string | null }) {
  const [open, setOpen] = useState(false);
  const toast = useToast();
  const fit = a.fits?.status;
  const save = async () => {
    try {
      await api.post("/activities/saved", { provider: a.provider, provider_item_id: a.provider_item_id, trip_id: tripId, data: a });
      toast("Saved for later", "success");
    } catch (e) {
      toast(errorMessage(e), "error");
    }
  };
  return (
    <article className="card flex w-full flex-col rounded-[22px] p-4 sm:p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="eyebrow">{a.categories?.[0] ?? "Activity"}</p>
          <h3 className="display mt-1 text-[19px] leading-snug text-ink-900">{a.title}</h3>
        </div>
        {a.price !== null ? (
          <div className="shrink-0 text-right">
            <p className="text-[16px] font-semibold text-ink-900">{a.price === 0 ? "Free" : money(a.price, a.currency)}</p>
            {a.price_basis && a.price !== 0 && <p className="whitespace-nowrap text-[11.5px] text-ink-400">{a.price_basis.replace("_", " ")}</p>}
          </div>
        ) : <p className="text-[12px] text-ink-400">Price unknown</p>}
      </div>
      {a.description && <p className="mt-2 line-clamp-2 text-[13.5px] text-ink-500">{a.description}</p>}
      <div className="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-[12.5px] text-ink-500">
        {a.duration_minutes && <span className="inline-flex items-center gap-1"><Clock className="h-3.5 w-3.5" />{duration(a.duration_minutes)}</span>}
        {a.distance_km !== null && <span className="inline-flex items-center gap-1"><MapPin className="h-3.5 w-3.5" />{a.distance_km} km from your stay</span>}
        {a.rating && <span className="inline-flex items-center gap-1"><Star className="h-3.5 w-3.5" />{a.rating.toFixed(1)}{a.review_count ? ` (${a.review_count})` : ""}</span>}
        {a.accessible && <span className="inline-flex items-center gap-1"><Accessibility className="h-3.5 w-3.5" />Step-free</span>}
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {fit === "fits" && <Badge tone="lagoon" icon={<CalendarCheck className="h-3 w-3" />}>Fits your free time · {a.fits.slots?.slice(0, 3).map((s) => s.time).join(", ")}</Badge>}
        {fit === "no_fitting_slot" && <Badge tone="amber" icon={<CalendarX className="h-3 w-3" />}>No slot fits your plans</Badge>}
        {!a.availability_checked && <Badge tone="neutral">Availability not checked</Badge>}
        {a.simulated && <Badge tone="violet">Simulated</Badge>}
      </div>
      {a.opening_hours_text && <p className="mt-2 text-[12px] text-ink-400">Listed hours (unverified): {a.opening_hours_text}</p>}
      <p className="mt-3 text-[11.5px] text-ink-400">{a.source_label}{a.attribution ? ` · ${a.attribution}` : ""}</p>
      <div className="mt-auto flex flex-wrap gap-2 pt-4">
        {a.bookable_via_api ? (
          <Button size="sm" onClick={() => setOpen(true)} icon={<CalendarCheck className="h-3.5 w-3.5" />}>Prepare booking</Button>
        ) : a.booking_url ? (
          <a href={a.booking_url} target="_blank" rel="noopener noreferrer nofollow"
            className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-sand-200 bg-white px-3 text-[13px] font-medium text-ink-800 transition active:scale-[0.97] hover:bg-sand-50 pointer-coarse:h-10 pointer-coarse:px-3.5 pointer-coarse:text-[14px]">
            {a.provider === "osm" ? "Official website" : "View on provider"} <ExternalLink className="h-3.5 w-3.5" />
          </a>
        ) : null}
        <Button size="sm" variant="ghost" onClick={save} icon={<Bookmark className="h-3.5 w-3.5" />}>Save</Button>
      </div>
      {open && <BookingDialog a={a} tripId={tripId} date={date} onClose={() => setOpen(false)} />}
    </article>
  );
}

function BookingDialog({ a, tripId, date, onClose }: { a: ActivityResult; tripId?: string; date?: string | null; onClose: () => void }) {
  const slots = (a.fits?.slots?.length ? a.fits.slots : a.available_slots ?? []).filter((s) => s.remaining > 0);
  const [slot, setSlot] = useState(slots[0] ? `${slots[0].date}|${slots[0].time}` : "");
  const [manualDate, setManualDate] = useState(date ?? "");
  const [participants, setParticipants] = useState(2);
  const [action, setAction] = useState<Action | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const invalidate = useInvalidateTripData();
  const prepare = async () => {
    setBusy(true);
    setError(null);
    const [d, t] = slot ? slot.split("|") : [manualDate, undefined];
    try {
      const res = await api.post<Action>("/activities/proposals", { provider: a.provider, provider_item_id: a.provider_item_id, date: d, time: t, participants, trip_id: tripId });
      setAction(res);
      invalidate();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={action ? "Review and approve" : `Book ${a.title}`}
      description={action ? "Tandem checked live availability and price. Nothing is booked until you approve." : "Pick a time. Tandem will get a live quote first."} wide>
      {action ? (
        <ActionCardLive initial={action} />
      ) : (
        <div className="space-y-4">
          {slots.length > 0 ? (
            <fieldset>
              <legend className="label">Available times{a.fits?.status === "fits" ? " that fit your itinerary" : ""}</legend>
              <div className="flex flex-wrap gap-2">
                {slots.slice(0, 12).map((s) => {
                  const v = `${s.date}|${s.time}`;
                  return (
                    <button key={v} type="button" onClick={() => setSlot(v)}
                      className={clsx("min-h-11 rounded-xl border px-3 py-2 text-left text-[13px] transition active:scale-95", slot === v ? "border-lagoon-500 bg-lagoon-50 text-lagoon-700" : "border-sand-200 hover:border-sand-300")}>
                      <span className="block font-medium">{s.time}</span>
                      <span className="block text-[11.5px] text-ink-400">{fmtDate(s.date)} · {s.remaining} left</span>
                    </button>
                  );
                })}
              </div>
            </fieldset>
          ) : (
            <div>
              <label className="label" htmlFor="bdate">Date</label>
              <input id="bdate" type="date" className="field" value={manualDate} onChange={(e) => setManualDate(e.target.value)} />
            </div>
          )}
          <div className="max-w-[160px]">
            <label className="label" htmlFor="ppl">People</label>
            <input id="ppl" type="number" min={1} max={20} className="field" value={participants} onChange={(e) => setParticipants(Math.max(1, +e.target.value))} />
          </div>
          {error && <ErrorNote>{error}</ErrorNote>}
          <div className="flex justify-end gap-2 pb-2">
            <Button variant="ghost" onClick={onClose}>Cancel</Button>
            <Button onClick={prepare} loading={busy} disabled={!slot && !manualDate}>Get live quote</Button>
          </div>
        </div>
      )}
    </Dialog>
  );
}

function ActionCardLive({ initial }: { initial: Action }) {
  // Follows the action after approval (in progress → completed/failed) so the dialog shows the verified outcome.
  const q = useQuery({
    queryKey: ["approvals", "one", initial.id],
    queryFn: () => api.get<Action>(`/approvals/${initial.id}`),
    initialData: initial,
    refetchInterval: (query) => (query.state.data?.status === "in_progress" ? 1000 : false),
  });
  return <ActionCard action={q.data} />;
}
