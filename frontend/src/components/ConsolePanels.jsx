import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Link2, Copy, Trash2, Send, Loader2 } from "lucide-react";
import { api, errMsg, fmtDate } from "@/lib/api";
import { Spinner, Badge } from "@/components/Shared";

const Field = ({ label, ...p }) => (
  <label className="block">
    <span className="text-xs font-bold text-slate-300">{label}</span>
    <input {...p} className="mt-1.5 w-full rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500 focus:border-brand-pink" />
  </label>
);

const tone = (s) => (s === "accepted" ? "green" : s === "revoked" ? "red" : "amber");

export const VendorInvites = ({ locked, cities }) => {
  const [items, setItems] = useState(null);
  const [f, setF] = useState({ email: "", org_name: "", city: "", note: "" });
  const [busy, setBusy] = useState(false);

  const load = () => api.get("/console/invites").then(({ data }) => setItems(data.items)).catch(() => setItems([]));
  useEffect(() => { load(); }, []);

  const create = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post("/console/invites", f);
      await navigator.clipboard?.writeText(data.link).catch(() => {});
      toast.success(f.email ? "Invite emailed — link copied too." : "Invite link created and copied.");
      setF({ email: "", org_name: "", city: "", note: "" });
      load();
    } catch (er) { toast.error(errMsg(er)); } finally { setBusy(false); }
  };

  const revoke = async (id) => {
    try { await api.delete(`/console/invites/${id}`); toast.success("Invite revoked"); load(); }
    catch (er) { toast.error(errMsg(er)); }
  };

  const copy = async (link) => {
    try { await navigator.clipboard.writeText(link); toast.success("Link copied"); }
    catch { toast.error("Copy failed — select the link manually."); }
  };

  return (
    <div className="grid lg:grid-cols-[1.4fr_1fr] gap-6 items-start" data-testid="invites-panel">
      <div className="rounded-3xl border border-white/10 bg-white/[0.03] overflow-hidden">
        <p className="border-b border-white/10 p-4 text-sm font-bold text-white">Invites</p>
        {!items ? <Spinner label="Loading invites" /> : items.length === 0 ? (
          <p className="p-8 text-center text-sm text-slate-400" data-testid="invites-empty">
            No invites yet. Send one and the vendor fills in their own details and documents.
          </p>
        ) : (
          <ul className="divide-y divide-white/5" data-testid="invites-list">
            {items.map((i) => (
              <li key={i.id} className="p-4" data-testid={`invite-row-${i.id}`}>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-semibold text-white">{i.org_name || i.email || "Open invite"}</span>
                  <Badge tone={tone(i.status)}>{i.status}</Badge>
                  <span className="text-[11px] text-slate-400">
                    {i.city ? `${i.city} · ` : ""}sent {fmtDate(i.created_at)} · expires {fmtDate(i.expires_at)}
                  </span>
                </div>
                {i.email && <p className="mt-0.5 text-[11px] text-slate-400">{i.email}</p>}
                <div className="mt-2.5 flex flex-wrap items-center gap-2">
                  {i.link && (
                    <button onClick={() => copy(i.link)} data-testid={`invite-copy-${i.id}`}
                      className="inline-flex items-center gap-1.5 rounded-full border border-white/15 px-3 py-1.5 text-[11px] font-bold text-white hover:bg-white/10">
                      <Copy className="h-3 w-3" />Copy link
                    </button>
                  )}
                  {i.status === "pending" && !locked && (
                    <button onClick={() => revoke(i.id)} data-testid={`invite-revoke-${i.id}`}
                      className="inline-flex items-center gap-1.5 rounded-full border border-white/15 px-3 py-1.5 text-[11px] font-bold text-rose-300 hover:bg-white/10">
                      <Trash2 className="h-3 w-3" />Revoke
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {locked ? (
        <div className="rounded-3xl border border-white/10 bg-white/[0.03] p-6" data-testid="invite-form-locked">
          <p className="text-sm font-bold text-white">Invites locked</p>
          <p className="mt-1 text-xs text-slate-400">Available once your console account is approved.</p>
        </div>
      ) : (
        <form onSubmit={create} className="rounded-3xl border border-white/10 bg-white/[0.03] p-6 space-y-4"
          data-testid="invite-form">
          <h2 className="flex items-center gap-2 text-lg font-bold text-white"><Link2 className="h-4 w-4 text-brand-pink" />Invite a vendor</h2>
          <p className="-mt-2 text-xs text-slate-400">
            They set their own password, profile and documents. Link lasts 14 days.
          </p>
          <Field label="Their email" type="email" required data-testid="invite-email" value={f.email}
            onChange={(e) => setF({ ...f, email: e.target.value })} />
          <Field label="Organisation (optional)" data-testid="invite-org" value={f.org_name}
            onChange={(e) => setF({ ...f, org_name: e.target.value })} />
          <label className="block">
            <span className="text-xs font-bold text-slate-300">City (optional)</span>
            <select data-testid="invite-city" value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })}
              className="mt-1.5 w-full rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm text-white">
              <option value="">Let them choose</option>
              {cities.map((c) => <option key={c} value={c} className="text-slate-900">{c}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="text-xs font-bold text-slate-300">Personal note (optional)</span>
            <textarea rows={3} data-testid="invite-note" value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })}
              placeholder="Loved your rooftop series — would you host it with us?"
              className="mt-1.5 w-full rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm text-white placeholder:text-slate-500" />
          </label>
          <button disabled={busy} data-testid="invite-create"
            className="inline-flex items-center gap-2 rounded-full brand-gradient px-5 py-3 text-sm font-bold text-white disabled:opacity-60">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            {busy ? "Sending…" : "Send invite"}
          </button>
        </form>
      )}
    </div>
  );
};

export const ConsolePayouts = () => {
  const [data, setData] = useState(null);

  useEffect(() => {
    api.get("/console/payouts").then(({ data }) => setData(data)).catch(() => setData({ items: [], totals: {} }));
  }, []);

  if (!data) return <Spinner label="Loading payouts" />;
  const t = data.totals || {};
  const cash = (n) => `${t.currency || ""} ${Number(n || 0).toLocaleString()}`;

  return (
    <div data-testid="console-payouts">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[["Owed to vendors", t.pending, "payout-total-pending"], ["Already paid", t.paid, "payout-total-paid"],
          ["Gross sales", t.gross, "payout-total-gross"], ["Platform fees", t.fees, "payout-total-fees"]].map(([l, v, tid]) => (
          <div key={l} className="rounded-2xl border border-white/10 bg-white/[0.03] p-5" data-testid={tid}>
            <p className="text-2xl font-bold text-white">{cash(v)}</p>
            <p className="text-[11px] font-bold uppercase tracking-widest text-slate-400">{l}</p>
          </div>
        ))}
      </div>

      {data.items.length === 0 ? (
        <p className="mt-6 rounded-2xl border border-white/10 bg-white/[0.03] p-8 text-center text-sm text-slate-400"
          data-testid="payouts-empty">
          Nothing to settle yet. A payout appears 48 hours after each event finishes.
        </p>
      ) : (
        <div className="mt-6 overflow-x-auto rounded-2xl border border-white/10 bg-white/[0.03]">
          <table className="w-full text-sm" data-testid="payouts-table">
            <thead className="text-left text-[11px] uppercase tracking-widest text-slate-400">
              <tr>{["Vendor", "Event", "Orders", "Gross", "Fee", "Net", "Status"].map((h) => (
                <th key={h} className="whitespace-nowrap px-4 py-3">{h}</th>))}
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {data.items.map((p) => (
                <tr key={p.id} data-testid={`payout-row-${p.id}`} className="text-slate-300">
                  <td className="px-4 py-3 font-semibold text-white">{p.vendor}</td>
                  <td className="px-4 py-3">
                    <span className="block">{p.event_title}</span>
                    <span className="text-[11px] text-slate-500">
                      {p.status === "paid" ? `paid ${fmtDate(p.paid_at)}` : `due since ${fmtDate(p.created_at)}`}
                    </span>
                  </td>
                  <td className="px-4 py-3">{p.orders}</td>
                  <td className="px-4 py-3">{p.currency} {p.gross.toLocaleString()}</td>
                  <td className="px-4 py-3">{p.fee_percent}%</td>
                  <td className="px-4 py-3 font-bold text-white">{p.currency} {p.net.toLocaleString()}</td>
                  <td className="px-4 py-3"><Badge tone={p.status === "paid" ? "green" : "amber"}>{p.status}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-3 text-[11px] text-slate-400">
        Buddilio settles payouts to vendors — admins mark them paid once the transfer clears.
      </p>
    </div>
  );
};
