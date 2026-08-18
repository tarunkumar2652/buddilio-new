import { useEffect, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Building2, Loader2, FileText, X, Upload, CheckCircle2 } from "lucide-react";
import { api, errMsg, fileUrl } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { uploadFile, prettySize } from "@/lib/uploads";
import { ImageUpload } from "@/components/ImageUpload";
import { Spinner, SEO } from "@/components/Shared";

const Field = ({ label, hint, ...p }) => (
  <label className="block">
    <span className="text-xs font-bold text-slate-600">{label}</span>
    <input {...p} className="mt-1.5 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-brand-magenta" />
    {hint && <span className="mt-1 block text-[11px] text-slate-400">{hint}</span>}
  </label>
);

export default function VendorSignup() {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const { refresh } = useAuth();
  const nav = useNavigate();
  const [state, setState] = useState({ loading: true, invite: null, error: "" });
  const [meta, setMeta] = useState({ cities: [] });
  const [step, setStep] = useState(1);
  const [busy, setBusy] = useState(false);
  const [docs, setDocs] = useState([]);
  const [pct, setPct] = useState(null);
  const [f, setF] = useState({ full_name: "", org_name: "", city: "", mobile: "", password: "", bio: "", photo: "" });

  useEffect(() => {
    api.get("/meta").then(({ data }) => setMeta(data)).catch(() => {});
    if (!token) return setState({ loading: false, invite: null, error: "This link is missing its invite code." });
    api.get(`/vendor-invite/${token}`)
      .then(({ data }) => {
        setState({ loading: false, invite: data, error: "" });
        setF((p) => ({ ...p, org_name: data.org_name || "", city: data.city || "" }));
      })
      .catch((e) => setState({ loading: false, invite: null, error: errMsg(e) }));
  }, [token]);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post(`/vendor-invite/${token}/accept`, f);
      localStorage.setItem("bud_token", data.access_token);  // sign them straight in
      await refresh();
      toast.success("Account created — add your documents to finish.");
      setStep(2);
    } catch (er) { toast.error(errMsg(er)); } finally { setBusy(false); }
  };

  const addDoc = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setPct(0);
    try {
      const data = await uploadFile(file, setPct);
      const next = [...docs, { name: data.name, url: data.url, size: data.size, kind: "" }];
      setDocs(next);
      await api.put("/partner/documents", { documents: next });
      toast.success(`${data.name} uploaded`);
    } catch (er) { toast.error(er.message || errMsg(er)); } finally { setPct(null); }
  };

  const removeDoc = async (url) => {
    const next = docs.filter((d) => d.url !== url);
    setDocs(next);
    try { await api.put("/partner/documents", { documents: next }); } catch (er) { toast.error(errMsg(er)); }
  };

  if (state.loading) return <Spinner label="Checking your invite" />;

  if (state.error) return (
    <div className="mx-auto max-w-xl px-5 py-24 text-center" data-testid="vendor-signup-invalid">
      <h1 className="text-3xl font-bold">This invite isn't valid</h1>
      <p className="mt-3 text-sm text-slate-500">{state.error}</p>
      <p className="mt-1 text-sm text-slate-500">Ask your Buddilio contact to send a fresh link.</p>
    </div>
  );

  return (
    <div className="mx-auto max-w-2xl px-5 py-14 pb-28" data-testid="vendor-signup-page">
      <SEO title="Organiser signup" />
      <p className="overline inline-flex items-center gap-1.5 text-brand-magenta">
        <Building2 className="h-3.5 w-3.5" />Organiser signup
      </p>
      <h1 className="mt-2 text-4xl font-bold">
        {step === 1 ? "Set up your host account" : "Add your documents"}
      </h1>
      <p className="mt-3 text-sm text-slate-500">
        {step === 1
          ? `${state.invite.manager_name} invited you to host experiences on Buddilio. Fill in your details and pick a password.`
          : "Upload anything that proves you're legit — trade licence, insurance, venue permission or ID. Our team checks these before your verified badge."}
      </p>
      {state.invite.note && step === 1 && (
        <p className="mt-4 rounded-2xl border border-slate-200 bg-white p-4 text-sm text-slate-600" data-testid="vendor-signup-note">
          “{state.invite.note}”
        </p>
      )}

      {step === 1 ? (
        <form onSubmit={submit} className="mt-8 space-y-4" data-testid="vendor-signup-form">
          <Field label="Your name" required data-testid="vs-name" value={f.full_name}
            onChange={(e) => setF({ ...f, full_name: e.target.value })} />
          <Field label="Organisation" required data-testid="vs-org" value={f.org_name}
            onChange={(e) => setF({ ...f, org_name: e.target.value })} />
          <Field label="Email" value={state.invite.email} disabled data-testid="vs-email"
            hint="This is the address your invite was sent to." />
          <label className="block">
            <span className="text-xs font-bold text-slate-600">City</span>
            <select required data-testid="vs-city" value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })}
              className="mt-1.5 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm">
              <option value="">Choose a city</option>
              {(meta.cities || []).map((c) => <option key={c}>{c}</option>)}
            </select>
          </label>
          <Field label="Phone" data-testid="vs-mobile" value={f.mobile}
            onChange={(e) => setF({ ...f, mobile: e.target.value })} />
          <Field label="Password" type="password" required minLength={8} data-testid="vs-password" value={f.password}
            onChange={(e) => setF({ ...f, password: e.target.value })} hint="At least 8 characters." />
          <label className="block">
            <span className="text-xs font-bold text-slate-600">About your events</span>
            <textarea rows={3} data-testid="vs-bio" value={f.bio} onChange={(e) => setF({ ...f, bio: e.target.value })}
              placeholder="What kind of nights do you run, and what makes them yours?"
              className="mt-1.5 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-brand-magenta" />
          </label>
          <ImageUpload value={f.photo} onChange={(url) => setF({ ...f, photo: url })} label="Logo or photo" testid="vs-photo" />
          <button disabled={busy} data-testid="vs-submit"
            className="w-full rounded-full brand-gradient py-3.5 text-sm font-bold text-white disabled:opacity-60">
            {busy ? "Creating your account…" : "Create my organiser account"}
          </button>
        </form>
      ) : (
        <div className="mt-8 space-y-4" data-testid="vendor-docs-step">
          <div className="rounded-3xl border border-slate-200 bg-white p-5">
            {docs.length > 0 && (
              <ul className="mb-4 divide-y divide-slate-100" data-testid="vendor-docs-list">
                {docs.map((d) => (
                  <li key={d.url} className="flex items-center gap-3 py-2.5" data-testid={`vendor-doc-${d.name}`}>
                    <FileText className="h-4 w-4 text-slate-400" />
                    <a href={fileUrl(d.url)} target="_blank" rel="noreferrer" className="min-w-0 flex-1 truncate text-sm font-semibold hover:text-brand-magenta">{d.name}</a>
                    <span className="text-[11px] text-slate-400">{prettySize(d.size || 0)}</span>
                    <button onClick={() => removeDoc(d.url)} data-testid={`vendor-doc-remove-${d.name}`}
                      className="p-1.5 rounded-full hover:bg-slate-100"><X className="h-3.5 w-3.5" /></button>
                  </li>
                ))}
              </ul>
            )}
            <label className="flex cursor-pointer items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-slate-300 py-8 text-sm font-bold text-slate-500 transition-colors hover:border-brand-magenta hover:text-brand-magenta">
              {pct !== null ? <><Loader2 className="h-4 w-4 animate-spin" />Uploading… {pct}%</> : <><Upload className="h-4 w-4" />Add a document (PDF or image, up to 25MB)</>}
              <input type="file" className="hidden" onChange={addDoc} data-testid="vendor-doc-input"
                accept="image/*,application/pdf" disabled={pct !== null} />
            </label>
          </div>
          <button onClick={() => nav("/partner")} data-testid="vendor-docs-done"
            className="inline-flex items-center gap-2 rounded-full bg-slate-900 px-5 py-3 text-sm font-bold text-white">
            <CheckCircle2 className="h-4 w-4" />Go to my organiser dashboard
          </button>
          <p className="text-[11px] text-slate-400">You can add or replace documents later from your dashboard.</p>
        </div>
      )}
    </div>
  );
}
