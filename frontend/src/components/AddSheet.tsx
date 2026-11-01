/**
 * singurul mod de a adauga ceva: un fisier de confirmare, poza unui bilet, un email lipit sau un link. Orice ar fi,
 * ajunge in chat si Tandem raspunde cu ce a citit. (Gmail nu are buton: dupa ce il conectezi din Setari, emailurile de
 * calatorie vin singure in chat.) Se deschide din + de la bara de chat si din ecranele goale.
 */
import { Camera, ChevronRight, ClipboardPaste, FileUp, Link2, Loader2 } from "lucide-react";
import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ACCEPT, PasteDialog, UrlDialog, useUpload } from "@/components/inbox/UploadZone";
import { Dialog } from "@/components/ui/Dialog";
import { useToast } from "@/components/ui/Toast";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT, type Key } from "@/lib/i18n";
import { keys, useTrips, type ConversationPayload } from "@/lib/queries";
import type { Conversation, DocumentItem } from "@/lib/types";

const Ctx = createContext<{ openAdd: () => void; busy: boolean }>({ openAdd: () => {}, busy: false });

export const useAdd = () => useContext(Ctx);

type Option = { key: string; icon: typeof FileUp; title: Key; hint: Key; touchOnly?: boolean; run: () => void };

export function AddProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [dialog, setDialog] = useState<"paste" | "url" | null>(null);
  const files = useRef<HTMLInputElement>(null);
  const camera = useRef<HTMLInputElement>(null);
  const { send, busy } = useUpload();
  const navigate = useNavigate();
  const location = useLocation();
  const trips = useTrips();
  const qc = useQueryClient();
  const toast = useToast();
  const { t } = useT();
  const { user } = useAuth();
  // in demo, documente de test trimise prin aceeasi citire reala, ca sa se vada ce spune asistentul
  const samples = useQuery({ queryKey: ["demo-samples"], enabled: !!user?.is_demo && open,
    queryFn: () => api.get<{ key: string; filename: string; description: string }[]>("/demo/samples") });
  const sendSample = async (key: string) => {
    setOpen(false);
    try {
      await show([await api.post<DocumentItem>(`/demo/samples/${key}/upload`)]);
    } catch (e) {
      toast(errorMessage(e), "error");
    }
  };

  // tot ce se adauga ajunge in chat: conversatia deschisa sau una noua despre urmatoarea calatorie
  const show = useCallback(async (docs: DocumentItem[]) => {
    if (!docs.length) return;
    try {
      let convId = location.pathname.match(/^\/assistant\/([\w-]+)/)?.[1];
      if (!convId) {
        const next = trips.data?.find((x) => x.stats.phase !== "past" && x.stats.phase !== "cancelled");
        convId = (await api.post<Conversation>("/assistant/conversations", { trip_id: next?.id ?? null })).id;
      }
      const payload = await api.post<ConversationPayload>(`/assistant/conversations/${convId}/attachments`, { document_ids: docs.map((d) => d.id) });
      qc.setQueryData(keys.conversation(convId), payload);
      qc.invalidateQueries({ queryKey: keys.conversations });
      navigate(`/assistant/${convId}`);
    } catch (e) {
      toast(errorMessage(e), "error");
    }
  }, [location.pathname, trips.data, qc, navigate, toast]);

  const pick = (input: HTMLInputElement | null) => {
    // selectorul trebuie sa se deschida in interiorul atingerii, inainte sa se inchida foaia (altfel iOS il ignora)
    input?.click();
    setOpen(false);
  };
  const options: Option[] = [
    { key: "file", icon: FileUp, title: "add.file", hint: "add.fileHint", run: () => pick(files.current) },
    { key: "camera", icon: Camera, title: "add.camera", hint: "add.cameraHint", touchOnly: true, run: () => pick(camera.current) },
    { key: "paste", icon: ClipboardPaste, title: "add.paste", hint: "add.pasteHint", run: () => { setOpen(false); setDialog("paste"); } },
    { key: "url", icon: Link2, title: "add.link", hint: "add.linkHint", run: () => { setOpen(false); setDialog("url"); } },
  ];

  const onFiles = async (list: FileList | null) => {
    if (list?.length) show(await send(list));
  };

  return (
    <Ctx.Provider value={{ openAdd: () => setOpen(true), busy }}>
      {children}
      <input ref={files} type="file" multiple accept={ACCEPT} className="sr-only" tabIndex={-1} aria-hidden
        onChange={(e) => { onFiles(e.target.files); e.target.value = ""; }} />
      <input ref={camera} type="file" accept="image/*" capture="environment" className="sr-only" tabIndex={-1} aria-hidden
        onChange={(e) => { onFiles(e.target.files); e.target.value = ""; }} />
      <Dialog open={open} onOpenChange={setOpen} title={t("add.title")} description={t("add.subtitle")}>
        <ul className="-mx-2 pb-3">
          {options.map((o) => (
            <li key={o.key} className={o.touchOnly ? "hidden pointer-coarse:block" : undefined}>
              <button onClick={o.run} className="flex min-h-[64px] w-full items-center gap-3.5 rounded-2xl px-2 py-2 text-left transition active:scale-[0.99] active:bg-sand-50 hover:bg-sand-50">
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[14px] bg-apricot-soft text-clay-600"><o.icon className="h-5 w-5" /></span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[15.5px] font-semibold text-ink-900">{t(o.title)}</span>
                  <span className="block text-[13px] text-ink-500">{t(o.hint)}</span>
                </span>
                <ChevronRight className="h-4 w-4 shrink-0 text-ink-300" />
              </button>
            </li>
          ))}
        </ul>
        {user?.is_demo && !!samples.data?.length && (
          <div className="-mx-2 border-t border-sand-100 px-2 pb-3 pt-3">
            <p className="eyebrow mb-1">{t("inbox.samples")}</p>
            <p className="mb-2 text-[12.5px] text-ink-500">{t("inbox.samplesHint")}</p>
            <ul className="space-y-1.5">
              {samples.data.map((s) => (
                <li key={s.key}>
                  <button onClick={() => sendSample(s.key)} className="flex min-h-11 w-full flex-col rounded-xl bg-sand-50 px-3 py-2 text-left active:scale-[0.99]">
                    <span className="text-[13.5px] font-medium text-ink-900">{s.filename}</span>
                    <span className="text-[12.5px] text-ink-500">{s.description}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Dialog>
      {busy && (
        <div role="status" className="fixed inset-x-0 top-[calc(env(safe-area-inset-top)+64px)] z-[60] flex justify-center px-4">
          <span className="flex items-center gap-2 rounded-full bg-ink-900/95 px-4 py-2 text-[13.5px] text-white shadow-[var(--shadow-float)]">
            <Loader2 className="h-4 w-4 animate-spin" />{t("upload.sending")}
          </span>
        </div>
      )}
      {dialog === "paste" && <PasteDialog onClose={() => setDialog(null)} onDone={(d) => show([d])} />}
      {dialog === "url" && <UrlDialog onClose={() => setDialog(null)} onDone={(d) => show([d])} />}
    </Ctx.Provider>
  );
}
