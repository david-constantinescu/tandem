import { ArrowRight, FileText, MessageCircle, ShieldCheck, Sparkles } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { Logo } from "@/components/layout/AppShell";
import { Button, ErrorNote, Field } from "@/components/ui";
import { errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function AuthPage({ mode }: { mode: "login" | "register" }) {
  const { user, login, register, startDemo } = useAuth();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"form" | "demo" | null>(null);
  const next = params.get("next") || "/";

  if (user) return <Navigate to={next} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy("form");
    try {
      if (mode === "login") await login(email, password);
      else await register(email, password, name);
      navigate(next, { replace: true });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  const demo = async () => {
    setError(null);
    setBusy("demo");
    try {
      await startDemo();
      navigate("/", { replace: true });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.05fr_1fr]">
      <section className="relative hidden overflow-hidden bg-lagoon-900 px-14 py-12 text-lagoon-50 lg:flex lg:flex-col">
        <div className="absolute -right-24 -top-24 h-96 w-96 rounded-full bg-clay-500/20 blur-3xl" />
        <div className="absolute -bottom-32 left-10 h-96 w-96 rounded-full bg-lagoon-500/25 blur-3xl" />
        <div className="relative flex items-center gap-2.5">
          <svg viewBox="0 0 64 64" className="h-9 w-9" aria-hidden>
            <rect width="64" height="64" rx="16" fill="#f3e9dc" />
            <circle cx="25" cy="32" r="11" fill="none" stroke="#14363a" strokeWidth="5" />
            <circle cx="39" cy="32" r="11" fill="none" stroke="#c8623a" strokeWidth="5" />
          </svg>
          <span className="display text-2xl font-semibold text-white">Tandem</span>
        </div>
        <div className="relative mt-auto max-w-lg">
          <h1 className="display text-[44px] leading-[1.08] text-white">Every booking, one calm itinerary.</h1>
          <p className="mt-5 text-[16px] leading-relaxed text-lagoon-100/85">
            Drop in confirmations, tickets and screenshots. Tandem reads them, builds your trip, spots clashes, and
            finds things to do that actually fit — booking only when you say so.
          </p>
          <ul className="mt-10 space-y-4 text-[14.5px] text-lagoon-50/90">
            <li className="flex gap-3"><FileText className="mt-0.5 h-5 w-5 text-clay-100" /> Extracts details with sources and confidence you can check</li>
            <li className="flex gap-3"><MessageCircle className="mt-0.5 h-5 w-5 text-clay-100" /> An assistant that works from your real itinerary</li>
            <li className="flex gap-3"><ShieldCheck className="mt-0.5 h-5 w-5 text-clay-100" /> Nothing is booked or paid without your explicit approval</li>
          </ul>
        </div>
      </section>

      <section className="flex flex-col justify-center px-5 py-10 sm:px-12">
        <div className="mx-auto w-full max-w-[400px]">
          <Logo className="mb-10 lg:hidden" />
          <h2 className="display text-[30px] leading-tight">{mode === "login" ? "Welcome back" : "Create your account"}</h2>
          <p className="mt-2 text-[15px] text-ink-500">
            {mode === "login" ? "Sign in to your travel workspace." : "Start organising your trips in a minute."}
          </p>

          <form onSubmit={submit} className="mt-8 space-y-4">
            {mode === "register" && (
              <Field label="Your name" htmlFor="name">
                <input id="name" className="field" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" />
              </Field>
            )}
            <Field label="Email" htmlFor="email">
              <input id="email" type="email" required className="field" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
            </Field>
            <Field label="Password" htmlFor="password" hint={mode === "register" ? "At least 10 characters." : undefined}>
              <input id="password" type="password" required minLength={mode === "register" ? 10 : 1} className="field" value={password}
                onChange={(e) => setPassword(e.target.value)} autoComplete={mode === "login" ? "current-password" : "new-password"} />
            </Field>
            {error && <ErrorNote>{error}</ErrorNote>}
            <Button type="submit" size="lg" className="w-full" loading={busy === "form"}>
              {mode === "login" ? "Sign in" : "Create account"}
            </Button>
          </form>

          <p className="mt-5 text-center text-[14px] text-ink-500">
            {mode === "login" ? <>New to Tandem? <Link className="font-medium text-lagoon-600 hover:underline" to="/register">Create an account</Link></>
              : <>Already have an account? <Link className="font-medium text-lagoon-600 hover:underline" to="/login">Sign in</Link></>}
          </p>

          <div className="my-8 flex items-center gap-3 text-[12px] uppercase tracking-wider text-ink-300">
            <span className="h-px flex-1 bg-sand-200" /> or <span className="h-px flex-1 bg-sand-200" />
          </div>
          <button onClick={demo} disabled={busy !== null}
            className="group flex w-full items-center gap-4 rounded-2xl border border-sand-200 bg-white p-4 text-left transition hover:border-lagoon-500/40 hover:shadow-[var(--shadow-lift)] disabled:opacity-60">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-clay-50 text-clay-600"><Sparkles className="h-5 w-5" /></span>
            <span className="flex-1">
              <span className="block text-[15px] font-semibold text-ink-900">{busy === "demo" ? "Preparing your demo…" : "Explore the demo"}</span>
              <span className="block text-[13px] text-ink-500">A Rome long weekend with fictional bookings and a simulated booking provider.</span>
            </span>
            <ArrowRight className="h-4 w-4 text-ink-300 transition group-hover:translate-x-0.5 group-hover:text-lagoon-600" />
          </button>
        </div>
      </section>
    </div>
  );
}
