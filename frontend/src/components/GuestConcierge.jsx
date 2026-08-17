import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Sparkles, Send, Loader2, ArrowRight } from "lucide-react";
import { api } from "@/lib/api";
import { streamAi, GUEST_QA_KEY } from "@/lib/aiStream";
import { RichText } from "@/components/Shared";

const load = () => {
  try { return JSON.parse(localStorage.getItem(GUEST_QA_KEY) || "null"); } catch { return null; }
};

export const GuestConcierge = () => {
  const [suggestions, setSuggestions] = useState([]);
  const [qa, setQa] = useState(load);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState("");
  const askedRef = useRef(!!qa);

  useEffect(() => {
    api.get("/ai/guest/config").then(({ data }) => setSuggestions(data.enabled ? data.suggestions : []))
      .catch(() => {});
  }, []);

  const ask = async (text) => {
    const q = (text || "").trim();
    if (!q || busy || askedRef.current) return;
    askedRef.current = true;
    setBusy(true);
    setDraft("");
    setLive("");
    try {
      const reply = await streamAi("/ai/guest", { message: q }, setLive);
      const next = { q, a: reply };
      localStorage.setItem(GUEST_QA_KEY, JSON.stringify(next));
      setQa(next);
    } catch (e) {
      askedRef.current = false;
      toast.error(e.message);
    } finally {
      setBusy(false);
      setLive("");
    }
  };

  return (
    <section className="mx-auto max-w-7xl px-4 sm:px-6 pb-4" data-testid="guest-ai">
      <div className="relative overflow-hidden rounded-3xl bg-slate-900 text-white p-6 sm:p-10 grain">
        <div className="pointer-events-none absolute -top-24 -right-16 h-72 w-72 rounded-full bg-brand-magenta/25 blur-3xl" />
        <div className="relative grid lg:grid-cols-[1fr_1.1fr] gap-8 lg:gap-14 items-start">
          <div>
            <p className="overline text-brand-pink inline-flex items-center gap-1.5">
              <Sparkles className="h-3.5 w-3.5" />Ask Buddy AI
            </p>
            <h2 className="mt-3 text-3xl sm:text-4xl font-bold leading-tight">
              One question, before you even sign up.
            </h2>
            <p className="mt-4 text-sm text-slate-300 max-w-md leading-relaxed">
              Buddy knows every live experience on Buddilio, in 27 cities. Ask what's on this weekend, what a
              night out costs, or how any of this works — you'll get a straight answer in seconds.
            </p>
          </div>

          <div className="rounded-2xl bg-white/[0.06] backdrop-blur-sm border border-white/10 p-4 sm:p-5">
            {qa ? (
              <div className="space-y-3" data-testid="guest-ai-answer">
                <p className="text-xs font-bold text-brand-pink" data-testid="guest-ai-question">You asked: {qa.q}</p>
                <div className="rounded-xl bg-white text-slate-800 p-4 text-sm" data-testid="guest-ai-reply">
                  <RichText text={qa.a} />
                </div>
                <div className="rounded-xl border border-white/15 bg-white/[0.04] p-4" data-testid="guest-ai-locked">
                  <p className="text-sm font-semibold">That was your free question.</p>
                  <p className="mt-1 text-xs text-slate-300">
                    Join free to keep chatting with Buddy, book experiences and message members going too.
                  </p>
                  <Link to="/register" data-testid="guest-ai-join"
                    className="mt-4 inline-flex items-center gap-2 rounded-full brand-gradient px-5 py-2.5 text-sm font-bold text-white transition-transform hover:scale-[1.03]">
                    Join Buddilio free <ArrowRight className="h-4 w-4" />
                  </Link>
                </div>
              </div>
            ) : (
              <>
                {(busy || live) && (
                  <div className="mb-3 rounded-xl bg-white text-slate-800 p-4 text-sm min-h-[52px]" data-testid="guest-ai-streaming">
                    {live ? <RichText text={live} /> : (
                      <span className="inline-flex items-center gap-2 text-slate-500">
                        <Loader2 className="h-4 w-4 animate-spin" />Buddy is thinking…
                      </span>
                    )}
                  </div>
                )}
                <form onSubmit={(e) => { e.preventDefault(); ask(draft); }} className="flex items-center gap-2">
                  <input value={draft} onChange={(e) => setDraft(e.target.value)} data-testid="guest-ai-input"
                    disabled={busy} maxLength={500} placeholder="What's on in Dubai this weekend?"
                    className="flex-1 rounded-full bg-white/95 text-slate-900 px-5 py-3.5 text-sm outline-none placeholder:text-slate-400 focus:ring-2 focus:ring-brand-pink disabled:opacity-70" />
                  <button type="submit" disabled={busy || !draft.trim()} data-testid="guest-ai-send"
                    className="shrink-0 grid place-items-center h-12 w-12 rounded-full brand-gradient text-white transition-transform hover:scale-[1.05] disabled:opacity-50">
                    {busy ? <Loader2 className="h-5 w-5 animate-spin" /> : <Send className="h-5 w-5" />}
                  </button>
                </form>
                {!!suggestions.length && (
                  <div className="mt-3 flex flex-wrap gap-2" data-testid="guest-ai-suggestions">
                    {suggestions.map((s, i) => (
                      <button key={s} onClick={() => ask(s)} disabled={busy} data-testid={`guest-ai-suggestion-${i}`}
                        className="rounded-full border border-white/20 bg-white/[0.06] px-3.5 py-2 text-xs font-semibold text-slate-200 transition-colors hover:border-brand-pink hover:text-white disabled:opacity-50">
                        {s}
                      </button>
                    ))}
                  </div>
                )}
                <p className="mt-3 text-[11px] text-slate-400">
                  Buddy only talks about real Buddilio experiences. No account needed for your first question.
                </p>
              </>
            )}
          </div>
        </div>
      </div>
    </section>
  );
};
