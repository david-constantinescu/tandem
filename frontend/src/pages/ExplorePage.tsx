import { Compass, Ticket } from "lucide-react";
import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { ActivitiesPanel } from "@/components/explore/ActivitiesPanel";
import { TicketsPanel } from "@/components/explore/TicketsPanel";
import { Segmented } from "@/components/motion";
import { PageHeader } from "@/components/ui";
import { useT } from "@/lib/i18n";
import { useTrips } from "@/lib/queries";

/** Explore: things to do and tickets to book, both for the trip picked at the top. */
export default function ExplorePage() {
  const [params, setParams] = useSearchParams();
  const trips = useTrips();
  const { t } = useT();
  const tab = params.get("tab") === "tickets" ? "tickets" : "activities";
  const upcoming = useMemo(() => (trips.data ?? []).filter((x) => ["current", "upcoming", "planning"].includes(x.stats.phase ?? "")), [trips.data]);
  const picked = params.get("trip");
  // No choice yet: the next trip. "none" means browsing without a trip.
  const tripId = picked === "none" ? "" : picked ?? upcoming[0]?.id ?? "";
  const trip = upcoming.find((x) => x.id === tripId) ?? (trips.data ?? []).find((x) => x.id === tripId);

  const update = (key: string, value: string | null) => setParams((p) => {
    const n = new URLSearchParams(p);
    if (value === null) n.delete(key); else n.set(key, value);
    if (key === "tab") n.delete("task");
    return n;
  }, { replace: true });

  return (
    <div>
      <PageHeader title={t("explore.title")} subtitle={t("explore.subtitle")} />
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <Segmented id="explore-tab" value={tab} onChange={(v) => update("tab", v === "activities" ? null : v)}
          options={[
            { value: "activities", label: <><Compass className="h-4 w-4" />{t("explore.tabActivities")}</> },
            { value: "tickets", label: <><Ticket className="h-4 w-4" />{t("explore.tabTickets")}</> },
          ]} />
        <div className="sm:w-72">
          <label className="label" htmlFor="xtrip">{t("explore.forTrip")}</label>
          <select id="xtrip" className="field" value={tripId || "none"} onChange={(e) => update("trip", e.target.value)}>
            <option value="none">{t("explore.noTrip")}</option>
            {upcoming.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
            {trip && !upcoming.includes(trip) && <option value={trip.id}>{trip.name}</option>}
          </select>
        </div>
      </div>
      {tab === "activities" ? <ActivitiesPanel trip={trip} /> : <TicketsPanel trip={trip} />}
    </div>
  );
}
