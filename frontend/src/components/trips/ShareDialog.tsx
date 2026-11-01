import { Check, Copy, Link2, Send, UserMinus, X } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, LoadError, PageLoader } from "@/components/ui";
import { Dialog } from "@/components/ui/Dialog";
import { useToast } from "@/components/ui/Toast";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { keys } from "@/lib/queries";
import type { Trip } from "@/lib/types";

type Sharing = {
  role: "owner" | "member";
  owner: { user_id: string; name: string };
  members: { user_id: string; name: string; joined_at: string }[];
  invites: { id: string; url: string; created_at: string; expires_at: string; uses: number }[];
};

/** impartirea unei calatorii cu familia: un link pe care il trimiti, iar cine il deschide vede planul (nu il poate schimba) */
export function ShareDialog({ trip, open, onOpenChange }: { trip: Trip; open: boolean; onOpenChange: (o: boolean) => void }) {
  const { t } = useT();
  const { user } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  const q = useQuery({ queryKey: ["sharing", trip.id], enabled: open, queryFn: () => api.get<Sharing>(`/trips/${trip.id}/sharing`) });
  const refresh = () => qc.invalidateQueries({ queryKey: ["sharing", trip.id] });
  const owner = q.data?.role === "owner";

  const create = async () => {
    setBusy(true);
    try { await api.post(`/trips/${trip.id}/invites`); await refresh(); } catch (e) { toast(errorMessage(e), "error"); } finally { setBusy(false); }
  };
  const copy = async (url: string, id: string) => {
    try { await navigator.clipboard.writeText(url); setCopied(id); setTimeout(() => setCopied((c) => (c === id ? null : c)), 2000); toast(t("share.copied"), "success"); }
    catch { window.prompt(t("share.copy"), url); }
  };
  const send = async (url: string) => {
    try { await navigator.share({ title: trip.name, text: t("share.message", { trip: trip.name }), url }); } catch { /* omul a inchis foaia de partajare */ }
  };
  const revoke = async (id: string) => {
    try { await api.del(`/trips/${trip.id}/invites/${id}`); await refresh(); } catch (e) { toast(errorMessage(e), "error"); }
  };
  const removeMember = async (userId: string, leaving: boolean) => {
    if (leaving && !confirm(t("share.leaveConfirm"))) return;
    try {
      await api.del(`/trips/${trip.id}/members/${userId}`);
      if (leaving) { qc.invalidateQueries({ queryKey: keys.trips }); onOpenChange(false); navigate("/trips"); } else await refresh();
    } catch (e) { toast(errorMessage(e), "error"); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={t("share.title")} description={owner ? t("share.subtitle") : t("share.sharedBy", { name: q.data?.owner.name ?? "" })}>
      {q.isLoading ? <PageLoader /> : q.isError || !q.data ? <LoadError title={t("share.loadError")} onRetry={() => q.refetch()} retrying={q.isFetching} /> : (
        <div className="max-h-[65dvh] space-y-5 overflow-y-auto pb-2">
          {owner && (
            <section className="space-y-2.5">
              {q.data.invites.map((i) => (
                <div key={i.id} className="rounded-2xl bg-sand-50 p-3">
                  <p className="flex items-center gap-1.5 truncate text-[13px] text-ink-600"><Link2 className="h-3.5 w-3.5 shrink-0" /><span className="truncate">{i.url}</span></p>
                  <p className="mt-0.5 text-[12px] text-ink-400">{t("share.expires", { date: fmtDate(i.expires_at.slice(0, 10), { year: true }) })}</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <Button size="sm" onClick={() => copy(i.url, i.id)} icon={copied === i.id ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}>{t("share.copy")}</Button>
                    {typeof navigator !== "undefined" && "share" in navigator && <Button size="sm" variant="secondary" onClick={() => send(i.url)} icon={<Send className="h-3.5 w-3.5" />}>{t("share.send")}</Button>}
                    <Button size="sm" variant="ghost" onClick={() => revoke(i.id)} icon={<X className="h-3.5 w-3.5" />}>{t("share.revoke")}</Button>
                  </div>
                </div>
              ))}
              <Button variant={q.data.invites.length ? "secondary" : "primary"} onClick={create} loading={busy} icon={<Link2 className="h-4 w-4" />}>{q.data.invites.length ? t("share.createAnother") : t("share.create")}</Button>
            </section>
          )}
          <section>
            <p className="eyebrow mb-2">{t("share.people")}</p>
            <ul className="divide-y divide-sand-100 rounded-2xl border border-sand-200">
              <li className="flex min-h-12 items-center gap-3 px-3 py-2"><Avatar name={q.data.owner.name} /><span className="min-w-0 flex-1 truncate text-[14.5px] font-medium">{q.data.owner.name}</span><span className="text-[12px] text-ink-400">{t("share.ownerTag")}</span></li>
              {q.data.members.map((m) => (
                <li key={m.user_id} className="flex min-h-12 items-center gap-3 px-3 py-2">
                  <Avatar name={m.name} />
                  <span className="min-w-0 flex-1 truncate text-[14.5px] font-medium">{m.name}{m.user_id === user?.id ? ` · ${t("share.you")}` : ""}</span>
                  {(owner || m.user_id === user?.id) && (
                    <button onClick={() => removeMember(m.user_id, m.user_id === user?.id)} aria-label={m.user_id === user?.id ? t("share.leave") : t("share.remove", { name: m.name })}
                      className="flex h-9 w-9 items-center justify-center rounded-full text-ink-400 hover:bg-sand-100 active:scale-90"><UserMinus className="h-4 w-4" /></button>
                  )}
                </li>
              ))}
            </ul>
            {q.data.members.length === 0 && owner && <p className="mt-2 text-[13px] text-ink-400">{t("share.nobody")}</p>}
          </section>
          {!owner && <p className="text-[12.5px] text-ink-400">{t("share.readOnly")}</p>}
        </div>
      )}
    </Dialog>
  );
}

function Avatar({ name }: { name: string }) {
  return <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-lagoon-900 text-[13px] font-semibold text-white">{name.slice(0, 1).toLocaleUpperCase()}</span>;
}
