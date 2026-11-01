/**
 * navigare. Asistentul e centrul aplicatiei: tabul din mijloc si locul unde ajunge tot ce se adauga. In jurul lui:
 * Acasa (ce urmeaza) si Calatorii (planul, rezervarile, harta si documentele fiecareia). Ce te asteapta (documente de
 * verificat, aprobari) vine ca mesaj de la asistent, cu un numar pe tabul lui.
 * O calatorie noua porneste din bara de sus. Paginile se deruleaza normal; chatul isi tine bara lipita jos.
 */
import * as Popover from "@radix-ui/react-popover";
import { clsx } from "clsx";
import { Bell, CheckCheck, Home, LogOut, Map, MessageCircle, Plus, Settings } from "lucide-react";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { motion } from "motion/react";
import { AddProvider } from "@/components/AddSheet";
import { NewTripDialog } from "@/components/trips/NewTripDialog";
import { LanguageSwitch } from "@/components/LanguageSwitch";
import { spring } from "@/components/motion";
import { ThemeToggle } from "@/lib/theme";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { relativeTime } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { keys, useApprovals, useInbox, useNotifications } from "@/lib/queries";

export function Logo({ className, compact }: { className?: string; compact?: boolean }) {
  const { t } = useT();
  return (
    <Link to="/" className={clsx("flex items-center gap-2.5", className)} aria-label={t("nav.homeLabel")}>
      <svg viewBox="0 0 64 64" className="h-8 w-8" aria-hidden>
        <rect width="64" height="64" rx="16" fill="#14363a" />
        <circle cx="25" cy="32" r="11" fill="none" stroke="#f3e9dc" strokeWidth="5" />
        <circle cx="39" cy="32" r="11" fill="none" stroke="#e08a5b" strokeWidth="5" />
      </svg>
      <span className={clsx("display text-[21px] font-semibold tracking-tight text-ink-900", compact && "hidden min-[400px]:inline")}>Tandem</span>
    </Link>
  );
}

/** ce asteapta omul: documente de verificat si rezervari de aprobat; apare ca numar pe tabul asistentului */
export function useWaitingCount() {
  const inbox = useInbox();
  const approvals = useApprovals("awaiting_approval");
  const review = (inbox.data?.data ?? []).filter((d) => d.status === "awaiting_review").length;
  return review + (approvals.data?.length ?? 0);
}

function NavItem({ to, icon, label, count, end }: { to: string; icon: ReactNode; label: string; count?: number; end?: boolean }) {
  return (
    <NavLink to={to} end={end} className="group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-[14px] font-medium">
      {({ isActive }) => (
        <>
          {isActive && <motion.span layoutId="side-pill" transition={spring} className="absolute inset-0 rounded-xl bg-white shadow-[var(--shadow-card)]" />}
          <span className={clsx("relative z-10 [&>svg]:h-[18px] [&>svg]:w-[18px] transition-colors", isActive ? "text-clay-600" : "text-ink-400 group-hover:text-ink-700")}>{icon}</span>
          <span className={clsx("relative z-10 flex-1 transition-colors", isActive ? "text-ink-900" : "text-ink-500 group-hover:text-ink-800")}>{label}</span>
          {!!count && <span className="relative z-10 rounded-full bg-clay-500 px-1.5 text-[11px] font-semibold leading-5 text-white">{count}</span>}
        </>
      )}
    </NavLink>
  );
}

function HeaderLink({ to, label, children, count }: { to: string; label: string; children: ReactNode; count?: number }) {
  return (
    <NavLink to={to} aria-label={label} className={({ isActive }) => clsx("relative flex h-11 w-11 items-center justify-center rounded-full transition active:scale-90 active:bg-sand-100 lg:hidden [&>svg]:h-[21px] [&>svg]:w-[21px]", isActive ? "text-clay-600" : "text-ink-600")}>
      {children}
      {!!count && <span className="absolute right-1 top-1 flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-clay-500 px-1 text-[10.5px] font-bold text-white ring-2 ring-paper">{count > 9 ? "9+" : count}</span>}
    </NavLink>
  );
}

