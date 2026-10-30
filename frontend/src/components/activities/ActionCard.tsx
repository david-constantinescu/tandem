import { clsx } from "clsx";
import { AlertTriangle, CheckCircle2, Clock, ExternalLink, Loader2, ShieldCheck, XCircle } from "lucide-react";
import { Button, StatusPill } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { errorMessage } from "@/lib/api";
import { fmtDate, money } from "@/lib/format";
import { useApprove, useReject } from "@/lib/queries";
import type { Action } from "@/lib/types";

/** Approval card bound to the exact payload: approving sends the payload hash the user is looking at. */
export function ActionCard({ action, compact }: { action: Action; compact?: boolean }) {
  const approve = useApprove();
  const reject = useReject();
  const toast = useToast();
  const p = action.payload;
  const awaiting = action.status === "awaiting_approval";
  const isWebsite = action.action_type === "browser_checkout";
  const isBooking = action.action_type === "book_activity" || isWebsite;

  const doApprove = async () => {
    try {
      const res = await approve.mutateAsync(action);
      if (res.status === "completed") toast(res.result?.simulated ? "Simulated booking confirmed and verified" : "Done", "success");
      else if (res.status === "awaiting_approval") toast("The price changed — please review again", "info");
      else if (res.status === "in_progress") toast("Submitting to the provider…", "info");
      else toast(res.error ?? `Status: ${res.status}`, "error");
    } catch (e) {
      toast(errorMessage(e), "error");
    }
  };

  return (
    <article className={clsx("rounded-2xl border bg-white p-4 sm:p-5", awaiting ? "border-clay-100 shadow-[var(--shadow-lift)]" : "border-sand-200")}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 gap-3">
          <span className={clsx("flex h-9 w-9 shrink-0 items-center justify-center rounded-xl",
            action.status === "completed" ? "bg-lagoon-50 text-lagoon-600" : action.status === "failed" ? "bg-rose-soft text-rose-ink"
              : awaiting ? "bg-clay-50 text-clay-600" : "bg-sand-100 text-ink-500")}>
            {action.status === "completed" ? <CheckCircle2 className="h-[18px] w-[18px]" /> : action.status === "failed" ? <XCircle className="h-[18px] w-[18px]" />
              : action.status === "in_progress" ? <Loader2 className="h-[18px] w-[18px] animate-spin" /> : <ShieldCheck className="h-[18px] w-[18px]" />}
          </span>
          <div className="min-w-0">
            <p className="eyebrow">{isWebsite ? `Website purchase by the browser agent · ${p.site_name}` : isBooking ? `Booking proposal · ${p.provider_name ?? action.provider}` : action.action_type === "link_out" ? "Book with provider" : "Itinerary change"}</p>
            <h3 className="mt-0.5 text-[15.5px] font-semibold text-ink-900">{action.title}</h3>
            {action.description && <p className="mt-0.5 text-[13.5px] text-ink-500">{action.description}</p>}
          </div>
        </div>
        <StatusPill status={action.status} />
      </div>

      {isBooking && !compact && (
        <dl className="mt-4 grid grid-cols-2 gap-3 rounded-xl bg-sand-50 p-3.5 text-[13px] sm:grid-cols-4">
          <div><dt className="text-ink-400">Date</dt><dd className="font-medium text-ink-800">{fmtDate(p.date, { year: true })}</dd></div>
          <div><dt className="text-ink-400">Time</dt><dd className="font-medium text-ink-800">{isWebsite ? `${p.offer?.depart}–${p.offer?.arrive}` : p.time} <span className="font-normal text-ink-400">{p.timezone?.split("/").pop()?.replace("_", " ")}</span></dd></div>
          <div><dt className="text-ink-400">People</dt><dd className="font-medium text-ink-800">{isWebsite ? p.travellers?.length : p.participants}</dd></div>
          <div><dt className="text-ink-400">Total</dt><dd className="font-semibold text-ink-900">{money(action.cost, action.currency)}</dd></div>
        </dl>
      )}
      {isWebsite && !compact && p.travellers?.length > 0 && (
        <p className="mt-3 text-[13px] text-ink-600">Names the agent will enter: <strong>{p.travellers.join(", ")}</strong></p>
      )}
      {!compact && action.consequences.length > 0 && awaiting && (
        <ul className="mt-3 space-y-1 text-[13px] text-ink-600">
          {action.consequences.map((c) => <li key={c} className="flex gap-2"><span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-ink-300" />{c}</li>)}
        </ul>
      )}
      {!compact && action.cancellation_policy && awaiting && <p className="mt-2 text-[12.5px] text-ink-400">Cancellation: {action.cancellation_policy}</p>}
      {action.result?.requote && awaiting && (
        <p className="mt-3 flex items-center gap-2 rounded-lg bg-amber-soft px-3 py-2 text-[13px] text-amber-ink"><AlertTriangle className="h-4 w-4" /> {action.result.requote}. Approve the new price to continue.</p>
      )}
      {action.status === "completed" && action.result?.provider_booking_id && (
        <p className="mt-3 rounded-lg bg-lagoon-50 px-3 py-2 text-[13px] text-lagoon-700">
          Confirmation <span className="font-mono font-medium">{action.result.provider_booking_id}</span>, {isWebsite ? "read back from the website's confirmation page" : "verified with the provider"}
          {action.result.simulated ? " (simulated — nothing was charged)" : ""}. Added to your itinerary.
        </p>
      )}
      {(action.status === "failed" || action.status === "requires_manual") && action.error && (
        <p className="mt-3 rounded-lg bg-rose-soft/70 px-3 py-2 text-[13px] text-rose-ink">{action.error}</p>
      )}
      {action.action_type === "link_out" && p.booking_url && (
        <a href={p.booking_url} target="_blank" rel="noopener noreferrer nofollow" className="mt-3 inline-flex items-center gap-1.5 text-[13.5px] font-medium text-lagoon-600 hover:underline">
          Open provider page <ExternalLink className="h-3.5 w-3.5" />
        </a>
      )}

      {awaiting && (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button onClick={doApprove} loading={approve.isPending} variant={isBooking ? "accent" : "primary"}>
            {isBooking ? `Approve & book ${money(action.cost, action.currency)}` : "Apply change"}
          </Button>
          <Button variant="ghost" onClick={() => reject.mutate(action)} loading={reject.isPending}>Decline</Button>
          {action.expires_at && <span className="ml-auto flex items-center gap-1 text-[12px] text-ink-400"><Clock className="h-3.5 w-3.5" /> Quote valid until {new Date(action.expires_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>}
        </div>
      )}
    </article>
  );
}
