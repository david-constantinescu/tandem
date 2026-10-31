import { clsx } from "clsx";
import { ArrowUp, Loader2, Plus } from "lucide-react";
import { useEffect, useRef, type FormEvent, type KeyboardEvent } from "react";
import { useAdd } from "@/components/AddSheet";
import { useT } from "@/lib/i18n";

/**
 * The chat bar, in the iMessage mould: a round + for adding a file, photo, email or link (it lands in the chat), a
 * pill that grows with the text, and a send button that only lights up when there is something to send.
 */
export function Composer({ value, onChange, onSend, busy, placeholder, autoFocus, className }: {
  value: string; onChange: (v: string) => void; onSend: (text: string) => void; busy?: boolean; placeholder?: string;
  autoFocus?: boolean; className?: string;
}) {
  const { t } = useT();
  const { openAdd, busy: uploading } = useAdd();
  const box = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [value]);
  const ready = !!value.trim() && !busy;
  const submit = (e: FormEvent) => { e.preventDefault(); if (ready) onSend(value); };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); if (ready) onSend(value); }
  };
  return (
    <form onSubmit={submit} className={clsx("flex items-end gap-2", className)}>
      <button type="button" onClick={openAdd} aria-label={t("chat.attach")} disabled={uploading}
        className="mb-[3px] flex h-[38px] w-[38px] shrink-0 items-center justify-center rounded-full bg-sand-100 text-ink-600 transition active:scale-90 hover:bg-sand-200 disabled:opacity-60">
        {uploading ? <Loader2 className="h-[18px] w-[18px] animate-spin" /> : <Plus className="h-5 w-5" strokeWidth={2.4} />}
      </button>
      <div className="flex min-h-[44px] min-w-0 flex-1 items-end rounded-[22px] border border-sand-200 bg-white/95 pl-4 pr-[5px] shadow-[0_1px_2px_rgba(20,30,40,0.04),0_8px_24px_-12px_rgba(20,30,40,0.18)] backdrop-blur-xl transition focus-within:border-ink-300">
        <textarea ref={box} rows={1} value={value} onChange={(e) => onChange(e.target.value)} onKeyDown={onKey} autoFocus={autoFocus}
          placeholder={placeholder ?? t("assistant.placeholder")} aria-label={t("assistant.message")} enterKeyHint="send"
          className="min-h-[42px] min-w-0 flex-1 resize-none bg-transparent py-[10px] text-[16px] leading-[22px] text-ink-900 outline-none placeholder:text-ink-300 lg:text-[15px]" />
        <button type="submit" disabled={!ready} aria-label={t("assistant.send")}
          className={clsx("mb-[5px] flex h-[32px] w-[32px] shrink-0 items-center justify-center rounded-full transition active:scale-90",
            ready ? "bg-clay-500 text-white shadow-[0_4px_12px_-4px_rgba(200,98,58,0.7)]" : "bg-sand-200 text-white")}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowUp className="h-[18px] w-[18px]" strokeWidth={2.6} />}
        </button>
      </div>
    </form>
  );
}
