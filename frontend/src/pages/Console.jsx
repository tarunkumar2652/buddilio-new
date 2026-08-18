import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Building2, Plus, RefreshCw, Search, ShieldCheck, Users, CalendarDays, Ticket, LogOut, ArrowLeft, Mail } from "lucide-react";
import { api, errMsg, fmtDate } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Spinner, SEO, Badge } from "@/components/Shared";

const Field = ({ label, ...p }) => (
  <label className="block">
    <span className="text-xs font-bold text-slate-300">{label}</span>
    <input {...p}
      className="mt-1.5 w-full rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500 focus:border-brand-pink" />
  </label>
);

const Tile = ({ icon: Icon, label, value, testid }) => (
  <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5" data-testid={testid}>
    <Icon className="h-4 w-4 text-brand-pink" />
    <p className="mt-3 text-2xl font-bold text-white">{value}</p>
    <p className="text-[11px] font-bold uppercase tracking-widest text-slate-400">{label}</p>
  </div>
);

const ConsoleAuth = () => {
  const { login, logout } = useAuth();
  const [mode, setMode] = useState("login");
  const [f, setF] = useState({ full_name: "", email: "", password: "", org_name: "", mobile: "", country: "" });
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      if (mode === "login") {
        const u = await login(f.email, f.password);
        if (!["manager", "admin"].includes(u.role)) {
          await logout();  // don't leave a member token sitting in the console
          toast.error("That's a member account. Use your console login, or request access below.");
        }
      } else {
        await api.post("/console/register", f);
        toast.success("Request sent — sign in to track your approval.");
        window.location.reload();
      }
    } catch (er) { toast.error(errMsg(er)); } finally { setBusy(false); }
  };

  return (
    <div className="min-h-screen grid place-items-center bg-slate-900 px-5 py-14" data-testid="console-auth">
      <div className="w-full max-w-md">
        <p className="overline text-brand-pink">Buddilio</p>
        <h1 className="mt-2 text-4xl font-bold text-white">Vendor Console</h1>
        <p className="mt-3 text-sm text-slate-400">
          The back office for onboarding organisers, managing their accounts and watching what they publish.
        </p>
        <form onSubmit={submit} className="mt-8 space-y-4 rounded-3xl border border-white/10 bg-white/[0.03] p-6"
          data-testid="console-auth-form">
          {mode === "register" && (
            <>
              <Field label="Your name" required data-testid="console-name" value={f.full_name}
                onChange={(e) => setF({ ...f, full_name: e.target.value })} />
              <Field label="Company / team" data-testid="console-org" value={f.org_name}
                onChange={(e) => setF({ ...f, org_name: e.target.value })} />
              <Field label="Phone" data-testid="console-mobile" value={f.mobile}
                onChange={(e) => setF({ ...f, mobile: e.target.value })} />
            </>
          )}
          <Field label="Work email" type="email" required data-testid="console-email" value={f.email}
            onChange={(e) => setF({ ...f, email: e.target.value })} />
          <Field label="Password" type="password" required data-testid="console-password" value={f.password}
            onChange={(e) => setF({ ...f, password: e.target.value })} />
          <button disabled={busy} data-testid="console-submit"
            className="w-full rounded-full brand-gradient py-3.5 text-sm font-bold text-white disabled:opacity-60">
            {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Request access"}
          </button>
          <button type="button" onClick={() => setMode(mode === "login" ? "register" : "login")}
            data-testid="console-toggle-mode" className="w-full text-xs font-bold text-slate-400 hover:text-white">
            {mode === "login" ? "Need an account? Request access" : "Already have an account? Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
};

const VendorForm = ({ onDone, cities }) => {
  const [f, setF] = useState({ full_name: "", email: "", org_name: "", city: "", mobile: "", bio: "" });
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post("/console/vendors", f);
      toast.success(`${data.org_name} created — set-password email sent.`);
      setF({ full_name: "", email: "", org_name: "", city: "", mobile: "", bio: "" });
      onDone(data);
    } catch (er) { toast.error(errMsg(er)); } finally { setBusy(false); }
  };

  return (
    <form onSubmit={submit} className="rounded-3xl border border-white/10 bg-white/[0.03] p-6 space-y-4"
      data-testid="vendor-form">
      <h2 className="text-lg font-bold text-white">Add a vendor</h2>
      <p className="text-xs text-slate-400 -mt-2">
        They get an email to set their own password, then they can publish experiences.
      </p>
      <Field label="Contact name" required data-testid="vendor-name" value={f.full_name}
        onChange={(e) => setF({ ...f, full_name: e.target.value })} />
      <Field label="Organisation" required data-testid="vendor-org" value={f.org_name}
        onChange={(e) => setF({ ...f, org_name: e.target.value })} />
      <Field label="Email" type="email" required data-testid="vendor-email" value={f.email}
        onChange={(e) => setF({ ...f, email: e.target.value })} />
      <label className="block">
        <span className="text-xs font-bold text-slate-300">City</span>
        <select required data-testid="vendor-city" value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })}
          className="mt-1.5 w-full rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm text-white focus:border-brand-pink">
          <option value="">Choose a city</option>
          {cities.map((c) => <option key={c} value={c} className="text-slate-900">{c}</option>)}
        </select>
      </label>
      <Field label="Phone" data-testid="vendor-mobile" value={f.mobile}
        onChange={(e) => setF({ ...f, mobile: e.target.value })} />
      <button disabled={busy} data-testid="vendor-create"
        className="inline-flex items-center gap-2 rounded-full brand-gradient px-5 py-3 text-sm font-bold text-white disabled:opacity-60">
        <Plus className="h-4 w-4" />{busy ? "Creating…" : "Create vendor"}
      </button>
    </form>
  );
};

