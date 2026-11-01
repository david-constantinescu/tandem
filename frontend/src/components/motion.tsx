import { motion, type HTMLMotionProps, type Transition } from "motion/react";
import type { ReactNode } from "react";

/** miscare comuna: rapida, elastica, niciodata in cale. Respecta miscarea redusa prin <MotionConfig> */
export const spring: Transition = { type: "spring", stiffness: 420, damping: 36, mass: 0.7 };
export const softSpring: Transition = { type: "spring", stiffness: 260, damping: 30 };
const easeOut = [0.22, 1, 0.36, 1] as const;

export function Page({ children }: { children: ReactNode }) {
  return (
    <motion.div className="h-full" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, ease: easeOut }}>
      {children}
    </motion.div>
  );
}

const container = { hidden: {}, show: { transition: { staggerChildren: 0.05, delayChildren: 0.04 } } };
const child = { hidden: { opacity: 0, y: 14 }, show: { opacity: 1, y: 0, transition: { duration: 0.42, ease: easeOut } } };

export function Stagger({ children, className, as = "div" }: { children: ReactNode; className?: string; as?: "div" | "ul" | "ol" }) {
  const Comp = motion[as];
  return <Comp className={className} variants={container} initial="hidden" animate="show">{children}</Comp>;
}

export function StaggerItem({ children, className, as = "div", ...rest }: { children: ReactNode; className?: string; as?: "div" | "li" | "article" } & Omit<HTMLMotionProps<"div">, "children">) {
  const Comp = motion[as] as typeof motion.div;
  return <Comp className={className} variants={child} {...rest}>{children}</Comp>;
}

/** linie de traseu ca desenata de mana, care se deseneaza singura, cu un avion care aluneca pe ea */
export function RouteDoodle({ className, from, to, light }: { className?: string; from?: string; to?: string; light?: boolean }) {
  const stroke = light ? "rgba(255,255,255,0.75)" : "var(--color-clay-500)";
  const path = "M10 46 C 70 6, 150 6, 210 30 S 300 58, 330 18";
  return (
    <div className={className} aria-hidden>
      <svg viewBox="0 0 340 64" className="h-full w-full overflow-visible">
        <motion.path d={path} fill="none" stroke={stroke} strokeWidth="2" strokeDasharray="5 7" strokeLinecap="round"
          initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.6, ease: easeOut, delay: 0.2 }} />
        <circle cx="10" cy="46" r="4.5" fill={stroke} />
        <motion.circle cx="330" cy="18" r="4.5" fill={stroke} initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ ...spring, delay: 1.5 }} />
        <motion.g initial={{ offsetDistance: "0%", opacity: 0 }} animate={{ offsetDistance: "100%", opacity: [0, 1, 1, 0] }}
          transition={{ duration: 1.8, ease: "easeInOut", delay: 0.2 }} style={{ offsetPath: `path("${path}")`, offsetRotate: "auto" }}>
          <path d="M-7 0 L5 -1 L9 0 L5 1 Z M-2 0 L-5 -6 L-3 -6 L2 -1 Z M-2 0 L-5 6 L-3 6 L2 1 Z" fill={stroke} />
        </motion.g>
      </svg>
      {(from || to) && (
        <div className="mt-1 flex justify-between text-[11px] font-semibold tracking-[0.18em] opacity-80">
          <span>{from}</span><span>{to}</span>
        </div>
      )}
    </div>
  );
}

/** comutator segmentat ca pe iOS, cu buton glisant */
export function Segmented<T extends string>({ value, onChange, options, id, className }: {
  value: T; onChange: (v: T) => void; options: { value: T; label: ReactNode }[]; id: string; className?: string;
}) {
  return (
    <div role="tablist" className={`grid rounded-[14px] bg-sand-100 p-1 sm:inline-grid ${className ?? ""}`} style={{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }}>
      {options.map((o) => (
        <button key={o.value} role="tab" aria-selected={value === o.value} onClick={() => onChange(o.value)}
          className={`relative flex h-9 items-center justify-center gap-1.5 rounded-[10px] px-4 text-[14px] font-medium transition-colors pointer-coarse:h-10 ${value === o.value ? "text-ink-900" : "text-ink-500"}`}>
          {value === o.value && <motion.span layoutId={id} transition={spring} className="absolute inset-0 rounded-[10px] bg-white shadow-[0_1px_3px_rgba(0,0,0,0.08)]" />}
          <span className="relative z-10 flex items-center gap-1.5">{o.label}</span>
        </button>
      ))}
    </div>
  );
}
