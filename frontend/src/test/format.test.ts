import { describe, expect, it } from "vitest";
import { fmtDate, fmtDayHeading, fmtRange, fmtTime, money, offsetLabel, parts, whenLabel } from "../lib/format";
import { translatePlural } from "../lib/i18n";

// Intl uses non-breaking and thin spaces; compare with plain ones.
const sp = (s: string) => s.replace(/[\u00a0\u2009\u202f]/g, " ");

describe("format", () => {
  it("formats wall-clock time from the event's own timezone, not the browser's", () => {
    // 09:30 in Rome must read 09:30 regardless of where the browser is.
    expect(fmtTime("2026-11-13T09:30:00+01:00")).toBe("09:30");
    expect(fmtTime("2026-11-12T08:05:00+00:00")).toBe("08:05");
  });

  it("parses and labels offsets", () => {
    expect(parts("2026-11-12T21:00:00+09:00")).toEqual({ y: 2026, m: 11, d: 12, hh: 21, mm: 0 });
    expect(offsetLabel("2026-11-12T11:40:00+01:00")).toBe("UTC+1");
    expect(offsetLabel("2026-11-12T11:40:00+05:30")).toBe("UTC+5:30");
    expect(offsetLabel("2026-11-12T11:40:00+00:00")).toBe("UTC");
  });

  it("formats dates and ranges in English", () => {
    expect(fmtDate("2026-11-14", {}, "en")).toBe("Sat 14 Nov");
    expect(fmtRange("2026-11-12", "2026-11-16", "en")).toBe("12–16 Nov 2026");
    expect(sp(fmtRange("2026-11-28", "2026-12-02", "en"))).toBe("28 Nov – 2 Dec 2026");
    expect(fmtDayHeading("2026-11-14", "en").weekday).toBe("Saturday");
  });

  it("formats dates and ranges in Romanian", () => {
    expect(fmtDate("2026-11-14", {}, "ro")).toBe("sâm., 14 nov.");
    expect(fmtRange("2026-11-12", "2026-11-16", "ro")).toBe("12–16 nov. 2026");
    expect(fmtDayHeading("2026-11-14", "ro")).toEqual({ weekday: "Sâmbătă", date: "14 nov." });
  });

  it("formats money per language", () => {
    expect(money(118, "EUR", "en")).toBe("€118");
    expect(money(54.5, "EUR", "en")).toBe("€54.50");
    expect(sp(money(54.5, "EUR", "ro"))).toBe("54,50 EUR");
    expect(money(null, "EUR")).toBe("");
  });

  it("uses Romanian's three plural forms", () => {
    expect(translatePlural("trips.bookings", 1, undefined, "ro")).toBe("1 rezervare");
    expect(translatePlural("trips.bookings", 3, undefined, "ro")).toBe("3 rezervări");
    expect(translatePlural("trips.bookings", 21, undefined, "ro")).toBe("21 de rezervări");
    expect(translatePlural("trips.bookings", 3, undefined, "en")).toBe("3 bookings");
    expect(whenLabel(12, "ro")).toBe("Peste 12 zile");
    expect(whenLabel(20, "ro")).toBe("Peste 20 de zile");
    expect(whenLabel(1, "en")).toBe("Tomorrow");
  });
});
