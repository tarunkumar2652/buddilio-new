import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2, ArrowUp, ArrowDown, Save, RotateCcw } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { ImageUpload } from "@/components/ImageUpload";
import { RichText } from "@/components/RichText";
import { Spinner, Empty, Badge } from "@/components/Shared";

const fieldCls = "mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm";
const L = ({ label, children }) => (
  <label className="block"><span className="text-xs font-bold text-slate-600">{label}</span>{children}</label>
);

const BLANK = {
  slug: "", title: "", content: "", blocks: [], seo_title: "", seo_description: "",
  status: "published", nav_header: false, nav_footer_group: "", nav_label: "", order: 0,
};
const BLOCK_BLANK = { type: "text", heading: "", text: "", image: "", items: [], cta_label: "", cta_url: "" };

const BlockEditor = ({ block, onChange, onRemove, onMove, index, types }) => (
  <div className="rounded-2xl border border-slate-200 bg-slate-50/60 p-4" data-testid={`block-${index}`}>
    <div className="flex flex-wrap items-center gap-2">
      <select value={block.type} onChange={(e) => onChange({ ...block, type: e.target.value })}
        data-testid={`block-type-${index}`} className="rounded-xl border border-slate-200 px-2 py-1.5 text-xs font-bold">
        {types.map((t) => <option key={t} value={t}>{t}</option>)}
      </select>
      <span className="text-[11px] text-slate-400">Block {index + 1}</span>
      <div className="ml-auto flex gap-1">
        <button onClick={() => onMove(-1)} data-testid={`block-up-${index}`} className="rounded-full border border-slate-200 bg-white p-1.5"><ArrowUp className="h-3.5 w-3.5" /></button>
        <button onClick={() => onMove(1)} data-testid={`block-down-${index}`} className="rounded-full border border-slate-200 bg-white p-1.5"><ArrowDown className="h-3.5 w-3.5" /></button>
        <button onClick={onRemove} data-testid={`block-remove-${index}`} className="rounded-full border border-slate-200 bg-white p-1.5 text-rose-600"><Trash2 className="h-3.5 w-3.5" /></button>
      </div>
    </div>

    {["heading", "text", "richtext", "quote", "cta", "faq", "list", "html"].includes(block.type) && (
      <L label="Heading">
        <input value={block.heading} data-testid={`block-heading-${index}`}
          onChange={(e) => onChange({ ...block, heading: e.target.value })} className={fieldCls} />
      </L>
    )}
    {["text", "richtext", "quote", "cta", "faq", "html"].includes(block.type) && (
      <L label="Text — use the toolbar to format">
        <RichText value={block.text} rows={block.type === "richtext" || block.type === "html" ? 8 : 4}
          testid={`block-text-${index}`} onChange={(html) => onChange({ ...block, text: html })} />
      </L>
    )}
    {block.type === "image" && (
      <div className="mt-2">
        <ImageUpload value={block.image} onChange={(url) => onChange({ ...block, image: url })}
          label="Image" testid={`block-image-${index}`} />
      </div>
    )}
    {["list", "faq"].includes(block.type) && (
      <L label={block.type === "faq" ? "Q&A lines — “Question | Answer”" : "List items (one per line)"}>
        <textarea rows={5} value={(block.items || []).join("\n")} data-testid={`block-items-${index}`}
          onChange={(e) => onChange({ ...block, items: e.target.value.split("\n") })} className={fieldCls} />
      </L>
    )}
    {block.type === "cta" && (
      <div className="mt-2 grid gap-3 sm:grid-cols-2">
        <L label="Button label"><input value={block.cta_label} data-testid={`block-cta-label-${index}`}
          onChange={(e) => onChange({ ...block, cta_label: e.target.value })} className={fieldCls} /></L>
        <L label="Button link"><input value={block.cta_url} data-testid={`block-cta-url-${index}`}
          onChange={(e) => onChange({ ...block, cta_url: e.target.value })} className={fieldCls} /></L>
      </div>
    )}
  </div>
);

