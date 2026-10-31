import { clsx } from "clsx";
import { AlertTriangle, Bell, CalendarDays, Check, ChevronLeft, ChevronRight, Copy, Database, ExternalLink, Gauge, HardDrive, Languages, Link2, Lock, LogOut, Mail, Moon, ShieldAlert, Sparkles, UserRound } from "lucide-react";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link, NavLink, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { LanguageSwitch } from "@/components/LanguageSwitch";
import { ThemeSwitch } from "@/components/ThemeSwitch";
import { Badge, Button, ErrorNote, Field, InfoNote, PageHeader, PageLoader, Toggle, useStatusLabel } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { num, relativeTime } from "@/lib/format";
import { useT, type Key } from "@/lib/i18n";
import type { ProviderCaps, User } from "@/lib/types";

const SECTIONS = [
  ["profile", "settings.sec.profile", UserRound, "bg-lagoon-600"], ["calendar", "settings.sec.calendar", CalendarDays, "bg-clay-600"],
  ["notifications", "settings.sec.notifications", Bell, "bg-rose-ink"], ["connections", "settings.sec.connections", Link2, "bg-lagoon-500"],
  ["ai", "settings.sec.ai", Sparkles, "bg-violet-ink"], ["usage", "settings.sec.usage", Gauge, "bg-clay-500"],
  ["storage", "settings.sec.storage", HardDrive, "bg-ink-500"], ["security", "settings.sec.security", Lock, "bg-ink-800"], ["data", "settings.sec.data", Database, "bg-amber-ink"],
] as const satisfies readonly (readonly [string, Key, unknown, string])[];

type Settings = {
  profile: User;
  preferences: { interests: string[]; pace: string; budget: string; accessibility_needs: string; default_currency: string; notification_prefs: Record<string, boolean>; retain_original_documents: boolean; auto_organize: boolean };
  ai: { mode: string; allowed_providers: Record<string, boolean>; preferred_provider: string | null; consent_recorded_at: string | null };
  limits: { max_upload_mb: number; max_files_per_upload: number };
};

