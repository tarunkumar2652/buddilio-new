import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Sparkles, Send, RotateCcw, Loader2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { SEO } from "@/components/Shared";

const SESSION_KEY = "bud_ai_session";
const newSession = () =>
  (window.crypto?.randomUUID?.() || `s-${Date.now()}-${Math.random().toString(16).slice(2)}`);

// Buddy answers in light markdown: [label](/path) links and **bold**.
const Rich = ({ text }) => {
  const nodes = [];
  const re = /\[([^\]]+)\]\((\/[^)\s]*)\)|\*\*([^*]+)\*\*/g;
  let last = 0, m, k = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    if (m[1]) {
      nodes.push(
        <Link key={k++} to={m[2]} className="font-semibold text-brand-magenta underline decoration-brand-pink/50 underline-offset-2 hover:decoration-brand-magenta">
          {m[1]}
        </Link>
      );
    } else {
      nodes.push(<strong key={k++} className="font-bold">{m[3]}</strong>);
    }
    last = m.index + m[0].length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return <span className="whitespace-pre-wrap leading-relaxed">{nodes}</span>;
};

const Bubble = ({ role, children, testid }) => (
  <div className={`flex ${role === "user" ? "justify-end" : "justify-start"}`} data-testid={testid}>
    <div className={`max-w-[85%] sm:max-w-[75%] rounded-2xl px-4 py-3 text-sm ${
      role === "user"
        ? "bg-slate-900 text-white rounded-br-md"
        : "border border-slate-200 bg-white text-slate-800 rounded-bl-md shadow-[0_2px_10px_rgba(42,8,54,0.05)]"}`}>
      {children}
    </div>
  </div>
);

