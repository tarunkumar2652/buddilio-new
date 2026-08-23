import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Globe, Send, RefreshCw, CheckCircle2, XCircle, Copy, Search, ExternalLink, AlertTriangle } from "lucide-react";
import { api, errMsg, fmtDate } from "@/lib/api";
import { Spinner, Badge } from "@/components/Shared";
import { PublishButton } from "@/components/PublishButton";

const CARD = "rounded-2xl border border-slate-200 bg-white p-5";
const PILL = "rounded-full px-4 py-2 text-xs font-bold transition-colors";
const IN = "mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm";

const Copyable = ({ label, value, testid }) => (
  <div className="flex flex-wrap items-center gap-2 text-xs">
    <span className="w-36 shrink-0 font-bold text-slate-600">{label}</span>
    <span className="min-w-0 flex-1 truncate font-semibold text-slate-700" data-testid={testid}>{value}</span>
    <button type="button" onClick={() => { navigator.clipboard?.writeText(value); toast.success("Copied"); }}
      className="text-slate-400 hover:text-slate-700"><Copy className="h-3.5 w-3.5" /></button>
  </div>
);

const Status = ({ ok, good, bad }) => (
  <span className={`inline-flex items-center gap-1.5 text-xs font-bold ${ok ? "text-emerald-700" : "text-amber-700"}`}>
    {ok ? <CheckCircle2 className="h-3.5 w-3.5" /> : <AlertTriangle className="h-3.5 w-3.5" />}
    {ok ? good : bad}
  </span>
);

const Step = ({ n, children }) => (
  <li className="flex gap-2.5 text-xs text-slate-600">
    <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-slate-900 text-[10px] font-bold text-white">{n}</span>
    <span className="pt-0.5">{children}</span>
  </li>
);

const Out = ({ to, children }) => (
  <a href={to} target="_blank" rel="noreferrer"
    className="inline-flex items-center gap-1 font-bold text-brand-magenta hover:underline">
    {children}<ExternalLink className="h-3 w-3" />
  </a>
);

