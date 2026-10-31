import { clsx } from "clsx";
import { AlertTriangle, ArrowRight, Check, MoreHorizontal, Pencil, Trash2, X } from "lucide-react";
import * as Menu from "@radix-ui/react-dropdown-menu";
import { Badge, StatusPill } from "@/components/ui";
import { dayKey, fmtDayHeading, fmtTime, offsetLabel, tzCity } from "@/lib/format";
import type { Conflict, ItineraryEvent } from "@/lib/types";
import { Stagger, StaggerItem } from "@/components/motion";
import { useT } from "@/lib/i18n";
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
            <div className="sticky top-[var(--hdr,52px)] z-10 -mx-4 mb-3 flex items-baseline gap-2.5 bg-paper/85 px-4 py-2 backdrop-blur-md sm:static sm:mx-0 sm:bg-transparent sm:px-0 sm:py-0 sm:backdrop-blur-none lg:top-0">
              <h3 className="display text-[21px] text-ink-900">{h.weekday}</h3>
              <span className="text-[14px] text-ink-400">{h.date}</span>
            </div>
            <Stagger as="ol" className="relative space-y-2.5 border-l border-dashed border-sand-300 pl-5 sm:pl-6">
              {list.map((e) => <EventRow key={e.id} e={e} flags={flagged.get(e.id) ?? []} tripTz={tripTz}
                onEdit={onEdit} onDelete={onDelete} onStatus={onStatus} />)}
            </Stagger>
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
  const { t } = useT();

  return (
    <StaggerItem as="li" className="relative">
      <span className={clsx("absolute -left-[27px] top-5 h-2.5 w-2.5 rounded-full ring-4 ring-paper sm:-left-[31px]",
        worst === "critical" ? "bg-rose-ink" : worst ? "bg-amber-ink" : e.status === "confirmed" ? "bg-lagoon-500" : suggested ? "bg-violet-ink/60" : "bg-ink-300")} />
      <div className={clsx("group flex gap-3 rounded-2xl border p-3.5 transition sm:gap-4 sm:p-4",
        suggested ? "border-dashed border-violet-ink/35 bg-violet-soft/40" :
          free ? "border-dashed border-lagoon-500/30 bg-lagoon-50/40" : "border-sand-200/80 bg-white shadow-[var(--shadow-card)]",
        cancelled && "opacity-60", worst === "critical" && "ring-1 ring-rose-ink/25")}>
        <div className="w-[44px] shrink-0 pt-0.5 text-right sm:w-[52px]">
          <div className="text-[15px] font-semibold tabular-nums text-ink-900">{fmtTime(e.start_local)}</div>
          {e.end_local && !["hotel_checkin", "hotel_checkout"].includes(e.type) && (
            <div className="text-[12.5px] tabular-nums text-ink-400">{fmtTime(e.end_local)}</div>
          )}
        </div>
        <span className="hidden sm:block"><EventIcon type={e.type} /></span>
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
              {t("timeline.localTime", { city: tzCity(e.start_tz), offset: offsetLabel(e.start_local) })}
              {crossTz && <> → {t("timeline.arrives", { time: fmtTime(e.end_local), city: tzCity(e.end_tz), offset: offsetLabel(e.end_local) })}</>}
            </p>
          )}
          {e.notes && <p className="mt-1.5 text-[13px] text-ink-500">{e.notes}</p>}
          {e.details?.booking_reference && <p className="mt-1.5 text-[12px] text-ink-400">{t("timeline.ref")} <span className="font-mono text-ink-600">{e.details.booking_reference}</span></p>}
          {flags.map((f) => (
            <p key={f.key} className={clsx("mt-2 flex items-start gap-1.5 rounded-lg px-2.5 py-1.5 text-[12.5px]",
              f.severity === "critical" ? "bg-rose-soft text-rose-ink" : "bg-amber-soft text-amber-ink")}>
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {f.title}
            </p>
          ))}
        </div>
        {(onEdit || onDelete || onStatus) && (
          <Menu.Root>
            <Menu.Trigger className="-mr-1.5 -mt-1.5 h-10 w-10 shrink-0 rounded-full text-ink-400 hover:bg-sand-100 hover:text-ink-700 active:scale-90 pointer-coarse:h-11 pointer-coarse:w-11" aria-label={t("timeline.actionsFor", { title: e.title })}>
              <MoreHorizontal className="mx-auto h-4 w-4" />
            </Menu.Trigger>
            <Menu.Portal>
              <Menu.Content align="end" className="z-50 min-w-[210px] rounded-xl border border-sand-200 bg-white p-1 text-[14px] shadow-[var(--shadow-lift)]">
                {suggested && onStatus && (
                  <Menu.Item onSelect={() => onStatus(e, "unbooked")} className="flex min-h-11 cursor-pointer items-center gap-2 rounded-lg px-2.5 outline-none data-[highlighted]:bg-sand-50">
                    <Check className="h-4 w-4 text-lagoon-600" /> {t("timeline.keep")}
                  </Menu.Item>
                )}
                {e.status !== "completed" && onStatus && !suggested && (
                  <Menu.Item onSelect={() => onStatus(e, "completed")} className="flex min-h-11 cursor-pointer items-center gap-2 rounded-lg px-2.5 outline-none data-[highlighted]:bg-sand-50">
                    <Check className="h-4 w-4" /> {t("timeline.complete")}
                  </Menu.Item>
                )}
                {onEdit && (
                  <Menu.Item onSelect={() => onEdit(e)} className="flex min-h-11 cursor-pointer items-center gap-2 rounded-lg px-2.5 outline-none data-[highlighted]:bg-sand-50">
                    <Pencil className="h-4 w-4" /> {editable ? t("common.edit") : t("timeline.editNotes")}
                  </Menu.Item>
                )}
                {editable && onDelete && (
                  <Menu.Item onSelect={() => onDelete(e)} className="flex min-h-11 cursor-pointer items-center gap-2 rounded-lg px-2.5 text-rose-ink outline-none data-[highlighted]:bg-rose-soft">
                    {suggested ? <X className="h-4 w-4" /> : <Trash2 className="h-4 w-4" />} {suggested ? t("timeline.dismiss") : t("common.delete")}
                  </Menu.Item>
                )}
              </Menu.Content>
            </Menu.Portal>
          </Menu.Root>
        )}
      </div>
    </StaggerItem>
  );
}

export function TimelineLegend() {
  const { t } = useT();
  return (
    <div className="flex flex-wrap gap-2 text-[12px] text-ink-500">
      <Badge tone="lagoon">{t("status.confirmed")}</Badge>
      <Badge tone="amber">{t("status.pending")}</Badge>
      <Badge tone="violet">{t("status.suggested")}</Badge>
      <Badge tone="outline">{t("status.unbooked")}</Badge>
    </div>
  );
}
