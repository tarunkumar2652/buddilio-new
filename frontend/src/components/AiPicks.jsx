import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Sparkles, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import { EventCard } from "@/components/Cards";

export const AiPicks = () => {
  const [state, setState] = useState({ loading: true, items: [], enabled: true });

  const load = (refresh = 0) => {
    setState((s) => ({ ...s, loading: true }));
    api.get("/ai/picks", { params: refresh ? { refresh: 1 } : {} })
      .then(({ data }) => setState({ loading: false, items: data.items || [], enabled: data.enabled }))
      .catch(() => setState({ loading: false, items: [], enabled: true }));
  };

  useEffect(() => { load(); }, []);

  if (!state.enabled || (!state.loading && !state.items.length)) return null;

  return (
    <section className="mt-14" data-testid="ai-picks-section">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="overline inline-flex items-center gap-1.5 text-brand-magenta">
            <Sparkles className="h-3.5 w-3.5" />Picked for you by Buddy
          </p>
          <h2 className="mt-2 text-2xl font-bold">Three nights that fit you</h2>
        </div>
        <div className="flex items-center gap-3">
          <Link to="/ai" data-testid="ai-picks-chat" className="text-xs font-bold text-slate-500 hover:text-brand-magenta">
            Ask Buddy for more →
          </Link>
          <button onClick={() => load(1)} disabled={state.loading} data-testid="ai-picks-refresh"
            className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2 text-xs font-bold transition-colors hover:border-slate-900 disabled:opacity-50">
            <RefreshCw className={`h-3.5 w-3.5 ${state.loading ? "animate-spin" : ""}`} />Refresh
          </button>
        </div>
      </div>

      {state.loading ? (
        <div className="mt-5 grid sm:grid-cols-2 lg:grid-cols-3 gap-6" data-testid="ai-picks-loading">
          {[0, 1, 2].map((i) => (
            <div key={i} className="rounded-2xl border border-slate-200 bg-white overflow-hidden">
              <div className="aspect-[4/3] bg-slate-100 animate-pulse" />
              <div className="p-5 space-y-3">
                <div className="h-4 w-3/4 rounded bg-slate-100 animate-pulse" />
                <div className="h-3 w-1/2 rounded bg-slate-100 animate-pulse" />
              </div>
            </div>
          ))}
          <p className="sr-only">Buddy is picking events for you</p>
        </div>
      ) : (
        <div className="mt-5 grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {state.items.map((ev) => (
            <div key={ev.id} className="flex flex-col" data-testid={`ai-pick-${ev.id}`}>
              <EventCard ev={ev} />
              <p className="mt-3 rounded-2xl border border-brand-pink/30 bg-brand-pink/[0.06] px-4 py-3 text-xs font-semibold leading-relaxed text-slate-700"
                data-testid={`ai-pick-why-${ev.id}`}>
                <Sparkles className="mr-1.5 -mt-0.5 inline h-3.5 w-3.5 text-brand-magenta" />{ev.why}
              </p>
            </div>
          ))}
        </div>
      )}
    </section>
  );
};
