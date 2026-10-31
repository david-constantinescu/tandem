/** Installable-app pieces: the offline strip, the "new version" prompt and the Add to Home Screen card. */
import { clsx } from "clsx";
import { CloudOff, Download, RotateCw, Share, SquarePlus, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState, useSyncExternalStore } from "react";
import { registerSW } from "virtual:pwa-register";
import { Button } from "@/components/ui";

type InstallPrompt = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: "accepted" | "dismissed" }> };

// Chrome and Edge fire this once, early, often before any page has mounted; keep it until the card asks.
let deferredInstall: InstallPrompt | null = null;
const installListeners = new Set<() => void>();
if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferredInstall = e as InstallPrompt;
    installListeners.forEach((f) => f());
  });
  window.addEventListener("appinstalled", () => {
    deferredInstall = null;
    installListeners.forEach((f) => f());
  });
}

const subscribeOnline = (f: () => void) => {
  window.addEventListener("online", f);
  window.addEventListener("offline", f);
  return () => {
    window.removeEventListener("online", f);
    window.removeEventListener("offline", f);
  };
};

export function useOnline(): boolean {
  return useSyncExternalStore(subscribeOnline, () => navigator.onLine, () => true);
}

export function isStandalone(): boolean {
  return window.matchMedia("(display-mode: standalone)").matches || (navigator as { standalone?: boolean }).standalone === true;
}

function isIOS(): boolean {
  // iPadOS reports itself as a Mac; touch support gives it away.
  return /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
}

export function OfflineBanner() {
  const online = useOnline();
  return (
    <AnimatePresence initial={false}>
      {!online && (
        <motion.div role="status" initial={{ height: 0 }} animate={{ height: "auto" }} exit={{ height: 0 }} className="overflow-hidden">
          <div className="flex items-center justify-center gap-2 bg-amber-soft px-4 py-1.5 text-center text-[12.5px] font-medium text-amber-ink">
            <CloudOff className="h-3.5 w-3.5 shrink-0" />
            Offline · showing trips saved on this device
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/** Registers the service worker and offers the new version when one is waiting, instead of swapping it mid-task. */
export function UpdatePrompt() {
  const [update, setUpdate] = useState<((reload?: boolean) => Promise<void>) | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    let timer: ReturnType<typeof setInterval> | undefined;
    const updateSW = registerSW({
      onNeedRefresh: () => setUpdate(() => updateSW),
      onRegisteredSW: (_url, reg) => {
        // Installed apps can stay open for days; look for a new version every hour.
        if (reg) timer = setInterval(() => { if (navigator.onLine) reg.update(); }, 3600_000);
      },
    });
    return () => clearInterval(timer);
  }, []);

  return (
    <AnimatePresence>
      {update && (
        <motion.div role="status" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 12 }}
          className="fixed inset-x-0 bottom-[calc(max(env(safe-area-inset-bottom),12px)+82px)] z-[55] flex justify-center px-4 lg:bottom-6">
          <div className="flex max-w-md items-center gap-3 rounded-2xl bg-ink-900/95 py-2 pl-4 pr-2 text-[14px] text-white shadow-[var(--shadow-float)] backdrop-blur">
            <span>A new version of Tandem is ready.</span>
            <button onClick={() => { setBusy(true); update(true); }}
              className="flex h-9 items-center gap-1.5 rounded-xl bg-white/15 px-3 font-semibold active:scale-95">
              <RotateCw className={clsx("h-4 w-4", busy && "animate-spin")} /> Reload
            </button>
            <button onClick={() => setUpdate(null)} className="flex h-9 w-9 items-center justify-center rounded-xl text-white/70 active:scale-95" aria-label="Later">
              <X className="h-4 w-4" />
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

const DISMISSED = "tandem.install.dismissed";

/** Home-screen install: the browser's own prompt where it exists, Safari's Share → Add to Home Screen otherwise. */
export function InstallCard({ className }: { className?: string }) {
  const [, rerender] = useState(0);
  const [dismissed, setDismissed] = useState(() => {
    try { return localStorage.getItem(DISMISSED) === "1"; } catch { return false; }
  });
  useEffect(() => {
    const f = () => rerender((n) => n + 1);
    installListeners.add(f);
    return () => { installListeners.delete(f); };
  }, []);

  if (dismissed || isStandalone()) return null;
  const ios = isIOS();
  if (!deferredInstall && !ios) return null;

  const dismiss = () => {
    setDismissed(true);
    try { localStorage.setItem(DISMISSED, "1"); } catch { /* remembered for this visit only */ }
  };
  const install = async () => {
    const p = deferredInstall;
    if (!p) return;
    await p.prompt();
    if ((await p.userChoice).outcome === "accepted") dismiss();
    deferredInstall = null;
    rerender((n) => n + 1);
  };

  return (
    <div className={clsx("relative flex max-w-xl items-start gap-3.5 rounded-[22px] border border-sand-200/80 bg-white p-4 pr-11 shadow-[var(--shadow-card)]", className)}>
      <img src="/apple-touch-icon.png" alt="" className="h-12 w-12 shrink-0 rounded-[13px]" />
      <div className="min-w-0">
        <p className="text-[15px] font-semibold text-ink-900">Put Tandem on your home screen</p>
        {deferredInstall ? (
          <>
            <p className="mt-0.5 text-[13.5px] text-ink-500">It opens like an app, full screen, and your trips work offline.</p>
            <Button size="sm" className="mt-3" onClick={install} icon={<Download className="h-4 w-4" />}>Install</Button>
          </>
        ) : (
          <p className="mt-0.5 text-[13.5px] leading-relaxed text-ink-500">
            Tap <Share className="mx-0.5 inline h-4 w-4 -translate-y-px text-lagoon-600" aria-label="Share" />, then
            {" "}<span className="whitespace-nowrap font-medium text-ink-700"><SquarePlus className="mx-0.5 inline h-4 w-4 -translate-y-px" aria-hidden />Add to Home Screen</span>.
            Trips open full screen and work offline.
          </p>
        )}
      </div>
      <button onClick={dismiss} aria-label="Dismiss"
        className="absolute right-2 top-2 flex h-9 w-9 items-center justify-center rounded-full text-ink-300 hover:bg-sand-50 hover:text-ink-600">
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}
