import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Globe, Send, RefreshCw, CheckCircle2, XCircle, Copy, Search } from "lucide-react";
import { api, errMsg, fmtDate } from "@/lib/api";
import { Spinner, Badge } from "@/components/Shared";

const CARD = "rounded-2xl border border-slate-200 bg-white p-5";
const PILL = "rounded-full px-4 py-2 text-xs font-bold transition-colors";
const IN = "mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm";

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

  return (
    <div className="space-y-6" data-testid="seo-panel">
      <div className={CARD}>
        <p className="flex items-center gap-2 text-sm font-black"><Globe className="h-4 w-4" />Search engines</p>
        <p className="mt-1 text-xs text-slate-500">
          {d.total} indexable pages, rebuilt live from your content. The Journal ships as real HTML in every
          publish, so crawlers read the words without running JavaScript.
        </p>
        <div className="mt-4 flex flex-wrap gap-2" data-testid="seo-groups">
          {Object.entries(d.groups).map(([k, v]) => (
            <Badge key={k} tone="slate">{k}: {v}</Badge>
          ))}
        </div>
        <div className="mt-4 grid gap-2 text-xs">
          {[["Sitemap", d.sitemap_url], ["Robots", d.robots_url], ["IndexNow key file", d.key_file_url]]
            .filter(([, v]) => v).map(([label, url]) => (
              <div key={label} className="flex flex-wrap items-center gap-2">
                <span className="w-32 font-bold text-slate-600">{label}</span>
                <a href={url} target="_blank" rel="noreferrer" data-testid={`seo-link-${label.split(" ")[0].toLowerCase()}`}
                  className="truncate font-semibold text-brand-magenta hover:underline">{url}</a>
                <button type="button" onClick={() => { navigator.clipboard?.writeText(url); toast.success("Copied"); }}
                  className="text-slate-400 hover:text-slate-700"><Copy className="h-3.5 w-3.5" /></button>
              </div>
            ))}
        </div>
      </div>

      <div className={CARD}>
        <p className="text-sm font-black">Push pages to search engines</p>
        <p className="mt-1 text-xs text-slate-500">
          Sends your URLs straight to Bing, Yandex, Seznam and Naver via IndexNow — usually crawled within
          hours. Google no longer accepts submissions this way: verify the site below, then use “Request
          indexing” inside Google Search Console.
        </p>
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
            <RefreshCw className="h-3.5 w-3.5" />New IndexNow key
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
                <li key={i} className="flex items-center gap-2" data-testid={`seo-result-${i}`}>
                  {r.ok ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                    : <XCircle className="h-3.5 w-3.5 text-rose-600" />}
                  <span className="font-semibold">{r.engine}</span>
                  <span className="text-slate-500">HTTP {r.status} {r.detail}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <form onSubmit={save} className={CARD} data-testid="seo-settings-form">
        <p className="text-sm font-black">Site address & Google verification</p>
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
          In Search Console pick “HTML tag”, paste it here, republish the site, then hit Verify.
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
          {urls.map((u) => (
            <li key={u} className="py-2 font-semibold text-slate-600">{u}</li>
          ))}
          {!urls.length && <li className="py-2 text-slate-400">Nothing matches that.</li>}
        </ul>
      </div>
    </div>
  );
};
