import {
  BedDouble, Bus, CalendarClock, Car, Coffee, Footprints, Landmark, LogIn, LogOut, MapPin, Plane, Ship, Sparkles, Ticket,
  TrainFront, Utensils, Bell, Users,
} from "lucide-react";
import { clsx } from "clsx";

const map: Record<string, any> = {
  flight: Plane, train: TrainFront, bus: Bus, ferry: Ship, car_rental: Car, transfer: Car,
  hotel: BedDouble, hotel_checkin: LogIn, hotel_checkout: LogOut, museum: Landmark, tour: Footprints,
  activity: Sparkles, restaurant: Utensils, event: Ticket, meeting: Users, free_time: Coffee,
  travel_time: CalendarClock, reminder: Bell, custom: MapPin, other: MapPin,
};

const tint: Record<string, string> = {
  flight: "bg-lagoon-50 text-lagoon-700", train: "bg-lagoon-50 text-lagoon-700", bus: "bg-lagoon-50 text-lagoon-700",
  ferry: "bg-lagoon-50 text-lagoon-700", hotel: "bg-sand-100 text-ink-700", hotel_checkin: "bg-sand-100 text-ink-700",
  hotel_checkout: "bg-sand-100 text-ink-700", restaurant: "bg-clay-50 text-clay-600", museum: "bg-violet-soft text-violet-ink",
  tour: "bg-amber-soft text-amber-ink", activity: "bg-amber-soft text-amber-ink", free_time: "bg-lagoon-50 text-lagoon-600",
};

export function EventIcon({ type, className, size = "md" }: { type: string; className?: string; size?: "sm" | "md" }) {
  const Icon = map[type] ?? MapPin;
  return (
    <span className={clsx("inline-flex shrink-0 items-center justify-center rounded-xl", size === "md" ? "h-9 w-9" : "h-7 w-7 rounded-lg",
      tint[type] ?? "bg-sand-100 text-ink-600", className)} aria-hidden>
      <Icon className={size === "md" ? "h-[18px] w-[18px]" : "h-3.5 w-3.5"} />
    </span>
  );
}
