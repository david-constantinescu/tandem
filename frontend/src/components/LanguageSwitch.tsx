import { clsx } from "clsx";
import { motion } from "motion/react";
import { useId } from "react";
import { spring } from "@/components/motion";
import { useAuth } from "@/lib/auth";
import { LOCALES, useT } from "@/lib/i18n";

/** comutator RO | EN. Orice loc care schimba limba trece pe aici, ca si contul sa ramana la fel */
export function LanguageSwitch({ className, size = "md" }: { className?: string; size?: "sm" | "md" }) {
  const { locale, t } = useT();
  const { setLanguage } = useAuth();
  const id = useId(); // pot fi doua comutatoare pe ecran odata; fiecare isi vrea propriul buton glisant
  return (
    <div role="radiogroup" aria-label={t("lang.label")} className={clsx("inline-grid grid-cols-2 rounded-full bg-sand-100 p-0.5", className)}>
      {LOCALES.map((l) => {
        const on = l.value === locale;
        return (
          <button key={l.value} type="button" role="radio" aria-checked={on} lang={l.value} aria-label={l.label} onClick={() => setLanguage(l.value)}
            className={clsx("relative flex items-center justify-center rounded-full font-semibold tracking-wide transition-colors",
              size === "sm" ? "h-7 min-w-10 px-2.5 text-[11.5px] pointer-coarse:h-9" : "h-9 min-w-12 px-3.5 text-[13px] pointer-coarse:h-10",
              on ? "text-ink-900" : "text-ink-400 hover:text-ink-700")}>
            {on && <motion.span layoutId={`lang-${id}`} transition={spring} className="absolute inset-0 rounded-full bg-white shadow-[0_1px_3px_rgba(0,0,0,0.1)]" />}
            <span className="relative z-10">{l.short}</span>
          </button>
        );
      })}
    </div>
  );
}