export default function SettingsPage() {
  const { section: picked } = useParams();
  const section = picked ?? "profile";
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { t } = useT();
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => api.get<Settings>("/settings") });
  if (settings.isLoading || !settings.data) return <PageLoader />;
  const s = settings.data;
  const sectionKey = SECTIONS.find(([k]) => k === section)?.[1];
  const label = sectionKey ? t(sectionKey) : t("nav.settings");
  return (
    <div>
      {/* Phones get an iOS-style grouped list first; a section opens as its own screen. */}
      <div className={clsx("lg:hidden", picked && "hidden")}>
        <PageHeader title={t("nav.settings")} />
        <div className="card mb-5 flex items-center gap-3 rounded-[22px] p-4">
          <span className="flex h-12 w-12 items-center justify-center rounded-full bg-lagoon-900 text-[18px] font-semibold text-white">{(user?.display_name || user?.email || "?").slice(0, 1).toUpperCase()}</span>
          <span className="min-w-0">
            <span className="block truncate text-[16px] font-semibold">{user?.display_name || t("common.traveller")}</span>
            <span className="block truncate text-[13px] text-ink-400">{user?.is_demo ? t("demo.workspace") : user?.email}</span>
          </span>
        </div>
        <div className="card mb-5 flex min-h-[56px] items-center gap-3 rounded-[22px] px-4">
          <span className="flex h-8 w-8 items-center justify-center rounded-[9px] bg-lagoon-900 text-white"><Languages className="h-[17px] w-[17px]" /></span>
          <span className="flex-1 text-[16px] text-ink-900">{t("lang.label")}</span>
          <LanguageSwitch />
        </div>
        <div className="card mb-5 -mt-3 flex min-h-[56px] items-center gap-3 rounded-[22px] px-4">
          <span className="flex h-8 w-8 items-center justify-center rounded-[9px] bg-ink-700 text-white"><Moon className="h-[17px] w-[17px]" /></span>
          <span className="flex-1 text-[16px] text-ink-900">{t("theme.label")}</span>
          <ThemeSwitch />
        </div>
        <ul className="card divide-y divide-sand-100 overflow-hidden rounded-[22px]">
          {SECTIONS.map(([key, name, Icon, tint]) => (
            <li key={key}>
              <Link to={`/settings/${key}`} className="flex min-h-[52px] items-center gap-3 px-4 active:bg-sand-50">
                <span className={clsx("flex h-8 w-8 items-center justify-center rounded-[9px] text-white", tint)}><Icon className="h-[17px] w-[17px]" /></span>
                <span className="flex-1 text-[16px] text-ink-900">{t(name)}</span>
                <ChevronRight className="h-4 w-4 text-ink-300" />
              </Link>
            </li>
          ))}
        </ul>
        <button onClick={async () => { await logout(); navigate("/login"); }} className="card mt-5 flex min-h-[52px] w-full items-center justify-center gap-2 rounded-[22px] text-[16px] font-medium text-rose-ink active:bg-sand-50">
          <LogOut className="h-[18px] w-[18px]" /> {t("auth.signOut")}
        </button>
      </div>

      <div className={clsx(!picked && "hidden lg:block")}>
        <Link to="/settings" className="-ml-1 inline-flex min-h-11 items-center gap-1 pr-3 text-[15px] text-lagoon-600 lg:hidden"><ChevronLeft className="h-5 w-5" />{t("nav.settings")}</Link>
        <h1 className="display mb-5 text-[30px] leading-tight lg:hidden">{label}</h1>
        <div className="hidden lg:block"><PageHeader title={t("nav.settings")} /></div>
      <div className="grid grid-cols-1 gap-8 lg:grid-cols-[200px_minmax(0,1fr)]">
        <nav className="hidden flex-col gap-1 lg:flex" aria-label={t("nav.settings")}>
          {SECTIONS.map(([key, name]) => (
            <NavLink key={key} to={`/settings/${key}`} className={({ isActive }) => clsx("whitespace-nowrap rounded-xl px-3 py-2 text-[13.5px] font-medium",
              isActive || (key === "profile" && !picked) ? "bg-white text-ink-900 shadow-[var(--shadow-card)]" : "text-ink-500 hover:text-ink-800")}>{t(name)}</NavLink>
          ))}
        </nav>
        <div className="max-w-2xl">
          {section === "profile" && <Profile s={s} />}
          {section === "ai" && <AISection />}
          {section === "usage" && <Usage />}
          {section === "connections" && <Connections />}
          {section === "calendar" && <CalendarSection />}
          {section === "notifications" && <NotificationPrefs s={s} />}
          {section === "storage" && <Storage s={s} />}
          {section === "security" && <Security />}
          {section === "data" && <DataSection />}
        </div>
      </div>
      </div>
    </div>
  );
}

function Panel({ title, description, children }: { title: string; description?: ReactNode; children: ReactNode }) {
  return (
    <section className="card rounded-[22px] p-4 sm:p-6">
      <h2 className="text-[17px] font-semibold">{title}</h2>
      {description && <p className="mt-1 text-[13.5px] text-ink-500">{description}</p>}
      <div className="mt-5">{children}</div>
    </section>
  );
}

function useSave() {
  const qc = useQueryClient();
  const toast = useToast();
  const { refresh } = useAuth();
  const { t } = useT();
  return async (fn: () => Promise<unknown>, msg = t("common.saved")) => {
    try {
      await fn();
      qc.invalidateQueries({ queryKey: ["settings"] });
      refresh();
      toast(msg, "success");
    } catch (e) {
      toast(errorMessage(e), "error");
    }
  };
}

