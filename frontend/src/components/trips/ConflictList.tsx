import { clsx } from "clsx";
import { AlertOctagon, AlertTriangle, Info, Sparkles } from "lucide-react";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { Button } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { Conflict } from "@/lib/types";

const icon = { critical: AlertOctagon, warning: AlertTriangle, info: Info };
const style = {
  critical: "border-rose-soft bg-rose-soft/50 text-rose-ink",
  warning: "border-amber-soft bg-amber-soft/60 text-amber-ink",
  info: "border-sand-200 bg-sand-50 text-ink-600",
};

/** textele suprapunerilor vin de pe server in limba contului. `compact` arata doar titlurile */
export function ConflictList({ conflicts, tripId, compact, showInfo }: { conflicts: Conflict[]; tripId: string; compact?: boolean; showInfo?: boolean }) {
  const [explanation, setExplanation] = useState<{ text: string | null; provider?: string | null; reason?: string } | null>(null);
  const [loading, setLoading] = useState(false);
  const { t } = useT();
  if (!conflicts.length) {
    return <p className="rounded-xl border border-lagoon-100 bg-lagoon-50/60 px-3.5 py-3 text-[13.5px] text-lagoon-700">{t("conflicts.none")}</p>;
  }
  const shown = compact && !showInfo ? conflicts.filter((c) => c.severity !== "info").slice(0, 3) : conflicts;
  const explain = async () => {
    setLoading(true);
    try {
      const r = await api.post<{ explanation: string | null; provider: string | null; unavailable_reason?: string }>(`/trips/${tripId}/conflicts/explain`);
      setExplanation({ text: r.explanation, provider: r.provider, reason: r.unavailable_reason });
    } catch (e) {
      setExplanation({ text: null, reason: errorMessage(e) });
    } finally {
      setLoading(false);
    }
  };
  return (
    <div className="space-y-2">
      {shown.map((c) => {
        const Icon = icon[c.severity];
        return (
          <div key={c.key} className={clsx("flex gap-2.5 rounded-xl border px-3.5 py-2.5", style[c.severity])}>
            <Icon className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
              <p className="text-[13.5px] font-medium">{c.title}</p>
              {!compact && c.detail && <p className="mt-0.5 text-[13px] opacity-90">{c.detail}</p>}
            </div>
          </div>
        );
      })}
      {!compact && (
        <div className="pt-1">
          {explanation ? (
            <div className="rounded-xl border border-sand-200 bg-white p-4">
              <p className="eyebrow mb-2 flex items-center gap-1.5"><Sparkles className="h-3 w-3" /> {t("conflicts.fixes")}</p>
              {explanation.text ? (
                <div className="prose-chat text-[13.5px] text-ink-700"><ReactMarkdown>{explanation.text}</ReactMarkdown></div>
              ) : (
                <p className="text-[13px] text-ink-500">{t("conflicts.noAi", { reason: explanation.reason?.replace(/_/g, " ") ?? "" })}</p>
              )}
            </div>
          ) : (
            <Button variant="secondary" size="sm" onClick={explain} loading={loading} icon={<Sparkles className="h-3.5 w-3.5" />}>{t("conflicts.suggestFixes")}</Button>
          )}
        </div>
      )}
    </div>
  );
}
