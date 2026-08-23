import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { toast } from "sonner";
import { MessageCircle, X, Send, Loader2, Sparkles, ArrowRight, Headphones, ChevronLeft } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { streamAi, newAiSession, GUEST_QA_KEY } from "@/lib/aiStream";
import { RichText } from "@/components/Shared";

const SESSION_KEY = "bud_ai_session";
const SUP_ID = "bud_support_id";
const SUP_TOKEN = "bud_support_token";

const loadGuestQa = () => {
  try { return JSON.parse(localStorage.getItem(GUEST_QA_KEY) || "null"); } catch { return null; }
};

/** A real conversation with the Buddilio team — replies land back in this same panel. */
const HumanChat = ({ user, transcript, onBack }) => {
  const [thread, setThread] = useState(null);
  const [form, setForm] = useState({ name: user?.full_name || "", email: user?.email || "" });
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef(null);
  const idRef = useRef(localStorage.getItem(SUP_ID) || "");
  const tokenRef = useRef(localStorage.getItem(SUP_TOKEN) || "");

  const load = useCallback(async () => {
    if (!idRef.current) return;
    try {
      const { data } = await api.get(`/support/threads/${idRef.current}`,
        { params: { token: tokenRef.current } });
      setThread(data.thread);
    } catch {
      localStorage.removeItem(SUP_ID); localStorage.removeItem(SUP_TOKEN);
      idRef.current = ""; tokenRef.current = ""; setThread(null);
    }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { const t = setInterval(load, 8000); return () => clearInterval(t); }, [load]);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [thread]);

  const send = async (e) => {
    e.preventDefault();
    const text = draft.trim();
    if (!text || busy) return;
    setBusy(true);
    try {
      if (!idRef.current) {
        const { data } = await api.post("/support/threads", {
          message: text, name: form.name, email: form.email,
          page: window.location.pathname, ai_transcript: transcript,
        });
        idRef.current = data.thread.id;
        tokenRef.current = data.token;
        localStorage.setItem(SUP_ID, data.thread.id);
        localStorage.setItem(SUP_TOKEN, data.token);
        setThread(data.thread);
        toast.success("Sent — the team replies right here.");
      } else {
        await api.post(`/support/threads/${idRef.current}/messages`,
          { message: text, token: tokenRef.current });
        await load();
      }
      setDraft("");
    } catch (e2) { toast.error(errMsg(e2)); } finally { setBusy(false); }
  };

  const needsDetails = !thread && !user;

  return (
    <div data-testid="support-chat">
      <div className="max-h-[52vh] min-h-[220px] overflow-y-auto bg-slate-50/70 px-4 py-4 space-y-3"
        data-testid="support-chat-thread">
        {!thread && (
          <p className="text-sm text-slate-500" data-testid="support-chat-intro">
            You're talking to the Buddilio team now. Tell us what's happening and we'll reply here —
            {user ? " you'll also get a notification." : " we'll email you the moment we answer."}
          </p>
        )}
        {thread?.messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "visitor" ? "justify-end" : "justify-start"}`}
            data-testid={`support-chat-msg-${m.role}-${i}`}>
            <div className={`max-w-[88%] rounded-2xl px-3.5 py-2.5 text-sm ${m.role === "visitor"
              ? "bg-slate-900 text-white rounded-br-md" : "border border-slate-200 bg-white rounded-bl-md"}`}>
              <p className="whitespace-pre-wrap">{m.body}</p>
              {m.role === "staff" && (
                <p className="mt-1 text-[10px] font-semibold text-slate-400">{m.author || "Buddilio"}</p>
              )}
            </div>
          </div>
        ))}
        {thread && thread.messages.filter((m) => m.role === "staff").length === 0 && (
          <p className="text-xs text-slate-400" data-testid="support-chat-waiting">
            Delivered. The team usually answers within a few hours.
          </p>
        )}
        <div ref={end} />
      </div>

      <form onSubmit={send} className="border-t border-slate-200 p-3 space-y-2">
        {needsDetails && (
          <div className="grid grid-cols-2 gap-2">
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="Your name" data-testid="support-chat-name"
              className="rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-brand-magenta" />
            <input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })}
              placeholder="Email for the reply" type="email" data-testid="support-chat-email"
              className="rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-brand-magenta" />
          </div>
        )}
        <div className="flex items-center gap-2">
          <input value={draft} onChange={(e) => setDraft(e.target.value)} maxLength={2000}
            placeholder="Message the team…" data-testid="support-chat-input" disabled={busy}
            className="flex-1 rounded-full border border-slate-200 px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-brand-magenta disabled:opacity-60" />
          <button type="submit" disabled={busy || !draft.trim()} data-testid="support-chat-send"
            className="shrink-0 grid place-items-center h-10 w-10 rounded-full brand-gradient text-white transition-transform hover:scale-105 disabled:opacity-50">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </button>
        </div>
        <button type="button" onClick={onBack} data-testid="support-chat-back"
          className="inline-flex items-center gap-1 text-[11px] font-semibold text-slate-500 hover:text-brand-magenta">
          <ChevronLeft className="h-3 w-3" />Back to Buddy AI
        </button>
      </form>
    </div>
  );
};

export const AiChatWidget = () => {
  const { user } = useAuth();
  const loc = useLocation();
  const isMember = !!user;
  const [open, setOpen] = useState(false);
  const [human, setHuman] = useState(false);
  const [msgs, setMsgs] = useState([]);
  const [draft, setDraft] = useState("");
  const [live, setLive] = useState("");
  const [busy, setBusy] = useState(false);
  const [suggestions, setSuggestions] = useState([]);
  const [guestLocked, setGuestLocked] = useState(false);
  const endRef = useRef(null);
  const sid = useRef(localStorage.getItem(SESSION_KEY) || newAiSession());

  useEffect(() => { localStorage.setItem(SESSION_KEY, sid.current); }, []);

  useEffect(() => {
    if (!open) return;
    const path = isMember ? "/ai/config" : "/ai/guest/config";
    api.get(path).then(({ data }) => setSuggestions(data.enabled ? (data.suggestions || []).slice(0, 3) : []))
      .catch(() => setSuggestions([]));
    if (isMember) {
      api.get("/ai/history", { params: { session_id: sid.current } })
        .then(({ data }) => setMsgs(data.messages)).catch(() => {});
    } else {
      const qa = loadGuestQa();
      if (qa) { setMsgs([{ role: "user", content: qa.q }, { role: "assistant", content: qa.a }]); setGuestLocked(true); }
    }
  }, [open, isMember]);

  useEffect(() => { if (open) endRef.current?.scrollIntoView({ block: "end" }); }, [msgs, live, open]);

  const ask = async (text) => {
    const q = (text || "").trim();
    if (!q || busy || (!isMember && guestLocked)) return;
    setDraft("");
    setMsgs((m) => [...m, { role: "user", content: q }]);
    setBusy(true);
    setLive("");
    try {
      const reply = isMember
        ? await streamAi("/ai/concierge", { session_id: sid.current, message: q }, setLive)
        : await streamAi("/ai/guest", { message: q }, setLive);
      if (reply) setMsgs((m) => [...m, { role: "assistant", content: reply }]);
      if (!isMember) {
        localStorage.setItem(GUEST_QA_KEY, JSON.stringify({ q, a: reply }));
        setGuestLocked(true);
      }
    } catch (e) {
      toast.error(e.message);
      setMsgs((m) => m.slice(0, -1));
    } finally {
      setBusy(false);
      setLive("");
    }
  };

  if (loc.pathname === "/ai") return null;

  const humanButton = (
    <button type="button" onClick={() => setHuman(true)} data-testid="ai-widget-talk-human"
      className="inline-flex items-center gap-1.5 text-[11px] font-bold text-slate-500 hover:text-brand-magenta">
      <Headphones className="h-3.5 w-3.5" />Talk to a real person
    </button>
  );

  return (
    <>
      {!open && (
        <button onClick={() => setOpen(true)} data-testid="ai-widget-open"
          className="fixed right-4 bottom-20 md:bottom-6 z-40 inline-flex items-center gap-2 rounded-full brand-gradient px-4 py-3 text-sm font-bold text-white shadow-[0_10px_30px_rgba(232,30,124,0.35)] transition-transform hover:scale-[1.04] active:scale-95">
          <MessageCircle className="h-5 w-5" />
          <span className="hidden sm:inline">Ask Buddy</span>
        </button>
      )}

      {open && (
        <div data-testid="ai-widget-panel"
          className="fixed z-50 right-2 left-2 bottom-20 sm:left-auto sm:right-4 md:bottom-6 sm:w-[380px] rounded-3xl border border-slate-200 bg-white shadow-[0_24px_70px_rgba(42,8,54,0.28)] overflow-hidden">
          <div className="flex items-center justify-between gap-3 bg-slate-900 px-4 py-3.5 text-white">
            <span className="flex items-center gap-2 text-sm font-bold">
              {human ? (
                <><Headphones className="h-4 w-4 text-brand-pink" />Buddilio team
                  <span className="text-[10px] font-semibold text-slate-400">a human replies</span></>
              ) : (
                <><Sparkles className="h-4 w-4 text-brand-pink" />Buddy AI
                  <span className="text-[10px] font-semibold text-slate-400">answers instantly</span></>
              )}
            </span>
            <button onClick={() => setOpen(false)} data-testid="ai-widget-close"
              className="p-1.5 rounded-full hover:bg-white/10 transition-colors"><X className="h-4 w-4" /></button>
          </div>

          {human ? (
            <HumanChat user={user} onBack={() => setHuman(false)}
              transcript={msgs.slice(-4).map((m) => `${m.role}: ${m.content}`)} />
          ) : (
            <>
              <div className="max-h-[52vh] min-h-[220px] overflow-y-auto px-4 py-4 space-y-3 bg-slate-50/70" data-testid="ai-widget-thread">
                {!msgs.length && !live && !busy && (
                  <p className="text-sm text-slate-500" data-testid="ai-widget-intro">
                    Hi{user?.full_name ? ` ${user.full_name.split(" ")[0]}` : ""} — ask me about events, bookings,
                    refunds, memberships or safety. I answer straight away, and I'll hand you to a human whenever
                    you want one.
                  </p>
                )}
                {msgs.map((m, i) => (
                  <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
                    data-testid={`ai-widget-msg-${m.role}-${i}`}>
                    <div className={`max-w-[88%] rounded-2xl px-3.5 py-2.5 text-sm ${m.role === "user"
                      ? "bg-slate-900 text-white rounded-br-md" : "border border-slate-200 bg-white rounded-bl-md"}`}>
                      <RichText text={m.content} />
                    </div>
                  </div>
                ))}
                {(live || busy) && (
                  <div className="flex justify-start" data-testid="ai-widget-streaming">
                    <div className="max-w-[88%] rounded-2xl rounded-bl-md border border-slate-200 bg-white px-3.5 py-2.5 text-sm">
                      {live ? <RichText text={live} /> : (
                        <span className="inline-flex items-center gap-2 text-slate-500">
                          <Loader2 className="h-4 w-4 animate-spin" />Thinking…
                        </span>
                      )}
                    </div>
                  </div>
                )}
                <div ref={endRef} />
              </div>

              {!isMember && guestLocked ? (
                <div className="border-t border-slate-200 p-4" data-testid="ai-widget-guest-locked">
                  <p className="text-sm font-semibold">That was your free question.</p>
                  <p className="mt-1 text-xs text-slate-500">Join free to keep chatting, book experiences and message members.</p>
                  <Link to="/register" onClick={() => setOpen(false)} data-testid="ai-widget-join"
                    className="mt-3 inline-flex items-center gap-2 rounded-full brand-gradient px-4 py-2.5 text-sm font-bold text-white">
                    Join Buddilio free <ArrowRight className="h-4 w-4" />
                  </Link>
                  <div className="mt-3">{humanButton}</div>
                </div>
              ) : (
                <div className="border-t border-slate-200 p-3">
                  {!!suggestions.length && !msgs.length && (
                    <div className="mb-2.5 flex flex-wrap gap-1.5" data-testid="ai-widget-suggestions">
                      {suggestions.map((s, i) => (
                        <button key={s} onClick={() => ask(s)} disabled={busy} data-testid={`ai-widget-suggestion-${i}`}
                          className="rounded-full border border-slate-200 px-3 py-1.5 text-[11px] font-semibold transition-colors hover:border-brand-magenta hover:text-brand-magenta disabled:opacity-50">
                          {s}
                        </button>
                      ))}
                    </div>
                  )}
                  <form onSubmit={(e) => { e.preventDefault(); ask(draft); }} className="flex items-center gap-2">
                    <input value={draft} onChange={(e) => setDraft(e.target.value)} data-testid="ai-widget-input"
                      disabled={busy} maxLength={isMember ? 1000 : 500} placeholder="Ask Buddy anything…"
                      className="flex-1 rounded-full border border-slate-200 px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-brand-magenta disabled:opacity-60" />
                    <button type="submit" disabled={busy || !draft.trim()} data-testid="ai-widget-send"
                      className="shrink-0 grid place-items-center h-10 w-10 rounded-full brand-gradient text-white transition-transform hover:scale-105 disabled:opacity-50">
                      {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                    </button>
                  </form>
                  <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                    {humanButton}
                    {isMember && (
                      <Link to="/ai" onClick={() => setOpen(false)} data-testid="ai-widget-fullpage"
                        className="text-[11px] font-semibold text-slate-500 hover:text-brand-magenta">
                        Open the full Buddy AI page →
                      </Link>
                    )}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </>
  );
};
