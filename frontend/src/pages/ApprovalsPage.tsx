import { ShieldCheck } from "lucide-react";
import { useState } from "react";
import { ActionCard } from "@/components/activities/ActionCard";
import { Segmented, Stagger, StaggerItem } from "@/components/motion";
import { EmptyState, LoadError, PageHeader, PageLoader } from "@/components/ui";
import { useApprovals } from "@/lib/queries";

export default function ApprovalsPage() {
  const [tab, setTab] = useState<"waiting" | "history">("waiting");
  const all = useApprovals();
  if (all.isLoading) return <PageLoader />;
  if (all.isError && !all.data) return <LoadError what="approvals" onRetry={() => all.refetch()} retrying={all.isFetching} />;
  const list = all.data ?? [];
  const waiting = list.filter((a) => ["awaiting_approval", "in_progress", "requires_manual"].includes(a.status));
  const history = list.filter((a) => !["awaiting_approval", "in_progress", "requires_manual"].includes(a.status));
  const shown = tab === "waiting" ? waiting : history;
  return (
    <div className="max-w-3xl">
      <PageHeader title="Approvals" subtitle="Bookings and changes the assistant or you prepared. Each approval covers exactly what you see — if the price or details change, Tandem asks again." />
      <Segmented id="approvals-seg" className="mb-5" value={tab} onChange={setTab}
        options={[{ value: "waiting", label: `Waiting${waiting.length ? ` · ${waiting.length}` : ""}` }, { value: "history", label: "History" }]} />
      {shown.length === 0 ? (
        <EmptyState icon={<ShieldCheck className="h-8 w-8" />} title={tab === "waiting" ? "Nothing waiting for you" : "No history yet"}
          body={tab === "waiting" ? "When the assistant prepares a booking, it appears here for your decision." : undefined} />
      ) : (
        <Stagger key={tab} className="space-y-3">{shown.map((a) => <StaggerItem key={a.id}><ActionCard action={a} /></StaggerItem>)}</Stagger>
      )}
    </div>
  );
}
