import { clsx } from "clsx";
import { Bookmark, ChevronDown, Search, SlidersHorizontal, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ActivityCard } from "@/components/activities/ActivityCard";
import { Stagger, StaggerItem } from "@/components/motion";
import { Badge, Button, EmptyState, ErrorNote, PageHeader, Spinner } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { fmtDate, money } from "@/lib/format";
import { useActivityProviders, useTrips } from "@/lib/queries";
import type { ActivityResult } from "@/lib/types";

const CATEGORIES = ["museums", "tours", "food", "workshops", "outdoor", "historical", "entertainment", "day trips", "attractions"];
const stateTone: Record<string, any> = {
  simulated_demo: "violet", search_only: "lagoon", redirect_only: "lagoon", sandbox_only: "amber", booking_enabled: "lagoon",
  awaiting_partner_approval: "neutral", not_configured: "neutral", disabled: "neutral", temporarily_unavailable: "rose",
};

type SearchResponse = { results: ActivityResult[]; providers: { provider: string; name: string; state: string; count: number; error: string | null }[] };

export default function DiscoverPage() {
  const [params] = useSearchParams();
  const trips = useTrips();
  const providers = useActivityProviders();
  const upcoming = useMemo(() => (trips.data ?? []).filter((t) => ["current", "upcoming", "planning"].includes(t.stats.phase ?? "")), [trips.data]);
  const [tripId, setTripId] = useState<string>(params.get("trip") ?? "");
  const trip = upcoming.find((t) => t.id === tripId);
  const [location, setLocation] = useState("");
  const [date, setDate] = useState("");
  const [after, setAfter] = useState("");
  const [before, setBefore] = useState("");
  const [cats, setCats] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [group, setGroup] = useState(2);
  const [accessible, setAccessible] = useState(false);
  const [more, setMore] = useState(false);

  useEffect(() => {
    if (!tripId && upcoming[0]) setTripId(upcoming[0].id);
  }, [upcoming, tripId]);
  useEffect(() => {
    if (trip) {
      setLocation(trip.primary_destination ?? "");
      if (trip.start_date && !date) {
        const d = new Date(trip.start_date + "T00:00:00Z");
        d.setUTCDate(d.getUTCDate() + 1);
        setDate(d.toISOString().slice(0, 10));
      }
    }
  }, [trip]); // eslint-disable-line react-hooks/exhaustive-deps

  const search = useMutation({
    mutationFn: () => api.post<SearchResponse>("/activities/search", {
      trip_id: tripId || null, location: location || null, date_from: date || null, date_to: date || null,
      start_after: after || null, end_before: before || null, categories: cats, query: query || null,
      max_price: maxPrice ? Number(maxPrice) : null, group_size: group, accessible_only: accessible,
    }),
  });
  const submit = (e: FormEvent) => { e.preventDefault(); search.mutate(); };

  return (
    <div>
      <PageHeader title="Discover" subtitle="Find things to do that fit around what's already planned." />

      <form onSubmit={submit} className="card overflow-hidden p-4 sm:p-5">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <label className="label" htmlFor="dtrip">Trip</label>
            <select id="dtrip" className="field" value={tripId} onChange={(e) => setTripId(e.target.value)}>
              <option value="">No trip (just browse)</option>
              {upcoming.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </div>
          <div><label className="label" htmlFor="dloc">Where</label><input id="dloc" className="field" value={location} onChange={(e) => setLocation(e.target.value)} placeholder="City" /></div>
          <div><label className="label" htmlFor="ddate">Day</label><input id="ddate" type="date" className="field" value={date} onChange={(e) => setDate(e.target.value)} min={trip?.start_date ?? undefined} max={trip?.end_date ?? undefined} /></div>
          <div className={clsx("grid-cols-2 gap-2 sm:grid", more ? "grid" : "hidden")}>
            <div><label className="label" htmlFor="dafter">After</label><input id="dafter" type="time" className="field" value={after} onChange={(e) => setAfter(e.target.value)} /></div>
            <div><label className="label" htmlFor="dbefore">Done by</label><input id="dbefore" type="time" className="field" value={before} onChange={(e) => setBefore(e.target.value)} /></div>
          </div>
        </div>
        <div className="-mx-4 mt-4 flex gap-1.5 overflow-x-auto px-4 [scrollbar-width:none] sm:mx-0 sm:flex-wrap sm:px-0" role="group" aria-label="Categories">
          {CATEGORIES.map((c) => (
            <button key={c} type="button" aria-pressed={cats.includes(c)} onClick={() => setCats(cats.includes(c) ? cats.filter((x) => x !== c) : [...cats, c])}
              className={clsx("h-9 shrink-0 rounded-full px-3.5 text-[13.5px] font-medium capitalize transition active:scale-95 pointer-coarse:h-10", cats.includes(c) ? "bg-lagoon-900 text-white" : "bg-sand-50 text-ink-600 ring-1 ring-sand-200 hover:bg-sand-100")}>{c}</button>
          ))}
        </div>
        <button type="button" onClick={() => setMore(!more)} aria-expanded={more} className="mt-3 flex min-h-11 items-center gap-1.5 text-[14px] font-medium text-lagoon-600 sm:hidden">
          <SlidersHorizontal className="h-4 w-4" /> {more ? "Fewer filters" : "Time, price & more"} <ChevronDown className={clsx("h-4 w-4 transition", more && "rotate-180")} />
        </button>
        <div className={clsx("mt-4 grid-cols-3 items-end gap-3 sm:grid sm:grid-cols-[1fr_120px_100px_auto]", more ? "grid" : "hidden")}>
          <div className="col-span-3 sm:col-span-1"><label className="label" htmlFor="dq">Keywords</label><input id="dq" className="field" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="e.g. walking tour" /></div>
          <div><label className="label" htmlFor="dmax">Max price</label><input id="dmax" type="number" min={0} className="field" value={maxPrice} onChange={(e) => setMaxPrice(e.target.value)} /></div>
          <div><label className="label" htmlFor="dg">People</label><input id="dg" type="number" min={1} max={20} className="field" value={group} onChange={(e) => setGroup(Math.max(1, +e.target.value))} /></div>
          <label className="flex h-[42px] items-center gap-2 text-[13.5px] text-ink-700 pointer-coarse:h-11"><input type="checkbox" className="h-5 w-5 accent-lagoon-600" checked={accessible} onChange={(e) => setAccessible(e.target.checked)} />Step-free</label>
        </div>
        <div className="mt-4 flex justify-end">
          <Button type="submit" size="lg" className="w-full sm:w-auto" loading={search.isPending} icon={<Search className="h-4 w-4" />}>Search</Button>
        </div>
      </form>

      <details className="group mt-4 text-[12.5px] text-ink-500 sm:open:block">
        <summary className="flex min-h-11 cursor-pointer list-none items-center gap-1.5 [&::-webkit-details-marker]:hidden">
          <span className="eyebrow">Where results come from</span>
          <span className="text-ink-300">· {(providers.data ?? []).length} source{(providers.data ?? []).length === 1 ? "" : "s"}</span>
          <ChevronDown className="h-3.5 w-3.5 text-ink-300 transition group-open:rotate-180" />
        </summary>
        <div className="flex flex-wrap gap-2 pb-1">
          {(providers.data ?? []).map((p) => (
            <span key={p.key} title={p.notes.join(" ")}><Badge tone={stateTone[p.state] ?? "neutral"}>{p.name}: {p.state.replace(/_/g, " ")}</Badge></span>
          ))}
        </div>
      </details>

      <div className="mt-8">
        {search.isPending && <div className="flex justify-center py-12"><Spinner /></div>}
        {search.isError && <ErrorNote>{errorMessage(search.error)}</ErrorNote>}
        {search.data && (
          <>
            <div className="mb-4 flex flex-wrap gap-2">
              {search.data.providers.filter((p) => p.error).map((p) => <Badge key={p.provider} tone="neutral">{p.name}: {p.error}</Badge>)}
            </div>
            {search.data.results.length === 0 ? (
              <EmptyState title="No activities found" body="Try another day, fewer filters, or a different city." />
            ) : (
              <>
                {trip && date && <p className="mb-4 text-[13.5px] text-ink-500">Checked against your plans for {fmtDate(date)} in {trip.name}.</p>}
                <Stagger key={search.submittedAt} className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
                  {search.data.results.map((a) => <StaggerItem key={`${a.provider}:${a.provider_item_id}`} className="flex"><ActivityCard a={a} tripId={tripId || undefined} date={date} /></StaggerItem>)}
                </Stagger>
              </>
            )}
          </>
        )}
        {!search.data && !search.isPending && <SavedActivities />}
      </div>
    </div>
  );
}

function SavedActivities() {
  const saved = useQuery({ queryKey: ["saved-activities"], queryFn: () => api.get<{ id: string; provider: string; data: Partial<ActivityResult> }[]>("/activities/saved") });
  if (!saved.data?.length) return <EmptyState icon={<Search className="h-7 w-7" />} title="Search to see what fits" body="Results show whether live availability was checked and whether a time slot fits around your existing plans." />;
  return (
    <section>
      <h2 className="eyebrow mb-3 flex items-center gap-1.5"><Bookmark className="h-3.5 w-3.5" /> Saved</h2>
      <ul className="card divide-y divide-sand-100">
        {saved.data.map((s) => (
          <li key={s.id} className="flex items-center justify-between gap-3 px-4 py-3">
            <div className="min-w-0">
              <p className="truncate text-[14px] font-medium">{s.data.title}</p>
              <p className="text-[12.5px] text-ink-400">{s.data.source_label}{s.data.price ? ` · ${money(s.data.price, s.data.currency)}` : ""}</p>
            </div>
            <button onClick={async () => { await api.del(`/activities/saved/${s.id}`); saved.refetch(); }} className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-ink-300 hover:bg-sand-100 hover:text-rose-ink" aria-label="Remove saved activity"><Trash2 className="h-4 w-4" /></button>
          </li>
        ))}
      </ul>
    </section>
  );
}
