import { useState } from "react";
import { toast } from "sonner";
import { Megaphone, Check } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { SEO } from "@/components/Shared";

const IN = "mt-1.5 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none focus:border-brand-magenta";
const STATS = [["27 cities", "across 12 countries"], ["21+ audience", "verified members only"],
  ["Nightlife & dining", "high-intent readers"]];

export default function Advertise() {
  const [f, setF] = useState({ name: "", email: "", company: "", budget: "", message: "" });
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post("/advertise", f);
      toast.success(data.message);
      setDone(true);
    } catch (e2) { toast.error(errMsg(e2)); } finally { setBusy(false); }
  };

  return (
    <div className="bg-white" data-testid="advertise-page">
      <SEO title="Advertise with Buddilio"
        description="Reach a verified 21+ audience planning nights out, dining and travel across 27 cities." />

      <section className="mx-auto max-w-4xl px-4 pt-16 sm:px-6 lg:pt-24">
        <p className="inline-flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.22em] text-brand-magenta">
          <Megaphone className="h-3.5 w-3.5" />Advertise with us
        </p>
        <h1 className="mt-5 font-display text-4xl font-bold tracking-tight text-slate-900 sm:text-5xl">
          Get in front of people who are already going out.
        </h1>
        <p className="mt-5 max-w-2xl text-base text-slate-600 sm:text-lg">
          Venues, brands and experience makers can take a slot on the pages our members browse before they
          book — the events list, the Journal and the membership pages.
        </p>
        <div className="mt-10 grid gap-4 sm:grid-cols-3">
          {STATS.map(([k, v]) => (
            <div key={k} className="rounded-2xl border border-slate-200 p-5">
              <p className="font-display text-xl font-bold text-slate-900">{k}</p>
              <p className="mt-1 text-xs text-slate-500">{v}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto mt-14 max-w-2xl px-4 pb-24 sm:px-6">
        {done ? (
          <div className="rounded-3xl border border-slate-200 bg-slate-50 p-8 text-center" data-testid="advertise-done">
            <Check className="mx-auto h-7 w-7 text-emerald-500" />
            <p className="mt-4 font-display text-2xl font-bold text-slate-900">Thanks — that's with our team.</p>
            <p className="mt-2 text-sm text-slate-600">We reply within two working days.</p>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-4 rounded-3xl border border-slate-200 p-6 sm:p-8">
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block"><span className="text-xs font-bold text-slate-600">Your name</span>
                <input required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })}
                  className={IN} data-testid="advertise-name" /></label>
              <label className="block"><span className="text-xs font-bold text-slate-600">Email</span>
                <input required type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })}
                  className={IN} data-testid="advertise-email" /></label>
              <label className="block"><span className="text-xs font-bold text-slate-600">Company or venue</span>
                <input value={f.company} onChange={(e) => setF({ ...f, company: e.target.value })}
                  className={IN} data-testid="advertise-company" /></label>
              <label className="block"><span className="text-xs font-bold text-slate-600">Monthly budget</span>
                <input value={f.budget} onChange={(e) => setF({ ...f, budget: e.target.value })}
                  placeholder="e.g. $500" className={IN} data-testid="advertise-budget" /></label>
            </div>
            <label className="block"><span className="text-xs font-bold text-slate-600">What would you like to promote?</span>
              <textarea required rows={4} value={f.message} onChange={(e) => setF({ ...f, message: e.target.value })}
                className={`${IN} resize-none`} data-testid="advertise-message" /></label>
            <button disabled={busy} data-testid="advertise-submit"
              className="rounded-full bg-brand-magenta px-7 py-3.5 text-sm font-bold text-white transition hover:bg-[#C81566] disabled:opacity-60">
              {busy ? "Sending…" : "Send enquiry"}
            </button>
          </form>
        )}
      </section>
    </div>
  );
}
