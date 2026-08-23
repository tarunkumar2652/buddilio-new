import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2, Pencil, X, MousePointerClick, Eye, CheckCircle2, AlertTriangle } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { Spinner, Badge, Empty } from "@/components/Shared";
import { ImageUpload } from "@/components/ImageUpload";
import { PublishButton } from "@/components/PublishButton";

const PILL = "rounded-full px-4 py-2 text-xs font-bold";
const IN = "mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm";
const BLANK = { name: "", headline: "", body: "", image: "", cta_label: "Find out more", url: "",
  advertiser: "", placements: [], cities: [], priority: 5, status: "active", starts_at: "", ends_at: "" };

const Field = ({ label, hint, children }) => (
  <label className="block">
    <span className="text-xs font-bold text-slate-600">{label}</span>
    {children}
    {hint && <span className="mt-1 block text-[11px] text-slate-400">{hint}</span>}
  </label>
);

/** House ads plus the network fallback — you decide what runs where. */
export const AdsAdmin = () => {
  const [d, setD] = useState(null);
  const [f, setF] = useState(BLANK);
  const [id, setId] = useState(null);
  const [open, setOpen] = useState(false);
  const [cfg, setCfg] = useState(null);
  const [doomed, setDoomed] = useState(null);

  const load = useCallback(() => {
    api.get("/admin/ads").then(({ data }) => { setD(data); setCfg(data.config); })
      .catch((e) => { setD(false); toast.error(errMsg(e)); });
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = async (e) => {
    e.preventDefault();
    if (!f.placements.length) return toast.error("Pick at least one place for it to appear.");
    try {
      const { data } = id ? await api.put(`/admin/ads/${id}`, f) : await api.post("/admin/ads", f);
      toast.success(data.message);
      setOpen(false); setF(BLANK); setId(null); load();
    } catch (e2) { toast.error(errMsg(e2)); }
  };

  const saveCfg = async (e) => {
    e.preventDefault();
    try { const { data } = await api.put("/admin/ads-config", cfg); toast.success(data.message); load(); }
    catch (e2) { toast.error(errMsg(e2)); }
  };

  const remove = async () => {
    try { await api.delete(`/admin/ads/${doomed.id}`); toast.success("Ad removed."); setDoomed(null); load(); }
    catch (e) { toast.error(errMsg(e)); }
  };

  const toggle = async (ad) => {
    try {
      await api.put(`/admin/ads/${ad.id}`, { ...ad, status: ad.status === "active" ? "paused" : "active" });
      load();
    } catch (e) { toast.error(errMsg(e)); }
  };

  if (!d) return <Spinner />;
  if (d === false) return null;
  const label = (k) => d.placements.find((p) => p.key === k)?.label || k;

  return (
    <div className="space-y-6" data-testid="ads-admin">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-black text-slate-900">Ads</p>
          <p className="mt-0.5 text-xs text-slate-500">
            Your own banners fill the empty spaces first; the ad network only runs where nothing is scheduled.
          </p>
        </div>
        <button onClick={() => { setF(BLANK); setId(null); setOpen(true); }} data-testid="ad-new"
          className={`${PILL} bg-slate-900 text-white`}><Plus className="mr-1.5 inline h-3.5 w-3.5" />New ad</button>
      </div>

      {!d.items.length ? (
        <div className="rounded-2xl border border-slate-200 bg-white p-8">
          <Empty title="No ads yet" sub="Create one and choose which pages it appears on." />
        </div>
      ) : (
        <div className="divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white" data-testid="ads-list">
          {d.items.map((a) => (
            <div key={a.id} className="flex flex-wrap items-center gap-3 p-4" data-testid={`ad-row-${a.id}`}>
              {a.image && <img src={a.image} alt="" className="h-12 w-20 rounded-lg object-cover" />}
              <div className="min-w-[200px] flex-1">
                <p className="text-sm font-bold text-slate-900">{a.name}</p>
                <p className="mt-0.5 text-xs text-slate-500">
                  {(a.placements || []).map(label).join(" · ") || "nowhere yet"}
                  {a.starts_at || a.ends_at ? ` · ${a.starts_at || "now"} → ${a.ends_at || "no end"}` : ""}
                  {" · priority "}{a.priority}
                </p>
              </div>
              <span className="flex items-center gap-3 text-xs font-bold text-slate-500">
                <span className="inline-flex items-center gap-1" title="Views"><Eye className="h-3.5 w-3.5" />{a.views}</span>
                <span className="inline-flex items-center gap-1" title="Clicks"><MousePointerClick className="h-3.5 w-3.5" />{a.clicks}</span>
                <span title="Click-through rate">{a.ctr}%</span>
              </span>
              <button onClick={() => toggle(a)} data-testid={`ad-toggle-${a.id}`}>
                <Badge tone={a.status === "active" ? "green" : "slate"}>{a.status}</Badge>
              </button>
              <button onClick={() => { setF({ ...BLANK, ...a }); setId(a.id); setOpen(true); }}
                data-testid={`ad-edit-${a.id}`} className="p-2 text-slate-400 hover:text-slate-900">
                <Pencil className="h-4 w-4" />
              </button>
              <button onClick={() => setDoomed(a)} data-testid={`ad-delete-${a.id}`}
                className="p-2 text-slate-400 hover:text-red-600"><Trash2 className="h-4 w-4" /></button>
            </div>
          ))}
        </div>
      )}

      {cfg && (
        <form onSubmit={saveCfg} className="rounded-2xl border border-slate-200 bg-white p-5"
          data-testid="ads-head-section">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-black text-slate-900">Ad code for your &lt;head&gt;</p>
            <span className={`inline-flex items-center gap-1.5 text-xs font-bold ${d.head_live ? "text-emerald-700" : "text-amber-700"}`}
              data-testid="ads-head-status">
              {d.head_live ? <CheckCircle2 className="h-3.5 w-3.5" /> : <AlertTriangle className="h-3.5 w-3.5" />}
              {d.head_live ? "Live on your site" : "Not live yet"}
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-500">
            This is the snippet AdSense asks you to paste “between the &lt;head&gt;&lt;/head&gt; tags on
            every page”. Paste it here once — it goes into the head of every page on {d.site_url} the next
            time you <b>Publish</b>, which is what Google checks when it verifies your site.
          </p>
          <textarea rows={4} value={cfg.head_code || ""} data-testid="ads-head-code"
            onChange={(e) => setCfg({ ...cfg, head_code: e.target.value })}
            placeholder='<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-…" crossorigin="anonymous"></script>'
            className={`${IN} font-mono text-[11px]`} />
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button className={`${PILL} bg-slate-900 text-white`} data-testid="ads-head-save">Save head code</button>
            {!d.head_live && cfg.head_code && (
              <span className="text-xs font-semibold text-amber-700">
                Saved — press Publish below, then hit Verify in AdSense.
              </span>
            )}
          </div>
          <div className="mt-4 border-t border-slate-100 pt-4"><PublishButton onDone={load} /></div>
        </form>
      )}

      {cfg && (
        <form onSubmit={saveCfg} className="rounded-2xl border border-slate-200 bg-white p-5"
          data-testid="ads-config">
          <p className="text-sm font-black text-slate-900">Ad units per slot</p>
          <p className="mt-1 text-xs text-slate-500">
            Paste the code your ad provider gives you for each space. Slots where you have your own banner
            scheduled never show these.
          </p>
          <ol className="mt-4 space-y-2 rounded-xl bg-slate-50 p-4 text-xs text-slate-600">
            <li><b>1.</b> In AdSense open <b>Ads → By ad unit</b>, create a <b>Display ad</b> and press
              <b> Get code</b>.</li>
            <li><b>2.</b> Copy the whole block (both the <code>&lt;script&gt;</code> and the
              <code> &lt;ins&gt;</code> lines) and paste it against the slot you want below.</li>
            <li><b>3.</b> Tick “Show ad code” and save. Unlike the head code above, these appear straight
              away — no republish needed.</li>
          </ol>
          <label className="mt-4 flex items-center gap-2 text-sm font-semibold">
            <input type="checkbox" checked={cfg.network_enabled} data-testid="ads-network-enabled"
              onChange={(e) => setCfg({ ...cfg, network_enabled: e.target.checked })} />
            Show ad code in empty slots
          </label>

          <p className="mt-6 text-xs font-bold uppercase tracking-wide text-slate-400">Code per slot</p>
          <div className="mt-2 grid gap-3 lg:grid-cols-2">
            {d.placements.map((p) => (
              <Field key={p.key} label={p.label} hint="Paste the full ad unit code, or leave blank.">
                <textarea rows={3} value={cfg.code_slots?.[p.key] || ""} data-testid={`ads-code-${p.key}`}
                  onChange={(e) => setCfg({ ...cfg, code_slots: { ...cfg.code_slots, [p.key]: e.target.value } })}
                  className={`${IN} font-mono text-[11px]`} />
              </Field>
            ))}
          </div>

          <details className="mt-5">
            <summary className="cursor-pointer text-xs font-bold text-slate-500">
              Advanced — use publisher id + unit ids instead of pasted code
            </summary>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <Field label="Publisher id" hint="Looks like ca-pub-1234567890123456">
                <input value={cfg.network_client} data-testid="ads-network-client" className={IN}
                  onChange={(e) => setCfg({ ...cfg, network_client: e.target.value })} />
              </Field>
              {d.placements.map((p) => (
                <Field key={p.key} label={`${p.label} — unit id`}>
                  <input value={cfg.network_slots?.[p.key] || ""} className={IN} data-testid={`ads-slot-${p.key}`}
                    onChange={(e) => setCfg({ ...cfg, network_slots: { ...cfg.network_slots, [p.key]: e.target.value } })} />
                </Field>
              ))}
            </div>
          </details>

          <div className="mt-5">
            <Field label="Hide ads from these plans" hint="Ctrl/Cmd-click to choose more than one.">
              <select multiple value={cfg.hide_for_plans} className={`${IN} h-24 max-w-sm`} data-testid="ads-hide-plans"
                onChange={(e) => setCfg({ ...cfg, hide_for_plans: Array.from(e.target.selectedOptions, (o) => o.value) })}>
                {d.plans.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </Field>
          </div>
          <button className={`${PILL} mt-4 bg-slate-900 text-white`} data-testid="ads-config-save">Save ad settings</button>
        </form>
      )}

      {open && (
        <div className="fixed inset-0 z-[90] flex items-start justify-center overflow-y-auto bg-slate-900/50 p-4"
          data-testid="ad-dialog">
          <form onSubmit={save} className="my-8 w-full max-w-xl space-y-3 rounded-3xl bg-white p-6 shadow-2xl">
            <div className="flex items-center justify-between">
              <p className="text-sm font-black">{id ? "Edit ad" : "New ad"}</p>
              <button type="button" onClick={() => setOpen(false)} data-testid="ad-dialog-close"
                className="p-1.5 text-slate-400 hover:text-slate-900"><X className="h-4 w-4" /></button>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Internal name">
                <input required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })}
                  className={IN} data-testid="ad-name" />
              </Field>
              <Field label="Advertiser (shown as “Promoted · name”)">
                <input value={f.advertiser} onChange={(e) => setF({ ...f, advertiser: e.target.value })} className={IN} />
              </Field>
            </div>
            <Field label="Headline">
              <input required value={f.headline} onChange={(e) => setF({ ...f, headline: e.target.value })}
                className={IN} data-testid="ad-headline" />
            </Field>
            <Field label="Supporting line">
              <input value={f.body} onChange={(e) => setF({ ...f, body: e.target.value })} className={IN} />
            </Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Button text">
                <input value={f.cta_label} onChange={(e) => setF({ ...f, cta_label: e.target.value })} className={IN} />
              </Field>
              <Field label="Link" hint="Full web address, or /events for a Buddilio page.">
                <input required value={f.url} onChange={(e) => setF({ ...f, url: e.target.value })}
                  className={IN} data-testid="ad-url" />
              </Field>
            </div>
            <ImageUpload label="Banner image" aspect="wide" testid="ad-image"
              value={f.image} onChange={(v) => setF({ ...f, image: v })} />
            <Field label="Where it appears">
              <div className="mt-2 grid gap-1.5 sm:grid-cols-2">
                {d.placements.map((p) => (
                  <label key={p.key} className="flex items-center gap-2 text-xs font-semibold">
                    <input type="checkbox" data-testid={`ad-place-${p.key}`}
                      checked={f.placements.includes(p.key)}
                      onChange={(e) => setF({ ...f, placements: e.target.checked
                        ? [...f.placements, p.key] : f.placements.filter((x) => x !== p.key) })} />
                    {p.label}
                  </label>
                ))}
              </div>
            </Field>
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Starts" hint="Leave blank for now.">
                <input type="date" value={f.starts_at} onChange={(e) => setF({ ...f, starts_at: e.target.value })} className={IN} />
              </Field>
              <Field label="Ends" hint="Leave blank for no end.">
                <input type="date" value={f.ends_at} onChange={(e) => setF({ ...f, ends_at: e.target.value })} className={IN} />
              </Field>
              <Field label="Priority" hint="10 shows first.">
                <input type="number" min={1} max={10} value={f.priority} data-testid="ad-priority"
                  onChange={(e) => setF({ ...f, priority: Number(e.target.value) })} className={IN} />
              </Field>
            </div>
            <div className="flex gap-2 pt-2">
              <button className={`${PILL} bg-slate-900 text-white`} data-testid="ad-save">
                {id ? "Save ad" : "Create ad"}
              </button>
              <button type="button" onClick={() => setOpen(false)} className={`${PILL} border border-slate-200`}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      {doomed && (
        <div className="fixed inset-0 z-[90] grid place-items-center bg-slate-900/50 p-4" data-testid="ad-delete-dialog">
          <div className="w-full max-w-sm rounded-3xl bg-white p-6 text-center shadow-2xl">
            <p className="text-sm font-black">Remove “{doomed.name}”?</p>
            <div className="mt-5 flex justify-center gap-2">
              <button onClick={remove} className={`${PILL} bg-red-600 text-white`} data-testid="ad-delete-confirm">Remove</button>
              <button onClick={() => setDoomed(null)} className={`${PILL} border border-slate-200`}>Keep</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdsAdmin;
