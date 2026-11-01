import { clsx } from "clsx";
import { ClipboardPaste, FileUp, Link2 } from "lucide-react";
import { useCallback, useRef, useState, type DragEvent, type FormEvent } from "react";
import { Button, ErrorNote, Field } from "@/components/ui";
import { Dialog } from "@/components/ui/Dialog";
import { useToast } from "@/components/ui/Toast";
import { api, errorMessage } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { useInvalidateTripData } from "@/lib/queries";
import type { DocumentItem } from "@/lib/types";

export const ACCEPT = ".pdf,.jpg,.jpeg,.png,.webp,.heic,.txt,.html,.htm,.eml,.docx";

type UploadError = { filename: string; message: string };

/** trimite fisiere in inbox. O folosesc zona de tras fisiere si foaia de adaugare */
export function useUpload() {
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<UploadError[]>([]);
  const invalidate = useInvalidateTripData();
  const toast = useToast();
  const { t, tp } = useT();
  const send = useCallback(async (files: FileList | File[]): Promise<DocumentItem[]> => {
    const list = Array.from(files);
    if (!list.length) return [];
    setBusy(true);
    setErrors([]);
    const form = new FormData();
    list.forEach((f) => form.append("files", f));
    try {
      const res = await api.upload<{ documents: DocumentItem[]; errors: UploadError[] }>("/inbox/upload", form);
      setErrors(res.errors);
      if (res.documents.length) toast(tp("upload.added", res.documents.length), "success");
      res.errors.forEach((e) => toast(`${e.filename}: ${e.message}`, "error"));
      return res.documents;
    } catch (e) {
      setErrors([{ filename: t("upload.upload"), message: errorMessage(e) }]);
      toast(errorMessage(e), "error");
      return [];
    } finally {
      setBusy(false);
      invalidate();
    }
  }, [invalidate, t, toast, tp]);
  return { send, busy, errors };
}

export function UploadZone() {
  const input = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const [dialog, setDialog] = useState<"paste" | "url" | null>(null);
  const { send, busy, errors } = useUpload();
  const { t } = useT();

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDrag(false);
    send(e.dataTransfer.files);
  };

  return (
    <div>
      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={onDrop}
        className={clsx("relative overflow-hidden rounded-[26px] border-2 border-dashed px-5 py-7 text-center transition sm:py-10",
          drag ? "scale-[1.01] border-lagoon-500 bg-lagoon-50" : "border-sand-300 bg-white hover:border-clay-500/40")}
      >
        <div className="mx-auto flex h-14 w-14 rotate-[-6deg] items-center justify-center rounded-[18px] bg-apricot-soft text-clay-600 shadow-[var(--shadow-card)]"><FileUp className="h-6 w-6" /></div>
        <p className="display mt-4 text-[22px] text-ink-900"><span className="pointer-coarse:hidden">{t("upload.dropTitle")}</span><span className="hidden pointer-coarse:inline">{t("upload.title")}</span></p>
        <p className="mx-auto mt-1.5 max-w-sm text-[14px] text-ink-500">{t("upload.formats")}</p>
        <div className="mx-auto mt-5 grid max-w-sm grid-cols-2 gap-2 sm:flex sm:max-w-none sm:flex-wrap sm:justify-center">
          <Button onClick={() => input.current?.click()} loading={busy} className="col-span-2" icon={<FileUp className="h-4 w-4" />}>{t("upload.choose")}</Button>
          <Button variant="secondary" onClick={() => setDialog("paste")} icon={<ClipboardPaste className="h-4 w-4" />}>{t("upload.paste")}</Button>
          <Button variant="secondary" onClick={() => setDialog("url")} icon={<Link2 className="h-4 w-4" />}>{t("upload.link")}</Button>
        </div>
        <input ref={input} type="file" multiple accept={ACCEPT} className="sr-only" aria-label={t("upload.choose")}
          onChange={(e) => { if (e.target.files) send(e.target.files); e.target.value = ""; }} />
      </div>
      {errors.length > 0 && <div className="mt-3 space-y-2">{errors.map((e, i) => <ErrorNote key={i}><strong>{e.filename}</strong>: {e.message}</ErrorNote>)}</div>}
      {dialog === "paste" && <PasteDialog onClose={() => setDialog(null)} />}
      {dialog === "url" && <UrlDialog onClose={() => setDialog(null)} />}
    </div>
  );
}

export function PasteDialog({ onClose, onDone }: { onClose: () => void; onDone?: (doc: DocumentItem) => void }) {
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const invalidate = useInvalidateTripData();
  const { t } = useT();
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const doc = await api.post<DocumentItem>("/inbox/paste", { text });
      invalidate();
      onClose();
      onDone?.(doc);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={t("upload.pasteTitle")} description={t("upload.pasteHint")} wide>
      <form onSubmit={submit} className="space-y-4">
        <textarea className="field min-h-[220px] font-mono text-[13px]" value={text} onChange={(e) => setText(e.target.value)} placeholder={t("upload.pastePlaceholder")} aria-label={t("upload.pasteTitle")} required />
        {error && <ErrorNote>{error}</ErrorNote>}
        <div className="flex justify-end gap-2 pb-2"><Button type="button" variant="ghost" onClick={onClose}>{t("common.cancel")}</Button><Button type="submit" loading={busy}>{t("upload.pasteSubmit")}</Button></div>
      </form>
    </Dialog>
  );
}

export function UrlDialog({ onClose, onDone }: { onClose: () => void; onDone?: (doc: DocumentItem) => void }) {
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const invalidate = useInvalidateTripData();
  const { t } = useT();
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const doc = await api.post<DocumentItem>("/inbox/url", { url });
      invalidate();
      onClose();
      onDone?.(doc);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={t("upload.urlTitle")} description={t("upload.urlHint")}>
      <form onSubmit={submit} className="space-y-4">
        <Field label={t("upload.urlLabel")} htmlFor="u"><input id="u" type="url" required className="field" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" /></Field>
        {error && <ErrorNote>{error}</ErrorNote>}
        <div className="flex justify-end gap-2 pb-2"><Button type="button" variant="ghost" onClick={onClose}>{t("common.cancel")}</Button><Button type="submit" loading={busy}>{t("upload.urlSubmit")}</Button></div>
      </form>
    </Dialog>
  );
}
