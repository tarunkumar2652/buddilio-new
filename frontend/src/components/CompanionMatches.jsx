import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Sparkles, MessageCircle, RefreshCw } from "lucide-react";
import { api, errMsg, fileUrl, fmtDate } from "@/lib/api";
import { Badge } from "@/components/Shared";

export const CompanionMatches = ({ ev }) => {
  const nav = useNavigate();
  const [state, setState] = useState({ loading: true, items: [], enabled: true });
  const [sending, setSending] = useState("");

  const load = (refresh = 0) => {
    setState((s) => ({ ...s, loading: true }));
    api.get(`/events/${ev.id}/ai-companions`, { params: refresh ? { refresh: 1 } : {} })
      .then(({ data }) => setState({ loading: false, items: data.items || [], enabled: data.enabled }))
      .catch(() => setState({ loading: false, items: [], enabled: true }));
  };

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [ev.id]);

  const message = async (person) => {
    setSending(person.id);
    try {
      const first = (person.full_name || "there").split(" ")[0];
      const { data } = await api.post("/conversations", { user_id: person.id });
      await api.post(`/conversations/${data.id}/messages`, {
        body: `Hey ${first}! Are you going to "${ev.title}" on ${fmtDate(ev.starts_at)}? `
          + `Thought I'd say hi before it — ${window.location.origin}/events/${ev.id}`,
      });
      toast.success("Message sent — carry on in your inbox.");
      nav(`/messages?c=${data.id}`);
    } catch (e) {
      toast.error(errMsg(e));
    } finally { setSending(""); }
  };

  if (!state.enabled || (!state.loading && !state.items.length)) return null;

  return (
    <div data-testid="ai-companions-section">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="overline inline-flex items-center gap-1.5 text-brand-magenta">
            <Sparkles className="h-3.5 w-3.5" />Buddy suggests
          </p>
          <h2 className="mt-2 text-2xl font-bold">Who to message about this</h2>
        </div>
        <button onClick={() => load(1)} disabled={state.loading} data-testid="ai-companions-refresh"
          className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2 text-xs font-bold transition-colors hover:border-slate-900 disabled:opacity-50">
          <RefreshCw className={`h-3.5 w-3.5 ${state.loading ? "animate-spin" : ""}`} />Refresh
        </button>
      </div>

      {state.loading ? (
        <div className="mt-4 space-y-3" data-testid="ai-companions-loading">
          {[0, 1, 2].map((i) => (
            <div key={i} className="flex items-center gap-4 rounded-2xl border border-slate-200 bg-white p-4">
              <div className="h-14 w-14 rounded-full bg-slate-100 animate-pulse" />
              <div className="flex-1 space-y-2">
                <div className="h-3.5 w-1/3 rounded bg-slate-100 animate-pulse" />
                <div className="h-3 w-2/3 rounded bg-slate-100 animate-pulse" />
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="mt-4 space-y-3">
          {state.items.map((p) => (
            <div key={p.id} data-testid={`ai-companion-${p.id}`}
              className="flex flex-wrap items-center gap-4 rounded-2xl border border-slate-200 bg-white p-4">
              <Link to={`/u/${p.id}`} className="shrink-0">
                {p.photo ? (
                  <img src={fileUrl(p.photo)} alt={p.full_name} className="h-14 w-14 rounded-full object-cover ring-2 ring-brand-pink/30" />
                ) : (
                  <span className="h-14 w-14 rounded-full brand-gradient text-white grid place-items-center font-bold">
                    {p.full_name?.[0]}
                  </span>
                )}
              </Link>
              <div className="min-w-[180px] flex-1">
                <div className="flex items-center gap-2">
                  <Link to={`/u/${p.id}`} className="font-semibold hover:text-brand-magenta">
                    {p.full_name.split(" ")[0]}
                  </Link>
                  {p.going && <Badge tone="green">Already going</Badge>}
                  {p.city && <span className="text-xs text-slate-400">{p.city}</span>}
                </div>
                <p className="mt-1.5 text-xs font-semibold leading-relaxed text-slate-600" data-testid={`ai-companion-why-${p.id}`}>
                  <Sparkles className="mr-1.5 -mt-0.5 inline h-3.5 w-3.5 text-brand-magenta" />{p.why}
                </p>
              </div>
              <button onClick={() => message(p)} disabled={sending === p.id} data-testid={`ai-companion-message-${p.id}`}
                className="inline-flex items-center gap-2 rounded-full bg-slate-900 px-4 py-2.5 text-sm font-bold text-white transition-colors hover:bg-slate-800 disabled:opacity-60">
                <MessageCircle className="h-4 w-4" />{sending === p.id ? "Sending…" : "Message"}
              </button>
            </div>
          ))}
          <p className="text-[11px] text-slate-400">
            Buddy suggests people with something in common — always meet in the public venue listed.
          </p>
        </div>
      )}
    </div>
  );
};
