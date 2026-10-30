import { useState, type FormEvent } from "react";
import { Button, ErrorNote, Field, InfoNote } from "@/components/ui";
import { Dialog } from "@/components/ui/Dialog";
import { api, errorMessage } from "@/lib/api";
import { useInvalidateTripData } from "@/lib/queries";
import type { ItineraryEvent, Reservation } from "@/lib/types";

const EVENT_TYPES = ["activity", "tour", "museum", "restaurant", "meeting", "free_time", "travel_time", "reminder", "custom"];
const RES_TYPES = ["flight", "train", "bus", "hotel", "car_rental", "activity", "tour", "museum", "restaurant", "transfer", "ferry", "event", "other"];

const local = (s: string | null | undefined) => (s ? s.slice(0, 16) : "");

export function EventDialog({ tripId, event, defaultTz, onClose }: { tripId: string; event?: ItineraryEvent | null; defaultTz?: string | null; onClose: () => void }) {
  const owned = !!event?.reservation_id;
  const [form, setForm] = useState({
    title: event?.title ?? "", type: event?.type ?? "activity", status: event?.status ?? "unbooked",
    start_local: local(event?.start_local), end_local: local(event?.end_local), start_tz: event?.start_tz ?? defaultTz ?? "",
    location_name: event?.location_name ?? "", address: event?.address ?? "", notes: event?.notes ?? "",
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const invalidate = useInvalidateTripData();
  const set = (k: keyof typeof form) => (e: any) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (event) {
        const body = owned ? { notes: form.notes } : { ...form, end_local: form.end_local || null };
        await api.patch(`/itinerary/events/${event.id}`, body);
      } else {
        await api.post("/itinerary/events", { ...form, trip_id: tripId, end_local: form.end_local || null, start_tz: form.start_tz || null });
      }
      invalidate();
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={event ? "Edit event" : "Add to itinerary"}
      description={owned ? "Times come from the booking. Edit the reservation to change them." : "Times are local to the event's timezone."}>
      <form onSubmit={submit} className="space-y-4">
        {owned ? (
          <InfoNote>{event!.title}</InfoNote>
        ) : (
          <>
            <Field label="Title" htmlFor="et"><input id="et" required className="field" value={form.title} onChange={set("title")} /></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Type" htmlFor="ety">
                <select id="ety" className="field" value={form.type} onChange={set("type")}>{EVENT_TYPES.map((t) => <option key={t} value={t}>{t.replace("_", " ")}</option>)}</select>
              </Field>
              <Field label="Status" htmlFor="est">
                <select id="est" className="field" value={form.status} onChange={set("status")}>
                  <option value="unbooked">Not booked</option><option value="pending">Pending</option>
                  <option value="confirmed">Confirmed (booked myself)</option><option value="completed">Completed</option>
                  {event?.status === "suggested" && <option value="suggested">Suggestion</option>}
                </select>
              </Field>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Starts" htmlFor="es"><input id="es" type="datetime-local" required className="field" value={form.start_local} onChange={set("start_local")} /></Field>
              <Field label="Ends" htmlFor="ee"><input id="ee" type="datetime-local" className="field" value={form.end_local} min={form.start_local} onChange={set("end_local")} /></Field>
            </div>
            <Field label="Timezone" htmlFor="etz" hint="IANA name, e.g. Europe/Rome"><input id="etz" className="field" value={form.start_tz} onChange={set("start_tz")} /></Field>
            <Field label="Place" htmlFor="el"><input id="el" className="field" value={form.location_name} onChange={set("location_name")} /></Field>
            <Field label="Address" htmlFor="ea"><input id="ea" className="field" value={form.address} onChange={set("address")} /></Field>
          </>
        )}
        <Field label="Notes" htmlFor="en"><textarea id="en" rows={3} className="field" value={form.notes} onChange={set("notes")} /></Field>
        {error && <ErrorNote>{error}</ErrorNote>}
        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" loading={busy}>Save</Button>
        </div>
      </form>
    </Dialog>
  );
}

export function ReservationDialog({ tripId, reservation, defaultTz, onClose }: { tripId: string; reservation?: Reservation | null; defaultTz?: string | null; onClose: () => void }) {
  const [form, setForm] = useState({
    type: reservation?.type ?? "activity", title: reservation?.title ?? "", status: reservation?.status ?? "confirmed",
    provider_name: reservation?.provider_name ?? "", booking_reference: reservation?.booking_reference ?? "",
    start_local: local(reservation?.start_local), start_tz: reservation?.start_tz ?? defaultTz ?? "",
    end_local: local(reservation?.end_local), end_tz: reservation?.end_tz ?? defaultTz ?? "",
    address: reservation?.address ?? "", city: reservation?.city ?? "", price: reservation?.price?.toString() ?? "",
    currency: reservation?.currency ?? "EUR", cancellation_policy: reservation?.cancellation_policy ?? "",
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const invalidate = useInvalidateTripData();
  const set = (k: keyof typeof form) => (e: any) => setForm({ ...form, [k]: e.target.value });
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body: Record<string, any> = Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v === "" ? null : v]));
    body.price = form.price ? Number(form.price) : null;
    try {
      if (reservation) await api.patch(`/reservations/${reservation.id}`, body);
      else await api.post("/reservations", { ...body, trip_id: tripId });
      invalidate();
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    if (!reservation || !confirm("Remove this reservation from Tandem? The booking with the provider is not cancelled.")) return;
    await api.del(`/reservations/${reservation.id}`);
    invalidate();
    onClose();
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={reservation ? "Edit reservation" : "Add a reservation"} wide
      description="For bookings you made elsewhere. Uploading the confirmation instead keeps the source document.">
      <form onSubmit={submit} className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Type" htmlFor="rt"><select id="rt" className="field" value={form.type} onChange={set("type")} disabled={!!reservation}>{RES_TYPES.map((t) => <option key={t} value={t}>{t.replace("_", " ")}</option>)}</select></Field>
          <div className="sm:col-span-2"><Field label="Title" htmlFor="rti"><input id="rti" required className="field" value={form.title} onChange={set("title")} /></Field></div>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Status" htmlFor="rs"><select id="rs" className="field" value={form.status} onChange={set("status")}><option value="confirmed">Confirmed</option><option value="pending">Pending</option><option value="unknown">Unconfirmed</option><option value="cancelled">Cancelled</option></select></Field>
          <Field label="Provider" htmlFor="rp"><input id="rp" className="field" value={form.provider_name} onChange={set("provider_name")} /></Field>
          <Field label="Booking reference" htmlFor="rr"><input id="rr" className="field font-mono" value={form.booking_reference} onChange={set("booking_reference")} /></Field>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Starts (local)" htmlFor="rsl"><input id="rsl" type="datetime-local" className="field" value={form.start_local} onChange={set("start_local")} /></Field>
          <Field label="Start timezone" htmlFor="rstz"><input id="rstz" className="field" value={form.start_tz} onChange={set("start_tz")} placeholder="Europe/Rome" /></Field>
          <Field label="Ends (local)" htmlFor="rel"><input id="rel" type="datetime-local" className="field" value={form.end_local} onChange={set("end_local")} /></Field>
          <Field label="End timezone" htmlFor="retz"><input id="retz" className="field" value={form.end_tz} onChange={set("end_tz")} /></Field>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="sm:col-span-2"><Field label="Address" htmlFor="ra"><input id="ra" className="field" value={form.address} onChange={set("address")} /></Field></div>
          <Field label="City" htmlFor="rc"><input id="rc" className="field" value={form.city} onChange={set("city")} /></Field>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Price" htmlFor="rpr"><input id="rpr" type="number" step="0.01" min="0" className="field" value={form.price} onChange={set("price")} /></Field>
          <Field label="Currency" htmlFor="rcu"><input id="rcu" maxLength={3} className="field uppercase" value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })} /></Field>
        </div>
        <Field label="Cancellation policy" htmlFor="rcp"><input id="rcp" className="field" value={form.cancellation_policy} onChange={set("cancellation_policy")} /></Field>
        {error && <ErrorNote>{error}</ErrorNote>}
        <div className="flex flex-wrap justify-between gap-2 pt-1">
          {reservation ? <Button type="button" variant="danger" onClick={remove}>Remove</Button> : <span />}
          <div className="flex gap-2"><Button type="button" variant="ghost" onClick={onClose}>Cancel</Button><Button type="submit" loading={busy}>Save</Button></div>
        </div>
      </form>
    </Dialog>
  );
}
