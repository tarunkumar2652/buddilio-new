import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { api, errMsg } from "@/lib/api";
import { ImageUpload } from "@/components/ImageUpload";
import { SEO } from "@/components/Shared";

const LIFESTYLE = ["Early Riser", "Night Owl", "Fitness Focused", "Vegetarian",
  "Social Drinker", "Non Smoker", "Pet Lover", "Frequent Traveller"];

const Chip = ({ on, children, ...p }) => (
  <button type="button" {...p}
    className={`rounded-full px-3 py-1.5 text-xs font-semibold border transition-colors ${on ? "bg-slate-900 text-white border-slate-900" : "border-slate-200 bg-white hover:border-slate-400"}`}>
    {children}
  </button>
);

export default function Welcome() {
  const { user, setUser } = useAuth();
  const nav = useNavigate();
  const [meta, setMeta] = useState({ cities: [], categories: [], interests: [], countries: [] });
  const [busy, setBusy] = useState(false);
  const [f, setF] = useState({
    dob: "", gender: "prefer not to say", mobile: "", country: "", city: "", bio: "",
    photo: user?.photo || "", interests: [], event_categories: [], lifestyle: [],
    is_adult: false, accept_terms: false,
  });

  useEffect(() => {
    api.get("/meta").then(({ data }) => {
      setMeta(data);
      const c = (data.countries || [])[0];
      setF((p) => p.country ? p : { ...p, country: c?.name || "", city: c?.cities?.[0] || "" });
    }).catch(() => {});
  }, []);

  const toggle = (key, val) => setF((p) => ({
    ...p, [key]: p[key].includes(val) ? p[key].filter((x) => x !== val) : [...p[key], val],
  }));

  const cities = ((meta.countries || []).find((c) => c.name === f.country)?.cities) || meta.cities || [];

  const submit = async (e) => {
    e.preventDefault();
    if (!f.is_adult || !f.accept_terms) return toast.error("Please confirm you're 21+ and accept the policies.");
    setBusy(true);
    try {
      const { data } = await api.post("/auth/onboarding", f);
      setUser(data);
      toast.success("You're all set. Welcome to Buddilio!");
      nav("/dashboard", { replace: true });
    } catch (er) { toast.error(errMsg(er)); } finally { setBusy(false); }
  };

  return (
    <div className="max-w-2xl mx-auto px-5 py-14" data-testid="welcome-page">
      <SEO title="Finish setting up" />
      <p className="text-xs font-bold uppercase tracking-widest text-brand-magenta">One last step</p>
      <h1 className="mt-2 text-4xl sm:text-5xl font-bold">
        Welcome{user?.full_name ? `, ${user.full_name.split(" ")[0]}` : ""}
      </h1>
      <p className="mt-3 text-base text-slate-500">
        Buddilio is an adults-only community, so we need your date of birth and city before you can join an
        experience. It takes under a minute.
      </p>

      <form onSubmit={submit} className="mt-9 space-y-5" data-testid="welcome-form">
        <div className="grid sm:grid-cols-2 gap-4">
          <label className="block">
            <span className="text-xs font-bold text-slate-600">Date of birth (21+ only)</span>
            <input type="date" required data-testid="welcome-dob" value={f.dob}
              onChange={(e) => setF({ ...f, dob: e.target.value })}
              className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-slate-900" />
          </label>
          <label className="block">
            <span className="text-xs font-bold text-slate-600">Gender</span>
            <select data-testid="welcome-gender" value={f.gender} onChange={(e) => setF({ ...f, gender: e.target.value })}
              className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm">
              {["female", "male", "non-binary", "prefer not to say"].map((g) => <option key={g} value={g}>{g}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="text-xs font-bold text-slate-600">Country</span>
            <select data-testid="welcome-country" value={f.country}
              onChange={(e) => {
                const c = (meta.countries || []).find((x) => x.name === e.target.value);
                setF({ ...f, country: e.target.value, city: c?.cities?.[0] || "" });
              }}
              className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm">
              {(meta.countries || []).map((c) => <option key={c.code} value={c.name}>{c.name}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="text-xs font-bold text-slate-600">City</span>
            <select data-testid="welcome-city" value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })}
              className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm">
              {cities.map((c) => <option key={c}>{c}</option>)}
            </select>
          </label>
          <label className="block sm:col-span-2">
            <span className="text-xs font-bold text-slate-600">Mobile number (optional)</span>
            <input data-testid="welcome-mobile" value={f.mobile} onChange={(e) => setF({ ...f, mobile: e.target.value })}
              className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-slate-900" />
          </label>
        </div>

        <label className="block">
          <span className="text-xs font-bold text-slate-600">Short bio</span>
          <textarea rows={3} data-testid="welcome-bio" value={f.bio} onChange={(e) => setF({ ...f, bio: e.target.value })}
            placeholder="What do you enjoy doing on a night off?"
            className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-slate-900" />
        </label>

        <ImageUpload value={f.photo} onChange={(url) => setF({ ...f, photo: url })} label="Profile photo" testid="welcome-photo" />

        <div>
          <p className="text-xs font-bold text-slate-600 mb-2">Social interests</p>
          <div className="flex flex-wrap gap-2" data-testid="welcome-interests">
            {(meta.interests || []).map((i) => (
              <Chip key={i} on={f.interests.includes(i)} data-testid={`welcome-interest-${i}`}
                onClick={() => toggle("interests", i)}>{i}</Chip>
            ))}
          </div>
        </div>
        <div>
          <p className="text-xs font-bold text-slate-600 mb-2">Preferred event categories</p>
          <div className="flex flex-wrap gap-2" data-testid="welcome-categories">
            {(meta.categories || []).map((c) => (
              <Chip key={c} on={f.event_categories.includes(c)} data-testid={`welcome-category-${c}`}
                onClick={() => toggle("event_categories", c)}>{c}</Chip>
            ))}
          </div>
        </div>
        <div>
          <p className="text-xs font-bold text-slate-600 mb-2">Lifestyle preferences</p>
          <div className="flex flex-wrap gap-2">
            {LIFESTYLE.map((l) => (
              <Chip key={l} on={f.lifestyle.includes(l)} onClick={() => toggle("lifestyle", l)}>{l}</Chip>
            ))}
          </div>
        </div>

        {[["is_adult", "I confirm I am 21 years of age or older."],
          ["accept_terms", "I accept the Terms, Privacy Policy and Community Safety Guidelines."]].map(([k, l]) => (
          <label key={k} className="flex gap-3 items-start text-sm">
            <input type="checkbox" checked={f[k]} data-testid={`welcome-${k}`}
              onChange={(e) => setF({ ...f, [k]: e.target.checked })} className="mt-1 h-4 w-4" />
            <span className="text-slate-600">{l}</span>
          </label>
        ))}

        <button disabled={busy} data-testid="welcome-submit"
          className="w-full rounded-full bg-slate-900 text-white py-3.5 text-sm font-bold disabled:opacity-60 hover:bg-slate-800">
          {busy ? "Saving…" : "Enter Buddilio"}
        </button>
      </form>
    </div>
  );
}
