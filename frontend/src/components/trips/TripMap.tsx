import L from "leaflet";
import { useEffect } from "react";
import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip, useMap } from "react-leaflet";
import { fmtDateTime } from "@/lib/format";
import { useT, type Key } from "@/lib/i18n";
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
  const { t } = useT();
  const located = events.filter((e) => e.lat !== null && e.lon !== null && !["flight", "train", "bus"].includes(e.type));
  const points = located.map((e) => [e.lat!, e.lon!] as [number, number]);
  if (!points.length) {
    return <p className="rounded-xl bg-sand-50 px-4 py-10 text-center text-[14px] text-ink-500">{t("map.empty")}</p>;
  }
  return (
    // `isolate` keeps Leaflet's high z-indexes from painting over the sticky header and tab bar.
    // On touch screens one-finger drags scroll the page; pinch still zooms the map.
    <div className="isolate h-[360px] overflow-hidden rounded-[22px] border border-sand-200 sm:h-[440px]">
      <MapContainer center={points[0]} zoom={13} scrollWheelZoom={false} dragging={!L.Browser.mobile} className="h-full w-full">
        <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
        <Polyline positions={points} pathOptions={{ color: "#c8623a", weight: 2, dashArray: "4 6", opacity: 0.6 }} />
        {located.map((e) => (
          <CircleMarker key={e.id} center={[e.lat!, e.lon!]} radius={8}
            pathOptions={{ color: "#fff", weight: 2, fillColor: colour[e.status] ?? "#33484c", fillOpacity: 1 }}>
            <Tooltip direction="top" offset={[0, -6]}>
              <strong>{e.title}</strong><br />{fmtDateTime(e.start_local)}{e.status !== "confirmed" ? ` · ${t(`status.${e.status}` as Key)}` : ""}
            </Tooltip>
          </CircleMarker>
        ))}
        <Fit points={points} />
      </MapContainer>
    </div>
  );
}
