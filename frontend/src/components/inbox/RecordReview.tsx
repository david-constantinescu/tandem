import { clsx } from "clsx";
import { AlertTriangle, ArrowRight, Check, CircleHelp, Quote, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { EventIcon } from "@/components/trips/EventIcon";
import { Badge, Button, Confidence, ErrorNote, InfoNote, useStatusLabel, useTypeLabel } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { api, errorMessage } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { useT, type Key } from "@/lib/i18n";
import { useInvalidateTripData, useTrips } from "@/lib/queries";
import type { ExtractedField, ExtractedRecord, ReservationChange } from "@/lib/types";

const EDITABLE: { key: string; label: Key; type?: string; detail?: boolean; wide?: boolean }[] = [
  { key: "title", label: "event.title", wide: true },
  { key: "provider_name", label: "res.provider" },
  { key: "booking_reference", label: "res.reference" },
  { key: "start_local", label: "res.startsLocal", type: "datetime-local" },
  { key: "end_local", label: "res.endsLocal", type: "datetime-local" },
  { key: "start_tz", label: "event.timezone" },
  { key: "status", label: "event.status" },
  { key: "origin", label: "review.from" },
  { key: "destination", label: "review.to" },
  { key: "address", label: "res.address", wide: true },
  { key: "city", label: "res.city" },
  { key: "price", label: "res.price", type: "number" },
  { key: "currency", label: "res.currency" },
  { key: "flight_number", label: "res.flight", detail: true },
  { key: "seat", label: "res.seat", detail: true },
  { key: "terminal", label: "res.terminal", detail: true },
  { key: "room_type", label: "res.room", detail: true },
  { key: "party_size", label: "common.people", detail: true, type: "number" },
  { key: "meeting_point", label: "res.meetingPoint", detail: true, wide: true },
];

const MARKS: Record<string, { tone: any; icon: any; text: Key }> = {
  evidence_found: { tone: "lagoon", icon: Check, text: "review.mark.found" },
  user_confirmed: { tone: "lagoon", icon: Check, text: "review.mark.confirmed" },
  user_corrected: { tone: "neutral", icon: Check, text: "review.mark.corrected" },
  derived: { tone: "lagoon", icon: Check, text: "review.mark.derived" },
  not_found_in_source: { tone: "rose", icon: AlertTriangle, text: "review.mark.notFound" },
  no_source_text: { tone: "neutral", icon: CircleHelp, text: "review.mark.noText" },
};

function VerificationMark({ f }: { f?: ExtractedField }) {
  const { t } = useT();
  const m = f && MARKS[f.verification];
  if (!m) return null;
  return <Badge tone={m.tone} icon={<m.icon className="h-3 w-3" />}>{t(m.text)}</Badge>;
}

export function RecordReview({ record, documentId }: { record: ExtractedRecord; documentId: string }) {
  const trips = useTrips();
  const toast = useToast();
  const invalidate = useInvalidateTripData();
  const { t } = useT();
  const typeLabel = useTypeLabel();
  const statusLabel = useStatusLabel();
  const data = record.data;
  const fieldsByName = useMemo(() => Object.fromEntries(record.fields.map((f) => [f.field, f])), [record.fields]);
  const initial = useMemo(() => {
    const out: Record<string, string> = {};
    for (const f of EDITABLE) {
      const v = f.detail ? data.details?.[f.key] : data[f.key];
      out[f.key] = v === null || v === undefined ? "" : String(f.type === "datetime-local" ? String(v).slice(0, 16) : v);
    }
    return out;
  }, [data]);
  const [values, setValues] = useState(initial);
  const [editing, setEditing] = useState(false);
  const proposal = record.grouping;
  const suggested = proposal?.action === "join" && proposal.trip_id ? proposal.trip_id : "__suggested_new";
  const [tripChoice, setTripChoice] = useState<string>(suggested);
  const [touched, setTouched] = useState(false);
  const [newName, setNewName] = useState(proposal?.new_trip?.name ?? "");
  // propunerile se reimprospateaza pe server cand alte inregistrari creeaza calatorii; le urmarim pana alege omul
  useEffect(() => {
    if (!touched) {
      setTripChoice(suggested);
      setNewName(proposal?.new_trip?.name ?? "");
    }
  }, [suggested, touched, proposal?.new_trip?.name]);
  const [busy, setBusy] = useState<"accept" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pending = record.status === "pending_review";

  const relevant = EDITABLE.filter((f) => initial[f.key] !== "" || editing);
  const changed = Object.fromEntries(Object.entries(values).filter(([k, v]) => v !== initial[k]).map(([k, v]) => {
    const def = EDITABLE.find((f) => f.key === k)!;
    return [k, v === "" ? null : def.type === "number" ? Number(v) : v];
  }));

  const decide = async (decision: "accept" | "reject") => {
    setBusy(decision);
    setError(null);
    const body: Record<string, any> = { record_id: record.id, decision, corrections: changed };
    if (tripChoice === "__none") body.no_trip = true;
    else if (tripChoice === "__suggested_new") {
      // pastram sugestia Tandem: serverul regrupeaza la acceptare, deci o calatorie creata cu cateva clipe
      // in urma (de ex. din zborul de dus) se uneste, nu se dubleaza. O calatorie redenumita e alegere explicita
      if (newName && newName !== proposal?.new_trip?.name) body.new_trip_name = newName;
    } else if (tripChoice === "__new") body.new_trip_name = newName || t("review.newTripDefault");
    else body.trip_id = tripChoice;
    try {
      await api.post(`/inbox/${documentId}/review`, { decisions: [body] });
      toast(decision === "accept" ? t("review.added") : t("review.dismissed"), decision === "accept" ? "success" : "info");
      invalidate();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <article className={clsx("card overflow-hidden", !pending && "opacity-90")}>
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-sand-100 px-5 py-4">
        <div className="flex min-w-0 gap-3">
          <EventIcon type={record.record_type} />
          <div className="min-w-0">
            <p className="eyebrow">{typeLabel(record.record_type)}{data.provider_name ? ` · ${data.provider_name}` : ""}</p>
            <h3 className="mt-0.5 text-[16px] font-semibold">{data.title}</h3>
            <p className="mt-0.5 text-[13px] text-ink-500">{fmtDateTime(data.start_local)}{data.end_local ? ` → ${fmtDateTime(data.end_local)}` : ""}</p>
          </div>
        </div>
        <div className="flex flex-col items-end gap-1.5">
          {record.status === "accepted" ? <Badge tone="lagoon">{t("review.badgeAdded")}</Badge> : record.status === "rejected" ? <Badge>{t("review.badgeDismissed")}</Badge> : record.status === "change_detected" ? <Badge tone="amber">{t("review.badgeUpdate")}</Badge> : <Badge tone="amber">{t("review.badgeReview")}</Badge>}
          <Confidence value={record.confidence} />
        </div>
      </div>

      {record.status === "change_detected" && record.matched_reservation_id ? (
        <ChangeReview reservationId={record.matched_reservation_id} documentId={documentId} />
      ) : (
        <div className="px-5 py-4">
          {record.uncertainty_notes.length > 0 && pending && (
            <div className="mb-4 space-y-1.5">
              {record.uncertainty_notes.map((n) => <p key={n} className="flex gap-2 text-[13px] text-amber-ink"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />{n}</p>)}
            </div>
          )}
          <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2">
            {relevant.map((f) => {
              const fld = fieldsByName[f.key];
              return (
                <div key={f.key} className={clsx(f.wide && "sm:col-span-2")}>
                  <dt className="mb-1 flex flex-wrap items-center gap-2 text-[12.5px] text-ink-400">{t(f.label)} <VerificationMark f={fld} /></dt>
                  <dd>
                    {editing && pending ? (
                      f.key === "status" ? (
                        <select className="field" value={values[f.key]} onChange={(e) => setValues({ ...values, [f.key]: e.target.value })}>
                          {["confirmed", "pending", "unknown", "cancelled"].map((x) => <option key={x} value={x}>{statusLabel(x)}</option>)}
                        </select>
                      ) : (
                        <input className="field" type={f.type ?? "text"} value={values[f.key]} onChange={(e) => setValues({ ...values, [f.key]: e.target.value })} />
                      )
                    ) : (
                      <span className={clsx("text-[14px] text-ink-800", f.key === "booking_reference" && "font-mono")}>
                        {f.type === "datetime-local" ? fmtDateTime(values[f.key]) : f.key === "status" && values[f.key] ? statusLabel(values[f.key]) : values[f.key] || "—"}
                      </span>
                    )}
                    {fld?.evidence && !editing && (
                      <p className="mt-1 flex gap-1.5 text-[12px] text-ink-400"><Quote className="mt-0.5 h-3 w-3 shrink-0" /><span className="line-clamp-2">“{fld.evidence}”{fld.source_page ? ` · p.${fld.source_page}` : ""}</span></p>
                    )}
                  </dd>
                </div>
              );
            })}
          </dl>

          {pending && (
            <div className="mt-5 rounded-xl bg-sand-50 p-4">
              <label htmlFor={`trip-${record.id}`} className="label">{t("review.addToTrip")}</label>
              <select id={`trip-${record.id}`} className="field" value={tripChoice} onChange={(e) => { setTouched(true); setTripChoice(e.target.value); }}>
                {proposal?.action === "join" && proposal.trip_id && <option value={proposal.trip_id}>{t("review.suggested", { name: proposal.trip_name ?? "" })}</option>}
                {proposal?.action === "create" && <option value="__suggested_new">{t("review.suggestedNew", { name: proposal.new_trip?.name ?? "" })}</option>}
                {(trips.data ?? []).filter((x) => x.id !== proposal?.trip_id).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
                <option value="__new">{t("review.newTrip")}</option>
                <option value="__none">{t("review.noTrip")}</option>
              </select>
              {(tripChoice === "__new" || tripChoice === "__suggested_new") && (
                <input className="field mt-2" value={newName} onChange={(e) => { setTouched(true); setNewName(e.target.value); }} placeholder={t("newTrip.name")} aria-label={t("newTrip.name")} />
              )}
              {proposal?.reasons?.length ? <p className="mt-2 text-[12.5px] text-ink-500">{t("review.why")} {proposal.reasons.join(" · ")}</p> : null}
            </div>
          )}
          {error && <div className="mt-3"><ErrorNote>{error}</ErrorNote></div>}
          {pending ? (
            <div className="mt-4 grid grid-cols-2 gap-2 sm:flex sm:flex-wrap sm:items-center">
              <Button onClick={() => decide("accept")} loading={busy === "accept"} className="col-span-2" icon={<Check className="h-4 w-4" />}>
                {Object.keys(changed).length ? t("review.saveAdd") : t("review.looksRight")}
              </Button>
              <Button variant="secondary" onClick={() => setEditing(!editing)}>{editing ? t("review.doneEditing") : t("review.correct")}</Button>
              <Button variant="ghost" onClick={() => decide("reject")} loading={busy === "reject"} icon={<X className="h-4 w-4" />}>{t("review.notBooking")}</Button>
            </div>
          ) : record.reservation_id && (
            <p className="mt-4 text-[13px] text-ink-500">{t("review.addedAs")}{record.grouping?.applied?.trip_id ? <> <Link className="text-lagoon-600 hover:underline" to={`/trips/${record.grouping.applied.trip_id}`}>{t("review.openTrip")}</Link></> : ""}</p>
          )}
          <p className="mt-4 text-[11.5px] text-ink-400">
            {record.extractor.provider === "local" ? t("review.byLocal") : t("review.by", { provider: `${record.extractor.provider} · ${record.extractor.model}` })}
            {record.extractor.path === "original_file" ? ` ${t("doc.fromOriginal")}` : record.extractor.path === "extracted_text" ? ` ${t("doc.fromText")}` : record.extractor.path === "page_images" ? ` ${t("doc.fromImages")}` : "."}
          </p>
        </div>
      )}
    </article>
  );
}

function ChangeReview({ reservationId, documentId }: { reservationId: string; documentId: string }) {
  const changes = useQuery({ queryKey: ["reservation-changes", reservationId], queryFn: () => api.get<ReservationChange[]>(`/reservations/${reservationId}/changes`) });
  const invalidate = useInvalidateTripData();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const { t } = useT();
  const change = changes.data?.find((c) => c.source_document_id === documentId) ?? changes.data?.[0];
  if (!change) return <div className="px-5 py-4 text-[13px] text-ink-400">{t("common.loading")}…</div>;
  const act = async (verb: "apply" | "dismiss") => {
    setBusy(true);
    try {
      await api.post(`/reservations/changes/${change.id}/${verb}`);
      toast(verb === "apply" ? t("change.applied") : t("change.dismissed"), "success");
      invalidate();
      changes.refetch();
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(false);
    }
  };
  const show = (v: any) => (typeof v === "string" && /^\d{4}-\d{2}-\d{2}T/.test(v) ? fmtDateTime(v) : v === null || v === undefined ? "—" : String(v));
  return (
    <div className="px-5 py-4">
      <InfoNote tone="amber">{t("change.note")}</InfoNote>
      <table className="mt-4 w-full text-[13.5px]">
        <thead><tr className="text-left text-[12px] text-ink-400"><th className="pb-2 font-medium">{t("change.field")}</th><th className="pb-2 font-medium">{t("change.before")}</th><th /><th className="pb-2 font-medium">{t("change.after")}</th></tr></thead>
        <tbody>
          {Object.entries(change.changes).map(([k, v]) => (
            <tr key={k} className="border-t border-sand-100">
              <td className="py-2 pr-3 text-ink-500">{k.replace("details.", "").replace("_at", "").replace(/_/g, " ")}</td>
              <td className="py-2 pr-3 text-ink-400 line-through">{show(v.old)}</td>
              <td className="py-2 pr-3"><ArrowRight className="h-3.5 w-3.5 text-ink-300" /></td>
              <td className="py-2 font-medium text-ink-900">{show(v.new)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {change.status === "pending" ? (
        <div className="mt-4 flex gap-2">
          <Button onClick={() => act("apply")} loading={busy}>{t("change.apply")}</Button>
          <Button variant="ghost" onClick={() => act("dismiss")} disabled={busy}>{t("change.keep")}</Button>
        </div>
      ) : <p className="mt-4 text-[13px] text-ink-500">{change.status === "applied" ? t("change.wasApplied") : t("change.wasDismissed")}</p>}
    </div>
  );
}
