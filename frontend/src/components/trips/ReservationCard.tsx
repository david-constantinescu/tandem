import { clsx } from "clsx";
import { BadgeCheck, FileText, History, ShieldQuestion } from "lucide-react";
import { Link } from "react-router-dom";
import { Badge, StatusPill } from "@/components/ui";
import { fmtDateTime, label, money, offsetLabel, tzCity } from "@/lib/format";
import type { Reservation } from "@/lib/types";
import { EventIcon } from "./EventIcon";

const verification = {
  verified: { text: "Verified with provider", icon: BadgeCheck, tone: "lagoon" as const },
  user_confirmed: { text: "Reviewed by you", icon: BadgeCheck, tone: "neutral" as const },
  unverified: { text: "Unverified", icon: ShieldQuestion, tone: "amber" as const },
};

export function ReservationCard({ r, onEdit }: { r: Reservation; onEdit?: (r: Reservation) => void }) {
  const v = verification[r.verification];
  const pendingChanges = r.changes?.filter((c) => c.status === "pending") ?? [];
  const applied = r.changes?.filter((c) => c.status === "applied") ?? [];
  const d = r.details ?? {};
  const facts: [string, string | undefined][] = [
    ["Flight", d.flight_number], ["Train", d.train_number], ["Seat", d.seat], ["Terminal", d.terminal], ["Gate", d.gate],
    ["Room", d.room_type], ["Guests", d.guests ?? d.party_size], ["Baggage", d.baggage], ["Meeting point", d.meeting_point],
    ["Check-in from", d.check_in_from], ["Check-out by", d.check_out_until],
  ].filter(([, v]) => v !== undefined && v !== null && v !== "") as [string, string][];

  return (
    <article className="card p-4 sm:p-5">
      <div className="flex gap-3.5">
        <EventIcon type={r.type} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="eyebrow">{label(r.type)}{r.provider_name ? ` · ${r.provider_name}` : ""}</p>
              <h3 className="mt-1 text-[16px] font-semibold text-ink-900">{r.title}</h3>
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              <StatusPill status={r.status} />
              <Badge tone={v.tone} icon={<v.icon className="h-3 w-3" />}>{v.text}</Badge>
            </div>
          </div>
          <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-1.5 text-[13.5px] sm:grid-cols-2">
            {r.start_local && <Row k={r.type === "hotel" ? "Check-in" : r.end_local && ["flight", "train", "bus"].includes(r.type) ? "Departs" : "Starts"}
              v={`${fmtDateTime(r.start_local)} · ${tzCity(r.start_tz)} (${offsetLabel(r.start_local)})`} />}
            {r.end_local && <Row k={r.type === "hotel" ? "Check-out" : ["flight", "train", "bus"].includes(r.type) ? "Arrives" : "Ends"}
              v={`${fmtDateTime(r.end_local)} · ${tzCity(r.end_tz)} (${offsetLabel(r.end_local)})`} />}
            {r.booking_reference && <Row k="Reference" v={<span className="font-mono">{r.booking_reference}</span>} />}
            {r.price !== null && <Row k="Price" v={money(r.price, r.currency)} />}
            {r.address && <Row k="Address" v={r.address} wide />}
            {facts.map(([k, val]) => <Row key={k} k={k} v={String(val)} />)}
            {r.cancellation_policy && <Row k="Cancellation" v={r.cancellation_policy} wide />}
            {r.travellers?.length > 0 && <Row k="Travellers" v={r.travellers.join(", ")} wide />}
          </dl>
          {pendingChanges.length > 0 && (
            <p className="mt-3 rounded-lg bg-amber-soft px-3 py-2 text-[13px] text-amber-ink">
              Update waiting for review: {pendingChanges[0].summary}
            </p>
          )}
          <div className="mt-3 flex flex-wrap items-center gap-3 text-[12.5px] text-ink-400">
            {r.source_document_id && (
              <Link to={`/inbox/${r.source_document_id}`} className="inline-flex items-center gap-1 hover:text-lagoon-600"><FileText className="h-3.5 w-3.5" /> Source document</Link>
            )}
            {applied.length > 0 && <span className="inline-flex items-center gap-1"><History className="h-3.5 w-3.5" /> {applied.length} update{applied.length > 1 ? "s" : ""} applied: {applied[0].summary}</span>}
            {d.simulated && <Badge tone="violet">Simulated booking</Badge>}
            {onEdit && <button onClick={() => onEdit(r)} className="ml-auto text-lagoon-600 hover:underline">Edit</button>}
          </div>
        </div>
      </div>
    </article>
  );
}

function Row({ k, v, wide }: { k: string; v: React.ReactNode; wide?: boolean }) {
  return (
    <div className={clsx("flex gap-2", wide && "sm:col-span-2")}>
      <dt className="w-[96px] shrink-0 text-ink-400">{k}</dt>
      <dd className="min-w-0 text-ink-700">{v}</dd>
    </div>
  );
}
