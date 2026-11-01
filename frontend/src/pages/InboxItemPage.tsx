import { ChevronDown, ChevronLeft, Download, EyeOff, Loader2, RotateCcw, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { RecordReview } from "@/components/inbox/RecordReview";
import { Button, EmptyState, ErrorNote, InfoNote, PageLoader, StatusPill } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { api, errorMessage } from "@/lib/api";
import { bytes, relativeTime } from "@/lib/format";
import { useT, type Key } from "@/lib/i18n";
import { PROCESSING, useInboxItem, useInvalidateTripData } from "@/lib/queries";

const steps = ["queued", "processing", "analysing", "awaiting_review"];
const stepText: Record<string, Key> = { queued: "doc.step.queued", processing: "doc.step.processing", analysing: "doc.step.analysing", awaiting_review: "doc.step.ready" };

export default function InboxItemPage() {
  const { id = "" } = useParams();
  const item = useInboxItem(id);
  const [showText, setShowText] = useState(false);
  const invalidate = useInvalidateTripData();
  const toast = useToast();
  const navigate = useNavigate();
  const { t, tp } = useT();
  if (item.isLoading) return <PageLoader />;
  const d = item.data;
  if (!d) return <EmptyState title={t("doc.notFound")} action={<Link to="/inbox?tab=documents" className="text-lagoon-600">{t("doc.back")}</Link>} />;
  const busy = PROCESSING.has(d.status);
  const records = [...(d.records ?? []), ...(d.attachments ?? []).flatMap((a) => a.records ?? [])];
  const m = d.extraction_method ?? {};

  const run = async (fn: () => Promise<unknown>, msg: string) => {
    try { await fn(); invalidate(); item.refetch(); toast(msg, "success"); } catch (e) { toast(errorMessage(e), "error"); }
  };

  return (
    <div className="max-w-4xl">
      <Link to="/inbox?tab=documents" className="-ml-1 inline-flex min-h-11 items-center gap-1 pr-3 text-[15px] text-lagoon-600 hover:text-lagoon-700"><ChevronLeft className="h-5 w-5" />{t("nav.inbox")}</Link>
      <div className="mt-1 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h1 className="display break-words text-[26px] leading-tight sm:text-[30px]">{d.filename}</h1>
          <p className="mt-1.5 flex flex-wrap items-center gap-2 text-[13.5px] text-ink-500">
            <StatusPill status={d.status} /> {bytes(d.size_bytes)}{d.page_count ? ` · ${tp("doc.pages", d.page_count)}` : ""} · {relativeTime(d.created_at)}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {d.has_original && <a href={`/api/v1/documents/${d.id}/download`} className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-sand-200 bg-white px-3 text-[13px] font-medium hover:bg-sand-50 pointer-coarse:h-10 pointer-coarse:px-3.5"><Download className="h-3.5 w-3.5" /> {t("doc.original")}</a>}
          {!busy && d.has_original && <Button size="sm" variant="secondary" icon={<RotateCcw className="h-3.5 w-3.5" />} onClick={() => run(() => api.post(`/inbox/${d.id}/retry`), t("doc.reprocessing"))}>{t("doc.reprocess")}</Button>}
          {d.status !== "ignored" && <Button size="sm" variant="ghost" icon={<EyeOff className="h-3.5 w-3.5" />} onClick={() => run(() => api.post(`/inbox/${d.id}/ignore`), t("doc.ignored"))}>{t("doc.ignore")}</Button>}
          <Button size="sm" variant="danger" icon={<Trash2 className="h-3.5 w-3.5" />} onClick={async () => {
            if (!confirm(t("doc.deleteConfirm"))) return;
            await api.del(`/inbox/${d.id}`); invalidate(); navigate("/inbox?tab=documents");
          }}>{t("common.delete")}</Button>
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
                  {t(stepText[s])}
                </li>
              );
            })}
          </ol>
        </div>
      )}

      {d.status === "failed" && <div className="mt-6"><ErrorNote>{d.status_detail || t("doc.failed")} {t("doc.failedHint")}</ErrorNote></div>}
      {d.status === "duplicate" && <div className="mt-6"><InfoNote>{t("doc.duplicate")}{d.duplicate_of_id ? <> <Link to={`/inbox/${d.duplicate_of_id}`} className="underline">{t("doc.viewOriginal")}</Link></> : ""}</InfoNote></div>}

      {!busy && m.path && (
        <p className="mt-6 text-[13px] text-ink-500">
          {m.provider === "local" ? t("doc.readLocal") : m.provider === "demo" ? t("doc.readDemo") : t("doc.readBy", { provider: `${m.provider}${m.model ? ` (${m.model})` : ""}` })}
          {m.path === "original_file" ? ` ${t("doc.fromOriginal")}` : m.path === "extracted_text" ? ` ${t("doc.fromText")}` : m.path === "page_images" ? ` ${t("doc.fromImages")}` : "."}
          {m.attempts?.some((a) => !a.ok && a.reason !== "external_ai_disabled") && ` ${t("doc.fellBack")}`}
        </p>
      )}

      {d.attachments && d.attachments.length > 0 && (
        <div className="mt-4 text-[13px] text-ink-500">{t("doc.attachments")} {d.attachments.map((a) => <Link key={a.id} to={`/inbox/${a.id}`} className="mr-3 text-lagoon-600 hover:underline">{a.filename}</Link>)}</div>
      )}

      <div className="mt-6 space-y-4">
        {!busy && records.length === 0 && d.status !== "failed" && d.status !== "duplicate" && (
          <EmptyState title={d.classification === "unrelated" ? t("doc.noTravel") : t("doc.nothing")} body={d.status_detail || t("doc.noBooking")} />
        )}
        {records.map((r) => <RecordReview key={r.id} record={r} documentId={r.document_id} />)}
      </div>

      {d.extracted_text && (
        <div className="mt-8">
          <button onClick={() => setShowText(!showText)} className="flex min-h-11 items-center gap-1.5 text-[14px] font-medium text-ink-500 hover:text-ink-800">
            <ChevronDown className={`h-4 w-4 transition ${showText ? "rotate-180" : ""}`} /> {showText ? t("doc.hideText") : t("doc.showText")}
          </button>
          {showText && <pre className="mt-3 max-h-[420px] overflow-auto whitespace-pre-wrap rounded-xl border border-sand-200 bg-sand-50 p-4 text-[12.5px] leading-relaxed text-ink-700">{d.extracted_text}</pre>}
        </div>
      )}
    </div>
  );
}
