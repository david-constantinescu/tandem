import { clsx } from "clsx";
import { ClipboardPaste, FileUp, Link2 } from "lucide-react";
import { useRef, useState, type DragEvent, type FormEvent } from "react";
import { Button, ErrorNote, Field } from "@/components/ui";
import { Dialog } from "@/components/ui/Dialog";
import { useToast } from "@/components/ui/Toast";
import { api, errorMessage } from "@/lib/api";
import { useInvalidateTripData } from "@/lib/queries";
import type { DocumentItem } from "@/lib/types";

const ACCEPT = ".pdf,.jpg,.jpeg,.png,.webp,.txt,.html,.htm,.eml,.docx";

export function UploadZone() {
  const input = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<{ filename: string; message: string }[]>([]);
  const [dialog, setDialog] = useState<"paste" | "url" | null>(null);
  const invalidate = useInvalidateTripData();
  const toast = useToast();

  const send = async (files: FileList | File[]) => {
    const list = Array.from(files);
    if (!list.length) return;
    setBusy(true);
    setErrors([]);
    const form = new FormData();
    list.forEach((f) => form.append("files", f));
    try {
      const res = await api.upload<{ documents: DocumentItem[]; errors: { filename: string; message: string }[] }>("/inbox/upload", form);
      setErrors(res.errors);
      if (res.documents.length) toast(`${res.documents.length} file${res.documents.length > 1 ? "s" : ""} added — reading now`, "success");
    } catch (e) {
      setErrors([{ filename: "Upload", message: errorMessage(e) }]);
    } finally {
      setBusy(false);
      invalidate();
      if (input.current) input.current.value = "";
    }
  };

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
        className={clsx("rounded-[22px] border-2 border-dashed px-5 py-9 text-center transition sm:py-11",
          drag ? "border-lagoon-500 bg-lagoon-50" : "border-sand-300 bg-white hover:border-sand-300/80")}
      >
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-lagoon-50 text-lagoon-600"><FileUp className="h-6 w-6" /></div>
        <p className="display mt-4 text-[20px] text-ink-900">Drop booking confirmations here</p>
        <p className="mt-1.5 text-[14px] text-ink-500">PDFs, screenshots, photos, emails (.eml), Word, HTML or text — up to 10 at once.</p>
        <div className="mt-5 flex flex-wrap justify-center gap-2">
          <Button onClick={() => input.current?.click()} loading={busy} icon={<FileUp className="h-4 w-4" />}>Choose files</Button>
          <Button variant="secondary" onClick={() => setDialog("paste")} icon={<ClipboardPaste className="h-4 w-4" />}>Paste text</Button>
          <Button variant="secondary" onClick={() => setDialog("url")} icon={<Link2 className="h-4 w-4" />}>Add a link</Button>
        </div>
        <input ref={input} type="file" multiple accept={ACCEPT} className="sr-only" onChange={(e) => e.target.files && send(e.target.files)} aria-label="Upload files" />
      </div>
      {errors.length > 0 && <div className="mt-3 space-y-2">{errors.map((e, i) => <ErrorNote key={i}><strong>{e.filename}</strong>: {e.message}</ErrorNote>)}</div>}
      {dialog === "paste" && <PasteDialog onClose={() => setDialog(null)} />}
      {dialog === "url" && <UrlDialog onClose={() => setDialog(null)} />}
    </div>
  );
}

function PasteDialog({ onClose }: { onClose: () => void }) {
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const invalidate = useInvalidateTripData();
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/inbox/paste", { text });
      invalidate();
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title="Paste a confirmation" description="Paste the text of an email or message. Instructions inside it are never followed — it's treated as data." wide>
      <form onSubmit={submit} className="space-y-4">
        <textarea className="field min-h-[220px] font-mono text-[13px]" value={text} onChange={(e) => setText(e.target.value)} placeholder="Booking reference: ..." aria-label="Pasted text" required />
        {error && <ErrorNote>{error}</ErrorNote>}
        <div className="flex justify-end gap-2"><Button type="button" variant="ghost" onClick={onClose}>Cancel</Button><Button type="submit" loading={busy}>Add to inbox</Button></div>
      </form>
    </Dialog>
  );
}

function UrlDialog({ onClose }: { onClose: () => void }) {
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const invalidate = useInvalidateTripData();
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post("/inbox/url", { url });
      invalidate();
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title="Import from a link" description="Tandem fetches public pages or files (PDF, image, HTML). Private network addresses are blocked.">
      <form onSubmit={submit} className="space-y-4">
        <Field label="Link" htmlFor="u"><input id="u" type="url" required className="field" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" /></Field>
        {error && <ErrorNote>{error}</ErrorNote>}
        <div className="flex justify-end gap-2"><Button type="button" variant="ghost" onClick={onClose}>Cancel</Button><Button type="submit" loading={busy}>Import</Button></div>
      </form>
    </Dialog>
  );
}
