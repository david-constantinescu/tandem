import { useT } from "@/lib/i18n";

/** The assistant's clarifying question as tappable answers. A tap is the user's reply; older questions are greyed out. */
export function Choices({ options, onChoose }: { options: string[]; onChoose?: (answer: string) => void }) {
  const { t } = useT();
  if (!options.length) return null;
  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label={t("assistant.choices")}>
      {options.map((c) => (
        <button key={c} type="button" disabled={!onChoose} onClick={() => onChoose?.(c)}
          className="min-h-11 rounded-full border border-lagoon-500/40 bg-lagoon-50/60 px-4 text-[14px] font-medium text-lagoon-700 transition active:scale-95 enabled:hover:bg-lagoon-100 disabled:opacity-45">{c}</button>
      ))}
    </div>
  );
}
