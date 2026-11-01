import { Moon, Sun } from "lucide-react";
import { useCallback, useSyncExternalStore } from "react";
import { useT } from "@/lib/i18n";

/** intunecat implicit, luminos cand e ales. Tinut pe dispozitiv in localStorage (tema tine de ecran, nu de cont) */
export type Theme = "dark" | "light";
const KEY = "tandem.theme";
const listeners = new Set<() => void>();

function read(): Theme {
  try {
    return localStorage.getItem(KEY) === "light" ? "light" : "dark";
  } catch {
    return "dark";
  }
}

export function applyTheme(theme: Theme = read()) {
  const root = document.documentElement;
  if (theme === "light") root.dataset.theme = "light";
  else delete root.dataset.theme; // intunecat e ce face stilul fara atribut
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "light" ? "#faf8f4" : "#0e1416");
}

export function useTheme(): [Theme, (t: Theme) => void] {
  const theme = useSyncExternalStore((cb) => { listeners.add(cb); return () => listeners.delete(cb); }, read, () => "dark" as Theme);
  const set = useCallback((t: Theme) => {
    try { localStorage.setItem(KEY, t); } catch { /* mod privat: schimbam oricum pentru vizita asta */ }
    applyTheme(t);
    listeners.forEach((l) => l());
  }, []);
  return [theme, set];
}

/** buton soare/luna pentru bara de sus */
export function ThemeToggle({ className }: { className?: string }) {
  const [theme, setTheme] = useTheme();
  const { t } = useT();
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button type="button" onClick={() => setTheme(next)} aria-label={t(next === "light" ? "theme.toLight" : "theme.toDark")}
      className={`flex h-10 w-10 items-center justify-center rounded-full text-ink-600 transition hover:bg-sand-100 active:scale-90 ${className ?? ""}`}>
      {theme === "dark" ? <Sun className="h-[19px] w-[19px]" /> : <Moon className="h-[19px] w-[19px]" />}
    </button>
  );
}