function Notifications() {
  const { data } = useNotifications();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { t, tp } = useT();
  const unread = data?.meta?.unread ?? 0;
  const items = data?.data ?? [];
  const markAll = async () => {
    await api.post("/notifications/read-all");
    qc.invalidateQueries({ queryKey: keys.notifications });
  };
  return (
    <Popover.Root>
      <Popover.Trigger className="relative flex h-11 w-11 items-center justify-center rounded-full text-ink-600 transition hover:bg-sand-100 hover:text-ink-800 active:scale-90"
        aria-label={unread ? tp("notif.labelUnread", unread) : t("notif.title")}>
        <Bell className="h-5 w-5" />
        {unread > 0 && <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-clay-500 ring-2 ring-paper" />}
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content align="end" sideOffset={8} collisionPadding={12} className="z-50 w-[min(94vw,380px)] rounded-[22px] border border-sand-200 bg-white p-2 shadow-[var(--shadow-float)] data-[state=open]:animate-[fade-in_.18s_ease-out]">
          <div className="flex items-center justify-between px-2 py-1.5">
            <p className="text-[13px] font-semibold">{t("notif.title")}</p>
            {unread > 0 && (
              <button onClick={markAll} className="flex min-h-9 items-center gap-1 text-[12.5px] text-lagoon-600 hover:underline">
                <CheckCheck className="h-3.5 w-3.5" /> {t("notif.markAll")}
              </button>
            )}
          </div>
          <div className="max-h-[60vh] overflow-y-auto">
            {items.length === 0 && <p className="px-3 py-8 text-center text-[13px] text-ink-400">{t("notif.empty")}</p>}
            {items.map((n) => (
              <Popover.Close asChild key={n.id}>
                <button
                  onClick={async () => {
                    if (!n.read) api.post(`/notifications/${n.id}/read`).then(() => qc.invalidateQueries({ queryKey: keys.notifications }));
                    if (n.link) navigate(n.link);
                  }}
                  className={clsx("flex w-full gap-3 rounded-xl px-3 py-2.5 text-left hover:bg-sand-50", !n.read && "bg-lagoon-50/40")}
                >
                  <span className={clsx("mt-1.5 h-2 w-2 shrink-0 rounded-full", {
                    "bg-rose-ink": n.severity === "critical", "bg-amber-ink": n.severity === "warning",
                    "bg-lagoon-500": n.severity === "success", "bg-ink-300": n.severity === "info",
                  })} />
                  <span className="min-w-0 flex-1">
                    <span className="block text-[13.5px] font-medium text-ink-800">{n.title}</span>
                    {n.body && <span className="mt-0.5 line-clamp-2 block text-[12.5px] text-ink-500">{n.body}</span>}
                    <span className="mt-1 block text-[11.5px] text-ink-400">{relativeTime(n.created_at)}</span>
                  </span>
                </button>
              </Popover.Close>
            ))}
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  return <AddProvider><Shell>{children}</Shell></AddProvider>;
}

/** o data pe vizita, lasam Tandem sa caute stiri despre calatoriile urmatoare (scrie in chat daca are nevoie de tine) */
function useCheckIn(enabled: boolean) {
  const qc = useQueryClient();
  useEffect(() => {
    if (!enabled) return;
    let done = false;
    try { done = sessionStorage.getItem("tandem.checkin") === "1"; } catch { /* mod privat */ }
    if (done) return;
    api.post<{ posted: number }>("/assistant/check-in").then((r) => {
      try { sessionStorage.setItem("tandem.checkin", "1"); } catch { /* ignoram */ }
      if (r.posted) {
        qc.invalidateQueries({ queryKey: keys.conversations });
        qc.invalidateQueries({ queryKey: keys.notifications });
      }
    }).catch(() => {});
  }, [enabled, qc]);
}

function Shell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const { t } = useT();
  const navigate = useNavigate();
  const waiting = useWaitingCount();
  const [newTrip, setNewTrip] = useState(false);
  useCheckIn(!!user);
  const tabs = [
    { to: "/", icon: <Home />, label: t("nav.home"), end: true, count: 0 },
    { to: "/assistant", icon: <MessageCircle />, label: t("nav.assistant"), count: waiting },
    { to: "/trips", icon: <Map />, label: t("nav.trips"), count: 0 },
  ];

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-paper lg:flex-row">
      <aside className="hidden w-[248px] shrink-0 flex-col border-r border-sand-200/70 bg-sand-50/80 px-4 py-6 lg:flex">
        <Logo className="px-2" />
        <button onClick={() => setNewTrip(true)} className="mt-7 flex h-11 items-center justify-center gap-2 rounded-xl bg-lagoon-900 text-[14px] font-medium text-white shadow-sm transition hover:bg-ink-800 active:scale-[0.98]">
          <Plus className="h-4 w-4" /> {t("trips.new")}
        </button>
        <nav className="mt-6 flex flex-col gap-1" aria-label={t("nav.main")}>
          <NavItem to="/" end icon={<Home />} label={t("nav.home")} />
          <NavItem to="/assistant" icon={<MessageCircle />} label={t("nav.assistant")} count={waiting} />
          <NavItem to="/trips" icon={<Map />} label={t("nav.trips")} />
        </nav>
        <div className="mt-auto flex flex-col gap-1">
          <NavItem to="/settings" icon={<Settings />} label={t("nav.settings")} />
          <div className="mt-2 flex items-center justify-between px-3">
            <span className="text-[12.5px] text-ink-400">{t("lang.label")}</span>
            <LanguageSwitch size="sm" />
          </div>
          <div className="mt-3 flex items-center gap-3 rounded-xl px-3 py-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-lagoon-900 text-[13px] font-semibold text-white">
              {(user?.display_name || user?.email || "?").slice(0, 1).toUpperCase()}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[13px] font-medium text-ink-800">{user?.display_name || t("common.traveller")}</span>
              <span className="block truncate text-[11.5px] text-ink-400">{user?.is_demo ? t("demo.workspace") : user?.email}</span>
            </span>
            <button onClick={async () => { navigate("/", { replace: true }); await logout(); }} className="rounded-lg p-1.5 text-ink-400 hover:bg-white hover:text-ink-700" aria-label={t("auth.signOut")}>
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </aside>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="safe-top z-30 shrink-0 border-b border-sand-200/60 bg-paper/90 backdrop-blur-xl lg:border-none lg:bg-transparent">
          <div className="flex h-[52px] items-center gap-1 px-3 lg:h-14 lg:justify-end lg:px-8">
            <Logo compact className="mr-auto pl-1 lg:hidden" />
            <button onClick={() => setNewTrip(true)} aria-label={t("trips.new")}
              className="flex h-9 items-center gap-1.5 rounded-full bg-ink-900 pl-2.5 pr-3.5 text-[13px] font-semibold text-white shadow-sm transition active:scale-95 lg:hidden">
              <Plus className="h-4 w-4" strokeWidth={2.5} /><span>{t("nav.trip")}</span>
            </button>
            <ThemeToggle />
            <Notifications />
            <HeaderLink to="/settings" label={t("nav.settings")}><Settings /></HeaderLink>
          </div>
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
          <div className="mx-auto h-full w-full max-w-[1100px] px-4 pt-3 sm:px-6 lg:px-10">{children}</div>
        </main>
        <nav aria-label={t("nav.main")} className="shrink-0 border-t border-sand-200/60 bg-white/85 px-2 pb-[max(env(safe-area-inset-bottom),6px)] pt-1 backdrop-blur-xl lg:hidden">
          <div className="mx-auto grid max-w-md grid-cols-3 items-end">
            {tabs.map((item) => (
              <NavLink key={item.to} to={item.to} end={item.end} className="relative flex h-[50px] flex-col items-center justify-end gap-0.5 pb-1 text-[10.5px] font-semibold">
                {({ isActive }) => (
                  <motion.span whileTap={{ scale: 0.86 }} className={clsx("relative flex flex-col items-center gap-0.5", isActive ? "text-clay-600" : "text-ink-400")}>
                    <span className="relative [&>svg]:h-[22px] [&>svg]:w-[22px]">
                      {item.icon}
                      {!!item.count && <span className="absolute -right-2 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-clay-500 px-1 text-[10px] font-bold leading-none text-white">{item.count > 9 ? "9+" : item.count}</span>}
                    </span>
                    {item.label}
                  </motion.span>
                )}
              </NavLink>
            ))}
          </div>
        </nav>
      </div>
      <NewTripDialog open={newTrip} onOpenChange={setNewTrip} />
    </div>
  );
}
