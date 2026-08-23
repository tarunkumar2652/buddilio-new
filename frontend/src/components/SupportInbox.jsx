import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { MessagesSquare, Send, Search, CheckCheck, Mail } from "lucide-react";
import { api, errMsg, fmtDate } from "@/lib/api";
import { Spinner, Badge, Empty } from "@/components/Shared";

const CARD = "rounded-2xl border border-slate-200 bg-white";
const PILL = "rounded-full px-3.5 py-1.5 text-xs font-bold transition-colors";
const TONE = { open: "amber", pending: "dark", closed: "green" };

const Bubble = ({ m }) => (
  <div className={`flex ${m.role === "staff" ? "justify-end" : "justify-start"}`}
    data-testid={`support-bubble-${m.role}`}>
    <div className={`max-w-[80%] rounded-2xl px-3.5 py-2.5 text-sm ${m.role === "staff"
      ? "bg-slate-900 text-white rounded-br-md" : "border border-slate-200 bg-white rounded-bl-md"}`}>
      <p className="whitespace-pre-wrap">{m.body}</p>
      <p className={`mt-1 text-[10px] ${m.role === "staff" ? "text-slate-300" : "text-slate-400"}`}>
        {m.author || (m.role === "staff" ? "Buddilio" : "Visitor")} · {fmtDate(m.created_at)}
      </p>
    </div>
  </div>
);

export const SupportInbox = () => {
  const [list, setList] = useState(null);
  const [counts, setCounts] = useState({});
  const [status, setStatus] = useState("");
  const [term, setTerm] = useState("");
  const [active, setActive] = useState(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef(null);

  const load = useCallback(() => {
    api.get("/admin/support", { params: { status, q: term } })
      .then(({ data }) => { setList(data.items); setCounts(data.counts); })
      .catch((e) => { setList([]); toast.error(errMsg(e)); });
  }, [status, term]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const t = setInterval(load, 20000);
    return () => clearInterval(t);
  }, [load]);

  const open = async (id) => {
    try {
      const { data } = await api.get(`/admin/support/${id}`);
      setActive({ ...data.thread, ai_transcript: data.ai_transcript });
      load();
    } catch (e) { toast.error(errMsg(e)); }
  };

  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [active]);

  const reply = async (e) => {
    e.preventDefault();
    if (!draft.trim()) return;
    setBusy(true);
    try {
      await api.post(`/admin/support/${active.id}/reply`, { message: draft });
      setDraft("");
      await open(active.id);
      toast.success("Reply sent");
    } catch (e2) { toast.error(errMsg(e2)); } finally { setBusy(false); }
  };

  const setStatusOf = async (s) => {
    try {
      const { data } = await api.patch(`/admin/support/${active.id}`, { status: s });
      toast.success(data.message);
      await open(active.id);
    } catch (e) { toast.error(errMsg(e)); }
  };

  if (!list) return <Spinner />;

  return (
    <div className="space-y-4" data-testid="support-inbox">
      <div className="flex flex-wrap items-center gap-2">
        {[["", "All"], ["open", "Open"], ["pending", "Waiting on them"], ["closed", "Closed"]].map(([v, l]) => (
          <button key={v || "all"} onClick={() => { setStatus(v); setActive(null); }}
            data-testid={`support-filter-${v || "all"}`}
            className={`${PILL} ${status === v ? "bg-slate-900 text-white" : "border border-slate-200"}`}>
            {l}{v && counts[v] ? ` (${counts[v]})` : ""}
          </button>
        ))}
        {!!counts.unread && (
          <span data-testid="support-unread-badge"><Badge tone="red">{counts.unread} unread</Badge></span>
        )}
        <label className="relative ml-auto">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
          <input value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Name, email or subject"
            data-testid="support-search"
            className="rounded-full border border-slate-200 py-2 pl-9 pr-4 text-sm" />
        </label>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,340px)_minmax(0,1fr)]">
        <div className={`${CARD} max-h-[70vh] overflow-y-auto`} data-testid="support-list">
          {!list.length && <div className="p-6"><Empty title="No conversations yet"
            sub="When someone asks for a human in the Ask Buddy chat, it lands here." /></div>}
          <ul className="divide-y divide-slate-100">
            {list.map((t) => (
              <li key={t.id}>
                <button onClick={() => open(t.id)} data-testid={`support-thread-${t.id}`}
                  className={`w-full px-4 py-3 text-left transition-colors hover:bg-slate-50 ${active?.id === t.id ? "bg-slate-50" : ""}`}>
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-bold">{t.name}</span>
                    {t.unread && <span className="h-2 w-2 shrink-0 rounded-full bg-brand-magenta" />}
                    <Badge tone={TONE[t.status]}>{t.status}</Badge>
                  </div>
                  <p className="mt-0.5 truncate text-xs font-semibold text-slate-600">{t.subject}</p>
                  <p className="mt-0.5 truncate text-xs text-slate-400">
                    {t.last_role === "staff" ? "You: " : ""}{t.last_message}
                  </p>
                  <p className="mt-1 text-[10px] text-slate-400">
                    {t.is_member ? "Member" : "Visitor"} · {fmtDate(t.updated_at)}
                  </p>
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div className={`${CARD} flex min-h-[320px] flex-col`} data-testid="support-thread-panel">
          {!active ? (
            <div className="grid flex-1 place-items-center p-8 text-center">
              <p className="text-sm text-slate-500" data-testid="support-no-selection">
                <MessagesSquare className="mx-auto mb-2 h-5 w-5 text-slate-300" />
                Pick a conversation to read and reply.
              </p>
            </div>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 px-4 py-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-black" data-testid="support-active-name">{active.name}</p>
                  <p className="truncate text-xs text-slate-500 inline-flex items-center gap-1">
                    <Mail className="h-3 w-3" />{active.email || "no email"}
                  </p>
                </div>
                <div className="ml-auto flex flex-wrap gap-2">
                  {["open", "pending", "closed"].map((s) => (
                    <button key={s} onClick={() => setStatusOf(s)} data-testid={`support-status-${s}`}
                      className={`${PILL} ${active.status === s ? "bg-slate-900 text-white" : "border border-slate-200"}`}>
                      {s === "closed" ? <span className="inline-flex items-center gap-1"><CheckCheck className="h-3 w-3" />Close</span> : s}
                    </button>
                  ))}
                </div>
              </div>

              {!!active.ai_transcript?.length && (
                <div className="border-b border-slate-100 bg-slate-50/70 px-4 py-2 text-[11px] text-slate-500"
                  data-testid="support-ai-transcript">
                  <span className="font-bold">Buddy AI said before this: </span>
                  {active.ai_transcript.join(" · ").slice(0, 300)}
                </div>
              )}

              <div className="flex-1 space-y-3 overflow-y-auto bg-slate-50/50 px-4 py-4 max-h-[46vh]"
                data-testid="support-messages">
                {active.messages.map((m, i) => <Bubble key={i} m={m} />)}
                <div ref={end} />
              </div>

              <form onSubmit={reply} className="flex items-end gap-2 border-t border-slate-100 p-3">
                <textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={2} maxLength={2000}
                  placeholder="Write your reply…" data-testid="support-reply-input"
                  className="flex-1 resize-none rounded-2xl border border-slate-200 px-3.5 py-2.5 text-sm outline-none focus:ring-2 focus:ring-brand-magenta" />
                <button disabled={busy || !draft.trim()} data-testid="support-reply-send"
                  className="grid h-11 w-11 shrink-0 place-items-center rounded-full brand-gradient text-white disabled:opacity-50">
                  <Send className="h-4 w-4" />
                </button>
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
