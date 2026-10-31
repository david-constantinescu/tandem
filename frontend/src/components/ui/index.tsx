import { clsx } from "clsx";
import { CloudOff, Loader2, RotateCw } from "lucide-react";
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { Link } from "react-router-dom";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "accent";
type Size = "sm" | "md" | "lg";

const variants: Record<Variant, string> = {
  primary: "bg-lagoon-900 text-white hover:bg-ink-800 shadow-sm",
  accent: "bg-clay-500 text-white hover:bg-clay-600 shadow-sm",
  secondary: "bg-white text-ink-800 border border-sand-200 hover:border-sand-300 hover:bg-sand-50",
  ghost: "text-ink-700 hover:bg-sand-100",
  danger: "bg-white text-rose-ink border border-rose-soft hover:bg-rose-soft",
};
const sizes: Record<Size, string> = {
  sm: "h-8 px-3 text-[13px] gap-1.5 rounded-lg pointer-coarse:h-10 pointer-coarse:px-3.5",
  md: "h-10 px-4 text-[14px] gap-2 rounded-xl pointer-coarse:h-11",
  lg: "h-12 px-5 text-[15px] gap-2 rounded-xl",
};

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: ReactNode;
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", loading, icon, className, children, disabled, ...rest }, ref,
) {
  return (
    <button
      ref={ref}
      className={clsx("inline-flex select-none items-center justify-center font-medium transition-[background-color,border-color,color,transform] duration-150 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100 whitespace-nowrap", variants[variant], sizes[size], className)}
      disabled={disabled || loading}
      {...rest}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
});

/** A button-styled link: `to` for routes inside the app, `href` for files and URLs the browser should open itself. */
export function LinkButton({ to, href, variant = "secondary", size = "md", icon, children, className }: { to?: string; href?: string; variant?: Variant; size?: Size; icon?: ReactNode; children: ReactNode; className?: string }) {
  const cls = clsx("inline-flex select-none items-center justify-center font-medium transition-[background-color,transform] duration-150 active:scale-[0.97] whitespace-nowrap", variants[variant], sizes[size], className);
  if (href) return <a href={href} className={cls}>{icon}{children}</a>;
  return <Link to={to ?? "/"} className={cls}>{icon}{children}</Link>;
}

export function Card({ className, children, as: As = "div" }: { className?: string; children: ReactNode; as?: any }) {
  return <As className={clsx("card", className)}>{children}</As>;
}

export function Spinner({ className, label = "Loading" }: { className?: string; label?: string }) {
  return (
    <span role="status" className={clsx("inline-flex items-center gap-2 text-ink-400", className)}>
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
      <span className="sr-only">{label}</span>
    </span>
  );
}

export function PageLoader() {
  return (
    <div className="flex min-h-[40vh] items-center justify-center">
      <Spinner />
    </div>
  );
}

type Tone = "neutral" | "lagoon" | "amber" | "violet" | "rose" | "clay" | "outline";
const tones: Record<Tone, string> = {
  neutral: "bg-sand-100 text-ink-700",
  lagoon: "bg-lagoon-50 text-lagoon-700",
  amber: "bg-amber-soft text-amber-ink",
  violet: "bg-violet-soft text-violet-ink",
  rose: "bg-rose-soft text-rose-ink",
  clay: "bg-clay-50 text-clay-600",
  outline: "border border-dashed border-ink-300 text-ink-500",
};

export function Badge({ tone = "neutral", children, className, icon }: { tone?: Tone; children: ReactNode; className?: string; icon?: ReactNode }) {
  return (
    <span className={clsx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11.5px] font-medium leading-5", tones[tone], className)}>
      {icon}
      {children}
    </span>
  );
}

const statusTone: Record<string, Tone> = {
  confirmed: "lagoon", completed: "lagoon", verified: "lagoon", processed: "lagoon",
  pending: "amber", unknown: "amber", awaiting_review: "amber", awaiting_approval: "amber", in_progress: "amber", requires_manual: "clay",
  suggested: "violet", unbooked: "outline",
  cancelled: "neutral", rejected: "neutral", expired: "neutral", ignored: "neutral", duplicate: "neutral",
  failed: "rose",
};
const statusText: Record<string, string> = {
  confirmed: "Confirmed", pending: "Pending", suggested: "Suggestion", unbooked: "Not booked", cancelled: "Cancelled",
  completed: "Completed", unknown: "Unconfirmed", awaiting_approval: "Awaiting approval", in_progress: "In progress",
  requires_manual: "Needs you", failed: "Failed", rejected: "Rejected", expired: "Expired", awaiting_review: "To review",
  processed: "Processed", ignored: "Ignored", duplicate: "Duplicate", queued: "Queued", processing: "Processing",
  analysing: "Analysing", validating: "Validating", uploaded: "Uploaded", prepared: "Prepared",
};

export function StatusPill({ status, className }: { status: string; className?: string }) {
  // Pills read like little stamps: tight, confident, never shouting.
  return <Badge tone={statusTone[status] ?? "neutral"} className={className}>{statusText[status] ?? status.replace(/_/g, " ")}</Badge>;
}

