import * as Tabs from "@radix-ui/react-tabs";
import { clsx } from "clsx";
import { ChevronRight, Download, FileImage, FileText, Loader2, Mail, ShieldCheck, Sparkles, Upload } from "lucide-react";
import { motion } from "motion/react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { UploadZone } from "@/components/inbox/UploadZone";
import { Stagger, StaggerItem, spring } from "@/components/motion";
import { Badge, Button, EmptyState, InfoNote, LoadError, PageHeader, PageLoader, StatusPill } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { bytes, relativeTime } from "@/lib/format";
import { PROCESSING, useInbox, useInvalidateTripData } from "@/lib/queries";
import type { DocumentItem } from "@/lib/types";

const filters: { key: string; label: string; match: (d: DocumentItem) => boolean }[] = [
  { key: "all", label: "All", match: () => true },
  { key: "review", label: "To review", match: (d) => d.status === "awaiting_review" },
  { key: "processing", label: "Processing", match: (d) => PROCESSING.has(d.status) },
  { key: "done", label: "Processed", match: (d) => d.status === "processed" },
  { key: "other", label: "Failed & duplicates", match: (d) => ["failed", "duplicate", "ignored"].includes(d.status) },
];

export default function InboxPage() {
  const { user } = useAuth();
  const inbox = useInbox();
  const [params, setParams] = useSearchParams();
  const [filter, setFilter] = useState("all");
  const ai = useQuery({ queryKey: ["settings", "ai"], queryFn: () => api.get<{ settings: { mode: string }; demo_external_ai: boolean; providers: { provider: string; configured: boolean }[] }>("/settings/ai") });
  const items = inbox.data?.data ?? [];
  const shown = items.filter(filters.find((f) => f.key === filter)!.match);
  const mode = ai.data?.settings.mode;
  const anyProvider = ai.data?.providers.some((p) => p.configured);
  const tab = params.get("tab") ?? "documents";

  return (
    <div>
      <PageHeader title="Inbox" subtitle="Everything you send Tandem lands here first. Review what was found before it joins a trip." />
      <Tabs.Root value={tab} onValueChange={(v) => setParams(v === "documents" ? {} : { tab: v })}>
        <Tabs.List className="mb-6 grid grid-cols-2 rounded-[14px] bg-sand-100 p-1 sm:inline-grid sm:w-auto" aria-label="Inbox sources">
          {([["documents", "Documents", Upload], ["email", "Email", Mail]] as const).map(([v, label, Icon]) => (
            <Tabs.Trigger key={v} value={v} className={clsx("relative flex h-9 items-center justify-center gap-1.5 rounded-[10px] px-4 text-[14px] font-medium transition-colors pointer-coarse:h-10", tab === v ? "text-ink-900" : "text-ink-500")}>
              {tab === v && <motion.span layoutId="inbox-seg" transition={spring} className="absolute inset-0 rounded-[10px] bg-white shadow-[0_1px_3px_rgba(0,0,0,0.08)]" />}
              <span className="relative z-10 flex items-center gap-1.5"><Icon className="h-4 w-4" />{label}</span>
            </Tabs.Trigger>
          ))}
        </Tabs.List>

        <Tabs.Content value="documents">
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
            <div className="space-y-6">
              <UploadZone />
              <div>
                <div className="-mx-4 mb-3 flex gap-1.5 overflow-x-auto scroll-px-4 px-4 [scrollbar-width:none] sm:mx-0 sm:px-0">
                  {filters.map((f) => {
                    const n = items.filter(f.match).length;
                    const on = filter === f.key;
                    return (
                      <button key={f.key} onClick={() => setFilter(f.key)} className={clsx("relative h-9 shrink-0 whitespace-nowrap rounded-full px-3.5 text-[13.5px] font-medium transition-colors active:scale-95 pointer-coarse:h-10",
                        on ? "text-white" : "bg-white text-ink-500 ring-1 ring-sand-200 hover:text-ink-800")}>
                        {on && <motion.span layoutId="inbox-filter" transition={spring} className="absolute inset-0 rounded-full bg-ink-900" />}
                        <span className="relative z-10">{f.label}{f.key !== "all" && n > 0 ? ` · ${n}` : ""}</span>
                      </button>
                    );
                  })}
                </div>
                {inbox.isLoading ? <PageLoader /> : inbox.isError && !inbox.data ? (
                  <LoadError what="inbox" onRetry={() => inbox.refetch()} retrying={inbox.isFetching} />
                ) : shown.length === 0 ? (
                  <EmptyState title={items.length ? "Nothing in this view" : "Your inbox is empty"} body={items.length ? undefined : "Upload a confirmation above to get started."} />
                ) : (
                  <Stagger key={filter} as="ul" className="card divide-y divide-sand-100 overflow-hidden">{shown.map((d) => <InboxRow key={d.id} d={d} />)}</Stagger>
                )}
              </div>
            </div>
            <aside className="space-y-4">
              <div className="card p-4">
                <p className="eyebrow mb-2 flex items-center gap-1.5"><ShieldCheck className="h-3.5 w-3.5" /> How documents are read</p>
                {mode === "off" && !user?.is_demo ? (
                  <p className="text-[13.5px] text-ink-600">External AI is <strong>off</strong>. Tandem reads documents with its own on-server parser and OCR — nothing leaves Tandem. <Link to="/settings/ai" className="text-lagoon-600 hover:underline">Enable AI</Link> for more accurate extraction.</p>
                ) : mode === "text_only" ? (
                  <p className="text-[13.5px] text-ink-600">Text Tandem extracts may be sent to your enabled AI providers. Original files stay on Tandem's servers.</p>
                ) : anyProvider ? (
                  <p className="text-[13.5px] text-ink-600">Files may be sent to Gemini (or Z.ai's vision model for images) for extraction, then removed from the provider. Groq never receives files.</p>
                ) : (
                  <p className="text-[13.5px] text-ink-600">No AI provider is configured on this server, so the local parser and OCR are used. Every value keeps the line it was read from.</p>
                )}
              </div>
              {user?.is_demo && <DemoSamples />}
            </aside>
          </div>
        </Tabs.Content>
        <Tabs.Content value="email"><EmailCandidates /></Tabs.Content>
      </Tabs.Root>
    </div>
  );
}

function InboxRow({ d }: { d: DocumentItem }) {
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
              <span className="hidden sm:inline">{d.status_detail || d.source} · {bytes(d.size_bytes)} · </span>{relativeTime(d.created_at)}
              {via && !busy ? <span className="hidden sm:inline"> · read by {via === "local" ? "local parser" : via}</span> : null}
              {d.attachments?.length ? ` · ${d.attachments.length} attachment${d.attachments.length > 1 ? "s" : ""}` : ""}
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
  const send = async (key: string) => {
    setBusy(key);
    try {
      await api.post(`/demo/samples/${key}/upload`);
      invalidate();
      toast("Sample sent through the real pipeline", "success");
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="card p-4">
      <p className="eyebrow mb-1 flex items-center gap-1.5"><Sparkles className="h-3.5 w-3.5" /> Try a sample document</p>
      <p className="mb-3 text-[12.5px] text-ink-500">Fictional files to upload — or download one and drag it in.</p>
      <ul className="space-y-3">
        {(samples.data ?? []).map((s) => (
          <li key={s.key} className="rounded-xl bg-sand-50 p-3">
            <p className="text-[13.5px] font-medium">{s.filename}</p>
            <p className="mt-0.5 text-[12.5px] text-ink-500">{s.description}</p>
            <div className="mt-2 flex gap-2">
              <Button size="sm" onClick={() => send(s.key)} loading={busy === s.key}>Upload</Button>
              <a href={`/api/v1/demo/samples/${s.key}`} className="inline-flex h-8 items-center gap-1 rounded-lg px-2.5 text-[12.5px] text-ink-600 hover:bg-white pointer-coarse:h-10 pointer-coarse:text-[13.5px]"><Download className="h-3.5 w-3.5" /> Download</a>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

type Candidate = { id: string; subject: string; sender: string; received_at: string | null; snippet: string; has_attachments: boolean; status: string; document_id: string | null };

function EmailCandidates() {
  const integrations = useQuery({ queryKey: ["integrations"], queryFn: () => api.get<{ gmail: { available: boolean; status: string; reason: string | null; account_email: string | null; last_sync_at: string | null } }>("/integrations") });
  const cands = useQuery({ queryKey: ["email-candidates"], queryFn: () => api.get<Candidate[]>("/inbox/email-candidates") });
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const invalidate = useInvalidateTripData();
  const gmail = integrations.data?.gmail;
  if (integrations.isLoading) return <PageLoader />;
  if (!gmail || gmail.status !== "connected") {
    return (
      <EmptyState icon={<Mail className="h-8 w-8" />} title="Import travel emails from Gmail"
        body={gmail?.available ? "Connect Gmail with read-only access. Tandem finds likely travel emails and you choose which to import." : (gmail?.reason ?? "Gmail is not available.")}
        action={gmail?.available ? <Link to="/settings/connections" className="text-[14px] font-medium text-lagoon-600 hover:underline">Connect Gmail in Settings</Link> : undefined} />
    );
  }
  const toggle = (id: string) => setSelected((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const importSel = async () => {
    setBusy(true);
    try {
      await api.post("/inbox/email-candidates/import", { candidate_ids: [...selected] });
      toast(`Importing ${selected.size} email(s)`, "success");
      setSelected(new Set());
      cands.refetch();
      invalidate();
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(false);
    }
  };
  const sync = async () => { await api.post("/integrations/gmail/sync"); setTimeout(() => cands.refetch(), 1500); };
  return (
    <div>
      <InfoNote tone="lagoon">Connected to {gmail.account_email} (read-only). Only messages you select are imported.</InfoNote>
      <div className="my-4 flex flex-wrap gap-2">
        <Button onClick={importSel} disabled={!selected.size} loading={busy}>Import {selected.size || ""} selected</Button>
        <Button variant="secondary" onClick={sync}>Check for new emails</Button>
      </div>
      {(cands.data?.length ?? 0) === 0 ? <EmptyState title="No travel emails found yet" /> : (
        <ul className="card divide-y divide-sand-100">
          {cands.data!.map((c) => (
            <li key={c.id}>
              <label className="flex cursor-pointer items-start gap-3 px-4 py-3 active:bg-sand-50">
              <input type="checkbox" className="mt-0.5 h-5 w-5 shrink-0 accent-lagoon-600" disabled={c.status !== "candidate"} checked={selected.has(c.id)} onChange={() => toggle(c.id)} aria-label={`Select ${c.subject}`} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-[14px] font-medium">{c.subject || "(no subject)"}</p>
                <p className="truncate text-[12.5px] text-ink-400">{c.sender} · {c.received_at ? new Date(c.received_at).toLocaleDateString() : ""}</p>
                <p className="mt-1 line-clamp-1 text-[13px] text-ink-500">{c.snippet}</p>
              </div>
              {c.status === "imported" ? (c.document_id ? <Link to={`/inbox/${c.document_id}`}><Badge tone="lagoon">Imported</Badge></Link> : <Badge tone="lagoon">Imported</Badge>) : c.has_attachments ? <Badge>Attachment</Badge> : null}
              </label>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