export const Pages = () => {
  const [items, setItems] = useState(null);
  const [types, setTypes] = useState(["text"]);
  const [missing, setMissing] = useState([]);
  const [sel, setSel] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get("/admin/pages").then(({ data }) => {
      setItems(data.items); setTypes(data.block_types); setMissing(data.missing_policy_pages || []);
    }).catch((e) => { toast.error(errMsg(e)); setItems([]); });
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = async () => {
    setBusy(true);
    try {
      const body = { ...sel, blocks: (sel.blocks || []).map((b) => ({ ...b, items: (b.items || []).filter(Boolean) })) };
      const { data } = sel.id ? await api.put(`/admin/pages/${sel.id}`, body) : await api.post("/admin/pages", body);
      toast.success(sel.id ? "Page saved." : "Page created.");
      setSel(data); load();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  const remove = async () => {
    if (!window.confirm(`Delete /p/${sel.slug}? This can't be undone.`)) return;
    try { await api.delete(`/admin/pages/${sel.id}`); toast.success("Page deleted."); setSel(null); load(); }
    catch (e) { toast.error(errMsg(e)); }
  };

  const setBlock = (i, b) => setSel((p) => ({ ...p, blocks: p.blocks.map((x, n) => (n === i ? b : x)) }));
  const moveBlock = (i, dir) => setSel((p) => {
    const next = p.blocks.slice();
    const j = i + dir;
    if (j < 0 || j >= next.length) return p;
    [next[i], next[j]] = [next[j], next[i]];
    return { ...p, blocks: next };
  });

  if (!items) return <Spinner />;

  return (
    <div className="space-y-4" data-testid="pages-wrap">
      {missing.length > 0 && (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-5" data-testid="pages-missing-banner">
          <p className="font-bold">{missing.length} standard page{missing.length === 1 ? "" : "s"} missing on this environment</p>
          <p className="mt-1 text-sm text-slate-600">
            Missing: {missing.join(", ")}. Footer links to these pages will look empty until they are filled.
          </p>
          <button onClick={async () => {
            try {
              const { data } = await api.post("/admin/cms/seed-policies?mode=missing");
              toast.success(`Added ${data.created.length} page(s).`); load();
            } catch (e) { toast.error(errMsg(e)); }
          }} data-testid="pages-missing-fill"
            className="mt-3 rounded-full bg-slate-900 px-5 py-2.5 text-xs font-bold text-white">
            Fill missing pages now
          </button>
        </div>
      )}
    <div className="grid lg:grid-cols-[300px_1fr] gap-6" data-testid="pages-panel">
      <div className="space-y-2">
        <button onClick={() => setSel({ ...BLANK })} data-testid="page-new"
          className="w-full inline-flex items-center justify-center gap-2 rounded-full bg-slate-900 px-4 py-2.5 text-sm font-bold text-white">
          <Plus className="h-4 w-4" />New page
        </button>
        <button onClick={async () => {
          if (!window.confirm("Fill any missing standard policy/information pages? Existing pages are left untouched.")) return;
          try {
            const { data } = await api.post("/admin/cms/seed-policies?mode=missing");
            toast.success(data.created.length ? `Added ${data.created.length} page(s): ${data.created.join(", ")}` : "Nothing missing — all standard pages exist.");
            load();
          } catch (e) { toast.error(errMsg(e)); }
        }} data-testid="page-seed-policies"
          className="w-full rounded-full border border-slate-200 px-4 py-2.5 text-xs font-bold">
          Fill missing policy pages
        </button>
        <button onClick={async () => {
          if (!window.confirm("Refresh ALL standard policy/information pages with Buddilio's full content? Your current version of each page is archived in version history first, and any wording you added yourself will be replaced.")) return;
          try {
            const { data } = await api.post("/admin/cms/seed-policies?mode=all");
            toast.success(`Refreshed ${data.updated.length + data.created.length} page(s).`);
            load();
          } catch (e) { toast.error(errMsg(e)); }
        }} data-testid="page-refresh-policies"
          className="w-full rounded-full border border-amber-300 bg-amber-50 px-4 py-2.5 text-xs font-bold text-amber-800">
          Refresh all standard pages (overwrites)
        </button>
        {items.map((p) => (
          <button key={p.id} onClick={() => setSel({ ...BLANK, ...p, blocks: p.blocks || [] })}
            data-testid={`page-select-${p.slug}`}
            className={`w-full rounded-xl border p-4 text-left ${sel?.id === p.id ? "border-slate-900 bg-slate-50" : "border-slate-200 bg-white"}`}>
            <p className="flex items-center gap-2 text-sm font-semibold">{p.title}
              {p.status === "draft" && <Badge tone="amber">draft</Badge>}</p>
            <p className="text-xs text-slate-500">/p/{p.slug}</p>
          </button>
        ))}
      </div>

      <div>
        {!sel ? <Empty title="Pick a page" sub="Choose a page to edit, or create a new one." /> : (
          <div className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5" data-testid="page-editor">
            <div className="grid gap-3 sm:grid-cols-2">
              <L label="Title"><input value={sel.title} data-testid="page-title"
                onChange={(e) => setSel({ ...sel, title: e.target.value })} className={fieldCls} /></L>
              <L label="Slug (page lives at /p/slug)"><input value={sel.slug} data-testid="page-slug"
                onChange={(e) => setSel({ ...sel, slug: e.target.value })} className={fieldCls} /></L>
              <L label="Status"><select value={sel.status} data-testid="page-status"
                onChange={(e) => setSel({ ...sel, status: e.target.value })} className={fieldCls}>
                <option value="published">Published</option><option value="draft">Draft</option>
              </select></L>
              <L label="Footer group"><select value={sel.nav_footer_group} data-testid="page-footer-group"
                onChange={(e) => setSel({ ...sel, nav_footer_group: e.target.value })} className={fieldCls}>
                {["", "Explore", "Company", "Trust & Safety"].map((g) => <option key={g} value={g}>{g || "Not in footer"}</option>)}
              </select></L>
              <L label="Menu label (optional)"><input value={sel.nav_label} data-testid="page-nav-label"
                onChange={(e) => setSel({ ...sel, nav_label: e.target.value })} className={fieldCls} /></L>
              <label className="mt-6 flex items-center gap-2 text-sm font-semibold">
                <input type="checkbox" checked={!!sel.nav_header} data-testid="page-nav-header"
                  onChange={(e) => setSel({ ...sel, nav_header: e.target.checked })} />
                Show in the header menu
              </label>
            </div>

            <L label="Intro text (used when there are no blocks)">
              <RichText value={sel.content} rows={5} testid="page-content"
                onChange={(html) => setSel({ ...sel, content: html })} />
            </L>

            <div>
              <div className="flex items-center justify-between">
                <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Content blocks</p>
                <button onClick={() => setSel({ ...sel, blocks: [...(sel.blocks || []), { ...BLOCK_BLANK }] })}
                  data-testid="page-add-block"
                  className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 px-3.5 py-1.5 text-xs font-bold">
                  <Plus className="h-3.5 w-3.5" />Add block
                </button>
              </div>
              <div className="mt-3 space-y-3">
                {(sel.blocks || []).map((b, i) => (
                  <BlockEditor key={i} index={i} block={b} types={types}
                    onChange={(nb) => setBlock(i, nb)} onMove={(d) => moveBlock(i, d)}
                    onRemove={() => setSel({ ...sel, blocks: sel.blocks.filter((_, n) => n !== i) })} />
                ))}
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <L label="SEO title"><input value={sel.seo_title} data-testid="page-seo-title"
                onChange={(e) => setSel({ ...sel, seo_title: e.target.value })} className={fieldCls} /></L>
              <L label="SEO description"><input value={sel.seo_description} data-testid="page-seo-desc"
                onChange={(e) => setSel({ ...sel, seo_description: e.target.value })} className={fieldCls} /></L>
            </div>

            <div className="flex flex-wrap gap-2">
              <button onClick={save} disabled={busy} data-testid="page-save"
                className="inline-flex items-center gap-2 rounded-full bg-slate-900 px-6 py-2.5 text-sm font-bold text-white disabled:opacity-50">
                <Save className="h-4 w-4" />{sel.id ? "Save page" : "Create page"}
              </button>
              {sel.id && (
                <>
                  <a href={`/p/${sel.slug}`} target="_blank" rel="noreferrer" data-testid="page-preview"
                    className="rounded-full border border-slate-200 px-5 py-2.5 text-sm font-bold">Preview</a>
                  <button onClick={remove} data-testid="page-delete"
                    className="inline-flex items-center gap-2 rounded-full border border-slate-200 px-5 py-2.5 text-sm font-bold text-rose-600">
                    <Trash2 className="h-4 w-4" />Delete
                  </button>
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
    </div>
  );
};

export const SiteContent = () => {
  const [content, setContent] = useState(null);
  const [raw, setRaw] = useState({});

  const load = useCallback(() => {
    api.get("/admin/site-content").then(({ data }) => {
      setContent(data.content);
      setRaw(Object.fromEntries(Object.entries(data.content).filter(([k]) => k !== "pages")
        .map(([k, v]) => [k, JSON.stringify(v, null, 2)])));
    }).catch((e) => { toast.error(errMsg(e)); setContent({}); });
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = async (key) => {
    let data;
    try { data = JSON.parse(raw[key]); }
    catch { return toast.error("That isn't valid JSON — check the quotes and commas."); }
    try { await api.put(`/admin/site-content/${key}`, { data }); toast.success(`${key} saved.`); load(); }
    catch (e) { toast.error(errMsg(e)); }
  };

  const reset = async (key) => {
    if (!window.confirm(`Reset ${key} back to the Buddilio default?`)) return;
    try { await api.delete(`/admin/site-content/${key}`); toast.success("Reset."); load(); }
    catch (e) { toast.error(errMsg(e)); }
  };

  if (!content) return <Spinner />;
  const keys = Object.keys(raw);

  return (
    <div className="space-y-5" data-testid="site-content-panel">
      <p className="text-sm text-slate-500">
        Hero, steps, stats, testimonials, header menu and footer columns — edit the values and save. Every change
        goes live immediately.
      </p>
      {keys.map((k) => (
        <div key={k} className="rounded-2xl border border-slate-200 bg-white p-5" data-testid={`section-${k}`}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-bold capitalize">{k.replace(/_/g, " ")}</p>
            <div className="flex gap-2">
              <button onClick={() => save(k)} data-testid={`section-save-${k}`}
                className="inline-flex items-center gap-1.5 rounded-full bg-slate-900 px-4 py-2 text-xs font-bold text-white">
                <Save className="h-3.5 w-3.5" />Save
              </button>
              <button onClick={() => reset(k)} data-testid={`section-reset-${k}`}
                className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 px-4 py-2 text-xs font-bold">
                <RotateCcw className="h-3.5 w-3.5" />Reset
              </button>
            </div>
          </div>
          <textarea rows={Math.min(18, (raw[k].match(/\n/g) || []).length + 2)} value={raw[k]}
            data-testid={`section-json-${k}`} onChange={(e) => setRaw({ ...raw, [k]: e.target.value })}
            className="mt-3 w-full rounded-xl border border-slate-200 bg-slate-50/60 p-3 font-mono text-xs" />
        </div>
      ))}
    </div>
  );
};

export const CityGuides = () => {
  const [items, setItems] = useState(null);
  const [sel, setSel] = useState(null);
  const [g, setG] = useState(null);
  const [raw, setRaw] = useState(false);
  const [text, setText] = useState("");

  const load = useCallback(() => {
    api.get("/admin/city-guides").then(({ data }) => setItems(data.items))
      .catch((e) => { toast.error(errMsg(e)); setItems([]); });
  }, []);
  useEffect(() => { load(); }, [load]);

  const pick = (it) => {
    setSel(it);
    setG({ areas: [], venues: [], faqs: [], ...it.guide });
    setText(JSON.stringify(it.guide, null, 2));
  };

  const save = async () => {
    let guide = g;
    if (raw) {
      try { guide = JSON.parse(text); } catch { return toast.error("That isn't valid JSON."); }
    }
    try {
      await api.put(`/admin/city-guides/${sel.slug}`, { guide });
      toast.success("Guide saved."); load();
    } catch (e) { toast.error(errMsg(e)); }
  };

  const reset = async () => {
    try {
      const { data } = await api.delete(`/admin/city-guides/${sel.slug}`);
      setG({ areas: [], venues: [], faqs: [], ...data.guide });
      setText(JSON.stringify(data.guide, null, 2));
      toast.success("Back to the default."); load();
    } catch (e) { toast.error(errMsg(e)); }
  };

  const setArea = (i, j, val) => {
    const areas = g.areas.map((a, x) => (x === i ? a.map((v, y) => (y === j ? val : v)) : a));
    setG({ ...g, areas });
  };
  const setVenue = (i, key, val) => {
    const venues = g.venues.map((v, x) => (x === i ? { ...v, [key]: val } : v));
    setG({ ...g, venues });
  };
  const field = "mt-1.5 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm";

  if (!items) return <Spinner />;

  return (
    <div className="grid lg:grid-cols-[280px_1fr] gap-6" data-testid="city-guides-panel">
      <div className="max-h-[520px] space-y-2 overflow-y-auto pr-1">
        {items.map((it) => (
          <button key={it.slug} onClick={() => pick(it)} data-testid={`guide-select-${it.slug}`}
            className={`w-full rounded-xl border p-3 text-left text-sm ${sel?.slug === it.slug ? "border-slate-900 bg-slate-50" : "border-slate-200 bg-white"}`}>
            <span className="font-semibold">{it.city}</span>
            {it.custom && <Badge tone="green">edited</Badge>}
          </button>
        ))}
      </div>
      <div>
        {!sel ? <Empty title="Pick a city" sub="Choose a city to edit its guide, venues, FAQs and local tips." /> : (
          <div className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5" data-testid="guide-editor">
            <div className="flex items-center justify-between">
              <p className="text-sm font-bold">{sel.city}</p>
              <button onClick={() => { setRaw(!raw); setText(JSON.stringify(g, null, 2)); }}
                data-testid="guide-toggle-raw"
                className="rounded-full border border-slate-200 px-4 py-1.5 text-[11px] font-bold">
                {raw ? "Use the form" : "Edit as JSON"}
              </button>
            </div>

            {raw ? (
              <textarea rows={20} value={text} data-testid="guide-json" onChange={(e) => setText(e.target.value)}
                className="w-full rounded-xl border border-slate-200 bg-slate-50/60 p-3 font-mono text-xs" />
            ) : (
              <div className="space-y-5">
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="block text-xs font-bold text-slate-500">SEO title
                    <input value={g.seo_title || ""} data-testid="guide-seo-title" className={field}
                      onChange={(e) => setG({ ...g, seo_title: e.target.value })}
                      placeholder={`Things to do in ${sel.city} — Buddilio`} /></label>
                  <label className="block text-xs font-bold text-slate-500">SEO description
                    <input value={g.seo_description || ""} data-testid="guide-seo-desc" className={field}
                      onChange={(e) => setG({ ...g, seo_description: e.target.value })} /></label>
                </div>
                <label className="block text-xs font-bold text-slate-500">Intro
                  <textarea rows={4} value={g.intro || ""} data-testid="guide-intro" className={field}
                    onChange={(e) => setG({ ...g, intro: e.target.value })} /></label>
                <div className="grid gap-3 sm:grid-cols-3">
                  <label className="block text-xs font-bold text-slate-500">When to go
                    <textarea rows={3} value={g.when || ""} data-testid="guide-when" className={field}
                      onChange={(e) => setG({ ...g, when: e.target.value })} /></label>
                  <label className="block text-xs font-bold text-slate-500">Getting around
                    <textarea rows={3} value={g.around || ""} data-testid="guide-around" className={field}
                      onChange={(e) => setG({ ...g, around: e.target.value })} /></label>
                  <label className="block text-xs font-bold text-slate-500">Local tip
                    <textarea rows={3} value={g.tip || ""} data-testid="guide-tip" className={field}
                      onChange={(e) => setG({ ...g, tip: e.target.value })} /></label>
                </div>

                <div>
                  <p className="text-xs font-bold uppercase tracking-wider text-slate-400">Areas</p>
                  {(g.areas || []).map((a, i) => (
                    <div key={i} className="mt-2 grid gap-2 sm:grid-cols-[1fr_2fr_1fr]" data-testid={`guide-area-${i}`}>
                      <input value={a[0] || ""} placeholder="Area name" className={field}
                        data-testid={`guide-area-name-${i}`} onChange={(e) => setArea(i, 0, e.target.value)} />
                      <input value={a[1] || ""} placeholder="What it's good for" className={field}
                        data-testid={`guide-area-blurb-${i}`} onChange={(e) => setArea(i, 1, e.target.value)} />
                      <input value={a[2] || ""} placeholder="Photo URL" className={field}
                        data-testid={`guide-area-photo-${i}`} onChange={(e) => setArea(i, 2, e.target.value)} />
                    </div>
                  ))}
                  <button onClick={() => setG({ ...g, areas: [...(g.areas || []), ["", "", ""]] })}
                    data-testid="guide-add-area"
                    className="mt-2 rounded-full border border-slate-200 px-4 py-1.5 text-[11px] font-bold">Add area</button>
                </div>

                <div>
                  <p className="text-xs font-bold uppercase tracking-wider text-slate-400">Top venues</p>
                  {(g.venues || []).map((v, i) => (
                    <div key={i} className="mt-2 grid gap-2 sm:grid-cols-5" data-testid={`guide-venue-${i}`}>
                      <input value={v.name || ""} placeholder="Name" className={field}
                        data-testid={`guide-venue-name-${i}`} onChange={(e) => setVenue(i, "name", e.target.value)} />
                      <input value={v.type || ""} placeholder="Type" className={field}
                        data-testid={`guide-venue-type-${i}`} onChange={(e) => setVenue(i, "type", e.target.value)} />
                      <input value={v.area || ""} placeholder="Area" className={field}
                        data-testid={`guide-venue-area-${i}`} onChange={(e) => setVenue(i, "area", e.target.value)} />
                      <input value={v.note || ""} placeholder="Why go" className={field}
                        data-testid={`guide-venue-note-${i}`} onChange={(e) => setVenue(i, "note", e.target.value)} />
                      <div className="flex gap-1">
                        <input value={v.url || ""} placeholder="Link (optional)" className={field}
                          data-testid={`guide-venue-url-${i}`} onChange={(e) => setVenue(i, "url", e.target.value)} />
                        <button onClick={() => setG({ ...g, venues: g.venues.filter((_, x) => x !== i) })}
                          data-testid={`guide-venue-remove-${i}`}
                          className="mt-1.5 rounded-lg border border-slate-200 px-2 text-xs">✕</button>
                      </div>
                    </div>
                  ))}
                  <button onClick={() => setG({ ...g, venues: [...(g.venues || []), { name: "", type: "", area: "", note: "", url: "" }] })}
                    data-testid="guide-add-venue"
                    className="mt-2 rounded-full border border-slate-200 px-4 py-1.5 text-[11px] font-bold">Add venue</button>
                </div>
              </div>
            )}

            <div className="flex gap-2">
              <button onClick={save} data-testid="guide-save"
                className="rounded-full bg-slate-900 px-6 py-2.5 text-sm font-bold text-white">Save guide</button>
              <button onClick={reset} data-testid="guide-reset"
                className="rounded-full border border-slate-200 px-5 py-2.5 text-sm font-bold">Reset to default</button>
              <a href={`/city/${sel.slug}`} target="_blank" rel="noreferrer" data-testid="guide-preview"
                className="rounded-full border border-slate-200 px-5 py-2.5 text-sm font-bold">Preview page</a>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
