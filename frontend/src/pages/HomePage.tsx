import { AlertTriangle, ArrowUpRight, ChevronRight, FileSearch, FileUp, Plane, ShieldCheck, Sparkles } from "lucide-react";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { Choices } from "@/components/assistant/Choices";
import { Composer } from "@/components/assistant/Composer";
import { MD } from "@/components/assistant/markdown";
import { Link, useNavigate } from "react-router-dom";
import { useAdd } from "@/components/AddSheet";
import { RouteDoodle } from "@/components/motion";
import { InstallCard } from "@/components/pwa";
import { EventIcon } from "@/components/trips/EventIcon";
import { WeatherChip } from "@/components/trips/TripContext";
import { Button, LoadError, PageLoader } from "@/components/ui";
import { Dialog } from "@/components/ui/Dialog";
import { ConflictList } from "@/components/trips/ConflictList";
import { NewsList } from "@/components/trips/TripContext";
import { useToast } from "@/components/ui/Toast";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { daysUntil, fmtDateTime, fmtRange, fmtToday, relativeTime, whenLabel } from "@/lib/format";
import { useT, type Key } from "@/lib/i18n";
import { useApprovals, useConflicts, useConversation, useConversations, useInbox, useItinerary, useTripContext, useTrips } from "@/lib/queries";
import type { Conversation, Trip } from "@/lib/types";

function greetingKey(): Key {
  const h = new Date().getHours();
  return h < 5 ? "home.greeting.late" : h < 12 ? "home.greeting.morning" : h < 18 ? "home.greeting.afternoon" : "home.greeting.evening";
}

/** Home: Tandem's latest word (with answers you can tap), a way to ask, and the next trip. It scrolls like any page. */
export default function HomePage() {
  const { user } = useAuth();
  const { t } = useT();
  const trips = useTrips();
  if (trips.isLoading) return <PageLoader />;
  if (trips.isError && !trips.data) return <LoadError title={t("load.trips")} onRetry={() => trips.refetch()} retrying={trips.isFetching} />;
  const list = trips.data ?? [];
  const featured = list.find((x) => x.stats.phase === "current") ?? list.find((x) => ["upcoming", "planning"].includes(x.stats.phase ?? "")) ?? null;
  const first = (user?.display_name || "").split(" ")[0];

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4 pb-8">
      <div>
        <p className="kicker">{fmtToday()}</p>
        <h1 className="display text-[28px] leading-[1.08] tracking-[-0.02em] sm:text-[34px]">{t(greetingKey())}{first ? `, ${first}` : ""}</h1>
      </div>
      <LatestUpdate />
      <AskBar tripId={featured?.id} />
      {featured ? <BoardingPass trip={featured} /> : <Welcome />}
      <InstallCard />
    </div>
  );
}

/** The newest thing Tandem wrote by itself, as a chat bubble; tapping an answer continues in the chat. */
function LatestUpdate() {
  const { t } = useT();
  const navigate = useNavigate();
  const conversations = useConversations();
  const updates = conversations.data?.find((c) => c.kind === "updates");
  const conv = useConversation(updates?.id ?? "");
  const mine = [...(conv.data?.messages ?? [])].reverse();
  const last = mine.find((m) => m.model === "proactive") ?? mine.find((m) => m.role === "assistant");
  if (!updates || !last) return null;
  const msgs = conv.data!.messages;
  const answered = msgs.slice(msgs.findIndex((m) => m.id === last.id) + 1).some((m) => m.role === "user");
  const options = answered ? [] : last.references.find((r) => r.type === "choices")?.options ?? [];
  return (
    <section className="rounded-[24px] border border-sand-200 bg-white p-4 shadow-[var(--shadow-card)]">
      <div className="flex items-center gap-2.5">
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-lagoon-900 text-white"><Sparkles className="h-4 w-4 text-apricot" /></span>
        <p className="text-[13px] font-semibold text-ink-900">Tandem</p>
        <span className="text-[12px] text-ink-400">· {relativeTime(last.created_at)}</span>
        <Link to={`/assistant/${updates.id}`} className="ml-auto text-[13px] font-medium text-lagoon-600">{t("home.openChat")}</Link>
      </div>
      <div className="prose-chat mt-2.5 line-clamp-6 text-[15px] leading-relaxed text-ink-800 [overflow-wrap:anywhere]"><ReactMarkdown components={MD}>{last.content}</ReactMarkdown></div>
      {options.length > 0 && <div className="mt-3"><Choices options={options} onChoose={(o) => navigate(`/assistant/${updates.id}`, { state: { prompt: o } })} /></div>}
    </section>
  );
}

