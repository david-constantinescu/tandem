import { clsx } from "clsx";
import { AlertTriangle, Bell, CalendarDays, Check, Copy, ChevronLeft, ChevronRight, Database, ExternalLink, Gauge, HardDrive, Link2, Lock, LogOut, Mail, ShieldAlert, Sparkles, UserRound } from "lucide-react";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link, NavLink, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge, Button, ErrorNote, Field, InfoNote, PageHeader, PageLoader, Toggle } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { relativeTime } from "@/lib/format";
import type { ProviderCaps, User } from "@/lib/types";

const SECTIONS = [
  ["profile", "Profile", UserRound, "bg-lagoon-600"], ["ai", "AI & privacy", Sparkles, "bg-violet-ink"], ["usage", "API usage", Gauge, "bg-clay-500"],
  ["connections", "Connected accounts", Link2, "bg-lagoon-500"], ["calendar", "Calendar", CalendarDays, "bg-clay-600"],
  ["notifications", "Notifications", Bell, "bg-rose-ink"],
  ["storage", "File storage", HardDrive, "bg-ink-500"], ["security", "Account security", Lock, "bg-ink-800"], ["data", "Your data", Database, "bg-amber-ink"],
] as const;

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
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => api.get<Settings>("/settings") });
  if (settings.isLoading || !settings.data) return <PageLoader />;
  const s = settings.data;
  const label = SECTIONS.find(([k]) => k === section)?.[1] ?? "Settings";
  return (
    <div>
      {/* Phones get an iOS-style grouped list first; a section opens as its own screen. */}
      <div className={clsx("lg:hidden", picked && "hidden")}>
        <PageHeader title="Settings" />
        <div className="card mb-5 flex items-center gap-3 rounded-[22px] p-4">
          <span className="flex h-12 w-12 items-center justify-center rounded-full bg-lagoon-900 text-[18px] font-semibold text-white">{(user?.display_name || user?.email || "?").slice(0, 1).toUpperCase()}</span>
          <span className="min-w-0">
            <span className="block truncate text-[16px] font-semibold">{user?.display_name || "Traveller"}</span>
            <span className="block truncate text-[13px] text-ink-400">{user?.is_demo ? "Demo workspace" : user?.email}</span>
          </span>
        </div>
        <ul className="card divide-y divide-sand-100 overflow-hidden rounded-[22px]">
          {SECTIONS.map(([key, name, Icon, tint]) => (
            <li key={key}>
              <Link to={`/settings/${key}`} className="flex min-h-[52px] items-center gap-3 px-4 active:bg-sand-50">
                <span className={clsx("flex h-8 w-8 items-center justify-center rounded-[9px] text-white", tint)}><Icon className="h-[17px] w-[17px]" /></span>
                <span className="flex-1 text-[16px] text-ink-900">{name}</span>
                <ChevronRight className="h-4 w-4 text-ink-300" />
              </Link>
            </li>
          ))}
        </ul>
        <button onClick={async () => { await logout(); navigate("/login"); }} className="card mt-5 flex min-h-[52px] w-full items-center justify-center gap-2 rounded-[22px] text-[16px] font-medium text-rose-ink active:bg-sand-50">
          <LogOut className="h-[18px] w-[18px]" /> Sign out
        </button>
      </div>

      <div className={clsx(!picked && "hidden lg:block")}>
        <Link to="/settings" className="-ml-1 inline-flex min-h-11 items-center gap-1 pr-3 text-[15px] text-lagoon-600 lg:hidden"><ChevronLeft className="h-5 w-5" />Settings</Link>
        <h1 className="display mb-5 text-[30px] leading-tight lg:hidden">{label}</h1>
        <div className="hidden lg:block"><PageHeader title="Settings" /></div>
      <div className="grid grid-cols-1 gap-8 lg:grid-cols-[200px_minmax(0,1fr)]">
        <nav className="hidden flex-col gap-1 lg:flex" aria-label="Settings sections">
          {SECTIONS.map(([key, name]) => (
            <NavLink key={key} to={`/settings/${key}`} className={({ isActive }) => clsx("whitespace-nowrap rounded-xl px-3 py-2 text-[13.5px] font-medium",
              isActive || (key === "profile" && !picked) ? "bg-white text-ink-900 shadow-[var(--shadow-card)]" : "text-ink-500 hover:text-ink-800")}>{name}</NavLink>
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
  return async (fn: () => Promise<unknown>, msg = "Saved") => {
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
  const [p, setP] = useState({ display_name: s.profile.display_name, home_city: s.profile.home_city ?? "", home_airport: s.profile.home_airport ?? "", timezone: s.profile.timezone, locale: s.profile.locale });
  const [prefs, setPrefs] = useState({ interests: s.preferences.interests.join(", "), pace: s.preferences.pace, budget: s.preferences.budget, accessibility_needs: s.preferences.accessibility_needs, default_currency: s.preferences.default_currency });
  const save = useSave();
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
      <Panel title="Profile" description="Your home city helps Tandem tell outbound from return journeys.">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Name" htmlFor="pn"><input id="pn" className="field" value={p.display_name} onChange={(e) => setP({ ...p, display_name: e.target.value })} /></Field>
          <Field label="Email"><input className="field" value={s.profile.email} disabled /></Field>
          <Field label="Home city" htmlFor="ph"><input id="ph" className="field" value={p.home_city} onChange={(e) => setP({ ...p, home_city: e.target.value })} /></Field>
          <Field label="Home airport" htmlFor="pa"><input id="pa" className="field uppercase" maxLength={4} value={p.home_airport} onChange={(e) => setP({ ...p, home_airport: e.target.value })} /></Field>
          <Field label="Timezone" htmlFor="ptz">
            <select id="ptz" className="field" value={p.timezone} onChange={(e) => setP({ ...p, timezone: e.target.value })}>{["UTC", ...zones].map((z) => <option key={z} value={z}>{z}</option>)}</select>
          </Field>
          <Field label="Language" htmlFor="pl" hint="Romanian is partially translated.">
            <select id="pl" className="field" value={p.locale} onChange={(e) => setP({ ...p, locale: e.target.value })}><option value="en">English</option><option value="ro">Română (beta)</option></select>
          </Field>
        </div>
      </Panel>
      <Panel title="Travel preferences" description="Used by the assistant when suggesting activities.">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2"><Field label="Interests" htmlFor="pi" hint="Comma separated"><input id="pi" className="field" value={prefs.interests} onChange={(e) => setPrefs({ ...prefs, interests: e.target.value })} /></Field></div>
          <Field label="Pace" htmlFor="pp"><select id="pp" className="field" value={prefs.pace} onChange={(e) => setPrefs({ ...prefs, pace: e.target.value })}><option value="relaxed">Relaxed</option><option value="balanced">Balanced</option><option value="packed">Packed</option></select></Field>
          <Field label="Budget" htmlFor="pb"><select id="pb" className="field" value={prefs.budget} onChange={(e) => setPrefs({ ...prefs, budget: e.target.value })}><option value="budget">Budget</option><option value="moderate">Moderate</option><option value="premium">Premium</option></select></Field>
          <Field label="Currency" htmlFor="pc"><input id="pc" maxLength={3} className="field uppercase" value={prefs.default_currency} onChange={(e) => setPrefs({ ...prefs, default_currency: e.target.value.toUpperCase() })} /></Field>
          <div className="sm:col-span-2"><Field label="Accessibility needs" htmlFor="pac"><input id="pac" className="field" value={prefs.accessibility_needs} onChange={(e) => setPrefs({ ...prefs, accessibility_needs: e.target.value })} /></Field></div>
        </div>
      </Panel>
      <div className="flex justify-end"><Button type="submit">Save changes</Button></div>
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
const PROVIDER_ROLE: Record<string, string> = {
  gemini: "Primary for PDFs, screenshots and photos, and the assistant.",
  zai: "Text reasoning and image reading (free vision model). PDFs only with paid models enabled.",
  groq: "Short text-only tasks (summaries, explanations). Never receives files.",
};

function AISection() {
  const info = useQuery({ queryKey: ["settings", "ai"], queryFn: () => api.get<AIInfo>("/settings/ai") });
  const [mode, setMode] = useState("off");
  const [allowed, setAllowed] = useState<Record<string, boolean>>({});
  const [ack, setAck] = useState(false);
  const save = useSave();
  const qc = useQueryClient();
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
    { key: "off", title: "Off — local only", body: "Documents are read by Tandem's own parser and OCR. Nothing is sent to AI companies. The assistant runs in a limited offline mode." },
    { key: "text_only", title: "Text only", body: "Text extracted on Tandem's servers may be sent to enabled providers. Original files never leave Tandem." },
    { key: "full", title: "Files and text", body: "Original PDFs and images may be sent to providers that officially support them (Gemini; Z.ai vision for images) for the most accurate extraction." },
  ];
  return (
    <div className="space-y-6">
      <Panel title="External AI processing" description="Choose what Tandem may send to AI providers. This is enforced on the server.">
        {info.data.demo_external_ai && <div className="mb-4"><InfoNote tone="violet">Demo workspace: documents are fictional, so external AI is on by default when configured on the server.</InfoNote></div>}
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
            <p className="flex gap-2 font-medium"><ShieldAlert className="h-4 w-4 shrink-0" /> Before you enable this</p>
            <ul className="list-disc space-y-1 pl-5">
              <li>On Google's free Gemini tier, prompts and files may be used by Google to improve its products, and human reviewers may see them.</li>
              <li>Gemini's Files API keeps temporary copies for up to 48 hours; Tandem deletes them after processing when possible.</li>
              <li>Z.ai and Groq process requests under their own terms and retention policies. Tandem cannot guarantee their deletion.</li>
              <li>Tandem only uses free-tier models{info.data.paid_models_allowed ? " unless the server administrator enabled paid models" : ""}. If the server's API key belongs to a billing-enabled project, usage may still be billed by the provider.</li>
            </ul>
            <label className="flex items-center gap-2 font-medium"><input type="checkbox" className="accent-lagoon-600" checked={ack} onChange={(e) => setAck(e.target.checked)} /> I understand how my documents will be processed</label>
          </div>
        )}
        <div className="mt-5 flex justify-end"><Button onClick={submit} disabled={needsAck && !ack}>Save AI settings</Button></div>
      </Panel>

      <Panel title="Providers" description="What each provider is used for, and which models this server is configured with.">
        <div className="space-y-4">
          {info.data.providers.map((p) => (
            <div key={p.provider} className="rounded-xl border border-sand-200 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-[14.5px] font-semibold">{PROVIDER_NAMES[p.provider]}</p>
                <div className="flex items-center gap-2">
                  {p.configured ? <Badge tone="lagoon">API key configured</Badge> : <Badge>Not configured</Badge>}
                  {p.status?.cooldown_until && new Date(p.status.cooldown_until) > new Date() && <Badge tone="amber">Quota reached — paused</Badge>}
                  <Toggle checked={allowed[p.provider] !== false} onChange={(v) => setAllowed({ ...allowed, [p.provider]: v })} label={`Allow ${PROVIDER_NAMES[p.provider]}`} hideLabel />
                </div>
              </div>
              <p className="mt-1 text-[13px] text-ink-500">{PROVIDER_ROLE[p.provider]}</p>
              <ul className="mt-3 space-y-1 text-[12.5px] text-ink-500">
                {Object.entries(p.roles).map(([role, r]) => (
                  <li key={role} className="flex flex-wrap items-center gap-2">
                    <span className="w-20 capitalize text-ink-400">{role}</span>
                    <code className="rounded bg-sand-50 px-1.5 py-0.5 text-[12px] text-ink-700">{r.model}</code>
                    {r.free_tier ? <Badge tone="lagoon">Free tier</Badge> : <Badge tone="amber">Paid</Badge>}
                    {!r.usable && <Badge tone="neutral">Blocked</Badge>}
                    {!r.id_verified && <span className="text-ink-400">ID checked at runtime</span>}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <p className="mt-4 text-[12.5px] text-ink-400">Groq is restricted to text in code: the server rejects any request containing a file before it reaches Groq.</p>
      </Panel>
    </div>
  );
}

function Usage() {
  const usage = useQuery({ queryKey: ["settings", "usage"], queryFn: () => api.get<{ summary: { provider: string; model: string; status: string; requests: number; input_tokens: number; output_tokens: number; estimated_cost_usd: number }[]; recent: { provider: string; model: string; task: string; status: string; input_tokens: number; output_tokens: number; latency_ms: number; error_code: string | null; created_at: string }[]; paid_models_allowed: boolean }>("/settings/usage") });
  if (!usage.data) return <PageLoader />;
  const totals = usage.data.summary.reduce((acc, r) => ({ req: acc.req + r.requests, tin: acc.tin + r.input_tokens, tout: acc.tout + r.output_tokens, cost: acc.cost + r.estimated_cost_usd }), { req: 0, tin: 0, tout: 0, cost: 0 });
  return (
    <div className="space-y-6">
      <Panel title="Last 30 days" description={usage.data.paid_models_allowed ? "Paid models are enabled on this server." : "Paid models are disabled on this server; only free-tier models are used."}>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[["Requests", totals.req], ["Input tokens", totals.tin.toLocaleString()], ["Output tokens", totals.tout.toLocaleString()], ["Est. cost", `$${totals.cost.toFixed(4)}`]].map(([k, v]) => (
            <div key={k as string} className="rounded-xl bg-sand-50 p-3"><p className="text-[12px] text-ink-400">{k}</p><p className="mt-1 text-[18px] font-semibold">{v}</p></div>
          ))}
        </div>
      </Panel>
      <Panel title="Recent requests">
        {usage.data.recent.length === 0 ? <p className="text-[13.5px] text-ink-400">No AI requests yet.</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-[12.5px]">
              <thead className="text-left text-ink-400"><tr><th className="pb-2 font-medium">When</th><th className="pb-2 font-medium">Provider</th><th className="pb-2 font-medium">Task</th><th className="pb-2 font-medium">Status</th><th className="pb-2 text-right font-medium">Tokens</th></tr></thead>
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
  const [deleteImported, setDeleteImported] = useState(false);
  if (!data.data) return <PageLoader />;
  const g = data.data.gmail;
  const connect = async () => {
    try { window.location.href = (await api.post<{ authorization_url: string }>("/integrations/gmail/connect")).authorization_url; } catch (e) { toast(errorMessage(e), "error"); }
  };
  const disconnect = async () => {
    if (!confirm("Disconnect Gmail and revoke Tandem's access?")) return;
    await api.post("/integrations/gmail/disconnect", { delete_imported: deleteImported });
    data.refetch();
    toast("Gmail disconnected", "success");
  };
  return (
    <div className="space-y-6">
      {params.get("gmail") === "connected" && <InfoNote tone="lagoon" icon={<Check className="h-4 w-4" />}>Gmail connected. Tandem is looking for travel emails now.</InfoNote>}
      {params.get("gmail") === "error" && <ErrorNote>Gmail connection failed ({params.get("code")}). Please try again.</ErrorNote>}
      <Panel title="Gmail" description="Read-only access. Tandem searches for likely travel emails and imports only those you choose. It can't send, delete or change email.">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-clay-50 text-clay-600"><Mail className="h-5 w-5" /></span>
            <div>
              <p className="text-[14px] font-medium">{g.status === "connected" ? g.account_email : "Not connected"}</p>
              <p className="text-[12.5px] text-ink-400">{g.status === "connected" ? `Last checked ${g.last_sync_at ? relativeTime(g.last_sync_at) : "never"}` : g.reason ?? "Connect to import confirmations automatically."}</p>
            </div>
          </div>
          {g.status === "connected" ? <Button variant="danger" onClick={disconnect}>Disconnect</Button> : <Button onClick={connect} disabled={!g.available}>Connect Gmail</Button>}
        </div>
        {g.status === "connected" && (
          <label className="mt-4 flex items-center gap-2 text-[13px] text-ink-600"><input type="checkbox" className="accent-lagoon-600" checked={deleteImported} onChange={(e) => setDeleteImported(e.target.checked)} /> Also delete emails imported from Gmail when disconnecting</label>
        )}
        {g.error && <div className="mt-3"><ErrorNote>{g.error}</ErrorNote></div>}
      </Panel>
      <Panel title="Travel providers" description="Booking integrations work only where the provider grants API access. Tandem never pretends a provider is connected.">
        <ul className="space-y-3">
          {data.data.travel_providers.map((p) => (
            <li key={p.key} className="rounded-xl border border-sand-200 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-[14px] font-semibold">{p.name}</p>
                <Badge tone={p.state === "simulated_demo" ? "violet" : ["search_only", "redirect_only", "booking_enabled"].includes(p.state) ? "lagoon" : p.state === "awaiting_partner_approval" ? "amber" : "neutral"}>{p.state.replace(/_/g, " ")}</Badge>
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5 text-[12px]">
                {(["search", "availability", "booking", "redirect"] as const).map((c) => <Badge key={c} tone={p[c] ? "lagoon" : "neutral"}>{p[c] ? <Check className="h-3 w-3" /> : null}{c}</Badge>)}
              </div>
              <ul className="mt-2 space-y-1 text-[12.5px] text-ink-500">{p.notes.map((n) => <li key={n}>{n}</li>)}</ul>
              {p.docs_url && <a href={p.docs_url} target="_blank" rel="noopener noreferrer" className="mt-2 inline-flex items-center gap-1 text-[12.5px] text-lagoon-600 hover:underline">Provider documentation <ExternalLink className="h-3 w-3" /></a>}
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
  if (!sub.data) return <PageLoader />;
  const s = sub.data;
  const change = async (action: "create" | "reset" | "off") => {
    if (action === "reset" && !confirm("Reset the link? Calendars using the current link stop updating until you add the new one.")) return;
    if (action === "off" && !confirm("Turn off the link? Calendars using it stop updating.")) return;
    setBusy(true);
    try {
      const next = action === "off" ? await api.del<CalendarSub>("/calendar/subscription") : await api.post<CalendarSub>("/calendar/subscription");
      qc.setQueryData(["calendar-subscription"], next);
      toast(action === "off" ? "Calendar link turned off" : action === "reset" ? "New link ready. Add it to your calendar again." : "Calendar link ready", "success");
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(false);
    }
  };
  const copy = async () => {
    try { await navigator.clipboard.writeText(s.url!); toast("Link copied", "success"); } catch { toast("Couldn't copy. Press and hold the link to copy it.", "error"); }
  };
  return (
    <div className="space-y-6">
      <Panel title="Your trips in your calendar" description="One private link that keeps Apple Calendar, Google Calendar or Outlook in step with Tandem. New bookings, changed times and cancellations show up on their own.">
        {!s.active ? (
          <div className="space-y-4">
            <ul className="space-y-2 text-[13.5px] text-ink-600">
              <li className="flex gap-2"><Check className="mt-0.5 h-4 w-4 shrink-0 text-lagoon-600" />Every confirmed and planned event, at the right time wherever you are.</li>
              <li className="flex gap-2"><Check className="mt-0.5 h-4 w-4 shrink-0 text-lagoon-600" />Title, place and a link back to the trip. Booking references, names, prices and notes stay in Tandem.</li>
            </ul>
            <Button onClick={() => change("create")} loading={busy} icon={<CalendarDays className="h-4 w-4" />}>Create calendar link</Button>
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
              <p className="eyebrow mb-2">Or copy the link</p>
              <div className="flex gap-2">
                <input readOnly value={s.url!} onFocus={(e) => e.currentTarget.select()} aria-label="Calendar subscription link"
                  className="h-11 min-w-0 flex-1 truncate rounded-xl border border-sand-200 bg-sand-50 px-3 text-[16px] text-ink-600 sm:text-[13.5px]" />
                <Button variant="secondary" onClick={copy} icon={<Copy className="h-4 w-4" />} className="shrink-0">Copy</Button>
              </div>
              <p className="mt-2 text-[12.5px] text-ink-400">Outlook: Add calendar → Subscribe from web. Google refreshes subscribed calendars every few hours, Apple about once an hour.</p>
            </div>
            <InfoNote tone="amber" icon={<ShieldAlert className="h-4 w-4" />}>Anyone with this link can see when and where you'll be. If you shared it by mistake, reset it.</InfoNote>
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-sand-100 pt-4">
              <p className="text-[12.5px] text-ink-400">Created {s.created_at ? relativeTime(s.created_at) : "recently"}</p>
              <div className="flex gap-2">
                <Button variant="secondary" size="sm" onClick={() => change("reset")} disabled={busy}>Reset link</Button>
                <Button variant="danger" size="sm" onClick={() => change("off")} disabled={busy}>Turn off</Button>
              </div>
            </div>
          </div>
        )}
      </Panel>
      <p className="px-1 text-[13px] text-ink-500">Want a one-off copy of a single trip instead? Open the trip and tap <strong className="font-medium text-ink-700">Add to Calendar</strong>.</p>
    </div>
  );
}

const NOTE_LABELS: Record<string, string> = {
  document_processed: "Document processed", document_failed: "Processing failed", reservation_detected: "Bookings found",
  trip_created: "New trip created", reservation_changed: "Reservation changed", conflict_detected: "Itinerary conflicts",
  upcoming_event: "Upcoming events", cancellation_deadline: "Cancellation deadlines", approval_required: "Approval needed",
  booking_result: "Booking results", integration_failure: "Integration problems",
};

function NotificationPrefs({ s }: { s: Settings }) {
  const [prefs, setPrefs] = useState(s.preferences.notification_prefs);
  const save = useSave();
  return (
    <Panel title="In-app notifications">
      <div className="divide-y divide-sand-100">
        {Object.entries(NOTE_LABELS).map(([k, l]) => (
          <Toggle key={k} label={l} checked={prefs[k] !== false} onChange={(v) => {
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
  return (
    <div className="space-y-6">
      <Panel title="Document storage" description={`Originals are stored privately and encrypted. Uploads up to ${s.limits.max_upload_mb} MB each.`}>
        <Toggle label="Keep original documents" description="Turn off to delete each original file after Tandem has read it. Extracted details stay." checked={s.preferences.retain_original_documents}
          onChange={(v) => save(() => api.patch("/settings/preferences", { retain_original_documents: v }))} />
        <Toggle label="Auto-organise high-confidence bookings" description="Add records to the matching trip without review when every key detail was verified against the document. Off by default."
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
  const change = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    try { await api.post("/settings/password", { current_password: cur, new_password: next }); await logout(); navigate("/login"); } catch (e2) { setErr(errorMessage(e2)); }
  };
  return (
    <div className="space-y-6">
      <Panel title="Change password" description="You'll be signed out everywhere.">
        <form onSubmit={change} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Current password" htmlFor="cp"><input id="cp" type="password" required className="field" value={cur} onChange={(e) => setCur(e.target.value)} autoComplete="current-password" /></Field>
          <Field label="New password" htmlFor="np" hint="At least 10 characters"><input id="np" type="password" required minLength={10} className="field" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" /></Field>
          {err && <div className="sm:col-span-2"><ErrorNote>{err}</ErrorNote></div>}
          <div className="sm:col-span-2"><Button type="submit">Update password</Button></div>
        </form>
      </Panel>
      <Panel title="Signed-in sessions">
        <ul className="divide-y divide-sand-100">
          {(sessions.data ?? []).map((s) => (
            <li key={s.id} className="flex items-center justify-between gap-3 py-3">
              <div className="min-w-0"><p className="truncate text-[13.5px]">{s.user_agent || "Unknown device"}</p><p className="text-[12px] text-ink-400">Active {relativeTime(s.last_seen_at)}</p></div>
              {s.current ? <Badge tone="lagoon">This device</Badge> : <Button size="sm" variant="ghost" onClick={async () => { await api.del(`/settings/sessions/${s.id}`); sessions.refetch(); }}>Sign out</Button>}
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
  const del = async (e: FormEvent) => {
    e.preventDefault();
    try { await api.post("/settings/delete-account", { password: pw, confirm: confirmText }); await refresh(); navigate("/login"); } catch (e2) { setErr(errorMessage(e2)); }
  };
  return (
    <div className="space-y-6">
      <Panel title="Export your data" description="Trips, reservations, itinerary, extracted records, assistant conversations and actions as JSON.">
        <a href="/api/v1/settings/export" className="inline-flex h-10 items-center rounded-xl bg-lagoon-900 px-4 text-[14px] font-medium text-white hover:bg-ink-800">Download export (.zip)</a>
      </Panel>
      <Panel title="Delete account" description="Permanently deletes your account, documents, trips and history, and revokes connected accounts. This can't be undone.">
        <form onSubmit={del} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Password" htmlFor="dp"><input id="dp" type="password" required className="field" value={pw} onChange={(e) => setPw(e.target.value)} /></Field>
          <Field label="Type DELETE to confirm" htmlFor="dc"><input id="dc" className="field" value={confirmText} onChange={(e) => setConfirmText(e.target.value)} /></Field>
          {err && <div className="sm:col-span-2"><ErrorNote>{err}</ErrorNote></div>}
          <div className="sm:col-span-2"><Button type="submit" variant="danger" icon={<AlertTriangle className="h-4 w-4" />} disabled={confirmText !== "DELETE"}>Delete my account</Button></div>
        </form>
      </Panel>
      <p className="text-[12.5px] text-ink-400">See also <Link to="/settings/ai" className="text-lagoon-600 hover:underline">AI & privacy</Link> for how documents are processed.</p>
    </div>
  );
}
