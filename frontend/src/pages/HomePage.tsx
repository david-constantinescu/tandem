import { ArrowUpRight, Compass, FileUp, Globe, MessageCircle, Plane, Sparkles } from "lucide-react";
import { motion } from "motion/react";
import { Link } from "react-router-dom";
import { ActionCard } from "@/components/activities/ActionCard";
import { RouteDoodle, Stagger, StaggerItem, spring } from "@/components/motion";
import { ConflictList } from "@/components/trips/ConflictList";
import { EventIcon } from "@/components/trips/EventIcon";
import { InstallCard } from "@/components/pwa";
import { EmptyState, LinkButton, LoadError, PageLoader, StatusPill } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { daysUntil, fmtDateTime, fmtRange, fmtTime, relativeTime } from "@/lib/format";
import { useApprovals, useConflicts, useInbox, useItinerary, useTrips } from "@/lib/queries";
import type { Trip } from "@/lib/types";

function greeting() {
  const h = new Date().getHours();
  return h < 5 ? "Up late" : h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

const QUICK = [
  { to: "/inbox", icon: FileUp, label: "Add a booking", hint: "PDF, screenshot, email" },
  { to: "/assistant", icon: MessageCircle, label: "Ask Tandem", hint: "About your plans" },
  { to: "/discover", icon: Compass, label: "Find things to do", hint: "That fit your days" },
  { to: "/websites", icon: Globe, label: "Book on sites", hint: "Trains, buses, museums" },
];

export default function HomePage() {
  const { user } = useAuth();
  const trips = useTrips();
  const inbox = useInbox();
  const approvals = useApprovals("awaiting_approval");

  if (trips.isLoading) return <PageLoader />;
  if (trips.isError && !trips.data) return <LoadError what="trips" onRetry={() => trips.refetch()} retrying={trips.isFetching} />;
  const list = trips.data ?? [];
  const featured = list.find((t) => t.stats.phase === "current") ?? list.find((t) => t.stats.phase === "upcoming") ?? null;
  const others = list.filter((t) => t.id !== featured?.id && (t.stats.phase === "upcoming" || t.stats.phase === "planning")).slice(0, 3);
  const review = (inbox.data?.data ?? []).filter((d) => d.status === "awaiting_review").slice(0, 4);
  const recent = (inbox.data?.data ?? []).slice(0, 5);
  const first = user?.display_name?.split(" ")[0];

  return (
    <div>
      <header className="mb-6 sm:mb-8">
        <p className="kicker">{greeting()}{first ? "," : "."}</p>
        {first && <h1 className="display text-[40px] leading-[1.02] tracking-[-0.025em] sm:text-[52px]">{first}.</h1>}
        <p className="mt-2 text-[15px] text-ink-500">{new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" })}</p>
      </header>

      <div className="-mx-4 mb-7 flex snap-x scroll-px-4 gap-2.5 overflow-x-auto px-4 pb-1 [scrollbar-width:none] sm:mx-0 sm:grid sm:grid-cols-4 sm:overflow-visible sm:px-0">
        {QUICK.map((q, i) => (
          <motion.div key={q.to} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ ...spring, delay: 0.05 * i }} className="shrink-0 snap-start">
            <Link to={q.to} className="group flex min-w-[150px] items-center gap-3 rounded-2xl border border-sand-200/80 bg-white px-3.5 py-3 shadow-[var(--shadow-card)] transition active:scale-[0.97] sm:min-w-0">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-apricot-soft text-clay-600 transition group-hover:rotate-[-6deg]"><q.icon className="h-[18px] w-[18px]" /></span>
              <span className="min-w-0">
                <span className="block truncate text-[14px] font-semibold leading-tight text-ink-900">{q.label}</span>
                <span className="block truncate text-[12px] text-ink-400">{q.hint}</span>
              </span>
            </Link>
          </motion.div>
        ))}
      </div>

      {!featured && list.length === 0 ? (
        <EmptyState icon={<Plane />} title="Your next trip starts with one booking"
          body="Drop in a confirmation, screenshot or email. Tandem reads it and builds the trip around it."
          action={<LinkButton to="/inbox" variant="primary" icon={<FileUp className="h-4 w-4" />}>Add your first booking</LinkButton>} />
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
          <Stagger className="space-y-6">
            {featured && <StaggerItem><BoardingPass trip={featured} /></StaggerItem>}
            {(approvals.data?.length ?? 0) > 0 && (
              <StaggerItem>
                <SectionHead title="Waiting for you" link={{ to: "/approvals", label: "All approvals" }} />
                <div className="space-y-3">{approvals.data!.slice(0, 2).map((a) => <ActionCard key={a.id} action={a} />)}</div>
              </StaggerItem>
            )}
            {others.length > 0 && (
              <StaggerItem>
                <SectionHead title="Also on the horizon" />
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  {others.map((t) => (
                    <Link key={t.id} to={`/trips/${t.id}`} className="card p-4 transition active:scale-[0.98] hover:shadow-[var(--shadow-lift)]">
                      <p className="display text-[19px]">{t.name}</p>
                      <p className="mt-0.5 text-[13px] text-ink-500">{fmtRange(t.start_date, t.end_date)}</p>
                    </Link>
                  ))}
                </div>
              </StaggerItem>
            )}
          </Stagger>

          <Stagger className="space-y-6">
            {review.length > 0 && (
              <StaggerItem className="card p-4">
                <SectionHead title="To review" link={{ to: "/inbox", label: "Inbox" }} />
                <ul className="divide-y divide-sand-100">
                  {review.map((d) => (
                    <li key={d.id}><Link to={`/inbox/${d.id}`} className="flex min-h-11 items-center justify-between gap-3 py-2 text-[14px] hover:text-lagoon-700">
                      <span className="truncate">{d.filename}</span><span className="shrink-0 text-[12.5px] font-medium text-amber-ink">{d.pending_review_count} to check</span>
                    </Link></li>
                  ))}
                </ul>
              </StaggerItem>
            )}
            {recent.length > 0 && (
              <StaggerItem className="card p-4">
                <SectionHead title="Lately in your inbox" />
                <ul className="space-y-1">
                  {recent.map((d) => (
                    <li key={d.id}>
                      <Link to={`/inbox/${d.id}`} className="flex min-h-11 items-center justify-between gap-3 rounded-lg text-[13.5px] text-ink-700 hover:text-lagoon-700">
                        <span className="truncate">{d.filename}</span>
                        <span className="flex shrink-0 items-center gap-2"><StatusPill status={d.status} /><span className="hidden text-[11.5px] text-ink-400 xl:inline">{relativeTime(d.created_at)}</span></span>
                      </Link>
                    </li>
                  ))}
                </ul>
              </StaggerItem>
            )}
          </Stagger>
        </div>
      )}
      <InstallCard className="mt-6" />
    </div>
  );
}