export function EmptyState({ icon, title, body, action }: { icon?: ReactNode; title: string; body?: ReactNode; action?: ReactNode }) {
  return (
    <div className="relative flex flex-col items-center justify-center overflow-hidden rounded-[24px] border border-dashed border-sand-300 bg-white/50 px-6 py-12 text-center">
      <svg viewBox="0 0 220 60" className="absolute inset-x-0 top-4 mx-auto h-12 w-56 opacity-60" aria-hidden>
        <path d="M6 44 C 50 8, 90 12, 118 30 S 180 52, 214 14" fill="none" stroke="var(--color-sand-300)" strokeWidth="2" strokeDasharray="4 7" strokeLinecap="round" />
      </svg>
      {icon && <div className="relative mb-3 mt-6 flex h-12 w-12 items-center justify-center rounded-2xl bg-apricot-soft text-clay-600 [&>svg]:h-6 [&>svg]:w-6">{icon}</div>}
      <p className="display relative text-xl text-ink-800">{title}</p>
      {body && <div className="relative mt-1.5 max-w-md text-[14.5px] text-ink-500">{body}</div>}
      {action && <div className="relative mt-5">{action}</div>}
    </div>
  );
}

export function SectionTitle({ children, action, eyebrow }: { children: ReactNode; action?: ReactNode; eyebrow?: string }) {
  return (
    <div className="mb-3 flex items-end justify-between gap-3">
      <div>
        {eyebrow && <p className="eyebrow mb-1">{eyebrow}</p>}
        <h2 className="text-[15px] font-semibold text-ink-900">{children}</h2>
      </div>
      {action}
    </div>
  );
}

export function PageHeader({ title, subtitle, actions, eyebrow }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; eyebrow?: ReactNode }) {
  return (
    <header className="mb-6 flex flex-col gap-4 sm:mb-8 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {eyebrow && <div className="eyebrow mb-2">{eyebrow}</div>}
        <h1 className="display text-[34px] leading-[1.08] tracking-[-0.02em] sm:text-[40px]">{title}</h1>
        {subtitle && <div className="mt-1.5 text-[15px] text-ink-500">{subtitle}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

/** A list that failed to load must not look like an empty account: say so and offer a retry. */
export function LoadError({ what, onRetry, retrying }: { what: string; onRetry: () => void; retrying?: boolean }) {
  const offline = typeof navigator !== "undefined" && !navigator.onLine;
  return (
    <EmptyState icon={<CloudOff />} title={`Couldn't load your ${what}`}
      body={offline ? "You're offline. Tandem will catch up when you're back online." : "Something went wrong on the way. Check your connection and try again."}
      action={<Button variant="secondary" onClick={onRetry} loading={retrying} icon={<RotateCw className="h-4 w-4" />}>Try again</Button>} />
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return <div role="alert" className="rounded-xl border border-rose-soft bg-rose-soft/60 px-3.5 py-2.5 text-[13.5px] text-rose-ink">{children}</div>;
}

export function InfoNote({ children, tone = "neutral", icon }: { children: ReactNode; tone?: "neutral" | "amber" | "lagoon" | "violet"; icon?: ReactNode }) {
  const map = { neutral: "bg-sand-50 border-sand-200 text-ink-700", amber: "bg-amber-soft border-amber-soft text-amber-ink", lagoon: "bg-lagoon-50 border-lagoon-100 text-lagoon-700", violet: "bg-violet-soft border-violet-soft text-violet-ink" };
  return <div className={clsx("flex gap-2.5 rounded-xl border px-3.5 py-2.5 text-[13.5px] leading-relaxed", map[tone])}>{icon && <span className="mt-0.5 shrink-0">{icon}</span>}<div>{children}</div></div>;
}

export function Field({ label, hint, children, htmlFor }: { label: string; hint?: ReactNode; children: ReactNode; htmlFor?: string }) {
  return (
    <div>
      <label className="label" htmlFor={htmlFor}>{label}</label>
      {children}
      {hint && <p className="mt-1 text-[12.5px] text-ink-400">{hint}</p>}
    </div>
  );
}

export function Toggle({ checked, onChange, label, description, disabled, hideLabel }: { checked: boolean; onChange: (v: boolean) => void; label: string; description?: ReactNode; disabled?: boolean; hideLabel?: boolean }) {
  return (
    <label className={clsx("flex justify-between gap-4", description ? "items-start" : "items-center", hideLabel ? "py-0" : "py-3", disabled && "opacity-60")}>
      <span className={clsx(hideLabel && "sr-only")}>
        <span className="block text-[14px] font-medium text-ink-800">{label}</span>
        {description && <span className="mt-0.5 block text-[13px] text-ink-500">{description}</span>}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        // On touch screens the switch takes UISwitch's 51×31 size, and an invisible margin stretches the hit area past 44pt.
        className={clsx("relative mt-0.5 inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors after:absolute after:-inset-2 after:content-[''] pointer-coarse:h-[31px] pointer-coarse:w-[51px]", checked ? "bg-lagoon-600" : "bg-sand-300")}
      >
        <span className={clsx("inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform pointer-coarse:h-[27px] pointer-coarse:w-[27px]", checked ? "translate-x-5 pointer-coarse:translate-x-[22px]" : "translate-x-0.5")} />
      </button>
    </label>
  );
}

export function Confidence({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const tone = value >= 0.8 ? "bg-lagoon-500" : value >= 0.55 ? "bg-amber-ink/70" : "bg-rose-ink/70";
  return (
    <span className="inline-flex items-center gap-1.5 text-[12px] text-ink-500" title="Extraction confidence">
      <span className="h-1.5 w-12 overflow-hidden rounded-full bg-sand-200"><span className={clsx("block h-full rounded-full", tone)} style={{ width: `${pct}%` }} /></span>
      {pct}%
    </span>
  );
}
