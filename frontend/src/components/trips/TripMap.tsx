import L from "leaflet";
import { useEffect } from "react";
import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip, useMap } from "react-leaflet";
import { fmtDateTime } from "@/lib/format";
import type { ItineraryEvent } from "@/lib/types";

const colour: Record<string, string> = { confirmed: "#23675f", pending: "#8a5a08", suggested: "#5b4bb5", unbooked: "#7d8c8e" };

function Fit({ points }: { points: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    if (points.length === 1) map.setView(points[0], 13);
    else if (points.length > 1) map.fitBounds(L.latLngBounds(points), { padding: [36, 36], maxZoom: 14 });
  }, [map, points]);
  return null;
}

export function TripMap({ events }: { events: ItineraryEvent[] }) {
  const located = events.filter((e) => e.lat !== null && e.lon !== null && !["flight", "train", "bus"].includes(e.type));
  const points = located.map((e) => [e.lat!, e.lon!] as [number, number]);
  if (!points.length) {
    return <p className="rounded-xl bg-sand-50 px-4 py-10 text-center text-[14px] text-ink-500">No mapped locations yet. Addresses from your bookings will appear here.</p>;
  }
  return (
    <div className="h-[440px] overflow-hidden rounded-2xl border border-sand-200">
      <MapContainer center={points[0]} zoom={13} scrollWheelZoom={false} className="h-full w-full">
        <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
        <Polyline positions={points} pathOptions={{ color: "#c8623a", weight: 2, dashArray: "4 6", opacity: 0.6 }} />
        {located.map((e) => (
          <CircleMarker key={e.id} center={[e.lat!, e.lon!]} radius={8}
            pathOptions={{ color: "#fff", weight: 2, fillColor: colour[e.status] ?? "#33484c", fillOpacity: 1 }}>
            <Tooltip direction="top" offset={[0, -6]}>
              <strong>{e.title}</strong><br />{fmtDateTime(e.start_local)}{e.status !== "confirmed" ? ` · ${e.status}` : ""}
            </Tooltip>
          </CircleMarker>
        ))}
        <Fit points={points} />
      </MapContainer>
    </div>
  );
}