function Profile({ s }: { s: Settings }) {
  const [p, setP] = useState({ display_name: s.profile.display_name, home_city: s.profile.home_city ?? "", home_airport: s.profile.home_airport ?? "", timezone: s.profile.timezone });
  const [prefs, setPrefs] = useState({ interests: s.preferences.interests.join(", "), pace: s.preferences.pace, budget: s.preferences.budget, accessibility_needs: s.preferences.accessibility_needs, default_currency: s.preferences.default_currency });
  const save = useSave();
  const { t } = useT();
  const zones = (Intl as any).supportedValuesOf ? (Intl as any).supportedValuesOf("timeZone") as string[] : [p.timezone];
  const submit = (e: FormEvent) => {
    e.preventDefault();
    save(async () => {
      await api.patch("/settings/profile", p);
      await api.patch("/settings/preferences", { ...prefs, interests: prefs.interests.split(",").map((x) => x.trim()).filter(Boolean) });
    });
  };
  return (
    <form onSubmit={submit} className="space-y-6">
      <Panel title={t("settings.sec.profile")} description={t("settings.profileHint")}>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label={t("settings.name")} htmlFor="pn"><input id="pn" className="field" value={p.display_name} onChange={(e) => setP({ ...p, display_name: e.target.value })} /></Field>
          <Field label={t("auth.email")}><input className="field" value={s.profile.email} disabled /></Field>
          <Field label={t("settings.homeCity")} htmlFor="ph"><input id="ph" className="field" value={p.home_city} onChange={(e) => setP({ ...p, home_city: e.target.value })} /></Field>
          <Field label={t("settings.homeAirport")} htmlFor="pa"><input id="pa" className="field uppercase" maxLength={4} value={p.home_airport} onChange={(e) => setP({ ...p, home_airport: e.target.value })} /></Field>
          <Field label={t("event.timezone")} htmlFor="ptz">
            <select id="ptz" className="field" value={p.timezone} onChange={(e) => setP({ ...p, timezone: e.target.value })}>{["UTC", ...zones].map((z) => <option key={z} value={z}>{z}</option>)}</select>
          </Field>
          <div className="flex flex-wrap gap-6">
            <div><p className="label">{t("lang.label")}</p><LanguageSwitch /></div>
            <div><p className="label">{t("theme.label")}</p><ThemeSwitch /></div>
          </div>
        </div>
      </Panel>
      <Panel title={t("settings.prefs")} description={t("settings.prefsHint")}>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2"><Field label={t("settings.interests")} htmlFor="pi" hint={t("settings.interestsHint")}><input id="pi" className="field" value={prefs.interests} onChange={(e) => setPrefs({ ...prefs, interests: e.target.value })} /></Field></div>
          <Field label={t("settings.pace")} htmlFor="pp"><select id="pp" className="field" value={prefs.pace} onChange={(e) => setPrefs({ ...prefs, pace: e.target.value })}><option value="relaxed">{t("settings.pace.relaxed")}</option><option value="balanced">{t("settings.pace.balanced")}</option><option value="packed">{t("settings.pace.packed")}</option></select></Field>
          <Field label={t("settings.budget")} htmlFor="pb"><select id="pb" className="field" value={prefs.budget} onChange={(e) => setPrefs({ ...prefs, budget: e.target.value })}><option value="budget">{t("settings.budget.budget")}</option><option value="moderate">{t("settings.budget.moderate")}</option><option value="premium">{t("settings.budget.premium")}</option></select></Field>
          <Field label={t("res.currency")} htmlFor="pc"><input id="pc" maxLength={3} className="field uppercase" value={prefs.default_currency} onChange={(e) => setPrefs({ ...prefs, default_currency: e.target.value.toUpperCase() })} /></Field>
          <div className="sm:col-span-2"><Field label={t("settings.accessibility")} htmlFor="pac"><input id="pac" className="field" value={prefs.accessibility_needs} onChange={(e) => setPrefs({ ...prefs, accessibility_needs: e.target.value })} /></Field></div>
        </div>
      </Panel>
      <div className="flex justify-end"><Button type="submit">{t("common.saveChanges")}</Button></div>
    </form>
  );
}

type AIInfo = {
  settings: Settings["ai"];
  providers: { provider: string; configured: boolean; original_file_processing: boolean; roles: Record<string, { model: string; free_tier: boolean; id_verified: boolean; usable: boolean; inputs: string[]; notes: string[] }>; status: { state: string; cooldown_until: string | null } | null }[];
  paid_models_allowed: boolean;
  demo_external_ai: boolean;
};

const PROVIDER_NAMES: Record<string, string> = { gemini: "Google Gemini", zai: "Z.ai (GLM)", groq: "Groq" };
const PROVIDER_ROLE: Record<string, Key> = { gemini: "ai.role.gemini", zai: "ai.role.zai", groq: "ai.role.groq" };