const VendorDetail = ({ id, onBack, onChanged, cities }) => {
  const [v, setV] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get(`/console/vendors/${id}`).then(({ data }) => setV(data)).catch((e) => toast.error(errMsg(e)));
  }, [id]);
  useEffect(() => { load(); }, [load]);

  const patch = async (body) => {
    setBusy(true);
    try {
      const { data } = await api.patch(`/console/vendors/${id}`, body);
      setV({ ...v, ...data });
      onChanged();
      toast.success("Vendor updated");
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  const invite = async () => {
    try { const { data } = await api.post(`/console/vendors/${id}/invite`); toast.success(data.message); }
    catch (e) { toast.error(errMsg(e)); }
  };

  if (!v) return <Spinner label="Loading vendor" />;

  return (
    <div data-testid="vendor-detail">
      <button onClick={onBack} data-testid="vendor-back"
        className="inline-flex items-center gap-2 text-xs font-bold text-slate-400 hover:text-white">
        <ArrowLeft className="h-3.5 w-3.5" />All vendors
      </button>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <h2 className="text-2xl font-bold text-white">{v.org_name || v.full_name}</h2>
        <Badge tone={v.status === "active" ? "green" : "amber"}>{v.status}</Badge>
        {v.verified && <Badge tone="violet">Verified</Badge>}
      </div>
      <p className="mt-1 text-sm text-slate-400">{v.full_name} · {v.email} · {v.city}</p>

      <div className="mt-6 grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Tile icon={CalendarDays} label="Events" value={v.events || 0} testid="vendor-stat-events" />
        <Tile icon={ShieldCheck} label="Published" value={v.published || 0} testid="vendor-stat-published" />
        <Tile icon={Ticket} label="Seats sold" value={v.participants || 0} testid="vendor-stat-seats" />
        <Tile icon={Users} label="Rating" value={v.rating ? v.rating.toFixed(1) : "—"} testid="vendor-stat-rating" />
      </div>

      <div className="mt-6 grid lg:grid-cols-2 gap-6">
        <div className="rounded-3xl border border-white/10 bg-white/[0.03] p-6 space-y-4">
          <h3 className="text-sm font-bold text-white">Account</h3>
          <Field label="Contact name" data-testid="vendor-edit-name" defaultValue={v.full_name}
            onBlur={(e) => e.target.value !== v.full_name && patch({ full_name: e.target.value })} />
          <Field label="Organisation" data-testid="vendor-edit-org" defaultValue={v.org_name}
            onBlur={(e) => e.target.value !== v.org_name && patch({ org_name: e.target.value })} />
          <label className="block">
            <span className="text-xs font-bold text-slate-300">City</span>
            <select data-testid="vendor-edit-city" value={v.city || ""} onChange={(e) => patch({ city: e.target.value })}
              className="mt-1.5 w-full rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm text-white">
              {cities.map((c) => <option key={c} value={c} className="text-slate-900">{c}</option>)}
            </select>
          </label>
          <div className="flex flex-wrap gap-2 pt-1">
            <button disabled={busy} data-testid="vendor-toggle-status"
              onClick={() => patch({ status: v.status === "active" ? "suspended" : "active" })}
              className="rounded-full border border-white/15 px-4 py-2 text-xs font-bold text-white hover:bg-white/10 disabled:opacity-50">
              {v.status === "active" ? "Suspend vendor" : "Reactivate vendor"}
            </button>
            <button disabled={busy} data-testid="vendor-toggle-verified" onClick={() => patch({ verified: !v.verified })}
              className="rounded-full border border-white/15 px-4 py-2 text-xs font-bold text-white hover:bg-white/10 disabled:opacity-50">
              {v.verified ? "Remove verified badge" : "Mark verified"}
            </button>
            <button onClick={invite} data-testid="vendor-resend-invite"
              className="inline-flex items-center gap-2 rounded-full border border-white/15 px-4 py-2 text-xs font-bold text-white hover:bg-white/10">
              <Mail className="h-3.5 w-3.5" />Resend password email
            </button>
          </div>
        </div>

        <div className="rounded-3xl border border-white/10 bg-white/[0.03] p-6">
          <h3 className="text-sm font-bold text-white">Recent events</h3>
          {v.recent_events?.length ? (
            <ul className="mt-3 divide-y divide-white/5" data-testid="vendor-events">
              {v.recent_events.map((e) => (
                <li key={e.id} className="flex items-center justify-between gap-3 py-2.5">
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-semibold text-white">{e.title}</span>
                    <span className="text-[11px] text-slate-400">{e.city} · {fmtDate(e.starts_at)}</span>
                  </span>
                  <Badge tone={e.status === "published" ? "green" : "amber"}>{e.status}</Badge>
                </li>
              ))}
            </ul>
          ) : <p className="mt-3 text-sm text-slate-400">No events yet.</p>}
        </div>
      </div>
    </div>
  );
};

export default function Console() {
  const { user, loading, logout } = useAuth();
  const [summary, setSummary] = useState(null);
  const [vendors, setVendors] = useState(null);
  const [q, setQ] = useState("");
  const [openId, setOpenId] = useState("");
  const [cities, setCities] = useState([]);

  const isConsoleUser = user && ["manager", "admin"].includes(user.role);

  const load = useCallback(() => {
    api.get("/console/summary").then(({ data }) => setSummary(data)).catch(() => {});
    api.get("/console/vendors", { params: q ? { q } : {} })
      .then(({ data }) => setVendors(data.items)).catch(() => setVendors([]));
  }, [q]);

  useEffect(() => { if (isConsoleUser) load(); }, [isConsoleUser, load]);
  useEffect(() => { api.get("/meta").then(({ data }) => setCities(data.cities || [])).catch(() => {}); }, []);

  if (loading) return <Spinner label="Checking your session" />;
  if (!isConsoleUser) return <ConsoleAuth />;

  const approved = summary?.approved !== false;

  return (
    <div className="min-h-screen bg-slate-900" data-testid="console-page">
      <SEO title="Vendor Console" description="Buddilio back office for vendor onboarding and management." />
      <header className="border-b border-white/10 px-5 sm:px-8 py-4 flex items-center gap-4">
        <span className="flex items-center gap-2 font-bold text-white">
          <Building2 className="h-5 w-5 text-brand-pink" />Vendor Console
        </span>
        <span className="ml-auto text-xs text-slate-400 hidden sm:inline" data-testid="console-user">
          {user.full_name} · {user.role}
        </span>
        <a href="/" className="text-xs font-bold text-slate-400 hover:text-white" data-testid="console-to-site">Main site</a>
        <button onClick={logout} data-testid="console-logout"
          className="inline-flex items-center gap-1.5 rounded-full border border-white/15 px-3.5 py-2 text-xs font-bold text-white hover:bg-white/10">
          <LogOut className="h-3.5 w-3.5" />Sign out
        </button>
      </header>

      <main className="mx-auto max-w-6xl px-5 sm:px-8 py-10">
        {!approved && (
          <div className="mb-8 rounded-2xl border border-amber-400/30 bg-amber-400/10 p-5" data-testid="console-pending">
            <p className="text-sm font-bold text-amber-200">Your access is awaiting approval</p>
            <p className="mt-1 text-xs text-amber-100/80">
              You can look around, but adding or editing vendors unlocks once Buddilio approves your account.
            </p>
          </div>
        )}

        {openId ? (
          <VendorDetail id={openId} cities={cities} onBack={() => setOpenId("")} onChanged={load} />
        ) : (
          <>
            <h1 className="text-3xl sm:text-4xl font-bold text-white">Vendors</h1>
            <p className="mt-2 text-sm text-slate-400">Onboard organisers and keep their accounts in order.</p>

            <div className="mt-7 grid grid-cols-2 lg:grid-cols-5 gap-4">
              <Tile icon={Building2} label="Vendors" value={summary?.vendors ?? "—"} testid="console-stat-vendors" />
              <Tile icon={ShieldCheck} label="Active" value={summary?.active_vendors ?? "—"} testid="console-stat-active" />
              <Tile icon={CalendarDays} label="Events" value={summary?.events ?? "—"} testid="console-stat-events" />
              <Tile icon={ShieldCheck} label="Published" value={summary?.published ?? "—"} testid="console-stat-published" />
              <Tile icon={Ticket} label="Seats sold" value={summary?.seats_sold ?? "—"} testid="console-stat-seats" />
            </div>

            <div className="mt-8 grid lg:grid-cols-[1.4fr_1fr] gap-6 items-start">
              <div className="rounded-3xl border border-white/10 bg-white/[0.03] overflow-hidden">
                <div className="flex items-center gap-3 border-b border-white/10 p-4">
                  <span className="flex flex-1 items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-4 py-2">
                    <Search className="h-3.5 w-3.5 text-slate-400" />
                    <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search vendors"
                      data-testid="console-search"
                      className="w-full bg-transparent text-sm text-white outline-none placeholder:text-slate-500" />
                  </span>
                  <button onClick={load} data-testid="console-refresh"
                    className="rounded-full border border-white/15 p-2 text-slate-300 hover:bg-white/10">
                    <RefreshCw className="h-3.5 w-3.5" />
                  </button>
                </div>
                {!vendors ? <Spinner label="Loading vendors" /> : vendors.length === 0 ? (
                  <p className="p-8 text-center text-sm text-slate-400" data-testid="console-empty">
                    No vendors yet. Add your first one on the right.
                  </p>
                ) : (
                  <ul className="divide-y divide-white/5" data-testid="vendor-list">
                    {vendors.map((v) => (
                      <li key={v.id}>
                        <button onClick={() => setOpenId(v.id)} data-testid={`vendor-row-${v.id}`}
                          className="flex w-full items-center gap-4 p-4 text-left transition-colors hover:bg-white/[0.04]">
                          <span className="h-10 w-10 shrink-0 rounded-full brand-gradient grid place-items-center text-sm font-bold text-white">
                            {(v.org_name || v.full_name || "?")[0]}
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-sm font-semibold text-white">{v.org_name || v.full_name}</span>
                            <span className="text-[11px] text-slate-400">{v.city || "No city"} · {v.email}</span>
                          </span>
                          <span className="hidden sm:block text-[11px] text-slate-400">
                            {v.published || 0} live · {v.participants || 0} seats
                          </span>
                          <Badge tone={v.status === "active" ? "green" : "amber"}>{v.status}</Badge>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              {approved ? <VendorForm cities={cities} onDone={load} /> : (
                <div className="rounded-3xl border border-white/10 bg-white/[0.03] p-6" data-testid="vendor-form-locked">
                  <p className="text-sm font-bold text-white">Vendor creation locked</p>
                  <p className="mt-1 text-xs text-slate-400">We'll email you the moment your account is approved.</p>
                </div>
              )}
            </div>
          </>
        )}
      </main>
    </div>
  );
}
