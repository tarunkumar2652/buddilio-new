import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errMsg, money, fmtDate } from "@/lib/api";
import { Spinner, Empty, Badge } from "@/components/Shared";

const SHEET = "fixed inset-0 z-[80] flex items-end sm:items-center justify-center bg-slate-900/50 p-0 sm:p-6";
const CARD = "w-full sm:max-w-md rounded-t-3xl sm:rounded-3xl bg-white p-6 shadow-2xl";
const IN = "mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm";
const PILL = "rounded-full px-4 py-2.5 text-xs font-bold";

/** Admin refund sheet — shows the policy ceiling and requires a reason to go beyond it. */
export const RefundDialog = ({ order, onClose, onDone }) => {
  const paid = Number(order.charge_total || order.total || 0);
  const already = Number(order.refunded_amount || 0);
  const quote = order.cancellation || {};
  const isMembership = order.kind === "membership";
  const ceiling = isMembership ? 0
    : quote.refundable != null ? Number(quote.refundable) : paid;
  const allowed = Math.max(0, Number((ceiling - already).toFixed(2)));
  const [amount, setAmount] = useState(allowed.toFixed(2));
  const [reason, setReason] = useState("");
  const [override, setOverride] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/admin/orders/${order.id}/refund`,
        { amount: Number(amount), reason, override_policy: override });
      toast.success(data.refund_status === "partial"
        ? `Partial refund done — ${money(data.refunded_amount, order.currency)} refunded so far.`
        : "Full refund processed.");
      onDone();
      onClose();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  return (
    <div className={SHEET} data-testid="refund-dialog" onClick={onClose}>
      <div className={CARD} onClick={(e) => e.stopPropagation()}>
        <p className="text-xs font-bold uppercase tracking-widest text-brand-magenta">Refund</p>
        <h3 className="mt-1 text-lg font-black text-slate-900">#{order.order_no} · {order.item_name}</h3>
        <dl className="mt-4 space-y-2 rounded-2xl bg-slate-50 p-4 text-sm">
          {[["Paid", money(paid, order.currency)],
            ["Already refunded", money(already, order.currency)],
            ["Deduction", quote.deduction_percent != null ? `${quote.deduction_percent}%` : "—"],
            ["Policy allows now", isMembership ? "Non-refundable" : money(allowed, order.currency)]].map(([k, v]) => (
              <div key={k} className="flex justify-between gap-3">
                <dt className="text-slate-500">{k}</dt><dd className="font-bold text-slate-900">{v}</dd>
              </div>
            ))}
        </dl>
        {isMembership && (
          <p className="mt-3 text-xs font-semibold text-amber-700" data-testid="refund-membership-note">
            Membership fees are non-refundable. Refunding needs a policy override with a reason.
          </p>
        )}
        <label className="mt-4 block"><span className="text-xs font-bold text-slate-600">Amount</span>
          <input value={amount} onChange={(e) => setAmount(e.target.value)} className={IN}
            data-testid="refund-amount" inputMode="decimal" /></label>
        <label className="mt-3 block"><span className="text-xs font-bold text-slate-600">Reason (audited)</span>
          <input value={reason} onChange={(e) => setReason(e.target.value)} className={IN}
            data-testid="refund-reason" placeholder="Why is this being refunded?" /></label>
        <label className="mt-3 flex items-center gap-2 text-xs font-semibold text-slate-600">
          <input type="checkbox" checked={override} onChange={(e) => setOverride(e.target.checked)}
            data-testid="refund-override" />
          Override the cancellation policy (goodwill exception)
        </label>
        <div className="mt-5 flex gap-2">
          <button onClick={submit} disabled={busy} data-testid="refund-confirm"
            className={`${PILL} flex-1 bg-slate-900 text-white`}>{busy ? "Refunding…" : "Refund"}</button>
          <button onClick={onClose} data-testid="refund-cancel"
            className={`${PILL} border border-slate-200`}>Close</button>
        </div>
      </div>
    </div>
  );
};

const SettleDialog = ({ order, onClose, onDone }) => {
  const c = order.cancellation || {};
  const [amount, setAmount] = useState(Number(c.refundable || 0).toFixed(2));
  const [asCredit, setAsCredit] = useState(c.prefer === "credit");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      await api.post(`/admin/orders/${order.id}/settle-cancellation`,
        { amount: Number(amount), as_credit: asCredit, note });
      toast.success(asCredit ? "Settled as Buddilio credit." : "Settled — refund sent to the gateway.");
      onDone();
      onClose();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  return (
    <div className={SHEET} data-testid="settle-dialog" onClick={onClose}>
      <div className={CARD} onClick={(e) => e.stopPropagation()}>
        <p className="text-xs font-bold uppercase tracking-widest text-brand-magenta">Settle cancellation</p>
        <h3 className="mt-1 text-lg font-black text-slate-900">#{order.order_no} · {order.item_name}</h3>
        <dl className="mt-4 space-y-2 rounded-2xl bg-slate-50 p-4 text-sm">
          {[["Member", order.user_name || "—"],
            ["Paid", money(order.charge_total || order.total, order.currency)],
            ["Deduction", `${c.deduction_percent || 0}%`],
            ["Quoted refundable", money(c.refundable || 0, order.currency)],
            ["Member prefers", c.prefer === "credit" ? "Credit (+10%)" : "Refund to card"],
            ["Currency", (order.currency || "USD").toUpperCase()],
            ["Member's reason", c.reason || "—"]].map(([k, v]) => (
              <div key={k} className="flex justify-between gap-3">
                <dt className="text-slate-500">{k}</dt><dd className="font-bold text-slate-900 text-right">{v}</dd>
              </div>
            ))}
        </dl>
        <label className="mt-4 block"><span className="text-xs font-bold text-slate-600">Amount to settle</span>
          <input value={amount} onChange={(e) => setAmount(e.target.value)} className={IN}
            data-testid="settle-amount" inputMode="decimal" /></label>
        <div className="mt-3 flex gap-2">
          {[[false, "Refund to payment method"], [true, "Buddilio credit (+10%)"]].map(([v, label]) => (
            <button key={String(v)} onClick={() => setAsCredit(v)} data-testid={`settle-mode-${v ? "credit" : "refund"}`}
              className={`${PILL} flex-1 border ${asCredit === v ? "bg-slate-900 text-white border-slate-900" : "border-slate-200"}`}>
              {label}
            </button>
          ))}
        </div>
        <label className="mt-3 block"><span className="text-xs font-bold text-slate-600">Note (audited)</span>
          <input value={note} onChange={(e) => setNote(e.target.value)} className={IN}
            data-testid="settle-note" placeholder="Decision note" /></label>
        <div className="mt-5 flex gap-2">
          <button onClick={submit} disabled={busy} data-testid="settle-confirm"
            className={`${PILL} flex-1 bg-slate-900 text-white`}>{busy ? "Settling…" : "Settle"}</button>
          <button onClick={onClose} data-testid="settle-cancel"
            className={`${PILL} border border-slate-200`}>Close</button>
        </div>
      </div>
    </div>
  );
};

export const Cancellations = () => {
  const [state, setState] = useState(null);
  const [open, setOpen] = useState(null);
  const load = useCallback(() => {
    api.get("/admin/cancellations").then(({ data }) => setState(data))
      .catch(() => setState({ items: [], tiers: [] }));
  }, []);
  useEffect(() => { load(); }, [load]);

  if (!state) return <Spinner />;
  return (
    <div data-testid="admin-cancellations">
      <h2 className="text-xl font-black text-slate-900">Cancellations awaiting settlement</h2>
      <p className="mt-1 text-sm text-slate-500">
        Membership fees are non-refundable. Bookings carry a minimum 30% deduction, rising to 50% within
        7 days and 100% within 48 hours of the booking.
      </p>
      <div className="mt-5 space-y-3">
        {state.items.length ? state.items.map((o) => (
          <div key={o.id} data-testid={`cancellation-${o.id}`}
            className="rounded-2xl border border-slate-200 bg-white p-4 flex flex-wrap items-center gap-4">
            <div className="min-w-[220px] flex-1">
              <p className="text-sm font-bold text-slate-900">#{o.order_no} · {o.item_name}</p>
              <p className="mt-0.5 text-xs text-slate-500">
                {o.user_name} · {o.kind} · requested {fmtDate(o.cancellation?.requested_at)}
              </p>
              <p className="mt-1 text-xs font-semibold text-amber-700">
                {o.cancellation?.deduction_percent}% deducted · {money(o.cancellation?.refundable || 0, o.currency)} refundable
                {o.kind === "membership" ? " · membership fee is non-refundable" : ""}
              </p>
            </div>
            <Badge tone="amber">{o.cancellation?.prefer === "credit" ? "wants credit" : "wants refund"}</Badge>
            <button onClick={() => setOpen(o)} data-testid={`settle-${o.id}`}
              className={`${PILL} bg-slate-900 text-white`}>Settle</button>
          </div>
        )) : <Empty title="Nothing pending" sub="No cancellations are waiting on a money decision." />}
      </div>
      {open && <SettleDialog order={open} onClose={() => setOpen(null)} onDone={load} />}
    </div>
  );
};

export default Cancellations;