export default function Concierge() {
  const { user } = useAuth();
  const [sid, setSid] = useState(() => {
    const s = localStorage.getItem(SESSION_KEY) || newSession();
    localStorage.setItem(SESSION_KEY, s);
    return s;
  });
  const [cfg, setCfg] = useState(null);
  const [msgs, setMsgs] = useState([]);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef(null);

  useEffect(() => { api.get("/ai/config").then(({ data }) => setCfg(data)).catch(() => setCfg({ enabled: false })); }, []);

  useEffect(() => {
    api.get("/ai/history", { params: { session_id: sid } })
      .then(({ data }) => setMsgs(data.messages)).catch(() => setMsgs([]));
  }, [sid]);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [msgs, streaming]);

  const ask = useCallback(async (text) => {
    const body = (text || "").trim();
    if (!body || busy) return;
    setDraft("");
    setMsgs((m) => [...m, { role: "user", content: body }]);
    setBusy(true);
    setStreaming("");
    let acc = "";
    try {
      const res = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/ai/concierge`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("bud_token") || ""}`,
        },
        body: JSON.stringify({ session_id: sid, message: body }),
      });
      if (!res.ok) {
        const j = await res.json().catch(() => ({}));
        throw new Error(j.detail || "Buddy is unavailable right now.");
      }
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const frames = buf.split("\n\n");
        buf = frames.pop();
        for (const f of frames) {
          const line = f.split("\n").find((l) => l.startsWith("data: "));
          if (!line) continue;
          const ev = JSON.parse(line.slice(6));
          if (ev.delta) { acc += ev.delta; setStreaming(acc); }
          if (ev.error) toast.error(ev.error);
        }
      }
      if (acc.trim()) setMsgs((m) => [...m, { role: "assistant", content: acc.trim() }]);
      setCfg((c) => (c ? { ...c, used_today: (c.used_today || 0) + 1 } : c));
    } catch (e) {
      toast.error(e.message || errMsg(e));
    } finally {
      setStreaming("");
      setBusy(false);
    }
  }, [busy, sid]);

  const reset = () => {
    const s = newSession();
    localStorage.setItem(SESSION_KEY, s);
    setMsgs([]);
    setStreaming("");
    setSid(s);
  };

  const left = cfg ? Math.max(0, (cfg.daily_cap || 0) - (cfg.used_today || 0)) : null;

  return (
    <div className="mx-auto max-w-3xl px-4 sm:px-6 py-8 pb-28 md:pb-12" data-testid="ai-page">
      <SEO title="Buddy AI" description="Ask Buddy what's on tonight, who to go with and how Buddilio works." />

      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="overline inline-flex items-center gap-1.5"><Sparkles className="h-3.5 w-3.5" />Buddy AI</p>
          <h1 className="mt-2 text-3xl sm:text-4xl font-bold">What are we doing this week?</h1>
          <p className="mt-2 text-sm text-slate-500">
            Buddy knows every live Buddilio event{user?.city ? ` in ${user.city}` : ""} and can plan your night out.
          </p>
        </div>
        <button onClick={reset} data-testid="ai-new-chat"
          className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2 text-xs font-bold transition-colors hover:border-slate-900">
          <RotateCcw className="h-3.5 w-3.5" />New chat
        </button>
      </div>

      {cfg && !cfg.enabled && (
        <p className="mt-6 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900" data-testid="ai-disabled">
          Buddy AI isn't switched on for this environment yet.
        </p>
      )}

      <div className="mt-7 rounded-3xl border border-slate-200 bg-slate-50/60 p-4 sm:p-5">
        <div className="min-h-[320px] space-y-3" data-testid="ai-thread">
          {!msgs.length && !streaming && (
            <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-6 text-center" data-testid="ai-empty">
              <Sparkles className="mx-auto h-6 w-6 text-brand-magenta" />
              <p className="mt-3 font-semibold">Ask Buddy anything about going out</p>
              <p className="mt-1 text-sm text-slate-500">Events, safety, memberships, or who to bring along.</p>
            </div>
          )}
          {msgs.map((m, i) => (
            <Bubble key={i} role={m.role} testid={`ai-msg-${m.role}-${i}`}>
              <Rich text={m.content} />
            </Bubble>
          ))}
          {streaming && (
            <Bubble role="assistant" testid="ai-streaming"><Rich text={streaming} /></Bubble>
          )}
          {busy && !streaming && (
            <Bubble role="assistant" testid="ai-thinking">
              <span className="inline-flex items-center gap-2 text-slate-500">
                <Loader2 className="h-4 w-4 animate-spin" />Buddy is thinking…
              </span>
            </Bubble>
          )}
          <div ref={endRef} />
        </div>

        {!!cfg?.suggestions?.length && !msgs.length && (
          <div className="mt-4 flex flex-wrap gap-2" data-testid="ai-suggestions">
            {cfg.suggestions.map((s, i) => (
              <button key={s} onClick={() => ask(s)} disabled={busy} data-testid={`ai-suggestion-${i}`}
                className="rounded-full border border-slate-200 bg-white px-3.5 py-2 text-xs font-semibold transition-colors hover:border-brand-magenta hover:text-brand-magenta disabled:opacity-50">
                {s}
              </button>
            ))}
          </div>
        )}

        <form onSubmit={(e) => { e.preventDefault(); ask(draft); }} className="mt-4 flex items-center gap-2">
          <input value={draft} onChange={(e) => setDraft(e.target.value)} data-testid="ai-input"
            placeholder="What's on in my city this Friday?" maxLength={1000}
            disabled={busy || (cfg && !cfg.enabled)}
            className="flex-1 rounded-full border border-slate-200 bg-white px-5 py-3.5 text-sm outline-none focus:ring-2 focus:ring-brand-magenta disabled:opacity-60" />
          <button type="submit" disabled={busy || !draft.trim() || (cfg && !cfg.enabled)} data-testid="ai-send"
            className="shrink-0 grid place-items-center h-12 w-12 rounded-full brand-gradient text-white shadow-[0_6px_18px_rgba(232,30,124,0.26)] transition-transform hover:scale-[1.04] active:scale-95 disabled:opacity-50 disabled:hover:scale-100">
            {busy ? <Loader2 className="h-5 w-5 animate-spin" /> : <Send className="h-5 w-5" />}
          </button>
        </form>

        <p className="mt-3 text-[11px] text-slate-400" data-testid="ai-footnote">
          Buddy only recommends live Buddilio events and can get details wrong — always check the event page.
          {left !== null && ` ${left} questions left today.`}
        </p>
      </div>
    </div>
  );
}
