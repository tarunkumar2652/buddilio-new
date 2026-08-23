import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2, ExternalLink, Star, Send, Users } from "lucide-react";
import { api, errMsg, fmtDate } from "@/lib/api";
import { Spinner, Badge } from "@/components/Shared";
import { ImageUpload } from "@/components/ImageUpload";

const PILL = "rounded-full px-4 py-2 text-xs font-bold";
const IN = "mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm";
const blank = {
  title: "", slug: "", category: "Community", excerpt: "", body: "", cover_image: "", cover_credit: "",
  author_name: "", author_role: "", tags: [], seo_title: "", seo_description: "", featured: false,
  status: "draft", cta_label: "", cta_url: "",
};

const Field = ({ label, hint, children }) => (
  <label className="block"><span className="text-xs font-bold text-slate-600">{label}</span>
    {children}
    {hint && <span className="mt-1 block text-[11px] text-slate-400">{hint}</span>}
  </label>
);

/** Admin authoring for the Journal — draft, publish, SEO and cover art in one screen. */
export const BlogAdmin = () => {
  const [list, setList] = useState(null);
  const [cats, setCats] = useState([]);
  const [f, setF] = useState(null);
  const [doomed, setDoomed] = useState(null);
  const [subs, setSubs] = useState(null);
  const [sending, setSending] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get("/admin/blog").then(({ data }) => { setList(data.items); setCats(data.categories); })
      .catch(() => setList([]));
    api.get("/admin/newsletter").then(({ data }) => setSubs(data)).catch(() => setSubs(null));
  }, []);
  useEffect(() => { load(); }, [load]);

  const sendNewsletter = async (p, force) => {
    setSending(p.id);
    try {
      const { data } = await api.post(`/admin/blog/${p.id}/newsletter`, {}, { params: { force } });
      toast.success(data.message);
      load();
    } catch (e) { toast.error(errMsg(e)); } finally { setSending(null); }
  };

  const edit = async (id) => {
    try {
      const { data } = await api.get(`/admin/blog/${id}`);
      setF({ ...blank, ...data, tags: data.tags || [] });
    } catch (e) { toast.error(errMsg(e)); }
  };

  const save = async (status) => {
    if (!f.title.trim()) return toast.error("Give the story a title.");
    if (status === "published" && f.body.trim().length < 40) return toast.error("Add the story body before publishing.");
    setBusy(true);
    const body = { ...f, status };
    try {
      const { data } = f.id ? await api.put(`/admin/blog/${f.id}`, body) : await api.post("/admin/blog", body);
      toast.success(status === "published" ? `Published at /blog/${data.slug}` : "Draft saved.");
      setF(null);
      load();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  const remove = async (p) => {
    setDoomed(p);
  };

  const confirmRemove = async () => {
    try { await api.delete(`/admin/blog/${doomed.id}`); toast.success("Deleted."); setDoomed(null); load(); }
    catch (e) { toast.error(errMsg(e)); }
  };

  if (!list) return <Spinner />;

  if (f) {
    return (
      <div className="space-y-5" data-testid="blog-editor">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-xl font-black text-slate-900">{f.id ? "Edit story" : "New story"}</h2>
          <div className="flex flex-wrap gap-2">
            <button onClick={() => save("draft")} disabled={busy} data-testid="blog-save-draft"
              className={`${PILL} border border-slate-200`}>Save draft</button>
            <button onClick={() => save("published")} disabled={busy} data-testid="blog-publish"
              className={`${PILL} bg-slate-900 text-white`}>{busy ? "Saving…" : "Publish"}</button>
            <button onClick={() => setF(null)} data-testid="blog-cancel" className={`${PILL} border border-slate-200`}>Close</button>
          </div>
        </div>

        <div className="grid gap-4 rounded-2xl border border-slate-200 bg-white p-5 lg:grid-cols-2">
          <Field label="Title">
            <input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} className={IN} data-testid="blog-title" />
          </Field>
          <Field label="Web address (leave blank to build it from the title)" hint={f.slug ? `buddilio.com/blog/${f.slug}` : ""}>
            <input value={f.slug} onChange={(e) => setF({ ...f, slug: e.target.value })} className={IN} data-testid="blog-slug" />
          </Field>
          <Field label="Category">
            <select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} className={IN} data-testid="blog-category">
              {cats.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </Field>
          <Field label="Tags (comma separated)">
            <input value={(f.tags || []).join(", ")} data-testid="blog-tags"
              onChange={(e) => setF({ ...f, tags: e.target.value.split(",").map((t) => t.trim()).filter(Boolean) })} className={IN} />
          </Field>
          <div className="lg:col-span-2">
            <Field label="Standfirst / excerpt" hint="Shown on cards and in search results. Left blank, we take the opening lines.">
              <textarea rows={2} value={f.excerpt} onChange={(e) => setF({ ...f, excerpt: e.target.value })}
                className={IN} data-testid="blog-excerpt" />
            </Field>
          </div>
          <div className="lg:col-span-2">
            <Field label="Story" hint="Basic HTML works: <p>, <h2>, <blockquote>, <ul>, <img src=…>, <a href=…>.">
              <textarea rows={14} value={f.body} onChange={(e) => setF({ ...f, body: e.target.value })}
                className={`${IN} font-mono text-xs`} data-testid="blog-body" />
            </Field>
          </div>
          <ImageUpload label="Cover image" aspect="wide" testid="blog-cover"
            value={f.cover_image} onChange={(v) => setF({ ...f, cover_image: v })} />
          <Field label="Cover credit">
            <input value={f.cover_credit} onChange={(e) => setF({ ...f, cover_credit: e.target.value })} className={IN} data-testid="blog-cover-credit" />
          </Field>
          <Field label="Author name">
            <input value={f.author_name} onChange={(e) => setF({ ...f, author_name: e.target.value })} className={IN} data-testid="blog-author" placeholder="Buddilio Editorial" />
          </Field>
          <Field label="Author role">
            <input value={f.author_role} onChange={(e) => setF({ ...f, author_role: e.target.value })} className={IN} placeholder="City editor" />
          </Field>
          <Field label="Search engine title" hint="Around 60 characters.">
            <input value={f.seo_title} onChange={(e) => setF({ ...f, seo_title: e.target.value })} className={IN} data-testid="blog-seo-title" />
          </Field>
          <Field label="Search engine description" hint="Around 155 characters.">
            <input value={f.seo_description} onChange={(e) => setF({ ...f, seo_description: e.target.value })} className={IN} data-testid="blog-seo-description" />
          </Field>
          <Field label="Call-to-action heading">
            <input value={f.cta_label} onChange={(e) => setF({ ...f, cta_label: e.target.value })} className={IN} placeholder="Find your people for the next one" />
          </Field>
          <Field label="Call-to-action link">
            <input value={f.cta_url} onChange={(e) => setF({ ...f, cta_url: e.target.value })} className={IN} placeholder="/events" />
          </Field>
          <label className="flex items-center gap-2 text-xs font-bold text-slate-600">
            <input type="checkbox" checked={!!f.featured} onChange={(e) => setF({ ...f, featured: e.target.checked })}
              data-testid="blog-featured" />
            Feature this at the top of the journal
          </label>
        </div>
      </div>
    );
  }

  return (
    <div data-testid="blog-admin">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-black text-slate-900">Journal</h2>
          <p className="mt-1 text-sm text-slate-500">
            Published stories appear at /blog, are added to your sitemap and carry article data for search engines.
          </p>
        </div>
        <div className="flex gap-2">
          {subs && (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-4 py-2 text-xs font-bold text-slate-600"
              data-testid="newsletter-count">
              <Users className="h-3.5 w-3.5" />{subs.active} subscribers
            </span>
          )}
          <a href="/blog" target="_blank" rel="noreferrer" className={`${PILL} border border-slate-200`} data-testid="blog-view-live">
            <ExternalLink className="mr-1.5 inline h-3.5 w-3.5" />View journal
          </a>
          <button onClick={() => setF({ ...blank })} data-testid="blog-new" className={`${PILL} bg-slate-900 text-white`}>
            <Plus className="mr-1 inline h-3.5 w-3.5" />New story
          </button>
        </div>
      </div>

      <div className="mt-5 divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white">
        {list.length ? list.map((p) => (
          <div key={p.id} className="flex flex-wrap items-center gap-4 p-4" data-testid={`blog-row-${p.slug}`}>
            <div className="h-14 w-20 shrink-0 overflow-hidden rounded-xl bg-slate-100">
              {p.cover_image && <img src={p.cover_image} alt="" className="h-full w-full object-cover" />}
            </div>
            <div className="min-w-[220px] flex-1">
              <p className="flex items-center gap-2 text-sm font-bold text-slate-900">
                {p.featured && <Star className="h-3.5 w-3.5 fill-brand-magenta text-brand-magenta" />}{p.title}
              </p>
              <p className="mt-0.5 text-xs text-slate-500">
                {p.category} · /blog/{p.slug} · {p.read_minutes} min · {p.views || 0} views · updated {fmtDate(p.updated_at)}
              </p>
            </div>
            <Badge tone={p.status === "published" ? "green" : "amber"}>{p.status}</Badge>
            <div className="flex gap-2">
              {p.status === "published" && (
                <button onClick={() => sendNewsletter(p, !!p.newsletter_sent_at)} disabled={sending === p.id}
                  data-testid={`blog-newsletter-${p.slug}`} title={p.newsletter_sent_at ? "Already sent — send again" : "Email this story to subscribers"}
                  className={`${PILL} border ${p.newsletter_sent_at ? "border-slate-200 text-slate-500" : "border-slate-900 text-slate-900"}`}>
                  <Send className="mr-1.5 inline h-3.5 w-3.5" />
                  {sending === p.id ? "Sending…" : p.newsletter_sent_at
                    ? `Sent to ${p.newsletter_sent_count || 0}` : "Send to subscribers"}
                </button>
              )}
              <button onClick={() => edit(p.id)} data-testid={`blog-edit-${p.slug}`} className={`${PILL} border border-slate-200`}>Edit</button>
              <button onClick={() => remove(p)} data-testid={`blog-delete-${p.slug}`} className={`${PILL} border border-slate-200 text-red-600`}>
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        )) : <p className="p-6 text-sm text-slate-500" data-testid="blog-admin-empty">No stories yet. Write the first one.</p>}
      </div>

      {doomed && (
        <div className="fixed inset-0 z-[90] flex items-center justify-center bg-slate-900/50 p-4"
          data-testid="blog-delete-dialog" onClick={() => setDoomed(null)}>
          <div className="w-full max-w-md rounded-3xl bg-white p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <p className="text-sm font-black text-slate-900">Delete “{doomed.title}”?</p>
            <p className="mt-1 text-xs text-slate-500">
              The story and its web address go for good. Search engines will drop it on their next crawl.
              Unpublish it instead if you might want it back.
            </p>
            <div className="mt-5 flex gap-2">
              <button onClick={confirmRemove} data-testid="blog-delete-confirm"
                className={`${PILL} flex-1 bg-red-600 text-white`}>Delete for good</button>
              <button onClick={() => setDoomed(null)} data-testid="blog-delete-cancel"
                className={`${PILL} border border-slate-200`}>Keep it</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default BlogAdmin;
