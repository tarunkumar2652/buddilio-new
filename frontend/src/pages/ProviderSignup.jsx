import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Upload, Compass } from "lucide-react";
import { api, errMsg, money } from "@/lib/api";
import { uploadFile } from "@/lib/uploads";
import { Spinner, Badge, SEO } from "@/components/Shared";
import { RichText } from "@/components/RichText";

const cls = "w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm";

export default function ProviderSignup() {
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const [f, setF] = useState({ roles: [], day_rate: 0, destinations: "", languages: "", headline: "",
    about: "", experience_years: 0, accept_terms: false });
  const [files, setFiles] = useState([]);
  const [pct, setPct] = useState(0);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef(null);

  useEffect(() => {
    api.get("/me/provider").then(({ data }) => {
      setData(data);
      const p = data.profile;
      if (p.status && p.status !== "none") {
        setF({ roles: p.roles, day_rate: p.day_rate, destinations: (p.destinations || []).join(", "),
          languages: (p.languages || []).join(", "), headline: p.headline, about: p.about,
          experience_years: p.experience_years, accept_terms: true });
        setFiles(p.documents || []);
      }
    }).catch(() => setData(false));
  }, []);

  const pick = async (e) => {
    for (const file of Array.from(e.target.files || []).slice(0, 5 - files.length)) {
      try { const up = await uploadFile(file, setPct); setFiles((x) => [...x, { url: up.url, name: file.name }]); }
      catch (er) { toast.error(er.message || "Upload failed"); }
    }
    setPct(0);
    if (inputRef.current) inputRef.current.value = "";
  };

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data: res } = await api.post("/me/provider", {
        ...f, day_rate: Number(f.day_rate), experience_years: Number(f.experience_years),
        destinations: f.destinations.split(",").map((s) => s.trim()).filter(Boolean),
        languages: f.languages.split(",").map((s) => s.trim()).filter(Boolean),
        documents: files });
      if (res.next === "checkout") return nav(`/checkout?kind=provider_fee&id=${res.checkout.item_id}`);
      toast.success("Sent for review — we'll be in touch within a day.");
      setData((d) => ({ ...d, profile: { ...d.profile, status: res.status } }));
    } catch (er) { toast.error(errMsg(er)); } finally { setBusy(false); }
  };

  if (data === null) return <Spinner label="Loading" />;
  if (data === false) return null;
  const status = data.profile.status || "none";

  return (
    <div className="mx-auto max-w-3xl px-4 sm:px-6 py-10 pb-28" data-testid="provider-signup-page">
      <SEO title="Offer your services" description="Register as a guide, cook or porter on Buddilio." />
      <p className="overline">Travel crew</p>
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <h1 className="text-3xl sm:text-4xl font-bold">Get listed as travel crew</h1>
        {status !== "none" && (
          <Badge tone={status === "approved" ? "green" : status === "rejected" ? "red" : "amber"}>
            <span data-testid="provider-status">{status.replace("_", " ")}</span>
          </Badge>
        )}
      </div>
      <p className="mt-3 text-base text-slate-600">
        Guides, cooks, porters, drivers and photographers pay a one-time registration fee of{" "}
        <b data-testid="provider-fee">{money(data.provider_fee)}</b>, then travellers book you through Buddilio.
        Buddilio keeps {data.profile.cut_percent}% of each booking and travellers see your rate with a{" "}
        {data.profile.markup_percent}% service markup.
      </p>
      {data.profile.rejected_reason && <p className="mt-2 text-sm text-amber-700">{data.profile.rejected_reason}</p>}

      <form onSubmit={submit} className="mt-8 grid gap-4 rounded-2xl border border-slate-200 bg-white p-6 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <p className="text-xs font-bold text-slate-600">What do you offer?</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {data.roles.map((r) => (
              <button key={r.key} type="button" data-testid={`provider-role-${r.key}`}
                onClick={() => setF({ ...f, roles: f.roles.includes(r.key) ? f.roles.filter((x) => x !== r.key) : [...f.roles, r.key] })}
                className={`rounded-full border px-4 py-2 text-xs font-bold ${f.roles.includes(r.key) ? "bg-slate-900 text-white border-slate-900" : "border-slate-200"}`}>
                {r.label}
              </button>
            ))}
          </div>
        </div>
        <label className="block"><span className="text-xs font-bold text-slate-600">Your day rate (what you keep before our cut)</span>
          <input required type="number" min={1} value={f.day_rate} data-testid="provider-day-rate"
            onChange={(e) => setF({ ...f, day_rate: e.target.value })} className={`${cls} mt-1.5`} /></label>
        <label className="block"><span className="text-xs font-bold text-slate-600">Years of experience</span>
          <input type="number" min={0} value={f.experience_years} data-testid="provider-experience"
            onChange={(e) => setF({ ...f, experience_years: e.target.value })} className={`${cls} mt-1.5`} /></label>
        <label className="block"><span className="text-xs font-bold text-slate-600">Destinations you cover (comma separated)</span>
          <input value={f.destinations} data-testid="provider-destinations"
            onChange={(e) => setF({ ...f, destinations: e.target.value })} className={`${cls} mt-1.5`} /></label>
        <label className="block"><span className="text-xs font-bold text-slate-600">Languages</span>
          <input value={f.languages} data-testid="provider-languages"
            onChange={(e) => setF({ ...f, languages: e.target.value })} className={`${cls} mt-1.5`} /></label>
        <label className="block sm:col-span-2"><span className="text-xs font-bold text-slate-600">One-line headline</span>
          <input value={f.headline} data-testid="provider-headline"
            onChange={(e) => setF({ ...f, headline: e.target.value })} className={`${cls} mt-1.5`} /></label>
        <div className="sm:col-span-2">
          <p className="text-xs font-bold text-slate-600">About your work</p>
          <div className="mt-1.5"><RichText value={f.about} rows={5} testid="provider-about"
            onChange={(html) => setF({ ...f, about: html })} /></div>
        </div>

        <div className="sm:col-span-2">
          <p className="text-xs font-bold text-slate-600">ID / licence documents</p>
          <div className="mt-2 flex flex-wrap items-center gap-2" data-testid="provider-files">
            {files.map((d, i) => (
              <span key={i} className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1.5 text-xs font-semibold">
                {d.name}
                <button type="button" onClick={() => setFiles(files.filter((_, x) => x !== i))}
                  data-testid={`provider-file-remove-${i}`} className="text-slate-400 hover:text-rose-600">×</button>
              </span>
            ))}
            {files.length < 5 && (
              <button type="button" onClick={() => inputRef.current?.click()} data-testid="provider-file-pick"
                className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 px-4 py-2 text-xs font-bold">
                <Upload className="h-3.5 w-3.5" />{pct ? `Uploading ${pct}%` : "Add document"}
              </button>
            )}
            <input ref={inputRef} type="file" accept="image/*,.pdf" multiple hidden onChange={pick} data-testid="provider-file-input" />
          </div>
        </div>

        <label className="flex items-start gap-2 text-xs text-slate-600 sm:col-span-2">
          <input type="checkbox" checked={f.accept_terms} data-testid="provider-terms"
            onChange={(e) => setF({ ...f, accept_terms: e.target.checked })} className="mt-0.5" />
          {data.terms}
        </label>
        <button disabled={busy} data-testid="provider-submit"
          className="rounded-full brand-gradient px-7 py-3 text-sm font-bold text-white disabled:opacity-50 sm:col-span-2 sm:w-fit">
          <Compass className="mr-1.5 inline h-4 w-4" />
          {busy ? "Saving…" : status === "none" ? `Pay ${money(data.provider_fee)} & apply` : "Update my listing"}
        </button>
      </form>
    </div>
  );
}
