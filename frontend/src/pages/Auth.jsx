import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { api, errMsg } from "@/lib/api";
import { useCurrency } from "@/context/CurrencyContext";
import { ImageUpload } from "@/components/ImageUpload";
import { SEO } from "@/components/Shared";

const Field = ({ label, ...p }) => (
  <label className="block">
    <span className="text-xs font-bold text-slate-600">{label}</span>
    <input {...p} className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-slate-900" />
  </label>
);

const AuthShell = ({ title, sub, children }) => (
  <div className="min-h-[80vh] grid lg:grid-cols-2">
    <div className="hidden lg:block relative bg-slate-900">
      <img src="https://images.pexels.com/photos/8921578/pexels-photo-8921578.jpeg?auto=compress&w=1200" alt=""
        className="absolute inset-0 h-full w-full object-cover opacity-40" />
      <div className="relative h-full flex flex-col justify-end p-14 text-white">
        <h2 className="text-3xl font-bold leading-tight">Thousands of members. One reason.</h2>
        <p className="mt-4 text-slate-300 max-w-sm">Nobody should skip a night out just because their friends were busy.</p>
      </div>
    </div>
    <div className="px-5 sm:px-10 py-14 flex items-center">
      <div className="w-full max-w-md mx-auto">
        <h1 className="text-3xl font-bold">{title}</h1>
        <p className="mt-2 text-sm text-slate-500">{sub}</p>
        <div className="mt-8">{children}</div>
      </div>
    </div>
  </div>
);

export const GoogleButton = ({ label = "Continue with Google", testid = "google-login" }) => {
  const go = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + "/dashboard";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };
  return (
    <>
      <div className="my-5 flex items-center gap-3 text-xs text-slate-400">
        <div className="h-px flex-1 bg-slate-200" />OR<div className="h-px flex-1 bg-slate-200" />
      </div>
      <button type="button" onClick={go} data-testid={testid}
        className="w-full flex items-center justify-center gap-2.5 rounded-full border border-slate-200 bg-white py-3.5 text-sm font-bold transition-colors hover:bg-slate-50">
        <svg viewBox="0 0 48 48" className="h-4 w-4" aria-hidden="true">
          <path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9 3.6l6.7-6.7C35.6 2.5 30.2 0 24 0 14.6 0 6.4 5.4 2.5 13.2l7.9 6.1C12.3 13.2 17.7 9.5 24 9.5z" />
          <path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-2.8-.4-4.1H24v8.4h12.7c-.3 2.1-1.6 5.2-4.6 7.3l7.7 6c4.5-4.2 6.7-10.3 6.7-17.6z" />
          <path fill="#FBBC05" d="M10.4 28.7A14.6 14.6 0 0 1 9.6 24c0-1.6.3-3.2.8-4.7l-7.9-6.1A24 24 0 0 0 0 24c0 3.9.9 7.5 2.5 10.8l7.9-6.1z" />
          <path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.8-5.8l-7.7-6c-2.1 1.4-4.9 2.4-8.1 2.4-6.3 0-11.7-3.7-13.6-9.9l-7.9 6.1C6.4 42.6 14.6 48 24 48z" />
        </svg>
        {label}
      </button>
    </>
  );
};

export function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [form, setForm] = useState({ email: "", password: "" });
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const u = await login(form.email, form.password);
      toast.success(`Welcome back, ${u.full_name.split(" ")[0]}`);
      nav(u.role === "admin" ? "/admin" : u.role === "partner" ? "/partner" : "/dashboard");
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  return (
    <AuthShell title="Welcome back" sub="Log in to see who's going out this week.">
      <SEO title="Log in" />
      <form onSubmit={submit} className="space-y-4" data-testid="login-form">
        <Field label="Email" type="email" required data-testid="login-email"
          value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        <Field label="Password" type="password" required data-testid="login-password"
          value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        <Link to="/forgot-password" className="block text-xs font-semibold text-slate-500 hover:text-slate-900" data-testid="forgot-link">
          Forgot your password?
        </Link>
        <button disabled={busy} data-testid="login-submit"
          className="w-full rounded-full bg-slate-900 text-white py-3.5 text-sm font-bold disabled:opacity-60 hover:bg-slate-800">
          {busy ? "Logging in…" : "Log in"}
        </button>
      </form>
      <GoogleButton label="Log in with Google" />
      <p className="mt-6 text-sm text-slate-500">New here? <Link to="/register" className="font-bold text-slate-900" data-testid="to-register">Join Buddilio</Link></p>
    </AuthShell>
  );
}

const STEPS = ["Account", "About you", "Interests", "Confirm"];

