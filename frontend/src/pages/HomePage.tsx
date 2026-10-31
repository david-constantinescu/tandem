import { ArrowUp, ArrowUpRight, ChevronRight, Compass, FileSearch, FileUp, Plane, ShieldCheck, Sparkles, Ticket } from "lucide-react";
import { motion } from "motion/react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAdd } from "@/components/AddSheet";
import { RouteDoodle, Stagger, StaggerItem, spring } from "@/components/motion";
import { ConflictList } from "@/components/trips/ConflictList";
import { EventIcon } from "@/components/trips/EventIcon";
import { InstallCard } from "@/components/pwa";
import { Button, LoadError, PageLoader } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { daysUntil, fmtDateTime, fmtRange, fmtTime, fmtToday, money, whenLabel } from "@/lib/format";
import { useT, type Key } from "@/lib/i18n";
import { useApprovals, useConflicts, useInbox, useItinerary, useTrips } from "@/lib/queries";
import type { Conversation, Trip } from "@/lib/types";

function greetingKey(): Key {
  const h = new Date().getHours();
  return h < 5 ? "home.greeting.late" : h < 12 ? "home.greeting.morning" : h < 18 ? "home.greeting.afternoon" : "home.greeting.evening";
}

export default function HomePage() {
  const { user } = useAuth();
  const trips = useTrips();
  const { t } = useT();
  const { openAdd } = useAdd();

  if (trips.isLoading) return <PageLoader />;
  if (trips.isError && !trips.data) return <LoadError title={t("load.trips")} onRetry={() => trips.refetch()} retrying={trips.isFetching} />;
  const list = trips.data ?? [];
  const featured = list.find((x) => x.stats.phase === "current") ?? list.find((x) => x.stats.phase === "upcoming") ?? null;
  const others = list.filter((x) => x.id !== featured?.id && (x.stats.phase === "upcoming" || x.stats.phase === "planning")).slice(0, 4);
  const first = user?.display_name?.split(" ")[0];

  const shortcuts = [
    { key: "add", icon: FileUp, label: t("home.short.add"), hint: t("home.short.addHint"), onClick: openAdd },
    { key: "do", icon: Compass, label: t("home.short.do"), hint: t("home.short.doHint"), to: featured ? `/explore?trip=${featured.id}` : "/explore" },
    { key: "tickets", icon: Ticket, label: t("home.short.tickets"), hint: t("home.short.ticketsHint"), to: `/explore?tab=tickets${featured ? `&trip=${featured.id}` : ""}` },
  ];

  return (
    <div>
      <header className="mb-5 sm:mb-7">
        <p className="kicker">{t(greetingKey())}{first ? "," : "."}</p>
        {first && <h1 className="display text-[40px] leading-[1.02] tracking-[-0.025em] sm:text-[52px]">{first}.</h1>}
        <p className="mt-2 text-[15px] text-ink-500">{fmtToday()}</p>
      </header>

      <AskBar tripId={featured?.id} />

      <div className="-mx-4 mb-7 mt-4 flex snap-x gap-2.5 overflow-x-auto scroll-px-4 px-4 pb-1 [scrollbar-width:none] sm:mx-0 sm:grid sm:grid-cols-3 sm:overflow-visible sm:px-0">
        {shortcuts.map((q, i) => {
          const body = (
            <>
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-apricot-soft text-clay-600 transition group-hover:rotate-[-6deg]"><q.icon className="h-[18px] w-[18px]" /></span>
              <span className="min-w-0 text-left">
                <span className="block truncate text-[14px] font-semibold leading-tight text-ink-900">{q.label}</span>
                <span className="block truncate text-[12px] text-ink-400">{q.hint}</span>
              </span>
            </>
          );
          const cls = "group flex w-full min-w-[160px] items-center gap-3 rounded-2xl border border-sand-200/80 bg-white px-3.5 py-3 shadow-[var(--shadow-card)] transition active:scale-[0.97] sm:min-w-0";
          return (
            <motion.div key={q.key} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ ...spring, delay: 0.05 * i }} className="shrink-0 snap-start sm:shrink">
              {q.to ? <Link to={q.to} className={cls}>{body}</Link> : <button onClick={q.onClick} className={cls}>{body}</button>}
            </motion.div>
          );
        })}
      </div>

      {list.length === 0 ? <Welcome /> : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
          <Stagger className="space-y-6">
            {featured && <StaggerItem><BoardingPass trip={featured} /></StaggerItem>}
            {others.length > 0 && (
              <StaggerItem>
                <SectionHead title={featured ? t("home.alsoComing") : t("home.yourTrips")} link={{ to: "/trips", label: t("home.allTrips") }} />
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  {others.map((x) => (
                    <Link key={x.id} to={`/trips/${x.id}`} className="card flex items-center justify-between gap-3 p-4 transition active:scale-[0.98] hover:shadow-[var(--shadow-lift)]">
                      <span className="min-w-0">
                        <span className="display block truncate text-[19px]">{x.name}</span>
                        <span className="mt-0.5 block text-[13px] text-ink-500">{fmtRange(x.start_date, x.end_date)}</span>
                      </span>
                      <ChevronRight className="h-4 w-4 shrink-0 text-ink-300" />
                    </Link>
                  ))}
                </div>
              </StaggerItem>
            )}
            {!featured && !others.length && (
              <StaggerItem><Link to="/trips" className="card flex items-center justify-between p-4 text-[15px] font-medium">{t("home.allTrips")}<ChevronRight className="h-4 w-4 text-ink-300" /></Link></StaggerItem>
            )}
          </Stagger>
          <Stagger className="space-y-6"><StaggerItem><NeedsYou /></StaggerItem></Stagger>
        </div>
      )}
      <InstallCard className="mt-6" />
    </div>
  );
}

