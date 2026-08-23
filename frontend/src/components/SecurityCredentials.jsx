import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { KeyRound, LogOut, ShieldAlert, ShieldCheck, Lock, Unlock, Info } from "lucide-react";
import { api, errMsg, fmtDate } from "@/lib/api";
import { Spinner, Badge } from "@/components/Shared";

const PILL = "rounded-full px-4 py-2 text-xs font-bold";
const IN = "mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm";
const CARD = "rounded-2xl border border-slate-200 bg-white p-5";

const ROLE_LABELS = {
  super_admin: "Super admin", operations: "Operations", finance: "Finance", support: "Support",
  moderator: "Moderator", viewer: "Viewer", vendor_manager: "Vendor manager",
  vendor_viewer: "Console viewer", admin: "Admin", manager: "Manager", partner: "Organiser",
};

const suggest = () => {
  const pool = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789";
  return Array.from({ length: 16 }, () => pool[Math.floor(Math.random() * pool.length)]).join("");
};

const MyPassword = () => {
  const [f, setF] = useState({ current_password: "", new_password: "", confirm: "" });
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (f.new_password !== f.confirm) return toast.error("The two new passwords don't match.");
    setBusy(true);
    try {
      const { data } = await api.post("/me/password", f);
      localStorage.setItem("token", data.access_token);
      toast.success(data.message);
      setF({ current_password: "", new_password: "", confirm: "" });
    } catch (e2) { toast.error(errMsg(e2)); } finally { setBusy(false); }
  };

  return (
    <form onSubmit={submit} className={CARD} data-testid="my-password-card">
      <p className="flex items-center gap-2 text-sm font-black text-slate-900">
        <KeyRound className="h-4 w-4" />My password
      </p>
      <p className="mt-1 text-xs text-slate-500">
        Changing it signs you out of every other device — including anyone who still has your old one.
      </p>
      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        {[["current_password", "Current password"], ["new_password", "New password"], ["confirm", "Repeat new password"]].map(([k, label]) => (
          <label key={k} className="block"><span className="text-xs font-bold text-slate-600">{label}</span>
            <input type="password" autoComplete="new-password" value={f[k]} data-testid={`pwd-${k}`}
              onChange={(e) => setF({ ...f, [k]: e.target.value })} className={IN} /></label>
        ))}
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button disabled={busy} data-testid="pwd-submit" className={`${PILL} bg-slate-900 text-white`}>
          {busy ? "Saving…" : "Change my password"}
        </button>
        <button type="button" data-testid="pwd-suggest"
          onClick={() => { const s = suggest(); setF({ ...f, new_password: s, confirm: s }); toast.success(`Suggested: ${s}`); }}
          className={`${PILL} border border-slate-200`}>Suggest a strong one</button>
        <span className="text-xs text-slate-400">10+ characters with upper, lower and a number.</span>
      </div>
    </form>
  );
};

