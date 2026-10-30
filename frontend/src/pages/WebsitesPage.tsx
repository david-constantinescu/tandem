import { clsx } from "clsx";
import { Bot, Bus, ExternalLink, Image as ImageIcon, Landmark, Loader2, Palette, Plane, ShieldCheck, TrainFront, Ticket, XCircle } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ActionCard } from "@/components/activities/ActionCard";
import { Badge, Button, EmptyState, ErrorNote, InfoNote, PageHeader, PageLoader, StatusPill } from "@/components/ui";
import { Dialog } from "@/components/ui/Dialog";
import { api, errorMessage } from "@/lib/api";
import { fmtDate, money, relativeTime } from "@/lib/format";
import { useTrips } from "@/lib/queries";
import type { Action, BookingSite, BrowserTask } from "@/lib/types";

const CATS = [
  { key: "all", label: "All", icon: Ticket },
  { key: "train", label: "Trains", icon: TrainFront },
  { key: "bus", label: "Buses", icon: Bus },
  { key: "flight", label: "Flights", icon: Plane },
  { key: "museum", label: "Museums & galleries", icon: Palette },
  { key: "attraction", label: "Attractions", icon: Landmark },
] as const;
const ICON: Record<string, any> = { train: TrainFront, bus: Bus, flight: Plane, museum: Landmark, gallery: Palette, attraction: Ticket };
const RUNNING = new Set(["searching", "navigating", "submitting", "verifying", "not_started"]);
const DEMO_VENUES = ["Galleria Demo d'Arte Moderna", "Museo Demo di Storia Antica", "Musée Démo des Beaux-Arts", "Demo Gallery of Modern Art", "Museu Demo do Azulejo"];

