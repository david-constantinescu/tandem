import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Button, ErrorNote, Field } from "@/components/ui";
import { Dialog } from "@/components/ui/Dialog";
import { api, errorMessage } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { useInvalidateTripData } from "@/lib/queries";
import type { Trip } from "@/lib/types";

export function NewTripDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const [name, setName] = useState("");
  const [dest, setDest] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const invalidate = useInvalidateTripData();
  const { t } = useT();
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const trip = await api.post<Trip>("/trips", { name, primary_destination: dest || null, start_date: start || null, end_date: end || null });
      invalidate();
      onOpenChange(false);
      navigate(`/trips/${trip.id}`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={t("newTrip.title")} description={t("newTrip.hint")}>
      <form onSubmit={submit} className="space-y-4">
        <Field label={t("newTrip.name")} htmlFor="tn"><input id="tn" required className="field" value={name} onChange={(e) => setName(e.target.value)} placeholder={t("newTrip.namePlaceholder")} /></Field>
        <Field label={t("newTrip.destination")} htmlFor="td"><input id="td" className="field" value={dest} onChange={(e) => setDest(e.target.value)} placeholder={t("newTrip.destinationPlaceholder")} /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("newTrip.start")} htmlFor="ts"><input id="ts" type="date" className="field" value={start} onChange={(e) => setStart(e.target.value)} /></Field>
          <Field label={t("newTrip.end")} htmlFor="te"><input id="te" type="date" className="field" value={end} min={start} onChange={(e) => setEnd(e.target.value)} /></Field>
        </div>
        {error && <ErrorNote>{error}</ErrorNote>}
        <div className="flex justify-end gap-2 pb-2 pt-2">
          <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>{t("common.cancel")}</Button>
          <Button type="submit" loading={busy}>{t("newTrip.submit")}</Button>
        </div>
      </form>
    </Dialog>
  );
}