function SectionHead({ title, link }: { title: string; link?: { to: string; label: string } }) {
  return (
    <div className="mb-3 flex items-baseline justify-between gap-3">
      <h2 className="display text-[21px] leading-tight">{title}</h2>
      {link && <Link to={link.to} className="text-[13.5px] font-medium text-lagoon-600 hover:underline">{link.label}</Link>}
    </div>
  );
}

function BoardingPass({ trip }: { trip: Trip }) {
  const { user } = useAuth();
  const itinerary = useItinerary(trip.id);
  const conflicts = useConflicts(trip.id);
  const days = daysUntil(trip.start_date);
  const now = Date.now();
  const upcoming = (itinerary.data ?? []).filter((e) => new Date(e.start_at).getTime() >= now && e.status !== "cancelled");
  const next = upcoming.filter((e) => e.status !== "suggested").slice(0, 4);
  const suggestions = (itinerary.data ?? []).filter((e) => e.status === "suggested").slice(0, 2);
  const alerts = (conflicts.data ?? []).filter((c) => c.severity !== "info");
  const dest = trip.destinations.map((d) => d.name).join(" · ") || trip.primary_destination || trip.name;
  const from = (user?.home_city || "Home").toUpperCase();
  const to = (trip.destinations[0]?.name || trip.primary_destination || "").toUpperCase();
  const when = trip.stats.phase === "current" ? "Happening now" : days === 0 ? "Today" : days === 1 ? "Tomorrow" : days !== null ? `In ${days} days` : "Coming up";

  return (
    <section className="overflow-hidden rounded-[28px] border border-sand-200 bg-white shadow-[var(--shadow-float)]">
      <Link to={`/trips/${trip.id}`} aria-label={`Open ${trip.name}`} className="group relative block overflow-hidden bg-lagoon-900 px-5 pb-6 pt-5 text-white sm:px-7">
        <div className="absolute -right-16 -top-20 h-64 w-64 rounded-full bg-clay-500/30 blur-3xl" />
        <div className="absolute -bottom-24 left-6 h-56 w-56 rounded-full bg-lagoon-500/30 blur-3xl" />
        <div className="relative flex items-start justify-between gap-3">
          <span className="flex items-center gap-3">
            <span className="rounded-full bg-white/12 px-2.5 py-1 text-[12px] font-medium text-lagoon-50 backdrop-blur">{when}</span>
            {(trip.stats.reservations ?? 0) > 0 && (
              <span className="rotate-[-6deg] rounded-md border-2 border-apricot/80 px-2 py-0.5 text-[11px] font-bold tracking-[0.14em] text-apricot">
                {trip.stats.reservations} BOOKED
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
          <p className="eyebrow mb-3">Next up</p>
          {next.length === 0 ? <p className="text-[14px] text-ink-400">Nothing scheduled yet.</p> : (
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
            <p className="eyebrow mb-3">Heads up</p>
            {alerts.length ? <ConflictList conflicts={alerts} tripId={trip.id} compact /> : <p className="text-[14px] text-ink-400">No clashes or tight connections.</p>}
          </div>
          {suggestions.length > 0 && (
            <div>
              <p className="eyebrow mb-2 flex items-center gap-1"><Sparkles className="h-3.5 w-3.5 text-violet-ink" /> Worth a look</p>
              {suggestions.map((s) => <p key={s.id} className="text-[14px] text-violet-ink">{s.title} · {fmtTime(s.start_local)}</p>)}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
