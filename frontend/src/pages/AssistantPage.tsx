import { clsx } from "clsx";
import { ArrowUp, CircleAlert, History, MessageCirclePlus, Plus, Trash2, Wrench } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import ReactMarkdown from "react-markdown";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { ActionCard } from "@/components/activities/ActionCard";
import { ActivityCard } from "@/components/activities/ActivityCard";
import { spring } from "@/components/motion";
import { Badge, Button, PageLoader } from "@/components/ui";
import { Dialog } from "@/components/ui/Dialog";
import { useToast } from "@/components/ui/Toast";
import { api, errorMessage } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import { useT, type Key } from "@/lib/i18n";
import { keys, useConversation, useConversations, useTrips, type ConversationPayload } from "@/lib/queries";
import type { ActivityResult, Conversation, Message } from "@/lib/types";

const PROMPTS: Key[] = ["assistant.prompt1", "assistant.prompt2", "assistant.prompt3", "assistant.prompt4", "assistant.prompt5", "assistant.prompt6"];

export default function AssistantPage() {
  const { id } = useParams();
  const conversations = useConversations();
  const trips = useTrips();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { t } = useT();
  const [history, setHistory] = useState(false);

  useEffect(() => {
    if (!id && conversations.data?.length) navigate(`/assistant/${conversations.data[0].id}`, { replace: true });
  }, [id, conversations.data, navigate]);

  const start = async (tripId?: string) => {
    const conv = await api.post<Conversation>("/assistant/conversations", { trip_id: tripId ?? trips.data?.find((t) => t.stats.phase !== "past")?.id ?? null });
    qc.invalidateQueries({ queryKey: keys.conversations });
    navigate(`/assistant/${conv.id}`);
  };

  return (
    <div className="grid grid-cols-1 gap-6 lg:h-[calc(100dvh-96px)] xl:grid-cols-[250px_minmax(0,1fr)]">
      <aside className="hidden flex-col xl:flex">
        <Button onClick={() => start()} icon={<Plus className="h-4 w-4" />} className="w-full">{t("assistant.new")}</Button>
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
      {id ? <Chat id={id} onNew={() => start()} onHistory={() => setHistory(true)} /> : (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <p className="display text-2xl">{t("assistant.introTitle")}</p>
          <p className="mt-2 max-w-md text-[14.5px] text-ink-500">{t("assistant.introBody")}</p>
          <Button className="mt-6" onClick={() => start()} icon={<MessageCirclePlus className="h-4 w-4" />}>{t("assistant.start")}</Button>
        </div>
      )}
      <Dialog open={history} onOpenChange={setHistory} title={t("assistant.conversations")}>
        <ul className="-mx-2 pb-2">
          {(conversations.data ?? []).map((c) => (
            <li key={c.id}>
              <Link to={`/assistant/${c.id}`} onClick={() => setHistory(false)} className={clsx("flex min-h-12 flex-col justify-center rounded-2xl px-3 py-2 transition", c.id === id ? "bg-sand-100" : "active:bg-sand-50")}>
                <span className="truncate text-[15px] font-medium text-ink-800">{c.title}</span>
                <span className="text-[12.5px] text-ink-400">{relativeTime(c.updated_at)}</span>
              </Link>
            </li>
          ))}
        </ul>
        <Button onClick={() => { setHistory(false); start(); }} icon={<Plus className="h-4 w-4" />} className="mb-2 w-full">{t("assistant.new")}</Button>
      </Dialog>
    </div>
  );
}

