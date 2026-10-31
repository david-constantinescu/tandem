import * as Popover from "@radix-ui/react-popover";
import { clsx } from "clsx";
import {
  Bell, CheckCheck, Compass, Globe, Home, Inbox, LogOut, Map, MessageCircle, Settings, ShieldCheck, Sparkles,
} from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { motion } from "motion/react";
import { spring } from "@/components/motion";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { relativeTime } from "@/lib/format";
import { t } from "@/lib/i18n";
import { keys, useApprovals, useInbox, useNotifications } from "@/lib/queries";

export function Logo({ className }: { className?: string }) {
  return (
    <Link to="/" className={clsx("flex items-center gap-2.5", className)} aria-label="Tandem home">
      <svg viewBox="0 0 64 64" className="h-8 w-8" aria-hidden>
        <rect width="64" height="64" rx="16" fill="#14363a" />
        <circle cx="25" cy="32" r="11" fill="none" stroke="#f3e9dc" strokeWidth="5" />
        <circle cx="39" cy="32" r="11" fill="none" stroke="#e08a5b" strokeWidth="5" />
      </svg>
      <span className="display text-[21px] font-semibold tracking-tight text-ink-900">Tandem</span>
    </Link>
  );
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

function IconLink({ to, label, children, badge }: { to: string; label: string; children: ReactNode; badge?: boolean }) {
  return (
    <Link to={to} aria-label={label} className="relative flex h-11 w-11 items-center justify-center rounded-full text-ink-600 transition active:scale-90 active:bg-sand-100 lg:hidden [&>svg]:h-[21px] [&>svg]:w-[21px]">
      {children}
      {badge && <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-clay-500 ring-2 ring-paper" />}
    </Link>
  );
}

function Notifications() {
  const { data } = useNotifications();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const unread = data?.meta?.unread ?? 0;
  const items = data?.data ?? [];
  const markAll = async () => {
    await api.post("/notifications/read-all");
    qc.invalidateQueries({ queryKey: keys.notifications });
  };
  return (
    <Popover.Root>
      <Popover.Trigger className="relative flex h-11 w-11 items-center justify-center rounded-full text-ink-600 transition hover:bg-sand-100 hover:text-ink-800 active:scale-90" aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`}>
        <Bell className="h-5 w-5" />
        {unread > 0 && <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-clay-500 ring-2 ring-paper" />}
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content align="end" sideOffset={8} collisionPadding={12} className="z-50 w-[min(94vw,380px)] rounded-[22px] border border-sand-200 bg-white p-2 shadow-[var(--shadow-float)] data-[state=open]:animate-[fade-in_.18s_ease-out]">
          <div className="flex items-center justify-between px-2 py-1.5">
            <p className="text-[13px] font-semibold">Notifications</p>
            {unread > 0 && (
              <button onClick={markAll} className="flex items-center gap-1 text-[12px] text-lagoon-600 hover:underline">
                <CheckCheck className="h-3.5 w-3.5" /> Mark all read
              </button>
            )}
          </div>
          <div className="max-h-[60vh] overflow-y-auto">
            {items.length === 0 && <p className="px-3 py-8 text-center text-[13px] text-ink-400">You're all caught up.</p>}
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
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const inbox = useInbox();
  const approvals = useApprovals("awaiting_approval");
  const reviewCount = (inbox.data?.data ?? []).filter((d) => d.status === "awaiting_review").length;
  const approvalCount = approvals.data?.length ?? 0;
  const headerRef = useRef<HTMLElement>(null);
  // Expose the header height so sticky section headers can sit right below it.
  useEffect(() => {
    const el = headerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => document.documentElement.style.setProperty("--hdr", `${el.offsetHeight}px`));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const tabs = [
    { to: "/", icon: <Home />, label: t("nav.home"), end: true },
    { to: "/trips", icon: <Map />, label: t("nav.trips") },
    { to: "/inbox", icon: <Inbox />, label: t("nav.inbox"), count: reviewCount },
    { to: "/discover", icon: <Compass />, label: t("nav.discover") },
    { to: "/assistant", icon: <MessageCircle />, label: t("nav.assistant") },
  ];

  return (
    <div className="min-h-dvh lg:flex">
      <aside className="hidden w-[248px] shrink-0 flex-col border-r border-sand-200/70 bg-sand-50/80 px-4 py-6 lg:sticky lg:top-0 lg:flex lg:h-screen">
        <Logo className="px-2" />
        <nav className="mt-8 flex flex-col gap-1" aria-label="Main">
          <NavItem to="/" end icon={<Home />} label={t("nav.home")} />
          <NavItem to="/trips" icon={<Map />} label={t("nav.trips")} />
          <NavItem to="/inbox" icon={<Inbox />} label={t("nav.inbox")} count={reviewCount} />
          <NavItem to="/discover" icon={<Compass />} label={t("nav.discover")} />
          <NavItem to="/websites" icon={<Globe />} label={t("nav.websites")} />
          <NavItem to="/assistant" icon={<MessageCircle />} label={t("nav.assistant")} />
          <NavItem to="/approvals" icon={<ShieldCheck />} label={t("nav.approvals")} count={approvalCount} />
        </nav>
        <div className="mt-auto flex flex-col gap-1">
          <NavItem to="/settings" icon={<Settings />} label={t("nav.settings")} />
          <div className="mt-3 flex items-center gap-3 rounded-xl px-3 py-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-lagoon-900 text-[13px] font-semibold text-white">
              {(user?.display_name || user?.email || "?").slice(0, 1).toUpperCase()}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[13px] font-medium text-ink-800">{user?.display_name || "Traveller"}</span>
              <span className="block truncate text-[11.5px] text-ink-400">{user?.is_demo ? "Demo workspace" : user?.email}</span>
            </span>
            <button onClick={async () => { await logout(); navigate("/login"); }} className="rounded-lg p-1.5 text-ink-400 hover:bg-white hover:text-ink-700" aria-label="Sign out">
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header ref={headerRef} className="glass safe-top sticky top-0 z-30 border-x-0 border-t-0 border-b-sand-200/50 lg:border-none lg:bg-transparent lg:backdrop-blur-none">
          {user?.is_demo && (
            <div className="flex items-center justify-center gap-2 bg-lagoon-900 px-4 py-1.5 text-center text-[12px] text-lagoon-50">
              <Sparkles className="h-3.5 w-3.5 shrink-0 text-apricot" />
              <span className="sm:hidden">Demo · fictional trips, simulated bookings</span>
              <span className="hidden sm:inline">{t("demo.banner")}</span>
            </div>
          )}
          <div className="flex h-[52px] items-center justify-between px-3 lg:h-auto lg:justify-end lg:px-8 lg:pt-5">
            <Logo className="pl-1 lg:hidden" />
            <div className="flex items-center">
              <IconLink to="/websites" label="Book on websites"><Globe /></IconLink>
              <IconLink to="/approvals" label={`Approvals${approvalCount ? `, ${approvalCount} waiting` : ""}`} badge={approvalCount > 0}><ShieldCheck /></IconLink>
              <Notifications />
              <IconLink to="/settings" label="Settings"><Settings /></IconLink>
            </div>
          </div>
        </header>
        <main className="mx-auto w-full max-w-[1180px] flex-1 px-4 pb-36 pt-5 sm:px-6 lg:px-10 lg:pb-14 lg:pt-2">{children}</main>
      </div>

      <nav aria-label="Main mobile" className="fixed inset-x-0 bottom-0 z-40 px-3 pb-[max(env(safe-area-inset-bottom),12px)] lg:hidden">
        <div className="glass mx-auto grid max-w-md grid-cols-5 rounded-[28px] p-1.5 shadow-[var(--shadow-float)]">
          {tabs.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} className="relative flex h-[54px] flex-col items-center justify-center gap-0.5 rounded-[22px] text-[10.5px] font-semibold">
              {({ isActive }) => (
                <>
                  {isActive && <motion.span layoutId="tab-pill" transition={spring} className="absolute inset-0 rounded-[22px] bg-ink-900" />}
                  <motion.span whileTap={{ scale: 0.86 }} className={clsx("relative z-10 flex flex-col items-center gap-0.5", isActive ? "text-white" : "text-ink-500")}>
                    <span className="[&>svg]:h-[21px] [&>svg]:w-[21px]">{item.icon}</span>
                    {item.label}
                  </motion.span>
                  {!!item.count && <span className="absolute right-[18%] top-1.5 z-10 h-2 w-2 rounded-full bg-clay-500 ring-2 ring-white" />}
                </>
              )}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  );
}
