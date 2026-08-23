import { useEffect, useState } from "react";
import { TrendingUp, TrendingDown, Minus, Search as SearchIcon } from "lucide-react";
import { api } from "@/lib/api";
import { Spinner } from "@/components/Shared";

const SOURCE_LABEL = { search: "Search engines", social: "Social", referral: "Other sites", direct: "Direct / app" };

const Delta = ({ n }) => {
  if (!n) return <span className="inline-flex items-center gap-1 text-slate-400"><Minus className="h-3 w-3" />level</span>;
  const up = n > 0;
  return (
    <span className={`inline-flex items-center gap-1 font-bold ${up ? "text-emerald-600" : "text-rose-600"}`}>
      {up ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
      {up ? "+" : ""}{n}
    </span>
  );
};

/** Weekly readership for the Journal — which stories actually pull people in. */
export const BlogInsights = () => {
  const [days, setDays] = useState(7);
  const [d, setD] = useState(null);

  useEffect(() => {
    setD(null);
    api.get("/admin/blog/insights", { params: { days } }).then(({ data }) => setD(data)).catch(() => setD(false));
  }, [days]);

  if (d === false) return null;

  const peak = Math.max(1, ...((d?.daily || []).map((x) => x.views)));
  const totalSources = Object.values(d?.sources || {}).reduce((a, b) => a + b, 0);

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5" data-testid="blog-insights">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-black text-slate-900">Readers report</p>
          <p className="mt-0.5 text-xs text-slate-500">
            Story reads over the last {days} days, against the {days} before that.
          </p>
        </div>
        <div className="flex gap-1.5">
          {[7, 30, 90].map((v) => (
            <button key={v} onClick={() => setDays(v)} data-testid={`insights-range-${v}`}
              className={`rounded-full px-3.5 py-1.5 text-xs font-bold ${days === v ? "bg-slate-900 text-white" : "border border-slate-200"}`}>
              {v}d
            </button>
          ))}
        </div>
      </div>

      {!d ? <div className="py-8"><Spinner /></div> : (
        <>
          <div className="mt-5 flex flex-wrap items-end gap-6">
            <div>
              <p className="text-3xl font-black text-slate-900" data-testid="insights-total">{d.total}</p>
              <p className="text-xs font-bold text-slate-500">reads · <Delta n={d.total - d.previous_total} /></p>
            </div>
            <div className="flex flex-wrap gap-4" data-testid="insights-sources">
              {Object.entries(d.sources).map(([k, v]) => (
                <div key={k}>
                  <p className="text-sm font-black text-slate-900">
                    {v}{totalSources ? <span className="ml-1 text-[11px] font-bold text-slate-400">
                      {Math.round((v / totalSources) * 100)}%</span> : null}
                  </p>
                  <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400">
                    {k === "search" && <SearchIcon className="mr-1 inline h-3 w-3" />}{SOURCE_LABEL[k] || k}
                  </p>
                </div>
              ))}
            </div>
          </div>

          {!!d.daily.length && (
            <div className="mt-5 flex h-16 items-end gap-1" data-testid="insights-spark">
              {d.daily.map((x) => (
                <div key={x.day} title={`${x.day}: ${x.views}`} style={{ height: `${(x.views / peak) * 100}%` }}
                  className="min-h-[3px] flex-1 rounded-t bg-brand-magenta/70" />
              ))}
            </div>
          )}

          <ul className="mt-5 divide-y divide-slate-100" data-testid="insights-list">
            {d.items.map((p, i) => (
              <li key={p.slug} className="flex flex-wrap items-center gap-3 py-2.5 text-sm"
                data-testid={`insights-row-${p.slug}`}>
                <span className="w-5 text-xs font-bold text-slate-400">{i + 1}</span>
                <span className="min-w-[200px] flex-1 truncate font-semibold text-slate-800">{p.title}</span>
                <span className="text-xs text-slate-400">was {p.previous}</span>
                <span className="text-xs"><Delta n={p.change} /></span>
                <span className="w-12 text-right font-black text-slate-900">{p.views}</span>
              </li>
            ))}
            {!d.items.length && (
              <li className="py-4 text-sm text-slate-500" data-testid="insights-empty">
                No reads recorded yet — this fills up as people open your stories.
              </li>
            )}
          </ul>
        </>
      )}
    </div>
  );
};

export default BlogInsights;
