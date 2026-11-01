import { clsx } from "clsx";
import { ExternalLink, Image as ImageIcon, Loader2, XCircle } from "lucide-react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ActionCard } from "@/components/activities/ActionCard";
import { Button, InfoNote, PageLoader, StatusPill } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDate, money } from "@/lib/format";
import { translatePlural, useT, type Key } from "@/lib/i18n";
import type { Action, BrowserTask } from "@/lib/types";

const RUNNING = new Set(["searching", "navigating", "submitting", "verifying", "not_started"]);

function describeParams(p: Record<string, any>) {
  const where = p.venue ? p.venue : p.origin ? `${p.origin} → ${p.destination}` : "";
  return [where, p.date ? fmtDate(p.date) : "", p.adults ? translatePlural("sites.people", p.adults) : ""].filter(Boolean).join(" · ");
}

/** ce a facut agentul de browser, pas cu pas, si aprobarea pe care o asteapta. Se deschide din raspunsul asistentului */
export function TaskPanel({ id, onClose }: { id: string; onClose: () => void }) {
  const task = useQuery({
    queryKey: ["browser-task", id],
    queryFn: () => api.get<BrowserTask>(`/browser/tasks/${id}`),
    refetchInterval: (q) => (q.state.data && RUNNING.has(q.state.data.state) ? 1200 : false),
  });
  const action = useQuery({
    queryKey: ["approvals", "one", task.data?.action_id ?? ""],
    queryFn: () => api.get<Action>(`/approvals/${task.data!.action_id}`),
    enabled: !!task.data?.action_id,
    refetchInterval: (q) => (q.state.data?.status === "in_progress" ? 1000 : false),
  });
  const qc = useQueryClient();
  const { t: tr } = useT();
  const stepLabel = (a: string) => { const k = `sites.step.${a}` as Key; const x = tr(k); return x === k ? a.replace(/_/g, " ") : x; };
  if (!task.data) return <div className="card mb-6 p-6"><PageLoader /></div>;
  const t = task.data;
  if (action.data && ["completed", "failed", "requires_manual"].includes(action.data.status) && t.state === "awaiting_approval") {
    qc.invalidateQueries({ queryKey: ["browser-task", id] });
  }
  return (
    <section className="card mb-6 overflow-hidden" aria-live="polite">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-sand-100 px-4 py-4 sm:px-5">
        <div className="min-w-0">
          <p className="eyebrow">{tr("sites.agent")} · {t.engine === "playwright" ? tr("sites.engine.browser") : t.engine === "http" ? tr("sites.engine.simulated") : tr("sites.engine.handoff")}</p>
          <h2 className="mt-0.5 text-[16px] font-semibold">{t.site_name}</h2>
          <p className="text-[13px] text-ink-500">{describeParams(t.params)}</p>
        </div>
        <div className="flex items-center gap-2">
          {RUNNING.has(t.state) && <Loader2 className="h-4 w-4 animate-spin text-lagoon-600" />}
          <StatusPill status={t.state} />
          {!["completed", "cancelled", "requires_manual", "failed", "blocked"].includes(t.state) && (
            <Button size="sm" variant="ghost" onClick={async () => { await api.post(`/browser/tasks/${t.id}/cancel`); task.refetch(); }}>{tr("common.cancel")}</Button>
          )}
          <button onClick={onClose} className="flex h-10 w-10 items-center justify-center rounded-full text-ink-400 hover:bg-sand-100 active:scale-90 pointer-coarse:h-11 pointer-coarse:w-11" aria-label={tr("common.close")}><XCircle className="h-5 w-5" /></button>
        </div>
      </header>
      <div className="grid grid-cols-1 gap-6 p-4 sm:p-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <ol className="space-y-3" aria-label={tr("sites.steps")}>
          {t.log.map((s) => (
            <li key={s.step} className="flex gap-3">
              <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-sand-100 text-[11px] font-semibold text-ink-600">{s.step}</span>
              <div className="min-w-0 flex-1">
                <p className="text-[13.5px] text-ink-800"><span className="font-medium">{stepLabel(s.action)}</span> — {s.reason}</p>
                {s.url && <p className="truncate text-[11.5px] text-ink-400">{s.title ? `${s.title} · ` : ""}{s.url}</p>}
                {s.screenshot && (
                  <img src={`/api/v1/browser/tasks/${t.id}/steps/${s.step}/screenshot`} alt={tr("sites.stepAlt", { n: s.step })} loading="lazy"
                    className="mt-2 w-full rounded-lg border border-sand-200" />
                )}
                {!s.screenshot && s.page_text && (
                  <details className="mt-1"><summary className="cursor-pointer text-[12px] text-ink-400"><ImageIcon className="mr-1 inline h-3 w-3" />{tr("sites.pageText")}</summary>
                    <p className="mt-1 rounded-lg bg-sand-50 p-2 text-[12px] text-ink-500">{s.page_text}</p></details>
                )}
              </div>
            </li>
          ))}
        </ol>
        <div className="space-y-4">
          {t.result.offers && t.result.offers.length > 0 && (
            <div>
              <p className="eyebrow mb-2">{tr("sites.options")}</p>
              <ul className="space-y-1.5 text-[13px]">
                {t.result.offers.map((o, i) => (
                  <li key={i} className={clsx("flex justify-between gap-3 rounded-lg px-3 py-2", t.result.selected?.offer_id === o.offer_id && o.offer_id ? "bg-lagoon-50 text-lagoon-700" : "bg-sand-50")}>
                    <span className="truncate">{o.title ?? `${o.offer_id} ${o.depart}–${o.arrive}`}</span>
                    <span className="shrink-0 font-medium">{money(o.total ?? o.price ?? null, o.currency ?? "EUR")}</span>
                  </li>
                ))}
              </ul>
              {t.result.selection_reason && <p className="mt-2 text-[12.5px] text-ink-500">{tr("sites.chosen", { reason: t.result.selection_reason })}</p>}
            </div>
          )}
          {action.data && <ActionCard action={action.data} />}
          {t.stop_reason && t.state !== "awaiting_approval" && <InfoNote tone={t.state === "completed" ? "lagoon" : "amber"}>{t.stop_reason}</InfoNote>}
          {t.handoff_url && t.state !== "completed" && (
            <a href={t.handoff_url} target="_blank" rel="noopener noreferrer" className="inline-flex h-10 items-center gap-2 rounded-xl bg-lagoon-900 px-4 text-[14px] font-medium text-white hover:bg-ink-800">
              {tr("sites.continueOn", { name: t.site_name })} <ExternalLink className="h-4 w-4" />
            </a>
          )}
          {t.state === "completed" && t.result.reservation_id && t.trip_id && (
            <Link to={`/trips/${t.trip_id}`} className="inline-flex h-10 items-center gap-2 rounded-xl border border-sand-200 bg-white px-4 text-[14px] font-medium hover:bg-sand-50">{tr("sites.viewInTrip")}</Link>
          )}
        </div>
      </div>
    </section>
  );
}
