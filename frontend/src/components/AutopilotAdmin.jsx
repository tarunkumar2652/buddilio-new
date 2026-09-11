import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Bot, Play, Plus, Trash2, CalendarClock, FileText, AlertTriangle } from "lucide-react";
import { api, errMsg, fmtDate } from "@/lib/api";
import { Spinner, Badge, Empty } from "@/components/Shared";

const CARD = "rounded-2xl border border-slate-200 bg-white p-5";
const PILL = "rounded-full px-4 py-2 text-xs font-bold transition-colors";
const IN = "mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm";
const BLANK_SERIES = { title: "", city: "", category: "Social Gatherings", venue: "", weekday: 3,
  hour: 20, price: 0, capacity: 30, description: "", weeks_ahead: 3, active: true };

const Field = ({ label, hint, children }) => (
  <label className="block">
    <span className="text-xs font-bold text-slate-600">{label}</span>
    {children}
    {hint && <span className="mt-1 block text-[11px] text-slate-400">{hint}</span>}
  </label>
);

const Check = ({ label, hint, checked, onChange, testid }) => (
  <label className="flex gap-2.5 text-sm">
    <input type="checkbox" className="mt-0.5" checked={checked} data-testid={testid}
      onChange={(e) => onChange(e.target.checked)} />
    <span><b>{label}</b>{hint && <span className="mt-0.5 block text-xs text-slate-500">{hint}</span>}</span>
  </label>
);

