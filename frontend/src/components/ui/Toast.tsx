import { CheckCircle2, AlertTriangle, Info } from "lucide-react";
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
      <div aria-live="polite" className="pointer-events-none fixed inset-x-0 bottom-20 z-[60] flex flex-col items-center gap-2 px-4 lg:bottom-6">
        {items.map((t) => (
          <div key={t.id} className="pointer-events-auto flex max-w-md items-start gap-2.5 rounded-xl bg-ink-900 px-4 py-3 text-[14px] text-white shadow-[var(--shadow-lift)]">
            {t.tone === "success" ? <CheckCircle2 className="mt-0.5 h-4 w-4 text-lagoon-100" /> : t.tone === "error" ? <AlertTriangle className="mt-0.5 h-4 w-4 text-clay-100" /> : <Info className="mt-0.5 h-4 w-4 text-sand-200" />}
            <span>{t.text}</span>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}

export const useToast = () => useContext(Ctx);
