import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Choices } from "@/components/assistant/Choices";
import { eachDay } from "@/lib/format";
import { I18nProvider } from "@/lib/i18n";
import { en } from "@/locales/en";
import { ro } from "@/locales/ro";

const wrap = (ui: React.ReactNode) => render(<I18nProvider>{ui}</I18nProvider>);

describe("the assistant's tappable answers", () => {
  it("sends the tapped answer as the user's reply", () => {
    const onChoose = vi.fn();
    wrap(<Choices options={["Muzeu", "Tur ghidat", "Concert"]} onChoose={onChoose} />);
    fireEvent.click(screen.getByRole("button", { name: "Tur ghidat" }));
    expect(onChoose).toHaveBeenCalledExactlyOnceWith("Tur ghidat");
  });

  it("greys out the answers of a question that has already been answered", () => {
    wrap(<Choices options={["A", "B"]} />);
    expect(screen.getAllByRole("button").every((b) => (b as HTMLButtonElement).disabled)).toBe(true);
  });

  it("renders nothing without options", () => {
    const { container } = wrap(<Choices options={[]} onChoose={() => {}} />);
    expect(container.querySelector("button")).toBeNull();
  });
});

describe("the trip's days", () => {
  it("lists each day from the first to the last, inclusive", () => {
    expect(eachDay("2026-11-12", "2026-11-16")).toEqual(["2026-11-12", "2026-11-13", "2026-11-14", "2026-11-15", "2026-11-16"]);
  });
  it("handles a trip without an end, a month boundary and nothing at all", () => {
    expect(eachDay("2026-11-12", null)).toEqual(["2026-11-12"]);
    expect(eachDay("2026-10-30", "2026-11-02")).toEqual(["2026-10-30", "2026-10-31", "2026-11-01", "2026-11-02"]);
    expect(eachDay(null, null)).toEqual([]);
  });
});

describe("translations", () => {
  it("has a Romanian text for every English key, and nothing extra", () => {
    expect(Object.keys(ro).sort()).toEqual(Object.keys(en).sort());
  });
  it("keeps placeholders identical between languages", () => {
    const slots = (s: string) => (s.match(/\{\w+\}/g) ?? []).sort().join();
    const off = Object.keys(en).filter((k) => slots(en[k as keyof typeof en]) !== slots(ro[k as keyof typeof ro]));
    expect(off).toEqual([]);
  });
});

describe("the chat bar", () => {
  it("sends with Enter, not with an empty box, and clears nothing itself", async () => {
    const { Composer } = await import("@/components/assistant/Composer");
    const onSend = vi.fn();
    const { rerender } = wrap(<Composer value="" onChange={() => {}} onSend={onSend} />);
    const send = screen.getByRole("button", { name: /send|trimite/i }) as HTMLButtonElement;
    expect(send.disabled).toBe(true);
    rerender(<I18nProvider><Composer value="Cum e vremea?" onChange={() => {}} onSend={onSend} /></I18nProvider>);
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter" });
    expect(onSend).toHaveBeenCalledWith("Cum e vremea?");
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter", shiftKey: true });
    expect(onSend).toHaveBeenCalledTimes(1); // shift+enter e rand nou
  });
});
