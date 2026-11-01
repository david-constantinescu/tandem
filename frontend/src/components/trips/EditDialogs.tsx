import { useState, type FormEvent } from "react";
import { Button, ErrorNote, Field, InfoNote, useTypeLabel } from "@/components/ui";
import { useT } from "@/lib/i18n";
import { Dialog } from "@/components/ui/Dialog";
import { api, errorMessage } from "@/lib/api";
import { useInvalidateTripData } from "@/lib/queries";
import type { ItineraryEvent, Reservation } from "@/lib/types";

const EVENT_TYPES = ["activity", "tour", "museum", "restaurant", "meeting", "free_time", "travel_time", "reminder", "custom"];
const RES_TYPES = ["flight", "train", "bus", "hotel", "car_rental", "activity", "tour", "museum", "restaurant", "transfer", "ferry", "event", "other"];

const local = (s: string | null | undefined) => (s ? s.slice(0, 16) : "");

export function EventDialog({ tripId, event, defaultTz, defaultDay, onClose }: { tripId: string; event?: ItineraryEvent | null; defaultTz?: string | null; defaultDay?: string | null; onClose: () => void }) {
  const owned = !!event?.reservation_id;
  const [form, setForm] = useState({
    title: event?.title ?? "", type: event?.type ?? "activity", status: event?.status ?? "unbooked",
    start_local: event ? local(event.start_local) : defaultDay ? `${defaultDay}T10:00` : "", end_local: event ? local(event.end_local) : defaultDay ? `${defaultDay}T11:00` : "", start_tz: event?.start_tz ?? defaultTz ?? "",
    location_name: event?.location_name ?? "", address: event?.address ?? "", notes: event?.notes ?? "",
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const invalidate = useInvalidateTripData();
  const { t } = useT();
  const typeLabel = useTypeLabel();
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
    <Dialog open onOpenChange={(o) => !o && onClose()} title={event ? t("event.editTitle") : t("event.addTitle")}
      description={owned ? t("event.ownedHint") : t("event.hint")}>
      <form onSubmit={submit} className="space-y-4">
        {owned ? (
          <InfoNote>{event!.title}</InfoNote>
        ) : (
          <>
            <Field label={t("event.title")} htmlFor="et"><input id="et" required className="field" value={form.title} onChange={set("title")} /></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label={t("event.type")} htmlFor="ety">
                <select id="ety" className="field" value={form.type} onChange={set("type")}>{EVENT_TYPES.map((x) => <option key={x} value={x}>{typeLabel(x)}</option>)}</select>
              </Field>
              <Field label={t("event.status")} htmlFor="est">
                <select id="est" className="field" value={form.status} onChange={set("status")}>
                  <option value="unbooked">{t("status.unbooked")}</option><option value="pending">{t("status.pending")}</option>
                  <option value="confirmed">{t("event.confirmedMyself")}</option><option value="completed">{t("status.completed")}</option>
                  {event?.status === "suggested" && <option value="suggested">{t("status.suggested")}</option>}
                </select>
              </Field>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label={t("event.starts")} htmlFor="es"><input id="es" type="datetime-local" required className="field" value={form.start_local} onChange={set("start_local")} /></Field>
              <Field label={t("event.ends")} htmlFor="ee"><input id="ee" type="datetime-local" className="field" value={form.end_local} min={form.start_local} onChange={set("end_local")} /></Field>
            </div>
            <Field label={t("event.timezone")} htmlFor="etz" hint={t("event.timezoneHint")}><input id="etz" className="field" value={form.start_tz} onChange={set("start_tz")} /></Field>
            <Field label={t("event.place")} htmlFor="el"><input id="el" className="field" value={form.location_name} onChange={set("location_name")} /></Field>
            <Field label={t("res.address")} htmlFor="ea"><input id="ea" className="field" value={form.address} onChange={set("address")} /></Field>
          </>
        )}
        <Field label={t("event.notes")} htmlFor="en"><textarea id="en" rows={3} className="field" value={form.notes} onChange={set("notes")} /></Field>
        {error && <ErrorNote>{error}</ErrorNote>}
        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
          <Button type="submit" loading={busy}>{t("common.save")}</Button>
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
  const { t } = useT();
  const typeLabel = useTypeLabel();
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
    if (!reservation || !confirm(t("res.removeConfirm"))) return;
    await api.del(`/reservations/${reservation.id}`);
    invalidate();
    onClose();
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={reservation ? t("res.editTitle") : t("res.addTitle")} wide
      description={t("res.addHint")}>
      <form onSubmit={submit} className="space-y-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Field label={t("event.type")} htmlFor="rt"><select id="rt" className="field" value={form.type} onChange={set("type")} disabled={!!reservation}>{RES_TYPES.map((x) => <option key={x} value={x}>{typeLabel(x)}</option>)}</select></Field>
          <div className="sm:col-span-2"><Field label={t("event.title")} htmlFor="rti"><input id="rti" required className="field" value={form.title} onChange={set("title")} /></Field></div>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Field label={t("event.status")} htmlFor="rs"><select id="rs" className="field" value={form.status} onChange={set("status")}>{["confirmed", "pending", "unknown", "cancelled"].map((x) => <option key={x} value={x}>{t(`status.${x}` as "status.confirmed")}</option>)}</select></Field>
          <Field label={t("res.provider")} htmlFor="rp"><input id="rp" className="field" value={form.provider_name} onChange={set("provider_name")} /></Field>
          <Field label={t("res.reference")} htmlFor="rr"><input id="rr" className="field font-mono" value={form.booking_reference} onChange={set("booking_reference")} /></Field>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label={t("res.startsLocal")} htmlFor="rsl"><input id="rsl" type="datetime-local" className="field" value={form.start_local} onChange={set("start_local")} /></Field>
          <Field label={t("res.startTz")} htmlFor="rstz"><input id="rstz" className="field" value={form.start_tz} onChange={set("start_tz")} placeholder="Europe/Rome" /></Field>
          <Field label={t("res.endsLocal")} htmlFor="rel"><input id="rel" type="datetime-local" className="field" value={form.end_local} onChange={set("end_local")} /></Field>
          <Field label={t("res.endTz")} htmlFor="retz"><input id="retz" className="field" value={form.end_tz} onChange={set("end_tz")} /></Field>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="sm:col-span-2"><Field label={t("res.address")} htmlFor="ra"><input id="ra" className="field" value={form.address} onChange={set("address")} /></Field></div>
          <Field label={t("res.city")} htmlFor="rc"><input id="rc" className="field" value={form.city} onChange={set("city")} /></Field>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Field label={t("res.price")} htmlFor="rpr"><input id="rpr" type="number" step="0.01" min="0" className="field" value={form.price} onChange={set("price")} /></Field>
          <Field label={t("res.currency")} htmlFor="rcu"><input id="rcu" maxLength={3} className="field uppercase" value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })} /></Field>
        </div>
        <Field label={t("res.cancellationPolicy")} htmlFor="rcp"><input id="rcp" className="field" value={form.cancellation_policy} onChange={set("cancellation_policy")} /></Field>
        {error && <ErrorNote>{error}</ErrorNote>}
        <div className="flex flex-wrap justify-between gap-2 pt-1">
          {reservation ? <Button type="button" variant="danger" onClick={remove}>{t("common.remove")}</Button> : <span />}
          <div className="flex gap-2"><Button type="button" variant="ghost" onClick={onClose}>{t("common.cancel")}</Button><Button type="submit" loading={busy}>{t("common.save")}</Button></div>
        </div>
      </form>
    </Dialog>
  );
}
