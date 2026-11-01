/**
 * tine pe dispozitiv o copie a calatoriilor omului conectat, ca itinerariul sa se deschida fara conexiune
 * (in avion, in strainatate fara date). Se pastreaza doar calatoriile, itinerariile, rezervarile si suprapunerile: nu
 * documentele, inbox-ul, setarile sau chaturile cu asistentul. Copia e legata de un singur om, expira dupa o saptamana si
 * se sterge la deconectare sau cand intra altcineva.
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

/** omul salvat odata cu copia offline, ca sa putem deschide aplicatia cand sesiunea nu poate fi verificata */
export function offlineUser(): User | null {
  return read()?.user ?? null;
}

/** incarca in cache calatoriile salvate (doar pentru acelasi om); datele proaspete le inlocuiesc cand sosesc */
export function restoreOffline(qc: QueryClient, userId: string): void {
  const s = read();
  if (s?.user.id === userId) hydrate(qc, s.state);
}

/** salveaza interogarile pastrate de fiecare data cand se schimba. Intoarce o functie care opreste salvarea */
export function persistOffline(qc: QueryClient, user: User): () => void {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const save = () => {
    try {
      const snapshot: Snapshot = { user, savedAt: Date.now(), state: dehydrate(qc, { shouldDehydrateQuery: keep }) };
      localStorage.setItem(STORE, JSON.stringify(snapshot));
    } catch {
      // spatiu plin sau blocat (navigare privata): aplicatia merge la fel, doar ca nu si fara net
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
    // nu era nimic salvat
  }
}
