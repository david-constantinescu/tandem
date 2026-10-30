import { clsx } from "clsx";
import { ArrowUp, CircleAlert, Loader2, MessageCirclePlus, Plus, Trash2, Wrench } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import ReactMarkdown from "react-markdown";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { ActionCard } from "@/components/activities/ActionCard";
import { ActivityCard } from "@/components/activities/ActivityCard";
import { Badge, Button, PageLoader } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { api, errorMessage } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import { keys, useConversation, useConversations, useTrips, type ConversationPayload } from "@/lib/queries";
import type { ActivityResult, Conversation, Message } from "@/lib/types";

const PROMPTS = [
  "What do I have booked tomorrow?",
  "Is there enough time between my flight and hotel check-in?",
  "Find something to do on Sunday afternoon that fits my plans",
  "What's still unconfirmed?",
  "Summarise everything I need before departure",
  "Are there any conflicts I should fix?",
];

const TOOL_LABEL: Record<string, string> = {
  list_trips: "Looked at your trips", get_trip: "Opened trip", get_itinerary: "Read itinerary", get_reservations: "Read reservations",
  get_documents: "Listed documents", detect_conflicts: "Checked for conflicts", get_free_time: "Found free time",
  search_activities: "Searched activities", get_activity_details: "Got activity details", create_itinerary_event: "Added a suggestion",
  update_itinerary_event: "Updated plan", delete_itinerary_event: "Removed event", create_booking_proposal: "Prepared booking proposal",
  get_pending_approvals: "Checked approvals", get_action_status: "Checked action status", search_travel_information: "Searched your bookings",
};

export default function AssistantPage() {
  const { id } = useParams();
  const conversations = useConversations();
  const trips = useTrips();
  const navigate = useNavigate();
  const qc = useQueryClient();

  useEffect(() => {
    if (!id && conversations.data?.length) navigate(`/assistant/${conversations.data[0].id}`, { replace: true });
  }, [id, conversations.data, navigate]);

  const start = async (tripId?: string) => {
    const conv = await api.post<Conversation>("/assistant/conversations", { trip_id: tripId ?? trips.data?.find((t) => t.stats.phase !== "past")?.id ?? null });
    qc.invalidateQueries({ queryKey: keys.conversations });
    navigate(`/assistant/${conv.id}`);
  };

  return (
    <div className="grid grid-cols-1 gap-6 lg:h-[calc(100vh-96px)] xl:grid-cols-[250px_minmax(0,1fr)]">
      <aside className="hidden flex-col xl:flex">
        <Button onClick={() => start()} icon={<Plus className="h-4 w-4" />} className="w-full">New conversation</Button>
        <ul className="mt-4 flex-1 space-y-1 overflow-y-auto">
          {(conversations.data ?? []).map((c) => (
            <li key={c.id}>
              <Link to={`/assistant/${c.id}`} className={clsx("block rounded-xl px-3 py-2.5 text-[13.5px] transition", c.id === id ? "bg-white shadow-[var(--shadow-card)]" : "text-ink-500 hover:bg-white/60")}>
                <span className="block truncate font-medium text-ink-800">{c.title}</span>
                <span className="text-[11.5px] text-ink-400">{relativeTime(c.updated_at)}</span>
              </Link>
            </li>
          ))}
        </ul>
      </aside>
      {id ? <Chat id={id} onNew={() => start()} /> : (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <p className="display text-2xl">Your travel assistant</p>
          <p className="mt-2 max-w-md text-[14.5px] text-ink-500">It reads your actual trips, checks conflicts and finds activities. It prepares bookings, but only you can approve them.</p>
          <Button className="mt-6" onClick={() => start()} icon={<MessageCirclePlus className="h-4 w-4" />}>Start a conversation</Button>
        </div>
      )}
    </div>
  );
}

