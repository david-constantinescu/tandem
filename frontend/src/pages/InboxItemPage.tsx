import { ChevronDown, Download, EyeOff, Loader2, RotateCcw, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { RecordReview } from "@/components/inbox/RecordReview";
import { Button, EmptyState, ErrorNote, InfoNote, PageLoader, StatusPill } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { api, errorMessage } from "@/lib/api";
import { bytes, relativeTime } from "@/lib/format";
import { PROCESSING, useInboxItem, useInvalidateTripData } from "@/lib/queries";

const steps = ["queued", "processing", "analysing", "awaiting_review"];
const stepText: Record<string, string> = { queued: "Queued", processing: "Extracting content", analysing: "Finding travel details", awaiting_review: "Ready to review" };

export default function InboxItemPage() {
  const { id = "" } = useParams();
  const item = useInboxItem(id);
  const [showText, setShowText] = useState(false);
  const invalidate = useInvalidateTripData();
  const toast = useToast();
  const navigate = useNavigate();
  if (item.isLoading) return <PageLoader />;
  const d = item.data;
  if (!d) return <EmptyState title="Document not found" action={<Link to="/inbox" className="text-lagoon-600">Back to inbox</Link>} />;
  const busy = PROCESSING.has(d.status);
  const records = [...(d.records ?? []), ...(d.attachments ?? []).flatMap((a) => a.records ?? [])];
  const m = d.extraction_method ?? {};

  const run = async (fn: () => Promise<unknown>, msg: string) => {
    try { await fn(); invalidate(); item.refetch(); toast(msg, "success"); } catch (e) { toast(errorMessage(e), "error"); }
  };

  return (
    <div className="max-w-4xl">
      <Link to="/inbox" className="text-[13px] text-ink-400 hover:text-ink-700">← Inbox</Link>
      <div className="mt-2 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h1 className="display break-words text-[26px] leading-tight sm:text-[30px]">{d.filename}</h1>
          <p className="mt-1.5 flex flex-wrap items-center gap-2 text-[13.5px] text-ink-500">
            <StatusPill status={d.status} /> {d.source} · {bytes(d.size_bytes)}{d.page_count ? ` · ${d.page_count} page${d.page_count > 1 ? "s" : ""}` : ""} · {relativeTime(d.created_at)}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {d.has_original && <a href={`/api/v1/documents/${d.id}/download`} className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-sand-200 bg-white px-3 text-[13px] font-medium hover:bg-sand-50"><Download className="h-3.5 w-3.5" /> Original</a>}
          {!busy && d.has_original && <Button size="sm" variant="secondary" icon={<RotateCcw className="h-3.5 w-3.5" />} onClick={() => run(() => api.post(`/inbox/${d.id}/retry`), "Re-processing")}>Re-process</Button>}
          {d.status !== "ignored" && <Button size="sm" variant="ghost" icon={<EyeOff className="h-3.5 w-3.5" />} onClick={() => run(() => api.post(`/inbox/${d.id}/ignore`), "Marked as not relevant")}>Ignore</Button>}
          <Button size="sm" variant="danger" icon={<Trash2 className="h-3.5 w-3.5" />} onClick={async () => {
            if (!confirm("Delete this document and its stored file?")) return;
            await api.del(`/inbox/${d.id}`); invalidate(); navigate("/inbox");
          }}>Delete</Button>
        </div>
      </div>

      {busy && (
        <div className="card mt-6 p-5">
          <ol className="flex flex-wrap items-center gap-x-6 gap-y-3">
            {steps.map((s, i) => {
              const idx = steps.indexOf(d.status);
              const state = i < idx ? "done" : i === idx ? "now" : "todo";
              return (
                <li key={s} className={`flex items-center gap-2 text-[13.5px] ${state === "todo" ? "text-ink-300" : "text-ink-800"}`}>
                  {state === "now" ? <Loader2 className="h-4 w-4 animate-spin text-lagoon-600" /> : <span className={`h-2 w-2 rounded-full ${state === "done" ? "bg-lagoon-500" : "bg-sand-300"}`} />}
                  {stepText[s]}
                </li>
              );
            })}
          </ol>
        </div>
      )}

      {d.status === "failed" && <div className="mt-6"><ErrorNote>{d.status_detail || "Processing failed."} You can re-process it or add the booking manually from a trip.</ErrorNote></div>}
      {d.status === "duplicate" && <div className="mt-6"><InfoNote>This file is identical to one you already uploaded{d.duplicate_of_id ? <> — <Link to={`/inbox/${d.duplicate_of_id}`} className="underline">view the original</Link></> : ""}. It was not processed again.</InfoNote></div>}

      {!busy && m.path && (
        <p className="mt-6 text-[13px] text-ink-500">
          {m.provider === "local" ? "Read by Tandem's on-server parser" : `Read by ${m.provider} (${m.model})`}
          {m.path === "original_file" ? " from the original file." : m.path === "extracted_text" ? " from text extracted on Tandem's servers." : m.path === "page_images" ? " from rendered page images." : "."}
          {m.attempts?.some((a) => !a.ok && a.reason !== "external_ai_disabled") && " AI extraction wasn't available, so Tandem fell back to local parsing."}
        </p>
      )}

      {d.attachments && d.attachments.length > 0 && (
        <div className="mt-4 text-[13px] text-ink-500">Attachments: {d.attachments.map((a) => <Link key={a.id} to={`/inbox/${a.id}`} className="mr-3 text-lagoon-600 hover:underline">{a.filename}</Link>)}</div>
      )}

      <div className="mt-6 space-y-4">
        {!busy && records.length === 0 && d.status !== "failed" && d.status !== "duplicate" && (
          <EmptyState title={d.classification === "unrelated" ? "No travel details found" : "Nothing to add"} body={d.status_detail || "This document doesn't seem to contain a booking."} />
        )}
        {records.map((r) => <RecordReview key={r.id} record={r} documentId={r.document_id} />)}
      </div>

      {d.extracted_text && (
        <div className="mt-8">
          <button onClick={() => setShowText(!showText)} className="flex items-center gap-1.5 text-[13px] font-medium text-ink-500 hover:text-ink-800">
            <ChevronDown className={`h-4 w-4 transition ${showText ? "rotate-180" : ""}`} /> {showText ? "Hide" : "Show"} text Tandem extracted
          </button>
          {showText && <pre className="mt-3 max-h-[420px] overflow-auto whitespace-pre-wrap rounded-xl border border-sand-200 bg-sand-50 p-4 text-[12.5px] leading-relaxed text-ink-700">{d.extracted_text}</pre>}
        </div>
      )}
    </div>
  );
}
