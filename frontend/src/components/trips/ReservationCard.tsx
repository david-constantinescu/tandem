import { clsx } from "clsx";
import { BadgeCheck, FileText, History, ShieldQuestion } from "lucide-react";
import { Link } from "react-router-dom";
import { Badge, StatusPill, useTypeLabel } from "@/components/ui";
import { fmtDateTime, money, offsetLabel, tzCity } from "@/lib/format";
import { useT, type Key } from "@/lib/i18n";
import type { Reservation } from "@/lib/types";
import { EventIcon } from "./EventIcon";

const verification = {
  verified: { text: "res.verified" as Key, icon: BadgeCheck, tone: "lagoon" as const },
  user_confirmed: { text: "res.reviewedByYou" as Key, icon: BadgeCheck, tone: "neutral" as const },
  unverified: { text: "res.unverified" as Key, icon: ShieldQuestion, tone: "amber" as const },
};

const TRANSPORT = ["flight", "train", "bus"];

export function ReservationCard({ r, onEdit }: { r: Reservation; onEdit?: (r: Reservation) => void }) {
  const { t, tp } = useT();
  const typeLabel = useTypeLabel();
  const v = verification[r.verification];
  const pendingChanges = r.changes?.filter((c) => c.status === "pending") ?? [];
  const applied = r.changes?.filter((c) => c.status === "applied") ?? [];
  const d = r.details ?? {};
  const facts: [Key, string | undefined][] = [
    ["res.flight", d.flight_number], ["res.train", d.train_number], ["res.seat", d.seat], ["res.terminal", d.terminal], ["res.gate", d.gate],
    ["res.room", d.room_type], ["res.guests", d.guests ?? d.party_size], ["res.baggage", d.baggage], ["res.meetingPoint", d.meeting_point],
    ["res.checkInFrom", d.check_in_from], ["res.checkOutBy", d.check_out_until],
  ].filter(([, val]) => val !== undefined && val !== null && val !== "") as [Key, string][];
  const startLabel: Key = r.type === "hotel" ? "res.checkIn" : r.end_local && TRANSPORT.includes(r.type) ? "res.departs" : "res.starts";
  const endLabel: Key = r.type === "hotel" ? "res.checkOut" : TRANSPORT.includes(r.type) ? "res.arrives" : "res.ends";

  return (
    <article className="card p-4 sm:p-5">
      <div className="flex gap-3.5">
        <EventIcon type={r.type} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="eyebrow">{typeLabel(r.type)}{r.provider_name ? ` · ${r.provider_name}` : ""}</p>
              <h3 className="mt-1 text-[16px] font-semibold text-ink-900">{r.title}</h3>
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              <StatusPill status={r.status} />
              <Badge tone={v.tone} icon={<v.icon className="h-3 w-3" />}>{t(v.text)}</Badge>
            </div>
          </div>
          <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-1.5 text-[13.5px] sm:grid-cols-2">
            {r.start_local && <Row k={t(startLabel)} v={`${fmtDateTime(r.start_local)} · ${tzCity(r.start_tz)} (${offsetLabel(r.start_local)})`} />}
            {r.end_local && <Row k={t(endLabel)} v={`${fmtDateTime(r.end_local)} · ${tzCity(r.end_tz)} (${offsetLabel(r.end_local)})`} />}
            {r.booking_reference && <Row k={t("res.reference")} v={<span className="font-mono">{r.booking_reference}</span>} />}
            {r.price !== null && <Row k={t("res.price")} v={money(r.price, r.currency)} />}
            {r.address && <Row k={t("res.address")} v={r.address} wide />}
            {facts.map(([k, val]) => <Row key={k} k={t(k)} v={String(val)} />)}
            {r.cancellation_policy && <Row k={t("res.cancellation")} v={r.cancellation_policy} wide />}
            {r.travellers?.length > 0 && <Row k={t("res.travellers")} v={r.travellers.join(", ")} wide />}
          </dl>
          {pendingChanges.length > 0 && (
            <p className="mt-3 rounded-lg bg-amber-soft px-3 py-2 text-[13px] text-amber-ink">{t("res.updateWaiting", { summary: pendingChanges[0].summary })}</p>
          )}
          <div className="mt-3 flex flex-wrap items-center gap-3 text-[12.5px] text-ink-400">
            {r.source_document_id && (
              <Link to={`/inbox/${r.source_document_id}`} className="inline-flex min-h-9 items-center gap-1 hover:text-lagoon-600"><FileText className="h-3.5 w-3.5" /> {t("res.source")}</Link>
            )}
            {applied.length > 0 && <span className="inline-flex items-center gap-1"><History className="h-3.5 w-3.5" /> {tp("res.updatesApplied", applied.length, { summary: applied[0].summary })}</span>}
            {d.simulated && <Badge tone="violet">{t("res.simulated")}</Badge>}
            {onEdit && <button onClick={() => onEdit(r)} className="ml-auto min-h-9 px-1 font-medium text-lagoon-600 hover:underline">{t("common.edit")}</button>}
          </div>
        </div>
      </div>
    </article>
  );
}

function Row({ k, v, wide }: { k: string; v: React.ReactNode; wide?: boolean }) {
  return (
    <div className={clsx("flex gap-2", wide && "sm:col-span-2")}>
      <dt className="w-[104px] shrink-0 text-ink-400">{k}</dt>
      <dd className="min-w-0 text-ink-700">{v}</dd>
    </div>
  );
}