function AISection() {
  const info = useQuery({ queryKey: ["settings", "ai"], queryFn: () => api.get<AIInfo>("/settings/ai") });
  const [mode, setMode] = useState("off");
  const [allowed, setAllowed] = useState<Record<string, boolean>>({});
  const [ack, setAck] = useState(false);
  const save = useSave();
  const qc = useQueryClient();
  const { t } = useT();
  useEffect(() => { if (info.data) { setMode(info.data.settings.mode); setAllowed(info.data.settings.allowed_providers); } }, [info.data]);
  if (!info.data) return <PageLoader />;
  const rank: Record<string, number> = { off: 0, text_only: 1, full: 2 };
  const needsAck = rank[mode] > rank[info.data.settings.mode];
  const submit = () => save(async () => {
    await api.put("/settings/ai", { mode, allowed_providers: allowed, acknowledge_privacy: ack });
    setAck(false);
    qc.invalidateQueries({ queryKey: ["settings", "ai"] });
  });
  const modes = [
    { key: "off", title: t("ai.mode.off"), body: t("ai.mode.offBody") },
    { key: "text_only", title: t("ai.mode.text"), body: t("ai.mode.textBody") },
    { key: "full", title: t("ai.mode.full"), body: t("ai.mode.fullBody") },
  ];
  return (
    <div className="space-y-6">
      <Panel title={t("ai.title")} description={t("ai.hint")}>
        {info.data.demo_external_ai && <div className="mb-4"><InfoNote tone="violet">{t("ai.demo")}</InfoNote></div>}
        <div className="space-y-2" role="radiogroup">
          {modes.map((m) => (
            <label key={m.key} className={clsx("flex cursor-pointer gap-3 rounded-xl border p-3.5 transition", mode === m.key ? "border-lagoon-500 bg-lagoon-50/50" : "border-sand-200 hover:border-sand-300")}>
              <input type="radio" name="aimode" className="mt-1 accent-lagoon-600" checked={mode === m.key} onChange={() => setMode(m.key)} />
              <span><span className="block text-[14px] font-medium">{m.title}</span><span className="mt-0.5 block text-[13px] text-ink-500">{m.body}</span></span>
            </label>
          ))}
        </div>
        {needsAck && (
          <div className="mt-5 space-y-3 rounded-xl border border-amber-soft bg-amber-soft/50 p-4 text-[13px] text-amber-ink">
            <p className="flex gap-2 font-medium"><ShieldAlert className="h-4 w-4 shrink-0" /> {t("ai.before")}</p>
            <ul className="list-disc space-y-1 pl-5">
              <li>{t("ai.warn1")}</li>
              <li>{t("ai.warn2")}</li>
              <li>{t("ai.warn3")}</li>
              <li>{info.data.paid_models_allowed ? t("ai.warn4paid") : t("ai.warn4")}</li>
            </ul>
            <label className="flex items-center gap-2 font-medium"><input type="checkbox" className="accent-lagoon-600" checked={ack} onChange={(e) => setAck(e.target.checked)} /> {t("ai.ack")}</label>
          </div>
        )}
        <div className="mt-5 flex justify-end"><Button onClick={submit} disabled={needsAck && !ack}>{t("ai.save")}</Button></div>
      </Panel>

      <Panel title={t("ai.providers")} description={t("ai.providersHint")}>
        <div className="space-y-4">
          {info.data.providers.map((p) => (
            <div key={p.provider} className="rounded-xl border border-sand-200 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-[14.5px] font-semibold">{PROVIDER_NAMES[p.provider]}</p>
                <div className="flex items-center gap-2">
                  {p.configured ? <Badge tone="lagoon">{t("ai.configured")}</Badge> : <Badge>{t("ai.notConfigured")}</Badge>}
                  {p.status?.cooldown_until && new Date(p.status.cooldown_until) > new Date() && <Badge tone="amber">{t("ai.quota")}</Badge>}
                  <Toggle checked={allowed[p.provider] !== false} onChange={(v) => setAllowed({ ...allowed, [p.provider]: v })} label={t("ai.allow", { name: PROVIDER_NAMES[p.provider] })} hideLabel />
                </div>
              </div>
              <p className="mt-1 text-[13px] text-ink-500">{PROVIDER_ROLE[p.provider] ? t(PROVIDER_ROLE[p.provider]) : ""}</p>
              <ul className="mt-3 space-y-1 text-[12.5px] text-ink-500">
                {Object.entries(p.roles).map(([role, r]) => (
                  <li key={role} className="flex flex-wrap items-center gap-2">
                    <span className="w-20 text-ink-400">{role}</span>
                    <code className="rounded bg-sand-50 px-1.5 py-0.5 text-[12px] text-ink-700">{r.model}</code>
                    {r.free_tier ? <Badge tone="lagoon">{t("ai.free")}</Badge> : <Badge tone="amber">{t("ai.paid")}</Badge>}
                    {!r.usable && <Badge tone="neutral">{t("ai.blocked")}</Badge>}
                    {!r.id_verified && <span className="text-ink-400">{t("ai.runtime")}</span>}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <p className="mt-4 text-[12.5px] text-ink-400">{t("ai.groqNote")}</p>
      </Panel>
    </div>
  );
}

function Usage() {
  const usage = useQuery({ queryKey: ["settings", "usage"], queryFn: () => api.get<{ summary: { provider: string; model: string; status: string; requests: number; input_tokens: number; output_tokens: number; estimated_cost_usd: number }[]; recent: { provider: string; model: string; task: string; status: string; input_tokens: number; output_tokens: number; latency_ms: number; error_code: string | null; created_at: string }[]; paid_models_allowed: boolean }>("/settings/usage") });
  const { t } = useT();
  if (!usage.data) return <PageLoader />;
  const totals = usage.data.summary.reduce((acc, r) => ({ req: acc.req + r.requests, tin: acc.tin + r.input_tokens, tout: acc.tout + r.output_tokens, cost: acc.cost + r.estimated_cost_usd }), { req: 0, tin: 0, tout: 0, cost: 0 });
  return (
    <div className="space-y-6">
      <Panel title={t("usage.title")} description={usage.data.paid_models_allowed ? t("usage.paid") : t("usage.free")}>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[[t("usage.requests"), num(totals.req)], [t("usage.input"), num(totals.tin)], [t("usage.output"), num(totals.tout)], [t("usage.cost"), `$${totals.cost.toFixed(4)}`]].map(([k, v]) => (
            <div key={k as string} className="rounded-xl bg-sand-50 p-3"><p className="text-[12px] text-ink-400">{k}</p><p className="mt-1 text-[18px] font-semibold">{v}</p></div>
          ))}
        </div>
      </Panel>
      <Panel title={t("usage.recent")}>
        {usage.data.recent.length === 0 ? <p className="text-[13.5px] text-ink-400">{t("usage.none")}</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-[12.5px]">
              <thead className="text-left text-ink-400"><tr><th className="pb-2 font-medium">{t("usage.when")}</th><th className="pb-2 font-medium">{t("res.provider")}</th><th className="pb-2 font-medium">{t("usage.task")}</th><th className="pb-2 font-medium">{t("event.status")}</th><th className="pb-2 text-right font-medium">{t("usage.tokens")}</th></tr></thead>
              <tbody>
                {usage.data.recent.map((r, i) => (
                  <tr key={i} className="border-t border-sand-100">
                    <td className="py-2 pr-3 text-ink-500">{relativeTime(r.created_at)}</td>
                    <td className="py-2 pr-3">{r.provider} <span className="text-ink-400">{r.model}</span></td>
                    <td className="py-2 pr-3">{r.task.replace(/_/g, " ")}</td>
                    <td className="py-2 pr-3"><Badge tone={r.status === "ok" || r.status === "cached" ? "lagoon" : r.status === "rate_limited" ? "amber" : "rose"}>{r.status}{r.error_code ? ` · ${r.error_code}` : ""}</Badge></td>
                    <td className="py-2 text-right tabular-nums">{r.input_tokens + r.output_tokens}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}

function Connections() {
  const [params] = useSearchParams();
  const data = useQuery({ queryKey: ["integrations"], queryFn: () => api.get<{ gmail: { available: boolean; status: string; reason: string | null; account_email: string | null; scopes: string[]; last_sync_at: string | null; error: string | null }; travel_providers: ProviderCaps[] }>("/integrations") });
  const toast = useToast();
  const { t } = useT();
  const statusLabel = useStatusLabel();
  const [deleteImported, setDeleteImported] = useState(false);
  if (!data.data) return <PageLoader />;
  const g = data.data.gmail;
  const connect = async () => {
    try { window.location.href = (await api.post<{ authorization_url: string }>("/integrations/gmail/connect")).authorization_url; } catch (e) { toast(errorMessage(e), "error"); }
  };
  const disconnect = async () => {
    if (!confirm(t("gmail.disconnectConfirm"))) return;
    await api.post("/integrations/gmail/disconnect", { delete_imported: deleteImported });
    data.refetch();
    toast(t("gmail.disconnected"), "success");
  };
  return (
    <div className="space-y-6">
      {params.get("gmail") === "connected" && <InfoNote tone="lagoon" icon={<Check className="h-4 w-4" />}>{t("gmail.connectedNow")}</InfoNote>}
      {params.get("gmail") === "error" && <ErrorNote>{t("gmail.failed", { code: params.get("code") ?? "" })}</ErrorNote>}
      <Panel title="Gmail" description={t("gmail.hint")}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-clay-50 text-clay-600"><Mail className="h-5 w-5" /></span>
            <div>
              <p className="text-[14px] font-medium">{g.status === "connected" ? g.account_email : t("gmail.notConnected")}</p>
              <p className="text-[12.5px] text-ink-400">{g.status === "connected" ? t("gmail.lastChecked", { when: g.last_sync_at ? relativeTime(g.last_sync_at) : t("gmail.never") }) : g.reason ?? t("gmail.connectHint")}</p>
            </div>
          </div>
          {g.status === "connected" ? <Button variant="danger" onClick={disconnect}>{t("gmail.disconnect")}</Button> : <Button onClick={connect} disabled={!g.available}>{t("gmail.connect")}</Button>}
        </div>
        {g.status === "connected" && (
          <label className="mt-4 flex items-center gap-2 text-[13px] text-ink-600"><input type="checkbox" className="accent-lagoon-600" checked={deleteImported} onChange={(e) => setDeleteImported(e.target.checked)} /> {t("gmail.deleteImported")}</label>
        )}
        {g.error && <div className="mt-3"><ErrorNote>{g.error}</ErrorNote></div>}
      </Panel>
      <Panel title={t("providers.title")} description={t("providers.hint")}>
        <ul className="space-y-3">
          {data.data.travel_providers.map((p) => (
            <li key={p.key} className="rounded-xl border border-sand-200 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-[14px] font-semibold">{p.name}</p>
                <Badge tone={p.state === "simulated_demo" ? "violet" : ["search_only", "redirect_only", "booking_enabled"].includes(p.state) ? "lagoon" : p.state === "awaiting_partner_approval" ? "amber" : "neutral"}>{statusLabel(p.state)}</Badge>
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5 text-[12px]">
                {(["search", "availability", "booking", "redirect"] as const).map((c) => <Badge key={c} tone={p[c] ? "lagoon" : "neutral"}>{p[c] ? <Check className="h-3 w-3" /> : null}{t(`providers.cap.${c}`)}</Badge>)}
              </div>
              <ul className="mt-2 space-y-1 text-[12.5px] text-ink-500">{p.notes.map((n) => <li key={n}>{n}</li>)}</ul>
              {p.docs_url && <a href={p.docs_url} target="_blank" rel="noopener noreferrer" className="mt-2 inline-flex items-center gap-1 text-[12.5px] text-lagoon-600 hover:underline">{t("providers.docs")} <ExternalLink className="h-3 w-3" /></a>}
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}

type CalendarSub = { active: boolean; url: string | null; webcal_url: string | null; created_at: string | null };

function CalendarSection() {
  const sub = useQuery({ queryKey: ["calendar-subscription"], queryFn: () => api.get<CalendarSub>("/calendar/subscription") });
  const qc = useQueryClient();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const { t } = useT();
  if (!sub.data) return <PageLoader />;
  const s = sub.data;
  const change = async (action: "create" | "reset" | "off") => {
    if (action === "reset" && !confirm(t("cal.resetConfirm"))) return;
    if (action === "off" && !confirm(t("cal.offConfirm"))) return;
    setBusy(true);
    try {
      const next = action === "off" ? await api.del<CalendarSub>("/calendar/subscription") : await api.post<CalendarSub>("/calendar/subscription");
      qc.setQueryData(["calendar-subscription"], next);
      toast(action === "off" ? t("cal.offDone") : action === "reset" ? t("cal.resetDone") : t("cal.ready"), "success");
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(false);
    }
  };
  const copy = async () => {
    try { await navigator.clipboard.writeText(s.url!); toast(t("cal.copied"), "success"); } catch { toast(t("cal.copyFailed"), "error"); }
  };
  return (
    <div className="space-y-6">
      <Panel title={t("cal.title")} description={t("cal.hint")}>
        {!s.active ? (
          <div className="space-y-4">
            <ul className="space-y-2 text-[13.5px] text-ink-600">
              <li className="flex gap-2"><Check className="mt-0.5 h-4 w-4 shrink-0 text-lagoon-600" />{t("cal.point1")}</li>
              <li className="flex gap-2"><Check className="mt-0.5 h-4 w-4 shrink-0 text-lagoon-600" />{t("cal.point2")}</li>
            </ul>
            <Button onClick={() => change("create")} loading={busy} icon={<CalendarDays className="h-4 w-4" />}>{t("cal.create")}</Button>
          </div>
        ) : (
          <div className="space-y-5">
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <a href={s.webcal_url!} className="flex min-h-12 items-center justify-center gap-2 rounded-xl bg-lagoon-900 px-4 text-[14.5px] font-medium text-white active:scale-[0.98]">
                <CalendarDays className="h-4 w-4" />Apple Calendar
              </a>
              <a href={`https://calendar.google.com/calendar/r?cid=${encodeURIComponent(s.webcal_url!)}`} target="_blank" rel="noopener noreferrer"
                className="flex min-h-12 items-center justify-center gap-2 rounded-xl border border-sand-200 bg-white px-4 text-[14.5px] font-medium text-ink-800 hover:bg-sand-50 active:scale-[0.98]">
                Google Calendar <ExternalLink className="h-3.5 w-3.5 text-ink-400" />
              </a>
            </div>
            <div>
              <p className="eyebrow mb-2">{t("cal.orCopy")}</p>
              <div className="flex gap-2">
                <input readOnly value={s.url!} onFocus={(e) => e.currentTarget.select()} aria-label={t("cal.linkLabel")}
                  className="h-11 min-w-0 flex-1 truncate rounded-xl border border-sand-200 bg-sand-50 px-3 text-[16px] text-ink-600 sm:text-[13.5px]" />
                <Button variant="secondary" onClick={copy} icon={<Copy className="h-4 w-4" />} className="shrink-0">{t("common.copy")}</Button>
              </div>
              <p className="mt-2 text-[12.5px] text-ink-400">{t("cal.refreshNote")}</p>
            </div>
            <InfoNote tone="amber" icon={<ShieldAlert className="h-4 w-4" />}>{t("cal.privacy")}</InfoNote>
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-sand-100 pt-4">
              <p className="text-[12.5px] text-ink-400">{t("cal.created", { when: s.created_at ? relativeTime(s.created_at) : "" })}</p>
              <div className="flex gap-2">
                <Button variant="secondary" size="sm" onClick={() => change("reset")} disabled={busy}>{t("cal.reset")}</Button>
                <Button variant="danger" size="sm" onClick={() => change("off")} disabled={busy}>{t("cal.off")}</Button>
              </div>
            </div>
          </div>
        )}
      </Panel>
      <p className="px-1 text-[13px] text-ink-500">{t("cal.oneOff")}</p>
    </div>
  );
}

const NOTE_KINDS = ["document_processed", "document_failed", "reservation_detected", "trip_created", "reservation_changed", "conflict_detected",
  "upcoming_event", "cancellation_deadline", "approval_required", "booking_result", "integration_failure"];

function NotificationPrefs({ s }: { s: Settings }) {
  const [prefs, setPrefs] = useState(s.preferences.notification_prefs);
  const save = useSave();
  const { t } = useT();
  return (
    <Panel title={t("notifPrefs.title")}>
      <div className="divide-y divide-sand-100">
        {NOTE_KINDS.map((k) => (
          <Toggle key={k} label={t(`notifPrefs.${k}` as Key)} checked={prefs[k] !== false} onChange={(v) => {
            const next = { ...prefs, [k]: v };
            setPrefs(next);
            save(() => api.patch("/settings/preferences", { notification_prefs: { [k]: v } }));
          }} />
        ))}
      </div>
    </Panel>
  );
}

function Storage({ s }: { s: Settings }) {
  const save = useSave();
  const { t } = useT();
  return (
    <div className="space-y-6">
      <Panel title={t("storage.title")} description={t("storage.hint", { mb: s.limits.max_upload_mb })}>
        <Toggle label={t("storage.keep")} description={t("storage.keepHint")} checked={s.preferences.retain_original_documents}
          onChange={(v) => save(() => api.patch("/settings/preferences", { retain_original_documents: v }))} />
        <Toggle label={t("storage.auto")} description={t("storage.autoHint")}
          checked={s.preferences.auto_organize} onChange={(v) => save(() => api.patch("/settings/preferences", { auto_organize: v }))} />
      </Panel>
    </div>
  );
}

function Security() {
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: () => api.get<{ id: string; user_agent: string; created_at: string; last_seen_at: string; current: boolean }[]>("/settings/sessions") });
  const [cur, setCur] = useState("");
  const [next, setNext] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const { logout } = useAuth();
  const navigate = useNavigate();
  const { t } = useT();
  const change = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    try { await api.post("/settings/password", { current_password: cur, new_password: next }); await logout(); navigate("/login"); } catch (e2) { setErr(errorMessage(e2)); }
  };
  return (
    <div className="space-y-6">
      <Panel title={t("security.password")} description={t("security.passwordHint")}>
        <form onSubmit={change} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label={t("security.current")} htmlFor="cp"><input id="cp" type="password" required className="field" value={cur} onChange={(e) => setCur(e.target.value)} autoComplete="current-password" /></Field>
          <Field label={t("security.new")} htmlFor="np" hint={t("auth.passwordHint")}><input id="np" type="password" required minLength={10} className="field" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" /></Field>
          {err && <div className="sm:col-span-2"><ErrorNote>{err}</ErrorNote></div>}
          <div className="sm:col-span-2"><Button type="submit">{t("security.update")}</Button></div>
        </form>
      </Panel>
      <Panel title={t("security.sessions")}>
        <ul className="divide-y divide-sand-100">
          {(sessions.data ?? []).map((s) => (
            <li key={s.id} className="flex items-center justify-between gap-3 py-3">
              <div className="min-w-0"><p className="truncate text-[13.5px]">{s.user_agent || t("security.unknownDevice")}</p><p className="text-[12px] text-ink-400">{t("security.active", { when: relativeTime(s.last_seen_at) })}</p></div>
              {s.current ? <Badge tone="lagoon">{t("security.thisDevice")}</Badge> : <Button size="sm" variant="ghost" onClick={async () => { await api.del(`/settings/sessions/${s.id}`); sessions.refetch(); }}>{t("auth.signOut")}</Button>}
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}

function DataSection() {
  const [pw, setPw] = useState("");
  const [confirmText, setConfirmText] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const navigate = useNavigate();
  const { refresh } = useAuth();
  const { t } = useT();
  const del = async (e: FormEvent) => {
    e.preventDefault();
    try { await api.post("/settings/delete-account", { password: pw, confirm: confirmText }); await refresh(); navigate("/login"); } catch (e2) { setErr(errorMessage(e2)); }
  };
  return (
    <div className="space-y-6">
      <Panel title={t("data.export")} description={t("data.exportHint")}>
        <a href="/api/v1/settings/export" className="inline-flex h-10 items-center rounded-xl bg-lagoon-900 px-4 text-[14px] font-medium text-white hover:bg-ink-800">{t("data.download")}</a>
      </Panel>
      <Panel title={t("data.delete")} description={t("data.deleteHint")}>
        <form onSubmit={del} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label={t("auth.password")} htmlFor="dp"><input id="dp" type="password" required className="field" value={pw} onChange={(e) => setPw(e.target.value)} /></Field>
          <Field label={t("data.typeDelete")} htmlFor="dc"><input id="dc" className="field" value={confirmText} onChange={(e) => setConfirmText(e.target.value)} /></Field>
          {err && <div className="sm:col-span-2"><ErrorNote>{err}</ErrorNote></div>}
          <div className="sm:col-span-2"><Button type="submit" variant="danger" icon={<AlertTriangle className="h-4 w-4" />} disabled={confirmText !== "DELETE"}>{t("data.deleteButton")}</Button></div>
        </form>
      </Panel>
      <p className="text-[12.5px] text-ink-400">{t("data.seeAlso")} <Link to="/settings/ai" className="text-lagoon-600 hover:underline">{t("settings.sec.ai")}</Link></p>
    </div>
  );
}
