import { clsx } from "clsx";
import { ChevronRight, Download, FileImage, FileText, Loader2, Mail, ShieldCheck, Sparkles } from "lucide-react";
import { motion } from "motion/react";
import { useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ActionCard } from "@/components/activities/ActionCard";
import { useAdd } from "@/components/AddSheet";
import { UploadZone } from "@/components/inbox/UploadZone";
import { Stagger, StaggerItem, spring } from "@/components/motion";
import { Button, EmptyState, LoadError, PageHeader, PageLoader, StatusPill } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { bytes, relativeTime } from "@/lib/format";
import { useT, type Key } from "@/lib/i18n";
import { PROCESSING, useApprovals, useInbox, useInvalidateTripData } from "@/lib/queries";
import type { Action, DocumentItem } from "@/lib/types";

const TABS = ["todo", "documents", "approvals"] as const;
type TabKey = (typeof TABS)[number];
const OPEN_ACTIONS = ["awaiting_approval", "in_progress", "requires_manual"];

const filters: { key: string; label: Key; match: (d: DocumentItem) => boolean }[] = [
  { key: "all", label: "inbox.filter.all", match: () => true },
  { key: "review", label: "inbox.filter.review", match: (d) => d.status === "awaiting_review" },
  { key: "processing", label: "inbox.filter.processing", match: (d) => PROCESSING.has(d.status) },
  { key: "done", label: "inbox.filter.done", match: (d) => d.status === "processed" },
  { key: "other", label: "inbox.filter.other", match: (d) => ["failed", "duplicate", "ignored"].includes(d.status) },
];

export default function InboxPage() {
  const [params, setParams] = useSearchParams();
  const inbox = useInbox();
  const approvals = useApprovals();
  const { t } = useT();
  const raw = params.get("tab");
  const tab: TabKey = (TABS as readonly string[]).includes(raw ?? "") ? (raw as TabKey) : "todo";
  const docs = inbox.data?.data ?? [];
  const review = docs.filter((d) => d.status === "awaiting_review");
  const waiting = (approvals.data ?? []).filter((a) => OPEN_ACTIONS.includes(a.status));
  const todoCount = review.length + waiting.length;

  const labels: Record<TabKey, ReactNode> = {
    todo: <>{t("inbox.tab.todo")}{todoCount > 0 && <span className="rounded-full bg-clay-500 px-1.5 text-[11px] leading-[18px] text-white">{todoCount}</span>}</>,
    documents: t("inbox.tab.documents"),
    approvals: t("inbox.tab.approvals"),
  };

  return (
    <div>
      <PageHeader title={t("inbox.title")} subtitle={t("inbox.subtitle")} />
      <div role="tablist" aria-label={t("inbox.title")} className="-mx-4 mb-6 flex gap-1 overflow-x-auto scroll-px-4 px-4 [scrollbar-width:none] sm:mx-0 sm:px-0">
        {TABS.map((k) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setParams(k === "todo" ? {} : { tab: k }, { replace: true })}
            className={clsx("relative flex h-10 shrink-0 items-center gap-1.5 rounded-full px-4 text-[14px] font-medium transition-colors pointer-coarse:h-11", tab === k ? "text-paper" : "text-ink-500 hover:text-ink-800")}>
            {tab === k && <motion.span layoutId="inbox-tab" transition={spring} className="absolute inset-0 rounded-full bg-ink-900" />}
            <span className="relative z-10 flex items-center gap-1.5">{labels[k]}</span>
          </button>
        ))}
      </div>

      {tab === "todo" && <Todo review={review} waiting={waiting} loading={inbox.isLoading || approvals.isLoading} onDocuments={() => setParams({ tab: "documents" })} />}
      {tab === "documents" && <Documents docs={docs} loading={inbox.isLoading} error={inbox.isError && !inbox.data} retry={() => inbox.refetch()} retrying={inbox.isFetching} />}
      {tab === "approvals" && <Approvals />}
    </div>
  );
}

