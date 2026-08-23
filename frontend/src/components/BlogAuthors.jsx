import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2, Pencil, X, Mail } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { ImageUpload } from "@/components/ImageUpload";

const PILL = "rounded-full px-4 py-2 text-xs font-bold";
const IN = "mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm";
const BLANK = { name: "", slug: "", role: "", bio: "", photo: "", city: "", x_url: "", instagram_url: "", site_url: "" };

const Field = ({ label, children }) => (
  <label className="block"><span className="text-xs font-bold text-slate-600">{label}</span>{children}</label>
);

/** Writers behind the Journal — each gets a byline, a photo and their own page. */
export const BlogAuthors = ({ onChange }) => {
  const [list, setList] = useState([]);
  const [open, setOpen] = useState(false);
  const [f, setF] = useState(BLANK);
  const [id, setId] = useState(null);
  const [doomed, setDoomed] = useState(null);
  const [inviting, setInviting] = useState(null);
  const [inviteEmail, setInviteEmail] = useState("");

  const invite = async (e) => {
    e.preventDefault();
    try {
      const { data } = await api.post(`/admin/blog-authors/${inviting.id}/invite`, { email: inviteEmail });
      toast.success(data.message);
      setInviting(null); setInviteEmail(""); load();
    } catch (e2) { toast.error(errMsg(e2)); }
  };

  const load = useCallback(() => {
    api.get("/admin/blog-authors").then(({ data }) => { setList(data.items); onChange?.(data.items); })
      .catch(() => setList([]));
  }, [onChange]);
  useEffect(() => { load(); }, [load]);

  const save = async (e) => {
    e.preventDefault();
    try {
      id ? await api.put(`/admin/blog-authors/${id}`, f) : await api.post("/admin/blog-authors", f);
      toast.success(id ? "Writer updated." : "Writer added.");
      setOpen(false); setF(BLANK); setId(null); load();
    } catch (e2) { toast.error(errMsg(e2)); }
  };

  const remove = async () => {
    try {
      await api.delete(`/admin/blog-authors/${doomed.id}`);
      toast.success("Writer removed.");
      setDoomed(null); load();
    } catch (e) { toast.error(errMsg(e)); }
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5" data-testid="blog-authors">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-black text-slate-900">Writers</p>
          <p className="mt-0.5 text-xs text-slate-500">
            Each writer gets a byline on their stories and a page at /blog/author/their-name.
          </p>
        </div>
        <button onClick={() => { setF(BLANK); setId(null); setOpen(true); }} data-testid="author-new"
          className={`${PILL} bg-slate-900 text-white`}><Plus className="mr-1.5 inline h-3.5 w-3.5" />Add writer</button>
      </div>

      {!!list.length && (
        <ul className="mt-4 divide-y divide-slate-100" data-testid="authors-list">
          {list.map((a) => (
            <li key={a.id} className="flex items-center gap-3 py-2.5" data-testid={`author-row-${a.slug}`}>
              {a.photo ? <img src={a.photo} alt={a.name} className="h-9 w-9 rounded-full object-cover" />
                : <span className="grid h-9 w-9 place-items-center rounded-full bg-slate-900 text-xs font-black text-white">{a.name.slice(0, 1)}</span>}
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-bold text-slate-900">{a.name}</p>
                <p className="truncate text-xs text-slate-500">
                  {a.role || "Writer"} · /blog/author/{a.slug} · {a.posts} {a.posts === 1 ? "story" : "stories"}
                </p>
              </div>
              <a href={`/blog/author/${a.slug}`} target="_blank" rel="noreferrer"
                className={`${PILL} border border-slate-200`} data-testid={`author-view-${a.slug}`}>View</a>
              <button onClick={() => { setInviting(a); setInviteEmail(a.email || ""); }}
                data-testid={`author-invite-${a.slug}`}
                className={`${PILL} border ${a.user_id ? "border-slate-200 text-slate-500" : "border-slate-900 text-slate-900"}`}>
                <Mail className="mr-1.5 inline h-3.5 w-3.5" />{a.user_id ? "Re-invite" : "Invite to write"}
              </button>
              <button onClick={() => { setF({ ...BLANK, ...a }); setId(a.id); setOpen(true); }}
                data-testid={`author-edit-${a.slug}`} className="p-2 text-slate-400 hover:text-slate-900">
                <Pencil className="h-4 w-4" />
              </button>
              <button onClick={() => setDoomed(a)} data-testid={`author-delete-${a.slug}`}
                className="p-2 text-slate-400 hover:text-red-600"><Trash2 className="h-4 w-4" /></button>
            </li>
          ))}
        </ul>
      )}
      {!list.length && (
        <p className="mt-4 text-sm text-slate-500" data-testid="authors-empty">
          No writers yet — add one and pick them when you write a story.
        </p>
      )}

      {open && (
        <div className="fixed inset-0 z-[90] flex items-start justify-center overflow-y-auto bg-slate-900/50 p-4"
          data-testid="author-dialog">
          <form onSubmit={save} className="my-8 w-full max-w-xl space-y-3 rounded-3xl bg-white p-6 shadow-2xl">
            <div className="flex items-center justify-between">
              <p className="text-sm font-black">{id ? "Edit writer" : "New writer"}</p>
              <button type="button" onClick={() => setOpen(false)} data-testid="author-dialog-close"
                className="p-1.5 text-slate-400 hover:text-slate-900"><X className="h-4 w-4" /></button>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Name">
                <input required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })}
                  className={IN} data-testid="author-name-input" />
              </Field>
              <Field label="Role">
                <input value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}
                  className={IN} placeholder="City editor" data-testid="author-role-input" />
              </Field>
              <Field label="Web address (optional)">
                <input value={f.slug} onChange={(e) => setF({ ...f, slug: e.target.value })}
                  className={IN} placeholder="auto from the name" data-testid="author-slug-input" />
              </Field>
              <Field label="City">
                <input value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })} className={IN} />
              </Field>
            </div>
            <Field label="Short bio">
              <textarea rows={3} value={f.bio} onChange={(e) => setF({ ...f, bio: e.target.value })}
                className={`${IN} resize-none`} data-testid="author-bio-input" />
            </Field>
            <ImageUpload label="Photo" aspect="square" testid="author-photo-upload"
              value={f.photo} onChange={(v) => setF({ ...f, photo: v })} />
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Website"><input value={f.site_url} onChange={(e) => setF({ ...f, site_url: e.target.value })} className={IN} /></Field>
              <Field label="X"><input value={f.x_url} onChange={(e) => setF({ ...f, x_url: e.target.value })} className={IN} /></Field>
              <Field label="Instagram"><input value={f.instagram_url} onChange={(e) => setF({ ...f, instagram_url: e.target.value })} className={IN} /></Field>
            </div>
            <div className="flex gap-2 pt-2">
              <button className={`${PILL} bg-slate-900 text-white`} data-testid="author-save">
                {id ? "Save writer" : "Add writer"}
              </button>
              <button type="button" onClick={() => setOpen(false)} className={`${PILL} border border-slate-200`}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      {inviting && (
        <div className="fixed inset-0 z-[90] grid place-items-center bg-slate-900/50 p-4" data-testid="author-invite-dialog">
          <form onSubmit={invite} className="w-full max-w-sm rounded-3xl bg-white p-6 shadow-2xl">
            <p className="text-sm font-black">Invite {inviting.name} to write</p>
            <p className="mt-2 text-xs text-slate-500">
              They get their own login with access to <b>My stories</b> only — they can draft and send
              for review, and you decide what goes live.
            </p>
            <input required type="email" value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)}
              placeholder="writer@email.com" className={IN} data-testid="author-invite-email" />
            <div className="mt-4 flex gap-2">
              <button className={`${PILL} bg-slate-900 text-white`} data-testid="author-invite-send">Send invite</button>
              <button type="button" onClick={() => setInviting(null)} className={`${PILL} border border-slate-200`}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      {doomed && (
        <div className="fixed inset-0 z-[90] grid place-items-center bg-slate-900/50 p-4" data-testid="author-delete-dialog">
          <div className="w-full max-w-sm rounded-3xl bg-white p-6 text-center shadow-2xl">
            <p className="text-sm font-black">Remove {doomed.name}?</p>
            <p className="mt-2 text-xs text-slate-500">
              Their stories stay published — they simply lose the byline link.
            </p>
            <div className="mt-5 flex justify-center gap-2">
              <button onClick={remove} className={`${PILL} bg-red-600 text-white`} data-testid="author-delete-confirm">Remove</button>
              <button onClick={() => setDoomed(null)} className={`${PILL} border border-slate-200`}>Keep</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default BlogAuthors;