function Chat({ id, onNew, onHistory }: { id: string; onNew: () => void; onHistory: () => void }) {
  const conv = useConversation(id);
  const [text, setText] = useState("");
  const [sending, setSending] = useState<string | null>(null);
  const qc = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const bottom = useRef<HTMLDivElement>(null);
  const trips = useTrips();
  const { t } = useT();
  const location = useLocation();
  const asked = useRef(false);

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
  const submit = (e: SubmitEvent) => { e.preventDefault(); send(text); };
  // A question typed on Home arrives with the navigation: send it once, then drop it so a reload doesn't resend.
  useEffect(() => {
    const prompt = (location.state as { prompt?: string } | null)?.prompt;
    if (prompt && !asked.current && conv.data) {
      asked.current = true;
      navigate(location.pathname, { replace: true, state: null });
      send(prompt);
    }
  }, [conv.data]); // eslint-disable-line react-hooks/exhaustive-deps
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(text); } };

  if (conv.isLoading) return <PageLoader />;
  if (!conv.data) return null;
  const { conversation, messages, actions } = conv.data;
  const trip = trips.data?.find((t) => t.id === conversation.trip_id);

  return (
    <section className="flex min-h-[calc(100dvh-230px)] flex-col lg:min-h-0 lg:rounded-[22px] lg:border lg:border-sand-200 lg:bg-white">
      <header className="flex items-center justify-between gap-2 pb-3 lg:border-b lg:border-sand-100 lg:px-5 lg:py-3">
        <div className="min-w-0">
          <p className="display truncate text-[22px] leading-tight lg:font-sans lg:text-[14.5px] lg:font-semibold">{conversation.title}</p>
          {trip && <Link to={`/trips/${trip.id}`} className="text-[13px] text-lagoon-600 hover:underline">{t("assistant.about", { name: trip.name })}</Link>}
        </div>
        <div className="flex shrink-0 items-center">
          <button onClick={onHistory} aria-label={t("assistant.conversations")} className="flex h-11 w-11 items-center justify-center rounded-full text-ink-500 hover:bg-sand-100 active:scale-90 xl:hidden"><History className="h-5 w-5" /></button>
          <button onClick={onNew} aria-label={t("assistant.new")} className="flex h-11 w-11 items-center justify-center rounded-full text-ink-500 hover:bg-sand-100 active:scale-90 xl:hidden"><Plus className="h-5 w-5" /></button>
          <button aria-label={t("assistant.delete")} className="flex h-11 w-11 items-center justify-center rounded-full text-ink-300 hover:bg-sand-100 hover:text-rose-ink active:scale-90" onClick={async () => {
            if (!confirm(t("assistant.deleteConfirm"))) return;
            await api.del(`/assistant/conversations/${id}`);
            qc.invalidateQueries({ queryKey: keys.conversations });
            navigate("/assistant");
          }}><Trash2 className="h-[18px] w-[18px]" /></button>
        </div>
      </header>

      <div className="flex-1 space-y-5 py-2 lg:overflow-y-auto lg:px-6 lg:py-5">
        {messages.length === 0 && !sending && (
          <div className="py-4">
            <p className="kicker">{t("assistant.emptyKicker")}</p>
            <p className="display mt-1 text-[26px] leading-tight">{t("assistant.emptyTitle")}</p>
            <p className="mt-2 text-[14px] text-ink-500">{t("assistant.emptyBody")}</p>
            <div className="mt-5 grid gap-2 sm:grid-cols-2">
              {PROMPTS.map((k) => t(k)).map((p, i) => (
                <motion.button key={p} onClick={() => send(p)} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ ...spring, delay: 0.04 * i }} whileTap={{ scale: 0.97 }}
                  className="min-h-12 rounded-2xl border border-sand-200 bg-white px-4 py-3 text-left text-[14.5px] text-ink-700 transition-colors hover:border-lagoon-500/40 hover:bg-lagoon-50/40">{p}</motion.button>
              ))}
            </div>
          </div>
        )}
        <AnimatePresence initial={false}>
          {messages.map((m) => (
            <motion.div key={m.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={spring}>
              <Bubble m={m} actions={actions} tripId={conversation.trip_id ?? undefined} />
            </motion.div>
          ))}
          {sending && (
            <motion.div key="pending" className="space-y-3" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={spring}>
              <div className="flex justify-end"><div className="max-w-[85%] whitespace-pre-wrap rounded-[20px] rounded-br-md bg-lagoon-900 px-4 py-2.5 text-[15px] text-white">{sending}</div></div>
              <div className="inline-flex items-center gap-1 rounded-[20px] rounded-bl-md bg-sand-100 px-4 py-3" aria-label={t("assistant.thinking")}>
                {[0, 1, 2].map((d) => <motion.span key={d} className="h-1.5 w-1.5 rounded-full bg-ink-400" animate={{ y: [0, -3, 0], opacity: [0.4, 1, 0.4] }} transition={{ duration: 0.9, repeat: Infinity, delay: d * 0.15 }} />)}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
        <div ref={bottom} />
      </div>

      <form onSubmit={submit} className="sticky bottom-[calc(max(env(safe-area-inset-bottom),12px)+78px)] z-20 pt-3 lg:static lg:border-t lg:border-sand-100 lg:p-4">
        <div className="flex items-end gap-2 rounded-[24px] border border-sand-200 bg-white/95 py-1.5 pl-4 pr-1.5 shadow-[var(--shadow-float)] backdrop-blur focus-within:border-lagoon-500 lg:bg-paper lg:shadow-none lg:focus-within:ring-4 lg:focus-within:ring-lagoon-100">
          <textarea rows={1} value={text} onChange={(e) => setText(e.target.value)} onKeyDown={onKey} placeholder={t("assistant.placeholder")} aria-label={t("assistant.message")} enterKeyHint="send"
            className="max-h-40 min-h-[40px] flex-1 resize-none bg-transparent py-2 text-[16px] outline-none placeholder:text-ink-300 lg:text-[15px]" />
          <Button type="submit" size="sm" disabled={!text.trim()} loading={!!sending} aria-label={t("assistant.send")} className="!h-10 !w-10 shrink-0 !rounded-full !p-0"><ArrowUp className="h-[18px] w-[18px]" /></Button>
        </div>
        <p className="mt-2 hidden px-1 text-[11.5px] text-ink-400 lg:block">{t("assistant.footer")}</p>
      </form>
    </section>
  );
}

function Bubble({ m, actions, tripId }: { m: Message; actions: ConversationPayload["actions"]; tripId?: string }) {
  const { t } = useT();
  const tool = (name: string) => { const k = `tool.${name}` as Key; const x = t(k); return x === k ? name : x; };
  if (m.role === "user") {
    return <div className="flex justify-end"><div className="max-w-[85%] whitespace-pre-wrap rounded-[20px] rounded-br-md bg-lagoon-900 px-4 py-2.5 text-[15px] text-white">{m.content}</div></div>;
  }
  const activities = m.references.filter((r) => r.type === "activity" && r.activity).slice(0, 3);
  const links = m.references.filter((r) => r.type === "trip" || r.type === "reservation" || r.type === "browser_task");
  return (
    <div className="max-w-[92%] space-y-3">
      {m.tool_calls.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {m.tool_calls.map((c, i) => (
            <span key={i} className={clsx("inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11.5px]", c.status === "ok" ? "bg-sand-100 text-ink-500" : "bg-rose-soft text-rose-ink")}>
              {c.status === "ok" ? <Wrench className="h-3 w-3" /> : <CircleAlert className="h-3 w-3" />}
              {tool(c.name)}{c.summary && c.summary !== "Done" ? ` · ${c.summary}` : ""}
            </span>
          ))}
        </div>
      )}
      <div className="prose-chat rounded-[20px] rounded-bl-md bg-sand-100/70 px-4 py-3 text-[15px] text-ink-800"><ReactMarkdown>{m.content}</ReactMarkdown></div>
      {activities.length > 0 && (
        <div className="grid grid-cols-1 gap-3 2xl:grid-cols-2">
          {activities.map((r) => <ActivityCard key={r.id} a={r.activity as ActivityResult & typeof r.activity} tripId={r.trip_id ?? tripId} date={r.date} />)}
        </div>
      )}
      {m.action_ids.map((aid) => actions[aid] && <ActionCard key={aid} action={actions[aid]} />)}
      <div className="flex flex-wrap items-center gap-2 text-[11.5px] text-ink-400">
        {m.provider === "local" ? <Badge tone="neutral">{t("assistant.offline")}</Badge> : m.provider && <span>{m.provider} · {m.model}</span>}
        {links.slice(0, 4).map((r) => (
          <Link key={r.id} to={r.type === "trip" ? `/trips/${r.id}` : r.type === "browser_task" ? `/explore?tab=tickets&task=${r.id}` : `/trips/${r.trip_id}`} className="text-lagoon-600 hover:underline">{r.label}</Link>
        ))}
      </div>
    </div>
  );
}
