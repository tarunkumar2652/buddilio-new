import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { ChevronRight, Search, Star } from "lucide-react";
import { api, errMsg, money, fmtDate, fileUrl } from "@/lib/api";
import { ImageUpload } from "@/components/ImageUpload";
import { Spinner, Empty, Badge, Stat, statusTone, SEO } from "@/components/Shared";
import { Verifications } from "@/components/Verifications";
import { PhotoModeration } from "@/components/PhotoModeration";
import { Companions } from "@/components/Companions";
import { Places } from "@/components/Places";
import { RichText } from "@/components/RichText";
import { RevealPii, TempPassword } from "@/components/RevealPii";
import { IdVerifications } from "@/components/IdVerifications";
import { ProvidersAdmin } from "@/components/ProvidersAdmin";
import { Ledger } from "@/components/Ledger";
import { Team } from "@/components/Team";
import { Pages, SiteContent, CityGuides } from "@/components/ContentStudio";
import { EmailTemplates } from "@/components/EmailTemplates";
import { PlansAdmin } from "@/components/PlansAdmin";
import { AgreementsAdmin } from "@/components/AgreementsAdmin";
import { VendorPayouts } from "@/components/VendorPayouts";
import { ProfileForm, EventForm } from "@/components/AdminForms";
import { Cancellations, RefundDialog } from "@/components/Cancellations";
import { PaypalWebhook } from "@/components/PaypalWebhook";
import { useAuth } from "@/context/AuthContext";

const NAV = [
  ["dashboard", "Dashboard", "analytics:view"], ["users", "Users", "members:view"],
  ["partners", "Partners", "vendors:view"], ["agreements", "Vendor agreements", "vendors:view"],
  ["verification", "Verification", "verification:manage"],
  ["managers", "Console access", "team:manage"], ["events", "Events", "events:view"],
  ["memberships", "Memberships", "finance:manage"], ["products", "Products", "finance:manage"],  ["orders", "Orders", "finance:view"], ["payments", "Payments", "finance:view"],
  ["cancellations", "Cancellations & refunds", "finance:manage"],
  ["payouts", "Payouts", "payouts:view"], ["vendorpay", "Vendor settlements", "payouts:view"],
  ["coupons", "Coupons", "finance:manage"],
  ["reports", "Reports", "moderation:manage"], ["reviews", "Reviews", "moderation:manage"],
  ["photos", "Photo wall", "moderation:manage"], ["companions", "Hangouts", "members:manage"],
  ["idchecks", "ID checks", "verification:manage"], ["providers", "Travel crew", "verification:manage"],
  ["ledger", "Ledger", "finance:view"], ["places", "Countries & cities", "content:manage"],
  ["content", "Content", "content:manage"],
  ["pages", "Pages", "content:manage"], ["sections", "Site sections", "content:manage"],
  ["guides", "City guides", "content:manage"], ["emails", "Emails", "content:manage"],
  ["settings", "Settings", "content:manage"], ["audit", "Audit logs", "audit:view"],
  ["team", "Team & roles", "team:manage"],
];

const VendorActivity = () => {
  const [items, setItems] = useState(null);
  useEffect(() => {
    api.get("/admin/vendor-activity").then(({ data }) => setItems(data.items)).catch(() => setItems([]));
  }, []);

  const label = {
    "vendor.create": "created vendor", "vendor.update": "updated vendor", "vendor.invite": "invited vendor",
    "vendor.invite_revoke": "revoked an invite", "manager.approve": "approved console access",
    "manager.suspend": "suspended console access", "manager.reject": "rejected console access",
  };

  if (!items) return <Spinner />;
  if (!items.length) return <p className="text-sm text-slate-500" data-testid="activity-empty">No vendor activity yet.</p>;

  return (
    <ul className="divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white" data-testid="activity-list">
      {items.map((a) => (
        <li key={a.id} className="flex flex-wrap items-center gap-x-2 gap-y-1 px-4 py-3 text-sm"
          data-testid={`activity-row-${a.id}`}>
          <span className="font-semibold">{a.actor}</span>
          <span className="text-slate-500">{label[a.action] || a.action}</span>
          {a.target && <span className="font-semibold">{a.target}</span>}
          {a.meta?.email && !a.target && <span className="text-slate-500">{a.meta.email}</span>}
          {a.meta?.status && <Badge tone={a.meta.status === "active" ? "green" : "amber"}>{a.meta.status}</Badge>}
          <span className="ml-auto text-[11px] text-slate-400">{fmtDate(a.created_at)}</span>
        </li>
      ))}
    </ul>
  );
};

