import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { ShieldCheck, UserPlus } from "lucide-react";
import { api, errMsg, fmtDate } from "@/lib/api";
import { Spinner, Badge } from "@/components/Shared";

const Field = ({ label, children }) => (
  <label className="block"><span className="text-xs font-bold text-slate-600">{label}</span>{children}</label>
);
const input = "mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm";

export const Team = () => {
  const [cat, setCat] = useState(null);
  const [items, setItems] = useState(null);
  const [f, setF] = useState({ full_name: "", email: "", scope: "admin", staff_role: "", extra_permissions: [] });
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(null);

  const load = useCallback(() => {
    api.get("/admin/team").then(({ data }) => setItems(data.items)).catch((e) => { toast.error(errMsg(e)); setItems([]); });
  }, []);
  useEffect(() => {
    api.get("/admin/permissions").then(({ data }) => setCat(data)).catch(() => setCat(null));
    load();
  }, [load]);

  if (!cat || !items) return <Spinner />;

  const roles = cat.roles.filter((r) => r.scope === f.scope);
  const groups = [...new Set(cat.groups.map((g) => g.group))];
  const presetOf = (key) => cat.roles.find((r) => r.key === key)?.permissions || [];

  const toggle = (key) => setF((p) => ({
    ...p,
    extra_permissions: p.extra_permissions.includes(key)
      ? p.extra_permissions.filter((k) => k !== key)
      : [...p.extra_permissions, key],
  }));

  const invite = async (e) => {
    e.preventDefault();
    if (!f.staff_role) return toast.error("Pick a role first.");
    setBusy(true);
    try {
      await api.post("/admin/team", f);
      toast.success("Invited — they'll get an email to set their password.");
      setF({ full_name: "", email: "", scope: "admin", staff_role: "", extra_permissions: [] });
      load();
    } catch (er) { toast.error(errMsg(er)); } finally { setBusy(false); }
  };

  const save = async (id, body) => {
    try { await api.patch(`/admin/team/${id}`, body); toast.success("Permissions updated."); setEditing(null); load(); }
    catch (e) { toast.error(errMsg(e)); }
  };

  return (
    <div className="space-y-8" data-testid="team-panel">
      <form onSubmit={invite} className="rounded-2xl border border-slate-200 bg-white p-6" data-testid="team-invite-form">
        <p className="flex items-center gap-2 font-bold"><UserPlus className="h-4 w-4" />Add a team member</p>
        <div className="mt-4 grid gap-4 md:grid-cols-4">
          <Field label="Full name">
            <input required value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })}
              className={input} data-testid="team-name" />
          </Field>
          <Field label="Work email">
            <input required type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })}
              className={input} data-testid="team-email" />
          </Field>
          <Field label="Access area">
            <select value={f.scope} onChange={(e) => setF({ ...f, scope: e.target.value, staff_role: "", extra_permissions: [] })}
              className={input} data-testid="team-scope">
              <option value="admin">Control centre (/admin)</option>
              <option value="manager">Vendor console (/console)</option>
            </select>
          </Field>
          <Field label="Role">
            <select value={f.staff_role} onChange={(e) => setF({ ...f, staff_role: e.target.value, extra_permissions: [] })}
              className={input} data-testid="team-role">
              <option value="">Choose a role…</option>
              {roles.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
            </select>
          </Field>
        </div>
        {f.staff_role && (
          <p className="mt-3 text-xs text-slate-500" data-testid="team-role-hint">
            {roles.find((r) => r.key === f.staff_role)?.description}
          </p>
        )}

        <div className="mt-5">
          <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Permissions</p>
          <p className="mt-1 text-xs text-slate-400">Ticks from the role are locked in; add anything extra you need.</p>
          <div className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {groups.map((g) => (
              <div key={g} className="rounded-xl border border-slate-200 p-4">
                <p className="text-xs font-bold">{g}</p>
                <ul className="mt-2 space-y-2">
                  {cat.groups.filter((p) => p.group === g).map((p) => {
                    const inPreset = presetOf(f.staff_role).includes(p.key);
                    const allowed = cat.my_permissions.includes(p.key);
                    return (
                      <li key={p.key}>
                        <label className={`flex items-start gap-2 text-xs ${allowed ? "" : "opacity-40"}`}>
                          <input type="checkbox" className="mt-0.5" data-testid={`team-perm-${p.key}`}
                            disabled={inPreset || !allowed}
                            checked={inPreset || f.extra_permissions.includes(p.key)}
                            onChange={() => toggle(p.key)} />
                          <span>
                            <span className="font-semibold">{p.key}</span>
                            <span className="block text-slate-400">{p.description}</span>
                          </span>
                        </label>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </div>
        </div>

        <button disabled={busy} data-testid="team-invite-btn"
          className="mt-5 rounded-full bg-slate-900 px-6 py-2.5 text-sm font-bold text-white disabled:opacity-50">
          {busy ? "Sending…" : "Send invite"}
        </button>
      </form>

      <div>
        <h2 className="mb-3 text-sm font-bold uppercase tracking-widest text-slate-500">Team</h2>
        <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white">
          <table className="w-full text-sm" data-testid="team-table">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>{["Name", "Area", "Role", "Permissions", "Status", ""].map((h) => <th key={h} className="px-4 py-3">{h}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {items.map((m) => (
                <tr key={m.id} data-testid={`team-row-${m.id}`} className="align-top">
                  <td className="px-4 py-3">
                    <span className="font-semibold">{m.full_name}</span>
                    <span className="block text-xs text-slate-500">{m.email}</span>
                    <span className="block text-[11px] text-slate-400">joined {fmtDate(m.created_at)}</span>
                  </td>
                  <td className="px-4 py-3 text-slate-500">{m.role === "admin" ? "Control centre" : "Vendor console"}</td>
                  <td className="px-4 py-3">
                    {editing?.id === m.id ? (
                      <div className="flex items-center gap-2">
                        <select defaultValue={m.staff_role || ""} data-testid={`team-edit-role-${m.id}`}
                          onChange={(e) => setEditing({ id: m.id, staff_role: e.target.value })}
                          className="rounded-xl border border-slate-200 px-2 py-1.5 text-xs">
                          <option value="">Choose…</option>
                          {cat.roles.filter((r) => r.scope === (m.role === "admin" ? "admin" : "manager"))
                            .map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
                        </select>
                        <button data-testid={`team-save-role-${m.id}`}
                          onClick={() => editing?.staff_role
                            ? save(m.id, { staff_role: editing.staff_role, extra_permissions: [] })
                            : toast.error("Pick a role first.")}
                          className="rounded-full bg-slate-900 px-3 py-1.5 text-xs font-bold text-white">Save</button>
                      </div>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 text-xs font-bold">
                        <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" />{m.role_label}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-xs text-slate-500" data-testid={`team-perms-${m.id}`}>
                      {m.permissions.length} permissions
                    </span>
                    <span className="mt-1 block max-w-[280px] text-[11px] text-slate-400 truncate">
                      {m.permissions.join(", ")}
                    </span>
                  </td>
                  <td className="px-4 py-3"><Badge tone={m.status === "active" ? "green" : "red"}>{m.status}</Badge></td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-2">
                      <button onClick={() => setEditing(editing?.id === m.id ? null : { id: m.id, staff_role: m.staff_role || "" })}
                        data-testid={`team-edit-${m.id}`}
                        className="rounded-full border border-slate-200 px-3.5 py-1.5 text-xs font-bold">
                        {editing?.id === m.id ? "Cancel" : "Change role"}
                      </button>
                      <button onClick={() => save(m.id, { status: m.status === "active" ? "suspended" : "active" })}
                        data-testid={`team-status-${m.id}`}
                        className="rounded-full border border-slate-200 px-3.5 py-1.5 text-xs font-bold text-rose-600">
                        {m.status === "active" ? "Suspend" : "Reactivate"}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