const Accounts = () => {
  const [d, setD] = useState(null);
  const [pending, setPending] = useState(null);   // { user, password } shown once, on success
  const [locking, setLocking] = useState(null);
  const load = useCallback(() => {
    api.get("/admin/security/accounts").then(({ data }) => setD(data)).catch(() => setD({ items: [] }));
  }, []);
  useEffect(() => { load(); }, [load]);

  const act = async (path, ok, body) => {
    try {
      const { data } = await api.post(path, body || {});
      toast.success(data.message || ok);
      load();
    } catch (e) { toast.error(errMsg(e)); }
  };

  const reset = (u) => setPending({ user: u, password: suggest(), saved: false, busy: false });

  const confirmReset = async () => {
    setPending((s) => ({ ...s, busy: true }));
    try {
      await api.post(`/admin/security/accounts/${pending.user.id}/password`, { value: pending.password });
      setPending((s) => ({ ...s, saved: true, busy: false }));
      load();
    } catch (e) {
      toast.error(errMsg(e));
      setPending((s) => ({ ...s, busy: false }));
    }
  };

  if (!d) return <Spinner />;
  return (
    <div className={CARD} data-testid="security-accounts">
      <p className="flex items-center gap-2 text-sm font-black text-slate-900">
        <ShieldCheck className="h-4 w-4" />Team and partner logins
      </p>
      <p className="mt-1 text-xs text-slate-500">
        Reset a password, sign someone out, or revoke access completely — useful the day a freelancer finishes.
      </p>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left"><tr>
            {["Person", "Role", "Status", "Password changed", ""].map((h) => (
              <th key={h} className="px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">{h}</th>))}
          </tr></thead>
          <tbody className="divide-y divide-slate-100">
            {d.items.map((u) => (
              <tr key={u.id} data-testid={`account-${u.id}`}>
                <td className="px-3 py-3">
                  <p className="font-semibold text-slate-900">{u.full_name || "—"}</p>
                  <p className="text-xs text-slate-500">{u.email}</p>
                </td>
                <td className="px-3 py-3 text-xs">{ROLE_LABELS[u.staff_role] || ROLE_LABELS[u.role] || u.role}</td>
                <td className="px-3 py-3">
                  <Badge tone={u.status === "active" || !u.status ? "green" : "red"}>{u.status || "active"}</Badge>
                </td>
                <td className="px-3 py-3 text-xs text-slate-500">{u.password_changed_at ? fmtDate(u.password_changed_at) : "never"}</td>
                <td className="px-3 py-3">
                  {u.id === d.me ? <span className="text-xs text-slate-400">that's you</span> : (
                    <div className="flex flex-wrap justify-end gap-2">
                      <button onClick={() => reset(u)} data-testid={`reset-${u.id}`} className={`${PILL} border border-slate-200`}>
                        <KeyRound className="mr-1 inline h-3.5 w-3.5" />New password
                      </button>
                      <button onClick={() => act(`/admin/security/accounts/${u.id}/revoke`, "Signed out.")}
                        data-testid={`revoke-${u.id}`} className={`${PILL} border border-slate-200`}>
                        <LogOut className="mr-1 inline h-3.5 w-3.5" />Sign out
                      </button>
                      {u.status === "suspended" ? (
                        <button onClick={() => act(`/admin/security/accounts/${u.id}/access`, "Restored.", { active: true })}
                          data-testid={`restore-${u.id}`} className={`${PILL} border border-slate-200`}>
                          <Unlock className="mr-1 inline h-3.5 w-3.5" />Restore
                        </button>
                      ) : (
                        <button onClick={() => setLocking(u)}
                          data-testid={`lock-${u.id}`} className={`${PILL} bg-red-600 text-white`}>
                          <Lock className="mr-1 inline h-3.5 w-3.5" />Revoke access
                        </button>
                      )}
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {pending && (
        <div className="fixed inset-0 z-[90] flex items-center justify-center bg-slate-900/50 p-4"
          data-testid="reset-dialog" onClick={() => !pending.busy && setPending(null)}>
          <div className="w-full max-w-md rounded-3xl bg-white p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            {pending.saved ? (
              <>
                <p className="text-sm font-black text-slate-900">New password for {pending.user.email}</p>
                <p className="mt-1 text-xs text-slate-500">
                  Shown once. Copy it now and send it to them another way — they have been signed out everywhere.
                </p>
                <p className="mt-4 select-all rounded-2xl bg-slate-900 px-4 py-4 text-center font-mono text-lg text-white"
                  data-testid="reset-password-value">{pending.password}</p>
                <div className="mt-5 flex gap-2">
                  <button onClick={() => { navigator.clipboard.writeText(pending.password); toast.success("Copied."); }}
                    data-testid="reset-copy" className={`${PILL} flex-1 bg-slate-900 text-white`}>Copy password</button>
                  <button onClick={() => setPending(null)} data-testid="reset-done"
                    className={`${PILL} border border-slate-200`}>Done</button>
                </div>
              </>
            ) : (
              <>
                <p className="text-sm font-black text-slate-900">Reset the password for {pending.user.email}?</p>
                <p className="mt-1 text-xs text-slate-500">
                  We'll generate a strong password and show it once. They will be signed out of every device.
                </p>
                <div className="mt-5 flex gap-2">
                  <button onClick={confirmReset} disabled={pending.busy} data-testid="reset-confirm"
                    className={`${PILL} flex-1 bg-slate-900 text-white`}>{pending.busy ? "Resetting…" : "Reset password"}</button>
                  <button onClick={() => setPending(null)} data-testid="reset-cancel"
                    className={`${PILL} border border-slate-200`}>Cancel</button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {locking && (
        <div className="fixed inset-0 z-[90] flex items-center justify-center bg-slate-900/50 p-4"
          data-testid="revoke-dialog" onClick={() => setLocking(null)}>
          <div className="w-full max-w-md rounded-3xl bg-white p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <p className="text-sm font-black text-slate-900">Revoke all access for {locking.email}?</p>
            <p className="mt-1 text-xs text-slate-500">
              They are signed out immediately and cannot log back in until you restore them. Their work stays intact.
            </p>
            <div className="mt-5 flex gap-2">
              <button data-testid="revoke-confirm" className={`${PILL} flex-1 bg-red-600 text-white`}
                onClick={() => { act(`/admin/security/accounts/${locking.id}/access`, "Revoked.", { active: false }); setLocking(null); }}>
                Revoke access
              </button>
              <button onClick={() => setLocking(null)} data-testid="revoke-cancel"
                className={`${PILL} border border-slate-200`}>Keep access</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

const CredentialRow = ({ c, onSaved }) => {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);

  const save = async (e) => {
    e.preventDefault();
    if (!value.trim()) return;
    if (c.name === "JWT_SECRET" && !window.confirm("Changing the login secret signs out every user, including you. Continue?")) return;
    setBusy(true);
    try {
      const { data } = await api.put(`/admin/credentials/${c.name}`, { value: value.trim() });
      toast.success(data.message);
      setValue("");
      onSaved();
    } catch (e2) { toast.error(errMsg(e2)); } finally { setBusy(false); }
  };

  const revert = async () => {
    try {
      const { data } = await api.delete(`/admin/credentials/${c.name}`);
      toast.success(data.message);
      onSaved();
    } catch (e) { toast.error(errMsg(e)); }
  };

  return (
    <form onSubmit={save} className="grid gap-3 border-t border-slate-100 py-4 sm:grid-cols-[1.1fr_1fr_auto] sm:items-end"
      data-testid={`credential-${c.name}`}>
      <div>
        <p className="text-sm font-semibold text-slate-900">{c.label}</p>
        <p className="mt-0.5 text-xs text-slate-500">{c.hint}</p>
        <p className="mt-1 flex flex-wrap items-center gap-2 text-xs">
          <Badge tone={c.configured ? "green" : "amber"}>{c.configured ? c.source : "not set"}</Badge>
          {c.configured && <span className="font-mono text-slate-400">{c.preview}</span>}
          {c.updated_at && <span className="text-slate-400">changed {fmtDate(c.updated_at)}</span>}
        </p>
      </div>
      <label className="block">
        <input type={c.sensitive ? "password" : "text"} autoComplete="new-password" value={value}
          onChange={(e) => setValue(e.target.value)} data-testid={`credential-input-${c.name}`}
          placeholder={c.configured ? "Enter a new value to replace it" : "Not set yet"} className={IN} />
      </label>
      <div className="flex gap-2">
        <button disabled={busy || !value.trim()} data-testid={`credential-save-${c.name}`}
          className={`${PILL} bg-slate-900 text-white disabled:opacity-40`}>{busy ? "Saving…" : "Save"}</button>
        {c.source === "dashboard" && (
          <button type="button" onClick={revert} data-testid={`credential-revert-${c.name}`}
            className={`${PILL} border border-slate-200`}>Revert</button>
        )}
      </div>
    </form>
  );
};

/** Super Admin control room for passwords and service keys — write-only, fully audited. */
export const SecurityCredentials = () => {
  const [d, setD] = useState(null);
  const [testing, setTesting] = useState("");
  const load = useCallback(() => {
    api.get("/admin/credentials").then(({ data }) => setD(data)).catch((e) => { setD(null); toast.error(errMsg(e)); });
  }, []);
  useEffect(() => { load(); }, [load]);

  const test = async (service) => {
    setTesting(service);
    try {
      const { data } = await api.post(`/admin/credentials/test/${service}`, {});
      data.ok ? toast.success(data.message) : toast.error(data.message);
    } catch (e) { toast.error(errMsg(e)); } finally { setTesting(""); }
  };

  if (!d) return <Spinner />;
  const groups = [...new Set(d.items.map((c) => c.group))];
  return (
    <div className="space-y-6" data-testid="security-panel">
      <div>
        <h2 className="text-xl font-black text-slate-900">Security &amp; credentials</h2>
        <p className="mt-1 text-sm text-slate-500">
          Everything a Super admin can rotate without touching the server. Keys are stored encrypted and
          never shown back — you can replace one, but nobody can read it here again.
        </p>
      </div>

      <MyPassword />
      <Accounts />

      <div className={CARD} data-testid="credentials-card">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="flex items-center gap-2 text-sm font-black text-slate-900">
              <ShieldAlert className="h-4 w-4" />Service keys
            </p>
            <p className="mt-1 text-xs text-slate-500">
              A saved key takes effect immediately and overrides whatever is in the server file.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {[["paypal", "Test PayPal"], ["email", "Test email"], ["ai", "Test AI"]].map(([s, label]) => (
              <button key={s} onClick={() => test(s)} disabled={testing === s} data-testid={`test-${s}`}
                className={`${PILL} border border-slate-200`}>{testing === s ? "Testing…" : label}</button>
            ))}
          </div>
        </div>
        {groups.map((g) => (
          <div key={g} className="mt-5">
            <p className="text-[11px] font-bold uppercase tracking-widest text-brand-magenta">{g}</p>
            {d.items.filter((c) => c.group === g).map((c) => (
              <CredentialRow key={c.name} c={c} onSaved={load} />
            ))}
          </div>
        ))}
      </div>

      <div className={CARD} data-testid="handover-card">
        <p className="flex items-center gap-2 text-sm font-black text-slate-900">
          <Info className="h-4 w-4" />Change these outside Buddilio
        </p>
        <p className="mt-1 text-xs text-slate-500">
          These logins live with other companies, so no app can change them for you. Do these yourself
          the day your freelancer finishes.
        </p>
        <ul className="mt-3 space-y-2 text-sm">
          {d.not_managed_here.map((x) => (
            <li key={x.what} className="flex flex-wrap gap-x-2 rounded-xl bg-slate-50 px-4 py-3">
              <span className="font-semibold text-slate-900">{x.what}</span>
              <span className="text-slate-500">— {x.where}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className={CARD} data-testid="credential-history">
        <p className="text-sm font-black text-slate-900">Recent security activity</p>
        <ul className="mt-3 space-y-2 text-xs text-slate-500">
          {d.history.length ? d.history.map((h) => (
            <li key={h.id} className="flex flex-wrap gap-2">
              <span className="font-mono">{fmtDate(h.created_at)}</span>
              <span className="font-semibold text-slate-900">{h.action}</span>
              <span>{h.meta?.name || h.meta?.email || h.target_id}</span>
              <span>by {h.actor_email || h.actor_name || "—"}</span>
            </li>
          )) : <li>Nothing yet.</li>}
        </ul>
      </div>
    </div>
  );
};

export default SecurityCredentials;
