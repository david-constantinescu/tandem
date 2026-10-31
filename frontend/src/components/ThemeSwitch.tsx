import { clsx } from "clsx";
import { motion } from "motion/react";
import { useId } from "react";
import { spring } from "@/components/motion";
import { useT } from "@/lib/i18n";
import { useTheme, type Theme } from "@/lib/theme";

/** Dark | Light, the same shape as the language switch. */
export function ThemeSwitch({ className }: { className?: string }) {
  const [theme, setTheme] = useTheme();
  const { t } = useT();
  const id = useId();
  const options: { value: Theme; label: string }[] = [{ value: "dark", label: t("theme.dark") }, { value: "light", label: t("theme.light") }];
  return (
    <div role="radiogroup" aria-label={t("theme.label")} className={clsx("inline-grid grid-cols-2 rounded-full bg-sand-100 p-0.5", className)}>
      {options.map((o) => {
        const on = o.value === theme;
        return (
          <button key={o.value} type="button" role="radio" aria-checked={on} onClick={() => setTheme(o.value)}
            className={clsx("relative flex h-9 min-w-[72px] items-center justify-center rounded-full px-3 text-[13px] font-semibold transition-colors pointer-coarse:h-10",
              on ? "text-ink-900" : "text-ink-400 hover:text-ink-700")}>
            {on && <motion.span layoutId={`theme-${id}`} transition={spring} className="absolute inset-0 rounded-full bg-white shadow-[0_1px_3px_rgba(0,0,0,0.1)]" />}
            <span className="relative z-10">{o.label}</span>
          </button>
        );
      })}
    </div>
  );
}