/** Buddilio writing its own Journal and topping up the calendar — all switchable from here. */
export const AutopilotAdmin = () => {
  const [d, setD] = useState(null);
  const [c, setC] = useState(null);
  const [busy, setBusy] = useState(false);
  const [s, setS] = useState(BLANK_SERIES);

  const load = useCallback(() => {
    api.get("/admin/autopilot").then(({ data }) => { setD(data); setC(data.config); })
      .catch(() => setD({ config: {}, runs: [] }));
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = async (next) => {
    const body = next || c;
    try { const { data } = await api.put("/admin/autopilot", body); setC(data.config); toast.success(data.message); }
    catch (e) { toast.error(errMsg(e)); }
  };

  const runNow = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/admin/autopilot/run");
      toast.success(data.message);
      // It writes in the background — refresh the log as the work lands.
      [20000, 50000, 90000].forEach((ms) => setTimeout(load, ms));
    } catch (e) { toast.error(errMsg(e)); } finally { setTimeout(() => setBusy(false), 20000); }
  };

  const addSeries = () => {
    if (!s.title.trim() || !s.city.trim()) return toast.error("A series needs a title and a city.");
    const next = { ...c, series: [...(c.series || []), { ...s, price: Number(s.price) || 0 }] };
    setS(BLANK_SERIES);
    save(next);
  };

  const dropSeries = (i) => save({ ...c, series: c.series.filter((_, n) => n !== i) });

  if (!d || !c) return <Spinner />;

  const toggleDay = (n) => {
    const days = c.blog_days.includes(n) ? c.blog_days.filter((x) => x !== n) : [...c.blog_days, n].sort();
    setC({ ...c, blog_days: days });
  };

  return (
    <div className="space-y-5" data-testid="autopilot-panel">
      <div className={`${CARD} flex flex-wrap items-center justify-between gap-3`}>
        <div>
          <p className="inline-flex items-center gap-2 text-sm font-black text-slate-900">
            <Bot className="h-4 w-4" />Buddilio Autopilot
          </p>
          <p className="mt-1 text-xs text-slate-500">
            Writes Journal stories and keeps the events calendar stocked on its own. Runs once a day,
            or press Run now. Model: <b>{d.model}</b>.
          </p>
          {d.last_run && (
            <p className="mt-1 text-xs font-semibold text-slate-500" data-testid="autopilot-last-run">
              Last run {fmtDate(d.last_run)} · {d.stories_written} stories and {d.events_created} events
              created so far
            </p>
          )}
        </div>
        <button onClick={runNow} disabled={busy || !d.ai_ready} data-testid="autopilot-run"
          className={`${PILL} inline-flex items-center gap-2 bg-slate-900 text-white disabled:opacity-50`}>
          <Play className="h-3.5 w-3.5" />{busy ? "Working…" : "Run now"}
        </button>
      </div>

      {!d.ai_ready && (
        <p className="flex gap-2 rounded-2xl bg-amber-50 p-4 text-xs font-semibold text-amber-900"
          data-testid="autopilot-no-key">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          No AI key is configured, so Autopilot can't write anything yet.
        </p>
      )}

      {/* ---------- Journal ---------- */}
      <div className={CARD} data-testid="autopilot-blog">
        <p className="inline-flex items-center gap-2 text-sm font-black text-slate-900">
          <FileText className="h-4 w-4" />Journal stories
        </p>
        <p className="mt-1 text-xs text-slate-500">
          One original 700-1000 word story per writing day, rotating between city guides, going-out
          playbooks, safety notes and community pieces — with titles, meta description and internal links
          written for search. Search engines that accept submissions are pinged on publish; Google still
          crawls on its own schedule, so no one can promise a ranking.
        </p>
        <div className="mt-4 space-y-3">
          <Check label="Write stories automatically" checked={c.blog_enabled} testid="autopilot-blog-enabled"
            onChange={(v) => setC({ ...c, blog_enabled: v })} />
          <Check label="Publish straight away" hint="Off = stories wait in Journal → In review for you."
            checked={c.blog_publish} testid="autopilot-blog-publish"
            onChange={(v) => setC({ ...c, blog_publish: v })} />
        </div>
        <p className="mt-4 text-xs font-bold uppercase tracking-wide text-slate-400">Writing days</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {d.weekdays.map((w, n) => (
            <button key={w} type="button" onClick={() => toggleDay(n)} data-testid={`autopilot-day-${n}`}
              className={`${PILL} border ${c.blog_days.includes(n)
                ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 text-slate-600"}`}>
              {w.slice(0, 3)}
            </button>
          ))}
        </div>
        <div className="mt-4">
          <Field label="Cities to feature" hint="Comma separated. Leave blank to rotate your busiest cities.">
            <input className={IN} data-testid="autopilot-blog-cities" value={(c.blog_cities || []).join(", ")}
              placeholder={d.cities.slice(0, 4).join(", ")}
              onChange={(e) => setC({ ...c, blog_cities: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })} />
          </Field>
        </div>
      </div>

      {/* ---------- Events ---------- */}
      <div className={CARD} data-testid="autopilot-events">
        <p className="inline-flex items-center gap-2 text-sm font-black text-slate-900">
          <CalendarClock className="h-4 w-4" />Events calendar
        </p>
        <p className="mt-1 text-xs text-slate-500">
          Two jobs: it repeats any weekly series you define below, and it invents fresh curated
          experiences for cities whose calendar is looking thin. Auto events are hosted as
          “{c.events_host_name}” and go live immediately — you can edit or delete any of them under Events.
        </p>
        <div className="mt-4 space-y-3">
          <Check label="Top up thin calendars automatically" checked={c.events_enabled}
            testid="autopilot-events-enabled" onChange={(v) => setC({ ...c, events_enabled: v })} />
          <Check label="Ping search engines after publishing" checked={c.ping_search_engines}
            testid="autopilot-ping" onChange={(v) => setC({ ...c, ping_search_engines: v })} />
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Cities per run">
            <input type="number" min={0} max={10} className={IN} data-testid="autopilot-events-per-run"
              value={c.events_per_run}
              onChange={(e) => setC({ ...c, events_per_run: Number(e.target.value) })} />
          </Field>
          <Field label="Top up only below">
            <input type="number" min={0} max={100} className={IN} data-testid="autopilot-min-upcoming"
              value={c.events_min_upcoming}
              onChange={(e) => setC({ ...c, events_min_upcoming: Number(e.target.value) })} />
          </Field>
          <Field label="Days ahead to schedule">
            <input type="number" min={3} max={120} className={IN} data-testid="autopilot-days-ahead"
              value={c.events_days_ahead}
              onChange={(e) => setC({ ...c, events_days_ahead: Number(e.target.value) })} />
          </Field>
          <Field label="Host name on auto events">
            <input className={IN} data-testid="autopilot-host-name" value={c.events_host_name}
              onChange={(e) => setC({ ...c, events_host_name: e.target.value })} />
          </Field>
        </div>
        <div className="mt-3">
          <Field label="Cities to cover" hint="Comma separated. Blank = your busiest cities.">
            <input className={IN} data-testid="autopilot-events-cities" value={(c.events_cities || []).join(", ")}
              placeholder={d.cities.slice(0, 4).join(", ")}
              onChange={(e) => setC({ ...c, events_cities: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })} />
          </Field>
        </div>
      </div>

      {/* ---------- Repeating series ---------- */}
      <div className={CARD} data-testid="autopilot-series">
        <p className="text-sm font-black text-slate-900">Repeating series</p>
        <p className="mt-1 text-xs text-slate-500">
          Define an evening once — “Thursday supper club, Delhi NCR, 8pm” — and Autopilot keeps the next
          few dates on the calendar for you.
        </p>
        {(c.series || []).length ? (
          <div className="mt-4 divide-y divide-slate-100">
            {c.series.map((row, i) => (
              <div key={`${row.title}-${i}`} className="flex flex-wrap items-center justify-between gap-2 py-3"
                data-testid={`series-row-${i}`}>
                <div>
                  <p className="text-sm font-bold text-slate-900">{row.title}</p>
                  <p className="text-xs text-slate-500">
                    {row.city} · every {d.weekdays[row.weekday]} at {String(row.hour).padStart(2, "0")}:00 ·
                    {row.price > 0 ? ` $${row.price}` : " free"} · {row.capacity} places
                  </p>
                </div>
                <span className="flex items-center gap-2">
                  <Badge tone={row.active ? "green" : "slate"}>{row.active ? "on" : "off"}</Badge>
                  <button onClick={() => dropSeries(i)} data-testid={`series-delete-${i}`}
                    className="p-2 text-slate-400 hover:text-red-600"><Trash2 className="h-4 w-4" /></button>
                </span>
              </div>
            ))}
          </div>
        ) : <div className="mt-4"><Empty title="No series yet" sub="Add your first repeating evening below." /></div>}

        <div className="mt-5 grid gap-3 border-t border-slate-100 pt-5 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Title"><input className={IN} data-testid="series-title" value={s.title}
            placeholder="Thursday Supper Club" onChange={(e) => setS({ ...s, title: e.target.value })} /></Field>
          <Field label="City"><input className={IN} data-testid="series-city" value={s.city}
            placeholder={d.cities[0] || "Delhi NCR"} onChange={(e) => setS({ ...s, city: e.target.value })} /></Field>
          <Field label="Category">
            <select className={IN} data-testid="series-category" value={s.category}
              onChange={(e) => setS({ ...s, category: e.target.value })}>
              {d.event_categories.map((x) => <option key={x} value={x}>{x}</option>)}
            </select>
          </Field>
          <Field label="Every">
            <select className={IN} data-testid="series-weekday" value={s.weekday}
              onChange={(e) => setS({ ...s, weekday: Number(e.target.value) })}>
              {d.weekdays.map((w, n) => <option key={w} value={n}>{w}</option>)}
            </select>
          </Field>
          <Field label="Start hour (24h)"><input type="number" min={0} max={23} className={IN}
            data-testid="series-hour" value={s.hour}
            onChange={(e) => setS({ ...s, hour: Number(e.target.value) })} /></Field>
          <Field label="Price (USD)"><input type="number" min={0} className={IN} data-testid="series-price"
            value={s.price} onChange={(e) => setS({ ...s, price: e.target.value })} /></Field>
          <Field label="Places"><input type="number" min={2} className={IN} data-testid="series-capacity"
            value={s.capacity} onChange={(e) => setS({ ...s, capacity: Number(e.target.value) })} /></Field>
          <Field label="Dates to keep ahead"><input type="number" min={1} max={8} className={IN}
            data-testid="series-weeks" value={s.weeks_ahead}
            onChange={(e) => setS({ ...s, weeks_ahead: Number(e.target.value) })} /></Field>
          <Field label="Venue"><input className={IN} data-testid="series-venue" value={s.venue}
            placeholder="A rooftop bar in Aerocity" onChange={(e) => setS({ ...s, venue: e.target.value })} /></Field>
          <div className="sm:col-span-2 lg:col-span-3">
            <Field label="Description">
              <textarea rows={2} className={IN} data-testid="series-description" value={s.description}
                onChange={(e) => setS({ ...s, description: e.target.value })} />
            </Field>
          </div>
        </div>
        <button onClick={addSeries} data-testid="series-add"
          className={`${PILL} mt-4 inline-flex items-center gap-2 bg-slate-900 text-white`}>
          <Plus className="h-3.5 w-3.5" />Add series
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button onClick={() => save()} data-testid="autopilot-save"
          className={`${PILL} bg-brand-magenta text-white`}>Save autopilot settings</button>
        <span className="text-xs text-slate-500">Runs with the daily maintenance job.</span>
      </div>

      {/* ---------- Log ---------- */}
      <div className={CARD} data-testid="autopilot-log">
        <p className="text-sm font-black text-slate-900">What Autopilot has made</p>
        {d.runs.length ? (
          <div className="mt-3 divide-y divide-slate-100">
            {d.runs.map((r, i) => (
              <div key={`${r.at}-${i}`} className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-sm"
                data-testid={`autopilot-run-${i}`}>
                <span className="flex items-center gap-2">
                  <Badge tone={r.kind === "story" ? "green" : "slate"}>{r.kind}</Badge>
                  {r.slug
                    ? <a href={`/blog/${r.slug}`} target="_blank" rel="noreferrer"
                      className="font-semibold hover:underline">{r.title}</a>
                    : <span className="font-semibold">{r.title}</span>}
                </span>
                <span className="text-xs text-slate-500">{r.city} · {fmtDate(r.at)}</span>
              </div>
            ))}
          </div>
        ) : <p className="mt-3 text-sm text-slate-500">Nothing yet — press Run now to try it.</p>}
      </div>
    </div>
  );
};

export default AutopilotAdmin;
