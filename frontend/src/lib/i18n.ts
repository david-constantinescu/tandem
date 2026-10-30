/**
 * Minimal localisation layer. English is complete; other locales fall back to English per key.
 * Add a language by adding a dictionary here (Romanian is scaffolded for the next phase).
 */
const en = {
  "nav.home": "Home",
  "nav.trips": "Trips",
  "nav.inbox": "Inbox",
  "nav.discover": "Discover",
  "nav.assistant": "Assistant",
  "nav.approvals": "Approvals",
  "nav.settings": "Settings",
  "status.confirmed": "Confirmed",
  "status.pending": "Pending",
  "status.suggested": "Suggested",
  "status.unbooked": "Not booked",
  "status.cancelled": "Cancelled",
  "status.completed": "Completed",
  "status.unknown": "Unconfirmed",
  "demo.banner": "Demo workspace — fictional trips, simulated bookings. Nothing real is booked or charged.",
};

type Key = keyof typeof en;

const ro: Partial<Record<Key, string>> = {
  "nav.home": "Acasă",
  "nav.trips": "Călătorii",
  "nav.inbox": "Inbox",
  "nav.discover": "Descoperă",
  "nav.assistant": "Asistent",
  "nav.approvals": "Aprobări",
  "nav.settings": "Setări",
};

const dictionaries: Record<string, Partial<Record<Key, string>>> = { en, ro };
let current = "en";

export function setLocale(locale: string) {
  current = dictionaries[locale] ? locale : "en";
  document.documentElement.lang = current;
}

export function t(key: Key): string {
  return dictionaries[current]?.[key] ?? en[key] ?? key;
}
