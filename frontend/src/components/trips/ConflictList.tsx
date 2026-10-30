import { clsx } from "clsx";
import { AlertOctagon, AlertTriangle, Info, Sparkles } from "lucide-react";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { Button } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import type { Conflict } from "@/lib/types";

const icon = { critical: AlertOctagon, warning: AlertTriangle, info: Info };
const style = {
  critical: "border-rose-soft bg-rose-soft/50 text-rose-ink",
  warning: "border-amber-soft bg-amber-soft/60 text-amber-ink",
  info: "border-sand-200 bg-sand-50 text-ink-600",
};

export function ConflictList({ conflicts, tripId, compact }: { conflicts: Conflict[]; tripId: string; compact?: boolean }) {
  const [explanation, setExplanation] = useState<{ text: string | null; provider?: string | null; reason?: string } | null>(null);
  const [loading, setLoading] = useState(false);
  if (!conflicts.length) {
    return <p className="rounded-xl border border-lagoon-100 bg-lagoon-50/60 px-3.5 py-3 text-[13.5px] text-lagoon-700">No conflicts found in this itinerary.</p>;
  }
  const shown = compact ? conflicts.filter((c) => c.severity !== "info").slice(0, 3) : conflicts;
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
              {!compact && <p className="mt-0.5 text-[13px] opacity-90">{c.detail}</p>}
            </div>
          </div>
        );
      })}
      {!compact && (
        <div className="pt-2">
          {explanation ? (
            <div className="rounded-xl border border-sand-200 bg-white p-4">
              <p className="eyebrow mb-2 flex items-center gap-1.5"><Sparkles className="h-3 w-3" /> Suggested fixes</p>
              {explanation.text ? (
                <div className="prose-chat text-[13.5px] text-ink-700"><ReactMarkdown>{explanation.text}</ReactMarkdown></div>
              ) : (
                <p className="text-[13px] text-ink-500">AI explanations aren't available right now ({explanation.reason?.replace(/_/g, " ")}). The checks above are deterministic and complete without AI.</p>
              )}
              {explanation.provider && <p className="mt-2 text-[11.5px] text-ink-400">Explained by {explanation.provider} from the detected facts only.</p>}
            </div>
          ) : (
            <Button variant="secondary" size="sm" onClick={explain} loading={loading} icon={<Sparkles className="h-3.5 w-3.5" />}>Suggest fixes</Button>
          )}
        </div>
      )}
    </div>
  );
}