function Chat({ id, onNew }: { id: string; onNew: () => void }) {
  const conv = useConversation(id);
  const [text, setText] = useState("");
  const [sending, setSending] = useState<string | null>(null);
  const qc = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const bottom = useRef<HTMLDivElement>(null);
  const trips = useTrips();

  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth" }); }, [conv.data?.messages.length, sending]);

  const send = async (content: string) => {
    if (!content.trim() || sending) return;
    setSending(content);
    setText("");
    try {
      const payload = await api.post<ConversationPayload>(`/assistant/conversations/${id}/messages`, { content });
      qc.setQueryData(keys.conversation(id), payload);
      qc.invalidateQueries({ queryKey: keys.conversations });
      qc.invalidateQueries({ queryKey: keys.approvals });
      qc.invalidateQueries({ queryKey: ["trip"] });
    } catch (e) {
      toast(errorMessage(e), "error");
      setText(content);
    } finally {
      setSending(null);
    }
  };
  const submit = (e: FormEvent) => { e.preventDefault(); send(text); };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(text); } };

  if (conv.isLoading) return <PageLoader />;
  if (!conv.data) return null;
  const { conversation, messages, actions } = conv.data;
  const trip = trips.data?.find((t) => t.id === conversation.trip_id);

  return (
    <section className="flex min-h-[70vh] flex-col rounded-[22px] border border-sand-200 bg-white lg:min-h-0">
      <header className="flex items-center justify-between gap-3 border-b border-sand-100 px-4 py-3 sm:px-5">
        <div className="min-w-0">
          <p className="truncate text-[14.5px] font-semibold">{conversation.title}</p>
          {trip && <Link to={`/trips/${trip.id}`} className="text-[12.5px] text-lagoon-600 hover:underline">Context: {trip.name}</Link>}
        </div>
        <div className="flex gap-1">
          <Button size="sm" variant="ghost" onClick={onNew} className="xl:hidden" icon={<Plus className="h-3.5 w-3.5" />}>New</Button>
          <button aria-label="Delete conversation" className="rounded-lg p-2 text-ink-300 hover:bg-sand-100 hover:text-rose-ink" onClick={async () => {
            if (!confirm("Delete this conversation?")) return;
            await api.del(`/assistant/conversations/${id}`);
            qc.invalidateQueries({ queryKey: keys.conversations });
            navigate("/assistant");
          }}><Trash2 className="h-4 w-4" /></button>
        </div>
      </header>

      <div className="flex-1 space-y-6 overflow-y-auto px-4 py-5 sm:px-6">
        {messages.length === 0 && !sending && (
          <div className="py-6">
            <p className="display text-xl">How can I help with your trip?</p>
            <div className="mt-4 grid gap-2 sm:grid-cols-2">
              {PROMPTS.map((p) => <button key={p} onClick={() => send(p)} className="rounded-xl border border-sand-200 px-3.5 py-3 text-left text-[13.5px] text-ink-700 transition hover:border-lagoon-500/40 hover:bg-lagoon-50/40">{p}</button>)}
            </div>
          </div>
        )}
        {messages.map((m) => <Bubble key={m.id} m={m} actions={actions} tripId={conversation.trip_id ?? undefined} />)}
        {sending && (
          <>
            <div className="flex justify-end"><div className="max-w-[85%] rounded-2xl rounded-br-md bg-lagoon-900 px-4 py-2.5 text-[14.5px] text-white">{sending}</div></div>
            <div className="flex items-center gap-2 text-[13px] text-ink-400"><Loader2 className="h-4 w-4 animate-spin" /> Checking your trip data…</div>
          </>
        )}
        <div ref={bottom} />
      </div>

      <form onSubmit={submit} className="border-t border-sand-100 p-3 sm:p-4">
        <div className="flex items-end gap-2 rounded-2xl border border-sand-200 bg-paper px-3 py-2 focus-within:border-lagoon-500 focus-within:ring-4 focus-within:ring-lagoon-100">
          <textarea rows={1} value={text} onChange={(e) => setText(e.target.value)} onKeyDown={onKey} placeholder="Ask about your trip…" aria-label="Message"
            className="max-h-40 min-h-[36px] flex-1 resize-none bg-transparent py-1.5 text-[15px] outline-none placeholder:text-ink-300" />
          <Button type="submit" size="sm" disabled={!text.trim()} loading={!!sending} aria-label="Send" className="!h-9 !w-9 !p-0"><ArrowUp className="h-4 w-4" /></Button>
        </div>
        <p className="mt-2 px-1 text-[11.5px] text-ink-400">The assistant can prepare bookings but never completes one without your approval.</p>
      </form>
    </section>
  );
}

function Bubble({ m, actions, tripId }: { m: Message; actions: ConversationPayload["actions"]; tripId?: string }) {
  if (m.role === "user") {
    return <div className="flex justify-end"><div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-lagoon-900 px-4 py-2.5 text-[14.5px] text-white">{m.content}</div></div>;
  }
  const activities = m.references.filter((r) => r.type === "activity" && r.activity).slice(0, 3);
  const links = m.references.filter((r) => r.type === "trip" || r.type === "reservation");
  return (
    <div className="max-w-[92%] space-y-3">
      {m.tool_calls.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {m.tool_calls.map((t, i) => (
            <span key={i} className={clsx("inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11.5px]", t.status === "ok" ? "bg-sand-100 text-ink-500" : "bg-rose-soft text-rose-ink")}>
              {t.status === "ok" ? <Wrench className="h-3 w-3" /> : <CircleAlert className="h-3 w-3" />}
              {TOOL_LABEL[t.name] ?? t.name}{t.summary && t.summary !== "Done" ? ` · ${t.summary}` : ""}
            </span>
          ))}
        </div>
      )}
      <div className="prose-chat rounded-2xl rounded-bl-md bg-sand-50 px-4 py-3 text-[14.5px] text-ink-800"><ReactMarkdown>{m.content}</ReactMarkdown></div>
      {activities.length > 0 && (
        <div className="grid gap-3 2xl:grid-cols-2">
          {activities.map((r) => <ActivityCard key={r.id} a={r.activity as ActivityResult & typeof r.activity} tripId={r.trip_id ?? tripId} date={r.date} />)}
        </div>
      )}
      {m.action_ids.map((aid) => actions[aid] && <ActionCard key={aid} action={actions[aid]} />)}
      <div className="flex flex-wrap items-center gap-2 text-[11.5px] text-ink-400">
        {m.provider === "local" ? <Badge tone="neutral">Offline assistant</Badge> : m.provider && <span>{m.provider} · {m.model}</span>}
        {links.slice(0, 4).map((r) => (
          <Link key={r.id} to={r.type === "trip" ? `/trips/${r.id}` : `/trips/${r.trip_id}`} className="text-lagoon-600 hover:underline">{r.label}</Link>
        ))}
      </div>
    </div>
  );
}
