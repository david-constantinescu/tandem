import { ArrowRight, Compass, FileUp, MessageCircle, Plane, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { ActionCard } from "@/components/activities/ActionCard";
import { ConflictList } from "@/components/trips/ConflictList";
import { EventIcon } from "@/components/trips/EventIcon";
import { EmptyState, LinkButton, PageLoader, SectionTitle, StatusPill } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { daysUntil, fmtDateTime, fmtRange, fmtTime, relativeTime } from "@/lib/format";
import { useApprovals, useConflicts, useInbox, useItinerary, useTrips } from "@/lib/queries";
import type { Trip } from "@/lib/types";

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

export default function HomePage() {
  const { user } = useAuth();
  const trips = useTrips();
  const inbox = useInbox();
  const approvals = useApprovals("awaiting_approval");

  if (trips.isLoading) return <PageLoader />;
  const list = trips.data ?? [];
  const featured = list.find((t) => t.stats.phase === "current") ?? list.find((t) => t.stats.phase === "upcoming") ?? null;
  const others = list.filter((t) => t.id !== featured?.id && (t.stats.phase === "upcoming" || t.stats.phase === "planning")).slice(0, 3);
  const review = (inbox.data?.data ?? []).filter((d) => d.status === "awaiting_review").slice(0, 4);
  const recent = (inbox.data?.data ?? []).slice(0, 5);

  return (
    <div>
      <div className="mb-7">
        <p className="eyebrow mb-2">{new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" })}</p>
        <h1 className="display text-[30px] leading-tight sm:text-[36px]">{greeting()}{user?.display_name ? `, ${user.display_name.split(" ")[0]}` : ""}.</h1>
      </div>

      {!featured && list.length === 0 ? (
        <EmptyState
          icon={<Plane className="h-8 w-8" />}
          title="Your trips will appear here"
          body="Upload a booking confirmation, screenshot or email and Tandem will build the trip for you."
          action={<LinkButton to="/inbox" variant="primary" icon={<FileUp className="h-4 w-4" />}>Add your first booking</LinkButton>}
        />
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
          <div className="space-y-6">
            {featured && <FeaturedTrip trip={featured} />}
            {(approvals.data?.length ?? 0) > 0 && (
              <section>
                <SectionTitle action={<Link to="/approvals" className="text-[13px] text-lagoon-600 hover:underline">All approvals</Link>}>Waiting for your approval</SectionTitle>
                <div className="space-y-3">{approvals.data!.slice(0, 2).map((a) => <ActionCard key={a.id} action={a} />)}</div>
              </section>
            )}
            {others.length > 0 && (
              <section>
                <SectionTitle>Also coming up</SectionTitle>
                <div className="grid gap-3 sm:grid-cols-2">
                  {others.map((t) => (
                    <Link key={t.id} to={`/trips/${t.id}`} className="card p-4 transition hover:shadow-[var(--shadow-lift)]">
                      <p className="text-[15px] font-semibold">{t.name}</p>
                      <p className="mt-0.5 text-[13px] text-ink-500">{fmtRange(t.start_date, t.end_date)}</p>
                    </Link>
                  ))}
                </div>
              </section>
            )}
          </div>

          <div className="space-y-6">
            <section className="card p-4">
              <SectionTitle>Quick actions</SectionTitle>
              <div className="grid grid-cols-3 gap-2">
                {[
                  { to: "/inbox", icon: <FileUp className="h-5 w-5" />, label: "Add booking" },
                  { to: "/assistant", icon: <MessageCircle className="h-5 w-5" />, label: "Ask Tandem" },
                  { to: "/discover", icon: <Compass className="h-5 w-5" />, label: "Discover" },
                ].map((q) => (
                  <Link key={q.to} to={q.to} className="flex flex-col items-center gap-2 rounded-xl bg-sand-50 px-2 py-4 text-center text-[12.5px] font-medium text-ink-700 transition hover:bg-sand-100">
                    <span className="text-lagoon-600">{q.icon}</span>{q.label}
                  </Link>
                ))}
              </div>
            </section>
            {review.length > 0 && (
              <section className="card p-4">
                <SectionTitle action={<Link to="/inbox" className="text-[13px] text-lagoon-600 hover:underline">Inbox</Link>}>To review</SectionTitle>
                <ul className="divide-y divide-sand-100">
                  {review.map((d) => (
                    <li key={d.id}><Link to={`/inbox/${d.id}`} className="flex items-center justify-between gap-3 py-2.5 text-[13.5px] hover:text-lagoon-700">
                      <span className="truncate">{d.filename}</span><span className="shrink-0 text-[12px] text-amber-ink">{d.pending_review_count} item{d.pending_review_count === 1 ? "" : "s"}</span>
                    </Link></li>
                  ))}
                </ul>
              </section>
            )}
            {recent.length > 0 && (
              <section className="card p-4">
                <SectionTitle>Recent inbox activity</SectionTitle>
                <ul className="space-y-2.5">
                  {recent.map((d) => (
                    <li key={d.id} className="flex items-center justify-between gap-3 text-[13px]">
                      <Link to={`/inbox/${d.id}`} className="truncate text-ink-700 hover:text-lagoon-700">{d.filename}</Link>
                      <span className="flex shrink-0 items-center gap-2"><StatusPill status={d.status} /><span className="hidden text-[11.5px] text-ink-400 sm:inline">{relativeTime(d.created_at)}</span></span>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function FeaturedTrip({ trip }: { trip: Trip }) {
  const itinerary = useItinerary(trip.id);
  const conflicts = useConflicts(trip.id);
  const days = daysUntil(trip.start_date);
  const now = Date.now();
  const upcoming = (itinerary.data ?? []).filter((e) => new Date(e.start_at).getTime() >= now && e.status !== "cancelled");
  const next = upcoming.filter((e) => e.status !== "suggested").slice(0, 4);
  const suggestions = (itinerary.data ?? []).filter((e) => e.status === "suggested").slice(0, 2);
  const alerts = (conflicts.data ?? []).filter((c) => c.severity !== "info");

  return (
    <section className="overflow-hidden rounded-[22px] border border-sand-200 bg-white shadow-[var(--shadow-card)]">
      <div className="relative bg-lagoon-900 px-5 py-6 text-white sm:px-7">
        <div className="absolute -right-10 -top-16 h-56 w-56 rounded-full bg-clay-500/25 blur-2xl" />
        <p className="eyebrow relative !text-lagoon-100/70">{trip.stats.phase === "current" ? "Happening now" : days !== null ? (days === 0 ? "Starts today" : days === 1 ? "Starts tomorrow" : `In ${days} days`) : "Upcoming"}</p>
        <h2 className="display relative mt-1.5 text-[28px] leading-tight text-white">{trip.name}</h2>
        <p className="relative mt-1 text-[14.5px] text-lagoon-100/85">{fmtRange(trip.start_date, trip.end_date)} · {trip.destinations.map((d) => d.name).join(" → ") || trip.primary_destination}</p>
        <Link to={`/trips/${trip.id}`} className="relative mt-5 inline-flex items-center gap-1.5 rounded-xl bg-white/10 px-3.5 py-2 text-[13.5px] font-medium text-white backdrop-blur transition hover:bg-white/20">
          Open itinerary <ArrowRight className="h-4 w-4" />
        </Link>
      </div>
      <div className="grid grid-cols-1 gap-6 p-5 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] sm:p-7">
        <div>
          <p className="eyebrow mb-3">Next up</p>
          {next.length === 0 ? <p className="text-[13.5px] text-ink-400">Nothing scheduled yet.</p> : (
            <ul className="space-y-3">
              {next.map((e) => (
                <li key={e.id} className="flex items-center gap-3">
                  <EventIcon type={e.type} size="sm" />
                  <div className="min-w-0">
                    <p className="truncate text-[14px] font-medium">{e.title}</p>
                    <p className="text-[12.5px] text-ink-400">{fmtDateTime(e.start_local)}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="space-y-5">
          <div>
            <p className="eyebrow mb-3">Alerts</p>
            {alerts.length ? <ConflictList conflicts={alerts} tripId={trip.id} compact /> : <p className="text-[13.5px] text-ink-400">No clashes or tight connections.</p>}
          </div>
          {suggestions.length > 0 && (
            <div>
              <p className="eyebrow mb-2 flex items-center gap-1"><Sparkles className="h-3 w-3" /> Suggested</p>
              {suggestions.map((s) => (
                <p key={s.id} className="text-[13.5px] text-violet-ink">{s.title} · {fmtTime(s.start_local)}</p>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