export const SeoIndexing = () => {
  const [d, setD] = useState(null);
  const [form, setForm] = useState({ site_url: "", gsc_verification: "" });
  const [busy, setBusy] = useState("");
  const [term, setTerm] = useState("");

  const load = useCallback(() => {
    api.get("/admin/seo").then(({ data }) => {
      setD(data);
      setForm({ site_url: data.site_url || "", gsc_verification: data.gsc_verification || "" });
    }).catch((e) => toast.error(errMsg(e)));
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = async (e) => {
    e.preventDefault();
    setBusy("save");
    try { const { data } = await api.put("/admin/seo", form); toast.success(data.message); load(); }
    catch (e2) { toast.error(errMsg(e2)); } finally { setBusy(""); }
  };

  const submit = async (scope) => {
    setBusy(scope);
    try {
      const { data } = await api.post("/admin/seo/submit", { scope });
      data.ok ? toast.success(data.message) : toast.error(data.message);
      load();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(""); }
  };

  const rotate = async () => {
    setBusy("key");
    try { const { data } = await api.post("/admin/seo/indexnow-key"); toast.success(data.message); load(); }
    catch (e) { toast.error(errMsg(e)); } finally { setBusy(""); }
  };

  if (!d) return <Spinner />;
  const urls = d.urls.filter((u) => u.toLowerCase().includes(term.toLowerCase()));
  const host = (d.site_url || "").replace(/^https?:\/\//, "");

  return (
    <div className="space-y-6" data-testid="seo-panel">
      <div className={CARD}>
        <p className="flex items-center gap-2 text-sm font-black"><Globe className="h-4 w-4" />Your pages</p>
        <p className="mt-1 text-xs text-slate-500">
          {d.total} indexable pages, rebuilt live from your content. Every search engine below reads the same
          sitemap.
        </p>
        <div className="mt-4 flex flex-wrap gap-2" data-testid="seo-groups">
          {Object.entries(d.groups).map(([k, v]) => <Badge key={k} tone="slate">{k}: {v}</Badge>)}
        </div>
        {!d.stories && (
          <p className="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-800"
            data-testid="seo-no-stories">
            No published Journal stories on this site yet — write or publish one in Journal (blog) so
            search engines have articles to index. Stories don't copy between preview and the live site.
          </p>
        )}
        <div className="mt-4 grid gap-2">
          <Copyable label="Sitemap" value={d.sitemap_url} testid="seo-sitemap-url" />
          <Copyable label="Robots" value={d.robots_url} testid="seo-robots-url" />
        </div>
        <div className="mt-4 border-t border-slate-100 pt-4">
          <p className="text-xs text-slate-500">
            Anything saved here — verification tags, key files, new stories — reaches your live pages the
            moment you publish.
          </p>
          <PublishButton className="mt-3" onDone={load} />
        </div>
      </div>

      {/* ---------- Google ---------- */}
      <div className={CARD} data-testid="seo-google">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm font-black">Google Search Console</p>
          <Status ok={d.gsc_live} good="Tag live on your site" bad="Tag not live yet" />
        </div>
        <ol className="mt-4 space-y-2.5">
          <Step n={1}>Open <Out to="https://search.google.com/search-console">Search Console</Out> → Add
            property → <b>URL prefix</b> → <code>{d.site_url}</code></Step>
          <Step n={2}>Choose the <b>HTML tag</b> method, copy the token and paste it in the box further down,
            then <b>Save</b> and <b>Republish</b> the site.</Step>
          <Step n={3}>Back in Search Console press <b>Verify</b>.</Step>
          <Step n={4}>Go to <b>Sitemaps</b>, paste <code>api/sitemap.xml</code> and submit.</Step>
          <Step n={5}>For a single new story use <b>URL inspection</b> → paste the article address →
            <b> Request indexing</b>. Google has no bulk submit API, so this is the fastest route for Google.</Step>
        </ol>
        {!d.gsc_live && d.gsc_verification && (
          <p className="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-800"
            data-testid="seo-gsc-pending">
            Your token is saved but isn't in the live HTML yet — hit Republish, then press Verify in Search Console.
          </p>
        )}
      </div>

      {/* ---------- Bing ---------- */}
      <div className={CARD} data-testid="seo-bing">
        <p className="text-sm font-black">Bing Webmaster Tools (also feeds Yahoo & DuckDuckGo)</p>
        <ol className="mt-4 space-y-2.5">
          <Step n={1}>Open <Out to="https://www.bing.com/webmasters">Bing Webmaster Tools</Out> and choose
            <b> Import from Google Search Console</b> — it copies the site and verification across in one click.</Step>
          <Step n={2}>Or add <code>{d.site_url}</code> manually and verify with the same HTML tag method.</Step>
          <Step n={3}>Submit the sitemap: <code>{d.sitemap_url}</code></Step>
          <Step n={4}>Then use the IndexNow push below whenever you publish — Bing crawls those within hours.</Step>
        </ol>
      </div>

      {/* ---------- IndexNow ---------- */}
      <div className={CARD} data-testid="seo-indexnow">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm font-black">Instant push (IndexNow: Bing, Yandex, Seznam, Naver)</p>
          <Status ok={d.key_file_live} good="Key file verified" bad="Key file not live" />
        </div>
        <p className="mt-1 text-xs text-slate-500">
          One click sends every address straight to the engines. Yandex, Seznam and Naver accept it too.
          Google does not take submissions this way — use Search Console above.
        </p>
        {d.key_file_url && <div className="mt-3"><Copyable label="Key file" value={d.key_file_url} testid="seo-key-url" /></div>}
        {!!d.pending_key && (
          <p className="mt-3 rounded-xl bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-600"
            data-testid="seo-key-pending">
            A new key is staged and takes over automatically once you republish. Until then the current
            key keeps working — nothing breaks.
          </p>
        )}
        {!d.key_file_live && (
          <p className="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-800"
            data-testid="seo-key-warning">
            Bing checks that key file before it accepts anything (that's the “Site Verification is not completed”
            error). Press <b>Republish</b> so the file goes live on {host || "your domain"}, then submit again.
          </p>
        )}
        {!d.can_submit && (
          <p className="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-800"
            data-testid="seo-submit-blocked">
            Set your live address (e.g. https://buddilio.com) below — search engines can't crawl the preview.
          </p>
        )}
        <div className="mt-4 flex flex-wrap gap-2">
          <button disabled={!d.can_submit || !!busy} onClick={() => submit("all")} data-testid="seo-submit-all"
            className={`${PILL} bg-slate-900 text-white disabled:opacity-50 inline-flex items-center gap-2`}>
            <Send className="h-3.5 w-3.5" />{busy === "all" ? "Sending…" : "Submit every page"}
          </button>
          <button disabled={!d.can_submit || !!busy} onClick={() => submit("blog")} data-testid="seo-submit-blog"
            className={`${PILL} border border-slate-200 disabled:opacity-50`}>
            {busy === "blog" ? "Sending…" : "Journal only"}
          </button>
          <button disabled={!!busy} onClick={rotate} data-testid="seo-rotate-key"
            className={`${PILL} border border-slate-200 inline-flex items-center gap-2 disabled:opacity-50`}>
            <RefreshCw className="h-3.5 w-3.5" />New key
          </button>
        </div>
        {d.last_submit && (
          <div className="mt-4 rounded-xl bg-slate-50 p-3 text-xs" data-testid="seo-last-submit">
            <p className="font-bold text-slate-700">
              Last push: {d.last_submit.count} URLs · {d.last_submit.scope} · {fmtDate(d.last_submit.at)}
              {d.last_submit.by ? ` · ${d.last_submit.by}` : ""}
            </p>
            <ul className="mt-2 space-y-1">
              {(d.last_submit.results || []).map((r, i) => (
                <li key={i} className="flex items-start gap-2" data-testid={`seo-result-${i}`}>
                  {r.ok ? <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-600" />
                    : <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-rose-600" />}
                  <span className="font-semibold">{r.engine}</span>
                  <span className="min-w-0 text-slate-500">HTTP {r.status} {r.detail}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <form onSubmit={save} className={CARD} data-testid="seo-settings-form">
        <p className="text-sm font-black">Site address & Google token</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <label className="block"><span className="text-xs font-bold text-slate-600">Live site address</span>
            <input value={form.site_url} onChange={(e) => setForm({ ...form, site_url: e.target.value })}
              placeholder="https://buddilio.com" className={IN} data-testid="seo-site-url" /></label>
          <label className="block"><span className="text-xs font-bold text-slate-600">Google Search Console token</span>
            <input value={form.gsc_verification} data-testid="seo-gsc"
              onChange={(e) => setForm({ ...form, gsc_verification: e.target.value })}
              placeholder="paste the whole <meta> tag or just the content value" className={IN} /></label>
        </div>
        <p className="mt-2 text-xs text-slate-500">
          Paste it, save, then <b>Republish</b> — the token only reaches the live HTML on a publish.
        </p>
        <button disabled={busy === "save"} data-testid="seo-save"
          className={`${PILL} mt-4 bg-slate-900 text-white disabled:opacity-50`}>
          {busy === "save" ? "Saving…" : "Save"}
        </button>
      </form>

      <div className={CARD}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm font-black">Indexable URLs</p>
          <label className="relative">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
            <input value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Filter…"
              data-testid="seo-url-filter"
              className="rounded-full border border-slate-200 py-2 pl-9 pr-4 text-sm" />
          </label>
        </div>
        <ul className="mt-3 max-h-80 divide-y divide-slate-100 overflow-y-auto text-xs" data-testid="seo-url-list">
          {urls.map((u) => <li key={u} className="py-2 font-semibold text-slate-600">{u}</li>)}
          {!urls.length && <li className="py-2 text-slate-400">Nothing matches that.</li>}
        </ul>
      </div>
    </div>
  );
};
