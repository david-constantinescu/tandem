import { ShieldCheck } from "lucide-react";
import { useState } from "react";
import { ActionCard } from "@/components/activities/ActionCard";
import { EmptyState, PageHeader, PageLoader } from "@/components/ui";
import { useApprovals } from "@/lib/queries";

export default function ApprovalsPage() {
  const [tab, setTab] = useState<"waiting" | "history">("waiting");
  const all = useApprovals();
  if (all.isLoading) return <PageLoader />;
  const list = all.data ?? [];
  const waiting = list.filter((a) => ["awaiting_approval", "in_progress", "requires_manual"].includes(a.status));
  const history = list.filter((a) => !["awaiting_approval", "in_progress", "requires_manual"].includes(a.status));
  const shown = tab === "waiting" ? waiting : history;
  return (
    <div className="max-w-3xl">
      <PageHeader title="Approvals" subtitle="Bookings and changes the assistant or you prepared. Each approval covers exactly what you see — if the price or details change, Tandem asks again." />
      <div className="mb-5 inline-flex rounded-xl bg-sand-100 p-1">
        {(["waiting", "history"] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)} className={`rounded-lg px-3.5 py-1.5 text-[13.5px] font-medium ${tab === t ? "bg-white text-ink-900 shadow-sm" : "text-ink-500"}`}>
            {t === "waiting" ? `Waiting${waiting.length ? ` · ${waiting.length}` : ""}` : "History"}
          </button>
        ))}
      </div>
      {shown.length === 0 ? (
        <EmptyState icon={<ShieldCheck className="h-8 w-8" />} title={tab === "waiting" ? "Nothing waiting for you" : "No history yet"}
          body={tab === "waiting" ? "When the assistant prepares a booking, it appears here for your decision." : undefined} />
      ) : (
        <div className="space-y-3">{shown.map((a) => <ActionCard key={a.id} action={a} />)}</div>
      )}
    </div>
  );
}