/** Ask the assistant straight from Home: opens a conversation about the next trip with the question already sent. */
function AskBar({ tripId }: { tripId?: string }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const toast = useToast();
  const { t } = useT();
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const prompt = text.trim();
    if (!prompt) return;
    setBusy(true);
    try {
      const conv = await api.post<Conversation>("/assistant/conversations", { trip_id: tripId ?? null });
      navigate(`/assistant/${conv.id}`, { state: { prompt } });
    } catch (err) {
      toast(errorMessage(err), "error");
      setBusy(false);
    }
  };
  return (
    <form onSubmit={submit} className="flex items-center gap-2 rounded-[22px] border border-sand-200 bg-white py-1.5 pl-4 pr-1.5 shadow-[var(--shadow-card)] focus-within:border-lagoon-500 focus-within:ring-4 focus-within:ring-lagoon-100">
      <Sparkles className="h-[18px] w-[18px] shrink-0 text-violet-ink" aria-hidden />
      <input value={text} onChange={(e) => setText(e.target.value)} placeholder={t("home.askPlaceholder")} aria-label={t("home.askLabel")} enterKeyHint="send"
        className="h-10 min-w-0 flex-1 bg-transparent text-[16px] outline-none placeholder:text-ink-300 sm:text-[15px]" />
      <Button type="submit" size="sm" disabled={!text.trim()} loading={busy} aria-label={t("assistant.send")} className="!h-10 !w-10 shrink-0 !rounded-full !p-0"><ArrowUp className="h-[18px] w-[18px]" /></Button>
    </form>
  );
}