export function Register() {
  const { register } = useAuth();
  const { fmt } = useCurrency();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const isPartner = params.get("role") === "partner";
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [meta, setMeta] = useState({ cities: [], categories: [], interests: [] });
  const [f, setF] = useState({
    full_name: "", email: "", mobile: "", password: "", dob: "", gender: "female",
    city: "Delhi NCR", country: "India", bio: "", photo: "", interests: [], event_categories: [], lifestyle: [],
    is_adult: false, accept_terms: false, role: isPartner ? "partner" : "user", org_name: "",
    referral_code: params.get("ref") || "",
  });
  const [inviter, setInviter] = useState(null);

  useEffect(() => {
    const ref = params.get("ref");
    if (ref) {
      localStorage.setItem("bud_ref", ref);  // so Google sign-ups keep the referral credit
      api.get(`/referrals/${ref}`).then(({ data }) => setInviter(data)).catch(() => setInviter(null));
    }
  }, [params]);

  useEffect(() => { api.get("/meta").then(({ data }) => setMeta(data)).catch(() => {}); }, []);

  const toggle = (key, val) => setF((p) => ({
    ...p, [key]: p[key].includes(val) ? p[key].filter((x) => x !== val) : [...p[key], val],
  }));

  const next = () => {
    if (step === 0) {
      if (!f.full_name || !f.email || !f.mobile || f.password.length < 6)
        return toast.error("Fill all fields. Password needs at least 6 characters.");
    }
    if (step === 1 && !f.dob) return toast.error("Please add your date of birth.");
    setStep(step + 1);
  };

  const submit = async () => {
    if (!f.is_adult || !f.accept_terms) return toast.error("Please confirm you're 21+ and accept the policies.");
    setBusy(true);
    try {
      const u = await register(f);
      toast.success("Welcome to Buddilio!");
      nav(u.role === "partner" ? "/partner" : "/dashboard");
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  return (
    <AuthShell title={isPartner ? "Partner with Buddilio" : "Join Buddilio"} sub={`Step ${step + 1} of 4 · ${STEPS[step]}`}>
      <SEO title="Join Buddilio" />
      {inviter && (
        <div className="mb-6 rounded-2xl border border-slate-900/10 bg-slate-900/[0.04] p-4" data-testid="referral-banner">
          <p className="text-sm font-semibold">{inviter.referrer_name} invited you to Buddilio</p>
          <p className="text-xs text-slate-500 mt-1">
            Join with their link and they earn {fmt(inviter.reward)} credit once you make your first booking.
          </p>
        </div>
      )}
      <div className="flex gap-1.5 mb-7">
        {STEPS.map((s, i) => <div key={s} className={`h-1.5 flex-1 rounded-full ${i <= step ? "bg-slate-900" : "bg-slate-200"}`} />)}
      </div>

      <div className="space-y-4" data-testid="register-form">
        {step === 0 && (
          <>
            <Field label="Full name" required data-testid="reg-name" value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} />
            {isPartner && <Field label="Organisation name" data-testid="reg-org" value={f.org_name} onChange={(e) => setF({ ...f, org_name: e.target.value })} />}
            <Field label="Email" type="email" required data-testid="reg-email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
            <Field label="Mobile number" required data-testid="reg-mobile" value={f.mobile} onChange={(e) => setF({ ...f, mobile: e.target.value })} />
            <Field label="Password" type="password" required data-testid="reg-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
            {!isPartner && <GoogleButton label="Sign up with Google" testid="google-signup" />}
          </>
        )}

        {step === 1 && (
          <>
            <Field label="Date of birth (21+ only)" type="date" required data-testid="reg-dob" value={f.dob} onChange={(e) => setF({ ...f, dob: e.target.value })} />
            <label className="block">
              <span className="text-xs font-bold text-slate-600">Gender</span>
              <select data-testid="reg-gender" value={f.gender} onChange={(e) => setF({ ...f, gender: e.target.value })}
                className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm">
                {["female", "male", "non-binary", "prefer not to say"].map((g) => <option key={g} value={g}>{g}</option>)}
              </select>
            </label>
            <label className="block">
              <span className="text-xs font-bold text-slate-600">Country</span>
              <select data-testid="reg-country" value={f.country}
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
              <select data-testid="reg-city" value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })}
                className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm">
                {(((meta.countries || []).find((c) => c.name === f.country)?.cities) || meta.cities || ["Delhi NCR"]).map((c) => <option key={c}>{c}</option>)}
              </select>
            </label>
            <label className="block">
              <span className="text-xs font-bold text-slate-600">Short bio</span>
              <textarea data-testid="reg-bio" rows={3} value={f.bio} onChange={(e) => setF({ ...f, bio: e.target.value })}
                placeholder="What do you enjoy doing on a night off?"
                className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-slate-900" />
            </label>
            <ImageUpload value={f.photo} onChange={(url) => setF({ ...f, photo: url })} label="Profile photo" testid="reg-photo" />
          </>
        )}

        {step === 2 && (
          <>
            <div>
              <p className="text-xs font-bold text-slate-600 mb-2">Social interests</p>
              <div className="flex flex-wrap gap-2" data-testid="reg-interests">
                {meta.interests.map((i) => (
                  <button key={i} type="button" onClick={() => toggle("interests", i)} data-testid={`interest-${i}`}
                    className={`rounded-full px-3 py-1.5 text-xs font-semibold border ${f.interests.includes(i) ? "bg-slate-900 text-white border-slate-900" : "border-slate-200 bg-white"}`}>{i}</button>
                ))}
              </div>
            </div>
            <div>
              <p className="text-xs font-bold text-slate-600 mb-2 mt-4">Preferred event categories</p>
              <div className="flex flex-wrap gap-2" data-testid="reg-categories">
                {meta.categories.map((c) => (
                  <button key={c} type="button" onClick={() => toggle("event_categories", c)} data-testid={`category-${c}`}
                    className={`rounded-full px-3 py-1.5 text-xs font-semibold border ${f.event_categories.includes(c) ? "bg-slate-900 text-white border-slate-900" : "border-slate-200 bg-white"}`}>{c}</button>
                ))}
              </div>
            </div>
            <div>
              <p className="text-xs font-bold text-slate-600 mb-2 mt-4">Lifestyle preferences</p>
              <div className="flex flex-wrap gap-2">
                {["Early Riser", "Night Owl", "Fitness Focused", "Vegetarian", "Social Drinker", "Non Smoker", "Pet Lover", "Frequent Traveller"].map((l) => (
                  <button key={l} type="button" onClick={() => toggle("lifestyle", l)}
                    className={`rounded-full px-3 py-1.5 text-xs font-semibold border ${f.lifestyle.includes(l) ? "bg-slate-900 text-white border-slate-900" : "border-slate-200 bg-white"}`}>{l}</button>
                ))}
              </div>
            </div>
          </>
        )}

        {step === 3 && (
          <div className="space-y-4">
            <div className="rounded-2xl border border-slate-200 bg-white p-5 text-sm space-y-1">
              <p><span className="text-slate-500">Name:</span> <b>{f.full_name}</b></p>
              <p><span className="text-slate-500">Email:</span> <b>{f.email}</b></p>
              <p><span className="text-slate-500">City:</span> <b>{f.city}</b></p>
              <p><span className="text-slate-500">Interests:</span> <b>{f.interests.length}</b> selected</p>
            </div>
            {[["is_adult", "I confirm I am 21 years of age or older."],
              ["accept_terms", "I accept the Terms, Privacy Policy and Community Safety Guidelines."]].map(([k, l]) => (
              <label key={k} className="flex gap-3 items-start text-sm">
                <input type="checkbox" checked={f[k]} data-testid={`reg-${k}`} onChange={(e) => setF({ ...f, [k]: e.target.checked })} className="mt-1 h-4 w-4" />
                <span className="text-slate-600">{l}</span>
              </label>
            ))}
          </div>
        )}

        <div className="flex gap-3 pt-2">
          {step > 0 && <button onClick={() => setStep(step - 1)} data-testid="reg-back"
            className="rounded-full border border-slate-200 px-6 py-3 text-sm font-bold">Back</button>}
          {step < 3 ? (
            <button onClick={next} data-testid="reg-next" className="flex-1 rounded-full bg-slate-900 text-white py-3 text-sm font-bold hover:bg-slate-800">Continue</button>
          ) : (
            <button onClick={submit} disabled={busy} data-testid="reg-submit"
              className="flex-1 rounded-full bg-slate-900 text-white py-3 text-sm font-bold disabled:opacity-60">
              {busy ? "Creating account…" : "Create my account"}
            </button>
          )}
        </div>
        <p className="text-sm text-slate-500">Already a member? <Link to="/login" className="font-bold text-slate-900" data-testid="to-login">Log in</Link></p>
      </div>
    </AuthShell>
  );
}