function Todo({ review, waiting, loading, onDocuments }: { review: DocumentItem[]; waiting: Action[]; loading: boolean; onDocuments: () => void }) {
  const { t } = useT();
  const { openAdd } = useAdd();
  if (loading) return <PageLoader />;
  if (!review.length && !waiting.length) {
    return (
      <EmptyState icon={<ShieldCheck />} title={t("inbox.todoEmpty")} body={t("inbox.todoEmptyBody")}
        action={<div className="flex flex-wrap justify-center gap-2"><Button onClick={openAdd}>{t("inbox.addBooking")}</Button><Button variant="secondary" onClick={onDocuments}>{t("inbox.seeDocuments")}</Button></div>} />
    );
  }
  return (
    <div className="max-w-3xl space-y-8">
      {waiting.length > 0 && (
        <section>
          <h2 className="display mb-1 text-[21px]">{t("inbox.toApprove")}</h2>
          <p className="mb-3 text-[13.5px] text-ink-500">{t("inbox.toApproveHint")}</p>
          <Stagger className="space-y-3">{waiting.map((a) => <StaggerItem key={a.id}><ActionCard action={a} /></StaggerItem>)}</Stagger>
        </section>
      )}
      {review.length > 0 && (
        <section>
          <h2 className="display mb-1 text-[21px]">{t("inbox.toReview")}</h2>
          <p className="mb-3 text-[13.5px] text-ink-500">{t("inbox.toReviewHint")}</p>
          <Stagger as="ul" className="card divide-y divide-sand-100 overflow-hidden">{review.map((d) => <InboxRow key={d.id} d={d} />)}</Stagger>
        </section>
      )}
    </div>
  );
}

function Documents({ docs, loading, error, retry, retrying }: { docs: DocumentItem[]; loading: boolean; error: boolean; retry: () => void; retrying: boolean }) {
  const { user } = useAuth();
  const { t } = useT();
  const [filter, setFilter] = useState("all");
  const ai = useQuery({ queryKey: ["settings", "ai"], queryFn: () => api.get<{ settings: { mode: string }; demo_external_ai: boolean; providers: { provider: string; configured: boolean }[] }>("/settings/ai") });
  const shown = docs.filter(filters.find((f) => f.key === filter)!.match);
  const mode = ai.data?.settings.mode;
  const anyProvider = ai.data?.providers.some((p) => p.configured);
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
      <div className="space-y-6">
        <UploadZone />
        <div>
          <div className="-mx-4 mb-3 flex gap-1.5 overflow-x-auto scroll-px-4 px-4 [scrollbar-width:none] sm:mx-0 sm:px-0">
            {filters.map((f) => {
              const n = docs.filter(f.match).length;
              const on = filter === f.key;
              return (
                <button key={f.key} onClick={() => setFilter(f.key)} className={clsx("relative h-9 shrink-0 whitespace-nowrap rounded-full px-3.5 text-[13.5px] font-medium transition-colors active:scale-95 pointer-coarse:h-10",
                  on ? "text-paper" : "bg-white text-ink-500 ring-1 ring-sand-200 hover:text-ink-800")}>
                  {on && <motion.span layoutId="inbox-filter" transition={spring} className="absolute inset-0 rounded-full bg-ink-900" />}
                  <span className="relative z-10">{t(f.label)}{f.key !== "all" && n > 0 ? ` · ${n}` : ""}</span>
                </button>
              );
            })}
          </div>
          {loading ? <PageLoader /> : error ? (
            <LoadError title={t("load.inbox")} onRetry={retry} retrying={retrying} />
          ) : shown.length === 0 ? (
            <EmptyState title={docs.length ? t("inbox.emptyFilter") : t("inbox.empty")} body={docs.length ? undefined : t("inbox.emptyBody")} />
          ) : (
            <Stagger key={filter} as="ul" className="card divide-y divide-sand-100 overflow-hidden">{shown.map((d) => <InboxRow key={d.id} d={d} />)}</Stagger>
          )}
        </div>
      </div>
      <aside className="space-y-4">
        <details className="card group p-4 lg:open:pb-4" open={typeof window !== "undefined" && window.innerWidth >= 1024}>
          <summary className="flex min-h-8 cursor-pointer list-none items-center gap-1.5 [&::-webkit-details-marker]:hidden"><span className="eyebrow flex items-center gap-1.5"><ShieldCheck className="h-3.5 w-3.5" /> {t("inbox.howRead")}</span></summary>
          <p className="mt-2 text-[13.5px] text-ink-600">
            {mode === "off" && !user?.is_demo ? <>{t("inbox.readOff")} <Link to="/settings/ai" className="text-lagoon-600 hover:underline">{t("inbox.enableAi")}</Link></>
              : mode === "text_only" ? t("inbox.readText") : anyProvider ? t("inbox.readFull") : t("inbox.readLocal")}
          </p>
        </details>
        {user?.is_demo && <DemoSamples />}
      </aside>
    </div>
  );
}

