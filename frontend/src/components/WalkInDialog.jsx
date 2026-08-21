import { useState } from "react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";

const PILL = "rounded-full px-4 py-2.5 text-xs font-bold";
const IN = "mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm";
const METHODS = [["cash", "Cash"], ["upi", "UPI"], ["card", "Card machine"], ["paypal_link", "PayPal link"]];

/** Door sale: take the money in person, or send the guest a PayPal link on the spot. */
export const WalkInDialog = ({ eventId, onClose, onDone }) => {
  const [f, setF] = useState({ guest_name: "", guest_phone: "", guest_email: "", quantity: 1, amount: "" });
  const [method, setMethod] = useState("cash");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);

  const submit = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/partner/events/${eventId}/walk-in`, {
        ...f, quantity: Number(f.quantity) || 1, amount: Number(f.amount) || 0, method,
        check_in_now: true });
      setDone(data);
      toast.success(data.message);
      onDone();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-[80] flex items-end sm:items-center justify-center bg-slate-900/50 p-0 sm:p-6"
      data-testid="walkin-dialog" onClick={onClose}>
      <div className="w-full sm:max-w-md rounded-t-3xl sm:rounded-3xl bg-white p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}>
        <p className="text-xs font-bold uppercase tracking-widest text-brand-magenta">Walk-in</p>
        <h3 className="mt-1 text-lg font-black text-slate-900">Sell a pass at the door</h3>
        {done ? (
          <div data-testid="walkin-done">
            <p className="mt-4 rounded-2xl bg-emerald-50 p-4 text-sm text-emerald-800">{done.message}</p>
            {done.pass && (
              <p className="mt-3 text-sm">
                Pass code <span className="font-mono font-bold" data-testid="walkin-pass-code">{done.pass.code}</span>
                {" "}· order #{done.order_no}
              </p>
            )}
            <button onClick={onClose} data-testid="walkin-close" className={`${PILL} mt-5 w-full bg-slate-900 text-white`}>Done</button>
          </div>
        ) : (
          <>
            <label className="mt-4 block"><span className="text-xs font-bold text-slate-600">Guest name</span>
              <input value={f.guest_name} onChange={(e) => setF({ ...f, guest_name: e.target.value })}
                data-testid="walkin-name" className={IN} placeholder="Who's coming in?" /></label>
            <div className="mt-3 grid grid-cols-2 gap-3">
              <label className="block"><span className="text-xs font-bold text-slate-600">Guests</span>
                <input type="number" min="1" value={f.quantity} onChange={(e) => setF({ ...f, quantity: e.target.value })}
                  data-testid="walkin-quantity" className={IN} /></label>
              <label className="block"><span className="text-xs font-bold text-slate-600">Amount collected</span>
                <input value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })}
                  data-testid="walkin-amount" inputMode="decimal" className={IN} placeholder="0.00" /></label>
            </div>
            <label className="mt-3 block"><span className="text-xs font-bold text-slate-600">Phone (optional)</span>
              <input value={f.guest_phone} onChange={(e) => setF({ ...f, guest_phone: e.target.value })}
                data-testid="walkin-phone" className={IN} /></label>
            <label className="mt-3 block">
              <span className="text-xs font-bold text-slate-600">
                Email {method === "paypal_link" ? "(required for a pay link)" : "(optional)"}
              </span>
              <input value={f.guest_email} onChange={(e) => setF({ ...f, guest_email: e.target.value })}
                data-testid="walkin-email" className={IN} placeholder="guest@email.com" /></label>
            <div className="mt-4 grid grid-cols-2 gap-2">
              {METHODS.map(([v, label]) => (
                <button key={v} onClick={() => setMethod(v)} data-testid={`walkin-method-${v}`}
                  className={`${PILL} border ${method === v ? "bg-slate-900 text-white border-slate-900" : "border-slate-200"}`}>
                  {label}
                </button>
              ))}
            </div>
            <p className="mt-3 text-xs text-slate-500">
              {method === "paypal_link"
                ? "We message the guest a PayPal payment request. Their pass is issued the moment PayPal confirms."
                : "Recorded as collected by you — Buddilio's commission comes off your next settlement, and the guest is checked in straight away."}
            </p>
            <div className="mt-5 flex gap-2">
              <button onClick={submit} disabled={busy} data-testid="walkin-submit"
                className={`${PILL} flex-1 bg-slate-900 text-white disabled:opacity-60`}>
                {busy ? "Saving…" : method === "paypal_link" ? "Send pay link" : "Take payment & check in"}
              </button>
              <button onClick={onClose} data-testid="walkin-cancel" className={`${PILL} border border-slate-200`}>Cancel</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default WalkInDialog;
