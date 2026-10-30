import { clsx } from "clsx";
import { AlertTriangle, ArrowRight, Check, MoreHorizontal, Pencil, Trash2, X } from "lucide-react";
import * as Menu from "@radix-ui/react-dropdown-menu";
import { Badge, StatusPill } from "@/components/ui";
import { dayKey, fmtDayHeading, fmtTime, offsetLabel, tzCity } from "@/lib/format";
import type { Conflict, ItineraryEvent } from "@/lib/types";
import { EventIcon } from "./EventIcon";

type Props = {
  events: ItineraryEvent[];
  conflicts: Conflict[];
  tripTz?: string | null;
  onEdit?: (e: ItineraryEvent) => void;
  onDelete?: (e: ItineraryEvent) => void;
  onStatus?: (e: ItineraryEvent, status: string) => void;
};

export function Timeline({ events, conflicts, tripTz, onEdit, onDelete, onStatus }: Props) {
  const byDay = new Map<string, ItineraryEvent[]>();
  for (const e of events) {
    const k = dayKey(e.start_local);
    byDay.set(k, [...(byDay.get(k) ?? []), e]);
  }
  const flagged = new Map<string, Conflict[]>();
  for (const c of conflicts) for (const id of c.event_ids) flagged.set(id, [...(flagged.get(id) ?? []), c]);

  return (
    <ol className="space-y-8">
      {[...byDay.entries()].map(([day, list]) => {
        const h = fmtDayHeading(day);
        return (
          <li key={day}>
            <div className="mb-3 flex items-baseline gap-2.5">
              <h3 className="display text-[19px] text-ink-900">{h.weekday}</h3>
              <span className="text-[14px] text-ink-400">{h.date}</span>
            </div>
            <ol className="relative space-y-2.5 border-l border-sand-200 pl-5 sm:pl-6">
              {list.map((e) => <EventRow key={e.id} e={e} flags={flagged.get(e.id) ?? []} tripTz={tripTz}
                onEdit={onEdit} onDelete={onDelete} onStatus={onStatus} />)}
            </ol>
          </li>
        );
      })}
    </ol>
  );
}