function Welcome() {
  const { t } = useT();
  const { openAdd } = useAdd();
  const steps: [Key, Key][] = [["home.welcome.step1", "home.welcome.step1Hint"], ["home.welcome.step2", "home.welcome.step2Hint"], ["home.welcome.step3", "home.welcome.step3Hint"]];
  return (
    <section className="overflow-hidden rounded-[28px] border border-sand-200 bg-white shadow-[var(--shadow-card)]">
      <div className="relative overflow-hidden bg-lagoon-900 px-5 py-6 text-white sm:px-7">
        <div className="absolute -right-16 -top-20 h-56 w-56 rounded-full bg-clay-500/30 blur-3xl" />
        <Plane className="relative h-6 w-6 text-apricot" />
        <h2 className="display relative mt-3 text-[28px] leading-tight">{t("home.welcome.title")}</h2>
        <p className="relative mt-1.5 max-w-md text-[14.5px] text-lagoon-100/85">{t("home.welcome.body")}</p>
      </div>
      <ol className="space-y-4 p-5 sm:p-7">
        {steps.map(([title, hint], i) => (
          <li key={title} className="flex gap-3.5">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-apricot-soft text-[13px] font-bold text-clay-600">{i + 1}</span>
            <span><span className="block text-[15px] font-semibold text-ink-900">{t(title)}</span><span className="block text-[13.5px] text-ink-500">{t(hint)}</span></span>
          </li>
        ))}
        <li className="pt-1"><Button onClick={openAdd} size="lg" className="w-full sm:w-auto" icon={<FileUp className="h-4 w-4" />}>{t("home.welcome.cta")}</Button></li>
      </ol>
    </section>
  );
}