const Managers = () => {
  const [items, setItems] = useState(null);
  const load = () => api.get("/admin/managers").then(({ data }) => setItems(data.items)).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); }, []);

  const act = async (id, action) => {
    try { await api.patch(`/admin/managers/${id}`, { action }); toast.success(`Console account ${action}d`); load(); }
    catch (e) { toast.error(errMsg(e)); }
  };

  if (!items) return <Spinner />;
  if (!items.length) return <p className="text-sm text-slate-500" data-testid="managers-empty">No console accounts requested yet.</p>;

  return (
    <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white" data-testid="managers-table">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
          <tr>{["Name", "Email", "Company", "Vendors", "Status", ""].map((h) => <th key={h} className="px-4 py-3">{h}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {items.map((m) => (
            <tr key={m.id} data-testid={`manager-row-${m.id}`}>
              <td className="px-4 py-3 font-semibold">{m.full_name}</td>
              <td className="px-4 py-3 text-slate-500">{m.email}</td>
              <td className="px-4 py-3 text-slate-500">{m.org_name || "—"}</td>
              <td className="px-4 py-3">{m.vendors}</td>
              <td className="px-4 py-3"><Badge tone={m.status === "active" ? "green" : m.status === "pending" ? "amber" : "red"}>{m.status}</Badge></td>
              <td className="px-4 py-3">
                <div className="flex gap-2">
                  {m.status !== "active" && (
                    <button onClick={() => act(m.id, "approve")} data-testid={`manager-approve-${m.id}`}
                      className="rounded-full bg-slate-900 px-3.5 py-1.5 text-xs font-bold text-white">Approve</button>
                  )}
                  {m.status === "active" && (
                    <button onClick={() => act(m.id, "suspend")} data-testid={`manager-suspend-${m.id}`}
                      className="rounded-full border border-slate-200 px-3.5 py-1.5 text-xs font-bold">Suspend</button>
                  )}
                  {m.status === "pending" && (
                    <button onClick={() => act(m.id, "reject")} data-testid={`manager-reject-${m.id}`}
                      className="rounded-full border border-slate-200 px-3.5 py-1.5 text-xs font-bold text-rose-600">Reject</button>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

const Input = ({ label, ...p }) => (
  <label className="block"><span className="text-xs font-bold text-slate-600">{label}</span>
    <input {...p} className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm" /></label>
);

const GROUPS = [
  ["Overview", ["dashboard", "events", "settings"]],
  ["Money", ["orders", "payments", "cancellations", "payouts", "vendorpay", "coupons", "memberships", "products", "ledger"]],
  ["Content", ["content", "pages", "sections", "guides", "emails", "places"]],
  ["People", ["users", "partners", "agreements", "managers", "companions", "team"]],
  ["Trust", ["verification", "idchecks", "providers", "reports", "reviews", "photos", "audit"]],
];

export default function Admin() {
  const { user } = useAuth();
  const perms = user?.permissions;
  const nav = NAV.filter(([, , p]) => !perms || perms.includes(p));
  const [tab, setTab] = useState("");
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [favs, setFavs] = useState([]);
  const active = tab && nav.some(([v]) => v === tab) ? tab : (nav[0]?.[0] || "dashboard");
  const label = (nav.find(([v]) => v === active) || [])[1] || "Dashboard";

  useEffect(() => {
    api.get("/me/admin-nav").then(({ data }) => setFavs(data.favourites || [])).catch(() => setFavs([]));
  }, []);

  const toggleFav = (v) => {
    const next = favs.includes(v) ? favs.filter((x) => x !== v) : [...favs, v];
    setFavs(next);
    api.put("/me/admin-nav", { favourites: next })
      .then(() => toast.success(favs.includes(v) ? "Removed from favourites" : "Pinned to favourites"))
      .catch((e) => toast.error(errMsg(e)));
  };

  const term = q.trim().toLowerCase();
  const matches = term ? nav.filter(([, l]) => l.toLowerCase().includes(term)) : [];
  const baseGroups = GROUPS
    .map(([title, keys]) => [title, keys.map((k) => nav.find(([v]) => v === k)).filter(Boolean)])
    .filter(([, items]) => items.length);
  const favGroup = favs.map((k) => nav.find(([v]) => v === k)).filter(Boolean);
  const groups = term
    ? (matches.length ? [["Results", matches]] : [])
    : (favGroup.length ? [["Favourites", favGroup], ...baseGroups] : baseGroups);

  const pick = (v) => { setTab(v); setOpen(false); setQ(""); };

  return (
    <div className="grid lg:grid-cols-[264px_1fr]" data-testid="admin-page">
      <SEO title="Admin" />
      <aside className={`border-r border-slate-200 bg-white ${open ? "block" : "hidden lg:block"}`}
        data-testid="admin-sidebar">
        <div className="p-6" data-testid="admin-sidebar-inner">
          <p className="overline">Control centre</p>
          <p className="mt-1.5 font-display text-lg font-bold">Buddilio admin</p>
          <div className="relative mt-5">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
            <input value={q} onChange={(e) => setQ(e.target.value)} data-testid="admin-nav-search"
              onKeyDown={(e) => { if (e.key === "Enter" && matches[0]) pick(matches[0][0]); }}
              placeholder="Search sections…"
              className="w-full rounded-lg border border-slate-200 bg-slate-50 py-2 pl-9 pr-3 text-[13px] outline-none focus:border-brand-magenta focus:bg-white" />
          </div>
          <nav className="mt-6 space-y-7">
            {groups.map(([title, items]) => (
              <div key={title}>
                <p className="px-3 text-[10px] font-bold uppercase tracking-[0.18em] text-slate-400">{title}</p>
                <div className="mt-2 space-y-0.5">
                  {items.map(([v, l]) => (
                    <div key={`${title}-${v}`} className="group flex items-center gap-1">
                      <button onClick={() => pick(v)} data-testid={`admin-tab-${v}`}
                        className={`flex flex-1 items-center gap-2 rounded-lg px-3 py-2 text-left text-[13px] font-semibold transition-colors ${
                          active === v ? "bg-brand-magenta/10 text-brand-magenta" : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"}`}>
                        <span className={`h-1.5 w-1.5 rounded-full ${active === v ? "bg-brand-magenta" : "bg-transparent"}`} />
                        {l}
                      </button>
                      <button onClick={() => toggleFav(v)} data-testid={`admin-fav-${v}`}
                        aria-label={favs.includes(v) ? `Unpin ${l}` : `Pin ${l}`}
                        className="rounded-md p-1.5 text-slate-300 transition-colors hover:text-amber-500">
                        <Star className={`h-3.5 w-3.5 ${favs.includes(v) ? "fill-amber-400 text-amber-400" : ""}`} />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            ))}
            {term && !matches.length && (
              <p className="px-3 text-xs text-slate-400" data-testid="admin-nav-no-results">No section matches “{q}”.</p>
            )}
          </nav>
        </div>
      </aside>

      <div className="min-w-0 px-4 sm:px-8 lg:px-12 py-8 pb-28">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="overline">Super admin</p>
            <h1 className="mt-2 text-3xl font-bold">{label}</h1>
          </div>
          <button onClick={() => setOpen(!open)} data-testid="admin-menu-toggle"
            className="lg:hidden inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2 text-xs font-bold">
            {open ? "Close menu" : "All sections"}<ChevronRight className="h-3.5 w-3.5" />
          </button>
        </div>
        <div className="mt-8">
        {active === "dashboard" && <Overview />}
        {active === "users" && <Users key="u" role="user" />}
        {active === "partners" && <Users key="p" role="partner" />}
        {active === "verification" && <Verifications />}
        {active === "managers" && (
          <div className="space-y-8">
            <Managers />
            <div>
              <h2 className="mb-3 text-sm font-bold uppercase tracking-widest text-slate-500">Vendor activity log</h2>
              <VendorActivity />
            </div>
          </div>
        )}
        {active === "events" && <Events />}
        {active === "memberships" && <PlansAdmin />}
        {active === "agreements" && <AgreementsAdmin />}
        {active === "products" && <Crud path="products" title="Products & passes"
          fields={[["name", "text"], ["description", "text"], ["price", "number"], ["discount_percent", "number"], ["tax_percent", "number"], ["image", "image"], ["validity_days", "number"], ["city", "text"], ["inventory", "number"], ["member_discount_percent", "number"], ["price_overrides", "json"], ["active", "bool"]]}
          blank={{ name: "", description: "", price: 0, discount_percent: 0, tax_percent: 18, image: "", validity_days: 30, city: "All India", inventory: 100, member_discount_percent: 10, price_overrides: {}, active: true }} />}
        {active === "coupons" && <Crud path="coupons" title="Coupons"
          fields={[["code", "text"], ["discount_type", "text"], ["value", "number"], ["min_order", "number"], ["usage_limit", "number"], ["members_only", "bool"], ["expires_at", "text"], ["active", "bool"]]}
          blank={{ code: "", discount_type: "percent", value: 10, min_order: 0, usage_limit: 100, members_only: false, expires_at: "", active: true }} />}
        {(active === "orders" || active === "payments") && <Orders payments={active === "payments"} />}
        {active === "cancellations" && <Cancellations />}
        {active === "payouts" && <Payouts />}
        {active === "vendorpay" && <VendorPayouts />}
        {active === "reports" && <Reports />}
        {active === "reviews" && <ReviewsMod />}
        {active === "photos" && <PhotoModeration />}
        {active === "companions" && <Companions />}
        {active === "idchecks" && <IdVerifications />}
        {active === "providers" && <ProvidersAdmin />}
        {active === "ledger" && <Ledger />}
        {active === "places" && <Places />}
        {active === "content" && <Content />}
        {active === "settings" && <Settings />}
        {active === "audit" && <Audit />}
        {active === "team" && <Team />}
        {active === "pages" && <Pages />}
        {active === "sections" && <SiteContent />}
        {active === "guides" && <CityGuides />}
        {active === "emails" && <EmailTemplates />}
        </div>
      </div>
    </div>
  );
}

function Overview() {
  const [days, setDays] = useState(30);
  const [s, setS] = useState(null);
  useEffect(() => { setS(null); api.get("/admin/stats", { params: { days } }).then(({ data }) => setS(data)).catch(() => setS({})); }, [days]);
  if (!s) return <Spinner />;
  return (
    <div data-testid="admin-overview">
      <div className="flex gap-2">
        {[7, 30, 90, 365].map((d) => (
          <button key={d} onClick={() => setDays(d)} data-testid={`admin-range-${d}`}
            className={`rounded-full px-4 py-2 text-xs font-bold border ${days === d ? "bg-slate-900 text-white border-slate-900" : "bg-white border-slate-200"}`}>Last {d}d</button>
        ))}
      </div>
      <div className="mt-6 grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat label="Total users" value={s.total_users} testid="admin-stat-users" />
        <Stat label="New registrations" value={s.new_users} testid="admin-stat-new" />
        <Stat label="Active users" value={s.active_users} testid="admin-stat-active" />
        <Stat label="Premium members" value={s.premium_members} testid="admin-stat-premium" />
        <Stat label="Partners" value={s.partners} />
        <Stat label="Events" value={s.events} />
        <Stat label="Upcoming events" value={s.upcoming_events} />
        <Stat label="Participations" value={s.participations} />
        <Stat label="Gross sales" value={money(s.gross_sales)} testid="admin-stat-sales" />
        <Stat label="Membership revenue" value={money(s.membership_revenue)} />
        <Stat label="Event revenue" value={money(s.event_revenue)} />
        <Stat label="Pass revenue" value={money(s.pass_revenue)} />
        <Stat label="Refunds" value={s.refunds} />
        <Stat label="Pending event approvals" value={s.pending_events} testid="admin-stat-pending-events" />
        <Stat label="Open reports" value={s.open_reports} testid="admin-stat-reports" />
        <Stat label="Flagged reviews" value={s.flagged_reviews} testid="admin-stat-flagged-reviews" />
      </div>
      <div className="mt-6 grid lg:grid-cols-2 gap-4">
        <div className="rounded-xl border border-slate-200 bg-white p-5">
          <p className="overline">Revenue trend</p>
          <div className="h-64 mt-4">
            <ResponsiveContainer><LineChart data={s.revenue_series}>
              <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} />
              <Tooltip /><Line type="monotone" dataKey="amount" stroke="#0F172A" strokeWidth={2} dot={false} />
            </LineChart></ResponsiveContainer>
          </div>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-5">
          <p className="overline">Registrations</p>
          <div className="h-64 mt-4">
            <ResponsiveContainer><BarChart data={s.registration_series}>
              <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} />
              <Tooltip /><Bar dataKey="count" fill="#0F172A" radius={[4, 4, 0, 0]} />
            </BarChart></ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
}

function Users({ role }) {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [data, setData] = useState(null);
  const [page, setPage] = useState(1);
  const [form, setForm] = useState(null);
  const load = useCallback(() => {
    api.get("/admin/users", { params: { q, role, status, page, limit: 20 } }).then(({ data }) => setData(data)).catch(() => setData({ items: [] }));
  }, [q, role, status, page]);
  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [load]);

  const act = async (u, body, msg) => {
    try { await api.patch(`/admin/users/${u.id}`, body); toast.success(msg); load(); }
    catch (e) { toast.error(errMsg(e)); }
  };

  const remove = async (u) => {
    const hard = window.confirm(`Delete ${u.full_name}?\n\nOK = permanent delete (removes everything)\nCancel = choose soft delete next.`);
    if (!hard && !window.confirm(`Soft delete ${u.full_name}? Their account is disabled but everything is kept and can be restored.`)) return;
    try {
      await api.delete(`/admin/users/${u.id}`, { params: { mode: hard ? "hard" : "soft" } });
      toast.success(hard ? "Profile permanently deleted." : "Profile disabled — you can restore it any time.");
      load();
    } catch (e) { toast.error(errMsg(e)); }
  };

  const restore = async (u) => {
    try { await api.post(`/admin/users/${u.id}/restore`); toast.success("Profile restored."); load(); }
    catch (e) { toast.error(errMsg(e)); }
  };

  if (!data) return <Spinner />;
  return (
    <div data-testid={`admin-users-${role}`}>
      {form && <ProfileForm profile={form.id ? form : null} onClose={() => setForm(null)} onSaved={load} />}
      <div className="flex flex-wrap gap-3">
        <input data-testid="admin-user-search" value={q} onChange={(e) => { setPage(1); setQ(e.target.value); }} placeholder="Search name or email…"
          className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm w-72" />
        <select data-testid="admin-user-status" value={status} onChange={(e) => setStatus(e.target.value)} className="rounded-xl border border-slate-200 px-3 py-2.5 text-sm">
          <option value="">All statuses</option>{["active", "suspended", "banned", "deleted"].map((s) => <option key={s}>{s}</option>)}
        </select>
        <button onClick={() => setForm({ role: role === "partner" ? "partner" : "user" })} data-testid="admin-user-new"
          className="rounded-full bg-slate-900 px-5 py-2.5 text-xs font-bold text-white">New profile</button>
      </div>
      <div className="mt-5 rounded-xl border border-slate-200 bg-white overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left"><tr>
            {["Member", "City", "Status", "Membership", "Verified", "Actions"].map((h) => <th key={h} className="px-4 py-3 font-semibold text-xs uppercase tracking-wider text-slate-500">{h}</th>)}
          </tr></thead>
          <tbody className="divide-y divide-slate-100">
            {data.items.map((u) => (
              <tr key={u.id} data-testid={`admin-user-row-${u.id}`}>
                <td className="px-4 py-3">
                  <Link to={`/u/${u.id}`} className="font-semibold hover:underline">{u.full_name}</Link>
                  <RevealPii user={u} canReveal={!!data.can_reveal} />
                </td>
                <td className="px-4 py-3">{u.city}{u.org_name ? ` · ${u.org_name}` : ""}</td>
                <td className="px-4 py-3"><Badge tone={statusTone(u.status)}>{u.status}</Badge></td>
                <td className="px-4 py-3 text-xs">{u.membership?.plan_name || "—"}</td>
                <td className="px-4 py-3 text-xs">{u.verified ? "Yes" : "No"}</td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1.5">
                    {u.status !== "active" && <button onClick={() => act(u, { status: "active" }, "Member activated")} data-testid={`activate-${u.id}`} className="rounded-full border border-slate-200 px-3 py-1.5 text-[11px] font-bold">Activate</button>}
                    {u.status !== "suspended" && <button onClick={() => act(u, { status: "suspended" }, "Member suspended")} data-testid={`suspend-${u.id}`} className="rounded-full border border-slate-200 px-3 py-1.5 text-[11px] font-bold">Suspend</button>}
                    {u.status !== "banned" && <button onClick={() => act(u, { status: "banned" }, "Member banned")} data-testid={`ban-${u.id}`} className="rounded-full border border-red-200 text-red-600 px-3 py-1.5 text-[11px] font-bold">Ban</button>}
                    {!u.verified && <button onClick={() => act(u, { verified: true }, "Member verified")} data-testid={`verify-${u.id}`} className="rounded-full bg-slate-900 text-white px-3 py-1.5 text-[11px] font-bold">Verify</button>}
                    <button onClick={() => setForm(u)} data-testid={`edit-profile-${u.id}`} className="rounded-full border border-slate-200 px-3 py-1.5 text-[11px] font-bold">Edit</button>
                    {data.can_reveal && <TempPassword user={u} />}
                    {u.status === "deleted"
                      ? <button onClick={() => restore(u)} data-testid={`restore-${u.id}`} className="rounded-full border border-emerald-200 text-emerald-700 px-3 py-1.5 text-[11px] font-bold">Restore</button>
                      : <button onClick={() => remove(u)} data-testid={`delete-profile-${u.id}`} className="rounded-full border border-red-200 text-red-600 px-3 py-1.5 text-[11px] font-bold">Delete</button>}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!data.items.length && <p className="p-6 text-sm text-slate-500">No members found.</p>}
      </div>
      {data.total > 20 && (
        <div className="mt-4 flex gap-2">
          <button disabled={page === 1} onClick={() => setPage(page - 1)} className="rounded-full border border-slate-200 bg-white px-4 py-2 text-xs font-bold disabled:opacity-40">Prev</button>
          <span className="text-xs py-2">Page {page} / {Math.ceil(data.total / 20)}</span>
          <button disabled={page >= Math.ceil(data.total / 20)} onClick={() => setPage(page + 1)} className="rounded-full border border-slate-200 bg-white px-4 py-2 text-xs font-bold disabled:opacity-40">Next</button>
        </div>
      )}
    </div>
  );
}

function Events() {
  const [status, setStatus] = useState("submitted");
  const [items, setItems] = useState(null);
  const [form, setForm] = useState(null);
  const load = useCallback(() => {
    api.get("/admin/events", { params: { status } }).then(({ data }) => setItems(data.items)).catch(() => setItems([]));
  }, [status]);
  useEffect(() => { load(); }, [load]);

  const moderate = async (id, action) => {
    try { await api.post(`/admin/events/${id}/moderate`, { action }); toast.success(`Event ${action === "approve" ? "approved and published" : "rejected"}`); load(); }
    catch (e) { toast.error(errMsg(e)); }
  };

  const remove = async (ev) => {
    if (!window.confirm(`Delete “${ev.title}”? Bookings and photos for it are removed too.`)) return;
    try { await api.delete(`/admin/events/${ev.id}`, { params: { force: true } }); toast.success("Event deleted."); load(); }
    catch (e) { toast.error(errMsg(e)); }
  };

  if (!items) return <Spinner />;
  return (
    <div data-testid="admin-events">
      {form && <EventForm event={form.id ? form : null} onClose={() => setForm(null)} onSaved={load} />}
      <div className="flex gap-2 flex-wrap">
        {["submitted", "published", "draft", "rejected", ""].map((s) => (
          <button key={s || "all"} onClick={() => setStatus(s)} data-testid={`admin-event-filter-${s || "all"}`}
            className={`rounded-full px-4 py-2 text-xs font-bold border ${status === s ? "bg-slate-900 text-white border-slate-900" : "bg-white border-slate-200"}`}>{s || "All"}</button>
        ))}
        <button onClick={() => setForm({})} data-testid="admin-event-new"
          className="rounded-full bg-slate-900 px-5 py-2 text-xs font-bold text-white">New event</button>
      </div>
      <div className="mt-5 space-y-3">
        {items.length ? items.map((ev) => (
          <div key={ev.id} className="rounded-xl border border-slate-200 bg-white p-4 flex flex-wrap items-center gap-4" data-testid={`admin-event-${ev.id}`}>
            {ev.cover_image && <img src={fileUrl(ev.cover_image)} alt="" className="h-14 w-20 rounded-lg object-cover" />}
            <div className="flex-1 min-w-[200px]">
              <p className="font-semibold text-sm">{ev.title}</p>
              <p className="text-xs text-slate-500 mt-0.5">{ev.partner_name} · {ev.city} · {fmtDate(ev.starts_at)} · {ev.price > 0 ? money(ev.price) : "Free"}</p>
            </div>
            <Badge tone={statusTone(ev.status)}>{ev.status}</Badge>
            <div className="flex gap-2">
              {ev.status !== "published" && <button onClick={() => moderate(ev.id, "approve")} data-testid={`approve-event-${ev.id}`} className="rounded-full bg-slate-900 text-white px-4 py-2 text-xs font-bold">Approve</button>}
              {ev.status !== "rejected" && <button onClick={() => moderate(ev.id, "reject")} data-testid={`reject-event-${ev.id}`} className="rounded-full border border-red-200 text-red-600 px-4 py-2 text-xs font-bold">Reject</button>}
              {ev.status === "published" && <Link to={`/events/${ev.id}`} className="rounded-full border border-slate-200 px-4 py-2 text-xs font-bold">View</Link>}
              <button onClick={() => setForm(ev)} data-testid={`edit-event-${ev.id}`} className="rounded-full border border-slate-200 px-4 py-2 text-xs font-bold">Edit</button>
              <button onClick={() => remove(ev)} data-testid={`delete-event-${ev.id}`} className="rounded-full border border-red-200 px-4 py-2 text-xs font-bold text-red-600">Delete</button>
            </div>
          </div>
        )) : <Empty title="Nothing here" sub="No events with this status." />}
      </div>
    </div>
  );
}

function Orders({ payments }) {
  const [status, setStatus] = useState("");
  const [items, setItems] = useState(null);
  const load = useCallback(() => {
    api.get("/admin/orders", { params: { status } }).then(({ data }) => setItems(data.items)).catch(() => setItems([]));
  }, [status]);
  useEffect(() => { load(); }, [load]);

  const [refunding, setRefunding] = useState(null);
  if (!items) return <Spinner />;
  return (
    <div data-testid="admin-orders">
      {payments && <PaypalWebhook />}
      <div className="flex gap-2">
        {["", "paid", "pending", "failed"].map((s) => (
          <button key={s || "all"} onClick={() => setStatus(s)} data-testid={`admin-order-filter-${s || "all"}`}
            className={`rounded-full px-4 py-2 text-xs font-bold border ${status === s ? "bg-slate-900 text-white border-slate-900" : "bg-white border-slate-200"}`}>{s || "All"}</button>
        ))}
      </div>
      <div className="mt-5 rounded-xl border border-slate-200 bg-white overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left"><tr>
            {["Order", "Item", "Type", "Amount", "Payment", "Refund", payments ? "Txn" : "Actions"].map((h) => <th key={h} className="px-4 py-3 text-xs uppercase tracking-wider text-slate-500 font-semibold">{h}</th>)}
          </tr></thead>
          <tbody className="divide-y divide-slate-100">
            {items.map((o) => (
              <tr key={o.id} data-testid={`admin-order-${o.id}`}>
                <td className="px-4 py-3"><p className="font-semibold">#{o.order_no}</p><p className="text-xs text-slate-500">{fmtDate(o.created_at)}</p></td>
                <td className="px-4 py-3">{o.item_name}</td>
                <td className="px-4 py-3 text-xs">{o.kind}</td>
                <td className="px-4 py-3 font-semibold">{money(o.total)}</td>
                <td className="px-4 py-3"><Badge tone={statusTone(o.payment_status)}>{o.payment_status}</Badge></td>
                <td className="px-4 py-3 text-xs">
                  {o.refund_status}
                  {Number(o.refunded_amount || 0) > 0 && <p className="text-[10px] text-slate-400">{money(o.refunded_amount)} back</p>}
                </td>
                <td className="px-4 py-3">
                  {payments ? <span className="text-xs text-slate-500">{o.transaction_id || "—"}</span>
                    : o.payment_status === "paid" && o.refund_status !== "refunded" ? (
                      <button onClick={() => setRefunding(o)} data-testid={`refund-${o.id}`} className="rounded-full border border-red-200 text-red-600 px-3 py-1.5 text-[11px] font-bold">
                        {o.refund_status === "partial" ? "Refund more" : "Refund"}
                      </button>
                    ) : <span className="text-xs text-slate-400">—</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!items.length && <p className="p-6 text-sm text-slate-500">No orders.</p>}
      </div>
      {refunding && <RefundDialog order={refunding} onClose={() => setRefunding(null)} onDone={load} />}
    </div>
  );
}

function Payouts() {
  const [items, setItems] = useState(null);
  const [status, setStatus] = useState("");
  const load = useCallback(() => {
    api.get("/admin/payouts", { params: { status } }).then(({ data }) => setItems(data.items)).catch(() => setItems([]));
  }, [status]);
  useEffect(() => { load(); }, [load]);

  const pay = async (id) => {
    try { const { data } = await api.post(`/admin/payouts/${id}/pay`, {}); toast.success(`Payout settled · ${data.reference}`); load(); }
    catch (e) { toast.error(errMsg(e)); }
  };
  const generate = async () => {
    try { const { data } = await api.post("/admin/payouts/generate"); toast.success(`${data.created} new payout${data.created === 1 ? "" : "s"} generated`); load(); }
    catch (e) { toast.error(errMsg(e)); }
  };

  if (!items) return <Spinner />;
  const pending = items.filter((p) => p.status === "pending");
  return (
    <div data-testid="admin-payouts">
      <div className="flex flex-wrap items-center gap-2">
        {["", "pending", "paid"].map((s) => (
          <button key={s || "all"} onClick={() => setStatus(s)} data-testid={`payout-filter-${s || "all"}`}
            className={`rounded-full px-4 py-2 text-xs font-bold border ${status === s ? "bg-slate-900 text-white border-slate-900" : "bg-white border-slate-200"}`}>{s || "All"}</button>
        ))}
        <button onClick={generate} data-testid="generate-payouts" className="ml-auto rounded-full border border-slate-900 px-4 py-2 text-xs font-bold">Run settlement now</button>
      </div>
      <div className="mt-4 grid sm:grid-cols-3 gap-4">
        <Stat label="Pending payouts" value={pending.length} testid="payouts-pending-count" />
        <Stat label="Pending amount" value={money(pending.reduce((s, p) => s + p.net, 0))} testid="payouts-pending-amount" />
        <Stat label="Settled amount" value={money(items.filter((p) => p.status === "paid").reduce((s, p) => s + p.net, 0))} testid="payouts-paid-amount" />
      </div>
      <div className="mt-5 rounded-xl border border-slate-200 bg-white overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left"><tr>
            {["Partner", "Event", "Gross", "Fee", "Net", "Status", "Action"].map((h) => (
              <th key={h} className="px-4 py-3 text-xs uppercase tracking-wider text-slate-500 font-semibold">{h}</th>))}
          </tr></thead>
          <tbody className="divide-y divide-slate-100">
            {items.map((p) => (
              <tr key={p.id} data-testid={`admin-payout-${p.id}`}>
                <td className="px-4 py-3"><p className="font-semibold">{p.partner?.org_name || p.partner?.full_name || "—"}</p><p className="text-xs text-slate-500">{p.partner?.email}</p></td>
                <td className="px-4 py-3">{p.event_title}<p className="text-xs text-slate-500">{p.orders} paid orders · {fmtDate(p.created_at)}</p></td>
                <td className="px-4 py-3">{money(p.gross)}</td>
                <td className="px-4 py-3 text-slate-500">− {money(p.fee)}</td>
                <td className="px-4 py-3 font-semibold">{money(p.net)}</td>
                <td className="px-4 py-3"><Badge tone={p.status === "paid" ? "green" : "amber"}>{p.status}</Badge></td>
                <td className="px-4 py-3">
                  {p.status === "pending"
                    ? <button onClick={() => pay(p.id)} data-testid={`pay-payout-${p.id}`} className="rounded-full bg-slate-900 text-white px-4 py-1.5 text-[11px] font-bold">Mark paid</button>
                    : <span className="text-xs text-slate-500">{p.reference}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!items.length && <p className="p-6 text-sm text-slate-500">No payouts yet — run settlement after events finish.</p>}
      </div>
    </div>
  );
}

function Reports() {
  const [items, setItems] = useState(null);
  const load = () => api.get("/admin/reports").then(({ data }) => setItems(data.items)).catch(() => setItems([]));
  useEffect(() => { load(); }, []);
  const resolve = async (id, action) => {
    try { await api.post(`/admin/reports/${id}/resolve`, { action }); toast.success(`Report resolved (${action})`); load(); }
    catch (e) { toast.error(errMsg(e)); }
  };
  if (!items) return <Spinner />;
  return (
    <div className="space-y-3" data-testid="admin-reports">
      {items.length ? items.map((r) => (
        <div key={r.id} className="rounded-xl border border-slate-200 bg-white p-5" data-testid={`admin-report-${r.id}`}>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <Badge tone={r.status === "open" ? "amber" : "green"}>{r.status}</Badge>
                <Badge>{r.target_type}</Badge>
              </div>
              <p className="mt-2 font-semibold text-sm">{r.reason}</p>
              <p className="text-sm text-slate-500 mt-1">{r.details}</p>
              <p className="text-xs text-slate-400 mt-2">
                Reported by {r.reporter_email} · {fmtDate(r.created_at)}
                {r.target ? ` · target: ${r.target.full_name} (${r.target.status})` : ""}
              </p>
            </div>
            {r.status === "open" && (
              <div className="flex flex-wrap gap-2">
                <button onClick={() => resolve(r.id, "dismiss")} data-testid={`dismiss-report-${r.id}`} className="rounded-full border border-slate-200 px-4 py-2 text-xs font-bold">Dismiss</button>
                <button onClick={() => resolve(r.id, "suspend")} data-testid={`suspend-report-${r.id}`} className="rounded-full border border-amber-300 text-amber-700 px-4 py-2 text-xs font-bold">Suspend user</button>
                <button onClick={() => resolve(r.id, "ban")} data-testid={`ban-report-${r.id}`} className="rounded-full bg-red-600 text-white px-4 py-2 text-xs font-bold">Ban user</button>
              </div>
            )}
          </div>
        </div>
      )) : <Empty title="Moderation queue is clear" sub="No open reports right now." />}
    </div>
  );
}

function ReviewsMod() {
  const [status, setStatus] = useState("flagged");
  const [data, setData] = useState(null);
  const load = useCallback(() => {
    api.get("/admin/reviews", { params: { status } }).then(({ data }) => setData(data)).catch(() => setData({ items: [] }));
  }, [status]);
  useEffect(() => { load(); }, [load]);

  const moderate = async (id, action) => {
    if (action === "delete" && !window.confirm("Delete this review permanently?")) return;
    try {
      await api.post(`/admin/reviews/${id}/moderate`, { action });
      toast.success(action === "hide" ? "Review hidden from the event page" : action === "publish" ? "Review kept visible" : "Review deleted");
      load();
    } catch (e) { toast.error(errMsg(e)); }
  };

  if (!data) return <Spinner />;
  const FILTERS = [["flagged", "Flagged"], ["published", "Published"], ["hidden", "Hidden"], ["", "All"]];
  return (
    <div data-testid="admin-reviews">
      <div className="flex flex-wrap gap-2">
        {FILTERS.map(([v, l]) => (
          <button key={v || "all"} onClick={() => setStatus(v)} data-testid={`review-filter-${v || "all"}`}
            className={`rounded-full px-4 py-2 text-xs font-bold border ${status === v ? "bg-slate-900 text-white border-slate-900" : "bg-white border-slate-200"}`}>{l}</button>
        ))}
      </div>
      <div className="mt-4 grid sm:grid-cols-3 gap-4">
        <Stat label="Flagged now" value={data.flagged ?? 0} testid="reviews-flagged-count" />
        <Stat label="Hidden" value={data.hidden ?? 0} testid="reviews-hidden-count" />
        <Stat label="Total reviews" value={data.total ?? 0} testid="reviews-total-count" />
      </div>
      <div className="mt-5 space-y-3">
        {data.items.length ? data.items.map((r) => (
          <div key={r.id} className="rounded-xl border border-slate-200 bg-white p-5" data-testid={`admin-review-${r.id}`}>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-[240px] flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={r.status === "hidden" ? "red" : "green"}>{r.status || "published"}</Badge>
                  {r.flag_count > 0 && <Badge tone="amber">{r.flag_count} flag{r.flag_count > 1 ? "s" : ""}</Badge>}
                  <span className="text-xs font-bold">{r.rating}/5</span>
                </div>
                <p className="mt-2 text-sm font-semibold">{r.event_title}<span className="text-slate-400 font-normal"> · {r.partner_name}</span></p>
                <p className="mt-1.5 text-sm text-slate-600 leading-relaxed">{r.comment || <span className="text-slate-400">No written comment</span>}</p>
                <p className="text-xs text-slate-400 mt-2">By {r.user_name} ({r.user_email}) · {fmtDate(r.created_at)}</p>
                {r.reply && <p className="mt-2 text-xs text-slate-500 border-l-2 border-slate-300 pl-3">Organiser reply: {r.reply.body}</p>}
                {r.reports?.length > 0 && (
                  <ul className="mt-2 space-y-1" data-testid={`review-reports-${r.id}`}>
                    {r.reports.map((rp, i) => <li key={i} className="text-xs text-amber-700">“{rp.reason}” — {rp.by}</li>)}
                  </ul>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                {r.status !== "hidden"
                  ? <button onClick={() => moderate(r.id, "hide")} data-testid={`hide-review-${r.id}`} className="rounded-full border border-amber-300 text-amber-700 px-4 py-2 text-xs font-bold">Hide</button>
                  : <button onClick={() => moderate(r.id, "publish")} data-testid={`restore-review-${r.id}`} className="rounded-full bg-slate-900 text-white px-4 py-2 text-xs font-bold">Restore</button>}
                {r.flag_count > 0 && r.status !== "hidden" && (
                  <button onClick={() => moderate(r.id, "publish")} data-testid={`keep-review-${r.id}`} className="rounded-full border border-slate-200 px-4 py-2 text-xs font-bold">Keep visible</button>
                )}
                <button onClick={() => moderate(r.id, "delete")} data-testid={`delete-review-${r.id}`} className="rounded-full border border-red-200 text-red-600 px-4 py-2 text-xs font-bold">Delete</button>
                <Link to={`/events/${r.event_id}`} className="rounded-full border border-slate-200 px-4 py-2 text-xs font-bold">Event</Link>
              </div>
            </div>
          </div>
        )) : <Empty title="Nothing to moderate" sub={status === "flagged" ? "No review has been flagged by members." : "No reviews with this status."} />}
      </div>
    </div>
  );
}

function Crud({ path, title, fields, blank }) {
  const [items, setItems] = useState(null);
  const [f, setF] = useState(blank);
  const [editing, setEditing] = useState(null);
  const load = useCallback(() => api.get(`/admin/${path}`).then(({ data }) => setItems(data.items)).catch(() => setItems([])), [path]);
  useEffect(() => { load(); }, [load]);

  const save = async () => {
    try {
      const payload = { ...f };
      fields.forEach(([k, t]) => { if (t === "number") payload[k] = Number(payload[k] || 0); });
      if (editing) await api.put(`/admin/${path}/${editing}`, payload);
      else await api.post(`/admin/${path}`, payload);
      toast.success(editing ? "Updated" : "Created");
      setF(blank); setEditing(null); load();
    } catch (e) { toast.error(errMsg(e)); }
  };
  const del = async (id) => {
    try { await api.delete(`/admin/${path}/${id}`); toast.success("Deleted"); load(); }
    catch (e) { toast.error(errMsg(e)); }
  };
  if (!items) return <Spinner />;

  return (
    <div className="grid lg:grid-cols-3 gap-6" data-testid={`admin-crud-${path}`}>
      <div className="lg:col-span-2 space-y-3">
        <h2 className="text-xl font-bold">{title}</h2>
        {items.map((it) => (
          <div key={it.id} className="rounded-xl border border-slate-200 bg-white p-4 flex flex-wrap items-center gap-3" data-testid={`crud-item-${it.id}`}>
            <div className="flex-1 min-w-[180px]">
              <p className="font-semibold text-sm">{it.name || it.code}</p>
              <p className="text-xs text-slate-500 mt-0.5">
                {it.price !== undefined ? money(it.price) : `${it.discount_type} ${it.value}`}
                {it.duration_days ? ` · ${it.duration_days} days` : ""}{it.city ? ` · ${it.city}` : ""}
              </p>
            </div>
            <Badge tone={it.active ? "green" : "slate"}>{it.active ? "active" : "inactive"}</Badge>
            <button onClick={() => { setF({ ...blank, ...it }); setEditing(it.id); }} data-testid={`crud-edit-${it.id}`} className="rounded-full border border-slate-200 px-4 py-1.5 text-xs font-bold">Edit</button>
            <button onClick={() => del(it.id)} data-testid={`crud-delete-${it.id}`} className="rounded-full border border-red-200 text-red-600 px-4 py-1.5 text-xs font-bold">Delete</button>
          </div>
        ))}
        {!items.length && <Empty title="Nothing yet" sub="Create your first item using the form." />}
      </div>
      <div className="rounded-xl border border-slate-200 bg-white p-5 space-y-3 h-fit" data-testid={`crud-form-${path}`}>
        <p className="font-semibold">{editing ? "Edit" : "Create new"}</p>
        {fields.map(([k, t]) => (
          t === "bool" ? (
            <label key={k} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!f[k]} data-testid={`crud-${k}`} onChange={(e) => setF({ ...f, [k]: e.target.checked })} />{k.replace(/_/g, " ")}</label>
          ) : t === "list" ? (
            <label key={k} className="block"><span className="text-xs font-bold text-slate-600">{k.replace(/_/g, " ")} (one per line)</span>
              <textarea rows={4} data-testid={`crud-${k}`} value={(f[k] || []).join("\n")} onChange={(e) => setF({ ...f, [k]: e.target.value.split("\n").filter(Boolean) })}
                className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm" /></label>
          ) : t === "json" ? (
            <label key={k} className="block"><span className="text-xs font-bold text-slate-600">Price per currency (optional)</span>
              <textarea rows={3} data-testid={`crud-${k}`} value={JSON.stringify(f[k] || {})}
                onChange={(e) => { try { setF({ ...f, [k]: JSON.parse(e.target.value || "{}") }); } catch { /* keep typing */ } }}
                placeholder='{"USD": 19, "EUR": 18}'
                className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-xs font-mono" />
              <span className="text-[11px] text-slate-400">Leave empty to auto-convert from the INR price.</span></label>
          ) : t === "image" ? (
            <ImageUpload key={k} value={f[k]} onChange={(url) => setF({ ...f, [k]: url })} label="Product image" testid="crud-image" aspect="wide" />
          ) : (
            <Input key={k} label={k.replace(/_/g, " ")} type={t} data-testid={`crud-${k}`} value={f[k] ?? ""} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
          )
        ))}
        <div className="flex gap-2 pt-2">
          <button onClick={save} data-testid={`crud-save-${path}`} className="flex-1 rounded-full bg-slate-900 text-white py-2.5 text-sm font-bold">{editing ? "Update" : "Create"}</button>
          {editing && <button onClick={() => { setF(blank); setEditing(null); }} className="rounded-full border border-slate-200 px-4 py-2.5 text-sm font-bold">Cancel</button>}
        </div>
      </div>
    </div>
  );
}

function Content() {
  const [pages, setPages] = useState(null);
  const [sel, setSel] = useState(null);
  const load = () => api.get("/cms").then(({ data }) => setPages(data.items)).catch(() => setPages([]));
  useEffect(() => { load(); }, []);
  const save = async () => {
    try { await api.put(`/admin/cms/${sel.slug}`, sel); toast.success("Page updated"); load(); }
    catch (e) { toast.error(errMsg(e)); }
  };
  if (!pages) return <Spinner />;
  return (
    <div className="grid lg:grid-cols-3 gap-6" data-testid="admin-content">
      <div className="space-y-2">
        {pages.map((p) => (
          <button key={p.slug} onClick={() => setSel(p)} data-testid={`cms-select-${p.slug}`}
            className={`w-full text-left rounded-xl border p-4 ${sel?.slug === p.slug ? "border-slate-900 bg-slate-50" : "border-slate-200 bg-white"}`}>
            <p className="font-semibold text-sm">{p.title}</p><p className="text-xs text-slate-500">/{p.slug}</p>
          </button>
        ))}
      </div>
      <div className="lg:col-span-2">
        {sel ? (
          <div className="rounded-xl border border-slate-200 bg-white p-5 space-y-3">
            <Input label="Title" data-testid="cms-title" value={sel.title} onChange={(e) => setSel({ ...sel, title: e.target.value })} />
            <label className="block"><span className="text-xs font-bold text-slate-600">Content</span>
              <RichText value={sel.content} rows={12} testid="cms-content"
                onChange={(html) => setSel({ ...sel, content: html })} /></label>
            <Input label="SEO title" data-testid="cms-seo-title" value={sel.seo_title || ""} onChange={(e) => setSel({ ...sel, seo_title: e.target.value })} />
            <Input label="SEO description" data-testid="cms-seo-desc" value={sel.seo_description || ""} onChange={(e) => setSel({ ...sel, seo_description: e.target.value })} />
            <button onClick={save} data-testid="cms-save" className="rounded-full bg-slate-900 text-white px-6 py-2.5 text-sm font-bold">Save page</button>
          </div>
        ) : <Empty title="Pick a page" sub="Select a CMS page on the left to edit it." />}
      </div>
    </div>
  );
}

function Settings() {
  const [s, setS] = useState(null);
  useEffect(() => { api.get("/admin/settings").then(({ data }) => setS(data)).catch(() => setS({})); }, []);
  if (!s) return <Spinner />;
  const save = async () => {
    try { const { data } = await api.put("/admin/settings", s); setS(data); toast.success("Settings saved"); }
    catch (e) { toast.error(errMsg(e)); }
  };
  const keys = [["platform_name", "text"], ["contact_email", "text"], ["contact_number", "text"], ["currency", "text"],
    ["tax_percent", "number"], ["gateway", "text"], ["gateway_mode", "text"], ["min_age", "number"],
    ["seo_title", "text"], ["seo_description", "text"], ["moderation_auto_suspend_reports", "number"]];
  return (
    <div className="max-w-2xl rounded-xl border border-slate-200 bg-white p-6 space-y-3" data-testid="admin-settings">
      {keys.map(([k, t]) => (
        <Input key={k} label={k.replace(/_/g, " ")} type={t} data-testid={`setting-${k}`} value={s[k] ?? ""} onChange={(e) => setS({ ...s, [k]: t === "number" ? Number(e.target.value) : e.target.value })} />
      ))}
      <Input label="free messages per week (members with no plan)" type="number" data-testid="setting-free_messages_per_week"
        value={s.free_messages_per_week ?? 5} onChange={(e) => setS({ ...s, free_messages_per_week: Number(e.target.value) })} />
      <Input label="pass reminder — hours before the event (default 12)" type="number" data-testid="setting-pass_reminder_hours"
        value={s.pass_reminder_hours ?? 12} onChange={(e) => setS({ ...s, pass_reminder_hours: Number(e.target.value) })} />
      {[["require_email_verification", "Require email verification"], ["auto_approve_events", "Auto-approve partner events"]].map(([k, l]) => (
        <label key={k} className="flex items-center gap-2 text-sm"><input type="checkbox" data-testid={`setting-${k}`} checked={!!s[k]} onChange={(e) => setS({ ...s, [k]: e.target.checked })} />{l}</label>
      ))}
      <button onClick={save} data-testid="save-settings" className="rounded-full bg-slate-900 text-white px-6 py-2.5 text-sm font-bold">Save settings</button>
    </div>
  );
}

function Audit() {
  const [items, setItems] = useState(null);
  useEffect(() => { api.get("/admin/audit-logs").then(({ data }) => setItems(data.items)).catch(() => setItems([])); }, []);
  if (!items) return <Spinner />;
  return (
    <div className="rounded-xl border border-slate-200 bg-white divide-y divide-slate-100" data-testid="admin-audit">
      {items.length ? items.map((l) => (
        <div key={l.id} className="p-4 flex flex-wrap justify-between gap-2 text-sm">
          <div><p className="font-semibold">{l.action}</p><p className="text-xs text-slate-500">{l.entity} {l.entity_id}</p></div>
          <div className="text-right text-xs text-slate-500"><p>{l.actor_email}</p><p>{new Date(l.created_at).toLocaleString(undefined)}</p></div>
        </div>
      )) : <p className="p-6 text-sm text-slate-500">No admin actions logged yet.</p>}
    </div>
  );
}
