import { QueryClient } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { clearOffline, offlineUser, persistOffline, restoreOffline } from "@/lib/offline";
import type { User } from "@/lib/types";

const alex = { id: "u1", email: "alex@example.com", display_name: "Alex" } as User;

async function saved(qc: QueryClient, user: User) {
  vi.useFakeTimers();
  const stop = persistOffline(qc, user);
  qc.setQueryData(["trips"], [{ id: "t1", name: "Rome" }]);
  qc.setQueryData(["trip", "t1"], { id: "t1" });
  qc.setQueryData(["trip", "t1", "itinerary"], [{ id: "e1" }]);
  qc.setQueryData(["trip", "t1", "documents"], [{ id: "d1" }]);
  qc.setQueryData(["inbox"], { data: [{ id: "doc" }] });
  qc.setQueryData(["settings"], { profile: {} });
  vi.advanceTimersByTime(1000);
  stop();
  vi.useRealTimers();
}

afterEach(() => localStorage.clear());

describe("offline trips", () => {
  it("keeps trips and itineraries only, for the same user", async () => {
    await saved(new QueryClient(), alex);
    expect(offlineUser()?.id).toBe("u1");

    const fresh = new QueryClient();
    restoreOffline(fresh, "u1");
    expect(fresh.getQueryData(["trips"])).toEqual([{ id: "t1", name: "Rome" }]);
    expect(fresh.getQueryData(["trip", "t1", "itinerary"])).toEqual([{ id: "e1" }]);
    expect(fresh.getQueryData(["trip", "t1", "documents"])).toBeUndefined();
    expect(fresh.getQueryData(["inbox"])).toBeUndefined();
    expect(fresh.getQueryData(["settings"])).toBeUndefined();

    const someoneElse = new QueryClient();
    restoreOffline(someoneElse, "u2");
    expect(someoneElse.getQueryData(["trips"])).toBeUndefined();
  });

  it("is gone after sign-out and expires after a week", async () => {
    await saved(new QueryClient(), alex);
    clearOffline();
    expect(offlineUser()).toBeNull();

    await saved(new QueryClient(), alex);
    const s = JSON.parse(localStorage.getItem("tandem.offline.v1")!);
    localStorage.setItem("tandem.offline.v1", JSON.stringify({ ...s, savedAt: Date.now() - 8 * 24 * 3600 * 1000 }));
    expect(offlineUser()).toBeNull();
  });
});