function EventRow({ e, flags, tripTz, onEdit, onDelete, onStatus }: { e: ItineraryEvent; flags: Conflict[]; tripTz?: string | null } & Omit<Props, "events" | "conflicts" | "tripTz">) {
  const suggested = e.status === "suggested";
  const free = e.type === "free_time";
  const cancelled = e.status === "cancelled";
  const crossTz = e.end_tz && e.end_tz !== e.start_tz;
  const showTz = (tripTz && e.start_tz !== tripTz) || crossTz;
  const worst = flags.some((f) => f.severity === "critical") ? "critical" : flags.length ? "warning" : null;
  const editable = !e.reservation_id;

  return (
    <li className="relative">
      <span className={clsx("absolute -left-[27px] top-5 h-2.5 w-2.5 rounded-full ring-4 ring-paper sm:-left-[31px]",
        worst === "critical" ? "bg-rose-ink" : worst ? "bg-amber-ink" : e.status === "confirmed" ? "bg-lagoon-500" : suggested ? "bg-violet-ink/60" : "bg-ink-300")} />
      <div className={clsx("group flex gap-3 rounded-2xl border p-3.5 transition sm:gap-4 sm:p-4",
        suggested ? "border-dashed border-violet-ink/35 bg-violet-soft/40" :
          free ? "border-dashed border-lagoon-500/30 bg-lagoon-50/40" : "border-sand-200/80 bg-white shadow-[var(--shadow-card)]",
        cancelled && "opacity-60", worst === "critical" && "ring-1 ring-rose-ink/25")}>
        <div className="w-[52px] shrink-0 pt-0.5 text-right">
          <div className="text-[15px] font-semibold tabular-nums text-ink-900">{fmtTime(e.start_local)}</div>
          {e.end_local && !["hotel_checkin", "hotel_checkout"].includes(e.type) && (
            <div className="text-[12.5px] tabular-nums text-ink-400">{fmtTime(e.end_local)}</div>
          )}
        </div>
        <EventIcon type={e.type} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <p className={clsx("text-[15px] font-medium text-ink-900", cancelled && "line-through")}>{e.title}</p>
            {e.status !== "confirmed" && <StatusPill status={e.status} />}
          </div>
          {(e.end_location_name || e.location_name) && (
            <p className="mt-0.5 flex flex-wrap items-center gap-1 text-[13px] text-ink-500">
              {e.location_name}
              {e.end_location_name && <><ArrowRight className="h-3 w-3" /> {e.end_location_name}</>}
            </p>
          )}
          {showTz && (
            <p className="mt-1 text-[12px] text-ink-400">
              {tzCity(e.start_tz)} time ({offsetLabel(e.start_local)})
              {crossTz && <> → arrives {fmtTime(e.end_local)} {tzCity(e.end_tz)} time ({offsetLabel(e.end_local)})</>}
            </p>
          )}
          {e.notes && <p className="mt-1.5 text-[13px] text-ink-500">{e.notes}</p>}
          {e.details?.booking_reference && <p className="mt-1.5 text-[12px] text-ink-400">Ref <span className="font-mono text-ink-600">{e.details.booking_reference}</span></p>}
          {flags.map((f) => (
            <p key={f.key} className={clsx("mt-2 flex items-start gap-1.5 rounded-lg px-2.5 py-1.5 text-[12.5px]",
              f.severity === "critical" ? "bg-rose-soft text-rose-ink" : "bg-amber-soft text-amber-ink")}>
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {f.title}
            </p>
          ))}
        </div>
        {(onEdit || onDelete || onStatus) && (
          <Menu.Root>
            <Menu.Trigger className="h-8 w-8 shrink-0 rounded-lg text-ink-300 opacity-70 hover:bg-sand-100 hover:text-ink-700 group-hover:opacity-100" aria-label={`Actions for ${e.title}`}>
              <MoreHorizontal className="mx-auto h-4 w-4" />
            </Menu.Trigger>
            <Menu.Portal>
              <Menu.Content align="end" className="z-50 min-w-[190px] rounded-xl border border-sand-200 bg-white p-1 text-[13.5px] shadow-[var(--shadow-lift)]">
                {suggested && onStatus && (
                  <Menu.Item onSelect={() => onStatus(e, "unbooked")} className="flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-2 outline-none data-[highlighted]:bg-sand-50">
                    <Check className="h-4 w-4 text-lagoon-600" /> Keep in plan (not booked)
                  </Menu.Item>
                )}
                {e.status !== "completed" && onStatus && !suggested && (
                  <Menu.Item onSelect={() => onStatus(e, "completed")} className="flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-2 outline-none data-[highlighted]:bg-sand-50">
                    <Check className="h-4 w-4" /> Mark completed
                  </Menu.Item>
                )}
                {onEdit && (
                  <Menu.Item onSelect={() => onEdit(e)} className="flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-2 outline-none data-[highlighted]:bg-sand-50">
                    <Pencil className="h-4 w-4" /> {editable ? "Edit" : "Edit notes"}
                  </Menu.Item>
                )}
                {editable && onDelete && (
                  <Menu.Item onSelect={() => onDelete(e)} className="flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-2 text-rose-ink outline-none data-[highlighted]:bg-rose-soft">
                    {suggested ? <X className="h-4 w-4" /> : <Trash2 className="h-4 w-4" />} {suggested ? "Dismiss suggestion" : "Delete"}
                  </Menu.Item>
                )}
              </Menu.Content>
            </Menu.Portal>
          </Menu.Root>
        )}
      </div>
    </li>
  );
}

export function TimelineLegend() {
  return (
    <div className="flex flex-wrap gap-2 text-[12px] text-ink-500">
      <Badge tone="lagoon">Confirmed</Badge>
      <Badge tone="amber">Pending</Badge>
      <Badge tone="violet">Suggestion</Badge>
      <Badge tone="outline">Not booked</Badge>
    </div>
  );
}