function Approvals() {
  const all = useApprovals();
  const { t } = useT();
  if (all.isLoading) return <PageLoader />;
  if (all.isError && !all.data) return <LoadError title={t("load.approvals")} onRetry={() => all.refetch()} retrying={all.isFetching} />;
  const list = all.data ?? [];
  return (
    <div className="max-w-3xl">
      <p className="mb-4 text-[14px] text-ink-500">{t("inbox.approvalsHint")}</p>
      {list.length === 0 ? (
        <EmptyState icon={<ShieldCheck className="h-8 w-8" />} title={t("inbox.approvalsEmpty")} body={t("inbox.approvalsEmptyBody")} />
      ) : (
        <Stagger className="space-y-3">{list.map((a) => <StaggerItem key={a.id}><ActionCard action={a} /></StaggerItem>)}</Stagger>
      )}
    </div>
  );
}

function InboxRow({ d }: { d: DocumentItem }) {
  const { t, tp } = useT();
  const busy = PROCESSING.has(d.status);
  const Icon = d.mime_type.startsWith("image/") ? FileImage : d.mime_type === "message/rfc822" ? Mail : FileText;
  const via = d.extraction_method?.provider;
  return (
    <StaggerItem as="li">
      <Link to={`/inbox/${d.id}`} className="flex min-h-[64px] items-center gap-3 px-4 py-3 transition hover:bg-sand-50/70 active:bg-sand-50">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-apricot-soft text-clay-600">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Icon className="h-[18px] w-[18px]" />}</span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[15px] font-medium text-ink-900">{d.filename}</p>
          <div className="mt-1 flex min-w-0 items-center gap-2 text-[12.5px] text-ink-400">
            <span className="shrink-0 sm:hidden"><StatusPill status={d.status} /></span>
            <span className="truncate">
              <span className="hidden sm:inline">{bytes(d.size_bytes)} · </span>{relativeTime(d.created_at)}
              {via && !busy ? <span className="hidden sm:inline"> · {via === "local" ? t("inbox.readByLocal") : t("inbox.readBy", { provider: via })}</span> : null}
              {d.attachments?.length ? ` · ${tp("inbox.attachments", d.attachments.length)}` : ""}
            </span>
          </div>
        </div>
        <span className="hidden sm:block"><StatusPill status={d.status} /></span>
        <ChevronRight className="h-4 w-4 shrink-0 text-ink-300" />
      </Link>
    </StaggerItem>
  );
}

function DemoSamples() {
  const samples = useQuery({ queryKey: ["demo-samples"], queryFn: () => api.get<{ key: string; filename: string; description: string }[]>("/demo/samples") });
  const [busy, setBusy] = useState<string | null>(null);
  const invalidate = useInvalidateTripData();
  const toast = useToast();
  const { t } = useT();
  const send = async (key: string) => {
    setBusy(key);
    try {
      await api.post(`/demo/samples/${key}/upload`);
      invalidate();
      toast(t("inbox.sampleSent"), "success");
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="card p-4">
      <p className="eyebrow mb-1 flex items-center gap-1.5"><Sparkles className="h-3.5 w-3.5" /> {t("inbox.samples")}</p>
      <p className="mb-3 text-[12.5px] text-ink-500">{t("inbox.samplesHint")}</p>
      <ul className="space-y-3">
        {(samples.data ?? []).map((s) => (
          <li key={s.key} className="rounded-xl bg-sand-50 p-3">
            <p className="text-[13.5px] font-medium">{s.filename}</p>
            <p className="mt-0.5 text-[12.5px] text-ink-500">{s.description}</p>
            <div className="mt-2 flex gap-2">
              <Button size="sm" onClick={() => send(s.key)} loading={busy === s.key}>{t("inbox.sampleUpload")}</Button>
              <a href={`/api/v1/demo/samples/${s.key}`} className="inline-flex h-8 items-center gap-1 rounded-lg px-2.5 text-[12.5px] text-ink-600 hover:bg-white pointer-coarse:h-10 pointer-coarse:text-[13.5px]"><Download className="h-3.5 w-3.5" /> {t("common.download")}</a>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}


