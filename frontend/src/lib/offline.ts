/**
 * Keeps a copy of the signed-in user's trips on this device so the itinerary opens without a connection
 * (in the air, abroad without data). Only trips, itineraries, reservations and conflicts are kept: not documents,
 * the inbox, settings or assistant chats. The copy is tied to one user, expires after a week and is deleted on
 * sign-out or when someone else signs in.
 */
import { dehydrate, hydrate, type DehydratedState, type Query, type QueryClient } from "@tanstack/react-query";
import type { User } from "./types";

const STORE = "tandem.offline.v1";
const MAX_AGE_MS = 7 * 24 * 3600 * 1000;
const TRIP_PARTS = new Set(["itinerary", "reservations", "conflicts"]);

type Snapshot = { user: User; savedAt: number; state: DehydratedState };

function read(): Snapshot | null {
  try {
    const s = JSON.parse(localStorage.getItem(STORE) ?? "null") as Snapshot | null;
    return s && Date.now() - s.savedAt < MAX_AGE_MS ? s : null;
  } catch {
    return null;
  }
}

function keep(q: Query): boolean {
  if (q.state.status !== "success") return false;
  const [root, , part] = q.queryKey as unknown[];
  return root === "trips" || (root === "trip" && (part === undefined || TRIP_PARTS.has(part as string)));
}

/** The user saved with the offline copy, for opening the app when the session can't be checked. */
export function offlineUser(): User | null {
  return read()?.user ?? null;
}

/** Load the saved trips into the cache (only for the same user); fresh data replaces them once it arrives. */
export function restoreOffline(qc: QueryClient, userId: string): void {
  const s = read();
  if (s?.user.id === userId) hydrate(qc, s.state);
}

/** Save the kept queries whenever they change. Returns a function that stops saving. */
export function persistOffline(qc: QueryClient, user: User): () => void {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const save = () => {
    try {
      const snapshot: Snapshot = { user, savedAt: Date.now(), state: dehydrate(qc, { shouldDehydrateQuery: keep }) };
      localStorage.setItem(STORE, JSON.stringify(snapshot));
    } catch {
      // Storage full or blocked (private browsing): the app works the same, just not offline.
    }
  };
  const unsubscribe = qc.getQueryCache().subscribe((e) => {
    if (e.type !== "updated" || !keep(e.query)) return;
    clearTimeout(timer);
    timer = setTimeout(save, 800);
  });
  return () => {
    clearTimeout(timer);
    unsubscribe();
  };
}

export function clearOffline(): void {
  try {
    localStorage.removeItem(STORE);
  } catch {
    // nothing stored
  }
}
