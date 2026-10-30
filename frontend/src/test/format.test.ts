import { describe, expect, it } from "vitest";
import { fmtDate, fmtRange, fmtTime, money, offsetLabel, parts } from "../lib/format";

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

  it("formats dates and ranges", () => {
    expect(fmtDate("2026-11-14")).toBe("Sat 14 Nov");
    expect(fmtRange("2026-11-12", "2026-11-16")).toBe("12–16 Nov 2026");
    expect(fmtRange("2026-11-28", "2026-12-02")).toBe("28 Nov – 2 Dec 2026");
  });

  it("formats money", () => {
    expect(money(118, "EUR")).toBe("€118");
    expect(money(54.5, "EUR")).toBe("€54.50");
    expect(money(null, "EUR")).toBe("");
  });
});