export default function WebsitesPage() {
  const [params, setParams] = useSearchParams();
  const [cat, setCat] = useState("all");
  const [runSite, setRunSite] = useState<BookingSite | null>(null);
  const sites = useQuery({ queryKey: ["browser-sites"], queryFn: () => api.getWithMeta<BookingSite[]>("/browser/sites") });
  const tasks = useQuery({ queryKey: ["browser-tasks"], queryFn: () => api.get<BrowserTask[]>("/browser/tasks") });
  const openTask = params.get("task");
  if (sites.isLoading) return <PageLoader />;
  const all = sites.data?.data ?? [];
  const workerAvailable = !!sites.data?.meta?.browser_worker;
  const inCat = (s: BookingSite) => cat === "all" || s.category === cat || (cat === "museum" && s.category === "gallery");
  const simulated = all.filter((s) => s.simulated && inCat(s));
  const real = all.filter((s) => !s.simulated && inCat(s));

  return (
    <div>
      <PageHeader title="Book on websites" subtitle="Tandem's browser agent can use booking websites for you. It always asks before entering anyone's details, and you stay in control of payment." />

      {openTask && <TaskPanel id={openTask} onClose={() => setParams({})} />}

      <InfoNote tone="lagoon" icon={<ShieldCheck className="h-4 w-4" />}>
        <strong>How the agent behaves.</strong> On Tandem's simulated sites it completes the whole purchase after your approval (nothing real is charged).
        Real airline, rail, bus and museum sites are <strong>link-only</strong> until their terms are reviewed for automated use; where an operator enables
        assisted search, the agent searches and compares, then hands off before personal or payment details. It stops at CAPTCHAs and logins and never bypasses them.
        {!workerAvailable && " Assisted search on real sites needs a browser worker, which isn't running on this deployment."}
      </InfoNote>

      <div className="mt-6 flex gap-1.5 overflow-x-auto" role="tablist" aria-label="Website categories">
        {CATS.map((c) => (
          <button key={c.key} role="tab" aria-selected={cat === c.key} onClick={() => setCat(c.key)}
            className={clsx("inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-3.5 py-1.5 text-[13px] font-medium transition",
              cat === c.key ? "bg-ink-900 text-white" : "bg-white text-ink-600 ring-1 ring-sand-200 hover:text-ink-900")}>
            <c.icon className="h-3.5 w-3.5" />{c.label}
          </button>
        ))}
      </div>

      {simulated.length > 0 && (
        <section className="mt-6">
          <h2 className="eyebrow mb-3 flex items-center gap-1.5"><Bot className="h-3.5 w-3.5" /> The agent can complete a purchase (simulated sites)</h2>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {simulated.map((s) => <SiteCard key={s.key} s={s} onRun={() => setRunSite(s)} />)}
          </div>
        </section>
      )}

      <section className="mt-8">
        <h2 className="eyebrow mb-3">Official websites ({real.length})</h2>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {real.map((s) => <SiteCard key={s.key} s={s} onRun={s.policy === "assisted" && workerAvailable ? () => setRunSite(s) : undefined} />)}
        </div>
      </section>

      <section className="mt-10">
        <h2 className="eyebrow mb-3">Recent agent runs</h2>
        {(tasks.data?.length ?? 0) === 0 ? <EmptyState icon={<Bot className="h-7 w-7" />} title="No agent runs yet" body="Run the agent on a simulated site to watch it search, choose and prepare a purchase for your approval." /> : (
          <ul className="card divide-y divide-sand-100">
            {tasks.data!.map((t) => (
              <li key={t.id}>
                <button onClick={() => setParams({ task: t.id })} className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-sand-50/70">
                  <span className="min-w-0">
                    <span className="block truncate text-[14px] font-medium">{t.site_name}</span>
                    <span className="block truncate text-[12.5px] text-ink-400">{describeParams(t.params)} · {relativeTime(t.created_at)}</span>
                  </span>
                  <StatusPill status={t.state} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {runSite && <RunDialog site={runSite} onClose={() => setRunSite(null)} onStarted={(id) => { setRunSite(null); setParams({ task: id }); }} />}
    </div>
  );
}

function describeParams(p: Record<string, any>) {
  const where = p.venue ? p.venue : p.origin ? `${p.origin} → ${p.destination}` : "";
  return [where, p.date ? fmtDate(p.date) : "", p.adults ? `${p.adults} ${p.adults === 1 ? "person" : "people"}` : ""].filter(Boolean).join(" · ");
}

function SiteCard({ s, onRun }: { s: BookingSite; onRun?: () => void }) {
  const Icon = ICON[s.category] ?? Ticket;
  const badge = s.simulated ? <Badge tone="violet">Full purchase · simulated</Badge>
    : s.automation_forbidden ? <Badge tone="rose">Site forbids automation</Badge>
      : s.policy === "assisted" ? <Badge tone="lagoon">Assisted search</Badge> : <Badge tone="neutral">Link only</Badge>;
  return (
    <article className="card flex flex-col p-4">
      <div className="flex items-start gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-sand-100 text-ink-600"><Icon className="h-[18px] w-[18px]" /></span>
        <div className="min-w-0">
          <h3 className="text-[14.5px] font-semibold leading-snug">{s.name}</h3>
          <p className="text-[12px] text-ink-400">{s.category}{s.country ? ` · ${s.country}` : ""}</p>
        </div>
      </div>
      <div className="mt-3">{badge}</div>
      <p className="mt-2 text-[12.5px] text-ink-500">{s.terms_note}</p>
      {s.notes.map((n) => <p key={n} className="mt-1 text-[12px] text-ink-400">{n}</p>)}
      <div className="mt-auto flex flex-wrap gap-2 pt-3">
        {onRun && <Button size="sm" onClick={onRun} icon={<Bot className="h-3.5 w-3.5" />}>Run agent</Button>}
        {!s.simulated && (
          <a href={s.homepage} target="_blank" rel="noopener noreferrer" className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-sand-200 bg-white px-3 text-[13px] font-medium text-ink-800 hover:bg-sand-50">
            Open {s.name} <ExternalLink className="h-3.5 w-3.5" />
          </a>
        )}
        {s.simulated && <a href={s.homepage} target="_blank" rel="noopener noreferrer" className="inline-flex h-8 items-center gap-1 px-2 text-[12.5px] text-ink-500 hover:text-ink-800">View site <ExternalLink className="h-3 w-3" /></a>}
      </div>
    </article>
  );
}

function RunDialog({ site, onClose, onStarted }: { site: BookingSite; onClose: () => void; onStarted: (id: string) => void }) {
  const trips = useTrips();
  const upcoming = (trips.data ?? []).filter((t) => t.stats.phase !== "past");
  const museum = site.category === "museum" || site.category === "gallery";
  const [form, setForm] = useState({ origin: "", destination: "", venue: museum ? DEMO_VENUES[0] : "", date: "", time: "", adults: 2, trip_id: upcoming[0]?.id ?? "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const qc = useQueryClient();
  // Trips may load after the dialog opens: default to the next trip once they arrive.
  useEffect(() => {
    if (!form.trip_id && upcoming[0]) setForm((f) => ({ ...f, trip_id: upcoming[0].id }));
  }, [upcoming[0]?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const set = (k: keyof typeof form) => (e: any) => setForm({ ...form, [k]: k === "adults" ? Number(e.target.value) : e.target.value });
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body: Record<string, any> = { site: site.key, date: form.date, adults: form.adults, trip_id: form.trip_id || null, time: form.time || null };
      if (museum) body.venue = form.venue; else { body.origin = form.origin; body.destination = form.destination; }
      const t = await api.post<BrowserTask>("/browser/tasks", body);
      qc.invalidateQueries({ queryKey: ["browser-tasks"] });
      qc.invalidateQueries({ queryKey: ["approvals"] });
      onStarted(t.id);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  const trip = upcoming.find((t) => t.id === form.trip_id);
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={`Run the agent on ${site.name}`}
      description="The agent searches, picks an option that fits your plans, and pauses for your approval before entering any names.">
      <form onSubmit={submit} className="space-y-3">
        {museum ? (
          <div><label className="label" htmlFor="rv">Museum or gallery</label>
            <select id="rv" className="field" value={form.venue} onChange={set("venue")}>{DEMO_VENUES.map((v) => <option key={v}>{v}</option>)}</select></div>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            <div><label className="label" htmlFor="ro">From</label><input id="ro" required className="field" value={form.origin} onChange={set("origin")} placeholder="Rome" /></div>
            <div><label className="label" htmlFor="rd">To</label><input id="rd" required className="field" value={form.destination} onChange={set("destination")} placeholder="Florence" /></div>
          </div>
        )}
        <div className="grid grid-cols-3 gap-3">
          <div><label className="label" htmlFor="rdt">Date</label><input id="rdt" type="date" required className="field" value={form.date} onChange={set("date")} min={trip?.start_date ?? undefined} max={trip?.end_date ?? undefined} /></div>
          <div><label className="label" htmlFor="rt">{museum ? "Entry from" : "Leave after"}</label><input id="rt" type="time" className="field" value={form.time} onChange={set("time")} /></div>
          <div><label className="label" htmlFor="ra">People</label><input id="ra" type="number" min={1} max={9} className="field" value={form.adults} onChange={set("adults")} /></div>
        </div>
        <div><label className="label" htmlFor="rtrip">Add to trip</label>
          <select id="rtrip" className="field" value={form.trip_id} onChange={set("trip_id")}>
            <option value="">No trip</option>{upcoming.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select></div>
        {error && <ErrorNote>{error}</ErrorNote>}
        <div className="flex justify-end gap-2 pt-2"><Button type="button" variant="ghost" onClick={onClose}>Cancel</Button><Button type="submit" loading={busy} icon={<Bot className="h-4 w-4" />}>Start agent</Button></div>
      </form>
    </Dialog>
  );
}

function TaskPanel({ id, onClose }: { id: string; onClose: () => void }) {
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
  if (!task.data) return <div className="card mb-6 p-6"><PageLoader /></div>;
  const t = task.data;
  if (action.data && ["completed", "failed", "requires_manual"].includes(action.data.status) && t.state === "awaiting_approval") {
    qc.invalidateQueries({ queryKey: ["browser-task", id] });
  }
  return (
    <section className="card mb-6 overflow-hidden" aria-live="polite">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-sand-100 px-5 py-4">
        <div className="min-w-0">
          <p className="eyebrow">Browser agent · {t.engine === "playwright" ? "headless Chromium" : t.engine === "http" ? "Tandem simulated site" : "hand-off"}</p>
          <h2 className="mt-0.5 text-[16px] font-semibold">{t.site_name}</h2>
          <p className="text-[13px] text-ink-500">{describeParams(t.params)}</p>
        </div>
        <div className="flex items-center gap-2">
          {RUNNING.has(t.state) && <Loader2 className="h-4 w-4 animate-spin text-lagoon-600" />}
          <StatusPill status={t.state} />
          {!["completed", "cancelled", "requires_manual", "failed", "blocked"].includes(t.state) && (
            <Button size="sm" variant="ghost" onClick={async () => { await api.post(`/browser/tasks/${t.id}/cancel`); task.refetch(); }}>Cancel</Button>
          )}
          <button onClick={onClose} className="rounded-lg p-1.5 text-ink-400 hover:bg-sand-100" aria-label="Close task"><XCircle className="h-4 w-4" /></button>
        </div>
      </header>
      <div className="grid gap-6 p-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <ol className="space-y-3" aria-label="Agent steps">
          {t.log.map((s) => (
            <li key={s.step} className="flex gap-3">
              <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-sand-100 text-[11px] font-semibold text-ink-600">{s.step}</span>
              <div className="min-w-0 flex-1">
                <p className="text-[13.5px] text-ink-800"><span className="font-medium capitalize">{s.action.replace(/_/g, " ")}</span> — {s.reason}</p>
                {s.url && <p className="truncate text-[11.5px] text-ink-400">{s.title ? `${s.title} · ` : ""}{s.url}</p>}
                {s.screenshot && (
                  <img src={`/api/v1/browser/tasks/${t.id}/steps/${s.step}/screenshot`} alt={`Page at step ${s.step}`} loading="lazy"
                    className="mt-2 w-full rounded-lg border border-sand-200" />
                )}
                {!s.screenshot && s.page_text && (
                  <details className="mt-1"><summary className="cursor-pointer text-[12px] text-ink-400"><ImageIcon className="mr-1 inline h-3 w-3" />Page text the agent saw</summary>
                    <p className="mt-1 rounded-lg bg-sand-50 p-2 text-[12px] text-ink-500">{s.page_text}</p></details>
                )}
              </div>
            </li>
          ))}
        </ol>
        <div className="space-y-4">
          {t.result.offers && t.result.offers.length > 0 && (
            <div>
              <p className="eyebrow mb-2">Options the agent found</p>
              <ul className="space-y-1.5 text-[13px]">
                {t.result.offers.map((o, i) => (
                  <li key={i} className={clsx("flex justify-between gap-3 rounded-lg px-3 py-2", t.result.selected?.offer_id === o.offer_id && o.offer_id ? "bg-lagoon-50 text-lagoon-700" : "bg-sand-50")}>
                    <span className="truncate">{o.title ?? `${o.offer_id} ${o.depart}–${o.arrive}`}</span>
                    <span className="shrink-0 font-medium">{money(o.total ?? o.price ?? null, o.currency ?? "EUR")}</span>
                  </li>
                ))}
              </ul>
              {t.result.selection_reason && <p className="mt-2 text-[12.5px] text-ink-500">Chosen: {t.result.selection_reason}.</p>}
            </div>
          )}
          {action.data && <ActionCard action={action.data} />}
          {t.stop_reason && t.state !== "awaiting_approval" && <InfoNote tone={t.state === "completed" ? "lagoon" : "amber"}>{t.stop_reason}</InfoNote>}
          {t.handoff_url && t.state !== "completed" && (
            <a href={t.handoff_url} target="_blank" rel="noopener noreferrer" className="inline-flex h-10 items-center gap-2 rounded-xl bg-lagoon-900 px-4 text-[14px] font-medium text-white hover:bg-ink-800">
              Continue on {t.site_name} <ExternalLink className="h-4 w-4" />
            </a>
          )}
          {t.state === "completed" && t.result.reservation_id && t.trip_id && (
            <Link to={`/trips/${t.trip_id}`} className="inline-flex h-10 items-center gap-2 rounded-xl border border-sand-200 bg-white px-4 text-[14px] font-medium hover:bg-sand-50">View it in your trip</Link>
          )}
        </div>
      </div>
    </section>
  );
}
