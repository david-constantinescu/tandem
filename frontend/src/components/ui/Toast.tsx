import { CheckCircle2, AlertTriangle, Info } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

type Toast = { id: number; tone: "success" | "error" | "info"; text: string };
const Ctx = createContext<(text: string, tone?: Toast["tone"]) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const push = useCallback((text: string, tone: Toast["tone"] = "info") => {
    const id = Date.now() + Math.random();
    setItems((xs) => [...xs, { id, tone, text }]);
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), 4500);
  }, []);
  return (
    <Ctx.Provider value={push}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed inset-x-0 bottom-[calc(max(env(safe-area-inset-bottom),12px)+82px)] z-[60] flex flex-col items-center gap-2 px-4 lg:bottom-6">
        <AnimatePresence>
        {items.map((t) => (
          <motion.div key={t.id} layout initial={{ opacity: 0, y: 24, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.98 }} transition={{ type: "spring", stiffness: 500, damping: 34 }}
            className="pointer-events-auto flex max-w-md items-start gap-2.5 rounded-2xl bg-ink-900/95 px-4 py-3 text-[14px] text-white shadow-[var(--shadow-float)] backdrop-blur">
            {t.tone === "success" ? <CheckCircle2 className="mt-0.5 h-4 w-4 text-lagoon-100" /> : t.tone === "error" ? <AlertTriangle className="mt-0.5 h-4 w-4 text-clay-100" /> : <Info className="mt-0.5 h-4 w-4 text-sand-200" />}
            <span>{t.text}</span>
          </motion.div>
        ))}
        </AnimatePresence>
      </div>
    </Ctx.Provider>
  );
}

export const useToast = () => useContext(Ctx);
