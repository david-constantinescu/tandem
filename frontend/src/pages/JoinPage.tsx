import { Users } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, EmptyState, PageLoader } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { api, errorMessage } from "@/lib/api";
import { fmtRange } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { keys } from "@/lib/queries";

type Preview = { trip_name: string; destination: string | null; start_date: string | null; end_date: string | null; owner_name: string; already_in: boolean };

/** cine deschide un link de invitatie vede despre ce calatorie e vorba si intra cu un singur buton */
export default function JoinPage() {
  const { token = "" } = useParams();
  const { t } = useT();
  const toast = useToast();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const q = useQuery({ queryKey: ["invite", token], retry: false, queryFn: () => api.get<Preview>(`/invites/${token}`) });

  if (q.isLoading) return <PageLoader />;
  if (q.isError || !q.data) {
    return <EmptyState icon={<Users />} title={t("join.invalidTitle")} body={t("join.invalidBody")} action={<Link to="/trips" className="text-lagoon-600">{t("trip.backToTrips")}</Link>} />;
  }
  const p = q.data;
  const join = async () => {
    setBusy(true);
    try {
      const r = await api.post<{ trip_id: string }>(`/invites/${token}/accept`);
      qc.invalidateQueries({ queryKey: keys.trips });
      navigate(`/trips/${r.trip_id}`, { replace: true });
    } catch (e) { toast(errorMessage(e), "error"); setBusy(false); }
  };
  return (
    <div className="mx-auto mt-10 max-w-md rounded-[28px] border border-sand-200 bg-white p-7 text-center shadow-[var(--shadow-float)]">
      <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-apricot-soft text-clay-600"><Users className="h-6 w-6" /></span>
      <h1 className="display mt-4 text-[26px] leading-tight">{t("join.title")}</h1>
      <p className="mt-2 text-[15px] text-ink-600">{t("join.body", { name: p.owner_name, trip: p.trip_name })}</p>
      <p className="mt-1 text-[13.5px] text-ink-400">{fmtRange(p.start_date, p.end_date)}{p.destination ? ` · ${p.destination}` : ""}</p>
      <p className="mt-4 text-[13px] text-ink-500">{t("join.readOnly")}</p>
      <div className="mt-6">
        {p.already_in ? <Link to="/trips" className="text-lagoon-600">{t("join.already")}</Link> : <Button onClick={join} loading={busy} className="w-full">{t("join.accept")}</Button>}
      </div>
    </div>
  );
}
