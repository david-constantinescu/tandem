import * as Popover from "@radix-ui/react-popover";
import { clsx } from "clsx";
import {
  Bell, CheckCheck, Compass, Globe, Home, Inbox, LogOut, Map, MessageCircle, Settings, ShieldCheck, Sparkles,
} from "lucide-react";
import type { ReactNode } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
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
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) => clsx(
        "group flex items-center gap-3 rounded-xl px-3 py-2.5 text-[14px] font-medium transition-colors",
        isActive ? "bg-white text-ink-900 shadow-[var(--shadow-card)]" : "text-ink-500 hover:bg-white/60 hover:text-ink-800",
      )}
    >
      <span className="text-current [&>svg]:h-[18px] [&>svg]:w-[18px]">{icon}</span>
      <span className="flex-1">{label}</span>
      {!!count && <span className="rounded-full bg-clay-500 px-1.5 text-[11px] font-semibold leading-5 text-white">{count}</span>}
    </NavLink>
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
      <Popover.Trigger className="relative rounded-xl p-2 text-ink-500 hover:bg-sand-100 hover:text-ink-800" aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`}>
        <Bell className="h-5 w-5" />
        {unread > 0 && <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-clay-500 ring-2 ring-paper" />}
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content align="end" sideOffset={8} className="z-50 w-[min(92vw,380px)] rounded-2xl border border-sand-200 bg-white p-2 shadow-[var(--shadow-lift)]">
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

  return (
    <div className="min-h-screen lg:flex">
      <aside className="hidden w-[248px] shrink-0 flex-col border-r border-sand-200/70 bg-sand-50 px-4 py-6 lg:sticky lg:top-0 lg:flex lg:h-screen">
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
        {user?.is_demo && (
          <div className="flex items-center justify-center gap-2 bg-lagoon-900 px-4 py-2 text-center text-[12.5px] text-lagoon-50">
            <Sparkles className="h-3.5 w-3.5 shrink-0 text-clay-100" /> {t("demo.banner")}
          </div>
        )}
        <header className="sticky top-0 z-30 flex items-center justify-between border-b border-sand-200/60 bg-paper/85 px-4 py-2.5 backdrop-blur lg:justify-end lg:border-none lg:bg-transparent lg:px-8 lg:pt-5 lg:backdrop-blur-none">
          <Logo className="lg:hidden" />
          <div className="flex items-center gap-1">
            <Notifications />
            <Link to="/websites" className="rounded-xl p-2 text-ink-500 hover:bg-sand-100 lg:hidden" aria-label="Book on websites"><Globe className="h-5 w-5" /></Link>
            <Link to="/approvals" className="rounded-xl p-2 text-ink-500 hover:bg-sand-100 lg:hidden" aria-label="Approvals"><ShieldCheck className="h-5 w-5" /></Link>
            <Link to="/settings" className="rounded-xl p-2 text-ink-500 hover:bg-sand-100 lg:hidden" aria-label="Settings"><Settings className="h-5 w-5" /></Link>
          </div>
        </header>
        <main className="mx-auto w-full max-w-[1180px] flex-1 px-4 pb-28 pt-4 sm:px-6 lg:px-10 lg:pb-14 lg:pt-2">{children}</main>
      </div>

      <nav className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t border-sand-200 bg-white/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden" aria-label="Main mobile">
        {[
          { to: "/", icon: <Home />, label: t("nav.home"), end: true },
          { to: "/trips", icon: <Map />, label: t("nav.trips") },
          { to: "/inbox", icon: <Inbox />, label: t("nav.inbox"), count: reviewCount },
          { to: "/discover", icon: <Compass />, label: t("nav.discover") },
          { to: "/assistant", icon: <MessageCircle />, label: t("nav.assistant") },
        ].map((item) => (
          <NavLink key={item.to} to={item.to} end={item.end} className={({ isActive }) => clsx("relative flex flex-col items-center gap-0.5 py-2 text-[10.5px] font-medium", isActive ? "text-lagoon-700" : "text-ink-400")}>
            <span className="[&>svg]:h-5 [&>svg]:w-5">{item.icon}</span>
            {item.label}
            {!!item.count && <span className="absolute right-[22%] top-1 h-2 w-2 rounded-full bg-clay-500" />}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
