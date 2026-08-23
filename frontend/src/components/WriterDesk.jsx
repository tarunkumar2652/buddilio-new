import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Send, ArrowLeft, AlertTriangle, ExternalLink } from "lucide-react";
import { api, errMsg, fmtDate } from "@/lib/api";
import { Spinner, Badge, Empty } from "@/components/Shared";
import { ImageUpload } from "@/components/ImageUpload";

const PILL = "rounded-full px-4 py-2 text-xs font-bold";
const IN = "mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm";
const BLANK = { title: "", category: "Community", excerpt: "", body: "", cover_image: "",
  cover_credit: "", tags: [], seo_title: "", seo_description: "" };
const TONE = { published: "green", in_review: "amber", changes_requested: "red", draft: "slate" };
const LABEL = { published: "live", in_review: "in review", changes_requested: "changes asked", draft: "draft" };

const Field = ({ label, hint, children }) => (
  <label className="block">
    <span className="text-xs font-bold text-slate-600">{label}</span>
    {children}
    {hint && <span className="mt-1 block text-[11px] text-slate-400">{hint}</span>}
  </label>
);

/** A writer's own desk — draft, save, send for review. Only editors publish. */
export const WriterDesk = () => {
  const [d, setD] = useState(null);
  const [editing, setEditing] = useState(null);   // null = list, "new" or post id
  const [f, setF] = useState(BLANK);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get("/writer/posts").then(({ data }) => setD(data)).catch((e) => { setD(false); toast.error(errMsg(e)); });
  }, []);
  useEffect(() => { load(); }, [load]);

  const open = async (id) => {
    if (id === "new") { setF(BLANK); setEditing("new"); return; }
    try {
      const { data } = await api.get(`/writer/posts/${id}`);
      setF({ ...BLANK, ...data.post });
      setEditing(id);
    } catch (e) { toast.error(errMsg(e)); }
  };

  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = editing === "new"
        ? await api.post("/writer/posts", f)
        : await api.put(`/writer/posts/${editing}`, f);
      toast.success(data.message);
      if (editing === "new") setEditing(data.id);
      load();
    } catch (e2) { toast.error(errMsg(e2)); } finally { setBusy(false); }
  };

  const submit = async (id) => {
    setBusy(true);
    try {
      const { data } = await api.post(`/writer/posts/${id}/submit`);
      toast.success(data.message);
      setEditing(null);
      load();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  if (d === null) return <Spinner />;
  if (d === false) return null;

  if (editing) {
    const current = d.items.find((p) => p.id === editing);
    return (
      <form onSubmit={save} className="space-y-4" data-testid="writer-editor">
        <button type="button" onClick={() => setEditing(null)} data-testid="writer-back"
          className="inline-flex items-center gap-1.5 text-xs font-bold text-slate-500 hover:text-brand-magenta">
          <ArrowLeft className="h-3.5 w-3.5" />My stories
        </button>
        {current?.review_note && (
          <p className="flex gap-2 rounded-2xl bg-amber-50 p-4 text-xs font-semibold text-amber-800"
            data-testid="writer-review-note">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span><b>Editor's note:</b> {current.review_note}</span>
          </p>
        )}
        <div className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5">
          <Field label="Headline">
            <input required value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })}
              className={IN} data-testid="writer-title" />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Category">
              <select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}
                className={IN} data-testid="writer-category">
                {d.categories.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </Field>
            <Field label="Tags" hint="Comma separated.">
              <input value={(f.tags || []).join(", ")} className={IN} data-testid="writer-tags"
                onChange={(e) => setF({ ...f, tags: e.target.value.split(",").map((t) => t.trim()).filter(Boolean) })} />
            </Field>
          </div>
          <Field label="Standfirst" hint="One or two lines that pull the reader in.">
            <textarea rows={2} value={f.excerpt} onChange={(e) => setF({ ...f, excerpt: e.target.value })}
              className={`${IN} resize-none`} data-testid="writer-excerpt" />
          </Field>
          <Field label="Story" hint="Basic HTML works: <p>, <h2>, <blockquote>, <ul>, <a href=…>.">
            <textarea rows={16} value={f.body} onChange={(e) => setF({ ...f, body: e.target.value })}
              className={`${IN} font-mono text-xs`} data-testid="writer-body" />
          </Field>
          <ImageUpload label="Cover image" aspect="wide" testid="writer-cover"
            value={f.cover_image} onChange={(v) => setF({ ...f, cover_image: v })} />
          <Field label="Cover credit">
            <input value={f.cover_credit} onChange={(e) => setF({ ...f, cover_credit: e.target.value })}
              className={IN} />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Search engine title" hint="Around 60 characters.">
              <input value={f.seo_title} onChange={(e) => setF({ ...f, seo_title: e.target.value })} className={IN} />
            </Field>
            <Field label="Search engine description" hint="Around 155 characters.">
              <input value={f.seo_description} onChange={(e) => setF({ ...f, seo_description: e.target.value })} className={IN} />
            </Field>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button disabled={busy} className={`${PILL} bg-slate-900 text-white disabled:opacity-50`}
            data-testid="writer-save">{busy ? "Saving…" : "Save draft"}</button>
          {editing !== "new" && current?.status !== "published" && (
            <button type="button" disabled={busy} onClick={() => submit(editing)} data-testid="writer-submit"
              className={`${PILL} border border-slate-900 disabled:opacity-50`}>
              <Send className="mr-1.5 inline h-3.5 w-3.5" />Send for review
            </button>
          )}
        </div>
      </form>
    );
  }

  return (
    <div className="space-y-4" data-testid="writer-desk">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-black text-slate-900">
            My stories{d.author ? ` — ${d.author.name}` : ""}
          </p>
          <p className="mt-0.5 text-xs text-slate-500">
            Write freely, then send it for review. An editor publishes it for you.
          </p>
        </div>
        <button onClick={() => open("new")} className={`${PILL} bg-slate-900 text-white`} data-testid="writer-new">
          <Plus className="mr-1.5 inline h-3.5 w-3.5" />New story
        </button>
      </div>

      {!d.items.length ? (
        <div className="rounded-2xl border border-slate-200 bg-white p-8">
          <Empty title="Nothing written yet" sub="Start your first story — it stays private until you send it." />
        </div>
      ) : (
        <div className="divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white"
          data-testid="writer-list">
          {d.items.map((p) => (
            <div key={p.id} className="flex flex-wrap items-center gap-3 p-4" data-testid={`writer-row-${p.id}`}>
              {p.cover_image && <img src={p.cover_image} alt="" className="h-12 w-16 rounded-lg object-cover" />}
              <div className="min-w-[200px] flex-1">
                <p className="text-sm font-bold text-slate-900">{p.title}</p>
                <p className="mt-0.5 text-xs text-slate-500">
                  {p.category} · updated {fmtDate(p.updated_at)}
                  {p.status === "published" ? ` · ${p.views} views` : ""}
                </p>
                {p.review_note && (
                  <p className="mt-1 text-xs font-semibold text-amber-700">Editor: {p.review_note}</p>
                )}
              </div>
              <Badge tone={TONE[p.status] || "slate"}>{LABEL[p.status] || p.status}</Badge>
              {p.status === "published" ? (
                <a href={`/blog/${p.slug}`} target="_blank" rel="noreferrer" className={`${PILL} border border-slate-200`}
                  data-testid={`writer-view-${p.id}`}><ExternalLink className="mr-1.5 inline h-3.5 w-3.5" />View</a>
              ) : (
                <button onClick={() => open(p.id)} className={`${PILL} border border-slate-200`}
                  data-testid={`writer-edit-${p.id}`}>Edit</button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default WriterDesk;