function NeedsYou() {
  const { t, tp } = useT();
  const inbox = useInbox();
  const approvals = useApprovals("awaiting_approval");
  const review = (inbox.data?.data ?? []).filter((d) => d.status === "awaiting_review");
  const waiting = approvals.data ?? [];
  const total = review.length + waiting.length;
  return (
    <section className="card p-4 sm:p-5">
      <SectionHead title={t("home.needsYou")} link={total ? { to: "/inbox", label: t("home.openInbox") } : undefined} />
      {total === 0 ? (
        <p className="flex items-center gap-2.5 rounded-xl bg-lagoon-50/70 px-3.5 py-3 text-[14px] text-lagoon-700"><ShieldCheck className="h-4 w-4 shrink-0" />{t("home.allClear")}</p>
      ) : (
        <ul className="divide-y divide-sand-100">
          {waiting.slice(0, 3).map((a) => (
            <li key={a.id}>
              <Link to="/inbox" className="flex min-h-[56px] items-center gap-3 py-2">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-clay-50 text-clay-600"><ShieldCheck className="h-[18px] w-[18px]" /></span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[14.5px] font-medium text-ink-900">{a.title}</span>
                  <span className="block text-[12.5px] text-amber-ink">{a.cost !== null ? t("home.approveFor", { price: money(a.cost, a.currency) }) : t("home.approve")}</span>
                </span>
                <ChevronRight className="h-4 w-4 shrink-0 text-ink-300" />
              </Link>
            </li>
          ))}
          {review.slice(0, 4).map((d) => (
            <li key={d.id}>
              <Link to={`/inbox/${d.id}`} className="flex min-h-[56px] items-center gap-3 py-2">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-amber-soft text-amber-ink"><FileSearch className="h-[18px] w-[18px]" /></span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[14.5px] font-medium text-ink-900">{d.filename}</span>
                  <span className="block text-[12.5px] text-amber-ink">{tp("home.toCheck", d.pending_review_count || 1)}</span>
                </span>
                <ChevronRight className="h-4 w-4 shrink-0 text-ink-300" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function SectionHead({ title, link }: { title: string; link?: { to: string; label: string } }) {
  return (
    <div className="mb-3 flex items-baseline justify-between gap-3">
      <h2 className="display text-[21px] leading-tight">{title}</h2>
      {link && <Link to={link.to} className="shrink-0 text-[13.5px] font-medium text-lagoon-600 hover:underline">{link.label}</Link>}
    </div>
  );
}

function BoardingPass({ trip }: { trip: Trip }) {
  const { user } = useAuth();
  const { t, tp } = useT();
  const itinerary = useItinerary(trip.id);
  const conflicts = useConflicts(trip.id);
  const now = Date.now();
  const upcoming = (itinerary.data ?? []).filter((e) => new Date(e.start_at).getTime() >= now && e.status !== "cancelled");
  const next = upcoming.filter((e) => e.status !== "suggested").slice(0, 4);
  const suggestions = (itinerary.data ?? []).filter((e) => e.status === "suggested").slice(0, 2);
  const alerts = (conflicts.data ?? []).filter((c) => c.severity !== "info");
  const dest = trip.destinations.map((d) => d.name).join(" · ") || trip.primary_destination || trip.name;
  const from = (user?.home_city || t("home.from")).toLocaleUpperCase();
  const to = (trip.destinations[0]?.name || trip.primary_destination || "").toLocaleUpperCase();
  const when = trip.stats.phase === "current" ? t("home.happeningNow") : whenLabel(daysUntil(trip.start_date));

  return (
    <section className="overflow-hidden rounded-[28px] border border-sand-200 bg-white shadow-[var(--shadow-float)]">
      <Link to={`/trips/${trip.id}`} aria-label={t("home.openTrip", { name: trip.name })} className="group relative block overflow-hidden bg-lagoon-900 px-5 pb-6 pt-5 text-white sm:px-7">
        <div className="absolute -right-16 -top-20 h-64 w-64 rounded-full bg-clay-500/30 blur-3xl" />
        <div className="absolute -bottom-24 left-6 h-56 w-56 rounded-full bg-lagoon-500/30 blur-3xl" />
        <div className="relative flex items-start justify-between gap-3">
          <span className="flex items-center gap-3">
            <span className="rounded-full bg-white/12 px-2.5 py-1 text-[12px] font-medium text-lagoon-50 backdrop-blur">{when}</span>
            {(trip.stats.reservations ?? 0) > 0 && (
              <span className="rotate-[-6deg] rounded-md border-2 border-apricot/80 px-2 py-0.5 text-[11px] font-bold uppercase tracking-[0.14em] text-apricot">
                {tp("home.booked", trip.stats.reservations ?? 0)}
              </span>
            )}
          </span>
          <span className="flex h-9 w-9 items-center justify-center rounded-full bg-white/10 transition group-hover:rotate-45 group-active:scale-90"><ArrowUpRight className="h-4 w-4" /></span>
        </div>
        <h2 className="display relative mt-5 text-[36px] leading-[1.02] tracking-[-0.02em] text-white sm:text-[44px]">{dest}</h2>
        <p className="relative mt-1.5 text-[14.5px] text-lagoon-100/85">{trip.name} · {fmtRange(trip.start_date, trip.end_date)}</p>
        <RouteDoodle light className="relative mt-5 h-16 w-full text-lagoon-50" from={from} to={to} />
      </Link>
      <div className="perforated" />
      <div className="grid grid-cols-1 gap-6 p-5 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] sm:p-7">
        <div>
          <p className="eyebrow mb-3">{t("home.nextUp")}</p>
          {next.length === 0 ? <p className="text-[14px] text-ink-400">{t("home.nothingScheduled")}</p> : (
            <ul className="space-y-3">
              {next.map((e) => (
                <li key={e.id} className="flex items-center gap-3">
                  <EventIcon type={e.type} size="sm" />
                  <div className="min-w-0">
                    <p className="truncate text-[14.5px] font-medium">{e.title}</p>
                    <p className="text-[12.5px] text-ink-400">{fmtDateTime(e.start_local)}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="space-y-5">
          <div>
            <p className="eyebrow mb-3">{t("home.headsUp")}</p>
            {alerts.length ? <ConflictList conflicts={alerts} tripId={trip.id} compact /> : <p className="text-[14px] text-ink-400">{t("home.noClashes")}</p>}
          </div>
          {suggestions.length > 0 && (
            <div>
              <p className="eyebrow mb-2 flex items-center gap-1"><Sparkles className="h-3.5 w-3.5 text-violet-ink" /> {t("home.worthALook")}</p>
              {suggestions.map((s) => <p key={s.id} className="text-[14px] text-violet-ink">{s.title} · {fmtTime(s.start_local)}</p>)}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