export function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    try { await api.post("/auth/forgot-password", { email }); setSent(true); }
    catch (er) { toast.error(errMsg(er)); }
  };
  return (
    <AuthShell title="Reset your password" sub="We'll email you a secure reset link.">
      {sent ? (
        <p className="text-sm text-slate-600" data-testid="forgot-sent">If that email is registered, a reset link is on its way. Check your inbox.</p>
      ) : (
        <form onSubmit={submit} className="space-y-4" data-testid="forgot-form">
          <Field label="Email" type="email" required data-testid="forgot-email" value={email} onChange={(e) => setEmail(e.target.value)} />
          <button className="w-full rounded-full bg-slate-900 text-white py-3.5 text-sm font-bold" data-testid="forgot-submit">Send reset link</button>
        </form>
      )}
      <p className="mt-6 text-sm"><Link to="/login" className="font-bold">Back to log in</Link></p>
    </AuthShell>
  );
}

export function ResetPassword() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const [password, setPassword] = useState("");
  const submit = async (e) => {
    e.preventDefault();
    try {
      await api.post("/auth/reset-password", { token: params.get("token"), password });
      toast.success("Password updated. Please log in.");
      nav("/login");
    } catch (er) { toast.error(errMsg(er)); }
  };
  return (
    <AuthShell title="Choose a new password" sub="Make it something only you would guess.">
      <form onSubmit={submit} className="space-y-4" data-testid="reset-form">
        <Field label="New password" type="password" required data-testid="reset-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        <button className="w-full rounded-full bg-slate-900 text-white py-3.5 text-sm font-bold" data-testid="reset-submit">Update password</button>
      </form>
    </AuthShell>
  );
}