/** Ask the assistant straight from Home: opens a conversation about the next trip with the question already sent. */
function AskBar({ tripId }: { tripId?: string }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const toast = useToast();
  const { t } = useT();
  const submit = async (value: string) => {
    const prompt = value.trim();
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
  return <Composer value={text} onChange={setText} onSend={(v) => submit(v)} busy={busy} placeholder={t("home.askPlaceholder")} />;
}

function Welcome() {
  const { t } = useT();
  const { openAdd } = useAdd();
  return (
    <section className="relative overflow-hidden rounded-[28px] bg-lagoon-900 p-6 text-white">
      <div className="absolute -right-16 -top-20 h-56 w-56 rounded-full bg-clay-500/30 blur-3xl" />
      <Plane className="relative h-6 w-6 text-apricot" />
      <h2 className="display relative mt-3 text-[28px] leading-tight">{t("home.welcome.title")}</h2>
      <p className="relative mt-1.5 max-w-md text-[14.5px] text-white/75">{t("home.welcome.body")}</p>
      <Button onClick={openAdd} size="lg" className="relative mt-5 w-full sm:w-auto" icon={<FileUp className="h-4 w-4" />}>{t("home.welcome.cta")}</Button>
    </section>
  );
}

function BoardingPass({ trip }: { trip: Trip }) {
  const { user } = useAuth();
  const { t, tp } = useT();
  const itinerary = useItinerary(trip.id);
  const conflicts = useConflicts(trip.id);
  const context = useTripContext(trip.id);
  const inbox = useInbox();
  const approvals = useApprovals("awaiting_approval");
  const [sheet, setSheet] = useState(false);
  const now = Date.now();
  const next = (itinerary.data ?? []).filter((e) => new Date(e.start_at).getTime() >= now && !["cancelled", "suggested"].includes(e.status)).slice(0, 3);
  const clashes = (conflicts.data ?? []).filter((c) => c.severity !== "info");
  const waiting = (inbox.data?.data ?? []).filter((d) => d.status === "awaiting_review").length + (approvals.data?.length ?? 0);
  // Only news that can change these plans: it names the trip's dates, or it is today's and the trip is under way.
  const fresh = (n: { published: string | null }) => !!n.published && now - new Date(n.published).getTime() < 24 * 3600_000;
  const news = (context.data?.news.items ?? []).filter((n) => n.kind !== "news" && (n.mentions_dates.length > 0 || (trip.stats.phase === "current" && fresh(n))));
  const forecast = (context.data?.weather.days ?? []).slice(0, 4);
  const dest = trip.destinations.map((d) => d.name).join(" · ") || trip.primary_destination || trip.name;
  const from = (user?.home_city || t("home.from")).toLocaleUpperCase();
  const to = (trip.destinations[0]?.name || trip.primary_destination || "").toLocaleUpperCase();
  const when = trip.stats.phase === "current" ? t("home.happeningNow") : whenLabel(daysUntil(trip.start_date));
  const flags = clashes.length + news.length;

  return (
    <section className="overflow-hidden rounded-[28px] border border-sand-200 bg-white shadow-[var(--shadow-float)]">
      <Link to={`/trips/${trip.id}`} aria-label={t("home.openTrip", { name: trip.name })} className="group relative block shrink-0 overflow-hidden bg-lagoon-900 px-5 pb-4 pt-4 text-white">
        <div className="absolute -right-16 -top-20 h-56 w-56 rounded-full bg-clay-500/30 blur-3xl" />
        <div className="relative flex items-center justify-between gap-3">
          <span className="flex items-center gap-2.5">
            <span className="rounded-full bg-white/12 px-2.5 py-0.5 text-[12px] font-medium text-white/90">{when}</span>
            {(trip.stats.reservations ?? 0) > 0 && (
              <span className="rotate-[-5deg] rounded-md border-2 border-apricot/80 px-1.5 py-px text-[10.5px] font-bold uppercase tracking-[0.14em] text-apricot">{tp("home.booked", trip.stats.reservations ?? 0)}</span>
            )}
          </span>
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-white/10 transition group-hover:rotate-45"><ArrowUpRight className="h-4 w-4" /></span>
        </div>
        <h2 className="display relative mt-2.5 text-[32px] leading-[1.02] tracking-[-0.02em] text-white sm:text-[40px]">{dest}</h2>
        <p className="relative mt-1 truncate text-[13.5px] text-white/75">{trip.name} · {fmtRange(trip.start_date, trip.end_date)}</p>
        <RouteDoodle light className="relative mt-2 w-full text-white/90 [&>svg]:!h-9" from={from} to={to} />
      </Link>
      <div className="perforated shrink-0" />
      <div className="flex flex-col gap-3 px-5 pb-4 pt-3">
        <div className="min-h-0">
          <p className="eyebrow mb-1.5">{t("home.nextUp")}</p>
          {next.length === 0 ? <p className="text-[14px] text-ink-400">{t("home.nothingScheduled")}</p> : (
            <ul className="space-y-1.5">
              {next.map((e) => (
                <li key={e.id} className="flex items-center gap-3">
                  <EventIcon type={e.type} size="sm" />
                  <div className="min-w-0">
                    <p className="truncate text-[14px] font-medium leading-tight">{e.title}</p>
                    <p className="text-[12px] text-ink-400">{fmtDateTime(e.start_local)}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
        {forecast.length > 0 && <div className="flex shrink-0 flex-wrap gap-1.5">{forecast.map((d) => <WeatherChip key={d.date} day={d} withDay />)}</div>}
        <div className="flex flex-col gap-1.5">
          {waiting > 0 && (
            <Link to="/inbox" className="flex min-h-11 items-center gap-2.5 rounded-xl bg-clay-50 px-3 text-[13.5px] font-medium text-clay-600 active:scale-[0.99]">
              <FileSearch className="h-4 w-4 shrink-0" /><span className="flex-1">{tp("home.waiting", waiting)}</span><ChevronRight className="h-4 w-4" />
            </Link>
          )}
          {flags > 0 ? (
            <button onClick={() => setSheet(true)} className="flex min-h-11 items-center gap-2.5 rounded-xl bg-amber-soft px-3 text-left text-[13.5px] font-medium text-amber-ink active:scale-[0.99]">
              <AlertTriangle className="h-4 w-4 shrink-0" /><span className="min-w-0 flex-1 truncate">{clashes[0]?.title ?? news[0]?.title}</span>
              {flags > 1 && <span className="rounded-full bg-white/70 px-1.5 text-[11.5px]">+{flags - 1}</span>}
            </button>
          ) : waiting === 0 && (
            <p className="flex min-h-11 items-center gap-2.5 rounded-xl bg-lagoon-50/70 px-3 text-[13.5px] text-lagoon-700"><ShieldCheck className="h-4 w-4 shrink-0" />{t("home.allClear")}</p>
          )}
        </div>
      </div>
      <Dialog open={sheet} onOpenChange={setSheet} title={t("home.headsUp")}>
        <div className="max-h-[60dvh] space-y-3 overflow-y-auto pb-2">
          {clashes.length > 0 && <ConflictList conflicts={clashes} tripId={trip.id} compact />}
          {news.length > 0 && <NewsList items={news} />}
        </div>
      </Dialog>
    </section>
  );
}
